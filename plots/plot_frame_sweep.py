"""
Plot the frame-count sweep results from exp7_frame_sweep.json.

Panel A: dual-axis — frames (x), full-context accuracy with 95% binomial CI
         (left axis, solid), prefill latency ms (right axis, dashed).
         Stateless accuracy plotted as a horizontal reference line.

Panel B: accuracy-vs-inertia trade-off — prefill latency on x, full-context
         accuracy on y with 95% CIs, each point labeled by frame count.

Works with whatever frame counts are present in the JSON (auto-includes 32
when the 32-frame run completes and results are merged into the file).

Usage:
    python plots/plot_frame_sweep.py
    python plots/plot_frame_sweep.py --input results/exp7_frame_sweep.json \
                                     --output plots/frame_sweep.png
"""

import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np


def wilson_ci(p: float, n: int, z: float = 1.96):
    """Wilson score 95% confidence interval for a proportion.

    Returns (lower, upper) half-widths (i.e., p - lower, upper - p) so the
    caller can pass them directly to errorbar's yerr.
    """
    if n == 0:
        return 0.0, 0.0
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return p - lo, hi - p  # lower err, upper err


def load_sweep(path: Path):
    """Return sorted list of (n_frames, full_acc, full_ms, full_tok, sl_acc, n)."""
    data = json.loads(path.read_text())
    sweep = data["sweep_summary"]
    rows = []
    for k, v in sweep.items():
        n_frames = int(k)
        full = v.get("full", {})
        sl   = v.get("stateless", {})
        rows.append({
            "n_frames":    n_frames,
            "full_acc":    full.get("accuracy", 0.0),
            "full_ms":     full.get("mean_prefill_ms", 0.0),
            "full_tok":    full.get("mean_prompt_tokens", 0.0),
            "sl_acc":      sl.get("accuracy", 0.0),
            "n":           full.get("n", 0),
        })
    rows.sort(key=lambda r: r["n_frames"])
    return rows


def make_plot(rows, out_path: Path):
    frames  = [r["n_frames"]  for r in rows]
    acc     = [r["full_acc"]  for r in rows]
    ms      = [r["full_ms"]   for r in rows]
    sl_acc  = [r["sl_acc"]    for r in rows]
    ns      = [r["n"]         for r in rows]

    # 95% Wilson CIs for full-context accuracy
    ci_lo = [wilson_ci(a, n)[0] for a, n in zip(acc, ns)]
    ci_hi = [wilson_ci(a, n)[1] for a, n in zip(acc, ns)]
    yerr  = np.array([ci_lo, ci_hi])

    # average stateless accuracy and CI as a flat reference
    sl_mean = float(np.mean(sl_acc))
    sl_n    = ns[0] if ns else 150
    sl_lo, sl_hi = wilson_ci(sl_mean, sl_n)

    BLUE   = "#2563EB"
    ORANGE = "#EA580C"
    GRAY   = "#6B7280"

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.suptitle("EgoSchema Frame-Count Sweep (150 questions, fp16, A6000)",
                 fontsize=11, y=1.01)

    # ── Panel A: dual-axis ───────────────────────────────────────────────
    ax_lat = ax_a.twinx()

    # Latency (right axis, dashed)
    ax_lat.plot(frames, ms, color=ORANGE, linestyle="--", linewidth=1.6,
                marker="s", markersize=5, label="Prefill latency (ms)")
    ax_lat.set_ylabel("Mean prefill latency (ms)", color=ORANGE, fontsize=9)
    ax_lat.tick_params(axis="y", labelcolor=ORANGE, labelsize=8)
    ax_lat.yaxis.set_minor_locator(mticker.AutoMinorLocator())

    # Full-context accuracy + CI (left axis, solid)
    ax_a.errorbar(frames, acc, yerr=yerr, color=BLUE, linewidth=1.8,
                  marker="o", markersize=6, capsize=4, capthick=1.2,
                  label="Full-context acc (±95% CI)")

    # Stateless reference band
    ax_a.axhline(sl_mean, color=GRAY, linestyle=":", linewidth=1.2)
    ax_a.axhspan(sl_mean - sl_lo, sl_mean + sl_hi, color=GRAY, alpha=0.12)
    ax_a.text(frames[-1], sl_mean + 0.005, "stateless", color=GRAY,
              fontsize=7.5, ha="right", va="bottom")

    ax_a.set_xlabel("Frame count (N)", fontsize=9)
    ax_a.set_ylabel("Accuracy (5-way MC)", color=BLUE, fontsize=9)
    ax_a.tick_params(axis="y", labelcolor=BLUE, labelsize=8)
    ax_a.set_xticks(frames)
    ax_a.set_ylim(0.0, 1.0)
    ax_a.yaxis.set_minor_locator(mticker.AutoMinorLocator())
    ax_a.set_title("A  Accuracy & latency vs. frame count", fontsize=9, loc="left")

    # Combined legend
    h1, l1 = ax_a.get_legend_handles_labels()
    h2, l2 = ax_lat.get_legend_handles_labels()
    ax_a.legend(h1 + h2, l1 + l2, fontsize=7.5, loc="lower right")

    # ── Panel B: accuracy vs. inertia ────────────────────────────────────
    ax_b.errorbar(ms, acc, yerr=yerr, color=BLUE, linestyle="-",
                  linewidth=1.2, marker="o", markersize=7,
                  capsize=4, capthick=1.2)

    for x, y, n in zip(ms, acc, frames):
        ax_b.annotate(f"{n}f", (x, y),
                      textcoords="offset points", xytext=(6, 4),
                      fontsize=8, color=BLUE)

    # Stateless reference
    ax_b.axhline(sl_mean, color=GRAY, linestyle=":", linewidth=1.2)
    ax_b.axhspan(sl_mean - sl_lo, sl_mean + sl_hi, color=GRAY, alpha=0.12)
    ax_b.text(min(ms), sl_mean + 0.005, "stateless", color=GRAY,
              fontsize=7.5, ha="left", va="bottom")

    ax_b.set_xlabel("Mean prefill latency (ms)", fontsize=9)
    ax_b.set_ylabel("Full-context accuracy", fontsize=9)
    ax_b.set_ylim(0.0, 1.0)
    ax_b.tick_params(labelsize=8)
    ax_b.yaxis.set_minor_locator(mticker.AutoMinorLocator())
    ax_b.set_title("B  Accuracy vs. inertia trade-off", fontsize=9, loc="left")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    print(f"Saved {out_path}  ({out_path.stat().st_size // 1024} KB)")


def main():
    ap = argparse.ArgumentParser(description="Plot frame-count sweep results")
    ap.add_argument("--input",  default="results/exp7_frame_sweep.json")
    ap.add_argument("--output", default="plots/frame_sweep.png")
    args = ap.parse_args()

    rows = load_sweep(Path(args.input))
    print(f"Loaded {len(rows)} frame counts: "
          f"{[r['n_frames'] for r in rows]}")
    for r in rows:
        lo, hi = wilson_ci(r["full_acc"], r["n"])
        print(f"  {r['n_frames']:2d}f  full={r['full_acc']:.3f} "
              f"[{r['full_acc']-lo:.3f}, {r['full_acc']+hi:.3f}]  "
              f"ms={r['full_ms']:.1f}  sl={r['sl_acc']:.3f}  n={r['n']}")
    make_plot(rows, Path(args.output))


if __name__ == "__main__":
    main()
