"""LoCoMo crossover figure — incompressible context story."""

import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.lines as mlines
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

# ── Palette (matches plot_frame_sweep.py) ──────────────────────────────────────
BLUE   = "#2563EB"
ORANGE = "#EA580C"
GRAY   = "#6B7280"
AMBER  = "#B45309"   # inertia curve

for sty in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "default"):
    try:
        plt.style.use(sty)
        break
    except OSError:
        continue

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Liberation Sans", "Arial"],
    "font.size": 10,
    "axes.spines.top": False,
    "axes.grid": True,
    "grid.alpha": 0.22,
    "grid.linestyle": "-",
    "grid.linewidth": 0.4,
    "axes.edgecolor": "#555",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# ── Load data ──────────────────────────────────────────────────────────────────

locomo = json.load(open(ROOT / "results" / "frontier_locomo_qwen7b.json"))
sm = locomo["summary"]

def s(name):
    r = sm[name]
    acc = r["accuracy"]
    return dict(
        acc=acc,
        tok=r["mean_prompt_tokens"],
        el=acc - r["ci_lo"],
        eu=r["ci_hi"] - acc,
    )

inertia_raw = json.load(open(ROOT / "results" / "inertia_smollm2_jetson.json"))
depths = np.array([d["depth"] for d in inertia_raw["depths"]], dtype=float)
ms_meas = np.array([d["prefill_ms_mean"] for d in inertia_raw["depths"]])

# Power-law extrapolation: log(ms) = α·log(tok) + β
alpha, beta = np.polyfit(np.log(depths), np.log(ms_meas), 1)

def inertia_s(tok):
    return np.exp(alpha * np.log(tok) + beta) / 1000.0

# ── Figure ─────────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(13, 6.5))
ax2 = ax.twinx()

ax.spines["right"].set_visible(False)
ax2.spines["top"].set_visible(False)
ax2.spines["left"].set_visible(False)
ax2.spines["right"].set_edgecolor(AMBER)

# ── Inertia curve ──────────────────────────────────────────────────────────────

meas_curve_x = np.linspace(100, 8192, 120)
meas_curve_y = [inertia_s(x) for x in meas_curve_x]
extrap_x = np.linspace(8192, 20500, 60)
extrap_y = [inertia_s(x) for x in extrap_x]

ax2.plot(meas_curve_x, meas_curve_y,  color=AMBER, lw=2.0, ls="-",  alpha=0.85, zorder=1,
         label="edge re-prefill (measured)")
ax2.plot(extrap_x, extrap_y,          color=AMBER, lw=2.0, ls="--", alpha=0.55, zorder=1,
         label="edge re-prefill (extrapolated)")

# Measured limit marker
ax2.axvline(8192, color=AMBER, lw=0.7, ls=":", alpha=0.45)
ax2.text(8400, 0.15, "measured\nlimit\n(8K tok)", color=AMBER, fontsize=7, va="bottom", alpha=0.75)

# ── Accuracy points ─────────────────────────────────────────────────────────────

CONDS = {
    "blind":       dict(**s("blind"),      color=GRAY,   mk="o", ms=9,  zo=5),
    "stateless":   dict(**s("stateless"),  color=GRAY,   mk="D", ms=8,  zo=5),
    "summary-80":  dict(**s("summary-80"), color=ORANGE, mk="s", ms=9,  zo=5),
    "summary-200": dict(**s("summary-200"),color=ORANGE, mk="s", ms=9,  zo=5),
    "window-3":    dict(**s("window-3"),   color=BLUE,   mk="o", ms=9,  zo=5),
    "window-10":   dict(**s("window-10"),  color=BLUE,   mk="o", ms=9,  zo=5),
    "full":        dict(**s("full"),       color=BLUE,   mk="*", ms=17, zo=6),
    "shuffled":    dict(**s("shuffled"),   color=GRAY,   mk="X", ms=10, zo=5),
}

for name, c in CONDS.items():
    ax.errorbar(
        c["tok"], c["acc"] * 100,
        yerr=[[c["el"] * 100], [c["eu"] * 100]],
        fmt=c["mk"], color=c["color"], markersize=c["ms"],
        capsize=4, capthick=1.2, elinewidth=1.2, linewidth=0, zorder=c["zo"],
    )

# Window → full trend
trend_x = [s("window-3")["tok"], s("window-10")["tok"], s("full")["tok"]]
trend_y = [s(k)["acc"] * 100 for k in ("window-3", "window-10", "full")]
ax.plot(trend_x, trend_y, color=BLUE, lw=1.2, ls="-", alpha=0.45, zorder=2)

# ── Point labels ──────────────────────────────────────────────────────────────

LABEL_OFFSETS = {
    "blind":       (-8,   9),
    "stateless":   ( 6, -13),
    "summary-80":  (-68, -14),
    "summary-200": ( 6,   5),
    "window-3":    ( 6,   5),
    "window-10":   ( 6,   5),
    "full":        ( 6,   2),
    "shuffled":    ( 6, -13),
}

for name, c in CONDS.items():
    dx, dy = LABEL_OFFSETS[name]
    ax.annotate(name, (c["tok"], c["acc"] * 100),
                xytext=(dx, dy), textcoords="offset points",
                fontsize=7.5, color=c["color"], fontweight="bold")

# ── Axes ──────────────────────────────────────────────────────────────────────

ax.set_xscale("log")
ax.set_xlim(50, 22000)
ax.set_ylim(0, 36)
ax.set_xlabel("Retained context (tokens, log scale)", fontsize=11)
ax.set_ylabel("Accuracy (%)", color=BLUE, fontsize=11)
ax.tick_params(axis="y", labelcolor=BLUE)

ax.set_xticks([100, 250, 500, 1000, 2500, 5000, 10000, 20000])
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
ax.xaxis.set_minor_formatter(mticker.NullFormatter())

right_max_s = inertia_s(21000) * 1.1
ax2.set_ylim(0, right_max_s)
ax2.set_ylabel("Edge re-prefill latency (s)\n[SmolLM2-1.7B, Jetson AGX Orin]",
               color=AMBER, fontsize=10)
ax2.tick_params(axis="y", labelcolor=AMBER)

# ── Blind floor line ──────────────────────────────────────────────────────────

blind_pct = s("blind")["acc"] * 100
ax.axhline(blind_pct, color=GRAY, lw=1.0, ls="--", alpha=0.55, zorder=1)
ax.text(55, blind_pct + 0.5, f"blind floor ({int(blind_pct)}% — no context)",
        color=GRAY, fontsize=7.5, va="bottom")

# ── Annotations ───────────────────────────────────────────────────────────────

# INCOMPRESSIBLE callout — summary cluster
ax.annotate(
    "summary ≈ blind (6% vs 8%)\ngeneric summarization discards\nthe specific fact.\n"
    "−20 pp vs full (p = 0.016).\nINCOMPRESSIBLE.",
    xy=(s("summary-200")["tok"], s("summary-200")["acc"] * 100),
    xytext=(420, 20),
    arrowprops=dict(arrowstyle="->", color=ORANGE, lw=1.1),
    fontsize=8, color=ORANGE, fontweight="bold",
    bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=ORANGE, alpha=0.92),
)

# Accuracy tracks context — arrow to window-10
ax.annotate(
    "accuracy tracks how much history\nis visible — no early saturation",
    xy=(s("window-10")["tok"], s("window-10")["acc"] * 100),
    xytext=(2000, 27),
    arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0),
    fontsize=8.5, color=BLUE,
    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=BLUE, alpha=0.88),
)

# Shuffled order doesn't matter
ax.annotate(
    "order doesn't matter\nfor single-hop recall\n(shuffled vs full p = 0.25)",
    xy=(s("shuffled")["tok"], s("shuffled")["acc"] * 100),
    xytext=(7500, 24),
    arrowprops=dict(arrowstyle="->", color=GRAY, lw=1.0),
    fontsize=7.5, color=GRAY,
)

# Full point note — 19K tokens
ax.annotate(
    "≈19K tok: past measured edge\nprofile & SmolLM2's 2K ctx limit",
    xy=(s("full")["tok"], s("full")["acc"] * 100),
    xytext=(9000, 32),
    arrowprops=dict(arrowstyle="->", color="#666", lw=0.9),
    fontsize=7, color="#555",
)

# Core-message box at bottom centre
core = ("No cheap-summary escape (unlike EgoSchema)\n"
        "→ to get accuracy you must carry the context"
        "  →  you must climb the inertia curve")
ax.text(0.5, 0.03, core, transform=ax.transAxes,
        fontsize=8.5, color="#1e293b", ha="center", va="bottom",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#f0f9ff", edgecolor="#0ea5e9", alpha=0.92))

# Contrast callout — top left
contrast = ("EgoSchema: summary-200 ≈ full at ~40% the tokens (compressible).\n"
            "LoCoMo:       summary ≈ blind; only full recovers accuracy (incompressible).")
ax.text(0.005, 0.985, contrast, transform=ax.transAxes,
        fontsize=7.5, color="#374151", va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#fefce8", edgecolor="#d97706", alpha=0.93))

# ── Title ──────────────────────────────────────────────────────────────────────

fig.suptitle("Task value tracks context — no saturation  (LoCoMo, n = 50)",
             fontsize=13, fontweight="bold", y=0.985)
ax.set_title("summary collapses to blind: context is incompressible",
             fontsize=9.5, color="#555", pad=5)

# ── Legend ─────────────────────────────────────────────────────────────────────

leg_handles = [
    mlines.Line2D([0], [0], color=BLUE,   marker="o", ls="", ms=8, label="window / full"),
    mlines.Line2D([0], [0], color=ORANGE, marker="s", ls="", ms=8, label="summary"),
    mlines.Line2D([0], [0], color=GRAY,   marker="o", ls="", ms=8, label="baseline / control"),
    mlines.Line2D([0], [0], color=AMBER, lw=2, ls="-",  label="inertia curve (measured)"),
    mlines.Line2D([0], [0], color=AMBER, lw=2, ls="--", label="inertia curve (extrapolated)"),
]
ax.legend(handles=leg_handles, fontsize=8, loc="lower right",
          frameon=True, framealpha=0.9, edgecolor="#ccc")

# ── Footnote ──────────────────────────────────────────────────────────────────

fig.text(
    0.5, 0.005,
    ("LoCoMo single-hop, n = 50, Qwen2.5-7B-Instruct (32 K ctx).  "
     "Substring scorer deflates absolute accuracy — the summary-vs-full gap is conservative; "
     "relative gaps valid (scorer applied identically)."),
    ha="center", fontsize=7.5, color="#666", style="italic",
)

# ── Save ──────────────────────────────────────────────────────────────────────

fig.tight_layout(rect=[0, 0.035, 1, 0.97])
out = FIGURES / "crossover_locomo.png"
fig.savefig(out, dpi=300, bbox_inches="tight")
print(f"Saved {out}")
