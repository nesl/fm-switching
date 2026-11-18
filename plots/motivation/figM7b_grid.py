"""M7b Load x host-memory grid.

The best way to serve a robot's cold-history question changes with fleet load and host
memory, so no fixed rule works. Each small multiple is the same trade-off scatter as
figM7 (x = the robot's own answer time from the question, y = extra missed dashcam
deadlines vs the no-question control; median with min-to-max whiskers over 5 reps), on
shared axes so the cells are comparable. Rows: light load (8 dashcams, 4 req/s) on top,
heavy load (20 dashcams, 10 req/s) on the bottom. Columns: tight 27 GiB host on the left,
roomy 256 GiB host on the right. The shaded band and the 5 s dashed line mark the good
region (robot on time, fleet unharmed); an action that lands there (0 extra misses and
robot median under 5 s) gets a bold ring. A one-line verdict is computed from the data
in each panel.

Source (read only, never recomputed): results/motivation/mot1/mot1_figdata_amend3.json,
block "grid_2x2". A host-warm point whose measured tier was not HOST is drawn hollow and
labelled flushed (the history had been evicted, so it answers cold). The light/roomy cold
actions are borrowed from light/tight (host size does not change cold actions, StudyENG1c
Part E; amendment 2 vs 1 agree within 1.01 to 1.17x) and drawn at half alpha; light/roomy
host-warm was not measured, so no point is drawn there.
"""
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
import figstyle as F

F.apply_style()
G = json.load(open(F.ROOT / "results/motivation/mot1/mot1_figdata_amend3.json"))["grid_2x2"]

ACT = [("ONE-GO", "one go", F.C_ONEGO, F.MARK["onego"]),
       ("P2048", "2,048 pieces", F.C_PIECE2048, F.MARK["piece2048"]),
       ("P1024", "1,024 pieces", F.C_PIECE1024, F.MARK["piece1024"]),
       ("HOST-WARM", "host-warm", F.C_HOSTWARM, F.MARK["hostwarm"])]

CELLS = {
    "light_tight": dict(title="light load, tight host memory", sub="8 dashcams, 4 requests/s (26% of peak)",
                        verdict="pieces serve both"),
    "light_roomy": dict(title="light load, roomy host memory", sub="8 dashcams, 4 requests/s (26% of peak)",
                        verdict="pieces serve both"),
    "heavy_tight": dict(title="heavy load, tight host memory", sub="20 dashcams, 10 requests/s (66% of peak)",
                        verdict="nothing serves both"),
    "heavy_roomy": dict(title="heavy load, roomy host memory", sub="20 dashcams, 10 requests/s (66% of peak)",
                        verdict="only a warm history serves both"),
}
XLO, XHI, YLO, YHI = 0.0, 8.5, 0.0, 80.0
TARGET = 5.0        # robot deadline, D71
EXPECT = {k: v["verdict"] for k, v in CELLS.items()}


def is_hollow(act, a):
    """HOST-WARM whose measured tier was not HOST in every repetition is flushed (cold)."""
    if act != "HOST-WARM":
        return False
    tiers = a.get("measured_tiers")
    return not (tiers and all(t == "HOST" for t in tiers))


def computed_verdict(cell):
    good = []
    for act, _, _, _ in ACT:
        a = G[cell][act]
        if a.get("status") == "not measured":
            continue
        if a["extra_missed"]["median"] == 0 and a["robot_ttft_s"]["median"] < TARGET:
            good.append(act)
    gs = set(good)
    if not gs:
        v = "nothing serves both"
    elif gs <= {"P2048", "P1024"}:
        v = "pieces serve both"
    elif gs == {"HOST-WARM"}:
        v = "only a warm history serves both"
    else:
        v = "MIXED:" + ",".join(good)
    return v, good


# STOP if any computed verdict disagrees with the required strings.
for cell in CELLS:
    v, _ = computed_verdict(cell)
    if v != EXPECT[cell]:
        raise SystemExit(f"STOP: verdict for {cell} computed '{v}' but expected '{EXPECT[cell]}'")


def draw_panel(ax, cell, show_region_text=False):
    plotted = []
    # good region: robot on time (x < 5) and fleet unharmed (thin band at y = 0..3)
    ax.add_patch(Rectangle((XLO, 0), TARGET - XLO, 3.0, facecolor=F.OI["grey"], alpha=0.16,
                           edgecolor="none", zorder=0))
    ax.axvline(TARGET, color="black", lw=0.9, ls="--", zorder=1)
    for act, lab, c, mk in ACT:
        a = G[cell][act]
        if a.get("status") == "not measured":
            continue
        x = a["robot_ttft_s"]["median"]
        y = a["extra_missed"]["median"]
        xlo, xhi = a["robot_ttft_s"]["min"], a["robot_ttft_s"]["max"]
        ylo, yhi = a["extra_missed"]["min"], a["extra_missed"]["max"]
        borrowed = a.get("measured_directly") is False
        alpha = 0.5 if borrowed else 1.0
        hollow = is_hollow(act, a)
        mfc = "none" if hollow else c
        ax.errorbar(x, y, xerr=[[x - xlo], [xhi - x]], yerr=[[y - ylo], [yhi - y]],
                    fmt=mk, color=c, mfc=mfc, mec=c, ecolor=c,
                    elinewidth=0.8, capsize=2, markersize=6,
                    markeredgewidth=1.0 if hollow else 0.5, alpha=alpha, zorder=3)
        # bold ring for an action in the good region
        if y == 0 and x < TARGET:
            ax.scatter([x], [y], s=150, facecolors="none", edgecolors="black",
                       linewidths=1.2, zorder=5, alpha=alpha)
        # label a flushed host-warm point directly, to its left (hollow => answered cold)
        if hollow:
            ax.text(x - 0.35, y, "flushed", ha="right", va="center", fontsize=5.4,
                    color=c, zorder=4)
        plotted.append((act, round(x, 4), y, hollow, borrowed))
    # verdict, top right
    ax.text(0.96, 0.95, CELLS[cell]["verdict"], transform=ax.transAxes, ha="right", va="top",
            fontsize=6.6, fontweight="bold", zorder=6)
    # borrowed / not-measured notes
    notes = []
    if any(G[cell][act].get("measured_directly") is False for act, _, _, _ in ACT
           if G[cell][act].get("status") != "not measured"):
        notes.append("cold actions borrowed")
    if G[cell]["HOST-WARM"].get("status") == "not measured":
        notes.append("host-warm: not measured")
    for i, nt in enumerate(notes):
        ax.text(0.96, 0.80 - 0.09 * i, nt, transform=ax.transAxes, ha="right", va="top",
                fontsize=5.4, color="#666666", style="italic", zorder=6)
    # title (main, then smaller sub line above the axes)
    ax.text(0.5, 1.13, CELLS[cell]["title"], transform=ax.transAxes, ha="center", va="bottom",
            fontsize=8, fontweight="bold")
    ax.text(0.5, 1.02, CELLS[cell]["sub"], transform=ax.transAxes, ha="center", va="bottom",
            fontsize=6.2, color="#444444")
    ax.set_xlim(XLO, XHI)
    ax.set_ylim(YLO, YHI)
    return plotted


def legend_handles():
    h = []
    for act, lab, c, mk in ACT:
        h.append(Line2D([0], [0], marker=mk, color="none", markerfacecolor=c, markeredgecolor=c,
                        markersize=6, label=lab))
    h.append(Line2D([0], [0], marker=F.MARK["hostwarm"], color="none", markerfacecolor="none",
                    markeredgecolor=F.C_HOSTWARM, markeredgewidth=1.0, markersize=6,
                    label="host-warm (flushed)"))
    h.append(Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markeredgecolor="black",
                    markeredgewidth=1.4, markersize=9, label="serves both"))
    return h


def record(cell):
    out = {}
    for act, _, _, _ in ACT:
        a = G[cell][act]
        if a.get("status") == "not measured":
            out[act] = {"status": "not measured", "plotted": False, "source": a.get("source")}
            continue
        out[act] = {
            "x_robot_ttft_s_median": round(a["robot_ttft_s"]["median"], 4),
            "y_extra_missed_median": a["extra_missed"]["median"],
            "x_min_max": [round(a["robot_ttft_s"]["min"], 4), round(a["robot_ttft_s"]["max"], 4)],
            "y_min_max": [a["extra_missed"]["min"], a["extra_missed"]["max"]],
            "hollow_flushed": is_hollow(act, a),
            "borrowed": a.get("measured_directly") is False,
            "in_good_region": a["extra_missed"]["median"] == 0 and a["robot_ttft_s"]["median"] < TARGET,
            "measured_tiers": a.get("measured_tiers"),
            "source": a.get("source"),
        }
    v, good = computed_verdict(cell)
    out["_verdict"] = {"computed": v, "expected": EXPECT[cell], "good_region_actions": good}
    return out


# ---------- 2 x 2 figure ----------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.5), sharex=True, sharey=True)
layout = [["light_tight", "light_roomy"], ["heavy_tight", "heavy_roomy"]]
tables = {}
for r in range(2):
    for cc in range(2):
        cell = layout[r][cc]
        tables[cell] = draw_panel(axes[r][cc], cell)
fig.supylabel("Extra missed dashcam deadlines", fontsize=8)
fig.text(0.5, 0.105, "Robot answer time from question (s)", ha="center", fontsize=8)
fig.legend(handles=legend_handles(), loc="lower center", ncol=6, fontsize=6.2,
           frameon=False, handletextpad=0.3, columnspacing=1.0, bbox_to_anchor=(0.5, 0.01))
fig.subplots_adjust(left=0.085, right=0.985, top=0.9, bottom=0.185, wspace=0.12, hspace=0.42)
pdf, png = F.save(fig, "figM7b_grid")

# ---------- 1 x 3 measured-only variant -------------------------------------
fig2, axes2 = plt.subplots(1, 3, figsize=(7.0, 3.0), sharex=True, sharey=True)
for ax, cell in zip(axes2, ["light_tight", "heavy_tight", "heavy_roomy"]):
    draw_panel(ax, cell)
fig2.supylabel("Extra missed\ndashcam deadlines", fontsize=8)
fig2.text(0.54, 0.145, "Robot answer time from question (s)", ha="center", fontsize=8)
fig2.legend(handles=legend_handles(), loc="lower center", ncol=6, fontsize=5.8,
            frameon=False, handletextpad=0.3, columnspacing=0.9, bbox_to_anchor=(0.5, 0.0))
fig2.subplots_adjust(left=0.105, right=0.99, top=0.78, bottom=0.30, wspace=0.12)
pdf2, png2 = F.save(fig2, "figM7b_grid_measured")

# ---------- JSON ------------------------------------------------------------
payload = {
    "figure": "M7b",
    "message": "The best way to serve a robot's cold-history question changes with fleet load and host memory, so no fixed rule works.",
    "source": "results/motivation/mot1/mot1_figdata_amend3.json block grid_2x2 (values used exactly, not recomputed)",
    "axes": {"x": "robot answer time from the question (s), shared 0 to 8.5",
             "y": "extra missed dashcam deadlines vs the no-question control, shared 0 to 80"},
    "load": {"light": "8 dashcams, 4 requests/s (26% of peak)",
             "heavy": "20 dashcams, 10 requests/s (66% of peak)"},
    "host": {"tight": "27 GiB", "roomy": "256 GiB"},
    "robot_deadline_s": TARGET,
    "palette": {"one go": "#D55E00", "2,048 pieces": "#56B4E9", "1,024 pieces": "#0072B2",
                "host-warm": "#009E73"},
    "verdict_rule": "an action is in the good region iff extra_missed median == 0 AND robot_ttft_s median < 5 s; pieces-only -> 'pieces serve both', host-warm-only -> 'only a warm history serves both', none -> 'nothing serves both'",
    "n": "5 paired repetitions per cell; whiskers min to max in both directions",
    "styling_rules": {
        "hollow": "HOST-WARM whose measured tier was not HOST in every repetition (flushed, answered cold)",
        "borrowed": "measured_directly == false, drawn at 50% alpha (light/roomy cold actions)",
        "not_measured": "light/roomy HOST-WARM: no point, 'host-warm: not measured' note"},
    "panels": {cell: record(cell) for cell in CELLS},
    "layout_2x2": "rows light(top)/heavy(bottom), cols tight(left)/roomy(right)",
    "layout_1x3_measured": ["light_tight", "heavy_tight", "heavy_roomy"],
    "outputs": {"grid_2x2": {"pdf": pdf, "png": png},
                "grid_1x3_measured": {"pdf": pdf2, "png": png2}},
}
print(F.dump_json("figM7b_grid", payload))

# verification table
print("\npanel        action      x(robot)  y(extra)  hollow borrowed  | source x,y median")
for cell in ["light_tight", "heavy_tight", "heavy_roomy", "light_roomy"]:
    for act, _, _, _ in ACT:
        a = G[cell][act]
        if a.get("status") == "not measured":
            print(f"{cell:12} {act:10} (not measured)")
            continue
        x = a["robot_ttft_s"]["median"]; y = a["extra_missed"]["median"]
        print(f"{cell:12} {act:10} {x:8.4f} {y:8d}  {str(is_hollow(act,a)):6} "
              f"{str(a.get('measured_directly') is False):8} | {x:.4f},{y}")
    v, good = computed_verdict(cell)
    print(f"   -> verdict '{v}' (good: {good})")
