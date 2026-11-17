"""StudyPOL5-engine: StudyENG1d Part C trials as the replay sees them, with the holdout fenced.

StudyENG1d repeated StudyENG1 Part C's paired design on fresh traces and recorded, for every
background arrival, which phase of the action it arrived in (its `bin`), how many requests were
in flight when it arrived, and the delta it suffered. That per-arrival record is what makes a
per-arrival diagnosis possible at all, so this module joins it to the raw request rows.

FENCE. The 60 StudyENG1d HOLDOUT pairs named in `eng1d_holdout_split.json` are NEVER built, and
`load_trials` raises unless an explicit authorization string is passed. The same applies to the
StudyENG1c Part D HOLDOUT through `score_t0b.load_part_d_trials`. Tests prove both refusals.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import trace_replay as tr

PART_C_PATH = "results/cost/study_eng1d/eng1d_partC_requests_h100nvl.jsonl"
DERIVED_PATH = "results/cost/study_eng1d/eng1d_requests_derived.jsonl"
TRIALS_PATH = "results/cost/study_eng1d/eng1d_trials_derived.jsonl"
SPLIT_PATH = "results/cost/study_eng1d/eng1d_holdout_split.json"
FRONTEND_PATH = "results/cost/study_eng1d/eng1d_frontend_requests_h100nvl.jsonl"
RESULTS_PATH = "results/cost/study_eng1d/eng1d_results.json"

ACTIONS = ("mono11k", "piece2048", "piece1024")
BINS = ("pre_inj", "pre_fe", "0-25", "25-50", "50-75", "75-100", "post")
IN_WINDOW_BINS = ("0-25", "25-50", "50-75", "75-100")


class HoldoutFenced(PermissionError):
    """Raised when the StudyENG1d holdout is requested without authorization."""


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _rows(path: str) -> List[Dict[str, Any]]:
    with open(_root() / path) as fh:
        return [json.loads(l) for l in fh]


def holdout_keys() -> set:
    raw = json.loads((_root() / SPLIT_PATH).read_text())
    keys = set()
    for cell, idx in raw["holdout"].items():
        load, action = cell.split("|")
        for i in idx:
            keys.add((load, action, int(i)))
    return keys


def load_trials(split: str = "fit", authorization: str = "") -> Tuple[List[tr.Trial],
                                                                     Dict[str, Any]]:
    """Every StudyENG1d Part C pair of the requested split, as trials the frozen replay scores.

    `load` carries the ENG1d load name and `action` StudyT0's own action name, so the criteria
    code compares the same actions it compared on StudyENG1 and StudyENG1c."""
    split = str(split).lower()
    if split not in ("fit", "holdout"):
        raise ValueError("split must be 'fit' or 'holdout', got %r" % split)
    if split == "holdout" and not authorization:
        raise HoldoutFenced(
            "the 60 StudyENG1d HOLDOUT pairs are reserved for the StudyT0b one-shot. Building "
            "them needs the user's authorization recorded in `authorization`, and the run must "
            "go through t0_harness.T0Harness.run_holdout_once so the freeze is re-verified.")
    want_holdout = (split == "holdout")
    keys = holdout_keys()
    buckets: Dict[Tuple[str, str, int], tr.Trial] = {}
    seen = dict(rows=0, pairs=set(), holdout_pairs=set())
    for row in _rows(PART_C_PATH):
        seen["rows"] += 1
        kind = row.get("kind")
        if kind in ("pair_check",):
            continue
        mode = row.get("mode")
        if mode not in ("with", "without"):
            continue
        hold = bool(row.get("holdout"))
        (seen["holdout_pairs"] if hold else seen["pairs"]).add(row.get("pair"))
        if hold != want_holdout:
            continue
        k = (str(row["load"]), str(row["action"]), int(row["trial"]))
        t = buckets.get(k)
        if t is None:
            t = tr.Trial(load=k[0], action=k[1], trial=k[2], holdout=hold,
                         t_inj_rel=float(row.get("t_inj_rel") or 0.0))
            buckets[k] = t
        arm = t.arms.get(mode)
        if arm is None:
            arm = tr.Arm(mode=mode, t0_trace=float(row.get("t0_trace") or 0.0))
            t.arms[mode] = arm
        if row.get("t0_trace") and not arm.t0_trace:
            arm.t0_trace = float(row["t0_trace"])
        if kind == "build":
            arm.setup.append(row)
        elif kind == "inject":
            arm.action.append(row)
        elif kind == "episodic":
            arm.background.append(row)
    trials = [buckets[k] for k in sorted(buckets)]
    built = {(t.load, t.action, t.trial) for t in trials}
    leaked = sorted(built & keys) if not want_holdout else []
    assert not leaked, "HOLDOUT LEAK: %s" % leaked[:5]
    audit = dict(split=split, n_trials=len(trials), n_fit_pairs=len(seen["pairs"]),
                 n_holdout_pairs=len(seen["holdout_pairs"]),
                 n_holdout_in_split_file=len(keys),
                 holdout_trials_used=(len(trials) if want_holdout else 0),
                 rows_read=seen["rows"], split_file=SPLIT_PATH,
                 assertions=["no scored trial's (load, action, trial) is in the split file",
                             "the record's holdout flag selects exactly the split file's cells"])
    assert len(seen["holdout_pairs"]) == len(keys), (
        "the record flags %d holdout pairs, the split file lists %d"
        % (len(seen["holdout_pairs"]), len(keys)))
    return trials, audit


def measured_arrivals(fence: bool = True) -> Dict[Tuple[str, str, int, int], Dict[str, Any]]:
    """StudyENG1d's own per-arrival record, keyed (load, action, trial, idx): the measured delta,
    the phase of the action the arrival fell in, and the in-flight count at arrival."""
    keys = holdout_keys()
    out = {}
    for r in _rows(DERIVED_PATH):
        k = (str(r["load"]), str(r["action"]), int(r["trial"]), int(r["idx"]))
        if fence and (k[0], k[1], k[2]) in keys:
            continue
        out[k] = dict(delta_s=float(r["delta_s"]), bin=str(r["bin"]),
                      offset=float(r["offset"]), inflight=int(r.get("inflight") or 0),
                      ttft_with=float(r["ttft_with"]), ttft_without=float(r["ttft_without"]),
                      steps_waited=r.get("steps_waited"))
    return out


def measured_trials(fence: bool = True) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    keys = holdout_keys()
    out = {}
    for r in _rows(TRIALS_PATH):
        k = (str(r["load"]), str(r["action"]), int(r["trial"]))
        if fence and k in keys:
            continue
        out[k] = r
    return out


def frontend_windows(fence: bool = True) -> List[Dict[str, Any]]:
    """Every StudyENG1d request's measured front-end window: the API server received it at
    `received_t` and handed it to the engine at `added_t`. Joined to the request row, this is the
    fitting data for the front-end channel: a duration against a body size and an image count."""
    keys = holdout_keys()
    fe = {}
    for r in _rows(FRONTEND_PATH):
        fe[str(r["rid"])] = r
    out = []
    for row in _rows(PART_C_PATH):
        if row.get("kind") not in ("episodic", "inject", "build"):
            continue
        if fence and bool(row.get("holdout")):
            continue
        f = fe.get(str(row.get("rid")))
        if f is None:
            continue
        dur = float(f["added_t"]) - float(f["received_t"])
        if dur < 0:
            continue
        out.append(dict(rid=str(row["rid"]), kind=row["kind"], load=row.get("load"),
                        action=row.get("action"), mode=row.get("mode"),
                        body_mb=float(row.get("body_mb") or 0.0),
                        prompt_tokens=int(row.get("prompt_tokens") or 0),
                        cached_tokens=int(row.get("cached_tokens") or 0),
                        n_frames=row.get("n_frames"),
                        received_t=float(f["received_t"]), added_t=float(f["added_t"]),
                        front_end_s=dur))
    return out
