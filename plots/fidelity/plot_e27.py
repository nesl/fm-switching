"""
Plot E27: Maintenance-mechanism kill test.

Produces two figures:
  figures/fidelity/e27_drift_curves.pdf
    — LoCoMo accuracy vs checkpoint for full_regen, recursive, periodic_5
      at sum80 and sum200 budgets, plus window-10 and full as references

  figures/fidelity/e27_lifecycle_cost.pdf
    — Expected refresh cost (seconds) per mode × budget at representative L values
      computed from cold_prefill_s(mean_input_tokens), both workloads
"""

import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = ROOT / "results" / "fidelity" / "e27_maintenance"
FIG_DIR    = ROOT / "figures" / "fidelity"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Cold-prefill curve (a6000) — same as in experiment script
_A6K_L = [1024, 2048, 4096, 8192, 16384, 24576, 32768, 49152, 65536]
_A6K_S = [0.165, 0.325, 0.667, 1.369, 3.090, 5.245, 7.805, 14.820, 21.720]


def cold_prefill_s(n_tokens):
    import bisect
    if n_tokens <= _A6K_L[0]: return _A6K_S[0]
    if n_tokens >= _A6K_L[-1]:
        slope = (_A6K_S[-1] - _A6K_S[-2]) / (_A6K_L[-1] - _A6K_L[-2])
        return _A6K_S[-1] + slope * (n_tokens - _A6K_L[-1])
    idx = bisect.bisect_right(_A6K_L, n_tokens)
    L0, L1 = _A6K_L[idx-1], _A6K_L[idx]
    t0, t1 = _A6K_S[idx-1], _A6K_S[idx]
    return t0 + (t1 - t0) * (n_tokens - L0) / (L1 - L0)


def load_results(path: Path) -> dict:
    return json.loads(path.read_text())


def acc_series(locomo_accuracy: dict, key: str) -> tuple:
    """Return (fracs, accs) for a given condition key across checkpoints 0-3."""
    fracs = [0.25, 0.50, 0.75, 1.0]
    accs = []
    for cp_idx in range(4):
        d = locomo_accuracy.get(str(cp_idx), locomo_accuracy.get(cp_idx, {}))
        val = d.get(key, {}).get("accuracy")
        accs.append(val)
    return fracs, accs


def plot_drift_curves(result: dict, out_path: Path):
    locomo_acc = result.get("locomo_accuracy", {})
    if not locomo_acc:
        print("No LoCoMo accuracy data, skipping drift curves")
        return

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    fracs = [0.25, 0.50, 0.75, 1.0]

    for ax, budget in zip(axes, ["sum80", "sum200"]):
        # Reference lines
        for ref_key, label, ls, color in [
            ("full", "full history", "-", "#1a6fe0"),
            ("window_10", "window-10", "--", "#2da050"),
            ("blind", "blind", ":", "#888888"),
        ]:
            _, vals = acc_series(locomo_acc, ref_key)
            if any(v is not None for v in vals):
                ax.plot(fracs, vals, linestyle=ls, color=color, lw=1.5,
                        label=label, zorder=3)

        # Maintenance modes
        mode_styles = [
            ("full_regen", f"full_regen_{budget}", "s-", "#e05a1a"),
            ("recursive", f"recursive_{budget}", "o-", "#c01090"),
            ("periodic_5", f"periodic_5_{budget}", "^--", "#9060c0"),
        ]
        for mode_label, key, fmt, color in mode_styles:
            _, vals = acc_series(locomo_acc, key)
            if any(v is not None for v in vals):
                ax.plot(fracs, vals, fmt, color=color, lw=1.5, ms=5,
                        label=mode_label, zorder=4)

        ax.set_xlabel("Session coverage (fraction)", fontsize=10)
        ax.set_title(f"Budget: {budget}", fontsize=10)
        ax.set_xlim(0.2, 1.05)
        ax.set_ylim(-0.02, None)
        ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
        ax.grid(axis="y", alpha=0.3)
        ax.legend(fontsize=8, loc="upper left", framealpha=0.7)

    axes[0].set_ylabel("QA accuracy (LoCoMo cat=1)", fontsize=10)
    fig.suptitle("E27: LoCoMo accuracy vs session coverage", fontsize=12, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_lifecycle_cost(result: dict, out_path: Path):
    lifecycle = result.get("lifecycle_cost", {})
    if not lifecycle:
        print("No lifecycle cost data, skipping lifecycle figure")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    for ax, (workload_key, title) in zip(axes, [
        ("locomo", "LoCoMo (dense-incompressible)"),
        ("egoschema", "EgoSchema (gist-compressible)"),
    ]):
        wl_data = lifecycle.get(workload_key, {})
        if not wl_data:
            ax.set_title(f"{title}\n(no data)")
            continue

        keys = sorted(wl_data.keys())
        labels, mean_toks, est_lats, meas_lats = [], [], [], []
        for key in keys:
            d = wl_data[key]
            mean_tok = d.get("mean_input_tokens", 0)
            est_lat = d.get("est_refresh_latency_s", cold_prefill_s(int(mean_tok)))
            meas_lat = d.get("mean_measured_latency_s", 0)
            labels.append(key.replace("_", "\n"))
            mean_toks.append(mean_tok)
            est_lats.append(est_lat)
            meas_lats.append(meas_lat)

        x = np.arange(len(labels))
        width = 0.35
        ax.bar(x - width/2, est_lats, width, label="Est. refresh (cold_prefill)", color="#1a6fe0", alpha=0.8)
        ax.bar(x + width/2, meas_lats, width, label="Measured generation latency", color="#e05a1a", alpha=0.8)

        # Add window-10 warm_append reference
        ax.axhline(0.066, color="#2da050", linestyle="--", lw=1.5,
                   label="window-10 warm-append (0.066s)")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("Latency (s)", fontsize=10)
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, None)

    fig.suptitle("E27: Summary refresh cost by maintenance mode", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def main():
    # Try to find the main result file
    candidates = [
        RESULT_DIR / "e27_maintenance_qwen7b.json",
        RESULT_DIR / "e27_maintenance_qwen7b_smoke.json",
    ]
    result_path = None
    for c in candidates:
        if c.exists():
            result_path = c
            break

    if result_path is None:
        print("No result file found yet. Run the experiment first.")
        sys.exit(1)

    print(f"Loading from: {result_path}")
    result = load_results(result_path)

    plot_drift_curves(result, FIG_DIR / "e27_drift_curves.pdf")
    plot_lifecycle_cost(result, FIG_DIR / "e27_lifecycle_cost.pdf")


if __name__ == "__main__":
    main()
