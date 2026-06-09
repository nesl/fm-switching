"""
Step 2: Generate synthetic network RTT traces.

Each trace is 600 samples (1 sample/sec, 10 minutes). Columns:
    time_s, rtt_ms, bandwidth_mbps, connected
"""

import csv
import math
import random
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "traces" / "network"
OUT.mkdir(parents=True, exist_ok=True)


def write_trace(name, samples):
    path = OUT / f"net_{name}.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "rtt_ms", "bandwidth_mbps", "connected"])
        for row in samples:
            w.writerow(row)
    print(f"  Wrote {path.relative_to(ROOT)}")


def make_stable(n=600):
    """Constant 30 ms RTT, good campus WiFi."""
    return [(t, 30, 100, 1) for t in range(n)]


def make_degrading(n=600):
    """Linear degrade 20 ms -> 300 ms over 10 minutes."""
    rows = []
    rng = random.Random(123)
    for t in range(n):
        rtt = 20 + (300 - 20) * (t / n)
        rtt += rng.gauss(0, 5)
        rtt = max(5, rtt)
        bw = max(5, 100 - (100 - 20) * (t / n))
        rows.append((t, round(rtt, 1), round(bw, 1), 1))
    return rows


def make_intermittent(n=600):
    """Connected for 60s @ 30ms, disconnected for 30s, repeat."""
    rows = []
    period = 90
    for t in range(n):
        in_period = t % period
        if in_period < 60:
            connected = 1
            rtt = 30 + random.Random(t).gauss(0, 3)
            rtt = max(5, rtt)
            bw = 100
        else:
            connected = 0
            rtt = 5000
            bw = 0
        rows.append((t, round(rtt, 1), bw, connected))
    return rows


def make_urban(n=600):
    """Base 50 ms with Gaussian noise (sigma=20), spike to 500 ms every 120 s."""
    rows = []
    rng = random.Random(7)
    for t in range(n):
        if t > 0 and t % 120 == 0:
            rtt = 500 + rng.gauss(0, 50)
        else:
            rtt = 50 + rng.gauss(0, 20)
        rtt = max(5, rtt)
        rows.append((t, round(rtt, 1), 50, 1))
    return rows


def make_realistic(n=600):
    """Compound: 0-180 stable @ 30ms; 180-300 degrade 30->200ms; 300-360 disc;
    360-600 stable @ 50ms.
    """
    rows = []
    rng = random.Random(99)
    for t in range(n):
        if t < 180:
            rtt = 30 + rng.gauss(0, 4)
            connected = 1
            bw = 100
        elif t < 300:
            frac = (t - 180) / 120
            rtt = 30 + (200 - 30) * frac + rng.gauss(0, 10)
            connected = 1
            bw = max(20, 100 - 50 * frac)
        elif t < 360:
            rtt = 5000
            connected = 0
            bw = 0
        else:
            rtt = 50 + rng.gauss(0, 5)
            connected = 1
            bw = 80
        rtt = max(5, rtt)
        rows.append((t, round(rtt, 1), round(bw, 1), connected))
    return rows


def main():
    print("Step 2: network traces")
    # All synthetic traces clamp to connected-good end-states, so 600s is
    # fine even when episodes run past the trace end. (Markov traces are
    # extended to 1500s separately via markov_network.py because the
    # Markov chain can end on a `disconnected` sample.)
    write_trace("stable",       make_stable())
    write_trace("degrading",    make_degrading())
    write_trace("intermittent", make_intermittent())
    write_trace("urban",        make_urban())
    write_trace("realistic",    make_realistic())
    print("Step 2 complete.")


if __name__ == "__main__":
    main()
