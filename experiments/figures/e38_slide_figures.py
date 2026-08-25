#!/usr/bin/env python3
"""
E38 — Slide figures from committed data.
All values from committed result files / reports; see reports/e38_slide_figures.md for provenance.
"""
import math
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyArrowPatch

# ── Committed constants ──────────────────────────────────────────────────────
# Sources: E35 (reports/e34b_corrected_catchup.md), E34 (reports/e34_maintenance_semantics.md),
#          E26 (reports/phase1_cost_profiling.md), E33a, E29, E23, E36e.

MAINT_FULL_MS        = 66.0     # E35/E26: full warm-append median at L≈median
MAINT_WIN10_GROW_MS  = 36.0     # E35: win10 intra-session (growth, voice-rate)
MAINT_WIN10_SLIDE_MS = 975.0    # E34 Part A: win10 slide COLD median
SLIDE_FRAC           = 0.657    # E34: fraction of win10 transitions that are slides
MAINT_WIN10_AMZ_MS   = SLIDE_FRAC * MAINT_WIN10_SLIDE_MS + (1 - SLIDE_FRAC) * MAINT_WIN10_GROW_MS
# = 653 ms (E34 report); simulation uses 689.7 ms (E35 slide=1031 ms); discrepancy documented in report.
MAINT_SUM200_MS      = 5822.0   # E35: sum200 recursive median

KV_BYTES_PER_TOK = 57344        # E23: B/token for qwen7b on A6000
TOKENS_FULL      = 20092        # E33a: median full context (L_locomo_median)
TOKENS_WIN10     = 7275         # E33a: last-10-sessions (Definition A)
TOKENS_SUM200    = 160          # E29/E36e: KV-equivalent tokens for sum200

SERVE_FULL_MS   = 59.0          # [ASSUMPTION B1]
SERVE_WIN10_MS  = 59.0          # E35
SERVE_SUM200_MS = 32.0          # E35

KV_CAP_GIB = 9.0               # Figure 3 fixed kv_cap
KV_CAP_BYTES = KV_CAP_GIB * (1024 ** 3)

# Figure 3: N_mem per representation
N_MEM_FULL   = math.floor(KV_CAP_BYTES / (TOKENS_FULL   * KV_BYTES_PER_TOK))   # = 8
N_MEM_WIN10  = math.floor(KV_CAP_BYTES / (TOKENS_WIN10  * KV_BYTES_PER_TOK))   # = 23
N_MEM_SUM200 = math.floor(KV_CAP_BYTES / (TOKENS_SUM200 * KV_BYTES_PER_TOK))   # = 1053

# win10 amortized for Fig 3 uses 690 ms (E36e simulation constant = 689.7 ≈ 690 ms)
# to match the analytic table in E36e Part A, which produced the published N_eff values.
# Fig 1 uses 653 ms (E34 report) — discrepancy documented in report.
MAINT_WIN10_AMZ_SIM_MS = 690.0  # E36e/E36d simulation constant (rounded from 689.7)

def n_accel(maint_ms, serve_ms, ti_ms):
    return math.floor(ti_ms / (maint_ms + serve_ms))

def n_eff(maint_ms, serve_ms, n_mem, ti_ms):
    return min(n_mem, n_accel(maint_ms, serve_ms, ti_ms))

# ── Styles ───────────────────────────────────────────────────────────────────
FONT_TITLE  = 17
FONT_AXIS   = 15
FONT_TICK   = 13
FONT_ANNOT  = 12

FULL_COLOR  = "#2166AC"   # blue
WIN10_COLOR = "#FC8D59"   # orange
SUM_COLOR   = "#1A9641"   # green
GRAY        = "#888888"

os.makedirs("figures/slides", exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 1 — Maintenance cost by state form
# ═══════════════════════════════════════════════════════════════════════════════
bar_labels  = ["full\nwarm-append", "win10\ngrowth", "win10\namortized\n(0.657×slide+0.343×grow)", "sum200\nrecursive"]
bar_values  = [MAINT_FULL_MS, MAINT_WIN10_GROW_MS, MAINT_WIN10_AMZ_MS, MAINT_SUM200_MS]
bar_colors  = [FULL_COLOR, WIN10_COLOR, WIN10_COLOR, SUM_COLOR]
bar_hatches = ["", "", "//", ""]   # hatching marks the derived/amortized bar

fig, ax = plt.subplots(figsize=(11, 5))
ax.set_facecolor("#F8F8F8")
fig.patch.set_facecolor("white")

ys = list(range(len(bar_labels)))
bars = ax.barh(ys, bar_values, color=bar_colors, hatch=bar_hatches,
               edgecolor="white", height=0.55, zorder=2)

ax.set_xscale("log")
ax.set_xlabel("Maintenance cost (ms, log scale)", fontsize=FONT_AXIS)
ax.set_title("Maintenance cost by state form", fontsize=FONT_TITLE, fontweight="bold", pad=12)

ax.set_yticks(ys)
ax.set_yticklabels(bar_labels, fontsize=FONT_TICK)
ax.tick_params(axis="x", labelsize=FONT_TICK)
ax.set_xlim(5, 30000)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
ax.grid(axis="x", which="major", color="#DDDDDD", zorder=0)
ax.grid(axis="x", which="minor", color="#EEEEEE", zorder=0)

ax.axvline(1000, color="#CC0000", linestyle="--", linewidth=1.5, zorder=3, alpha=0.8)
ax.text(1000 * 1.08, 3.4, "1 s SLO", color="#CC0000", fontsize=FONT_ANNOT, va="top")

for bar, val in zip(bars, bar_values):
    x = val * 1.12
    ax.text(x, bar.get_y() + bar.get_height() / 2,
            f"{val:.0f} ms", va="center", ha="left", fontsize=FONT_TICK, color="#333333")

ax.text(0.99, 0.02,
        "vLLM 1.10–1.17× faster cold prefill; 1.59–2.55× faster warm-append vs HF (E26)",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=10, color="#555555",
        style="italic")

plt.tight_layout()
for ext in ("pdf", "png"):
    plt.savefig(f"figures/slides/e38_fig1_maintenance_cost.{ext}", dpi=150, bbox_inches="tight")
plt.close()
print("Fig 1 done.")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 2 — The inversion
# ═══════════════════════════════════════════════════════════════════════════════
kv_bytes = {
    "sum200": TOKENS_SUM200 * KV_BYTES_PER_TOK,          # 9,175,040 B = 9.2 MB
    "win10":  TOKENS_WIN10  * KV_BYTES_PER_TOK,          # 417,177,600 B = 417 MB
    "full":   TOKENS_FULL   * KV_BYTES_PER_TOK,          # 1,152,123,648 B = 1.15 GB
}
kv_mb = {k: v / 1e6 for k, v in kv_bytes.items()}       # in MB for display
maint = {"sum200": MAINT_SUM200_MS, "win10": MAINT_WIN10_AMZ_MS, "full": MAINT_FULL_MS}

cats     = ["sum200", "win10", "full"]
cat_lbls = ["sum200", "win10", "full"]
clrs     = [SUM_COLOR, WIN10_COLOR, FULL_COLOR]

fig, (ax_kv, ax_m) = plt.subplots(1, 2, figsize=(12, 5.5), sharey=False)
fig.patch.set_facecolor("white")
for ax in (ax_kv, ax_m):
    ax.set_facecolor("#F8F8F8")

# Left panel: KV footprint (log scale, MB)
kv_vals = [kv_mb[c] for c in cats]
ax_kv.barh(cat_lbls, kv_vals, color=clrs, edgecolor="white", height=0.55, zorder=2)
ax_kv.set_xscale("log")
ax_kv.set_xlabel("KV footprint (MB, log scale)", fontsize=FONT_AXIS)
ax_kv.set_title("KV footprint\n↑ ascending →", fontsize=FONT_TITLE, fontweight="bold")
ax_kv.tick_params(labelsize=FONT_TICK)
ax_kv.grid(axis="x", which="major", color="#DDDDDD", zorder=0)
ax_kv.grid(axis="x", which="minor", color="#EEEEEE", zorder=0)
ax_kv.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _:
    f"{v/1000:.1f} GB" if v >= 1000 else f"{v:.0f} MB"))
for i, (c, v) in enumerate(zip(cats, kv_vals)):
    label = f"{v:.0f} MB" if v < 1000 else f"{v/1000:.2f} GB"
    ax_kv.text(v * 1.15, i, label, va="center", ha="left", fontsize=FONT_TICK, color="#333333")

# Right panel: maintenance cost (log scale, ms)
m_vals = [maint[c] for c in cats]
ax_m.barh(cat_lbls, m_vals, color=clrs, edgecolor="white", height=0.55, zorder=2)
ax_m.set_xscale("log")
ax_m.set_xlabel("Maintenance cost (ms, log scale)", fontsize=FONT_AXIS)
ax_m.set_title("Maintenance cost\n← descending ↓", fontsize=FONT_TITLE, fontweight="bold")
ax_m.tick_params(labelsize=FONT_TICK)
ax_m.grid(axis="x", which="major", color="#DDDDDD", zorder=0)
ax_m.grid(axis="x", which="minor", color="#EEEEEE", zorder=0)
ax_m.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,} ms"))
for i, (c, v) in enumerate(zip(cats, m_vals)):
    ax_m.text(v * 1.12, i, f"{v:.0f} ms", va="center", ha="left", fontsize=FONT_TICK, color="#333333")

fig.suptitle("The smallest state to store is the most expensive to keep current",
             fontsize=FONT_TITLE, fontweight="bold", y=1.01)

plt.tight_layout()
for ext in ("pdf", "png"):
    plt.savefig(f"figures/slides/e38_fig2_inversion.{ext}", dpi=150, bbox_inches="tight")
plt.close()
print("Fig 2 done.")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Effective capacity = min(N_mem, N_accel) vs turn interval
# ═══════════════════════════════════════════════════════════════════════════════
ti_s_range = np.linspace(1, 65, 640)   # smooth curve

def n_eff_smooth(maint_ms, serve_ms, n_mem, ti_s_arr):
    return np.array([min(n_mem, math.floor(ti_s * 1000 / (maint_ms + serve_ms)))
                     for ti_s in ti_s_arr])

eff_full  = n_eff_smooth(MAINT_FULL_MS,          SERVE_FULL_MS,   N_MEM_FULL,  ti_s_range)
eff_win10 = n_eff_smooth(MAINT_WIN10_AMZ_SIM_MS, SERVE_WIN10_MS,  N_MEM_WIN10, ti_s_range)
eff_sum200= n_eff_smooth(MAINT_SUM200_MS,        SERVE_SUM200_MS, N_MEM_SUM200,ti_s_range)

# Dashed limits
accel_full  = np.array([n_accel(MAINT_FULL_MS,          SERVE_FULL_MS,   ti * 1000) for ti in ti_s_range], dtype=float)
accel_win10 = np.array([n_accel(MAINT_WIN10_AMZ_SIM_MS, SERVE_WIN10_MS,  ti * 1000) for ti in ti_s_range], dtype=float)
accel_sum200= np.array([n_accel(MAINT_SUM200_MS,        SERVE_SUM200_MS, ti * 1000) for ti in ti_s_range], dtype=float)

fig, ax = plt.subplots(figsize=(11, 6))
ax.set_facecolor("#F8F8F8")
fig.patch.set_facecolor("white")

lw_dash = 1.2
lw_main = 2.8

# Memory limit horizontal lines
ax.axhline(N_MEM_FULL,   color=FULL_COLOR,  linestyle=":", linewidth=lw_dash, alpha=0.6)
ax.axhline(N_MEM_WIN10,  color=WIN10_COLOR, linestyle=":", linewidth=lw_dash, alpha=0.6)
# sum200 N_mem=1053 is off-chart; skip

# Accelerator limits (dashed)
ax.plot(ti_s_range, np.clip(accel_full, 0, 60),   color=FULL_COLOR,  linestyle="--", linewidth=lw_dash, alpha=0.55, label="_nolegend_")
ax.plot(ti_s_range, np.clip(accel_win10, 0, 60),  color=WIN10_COLOR, linestyle="--", linewidth=lw_dash, alpha=0.55, label="_nolegend_")
ax.plot(ti_s_range, np.clip(accel_sum200, 0, 60), color=SUM_COLOR,   linestyle="--", linewidth=lw_dash, alpha=0.55, label="_nolegend_")

# Effective capacity (solid bold)
ax.plot(ti_s_range, np.clip(eff_full, 0, 60),    color=FULL_COLOR,  linewidth=lw_main, label=f"full (N_mem={N_MEM_FULL})")
ax.plot(ti_s_range, np.clip(eff_win10, 0, 60),   color=WIN10_COLOR, linewidth=lw_main, label=f"win10 (N_mem={N_MEM_WIN10})")
ax.plot(ti_s_range, np.clip(eff_sum200, 0, 60),  color=SUM_COLOR,   linewidth=lw_main, label="sum200")

# Mark crossover at 17.2s (E36e Part A2: win10 accel→mem-bound crossover)
# This is also where win10 N_eff stabilizes at N_mem=23, clearly > full N_eff=8.
CROSSOVER_TI = 17.2
ax.axvline(CROSSOVER_TI, color="#555555", linestyle="-.", linewidth=1.5, alpha=0.7)
ax.text(CROSSOVER_TI + 0.5, 43, f"win10 mem-bound\n(ti≈{CROSSOVER_TI}s)",
        fontsize=FONT_ANNOT, color="#555555", va="top")

# Point markers at the 4 sweep ti values
for ti_pt, color, eff_arr in [(5,  FULL_COLOR,  eff_full),
                               (15, WIN10_COLOR, eff_win10),
                               (30, WIN10_COLOR, eff_win10),
                               (60, WIN10_COLOR, eff_win10)]:
    pass   # Let the curves speak; no need for extra markers

# N_mem annotation labels
ax.text(63, N_MEM_FULL + 0.4,  f"N_mem(full)={N_MEM_FULL}",   color=FULL_COLOR,
        fontsize=FONT_ANNOT, ha="right", va="bottom")
ax.text(63, N_MEM_WIN10 + 0.4, f"N_mem(win10)={N_MEM_WIN10}", color=WIN10_COLOR,
        fontsize=FONT_ANNOT, ha="right", va="bottom")

# Caption about dashed/dotted lines
ax.text(0.01, 0.97,
        "— dashed: accel limit   ···· dotted: memory limit   — solid: N_eff = min(both)",
        transform=ax.transAxes, fontsize=10, color="#555555", va="top")

ax.set_xlabel("Turn interval (s)", fontsize=FONT_AXIS)
ax.set_ylabel("Sessions supported (N_eff)", fontsize=FONT_AXIS)
ax.set_title(f"Effective capacity vs turn interval  (kv_cap={KV_CAP_GIB} GiB, LoCoMo)",
             fontsize=FONT_TITLE, fontweight="bold", pad=12)
ax.set_xlim(1, 65)
ax.set_ylim(-0.5, 50)
ax.tick_params(labelsize=FONT_TICK)
ax.legend(fontsize=FONT_TICK, loc="upper left", framealpha=0.9)
ax.grid(axis="both", color="#DDDDDD", zorder=0)

plt.tight_layout()
for ext in ("pdf", "png"):
    plt.savefig(f"figures/slides/e38_fig3_effective_capacity.{ext}", dpi=150, bbox_inches="tight")
plt.close()
print("Fig 3 done.")

# ── Print provenance summary ──────────────────────────────────────────────────
print(f"\n=== E38 committed constants ===")
print(f"MAINT_FULL_MS        = {MAINT_FULL_MS:.1f} ms")
print(f"MAINT_WIN10_GROW_MS  = {MAINT_WIN10_GROW_MS:.1f} ms")
print(f"MAINT_WIN10_SLIDE_MS = {MAINT_WIN10_SLIDE_MS:.1f} ms  (E34 Part A)")
print(f"SLIDE_FRAC           = {SLIDE_FRAC}")
print(f"MAINT_WIN10_AMZ_MS   = {MAINT_WIN10_AMZ_MS:.1f} ms  (Fig 1; sim uses {MAINT_WIN10_AMZ_SIM_MS} ms)")
print(f"MAINT_SUM200_MS      = {MAINT_SUM200_MS:.1f} ms")
print(f"KV footprint sum200  = {TOKENS_SUM200 * KV_BYTES_PER_TOK / 1e6:.2f} MB  ({TOKENS_SUM200} tok × {KV_BYTES_PER_TOK} B)")
print(f"KV footprint win10   = {TOKENS_WIN10 * KV_BYTES_PER_TOK / 1e6:.1f} MB  ({TOKENS_WIN10} tok × {KV_BYTES_PER_TOK} B)")
print(f"KV footprint full    = {TOKENS_FULL * KV_BYTES_PER_TOK / 1e9:.3f} GB  ({TOKENS_FULL} tok × {KV_BYTES_PER_TOK} B)")
print(f"N_MEM: full={N_MEM_FULL}  win10={N_MEM_WIN10}  sum200={N_MEM_SUM200}")
print(f"N_accel at ti=5s:  full={n_accel(MAINT_FULL_MS,SERVE_FULL_MS,5000)}  "
      f"win10={n_accel(MAINT_WIN10_AMZ_SIM_MS,SERVE_WIN10_MS,5000)}  "
      f"sum200={n_accel(MAINT_SUM200_MS,SERVE_SUM200_MS,5000)}")
print(f"N_accel at ti=15s: full={n_accel(MAINT_FULL_MS,SERVE_FULL_MS,15000)}  "
      f"win10={n_accel(MAINT_WIN10_AMZ_SIM_MS,SERVE_WIN10_MS,15000)}  "
      f"sum200={n_accel(MAINT_SUM200_MS,SERVE_SUM200_MS,15000)}")
print(f"N_accel at ti=30s: full={n_accel(MAINT_FULL_MS,SERVE_FULL_MS,30000)}  "
      f"win10={n_accel(MAINT_WIN10_AMZ_SIM_MS,SERVE_WIN10_MS,30000)}  "
      f"sum200={n_accel(MAINT_SUM200_MS,SERVE_SUM200_MS,30000)}")
print(f"N_accel at ti=60s: full={n_accel(MAINT_FULL_MS,SERVE_FULL_MS,60000)}  "
      f"win10={n_accel(MAINT_WIN10_AMZ_SIM_MS,SERVE_WIN10_MS,60000)}  "
      f"sum200={n_accel(MAINT_SUM200_MS,SERVE_SUM200_MS,60000)}")
