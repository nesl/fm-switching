#!/usr/bin/env python3
"""Run N device slices concurrently as real network clients. Runs on flash (A6000).

StudyREAL-NET, component 4.

WHY THE EMULATED FLEET IS A NETWORK CLIENT AND NOT AN IN-PROCESS OBJECT. In live2 today the
emulated devices live inside the `FleetEmulator` process and reach the coordinator through a
Python call, so their events arrive with no transport cost at all while a real device pays
one. That difference sits directly inside the quantity the study measures. Moving the emulated
fleet onto flash and over a real socket makes the transport model UNIFORM across all 16
devices: every event, real or emulated, arrives the same way.

Measured on 2026-11-25, flash -> H100 is the best path in the lab: p50 0.761 ms, stdev
0.032 ms, single hop, 10 GbE both ends. Its jitter is 11.6x lower than orin-1's, so an
emulated device contributes about 1/10th as much measurement noise as a real board -- which
is the right way round.

One thread per device. 12 threads of mostly-sleeping socket I/O on a 24-thread host at load
~1.5 is not a scheduling concern; threads keep each device's send schedule independent without
an event loop.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from device_agent import DeviceAgent  # noqa: E402


class FleetRunner:
    """Drives several DeviceAgents at once, each on its own connection."""

    def __init__(self, slice_root: Path, devices: Sequence[str], host: str, port: int,
                 frames_root: Optional[Path] = None, synthetic_frames: bool = False,
                 speed: float = 1.0) -> None:
        self.slice_root = Path(slice_root)
        self.devices = list(devices)
        self.host, self.port = host, int(port)
        self.frames_root = frames_root
        self.synthetic = synthetic_frames
        self.speed = speed
        self.agents: Dict[str, DeviceAgent] = {}
        self.results: Dict[str, Any] = {}
        self.failures: Dict[str, str] = {}

    def _one(self, d: str) -> None:
        try:
            ag = DeviceAgent(self.slice_root / d, self.host, self.port,
                             self.frames_root, self.synthetic, self.speed)
            self.agents[d] = ag
            self.results[d] = ag.run()
        except Exception as e:
            self.failures[d] = "%s: %s" % (type(e).__name__, e)

    def run(self, out_dir: Optional[Path] = None) -> Dict[str, Any]:
        threads = []
        for d in self.devices:
            th = threading.Thread(target=self._one, args=(d,), name="dev-" + d)
            th.daemon = True
            th.start()
            threads.append(th)
        for th in threads:
            th.join()
        if out_dir:
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            for d, ag in self.agents.items():
                ag.write_log(out_dir)
        n_res = sum(r.get("n_resolved", 0) for r in self.results.values())
        n_cloud = sum(r.get("n_cloud", 0) for r in self.results.values())
        return dict(
            n_devices=len(self.devices), n_ok=len(self.results),
            n_failed=len(self.failures), failures=self.failures,
            n_resolved=n_res, n_cloud=n_cloud, n_device=n_res - n_cloud,
            cloud_frac=(round(n_cloud / n_res, 4) if n_res else None),
            per_device={d: dict(type=r.get("type"), n_resolved=r.get("n_resolved"),
                                n_cloud=r.get("n_cloud"), n_device=r.get("n_device"),
                                bytes_sent=(r.get("wire") or {}).get("bytes_sent"),
                                recv_error=r.get("recv_error"))
                        for d, r in sorted(self.results.items())},
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run several device slices as network clients")
    ap.add_argument("--slice-root", required=True)
    ap.add_argument("--devices", required=True,
                    help="comma-separated device ids, or 'all' for every slice present")
    ap.add_argument("--server", required=True, help="host:port")
    ap.add_argument("--frames-root", default=None)
    ap.add_argument("--synthetic-frames", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    root = Path(a.slice_root)
    if a.devices == "all":
        devs = sorted(p.name for p in root.iterdir()
                      if p.is_dir() and (p / "slice_meta.json").exists())
    else:
        devs = [d.strip() for d in a.devices.split(",") if d.strip()]
    host, _, port = a.server.rpartition(":")
    fr = FleetRunner(root, devs, host, int(port),
                     Path(a.frames_root) if a.frames_root else None,
                     a.synthetic_frames, a.speed)
    summ = fr.run(Path(a.out) if a.out else None)
    print(json.dumps(summ, indent=2, sort_keys=True))
    return 0 if summ["n_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
