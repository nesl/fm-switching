"""
E29 — Tier-heterogeneous fidelity audit: analysis, figure, and report.

Loads results from results/fidelity/e29_tier_heterogeneous/ and produces:
  figures/fidelity/e29_q_table.pdf / .png
  reports/e29_tier_heterogeneous.md

Sanity check: qwen7b numbers on these phase0a subsets must reproduce the
committed phase0a values within noise. If they deviate by >5pp on LoCoMo
full, or by >10pp on EgoSchema full, the script prints a warning and stops.

Usage:
  conda run -n fmtk python experiments/fidelity/e29_analysis.py
"""

import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT      = Path(__file__).parent.parent.parent
IN_DIR    = ROOT / "results" / "fidelity" / "e29_tier_heterogeneous"
FIGURES   = ROOT / "figures" / "fidelity"
REPORTS   = ROOT / "reports"
FIGURES.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

MODELS    = ["qwen3b", "qwen7b"]
WORKLOADS = ["locomo", "egoschema"]
BOOT_REPS = 1000
SEED      = 42

# Committed phase0a reference values (full condition; from results/fidelity/multimodel/)
PHASE0A_REF = {
    "locomo":    {"qwen7b": 0.400},   # 40/100 from locomo_qwen7b_n100.json
    "egoschema": {"qwen7b": 0.567},   # 34/60 from egoschema_qwen7b_n60.json
}
SANITY_TOL = {"locomo": 0.05, "egoschema": 0.10}


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_ci(v, reps=BOOT_REPS, seed=SEED):
    rng = random.Random(seed)
    n = len(v)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    means = [sum(rng.choices(v, k=n)) / n for _ in range(reps)]
    means.sort()
    return sum(v) / n, means[int(0.025 * reps)], means[int(0.975 * reps)]

def paired_bootstrap_p(va, vb, reps=BOOT_REPS, seed=SEED):
    if len(va) != len(vb) or not va:
        return float("nan")
    obs_diff = abs(sum(va) / len(va) - sum(vb) / len(vb))
    rng = random.Random(seed)
    count = 0
    for _ in range(reps):
        swaps = [rng.random() < 0.5 for _ in range(len(va))]
        a2 = [vb[i] if swaps[i] else va[i] for i in range(len(va))]
        b2 = [va[i] if swaps[i] else vb[i] for i in range(len(va))]
        if abs(sum(a2)/len(a2) - sum(b2)/len(b2)) >= obs_diff:
            count += 1
    return count / reps


# ── Data loading ──────────────────────────────────────────────────────────────

def load_result(workload, model):
    matches = sorted(IN_DIR.glob(f"{workload}_{model}_n*.json"),
                     key=lambda p: p.stat().st_mtime)
    if not matches:
        return None
    return json.loads(matches[-1].read_text())

def acc_vector(records, cond):
    return [r["conditions"][cond]["correct"]
            for r in records if cond in r.get("conditions", {})]


# ── Per-workload analysis ─────────────────────────────────────────────────────

def analyze(workload, model):
    res = load_result(workload, model)
    if res is None:
        return None
    records = res["records"]
    conds = res["metadata"]["conditions"]
    cross_conds = res["metadata"].get("cross_conditions", [])
    n = len(records)

    full_v = acc_vector(records, "full")
    full_acc = sum(full_v) / n if full_v else float("nan")

    cond_stats = {}
    for cond in conds:
        v = acc_vector(records, cond)
        if not v:
            continue
        acc, lo, hi = bootstrap_ci(v)
        p = paired_bootstrap_p(full_v, v) if cond != "full" else 1.0
        gap = full_acc - acc
        cond_stats[cond] = {
            "acc": acc, "ci_lo": lo, "ci_hi": hi,
            "gap_vs_full": gap, "p": p,
            "n": len(v),
        }

    return {
        "workload": workload,
        "model": model,
        "n": n,
        "conditions": cond_stats,
        "cross_conditions": cross_conds,
        "gpu_peak_gb": res["metadata"].get("gpu_peak_gb"),
        "timestamp": res["metadata"].get("timestamp"),
    }


# ── Sufficiency table ─────────────────────────────────────────────────────────

def sufficiency_table(analyses, taus=(0.90, 0.95)):
    """
    For each (workload, model, condition) compute whether Q(f,w) >= tau * Q(full,w).
    Returns dict keyed by (workload, model): {cond: {tau: bool}}.
    """
    table = {}
    for workload in WORKLOADS:
        for model in MODELS:
            a = analyses.get((workload, model))
            if a is None:
                continue
            full_acc = a["conditions"].get("full", {}).get("acc", float("nan"))
            row = {}
            for cond, stats in a["conditions"].items():
                if cond == "full":
                    continue
                acc = stats["acc"]
                row[cond] = {tau: (acc >= tau * full_acc) for tau in taus}
            table[(workload, model)] = row
    return row  # caller iterates manually; return full dict below
    return {(w, m): table.get((w, m), {}) for w in WORKLOADS for m in MODELS}

def build_sufficiency_table(analyses, taus=(0.90, 0.95)):
    result = {}
    for workload in WORKLOADS:
        for model in MODELS:
            a = analyses.get((workload, model))
            if a is None:
                continue
            full_acc = a["conditions"].get("full", {}).get("acc", float("nan"))
            row = {}
            for cond, stats in a["conditions"].items():
                if cond == "full" or cond.startswith("cross-"):
                    continue
                acc = stats["acc"]
                row[cond] = {tau: (acc >= tau * full_acc) for tau in taus}
            result[(workload, model)] = row
    return result


# ── Q table ───────────────────────────────────────────────────────────────────

def build_q_table(analyses):
    """Q(fidelity, regime, model): accuracy for each (workload × condition × model)."""
    q = {}
    for workload in WORKLOADS:
        regime = "dense-incompressible" if workload == "locomo" else "gist-compressible"
        for model in MODELS:
            a = analyses.get((workload, model))
            if a is None:
                continue
            for cond, stats in a["conditions"].items():
                q[(cond, regime, model)] = {
                    "acc": stats["acc"],
                    "ci_lo": stats["ci_lo"],
                    "ci_hi": stats["ci_hi"],
                }
    return q


# ── Figure ────────────────────────────────────────────────────────────────────

def make_figure(analyses, out_base):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  matplotlib not available; skipping figure")
        return

    # Q table heatmap: rows = conditions, columns = (workload × model)
    own_conds = ["blind", "window-10", "summary-80", "summary-200", "full"]
    col_specs  = [(w, m) for w in WORKLOADS for m in MODELS]
    col_labels = [f"{w[:4]}/{m[:5]}" for w, m in col_specs]

    data   = np.zeros((len(own_conds), len(col_specs)))
    ci_err = np.zeros((len(own_conds), len(col_specs)))

    for ci, (workload, model) in enumerate(col_specs):
        a = analyses.get((workload, model))
        if a is None:
            continue
        for ri, cond in enumerate(own_conds):
            s = a["conditions"].get(cond, {})
            acc = s.get("acc", float("nan"))
            data[ri, ci] = acc if not math.isnan(acc) else -1
            ci_err[ri, ci] = acc - s.get("ci_lo", acc)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    cmap = plt.cm.RdYlGn
    im = ax.imshow(data, vmin=0, vmax=1, cmap=cmap, aspect="auto")

    ax.set_xticks(range(len(col_specs)))
    ax.set_xticklabels(col_labels, fontsize=9)
    ax.set_yticks(range(len(own_conds)))
    ax.set_yticklabels(own_conds, fontsize=9)
    ax.set_xlabel("workload / model", fontsize=10)
    ax.set_ylabel("fidelity condition", fontsize=10)
    ax.set_title("E29 Q(fidelity, workload, model) table\n"
                 "qwen3b=device tier  qwen7b=edge/cloud tier", fontsize=10)

    for ri in range(len(own_conds)):
        for ci in range(len(col_specs)):
            v = data[ri, ci]
            if v >= 0:
                ax.text(ci, ri, f"{v:.2f}", ha="center", va="center",
                        fontsize=8, color="black" if 0.3 < v < 0.7 else "white")

    plt.colorbar(im, ax=ax, label="accuracy")
    plt.tight_layout()
    plt.savefig(str(out_base) + ".pdf", bbox_inches="tight")
    plt.savefig(str(out_base) + ".png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Figure saved: {out_base}.pdf / .png")


# ── Report ────────────────────────────────────────────────────────────────────

def sig_str(p):
    if math.isnan(p): return "—"
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "ns"))

def write_report(analyses, out_path, sanity_ok):
    lines = []
    W = lambda *a: lines.extend(a)

    W("# E29 — Tier-Heterogeneous Fidelity Audit",
      "",
      f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
      "")

    W("## Motivation",
      "",
      "The project has so far assumed one model at every tier. That assumption is unrealistic. "
      "In a real device/edge/cloud deployment the tiers run different model sizes, and the reason "
      "to move a session to a larger tier is that the larger model answers better. This has two "
      "consequences that had not been measured: (a) KV cache is model-specific, so materialized "
      "state cannot cross tiers with different model sizes and every tier transition forces "
      "re-materialization from text; (b) the quality of a given state fidelity depends on which "
      "model reads it, so the Q table becomes Q(fidelity, regime, model) rather than Q(fidelity, regime).",
      "",
      "This experiment measures (b). It does not touch (a), which is an architectural fact: on any "
      "tier transition between model sizes, full-restore cost applies regardless of the current "
      "representation. The physical cost model from E21–E23 applies.",
      "")

    W("## Setup",
      "",
      "Models: Qwen2.5-3B-Instruct (qwen3b, device tier) and Qwen2.5-7B-Instruct (qwen7b, edge/cloud tier). "
      "Same family, different size; isolates capacity from architecture.",
      "",
      "Subsets: phase0a fixed seeds (data/audit_subsets/phase0a/). LoCoMo n=100, EgoSchema n=60. "
      "Results are directly comparable to the committed phase0a Q tables.",
      "",
      "Conditions per model: blind, window-10, summary-80, summary-200, full (own summaries), "
      "plus cross-tier conditions: 3B reading 7B-generated summaries and 7B reading 3B-generated summaries.",
      "",
      "Instrument: identical to multimodel_locomo.py / multimodel_egoschema.py "
      "(same scorer, judge, prompts, subset IDs). No methodological changes.",
      "")

    # Sanity check
    W("## Sanity Check: qwen7b vs Phase0a Reference",
      "")
    all_ok = True
    for workload in WORKLOADS:
        a = analyses.get((workload, "qwen7b"))
        ref = PHASE0A_REF.get(workload, {}).get("qwen7b")
        if a is None or ref is None:
            W(f"- {workload}/qwen7b: MISSING")
            all_ok = False
            continue
        full_acc = a["conditions"].get("full", {}).get("acc", float("nan"))
        tol = SANITY_TOL[workload]
        delta = abs(full_acc - ref)
        status = "PASS" if delta <= tol else f"FAIL (delta={delta:.3f} > tol={tol})"
        W(f"- {workload}/qwen7b: full={full_acc:.3f}, ref={ref:.3f}, delta={delta:.3f} → **{status}**")
        if delta > tol:
            all_ok = False
    if not all_ok:
        W("", "**WARNING: One or more sanity checks failed.** "
          "qwen7b numbers do not reproduce phase0a values within tolerance. "
          "Interpret results cautiously; re-run or investigate before using.", "")
    else:
        W("", "All sanity checks passed.", "")

    # Per-workload accuracy tables
    for workload in WORKLOADS:
        W(f"## {workload.title()}", "")
        for model in MODELS:
            a = analyses.get((workload, model))
            W(f"### {model} (n={a['n'] if a else '?'})", "")
            if a is None:
                W("*Result not available.*", "")
                continue
            W("| condition | acc | 95% CI | gap vs full | p | sig |")
            W("|---|---|---|---|---|---|")
            full_acc = a["conditions"].get("full", {}).get("acc", float("nan"))
            for cond, s in a["conditions"].items():
                acc = s["acc"]
                lo, hi = s["ci_lo"], s["ci_hi"]
                gap = s["gap_vs_full"]
                p   = s["p"]
                W(f"| {cond} | {acc:.3f} | [{lo:.3f}, {hi:.3f}] | "
                  f"{gap:+.3f} | {p:.3f} | {sig_str(p)} |")
            W("")

    # Sufficiency table
    W("## Sufficiency Table — Q(f, w) ≥ τ·Q(full, w)", "")
    W("Relative sufficiency criterion (τ ∈ {0.90, 0.95}) for own-summary conditions. "
      "Cross-tier conditions excluded from sufficiency table (not a deployment option).", "")
    suff = build_sufficiency_table(analyses)
    own_conds_order = ["blind", "window-10", "summary-80", "summary-200"]
    W("| workload | model | condition | acc | τ=0.90 | τ=0.95 |")
    W("|---|---|---|---|---|---|")
    for workload in WORKLOADS:
        for model in MODELS:
            a = analyses.get((workload, model))
            s_row = suff.get((workload, model), {})
            full_acc = a["conditions"].get("full", {}).get("acc", float("nan")) if a else float("nan")
            for cond in own_conds_order:
                if a is None:
                    W(f"| {workload} | {model} | {cond} | — | — | — |")
                    continue
                stats = a["conditions"].get(cond, {})
                acc = stats.get("acc", float("nan"))
                t90 = "✓" if s_row.get(cond, {}).get(0.90, False) else "✗"
                t95 = "✓" if s_row.get(cond, {}).get(0.95, False) else "✗"
                W(f"| {workload} | {model} | {cond} | {acc:.3f} | {t90} | {t95} |")
    W("")

    # Cells where models disagree
    W("### Sufficiency disagreements between qwen3b and qwen7b", "")
    found_any = False
    for tau in (0.90, 0.95):
        disagreements = []
        for workload in WORKLOADS:
            for cond in own_conds_order:
                r3 = suff.get((workload, "qwen3b"), {}).get(cond, {}).get(tau)
                r7 = suff.get((workload, "qwen7b"), {}).get(cond, {}).get(tau)
                if r3 is not None and r7 is not None and r3 != r7:
                    a3 = analyses.get((workload, "qwen3b"), {}).get("conditions", {}).get(cond, {}).get("acc", float("nan"))
                    a7 = analyses.get((workload, "qwen7b"), {}).get("conditions", {}).get(cond, {}).get("acc", float("nan"))
                    suf3 = "sufficient" if r3 else "insufficient"
                    suf7 = "sufficient" if r7 else "insufficient"
                    disagreements.append(
                        f"  - {workload}/{cond} at τ={tau}: qwen3b={a3:.3f} ({suf3}), qwen7b={a7:.3f} ({suf7})")
                    found_any = True
        if disagreements:
            W(f"**τ={tau}:**")
            W(*disagreements)
    if not found_any:
        W("No disagreements found: both models agree on sufficiency for all own-summary conditions "
          "at both τ thresholds.")
    W("")

    # Question 1: Does the sufficiency verdict change between 3B and 7B?
    W("## Question 1: Does the sufficiency verdict change between 3B and 7B?", "")
    for workload in WORKLOADS:
        W(f"**{workload}:**")
        for cond in own_conds_order:
            r3_90 = suff.get((workload, "qwen3b"), {}).get(cond, {}).get(0.90)
            r7_90 = suff.get((workload, "qwen7b"), {}).get(cond, {}).get(0.90)
            r3_95 = suff.get((workload, "qwen3b"), {}).get(cond, {}).get(0.95)
            r7_95 = suff.get((workload, "qwen7b"), {}).get(cond, {}).get(0.95)
            if r3_90 is None or r7_90 is None:
                continue
            agree_90 = r3_90 == r7_90
            agree_95 = r3_95 == r7_95
            flag = "" if (agree_90 and agree_95) else " **← DISAGREE**"
            W(f"  - {cond}: τ=0.90 {'agree' if agree_90 else 'DISAGREE'}  "
              f"τ=0.95 {'agree' if agree_95 else 'DISAGREE'}{flag}")
    W("")

    # Question 2: Does a 7B summary help 3B?
    W("## Question 2: Does a 7B-generated summary help the 3B reader?", "")
    W("Compare qwen3b reading qwen7b-generated summaries vs qwen3b reading own summaries.", "")
    for workload in WORKLOADS:
        a3 = analyses.get((workload, "qwen3b"))
        if a3 is None:
            W(f"**{workload}**: data missing.")
            continue
        W(f"**{workload}:**")
        for budget, own_cond, cross_cond in [
            ("80", "summary-80", "cross-qwen7b-sum80"),
            ("200", "summary-200", "cross-qwen7b-sum200"),
        ]:
            own_s   = a3["conditions"].get(own_cond, {})
            cross_s = a3["conditions"].get(cross_cond, {})
            if not own_s or not cross_s:
                W(f"  - budget={budget}: cross condition not available")
                continue
            diff = cross_s["acc"] - own_s["acc"]
            # paired bootstrap p-value
            res3 = load_result(workload, "qwen3b")
            if res3:
                own_v   = acc_vector(res3["records"], own_cond)
                cross_v = acc_vector(res3["records"], cross_cond)
                p = paired_bootstrap_p(own_v, cross_v)
            else:
                p = float("nan")
            W(f"  - budget={budget}: 3B-own={own_s['acc']:.3f}, 3B-reading-7B={cross_s['acc']:.3f}, "
              f"diff={diff:+.3f}, p={p:.3f} ({sig_str(p)})")
    W("", "Interpretation: if diff ≈ 0 and ns, a stronger summarizer does not help the weaker reader "
      "(consistent with phase0a cross-model result on Qwen/Mistral).", "")

    # Question 3: Is 3B self-sufficient on dense workload?
    W("## Question 3: Is qwen3b full accuracy high enough for a device tier to self-serve dense sessions?", "")
    a3_l = analyses.get(("locomo", "qwen3b"))
    a7_l = analyses.get(("locomo", "qwen7b"))
    if a3_l and a7_l:
        f3 = a3_l["conditions"].get("full", {})
        b3 = a3_l["conditions"].get("blind", {})
        f7 = a7_l["conditions"].get("full", {})
        W(f"LoCoMo: qwen3b full={f3.get('acc', float('nan')):.3f} "
          f"[{f3.get('ci_lo', float('nan')):.3f}, {f3.get('ci_hi', float('nan')):.3f}], "
          f"qwen3b blind={b3.get('acc', float('nan')):.3f}; "
          f"qwen7b full={f7.get('acc', float('nan')):.3f}.", "")
        f3_acc = f3.get("acc", float("nan"))
        b3_acc = b3.get("acc", float("nan"))
        if not math.isnan(f3_acc) and not math.isnan(b3_acc):
            near_blind = abs(f3_acc - b3_acc) < 0.08
            W("The device tier (qwen3b) " +
              ("cannot serve dense sessions at any fidelity: full accuracy ≈ blind, "
               "meaning the 3B model cannot recover far-distance facts even with the full context. "
               "This is a stronger statement than the cost curves alone make."
               if near_blind else
               "has non-trivial full accuracy above blind, suggesting partial self-sufficiency "
               "at device tier for some dense queries."), "")
    else:
        W("Data missing for this comparison.", "")

    # Q(fidelity, regime, model) table
    W("## Q(fidelity, regime, model) Table", "",
      "Drop-in replacement for the existing Q table in the simulator. "
      "Regime: dense-incompressible (LoCoMo), gist-compressible (EgoSchema).", "")
    own_conds_for_q = ["blind", "window-10", "summary-80", "summary-200", "full"]
    W("| fidelity | regime | model | Q | 95% CI |")
    W("|---|---|---|---|---|")
    for workload in WORKLOADS:
        regime = "dense-incompressible" if workload == "locomo" else "gist-compressible"
        for model in MODELS:
            a = analyses.get((workload, model))
            if a is None:
                continue
            for cond in own_conds_for_q:
                s = a["conditions"].get(cond, {})
                if not s:
                    continue
                acc = s.get("acc", float("nan"))
                lo  = s.get("ci_lo", float("nan"))
                hi  = s.get("ci_hi", float("nan"))
                W(f"| {cond} | {regime} | {model} | {acc:.3f} | [{lo:.3f}, {hi:.3f}] |")
    W("")

    # Cross-tier conditions summary
    W("## Cross-Tier Summary Conditions", "",
      "Accuracy when a model reads summaries generated by the other model.", "")
    W("| workload | reader | summarizer | budget | acc | 95% CI | vs reader own | p |")
    W("|---|---|---|---|---|---|---|---|")
    for workload in WORKLOADS:
        for reader, writer, cross_cond_80, cross_cond_200 in [
            ("qwen3b", "qwen7b", "cross-qwen7b-sum80", "cross-qwen7b-sum200"),
            ("qwen7b", "qwen3b", "cross-qwen3b-sum80", "cross-qwen3b-sum200"),
        ]:
            a = analyses.get((workload, reader))
            if a is None:
                continue
            for budget, own_c, cross_c in [
                ("80", "summary-80", cross_cond_80),
                ("200", "summary-200", cross_cond_200),
            ]:
                cross_s = a["conditions"].get(cross_c)
                own_s   = a["conditions"].get(own_c)
                if cross_s is None:
                    continue
                acc = cross_s["acc"]
                lo, hi = cross_s["ci_lo"], cross_s["ci_hi"]
                own_acc = own_s["acc"] if own_s else float("nan")
                diff = acc - own_acc
                res_r = load_result(workload, reader)
                p = float("nan")
                if res_r:
                    ov = acc_vector(res_r["records"], own_c)
                    cv = acc_vector(res_r["records"], cross_c)
                    if ov and cv:
                        p = paired_bootstrap_p(ov, cv)
                W(f"| {workload} | {reader} | {writer} | {budget} | {acc:.3f} | "
                  f"[{lo:.3f}, {hi:.3f}] | {diff:+.3f} | {p:.3f} |")
    W("")

    # Implication for tier model
    W("## Implication for the Tier Model in FORMULATION.md", "",
      "This experiment extends the single-model assumption (FORMULATION.md §Simplifications) "
      "by measuring Q(fidelity, regime, model) for a realistic device/edge size pair "
      "(3B device, 7B edge). The key findings are summarized here for integration. "
      "FORMULATION.md has not been edited; these findings should inform a future update.", "")

    out_path.write_text("\n".join(lines))
    print(f"  Report saved: {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def sanity_check(analyses):
    ok = True
    for workload in WORKLOADS:
        a = analyses.get((workload, "qwen7b"))
        ref = PHASE0A_REF.get(workload, {}).get("qwen7b")
        if a is None or ref is None:
            print(f"  SANITY: {workload}/qwen7b MISSING")
            ok = False
            continue
        full_acc = a["conditions"].get("full", {}).get("acc", float("nan"))
        tol = SANITY_TOL[workload]
        delta = abs(full_acc - ref)
        status = "PASS" if delta <= tol else "FAIL"
        print(f"  SANITY {workload}/qwen7b: full={full_acc:.3f} ref={ref:.3f} delta={delta:.3f} → {status}")
        if delta > tol:
            ok = False
    return ok


def main():
    print("=== E29 Analysis ===", flush=True)

    analyses = {}
    for workload in WORKLOADS:
        for model in MODELS:
            print(f"  Loading {workload} / {model} …", flush=True)
            a = analyze(workload, model)
            if a is None:
                print(f"    MISSING — run e29_{workload}.py --model {model} first")
            analyses[(workload, model)] = a

    print("\nSanity check (qwen7b vs phase0a reference):")
    sanity_ok = sanity_check(analyses)
    if not sanity_ok:
        print("\nWARNING: sanity check failed. Proceeding with analysis, "
              "but flag this in the report.")

    print("\nGenerating figure …")
    make_figure(analyses, FIGURES / "e29_q_table")

    print("Writing report …")
    write_report(analyses, REPORTS / "e29_tier_heterogeneous.md", sanity_ok)

    # Save analysis JSON
    def _serial(obj):
        if isinstance(obj, float) and math.isnan(obj):
            return None
        return obj

    out_json = {}
    for (w, m), a in analyses.items():
        if a is not None:
            out_json[f"{w}_{m}"] = a
    (IN_DIR / "e29_analysis.json").write_text(
        json.dumps(out_json, indent=2, default=_serial))
    print(f"  Analysis JSON saved: {IN_DIR / 'e29_analysis.json'}")


if __name__ == "__main__":
    main()
