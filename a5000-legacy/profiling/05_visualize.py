"""
05_visualize.py — Generate plots from profiling data

Produces three key visualizations:
  1. GPU + vLLM metrics over time (utilization, KV cache occupancy, request concurrency)
  2. Per-session context depth growth and incremental latency
  3. Context inertia curve (prefill cost vs depth) — THE MONEY PLOT

Usage:
    python 05_visualize.py [--logs-dir logs/] [--output-dir plots/]
"""

import os
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")  # non-interactive backend


def plot_gpu_metrics(df: pd.DataFrame, output_dir: str):
    """Plot GPU utilization and vLLM KV cache metrics over time.

    Uses scatter plots for GPU utilization (avoids false diagonal artifact from
    sparse spike data when using line plots with many zero samples).
    Shows vLLM KV cache occupancy as the primary memory pressure signal.
    """
    has_vllm = "vllm_cache_usage_pct" in df.columns and (df["vllm_cache_usage_pct"] >= 0).any()

    nrows = 3 if has_vllm else 2
    fig, axes = plt.subplots(nrows, 1, figsize=(14, 4 * nrows), sharex=True)
    fig.suptitle("GPU + vLLM Metrics During Workload", fontsize=14, fontweight="bold")

    ax_util, ax_power = axes[0], axes[1]
    ax_cache = axes[2] if has_vllm else None

    # GPU utilization — scatter to avoid false diagonal from sparse spikes
    ax_util.scatter(df["elapsed_s"], df["gpu_utilization_pct"],
                    s=1, alpha=0.4, color="#1f77b4")
    ax_util.set_ylabel("GPU Utilization (%)")
    ax_util.set_ylim(0, 105)
    ax_util.grid(True, alpha=0.3)

    # Power draw
    ax_power.plot(df["elapsed_s"], df["power_draw_w"],
                  linewidth=0.8, alpha=0.8, color="#ff7f0e")
    ax_power.set_ylabel("Power Draw (W)")
    ax_power.grid(True, alpha=0.3)

    if has_vllm:
        # KV cache usage — the real memory signal
        vllm_df = df[df["vllm_cache_usage_pct"] >= 0]
        ax_cache.plot(vllm_df["elapsed_s"], vllm_df["vllm_cache_usage_pct"] * 100,
                      linewidth=1.5, color="#2ca02c", label="KV cache used %")
        # Overlay request concurrency on a secondary axis
        ax_cache2 = ax_cache.twinx()
        ax_cache2.plot(vllm_df["elapsed_s"], vllm_df["vllm_requests_running"],
                       linewidth=1, color="#9467bd", alpha=0.7, linestyle="--",
                       label="Requests running")
        ax_cache.set_ylabel("KV Cache Occupancy (%)", color="#2ca02c")
        ax_cache2.set_ylabel("Requests Running", color="#9467bd")
        ax_cache.set_xlabel("Time (seconds)")
        ax_cache.grid(True, alpha=0.3)
        # Combined legend
        lines1, labels1 = ax_cache.get_legend_handles_labels()
        lines2, labels2 = ax_cache2.get_legend_handles_labels()
        ax_cache.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
        ax_cache.set_title("vLLM KV Cache Occupancy (actual session load — replaces flat pynvml memory)",
                           fontsize=10)
    else:
        ax_power.set_xlabel("Time (seconds)")

    plt.tight_layout()
    path = os.path.join(output_dir, "gpu_metrics.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def plot_session_traces(df: pd.DataFrame, output_dir: str):
    """Plot per-session context depth growth and incremental latency."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    df["ts"] = pd.to_datetime(df["timestamp"])
    t0 = df["ts"].min()
    df["elapsed_s"] = (df["ts"] - t0).dt.total_seconds()

    colors = plt.cm.Set2.colors
    sessions = df["session_id"].unique()

    for i, sid in enumerate(sorted(sessions)):
        sdf = df[df["session_id"] == sid]
        label = f"Session {sid} ({sdf['session_name'].iloc[0]})"
        ax1.plot(sdf["elapsed_s"], sdf["total_context_tokens"],
                 marker="o", markersize=4, label=label, color=colors[i % len(colors)])

    ax1.set_ylabel("Total Context Tokens (KV Cache Size)")
    ax1.set_xlabel("Time (seconds)")
    ax1.set_title("KV Cache Growth Per Session")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Incremental latency — NOT migration cost
    for i, sid in enumerate(sorted(sessions)):
        sdf = df[df["session_id"] == sid]
        ax2.plot(sdf["elapsed_s"], sdf["incremental_latency_s"],
                 marker="s", markersize=3, label=f"Session {sid}",
                 color=colors[i % len(colors)])

    ax2.set_ylabel("Incremental Latency (seconds)")
    ax2.set_xlabel("Time (seconds)")
    ax2.set_title("Incremental Serving Latency Per Turn\n"
                  "(warm KV cache — NOT migration cost; see context_inertia_curve.png for that)")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, "session_traces.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


def plot_prefill_cost_curve(df: pd.DataFrame, output_dir: str):
    """Plot the context inertia curve — THE KEY FIGURE FOR THE PAPER."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    grouped = df.groupby("actual_prompt_tokens").agg(
        prefill_mean=("prefill_time_ms", "mean"),
        prefill_std=("prefill_time_ms", "std"),
        ms_per_token_mean=("ms_per_token", "mean"),
    ).reset_index()

    x = grouped["actual_prompt_tokens"].values
    y = grouped["prefill_mean"].values

    # Fit linear model and overlay
    coeffs = np.polyfit(x, y, 1)
    x_fit = np.linspace(x.min(), x.max(), 200)
    r2 = 1 - np.sum((y - np.polyval(coeffs, x))**2) / np.sum((y - y.mean())**2)

    ax1.errorbar(x, y, yerr=grouped["prefill_std"].values,
                 fmt="o", capsize=4, color="#d62728", markersize=8, zorder=3,
                 label="Measured (mean ± std)")
    ax1.plot(x_fit, np.polyval(coeffs, x_fit),
             "--", color="#888888", linewidth=1.5,
             label=f"Linear fit: {coeffs[0]:.4f}n + {coeffs[1]:.1f}ms  (R²={r2:.4f})")

    ax1.set_xlabel("Context Depth (tokens)", fontsize=12)
    ax1.set_ylabel("Re-Prefill Time / TTFT (ms)", fontsize=12)
    ax1.set_title("Context Inertia: Migration Cost vs Session Depth", fontsize=13)
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    max_row = grouped.loc[grouped["prefill_mean"].idxmax()]
    ax1.annotate(
        f"At {int(max_row['actual_prompt_tokens'])} tokens:\n"
        f"migration costs {max_row['prefill_mean']:.0f}ms",
        xy=(max_row["actual_prompt_tokens"], max_row["prefill_mean"]),
        xytext=(-80, -40), textcoords="offset points",
        arrowprops=dict(arrowstyle="->", color="gray"),
        fontsize=10, color="#d62728",
    )

    # Right: ms/token — shows efficiency plateau
    ax2.plot(grouped["actual_prompt_tokens"], grouped["ms_per_token_mean"],
             "s-", color="#2ca02c", linewidth=2, markersize=8)
    ax2.set_xlabel("Context Depth (tokens)", fontsize=12)
    ax2.set_ylabel("Marginal Cost (ms/token)", fontsize=12)
    ax2.set_title("Inertia Growth Rate\n"
                  "(decreasing = GPU reaches memory BW saturation at larger batch)", fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    path = os.path.join(output_dir, "context_inertia_curve.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  Saved: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-dir", type=str, default="logs",
                        help="Directory containing CSV log files")
    parser.add_argument("--output-dir", type=str, default="plots",
                        help="Directory to write plot PNGs")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print("Generating visualizations...\n")

    gpu_path = os.path.join(args.logs_dir, "gpu_metrics.csv")
    if os.path.exists(gpu_path):
        df = pd.read_csv(gpu_path)
        print(f"GPU metrics: {len(df)} samples")
        plot_gpu_metrics(df, args.output_dir)
    else:
        print(f"  Skipping GPU metrics (no {gpu_path})")

    session_path = os.path.join(args.logs_dir, "session_traces.csv")
    if os.path.exists(session_path):
        df = pd.read_csv(session_path)
        print(f"Session traces: {len(df)} records, {df['session_id'].nunique()} sessions")
        plot_session_traces(df, args.output_dir)
    else:
        print(f"  Skipping session traces (no {session_path})")

    prefill_path = os.path.join(args.logs_dir, "prefill_cost_curve.csv")
    if os.path.exists(prefill_path):
        df = pd.read_csv(prefill_path)
        print(f"Prefill measurements: {len(df)} data points")
        plot_prefill_cost_curve(df, args.output_dir)
    else:
        print(f"  Skipping prefill curve (no {prefill_path})")

    print(f"\nDone. Check {args.output_dir}/ for plots.")


if __name__ == "__main__":
    main()
