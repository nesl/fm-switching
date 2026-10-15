#!/usr/bin/env python3
"""Study O — pre-run checks (plan §8) plus the D4 evidence_covered redefinition.

D4: evidence_covered must be computed from ACTUAL SAMPLED FRAME TIMESTAMPS per
arm — "does any sampled frame fall within [answer_start_time, answer_end_time]"
— not from whether the arm's window spans [0, qt]. Spanning is not covering.
"""

import json
import math
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np

GROUNDING = Path("results/sember/study_h/data/sember_grounding.jsonl")
VIDEO_DIR = Path("results/sember/study_i/videos")
SEED = 42
RECENT_W = 120.0
UNIFORM_N = 16
RICH_N = 256


def distance_bin(farthest):
    if farthest <= 60:
        return "<=60s"
    if farthest <= 120:
        return "60-120s"
    return ">120s"


def sampled_timestamps(arm, qt):
    """Actual frame timestamps each arm would sample."""
    if arm == "RECENT":
        start = max(0.0, qt - RECENT_W)
        n = int(math.floor(qt - start)) + 1
        return np.linspace(start, qt, n) if n > 1 else np.array([qt])
    if arm == "UNIFORM":
        return np.linspace(0.0, qt, UNIFORM_N)
    if arm == "RICH":
        return np.linspace(0.0, qt, RICH_N)
    raise ValueError(arm)


def covered(arm, rec):
    """D4: does ANY sampled frame timestamp fall inside the evidence window?"""
    ts = sampled_timestamps(arm, float(rec["question_time"]))
    a, b = float(rec["answer_start_time"]), float(rec["answer_end_time"])
    if b < a:
        a, b = b, a
    return bool(np.any((ts >= a) & (ts <= b)))


def old_covered(arm, rec):
    """The DEFECTIVE D4 definition, for contrast."""
    if arm in ("RICH", "UNIFORM"):
        return True
    return float(rec["farthest"]) <= RECENT_W


def main():
    recs = [json.loads(l) for l in open(GROUNDING)]
    recs = [r for r in recs if r.get("answer_start_time") is not None]
    for r in recs:
        qt = float(r["question_time"])
        r["farthest"] = qt - min(float(r["answer_start_time"]),
                                 float(r["answer_end_time"]))
        r["evid_range"] = abs(float(r["answer_end_time"]) -
                              float(r["answer_start_time"]))
    recs = [r for r in recs if r["farthest"] >= 0]
    print(f"grounding records usable: {len(recs)}")

    have = {p.stem for p in VIDEO_DIR.glob("*.mp4")}
    local = [r for r in recs if r["video_id"] in have]
    print(f"videos present locally: {len(have)} of "
          f"{len({r['video_id'] for r in recs})} referenced")
    print(f"questions on locally-present videos: {len(local)}")
    print()

    print("=" * 72)
    print("D4 — evidence_covered from ACTUAL SAMPLED TIMESTAMPS")
    print("=" * 72)
    print(f"{'arm':<9} {'OLD (defective)':>16} {'NEW (sampled)':>15} {'delta':>9}")
    for arm in ("RECENT", "UNIFORM", "RICH"):
        old = np.mean([old_covered(arm, r) for r in local]) * 100
        new = np.mean([covered(arm, r) for r in local]) * 100
        print(f"{arm:<9} {old:>15.1f}% {new:>14.1f}% {new-old:>+8.1f}pp")
    print()
    gaps = [float(r["question_time"]) / (UNIFORM_N - 1) for r in local]
    er = [r["evid_range"] for r in local]
    print(f"UNIFORM inter-frame gap: median {np.median(gaps):.1f}s  "
          f"max {max(gaps):.1f}s")
    print(f"evidence window width:   median {np.median(er):.1f}s  "
          f"p25 {np.percentile(er,25):.1f}s  frac < UNIFORM gap: "
          f"{np.mean([e < g for e, g in zip(er, gaps)])*100:.1f}%")
    print("  (an evidence window narrower than the sampling gap can fall "
          "entirely between UNIFORM samples)")
    print()

    print("=" * 72)
    print("§8.1 Q4 POWER")
    print("=" * 72)
    p_far = np.mean([r["farthest"] > 120 for r in local]) * 100
    print(f"fraction with farthest > 120s: {p_far:.1f}%  (H2 expectation ~29.7%)")
    print()

    print("=" * 72)
    print("§8.2 Q1 CELL BALANCE  (need >= 20 questions per category x "
          "distance_bin)")
    print("=" * 72)
    cells = Counter((r["question_category"], distance_bin(r["farthest"]))
                    for r in local)
    cats = sorted({c for c, _ in cells})
    bins_ = ["<=60s", "60-120s", ">120s"]
    print(f"{'category':<32} " + " ".join(f"{b:>9}" for b in bins_))
    nfail = 0
    for c in cats:
        row = [cells.get((c, b), 0) for b in bins_]
        nfail += sum(1 for v in row if v < 20)
        print(f"{c:<32} " + " ".join(
            f"{v:>9}" if v >= 20 else f"{str(v)+'!':>9}" for v in row))
    total_cells = len(cats) * len(bins_)
    print(f"\ncells below 20: {nfail}/{total_cells}")
    need = total_cells * 20
    print(f"questions needed for full balance: ~{need} "
          f"(available locally: {len(local)})")
    print(f"CHECK: {'PASS' if nfail == 0 else 'FAIL'}")


if __name__ == "__main__":
    main()
