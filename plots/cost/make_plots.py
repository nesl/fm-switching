"""Generate plots for the comparable results gathered in this session."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
SIM = ROOT / "simulator" / "results"
OUT = Path(__file__).parent
OUT.mkdir(exist_ok=True)


def jload(p):
    return json.loads(Path(p).read_text())


# ── 1) exp1: load time & weight memory, FP16 vs INT4 ────────────────────
def plot_exp1():
    int4 = jload(RES / "exp1_prequant_all.json")["models"]
    fp16_files = {
        "smolvlm-256m":  RES / "exp1_fp16_smolvlm256.json",
        "smolvlm-500m":  RES / "exp1_fp16_smolvlm500.json",
        "qwen2.5-vl-3b": RES / "exp1_fp16_qwen_vl.json",
        "smollm2-1.7b":  RES / "exp1_fp16_smollm2.json",
    }
    fp16 = {}
    for k, p in fp16_files.items():
        if p.exists():
            fp16[k] = jload(p)["models"][k]

    models = [m for m in fp16_files if m in int4 and m in fp16]
    int4_mem = [int4[m]["summary"]["mean_memory_mb"] for m in models]
    fp16_mem = [fp16[m]["summary"]["mean_memory_mb"] for m in models]
    int4_load = [int4[m]["summary"]["min_load_s"] for m in models]
    fp16_load = [fp16[m]["summary"]["min_load_s"] for m in models]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(models))
    w = 0.38
    ax1.bar(x - w/2, fp16_mem, w, label="FP16", color="#3b82f6")
    ax1.bar(x + w/2, int4_mem, w, label="INT4", color="#ef4444")
    ax1.set_xticks(x); ax1.set_xticklabels(models, rotation=20, ha="right")
    ax1.set_ylabel("Weight memory (MB)")
    ax1.set_title("exp1: model weight memory")
    ax1.legend(); ax1.grid(axis="y", alpha=0.3)

    ax2.bar(x - w/2, fp16_load, w, label="FP16", color="#3b82f6")
    ax2.bar(x + w/2, int4_load, w, label="INT4", color="#ef4444")
    ax2.set_xticks(x); ax2.set_xticklabels(models, rotation=20, ha="right")
    ax2.set_ylabel("Min load time (s)")
    ax2.set_title("exp1: cold-start load time (min over trials)")
    ax2.legend(); ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("Jetson AGX Orin 64GB — Qwen2.5-VL-3B + SmolLM2-1.7B family")
    fig.tight_layout()
    fig.savefig(OUT / "exp1_loading.png", dpi=140)
    plt.close(fig)


# ── 2) exp2: per-cycle latency, FP16 vs INT4 ────────────────────────────
def plot_exp2():
    fp16 = jload(RES / "exp2_fp16_13gb.json")
    int4 = jload(RES / "exp2_int4_13gb.json")
    fig, ax = plt.subplots(figsize=(9, 5))
    for d, label, color in [(fp16, "FP16 (10.4 GB)", "#3b82f6"),
                              (int4, "INT4 (3.3 GB)", "#ef4444")]:
        cyc = d["cycles"]
        cycles = [c["cycle"] for c in cyc]
        vlm = [c["vlm_latency_s"] for c in cyc]
        llm = [c["llm_latency_s"] for c in cyc]
        ax.plot(cycles, vlm, "-o", color=color, label=f"{label} VLM")
        ax.plot(cycles, llm, "--s", color=color, alpha=0.6, label=f"{label} LLM")
    ax.set_xlabel("Cycle"); ax.set_ylabel("Latency (s)")
    ax.set_title("exp2: per-cycle pipeline latency (Qwen2.5-VL-3B + SmolLM2-1.7B, 13 GB cap)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "exp2_pipeline_latency.png", dpi=140)
    plt.close(fig)


# ── 3) exp5: context-inertia prefill cost ───────────────────────────────
def plot_exp5():
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, fpath, qname in [(axes[0], RES / "exp5_fp16_13gb.json", "FP16"),
                                (axes[1], RES / "exp5_int4_13gb.json", "INT4")]:
        if not fpath.exists():
            continue
        d = jload(fpath)
        for mode in ["stateless", "window-3", "window-10", "full"]:
            cyc = d["modes"][mode]["cycles"]
            x = [c["cycle"] for c in cyc]
            y = [c["prefill_ms"] for c in cyc]
            ax.plot(x, y, "-o", markersize=3, label=mode)
        ax.set_xlabel("Cycle"); ax.set_ylabel("LLM prefill (ms)")
        ax.set_title(f"exp5: prefill vs context mode ({qname})")
        ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "exp5_context_inertia.png", dpi=140)
    plt.close(fig)


# ── 4) quality comparison: latency across 6 cells ──────────────────────
def plot_quality():
    d = jload(RES / "quality_comparison.json")
    rows = d["results"]
    cells = ["smolvlm_256m_fp16", "smolvlm_256m_int4",
             "smolvlm_500m_fp16", "smolvlm_500m_int4",
             "qwen_vl_3b_fp16", "qwen_vl_3b_int4"]
    means = []
    stds = []
    for c in cells:
        lats = [r[c]["latency_s"] for r in rows if c in r]
        means.append(np.mean(lats)); stds.append(np.std(lats))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    colors = ["#3b82f6", "#ef4444"] * 3
    ax.bar(cells, means, yerr=stds, color=colors, alpha=0.85, capsize=4)
    ax.set_ylabel("Per-frame VLM latency (s, mean ± std over 10 frames)")
    ax.set_title("Quality-comparison VLMs: latency by model × quantization")
    ax.set_xticklabels(cells, rotation=20, ha="right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "quality_latency.png", dpi=140)
    plt.close(fig)


# ── 5) simulator: mean cycle latency heatmap (policy × scenario) ───────
def plot_sim_comparison():
    # Prefer the Track-1 output (Markov + LatencyHiding) if present; fall
    # back to the previous SSM comparison file.
    src = SIM / "comparison_lh_variants.json"
    if not src.exists():
        src = SIM / "comparison_track1.json"
    if not src.exists():
        src = SIM / "comparison_with_ssm.json"
    rows = jload(src)
    policies = []
    for r in rows:
        if r["policy"] not in policies:
            policies.append(r["policy"])
    workloads = ["steady", "variable", "burst"]
    networks  = ["stable", "degrading", "intermittent", "urban", "realistic",
                 "markov_campus", "markov_urban", "markov_indoor"]
    # Truncate to networks actually present in the data
    present_nets = {r["network"] for r in rows}
    networks = [n for n in networks if n in present_nets]

    def short(n):
        return n.replace("markov_", "mk-")[:8]
    scenarios = [f"{w[:3]}/{short(n)}" for w in workloads for n in networks]
    M = np.full((len(policies), len(scenarios)), np.nan)
    for r in rows:
        i = policies.index(r["policy"])
        scen = f"{r['workload'][:3]}/{short(r['network'])}"
        if scen not in scenarios:
            continue
        j = scenarios.index(scen)
        M[i, j] = r["mean_cycle_latency_s"]

    fig, ax = plt.subplots(figsize=(13, 0.55 * len(policies) + 2))
    im = ax.imshow(M, aspect="auto", cmap="viridis_r")
    ax.set_xticks(range(len(scenarios))); ax.set_xticklabels(scenarios, rotation=45, ha="right")
    ax.set_yticks(range(len(policies))); ax.set_yticklabels(policies)
    for i in range(len(policies)):
        for j in range(len(scenarios)):
            ax.text(j, i, f"{M[i,j]:.1f}", ha="center", va="center",
                     color="white" if M[i,j] > np.nanmean(M) else "black", fontsize=7)
    ax.set_title("Simulator: mean cycle latency (s), policy × (workload/network). Lower is better.")
    fig.colorbar(im, ax=ax, label="s/cycle")
    fig.tight_layout(); fig.savefig(OUT / "sim_comparison_heatmap.png", dpi=140)
    plt.close(fig)

    # Companion bar chart: mean across all scenarios per policy
    means = np.nanmean(M, axis=1)
    order = np.argsort(means)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh([policies[i] for i in order], [means[i] for i in order], color="#10b981")
    ax.set_xlabel("Mean cycle latency across 15 scenarios (s)")
    ax.set_title("Simulator: policy ranking (lower is better)")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "sim_policy_ranking.png", dpi=140)
    plt.close(fig)


# ── 6) sensitivity: memory cap sweep ───────────────────────────────────
def plot_sensitivity_memory():
    d = jload(SIM / "sensitivity_memory.json")
    rows = d["rows"]
    policies = sorted({r["policy"] for r in rows})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    for p in policies:
        sub = [r for r in rows if r["policy"] == p]
        sub.sort(key=lambda r: r["memory_cap_gb"])
        x = [r["memory_cap_gb"] for r in sub]
        ax1.plot(x, [r["mean_cycle_latency_s"] for r in sub], "-o", label=p)
        ax2.plot(x, [r["oom_events"] for r in sub], "-o", label=p)
    ax1.set_xlabel("Memory cap (GB)"); ax1.set_ylabel("Mean cycle latency (s)")
    ax1.set_title("Sensitivity: latency vs memory cap"); ax1.grid(alpha=0.3); ax1.legend(fontsize=8)
    ax2.set_xlabel("Memory cap (GB)"); ax2.set_ylabel("OOM events")
    ax2.set_title("Sensitivity: OOM events vs memory cap"); ax2.grid(alpha=0.3); ax2.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "sensitivity_memory.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    plot_exp1();             print("✓ exp1_loading.png")
    plot_exp2();             print("✓ exp2_pipeline_latency.png")
    plot_exp5();             print("✓ exp5_context_inertia.png")
    plot_quality();          print("✓ quality_latency.png")
    plot_sim_comparison();   print("✓ sim_comparison_heatmap.png + sim_policy_ranking.png")
    plot_sensitivity_memory(); print("✓ sensitivity_memory.png")
    print(f"\nAll plots written to {OUT}/")
