#!/usr/bin/env python3
"""StudyR8a — do device-side reasoning PREFIXES improve the escalation decision?

CPU only. Reads committed results; runs no inference. Pre-registered in
research/EXPERIMENTS.md (StudyR8a, 2026-10-23) before any number here was computed.

Part 1  signals at reasoning prefixes k in {0, 25, 50, 100, 200, 400} tokens
Part 2  escalation utility at budgets e, against a query-only router
Part 3  rescue matrix (S-EMBER)
plus the mechanism-verification artifacts (Steps 2-5) the registry requires.

R8a runs concurrently with R8b (A6000) and R8c (3090 Ti) by the user's scheduling
rule; it measures no latency of its own. Decision latency comes only from the Orin's
standalone, uncontended token timings.
"""
import argparse, gzip, json, os, re, sys, time
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "erqa"))
sys.path.insert(0, str(ROOT / "experiments" / "sember"))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))

import r4_device_signals as R4S                      # hesitation counts, verbatim
from study_o_q4_analyze import clustered_bootstrap   # S-EMBER video-clustered bootstrap
from _provenance import stamp

OUT = ROOT / "results/escalation/study_r8a"
OUT.mkdir(parents=True, exist_ok=True)
# Frozen-embedding caches are regenerable intermediates, not results: they live outside
# results/ so nothing large and derived is committed.
EMB_CACHE = Path(os.environ.get(
    "R8A_EMB_CACHE",
    "/tmp/claude-1001/-home-pragya-Desktop-FM-switching/"
    "8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/r8a_cache"))
EMB_CACHE.mkdir(parents=True, exist_ok=True)

KS = [0, 25, 50, 100, 200, 400]
RATES = [0.1, 0.2, 0.3, 0.5, 1.0]
NBOOT = 2000
SEED = 0
NFOLD = 5
RANDOM_DRAWS = 200
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOK_4BT = "/mnt/ssd/hf_models/models--Qwen--Qwen3-VL-4B-Thinking/snapshots/1de27d8c51f12e819435303b9e84c4e25ba8401e"

# Pre-registered in research/EXPERIMENTS.md (StudyR8a) BEFORE any scoring.
MISSING_EVIDENCE_PHRASES = [
    "not visible", "can't see", "cannot see", "not shown", "not in the", "earlier",
    "before the clip", "before the video", "outside the", "don't see", "do not see",
    "no visible", "hard to tell", "unclear", "not enough information",
    "can't determine", "cannot determine",
]


# ─────────────────────────────────────────────────────────────── loaders ────
def jl(path):
    p = ROOT / path
    op = gzip.open if str(p).endswith(".gz") else open
    with op(p, "rt") as f:
        return [json.loads(line) for line in f]


def _r8b_seed(seed):
    recs = {}
    for part in sorted((ROOT / "results/device").glob(
            f"accuracy_C3_logprobs_s{seed}_part*.jsonl.gz")):
        for r in jl(f"results/device/{part.name}"):
            recs[r["question_id"]] = r
    return recs


def _r8b_series(rec):
    """Per-reasoning-token (text, uncertainty) for one R8b record.

    Uncertainty is -chosen_logprob, so larger means less certain, matching the
    entropy convention R8c uses. These are PRE-sampling-chain logprobs.
    """
    t = rec["tokens"]
    txt, lp, ch = t["text"], t["chosen_lp"], t["channel"]
    keep = [i for i, c in enumerate(ch) if c == "r"]
    return ([txt[i] for i in keep],
            np.array([-float(lp[i]) for i in keep], float))


def load_sember(v2_seed=None):
    cells = {c: {r["question_id"]: r for r in jl(f"results/device/accuracy_{c}.jsonl")}
             for c in ("C1", "C2", "C3", "C4")}
    k = {}
    for r in jl("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"):
        if r["mode"] == "batched":
            k.setdefault(r["cell"], {})[r["question_id"]] = r
    ids = sorted(set(cells["C3"]) & set(cells["C1"]) & set(cells["C2"])
                 & set(k["K1"]) & set(k["K3"]))
    s1, s2 = _r8b_seed(1), _r8b_seed(2)
    if v2_seed is not None:
        ids = sorted(set(ids) & set(s1) & set(s2))
    nright = (np.array([int(cells["C3"][i]["correct"]) for i in ids])
              + np.array([int(s1[i]["correct"]) for i in ids])
              + np.array([int(s2[i]["correct"]) for i in ids])) if (s1 and s2) else None
    # v2: trace text, per-token uncertainty and the device label all come from ONE
    # generation. Seed-1 logprobs cannot be attached to the seed-0 (C3) trace.
    dev = {1: s1, 2: s2}.get(v2_seed)
    series = [_r8b_series(dev[i]) for i in ids] if v2_seed else None
    return dict(
        name="sember", ids=ids,
        groups=np.array([cells["C1"][i]["video_id"] for i in ids]),
        trace=([ "".join(x[0]) for x in series] if v2_seed
               else [cells["C3"][i].get("reasoning_text") or "" for i in ids]),
        tok_text=([x[0] for x in series] if v2_seed else None),
        unc=([x[1] for x in series] if v2_seed else None),
        nright=nright, n_samples=3,
        device_ok=np.array([bool((dev[i] if v2_seed else cells["C3"][i])["correct"])
                            for i in ids]),
        cloud_ok=np.array([bool(k["K1"][i]["correct"]) for i in ids]),
        evidence_miss=np.array([not bool(k["K3"][i]["evidence_covered"]) for i in ids]),
        query=[_sember_query(cells["C1"][i]) for i in ids],
        extra_num=np.array([[float(cells["C1"][i]["question_time"])] for i in ids]),
        extra_cat=[cells["C1"][i].get("question_category") or "none" for i in ids],
        letters=list("ABCDE"),
        conf=None,
        part3=dict(c1=np.array([bool(cells["C1"][i]["correct"]) for i in ids]),
                   c2=np.array([bool(cells["C2"][i]["correct"]) for i in ids]),
                   k3=np.array([bool(k["K3"][i]["correct"]) for i in ids]),
                   k1=np.array([bool(k["K1"][i]["correct"]) for i in ids])),
    )


def _sember_query(rec):
    """S-EMBER stores no question text in the device cells; the MCQ file has it."""
    return _MCQ[rec["question_id"]]


def _r8c_seed(seed):
    recs = {}
    for part in sorted((ROOT / "results/erqa/r8c_signals").glob(
            f"r8c_erqa_thinking_s{seed}_part*.jsonl.gz")):
        for r in jl(f"results/erqa/r8c_signals/{part.name}"):
            if not r.get("oom"):
                recs[r["qid"]] = r
    return recs


def load_erqa(v2_seed=None):
    dev = [r for r in jl("results/erqa/r4_signals/r4_erqa_thinking.jsonl") if not r.get("oom")]
    dev = {r["qid"]: r for r in dev}
    e1, e2 = _r8c_seed(1), _r8c_seed(2)
    ins = {r["qid"]: r for r in jl("results/erqa/r4_signals/r4_erqa_instruct.jsonl")
           if not r.get("oom")}
    cloud = {t["question_id"]: t
             for t in jl("results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl")
             if t["arm"] == "C"}
    ids = sorted(set(dev) & set(cloud) & set(ins))
    if v2_seed is not None:
        ids = sorted(set(ids) & set(e1) & set(e2))
    nright = (np.array([int(dev[i]["correct"]) for i in ids])
              + np.array([int(e1[i]["correct"]) for i in ids])
              + np.array([int(e2[i]["correct"]) for i in ids])) if (e1 and e2) else None
    d2 = {1: e1, 2: e2}.get(v2_seed)
    src = d2 if v2_seed else dev
    # R8c records no per-step text, so the step index IS the reasoning-token index.
    unc = ([np.array(d2[i]["steps"]["ent_bits"][:d2[i]["n_think_tokens_in_steps"]], float)
            for i in ids] if v2_seed else None)
    return dict(
        name="erqa", ids=ids,
        groups=np.array([str(i) for i in ids]),
        trace=[src[i].get("think_text") or "" for i in ids],
        tok_text=None, unc=unc, nright=nright, n_samples=3,
        device_ok=np.array([bool(src[i]["correct"]) for i in ids]),
        cloud_ok=np.array([bool(cloud[i]["correct"]) for i in ids]),
        evidence_miss=None,
        query=[_ERQA_Q[i] for i in ids],
        extra_num=np.zeros((len(ids), 0)),
        extra_cat=[dev[i].get("category") or "none" for i in ids],
        letters=list("ABCD"),
        # final-answer confidence baseline: the device's own option-letter distribution
        conf=np.array([max(src[i]["option_prob_norm"].values()) for i in ids], float),
        part3=None,
    )


# ───────────────────────────────────────────────────── prefix features ────
def cut_prefixes(tokenizer, traces, k):
    if k == 0:
        return [""] * len(traces), np.zeros(len(traces), int), np.ones(len(traces), bool)
    out, ntok, closed = [], [], []
    for t in traces:
        ids = tokenizer.encode(t, add_special_tokens=False) if t else []
        take = ids[:k]
        out.append(tokenizer.decode(take) if take else "")
        ntok.append(len(take))
        closed.append(len(ids) <= k)          # the trace finished within k tokens
    return out, np.array(ntok), np.array(closed, bool)


def repeated(text):
    w = text.split()
    g3 = [" ".join(w[i:i + 3]) for i in range(max(0, len(w) - 2))]
    c3 = Counter(g3)
    rep3 = sum(v - 1 for v in c3.values() if v > 1)
    max3 = max(c3.values()) if c3 else 0
    sents = [s.strip() for s in re.split(r'[.!?\n]+', text) if len(s.strip()) > 10]
    cs = Counter(sents)
    reps = sum(v - 1 for v in cs.values() if v > 1)
    maxs = max(cs.values()) if cs else 0
    return [rep3, max3, reps, maxs]


UNC_THRESH = [0.1, 0.5, 1.0, 2.0]
UNC_NAMES = (["unc_mean", "unc_sd", "unc_max", "unc_min", "unc_last", "unc_sum",
              "unc_slope", "unc_mean_firsthalf", "unc_mean_secondhalf", "unc_n"]
             + [f"unc_frac_gt_{t}" for t in UNC_THRESH])


def unc_features(unc_list, k):
    """Summaries of the per-token uncertainty over the first k reasoning tokens.

    S-EMBER uses -chosen_logprob, ERQA uses full-vocab entropy in bits; both are
    oriented so larger means less certain. They are different quantities measured
    on different stacks and are never pooled across workloads.
    """
    rows = []
    for u in unc_list:
        v = u[:k] if k != "full" else u
        if len(v) == 0:
            rows.append([0.0] * len(UNC_NAMES))
            continue
        h = max(1, len(v) // 2)
        sl = (float(np.polyfit(np.arange(len(v)), v, 1)[0]) if len(v) > 1 else 0.0)
        rows.append([float(v.mean()), float(v.std()), float(v.max()), float(v.min()),
                     float(v[-1]), float(v.sum()), sl, float(v[:h].mean()),
                     float(v[h:].mean()) if len(v) > h else float(v[:h].mean()),
                     float(len(v))]
                    + [float((v > t).mean()) for t in UNC_THRESH])
    return np.array(rows, float)


HAND_NAMES = (["hesitation_wait", "hesitation_but", "hesitation_total",
               "n_letter_mentions", "n_letter_changes", "letter_appears"]
              + ["rep3_total", "rep3_max", "repsent_total", "repsent_max"]
              + [f"phrase::{p}" for p in MISSING_EVIDENCE_PHRASES]
              + ["missing_evidence_total", "trace_closed_by_k", "n_prefix_tokens",
                 "n_prefix_chars"])


def hand_features(prefixes, ntok, closed, letters):
    rows = []
    for text, nt, cl in zip(prefixes, ntok, closed):
        rs = R4S.reasoning_signals(text, letters)
        low = text.lower()
        ph = [low.count(p) for p in MISSING_EVIDENCE_PHRASES]
        rows.append([rs["hesitation_wait"], rs["hesitation_but"], rs["hesitation_total"],
                     rs["n_letter_mentions"], rs["n_letter_changes"],
                     int(rs["letter_appears_in_reasoning"])]
                    + repeated(text) + ph + [sum(ph), int(cl), int(nt), len(text)])
    return np.array(rows, float)


# ──────────────────────────────────────────────────────── routers ────
def _lr():
    return LogisticRegression(max_iter=3000, C=1.0, solver="lbfgs")


def oof_scores(kind, X_text, X_num, y, folds, task):
    """Out-of-fold score for one router. Everything is fitted inside training folds."""
    n = len(y)
    out = np.zeros(n)
    for tr, te in folds:
        if kind == "text":
            from scipy.sparse import hstack, csr_matrix
            A = B = None
            try:
                vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True,
                                      max_features=50000)
                A = vec.fit_transform([X_text[i] for i in tr])
                B = vec.transform([X_text[i] for i in te])
            except ValueError:
                # empty vocabulary: every prefix in this fold is blank (k = 0). The
                # router degenerates to its numeric part, which is the pre-registered
                # k = 0 control: query+prefix at k = 0 must equal query-only.
                A = csr_matrix((len(tr), 0))
                B = csr_matrix((len(te), 0))
            if X_num is not None and X_num.shape[1]:
                sc = StandardScaler().fit(X_num[tr])
                A = hstack([A, csr_matrix(sc.transform(X_num[tr]))]).tocsr()
                B = hstack([B, csr_matrix(sc.transform(X_num[te]))]).tocsr()
            if A.shape[1] == 0:
                out[te] = (float(np.mean(y[tr])) if task != "gain"
                           else float(np.mean(y[tr])))
                continue
        else:
            sc = StandardScaler().fit(X_num[tr])
            A, B = sc.transform(X_num[tr]), sc.transform(X_num[te])
            A, B = np.nan_to_num(A), np.nan_to_num(B)
            keep = A.std(axis=0) > 0
            if not keep.any():
                out[te] = float(np.mean(y[tr]))
                continue
            A, B = A[:, keep], B[:, keep]
        yt = y[tr]
        if task == "gain":
            m = Ridge(alpha=1.0).fit(A, yt)
            out[te] = m.predict(B)
        else:
            if len(np.unique(yt)) < 2:
                out[te] = float(yt.mean())
                continue
            m = _lr().fit(A, yt)
            out[te] = m.predict_proba(B)[:, 1]
    return out


def auroc(score, label):
    """Mann-Whitney U, tie-corrected; identical to experiments/erqa/r4_analyse.auroc."""
    return R4S_auroc(score, label)


def R4S_auroc(score, label):
    score = np.asarray(score, float)
    label = np.asarray(label, bool)
    n1, n0 = label.sum(), (~label).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), float)
    s = score[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return (ranks[label].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def boot_ci_stat(fn, n, groups, clustered, nboot=NBOOT, seed=SEED):
    """Percentile CI; video-clustered for S-EMBER, question-level otherwise."""
    if clustered:
        vals = clustered_bootstrap(groups, fn, nboot=nboot, seed=seed)
    else:
        rng = np.random.default_rng(seed)
        vals = np.array([fn(rng.integers(0, n, n)) for _ in range(nboot)])
    vals = np.asarray(vals, float)
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return (float("nan"), float("nan"))
    return tuple(float(x) for x in np.percentile(vals, [2.5, 97.5]))


def escalate_acc(order, dev_ok, cloud_ok, k):
    esc = np.zeros(len(dev_ok), bool)
    esc[order[:k]] = True
    return float(np.where(esc, cloud_ok, dev_ok).mean())


def acc_at_e(score, dev_ok, cloud_ok, e, descending=True):
    n = len(dev_ok)
    k = int(round(e * n))
    order = np.argsort(-score if descending else score, kind="mergesort")
    return escalate_acc(order, dev_ok, cloud_ok, k)


def random_acc(dev_ok, cloud_ok, e, draws=RANDOM_DRAWS, seed=SEED):
    n = len(dev_ok)
    k = int(round(e * n))
    rng = np.random.default_rng(seed)
    return float(np.mean([escalate_acc(rng.permutation(n), dev_ok, cloud_ok, k)
                          for _ in range(draws)]))


def oracle_acc(dev_ok, cloud_ok, e):
    helps = cloud_ok.astype(int) - dev_ok.astype(int)
    return escalate_acc(np.argsort(-helps, kind="mergesort"), dev_ok, cloud_ok,
                        int(round(e * len(dev_ok))))


# ───────────────────────────────────────────── Orin decision latency ────
def orin_latency_by_k(ks):
    """Median seconds from request submit to the k-th REASONING token, on the Orin.

    Token timestamps in tokens_4bt_f16_F16.jsonl.gz are seconds since submit and
    already include prefill, so no TTFT is added. Standalone, uncontended run.
    """
    rows = jl("results/device/tokens_4bt_f16_F16.jsonl.gz")
    out = {}
    for k in ks:
        if k == 0:
            out[k] = 0.0            # decidable before generation starts
            continue
        v = []
        for r in rows:
            ts = [t[0] for t in r["tokens"] if t[1] == "reason"]
            if ts:
                v.append(ts[min(k, len(ts)) - 1])
        out[k] = float(np.median(v)) if v else float("nan")
    out["full"] = float(np.median([max([t[0] for t in r["tokens"]], default=np.nan)
                                   for r in rows]))
    out["_n"] = len(rows)
    return out


# ───────────────────────────────────────────────────────────── main ────
_MCQ, _ERQA_Q = {}, {}


def build_question_text():
    """Question + options text for the query-only router, for both workloads."""
    global _MCQ, _ERQA_Q
    for r in jl("results/sember/study_h/data/sember_mcq.jsonl"):
        opts = r.get("options") or r.get("choices") or []
        if isinstance(opts, dict):
            opts = [f"{k}. {v}" for k, v in sorted(opts.items())]
        _MCQ[r["question_id"]] = (r.get("question") or "") + " " + " ".join(map(str, opts))
    qf = ROOT / "results/escalation/study_r8a/erqa_question_text.json"
    if qf.exists():
        _ERQA_Q.update({int(k): v for k, v in json.load(open(qf)).items()})
    else:
        from datasets import load_dataset
        ds = load_dataset("RunsenXu/ERQA", verification_mode="no_checks")["test"]
        for i, row in enumerate(ds):
            _ERQA_Q[i] = row["question"]
        json.dump({str(k): v for k, v in _ERQA_Q.items()}, open(qf, "w"))


def embed(texts, cache_path):
    """Frozen sentence embeddings; the model is never fitted, only the LR on top is."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        return np.load(cache_path)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(EMB_MODEL, device="cpu")
    v = m.encode(texts, batch_size=64, show_progress_bar=False,
                 convert_to_numpy=True, normalize_embeddings=True)
    np.save(cache_path, v)
    return v


def folds_for(ds):
    if ds["name"] == "sember":
        return list(GroupKFold(n_splits=NFOLD).split(np.zeros(len(ds["ids"])),
                                                     groups=ds["groups"]))
    return list(KFold(n_splits=NFOLD, shuffle=True, random_state=SEED)
                .split(np.zeros(len(ds["ids"]))))


def onehot(cats):
    vals = sorted(set(cats))
    idx = {v: i for i, v in enumerate(vals)}
    M = np.zeros((len(cats), len(vals)))
    for i, c in enumerate(cats):
        M[i, idx[c]] = 1
    return M


def run_dataset(ds, tokenizer, no_embed=False, file_tag=""):
    name = ds["name"]
    clustered = (name == "sember")
    n = len(ds["ids"])
    folds = folds_for(ds)
    dev_ok, cloud_ok = ds["device_ok"], ds["cloud_ok"]
    gain = cloud_ok.astype(int) - dev_ok.astype(int)
    y_fail = ~dev_ok
    groups = ds["groups"]
    res = dict(name=name, n=n, n_folds=NFOLD,
               device_acc=float(dev_ok.mean()), cloud_acc=float(cloud_ok.mean()),
               gain_counts={str(v): int((gain == v).sum()) for v in (-1, 0, 1)})
    print(f"\n=== {name}: n={n} device {100*dev_ok.mean():.2f}% cloud {100*cloud_ok.mean():.2f}%",
          flush=True)

    q_num = np.hstack([ds["extra_num"], onehot(ds["extra_cat"])]) if name == "sember" \
        else onehot(ds["extra_cat"])
    q_text = ds["query"]

    # ---- query-only router (the comparator the gate is defined against) ----
    routers = {}
    routers["query_only"] = dict(
        fail=oof_scores("text", q_text, q_num, y_fail, folds, "fail"),
        gain=oof_scores("text", q_text, q_num, gain, folds, "gain"), k=None, latency=0.0)

    # ---- prefix routers ----
    lat = orin_latency_by_k(KS)
    res["decision_latency_s"] = lat
    feat_report = {}
    cuts = {}
    for k in KS + ["full"]:
        kk = 10 ** 9 if k == "full" else k
        pre, ntok, closed = cut_prefixes(tokenizer, ds["trace"], kk)
        cuts[k] = (pre, ntok, closed)
        H = hand_features(pre, ntok, closed, ds["letters"])
        feat_report[str(k)] = {
            nm: dict(mean=float(H[:, j].mean()), std=float(H[:, j].std()),
                     nonzero=int((H[:, j] != 0).sum()),
                     status=("CONSTANT" if H[:, j].std() == 0 else "varies"))
            for j, nm in enumerate(HAND_NAMES)}
        E = None
        if not no_embed:
            E = embed(pre, EMB_CACHE / f"emb_{name}_k{k}.npy")
        for tag, Xn, Xt in [("hand", H, None), ("tfidf", None, pre),
                            ("emb", E, None)]:
            if tag == "emb" and E is None:
                continue
            key = f"prefix_{tag}_k{k}"
            kind = "text" if Xt is not None else "num"
            routers[key] = dict(
                fail=oof_scores(kind, Xt, Xn, y_fail, folds, "fail"),
                gain=oof_scores(kind, Xt, Xn, gain, folds, "gain"),
                k=k, latency=lat[k])
            # query + prefix
            key2 = f"query+prefix_{tag}_k{k}"
            if Xt is not None:
                jt = [a + " \n " + b for a, b in zip(q_text, Xt)]
                routers[key2] = dict(
                    fail=oof_scores("text", jt, q_num, y_fail, folds, "fail"),
                    gain=oof_scores("text", jt, q_num, gain, folds, "gain"),
                    k=k, latency=lat[k])
            else:
                routers[key2] = dict(
                    fail=oof_scores("text", q_text, np.hstack([q_num, Xn]), y_fail, folds, "fail"),
                    gain=oof_scores("text", q_text, np.hstack([q_num, Xn]), gain, folds, "gain"),
                    k=k, latency=lat[k])
            print(f"  fitted {key} / {key2}", flush=True)
        if ds.get("unc") is not None:
            U = unc_features(ds["unc"], kk if k != "full" else "full")
            feat_report[str(k)].update({
                nm: dict(mean=float(U[:, j].mean()), std=float(U[:, j].std()),
                         nonzero=int((U[:, j] != 0).sum()),
                         status=("CONSTANT" if U[:, j].std() == 0 else "varies"))
                for j, nm in enumerate(UNC_NAMES)})
            for tag, Xn in [("unc", U), ("handunc", np.hstack([H, U]))]:
                routers[f"prefix_{tag}_k{k}"] = dict(
                    fail=oof_scores("num", None, Xn, y_fail, folds, "fail"),
                    gain=oof_scores("num", None, Xn, gain, folds, "gain"),
                    k=k, latency=lat[k])
                routers[f"query+prefix_{tag}_k{k}"] = dict(
                    fail=oof_scores("text", q_text, np.hstack([q_num, Xn]), y_fail,
                                    folds, "fail"),
                    gain=oof_scores("text", q_text, np.hstack([q_num, Xn]), gain,
                                    folds, "gain"),
                    k=k, latency=lat[k])
            print(f"  fitted prefix_unc_k{k} / prefix_handunc_k{k}", flush=True)

        # Step 5 alternative explanation: length alone
        L = np.column_stack([ntok, closed.astype(float)])
        routers[f"length_only_k{k}"] = dict(
            fail=oof_scores("num", None, L, y_fail, folds, "fail"),
            gain=oof_scores("num", None, L, gain, folds, "gain"), k=k, latency=lat[k])

    # ---- Step 4 controls ----
    rng = np.random.default_rng(SEED)
    pre100, nt100, cl100 = cuts[100]
    H100 = hand_features(pre100, nt100, cl100, ds["letters"])
    Hs = H100.copy()
    for tr, te in folds:
        perm = rng.permutation(len(tr))
        Hs[tr] = H100[np.array(tr)[perm]]
    routers["CONTROL_shuffled_prefix_k100"] = dict(
        fail=oof_scores("text", q_text, np.hstack([q_num, Hs]), y_fail, folds, "fail"),
        gain=oof_scores("text", q_text, np.hstack([q_num, Hs]), gain, folds, "gain"),
        k=100, latency=lat[100])

    # ---- ERQA final-answer confidence baseline ----
    if ds["conf"] is not None:
        routers["answer_confidence"] = dict(fail=-ds["conf"], gain=-ds["conf"],
                                            k="full", latency=lat["full"])

    # ---- PART 1: held-out AUROC, and the PAIRED delta against the query-only router ----
    part1 = {}
    q_fail = routers["query_only"]["fail"]
    for key, r in routers.items():
        row = {}
        targets = [("device_incorrect", y_fail)]
        if ds["evidence_miss"] is not None:
            targets.append(("evidence_outside_window", ds["evidence_miss"]))
        if ds.get("nright") is not None:
            # better-powered: wrong on every one of the repeated samples
            targets.append(("wrong_on_all_samples", ds["nright"] == 0))
        for tgt, y in targets:
            sc = r["fail"]
            a = R4S_auroc(sc, y)
            lo, hi = boot_ci_stat(lambda idx: R4S_auroc(sc[idx], y[idx]), n, groups, clustered)
            dq = float(a - R4S_auroc(q_fail, y))

            def dfn(idx, sc=sc, y=y):
                return R4S_auroc(sc[idx], y[idx]) - R4S_auroc(q_fail[idx], y[idx])
            dlo, dhi = boot_ci_stat(dfn, n, groups, clustered)
            row[tgt] = dict(auroc=round(float(a), 4), ci=[round(lo, 4), round(hi, 4)],
                            delta_vs_query_only=round(dq, 4),
                            delta_ci=[round(dlo, 4), round(dhi, 4)])
        part1[key] = dict(k=r["k"], latency_s=r["latency"], **row)

    # ---- PART 2: escalation utility ----
    base_q = routers["query_only"]
    part2 = {}
    for key, r in routers.items():
        cells = {}
        for e in RATES:
            for rank, desc in [("by_gain", True), ("by_failure", True)]:
                sc = r["gain"] if rank == "by_gain" else r["fail"]
                a = acc_at_e(sc, dev_ok, cloud_ok, e, descending=desc)
                bq = base_q["gain"] if rank == "by_gain" else base_q["fail"]
                d = a - acc_at_e(bq, dev_ok, cloud_ok, e, descending=desc)

                def diff(idx, sc=sc, bq=bq, e=e, desc=desc):
                    return (acc_at_e(sc[idx], dev_ok[idx], cloud_ok[idx], e, desc)
                            - acc_at_e(bq[idx], dev_ok[idx], cloud_ok[idx], e, desc))
                lo, hi = boot_ci_stat(diff, n, groups, clustered)
                cells[f"e{e}_{rank}"] = dict(
                    acc=round(100 * a, 3), delta_vs_query_only=round(100 * d, 3),
                    ci=[round(100 * lo, 3), round(100 * hi, 3)])
        part2[key] = dict(k=r["k"], latency_s=r["latency"], **cells)
    if ds.get("nright") is not None:
        pdev = ds["nright"] / float(ds["n_samples"])
        bq = base_q["gain"]
        for key, r in routers.items():
            sc = r["gain"]
            a = acc_at_e(sc, pdev, cloud_ok.astype(float), 0.2)
            d = a - acc_at_e(bq, pdev, cloud_ok.astype(float), 0.2)

            def diff(idx, sc=sc, bq=bq):
                return (acc_at_e(sc[idx], pdev[idx], cloud_ok[idx].astype(float), 0.2)
                        - acc_at_e(bq[idx], pdev[idx], cloud_ok[idx].astype(float), 0.2))
            lo, hi = boot_ci_stat(diff, n, groups, clustered)
            part2[key]["e0.2_by_gain_expected_device_acc"] = dict(
                acc=round(100 * a, 3), delta_vs_query_only=round(100 * d, 3),
                ci=[round(100 * lo, 3), round(100 * hi, 3)])
    part2["_baselines"] = {
        f"e{e}": dict(random=round(100 * random_acc(dev_ok, cloud_ok, e), 3),
                      oracle=round(100 * oracle_acc(dev_ok, cloud_ok, e), 3),
                      always_local=round(100 * dev_ok.mean(), 3),
                      always_cloud=round(100 * cloud_ok.mean(), 3))
        for e in RATES}

    np.savez_compressed(
        OUT / f"oof_scores_{name}{file_tag}.npz",
        device_ok=dev_ok, cloud_ok=cloud_ok, gain=gain, groups=groups,
        evidence_miss=(ds["evidence_miss"] if ds["evidence_miss"] is not None
                       else np.zeros(n, bool)),
        **{f"{k}::fail": v["fail"] for k, v in routers.items()},
        **{f"{k}::gain": v["gain"] for k, v in routers.items()})
    res.update(part1=part1, part2=part2, feature_audit=feat_report,
               routers=sorted(routers))

    # ---- Step 3: one traced unit at each k ----
    pick = int(np.argmax((gain == 1) & (~dev_ok)))
    trace_unit = {"question_id": str(ds["ids"][pick]), "device_correct": bool(dev_ok[pick]),
                  "cloud_correct": bool(cloud_ok[pick]), "gain": int(gain[pick]),
                  "group": str(groups[pick]), "per_k": {}}
    for k in KS:
        pre, ntok, closed = cuts[k]
        H = hand_features([pre[pick]], ntok[pick:pick + 1], closed[pick:pick + 1], ds["letters"])
        key = f"query+prefix_hand_k{k}"
        sc = routers[key]["gain"]
        order = np.argsort(-sc, kind="mergesort")
        rank = int(np.where(order == pick)[0][0])
        trace_unit["per_k"][str(k)] = dict(
            prefix_chars=len(pre[pick]), prefix_tokens=int(ntok[pick]),
            prefix_head=pre[pick][:240],
            features={nm: float(v) for nm, v in zip(HAND_NAMES, H[0]) if v != 0},
            predicted_gain=round(float(sc[pick]), 5), rank_of_n=f"{rank}/{n}",
            escalated_at_e02=bool(rank < int(round(0.2 * n))))
    res["mechanism_step3_trace"] = trace_unit
    return res, routers


def part3_rescue(ds, routers):
    p = ds["part3"]
    c1, c2, k3, k1 = p["c1"], p["c2"], p["k3"], p["k1"]
    hist_dev = (~c1) & c2
    hist_cloud = (~k3) & k1
    hist_any = hist_dev | hist_cloud
    cap = (~c1) & k3
    both = (~c1) & (~c2) & (~k3) & k1
    none = (~c1) & ~(hist_any | cap | both)
    out = dict(
        n=len(c1),
        counts=dict(device_fails=int((~c1).sum()),
                    history_rescuable_device=int(hist_dev.sum()),
                    history_rescuable_cloud=int(hist_cloud.sum()),
                    history_rescuable_either=int(hist_any.sum()),
                    capability_rescuable=int(cap.sum()),
                    both_needed=int(both.sum()),
                    none=int(none.sum())),
        overlaps=dict(history_and_capability=int((hist_any & cap).sum()),
                      history_and_both=int((hist_any & both).sum()),
                      capability_and_both=int((cap & both).sum())),
    )
    fails = ~c1
    y = cap[fails]
    sub = {}
    for key, r in routers.items():
        if not key.startswith(("prefix_", "query+prefix_", "query_only", "length_only")):
            continue
        sc = r["fail"][fails]
        if len(np.unique(y)) > 1:
            sub[key] = round(float(R4S_auroc(sc, y)), 4)
    out["auroc_capability_vs_history_among_device_failures"] = dict(
        definition="label 1 = capability-rescuable (C1 wrong, K3 right); label 0 = the rest of "
                   "the device failures, which include the history-rescuable ones",
        n=int(fails.sum()), n_positive=int(y.sum()), per_router=sub)
    return out


def gate(results):
    """PARTIAL REASONING ADDS VALUE iff some query+prefix router at k<=100 beats the
    query-only router at e=0.2 by >= 2 pp with a 95% CI excluding 0, on either workload."""
    fired, detail = False, {}
    for name, res in results.items():
        best = None
        for key, row in res["part2"].items():
            if not key.startswith("query+prefix_"):
                continue
            k = row["k"]
            if k == "full" or k is None or k > 100:
                continue
            for rank in ("by_gain", "by_failure"):
                c = row[f"e0.2_{rank}"]
                ok = c["delta_vs_query_only"] >= 2.0 and c["ci"][0] > 0
                cand = dict(router=key, rank=rank, delta=c["delta_vs_query_only"],
                            ci=c["ci"], acc=c["acc"], k=k, passes=ok)
                if best is None or cand["delta"] > best["delta"]:
                    best = cand
                if ok:
                    fired = True
        detail[name] = best
    return dict(verdict="PARTIAL REASONING ADDS VALUE" if fired else "NOT SHOWN",
                best_per_workload=detail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", default="both", choices=["both", "sember", "erqa"])
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--v2-seed", type=int, default=None,
                    help="R8b/R8c seed supplying per-token uncertainty; enables R8a-v2")
    args = ap.parse_args()

    t0 = time.time()
    suffix = f"_{args.tag}" if args.tag else ""
    build_question_text()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(TOK_4BT)

    results, all_routers = {}, {}
    if args.workload in ("both", "sember"):
        ds = load_sember(args.v2_seed)
        r, rt = run_dataset(ds, tokenizer, args.no_embed, suffix)
        r["part3_rescue_matrix"] = part3_rescue(ds, rt)
        results["sember"] = r
        all_routers["sember"] = rt
    if args.workload in ("both", "erqa"):
        ds = load_erqa(args.v2_seed)
        r, rt = run_dataset(ds, tokenizer, args.no_embed, suffix)
        results["erqa"] = r
        all_routers["erqa"] = rt

    payload = dict(
        study=("StudyR8a-v2" if args.v2_seed else "StudyR8a"),
        v2_seed=args.v2_seed, ks=KS, rates=RATES, nboot=NBOOT, seed=SEED, n_folds=NFOLD,
        embedding_model=(None if args.no_embed else EMB_MODEL),
        missing_evidence_phrases=MISSING_EVIDENCE_PHRASES,
        device_arm=(dict(
            sember=f"accuracy_C3_logprobs_s{args.v2_seed} (R8b; 4B-Thinking, DEV-RECENT, "
                   "A6000 llama.cpp F16; uncertainty = -chosen_logprob, pre-sampling-chain)",
            erqa=f"r8c_erqa_thinking_s{args.v2_seed} (R8c; 4B-Thinking, RTX 3090 Ti, HF sdpa, "
                 "temperature 1.0; uncertainty = full-vocab entropy in bits)")
            if args.v2_seed else
            dict(sember="accuracy_C3.jsonl (4B-Thinking, DEV-RECENT, A6000 llama.cpp F16)",
                 erqa="r4_erqa_thinking.jsonl (4B-Thinking, RTX 3090 Ti, HF sdpa)")),
        cloud_arm=dict(sember="study_r1 K1 (32B-Instruct RICH, H100 vLLM)",
                       erqa="study_r arm C (32B-Instruct, H100 HF fa2)"),
        contended="R8a ran concurrently with R8b (A6000) and R8c (3090 Ti); it measures no "
                  "latency of its own. Decision latency is the Orin's standalone timing.",
        results=results, gate=gate(results),
        elapsed_h=round((time.time() - t0) / 3600, 3),
        _provenance=stamp(script="study_r8a_prefix_signals.py", model="none", device="cpu",
                          n=sum(r["n"] for r in results.values()), args=args),
    )
    p = OUT / f"study_r8a_results{suffix}.json"
    json.dump(payload, open(p, "w"), indent=1)
    print(f"\nGATE: {payload['gate']['verdict']}")
    for w, b in payload["gate"]["best_per_workload"].items():
        print(f"  {w}: {b}")
    print(f"-> {p}  ({(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    main()
