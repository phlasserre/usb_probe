# usb_probe
Assess real USB flashdrive size, and R/W speeds<br>
<br>
This is a python3 script, intended for MacOS users needing to check USB flash drive real capacity<br>
<br>
1.) plug the USB key in USB port<br>
if USB key is 'mounted' (by MacOS), do :<br>
   diskutil list <br>
identify your usb key in above list ; then unmount it : example for /dev/disk4<br>
  diskutil unmountDisk /dev/disk4<br>
<br>
2.) select either --quick, --deep, or --probeXXX (drive size), or detailed params<br>
2.1) "Quick" test (64 blocs × 4 KiB, 1 pass → 256 KiB written) :<br>
   sudo python3 usb_probe.py /dev/rdisk4 --quick<br>
note : adapt '/dev/rdisk4' to your drive (replace '4' by your drive number)<br>
<br>
2.2) “Normal” test allows for detailed params for test (ex: 2048 blocks × 1 MiB, 2 passes) :<br>
   sudo python3 usb_probe.py /dev/rdisk4 --samples 2048 --block-kib 1024 --passes 2<br>
whatever the number of writting phases, there is only one reading, checking the last writen values<br>
<br>
2.3) "Deep" Test :<br>
   sudo python3 usb_probe.py /dev/rdisk4 --deep<br>
--deep is equivalent to : --samples 4096 --block-kib 1024 --passes 2 --flush-every 256 --use-sync true<br>
<br>
2.4) Predefined Tests, generally sufficient :<br>
   --probe64   : ~64 MiB written (1024 × 64 KiB, 1 pass)<br>
   --probe128  : ~128 MiB<br>
   --probe256  : ~256 MiB<br>
   --probe512  : ~128 MiB<br>
   --probe1T   : ~256 MiB<br>
<br>
3.) after writing phase, you will have to physically unplug the key, <br>
* wait 5 seconds, then physically re-plug the USB key<br>
* on MacOS : wait for dialogbox to propose 'eject', 'ignore', 'initialize...' : click 'ignore'<br>
* press 'Return' key when ready<br>
* reading/checking phase is usually much faster that writing<br>
<br>
Results shown according to test finding.<br>
<br>
Result example for a fake key (purchased on Amazon as a 512Go key) :<br>
- - - - - - - - - -<br>
sudo python3 usb_probe.py /dev/rdisk4 --probe512<br>
{<br>
  "device": "/dev/rdisk4",<br>
  "device_size_gib": 486.56,    <- logical claim 512Go<br>
  "sample_count": 2048,<br>
  "block_size_kib": 64,<br>
  "passes": 1,<br>
  "flush_every": 256,<br>
  "total_write_mib": 128.0,<br>
  "mode": "probe512"<br>
}<br>
Manifest: output/captest_manifest.json<br>
write P1   [############################] 2048/2048 100.00% |   12.9 MiB/s | elapsed 00:09 | ETA 00:00<br>
write P1   [############################] 2048/2048 100.00% |   12.9 MiB/s | elapsed 00:09 | ETA 00:00<br>
<br>
IMPORTANT: physically eject then reconnect the key now.<br>
IMPORTANT: on MacOS, wait for dialog box then click 'ignore' (no 'eject' nor 'initialize').<br>
Push the 'Enter' key to launch the Reading Phase... <br>
read P1    [############################] 2048/2048 100.00% |   19.6 MiB/s | elapsed 00:06 | ETA 00:00<br>
read P1    [############################] 2048/2048 100.00% |   19.6 MiB/s | elapsed 00:06 | ETA 00:00<br>
<br>
Résults:<br>
{<br>
  "ok": 495,<br>
  "misplaced": 0,<br>
  "payload-corrupt": 0,<br>
  "bad-header": 0,<br>
  "bad-magic": 1553,<br>
  "foreign-session": 0,<br>
  "wrong-block-size": 0,<br>
  "short-read": 0<br>
}<br>
<br>
Distribution per zones (% of logical capacity):<br>
{<br>
  "0-25": {<br>
    "ok": 495,<br>
    "errors": 25        <- usable<br>
  },<br>
  "25-50": {<br>
    "ok": 0,<br>
    "errors": 513       <- cannot be used<br>
  },<br>
  "50-75": {<br>
    "ok": 0,<br>
    "errors": 504       <- cannot be used<br>
  },<br>
  "75-100": {<br>
    "ok": 0,<br>
    "errors": 511       <- cannot be used<br>
  }<br>
}<br>
<br>
Estimated capacity probably healthy (heuristic):<br>
  Capacité seem healthy till around ~121.64 GiB (25 % of logical space).<br>
  Beyond, the error rate increase significantly : the key can be either fake or very much damaged.<br>
<br>
- - - - - - - - - - - - - - - - - -<br>
Result example for a reliable key<br>
- - - - - - - - - - - - - - - - - - <br>
sudo python3 usb_probe.py /dev/rdisk4 --samples 4096 --block-kib 1024 --passes 2<br>
Password:<br>
{<br>
  "device": "/dev/rdisk4",<br>
  "device_size_gib": 114.61,<br>
  "sample_count": 4096,<br>
  "block_size_kib": 1024,<br>
  "passes": 2,<br>
  "flush_every": 256,<br>
  "total_write_mib": 8192.0,<br>
  "mode": "normal"<br>
}<br>
Manifest: output/captest_manifest.json<br>
write P1   [############################] 4096/4096 100.00% |   16.2 MiB/s | elapsed 04:13 | ETA 00:00<br>
write P1   [############################] 4096/4096 100.00% |   16.2 MiB/s | elapsed 04:13 | ETA 00:00<br>
write P2   [############################] 4096/4096 100.00% |   16.0 MiB/s | elapsed 04:15 | ETA 00:00<br>
write P2   [############################] 4096/4096 100.00% |   16.0 MiB/s | elapsed 04:15 | ETA 00:00<br>
<br>
IMPORTANT: physically eject then reconnect the key now.<br>
IMPORTANT: on MacOS, wait for dialog box then click 'ignore' (no 'eject' nor 'initialize').<br>
Push the 'Enter' key to launch the Reading Phase... <br>
read P2    [############################] 4096/4096 100.00% |  129.0 MiB/s | elapsed 00:31 | ETA 00:00<br>
read P2    [############################] 4096/4096 100.00% |  129.0 MiB/s | elapsed 00:31 | ETA 00:00<br>
<br>
Results:<br>
{<br>
  "ok": 3947,<br>
  "misplaced": 0,<br>
  "payload-corrupt": 149,<br>
  "bad-header": 0,<br>
  "bad-magic": 0,<br>
  "foreign-session": 0,<br>
  "wrong-block-size": 0,<br>
  "short-read": 0<br>
}<br>
<br>
Distribution per range (% of logical capacity):<br>
{<br>
  "0-25": {<br>
    "ok": 971,<br>
    "errors": 38<br>
  },<br>
  "25-50": {<br>
    "ok": 1016,<br>
    "errors": 34<br>
  },<br>
  "50-75": {<br>
    "ok": 953,<br>
    "errors": 31<br>
  },<br>
  "75-100": {<br>
    "ok": 1007,<br>
    "errors": 46<br>
  }<br>
  - - - - - - - - - - - - - - - -<br>
  
}

Estimated capacity probably healthy (heuristic):
  The test suggest an announced capacity annoncée probably consistent (at least ~114.61 GiB).
