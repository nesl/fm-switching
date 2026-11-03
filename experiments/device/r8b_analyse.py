#!/usr/bin/env python3
"""StudyR8b analysis: seed accuracy against C3, reasoning length, repeated-sample counts."""
import glob, gzip, json, math, sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/device"
C3_CI = (30.3, 36.6)          # device_tier_accuracy_llamacpp.md §A
C3_ACC = 33.4
C3_MEDIAN_THINK_WORDS = 237   # the n_think_tokens whitespace-word count C3 stores


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def load_shards(seed):
    rows = []
    for f in sorted(glob.glob(str(OUT / f"accuracy_C3_logprobs_s{seed}_part*.jsonl.gz"))):
        with gzip.open(f, "rt") as fh:
            rows += [json.loads(l) for l in fh]
    return {r["question_id"]: r for r in rows}


def main():
    c3 = {json.loads(l)["question_id"]: json.loads(l)
          for l in open(OUT / "accuracy_C3.jsonl")}
    seeds = {s: load_shards(s) for s in (1, 2)}
    seeds = {s: v for s, v in seeds.items() if v}
    if not seeds:
        sys.exit("no R8b shards found")

    rep = {"c3_reference": dict(n=len(c3), accuracy=round(100 * np.mean(
        [r["correct"] for r in c3.values()]), 3), ci_quoted=list(C3_CI)), "seeds": {}}
    for s, d in seeds.items():
        ok = np.array([bool(r["correct"]) for r in d.values()])
        a = 100 * ok.mean()
        lo, hi = wilson(int(ok.sum()), len(ok))
        words = np.array([r["n_think_tokens"] for r in d.values()], float)
        toks = np.array([r["n_think_tokens_real"] for r in d.values()], float)
        lps = [np.array(r["tokens"]["chosen_lp"], float) for r in d.values()]
        allp = np.concatenate(lps) if lps else np.array([0.0])
        entries_ok = all(r["logprob_entries_equal_completion_tokens"] for r in d.values())
        rep["seeds"][str(s)] = dict(
            n=len(d), accuracy=round(a, 3), wilson=[round(lo, 2), round(hi, 2)],
            inside_c3_ci=bool(C3_CI[0] <= a <= C3_CI[1]),
            median_think_words=float(np.median(words)),
            c3_median_think_words=C3_MEDIAN_THINK_WORDS,
            median_think_tokens_real=float(np.median(toks)),
            mean_chosen_logprob=round(float(allp.mean()), 4),
            median_chosen_logprob=round(float(np.median(allp)), 4),
            frac_chosen_logprob_above_minus_0_01=round(float((allp > -0.01).mean()), 4),
            logprob_entries_match_completion_tokens=bool(entries_ok),
            budget_hits=int(sum(bool(r["budget_hit"]) for r in d.values())),
        )

    ids = sorted(set(c3) & set.intersection(*[set(d) for d in seeds.values()]))
    counts = []
    for i in ids:
        counts.append(int(c3[i]["correct"]) + sum(int(seeds[s][i]["correct"]) for s in seeds))
    rep["repeated_sample_counts"] = dict(
        n=len(ids), n_samples=1 + len(seeds),
        distribution={str(k): int(v) for k, v in sorted(Counter(counts).items())},
        note="count of correct samples across C3 (seed 0) and the R8b seeds; this is the "
             "better-powered device-failure target R8a-v2 uses")
    p = OUT / "r8b_analysis.json"
    json.dump(rep, open(p, "w"), indent=2)
    print(json.dumps(rep, indent=1))
    print(f"-> {p}")


if __name__ == "__main__":
    main()
