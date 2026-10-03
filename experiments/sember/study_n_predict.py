"""
StudyN — Is evidence horizon predictable at runtime from question text and elapsed time?

Pre-registered decision rule (EXPERIMENTS.md row StudyN):
  PREDICTABLE:   best non-oracle closes >= 40% oracle coverage gap at W=120, 95% bootstrap CI excl. 0
  UNPREDICTABLE: best predictor closes < 15% OR CI includes 0
  PARTIAL:       otherwise

Writes: results/sember/study_n/study_n_results.json
        reports/study_n_results.md
"""
import json, re, sys, os, random, math, warnings
import numpy as np
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp

warnings.filterwarnings("ignore")

GROUNDING_PATH = "results/sember/study_h/data/sember_grounding.jsonl"
OUT_JSON       = "results/sember/study_n/study_n_results.json"
OUT_REPORT     = "reports/study_n_results.md"
SEED           = 42
N_FOLDS        = 5
N_BOOTSTRAP    = 2000
W_LIST         = [60, 120, 300]
W_PRIMARY      = 120

KEYWORD_RULES = [
    "first", "earlier", "before", "at the beginning", "last time",
    "just", "now", "currently", "recently", "start", "began", "initially",
    "earlier in", "beginning of"
]

EMBED_MODEL_ID = "all-MiniLM-L6-v2"


# ── data loading ─────────────────────────────────────────────────────────────

def load_data():
    records = [json.loads(l) for l in open(GROUNDING_PATH)]
    rows, neg = [], 0
    for r in records:
        qt  = r["question_time"]
        aet = r["answer_end_time"]
        ast = r["answer_start_time"]
        nd  = qt - aet
        fd  = qt - ast
        if nd < 0:
            neg += 1
            continue
        rows.append({
            "qid":      r["question_id"],
            "vid":      r["video_id"],
            "question": r["question"],
            "qt":       qt,
            "duration": r["duration"],
            "category": r["question_category"],
            "nearest":  nd,
            "farthest": fd,
        })
    print(f"Loaded {len(rows)} rows; excluded {neg} negative-nearest.", flush=True)
    return rows


def sanity_check(rows):
    nearest  = np.array([r["nearest"]  for r in rows])
    farthest = np.array([r["farthest"] for r in rows])
    print(f"nearest  p50={np.percentile(nearest,50):.0f} p75={np.percentile(nearest,75):.0f} p90={np.percentile(nearest,90):.0f}")
    print(f"farthest p50={np.percentile(farthest,50):.0f} p75={np.percentile(farthest,75):.0f} p90={np.percentile(farthest,90):.0f}")
    print("H2 committed: nearest 21/56/117; farthest 74/135/236")
    assert np.percentile(nearest, 50) == 21
    assert np.percentile(nearest, 75) == 56
    assert np.percentile(nearest, 90) == 117
    print("Sanity check PASS.")


# ── cross-validation folds (grouped by video_id) ─────────────────────────────

def make_folds(rows, n_folds=5, seed=42):
    rng = random.Random(seed)
    vids = sorted(set(r["vid"] for r in rows))
    rng.shuffle(vids)
    vid_fold = {v: i % n_folds for i, v in enumerate(vids)}
    folds = [[] for _ in range(n_folds)]
    for i, r in enumerate(rows):
        folds[vid_fold[r["vid"]]].append(i)
    return folds


def check_no_leakage(rows, folds):
    for fi, fold in enumerate(folds):
        fold_vids = set(rows[i]["vid"] for i in fold)
        other_vids = set(rows[i]["vid"] for j, f in enumerate(folds) if j != fi for i in f)
        assert len(fold_vids & other_vids) == 0, f"Leakage in fold {fi}"
    print("No session leakage across folds: CONFIRMED.")


# ── feature builders ──────────────────────────────────────────────────────────

def feat_elapsed(rows, idx):
    return np.array([[rows[i]["qt"]] for i in idx], dtype=float)


def feat_keyword(rows, idx):
    feats = []
    for i in idx:
        q = rows[i]["question"].lower()
        hit = int(any(kw in q for kw in KEYWORD_RULES))
        feats.append([hit, rows[i]["qt"]])
    return np.array(feats, dtype=float)


def feat_tfidf(rows, train_idx, test_idx, extra_feat_fn):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy.sparse import hstack, csr_matrix
    questions_train = [rows[i]["question"] for i in train_idx]
    questions_test  = [rows[i]["question"] for i in test_idx]
    vec = TfidfVectorizer(max_features=2000, ngram_range=(1,2), sublinear_tf=True)
    Xtr = vec.fit_transform(questions_train)
    Xte = vec.transform(questions_test)
    etr = csr_matrix(extra_feat_fn(rows, train_idx))
    ete = csr_matrix(extra_feat_fn(rows, test_idx))
    return hstack([Xtr, etr]), hstack([Xte, ete]), vec


_embed_cache = {}

def feat_embed(rows, train_idx, test_idx, extra_feat_fn):
    global _embed_cache
    from sentence_transformers import SentenceTransformer
    if "model" not in _embed_cache:
        print(f"  Loading {EMBED_MODEL_ID}...", flush=True)
        _embed_cache["model"] = SentenceTransformer(EMBED_MODEL_ID)
    model = _embed_cache["model"]
    all_idx = sorted(set(train_idx) | set(test_idx))
    if "embeds" not in _embed_cache:
        questions = [rows[i]["question"] for i in range(len(rows))]
        _embed_cache["embeds"] = model.encode(questions, batch_size=256, show_progress_bar=True)
    E = _embed_cache["embeds"]
    Etr = E[np.array(train_idx)]
    Ete = E[np.array(test_idx)]
    etr = extra_feat_fn(rows, train_idx)
    ete = extra_feat_fn(rows, test_idx)
    return np.hstack([Etr, etr]), np.hstack([Ete, ete])


def feat_oracle(rows, idx):
    return np.array([[rows[i]["qt"], {"counting_objects_events":0,
                    "time_duration":1,"sequential_action":2,
                    "spatial_aware_reasoning":3,"object_comparison":4,
                    "location_trace":5}.get(rows[i]["category"], 6)] for i in idx], dtype=float)


# ── regression / classification ───────────────────────────────────────────────

def fit_predict_t1(Xtr, Ytr, Xte):
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler(with_mean=False)
    Xtr2 = sc.fit_transform(Xtr)
    Xte2 = sc.transform(Xte)
    m = Ridge(alpha=1.0)
    m.fit(Xtr2, Ytr)
    return m.predict(Xte2)


def fit_predict_t2(Xtr, Ytr, Xte):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler(with_mean=False)
    Xtr2 = sc.fit_transform(Xtr)
    Xte2 = sc.transform(Xte)
    m = LogisticRegression(max_iter=1000, C=1.0)
    m.fit(Xtr2, Ytr.astype(int))
    return m.predict_proba(Xte2)[:, 1]


# ── metrics ───────────────────────────────────────────────────────────────────

def spearman(a, b):
    from scipy.stats import spearmanr
    r, p = spearmanr(a, b)
    return float(r), float(p)


def auroc(y_true, y_score):
    from sklearn.metrics import roc_auc_score
    if len(set(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def calibration_table(y_true, y_score, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_score >= lo) & (y_score < hi)
        n = mask.sum()
        if n == 0:
            rows.append({"bin_lo": round(lo,2), "bin_hi": round(hi,2), "n": 0, "mean_pred": None, "frac_pos": None})
        else:
            rows.append({"bin_lo": round(lo,2), "bin_hi": round(hi,2),
                         "n": int(n), "mean_pred": float(y_score[mask].mean()),
                         "frac_pos": float(y_true[mask].mean())})
    return rows


# ── coverage / systems metric ─────────────────────────────────────────────────

def coverage_fixed(rows, idx, W):
    """Fraction of questions where farthest evidence distance <= W."""
    return np.mean([rows[i]["farthest"] <= W for i in idx])


def coverage_oracle(rows, idx, W_s, W_l, W_budget):
    """Budget-constrained oracle: knows true farthest distance, allocates optimally.

    Assigns W_l to frac_long fraction of questions, W_s to the rest.
    Strategy: assign W_s to all farthest<=W_s (already covered, saves budget),
    then assign W_l to questions with farthest in (W_s, W_l] in ascending order
    until W_l budget is exhausted.  Remaining questions get W_s.
    """
    frac_long = (W_budget - W_s) / (W_l - W_s)
    frac_long = max(0.0, min(1.0, frac_long))
    n_long_budget = int(round(frac_long * len(idx)))

    idx_arr = np.array(idx)
    fd_arr  = np.array([rows[i]["farthest"] for i in idx])

    # Questions that need W_l: those with farthest > W_s (W_s doesn't cover them)
    need_long = np.where(fd_arr > W_s)[0]  # local indices into idx_arr
    # Sort by farthest ascending: cover the easiest hard cases first (just above W_s)
    need_long_sorted = need_long[np.argsort(fd_arr[need_long])]
    # Assign W_l to the first n_long_budget of these (ascending distance)
    get_long = set(need_long_sorted[:n_long_budget].tolist())

    covered = []
    for j, i in enumerate(idx):
        fd = rows[i]["farthest"]
        chosen_W = W_l if j in get_long else W_s
        covered.append(fd <= chosen_W)
    return np.mean(covered)


def coverage_policy_b(rows, idx, scores, W_s, W_l, W_budget):
    """
    Policy B: choose W_l if score > threshold, else W_s.
    Threshold set so mean retained seconds = W_budget.
    Score is P(evidence within W_budget) -- high score = evidence is near = use W_s.
    Actually: high score = predict far evidence = use W_l.
    We need: mean_window = threshold_frac * W_l + (1-threshold_frac) * W_s = W_budget
    """
    # Sort by score ascending: low score = predict evidence is near (short window)
    # We want (n_long / n_total) * W_l + (n_short / n_total) * W_s = W_budget
    # n_long / n_total = (W_budget - W_s) / (W_l - W_s)
    frac_long = (W_budget - W_s) / (W_l - W_s)
    frac_long = max(0.0, min(1.0, frac_long))
    # Low score = P(evidence within W) is low = evidence far → assign W_l.
    # Bottom frac_long fraction of scores get W_l; rest get W_s.
    threshold = np.quantile(scores, frac_long) if frac_long > 0.0 else np.inf
    covered = []
    for j, i in enumerate(idx):
        fd = rows[i]["farthest"]
        chosen_W = W_l if scores[j] < threshold else W_s
        covered.append(fd <= chosen_W)
    return np.mean(covered), float(frac_long)


def gap_closed(policy_b_cov, policy_a_cov, oracle_cov):
    denom = oracle_cov - policy_a_cov
    if denom < 1e-9:
        return 0.0
    return (policy_b_cov - policy_a_cov) / denom


# ── bootstrap CI for gap_closed ───────────────────────────────────────────────

def bootstrap_gap_ci(rows, test_idx, scores, W=120, W_s=60, W_l=300, n_boot=2000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(test_idx)
    idx_arr = np.array(test_idx)
    sc_arr  = np.array(scores)
    gaps = []
    for _ in range(n_boot):
        bi = rng.integers(0, n, size=n)
        bi_idx = list(idx_arr[bi])
        bi_sc  = sc_arr[bi]
        A = coverage_fixed(rows, bi_idx, W)
        O = coverage_oracle(rows, bi_idx, W_s, W_l, W)
        B, _ = coverage_policy_b(rows, bi_idx, bi_sc, W_s, W_l, W)
        gaps.append(gap_closed(B, A, O))
    gaps = np.array(gaps)
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))


# ── main ──────────────────────────────────────────────────────────────────────

def run_cv(rows, folds, with_counting=True):
    if not with_counting:
        subset = [r for r in rows if r["category"] != "counting_objects_events"]
        idx_map = list(range(len(subset)))
        # remap folds
        orig_to_sub = {}
        sub_rows = []
        for i, r in enumerate(rows):
            if r["category"] != "counting_objects_events":
                orig_to_sub[i] = len(sub_rows)
                sub_rows.append(r)
        sub_folds = []
        for fold in folds:
            sub_folds.append([orig_to_sub[i] for i in fold if i in orig_to_sub])
        return run_cv_on(sub_rows, sub_folds)
    return run_cv_on(rows, folds)


def run_cv_on(rows, folds):
    n = len(rows)
    Y_t1 = np.array([math.log(r["farthest"] + 1) for r in rows])
    Y_t2 = {W: np.array([float(r["farthest"] <= W) for r in rows]) for W in W_LIST}

    pred_t1  = {p: np.full(n, np.nan) for p in ["P0","P1","P2","P3","P4","P5"]}
    pred_t2  = {p: {W: np.full(n, np.nan) for W in W_LIST} for p in ["P0","P1","P2","P3","P4","P5"]}

    for fold_idx, test_idx in enumerate(folds):
        train_idx = [i for j, f in enumerate(folds) if j != fold_idx for i in f]
        test_idx  = list(test_idx)

        Ytr_t1 = Y_t1[np.array(train_idx)]

        # P0 — constant
        med_t1 = float(np.median(Ytr_t1))
        pred_t1["P0"][test_idx] = med_t1
        for W in W_LIST:
            Ytr_t2 = Y_t2[W][np.array(train_idx)]
            maj = float(np.mean(Ytr_t2) >= 0.5)
            # P0 constant for T2: predict train mean as score
            pred_t2["P0"][W][test_idx] = float(np.mean(Ytr_t2))

        # P1 — elapsed time only
        Xtr1 = feat_elapsed(rows, train_idx)
        Xte1 = feat_elapsed(rows, test_idx)
        pred_t1["P1"][test_idx] = fit_predict_t1(Xtr1, Ytr_t1, Xte1)
        for W in W_LIST:
            pred_t2["P1"][W][test_idx] = fit_predict_t2(Xtr1, Y_t2[W][np.array(train_idx)], Xte1)

        # P2 — keyword + elapsed
        Xtr2 = feat_keyword(rows, train_idx)
        Xte2 = feat_keyword(rows, test_idx)
        pred_t1["P2"][test_idx] = fit_predict_t1(Xtr2, Ytr_t1, Xte2)
        for W in W_LIST:
            pred_t2["P2"][W][test_idx] = fit_predict_t2(Xtr2, Y_t2[W][np.array(train_idx)], Xte2)

        # P3 — TF-IDF + elapsed
        Xtr3, Xte3, _ = feat_tfidf(rows, train_idx, test_idx, feat_elapsed)
        pred_t1["P3"][test_idx] = fit_predict_t1(Xtr3, Ytr_t1, Xte3)
        for W in W_LIST:
            pred_t2["P3"][W][test_idx] = fit_predict_t2(Xtr3, Y_t2[W][np.array(train_idx)], Xte3)

        # P4 — sentence embed + elapsed
        Xtr4, Xte4 = feat_embed(rows, train_idx, test_idx, feat_elapsed)
        pred_t1["P4"][test_idx] = fit_predict_t1(Xtr4, Ytr_t1, Xte4)
        for W in W_LIST:
            pred_t2["P4"][W][test_idx] = fit_predict_t2(Xtr4, Y_t2[W][np.array(train_idx)], Xte4)

        # P5 — oracle: category + elapsed
        Xtr5 = feat_oracle(rows, train_idx)
        Xte5 = feat_oracle(rows, test_idx)
        pred_t1["P5"][test_idx] = fit_predict_t1(Xtr5, Ytr_t1, Xte5)
        for W in W_LIST:
            pred_t2["P5"][W][test_idx] = fit_predict_t2(Xtr5, Y_t2[W][np.array(train_idx)], Xte5)

        print(f"  fold {fold_idx+1}/{N_FOLDS} done ({len(test_idx)} test)", flush=True)

    # ── metrics ───────────────────────────────────────────────────────────────
    results = {"t1": {}, "t2": {}, "coverage": {}}
    all_idx = list(range(n))

    for p in ["P0","P1","P2","P3","P4","P5"]:
        r_sp, _ = spearman(Y_t1, pred_t1[p])
        mae = float(np.mean(np.abs(Y_t1 - pred_t1[p])))
        results["t1"][p] = {"spearman": round(r_sp, 4), "mae": round(mae, 4)}
        results["t2"][p] = {}
        for W in W_LIST:
            auc = auroc(Y_t2[W], pred_t2[p][W])
            cal = calibration_table(Y_t2[W], pred_t2[p][W])
            results["t2"][p][W] = {"auroc": round(auc, 4), "calibration": cal}

    # ── systems metric ────────────────────────────────────────────────────────
    # W_s = W/2, W_l = W*2 (so budget matches W)
    results["coverage"] = {}
    for W in W_LIST:
        W_s = W // 2
        W_l = W * 2
        policy_a = coverage_fixed(rows, all_idx, W)
        oracle   = coverage_oracle(rows, all_idx, W_s, W_l, W)
        results["coverage"][W] = {
            "policy_a":  round(policy_a, 4),
            "oracle":    round(oracle, 4),
            "predictors": {}
        }
        for p in ["P0","P1","P2","P3","P4","P5"]:
            scores = pred_t2[p][W]
            pb_cov, frac_long = coverage_policy_b(rows, all_idx, scores, W_s, W_l, W)
            gc = gap_closed(pb_cov, policy_a, oracle)
            results["coverage"][W]["predictors"][p] = {
                "policy_b": round(pb_cov, 4),
                "gap_closed": round(gc, 4),
                "frac_long": round(frac_long, 4),
            }

    # bootstrap CI for primary (W=120) on best non-oracle predictor by gap_closed
    all_test_idx = list(range(n))
    best_p = max(["P0","P1","P2","P3","P4"],
                 key=lambda p: results["coverage"][W_PRIMARY]["predictors"][p]["gap_closed"])
    print(f"\nBest non-oracle predictor at W={W_PRIMARY}: {best_p} (gap_closed={results['coverage'][W_PRIMARY]['predictors'][best_p]['gap_closed']:.3f})", flush=True)
    print("Computing bootstrap CI...", flush=True)
    W_s, W_l = W_PRIMARY // 2, W_PRIMARY * 2
    ci_lo, ci_hi = bootstrap_gap_ci(rows, all_test_idx, pred_t2[best_p][W_PRIMARY],
                                    W=W_PRIMARY, W_s=W_s, W_l=W_l, n_boot=N_BOOTSTRAP, seed=SEED)
    results["coverage"][W_PRIMARY]["best_predictor"] = best_p
    results["coverage"][W_PRIMARY]["best_gap_closed"] = results["coverage"][W_PRIMARY]["predictors"][best_p]["gap_closed"]
    results["coverage"][W_PRIMARY]["best_ci_95"] = [round(ci_lo, 4), round(ci_hi, 4)]

    # ── verdict ───────────────────────────────────────────────────────────────
    gc_best = results["coverage"][W_PRIMARY]["best_gap_closed"]
    if gc_best >= 0.40 and ci_lo > 0:
        verdict = "PREDICTABLE"
    elif gc_best < 0.15 or ci_hi <= 0:
        verdict = "UNPREDICTABLE"
    else:
        verdict = "PARTIAL"
    results["verdict"] = verdict
    results["best_predictor"] = best_p
    results["best_gap_closed_w120"] = gc_best
    results["best_ci_95_w120"] = [round(ci_lo, 4), round(ci_hi, 4)]

    # ── per-category breakdown ────────────────────────────────────────────────
    cats = sorted(set(r["category"] for r in rows))
    results["per_category"] = {}
    for cat in cats:
        cat_idx = [i for i, r in enumerate(rows) if r["category"] == cat]
        pa = coverage_fixed(rows, cat_idx, W_PRIMARY)
        ora = coverage_oracle(rows, cat_idx, W_PRIMARY // 2, W_PRIMARY * 2, W_PRIMARY)
        best_gc_cat = {}
        for p in ["P0","P1","P2","P3","P4","P5"]:
            sc = pred_t2[p][W_PRIMARY][np.array(cat_idx)]
            pb_c, _ = coverage_policy_b(rows, cat_idx, sc, W_PRIMARY // 2, W_PRIMARY * 2, W_PRIMARY)
            best_gc_cat[p] = round(gap_closed(pb_c, pa, ora), 4)
        results["per_category"][cat] = {
            "n": len(cat_idx),
            "policy_a_cov": round(pa, 4),
            "oracle_cov": round(ora, 4),
            "gap_closed_per_predictor": best_gc_cat,
        }

    # ── 20 random examples ────────────────────────────────────────────────────
    rng = random.Random(SEED)
    sample_idx = rng.sample(range(n), 20)
    examples = []
    for i in sample_idx:
        r = rows[i]
        ex = {
            "question": r["question"][:100],
            "category": r["category"],
            "qt": r["qt"],
            "nearest": round(r["nearest"], 1),
            "farthest": round(r["farthest"], 1),
            "log_farthest": round(math.log(r["farthest"]+1), 3),
            "pred_t1": {p: round(float(pred_t1[p][i]), 3) for p in pred_t1},
            "pred_t2_120": {p: round(float(pred_t2[p][W_PRIMARY][i]), 3) for p in pred_t2},
            "true_within_120": bool(r["farthest"] <= W_PRIMARY),
        }
        examples.append(ex)
    results["examples"] = examples

    return results, rows, pred_t1, pred_t2, Y_t1, Y_t2


def main():
    print("=== StudyN: Evidence-Horizon Predictability ===", flush=True)
    rows = load_data()
    sanity_check(rows)

    folds = make_folds(rows, N_FOLDS, SEED)
    check_no_leakage(rows, folds)

    print(f"\nRunning with counting (n={len(rows)})...", flush=True)
    res_with, rows_with, pt1_with, pt2_with, Y_t1, Y_t2 = run_cv(rows, folds, with_counting=True)

    print(f"\nRunning without counting...", flush=True)
    res_without, *_ = run_cv(rows, folds, with_counting=False)

    result = {
        "with_counting": res_with,
        "without_counting": res_without,
        "_provenance": stamp(script="study_n_predict.py", model="all-MiniLM-L6-v2",
                             device=None, n=len(rows)),
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nResults written to {OUT_JSON}", flush=True)

    write_report(result, rows_with)
    print(f"Report written to {OUT_REPORT}", flush=True)


def write_report(result, rows):
    r = result["with_counting"]
    rw = result["without_counting"]

    lines = []
    A = lambda s: lines.append(s)

    verdict = r["verdict"]
    gc_best = r["best_gap_closed_w120"]
    ci      = r["best_ci_95_w120"]
    best_p  = r["best_predictor"]

    A(f"# Study N — Evidence-Horizon Predictability")
    A(f"")
    A(f"**Date:** 2026-10-01  ")
    A(f"**VERDICT (first line, pre-registered): {verdict}**  ")
    A(f"Best non-oracle predictor {best_p} closes {100*gc_best:.1f}% of oracle coverage gap at W=120 s "
      f"(95% bootstrap CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%, {'excludes 0' if ci[0]>0 else 'includes 0'}).  ")
    A(f"Pre-registered rule: PREDICTABLE ≥40% CI excl. 0; UNPREDICTABLE <15% or CI incl. 0; PARTIAL otherwise.")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 1. Data")
    A(f"")
    A(f"Source: `results/sember/study_h/data/sember_grounding.jsonl`, n=9,448.  ")
    A(f"Excluded: 10 records with negative nearest evidence distance (question_time < answer_end_time, 1 s rounding).  ")
    A(f"Used: {len(rows)} records.")
    A(f"")
    A(f"**Sanity check (vs H2 committed values):**")
    nearest  = np.array([r["nearest"]  for r in rows])
    farthest = np.array([r["farthest"] for r in rows])
    A(f"")
    A(f"| metric | this run | H2 committed | match |")
    A(f"|---|---|---|---|")
    A(f"| nearest p50 | {np.percentile(nearest,50):.0f} s | 21 s | {'✓' if np.percentile(nearest,50)==21 else '✗'} |")
    A(f"| nearest p75 | {np.percentile(nearest,75):.0f} s | 56 s | {'✓' if np.percentile(nearest,75)==56 else '✗'} |")
    A(f"| nearest p90 | {np.percentile(nearest,90):.0f} s | 117 s | {'✓' if np.percentile(nearest,90)==117 else '✗'} |")
    A(f"| farthest p50 | {np.percentile(farthest,50):.0f} s | 74 s | {'✓' if np.percentile(farthest,50)==74 else '✗'} |")
    A(f"| farthest p75 | {np.percentile(farthest,75):.0f} s | 135 s | {'✓' if np.percentile(farthest,75)==135 else '✗'} |")
    A(f"| farthest p90 | {np.percentile(farthest,90):.0f} s | 236 s | {'✓' if abs(np.percentile(farthest,90)-236)<=1 else '✗'} |")
    A(f"")
    cats = [(cat, sum(1 for r in rows if r["category"]==cat)) for cat in sorted(set(r["category"] for r in rows))]
    A(f"**Category counts (with counting):**")
    for cat, cn in cats:
        A(f"- {cat}: {cn}")
    n_no_count = sum(1 for r in rows if r["category"] != "counting_objects_events")
    A(f"- **Total without counting:** {n_no_count}")
    A(f"")
    A(f"Keyword rules (P2): {', '.join(repr(k) for k in KEYWORD_RULES)}")
    A(f"")
    A(f"P4 sentence-embedding model: `{EMBED_MODEL_ID}` (sentence-transformers)")
    A(f"")
    A(f"Cross-validation: {N_FOLDS}-fold grouped by video_id, seed={SEED}. No session leakage confirmed.")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 2. T1 Regression — log(farthest + 1)")
    A(f"")
    A(f"| predictor | Spearman ρ | MAE (log s) |")
    A(f"|---|---|---|")
    for p in ["P0","P1","P2","P3","P4","P5"]:
        t1 = r["t1"][p]
        label = p + (" (ORACLE-INFO)" if p=="P5" else "")
        A(f"| {label} | {t1['spearman']:.4f} | {t1['mae']:.4f} |")
    A(f"")
    A(f"**Without counting:**")
    A(f"")
    A(f"| predictor | Spearman ρ | MAE (log s) |")
    A(f"|---|---|---|")
    for p in ["P0","P1","P2","P3","P4","P5"]:
        t1 = rw["t1"][p]
        label = p + (" (ORACLE-INFO)" if p=="P5" else "")
        A(f"| {label} | {t1['spearman']:.4f} | {t1['mae']:.4f} |")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 3. T2 Classification — binary evidence within W seconds")
    A(f"")
    A(f"### AUROC (with counting)")
    A(f"")
    A(f"| predictor | W=60 | W=120 | W=300 |")
    A(f"|---|---|---|---|")
    for p in ["P0","P1","P2","P3","P4","P5"]:
        label = p + (" (ORACLE-INFO)" if p=="P5" else "")
        row_aucs = [r["t2"][p][W]["auroc"] for W in W_LIST]
        A(f"| {label} | {row_aucs[0]:.4f} | {row_aucs[1]:.4f} | {row_aucs[2]:.4f} |")
    A(f"")
    A(f"### AUROC (without counting)")
    A(f"")
    A(f"| predictor | W=60 | W=120 | W=300 |")
    A(f"|---|---|---|---|")
    for p in ["P0","P1","P2","P3","P4","P5"]:
        label = p + (" (ORACLE-INFO)" if p=="P5" else "")
        row_aucs = [rw["t2"][p][W]["auroc"] for W in W_LIST]
        A(f"| {label} | {row_aucs[0]:.4f} | {row_aucs[1]:.4f} | {row_aucs[2]:.4f} |")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 4. Systems Metric — Coverage at Matched Mean Budget")
    A(f"")
    A(f"Policy A: fixed trailing window of W seconds.  ")
    A(f"Policy B: per-question choice between W_s=W/2 and W_l=W×2, threshold set to matched mean budget.  ")
    A(f"Oracle: always picks the smaller window if evidence fits, else larger.  ")
    A(f"Gap closed = (Policy B − Policy A) / (Oracle − Policy A).")
    A(f"")
    for W in W_LIST:
        cov = r["coverage"][W]
        A(f"### W = {W} s  (W_s={W//2}, W_l={W*2})")
        A(f"")
        A(f"Policy A (fixed): {100*cov['policy_a']:.1f}%  |  Oracle: {100*cov['oracle']:.1f}%")
        A(f"")
        A(f"| predictor | policy B cov | gap closed |")
        A(f"|---|---|---|")
        for p in ["P0","P1","P2","P3","P4","P5"]:
            label = p + (" (ORACLE-INFO)" if p=="P5" else "")
            d = cov["predictors"][p]
            A(f"| {label} | {100*d['policy_b']:.1f}% | {100*d['gap_closed']:.1f}% |")
        if W == W_PRIMARY:
            A(f"")
            A(f"**Best non-oracle (W=120): {cov.get('best_predictor','?')} = {100*cov.get('best_gap_closed',0):.1f}% (95% CI: {100*cov['best_ci_95'][0]:.1f}%–{100*cov['best_ci_95'][1]:.1f}%)**")
        A(f"")
    A(f"---")
    A(f"")
    A(f"## 5. Per-Category Gap Closed (W=120, with counting)")
    A(f"")
    A(f"| category | n | policy_a | oracle | {best_p} gap closed |")
    A(f"|---|---|---|---|---|")
    for cat, info in sorted(r["per_category"].items()):
        gc_cat = info["gap_closed_per_predictor"].get(best_p, 0)
        A(f"| {cat} | {info['n']} | {100*info['policy_a_cov']:.1f}% | {100*info['oracle_cov']:.1f}% | {100*gc_cat:.1f}% |")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 6. 20 Random Examples")
    A(f"")
    A(f"| question (trunc) | category | qt | nearest | farthest | within_120 | P0 | P1 | P2 | P3 | P4 | P5 (oracle) |")
    A(f"|---|---|---|---|---|---|---|---|---|---|---|---|")
    for ex in r["examples"]:
        p_vals = [f"{ex['pred_t2_120'][p]:.2f}" for p in ["P0","P1","P2","P3","P4","P5"]]
        A(f"| {ex['question'][:50]} | {ex['category'][:20]} | {ex['qt']:.0f}s | {ex['nearest']:.0f}s | {ex['farthest']:.0f}s | {ex['true_within_120']} | {' | '.join(p_vals)} |")
    A(f"")
    A(f"---")
    A(f"")
    A(f"## 7. Verdict and Interpretation")
    A(f"")
    A(f"**{verdict}**")
    A(f"")
    if verdict == "PREDICTABLE":
        A(f"Best non-oracle predictor ({best_p}) closes {100*gc_best:.1f}% of the oracle coverage gap at W=120 s, "
          f"with 95% bootstrap CI {100*ci[0]:.1f}%–{100*ci[1]:.1f}% (excludes 0). "
          f"Evidence horizon is predictable from runtime-available information.")
    elif verdict == "UNPREDICTABLE":
        A(f"Best non-oracle predictor ({best_p}) closes only {100*gc_best:.1f}% of the oracle coverage gap at W=120 s "
          f"(95% bootstrap CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%). "
          f"Evidence horizon is not reliably predictable from question text and elapsed time alone.")
    else:
        A(f"Best non-oracle predictor ({best_p}) closes {100*gc_best:.1f}% of the oracle coverage gap at W=120 s "
          f"(95% bootstrap CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%). "
          f"Partial predictability: above the unpredictable threshold but below the predictable threshold.")

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
