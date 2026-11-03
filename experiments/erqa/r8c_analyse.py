#!/usr/bin/env python3
"""StudyR8c analysis: seed accuracy against R4, agreement, entropy by position, T control."""
import glob, gzip, json, math, sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SIG = ROOT / "results/erqa/r8c_signals"
R4_ACC = 45.0
R4_CI = (40.2, 49.9)


def wilson(k, n, z=1.959963985):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def load(tag):
    rows = []
    for f in sorted(glob.glob(str(SIG / f"r8c_erqa_thinking_{tag}_part*.jsonl.gz"))):
        with gzip.open(f, "rt") as fh:
            rows += [json.loads(l) for l in fh]
    return {r["qid"]: r for r in rows if not r.get("oom")}


def ent_stats(rows):
    e = [np.array(r["steps"]["ent_bits"], float) for r in rows if r["steps"]["ent_bits"]]
    if not e:
        return {}
    allv = np.concatenate(e)
    byq = np.array([x.mean() for x in e])
    first = np.concatenate([x[:50] for x in e])
    last = np.concatenate([x[-50:] for x in e])
    return dict(mean_bits=round(float(allv.mean()), 4),
                median_bits=round(float(np.median(allv)), 4),
                sd_within_trace_median=round(float(np.median([x.std() for x in e])), 4),
                sd_across_questions=round(float(byq.std()), 4),
                mean_first50=round(float(first.mean()), 4),
                mean_last50=round(float(last.mean()), 4),
                n_steps=int(len(allv)))


def main():
    r4 = {r["qid"]: r for r in
          (json.loads(l) for l in open(ROOT / "results/erqa/r4_signals/r4_erqa_thinking.jsonl"))
          if not r.get("oom")}
    seeds = {s: load(f"s{s}") for s in (1, 2)}
    seeds = {s: v for s, v in seeds.items() if v}
    if not seeds:
        sys.exit("no R8c shards found")
    rep = {"r4_reference": dict(n=len(r4), accuracy=R4_ACC, ci=list(R4_CI)), "seeds": {}}
    for s, d in seeds.items():
        ok = np.array([bool(r["correct"]) for r in d.values()])
        a = 100 * ok.mean()
        lo, hi = wilson(int(ok.sum()), len(ok))
        rows = list(d.values())
        rep["seeds"][str(s)] = dict(
            n=len(d), accuracy=round(a, 3), wilson=[round(lo, 2), round(hi, 2)],
            delta_vs_r4=round(a - R4_ACC, 3),
            overlaps_r4_ci=bool(lo <= R4_CI[1] and hi >= R4_CI[0]),
            median_generated=int(np.median([r["n_generated"] for r in rows])),
            median_think_tokens=int(np.median([r["n_think_tokens"] for r in rows])),
            budget_hits=int(sum(bool(r["budget_hit"]) for r in rows)),
            gate_steps_equal_generated=bool(all(r["steps_equal_generated"] for r in rows)),
            gate_text_reassembles=bool(all(r["reassembled_equals_generated"] for r in rows)),
            truncated_input_steps=int(sum(r["truncated_input_steps"] for r in rows)),
            entropy=ent_stats(rows))

    ctl = load("s1_t01control")
    if ctl:
        rep["temperature_control"] = dict(
            n=len(ctl), temperature=0.1, entropy=ent_stats(list(ctl.values())),
            note="Step 4 control: entropy must fall against temperature 1.0")

    ids = sorted(set(r4) & set.intersection(*[set(d) for d in seeds.values()]))
    counts = [int(r4[i]["correct"]) + sum(int(seeds[s][i]["correct"]) for s in seeds)
              for i in ids]
    rep["repeated_sample_counts"] = dict(
        n=len(ids), n_samples=1 + len(seeds),
        distribution={str(k): int(v) for k, v in sorted(Counter(counts).items())},
        note="R4 (seed 42, temperature 0.6) plus the R8c seeds (temperature 1.0); the "
             "arms differ in temperature, which is a deliberate, recorded change")
    p = SIG / "r8c_analysis.json"
    json.dump(rep, open(p, "w"), indent=2)
    print(json.dumps(rep, indent=1))
    print(f"-> {p}")


if __name__ == "__main__":
    main()
