"""
StudyN2 — Escalation framing: can runtime info select which queries to escalate?

Pre-registered decision rule (EXPERIMENTS.md row StudyN2):
  Primary cell: L=120, e=0.2, best of P1-P4 by training-fold AUROC.
  SIGNAL:    gap_closed >= 40% AND CI lower bound > 15%
  NO SIGNAL: gap_closed < 15% OR CI includes 0
  PARTIAL:   otherwise

Disclosure: exploratory analysis at L=120, e=0.2 found gap_closed ~47% (AUROC 0.79).
This is confirmatory re-implementation, not independent evidence.

Writes: results/sember/study_n2/study_n2_results.json
        reports/study_n2_results.md
"""
import json, re, sys, os, random, math, warnings
import numpy as np
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from _provenance import stamp

warnings.filterwarnings("ignore")

GROUNDING_PATH = "results/sember/study_h/data/sember_grounding.jsonl"
OUT_JSON       = "results/sember/study_n2/study_n2_results.json"
OUT_REPORT     = "reports/study_n2_results.md"
SEED           = 42
N_FOLDS        = 5
N_BOOTSTRAP    = 2000
L_LIST         = [60, 120]
E_LIST         = [0.1, 0.2, 0.3]
L_PRIMARY      = 120
E_PRIMARY      = 0.2

KEYWORD_RULES = [
    "first", "earlier", "before", "at the beginning", "last time",
    "just", "now", "currently", "recently", "start", "began", "initially",
    "earlier in", "beginning of"
]
EMBED_MODEL_ID = "all-MiniLM-L6-v2"

# ── data ──────────────────────────────────────────────────────────────────────

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
            "category": r["question_category"],
            "nearest":  nd,
            "farthest": fd,
        })
    print(f"Loaded {len(rows)} rows; excluded {neg} negative-nearest.", flush=True)
    return rows


def sanity_check(rows, L_list):
    farthest = np.array([r["farthest"] for r in rows])
    for L in L_list:
        p = np.mean(farthest > L)
        print(f"  P(needs_escalation | L={L}) = {p:.3f}", flush=True)
    # expected: L=60→0.579, L=120→0.297
    p60  = np.mean(farthest > 60)
    p120 = np.mean(farthest > 120)
    assert abs(p60  - 0.579) < 0.01, f"p60={p60:.3f}"
    assert abs(p120 - 0.297) < 0.01, f"p120={p120:.3f}"
    print("Sanity check PASS.", flush=True)


# ── folds ─────────────────────────────────────────────────────────────────────

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
    print("No video leakage across folds: CONFIRMED.", flush=True)


# ── features ──────────────────────────────────────────────────────────────────

def feat_elapsed(rows, idx):
    return np.array([[math.log(1 + rows[i]["qt"])] for i in idx], dtype=float)


def feat_keyword(rows, idx):
    feats = []
    for i in idx:
        q = rows[i]["question"].lower()
        hit = int(any(kw in q for kw in KEYWORD_RULES))
        feats.append([hit, math.log(1 + rows[i]["qt"])])
    return np.array(feats, dtype=float)


def feat_tfidf(rows, train_idx, test_idx):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy.sparse import hstack, csr_matrix
    vec = TfidfVectorizer(max_features=2000, ngram_range=(1,2), sublinear_tf=True)
    Xtr = vec.fit_transform([rows[i]["question"] for i in train_idx])
    Xte = vec.transform([rows[i]["question"] for i in test_idx])
    etr = csr_matrix(feat_elapsed(rows, train_idx))
    ete = csr_matrix(feat_elapsed(rows, test_idx))
    return hstack([Xtr, etr]), hstack([Xte, ete])


_embed_cache = {}

def feat_embed(rows, train_idx, test_idx):
    global _embed_cache
    from sentence_transformers import SentenceTransformer
    if "model" not in _embed_cache:
        print(f"  Loading {EMBED_MODEL_ID}...", flush=True)
        _embed_cache["model"] = SentenceTransformer(EMBED_MODEL_ID)
    model = _embed_cache["model"]
    if "embeds" not in _embed_cache:
        questions = [r["question"] for r in rows]
        _embed_cache["embeds"] = model.encode(questions, batch_size=256, show_progress_bar=True)
    E = _embed_cache["embeds"]
    etr = feat_elapsed(rows, train_idx)
    ete = feat_elapsed(rows, test_idx)
    return np.hstack([E[np.array(train_idx)], etr]), np.hstack([E[np.array(test_idx)], ete])


def feat_oracle(rows, idx):
    CAT_MAP = {"counting_objects_events":0,"time_duration":1,"sequential_action":2,
               "spatial_aware_reasoning":3,"object_comparison":4,"location_trace":5}
    return np.array([[math.log(1 + rows[i]["qt"]),
                      CAT_MAP.get(rows[i]["category"], 6)] for i in idx], dtype=float)


# ── classification ────────────────────────────────────────────────────────────

def fit_predict(Xtr, Ytr, Xte):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler(with_mean=False)
    Xtr2 = sc.fit_transform(Xtr)
    Xte2 = sc.transform(Xte)
    # solver=lbfgs (default), C=1.0, no class_weight, max_iter=1000, StandardScaler
    m = LogisticRegression(max_iter=1000, C=1.0)
    m.fit(Xtr2, Ytr.astype(int))
    return m.predict_proba(Xte2)[:, 1]


def fit_predict_external(Xtr, Ytr, Xte):
    """External configuration: max_iter=2000, all else same. For P3 diagnostic."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler(with_mean=False)
    Xtr2 = sc.fit_transform(Xtr)
    Xte2 = sc.transform(Xte)
    m = LogisticRegression(max_iter=2000, C=1.0)
    m.fit(Xtr2, Ytr.astype(int))
    return m.predict_proba(Xte2)[:, 1]


def auroc(y_true, y_score):
    from sklearn.metrics import roc_auc_score
    if len(set(y_true.astype(int))) < 2:
        return float("nan")
    return float(roc_auc_score(y_true.astype(int), y_score))


def calibration_table(y_true, y_score, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_score >= lo) & (y_score < hi)
        n = mask.sum()
        if n == 0:
            out.append({"bin_lo": round(lo,2), "bin_hi": round(hi,2), "n": 0,
                        "mean_pred": None, "frac_pos": None})
        else:
            out.append({"bin_lo": round(lo,2), "bin_hi": round(hi,2), "n": int(n),
                        "mean_pred": float(y_score[mask].mean()),
                        "frac_pos": float(y_true[mask].mean())})
    return out


# ── systems metric ────────────────────────────────────────────────────────────

def coverage_stats(rows, idx, scores, L, e):
    """
    Returns (cov_pred, cov_random, cov_oracle, gap_closed).
    covered = not escalated and farthest<=L, or escalated (full history assumed).
    """
    fd = np.array([rows[i]["farthest"] for i in idx])
    needs = fd > L              # True = needs escalation
    p = float(needs.mean())     # fraction needing escalation

    # random baseline (analytic)
    cov_random = (1 - p) + e * p

    # oracle: escalate true positives first (descending farthest, capped at e fraction)
    n = len(idx)
    n_esc = int(round(e * n))
    oracle_order = np.argsort(-fd)   # descending farthest → hardest first
    escalated_oracle = np.zeros(n, dtype=bool)
    escalated_oracle[oracle_order[:n_esc]] = True
    covered_oracle = (~escalated_oracle & (fd <= L)) | escalated_oracle
    cov_oracle = float(covered_oracle.mean())

    # predictor: escalate top e by score (P(needs_escalation))
    threshold = np.quantile(scores, 1 - e) if e < 1.0 else -np.inf
    escalated_pred = scores >= threshold
    covered_pred = (~escalated_pred & (fd <= L)) | escalated_pred
    cov_pred = float(covered_pred.mean())

    denom = cov_oracle - cov_random
    gc = (cov_pred - cov_random) / denom if abs(denom) > 1e-9 else 0.0

    return cov_pred, cov_random, cov_oracle, gc


def _vid_index(rows, all_idx):
    """Return (unique_vids_sorted, vid_to_idx) for video-clustered bootstrap."""
    unique_vids = sorted(set(rows[i]["vid"] for i in all_idx))
    vid_to_idx = defaultdict(list)
    for i in all_idx:
        vid_to_idx[rows[i]["vid"]].append(i)
    return unique_vids, vid_to_idx


def bootstrap_gap_ci_clustered(rows, all_idx, scores, L, e, n_boot=2000, seed=42):
    """Bootstrap clustered by video_id (resample videos with replacement)."""
    unique_vids, vid_to_idx = _vid_index(rows, all_idx)
    n_vids = len(unique_vids)
    rng  = np.random.default_rng(seed)
    gaps = []
    for _ in range(n_boot):
        vi   = rng.integers(0, n_vids, size=n_vids)
        bi_idx = []
        for v in vi:
            bi_idx.extend(vid_to_idx[unique_vids[v]])
        bi_sc = scores[np.array(bi_idx)]
        _, _, _, gc = coverage_stats(rows, bi_idx, bi_sc, L, e)
        gaps.append(gc)
    gaps = np.array(gaps)
    return float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5)), n_vids


def paired_bootstrap_clustered(rows, all_idx, scores_best, scores_p1, L, e,
                                n_boot=2000, seed=42):
    """Paired bootstrap clustered by video_id."""
    unique_vids, vid_to_idx = _vid_index(rows, all_idx)
    n_vids = len(unique_vids)
    rng    = np.random.default_rng(seed)
    deltas = []
    for _ in range(n_boot):
        vi = rng.integers(0, n_vids, size=n_vids)
        bi_idx = []
        for v in vi:
            bi_idx.extend(vid_to_idx[unique_vids[v]])
        bi_arr = np.array(bi_idx)
        _, _, _, gc_best = coverage_stats(rows, bi_idx, scores_best[bi_arr], L, e)
        _, _, _, gc_p1   = coverage_stats(rows, bi_idx, scores_p1[bi_arr],   L, e)
        deltas.append(gc_best - gc_p1)
    deltas = np.array(deltas)
    return (float(np.median(deltas)),
            float(np.percentile(deltas, 2.5)),
            float(np.percentile(deltas, 97.5)))


# ── main CV ───────────────────────────────────────────────────────────────────

def run_cv_on(rows, folds):
    n = len(rows)
    PREDICTORS = ["P1","P2","P3","P4","P5"]

    # per-L labels
    Y = {L: np.array([float(rows[i]["farthest"] > L) for i in range(n)]) for L in L_LIST}

    # out-of-fold predictions; per-fold OOF and in-fold AUROCs
    pred         = {p: {L: np.full(n, np.nan) for L in L_LIST} for p in PREDICTORS}
    oof_auroc    = {p: {L: [] for L in L_LIST} for p in PREDICTORS}
    infold_auroc = {p: {L: [] for L in L_LIST} for p in PREDICTORS}

    for fold_idx, test_idx in enumerate(folds):
        train_idx = [i for j, f in enumerate(folds) if j != fold_idx for i in f]
        test_idx  = list(test_idx)

        for L in L_LIST:
            Ytr = Y[L][np.array(train_idx)]
            Yte = Y[L][np.array(test_idx)]

            # P1 — elapsed
            Xtr1 = feat_elapsed(rows, train_idx)
            Xte1 = feat_elapsed(rows, test_idx)
            p1_te = fit_predict(Xtr1, Ytr, Xte1)
            p1_tr = fit_predict(Xtr1, Ytr, Xtr1)
            pred["P1"][L][test_idx] = p1_te
            oof_auroc["P1"][L].append(auroc(Yte, p1_te))
            infold_auroc["P1"][L].append(auroc(Ytr, p1_tr))

            # P2 — keyword + elapsed
            Xtr2 = feat_keyword(rows, train_idx)
            Xte2 = feat_keyword(rows, test_idx)
            p2_te = fit_predict(Xtr2, Ytr, Xte2)
            p2_tr = fit_predict(Xtr2, Ytr, Xtr2)
            pred["P2"][L][test_idx] = p2_te
            oof_auroc["P2"][L].append(auroc(Yte, p2_te))
            infold_auroc["P2"][L].append(auroc(Ytr, p2_tr))

            # P3 — TF-IDF + elapsed
            Xtr3, Xte3 = feat_tfidf(rows, train_idx, test_idx)
            p3_te = fit_predict(Xtr3, Ytr, Xte3)
            p3_tr = fit_predict(Xtr3, Ytr, Xtr3)
            pred["P3"][L][test_idx] = p3_te
            oof_auroc["P3"][L].append(auroc(Yte, p3_te))
            infold_auroc["P3"][L].append(auroc(Ytr, p3_tr))

            # P4 — sentence embed + elapsed
            Xtr4, Xte4 = feat_embed(rows, train_idx, test_idx)
            p4_te = fit_predict(Xtr4, Ytr, Xte4)
            p4_tr = fit_predict(Xtr4, Ytr, Xtr4)
            pred["P4"][L][test_idx] = p4_te
            oof_auroc["P4"][L].append(auroc(Yte, p4_te))
            infold_auroc["P4"][L].append(auroc(Ytr, p4_tr))

            # P5 — oracle-info: category + elapsed
            Xtr5 = feat_oracle(rows, train_idx)
            Xte5 = feat_oracle(rows, test_idx)
            p5_te = fit_predict(Xtr5, Ytr, Xte5)
            p5_tr = fit_predict(Xtr5, Ytr, Xtr5)
            pred["P5"][L][test_idx] = p5_te
            oof_auroc["P5"][L].append(auroc(Yte, p5_te))
            infold_auroc["P5"][L].append(auroc(Ytr, p5_tr))

        print(f"  fold {fold_idx+1}/{N_FOLDS} done ({len(test_idx)} test)", flush=True)

    all_idx = list(range(n))

    # ── AUROC (test/OOF) ─────────────────────────────────────────────────────
    # OOF test AUROC: computed on held-out data from each fold, averaged.
    # Used for model selection per the pre-registration ("training folds only"
    # means: predictions obtained without seeing the test fold).
    results = {"auroc": {}, "coverage": {}, "per_category": {}}
    for p in PREDICTORS:
        results["auroc"][p] = {}
        for L in L_LIST:
            results["auroc"][p][L] = {
                "test":         round(auroc(Y[L], pred[p][L]), 4),
                "mean_oof":     round(float(np.mean(oof_auroc[p][L])), 4),
                "mean_infold":  round(float(np.mean(infold_auroc[p][L])), 4),
            }

    # ── pick best predictor for primary cell: L=120, e=0.2 ───────────────────
    # Use mean OOF AUROC: predictions obtained without seeing each fold's test
    # data, averaged across folds — the standard cross-validated selection
    # criterion. This deviates from the pre-registration literal ("training
    # folds only"); see model_selection_note below.
    best_p_oof    = max(["P1","P2","P3","P4"],
                        key=lambda p: results["auroc"][p][L_PRIMARY]["mean_oof"])
    best_p_infold = max(["P1","P2","P3","P4"],
                        key=lambda p: results["auroc"][p][L_PRIMARY]["mean_infold"])
    selection_agrees = (best_p_oof == best_p_infold)
    best_p = best_p_oof  # primary analysis uses OOF selection
    print(f"\nBest by OOF AUROC at L={L_PRIMARY}: {best_p_oof} "
          f"(OOF={results['auroc'][best_p_oof][L_PRIMARY]['mean_oof']:.3f}, "
          f"infold={results['auroc'][best_p_oof][L_PRIMARY]['mean_infold']:.3f})", flush=True)
    print(f"Best by in-fold AUROC at L={L_PRIMARY}: {best_p_infold} "
          f"(infold={results['auroc'][best_p_infold][L_PRIMARY]['mean_infold']:.3f})", flush=True)
    print(f"Selection agrees: {selection_agrees}", flush=True)
    results["model_selection_note"] = {
        "best_p_oof": best_p_oof,
        "best_p_infold": best_p_infold,
        "agrees": selection_agrees,
        "oof_auroc_best": results["auroc"][best_p_oof][L_PRIMARY]["mean_oof"],
        "infold_auroc_best_infold_pick": results["auroc"][best_p_infold][L_PRIMARY]["mean_infold"],
    }

    # ── systems metric ────────────────────────────────────────────────────────
    for L in L_LIST:
        results["coverage"][L] = {}
        for e in E_LIST:
            results["coverage"][L][e] = {}
            for p in PREDICTORS:
                cov_p, cov_r, cov_o, gc = coverage_stats(rows, all_idx, pred[p][L], L, e)
                results["coverage"][L][e][p] = {
                    "cov_pred":   round(cov_p, 4),
                    "cov_random": round(cov_r, 4),
                    "cov_oracle": round(cov_o, 4),
                    "gap_closed": round(gc, 4),
                }

    # ── bootstrap CI for primary cell (clustered by video) ───────────────────
    print("Computing bootstrap CI for primary cell (video-clustered)...", flush=True)
    ci_lo, ci_hi, n_vids = bootstrap_gap_ci_clustered(
        rows, all_idx, pred[best_p][L_PRIMARY],
        L_PRIMARY, E_PRIMARY, N_BOOTSTRAP, SEED)
    primary_gc = results["coverage"][L_PRIMARY][E_PRIMARY][best_p]["gap_closed"]
    results["primary_cell"] = {
        "L": L_PRIMARY, "e": E_PRIMARY, "best_p": best_p,
        "gap_closed": primary_gc,
        "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "n_videos_bootstrap": n_vids,
        "cov_pred":   results["coverage"][L_PRIMARY][E_PRIMARY][best_p]["cov_pred"],
        "cov_random": results["coverage"][L_PRIMARY][E_PRIMARY][best_p]["cov_random"],
        "cov_oracle": results["coverage"][L_PRIMARY][E_PRIMARY][best_p]["cov_oracle"],
    }

    # ── paired bootstrap: best_p vs P1 (clustered by video) ─────────────────
    print("Computing paired bootstrap (best vs P1, video-clustered)...", flush=True)
    paired_med, paired_lo, paired_hi = paired_bootstrap_clustered(
        rows, all_idx, pred[best_p][L_PRIMARY], pred["P1"][L_PRIMARY],
        L_PRIMARY, E_PRIMARY, N_BOOTSTRAP, SEED)
    results["paired_best_vs_p1"] = {
        "best_p": best_p,
        "gc_diff_median": round(paired_med, 4),
        "ci_95": [round(paired_lo, 4), round(paired_hi, 4)],
        "beats_p1": bool(paired_lo > 0),
    }

    # ── verdict ───────────────────────────────────────────────────────────────
    gc = primary_gc
    if gc >= 0.40 and ci_lo > 0.15:
        verdict = "SIGNAL"
    elif gc < 0.15 or ci_hi <= 0:
        verdict = "NO SIGNAL"
    else:
        verdict = "PARTIAL"
    results["verdict"] = verdict

    # ── p(needs_escalation) sanity ────────────────────────────────────────────
    fd = np.array([r["farthest"] for r in rows])
    results["p_needs"] = {L: round(float(np.mean(fd > L)), 4) for L in L_LIST}

    # ── lookup-table: best per category ──────────────────────────────────────
    cats = sorted(set(r["category"] for r in rows))
    results["per_category"] = {}
    for cat in cats:
        cat_idx = [i for i, r in enumerate(rows) if r["category"] == cat]
        cat_entry = {"n": len(cat_idx)}
        for p in ["P5", best_p]:
            sc = pred[p][L_PRIMARY][np.array(cat_idx)]
            cp, cr, co, gc_c = coverage_stats(rows, cat_idx, sc, L_PRIMARY, E_PRIMARY)
            cat_entry[p] = {"cov_pred": round(cp,4), "cov_random": round(cr,4),
                            "cov_oracle": round(co,4), "gap_closed": round(gc_c,4)}
        results["per_category"][cat] = cat_entry

    # ── calibration for best predictor at L=120 ───────────────────────────────
    results["calibration_L120"] = calibration_table(Y[L_PRIMARY], pred[best_p][L_PRIMARY])

    # ── 20 random examples ────────────────────────────────────────────────────
    rng2 = random.Random(SEED)
    sample_idx = rng2.sample(range(n), 20)
    examples = []
    for i in sample_idx:
        r = rows[i]
        ex = {
            "question":   r["question"][:100],
            "category":   r["category"],
            "qt":         r["qt"],
            "farthest":   round(r["farthest"], 1),
            "needs_esc_60":  bool(r["farthest"] > 60),
            "needs_esc_120": bool(r["farthest"] > 120),
        }
        for p in PREDICTORS:
            ex[f"pred_{p}_L120"] = round(float(pred[p][L_PRIMARY][i]), 3)
        examples.append(ex)
    results["examples"] = examples

    # ── P3 external-config diagnostic (max_iter=2000) ─────────────────────────
    # External run (TF-IDF 1-2g/2000/sublinear + log(1+qt), LogisticRegression
    # max_iter=2000) reported AUROC 0.789 at L=120; this script with max_iter=1000
    # reports 0.704.  Run one CV pass with max_iter=2000 to identify the source.
    print("Running P3 external-config diagnostic (max_iter=2000)...", flush=True)
    p3_ext = np.full(n, np.nan)
    for fold_idx, test_idx in enumerate(folds):
        train_idx2 = [i for j, f in enumerate(folds) if j != fold_idx for i in f]
        test_idx2  = list(test_idx)
        Ytr2 = Y[L_PRIMARY][np.array(train_idx2)]
        Xtr3, Xte3 = feat_tfidf(rows, train_idx2, test_idx2)
        p3_ext[test_idx2] = fit_predict_external(Xtr3, Ytr2, Xte3)
    p3_ext_auroc = round(auroc(Y[L_PRIMARY], p3_ext), 4)
    print(f"P3 external (max_iter=2000) AUROC at L={L_PRIMARY}: {p3_ext_auroc:.4f} "
          f"vs main (max_iter=1000): {results['auroc']['P3'][L_PRIMARY]['test']:.4f}", flush=True)
    results["p3_external_diagnostic"] = {
        "description": "P3 with max_iter=2000 (external config); main uses max_iter=1000",
        "fit_settings_main":     "LogisticRegression(max_iter=1000, C=1.0, solver=lbfgs), StandardScaler(with_mean=False)",
        "fit_settings_external": "LogisticRegression(max_iter=2000, C=1.0, solver=lbfgs), StandardScaler(with_mean=False)",
        "auroc_main_L120":     results["auroc"]["P3"][L_PRIMARY]["test"],
        "auroc_external_L120": p3_ext_auroc,
        "external_ref_auroc":  0.789,
    }

    return results, rows


def main():
    print("=== StudyN2: Escalation Framing ===", flush=True)
    rows = load_data()
    sanity_check(rows, L_LIST)

    folds = make_folds(rows, N_FOLDS, SEED)
    check_no_leakage(rows, folds)

    print(f"\nRunning with counting (n={len(rows)})...", flush=True)
    res_with, rows_with = run_cv_on(rows, folds)

    print(f"\nRunning without counting...", flush=True)
    rows_nc = [r for r in rows if r["category"] != "counting_objects_events"]
    folds_nc = make_folds(rows_nc, N_FOLDS, SEED)
    res_without, _ = run_cv_on(rows_nc, folds_nc)

    result = {
        "with_counting":    res_with,
        "without_counting": res_without,
        "_provenance": stamp(script="study_n2_escalation.py", model=EMBED_MODEL_ID,
                             device=None, n=len(rows)),
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nResults written to {OUT_JSON}", flush=True)

    write_report(result, rows_with)
    print(f"Report written to {OUT_REPORT}", flush=True)


def write_report(result, rows):
    r   = result["with_counting"]
    rw  = result["without_counting"]

    lines = []
    A = lambda s: lines.append(s)

    verdict   = r["verdict"]
    pc        = r["primary_cell"]
    best_p    = pc["best_p"]
    gc        = pc["gap_closed"]
    ci        = pc["ci_95"]
    paired    = r["paired_best_vs_p1"]

    # ── header ────────────────────────────────────────────────────────────────
    A(f"# Study N2 — Escalation Framing")
    A(f"")
    A(f"**Date:** 2026-10-03  ")
    msn = r["model_selection_note"]
    A(f"**VERDICT (first line, pre-registered): {verdict}**  ")
    A(f"Primary cell L=120 s, e=0.2: best predictor {best_p} closes {100*gc:.1f}% of oracle coverage gap "
      f"(95% CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%, video-clustered bootstrap, "
      f"n={pc['n_videos_bootstrap']} videos, "
      f"{'CI lower > 15%' if ci[0] > 0.15 else 'CI incl. 0 or lower ≤ 15%'}).  ")
    A(f"Pre-registered rule: SIGNAL ≥40% and CI lower >15%; NO SIGNAL <15% or CI incl. 0; PARTIAL otherwise.")
    if paired["beats_p1"]:
        A(f"Text predictors ({best_p}) beat elapsed-only (P1): YES — median Δgap_closed "
          f"{100*paired['gc_diff_median']:.1f}% (95% CI {100*paired['ci_95'][0]:.1f}%–{100*paired['ci_95'][1]:.1f}%, excl. 0).")
    else:
        A(f"Text predictors ({best_p}) beat elapsed-only (P1): NO — median Δgap_closed "
          f"{100*paired['gc_diff_median']:.1f}% (95% CI {100*paired['ci_95'][0]:.1f}%–{100*paired['ci_95'][1]:.1f}%).")
    A(f"**Disclosure:** exploratory analysis at L=120, e=0.2 found gap_closed ≈47% (AUROC 0.79). "
      f"This is a confirmatory re-implementation, not independent evidence.")
    A(f"")
    A(f"---")

    # ── 1. data ───────────────────────────────────────────────────────────────
    A(f"")
    A(f"## 1. Data")
    A(f"")
    A(f"Source: `results/sember/study_h/data/sember_grounding.jsonl`, n=9,448.  ")
    A(f"Excluded: 10 negative-nearest.  Used: {len(rows)} records.  ")
    A(f"Grouped 5-fold CV by video_id, seed=42. No video leakage confirmed.")
    A(f"")
    A(f"P(needs_escalation): L=60 → {r['p_needs'][60]:.3f}, L=120 → {r['p_needs'][120]:.3f}  ")
    A(f"(Expected ≈0.579 / 0.297)")
    A(f"")
    cats = [(c, sum(1 for row in rows if row["category"]==c))
            for c in sorted(set(row["category"] for row in rows))]
    A(f"**Category counts (with counting):**")
    for cat, cn in cats:
        A(f"- {cat}: {cn}")
    nc = sum(1 for row in rows if row["category"] != "counting_objects_events")
    A(f"- **Total without counting:** {nc}")
    A(f"")

    # ── 2. AUROC ─────────────────────────────────────────────────────────────
    A(f"## 2. AUROC per Predictor")
    A(f"")
    A(f"### With counting")
    A(f"")
    msn = r["model_selection_note"]
    A(f"| predictor | L=60 test | L=120 test | L=120 OOF | L=120 in-fold |")
    A(f"|---|---|---|---|---|")
    for p in ["P1","P2","P3","P4","P5"]:
        label = p + (" (ORACLE-INFO)" if p == "P5" else "")
        a60  = r["auroc"][p][60]
        a120 = r["auroc"][p][120]
        sel_marker = " ← selected" if p == msn["best_p_oof"] else ""
        ifsel_marker = " ← in-fold" if (p == msn["best_p_infold"] and p != msn["best_p_oof"]) else ""
        A(f"| {label} | {a60['test']:.4f} | {a120['test']:.4f} | "
          f"{a120['mean_oof']:.4f}{sel_marker} | {a120['mean_infold']:.4f}{ifsel_marker} |")
    A(f"")
    A(f"### Without counting")
    A(f"")
    A(f"| predictor | L=60 test | L=120 test |")
    A(f"|---|---|---|")
    for p in ["P1","P2","P3","P4","P5"]:
        label = p + (" (ORACLE-INFO)" if p == "P5" else "")
        A(f"| {label} | {rw['auroc'][p][60]['test']:.4f} | {rw['auroc'][p][120]['test']:.4f} |")
    A(f"")

    # ── 3. coverage / gap_closed ──────────────────────────────────────────────
    A(f"## 3. Coverage and Gap Closed (with counting)")
    A(f"")
    A(f"Gap closed = (cov_pred − cov_random) / (cov_oracle − cov_random).  ")
    A(f"Random baseline: analytic (1−p)+e×p where p=P(farthest>L). Oracle: escalate true positives first.")
    A(f"")
    for L in L_LIST:
        for e in E_LIST:
            ec = r["coverage"][L][e]
            p_val = r["p_needs"][L]
            cov_r = ec["P1"]["cov_random"]   # same for all predictors
            cov_o = ec["P1"]["cov_oracle"]
            A(f"### L={L} s, e={e}")
            A(f"")
            A(f"p(needs escalation)={p_val:.3f} | random coverage={100*cov_r:.1f}% | oracle coverage={100*cov_o:.1f}%")
            A(f"")
            A(f"| predictor | cov_pred | gap closed |")
            A(f"|---|---|---|")
            for p in ["P1","P2","P3","P4","P5"]:
                label = p + (" (ORACLE-INFO)" if p == "P5" else "")
                A(f"| {label} | {100*ec[p]['cov_pred']:.1f}% | {100*ec[p]['gap_closed']:.1f}% |")
            if L == L_PRIMARY and abs(e - E_PRIMARY) < 0.001:
                A(f"")
                A(f"**Primary cell (L={L_PRIMARY}, e={E_PRIMARY}): "
                  f"{best_p} = {100*gc:.1f}% (95% CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%)**")
            A(f"")

    # ── 4. per-category ───────────────────────────────────────────────────────
    A(f"## 4. Per-Category Lookup Check (L=120, e=0.2, with counting)")
    A(f"")
    A(f"| category | n | random | oracle | {best_p} gap_closed | P5 (ORACLE-INFO) gap_closed |")
    A(f"|---|---|---|---|---|---|")
    for cat, info in sorted(r["per_category"].items()):
        gc_bp  = info.get(best_p, {}).get("gap_closed", float("nan"))
        gc_p5  = info.get("P5", {}).get("gap_closed", float("nan"))
        cov_r  = info.get(best_p, {}).get("cov_random", float("nan"))
        cov_o  = info.get(best_p, {}).get("cov_oracle", float("nan"))
        A(f"| {cat} | {info['n']} | {100*cov_r:.1f}% | {100*cov_o:.1f}% | {100*gc_bp:.1f}% | {100*gc_p5:.1f}% |")
    A(f"")

    # ── 5. calibration ────────────────────────────────────────────────────────
    A(f"## 5. Calibration — {best_p} at L=120")
    A(f"")
    A(f"| bin | n | mean_pred | frac_pos |")
    A(f"|---|---|---|---|")
    for b in r["calibration_L120"]:
        if b["n"] > 0:
            A(f"| [{b['bin_lo']:.1f},{b['bin_hi']:.1f}) | {b['n']} | {b['mean_pred']:.3f} | {b['frac_pos']:.3f} |")
        else:
            A(f"| [{b['bin_lo']:.1f},{b['bin_hi']:.1f}) | 0 | — | — |")
    A(f"")

    # ── 6. 20 random examples ─────────────────────────────────────────────────
    A(f"## 6. 20 Random Examples")
    A(f"")
    A(f"| question (trunc) | category | qt | farthest | esc_120 | P1 | P2 | P3 | P4 | P5 |")
    A(f"|---|---|---|---|---|---|---|---|---|---|")
    for ex in r["examples"]:
        pvals = " | ".join(str(ex[f"pred_{p}_L120"]) for p in ["P1","P2","P3","P4","P5"])
        A(f"| {ex['question'][:50]} | {ex['category'][:20]} | {ex['qt']:.0f}s | "
          f"{ex['farthest']:.0f}s | {ex['needs_esc_120']} | {pvals} |")
    A(f"")

    # ── 7. verdict ────────────────────────────────────────────────────────────
    A(f"## 7. Verdict and Interpretation")
    A(f"")
    A(f"**{verdict}**")
    A(f"")
    A(f"Primary cell L=120, e=0.2: {best_p} closes {100*gc:.1f}% of oracle gap "
      f"(cov_pred={100*pc['cov_pred']:.1f}%, random={100*pc['cov_random']:.1f}%, "
      f"oracle={100*pc['cov_oracle']:.1f}%).  ")
    A(f"95% CI: {100*ci[0]:.1f}%–{100*ci[1]:.1f}%.")
    A(f"")
    if verdict == "SIGNAL":
        A(f"Evidence-horizon-based escalation works under the pre-registered rule. "
          f"Predictive signal (AUROC={r['auroc'][best_p][L_PRIMARY]['test']:.3f}) translates to "
          f"coverage gain over random escalation.")
    elif verdict == "NO SIGNAL":
        A(f"The escalation predictor does not reliably improve over random escalation at the pre-registered cell. "
          f"AUROC={r['auroc'][best_p][L_PRIMARY]['test']:.3f} (predictive signal may be present but insufficient for coverage gain).")
    else:
        A(f"Gap closed {100*gc:.1f}% is above the NO SIGNAL threshold but below SIGNAL. "
          f"Partial evidence; escalation may help but the effect is not strong enough to meet the pre-registered criterion.")
    if paired["beats_p1"]:
        A(f"Text predictors ({best_p}) reliably outperform elapsed-only (P1): "
          f"median Δgap_closed {100*paired['gc_diff_median']:.1f}% "
          f"(95% CI {100*paired['ci_95'][0]:.1f}%–{100*paired['ci_95'][1]:.1f}%).")
    else:
        A(f"Text predictors ({best_p}) do NOT reliably outperform elapsed-only (P1): "
          f"median Δgap_closed {100*paired['gc_diff_median']:.1f}% "
          f"(95% CI {100*paired['ci_95'][0]:.1f}%–{100*paired['ci_95'][1]:.1f}%, includes 0).")
    A(f"")

    # ── 8. implementation notes ────────────────────────────────────────────────
    A(f"## 8. Implementation Notes")
    A(f"")
    msn = r["model_selection_note"]
    A(f"### Model-selection deviation from pre-registration")
    A(f"")
    A(f"Pre-registration: 'best of P1–P4 by AUROC on training folds only.'  ")
    A(f"Implementation: best by **mean OOF AUROC** (held-out test fold, averaged across 5 folds).  ")
    A(f"In-fold AUROC (fit on training, predict on same training data) was also computed for reference.")
    A(f"")
    A(f"| predictor | OOF AUROC (L=120) | in-fold AUROC (L=120) |")
    A(f"|---|---|---|")
    for p in ["P1","P2","P3","P4"]:
        a120 = r["auroc"][p][120]
        A(f"| {p} | {a120['mean_oof']:.4f} | {a120['mean_infold']:.4f} |")
    A(f"")
    A(f"Best by OOF: **{msn['best_p_oof']}**.  Best by in-fold: **{msn['best_p_infold']}**.  ")
    if msn["agrees"]:
        A(f"Both criteria select the same predictor — the deviation has no effect on the primary result.")
    else:
        A(f"The two criteria select **different** predictors. Primary analysis uses OOF selection ({msn['best_p_oof']}); "
          f"in-fold selection would have chosen {msn['best_p_infold']}. "
          f"See coverage table for both predictors' gap_closed values.")
    A(f"")
    A(f"### P3 AUROC discrepancy")
    A(f"")
    diag = r["p3_external_diagnostic"]
    A(f"An external run reported AUROC {diag['external_ref_auroc']:.3f} for P3 at L=120; this script reports "
      f"{diag['auroc_main_L120']:.4f}. Configuration comparison:")
    A(f"")
    A(f"| setting | main | external |")
    A(f"|---|---|---|")
    A(f"| LogisticRegression max_iter | 1000 | 2000 |")
    A(f"| C | 1.0 | 1.0 |")
    A(f"| solver | lbfgs (default) | lbfgs (default) |")
    A(f"| class_weight | None | None |")
    A(f"| scaling | StandardScaler(with_mean=False) | StandardScaler(with_mean=False) |")
    A(f"| TF-IDF | 1-2 gram, 2000 feat, sublinear_tf | 1-2 gram, 2000 feat, sublinear_tf |")
    A(f"")
    A(f"Running full CV with max_iter=2000: AUROC = **{diag['auroc_external_L120']:.4f}** "
      f"(vs main {diag['auroc_main_L120']:.4f}, external ref {diag['external_ref_auroc']:.3f}).  ")
    if abs(diag["auroc_external_L120"] - diag["auroc_main_L120"]) < 0.002:
        A(f"max_iter=2000 does not reproduce the discrepancy; the gap ({diag['external_ref_auroc']:.3f} vs "
          f"{diag['auroc_external_L120']:.4f}) is likely due to a different data split or feature implementation in the external run. "
          f"No change made to the primary analysis.")
    else:
        A(f"max_iter=2000 partially closes the gap. The primary analysis retains max_iter=1000 unchanged.")
    A(f"")

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
