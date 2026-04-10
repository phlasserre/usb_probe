#!/usr/bin/env python3

# =================================
# ----         USAGE          -----
# =================================
# This script is intended for MacOS users needing to check USB flash drive real capacity

# (1) plug the USB key in USB port
# if USB key is 'mounted' (by MacOS), do :
#   diskutil list 
# identify your usb key in above list ; then unmount it : example for /dev/disk4
#	diskutil unmountDisk /dev/disk4

# (2) select either --quick, --deep, or --probeXXX (drive size), or detailed params
# "Quick" test (64 blocs × 4 KiB, 1 pass → 256 KiB written) :
#   sudo python3 usb_size_proof.py /dev/rdisk4 --quick
# note : adapt '/dev/rdisk4' to your drive (replace '4' by your drive number)

# “Normal” test allows for detailed params for test (ex: 2048 blocks × 1 MiB, 2 passes) :
#   sudo python3 usb_size_proof.py /dev/rdisk4 --samples 2048 --block-kib 1024 --passes 2
# whatever the number of writting phases, there is only one reading, checking the last writen values

# "Deep" Test :
#   sudo python3 usb_size_proof.py /dev/rdisk4 --deep
# --deep is equivalent to : --samples 4096 --block-kib 1024 --passes 2 --flush-every 256 --use-sync true

# Predefined Tests  :
#   --probe64   : ~64 MiB written (1024 × 64 KiB, 1 pass)
#   --probe128  : ~128 MiB
#   --probe256  : ~256 MiB
#   --probe512  : ~128 MiB
#   --probe1T   : ~256 MiB

# (3) after writing phase, you will have to physically unplug the key, 
# wait 5 seconds, then physically re-plug the USB key
# MacOS : wait for dialogbox to propose 'eject', 'ignore', 'initialize...' : click 'ignore'
# press 'Return' key when ready
# reading/checking phase is usually much faster that writing
# =================================

import os
import sys
import time
import json
import random
import struct
import hashlib
import secrets
import argparse
import fcntl
import subprocess

MAGIC = b"CAPTEST1"
HEADER_FMT = ">8sQIQ16s32s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
DKIOCGETBLOCKSIZE = 0x40046418
DKIOCGETBLOCKCOUNT = 0x40086419

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def fmt_seconds(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class Progress:
    def __init__(self, total, label="", bytes_per_item=None):
        self.total = max(1, total)
        self.label = label
        self.bytes_per_item = bytes_per_item
        self.start = time.monotonic()
        self.last_draw = 0.0
        self.draw_interval = 0.2

    def update(self, current, force=False):
        now = time.monotonic()
        if not force and (now - self.last_draw) < self.draw_interval and current < self.total:
            return

        elapsed = now - self.start
        ratio = min(max(current / self.total, 0.0), 1.0)
        percent = ratio * 100.0

        eta = 0.0
        if current > 0 and ratio > 0:
            total_est = elapsed / ratio
            eta = max(0.0, total_est - elapsed)

        bar_width = 28
        filled = int(bar_width * ratio)
        bar = "#" * filled + "-" * (bar_width - filled)

        speed_txt = ""
        if self.bytes_per_item and elapsed > 0 and current > 0:
            mib_done = (current * self.bytes_per_item) / (1024 * 1024)
            mib_s = mib_done / elapsed
            speed_txt = f" | {mib_s:6.1f} MiB/s"

        msg = (
            f"\r{self.label:10s} [{bar}] "
            f"{current:4d}/{self.total:<4d} "
            f"{percent:6.2f}%"
            f"{speed_txt} | elapsed {fmt_seconds(elapsed)} | ETA {fmt_seconds(eta)}"
        )
        sys.stdout.write(msg)
        sys.stdout.flush()
        self.last_draw = now

        if current >= self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()

def get_disk_size(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        buf = bytearray(4)
        fcntl.ioctl(fd, DKIOCGETBLOCKSIZE, buf, True)
        block_size = struct.unpack("I", buf)[0]

        buf = bytearray(8)
        fcntl.ioctl(fd, DKIOCGETBLOCKCOUNT, buf, True)
        block_count = struct.unpack("Q", buf)[0]

        return block_size * block_count
    finally:
        os.close(fd)

def build_block(offset, pass_id, block_size, session_nonce):
    seed = sha256(struct.pack(">QIQ16s", offset, pass_id, block_size, session_nonce))
    payload = bytearray(block_size - HEADER_SIZE)
    chunk = seed
    pos = 0
    while pos < len(payload):
        chunk = sha256(chunk + struct.pack(">QI", offset, pass_id))
        n = min(len(chunk), len(payload) - pos)
        payload[pos:pos+n] = chunk[:n]
        pos += n
    digest = sha256(payload)
    header = struct.pack(HEADER_FMT, MAGIC, offset, pass_id, block_size, session_nonce, digest)
    return header + payload

def parse_and_check(block, expected_offset, expected_pass, expected_block_size, session_nonce):
    if len(block) != expected_block_size:
        return ("short-read", None)
    try:
        magic, offset, pass_id, block_size, nonce, digest = struct.unpack(
            HEADER_FMT, block[:HEADER_SIZE]
        )
    except struct.error:
        return ("bad-header", None)

    if magic != MAGIC:
        return ("bad-magic", None)

    payload = block[HEADER_SIZE:]
    got_digest = sha256(payload)
    meta = {
        "offset": offset,
        "pass_id": pass_id,
        "block_size": block_size,
        "nonce_ok": nonce == session_nonce,
        "digest_ok": got_digest == digest,
    }

    if nonce != session_nonce:
        return ("foreign-session", meta)
    if block_size != expected_block_size:
        return ("wrong-block-size", meta)
    if got_digest != digest:
        return ("payload-corrupt", meta)
    if offset != expected_offset or pass_id != expected_pass:
        return ("misplaced", meta)
    return ("ok", meta)

def choose_offsets(device_size, block_size, sample_count):
    if block_size <= 0:
        raise RuntimeError("block_size is invalid")
    if device_size <= block_size:
        raise RuntimeError(
            f"device is too samll: device_size={device_size} block_size={block_size}"
        )

    usable = device_size - block_size
    offsets = set()
    anchors = [
        0,
        min(block_size, usable),
        usable // 4,
        usable // 2,
        (usable * 3) // 4,
        usable,
    ]
    for x in anchors:
        offsets.add((x // 4096) * 4096)

    rnd = random.Random(0xC0FFEE)
    while len(offsets) < sample_count:
        x = rnd.randrange(0, usable + 1)
        offsets.add((x // 4096) * 4096)

    return sorted(offsets)

def open_rw(path, use_sync=True):
    flags = os.O_RDWR
    if use_sync and hasattr(os, "O_SYNC"):
        flags |= os.O_SYNC
    return os.open(path, flags)

def flush_fd(fd):
    os.fsync(fd)

def main():
    if os.geteuid() != 0:
        print("Ce script doit être lancé avec sudo.", file=sys.stderr)
        sys.exit(2)

    parser = argparse.ArgumentParser()
    parser.add_argument("device", help="/dev/rdiskN")
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--block-kib", type=int, default=1024, help="block size in KiB (default 1024 = 1 MiB)")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--flush-every", type=int, default=256, help="0 = never (unless end of phase)")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--probe64", action="store_true")
    parser.add_argument("--probe128", action="store_true")
    parser.add_argument("--probe256", action="store_true")
    parser.add_argument("--probe512", action="store_true")
    parser.add_argument("--probe1T", action="store_true")
    args = parser.parse_args()

    dev = args.device
    if not dev.startswith("/dev/rdisk"):
        print("please use a raw peripheral /dev/rdiskN, not /dev/diskN nor a partition.", file=sys.stderr)
        sys.exit(2)

    sample_count = args.samples
    block_kib = args.block_kib
    passes = args.passes
    flush_every = args.flush_every
    use_sync = True

    # Presets per maximum nominal capacity 
    if args.probe64:
        sample_count = 1024
        block_kib = 64
        passes = 1
        flush_every = 128
        use_sync = True

    if args.probe128:
        sample_count = 2048
        block_kib = 64
        passes = 1
        flush_every = 256
        use_sync = True

    if args.probe256:
        sample_count = 4096
        block_kib = 64
        passes = 1
        flush_every = 256
        use_sync = True

    if args.probe512:
        sample_count = 2048
        block_kib = 64
        passes = 1
        flush_every = 256
        use_sync = True

    if args.probe1T:
        sample_count = 4096
        block_kib = 64
        passes = 1
        flush_every = 512
        use_sync = True

    # Quick Profile : few seconds / minutes
    if args.quick:
        sample_count = min(sample_count, 64)
        block_kib = min(block_kib, 4)   # 4 KiB
        passes = 1
        flush_every = 0                 # no intermediate flush 
        use_sync = False                # don't force O_SYNC

    # Deep Profile : more agressive
    if args.deep:
        sample_count = max(sample_count, 4096)
        block_kib = max(block_kib, 1024)  # 1 MiB
        passes = max(passes, 2)
        flush_every = max(flush_every, 256)
        use_sync = True

    block_size = block_kib * 1024
    if block_size <= HEADER_SIZE:
        print("block_size is too small to contain header.", file=sys.stderr)
        sys.exit(2)

    device_size = get_disk_size(dev)
    session_nonce = secrets.token_bytes(16)
    offsets = choose_offsets(device_size, block_size, sample_count)

    mode = "normal"
    if args.quick:
        mode = "quick"
    elif args.deep:
        mode = "deep"
    elif args.probe64:
        mode = "probe64"
    elif args.probe128:
        mode = "probe128"
    elif args.probe256:
        mode = "probe256"
    elif args.probe512:
        mode = "probe512"
    elif args.probe1T:
        mode = "probe1T"

    manifest = {
        "device": dev,
        "device_size": device_size,
        "device_size_gib": round(device_size / (1024**3), 2),
        "sample_count": sample_count,
        "block_size": block_size,
        "block_size_kib": block_kib,
        "passes": passes,
        "read_pass_mode": "last-only",
        "flush_every": flush_every,
        "session_nonce_hex": session_nonce.hex(),
        "offsets": offsets,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
    }

    os.makedirs("output", exist_ok=True)
    manifest_path = os.path.join("output", "captest_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    total_write_bytes = sample_count * block_size * passes
    print(json.dumps({
        "device": dev,
        "device_size_gib": round(device_size / (1024**3), 2),
        "sample_count": sample_count,
        "block_size_kib": block_kib,
        "passes": passes,
        "flush_every": flush_every,
        "total_write_mib": round(total_write_bytes / (1024**2), 2),
        "mode": manifest["mode"],
    }, indent=2))
    print(f"Manifest: {manifest_path}")

    # Writing Phase
    fd = open_rw(dev, use_sync=use_sync)
    try:
        for pass_id in range(1, passes + 1):
            prog = Progress(len(offsets), label=f"write P{pass_id}", bytes_per_item=block_size)
            for i, offset in enumerate(offsets, 1):
                block = build_block(offset, pass_id, block_size, session_nonce)
                n = os.pwrite(fd, block, offset)
                if n != len(block):
                    raise RuntimeError(f"partial writing at {offset}: {n}/{len(block)}")
                if flush_every > 0 and (i % flush_every == 0):
                    flush_fd(fd)
                prog.update(i)
            flush_fd(fd)
            prog.update(len(offsets), force=True)
    finally:
        os.close(fd)

    print("\nIMPORTANT: physically eject then reconnect the key now.")
    print("IMPORTANT: on MacOS, wait for dialog box then click 'ignore' (no 'eject' nor 'initialize').")
    input("Push the 'Enter' key to launch the Reading Phase... ")

    # Phase lecture + stats par bandes
    fd = os.open(dev, os.O_RDONLY)
    try:
        read_order = offsets[:]
        random.Random(0xBAD5EED).shuffle(read_order)

        stats = {
            "ok": 0,
            "misplaced": 0,
            "payload-corrupt": 0,
            "bad-header": 0,
            "bad-magic": 0,
            "foreign-session": 0,
            "wrong-block-size": 0,
            "short-read": 0,
        }
        misplaced_examples = []

        # bandes 0–25, 25–50, 50–75, 75–100 %
        bands = {
            "0-25": {"ok": 0, "errors": 0},
            "25-50": {"ok": 0, "errors": 0},
            "50-75": {"ok": 0, "errors": 0},
            "75-100": {"ok": 0, "errors": 0},
        }

        def band_for_offset(off, dev_size):
            ratio = off / dev_size if dev_size > 0 else 0.0
            if ratio < 0.25:
                return "0-25"
            elif ratio < 0.50:
                return "25-50"
            elif ratio < 0.75:
                return "50-75"
            else:
                return "75-100"

        expected_pass = passes
        prog = Progress(len(read_order), label=f"read P{expected_pass}", bytes_per_item=block_size)

        for i, offset in enumerate(read_order, 1):
            data = os.pread(fd, block_size, offset)
            status, meta = parse_and_check(data, offset, expected_pass, block_size, session_nonce)
            stats[status] = stats.get(status, 0) + 1

            band = band_for_offset(offset, device_size)
            if status == "ok":
                bands[band]["ok"] += 1
            else:
                bands[band]["errors"] += 1

            if status == "misplaced" and len(misplaced_examples) < 20 and meta:
                misplaced_examples.append({
                    "expected_offset": offset,
                    "found_offset": meta["offset"],
                    "expected_pass": expected_pass,
                    "found_pass": meta["pass_id"],
                })
            prog.update(i)
        prog.update(len(read_order), force=True)

        print("\nResults:")
        print(json.dumps(stats, indent=2))

        if misplaced_examples:
            print("\nExamples of collisions / wraparound probability:")
            print(json.dumps(misplaced_examples, indent=2))

        print("\nDistribution per range (% of logical capacity):")
        print(json.dumps(bands, indent=2))

        # Simple Estimate of capacity "probably healthy"
        # Heuristic : considering a range is "healthy" if errors <= 5 % of samples in that range.
        healthy_up_to_ratio = 0.0
        band_edges = [("0-25", 0.25), ("25-50", 0.50), ("50-75", 0.75), ("75-100", 1.00)]

        for name, edge in band_edges:
            b = bands[name]
            total_band = b["ok"] + b["errors"]
            if total_band == 0:
                # no sample in that range, no conclusion here
                break
            err_ratio = b["errors"] / total_band
            if err_ratio <= 0.05:
                healthy_up_to_ratio = edge
            else:
                break

        healthy_bytes = healthy_up_to_ratio * device_size
        healthy_gib = healthy_bytes / (1024 ** 3)

        print("\nEstimated capacity probably healthy (heuristic):")
        if healthy_up_to_ratio == 0.0:
            print("  Impossible to estimate a contiguous healthy zone (too many errors since beginning).")
        elif healthy_up_to_ratio >= 0.99:
            print(f"  The test suggest an announced capacity probably consistent (at least ~{healthy_gib:.2f} GiB).")
        else:
            print(f"  The capacity seem healthy till around ~{healthy_gib:.2f} GiB "
                  f"({healthy_up_to_ratio*100:.0f} % of logical space).")
            print("  Beyond, error rate increase significantly : the key can be fake or very much damaged.")

    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
