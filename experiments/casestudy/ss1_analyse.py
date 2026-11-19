#!/usr/bin/env python3
"""StudySS1 analysis: accuracy with bootstrap CIs, TTFT p50/p90 and token counts, overall and by
stratum, for a run JSON from ss1_run.py. For EgoThink, merges the judge pass (scorer a) and reports
it beside containment (scorer b) and their agreement. No model is run. No em dashes.

Usage:
  python3 ss1_analyse.py --run <run.json> [--judge <judge.json>] --out <summary.json>
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

NB, SEED = 2000, 0


def boot_ci(vals):
    v = np.asarray([x for x in vals if x is not None], dtype=float)
    if v.size < 2:
        return [None, None]
    rng = np.random.default_rng(SEED)
    b = v[rng.integers(0, v.size, (NB, v.size))].mean(axis=1)
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def pct(vals, p):
    v = np.asarray([x for x in vals if x is not None], dtype=float)
    return float(np.percentile(v, p)) if v.size else None


def summ(vals):
    v = [x for x in vals if x is not None]
    return dict(n=len(v), mean=(float(np.mean(v)) if v else None), ci=boot_ci(v))


def timing_block(rows):
    ttft = [r["ttft_s"] for r in rows if r.get("ttft_s") is not None]
    tot = [r["total_s"] for r in rows if r.get("total_s") is not None]
    return dict(
        ttft_s=dict(p50=pct(ttft, 50), p90=pct(ttft, 90), mean=(float(np.mean(ttft)) if ttft else None)),
        total_s=dict(p50=pct(tot, 50), p90=pct(tot, 90)),
        prompt_tokens_mean=(float(np.mean([r["prompt_tokens"] for r in rows
                                           if r.get("prompt_tokens") is not None])) if rows else None),
        completion_tokens_mean=(float(np.mean([r["completion_tokens"] for r in rows
                                               if r.get("completion_tokens") is not None]))
                                if rows else None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--judge", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    run = json.loads(Path(a.run).read_text())
    rows = [r for r in run["rows"] if "error" not in r]
    ds = run["dataset"]
    out = dict(study="StudySS1", dataset=ds, tier=run["tier"], model=run["model"],
               n=run["n"], n_scored=len(rows), n_errors=run.get("n_errors"),
               caching=run.get("caching"), decoding=run.get("decoding"),
               timing=timing_block(rows), overall={}, by_stratum={})

    if ds == "vizwiz":
        acc = [r["score"]["vqa_accuracy"] for r in rows]
        out["overall"]["vqa_accuracy"] = summ(acc)
        ans = [r["score"]["vqa_accuracy"] for r in rows if r.get("answerable") == 1]
        out["overall"]["vqa_accuracy_answerable_only"] = summ(ans)
        by = defaultdict(list)
        for r in rows:
            by[r.get("answer_type")].append(r["score"]["vqa_accuracy"])
        out["by_stratum"]["answer_type"] = {k: summ(v) for k, v in sorted(by.items())}
    else:
        cont = [r["score"]["containment"] for r in rows]
        out["overall"]["containment"] = summ(cont)
        jmap = {}
        if a.judge:
            jj = json.loads(Path(a.judge).read_text())
            jmap = {o["qid"]: o["judge_rating"] for o in jj["rows"]}
            out["judge_model"] = jj.get("judge_model")
            out["judge_unparsed"] = jj.get("n_unparsed")
            jvals = [jmap.get(r["qid"]) for r in rows]
            out["overall"]["judge_rating"] = summ(jvals)
            out["overall"]["judge_vs_containment_agreement"] = jj.get("judge_vs_containment_agreement")
        for key in ("dimension", "area"):
            by_c = defaultdict(list)
            by_j = defaultdict(list)
            for r in rows:
                by_c[r.get(key)].append(r["score"]["containment"])
                if jmap:
                    by_j[r.get(key)].append(jmap.get(r["qid"]))
            out["by_stratum"][key] = {k: dict(containment=summ(by_c[k]),
                                              judge_rating=(summ(by_j[k]) if jmap else None))
                                      for k in sorted(by_c)}

    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out["overall"], indent=1, default=float))
    print("timing:", json.dumps(out["timing"], default=float))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
