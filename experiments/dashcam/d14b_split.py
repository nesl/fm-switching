#!/usr/bin/env python3
"""The PRE-REGISTERED DEV / EVAL split of StudyD14b's 300 clips. CPU only.

WHY THIS FILE EXISTS. The Nexar canonical split
(`results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv`) is dev 751 / val 300 / test 449
clips, and StudyD14b IS the 300 val clips. So the D14b clips carry no DEV / EVAL partition of
their own, and StudyD3 - which ran the dev clips - holds a 10-OFFSET design, not a 0.25-s
trajectory, so a controller whose parameters are a window length, a lag and a frame count cannot
be fitted there at all. StudyCTRL1's step 1 stop condition fired, and the user authorized the
rule below BEFORE anything was computed (research/EXPERIMENTS.md, StudyCTRL1-episodes).

THE RULE, as pre-registered:

    DEV  = the lowest 30 % of the 300 clips in sha256(file_name) hex order, STRATIFIED BY LABEL
    EVAL = the rest

Stratifying by label is part of the rule, not a repair applied afterwards: the challenge metric
crops one point per clip and its base rate is n_positive / (n_positive + n_negative), so an
unbalanced split would move the metric's base rate between DEV and EVAL and make the two sides
incomparable. Inside a label the sha256 order is untouched.

WHAT IT COSTS, stated with every number that uses it: every StudyCTRL1 and StudyPROF1 figure is
computed on the EVAL subset; the committed challenge mAP references (always-cloud 0.5675,
device-only 0.4776) were computed over all 300 clips and are RECOMPUTED here on EVAL, with the
all-300 values kept as reference-only; and the DEV clips are burned for any future fitting.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
SPLIT_CSV = ROOT / "results/dashcam/study_d2_nexar/nexar_train_split_seed0.csv"
DEV_FRACTION = 0.30
STRATIFY_BY = "label"


def _digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def clip_rows() -> List[Dict[str, str]]:
    """The 300 val clips, which are exactly StudyD14b's clips."""
    rows = [r for r in csv.DictReader(SPLIT_CSV.open()) if r["split"] == "val"]
    assert len(rows) == 300, len(rows)
    return rows


def split() -> Dict[str, object]:
    rows = clip_rows()
    by = defaultdict(list)
    for r in rows:
        by[r[STRATIFY_BY]].append(r)
    dev: List[str] = []
    ev: List[str] = []
    per_stratum = {}
    for k in sorted(by):
        rs = sorted(by[k], key=lambda r: _digest(r["file_name"]))
        n_dev = int(round(DEV_FRACTION * len(rs)))
        dev += [r["file_name"] for r in rs[:n_dev]]
        ev += [r["file_name"] for r in rs[n_dev:]]
        per_stratum[k] = dict(total=len(rs), dev=n_dev, eval=len(rs) - n_dev)
    dev, ev = sorted(dev), sorted(ev)
    assert not (set(dev) & set(ev))
    assert len(dev) + len(ev) == 300
    meta = {r["file_name"]: r for r in rows}
    def counts(names: List[str], field: str) -> Dict[str, int]:
        c: Dict[str, int] = defaultdict(int)
        for n in names:
            c[meta[n][field] or "(blank)"] += 1
        return dict(sorted(c.items()))
    return dict(
        rule=("sha256(file_name) hex order, lowest %.0f %% to DEV, stratified by %s; "
              "pre-registered in research/EXPERIMENTS.md (StudyCTRL1-episodes) before any "
              "computation" % (100 * DEV_FRACTION, STRATIFY_BY)),
        dev_fraction=DEV_FRACTION, stratify_by=STRATIFY_BY,
        dev=dev, eval=ev, n_dev=len(dev), n_eval=len(ev),
        per_stratum=per_stratum,
        overlap_clips=0,
        dev_by_label=counts(dev, "label"), eval_by_label=counts(ev, "label"),
        dev_by_scene=counts(dev, "scene"), eval_by_scene=counts(ev, "scene"),
        dev_by_light=counts(dev, "light"), eval_by_light=counts(ev, "light"),
        dev_by_weather=counts(dev, "weather"), eval_by_weather=counts(ev, "weather"),
        dev_duration_s=round(sum(float(meta[n]["duration_s"]) for n in dev), 3),
        eval_duration_s=round(sum(float(meta[n]["duration_s"]) for n in ev), 3))


def side(clip: str) -> str:
    s = split()
    return "DEV" if clip in set(s["dev"]) else "EVAL"


def subset_ctx(ctx, which: str):
    """A context restricted to one side of the split.

    StudyE9d's `Challenge` asserts that `read_clip_meta()` covers ctx["clips"] exactly, so the
    clip list and the score arrays are left whole and only the POSITIVE and NEGATIVE clip lists
    are restricted. Every crop the metric takes comes from those two lists, so this restricts the
    metric without touching the committed geometry (each negative clip keeps its own fake event
    time, which is drawn per clip at seed 0 and therefore does not move when the set changes).
    """
    s = split()
    keep = set(s["dev"] if which.upper() == "DEV" else s["eval"])
    sub = dict(ctx)
    sub["pos"] = [c for c in ctx["pos"] if c in keep]
    sub["neg"] = [c for c in ctx["neg"] if c in keep]
    sub["side"] = which.upper()
    sub["scored_clips"] = [c for c in ctx["clips"] if c in keep]
    sub["neg_pts"] = sum(ctx["meta"][c]["G"] for c in sub["neg"])
    sub["pos_pts"] = sum(ctx["meta"][c]["G"] for c in sub["pos"])
    sub["hours_pos"] = sub["pos_pts"] * ctx["step"] / 3600.0
    sub["hours_neg"] = sub["neg_pts"] * ctx["step"] / 3600.0
    sub["hours_all"] = sub["hours_pos"] + sub["hours_neg"]
    return sub


def main() -> int:
    s = split()
    out = ROOT / "results/dashcam/ctrl1"
    out.mkdir(parents=True, exist_ok=True)
    import sys
    sys.path.insert(0, str(ROOT / "experiments/lib"))
    from _provenance import stamp
    s["_provenance"] = stamp(script="d14b_split.py", model=None, device="cpu", n=300, args=None)
    (out / "d14b_split.json").write_text(json.dumps(s, indent=1))
    print("DEV %d clips, EVAL %d clips, overlap 0" % (s["n_dev"], s["n_eval"]))
    print("DEV by label ", s["dev_by_label"])
    print("EVAL by label", s["eval_by_label"])
    print("DEV by scene ", s["dev_by_scene"])
    print("EVAL by scene", s["eval_by_scene"])
    print("DEV %.1f s of video, EVAL %.1f s" % (s["dev_duration_s"], s["eval_duration_s"]))
    print("wrote", out / "d14b_split.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
