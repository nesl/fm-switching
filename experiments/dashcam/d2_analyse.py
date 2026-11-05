#!/usr/bin/env python3
"""StudyD2-nexar pilot analysis (CPU; .venv). Pre-registered (research/EXPERIMENTS.md, StudyD2-nexar). PILOT,
INDICATIVE; no reliability thresholds fitted; no time-shift claim. Development clips only.

Scored requests: gt positive (positive clip, prefix end >= time_of_alert) and gt negative (negative clip, any
offset). Unscored (positive clip, prefix end < time_of_alert) -> early-response Yes rate only.
Score = P(Yes) normalised over Yes / No variants at the first generated token; Yes at threshold 0.5.
Per model x resolution x offset (and pooled over offsets; and within Urban / Highway): AUROC and accuracy, cluster
bootstrap by clip (2,000 resamples, seed 0); Yes rate on positives / negatives (FPR = Yes rate on negatives), early-
response rate, 4B-vs-32B disagreement, prompt tokens; 32B − 4B AUROC per offset (paired by request, clip bootstrap;
INDICATIVE). Controls: grey frames (Yes rate, number of distinct scores), causality (from the manifest), identical
input across models (frame sha256 + prompt tokens per request), neither-Yes-nor-No rate.
Baselines (same scored requests): always-Yes; metadata (scene, weather, light one-hot) logistic regression and
optical-flow logistic regression (17 features, standardised), both out-of-fold by clip (GroupKFold 5), AUROC with the
same bootstrap. Examples: first 5 request_ids (sorted) per 4B/32B agreement cell at SMALL resolution — listed only.
Writes results/dashcam/study_d2_nexar/d2_results_h100nvl.json.
"""
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

D = Path("results/dashcam/study_d2_nexar")
OFFSETS = [-3.0, -1.5, -1.0, -0.5, 0.0, 1.0, 2.0]
NBOOT, SEED = 2000, 0
MODELS, RES = ("4BI", "32BI"), ("small", "native")


def boot(clips, fn):
    """Cluster bootstrap by clip: fn(index array) on resampled rows."""
    rng = np.random.default_rng(SEED)
    uc = np.unique(clips)
    by = {c: np.where(clips == c)[0] for c in uc}
    out = []
    for _ in range(NBOOT):
        idx = np.concatenate([by[c] for c in rng.choice(uc, len(uc), replace=True)])
        out.append(fn(idx))
    out = np.array([x for x in out if x is not None and not np.isnan(x)], float)
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))] if len(out) else None


def auc(y, s):
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else None


def metrics(y, s, clips):
    y, s, clips = np.asarray(y), np.asarray(s, float), np.asarray(clips)
    a = auc(y, s)
    yes = s >= 0.5
    return dict(n=int(len(y)), n_pos=int(y.sum()), auroc=a,
                auroc_ci95=boot(clips, lambda i: auc(y[i], s[i])) if a is not None else None,
                acc=float(np.mean(yes == y)), acc_ci95=boot(clips, lambda i: float(np.mean(yes[i] == y[i]))),
                yes_rate_pos=float(np.mean(yes[y == 1])) if (y == 1).any() else None,
                yes_rate_neg=float(np.mean(yes[y == 0])) if (y == 0).any() else None)


def oof(X, y, groups, model):
    p = np.zeros(len(y))
    for tr, te in GroupKFold(5).split(X, y, groups):
        m = model()
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return p


def main():
    reqs = {r["request_id"]: r for r in map(json.loads, open(D / "pilot_requests.jsonl"))}
    samp = json.load(open(D / "pilot_sample.json"))
    meta = {c["file_name"]: c for c in samp["clips"]}
    rows = [json.loads(l) for l in open(D / "d2_requests_h100nvl.jsonl")]
    errs = sum(bool(r["error"]) for r in rows)
    R = {}
    for r in rows:
        if not r["error"]:
            R[(r["model"], r["res"], r["request_id"])] = r
    real = [r for r in R.values() if not r["grey"]]
    res = dict(label="PILOT — INDICATIVE; development clips only; no test-set result", errors=errs,
               n_rows=len(rows), neither={f"{m}/{s}": dict(n=sum(1 for r in real if r["model"] == m and r["res"] == s),
                                                           neither=sum(r["neither"] for r in real
                                                                       if r["model"] == m and r["res"] == s))
                                          for m in MODELS for s in RES},
               causality=dict(all_requests_last_frame_le_offset=all(q["last_pts_le_end"] for q in reqs.values()),
                              n=len(reqs)))
    # identical input across models
    ii = {}
    for s in RES:
        both = [q for q in reqs if all((m, s, q) in R for m in MODELS)]
        ii[s] = dict(n=len(both), frames_equal=sum(R[("4BI", s, q)]["frame_sha256"] == R[("32BI", s, q)]["frame_sha256"]
                                                   for q in both),
                     prompt_tokens_equal=sum(R[("4BI", s, q)]["prompt_tokens"] == R[("32BI", s, q)]["prompt_tokens"]
                                             for q in both),
                     frames_equal_manifest=sum(R[("4BI", s, q)]["frame_sha256"] == reqs[q][f"{s}_sha256"] for q in both))
    res["identical_input"] = ii
    # tokens
    res["prompt_tokens"] = {f"{m}/{s}": dict(median=float(np.median(t)), min=int(min(t)), max=int(max(t)))
                            for m in MODELS for s in RES
                            for t in [[r["prompt_tokens"] for r in real if r["model"] == m and r["res"] == s]] if t}
    # grey control
    g = {}
    for m in MODELS:
        for s in RES:
            gr = [r for r in R.values() if r["grey"] and r["model"] == m and r["res"] == s]
            rr = [r for r in real if r["model"] == m and r["res"] == s and r["p_yes"] is not None]
            if gr:
                ps = [r["p_yes"] for r in gr]
                g[f"{m}/{s}"] = dict(n=len(gr), yes_rate=float(np.mean([p >= 0.5 for p in ps if p is not None])),
                                     distinct_scores=len({round(p, 9) for p in ps if p is not None}),
                                     p_yes=ps[0], neither=sum(r["neither"] for r in gr),
                                     real_yes_rate_all_requests=float(np.mean([r["p_yes"] >= 0.5 for r in rr])),
                                     prompt_tokens=gr[0]["prompt_tokens"])
    res["grey_control"] = g
    # main metrics
    def sc(m, s, filt=lambda q: True):
        out = []
        for q, r in reqs.items():
            k = (m, s, q)
            if k in R and r["gt"] != "unscored" and filt(r) and R[k]["p_yes"] is not None:
                out.append((q, r, R[k]["p_yes"]))
        return out
    main_tab, strata = {}, {}
    for m in MODELS:
        for s in RES:
            for o in OFFSETS + ["pooled"]:
                f = (lambda r: True) if o == "pooled" else (lambda r, o=o: r["offset"] == o)
                x = sc(m, s, f)
                if not x:
                    continue
                main_tab[f"{m}/{s}/{o}"] = metrics([r["gt"] == "positive" for _, r, _ in x], [p for _, _, p in x],
                                                   [r["file_name"] for _, r, _ in x])
                un = [R[(m, s, q)]["p_yes"] >= 0.5 for q, r in reqs.items() if r["gt"] == "unscored"
                      and (o == "pooled" or r["offset"] == o) and (m, s, q) in R and R[(m, s, q)]["p_yes"] is not None]
                main_tab[f"{m}/{s}/{o}"]["early_response_rate"] = float(np.mean(un)) if un else None
                main_tab[f"{m}/{s}/{o}"]["n_unscored"] = len(un)
                for sc_name in ("Urban", "Highway"):
                    x2 = sc(m, s, lambda r, f=f, sc_name=sc_name: f(r) and r["scene"] == sc_name)
                    if x2:
                        strata[f"{m}/{s}/{o}/{sc_name}"] = metrics([r["gt"] == "positive" for _, r, _ in x2],
                                                                   [p for _, _, p in x2],
                                                                   [r["file_name"] for _, r, _ in x2])
    res["by_model_res_offset"] = main_tab
    res["by_scene"] = strata
    # 32B - 4B AUROC and disagreement
    d = {}
    for s in RES:
        for o in OFFSETS + ["pooled"]:
            q = [qq for qq, r in reqs.items() if r["gt"] != "unscored" and (o == "pooled" or r["offset"] == o)
                 and all((m, s, qq) in R and R[(m, s, qq)]["p_yes"] is not None for m in MODELS)]
            if not q:
                continue
            y = np.array([reqs[x]["gt"] == "positive" for x in q])
            a4 = np.array([R[("4BI", s, x)]["p_yes"] for x in q])
            a32 = np.array([R[("32BI", s, x)]["p_yes"] for x in q])
            cl = np.array([reqs[x]["file_name"] for x in q])

            def diff(i, y=y, a4=a4, a32=a32):
                if len(set(y[i])) < 2:
                    return None
                return roc_auc_score(y[i], a32[i]) - roc_auc_score(y[i], a4[i])
            dv = diff(np.arange(len(q)))
            d[f"{s}/{o}"] = dict(n=len(q), auroc_32b_minus_4b=dv, ci95=boot(cl, diff) if dv is not None else None,
                                 disagreement=float(np.mean((a4 >= 0.5) != (a32 >= 0.5))),
                                 label="INDICATIVE")
    res["b32_minus_b4"] = d
    # baselines
    q = [qq for qq, r in reqs.items() if r["gt"] != "unscored"]
    y = np.array([reqs[x]["gt"] == "positive" for x in q]).astype(int)
    cl = np.array([reqs[x]["file_name"] for x in q])
    off = np.array([reqs[x]["offset"] for x in q])
    Xm = np.array([[meta[reqs[x]["file_name"]][k] for k in ("scene", "weather", "light")] for x in q], dtype=object)
    pm = oof(Xm, y, cl, lambda: make_pipeline(OneHotEncoder(handle_unknown="ignore"), LogisticRegression(max_iter=1000)))
    with open(D / "flow_features.csv") as f:
        fr = {r["request_id"]: r for r in csv.DictReader(f)}
    feats = [k for k in next(iter(fr.values())) if k != "request_id"]
    Xf = np.array([[float(fr[x][k]) for k in feats] for x in q])
    pf = oof(Xf, y, cl, lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)))
    base = {}
    for name, p in (("metadata_LR", pm), ("flow_LR", pf)):
        for o in OFFSETS + ["pooled"]:
            i = np.arange(len(q)) if o == "pooled" else np.where(off == o)[0]
            base[f"{name}/{o}"] = metrics(y[i], p[i], cl[i])
    for o in OFFSETS + ["pooled"]:
        i = np.arange(len(q)) if o == "pooled" else np.where(off == o)[0]
        base[f"always_yes/{o}"] = dict(n=int(len(i)), acc=float(y[i].mean()), auroc=0.5, yes_rate_pos=1.0,
                                       yes_rate_neg=1.0)
    res["baselines"] = base
    res["flow_features"] = feats
    res["metadata_features"] = ["scene", "weather", "light (one-hot)"]
    res["ref_time_check"] = samp["ref_time_check"]
    # examples (SMALL; listed only)
    ex = {"both_right": [], "both_wrong": [], "32B_right_4B_wrong": [], "4B_right_32B_wrong": []}
    for qq in sorted(q):
        if not all(("4BI" if m == 4 else "32BI", "small", qq) in R for m in (4, 32)):
            continue
        t = reqs[qq]["gt"] == "positive"
        r4 = (R[("4BI", "small", qq)]["p_yes"] or 0) >= 0.5
        r32 = (R[("32BI", "small", qq)]["p_yes"] or 0) >= 0.5
        k = ("both_right" if (r4 == t and r32 == t) else "both_wrong" if (r4 != t and r32 != t)
             else "32B_right_4B_wrong" if r32 == t else "4B_right_32B_wrong")
        if len(ex[k]) < 5:
            ex[k].append(dict(file=reqs[qq]["file_name"], offset=reqs[qq]["offset"], gt=reqs[qq]["gt"]))
    res["examples_small"] = ex
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="d2_analyse.py", model="4BI,32BI", device="cpu", n=len(rows))
    (D / "d2_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    print("errors", errs, "neither", res["neither"])
    print("grey", {k: (v["yes_rate"], v["distinct_scores"], round(v["p_yes"], 4), round(v["real_yes_rate_all_requests"], 3))
                   for k, v in g.items()})
    for k, v in main_tab.items():
        print(k, "AUROC", v["auroc"] and round(v["auroc"], 3), v["auroc_ci95"] and [round(x, 3) for x in v["auroc_ci95"]],
              "acc", round(v["acc"], 3), "yes+", v["yes_rate_pos"] and round(v["yes_rate_pos"], 2),
              "yes-", round(v["yes_rate_neg"], 2), "early", v["early_response_rate"])
    for k, v in base.items():
        if k.endswith("pooled") or "flow" in k:
            print(k, v.get("auroc") and round(v["auroc"], 3), v.get("auroc_ci95"))


if __name__ == "__main__":
    main()
