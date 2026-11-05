#!/usr/bin/env python3
"""StudyD3-nexar analysis (CPU; .venv). Pre-registered in research/EXPERIMENTS.md (StudyD3-nexar).

PRIMARY (N = 9, SMALL): score = log P(Yes) floored at 1e-12. Subgroup AUROC at offset o = the subgroup's positive
clips at o (ALL offsets, including prefixes before alert — deliberate departure from D2's unscored rule) vs all
negative clips at o. gap(g) = mean over PRIMARY_OFFSETS of AUROC32 − AUROC4. Statistic = gap(sudden) − gap(slow);
bootstrap resampling sudden, slow and negative clips separately (2,000, seed 0). Supported iff CI excludes 0 and > 0.
`--sanity` applies the same code to the D2 pilot's SMALL results (expects slow +0.006, sudden +0.107, diff +0.100).
SECONDARY (labelled): (a) primary at N = 3 / N = 1, and on offsets 0, +1, +2; (b) per-clip mean 32B − 4B log-odds
difference over the primary offsets regressed on lead (OLS slope, clip bootstrap); (c) floor check: primary on
logit-AUROC, and gaps on offsets where 4B AUROC differs < 0.05 between subgroups; (d) reliability time (first offset
where AUROC reaches 0.70 / 0.75, linear interpolation over all 10 offsets; "never" otherwise) per subgroup x model,
bootstrapped 32B − 4B shift; (e) AUROC by model x N x offset on the usual scored positives and on a fixed slow cohort
(lead >= 1.5 s, all offsets), model x offset interaction on the logit scale, late (0, +1, +2) − early (−1.5, −1, −0.5);
(f) value of waiting: per clip, change in log-odds of the correct answer between consecutive offsets per model vs the
4B -> 32B change at the same offset (requests with a defined ground truth at both); (g) Urban / Highway AUROC and
recall at out-of-fold (GroupKFold 5 by clip) negative-derived thresholds for 1 % / 5 % FPR.
BASELINES (same scored requests): always-Yes; metadata LR (scene, weather, light); prefix-only optical-flow LR (17
features from the N = 9 prefix frames); out of fold by clip. EXPLORATORY observability: predict sudden vs slow (AUROC)
and the per-(clip, offset) 32B − 4B log-odds difference (R2) from F1 offset; F2 F1 + flow; F3 F2 + 4B log P(Yes) at
N = 9 and its change from the previous offset; out of fold by clip, clip-bootstrap CIs, incremental gains. No policy.
Writes results/dashcam/study_d3_nexar/d3_results_h100nvl.json.
"""
import argparse
import gzip
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

D = Path("results/dashcam/study_d3_nexar")
OFFSETS = [-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]
PRIMARY = [-1.5, -1.0, -0.5, 0.0, 1.0, 2.0]
LATE, EARLY = [0.0, 1.0, 2.0], [-1.5, -1.0, -0.5]
NBOOT, SEED, FLOOR = 2000, 0, 1e-12
MODELS = ("4BI", "32BI")


def open_rows():
    """Per-request rows; gzipped after the run (repo size limit), plain file accepted too."""
    p = D / "d3_requests_h100nvl.jsonl"
    return open(p) if p.exists() else gzip.open(str(p) + ".gz", "rt")


def lg(p):
    return float(np.log(max(p, FLOOR)))


def logit(p):
    p = min(max(p, FLOOR), 1 - FLOOR)
    return float(np.log(p / (1 - p)))


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return np.nan
    r = rankdata(np.concatenate([pos, neg]))
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def lauc(a):
    a = min(max(a, 1e-6), 1 - 1e-6)
    return np.log(a / (1 - a))


def ci(x):
    x = np.asarray([v for v in x if v is not None and not np.isnan(v)], float)
    return [float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))] if len(x) else None


# ----------------------------------------------------------------------------------------------- data
class Data:
    """S[model][clip] = {offset: score}; groups; negatives; meta."""

    def __init__(self, scores, clipinfo):
        self.S, self.info = scores, clipinfo
        self.sudden = sorted(c for c, i in clipinfo.items() if i["label"] == "positive" and i["subgroup"] == "sudden")
        self.slow = sorted(c for c, i in clipinfo.items() if i["label"] == "positive" and i["subgroup"] == "slow")
        self.neg = sorted(c for c, i in clipinfo.items() if i["label"] == "negative")


def subgroup_auc(d, m, pos_clips, neg_clips, o, f=lg):
    return auc([f(d.S[m][c][o]) for c in pos_clips], [f(d.S[m][c][o]) for c in neg_clips])


def gap(d, pos, neg, offs, f=lg, transform=None):
    v = []
    for o in offs:
        a32, a4 = subgroup_auc(d, "32BI", pos, neg, o, f), subgroup_auc(d, "4BI", pos, neg, o, f)
        v.append((lauc(a32) - lauc(a4)) if transform == "logit" else (a32 - a4))
    return float(np.mean(v))


def primary(d, offs=PRIMARY, transform=None, boot=True):
    gs, gw = gap(d, d.sudden, d.neg, offs, transform=transform), gap(d, d.slow, d.neg, offs, transform=transform)
    out = dict(n_sudden=len(d.sudden), n_slow=len(d.slow), n_neg=len(d.neg), offsets=offs, transform=transform or "auroc",
               gap_sudden=gs, gap_slow=gw, diff=gs - gw)
    if boot:
        rng = np.random.default_rng(SEED)
        bs, bsu, bsl = [], [], []
        for _ in range(NBOOT):
            su = list(rng.choice(d.sudden, len(d.sudden)))
            sl = list(rng.choice(d.slow, len(d.slow)))
            ng = list(rng.choice(d.neg, len(d.neg)))
            a, b = gap(d, su, ng, offs, transform=transform), gap(d, sl, ng, offs, transform=transform)
            bs.append(a - b)
            bsu.append(a)
            bsl.append(b)
        out.update(diff_ci95=ci(bs), gap_sudden_ci95=ci(bsu), gap_slow_ci95=ci(bsl))
        out["supported"] = bool(out["diff_ci95"][0] > 0 and out["diff"] > 0)
    return out


def load_d2():
    P = Path("results/dashcam/study_d2_nexar")
    reqs = {r["request_id"]: r for r in map(json.loads, open(P / "pilot_requests.jsonl"))}
    clips = {c["file_name"]: c for c in json.load(open(P / "pilot_sample.json"))["clips"]}
    S = {m: defaultdict(dict) for m in MODELS}
    for r in map(json.loads, open(P / "d2_requests_h100nvl.jsonl")):
        if r["grey"] or r["error"] or r["res"] != "small":
            continue
        q = reqs[r["request_id"]]
        S[r["model"]][q["file_name"]][q["offset"]] = r["p_yes"]
    info = {f: dict(label=c["label"], subgroup=(None if c["label"] == "negative" else
                                               ("sudden" if c["ref"] - c["time_of_alert"] < 1.5 else "slow")))
            for f, c in clips.items()}
    return Data(S, info)


def load_d3(n):
    man = [r for r in map(json.loads, open(D / "d3_requests_manifest.jsonl")) if r["n"] == n]
    byid = {r["request_id"]: r for r in man}
    S = {m: defaultdict(dict) for m in MODELS}
    rows = {}
    for r in map(json.loads, open_rows()):
        if r["grey"] or r["error"] or r["n"] != n:
            continue
        q = byid[r["request_id"]]
        S[r["model"]][q["file_name"]][q["offset"]] = r["p_yes"]
        rows[(r["model"], r["request_id"])] = r
    samp = json.load(open(D / "d3_sample.json"))
    info = {c["file_name"]: dict(label=c["label"], subgroup=c.get("subgroup"), lead=c.get("lead"), scene=c["scene"],
                                 weather=c["weather"], light=c["light"]) for c in samp["clips"]}
    return Data(S, info), man, rows, samp


# ----------------------------------------------------------------------------------------------- secondaries
def reliability(d, pos, neg, m, thr):
    a = [subgroup_auc(d, m, pos, neg, o) for o in OFFSETS]
    for i, (o, v) in enumerate(zip(OFFSETS, a)):
        if v >= thr:
            if i == 0:
                return o
            o0, v0 = OFFSETS[i - 1], a[i - 1]
            return o0 + (thr - v0) * (o - o0) / (v - v0)
    return None


def sec_reliability(d):
    out = {}
    rng = np.random.default_rng(SEED)
    for g, pos in (("sudden", d.sudden), ("slow", d.slow)):
        for thr in (0.70, 0.75):
            t = {m: reliability(d, pos, d.neg, m, thr) for m in MODELS}
            shifts, never = [], 0
            for _ in range(NBOOT):
                p = list(rng.choice(pos, len(pos)))
                ng = list(rng.choice(d.neg, len(d.neg)))
                t4, t32 = reliability(d, p, ng, "4BI", thr), reliability(d, p, ng, "32BI", thr)
                if t4 is None or t32 is None:
                    never += 1
                else:
                    shifts.append(t32 - t4)
            out[f"{g}/{thr}"] = dict(time_4B=t["4BI"], time_32B=t["32BI"],
                                     shift_32B_minus_4B=(t["32BI"] - t["4BI"]) if None not in t.values() else None,
                                     shift_ci95=ci(shifts), boot_never_reached=never,
                                     note="time = offset (s from the reference) where AUROC first reaches the "
                                          "threshold; None = never reached within -3..+2 s")
    return out


def sec_lead_regression(d):
    pos = d.sudden + d.slow
    x = np.array([d.info[c]["lead"] for c in pos])
    y = np.array([np.mean([logit(d.S["32BI"][c][o]) - logit(d.S["4BI"][c][o]) for o in PRIMARY]) for c in pos])
    slope = float(np.polyfit(x, y, 1)[0])
    rng = np.random.default_rng(SEED)
    bs = []
    for _ in range(NBOOT):
        i = rng.integers(0, len(pos), len(pos))
        bs.append(np.polyfit(x[i], y[i], 1)[0])
    return dict(n=len(pos), slope_logodds_per_s=slope, slope_ci95=ci(bs),
                mean_diff_sudden=float(np.mean([y[k] for k, c in enumerate(pos) if c in set(d.sudden)])),
                mean_diff_slow=float(np.mean([y[k] for k, c in enumerate(pos) if c in set(d.slow)])),
                note="y = per-clip mean over the primary offsets of logit P32(Yes) − logit P4(Yes); x = lead (s)")


def sec_floor(d):
    out = dict(logit_auroc=primary(d, transform="logit"))
    per = []
    for o in OFFSETS:
        a = {(g, m): subgroup_auc(d, m, pos, d.neg, o) for g, pos in (("sudden", d.sudden), ("slow", d.slow))
             for m in MODELS}
        per.append(dict(offset=o, **{f"{g}_{m}": a[(g, m)] for g, m in a},
                        gap_sudden=a[("sudden", "32BI")] - a[("sudden", "4BI")],
                        gap_slow=a[("slow", "32BI")] - a[("slow", "4BI")],
                        abs_4b_diff=abs(a[("sudden", "4BI")] - a[("slow", "4BI")])))
    sim = [r for r in per if r["abs_4b_diff"] < 0.05]
    out["per_offset"] = per
    out["matched_4B_offsets"] = dict(offsets=[r["offset"] for r in sim],
                                     mean_gap_sudden=float(np.mean([r["gap_sudden"] for r in sim])) if sim else None,
                                     mean_gap_slow=float(np.mean([r["gap_slow"] for r in sim])) if sim else None)
    return out


def sec_overall(d, man, rows, n):
    """(e): AUROC by model x offset on usual scored positives, and on the fixed slow cohort; interaction (logit)."""
    rq = {(r["file_name"], r["offset"]): r for r in man}
    res = {}
    for m in MODELS:
        for o in OFFSETS:
            pos = [c for c in d.sudden + d.slow if rq[(c, o)]["gt"] == "positive"]
            res[f"{m}/scored/{o}"] = dict(n_pos=len(pos), auroc=subgroup_auc(d, m, pos, d.neg, o))
            res[f"{m}/slow_cohort/{o}"] = dict(n_pos=len(d.slow), auroc=subgroup_auc(d, m, d.slow, d.neg, o))
    inter = {}
    rng = np.random.default_rng(SEED)
    for cohort in ("scored", "slow_cohort"):
        def stat(pos_by_off, neg):
            late = np.mean([lauc(subgroup_auc(d, "32BI", pos_by_off[o], neg, o)) -
                            lauc(subgroup_auc(d, "4BI", pos_by_off[o], neg, o)) for o in LATE])
            early = np.mean([lauc(subgroup_auc(d, "32BI", pos_by_off[o], neg, o)) -
                             lauc(subgroup_auc(d, "4BI", pos_by_off[o], neg, o)) for o in EARLY])
            return late - early
        allpos = d.sudden + d.slow if cohort == "scored" else d.slow
        pbo = {o: [c for c in allpos if cohort == "slow_cohort" or rq[(c, o)]["gt"] == "positive"] for o in OFFSETS}
        point = stat(pbo, d.neg)
        bs = []
        for _ in range(NBOOT):
            p = list(rng.choice(allpos, len(allpos)))
            ng = list(rng.choice(d.neg, len(d.neg)))
            pb = {o: [c for c in p if cohort == "slow_cohort" or rq[(c, o)]["gt"] == "positive"] for o in OFFSETS}
            bs.append(stat(pb, ng))
        inter[cohort] = dict(late_minus_early_logit_gap=float(point), ci95=ci(bs),
                             note="[logit AUROC32 − logit AUROC4] mean over late (0, +1, +2) − over early (−1.5, −1, −0.5)")
    return res, inter


def sec_waiting(d, man):
    rq = {(r["file_name"], r["offset"]): r for r in man}
    out = {}
    clips = d.sudden + d.slow + d.neg
    rng = np.random.default_rng(SEED)
    for o0, o1 in zip(OFFSETS[:-1], OFFSETS[1:]):
        cs = [c for c in clips if rq[(c, o0)]["gt"] != "unscored" and rq[(c, o1)]["gt"] != "unscored"]
        if not cs:
            continue

        def corr(m, c, o):
            v = logit(d.S[m][c][o])
            return v if d.info[c]["label"] == "positive" else -v
        w4 = np.array([corr("4BI", c, o1) - corr("4BI", c, o0) for c in cs])
        w32 = np.array([corr("32BI", c, o1) - corr("32BI", c, o0) for c in cs])
        up = np.array([corr("32BI", c, o0) - corr("4BI", c, o0) for c in cs])

        def bm(x):
            return ci([x[rng.integers(0, len(x), len(x))].mean() for _ in range(NBOOT)])
        out[f"{o0:+.1f}->{o1:+.1f}"] = dict(n=len(cs), wait_4B=float(w4.mean()), wait_4B_ci95=bm(w4),
                                            wait_32B=float(w32.mean()), wait_32B_ci95=bm(w32),
                                            upgrade_at_start=float(up.mean()), upgrade_ci95=bm(up))
    return out


def oof_threshold_recall(d, m, o, man, fprs=(0.01, 0.05)):
    from sklearn.model_selection import GroupKFold
    rq = {(r["file_name"], r["offset"]): r for r in man}
    pos = [c for c in d.sudden + d.slow if rq[(c, o)]["gt"] == "positive"]
    clips = pos + d.neg
    y = np.array([c in set(pos) for c in clips])
    s = np.array([lg(d.S[m][c][o]) for c in clips])
    out = {}
    for fpr in fprs:
        hit = np.zeros(len(clips), bool)
        for tr, te in GroupKFold(5).split(s, y, clips):
            neg_tr = s[tr][~y[tr]]
            thr = np.quantile(neg_tr, 1 - fpr)
            hit[te] = s[te] > thr
        out[f"recall_at_{int(fpr * 100)}pct_fpr"] = float(hit[y].mean()) if y.any() else None
        out[f"realised_fpr_{int(fpr * 100)}pct"] = float(hit[~y].mean())
    return out


def baselines(d, man, n9):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    rq = [r for r in n9 if r["gt"] != "unscored"]
    y = np.array([r["gt"] == "positive" for r in rq]).astype(int)
    cl = np.array([r["file_name"] for r in rq])
    off = np.array([r["offset"] for r in rq])
    with open(D / "flow_features.csv") as f:
        fr = {r["request_id"]: r for r in csv.DictReader(f)}
    feats = [k for k in next(iter(fr.values())) if k != "request_id"]

    def oof(X, mk):
        p = np.zeros(len(y))
        for tr, te in GroupKFold(5).split(X, y, cl):
            mdl = mk()
            mdl.fit(X[tr], y[tr])
            p[te] = mdl.predict_proba(X[te])[:, 1]
        return p
    Xm = np.array([[d.info[r["file_name"]][k] for k in ("scene", "weather", "light")] for r in rq], dtype=object)
    Xf = np.array([[float(fr[r["request_id"]][k]) for k in feats] for r in rq])
    pm = oof(Xm, lambda: make_pipeline(OneHotEncoder(handle_unknown="ignore"), LogisticRegression(max_iter=1000)))
    pf = oof(Xf, lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)))
    out = {}
    for name, p in (("metadata_LR", pm), ("flow_LR", pf)):
        for o in OFFSETS + ["pooled"]:
            i = np.arange(len(y)) if o == "pooled" else np.where(off == o)[0]
            out[f"{name}/{o}"] = dict(n=int(len(i)), auroc=float(auc(p[i][y[i] == 1], p[i][y[i] == 0])))
    for o in OFFSETS + ["pooled"]:
        i = np.arange(len(y)) if o == "pooled" else np.where(off == o)[0]
        out[f"always_yes/{o}"] = dict(n=int(len(i)), auroc=0.5, acc=float(y[i].mean()))
    return out, feats


def observability(d, man, rows, feats):
    """EXPLORATORY. Rows = (positive clip, offset) at N = 9."""
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    with open(D / "flow_features.csv") as f:
        fr = {r["request_id"]: r for r in csv.DictReader(f)}
    rq = {(r["file_name"], r["offset"]): r for r in man}
    pos = d.sudden + d.slow
    R = []
    for c in pos:
        prev = None
        for o in OFFSETS:
            p4 = lg(d.S["4BI"][c][o])
            R.append(dict(clip=c, offset=o, flow=[float(fr[rq[(c, o)]["request_id"]][k]) for k in feats], p4=p4,
                          dp4=0.0 if prev is None else p4 - prev, sudden=int(c in set(d.sudden)),
                          gapz=logit(d.S["32BI"][c][o]) - logit(d.S["4BI"][c][o])))
            prev = p4
    cl = np.array([r["clip"] for r in R])
    F = {"F1": np.array([[r["offset"]] for r in R]),
         "F2": np.array([[r["offset"]] + r["flow"] for r in R]),
         "F3": np.array([[r["offset"]] + r["flow"] + [r["p4"], r["dp4"]] for r in R])}
    ys, yg = np.array([r["sudden"] for r in R]), np.array([r["gapz"] for r in R])
    pred = {}
    for k, X in F.items():
        ps, pg = np.zeros(len(R)), np.zeros(len(R))
        for tr, te in GroupKFold(5).split(X, ys, cl):
            m1 = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X[tr], ys[tr])
            ps[te] = m1.predict_proba(X[te])[:, 1]
            m2 = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(X[tr], yg[tr])
            pg[te] = m2.predict(X[te])
        pred[k] = (ps, pg)
    uc = np.unique(cl)
    by = {c: np.where(cl == c)[0] for c in uc}
    rng = np.random.default_rng(SEED)

    def r2(y, p):
        return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    point = {k: (auc(ps[ys == 1], ps[ys == 0]), r2(yg, pg)) for k, (ps, pg) in pred.items()}
    boots = defaultdict(list)
    for _ in range(NBOOT):
        i = np.concatenate([by[c] for c in rng.choice(uc, len(uc))])
        v = {k: (auc(ps[i][ys[i] == 1], ps[i][ys[i] == 0]), r2(yg[i], pg[i])) for k, (ps, pg) in pred.items()}
        for k in v:
            boots[f"{k}_auc"].append(v[k][0])
            boots[f"{k}_r2"].append(v[k][1])
        boots["F2-F1_auc"].append(v["F2"][0] - v["F1"][0])
        boots["F3-F2_auc"].append(v["F3"][0] - v["F2"][0])
        boots["F2-F1_r2"].append(v["F2"][1] - v["F1"][1])
        boots["F3-F2_r2"].append(v["F3"][1] - v["F2"][1])
    out = {k: dict(sudden_vs_slow_auroc=point[k][0], auroc_ci95=ci(boots[f"{k}_auc"]),
                   gap_logodds_r2=point[k][1], r2_ci95=ci(boots[f"{k}_r2"])) for k in F}
    out["increments"] = {k: dict(point=(point[k.split("-")[0]][0 if "auc" in k else 1] -
                                        point[k.split("-")[1].split("_")[0]][0 if "auc" in k else 1]),
                                 ci95=ci(boots[k])) for k in ("F2-F1_auc", "F3-F2_auc", "F2-F1_r2", "F3-F2_r2")}
    out["label"] = "EXPLORATORY; rows = (positive clip, offset) at N = 9; features available at decision time; no " \
                   "elapsed time; GroupKFold 5 by clip; no policy built"
    return out


def checks(rows_all, man_all):
    real = [r for r in rows_all if not r["grey"] and not r["error"]]
    byk = {(r["model"], r["n"], r["request_id"]): r for r in real}
    out = {}
    for n in (1, 3, 9):
        ids = [r["request_id"] for r in man_all if r["n"] == n]
        both = [q for q in ids if all((m, n, q) in byk for m in MODELS)]
        out[f"N{n}"] = dict(n=len(ids), answered_both=len(both),
                            frames_equal=sum(byk[("4BI", n, q)]["frame_sha256"] == byk[("32BI", n, q)]["frame_sha256"]
                                             for q in both),
                            tokens_equal=sum(byk[("4BI", n, q)]["prompt_tokens"] == byk[("32BI", n, q)]["prompt_tokens"]
                                             for q in both),
                            prompt_tokens=dict(Counter(byk[("4BI", n, q)]["prompt_tokens"] for q in both).most_common(4)),
                            neither={m: sum(byk[(m, n, q)]["neither"] for q in ids if (m, n, q) in byk) for m in MODELS})
        for m in MODELS:
            g = [r for r in rows_all if r["grey"] and r["n"] == n and r["model"] == m and not r["error"]]
            if g:
                ps = [r["p_yes"] for r in g if r["p_yes"] is not None]
                out[f"N{n}"][f"grey_{m}"] = dict(n=len(g), yes_rate=float(np.mean([p >= 0.5 for p in ps])),
                                                 distinct=len({round(p, 12) for p in ps}), p_yes_median=float(np.median(ps)),
                                                 real_yes_rate=float(np.mean([r["p_yes"] >= 0.5 for r in real
                                                                              if r["model"] == m and r["n"] == n
                                                                              and r["p_yes"] is not None])))
    out["errors_and_retries"] = dict(error_rows=sum(bool(r["error"]) for r in rows_all),
                                     attempts=dict(Counter(r["attempt"] for r in rows_all)))
    out["causality_all"] = all(r["last_pts_le_end"] for r in man_all)
    return out


def write_summary(res):
    """Compact text summary (read without starting a process while latency jobs run)."""
    L = []
    def f(x, k=3):
        return "None" if x is None else (f"{x:+.{k}f}" if isinstance(x, float) else str(x))
    p = res["primary"]
    L.append(f"PRIMARY N9: gap sudden {f(p['gap_sudden'])} {p['gap_sudden_ci95']} | slow {f(p['gap_slow'])} "
             f"{p['gap_slow_ci95']} | diff {f(p['diff'])} CI {p['diff_ci95']} | supported {p['supported']} | "
             f"n {p['n_sudden']}/{p['n_slow']}/{p['n_neg']}")
    sec = res["secondary"]
    for k in ("a_N3", "a_N1", "a_offsets_0_1_2_N9"):
        q = sec[k]
        L.append(f"SEC {k}: sudden {f(q['gap_sudden'])} slow {f(q['gap_slow'])} diff {f(q['diff'])} CI {q['diff_ci95']}")
    b = sec["b_lead_regression"]
    L.append(f"SEC b: slope {f(b['slope_logodds_per_s'])} CI {b['slope_ci95']} mean diff sudden {f(b['mean_diff_sudden'])} "
             f"slow {f(b['mean_diff_slow'])} n {b['n']}")
    c = sec["c_floor"]
    lq = c["logit_auroc"]
    L.append(f"SEC c logit: diff {f(lq['diff'])} CI {lq['diff_ci95']}; matched-4B offsets {c['matched_4B_offsets']}")
    for r in c["per_offset"]:
        L.append("  c off {:+.1f}: 4B sud {:.3f} slow {:.3f} | 32B sud {:.3f} slow {:.3f} | gap sud {:+.3f} slow {:+.3f}".format(
            r["offset"], r["sudden_4BI"], r["slow_4BI"], r["sudden_32BI"], r["slow_32BI"], r["gap_sudden"], r["gap_slow"]))
    for k, v in sec["d_reliability"].items():
        L.append(f"SEC d {k}: 4B {v['time_4B']} 32B {v['time_32B']} shift {v['shift_32B_minus_4B']} CI {v['shift_ci95']} "
                 f"boot-never {v['boot_never_reached']}")
    for n, e in sec["e_overall"].items():
        for cohort in ("scored", "slow_cohort"):
            L.append(f"SEC e {n} {cohort}: " + " ".join(
                "{:+.1f}:{:.3f}/{:.3f}".format(o, e["auroc"][f"4BI/{cohort}/{o}"]["auroc"], e["auroc"][f"32BI/{cohort}/{o}"]["auroc"])
                for o in OFFSETS) + f" | interaction {f(e['interaction'][cohort]['late_minus_early_logit_gap'])} "
                f"{e['interaction'][cohort]['ci95']}")
    for k, v in sec["f_value_of_waiting_N9"].items():
        L.append(f"SEC f {k}: n {v['n']} wait4 {f(v['wait_4B'])} {v['wait_4B_ci95']} wait32 {f(v['wait_32B'])} "
                 f"{v['wait_32B_ci95']} upgrade {f(v['upgrade_at_start'])} {v['upgrade_ci95']}")
    g = sec["g_scene_and_recall"]
    for sc in ("Urban", "Highway"):
        L.append(f"SEC g {sc} (pos {g[sc]['n_pos']}, neg {g[sc]['n_neg']}): " + " ".join(
            "{:+.1f}:{:.3f}/{:.3f}".format(o, g[sc]["auroc"][f"4BI/{o}"], g[sc]["auroc"][f"32BI/{o}"]) for o in OFFSETS))
    for m in MODELS:
        L.append(f"SEC g recall {m}: " + " ".join("{:+.1f}:{:.2f}/{:.2f}".format(
            o, g["recall_oof_thresholds"][f"{m}/{o}"]["recall_at_1pct_fpr"],
            g["recall_oof_thresholds"][f"{m}/{o}"]["recall_at_5pct_fpr"]) for o in OFFSETS))
    bl = res["baselines"]
    for name in ("metadata_LR", "flow_LR", "always_yes"):
        L.append(f"BASE {name}: " + " ".join("{}:{:.3f}".format(o, bl[f"{name}/{o}"]["auroc"]) for o in OFFSETS + ["pooled"]))
    ob = res["observability_exploratory"]
    for k in ("F1", "F2", "F3"):
        L.append(f"OBS {k}: sudden-vs-slow AUROC {ob[k]['sudden_vs_slow_auroc']:.3f} {ob[k]['auroc_ci95']} | gap R2 "
                 f"{ob[k]['gap_logodds_r2']:.3f} {ob[k]['r2_ci95']}")
    L.append(f"OBS increments: {json.dumps(ob['increments'])}")
    ck = res["checks"]
    for n in ("N1", "N3", "N9"):
        L.append(f"CHECK {n}: {json.dumps(ck[n])}")
    L.append(f"CHECK errors {ck['errors_and_retries']} causality {ck['causality_all']}")
    (D / "d3_summary.txt").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sanity", action="store_true")
    ap.add_argument("--pilot-ci", action="store_true",
                    help="consistency check 1 follow-up: bootstrap CIs of the D2 pilot's gaps, and the D3 slow-gap "
                         "distribution at the pilot's sample size (36 slow / 75 negative clips drawn from D3)")
    a = ap.parse_args()
    if a.pilot_ci:
        from _provenance import stamp
        r2 = primary(load_d2(), boot=True)
        d3 = load_d3(9)[0]
        rng = np.random.default_rng(SEED)
        sub = []
        for _ in range(NBOOT):
            sl = list(rng.choice(d3.slow, 36, replace=False))
            ng = list(rng.choice(d3.neg, 75, replace=False))
            sub.append(gap(d3, sl, ng, PRIMARY))
        sub = np.array(sub)
        out = dict(pilot=r2, d3_slow_gap_at_pilot_n=dict(n_slow=36, n_neg=75, draws=NBOOT, seed=SEED,
                                                         without_replacement=True,
                                                         median=float(np.median(sub)), ci95=ci(list(sub)),
                                                         frac_le_pilot=float((sub <= r2["gap_slow"]).mean())),
                   _provenance=stamp(script="d3_analyse.py --pilot-ci", model="4BI,32BI", device="cpu", n=NBOOT))
        (D / "d3_pilot_ci.json").write_text(json.dumps(out, indent=1, default=float))
        print(json.dumps({k: v for k, v in out.items() if k != "_provenance"}, default=float))
        sys.exit(0)
    if a.sanity:
        d = load_d2()
        r = primary(d, boot=False)
        print(json.dumps(r))
        ok = abs(r["gap_slow"] - 0.006) <= 0.002 and abs(r["gap_sudden"] - 0.107) <= 0.002 and \
            abs(r["diff"] - 0.100) <= 0.002 and r["n_slow"] == 36 and r["n_sudden"] == 39
        (D / "d3_sanity_check.json").write_text(json.dumps(dict(r, expected=dict(slow=0.006, sudden=0.107, diff=0.100,
                                                                                n_slow=36, n_sudden=39),
                                                               tolerance=0.002, passed=ok), indent=1))
        print("SANITY", "PASSED" if ok else "FAILED")
        sys.exit(0 if ok else 1)
    from _provenance import stamp
    rows_all = [json.loads(l) for l in open_rows()]
    man_all = [json.loads(l) for l in open(D / "d3_requests_manifest.jsonl")]
    res = dict(label="StudyD3-nexar; development clips (not the D2 pilot); strata/subgroups from annotation times",
               checks=checks(rows_all, man_all))
    d9, man9, rows9, samp = load_d3(9)
    res["primary"] = primary(d9)
    res["primary"]["note"] = ("positives used at ALL offsets incl. before time_of_alert (fixed clip set) — deliberate "
                              "departure from D2's unscored rule")
    sec = {}
    for n in (3, 1):
        dn, _, _, _ = load_d3(n)
        sec[f"a_N{n}"] = primary(dn)
    sec["a_offsets_0_1_2_N9"] = primary(d9, offs=LATE)
    sec["b_lead_regression"] = sec_lead_regression(d9)
    sec["c_floor"] = sec_floor(d9)
    sec["d_reliability"] = sec_reliability(d9)
    e = {}
    for n in (1, 3, 9):
        dn, mn, rn, _ = load_d3(n)
        tab, inter = sec_overall(dn, mn, rn, n)
        e[f"N{n}"] = dict(auroc=tab, interaction=inter)
    sec["e_overall"] = e
    sec["f_value_of_waiting_N9"] = sec_waiting(d9, man9)
    g = {}
    for scene in ("Urban", "Highway"):
        ds = Data(d9.S, {c: i for c, i in d9.info.items() if i["scene"] == scene})
        g[scene] = dict(n_pos=len(ds.sudden) + len(ds.slow), n_neg=len(ds.neg),
                        auroc={f"{m}/{o}": subgroup_auc(ds, m, [c for c in ds.sudden + ds.slow
                                                                if next(r for r in man9 if r["file_name"] == c and
                                                                        r["offset"] == o)["gt"] == "positive"],
                                                        ds.neg, o) for m in MODELS for o in OFFSETS})
    g["recall_oof_thresholds"] = {f"{m}/{o}": oof_threshold_recall(d9, m, o, man9) for m in MODELS for o in OFFSETS}
    sec["g_scene_and_recall"] = g
    res["secondary"] = sec
    res["baselines"], feats = baselines(d9, man9, man9)
    res["flow_features"] = feats
    res["observability_exploratory"] = observability(d9, man9, rows9, feats)
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="d3_analyse.py", model="4BI,32BI", device="cpu", n=len(rows_all))
    (D / "d3_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    write_summary(res)
    p = res["primary"]
    print(f"PRIMARY gap sudden {p['gap_sudden']:+.4f} slow {p['gap_slow']:+.4f} diff {p['diff']:+.4f} "
          f"CI {p['diff_ci95']} supported={p['supported']}")


if __name__ == "__main__":
    main()
