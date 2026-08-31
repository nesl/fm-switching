#!/usr/bin/env python3
"""
Study E — thermal / clock sampler (Jetson AGX Orin).

Reads sysfs directly (no sudo, no tegrastats) every INTERVAL seconds and logs
temperatures, GPU clock, and a throttle flag to CSV. Runs until SIGTERM/SIGINT.

Throttle detection: GPU cur_freq < locked max (jetson_clocks pins it to
MAX_GPU_FREQ_HZ; any drop below indicates thermal/power clock capping).

Columns: iso_time, elapsed_s, tj_c, gpu_c, cpu_c, soc0_c, gpu_freq_hz, gpu_throttled
"""
import argparse
import csv
import glob
import os
import signal
import sys
import time

GPU_FREQ_PATH = "/sys/devices/platform/bus@0/17000000.gpu/devfreq/17000000.gpu/cur_freq"
MAX_GPU_FREQ_HZ = 1300500000  # jetson_clocks-locked max on AGX Orin 64GB


def discover_zones():
    """Map thermal-zone type -> temp file path."""
    zones = {}
    for zdir in glob.glob("/sys/devices/virtual/thermal/thermal_zone*"):
        try:
            ztype = open(os.path.join(zdir, "type")).read().strip()
            zones[ztype] = os.path.join(zdir, "temp")
        except Exception:
            pass
    return zones


def read_c(path):
    try:
        return int(open(path).read().strip()) / 1000.0
    except Exception:
        return None


_run = True


def _stop(sig, frame):
    global _run
    _run = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-gpu-freq", type=int, default=MAX_GPU_FREQ_HZ)
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    zones = discover_zones()
    tj  = zones.get("tj-thermal")
    gpu = zones.get("gpu-thermal")
    cpu = zones.get("cpu-thermal")
    soc0 = zones.get("soc0-thermal")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    f = open(args.out, "w", newline="")
    w = csv.writer(f)
    w.writerow(["iso_time", "elapsed_s", "tj_c", "gpu_c", "cpu_c", "soc0_c",
                "gpu_freq_hz", "gpu_throttled"])
    f.flush()

    t0 = time.time()
    while _run:
        now = time.time()
        try:
            freq_hz = int(open(GPU_FREQ_PATH).read().strip())
        except Exception:
            freq_hz = None
        throttled = (freq_hz is not None and freq_hz < args.max_gpu_freq)
        w.writerow([
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            round(now - t0, 1),
            read_c(tj) if tj else "",
            read_c(gpu) if gpu else "",
            read_c(cpu) if cpu else "",
            read_c(soc0) if soc0 else "",
            freq_hz if freq_hz is not None else "",
            int(throttled),
        ])
        f.flush()
        # sleep in small steps so SIGTERM is responsive
        slept = 0.0
        while _run and slept < args.interval:
            time.sleep(min(0.5, args.interval - slept))
            slept += 0.5

    f.close()


if __name__ == "__main__":
    main()
