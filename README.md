# usb_probe

Efficiently assess the **real** capacity and R/W speeds of USB flash drives on macOS.

`usb_probe` is a Python 3 CLI tool for macOS users who need to verify whether a USB flash drive’s advertised capacity is genuine and how healthy it is across its address space.

## Features

- Works directly on the raw device (`/dev/rdiskN`) for realistic testing.
- Supports quick, deep and predefined “probe” modes.
- Uses sparse, randomized sampling instead of writing every byte.
- Provides a heuristic estimate of the safely usable capacity.
- Shows progress bars with throughput and ETA for each phase.

## Prerequisites

- macOS
- Python 3
- Administrator privileges (`sudo`)
- A USB flash drive you are willing to **destroy** (all data on the tested drive will be lost).

## Safety warning

This tool is **destructive**: it writes directly to the raw disk device.

- Always double-check the target device with `diskutil list` before running the script.
- Never run it on your internal disk or on any disk that contains valuable data.

Example to identify and unmount your USB drive:

```bash
diskutil list
diskutil unmountDisk /dev/disk4
```

Then use the corresponding **raw** device, e.g. `/dev/rdisk4`.

## Basic usage

General syntax:

```bash
sudo python3 usb_probe.py /dev/rdiskN [mode/options...]
```

Replace `N` with the correct disk number for your USB drive.

### Quick test

Minimal, fast sanity check (e.g. 64 blocks × 4 KiB, 1 pass → 256 KiB written):

```bash
sudo python3 usb_probe.py /dev/rdisk4 --quick
```

This mode is useful to verify that the tool works correctly on your system and that you are targeting the right device.

### Normal / custom test

“Normal” tests allow you to specify detailed parameters, for example:

```bash
sudo python3 usb_probe.py /dev/rdisk4 \
  --samples 2048 \
  --block-kib 1024 \
  --passes 2
```

- `--samples` : number of sampled offsets.
- `--block-kib` : block size in KiB.
- `--passes` : number of write passes.

Regardless of the number of write passes, there is a **single** read phase that checks the last written values at each sampled offset.

### Deep test

More intensive test with higher coverage:

```bash
sudo python3 usb_probe.py /dev/rdisk4 --deep
```

`--deep` is equivalent to:

```text
--samples 4096 --block-kib 1024 --passes 2 --flush-every 256 --use-sync true
```

This can take several minutes on large or slow drives, but gives a more robust picture of the usable capacity.

### Predefined probe modes

These modes are convenient presets that write a moderate amount of data, generally sufficient to detect gross fraud or serious defects:

```text
--probe64   : ~64 MiB written   (1024 × 64 KiB, 1 pass)
--probe128  : ~128 MiB
--probe256  : ~256 MiB
--probe512  : ~128 MiB
--probe1T   : ~256 MiB
```

Example:

```bash
sudo python3 usb_probe.py /dev/rdisk4 --probe512
```

## Required unplug / replug step

After the write phase completes, the tool requires a **physical reset** of the drive to avoid false positives due to OS or controller caches.

The typical sequence is:

1. Wait for the write phase to reach 100 %.
2. Physically unplug the USB key.
3. Wait about 5 seconds, then plug it back in.
4. On macOS, when the dialog proposes “Eject”, “Ignore”, “Initialize…”, click **Ignore**.
5. Go back to the terminal and press **Enter** to start the read / verification phase.

The read phase is usually much faster than the write phase.

## Example: fake “512 GB” drive

Example run on a fake USB key bought as “512 GB”:

```bash
sudo python3 usb_probe.py /dev/rdisk4 --probe512
```

Manifest and write phase:

```text
{
  "device": "/dev/rdisk4",
  "device_size_gib": 486.56,      <- logical claim ~512 GB
  "sample_count": 2048,
  "block_size_kib": 64,
  "passes": 1,
  "flush_every": 256,
  "total_write_mib": 128.0,
  "mode": "probe512"
}
Manifest: output/captest_manifest.json

write P1   [############################] 2048/2048 100.00% |   12.9 MiB/s | elapsed 00:09 | ETA 00:00
```

Prompt to reset the key and read phase:

```text
IMPORTANT: physically eject then reconnect the key now.
IMPORTANT: on macOS, wait for dialog box then click 'Ignore' (not 'Eject' or 'Initialize').
Press the Enter key to start the Reading Phase...

read P1    [############################] 2048/2048 100.00% |   19.6 MiB/s | elapsed 00:06 | ETA 00:00
```

Error statistics:

```text
Results:
{
  "ok": 495,
  "misplaced": 0,
  "payload-corrupt": 0,
  "bad-header": 0,
  "bad-magic": 1553,
  "foreign-session": 0,
  "wrong-block-size": 0,
  "short-read": 0
}
```

Distribution per logical capacity range:

```text
{
  "0-25": {
    "ok": 495,
    "errors": 25          <- usable
  },
  "25-50": {
    "ok": 0,
    "errors": 513         <- cannot be used
  },
  "50-75": {
    "ok": 0,
    "errors": 504         <- cannot be used
  },
  "75-100": {
    "ok": 0,
    "errors": 511         <- cannot be used
  }
}
```

Heuristic capacity estimate:

```text
Estimated healthy capacity (heuristic):
  Capacity appears healthy up to ~121.64 GiB (about 25% of logical space).
  Beyond this point, the error rate increases significantly: the drive is either fake or severely damaged.
```

## Example: reliable drive

Example on a trustworthy drive:

```bash
sudo python3 usb_probe.py /dev/rdisk4 --samples 4096 --block-kib 1024 --passes 2
```

Manifest and write phase:

```text
{
  "device": "/dev/rdisk4",
  "device_size_gib": 114.61,
  "sample_count": 4096,
  "block_size_kib": 1024,
  "passes": 2,
  "flush_every": 256,
  "total_write_mib": 8192.0,
  "mode": "normal"
}
Manifest: output/captest_manifest.json

write P1   [############################] 4096/4096 100.00% |   16.2 MiB/s | elapsed 04:13 | ETA 00:00
write P2   [############################] 4096/4096 100.00% |   16.0 MiB/s | elapsed 04:15 | ETA 00:00
```

Reset + read phase:

```text
IMPORTANT: physically eject then reconnect the key now.
IMPORTANT: on macOS, wait for dialog box then click 'Ignore' (not 'Eject' or 'Initialize').
Press the Enter key to start the Reading Phase...

read P2    [############################] 4096/4096 100.00% |  129.0 MiB/s | elapsed 00:31 | ETA 00:00
```

Error statistics:

```text
Results:
{
  "ok": 3947,
  "misplaced": 0,
  "payload-corrupt": 149,
  "bad-header": 0,
  "bad-magic": 0,
  "foreign-session": 0,
  "wrong-block-size": 0,
  "short-read": 0
}
```

Distribution per logical capacity range:

```text
{
  "0-25": {
    "ok": 971,
    "errors": 38
  },
  "25-50": {
    "ok": 1016,
    "errors": 34
  },
  "50-75": {
    "ok": 953,
    "errors": 31
  },
  "75-100": {
    "ok": 1007,
    "errors": 46
  }
}
```

Heuristic capacity estimate:

```text
Estimated healthy capacity (heuristic):
  The test suggests that the advertised capacity is probably consistent
  (at least ~114.61 GiB of logical space appears usable).
```

## License

[MIT](LICENSE) : Free to use and modify ; Attribution required.

If you reuse/modify, be kind enough to inform me (e.g., open an issue, send a mail, or link your fork).
