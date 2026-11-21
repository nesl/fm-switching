#!/usr/bin/env python3
"""E5 (PILOT): memory sweep.

Claim: under a shrinking KV pool, first-token latency stays low for a pool-aware warming
policy that spills to the host tier (P3) and for the no-warming base (which never queues
a prefill), while a naive GPU-only warming policy (P1) degrades as its coverage collapses.
Memory pressure is a policy problem, not just a capacity number.

CPU only. Committed offline warm-state study warm_state_offline.json (the memory-sweep axis,
scales 1.0, 0.5, 0.25). The live EP-G pilot has only a single 0.25x KV cell (warm-all-lru,
labelled kv0.25 and race-fixed), not a policy memory sweep, so the live sweep is deferred to
the repeat-trace cells and the committed offline sim carries the axis here. This figure is the
latency cut of the same sweep whose coverage and on-time are the motivation figure M6.
WATERMARKED PILOT.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

SRC = "results/orchestration/live2/frozen_test/warm_state_offline.json"
FIGID = "E5_memory_sweep"
SCALES = [1.0, 0.5, 0.25]
POLICIES = [
    ("P0", "no warming", F.GREY, ":", "x"),
    ("P1", "warm, GPU + LRU", F.RISK, "--", "s"),
    ("P2 T=120", "warm, TTL 120 s", F.GREEN, "-.", "^"),
    ("P3", "warm, pool-aware (GPU + host)", F.BLUE, "-", "o"),
]


def main():
    d = F.load_json(SRC)
    idx = {(c["policy"], c["capacity_scale"]): c for c in d["cells"] if c["n_devices"] == 16}

    fig, ax = F.new_fig(7.2, 4.6)
    xpos = np.arange(len(SCALES))
    for key, lab, col, ls, mk in POLICIES:
        ttft = [idx[(key, s)]["ttft_p50"] for s in SCALES]
        ax.plot(xpos, ttft, color=col, ls=ls, marker=mk, ms=6, lw=2.0, zorder=4, label=lab)

    ax.axhline(3.0, color=F.INK, lw=1.2, ls=(0, (6, 4)), zorder=3)
    ax.text(0.02, 3.1, "3 s first-token budget", fontsize=8.6, color=F.INK)
    ax.set_xticks(xpos)
    ax.set_xticklabels([f"{s:g}x" for s in SCALES])
    ax.set_xlabel("KV pool size (fraction of deployed)")
    ax.set_ylabel("first-token latency p50 (s)")
    ax.set_ylim(0, 3.4)
    ax.legend(loc="upper center", fontsize=8.4)
    ax.set_title("Memory sweep: pool-aware warming holds latency as the pool shrinks",
                 fontsize=10.4, pad=8)
    F.save(fig, FIGID, pilot=True)

    p3 = [idx[("P3", s)]["ttft_p50"] for s in SCALES]
    p1 = [idx[("P1", s)]["ttft_p50"] for s in SCALES]
    claim = (
        "Under a shrinking KV pool, the pool-aware warming policy P3 holds first-token latency at about "
        f"{p3[-1]:.2f} s even at one-quarter pool, while the naive GPU-only warming policy P1 rises from "
        f"{p1[0]:.2f} s to {p1[-1]:.2f} s as its coverage collapses. The no-warming base is flat but high "
        "because it never warms. Memory pressure is handled by the policy, not by the pool size alone."
    )
    notes = (
        "Committed offline warm-state study warm_state_offline.json (the same sim as motivation figure M6; this "
        "is its first-token-latency cut, M6 shows coverage and on-time). ttft_p50 vs capacity scale, 16 devices, "
        "eval seeds 4, 5, 6. The live EP-G pilot has only one 0.25x KV cell (warm-all-lru, labelled kv0.25 and "
        "race-fixed), which is a single labelled point on a collapsing baseline, not a policy memory sweep, so "
        "the live sweep is deferred to the repeat-trace cells and is not plotted. Policy colours, linestyles and "
        "markers from the shared registry. PILOT."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
