#!/usr/bin/env python3
"""StudyR8a target-mismatch fix — train on the evidence_outside_window label.

StudyR8a's Part 1 scores every router's DEVICE-FAILURE score (`r["fail"]`,
study_r8a_prefix_signals.py:587) against every target, including
`evidence_outside_window`. No model was ever fitted on the evidence label, so the
"query text is at chance" and "clearest positive" readings compared mismatched
targets. This script fits each router ON that label, in the same folds, and reports
held-out AUROC.

CPU only, no inference. Does not edit study_r8a_prefix_signals.py; it imports it so
the loaders, folds, feature builders and bootstrap are byte-identical.
"""
import json, sys, time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "escalation"))
sys.path.insert(0, str(ROOT / "experiments" / "lib"))

import study_r8a_prefix_signals as R8A
from _provenance import stamp

OUT = ROOT / "results/escalation/study_r8a/target_fix.json"
KS = [25, 50, 100]
NBOOT, BSEED = R8A.NBOOT, R8A.SEED


def auroc(score, y):
    return float(R8A.R4S_auroc(np.asarray(score, float), np.asarray(y, bool)))


def ci_of(fn, n, groups):
    lo, hi = R8A.boot_ci_stat(fn, n, groups, clustered=True, nboot=NBOOT, seed=BSEED)
    return [round(lo, 4), round(hi, 4)]


def build_routers(ds, tokenizer, folds, y):
    """Every router fitted on y = evidence_outside_window, inside training folds only."""
    q_text = ds["query"]
    q_num = np.hstack([ds["extra_num"], R8A.onehot(ds["extra_cat"])])
    cat_oh = R8A.onehot(ds["extra_cat"])
    qt = ds["extra_num"]                      # question_time, shape (n, 1)

    R = {}
    R["query_only"] = R8A.oof_scores("text", q_text, q_num, y, folds, "fail")
    R["category+question_time"] = R8A.oof_scores("num", None, np.hstack([cat_oh, qt]),
                                                 y, folds, "fail")
    R["question_time_only"] = R8A.oof_scores("num", None, qt, y, folds, "fail")
    for k in KS:
        pre, ntok, closed = R8A.cut_prefixes(tokenizer, ds["trace"], k)
        H = R8A.hand_features(pre, ntok, closed, ds["letters"])
        R[f"prefix_hand_k{k}"] = R8A.oof_scores("num", None, H, y, folds, "fail")
        R[f"query+prefix_hand_k{k}"] = R8A.oof_scores(
            "text", q_text, np.hstack([q_num, H]), y, folds, "fail")
    return R


def evaluate(R, y, groups, qt_flat):
    """Held-out AUROC + clustered CI + paired delta vs query-only, all 845 and qt>120."""
    subsets = {"all_845": np.ones(len(y), bool), "qt_gt_120": qt_flat > 120}
    base = R["query_only"]
    out = {}
    for sname, m in subsets.items():
        idxs = np.where(m)[0]
        g = np.asarray(groups)[idxs]
        yy = np.asarray(y, bool)[idxs]
        rows = {}
        for key, sc in R.items():
            s = np.asarray(sc, float)[idxs]
            b = np.asarray(base, float)[idxs]
            a = auroc(s, yy)
            rows[key] = dict(
                auroc=round(a, 4),
                ci=ci_of(lambda ix, s=s, yy=yy: R8A.R4S_auroc(s[ix], yy[ix]), len(idxs), g),
                delta_vs_query_only=round(a - auroc(b, yy), 4),
                delta_ci=ci_of(
                    lambda ix, s=s, b=b, yy=yy: (R8A.R4S_auroc(s[ix], yy[ix])
                                                 - R8A.R4S_auroc(b[ix], yy[ix])),
                    len(idxs), g))
        out[sname] = dict(n=int(m.sum()), n_positive=int(yy.sum()), routers=rows)
    return out


EXPECTED = {"query_only": 0.80, "category+question_time": 0.79, "question_time_only": 0.685}


def main():
    t0 = time.time()
    R8A.build_question_text()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(R8A.TOK_4BT)

    payload = dict(
        study="StudyR8a-target-fix",
        what="Routers fitted ON the evidence_outside_window label, in StudyR8a's folds. "
             "StudyR8a Part 1 instead scored its device-failure score against this label "
             "(study_r8a_prefix_signals.py:587), so its figures for this target are "
             "target-mismatched.",
        label="evidence_outside_window = NOT K3 evidence_covered (R1 K3, batched)",
        nboot=NBOOT, bootstrap_seed=BSEED, n_folds=R8A.NFOLD,
        folds="GroupKFold by video_id, identical to study_r8a_prefix_signals.folds_for()",
        ks=KS, arms={})

    for label, seed in (("v1_C3_seed0", None), ("v2_seed1", 1), ("v2_seed2", 2)):
        ds = R8A.load_sember(seed)
        y = ds["evidence_miss"]
        folds = R8A.folds_for(ds)
        qt_flat = ds["extra_num"][:, 0]
        print(f"\n=== {label}: n={len(ds['ids'])} positives={int(y.sum())}", flush=True)
        R = build_routers(ds, tokenizer, folds, y)
        payload["arms"][label] = dict(
            n=len(ds["ids"]), device_arm=label,
            results=evaluate(R, y, ds["groups"], qt_flat))
        for k, v in payload["arms"][label]["results"]["all_845"]["routers"].items():
            print(f"   {k:28s} AUROC {v['auroc']:.4f} {v['ci']}  "
                  f"delta {v['delta_vs_query_only']:+.4f} {v['delta_ci']}", flush=True)

    # expected-value check on the v1 arm, all 845
    chk = {}
    got = payload["arms"]["v1_C3_seed0"]["results"]["all_845"]["routers"]
    for key, exp in EXPECTED.items():
        a = got[key]["auroc"]
        chk[key] = dict(expected=exp, recomputed=a, abs_diff=round(abs(a - exp), 4),
                        over_0_02=bool(abs(a - exp) > 0.02))
    payload["expected_check"] = dict(
        basis="v1_C3_seed0, all 845", tolerance=0.02, checks=chk,
        any_over_tolerance=any(v["over_0_02"] for v in chk.values()))

    payload["elapsed_h"] = round((time.time() - t0) / 3600, 3)
    payload["_provenance"] = stamp(script="study_r8a_target_fix.py", model="none",
                                   device="cpu", n=sum(a["n"] for a in payload["arms"].values()),
                                   args={})
    json.dump(payload, open(OUT, "w"), indent=1)
    print("\nEXPECTED CHECK:")
    for k, v in chk.items():
        flag = "  <== OVER 0.02" if v["over_0_02"] else ""
        print(f"  {k:28s} expected {v['expected']:.3f}  got {v['recomputed']:.4f}  "
              f"diff {v['abs_diff']:.4f}{flag}")
    print(f"-> {OUT}  ({(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    main()
