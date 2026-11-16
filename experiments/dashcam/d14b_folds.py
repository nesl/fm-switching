#!/usr/bin/env python3
"""The PRE-REGISTERED 5-fold cross-fitting assignment over all 300 StudyD14b clips. CPU only.

WHY THIS FILE EXISTS. StudyCTRL1-episodes fitted on 90 DEV clips and reported on 210 EVAL clips,
and the 210-clip subset could not resolve even the always-cloud minus device-only gap it was
measuring against (+0.0598, CI -0.0076 to +0.1395). Cross-fitting keeps the no-peeking property
of a split while scoring EVERY clip held out, so the pooled metric is computed on all 300 clips
and carries the power of the full set.

THE RULE, as pre-registered in research/EXPERIMENTS.md (StudyCTRL1b-crossfit) BEFORE any
computation:

    within each LABEL stratum, order the clips by sha256(file_name) hex
    fold(clip) = rank within its stratum, modulo 5

Stratification is by label for the same reason as the 90/210 split: the challenge metric crops one
point per clip and its base rate is n_positive / n_clips, so folds of differing balance would not
be comparable. The sha256 order is the same digest the 90/210 split used, so the assignment is
reproducible from the committed clip list alone and no seed is involved.

HOW IT IS USED. For each fold f, every tunable is chosen on the OTHER FOUR folds and applied
unchanged to f. The pooled held-out result concatenates the five held-out folds, so every clip is
scored under settings fitted without it. Per-fold results are reported beside the pooled ones.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import d14b_split as SP

ROOT = Path(__file__).resolve().parents[2]
N_FOLDS = 5
STRATIFY_BY = "label"


def folds() -> Dict[str, object]:
    rows = SP.clip_rows()
    by = defaultdict(list)
    for r in rows:
        by[r[STRATIFY_BY]].append(r)
    assign: Dict[str, int] = {}
    per_stratum = {}
    for k in sorted(by):
        rs = sorted(by[k], key=lambda r: SP._digest(r["file_name"]))
        counts = defaultdict(int)
        for rank, r in enumerate(rs):
            f = rank % N_FOLDS
            assign[r["file_name"]] = f
            counts[f] += 1
        per_stratum[k] = dict(total=len(rs), by_fold=dict(sorted(counts.items())))
    meta = {r["file_name"]: r for r in rows}
    members = {f: sorted(c for c, g in assign.items() if g == f) for f in range(N_FOLDS)}
    assert sum(len(v) for v in members.values()) == 300
    for f in range(N_FOLDS):
        for g in range(f + 1, N_FOLDS):
            assert not (set(members[f]) & set(members[g]))
    fold_info = {}
    for f in range(N_FOLDS):
        lab = defaultdict(int)
        for c in members[f]:
            lab[meta[c]["label"]] += 1
        fold_info[str(f)] = dict(
            n=len(members[f]), by_label=dict(sorted(lab.items())),
            duration_s=round(sum(float(meta[c]["duration_s"]) for c in members[f]), 3),
            clips=members[f])
    return dict(
        rule=("within each %s stratum, order by sha256(file_name) hex; fold = rank mod %d; "
              "pre-registered in research/EXPERIMENTS.md (StudyCTRL1b-crossfit) before any "
              "computation" % (STRATIFY_BY, N_FOLDS)),
        n_folds=N_FOLDS, stratify_by=STRATIFY_BY, n_clips=300,
        assignment=dict(sorted(assign.items())), fold=fold_info,
        overlap_clips=0,
        superseded_split=dict(
            note=("StudyCTRL1-episodes' 90/210 DEV/EVAL split is kept in "
                  "results/dashcam/ctrl1/d14b_split.json and its results are kept in the report "
                  "as SUPERSEDED, not deleted"),
            n_dev=90, n_eval=210))


def train_eval(f: int) -> Dict[str, List[str]]:
    a = folds()["assignment"]
    return dict(train=sorted(c for c, g in a.items() if g != f),
                held=sorted(c for c, g in a.items() if g == f))


def main() -> int:
    import sys
    s = folds()
    out = ROOT / "results/dashcam/ctrl1b"
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "experiments/lib"))
    from _provenance import stamp
    s["_provenance"] = stamp(script="d14b_folds.py", model=None, device="cpu", n=300, args=None)
    (out / "d14b_folds.json").write_text(json.dumps(s, indent=1))
    for f in range(N_FOLDS):
        i = s["fold"][str(f)]
        print("fold %d: %3d clips %s %.1f s" % (f, i["n"], i["by_label"], i["duration_s"]))
    print("wrote", out / "d14b_folds.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
