#!/usr/bin/env python3
"""D190 off-critical-path figures F1 to F5 (CPU only, read-only on all inputs).

Draws from reports/figures/frontier_data.csv (built by build_frontier.py by CALLING the committed
scorers). F4's on-time / late / unsent buckets are the one thing not in the CSV; they are computed
here from the three seed-5 cells' outcomes with the committed delivery functions of the D179 scorer
(D._committed_delivery, D._within), never a reimplemented rule. PDF + PNG, colour-blind-safe,
consistent arm colours. No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figlib_d190 as FL  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = FL.REPO
RUNS = os.path.join(REPO, "results/orchestration/live2/frozen_test/runs")
sys.path.insert(0, os.path.join(REPO, "experiments", "orchestration", "live2"))
import d179_rung2_verdict as D  # noqa: E402

FL.rcparams()
SEEDS = [4, 5, 6, 7]

# ladder for F2 and the F4 mechanism trio, resolved to raw arms
RUNG = [("base", "base"), ("rules", "rules"), ("state", "state-uo"),
        ("state-c5attr", "state-uo-c5attr"), ("fair", "fair-c5attr")]
MECH = [("engine flag\n(state-uo)", "state-uo"), ("+C5 attr\n(state-uo-c5attr)", "state-uo-c5attr"),
        ("shares\n(state-shares)", "shares")]


def _jsonl(path_noext):
    for cand, op in ((path_noext + ".gz", gzip.open), (path_noext, open)):
        if os.path.exists(cand):
            with op(cand, "rt") as fh:
                return [json.loads(l) for l in fh if l.strip()]
    return []


# ----------------------------------------------------------------------------- F1 frontier
def f1(rows):
    fam = FL.by_family(rows)
    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    ax.axhline(0.25, color=FL.C["black"], lw=1.1, ls=(0, (6, 4)), zorder=1)
    ax.text(0.012, 0.262, "alert target 0.25 per episode", fontsize=7.8, color=FL.C["black"])

    bi = 0
    legend_done = set()
    for f in sorted(fam, key=lambda f: FL.style(f).get("order", 999)):
        is_base = f in FL.BASELINES
        st = FL.style(f, bi)
        if is_base:
            bi += 1
        xs = [r["robot_on_time_frac"] for r in fam[f] if r["robot_on_time_frac"] is not None]
        ys = [r["alert_mean_per_episode_attain"] for r in fam[f]
              if r["alert_mean_per_episode_attain"] is not None]
        if not xs or not ys:
            continue
        # per-seed faint points
        ax.scatter(xs, ys, s=22, color=st["color"], marker=st["marker"], alpha=0.33,
                   edgecolors="none", zorder=2)
        mx, my = FL.mean(xs), FL.mean(ys)
        # per-arm mean, emphasised
        if is_base:
            lab = "baselines" if "baselines" not in legend_done else None
            legend_done.add("baselines")
            ax.scatter([mx], [my], s=46, color=st["color"], marker=st["marker"],
                       edgecolors="white", linewidths=0.6, alpha=0.85, zorder=3, label=lab)
        else:
            lab = st["label"]
            if st["cls"] == "c5":
                lab = lab + "  (rule-based C5 fix family)"
            ax.scatter([mx], [my], s=108, color=st["color"], marker=st["marker"],
                       edgecolors="white", linewidths=1.0, zorder=5, label=lab)

    # mark the base explicitly
    if "base" in fam:
        bx = FL.mean([r["robot_on_time_frac"] for r in fam["base"]])
        by = FL.mean([r["alert_mean_per_episode_attain"] for r in fam["base"]])
        ax.annotate("base", (bx, by), textcoords="offset points", xytext=(8, 8),
                    fontsize=8.4, color=FL.C["blue"], fontweight="bold")

    # honesty annotation: the stream-all baselines look dominant on these two TIMING axes but
    # deliver low-accuracy answers (robot correct-by-deadline 0.14 to 0.29; see F3). On-time is a
    # delivery-timing rate, not a correctness rate.
    stream = [r for f in ("simplestream", "streamscout") for r in fam.get(f, [])]
    if stream:
        sx = FL.mean([r["robot_on_time_frac"] for r in stream])
        sy = FL.mean([r["alert_mean_per_episode_attain"] for r in stream])
        ax.annotate("stream-all baselines:\non-time but low answer\naccuracy (see F3)",
                    (sx, sy), textcoords="offset points", xytext=(-150, -6), fontsize=7.6,
                    color=FL.C["vermilion"],
                    arrowprops=dict(arrowstyle="->", color=FL.C["vermilion"], lw=1.0))

    ax.set_xlabel("robot on-time fraction (cloud answers DELIVERED within 3 s, pooled; timing only)")
    ax.set_ylabel("mean per-episode alert attainment (D186 primary)")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, max(0.75, max(r["alert_mean_per_episode_attain"] for r in rows
                                 if r["alert_mean_per_episode_attain"] is not None) + 0.05))
    ax.set_title("F1  Off-critical-path frontier: robot on-time vs alert attainment\n"
                 "(small = per seed, large = per-arm mean; seeds 4 to 7, full memory)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), ncol=1, framealpha=0.95,
              handletextpad=0.3, borderpad=0.4, labelspacing=0.3)
    fig.tight_layout()
    return FL.save(fig, "F1_frontier")


# ----------------------------------------------------------------------------- F2 ablation ladder
def f2(rows):
    fam = FL.by_family(rows)
    base_alert = {int(r["seed"]): r["alert_mean_per_episode_attain"] for r in fam.get("base", [])}
    fig, axes = plt.subplots(1, 3, figsize=(11.6, 4.3))
    panels = [
        ("alert attainment\n(mean per episode)", "alert_mean_per_episode_attain", None),
        ("robot retention of\nrung-2 gain over base", "retention_rung2_gain_over_base", 0.90),
        ("assistance within 2 s\n(worst device)", "assist_perdev_min", 0.90),
    ]
    xpos = np.arange(len(RUNG))
    for ax, (title, col, bar) in zip(axes, panels):
        for xi, (lab, famname) in zip(xpos, RUNG):
            pts = [(int(r["seed"]), r[col]) for r in fam.get(famname, []) if r[col] is not None]
            st = FL.style(famname)
            ys = [v for _, v in pts]
            if ys:
                ax.scatter([xi] * len(ys), ys, s=30, color=st["color"], marker=st["marker"],
                           alpha=0.5, edgecolors="none", zorder=3)
                ax.scatter([xi], [FL.mean(ys)], s=96, color=st["color"], marker=st["marker"],
                           edgecolors="white", linewidths=0.9, zorder=5)
        if bar is not None:
            ax.axhline(bar, color=FL.C["black"], lw=1.0, ls=(0, (5, 4)), zorder=1)
            ax.text(len(RUNG) - 0.5, bar + 0.01, f"check bar {bar:g}", ha="right",
                    fontsize=7.4, color=FL.C["black"])
        if col == "alert_mean_per_episode_attain" and base_alert:
            bm = FL.mean(list(base_alert.values()))
            ax.axhline(bm, color=FL.C["blue"], lw=1.0, ls=":", zorder=1)
            ax.text(0.0, bm + 0.01, "base level (check 1)", fontsize=7.2, color=FL.C["blue"])
        ax.set_xticks(xpos)
        ax.set_xticklabels([lab for lab, _ in RUNG], rotation=20, ha="right", fontsize=7.8)
        ax.set_title(title, fontsize=9.6)
    axes[0].set_ylabel("value (points = seeds 4 to 7, large = mean)")
    fig.suptitle("F2  Ablation ladder: the three D179 pre-registered checks per rung, per seed",
                 fontsize=11, y=1.01)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    return FL.save(fig, "F2_ablation_ladder")


# ----------------------------------------------------------------------------- F3 baselines
def f3(rows):
    fam = FL.by_family(rows)
    main = "fair-c5attr"
    ref = ["base", "state-uo"]
    base_list = [b for b in FL.BASELINES if b in fam]
    order = [main] + ref + base_list
    panels = [
        ("robot correct by deadline\n(accuracy; floor dashed)", "robot_by_deadline_acc", True),
        ("assistance within 2 s\n(pooled)", "assist_within2s_pooled", False),
        ("alert attainment\n(mean per episode)", "alert_mean_per_episode_attain", False),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 4.8))
    xpos = np.arange(len(order))
    bi = 0
    colors = {}
    for f in order:
        if f == main:
            colors[f] = FL.C["vermilion"]
        elif f in ("base", "state-uo"):
            colors[f] = FL.style(f)["color"]
        else:
            colors[f] = FL.C["grey"]
    for ax, (title, col, floor) in zip(axes, panels):
        for xi, f in zip(xpos, order):
            ys = [r[col] for r in fam.get(f, []) if r[col] is not None]
            if not ys:
                continue
            ax.bar(xi, FL.mean(ys), width=0.7, color=colors[f],
                   edgecolor="white", linewidth=0.7,
                   zorder=2, alpha=(0.95 if f in (main, "base", "state-uo") else 0.6))
            ax.scatter([xi] * len(ys), ys, s=16, color=FL.C["black"], alpha=0.55, zorder=4)
            if floor:
                fl = [r["device_only_robot_floor"] for r in fam.get(f, [])
                      if r["device_only_robot_floor"] is not None]
                if fl:
                    ax.plot([xi - 0.35, xi + 0.35], [FL.mean(fl)] * 2, color=FL.C["black"],
                            lw=1.1, ls=(0, (3, 2)), zorder=5)
        if col == "assist_within2s_pooled":
            ax.axhline(0.90, color=FL.C["black"], lw=1.0, ls=(0, (5, 4)))
            ax.text(len(order) - 0.5, 0.91, "0.90", ha="right", fontsize=7.4)
        if col == "alert_mean_per_episode_attain":
            ax.axhline(0.25, color=FL.C["black"], lw=1.0, ls=(0, (5, 4)))
            ax.text(len(order) - 0.5, 0.26, "target 0.25", ha="right", fontsize=7.4)
        ax.set_xticks(xpos)
        ax.set_xticklabels(order, rotation=55, ha="right", fontsize=6.9)
        ax.set_title(title, fontsize=9.4)
        ax.set_ylim(0, 1.0)
    axes[0].set_ylabel("value (bar = mean over seeds, dots = seeds)")
    fig.suptitle("F3  Our main arm (fair +C5) vs baselines at the main operating point, per seed",
                 fontsize=11, y=1.02)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return FL.save(fig, "F3_baseline_comparison")


# ----------------------------------------------------------------------------- F4 mechanism (s5)
def _alert_buckets(cell_dir):
    """on-time / late / unsent fractions of OFFERED alert instants, committed delivery rule."""
    outs = _jsonl(os.path.join(cell_dir, "outcomes.jsonl"))
    reqs = _jsonl(os.path.join(cell_dir, "request.jsonl"))
    if not reqs:
        reqs = _jsonl(os.path.join(cell_dir, "requests.jsonl"))
    if not outs:
        return None
    delivered = D._committed_delivery(outs, reqs)
    on = late = unsent = 0
    for o in delivered.values():
        if D._type_of(o.get("device_id")) != "alert":
            continue
        td = o.get("t_delivered")
        if td is None:
            unsent += 1
        elif D._within(o, D.DEADLINE_S["alert"]):
            on += 1
        else:
            late += 1
    n = on + late + unsent
    return None if not n else dict(on=on / n, late=late / n, unsent=unsent / n, n=n)


def f4():
    cells = {lab: os.path.join(RUNS, raw if raw in FL.ARMS else raw)
             for lab, raw in MECH}
    # resolve raw arm -> actual cell dir name at seed 5
    name_of = {"state-uo": "covex-v6-state-uo", "state-uo-c5attr": "covex-v6-state-uo-c5attr",
               "shares": "covex-v6-state-shares"}
    fig, (axb, axh) = plt.subplots(1, 2, figsize=(10.4, 4.6),
                                   gridspec_kw={"width_ratios": [1.25, 1.0]})
    labels = [lab for lab, _ in MECH]
    xpos = np.arange(len(MECH))
    bcols = {"on": FL.C["green"], "late": FL.C["orange"], "unsent": FL.C["vermilion"]}
    notes = []
    holds = {"p50": [], "p90": []}
    for xi, (lab, raw) in zip(xpos, MECH):
        cdir = os.path.join(RUNS, f"{name_of[raw]}_n16_s5_1200s_h27_3t_L3_epg_rq30")
        b = _alert_buckets(cdir)
        if b is None:
            notes.append(f"{raw}: no outcomes at s5")
            holds["p50"].append(None)
            holds["p90"].append(None)
            continue
        bottom = 0.0
        for key in ("on", "late", "unsent"):
            axb.bar(xi, b[key], bottom=bottom, width=0.62, color=bcols[key],
                    edgecolor="white", linewidth=0.7, zorder=3,
                    label=(key if xi == 0 else None))
            if b[key] > 0.04:
                axb.text(xi, bottom + b[key] / 2, f"{b[key]*100:.0f}%", ha="center",
                         va="center", fontsize=7.6, color="white", fontweight="bold")
            bottom += b[key]
        ht = D.read_cell(cdir)["hold_times"]["per_type"].get("alert", {})
        holds["p50"].append(ht.get("hold_s_p50"))
        holds["p90"].append(ht.get("hold_s_p90"))
    axb.set_xticks(xpos)
    axb.set_xticklabels(labels, fontsize=8.0)
    axb.set_ylabel("fraction of offered alert instants")
    axb.set_ylim(0, 1.0)
    axb.set_title("alert delivery buckets (seed 5)", fontsize=9.8)
    axb.legend(loc="lower right", fontsize=7.8, title="alert", title_fontsize=7.8)

    w = 0.34
    p50 = [h if h is not None else 0 for h in holds["p50"]]
    p90 = [h if h is not None else 0 for h in holds["p90"]]
    axh.bar(xpos - w / 2, p50, width=w, color=FL.C["blue"], edgecolor="white",
            linewidth=0.7, label="hold p50", zorder=3)
    axh.bar(xpos + w / 2, p90, width=w, color=FL.C["sky"], edgecolor="white",
            linewidth=0.7, label="hold p90", zorder=3)
    for xi, (a, b) in enumerate(zip(holds["p50"], holds["p90"])):
        if a is None and b is None:
            axh.text(xi, 0.0, "no share\nhold rows", ha="center", va="bottom",
                     fontsize=7.2, color=FL.C["grey"])
    axh.set_xticks(xpos)
    axh.set_xticklabels(labels, fontsize=8.0)
    axh.set_ylabel("alert hold time (s)")
    axh.set_title("share hold time, alert (seed 5)", fontsize=9.8)
    axh.legend(loc="upper left", fontsize=7.8)

    fig.suptitle("F4  Mechanism at seed 5: engine flag vs +C5 attr vs shares", fontsize=11, y=1.02)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    if notes:
        fig.text(0.5, -0.02, "; ".join(notes), ha="center", fontsize=7.0, color=FL.C["vermilion"])
    return FL.save(fig, "F4_mechanism_s5")


# ----------------------------------------------------------------------------- F5 memory sweep
def f5():
    r1 = {(_r["arm_family"], int(_r["seed"])): _r for _r in FL.load(memory="1x")}
    rh = {(_r["arm_family"], int(_r["seed"])): _r for _r in FL.load(memory="0.5x")}
    fams = sorted({k[0] for k in r1} & {k[0] for k in rh},
                  key=lambda f: FL.style(f).get("order", 999))
    panels = [("robot on-time fraction", "robot_on_time_frac"),
              ("mean per-episode alert attainment", "alert_mean_per_episode_attain")]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.8))
    msweep = [4, 5]
    bi = 0
    for ax, (title, col) in zip(axes, panels):
        bi = 0
        for f in fams:
            st = FL.style(f, bi)
            if f in FL.BASELINES:
                bi += 1
            v1 = FL.mean([r1[(f, s)][col] for s in msweep
                          if (f, s) in r1 and r1[(f, s)][col] is not None])
            v2 = FL.mean([rh[(f, s)][col] for s in msweep
                          if (f, s) in rh and rh[(f, s)][col] is not None])
            if v1 is None or v2 is None:
                continue
            # the 0.5x points are a halved SELF-IMPOSED coordinator budget, not a halved engine KV
            # pool, so the 1x->0.5x segment is drawn dotted and greyed to mark it logical-only.
            ax.plot([1.0, 0.5], [v1, v2], color=st["color"], marker=st["marker"], ls=":",
                    lw=1.3, ms=7, alpha=0.75,
                    label=(st["label"] if col == "robot_on_time_frac" else None), zorder=3)
        ax.axvspan(0.38, 0.74, color=FL.C["grey"], alpha=0.10, zorder=0)
        ax.set_xticks([0.5, 1.0])
        ax.set_xticklabels(["0.5x\n(logical-only)", "1x"])
        ax.set_xlim(0.38, 1.12)
        ax.invert_xaxis()
        ax.set_xlabel("KV budget (fraction of deployed)")
        ax.set_title(title, fontsize=9.8)
        ax.text(0.56, ax.get_ylim()[1], "logical budget,\nnot engine pool", fontsize=6.6,
                color=FL.C["grey"], va="top", ha="center")
    axes[0].set_ylabel("value (mean over seeds 4 and 5)")
    axes[0].legend(loc="best", fontsize=6.8, ncol=2)
    fig.suptitle("F5  Budget sweep: full memory (1x) vs halved SELF-IMPOSED KV budget (0.5x, "
                 "LOGICAL-ONLY)\n0.5x does NOT test engine memory pressure (D189: same server argv, "
                 "engine pool 62944 both; evidence d189_kv05_logical_only.json). Real-engine 0.25x "
                 "cells are pending.", fontsize=8.8, y=1.03)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return FL.save(fig, "F5_memory_sweep")


def main():
    rows1 = FL.load(memory="1x")
    made = []
    made.append(f1(rows1))
    made.append(f2(rows1))
    made.append(f3(rows1))
    made.append(f4())
    made.append(f5())
    for png, pdf in made:
        print("wrote", os.path.relpath(png, REPO), "+", os.path.basename(pdf))


if __name__ == "__main__":
    main()
