#!/usr/bin/env python3
"""StudySS2 analysis: accuracy with bootstrap CIs, TTFT p50/p90 and token counts, overall and by
stratum, for a run JSON from ss2_run.py. RefSpatial: per-split point-in-mask accuracy (the
benchmark's own metric; reported per split, plus an n-weighted pooled overall which the benchmark
itself does NOT define). RealWorldQA: exact match overall and by MCQ / free-form subset. No model is
run. No em dashes.

Usage:
  python3 ss2_analyse.py --run <run.json> --out <summary.json>
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
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    run = json.loads(Path(a.run).read_text())
    rows = [r for r in run["rows"] if "error" not in r]
    ds = run["dataset"]
    out = dict(study="StudySS2", dataset=ds, tier=run["tier"], model=run["model"],
               n=run["n"], n_scored=len(rows), n_errors=run.get("n_errors"),
               coord_mode=run.get("coord_mode"), caching=run.get("caching"),
               decoding=run.get("decoding"), timing=timing_block(rows),
               overall={}, by_stratum={})

    if ds == "refspatial":
        acc = [r["score"]["point_accuracy"] for r in rows]
        out["overall"]["point_accuracy_pooled"] = summ(acc)
        out["overall"]["_note"] = ("benchmark reports per-split means; pooled is n-weighted over "
                                   "all items for convenience only")
        npts = [r["score"]["n_points"] for r in rows]
        out["overall"]["frac_items_zero_points"] = float(np.mean([1.0 if n == 0 else 0.0
                                                                  for n in npts]))
        out["overall"]["n_points_mean"] = float(np.mean(npts)) if npts else None
        by = defaultdict(list)
        for r in rows:
            by[r["score"].get("split")].append(r["score"]["point_accuracy"])
        out["by_stratum"]["split"] = {k: summ(v) for k, v in sorted(by.items())}
        byst = defaultdict(list)
        for r in rows:
            byst[r["score"].get("step")].append(r["score"]["point_accuracy"])
        out["by_stratum"]["step"] = {str(k): summ(v) for k, v in sorted(byst.items())}
    else:
        em = [r["score"]["exact_match"] for r in rows]
        out["overall"]["exact_match"] = summ(em)
        by = defaultdict(list)
        for r in rows:
            by[r["score"].get("subset")].append(r["score"]["exact_match"])
        out["by_stratum"]["subset"] = {k: summ(v) for k, v in sorted(by.items())}

    Path(a.out).write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out["overall"], indent=1, default=float))
    print("by_stratum:", json.dumps(out["by_stratum"], default=float))
    print("timing:", json.dumps(out["timing"], default=float))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
