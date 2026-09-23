#!/usr/bin/env python3
"""Study K analysis — multi-seed-aware version.

Fixes vs original:
- QUICK_SUFFIX defined here (not imported from runner)
- Multi-seed arms (THINKING, THINKING-QUICK, THINKING_PERMUTED) aggregated via
  majority vote per question for McNemar; mean accuracy for replication check.
- Gracefully skips arms / bias sections when not yet complete.
"""

import json, math, sys
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
from scipy import stats as scipy_stats

JSONL_PATH  = Path("results/erqa/study_k/study_k_trials.jsonl")
REPORT_PATH = Path("reports/study_k_erqa.md")
JSON_PATH   = Path("results/erqa/study_k/study_k_results.json")

QUICK_SUFFIX = " Answer quickly without overthinking."
LETTERS      = ["A", "B", "C", "D"]
PRIMARY_ARMS = ["INSTRUCT", "THINKING", "THINKING-QUICK"]
BIAS_ARMS    = {"INSTRUCT": "INSTRUCT_PERMUTED", "THINKING": "THINKING_PERMUTED"}
MULTI_SEED_ARMS = {"THINKING", "THINKING-QUICK", "THINKING_PERMUTED"}

PUBLISHED = {"INSTRUCT": 41.3, "THINKING": 47.3}
REPLICATION_THRESHOLD = 5.0


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def mcnemar(b, c):
    n_disc = b + c
    if n_disc == 0:
        return 1.0, "exact_binomial(n=0)"
    if n_disc < 25:
        k = min(b, c)
        pval = min(1.0, 2 * min(
            scipy_stats.binom.cdf(k, n_disc, 0.5),
            1 - scipy_stats.binom.cdf(k - 1, n_disc, 0.5),
        ))
        return float(pval), "exact_binomial"
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    return float(scipy_stats.chi2.sf(chi2, df=1)), "chisq_continuity"


def bh_correct(pvals_dict):
    items = sorted(pvals_dict.items(), key=lambda x: x[1])
    m = len(items)
    adjusted = {}
    for rank, (key, pval) in enumerate(items, 1):
        adjusted[key] = min(1.0, pval * m / rank)
    keys_sorted = [k for k, _ in items]
    for i in range(len(keys_sorted) - 2, -1, -1):
        adjusted[keys_sorted[i]] = min(adjusted[keys_sorted[i]], adjusted[keys_sorted[i + 1]])
    return adjusted


def boot_ci(arr_a, arr_b, n_boot=10000, seed=42):
    rng = np.random.default_rng(seed)
    arr_a, arr_b = np.array(arr_a, float), np.array(arr_b, float)
    n = len(arr_a)
    diffs = [arr_b[rng.integers(0, n, size=n)].mean() - arr_a[rng.integers(0, n, size=n)].mean()
             for _ in range(n_boot)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(lo), float(hi)


def wilson_ci(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


# ---------------------------------------------------------------------------
# Load trials
# ---------------------------------------------------------------------------

def load_trials():
    trials = []
    with open(JSONL_PATH) as f:
        for line in f:
            if line.strip():
                trials.append(json.loads(line))
    return trials


def index_trials(trials):
    """Return two indexes:
       flat[arm]          = list of all trials (all seeds) for that arm
       by_seed[arm][seed] = {qid: trial}
    """
    flat     = defaultdict(list)
    by_seed  = defaultdict(lambda: defaultdict(dict))
    for t in trials:
        arm  = t["arm"]
        seed = t.get("seed")
        qid  = t["question_id"]
        flat[arm].append(t)
        by_seed[arm][seed][qid] = t
    return flat, by_seed


def majority_vote_correct(arm, by_seed, qids):
    """For each qid: majority of seeds correct → 1, else 0.
       For single-seed arms (seed=None) this is just that seed's answer.
       Returns {qid: 0/1}.
    """
    seeds = list(by_seed[arm].keys())
    if not seeds:
        return {}
    result = {}
    for qid in qids:
        votes = [int(by_seed[arm][s].get(qid, {}).get("correct", 0)) for s in seeds]
        if not any(by_seed[arm][s].get(qid) for s in seeds):
            continue
        result[qid] = 1 if sum(votes) > len(votes) / 2 else 0
    return result


def mean_acc(arm, flat):
    t = flat.get(arm, [])
    if not t:
        return None
    return sum(x["correct"] for x in t) / len(t)


def per_seed_accs(arm, by_seed):
    return {seed: sum(t["correct"] for t in qid_dict.values()) / max(1, len(qid_dict))
            for seed, qid_dict in by_seed.get(arm, {}).items()}


# ---------------------------------------------------------------------------
# Gate test (uses majority-vote correctness vectors)
# ---------------------------------------------------------------------------

def gate_test(mv_a, mv_b, qids):
    """McNemar + bootstrap CI. mv_a / mv_b are {qid: 0/1} from majority_vote_correct."""
    paired_a, paired_b, b, c = [], [], 0, 0
    for qid in qids:
        if qid not in mv_a or qid not in mv_b:
            continue
        ca, cb = mv_a[qid], mv_b[qid]
        paired_a.append(ca)
        paired_b.append(cb)
        if cb == 1 and ca == 0:
            b += 1
        elif cb == 0 and ca == 1:
            c += 1
    pval, method = mcnemar(b, c)
    lo, hi = boot_ci(paired_a, paired_b)
    diff = np.mean(paired_b) - np.mean(paired_a)
    return {
        "n": len(paired_a), "b": b, "c": c,
        "diff": round(float(diff), 4),
        "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
        "pval": round(pval, 4), "method": method,
    }


def gate_line(g):
    sig = "**p<0.05**" if g["pval"] < 0.05 else "p≥0.05"
    return (f"diff={100*g['diff']:+.2f}pp, 95%CI=[{100*g['ci_lo']:+.1f},{100*g['ci_hi']:+.1f}], "
            f"b={g['b']},c={g['c']}, p={g['pval']:.4f} ({g['method']}), {sig}")


# ---------------------------------------------------------------------------
# Think-token stats across all seeds
# ---------------------------------------------------------------------------

def think_stats(arm, flat, qids):
    qid_set = set(qids)
    tokens = [t["n_think_tokens"] for t in flat.get(arm, []) if t["question_id"] in qid_set]
    if not tokens:
        return {}
    tokens = sorted(tokens)
    median = float(np.median(tokens))
    return {
        "n": len(tokens),
        "median": round(median, 1),
        "iqr": round(float(np.percentile(tokens, 75) - np.percentile(tokens, 25)), 1),
        "min": tokens[0], "max": tokens[-1],
        "iqr_over_median": round(
            (np.percentile(tokens, 75) - np.percentile(tokens, 25)) / median, 3
        ) if median > 0 else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyse(prelim=False):
    trials = load_trials()
    flat, by_seed = index_trials(trials)

    present_arms = sorted(flat.keys())
    print("Arms present:", present_arms)
    for arm in present_arms:
        seeds_done = sorted(by_seed[arm].keys())
        n_per_seed = {s: len(d) for s, d in by_seed[arm].items()}
        print(f"  {arm}: seeds={seeds_done}  n_per_seed={n_per_seed}")

    all_qids = sorted(set(t["question_id"] for t in trials))

    meta = {t["question_id"]: {"category": t["category"], "n_images": t["n_images"]}
            for t in trials}
    categories = sorted(set(m["category"] for m in meta.values()))
    single_qids = [q for q in all_qids if meta[q]["n_images"] == 1]
    multi_qids  = [q for q in all_qids if meta[q]["n_images"] > 1]

    # -----------------------------------------------------------------------
    # Majority-vote correctness maps for all arms
    # -----------------------------------------------------------------------
    mv = {arm: majority_vote_correct(arm, by_seed, all_qids) for arm in present_arms}

    # -----------------------------------------------------------------------
    # Part A: replication check  (mean accuracy across seeds)
    # -----------------------------------------------------------------------
    replication = {}
    for arm in ["INSTRUCT", "THINKING"]:
        if arm not in flat:
            replication[arm] = None
            continue
        acc = mean_acc(arm, flat)
        pub = PUBLISHED[arm]
        diff = 100 * acc - pub
        seed_accs = per_seed_accs(arm, by_seed)
        replication[arm] = {
            "acc_pct": round(100 * acc, 2),
            "published": pub,
            "diff_pp": round(diff, 2),
            "pass": abs(diff) <= REPLICATION_THRESHOLD,
            "per_seed": {str(s): round(100 * a, 2) for s, a in seed_accs.items()},
        }
    replication_pass = all(v["pass"] for v in replication.values() if v is not None)

    # -----------------------------------------------------------------------
    # Part B: gate test  THINKING (majority vote) vs INSTRUCT
    # -----------------------------------------------------------------------
    instruct_mv = mv.get("INSTRUCT", {})
    thinking_mv = mv.get("THINKING", {})
    overall_gate = gate_test(instruct_mv, thinking_mv, all_qids)
    gate_holds   = overall_gate["pval"] < 0.05 and overall_gate["diff"] > 0

    # -----------------------------------------------------------------------
    # Part C: breakdown by category / image count (BH corrected)
    # -----------------------------------------------------------------------
    groups = {
        "single_image": single_qids,
        "multi_image":  multi_qids,
    }
    for cat in categories:
        groups[f"cat:{cat}"] = [q for q in all_qids if meta[q]["category"] == cat]

    group_results = {}
    raw_pvals = {}
    for gname, qids in groups.items():
        g = gate_test(instruct_mv, thinking_mv, qids)
        group_results[gname] = g
        raw_pvals[gname] = g["pval"]
    bh = bh_correct(raw_pvals)
    for gname in group_results:
        group_results[gname]["pval_bh"] = round(bh[gname], 4)
        group_results[gname]["sig_bh"]  = bh[gname] < 0.05

    # -----------------------------------------------------------------------
    # Part D: reasoning spend (aggregated across seeds)
    # -----------------------------------------------------------------------
    think_spend = {}
    for arm in ["THINKING", "THINKING-QUICK"]:
        if arm not in flat:
            continue
        think_spend[arm] = {
            "overall": think_stats(arm, flat, all_qids),
            "single":  think_stats(arm, flat, single_qids),
            "multi":   think_stats(arm, flat, multi_qids),
        }
        for cat in categories:
            think_spend[arm][f"cat:{cat}"] = think_stats(arm, flat, groups[f"cat:{cat}"])

    # -----------------------------------------------------------------------
    # Part E: non-termination  (across seeds; fraction over total trials)
    # -----------------------------------------------------------------------
    non_term = {}
    for arm in ["INSTRUCT", "THINKING", "THINKING-QUICK"]:
        tlist = flat.get(arm, [])
        if not tlist:
            continue
        n_seeds = len(by_seed.get(arm, {}))
        non_term[arm] = {
            "budget_hits": sum(t["budget_hit"] for t in tlist),
            "total_trials": len(tlist),
            "n_seeds": n_seeds,
            "hits_per_400q": round(sum(t["budget_hit"] for t in tlist) / n_seeds, 1) if n_seeds else None,
            "single": sum(t["budget_hit"] for t in tlist if t["n_images"] == 1),
            "multi":  sum(t["budget_hit"] for t in tlist if t["n_images"] > 1),
        }

    # -----------------------------------------------------------------------
    # Part F: think tokens vs correctness (aggregated across seeds)
    # -----------------------------------------------------------------------
    def within_corr(qids, label):
        rows = [(t["n_think_tokens"], int(t["correct"]))
                for t in flat.get("THINKING", []) if t["question_id"] in set(qids)]
        if len(rows) < 10:
            return {"n": len(rows), "r": None, "pval": None, "label": label}
        toks, corr = zip(*rows)
        r, pval = scipy_stats.pointbiserialr(list(toks), list(corr))
        return {"n": len(rows), "r": round(float(r), 4), "pval": round(float(pval), 4), "label": label}

    corr_results = {"overall": within_corr(all_qids, "overall"),
                    "single":  within_corr(single_qids, "single"),
                    "multi":   within_corr(multi_qids, "multi")}
    for cat in categories:
        corr_results[f"cat:{cat}"] = within_corr(groups[f"cat:{cat}"], cat)

    # -----------------------------------------------------------------------
    # Part G: THINKING-QUICK vs THINKING
    # -----------------------------------------------------------------------
    tq_mv = mv.get("THINKING-QUICK", {})
    tq_gate = gate_test(thinking_mv, tq_mv, all_qids) if tq_mv else None

    def latency_think(arm):
        tlist = flat.get(arm, [])
        lat   = [t["total_latency_ms"] for t in tlist]
        think = [t["n_think_tokens"]    for t in tlist]
        return lat, think

    t_lat,  t_think  = latency_think("THINKING")
    tq_lat, tq_think = latency_think("THINKING-QUICK")
    thinking_quick_vs_thinking = {
        "gate": tq_gate,
        "thinking_mean_acc_pct":  round(100 * mean_acc("THINKING",       flat), 2) if flat.get("THINKING")       else None,
        "thinking_quick_mean_acc_pct": round(100 * mean_acc("THINKING-QUICK", flat), 2) if flat.get("THINKING-QUICK") else None,
        "median_latency_thinking":     round(float(np.median(t_lat)),   1) if t_lat  else None,
        "median_latency_quick":        round(float(np.median(tq_lat)),  1) if tq_lat else None,
        "median_think_tokens_thinking": round(float(np.median(t_think)), 1) if t_think else None,
        "median_think_tokens_quick":    round(float(np.median(tq_think)),1) if tq_think else None,
    }

    # -----------------------------------------------------------------------
    # Part H: position bias
    # -----------------------------------------------------------------------
    bias = {}
    for arm, perm_arm in BIAS_ARMS.items():
        if arm not in mv or perm_arm not in mv:
            bias[arm] = None
            continue
        arm_mv  = mv[arm]
        perm_mv = mv[perm_arm]
        acc_orig = sum(arm_mv.values())  / max(1, len(arm_mv))
        acc_perm = sum(perm_mv.values()) / max(1, len(perm_mv))
        orig_letters = Counter(t["predicted_letter"] for t in flat[arm] if t.get("predicted_letter"))
        perm_letters = Counter(t["predicted_letter"] for t in flat[perm_arm] if t.get("predicted_letter"))
        bias[arm] = {
            "acc_original_pct": round(100 * acc_orig, 2),
            "acc_permuted_pct": round(100 * acc_perm, 2),
            "diff_pp":          round(100 * (acc_perm - acc_orig), 2),
            "letter_dist_original": dict(orig_letters),
            "letter_dist_permuted": dict(perm_letters),
        }

    # -----------------------------------------------------------------------
    # Assemble JSON result
    # -----------------------------------------------------------------------
    arm_accs = {}
    for arm in present_arms:
        arm_accs[arm] = {
            "mean_acc_pct": round(100 * mean_acc(arm, flat), 2),
            "per_seed": {str(s): round(100 * sum(t["correct"] for t in d.values()) / max(1, len(d)), 2)
                         for s, d in by_seed[arm].items()},
        }

    result = {
        "study": "K",
        "preliminary": prelim,
        "n_questions": 400,
        "n_multi_image": len(multi_qids),
        "category_distribution": dict(Counter(meta[q]["category"] for q in all_qids)),
        "arm_accuracies": arm_accs,
        "replication": replication,
        "replication_pass": replication_pass,
        "gate_overall": overall_gate,
        "gate_holds": gate_holds,
        "gate_verdict": (
            "HOLDS" if gate_holds else
            "FAILS — THINKING ≤ INSTRUCT under McNemar's test"
        ),
        "group_breakdown": group_results,
        "think_spend": think_spend,
        "non_termination": non_term,
        "think_vs_correct_corr": corr_results,
        "thinking_quick_vs_thinking": thinking_quick_vs_thinking,
        "position_bias": bias,
    }

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(result, indent=2))

    # -----------------------------------------------------------------------
    # Markdown report
    # -----------------------------------------------------------------------
    lines = []
    def w(s=""): lines.append(s)

    w(f"# Study K — Reasoning Gate on ERQA{'  *(PRELIMINARY)*' if prelim else ''}")
    w()
    if prelim:
        w("> **Preliminary run.** THINKING_PERMUTED arm not yet complete; position bias for THINKING is unavailable.")
        w()

    w("## 1. Arm Accuracies")
    w()
    w("| Arm | Seeds | Mean acc | Per-seed |")
    w("|---|---|---|---|")
    for arm in ["INSTRUCT", "INSTRUCT_PERMUTED", "THINKING", "THINKING-QUICK", "THINKING_PERMUTED"]:
        if arm not in arm_accs:
            continue
        info = arm_accs[arm]
        seeds_str = ", ".join(f"{s}={v:.1f}%" for s, v in sorted(info["per_seed"].items(), key=lambda x: str(x[0])))
        w(f"| {arm} | {len(info['per_seed'])} | **{info['mean_acc_pct']:.1f}%** | {seeds_str} |")
    w()

    w("## 2. Replication Check (vs arXiv 2511.21631 Table 4: INSTRUCT=41.3, THINKING=47.3)")
    w()
    w("| Arm | Ours (mean) | Published | Diff | Pass |")
    w("|---|---|---|---|---|")
    for arm in ["INSTRUCT", "THINKING"]:
        r = replication.get(arm)
        if r:
            w(f"| {arm} | {r['acc_pct']:.1f}% | {r['published']}% | {r['diff_pp']:+.1f}pp | {'✓' if r['pass'] else '✗ STOP'} |")
    if not replication_pass:
        w()
        w("**STOP: Replication check FAILED. Do not interpret gate result.**")
    else:
        w()
        w("Replication check PASS.")
    w()

    w("## 3. Gate Test — THINKING vs INSTRUCT (McNemar, majority vote)")
    w()
    g = overall_gate
    w(f"Paired McNemar, n={g['n']}: {gate_line(g)}")
    w()
    w(f"**PRE-REGISTERED VERDICT: {result['gate_verdict']}**")
    w()

    w("## 4. Breakdown by Group (BH corrected)")
    w()
    w("| Group | n | diff | 95%CI | p | p_BH | sig |")
    w("|---|---|---|---|---|---|---|")
    for gname in ["single_image", "multi_image"] + [f"cat:{c}" for c in categories]:
        g = group_results.get(gname, {})
        if not g: continue
        label = gname.replace("cat:", "")
        w(f"| {label} | {g['n']} | {100*g['diff']:+.1f}pp | "
          f"[{100*g['ci_lo']:+.1f},{100*g['ci_hi']:+.1f}] | "
          f"{g['pval']:.4f} | {g['pval_bh']:.4f} | {'✓' if g['sig_bh'] else '—'} |")
    w()

    w("## 5. Reasoning Spend (all seeds pooled)")
    w()
    w("| Arm | Group | n | median tok | IQR | min | max | IQR/median |")
    w("|---|---|---|---|---|---|---|---|")
    for arm in ["THINKING", "THINKING-QUICK"]:
        for gkey in ["overall", "single", "multi"] + [f"cat:{c}" for c in categories]:
            s = think_spend.get(arm, {}).get(gkey, {})
            if not s: continue
            label = gkey.replace("cat:", "")
            w(f"| {arm} | {label} | {s['n']} | {s['median']} | {s['iqr']} | "
              f"{s['min']} | {s['max']} | {s.get('iqr_over_median','—')} |")
    w()

    w("## 6. Non-Termination")
    w()
    w("| Arm | Budget hits (total) | Per 400q | Single | Multi |")
    w("|---|---|---|---|---|")
    for arm in ["INSTRUCT", "THINKING", "THINKING-QUICK"]:
        nt = non_term.get(arm, {})
        if not nt: continue
        w(f"| {arm} | {nt['budget_hits']}/{nt['total_trials']} | {nt['hits_per_400q']} | "
          f"{nt['single']} | {nt['multi']} |")
    w()

    w("## 7. Think Tokens vs Correctness (point-biserial r, THINKING arm)")
    w()
    w("| Group | n | r | p |")
    w("|---|---|---|---|")
    for gkey, cr in corr_results.items():
        label = gkey.replace("cat:", "")
        r_str = f"{cr['r']:.4f}" if cr.get("r") is not None else "—"
        p_str = f"{cr['pval']:.4f}" if cr.get("pval") is not None else "—"
        w(f"| {label} | {cr['n']} | {r_str} | {p_str} |")
    w()

    w("## 8. THINKING-QUICK vs THINKING")
    w()
    tq = thinking_quick_vs_thinking
    if tq["gate"]:
        w(f"THINKING mean={tq['thinking_mean_acc_pct']:.1f}%  "
          f"THINKING-QUICK mean={tq['thinking_quick_mean_acc_pct']:.1f}%")
        w()
        w(f"Paired McNemar (QUICK vs THINKING, majority vote): {gate_line(tq['gate'])}")
        w()
        w("| | THINKING | THINKING-QUICK |")
        w("|---|---|---|")
        w(f"| Median latency (ms) | {tq['median_latency_thinking']} | {tq['median_latency_quick']} |")
        w(f"| Median think tokens | {tq['median_think_tokens_thinking']} | {tq['median_think_tokens_quick']} |")
    else:
        w("THINKING-QUICK not yet complete.")
    w()

    w("## 9. Position Bias")
    w()
    for arm, b in bias.items():
        if b is None:
            w(f"**{arm}:** permuted arm not yet complete — skipped.")
            continue
        material = abs(b["diff_pp"]) >= 3.0
        w(f"**{arm}:** original={b['acc_original_pct']:.1f}%, permuted={b['acc_permuted_pct']:.1f}%, "
          f"diff={b['diff_pp']:+.1f}pp → {'**MATERIAL BIAS**' if material else 'not material'}")
        w(f"  Letter dist (original): {b['letter_dist_original']}")
        w(f"  Letter dist (permuted): {b['letter_dist_permuted']}")
        w()

    w("## 10. Plain-Language Summary")
    w()
    rep_i = replication.get("INSTRUCT"); rep_t = replication.get("THINKING")
    if rep_i and rep_t:
        if rep_i["pass"] and rep_t["pass"]:
            w(f"**Replication:** INSTRUCT={rep_i['acc_pct']:.1f}% ({rep_i['diff_pp']:+.1f}pp vs 41.3), "
              f"THINKING={rep_t['acc_pct']:.1f}% ({rep_t['diff_pp']:+.1f}pp vs 47.3). Both within 5pp. ✓")
        else:
            w("**Replication FAILED** — harness suspect.")
    g = overall_gate
    w(f"**Gate:** diff={100*g['diff']:+.2f}pp, p={g['pval']:.4f}. {result['gate_verdict']}")
    if tq["gate"]:
        w(f"**THINKING-QUICK vs THINKING:** diff={100*tq['gate']['diff']:+.2f}pp, p={tq['gate']['pval']:.4f}.")
    w()

    REPORT_PATH.write_text("\n".join(lines))
    print(f"\nReport: {REPORT_PATH}")
    print(f"JSON:   {JSON_PATH}")

    # Print key numbers to stdout
    print("\n=== KEY RESULTS ===")
    for arm, info in arm_accs.items():
        seeds_str = "  ".join(f"s{s}={v:.1f}%" for s, v in sorted(info["per_seed"].items(), key=lambda x: str(x[0])))
        print(f"  {arm:25s}  mean={info['mean_acc_pct']:.1f}%  {seeds_str}")
    print(f"\n  Gate: {gate_line(overall_gate)}")
    print(f"  VERDICT: {result['gate_verdict']}")
    if tq["gate"]:
        print(f"\n  THINKING-QUICK vs THINKING: {gate_line(tq['gate'])}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prelim", action="store_true")
    args = ap.parse_args()
    analyse(prelim=args.prelim)
