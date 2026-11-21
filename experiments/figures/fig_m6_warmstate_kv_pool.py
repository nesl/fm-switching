#!/usr/bin/env python3
"""M6: KV pool vs history sizes, warm-state simulator at 1x, 0.5x, 0.25x.

Claim: warming the right histories buys on-time service that a no-warming policy
cannot (no warming holds about 78 percent on time at every pool size because it never
uses the pool), and as the KV pool shrinks a pool-aware warming policy holds full
warm coverage and 100 percent on time by spilling to the host tier, while a naive
GPU-only warming policy loses coverage and on-time service. The value of warm state
is real and depends on managing the pool, not just on turning warming on.

CPU only. Committed data only: the offline warm-state study warm_state_offline.json
(what a warming policy could have bought; an offline sim, not a live run).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np
import matplotlib.pyplot as plt

SRC = "results/orchestration/live2/frozen_test/warm_state_offline.json"
FIGID = "M6_warmstate_kv_pool"
SCALES = [1.0, 0.5, 0.25]
# policy key -> (label, color, linestyle, marker)
POLICIES = [
    ("P0", "no warming", F.GREY, ":", "x"),
    ("P1", "warm, GPU + LRU", F.RISK, "--", "s"),
    ("P2 T=120", "warm, TTL 120 s", F.GREEN, "-.", "^"),
    ("P3", "warm, pool-aware (GPU + host)", F.BLUE, "-", "o"),
]


def main():
    d = F.load_json(SRC)
    cells = [c for c in d["cells"] if c["n_devices"] == 16]
    idx = {(c["policy"], c["capacity_scale"]): c for c in cells}

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.6, 4.4))
    for ax in (axA, axB):
        ax.grid(True, color=F.GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    xpos = np.arange(len(SCALES))
    for key, lab, col, ls, mk in POLICIES:
        cov = [idx[(key, s)]["covered_fraction_p50"] for s in SCALES]
        ont = [idx[(key, s)]["on_time_with_queue_frac"] for s in SCALES]
        axA.plot(xpos, cov, color=col, ls=ls, marker=mk, ms=6, lw=2.0, zorder=4, label=lab)
        axB.plot(xpos, ont, color=col, ls=ls, marker=mk, ms=6, lw=2.0, zorder=4, label=lab)

    for ax, ylab, title in [
            (axA, "warm coverage (median fraction)", "Pool-aware warming keeps coverage as the pool shrinks"),
            (axB, "served within deadline", "and keeps service on time")]:
        ax.set_xticks(xpos)
        ax.set_xticklabels([f"{s:g}x" for s in SCALES])
        ax.set_xlabel("KV pool size (fraction of deployed)")
        ax.set_ylabel(ylab)
        ax.set_ylim(-0.03, 1.08)
        ax.set_yticks(np.arange(0, 1.01, 0.25))
        ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
        ax.set_title(title, fontsize=10.3, pad=6)
    axA.legend(loc="lower left", ncol=1, fontsize=8.4)

    F.save(fig, FIGID, pilot=False)

    p0 = idx[("P0", 1.0)]
    p3_25 = idx[("P3", 0.25)]
    p1_25 = idx[("P1", 0.25)]
    claim = (
        "In the offline warm-state sim, a no-warming policy holds "
        f"{p0['on_time_with_queue_frac']*100:.0f}% on time at every pool size because it never uses the "
        "pool, while warming the right histories reaches 100 percent on time at the deployed pool. As the "
        "KV pool shrinks to one quarter, a pool-aware warming policy that spills to the host tier (P3) holds "
        f"full warm coverage ({p3_25['covered_fraction_p50']:.2f}) and {p3_25['on_time_with_queue_frac']*100:.0f}% "
        "on time, while a naive GPU-only warming policy (P1) loses coverage "
        f"({p1_25['covered_fraction_p50']:.2f}) and falls to {p1_25['on_time_with_queue_frac']*100:.0f}% on time. "
        "The value of warm state depends on managing the pool, not just on turning warming on."
    )
    notes = (
        "Offline warm-state study (warm_state_offline.json, user 2026-11-20): what a warming policy could "
        "have bought, an offline simulation over 65 questions at 16 devices, eval seeds 4, 5, 6, deployed pool "
        f"gpu {d['capacities']['gpu_tokens']:,} and host {d['capacities']['host_tokens']:,} tokens, scales "
        "1.0, 0.5, 0.25. Warm coverage is the median covered fraction; on-time is on_time_with_queue_frac at "
        "the committed 0.74 s queue allowance. Policies: P0 no warming (all cold), P1 GPU warming with LRU "
        "eviction, P2 time-to-live warming, P3 pool-aware warming that spills to the host KV tier. Each policy "
        "carries its own colour, linestyle and marker. This is an offline sim, not a live EP-G run, and is "
        "labelled as such; it bounds what warming could buy."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=False, notes=notes)


if __name__ == "__main__":
    main()
