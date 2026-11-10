#!/usr/bin/env python3
"""StudyE6-intervention — can a policy predict WHICH intervention helps, and does a combined policy beat
an independent evidence selector + model router? OFFLINE ANALYSIS OF EXISTING RESULTS. CPU only, no inference.

Cells (S-EMBER, 845 questions, Instruct, greedy, H100 vLLM 0.31.0):
  H1 = 4B RECENT, H2 = 4B RICH, K3 = 32B RECENT, K1 = 32B RICH.
Targets per question from the 1/0 correctness of those cells (E6 spec):
  cap_recent = K3-H1, ev_4B = H2-H1, both = K1-H1, cap_rich = K1-H2, ev_32B = K1-K3.
Features use ONLY information available before the question (F0-F3). F4 additionally uses the 4B RECENT
answer-letter logprobs for the current question (StudyD13, byte-identical re-run of H1) and is charged the
4B run's cost in the timely-utility setting.

Every policy supplies a score matrix score[q, cell]; the allocation maximises total predicted score subject to
the budget constraints (LP). That makes "maximise predicted correctness within the budget" one rule for all
policies: the lookup policies' predictor is a training-fold table, the learned policies' is a fitted model.
Vectorisers, scalers and models are fitted inside training folds only; 5-fold cross-fitting by video, seed 0.
"""
import collections, gzip, json, sys, warnings
from datetime import datetime
from pathlib import Path
import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.model_selection import KFold  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from scipy.optimize import linprog  # noqa: E402
from scipy import sparse as sp  # noqa: E402

OUT = ROOT / "results/orchestration/study_e6"
E4 = ROOT / "results/orchestration/study_e4"
NB, SEED, NFOLD = 2000, 0, 5
CELLS = ["H1", "H2", "K3", "K1"]
CELL_MODEL = {"H1": "4B", "H2": "4B", "K3": "32B", "K1": "32B"}
CELL_EV = {"H1": "RECENT", "H2": "RICH", "K3": "RECENT", "K1": "RICH"}
TFIDF = dict(lowercase=True, min_df=3, max_features=300, sublinear_tf=True)
TARGETS = {"cap_recent": ("K3", "H1"), "ev_4B": ("H2", "H1"), "both": ("K1", "H1"),
           "cap_rich": ("K1", "H2"), "ev_32B": ("K1", "K3")}
NETS = {"13.6Mbps_44ms": (13.6, 0.044), "88Mbps_22ms": (88.0, 0.022)}
UTIL_CELLS = [("88Mbps_22ms", "png", 5), ("88Mbps_22ms", "png", 10), ("13.6Mbps_44ms", "png", 10)]
BUDGETS = [(b32, br) for b32 in (0.25, 0.5, 1.0) for br in (0.25, 0.5, 1.0)]


def jl(p):
    op = gzip.open if str(p).endswith(".gz") else open
    return [json.loads(l) for l in op(p, "rt")]


def qbin(qt):
    return "le120" if qt <= 120 else ("120-480" if qt <= 480 else "gt480")


# ------------------------------------------------------------------ data
def load():
    man = collections.defaultdict(dict)
    for r in jl(ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"):
        man[r["question_id"]][r["construction"]] = r
    ans, tok = {}, {}

    def put(key, rows, f):
        ans[key], tok[key] = {}, {}
        for r in rows:
            if r.get("error") or not f(r):
                continue
            ans[key][r["question_id"]] = bool(r["correct"])
            tok[key][r["question_id"]] = r.get("prompt_tokens")
    r1 = jl(ROOT / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
    put("K3", r1, lambda r: r["cell"] == "K3" and r["mode"] == "batched")
    put("K1", r1, lambda r: r["cell"] == "K1" and r["mode"] == "batched")
    cl = jl(ROOT / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
    put("H1", cl, lambda r: r["cell"] == "H1" and r["mode"] == "batched")
    put("H2", cl, lambda r: r["cell"] == "H2" and r["mode"] == "batched")
    d11 = jl(ROOT / "results/cost/study_d11/study_d11_requests_h100nvl.jsonl")
    put("F32", d11, lambda r: r["arm"] == "F" and r["model"] == "32BI")
    put("F4", d11, lambda r: r["arm"] == "F" and r["model"] == "4BI")
    d13 = {r["question_id"]: r for r in jl(ROOT / "results/cost/study_d13/study_d13_requests_h100nvl.jsonl")
           if not r.get("error")}
    h5 = [r for r in jl(ROOT / "results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz")
          if not r.get("error") and not r.get("warmup")]
    pts = {"cold32": [(r["prompt_tokens"], r["total_s"]) for r in h5 if r["model"] == "32BI"],
           "cold4": [(r["prompt_tokens"], r["total_s"]) for r in h5 if r["model"] == "4BI"]}
    pts["cold32"] += [(r["prompt_tokens"], r["latency_s"]) for r in r1 if r["mode"] == "single" and not r.get("error")]
    pts["cold32"] += [(r["prompt_tokens"], r["total_s"]) for r in jl(ROOT / "results/cost/study_d10/study_d10_requests_h100nvl.jsonl")
                      if r["load"] == "images_I" and not r["warmup"] and not r["error"]]
    return man, ans, tok, d13, pts


class Curve:
    def __init__(self, points, binw=100):
        bins = collections.defaultdict(list)
        for x, y in sorted(points):
            bins[int(x // binw)].append((x, y))
        self.cx = np.array([np.median([a for a, _ in v]) for _, v in sorted(bins.items())])
        self.cy = np.array([np.median([b for _, b in v]) for _, v in sorted(bins.items())])
        self.lo, self.hi = float(self.cx[0]), float(self.cx[-1])

    def at(self, x):
        if x is None or not (self.lo <= x <= self.hi):
            return None
        return float(np.interp(x, self.cx, self.cy))


FB = {}


def frame_bytes(hw, fmt):
    k = f"{hw[1]}x{hw[0]}"
    if k not in FB:
        k = f"{hw[0]}x{hw[1]}"
    return FB[k]["png_median"] if fmt == "png" else FB[k]["raw"]


# ------------------------------------------------------------------ features
def build_features(Q, meta, man, d13):
    cats = sorted({meta[q]["cat"] for q in Q})
    bins = ["le120", "120-480", "gt480"]
    hist = {}
    byv = collections.defaultdict(list)
    for q in Q:
        byv[meta[q]["video"]].append(q)
    for v, qs in byv.items():
        qs.sort(key=lambda q: (meta[q]["qt"], q))
        for i, q in enumerate(qs):
            earlier = [p for p in qs[:i] if meta[p]["qt"] < meta[q]["qt"]]
            ct = collections.Counter(meta[p]["cat"] for p in earlier)
            ts = [meta[p]["qt"] for p in earlier]
            hist[q] = dict(n=len(earlier), cat_counts=ct,
                           last_qt=max(ts) if ts else -1.0, first_qt=min(ts) if ts else -1.0,
                           gap=(meta[q]["qt"] - max(ts)) if ts else -1.0,
                           mean_gap=(float(np.mean(np.diff(sorted(ts + [meta[q]["qt"]])))) if len(ts) >= 1 else -1.0),
                           same_cat=ct.get(meta[q]["cat"], 0))

    def f1(q):
        v = [1.0 * (meta[q]["cat"] == c) for c in cats] + [1.0 * (qbin(meta[q]["qt"]) == b) for b in bins]
        return v + [float(meta[q]["qt"]), float(meta[q]["qt"]) / 600.0]

    def f3extra(q):
        h = hist[q]
        return ([float(h["n"])] + [float(h["cat_counts"].get(c, 0)) for c in cats]
                + [h["last_qt"], h["first_qt"], h["gap"], h["mean_gap"], float(h["same_cat"])])

    def f4extra(q):
        r = d13.get(q)
        if r is None:
            return [0.0] * 5
        L = r["letter"]
        lp = L["letter_logprobs"]
        s = sorted(lp.values(), reverse=True)
        p = np.exp(np.array(s))
        p = p / max(p.sum(), 1e-12)
        ent = float(-(p * np.log(p + 1e-12)).sum())
        return [float(s[0]), float(s[0] - s[1]) if len(s) > 1 else 0.0, ent,
                float(L.get("letter_mass_in_topk", 1.0)), float(r.get("n_logprob_tokens") or 0)]

    dense = {"F0": np.zeros((len(Q), 1)),
             "F1": np.array([f1(q) for q in Q]),
             "F2": np.array([f1(q) for q in Q]),
             "F3": np.array([f1(q) + f3extra(q) for q in Q]),
             "F4": np.array([f1(q) + f4extra(q) for q in Q])}
    text = [man[q]["RECENT"]["text"] for q in Q]
    use_text = {"F0": False, "F1": False, "F2": True, "F3": True, "F4": True}
    return dense, text, use_text, cats


def fit_predict(name, Xtr, ytr, Xte):
    """Returns out-of-fold P(y=1). Falls back to the training prior for a degenerate fold."""
    if len(set(ytr)) < 2:
        return np.full(Xte.shape[0], float(np.mean(ytr)))
    if name == "logreg":
        sc = StandardScaler(with_mean=False).fit(Xtr)
        m = LogisticRegression(max_iter=3000, C=1.0, random_state=SEED).fit(sc.transform(Xtr), ytr)
        return m.predict_proba(sc.transform(Xte))[:, 1]
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_leaf_nodes=15,
                                       min_samples_leaf=20, l2_regularization=1.0,
                                       random_state=SEED).fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def main():
    global FB
    OUT.mkdir(parents=True, exist_ok=True)
    FB = json.loads((E4 / "e4_frame_bytes.json").read_text())["sizes"]
    man, ans, tok, d13, pts = load()
    Q = sorted(man)
    assert len(Q) == 845
    for c in CELLS:
        assert set(ans[c]) == set(Q), (c, len(ans[c]))
    meta = {q: dict(video=man[q]["RECENT"]["video_id"], qt=man[q]["RECENT"]["question_time"],
                    cat=man[q]["RECENT"]["question_category"],
                    cov=bool(man[q]["RECENT"]["evidence_covered"])) for q in Q}
    qi = {q: i for i, q in enumerate(Q)}
    N = len(Q)
    Y = {c: np.array([1.0 if ans[c][q] else 0.0 for q in Q]) for c in CELLS}
    res = dict(label="StudyE6-intervention: OFFLINE ANALYSIS OF EXISTING RESULTS (S-EMBER 845, Instruct, greedy, "
                     "H100 vLLM 0.31.0). CPU only; no new inference; no model server.",
               at=datetime.now().isoformat(), checks={}, match_statements={})
    res["match_statements"] = {
        "K3 vs H1 (cap_recent)": "IDENTICAL_INPUT (ledger H1-K3): same requests 845/845, same vLLM 0.31.0 FA3, both greedy 512. "
                                 "Differs: model (4B vs 32B) and GPU (1 vs 3). Identifies capability at fixed input.",
        "K1 vs H2 (cap_rich)": "IDENTICAL_INPUT (ledger H2-K1): prompt tokens 845/845 exact, same stack and decoding, GPU 1 vs 3.",
        "H2 vs H1 (ev_4B)": "REALLOCATED_BUDGET (ledger H2-H1): same server, stack, decoding, questions. RICH vs RECENT moves "
                            "window, frame count and resolution TOGETHER under one token budget - not history length alone.",
        "K1 vs K3 (ev_32B)": "REALLOCATED_BUDGET (ledger K1-K3): same model, stack, host, greedy. Same caveat as H2-H1.",
        "K1 vs H1 (both)": "model and evidence move together; not decomposable into one factor.",
        "D13 vs H1 (F4 features)": "same model, stack and decoding, logprobs=True; predictions 845/845 identical and prompt "
                                   "tokens 845/845 identical (checks.d13_vs_h1), so D13 confidence is H1's own confidence."}
    # ---- checks
    res["checks"]["cell_accuracy"] = {c: float(Y[c].mean()) for c in CELLS}
    res["checks"]["n_matched_all_four_cells"] = int(sum(all(q in ans[c] for c in CELLS) for q in Q))
    res["checks"]["d13_vs_h1"] = dict(
        n=len(d13),
        pred_agreement=float(np.mean([d13[q]["pred"] == [r for r in [None]][0] if False else True for q in Q])),
    )
    cl_rows = {r["question_id"]: r for r in jl(ROOT / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
               if r["cell"] == "H1" and r["mode"] == "batched" and not r.get("error")}
    res["checks"]["d13_vs_h1"] = dict(
        n=len([q for q in Q if q in d13]),
        pred_agreement=float(np.mean([d13[q]["pred"] == cl_rows[q]["pred"] for q in Q if q in d13])),
        prompt_tokens_identical=float(np.mean([d13[q]["prompt_tokens"] == cl_rows[q]["prompt_tokens"] for q in Q if q in d13])),
        correct_agreement=float(np.mean([bool(d13[q]["correct"]) == bool(cl_rows[q]["correct"]) for q in Q if q in d13])))
    # noise floor (E4 s6)
    nf = {}
    for f, ref in (("F32", "K3"), ("F4", "H1")):
        ks = sorted(set(ans[f]) & set(ans[ref]))
        a = np.array([ans[f][k] for k in ks]); b = np.array([ans[ref][k] for k in ks])
        nf[f"{f}vs{ref}"] = dict(n=len(ks), disagreement=float(np.mean(a != b)),
                                 oracle_headroom=float(np.mean(a | b) - max(a.mean(), b.mean())))
    res["noise_floor"] = nf

    # ---- targets and joint distribution
    tg = {t: (Y[a] - Y[b]) for t, (a, b) in TARGETS.items()}
    res["targets"] = {t: dict(improves=int((v > 0).sum()), unchanged=int((v == 0).sum()), harms=int((v < 0).sum()),
                              mean=float(v.mean())) for t, v in tg.items()}
    joint = collections.Counter(tuple(int(Y[c][i]) for c in CELLS) for i in range(N))
    res["joint_distribution_H1_H2_K3_K1"] = {"".join(map(str, k)): v for k, v in sorted(joint.items(), key=lambda x: -x[1])}
    res["joint_marginals"] = dict(
        any_cell_correct=int(sum(1 for i in range(N) if max(Y[c][i] for c in CELLS) > 0)),
        all_four_correct=int(sum(1 for i in range(N) if min(Y[c][i] for c in CELLS) > 0)),
        none_correct=int(sum(1 for i in range(N) if max(Y[c][i] for c in CELLS) == 0)))
    res["joint_cross_tab_cap_x_ev_at_baseline_H1"] = {
        f"cap_recent={int(a)},ev_4B={int(b)}": int(sum(1 for i in range(N) if tg["cap_recent"][i] == a and tg["ev_4B"][i] == b))
        for a in (-1, 0, 1) for b in (-1, 0, 1)}

    # ---- folds (5-fold by video, seed 0) and bootstrap
    vids = sorted({meta[q]["video"] for q in Q})
    vfold = {}
    for fi, (_, te) in enumerate(KFold(NFOLD, shuffle=True, random_state=SEED).split(vids)):
        for i in te:
            vfold[vids[i]] = fi
    fold = np.array([vfold[meta[q]["video"]] for q in Q])
    byv = collections.defaultdict(list)
    for q in Q:
        byv[meta[q]["video"]].append(qi[q])
    rng = np.random.default_rng(SEED)
    boots = [np.array([i for v in rng.choice(vids, len(vids), replace=True) for i in byv[v]]) for _ in range(NB)]

    def ci(vec_diff):
        d = np.asarray(vec_diff, dtype=float)
        bs = np.array([d[b].mean() for b in boots])
        return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]

    dense, text, use_text, cats = build_features(Q, meta, man, d13)
    res["feature_sets"] = {
        "F0": "none (static); intercept only",
        "F1": "question category (one-hot) + question time + question-time bin (one-hot)",
        "F2": "F1 + question text TF-IDF (min_df=3, max_features=300, sublinear_tf; fitted in training folds only)",
        "F3": "F2 + session history: count of earlier questions in the same video, per-category counts, first/last "
              "earlier question time, gap to the previous question, mean gap",
        "F4": "F2 + StudyD13 4B-RECENT answer-letter logprobs for the current question (top logprob, top-2 margin, "
              "entropy over letters, letter mass in top-k, logprob token count); charged the 4B run's cost in setting (b)"}
    res["feature_audit_no_leakage"] = ("F0-F3 use only question metadata, question text and earlier questions' metadata "
                                       "in the same video: no answer, correctness or model output of any question. F4 uses "
                                       "the 4B RECENT model output for the CURRENT question only (spec-permitted, cost charged).")

    def oof_matrix(fs, learner, ycols):
        """Out-of-fold predicted P(correct) for each named target column."""
        P = {k: np.zeros(N) for k in ycols}
        for fi in range(NFOLD):
            tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
            Xtr, Xte = dense[fs][tr], dense[fs][te]
            if use_text[fs]:
                vec = TfidfVectorizer(**TFIDF).fit([text[i] for i in tr])
                Ttr = vec.transform([text[i] for i in tr]).toarray()
                Tte = vec.transform([text[i] for i in te]).toarray()
                Xtr, Xte = np.hstack([Xtr, Ttr]), np.hstack([Xte, Tte])
            for k, y in ycols.items():
                P[k][te] = fit_predict(learner, Xtr, y[tr], Xte)
        return P

    # ---- AUROC diagnostics per target per feature set (gain > 0)
    auroc = {}
    for fs in ("F0", "F1", "F2", "F3", "F4"):
        for learner in ("logreg", "gbt"):
            ycols = {t: (tg[t] > 0).astype(float) for t in TARGETS}
            P = oof_matrix(fs, learner, ycols)
            for t in TARGETS:
                y = ycols[t]
                if len(set(y)) < 2:
                    continue
                a = float(roc_auc_score(y, P[t]))
                bs = []
                for b in boots:
                    yb, pb = y[b], P[t][b]
                    if len(set(yb)) > 1:
                        bs.append(roc_auc_score(yb, pb))
                auroc[f"{fs}/{learner}/{t}"] = dict(auroc=a, n_pos=int(y.sum()),
                                                    ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                                                    oof_pred=None)
                auroc[f"{fs}/{learner}/{t}"]["_p"] = P[t].tolist()
    # paired deltas vs F1 (the lookup-table test)
    delta = {}
    for learner in ("logreg", "gbt"):
        for t in TARGETS:
            base = auroc.get(f"F1/{learner}/{t}")
            if not base:
                continue
            for fs in ("F2", "F3", "F4"):
                k = f"{fs}/{learner}/{t}"
                if k not in auroc:
                    continue
                y = (tg[t] > 0).astype(float)
                p1, p2 = np.array(base["_p"]), np.array(auroc[k]["_p"])
                d = []
                for b in boots:
                    yb = y[b]
                    if len(set(yb)) > 1:
                        d.append(roc_auc_score(yb, p2[b]) - roc_auc_score(yb, p1[b]))
                delta[f"{fs}-minus-F1/{learner}/{t}"] = dict(
                    delta=float(roc_auc_score(y, p2) - roc_auc_score(y, p1)),
                    ci=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))])
    for k in auroc:
        auroc[k].pop("_p", None)
        auroc[k].pop("oof_pred", None)
    res["auroc_diagnostic"] = auroc
    res["auroc_delta_vs_F1"] = delta

    # ---- per-cell out-of-fold correctness predictions (the combined policy's engine)
    cellP = {}
    for fs in ("F0", "F1", "F2", "F3", "F4"):
        for learner in ("logreg", "gbt"):
            cellP[(fs, learner)] = oof_matrix(fs, learner, {c: Y[c] for c in CELLS})

    # ---- lookup tables (static, per-type), cross-fitted
    qtype = [(meta[q]["cat"], qbin(meta[q]["qt"])) for q in Q]
    S_static = np.zeros((N, 4)); S_type = np.zeros((N, 4))
    for fi in range(NFOLD):
        tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
        for j, c in enumerate(CELLS):
            S_static[te, j] = Y[c][tr].mean()
        pools = collections.defaultdict(list)
        for i in tr:
            pools[qtype[i]].append(i)
        for i in te:
            pool = pools.get(qtype[i]) or list(tr)
            for j, c in enumerate(CELLS):
                S_type[i, j] = Y[c][pool].mean()

    # ---- independent baseline: coverage predictor (evidence) x model router
    #  evidence selector: R8a-style coverage predictor on F2, target = evidence NOT covered by the recent window
    cov_out = (~np.array([meta[q]["cov"] for q in Q])).astype(float)
    ev_score = {}
    for learner in ("logreg", "gbt"):
        P = oof_matrix("F2", learner, {"cov": cov_out})
        ev_score[learner] = P["cov"]
        if len(set(cov_out)) > 1:
            res.setdefault("coverage_predictor_auroc", {})[learner] = dict(
                auroc=float(roc_auc_score(cov_out, P["cov"])), n_pos=int(cov_out.sum()),
                note="target = evidence outside the recent window (RECENT construction evidence_covered == False); "
                     "benchmark is StudyR8a's 2026-11-03 CORRECTION (query-only 0.7885), not its superseded Part 1 table")
    conf = np.array([np.exp(d13[q]["letter"]["letter_logprobs"][max(d13[q]["letter"]["letter_logprobs"],
                    key=d13[q]["letter"]["letter_logprobs"].get)]) if q in d13 else 0.5 for q in Q])
    md_score = {}
    for learner in ("logreg", "gbt"):
        # (a) always 32B
        md_score[(learner, "always32B")] = np.ones(N)
        # (b) 4B confidence, threshold fitted in training folds (escalate the least confident)
        s = np.zeros(N)
        for fi in range(NFOLD):
            tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
            best, bq = None, None
            for qt_ in np.arange(0.05, 1.0, 0.05):
                thr = np.quantile(conf[tr], qt_)
                esc = conf[tr] <= thr
                acc = np.where(esc, Y["K3"][tr], Y["H1"][tr]).mean()
                if best is None or acc > best:
                    best, bq = acc, qt_
            thr = np.quantile(conf[tr], bq)
            s[te] = (conf[te] <= thr).astype(float)
        md_score[(learner, "conf4B")] = s
        # (c) classifier on F2 for K3 > H1
        P = oof_matrix("F2", learner, {"k3gt": (tg["cap_recent"] > 0).astype(float)})
        md_score[(learner, "clsF2")] = P["k3gt"]
    res["independent_router_variants"] = {
        "always32B": "model router sends every question to 32B",
        "conf4B": "4B RECENT top-letter probability (StudyD13); escalate the least-confident questions, quantile "
                  "threshold chosen on training folds to maximise training-fold accuracy",
        "clsF2": "classifier on F2 predicting K3 > H1"}

    # ---- LP allocation under budgets
    def allocate(score, feas, b32, br):
        """Maximise sum score[q,c] s.t. one cell per question, 32B share <= b32, RICH share <= br.
        feas[q,c] = 0 forbids a cell (used for timely utility: a cell that cannot deliver is still allowed,
        it simply scores 0; feas is used only to force H1 available). Returns x (N,4)."""
        c_obj = -(score * feas).reshape(-1)
        A_eq = sp.csr_matrix((np.ones(N * 4), (np.repeat(np.arange(N), 4), np.arange(N * 4))), shape=(N, N * 4))
        b_eq = np.ones(N)
        rows, rhs = [], []
        if b32 < 1.0:
            r = np.zeros(N * 4)
            for j, c in enumerate(CELLS):
                if CELL_MODEL[c] == "32B":
                    r[j::4] = 1.0
            rows.append(r); rhs.append(b32 * N)
        if br < 1.0:
            r = np.zeros(N * 4)
            for j, c in enumerate(CELLS):
                if CELL_EV[c] == "RICH":
                    r[j::4] = 1.0
            rows.append(r); rhs.append(br * N)
        kw = dict(A_eq=A_eq, b_eq=b_eq, bounds=(0, 1), method="highs")
        if rows:
            kw.update(A_ub=sp.csr_matrix(np.array(rows)), b_ub=np.array(rhs))
        out = linprog(c_obj, **kw)
        assert out.success, out.message
        return out.x.reshape(N, 4)

    ONE = np.ones((N, 4))
    Ymat = np.column_stack([Y[c] for c in CELLS])

    def realized(x, val):
        return (x * val).sum(axis=1)

    POLICIES = ["oracle", "static", "pertype", "indep_always32B", "indep_conf4B", "indep_clsF2",
                "capability_only", "evidence_only", "combined"]
    res["fixed_factor_per_fold"] = {}
    for fi in range(NFOLD):
        tr = np.where(fold != fi)[0]
        bstat = max(CELLS, key=lambda c: (Y[c][tr].mean(), c))
        res["fixed_factor_per_fold"][f"fold{fi}"] = dict(
            best_static_cell_on_training_folds=bstat,
            capability_only_varies_model_at_evidence=CELL_EV[bstat],
            evidence_only_varies_evidence_at_model=CELL_MODEL[bstat])

    def score_for(pol, fs, learner):
        if pol == "oracle":
            return Ymat
        if pol == "static":
            return S_static
        if pol == "pertype":
            return S_type
        if pol.startswith("indep_"):
            v = pol[len("indep_"):]
            m = md_score[(learner, v)]
            e = ev_score[learner]
            S = np.zeros((N, 4))
            for j, c in enumerate(CELLS):
                sm = m if CELL_MODEL[c] == "32B" else 1.0 - m
                se = e if CELL_EV[c] == "RICH" else 1.0 - e
                S[:, j] = sm * se
            return S
        P = cellP[(fs, learner)]
        if pol == "combined":
            return np.column_stack([P[c] for c in CELLS])
        if pol in ("capability_only", "evidence_only"):
            # The held-fixed factor comes from the BEST STATIC CELL, chosen inside the training folds only.
            # capability_only varies the model at that cell's evidence arm; evidence_only varies the evidence
            # at that cell's model. Both therefore contain the best static cell by construction.
            S = np.full((N, 4), -1.0)
            for fi in range(NFOLD):
                tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
                bstat = max(CELLS, key=lambda c: (Y[c][tr].mean(), c))
                keep = (lambda c: CELL_EV[c] == CELL_EV[bstat]) if pol == "capability_only" \
                    else (lambda c: CELL_MODEL[c] == CELL_MODEL[bstat])
                for j, c in enumerate(CELLS):
                    if keep(c):
                        S[te, j] = P[c][te]
            return S
        raise ValueError(pol)

    # ---------------- setting (a): accuracy under budgets
    acc_out, realized_vec = {}, {}
    for learner in ("logreg", "gbt"):
        for fs in ("F1", "F2", "F3", "F4"):
            for pol in POLICIES:
                if pol in ("oracle", "static", "pertype") and (fs != "F1" or learner != "logreg"):
                    continue
                S = score_for(pol, fs, learner)
                for (b32, br) in BUDGETS:
                    x = allocate(S, ONE, b32, br)
                    r = realized(x, Ymat)
                    key = f"{pol}|{fs}|{learner}|b32={b32}|bRICH={br}"
                    realized_vec[key] = r
                    acc_out[key] = dict(accuracy=float(r.mean()),
                                        frac_32B=float(x[:, [2, 3]].sum() / N), frac_RICH=float(x[:, [1, 3]].sum() / N),
                                        fractional_mass=float(np.abs(x - np.round(x)).sum()))
    res["setting_a_accuracy_under_budgets"] = acc_out

    # ---------------- setting (b): timely utility with Part 0's corrected costs
    curves = {k: Curve(v) for k, v in pts.items()}
    byv_q = collections.defaultdict(list)
    for q in Q:
        byv_q[meta[q]["video"]].append(q)

    def frames_of(cell, q):
        rec, rich = man[q]["RECENT"], man[q]["RICH"]
        if CELL_EV[cell] == "RECENT":
            return [(t, rec["final_hw"]) for t in rec["frame_t"]]
        return [(t, rich["final_hw"]) for t in rich["frame_t"]]

    lat_status = collections.Counter()
    deliver, totals = {}, {}
    for (net, fmt, dl) in UTIL_CELLS:
        up, rtt = NETS[net]
        D = np.zeros((N, 4)); T = np.full((N, 4), np.nan)
        for j, c in enumerate(CELLS):
            cur = "cold4" if CELL_MODEL[c] == "4B" else "cold32"
            for q in Q:
                i = qi[q]
                comp = curves[cur].at(tok[c].get(q))
                if comp is None:
                    lat_status[f"{c}/UNKNOWN"] += 1
                    D[i, j] = 0.0
                    continue
                fr = frames_of(c, q)
                ub = (frame_bytes(fr[-1][1], fmt) if fr else 0) if CELL_EV[c] == "RICH" \
                    else sum(frame_bytes(hw, fmt) for _, hw in fr)
                tot = comp + ub * 8 / (up * 1e6) + rtt
                T[i, j] = tot
                D[i, j] = float(tot <= dl)
        deliver[(net, fmt, dl)] = D
        totals[(net, fmt, dl)] = T
    res["checks"]["latency_UNKNOWN_per_cell_one_pass"] = {k: v // len(UTIL_CELLS) for k, v in lat_status.items()}
    res["setting_b_definition"] = ("utility = correct AND (compute + upload + RTT) <= deadline. Upload uses PART 0's "
                                   "corrected rule: RICH cells pay only the newest pending frame; RECENT cells pay all "
                                   "their frames. Compute from the same cold curves as StudyE4; a prompt outside the "
                                   "measured token range is UNKNOWN and that cell is unavailable (utility 0), as in E4. "
                                   "F4 additionally pays the 4B RECENT run (compute + its upload) before deciding, except "
                                   "when it then chooses H1, whose answer it already has.")
    util_out, util_vec = {}, {}
    for (net, fmt, dl) in UTIL_CELLS:
        D = deliver[(net, fmt, dl)]
        T = totals[(net, fmt, dl)]
        Umat = Ymat * D
        up, rtt = NETS[net]
        # F4's probe cost: the 4B RECENT request must complete first
        probe = np.array([(curves["cold4"].at(tok["H1"].get(q)) or np.inf)
                          + sum(frame_bytes(hw, fmt) for _, hw in frames_of("H1", q)) * 8 / (up * 1e6) + rtt for q in Q])
        D4 = np.zeros((N, 4))
        for j, c in enumerate(CELLS):
            if c == "H1":
                D4[:, j] = D[:, j]
            else:
                with np.errstate(invalid="ignore"):
                    D4[:, j] = np.where(np.isnan(T[:, j]), 0.0, (probe + np.nan_to_num(T[:, j], nan=1e9)) <= dl)
        U4mat = Ymat * D4
        for learner in ("logreg", "gbt"):
            for fs in ("F1", "F2", "F3", "F4"):
                for pol in POLICIES:
                    if pol in ("oracle", "static", "pertype") and (fs != "F1" or learner != "logreg"):
                        continue
                    M = U4mat if fs == "F4" else Umat
                    Dm = D4 if fs == "F4" else D
                    if pol == "oracle":
                        S = M
                    else:
                        S = score_for(pol, fs, learner) * Dm  # deliverability is known before the question
                    x = allocate(S, ONE, 1.0, 1.0)
                    r = realized(x, M)
                    key = f"{pol}|{fs}|{learner}|{net}/{fmt}/{dl}s"
                    util_vec[key] = r
                    util_out[key] = dict(utility=float(r.mean()), frac_32B=float(x[:, [2, 3]].sum() / N),
                                         frac_RICH=float(x[:, [1, 3]].sum() / N))
        util_out[f"_deliverable_fraction|{net}/{fmt}/{dl}s"] = {c: float(D[:, j].mean()) for j, c in enumerate(CELLS)}
        util_out[f"_per_cell_utility|{net}/{fmt}/{dl}s"] = {c: float(Umat[:, j].mean()) for j, c in enumerate(CELLS)}
    res["setting_b_timely_utility"] = util_out

    # ---------------- combined minus best independent baseline, paired, with CI
    paired = {}
    for learner in ("logreg", "gbt"):
        for fs in ("F2", "F3", "F4"):
            for (b32, br) in BUDGETS:
                cand = {v: acc_out[f"indep_{v}|{fs}|{learner}|b32={b32}|bRICH={br}"]["accuracy"]
                        for v in ("always32B", "conf4B", "clsF2")}
                bestv = max(cand, key=cand.get)
                a = realized_vec[f"combined|{fs}|{learner}|b32={b32}|bRICH={br}"]
                b = realized_vec[f"indep_{bestv}|{fs}|{learner}|b32={b32}|bRICH={br}"]
                paired[f"accuracy|{fs}|{learner}|b32={b32}|bRICH={br}"] = dict(
                    best_independent=bestv, independent=float(b.mean()), combined=float(a.mean()),
                    diff=float((a - b).mean()), ci=ci(a - b),
                    per_type_ref=acc_out[f"pertype|F1|logreg|b32={b32}|bRICH={br}"]["accuracy"],
                    oracle_ref=acc_out[f"oracle|F1|logreg|b32={b32}|bRICH={br}"]["accuracy"])
            for (net, fmt, dl) in UTIL_CELLS:
                tagc = f"{net}/{fmt}/{dl}s"
                cand = {v: util_out[f"indep_{v}|{fs}|{learner}|{tagc}"]["utility"] for v in ("always32B", "conf4B", "clsF2")}
                bestv = max(cand, key=cand.get)
                a = util_vec[f"combined|{fs}|{learner}|{tagc}"]
                b = util_vec[f"indep_{bestv}|{fs}|{learner}|{tagc}"]
                paired[f"utility|{fs}|{learner}|{tagc}"] = dict(
                    best_independent=bestv, independent=float(b.mean()), combined=float(a.mean()),
                    diff=float((a - b).mean()), ci=ci(a - b),
                    per_type_ref=util_out[f"pertype|F1|logreg|{tagc}"]["utility"],
                    oracle_ref=util_out[f"oracle|F1|logreg|{tagc}"]["utility"])
    res["paired_combined_minus_best_independent"] = paired

    # ---------------- fraction of oracle headroom over per-type captured
    frac = {}
    for key, d in list(acc_out.items()):
        pol, fs, learner, b1, b2 = key.split("|")
        o = acc_out[f"oracle|F1|logreg|{b1}|{b2}"]["accuracy"]
        p = acc_out[f"pertype|F1|logreg|{b1}|{b2}"]["accuracy"]
        frac[f"accuracy|{key}"] = (float((d["accuracy"] - p) / (o - p)) if o > p else None)
    for key, d in list(util_out.items()):
        if key.startswith("_"):
            continue
        pol, fs, learner, tagc = key.split("|")
        o = util_out[f"oracle|F1|logreg|{tagc}"]["utility"]
        p = util_out[f"pertype|F1|logreg|{tagc}"]["utility"]
        frac[f"utility|{key}"] = (float((d["utility"] - p) / (o - p)) if o > p else None)
    res["fraction_of_oracle_headroom_over_pertype"] = frac

    # ---------------- every policy vs the per-type lookup: paired diff, CI, and headroom fraction with CI
    pvp = {}
    for key, dd in list(acc_out.items()):
        pol, fs, learner, b1, b2 = key.split("|")
        ref = realized_vec[f"pertype|F1|logreg|{b1}|{b2}"]
        orc = realized_vec[f"oracle|F1|logreg|{b1}|{b2}"]
        a = realized_vec[key]
        den = orc.mean() - ref.mean()
        bs_num = np.array([(a[b] - ref[b]).mean() for b in boots])
        bs_den = np.array([(orc[b] - ref[b]).mean() for b in boots])
        with np.errstate(divide="ignore", invalid="ignore"):
            bs_fr = np.where(np.abs(bs_den) > 1e-12, bs_num / bs_den, np.nan)
        pvp[f"accuracy|{key}"] = dict(
            value=float(a.mean()), pertype=float(ref.mean()), oracle=float(orc.mean()),
            diff_vs_pertype=float((a - ref).mean()), ci_vs_pertype=ci(a - ref),
            headroom_fraction=(float((a.mean() - ref.mean()) / den) if abs(den) > 1e-12 else None),
            headroom_fraction_ci=([float(np.nanpercentile(bs_fr, 2.5)), float(np.nanpercentile(bs_fr, 97.5))]
                                  if np.isfinite(bs_fr).any() else None))
    for key, dd in list(util_out.items()):
        if key.startswith("_"):
            continue
        pol, fs, learner, tagc = key.split("|")
        ref = util_vec[f"pertype|F1|logreg|{tagc}"]
        orc = util_vec[f"oracle|F1|logreg|{tagc}"]
        a = util_vec[key]
        den = orc.mean() - ref.mean()
        bs_num = np.array([(a[b] - ref[b]).mean() for b in boots])
        bs_den = np.array([(orc[b] - ref[b]).mean() for b in boots])
        with np.errstate(divide="ignore", invalid="ignore"):
            bs_fr = np.where(np.abs(bs_den) > 1e-12, bs_num / bs_den, np.nan)
        pvp[f"utility|{key}"] = dict(
            value=float(a.mean()), pertype=float(ref.mean()), oracle=float(orc.mean()),
            diff_vs_pertype=float((a - ref).mean()), ci_vs_pertype=ci(a - ref),
            headroom_fraction=(float((a.mean() - ref.mean()) / den) if abs(den) > 1e-12 else None),
            headroom_fraction_ci=([float(np.nanpercentile(bs_fr, 2.5)), float(np.nanpercentile(bs_fr, 97.5))]
                                  if np.isfinite(bs_fr).any() else None))
    res["policy_vs_pertype"] = pvp
    # also vs the best static cell, the stronger lookup reference
    pvs = {}
    for key in list(acc_out):
        pol, fs, learner, b1, b2 = key.split("|")
        ref = realized_vec[f"static|F1|logreg|{b1}|{b2}"]
        a = realized_vec[key]
        pvs[f"accuracy|{key}"] = dict(diff_vs_static=float((a - ref).mean()), ci_vs_static=ci(a - ref))
    for key in list(util_out):
        if key.startswith("_"):
            continue
        pol, fs, learner, tagc = key.split("|")
        ref = util_vec[f"static|F1|logreg|{tagc}"]
        a = util_vec[key]
        pvs[f"utility|{key}"] = dict(diff_vs_static=float((a - ref).mean()), ci_vs_static=ci(a - ref))
    res["policy_vs_best_static"] = pvs
    np.savez_compressed(OUT / "e6_realized_vectors.npz",
                        **{("acc__" + k): v for k, v in realized_vec.items()},
                        **{("util__" + k): v for k, v in util_vec.items()})

    # ---------------- capability-only usefulness rule and within-category results
    capr = {}
    for learner in ("logreg", "gbt"):
        for fs in ("F2", "F3", "F4"):
            for (b32, br) in BUDGETS:
                co = acc_out[f"capability_only|{fs}|{learner}|b32={b32}|bRICH={br}"]
                a32 = acc_out[f"indep_always32B|{fs}|{learner}|b32={b32}|bRICH={br}"]
                r4 = realized_vec[f"capability_only|{fs}|{learner}|b32={b32}|bRICH={br}"]
                b4 = realized_vec[f"indep_always32B|{fs}|{learner}|b32={b32}|bRICH={br}"]
                always4B = float(Y["H1"].mean())
                capr[f"{fs}|{learner}|b32={b32}|bRICH={br}"] = dict(
                    capability_only=co["accuracy"], always32B_within_budget=a32["accuracy"], always4B=always4B,
                    diff_vs_always32B=float((r4 - b4).mean()), ci_vs_always32B=ci(r4 - b4),
                    beats_always32B=bool(ci(r4 - b4)[0] > 0), beats_always4B=bool(co["accuracy"] > always4B))
    res["capability_only_rule"] = capr
    bycat = {}
    cat_of = np.array([meta[q]["cat"] for q in Q])
    for c in sorted(set(cat_of)):
        m = cat_of == c
        bycat[c] = dict(n=int(m.sum()), cells={cc: float(Y[cc][m].mean()) for cc in CELLS},
                        oracle=float(Ymat[m].max(axis=1).mean()),
                        pertype=float(realized_vec["pertype|F1|logreg|b32=1.0|bRICH=1.0"][m].mean()),
                        combined_F2_gbt=float(realized_vec["combined|F2|gbt|b32=1.0|bRICH=1.0"][m].mean()),
                        combined_F3_gbt=float(realized_vec["combined|F3|gbt|b32=1.0|bRICH=1.0"][m].mean()),
                        best_indep=float(max(realized_vec[f"indep_{v}|F2|gbt|b32=1.0|bRICH=1.0"][m].mean()
                                             for v in ("always32B", "conf4B", "clsF2"))),
                        targets={t: dict(improves=int((tg[t][m] > 0).sum()), harms=int((tg[t][m] < 0).sum())) for t in TARGETS})
    res["by_question_category"] = bycat
    res["_provenance"] = stamp(script="study_e6_intervention.py", model="4BI,32BI (existing results)", device="cpu", n=N)
    (OUT / "e6_results.json").write_text(json.dumps(res, indent=1, default=float))
    print("cell accuracy:", {k: round(v, 4) for k, v in res["checks"]["cell_accuracy"].items()})
    print("d13 vs h1:", res["checks"]["d13_vs_h1"])
    print("coverage predictor AUROC:", {k: round(v["auroc"], 4) for k, v in res.get("coverage_predictor_auroc", {}).items()})
    print("targets:", json.dumps(res["targets"], default=float))
    for b in (1.0,):
        print(f"\n-- unconstrained accuracy (b32={b}, bRICH={b}) --")
        for pol in POLICIES:
            for fs in ("F1", "F2", "F3"):
                for lr in ("logreg", "gbt"):
                    k = f"{pol}|{fs}|{lr}|b32={b}|bRICH={b}"
                    if k in acc_out:
                        print(f"  {pol:18s} {fs} {lr:7s} {acc_out[k]['accuracy']:.4f}")


if __name__ == "__main__":
    main()
