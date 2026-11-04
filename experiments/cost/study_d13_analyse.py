#!/usr/bin/env python3
"""StudyD13 analysis (CPU; .venv). Pre-registered in research/EXPERIMENTS.md (StudyD13).

Confidence: 4B-I (D13 rerun of H1, logprobs) probability of its own answer letter, renormalised over the A–E letters
present in the top-20 at the first answer-letter token: conf = exp(lp[pred]) / sum_L exp(lp[L]). Rows with no letter
token get conf = NaN and are reported, not imputed.
Outcomes (canonical cells, same vLLM stack): 32B gain = K3 - H1 (per question, correct in {0,1}); history gain = K1 - K3.
Quintiles of conf over the 845 questions (rank-based, ties by question order). Within each quintile: mean gains for
OLDER and INSIDE, and OLDER - INSIDE with the video-clustered paired bootstrap (2,000, seed 0).
AUROC (with clustered-bootstrap CI): conf as a score for (a) OLDER vs not-OLDER over all 845, and over qt > 120 only;
(b) "32B correct given 4B wrong" (K3 correct among H1-wrong questions). AUROC < 0.5 means LOW confidence predicts the
positive class. STRATA ARE ORACLE LABELS (from the MCQ answer interval; not observable at request time).
No E24 / E24b / E24c or Thinking T0.6 result is used.
"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_clean_analyse as CA  # noqa: E402
import study_d13_interaction as I  # noqa: E402
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_o_q4_analyze import clustered_bootstrap  # noqa: E402

D = Path("results/cost/study_d13")
REQ = D / "study_d13_requests_h100nvl.jsonl"
OUT = D / "study_d13_results_h100nvl.json"


def conf_of(r):
    L = (r.get("letter") or {}).get("letter_logprobs") or {}
    if r["pred"] not in L:
        return float("nan")
    z = sum(math.exp(v) for v in L.values())
    return math.exp(L[r["pred"]]) / z


def auroc(y, s, v):
    y, s, v = np.asarray(y), np.asarray(s, float), np.asarray(v)
    ok = ~np.isnan(s)
    y, s, v = y[ok], s[ok], v[ok]
    if len(set(y)) < 2:
        return None

    def f(i):
        return roc_auc_score(y[i], s[i]) if len(set(y[i])) == 2 else np.nan
    bs = clustered_bootstrap(v, f, nboot=CA.NBOOT, seed=CA.SEED)
    return dict(n=int(len(y)), n_pos=int(y.sum()), auroc=float(roc_auc_score(y, s)),
                ci95=[float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))])


def main():
    c, strat, vid = I.load()
    K1, K3, H1 = c["K1"], c["K3"], c["H1"]
    D13 = {r["question_id"]: r for r in map(json.loads, open(REQ)) if not r["error"]}
    meta = json.load(open(D / "study_d13_run_meta_h100nvl.json"))
    q = sorted(set(D13) & set(K1) & set(K3) & set(H1))
    conf = {x: conf_of(D13[x]) for x in q}
    nan = [x for x in q if math.isnan(conf[x])]
    qs = [x for x in q if not math.isnan(conf[x])]
    order = sorted(qs, key=lambda x: (conf[x], q.index(x)))
    quint = {x: min(4, i * 5 // len(order)) for i, x in enumerate(order)}
    g32 = {x: int(K3[x]["correct"]) - int(H1[x]["correct"]) for x in q}
    ghist = {x: int(K1[x]["correct"]) - int(K3[x]["correct"]) for x in q}
    res = dict(n=len(q), n_conf_nan=len(nan), conf_nan_qids=nan, h1_match_gate=meta.get("h1_match_gate"),
               strata_note="ORACLE labels (MCQ answer interval); not observable at request time",
               confidence_definition="p(pred) renormalised over A–E letters in the top-20 at the first letter token",
               conf_summary={s: dict(n=len(z), mean=float(np.mean(z)), median=float(np.median(z)))
                             for s in ("ALL",) + CA.STRATA
                             for z in [[conf[x] for x in qs if s == "ALL" or strat[x] == s]] if z})
    rows = []
    for k in range(5):
        qq = [x for x in qs if quint[x] == k]
        rec = dict(quintile=k + 1, n=len(qq), conf_range=[min(conf[x] for x in qq), max(conf[x] for x in qq)],
                   h1_acc=float(np.mean([H1[x]["correct"] for x in qq])))
        for s in ("OLDER", "INSIDE", "OVERLAP", "QT_LE_120"):
            z = [x for x in qq if strat[x] == s]
            rec[s] = dict(n=len(z), gain_32b_pp=100 * float(np.mean([g32[x] for x in z])) if z else None,
                          gain_history_pp=100 * float(np.mean([ghist[x] for x in z])) if z else None)
        for name, g in (("gain_32b", g32), ("gain_history", ghist)):
            z = [x for x in qq if strat[x] in ("OLDER", "INSIDE")]
            if sum(strat[x] == "OLDER" for x in z) and sum(strat[x] == "INSIDE" for x in z):
                y = np.array([g[x] for x in z], float)
                isold = np.array([strat[x] == "OLDER" for x in z])
                v = np.array([vid[x] for x in z])

                def f(i, y=y, isold=isold):
                    a, b = y[i][isold[i]], y[i][~isold[i]]
                    return a.mean() - b.mean() if len(a) and len(b) else np.nan
                bs = clustered_bootstrap(v, f, nboot=CA.NBOOT, seed=CA.SEED)
                rec[f"older_minus_inside_{name}_pp"] = dict(
                    diff=100 * float(f(np.arange(len(z)))),
                    ci95=[100 * float(np.nanpercentile(bs, 2.5)), 100 * float(np.nanpercentile(bs, 97.5))])
        rows.append(rec)
    res["quintiles"] = rows
    v = [vid[x] for x in q]
    res["auroc"] = dict(
        older_vs_rest_all=auroc([strat[x] == "OLDER" for x in q], [conf[x] for x in q], v),
        older_vs_rest_qt_gt_120=auroc(*zip(*[(strat[x] == "OLDER", conf[x], vid[x]) for x in q
                                             if strat[x] != "QT_LE_120"])),
        k3_correct_given_h1_wrong=auroc(*zip(*[(bool(K3[x]["correct"]), conf[x], vid[x]) for x in q
                                               if not H1[x]["correct"]])),
        note="score = 4B confidence; AUROC < 0.5 => low confidence predicts the positive class")
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d13_analyse.py", model="4BI", device="cpu", n=len(q))
    OUT.write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(dict(n=res["n"], nan=len(nan), auroc=res["auroc"]), default=float, indent=1))
    for r in rows:
        print(r["quintile"], r["n"], [round(x, 3) for x in r["conf_range"]], "OLDER", r["OLDER"], "INSIDE", r["INSIDE"],
              r.get("older_minus_inside_gain_32b_pp"), r.get("older_minus_inside_gain_history_pp"))


if __name__ == "__main__":
    main()
