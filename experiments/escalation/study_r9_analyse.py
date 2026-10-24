#!/usr/bin/env python3
"""StudyR9 analysis (CPU). Pre-registered decision rule (research/EXPERIMENTS.md, StudyR9).

Ground truth: R1 K3 (RECENT, last 120 s) evidence_covered == false (97 / 845). Per detector: AUROC with a video-
clustered bootstrap 95 % CI (2,000 resamples, seed 0; study_o_q4_analyze.clustered_bootstrap/auroc); GPU-seconds
per question (end-to-end latency of sequential single requests; mean, median); escalation utility at e in {0.05,
0.1, 0.12, 0.2}: device C1 (results/device/accuracy_C1.jsonl) with the top round(e n) questions by score answered by
cloud R1 K1 (ties split at their expected value; unparsed = lowest score), vs random (expectation), the evidence
oracle (the 97 first, expectation within sets) and the perfect oracle (device-wrong & cloud-right first).
DECISION: CLOUD-SIDE HISTORY CHECK WORKS iff C1 AUROC >= 0.75 and C1 accuracy at e = 0.12 >= 34.44 - 1 pp (evidence
oracle, 4B-I at e = 97/845) and C1 mean GPU-s/question <= 0.25 x C2's.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sember"))
sys.path.insert(0, str(ROOT / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_o_q4_analyze import auroc, clustered_bootstrap  # noqa: E402

D_ = Path("results/escalation/study_r9")
DEV = "h100nvl"
ES = (0.05, 0.10, 0.12, 0.20)
EVIDENCE_ORACLE_REF = 34.44          # figures/advisor_2026_10_23/numbers.md (4B-I, e = 97/845)
AUROC_MIN, WITHIN_PP, COST_FRAC = 0.75, 1.0, 0.25


def expected_gain(score, gain, k):
    """Expected summed gain of escalating the top-k by score, ties broken uniformly at random."""
    s = np.asarray(score, float)
    g = np.asarray(gain, float)
    tot, left = 0.0, k
    for v in sorted(set(s.tolist()), reverse=True):
        grp = g[s == v]
        if left <= 0:
            break
        take = min(left, len(grp))
        tot += grp.mean() * take
        left -= take
    return tot


def curve(score, dev_ok, gain, n):
    return {f"{e:g}": 100 * (dev_ok.sum() + expected_gain(score, gain, int(round(e * n)))) / n for e in ES}


def main():
    R = list(read_jsonl(D_ / f"study_r9_requests_{DEV}.jsonl.gz"))
    meta = json.loads((D_ / f"study_r9_run_meta_{DEV}.json").read_text())
    r1 = [r for r in read_jsonl(Path("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"))
          if r["mode"] == "batched"]
    K1 = {r["question_id"]: r for r in r1 if r["cell"] == "K1"}
    K3 = {r["question_id"]: r for r in r1 if r["cell"] == "K3"}
    DV = {r["question_id"]: r for r in read_jsonl(Path("results/device/accuracy_C1.jsonl"))}
    ids = sorted(set(K1) & set(K3) & set(DV))
    n = len(ids)
    y = np.array([not K3[q]["evidence_covered"] for q in ids])
    vids = np.array([K3[q]["video_id"] for q in ids])
    dev_ok = np.array([bool(DV[q]["correct"]) for q in ids], int)
    cloud_ok = np.array([bool(K1[q]["correct"]) for q in ids], int)
    gain = cloud_ok - dev_ok
    out = dict(n=n, positives=int(y.sum()), device_accuracy=100 * dev_ok.mean(), cloud_k1_accuracy=100 * cloud_ok.mean(),
               servers=[{k: s.get(k) for k in ("detector", "key", "revision", "startup_s", "kv_cache_tokens",
                                               "flash_attention_version", "cuda_graphs", "extra_server_args")}
                        for s in meta.get("servers", [])], stack=meta.get("stack"), pilot={
                   d: {k: v for k, v in p.items() if k != "rows"} for d, p in meta.get("pilot", {}).items()},
               baselines=dict(random=curve(np.zeros(n), dev_ok, gain, n), evidence_oracle=curve(y.astype(float), dev_ok,
                                                                                                gain, n),
                              perfect_oracle=curve(gain.astype(float), dev_ok, gain, n),
                              evidence_oracle_at_97=100 * (dev_ok.sum() + gain[y].sum()) / n), detectors={})
    for det in ("C0", "C1", "C2"):
        rows = {r["question_id"]: r for r in R if r["detector"] == det}
        if not rows:
            continue
        miss = [q for q in ids if q not in rows]
        sc = np.array([rows[q]["score"] if q in rows and rows[q]["score"] is not None else -np.inf for q in ids])
        lo = np.nanmin(sc[np.isfinite(sc)]) - 1 if np.isfinite(sc).any() else 0.0
        sc_f = np.where(np.isfinite(sc), sc, lo)
        a = auroc(y, sc_f)
        bs = clustered_bootstrap(vids, lambda idx: auroc(y[idx], sc_f[idx]), nboot=2000, seed=0)
        lat = np.array([rows[q]["latency_s"] for q in ids if q in rows])
        o = dict(n=len(rows), missing=len(miss), errors=sum(bool(r["error"]) for r in rows.values()),
                 parse_rate=float(np.mean([rows[q]["parse_ok"] for q in ids if q in rows])),
                 auroc=a, auroc_ci95=[float(np.nanpercentile(bs, 2.5)), float(np.nanpercentile(bs, 97.5))],
                 gpu_s_per_question=dict(mean=float(lat.mean()), median=float(np.median(lat)),
                                         p90=float(np.percentile(lat, 90)), max=float(lat.max()),
                                         total_h=float(lat.sum() / 3600)),
                 prompt_tokens=dict(mean=float(np.mean([rows[q]["prompt_tokens"] or 0 for q in ids if q in rows])),
                                    max=int(max(rows[q]["prompt_tokens"] or 0 for q in ids if q in rows))),
                 escalation_accuracy=curve(sc_f, dev_ok, gain, n),
                 score_by_truth=dict(positive_median=float(np.median(sc_f[y])), negative_median=float(np.median(sc_f[~y]))))
        if det != "C0":
            tp = [rows[q] for q in ids if q in rows and rows[q]["parse_ok"]]
            older = np.array([rows[q]["older_than_window"] if q in rows and rows[q]["parse_ok"] else False for q in ids])
            dist = np.array([r["dist_to_interval_s"] for r in tp])
            o.update(auroc_binary_older=auroc(y, older.astype(float)),
                     older_flag_rate=float(older.mean()),
                     older_flag_tpr=float(older[y].mean()), older_flag_fpr=float(older[~y].mean()),
                     t_pred_inside_interval=float(np.mean(dist == 0)),
                     dist_to_interval_s=dict(median=float(np.median(dist)), p90=float(np.percentile(dist, 90))),
                     t_pred_after_qt=float(np.mean([r["t_pred"] > r["qt"] for r in tp])))
        else:
            o["text_digit_hist"] = {str(d): sum(1 for r in rows.values() if r.get("text_digit") == d) for d in range(10)}
        out["detectors"][det] = o
    D = out["detectors"]
    if "C1" in D and "C2" in D:
        c1, c2 = D["C1"], D["C2"]
        acc = c1["escalation_accuracy"]["0.12"]
        cost = c1["gpu_s_per_question"]["mean"] / c2["gpu_s_per_question"]["mean"]
        cl = dict(auroc=bool(c1["auroc"] >= AUROC_MIN), accuracy=bool(acc >= EVIDENCE_ORACLE_REF - WITHIN_PP),
                  cost=bool(cost <= COST_FRAC))
        out["decision"] = dict(c1_auroc=c1["auroc"], c1_accuracy_e012=acc, evidence_oracle_ref=EVIDENCE_ORACLE_REF,
                               evidence_oracle_at_e012=out["baselines"]["evidence_oracle"]["0.12"],
                               c1_over_c2_gpu_s=cost, clauses=cl,
                               verdict="CLOUD-SIDE HISTORY CHECK WORKS" if all(cl.values()) else
                               "DOES NOT WORK (failing: " + ", ".join(k for k, v in cl.items() if not v) + ")")
    out["_provenance"] = stamp(script="study_r9_analyse.py", model="qwen3vl-32b-instruct+qwen3vl-4b-instruct",
                               device=DEV, n=len(R))
    (D_ / f"study_r9_results_{DEV}.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: v for k, v in out.items() if k not in ("servers",)}, indent=1, default=float))


if __name__ == "__main__":
    main()
