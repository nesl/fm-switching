#!/usr/bin/env python3
"""StudyD9 analysis (CPU; .venv). Pre-registered in research/EXPERIMENTS.md (StudyD9).

Per benchmark (ERQA 400, MV-RoboBench 401) and pooled (801): accuracy of vLLM arms I (32B-I greedy), T0 / T1 (32B-T,
model-card sampling T 1.0, seeds 0 / 1) and Tmean (per-question mean of T0, T1); paired bootstrap over questions
(2,000, seed 0) for T0 - I, T1 - I, Tmean - I and T0 - T1. Empty answers, runaways (finish_reason length or </think>
never closed), think-closed rate, completion tokens.
Stack check (Instruct only): vLLM arm I vs the earlier HF arm C on the same questions and prompts — StudyR arm C and
StudyS2 arm C (SDPA, `*_h100nvl.jsonl`) and their -fa2 reruns; letter agreement + accuracy difference. Backends differ
(vLLM FA3 vs HF SDPA / FA2): BACKEND-MISMATCHED by construction; prompt tokens are checked equal.
Earlier Thinking arms (T 0.6) are CONFOUNDED and are not compared.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

D = Path("results/erqa/study_d9")
REQ = D / "study_d9_requests_h100nvl.jsonl"
OUT = D / "study_d9_results_h100nvl.json"
PRIOR = {("erqa", "sdpa"): ("results/erqa/study_r/study_r_trials_h100nvl.jsonl", "question_id"),
         ("erqa", "fa2"): ("results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl", "question_id"),
         ("mvrb", "sdpa"): ("results/erqa/study_s2/study_s2_trials_h100nvl.jsonl", "index"),
         ("mvrb", "fa2"): ("results/erqa/study_s2/study_s2_trials_h100nvl_fa2.jsonl", "index")}
NBOOT, SEED = 2000, 0


def tb(x):
    return x in (True, "True", "true", 1, "1")


def boot(d):
    d = np.asarray(d, float)
    rng = np.random.default_rng(SEED)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(NBOOT)]
    return dict(n=len(d), diff_pp=100 * float(d.mean()),
                ci95_pp=[100 * float(np.percentile(bs, 2.5)), 100 * float(np.percentile(bs, 97.5))])


def arm_stats(rs):
    ct = [r["completion_tokens"] for r in rs if r["completion_tokens"] is not None]
    return dict(n=len(rs), acc_pct=100 * float(np.mean([r["correct"] for r in rs])),
                empty_answers=sum(r["empty_answer"] for r in rs), no_letter=sum(r["pred"] is None for r in rs),
                runaways=sum(r["runaway"] for r in rs), finish_length=sum(r["finish_reason"] == "length" for r in rs),
                think_closed=sum(bool(r["think_closed"]) for r in rs) if rs[0]["arm"] == "T" else None,
                prompt_tokens_equal_hf=sum(r["prompt_tokens"] == r["expected_prompt_tokens"] for r in rs),
                completion_tokens=dict(p50=float(np.median(ct)), p90=float(np.percentile(ct, 90)), max=int(max(ct)),
                                       mean=float(np.mean(ct))) if ct else None)


def main():
    import gzip
    rows = [json.loads(l) for l in (gzip.open(f"{REQ}.gz", "rt") if not REQ.exists() else open(REQ))]
    errs = sum(bool(r["error"]) for r in rows)
    ok = [r for r in rows if not r["error"]]
    A = {}
    for r in ok:
        k = "I" if r["arm"] == "I" else f"T{r['seed']}"
        A.setdefault(k, {})[(r["bench"], r["qid"])] = r
    res = dict(errors_logged=errs, arms_present={k: len(v) for k, v in A.items()})
    for bench in ("erqa", "mvrb", "pooled"):
        keys = sorted(set.intersection(*(set(v) for v in A.values())))
        keys = [k for k in keys if bench == "pooled" or k[0] == bench]
        b = dict(n=len(keys), arms={a: arm_stats([A[a][k] for k in keys]) for a in A})
        c = {a: np.array([int(A[a][k]["correct"]) for k in keys]) for a in A}
        if {"T0", "T1"} <= set(c):
            c["Tmean"] = (c["T0"] + c["T1"]) / 2
            b["arms"]["Tmean"] = dict(acc_pct=100 * float(c["Tmean"].mean()))
            b["T0_minus_T1"] = boot(c["T0"] - c["T1"])
            b["T0_T1_letter_agreement"] = float(np.mean([A["T0"][k]["pred"] == A["T1"][k]["pred"] for k in keys]))
        if "I" in c:
            for t in ("T0", "T1", "Tmean"):
                if t in c:
                    b[f"{t}_minus_I"] = boot(c[t] - c["I"])
        res[bench] = b
    # stack check: vLLM arm I vs earlier HF arm C
    sc = {}
    if "I" in A:
        for (bench, backend), (path, key) in PRIOR.items():
            C = {str(r[key]): r for r in map(json.loads, open(path)) if r["arm"] == "C"}
            ks = [k for k in A["I"] if k[0] == bench and k[1] in C]
            ci = np.array([int(tb(C[k[1]]["correct"])) for k in ks])
            vi = np.array([int(A["I"][k]["correct"]) for k in ks])
            predC = [C[k[1]].get("predicted_letter") or C[k[1]].get("pred") for k in ks]
            sc[f"{bench}_vs_{backend}"] = dict(
                prior_file=path, n=len(ks), vllm_acc_pct=100 * float(vi.mean()), hf_acc_pct=100 * float(ci.mean()),
                vllm_minus_hf=boot(vi - ci),
                letter_agreement=float(np.mean([A["I"][k]["pred"] == p for k, p in zip(ks, predC)])),
                prompt_tokens_equal=int(sum(A["I"][k]["prompt_tokens"] == int(C[k[1]]["n_input_tokens"]) for k in ks)),
                label="BACKEND-MISMATCHED (vLLM FA3 vs HF " + backend.upper() + "); same prompts, greedy, max 512")
    res["stack_check"] = sc
    res["note"] = "Earlier Thinking T0.6 arms are CONFOUNDED (audit 2026-11-03) and are not compared."
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d9_analyse.py", model="32BI,32BT", device="cpu", n=801)
    OUT.write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: res[k] for k in ("errors_logged", "arms_present")}))
    for bench in ("erqa", "mvrb", "pooled"):
        b = res[bench]
        print(bench, {a: round(s["acc_pct"], 2) for a, s in b["arms"].items()},
              {k: (round(v["diff_pp"], 2), [round(x, 2) for x in v["ci95_pp"]]) for k, v in b.items()
               if k.endswith("minus_I") or k == "T0_minus_T1"})
    for k, v in sc.items():
        print(k, round(v["vllm_acc_pct"], 2), round(v["hf_acc_pct"], 2), round(v["letter_agreement"], 3),
              v["prompt_tokens_equal"])


if __name__ == "__main__":
    main()
