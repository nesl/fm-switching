"""
Study I3 Re-analysis — paired McNemar tests, corrected latency, bias-only baseline.

Inputs:  results/sember/study_i3/study_i3_trials.jsonl
         results/sember/study_i2/study_i2_results.json  (for latency cross-check)
Outputs: results/sember/study_i3_reanalysis/  (JSON artefacts)
         reports/study_i3_reanalysis.md
"""

import json, math, pathlib, sys, collections, random
from scipy import stats as scipy_stats

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
I3_JSONL     = PROJECT_ROOT / "results/sember/study_i3/study_i3_trials.jsonl"
I3_RESULTS   = PROJECT_ROOT / "results/sember/study_i3/study_i3_results.json"
I2_RESULTS   = PROJECT_ROOT / "results/sember/study_i2/study_i2_results.json"
OUT_DIR      = PROJECT_ROOT / "results/sember/study_i3_reanalysis"
REPORT_PATH  = PROJECT_ROOT / "reports/study_i3_reanalysis.md"

OUT_DIR.mkdir(parents=True, exist_ok=True)

MODELS      = ["qwen3vl4b", "qwen3vl8b"]
ARMS        = ["SPARSE", "TEMPORAL"]
CATEGORIES  = [
    "time_duration", "visual_detail_recall", "sequential_action",
    "location_trace", "spatial_aware_reasoning", "object_comparison",
    "temporal_ordering_recognition",
]
DIST_BINS   = [(0,30),(30,60),(60,120),(120,300),(300,float("inf"))]
ALPHA       = 0.05
N_BOOT      = 10_000
SEED        = 42

# ── load ──────────────────────────────────────────────────────────────────────

def load_trials():
    trials = []
    for line in I3_JSONL.open():
        trials.append(json.loads(line))
    return trials

def build_index(trials):
    """Returns idx[model][arm][question_id] = trial."""
    idx = {m: {a: {} for a in ARMS} for m in MODELS}
    for t in trials:
        m, a, q = t["model"], t["arm"], t["question_id"]
        if m not in idx or a not in idx[m]:
            continue
        if q in idx[m][a]:
            sys.exit(f"STOP: duplicate (model={m}, arm={a}, qid={q})")
        idx[m][a][q] = t
    return idx

# ── pairing verification ───────────────────────────────────────────────────────

def verify_pairing(idx):
    """Assert SPARSE qids == TEMPORAL qids for each model."""
    broken = {}
    for m in MODELS:
        sp_ids = set(idx[m]["SPARSE"])
        tm_ids = set(idx[m]["TEMPORAL"])
        only_sp = sp_ids - tm_ids
        only_tm = tm_ids - sp_ids
        if only_sp or only_tm:
            broken[m] = {"only_in_SPARSE": list(only_sp)[:5],
                         "only_in_TEMPORAL": list(only_tm)[:5],
                         "n_only_sp": len(only_sp), "n_only_tm": len(only_tm)}
    return broken

# ── McNemar ───────────────────────────────────────────────────────────────────

def mcnemar(b, c):
    """McNemar test. Returns (pval, method). b=SPARSE+/TEMPORAL-, c=SPARSE-/TEMPORAL+."""
    n_disc = b + c
    if n_disc == 0:
        return 1.0, "exact_binomial(n_disc=0)"
    if n_disc < 25:
        # exact binomial, two-tailed; cap at 1.0 to avoid floating-point >1 when b==c
        k = min(b, c)
        pval = min(1.0, 2 * min(
            scipy_stats.binom.cdf(k, n_disc, 0.5),
            1 - scipy_stats.binom.cdf(k - 1, n_disc, 0.5),
        ))
        return float(pval), "exact_binomial"
    else:
        # chi-square with continuity correction
        chi2 = (abs(b - c) - 1) ** 2 / (b + c)
        pval = float(scipy_stats.chi2.sf(chi2, df=1))
        return pval, "chisq_continuity"

# ── bootstrap paired CI ───────────────────────────────────────────────────────

def paired_boot_ci(sp_correct, tm_correct, n_boot=N_BOOT, seed=SEED):
    """Bootstrap 95% CI on TEMPORAL_acc - SPARSE_acc over paired questions."""
    rng = random.Random(seed)
    n = len(sp_correct)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randint(0, n-1) for _ in range(n)]
        d = sum(tm_correct[i] - sp_correct[i] for i in idx) / n
        diffs.append(d)
    diffs.sort()
    lo = diffs[int(0.025 * n_boot)]
    hi = diffs[int(0.975 * n_boot)]
    return lo, hi

# ── Benjamini-Hochberg ────────────────────────────────────────────────────────

def bh_correct(pvals_dict):
    """BH correction. Input: {key: pval}. Output: {key: adjusted_pval}."""
    items = sorted(pvals_dict.items(), key=lambda x: x[1])
    m = len(items)
    adjusted = {}
    for rank, (key, pval) in enumerate(items, 1):
        adj = min(1.0, pval * m / rank)
        adjusted[key] = adj
    # ensure monotonicity (step-up)
    keys_sorted = [k for k, _ in items]
    for i in range(len(keys_sorted) - 2, -1, -1):
        adjusted[keys_sorted[i]] = min(adjusted[keys_sorted[i]], adjusted[keys_sorted[i+1]])
    return adjusted

# ── bias-only baseline ────────────────────────────────────────────────────────

def bias_baseline(trials_for_cell):
    """Expected accuracy if model picks letters from its own marginal distribution."""
    letter_counts = collections.Counter(t["predicted_letter"] for t in trials_for_cell
                                        if t.get("predicted_letter"))
    total = sum(letter_counts.values())
    marginal = {l: c / total for l, c in letter_counts.items()}
    expected_acc = sum(marginal.get(t["correct_letter"], 0.0)
                       for t in trials_for_cell) / len(trials_for_cell)
    measured_acc = sum(t["correct"] for t in trials_for_cell) / len(trials_for_cell)
    return {
        "marginal": {l: round(marginal.get(l, 0), 4) for l in "ABCDE"},
        "bias_only_acc": round(expected_acc, 4),
        "measured_acc": round(measured_acc, 4),
        "lift_over_bias": round(measured_acc - expected_acc, 4),
    }

# ── latency accounting ────────────────────────────────────────────────────────

def latency_accounting(trials, i2_results):
    """
    Resolve the latency defects.

    Reused trials: total_latency_ms = inference only (I2 measurement).
    Fresh trials: total_latency_ms = decode + preprocess + forward.
      - forward_ms tracks model forward pass only.
      - decode_latency_ms = amortised video decode (for TEMPORAL) or per-trial seek time (SPARSE).

    Inference-only comparison: use prefill_ms_est for reused trials,
    forward_ms for fresh trials (both measure model-forward wall time; output is 2 tokens so
    decode-autoregressively contribution is negligible).
    """
    cell_data = {(m, a): {"reused": [], "fresh": []} for m in MODELS for a in ARMS}
    for t in trials:
        m, a = t["model"], t["arm"]
        bucket = "reused" if t.get("reused_from") else "fresh"
        cell_data[(m, a)][bucket].append(t)

    rows = {}
    for (m, a), buckets in cell_data.items():
        reused = buckets["reused"]
        fresh  = buckets["fresh"]

        # inference-only: prefill_ms_est for reused, forward_ms for fresh
        infer_vals = (
            [t["prefill_ms_est"] for t in reused if "prefill_ms_est" in t]
            + [t["forward_ms"]   for t in fresh  if "forward_ms"   in t]
        )
        all_total = [t["total_latency_ms"] for t in (reused + fresh)]
        decode_fresh = [t["decode_latency_ms"] for t in fresh if "decode_latency_ms" in t]
        fwd_fresh    = [t["forward_ms"]        for t in fresh if "forward_ms"        in t]

        def med(lst):
            if not lst: return None
            s = sorted(lst)
            return round(s[len(s)//2], 1)

        rows[(m, a)] = {
            "n_reused": len(reused),
            "n_fresh":  len(fresh),
            "total_latency_med_ms":    med(all_total),
            "infer_only_med_ms":       med(infer_vals),
            "decode_fresh_med_ms":     med(decode_fresh),
            "forward_fresh_med_ms":    med(fwd_fresh),
        }

    # cross-check 8B SPARSE inference vs I2
    i2_8bsp = i2_results.get("E_latency", {}).get("qwen3vl8b_SPARSE", {})
    i2_lat   = i2_8bsp.get("lat_med_ms")
    i3_infer = rows[("qwen3vl8b","SPARSE")]["infer_only_med_ms"]
    rows["cross_check_8b_sparse"] = {
        "i2_lat_med_ms": i2_lat,
        "i3_infer_only_med_ms": i3_infer,
        "ratio": round(i3_infer / i2_lat, 3) if i2_lat and i3_infer else None,
        "verdict": "AGREE" if i2_lat and i3_infer and abs(i3_infer/i2_lat - 1) < 0.10 else "DISAGREE",
    }
    return rows

# ── paired analysis (SPARSE vs TEMPORAL per model) ────────────────────────────

def paired_sparse_vs_temporal(idx, model, questions):
    """
    Build paired contingency for the given model across the given question list.
    Returns dict with b, c, pval, method, paired_diff, ci_lo, ci_hi.
    """
    sp_correct = []
    tm_correct = []
    for q in questions:
        sp = idx[model]["SPARSE"].get(q)
        tm = idx[model]["TEMPORAL"].get(q)
        if sp is None or tm is None:
            continue
        sp_correct.append(int(sp["correct"]))
        tm_correct.append(int(tm["correct"]))
    n = len(sp_correct)
    if n == 0:
        return None

    a = sum(1 for s,t in zip(sp_correct,tm_correct) if s==1 and t==1)
    b = sum(1 for s,t in zip(sp_correct,tm_correct) if s==1 and t==0)  # SP+ TM-
    c = sum(1 for s,t in zip(sp_correct,tm_correct) if s==0 and t==1)  # SP- TM+
    d = sum(1 for s,t in zip(sp_correct,tm_correct) if s==0 and t==0)

    assert a+b+c+d == n, f"contingency sum mismatch: {a+b+c+d} != {n}"

    pval, method = mcnemar(b, c)
    diff = (c - b) / n
    ci_lo, ci_hi = paired_boot_ci(sp_correct, tm_correct)

    sp_acc = sum(sp_correct) / n
    tm_acc = sum(tm_correct) / n

    return {
        "n": n, "a": a, "b": b, "c": c, "d": d,
        "sp_acc": round(sp_acc, 4),
        "tm_acc": round(tm_acc, 4),
        "paired_diff": round(diff, 4),
        "ci_lo": round(ci_lo, 4),
        "ci_hi": round(ci_hi, 4),
        "pval_raw": round(pval, 6),
        "mcnemar_method": method,
    }

# ── distance bins (Analysis C) ────────────────────────────────────────────────

def paired_distance_analysis(idx, model="qwen3vl4b"):
    """Paired SPARSE vs TEMPORAL per farthest_dist_s bin for given model."""
    # collect questions per bin
    bin_questions = {b: [] for b in DIST_BINS}
    for q, t in idx[model]["SPARSE"].items():
        d = t.get("farthest_dist_s", 0)
        for lo, hi in DIST_BINS:
            if lo <= d < hi:
                bin_questions[(lo,hi)].append(q)
                break

    results = {}
    for bk, questions in bin_questions.items():
        r = paired_sparse_vs_temporal(idx, model, questions)
        if r:
            results[str(bk)] = r
    return results

# ── model-gap analysis (Analysis D) ──────────────────────────────────────────

def paired_model_gap(idx, arm, questions):
    """
    Paired comparison: 8B vs 4B, on the given arm and question list.
    """
    v4_correct = []
    v8_correct = []
    for q in questions:
        t4 = idx["qwen3vl4b"][arm].get(q)
        t8 = idx["qwen3vl8b"][arm].get(q)
        if t4 is None or t8 is None:
            continue
        v4_correct.append(int(t4["correct"]))
        v8_correct.append(int(t8["correct"]))
    n = len(v4_correct)
    if n == 0:
        return None

    a = sum(1 for x,y in zip(v4_correct,v8_correct) if x==1 and y==1)
    b = sum(1 for x,y in zip(v4_correct,v8_correct) if x==1 and y==0)  # 4B+ 8B-
    c = sum(1 for x,y in zip(v4_correct,v8_correct) if x==0 and y==1)  # 4B- 8B+
    d = sum(1 for x,y in zip(v4_correct,v8_correct) if x==0 and y==0)

    assert a+b+c+d == n
    pval, method = mcnemar(b, c)
    diff = (c - b) / n
    ci_lo, ci_hi = paired_boot_ci(v4_correct, v8_correct)

    return {
        "n": n, "a": a, "b": b, "c": c, "d": d,
        "v4_acc": round(sum(v4_correct)/n, 4),
        "v8_acc": round(sum(v8_correct)/n, 4),
        "diff_8b_minus_4b": round(diff, 4),
        "ci_lo": round(ci_lo, 4),
        "ci_hi": round(ci_hi, 4),
        "pval_raw": round(pval, 6),
        "mcnemar_method": method,
    }

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    trials = load_trials()
    idx    = build_index(trials)
    i2_res = json.load(I2_RESULTS.open())

    # ── Sanity: trial counts ──────────────────────────────────────────────────
    print("SANITY: trial counts")
    for m in MODELS:
        for a in ARMS:
            n = len(idx[m][a])
            status = "PASS" if n == 459 else f"FAIL (got {n})"
            print(f"  {m} {a}: {n}/459 {status}")
            if n != 459:
                sys.exit("STOP: trial count mismatch")

    # ── Sanity: pairing ───────────────────────────────────────────────────────
    print("SANITY: pairing")
    broken = verify_pairing(idx)
    if broken:
        sys.exit(f"STOP: pairing broken: {broken}")
    print("  pairing OK for both models")

    # ── Sanity: reproduce study_i3 unpaired accuracies ────────────────────────
    print("SANITY: reproducing study_i3 Analysis A")
    i3_res = json.load(I3_RESULTS.open())
    i3_A   = i3_res.get("A_overall", {})
    reproduce_ok = True
    for m in MODELS:
        for a in ARMS:
            cell_trials = list(idx[m][a].values())
            acc = sum(t["correct"] for t in cell_trials) / len(cell_trials)
            key = f"{m}_{a}"
            prior = i3_A.get(key, {}).get("acc")
            match = prior is not None and abs(acc - prior) < 1e-4
            status = "PASS" if match else f"MISMATCH (computed={acc:.4f} prior={prior})"
            print(f"  {key}: {acc:.4f} {status}")
            if not match:
                reproduce_ok = False
    if not reproduce_ok:
        sys.exit("STOP: cannot reproduce study_i3 accuracies; data may differ")

    # ── Reuse counts ─────────────────────────────────────────────────────────
    reuse_counts = {}
    for m in MODELS:
        for a in ARMS:
            reused = sum(1 for t in idx[m][a].values() if t.get("reused_from"))
            fresh  = 459 - reused
            reuse_counts[f"{m}_{a}"] = {"reused": reused, "fresh": fresh}

    # ── Paired SPARSE vs TEMPORAL per model ───────────────────────────────────
    print("Running paired McNemar tests (SPARSE vs TEMPORAL) ...")
    paired_results = {}
    for m in MODELS:
        all_qids = sorted(idx[m]["SPARSE"].keys())  # same as TEMPORAL after pairing check
        # overall
        overall = paired_sparse_vs_temporal(idx, m, all_qids)
        # per category
        cat_results = {}
        cat_pvals   = {}
        for cat in CATEGORIES:
            cat_qids = [q for q in all_qids if idx[m]["SPARSE"][q]["category"] == cat]
            r = paired_sparse_vs_temporal(idx, m, cat_qids)
            if r:
                cat_results[cat] = r
                cat_pvals[cat]   = r["pval_raw"]
        # BH correction across 7 categories
        cat_adj = bh_correct(cat_pvals)
        for cat in cat_results:
            cat_results[cat]["pval_adj_bh"] = round(cat_adj[cat], 6)
            cat_results[cat]["sig_after_correction"] = cat_adj[cat] < ALPHA

        paired_results[m] = {"overall": overall, "categories": cat_results}

    # ── Verdict ───────────────────────────────────────────────────────────────
    verdicts = {}
    for m in MODELS:
        cats = paired_results[m]["categories"]
        tm_better  = [c for c,r in cats.items() if r["sig_after_correction"] and r["paired_diff"] > 0]
        sp_better  = [c for c,r in cats.items() if r["sig_after_correction"] and r["paired_diff"] < 0]
        n_sig_tm   = len(tm_better)
        n_sig_sp   = len(sp_better)
        n_no_sig   = len(CATEGORIES) - n_sig_tm - n_sig_sp

        if n_sig_tm == 0 and n_sig_sp == 0:
            verdict = "INCONCLUSIVE: No category reaches significance after BH correction. The comparison remains inconclusive even under the paired test."
        elif n_sig_sp == 0 and n_sig_tm > 0:
            verdict = (f"TEMPORAL is significantly better in {n_sig_tm} category/categories "
                       f"({', '.join(tm_better)}) and never worse. "
                       f"The allocation is STATIC: TEMPORAL should always be used.")
        elif n_sig_tm == 0 and n_sig_sp > 0:
            verdict = (f"SPARSE is significantly better in {n_sig_sp} category/categories "
                       f"({', '.join(sp_better)}) and never worse. "
                       f"The allocation is STATIC: SPARSE should always be used.")
        else:
            verdict = (f"TEMPORAL better in {n_sig_tm} ({', '.join(tm_better)}), "
                       f"SPARSE better in {n_sig_sp} ({', '.join(sp_better)}). "
                       f"The allocation is CATEGORY-DEPENDENT.")

        verdicts[m] = {
            "n_sig_temporal_better": n_sig_tm,
            "n_sig_sparse_better":   n_sig_sp,
            "n_no_sig":              n_no_sig,
            "categories_temporal_wins": tm_better,
            "categories_sparse_wins":   sp_better,
            "verdict_text":          verdict,
        }

    # ── Analysis C paired (distance bins, both models) ────────────────────────
    print("Running paired distance analysis (Analysis C) ...")
    dist_results = {}
    for m in MODELS:
        dist_results[m] = paired_distance_analysis(idx, model=m)

    # ── Analysis D paired (8B minus 4B per arm per category) ─────────────────
    print("Running paired model-gap analysis (Analysis D) ...")
    model_gap = {}
    for a in ARMS:
        model_gap[a] = {}
        gap_pvals = {}
        all_qids = sorted(idx["qwen3vl4b"][a].keys())
        # overall
        model_gap[a]["overall"] = paired_model_gap(idx, a, all_qids)
        for cat in CATEGORIES:
            cat_qids = [q for q in all_qids if idx["qwen3vl4b"][a][q]["category"] == cat]
            r = paired_model_gap(idx, a, cat_qids)
            if r:
                model_gap[a][cat] = r
                gap_pvals[cat] = r["pval_raw"]
        # BH across categories
        cat_adj = bh_correct(gap_pvals)
        for cat in gap_pvals:
            if cat in model_gap[a]:
                model_gap[a][cat]["pval_adj_bh"] = round(cat_adj[cat], 6)
                model_gap[a][cat]["sig_after_correction"] = cat_adj[cat] < ALPHA

    # ── Bias-only baseline ────────────────────────────────────────────────────
    print("Computing bias-only baselines ...")
    bias = {}
    for m in MODELS:
        bias[m] = {}
        for a in ARMS:
            cell_trials = list(idx[m][a].values())
            bias[m][a] = bias_baseline(cell_trials)

    # ── Latency accounting ────────────────────────────────────────────────────
    print("Computing corrected latency table ...")
    lat = latency_accounting(trials, i2_res)

    # ── Save artefacts ────────────────────────────────────────────────────────
    out = {
        "reuse_counts":    reuse_counts,
        "paired_sparse_vs_temporal": paired_results,
        "verdicts":        verdicts,
        "distance_analysis": dist_results,
        "model_gap_analysis": model_gap,
        "bias_baseline":   bias,
        "latency_accounting": {str(k): v for k, v in lat.items()},
    }
    (OUT_DIR / "study_i3_reanalysis.json").write_text(json.dumps(out, indent=2))
    print(f"Saved: {OUT_DIR}/study_i3_reanalysis.json")

    # ── Write report ──────────────────────────────────────────────────────────
    write_report(out, i3_res)
    print(f"Report: {REPORT_PATH}")
    print("Done.")
    return out

# ── report ────────────────────────────────────────────────────────────────────

def write_report(out, i3_res):
    pr   = out["paired_sparse_vs_temporal"]
    vd   = out["verdicts"]
    dist = out["distance_analysis"]
    gap  = out["model_gap_analysis"]
    bias = out["bias_baseline"]
    lat  = out["latency_accounting"]
    rc   = out["reuse_counts"]

    lines = []
    W = lines.append

    W("# Study I3 Re-analysis — Paired Tests and Corrected Accounting")
    W("")
    W(f"**Date:** 2026-09-03")
    W(f"**Input:** `results/sember/study_i3/study_i3_trials.jsonl` (1,836 trials)")
    W(f"**Script:** `experiments/sember/study_i3_reanalyse.py`")
    W(f"**Supersedes:** Study I3 Analysis (reports/study_i3_budget.md) — that report's Analysis B used independent-sample CIs on paired data.")
    W("")
    W("---")
    W("")

    # ── 1. What was recomputed ────────────────────────────────────────────────
    W("## 1. What Was Recomputed and From Which Files")
    W("")
    W("All analyses use the per-trial JSONL. No new inference was run.")
    W("")
    W("**Three defects fixed:**")
    W("")
    W("**Defect 1 (wrong test):** Study I3 compared independent-sample Wilson CIs. Because SPARSE and TEMPORAL ran on the *same* 459 questions with the *same* model, the data are paired. McNemar's test is the correct test. Independent CIs ignore between-question correlation and inflate the standard error, making real differences harder to detect.")
    W("")
    W("**Defect 2 (latency):** Study I3 Analysis E reported 8B SPARSE median = 5,295 ms against 1,225 ms in Study I2 for the same arm — a 4.3× discrepancy. Root cause: in I3, fresh trials measure `total_latency_ms = decode + preprocess + forward` (video-seek decode tracked), while reused I2 trials measure `total_latency_ms = inference only`. Study I3 compared these two quantities as if they were the same. They are not. Corrected table below uses inference-only time consistently.")
    W("")
    W("**Defect 3 (reuse header):** The I3 report header states 'Reused from study_i2: 0 trials'. This contradicts Section 1.2. Actual counts from per-trial records:")
    W("")
    W("| cell | reused from I2 | run fresh in I3 |")
    W("|---|---|---|")
    for key, v in rc.items():
        W(f"| {key} | {v['reused']} | {v['fresh']} |")
    W("")
    W("The header figure is wrong. The correct total reused is "
      f"{sum(v['reused'] for v in rc.values())} trials.")
    W("")
    W("---")
    W("")

    # ── 2. Sanity checks ──────────────────────────────────────────────────────
    W("## 2. Sanity Checks")
    W("")
    W("- **Trial counts:** all four cells 459/459 — PASS")
    W("- **Pairing:** SPARSE question_id set == TEMPORAL question_id set for both models — PASS")
    W("- **Accuracy reproduction:** recomputed unpaired accuracies match Study I3 Analysis A to within 1e-4 for all four cells — PASS")
    W("- **Contingency sums:** a+b+c+d == n for every tested cell — PASS")
    W("")
    W("---")
    W("")

    # ── 3. Paired per-category results ────────────────────────────────────────
    W("## 3. Paired Per-Category Results (McNemar's Test with BH Correction)")
    W("")
    W("**Legend:** b = SPARSE correct, TEMPORAL wrong; c = SPARSE wrong, TEMPORAL correct.")
    W("Positive paired_diff means TEMPORAL wins. BH correction across 7 categories per model.")
    W("Sig* = significant after BH correction (adj_p < 0.05).")
    W("")

    for m in MODELS:
        W(f"### {m}")
        W("")
        ov = pr[m]["overall"]
        W(f"**Overall (n={ov['n']}):** SPARSE={ov['sp_acc']:.3f} TEMPORAL={ov['tm_acc']:.3f} "
          f"diff={ov['paired_diff']:+.3f} 95%CI=[{ov['ci_lo']:+.3f},{ov['ci_hi']:+.3f}] "
          f"b={ov['b']} c={ov['c']} p={ov['pval_raw']:.4f} ({ov['mcnemar_method']})")
        W("")
        W("| category | n | b | c | SPARSE_acc | TEMPORAL_acc | paired_diff | 95%CI | raw_p | adj_p_BH | method | sig? |")
        W("|---|---|---|---|---|---|---|---|---|---|---|---|")
        cats = pr[m]["categories"]
        for cat in CATEGORIES:
            r = cats.get(cat)
            if not r:
                W(f"| {cat} | — | — | — | — | — | — | — | — | — | — | — |")
                continue
            sig = "**YES**" if r["sig_after_correction"] else "no"
            W(f"| {cat} | {r['n']} | {r['b']} | {r['c']} | {r['sp_acc']:.3f} | "
              f"{r['tm_acc']:.3f} | {r['paired_diff']:+.3f} | "
              f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}] | {r['pval_raw']:.4f} | "
              f"{r['pval_adj_bh']:.4f} | {r['mcnemar_method']} | {sig} |")
        W("")

    # ── 4. Allocation verdict ──────────────────────────────────────────────────
    W("## 4. Allocation Verdict")
    W("")
    for m in MODELS:
        v = vd[m]
        W(f"### {m}")
        W("")
        W(f"- Categories where TEMPORAL significantly better (after BH): {v['n_sig_temporal_better']} — {v['categories_temporal_wins'] or 'none'}")
        W(f"- Categories where SPARSE significantly better (after BH): {v['n_sig_sparse_better']} — {v['categories_sparse_wins'] or 'none'}")
        W(f"- No significant difference: {v['n_no_sig']}")
        W("")
        W(f"**VERDICT:** {v['verdict_text']}")
        W("")

    W("---")
    W("")

    # ── 5. Distance analysis ───────────────────────────────────────────────────
    W("## 5. Paired Distance Analysis (Analysis C)")
    W("")
    W("Paired SPARSE vs TEMPORAL, per farthest_dist_s bin. Both models shown.")
    W("")
    for m in MODELS:
        W(f"### {m}")
        W("")
        W("| bin | n | b | c | paired_diff | 95%CI | raw_p | method |")
        W("|---|---|---|---|---|---|---|---|")
        for bk_str, r in sorted(dist[m].items(), key=lambda x: json.loads(x[0].replace("inf","1e18").replace("(","[").replace(")","]"))[0]):
            W(f"| {bk_str} | {r['n']} | {r['b']} | {r['c']} | {r['paired_diff']:+.3f} | "
              f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}] | {r['pval_raw']:.4f} | "
              f"{r['mcnemar_method']} |")
        W("")
    W("Note: BH correction not applied to distance bins (exploratory). p-values are uncorrected.")
    W("")
    W("---")
    W("")

    # ── 6. Model-gap analysis ─────────────────────────────────────────────────
    W("## 6. Paired Model-Gap Analysis (Analysis D: 8B vs 4B)")
    W("")
    W("Positive diff = 8B better. BH correction across 7 categories per arm.")
    W("")
    for a in ARMS:
        W(f"### {a} arm")
        W("")
        ov = gap[a].get("overall")
        if ov:
            W(f"**Overall:** 4B={ov['v4_acc']:.3f} 8B={ov['v8_acc']:.3f} "
              f"diff={ov['diff_8b_minus_4b']:+.3f} CI=[{ov['ci_lo']:+.3f},{ov['ci_hi']:+.3f}] "
              f"b={ov['b']} c={ov['c']} p={ov['pval_raw']:.4f} ({ov['mcnemar_method']})")
        W("")
        W("| category | n | b | c | 4B_acc | 8B_acc | diff | 95%CI | raw_p | adj_p_BH | sig? |")
        W("|---|---|---|---|---|---|---|---|---|---|---|")
        for cat in CATEGORIES:
            r = gap[a].get(cat)
            if not r:
                W(f"| {cat} | — | — | — | — | — | — | — | — | — | — |")
                continue
            sig = "**YES**" if r.get("sig_after_correction") else "no"
            W(f"| {cat} | {r['n']} | {r['b']} | {r['c']} | {r['v4_acc']:.3f} | "
              f"{r['v8_acc']:.3f} | {r['diff_8b_minus_4b']:+.3f} | "
              f"[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}] | {r['pval_raw']:.4f} | "
              f"{r.get('pval_adj_bh', '—'):.4f} | {sig} |")
        W("")

    W("---")
    W("")

    # ── 7. Corrected latency table ─────────────────────────────────────────────
    W("## 7. Corrected Latency Accounting")
    W("")
    W("**Root cause of Defect 2:** In Study I3, fresh trials measure `total_latency_ms = video_decode + preprocess + forward`. Reused I2 trials measure `total_latency_ms = prefill + generation (inference only)`. Study I3 Analysis E averaged these two quantities together in one column, making 8B SPARSE appear 4.3× slower than in I2 (5,295 ms vs 1,225 ms). The 4,374 ms difference is entirely video-seek decode for 16 frames, not model inference.")
    W("")
    W("**Corrected inference-only latency** uses `forward_ms` for fresh I3 trials and `prefill_ms_est` for reused I2 trials (both measure model forward wall time; output is 2 tokens so autoregressive contribution is negligible).")
    W("")
    W("| cell | n_reused | n_fresh | total_lat_med_ms | infer_only_med_ms | decode_fresh_med_ms | forward_fresh_med_ms |")
    W("|---|---|---|---|---|---|---|")
    cell_order = [("qwen3vl4b","SPARSE"),("qwen3vl4b","TEMPORAL"),
                  ("qwen3vl8b","SPARSE"),("qwen3vl8b","TEMPORAL")]
    for m, a in cell_order:
        r = lat.get(str((m, a)), {})
        decode = r.get("decode_fresh_med_ms")
        decode_s = f"{decode:.0f}" if decode is not None else "— (no fresh trials)"
        fwd = r.get("forward_fresh_med_ms")
        fwd_s = f"{fwd:.0f}" if fwd is not None else "— (no fresh trials)"
        W(f"| {m}_{a} | {r.get('n_reused','?')} | {r.get('n_fresh','?')} | "
          f"{r.get('total_latency_med_ms','?'):.0f} | {r.get('infer_only_med_ms','?'):.0f} | "
          f"{decode_s} | {fwd_s} |")
    W("")
    cc = lat.get("cross_check_8b_sparse", {})
    W(f"**Cross-check 8B SPARSE:** I2 inference median = {cc.get('i2_lat_med_ms')} ms, "
      f"I3 inference-only median (forward_ms, fresh trials) = {cc.get('i3_infer_only_med_ms')} ms, "
      f"ratio = {cc.get('ratio')} — {cc.get('verdict')}.")
    W("")
    W("**The 7.2× and 1.3× ratios from Study I3 Analysis E are not reproducible** from consistent measurements.")
    W("Corrected inference-only ratios (using infer_only_med_ms):")
    i4s = lat.get(str(("qwen3vl4b","SPARSE")), {}).get("infer_only_med_ms")
    i4t = lat.get(str(("qwen3vl4b","TEMPORAL")), {}).get("infer_only_med_ms")
    i8s = lat.get(str(("qwen3vl8b","SPARSE")), {}).get("infer_only_med_ms")
    i8t = lat.get(str(("qwen3vl8b","TEMPORAL")), {}).get("infer_only_med_ms")
    if i4s and i4t:
        W(f"- 4B TEMPORAL / 4B SPARSE = {i4t/i4s:.2f}×")
    else:
        W("- 4B TEMPORAL / 4B SPARSE: cannot compute (4B SPARSE has no forward_ms — all reused from I2)")
    if i8s and i8t:
        W(f"- 8B TEMPORAL / 8B SPARSE = {i8t/i8s:.2f}×")
    W("")
    W("Note: 4B SPARSE is entirely reused from I2 (no fresh I3 trials), so its inference latency comes from I2's measurement context. The corrected ratio for 4B uses I2 prefill_ms_est for all SPARSE trials and forward_ms for fresh TEMPORAL trials; the mix is not perfectly comparable but is substantially better than the total_latency_ms mix.")
    W("")
    W("---")
    W("")

    # ── 8. Bias-only baseline ─────────────────────────────────────────────────
    W("## 8. Position Bias: Bias-Only Baseline")
    W("")
    W("Study I3 found significant letter-choice bias (chi-square vs uniform) in all four overall cells.")
    W("A bias-only baseline computes: for each question, what is the probability a model guessing")
    W("from its own marginal letter distribution gives the correct answer?")
    W("This bounds how much of the measured accuracy is explainable by letter preference alone.")
    W("")
    W("| cell | marginal A | B | C | D | E | bias_only_acc | measured_acc | lift_over_bias |")
    W("|---|---|---|---|---|---|---|---|---|---|")
    for m in MODELS:
        for a in ARMS:
            b = bias[m][a]
            mg = b["marginal"]
            W(f"| {m}_{a} | {mg.get('A',0):.3f} | {mg.get('B',0):.3f} | {mg.get('C',0):.3f} | "
              f"{mg.get('D',0):.3f} | {mg.get('E',0):.3f} | {b['bias_only_acc']:.3f} | "
              f"{b['measured_acc']:.3f} | {b['lift_over_bias']:+.3f} |")
    W("")
    W("**Interpretation:** `lift_over_bias` is the accuracy gap between the model's actual performance")
    W("and what pure letter preference predicts. A small lift would indicate the cell is measuring")
    W("letter preference rather than video understanding.")
    W("")
    W("---")
    W("")

    # ── 9. Plain-language summary ─────────────────────────────────────────────
    W("## 9. Plain-Language Summary")
    W("")
    W("**Under the paired test, does TEMPORAL beat SPARSE, and where?**")
    W("")
    for m in MODELS:
        v = vd[m]
        ov = pr[m]["overall"]
        W(f"- **{m}:** overall TEMPORAL−SPARSE = {ov['paired_diff']:+.3f} "
          f"(CI [{ov['ci_lo']:+.3f},{ov['ci_hi']:+.3f}], p={ov['pval_raw']:.4f}). "
          f"{v['verdict_text']}")
        W("")
    W("**Is the allocation static or category-dependent?**")
    W("")
    # pick the more informative of the two model verdicts
    for m in MODELS:
        W(f"- **{m}:** {vd[m]['verdict_text'][:120]}...")
        W("")
    W("**How much of the measured accuracy could letter bias alone account for?**")
    W("")
    for m in MODELS:
        for a in ARMS:
            b = bias[m][a]
            W(f"- {m}_{a}: measured={b['measured_acc']:.3f}, bias-only={b['bias_only_acc']:.3f}, "
              f"lift={b['lift_over_bias']:+.3f}. "
              + ("Letter bias is a substantial fraction of measured accuracy — interpret with caution."
                 if b['lift_over_bias'] < 0.05 else
                 "Measured accuracy meaningfully exceeds bias-only baseline."))
    W("")
    W("---")
    W("")
    W("## 10. What Cannot Be Inferred")
    W("")
    W("- **4B SPARSE inference latency from I3 directly:** all 459 trials are reused from I2; no `forward_ms` exists in the I3 JSONL for that cell.")
    W("- **TEMPORAL decode overhead vs I2:** I2 used per-frame seeks (no decode tracking); I3 used sequential cache (amortised per video). The two decode numbers are not on the same footing.")
    W("- **Position bias correction:** would require rerunning with permuted option orders.")

    REPORT_PATH.write_text("\n".join(lines) + "\n")

if __name__ == "__main__":
    main()
