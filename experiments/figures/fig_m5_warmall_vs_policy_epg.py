#!/usr/bin/env python3
"""M5: warm-all-lru vs hybrid-F-lhreq-noc3 on EP-G.

Claim: a naive warm-everything baseline (warm-all-lru, which prefills every uploaded
batch and lets the engine evict by LRU) collapses under EP-G load: it serves almost
nothing within its deadline and its service latency grows into the minutes as the
run proceeds. The selective policy (hybrid-F-lhreq-noc3) serves most opportunities on
time and holds a flat sub-second service latency. Warming must be selective, not
indiscriminate.

CPU only. Committed EP-G pilot cells (seeds 4 and 5). Workloads present in these
cells: monitor (dashcam, deadline 1.0 s) and recall (SS, deadline 2.0 s). Numbers are
provisional pending the repeat-trace cells.

Note on warm share: the task also lists warm share, but believed-tier warm share is
not a sound cross-arm metric in these cells (StudyV5-ENGINE records that the residency
belief understates prefix reuse by construction, and the two arms log different event
sets, so warm-all-lru shows 79 percent and hybrid-noc3 shows 0 percent by belief while
hybrid still reuses prefix on the wire). It is therefore not plotted as a headline;
the service metrics below are what the deadline target is defined on.
"""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np
import matplotlib.pyplot as plt

RUNS = "results/orchestration/live2/frozen_test/runs"
SEEDS = ["s4", "s5"]
ARMS = ["warm-all-lru", "hybrid-F-lhreq-noc3"]
FIGID = "M5_warmall_vs_policy_epg"


def outcomes(arm):
    rows = []
    for s in SEEDS:
        p = f"{RUNS}/{arm}_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz"
        fp = F.REPO / p
        if not fp.exists():
            continue
        with gzip.open(fp) as f:
            rows += [json.loads(l) for l in f]
    return rows


def on_time(rows, kind):
    sel = [r for r in rows if r["kind"] == kind]
    n = len(sel)
    h = sum(1 for r in sel if r.get("within_L"))
    p, lo, hi = F.wilson(h, n)
    return dict(p=p, lo=lo, hi=hi, h=h, n=n)


def latency_series(rows, kind, width=120, horizon=1200):
    pts = [(r["t_opportunity"], r["t_delivered"] - r["t_opportunity"]) for r in rows
           if r["kind"] == kind and r.get("t_delivered") is not None
           and r.get("t_opportunity") is not None]
    xs, med = [], []
    for lo in range(0, horizon, width):
        sel = [d for t, d in pts if lo <= t < lo + width]
        if len(sel) >= 10:
            xs.append((lo + width / 2) / 60.0)
            med.append(np.median(sel))
    return xs, med


def main():
    data = {a: outcomes(a) for a in ARMS}

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.6, 4.4))
    for ax in (axA, axB):
        ax.grid(True, color=F.GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # Panel A: on-time service, two workloads, two arms.
    metrics = [("monitor", "dashcam\nwithin 1 s"), ("recall", "SS (recall)\nwithin 2 s")]
    x = np.arange(len(metrics))
    bw = 0.38
    for off, arm in zip([-bw / 2, bw / 2], ARMS):
        A = F.arm(arm)
        vals = [on_time(data[arm], k) for k, _ in metrics]
        axA.bar(x + off, [v["p"] for v in vals], width=bw, color=A.color,
                hatch=A.hatch, edgecolor="white", linewidth=0.9, zorder=3, label=A.label)
        axA.errorbar(x + off, [v["p"] for v in vals],
                     yerr=[[v["p"] - v["lo"] for v in vals], [v["hi"] - v["p"] for v in vals]],
                     fmt="none", ecolor=F.INK, elinewidth=1.1, capsize=3, zorder=4)
        for xi, v in zip(x + off, vals):
            axA.text(xi, v["p"] + 0.02, f"{v['p']*100:.0f}%", ha="center", va="bottom",
                     fontsize=9, color=F.INK)
    axA.set_xticks(x); axA.set_xticklabels([lab for _, lab in metrics])
    axA.set_ylabel("served within deadline")
    axA.set_ylim(0, 1.08)
    axA.set_yticks(np.arange(0, 1.01, 0.25))
    axA.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
    axA.legend(loc="upper center", ncol=1, fontsize=8.8)
    axA.set_title("Warm-all misses almost every deadline", fontsize=10.5, pad=6)

    # Panel B: service latency over run time (dashcam / monitor), log y.
    for arm in ARMS:
        A = F.arm(arm)
        xs, med = latency_series(data[arm], "monitor")
        axB.plot(xs, med, color=A.color, lw=2.2, ls=A.ls, marker=A.marker, ms=5,
                 zorder=4, label=A.label)
    axB.axhline(1.0, color=F.INK, lw=1.1, ls=(0, (6, 4)), zorder=2)
    axB.text(19.8, 1.08, "1 s deadline", ha="right", va="bottom", fontsize=8.5, color=F.INK)
    axB.set_yscale("log")
    axB.set_xlabel("run time (min)")
    axB.set_ylabel("dashcam service latency median (s)")
    axB.set_xlim(0, 20)
    axB.legend(loc="center right", ncol=1, fontsize=8.8)
    axB.set_title("Warm-all's latency grows into the minutes; policy stays flat",
                  fontsize=10.5, pad=6)
    F.save(fig, FIGID, pilot=False)

    wm = {a: on_time(data[a], "monitor") for a in ARMS}
    wr = {a: on_time(data[a], "recall") for a in ARMS}
    _, lm_warm = latency_series(data["warm-all-lru"], "monitor")
    _, lm_pol = latency_series(data["hybrid-F-lhreq-noc3"], "monitor")
    claim = (
        "On EP-G, the warm-everything baseline warm-all-lru serves only "
        f"{wm['warm-all-lru']['p']*100:.0f}% of dashcam opportunities within the 1 s deadline and "
        f"{wr['warm-all-lru']['p']*100:.0f}% of SS recalls within 2 s, and its dashcam service latency "
        f"grows from about {min(lm_warm):.0f} s early in the run to about {max(lm_warm):.0f} s late, "
        "because prefilling every batch saturates the engine. The selective policy "
        f"hybrid-F-lhreq-noc3 serves {wm['hybrid-F-lhreq-noc3']['p']*100:.0f}% of dashcam within 1 s and "
        f"{wr['hybrid-F-lhreq-noc3']['p']*100:.0f}% of SS within 2 s and holds a flat "
        f"{np.median(lm_pol):.1f} s dashcam latency across the run. Warming indiscriminately is worse "
        "than the selective policy, which is the case for a policy rather than a fixed warm-all rule."
    )
    notes = (
        "EP-G pilot cells, seeds 4 and 5, 16 devices, 1200 s, ratio 40:40:20. Workloads present: monitor "
        "(dashcam, deadline 1.0 s) and recall (SS, deadline 2.0 s); served-within-deadline is the committed "
        "per-opportunity within_L. Panel A error bars are Wilson 95 percent. Panel B is the median of "
        "t_delivered minus t_opportunity per 2 min bin, log scale. warm-all-lru is KV-green (the warming "
        "baseline), the policy is query-blue, each also carrying its own linestyle and marker. Warm share is "
        "discussed in the header and not plotted: believed-tier warm share is not a sound cross-arm metric "
        "here (StudyV5-ENGINE: the residency belief understates prefix reuse). Numbers are provisional "
        "pending the repeat-trace cells."
    )
    srcs = [f"{RUNS}/{a}_n16_{s}_1200s_h27_3t_L3_epg/outcomes.jsonl.gz"
            for a in ARMS for s in SEEDS]
    F.write_caption(FIGID, claim, srcs, pilot=False, notes=notes)


if __name__ == "__main__":
    main()
