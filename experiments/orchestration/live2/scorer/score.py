#!/usr/bin/env python3
"""The offline scorer for live round 1: attainment, capacity, task value, intervals.

StudyLIVE2-fleet, part 5. CPU only. It reads a trace, one run per arm, and the input calibration
maps; it writes a score file per run and a comparison across arms. It never runs a model and
never touches a GPU, so it can be re-run on any box against committed run outputs.

THE STANDING ANSWER (the object every metric is computed on)

  standing answer = the CLOUD's answer if it was DELIVERED within L, else the DEVICE's answer.

Every row is keyed on the `opportunity_id` the TRACE GENERATOR assigned (D96 (1)): the scorer
reads that id from `outcomes.jsonl` and from `device_answers.jsonl` and never constructs or
parses one. The descriptive fields it needs for the play-indexed AP and the per-device breakdown
travel alongside the id in the trace, not inside it.

The device always has an answer (D1: every device can always fall back to its own model), so an
opportunity never has none. `device_answers.jsonl` is produced by the trace generator and is
NEVER sent to the coordinator, so no arm can see it.

TARGETS ARE INPUTS, AND EVERY SETTING IS REPORTED (D71 as amended by D82)

  dashcam   PER DEVICE: fraction of its decision instants served on time >= p, with a minimum of
            200 instants in the run; devices under the minimum are EXCLUDED from the capacity
            count and reported. Starting values L = 1.0 s, p = 0.25.
  robot     POOLED over all robot devices in the run: fraction of questions served on time >= p,
            with a minimum of 20 questions in the RUN (not per device). A run whose robot pool
            holds fewer than 20 questions is marked INELIGIBLE for the robot part and reported.
            Starting values L = 5.0 s, p = 0.90.

D82 fixes the pooled form because no S-EMBER EVAL session holds 20 questions (max 6, median 4),
so a per-device minimum of 20 is unreachable. The worst-served robot device and the per-device
distribution are always reported. D71's guard applies: the scorer SWEEPS whatever L and p it is
given and reports EVERY setting. It never selects a setting.

CAPACITY (D64, D82)

  per arm, the largest fleet size at which EVERY ELIGIBLE DASHCAM DEVICE meets its own target AND
  the ROBOT POOL meets its target.

TASK VALUE

  dashcam   streaming AP over the clip-PLAYS completed in the run (D85): plays cut by the run end
            are excluded FOR EVERY ARM, plays are indexed by play id and paired across arms, and
            the summary pools across seeds. Computed with StudyE9b's own `ApEngine` /`ap_point`
            through `experiments/orchestration/sim/metrics.streaming_ap`, never re-implemented.
            Scores are put on one scale first by the per-tier calibration maps (D57): the device
            map for a device answer, the cloud map for a cloud answer.
  robot     accuracy of the STANDING answer; cloud correctness from the CLOUD's ACTUAL answers
            (not a lookup table); reported split WARM / COLD per arm from the request log's
            `cache_path` (D81).
  device-only   computed from the recordings alone, with no run at all.

CALIBRATION MAPS ARE INPUT FILES, AND AN INTERIM MAP CANNOT SCORE A MEASUREMENT (D86)

The dense refit of both tiers is an H100 task. Until it exists, `orin2_calibration.json`'s maps
are INTERIM: fitted on an event-anchored 10-offset sample while round 1 scores every instant on a
dense trajectory, with the D3-fitted device slope 3.007x steeper than a dense D14b-DEV fit. The
scorer therefore REFUSES to score a run whose server is not a stub when the map is INTERIM. A
stub run is scored, and every output says `is_measurement: false`.

ROBOT MEASURABILITY (D97, user ruling 2026-11-17, row pending)

Robot-pool eligibility (at least 20 pooled questions per run, D82) is a property of the TRACE, so
it is fixed from traces before any GPU run. A fleet size enters a main-sweep comparison only if
its robot pool is eligible at EVERY seed that will be reported for that comparison: seeds 1, 2
and 3. The pilot (seed 0) only reports which of its sizes were measurable at seed 0; seed 0 never
sets an entry point. A size is never made measurable by averaging or borrowing across seeds.
`d97_sweep_sizes` and `d97_pilot_labels` implement the two modes, and the pilot function has no
entry point to return.

INTERVALS

Paired bootstrap, policy minus each baseline, no pass / fail margin (D64):
  within a run   resample DEVICES for dashcam quantities and QUESTIONS for the robot pool
  across runs    resample SEEDS
  dashcam AP     resample PLAYS, label-stratified, and recompute AP with StudyE9b's `ap_point`
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = HERE.parents[3]
for _p in (str(LIVE2 / "fleet"), str(ROOT / "experiments/orchestration/sim"),
           str(ROOT / "experiments/dashcam"), str(ROOT / "experiments/orchestration/baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import data_sources as DS       # noqa: E402

DASH_L_S = DS.NEXAR_DEADLINE_S          # 1.0 (D71)
DASH_P = 0.25                           # D71
DASH_MIN_INSTANTS = 200                 # D71
ROB_L_S = DS.ROBOT_DEADLINE_S           # 5.0 (D71)
ROB_P = 0.90                            # D71
ROB_MIN_QUESTIONS = 20                  # D82, POOLED over the run
N_BOOT = 2000
N_BOOT_AP = 200                         # AP is recomputed per resample; see the docstring
AP_HORIZONS = (0.0, 0.5, 1.0, 1.5)


class ScoringRefused(RuntimeError):
    """A stop condition: the scorer will not produce numbers from this input."""


# ---------------------------------------------------------------- loading
@dataclass
class Loaded:
    trace_dir: Path
    run_dir: Path
    meta: Dict[str, Any]
    run_meta: Dict[str, Any]
    records: List[Dict[str, Any]]
    outcomes: Dict[str, Dict[str, Any]]
    device_answers: Dict[str, Dict[str, Any]]
    requests: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]


def load(trace_dir: Path, run_dir: Path) -> Loaded:
    trace_dir, run_dir = Path(trace_dir), Path(run_dir)
    meta = json.loads((trace_dir / "trace_meta.json").read_text())
    run_meta = json.loads((run_dir / "run_meta.json").read_text())
    records = [json.loads(l) for l in open(trace_dir / "trace.jsonl")]
    dev = {r["opportunity_id"]: r
           for r in (json.loads(l) for l in open(trace_dir / "device_answers.jsonl"))}
    out = {r["opportunity_id"]: r
           for r in (json.loads(l) for l in open(run_dir / "outcomes.jsonl"))}
    reqs: List[Dict[str, Any]] = []
    if (run_dir / "requests.jsonl").exists():
        reqs = [json.loads(l) for l in open(run_dir / "requests.jsonl")]
    dec: List[Dict[str, Any]] = []
    for name in ("decisions.jsonl", "decision.jsonl"):
        if (run_dir / name).exists():
            dec = [json.loads(l) for l in open(run_dir / name)]
            break
    # D96 (2): the canonical fairness digest is per mode. The trace carries one for each; the
    # run is checked against the one for ITS mode.
    if "fairness_digest" not in run_meta and "sent_stream_digest" in run_meta:
        raise ScoringRefused(
            "this run carries only a pre-D96 `sent_stream_digest`, which covered a DIFFERENT "
            "event set (opportunities only, and frames in pull mode). It is not comparable with "
            "the canonical `fairness_digest` of D96 (2) and must not be compared against it. "
            "Re-run the cell with the current emulator.")
    digest_run = run_meta.get("fairness_digest")
    mode = run_meta.get("mode") or meta.get("mode")
    want = meta.get(f"fairness_digest_{mode}") or meta.get("fairness_digest")
    if digest_run and want and digest_run != want:
        raise ScoringRefused(
            "the run's fairness digest does not equal the trace's digest for this mode, so this "
            "run did not see the same event stream as the others; D69 fairness is broken and "
            f"this is a STOP condition (D96 (2)):\n  run   {digest_run}\n  trace {want}\n"
            f"  mode  {mode}")
    return Loaded(trace_dir, run_dir, meta, run_meta, records, out, dev, reqs, dec)


NON_MEASUREMENT_SERVERS = ("stub", "fake")     # live2/CONTRACT.md calls it "fake"


def check_calibration(cal: Dict[str, Any], run_meta: Dict[str, Any]) -> None:
    """D86 / ruling 10-11: an INTERIM map may score a fake / stub run and nothing else."""
    is_stub = run_meta.get("server_kind") in NON_MEASUREMENT_SERVERS
    if cal["label"] != "FINAL" and not is_stub:
        raise ScoringRefused(
            "SCORING REFUSED: the calibration map is INTERIM and this run's server is "
            f"{run_meta.get('server_kind')!r}, not a fake / stub server. D86 allows the "
            "committed "
            "orin2_calibration.json maps for flash builds and tests ONLY; a measured run needs "
            "the dense refit of both tiers (an H100 task). Map: "
            f"{cal['path']} sha256 {cal['sha256'][:16]}")


# ---------------------------------------------------------------- attainment
@dataclass
class Attainment:
    dashcam_per_device: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    dashcam_eligible: List[str] = field(default_factory=list)
    dashcam_excluded: List[str] = field(default_factory=list)
    dashcam_all_meet: bool = False
    robot_pool_n: int = 0
    robot_pool_on_time: int = 0
    robot_pool_fraction: Optional[float] = None
    robot_pool_eligible: bool = False
    robot_pool_meets: bool = False
    robot_per_device: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    robot_worst_device: Optional[str] = None
    capacity_met: bool = False


def _within(o: Dict[str, Any], L: float) -> bool:
    td = o.get("t_delivered")
    return td is not None and (float(td) - float(o["t_opportunity"])) <= L + 1e-9


def attainment(lo: Loaded, L_dash: float = DASH_L_S, p_dash: float = DASH_P,
               L_rob: float = ROB_L_S, p_rob: float = ROB_P,
               min_dash: int = DASH_MIN_INSTANTS,
               min_rob: int = ROB_MIN_QUESTIONS) -> Attainment:
    a = Attainment()
    by_dev: Dict[str, List[Dict[str, Any]]] = {}
    rob: List[Dict[str, Any]] = []
    for o in lo.outcomes.values():
        if o["kind"] == "monitor":
            by_dev.setdefault(o["device_id"], []).append(o)
        else:
            rob.append(o)
    for d, os_ in sorted(by_dev.items()):
        n = len(os_)
        k = sum(1 for o in os_ if _within(o, L_dash))
        frac = k / n if n else None
        eligible = n >= min_dash
        a.dashcam_per_device[d] = dict(n_instants=n, on_time=k,
                                       fraction=(round(frac, 6) if frac is not None else None),
                                       eligible=eligible,
                                       meets=(eligible and frac is not None
                                              and frac >= p_dash - 1e-12))
        (a.dashcam_eligible if eligible else a.dashcam_excluded).append(d)
    a.dashcam_all_meet = bool(a.dashcam_eligible) and all(
        a.dashcam_per_device[d]["meets"] for d in a.dashcam_eligible)

    a.robot_pool_n = len(rob)
    a.robot_pool_on_time = sum(1 for o in rob if _within(o, L_rob))
    if a.robot_pool_n:
        a.robot_pool_fraction = round(a.robot_pool_on_time / a.robot_pool_n, 6)
    a.robot_pool_eligible = a.robot_pool_n >= min_rob
    a.robot_pool_meets = bool(a.robot_pool_eligible and a.robot_pool_fraction is not None
                              and a.robot_pool_fraction >= p_rob - 1e-12)
    perdev: Dict[str, List[Dict[str, Any]]] = {}
    for o in rob:
        perdev.setdefault(o["device_id"], []).append(o)
    for d, os_ in sorted(perdev.items()):
        n = len(os_)
        k = sum(1 for o in os_ if _within(o, L_rob))
        a.robot_per_device[d] = dict(n_questions=n, on_time=k,
                                     fraction=(round(k / n, 6) if n else None))
    if a.robot_per_device:
        a.robot_worst_device = min(a.robot_per_device,
                                   key=lambda d: (a.robot_per_device[d]["fraction"]
                                                  if a.robot_per_device[d]["fraction"] is not None
                                                  else 2.0, d))
    # No robot devices at all in this cell: the robot conjunct is vacuous, and that is reported
    # rather than being silently read as "met".
    robot_ok = a.robot_pool_meets if a.robot_pool_n else None
    a.capacity_met = bool(a.dashcam_all_meet and (robot_ok is not False)
                          and (robot_ok is not None or not a.robot_pool_n))
    if a.robot_pool_n and not a.robot_pool_eligible:
        a.capacity_met = False
    return a


# ---------------------------------------------------------------- task value
def _standing(o: Dict[str, Any], dev: Dict[str, Any], L: float) -> Dict[str, Any]:
    if _within(o, L):
        return dict(source="cloud", payload=o.get("cloud_payload") or {})
    return dict(source="device", payload=dev)


def robot_value(lo: Loaded, L_rob: float = ROB_L_S) -> Dict[str, Any]:
    """Standing-answer accuracy, the cloud's own accuracy, and the D81 WARM / COLD split."""
    path_by_opp = {r.get("opportunity_id"): r.get("cache_path")
                   for r in lo.requests if r.get("opportunity_id")}
    rows = []
    for opp, o in sorted(lo.outcomes.items()):
        if o["kind"] != "recall":
            continue
        dev = lo.device_answers.get(opp)
        if dev is None:
            raise ScoringRefused(f"no device answer recorded for recall opportunity {opp!r}")
        st = _standing(o, dev, L_rob)
        gold = dev["gold_letter"]
        cl = (o.get("cloud_payload") or {}).get("cloud_letter")
        rows.append(dict(opportunity_id=opp, device_id=o["device_id"],
                         question_id=o.get("question_id"), gold=gold,
                         source=st["source"], device_correct=bool(dev["device_correct"]),
                         cloud_letter=cl,
                         cloud_correct=(None if cl is None else (cl == gold)),
                         standing_correct=(bool(dev["device_correct"])
                                           if st["source"] == "device"
                                           else (None if cl is None else cl == gold)),
                         cache_path=path_by_opp.get(opp)))
    def acc(sel) -> Optional[float]:
        v = [r for r in rows if sel(r) and r["standing_correct"] is not None]
        return round(sum(1 for r in v if r["standing_correct"]) / len(v), 6) if v else None
    served = [r for r in rows if r["source"] == "cloud"]
    cloud_known = [r for r in served if r["cloud_correct"] is not None]
    out = dict(
        n=len(rows), n_cloud_standing=len(served), n_device_standing=len(rows) - len(served),
        standing_accuracy=acc(lambda r: True),
        standing_accuracy_n=sum(1 for r in rows if r["standing_correct"] is not None),
        device_only_accuracy=(round(sum(1 for r in rows if r["device_correct"]) / len(rows), 6)
                              if rows else None),
        cloud_accuracy_on_served=(round(sum(1 for r in cloud_known if r["cloud_correct"])
                                        / len(cloud_known), 6) if cloud_known else None),
        cloud_answers_available=len(cloud_known),
        warm_cold={
            name: dict(n=sum(1 for r in served if r["cache_path"] == p),
                       cloud_accuracy=(
                           round(sum(1 for r in served
                                     if r["cache_path"] == p and r["cloud_correct"])
                                 / max(1, sum(1 for r in served if r["cache_path"] == p
                                              and r["cloud_correct"] is not None)), 6)
                           if any(r["cache_path"] == p and r["cloud_correct"] is not None
                                  for r in served) else None))
            for name, p in (("WARM", "WARM"), ("COLD", "COLD"), ("unknown", None))},
        rows=rows)
    if len(served) and not cloud_known:
        out["note"] = ("the cloud delivered answers but none carried a letter, so no cloud or "
                       "standing accuracy is computable for this run (a stub coordinator holds "
                       "no model); this is reported, not imputed")
    return out


def _ap_streams(lo: Loaded, cal: Dict[str, Any], L_dash: float,
                device_map_key: str = "device_4b_orin",
                cloud_map_key: str = "h100_32b") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Per-play calibrated score streams on StudyE9b's 0.25-s grid, plus the play-level meta.

    The decision cadence is 0.5 s and the AP grid is 0.25 s, so the standing score is held
    forward one grid point (sample and hold, StudyE9b's own delivery convention). A grid point
    before the play's first standing answer is StudyE9b's MISSING sentinel.
    """
    import numpy as np
    import study_e9b_dense as B
    clips = DS.nexar_clip_meta()
    dm, cm = cal["maps"][device_map_key], cal["maps"][cloud_map_key]
    rec_by_play: Dict[str, List[Dict[str, Any]]] = {}
    completed: Dict[str, bool] = {}
    for r in lo.records:
        if r["kind"] != "monitor_opportunity":
            continue
        rec_by_play.setdefault(r["play_id"], []).append(r)
        completed[r["play_id"]] = bool(r["play_completed"])
    streams: Dict[str, Any] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    n_missing_cloud_score = 0
    for play, recs in rec_by_play.items():
        if not completed[play]:
            continue                       # D85: plays cut by the run end, excluded for all arms
        clip = recs[0]["clip"]
        G = clips[clip].grid_points
        arr = np.full(G, B.MISSING, dtype=np.float64)
        for r in sorted(recs, key=lambda x: x["t_local"]):
            o = lo.outcomes.get(r["opportunity_id"])
            dev = lo.device_answers[r["opportunity_id"]]
            if o is not None and _within(o, L_dash):
                cs = (o.get("cloud_payload") or {}).get("cloud_score")
                if cs is None:
                    n_missing_cloud_score += 1
                    v = DS.calibrate(float(dev["device_score"]), dm)
                else:
                    v = DS.calibrate(float(cs), cm)
            else:
                v = DS.calibrate(float(dev["device_score"]), dm)
            i = int(round((float(r["t_local"]) - B.T0) / B.STEP_DENSE))
            if 0 <= i < G:
                arr[i] = v
                if i + 1 < G:
                    arr[i + 1] = v          # hold over the 0.25-s point the cadence skips
        streams[play] = arr
        meta[play] = dict(event=clips[clip].event_s, G=G, clip=clip,
                          label=clips[clip].label)
    return streams, dict(meta=meta, n_missing_cloud_score=n_missing_cloud_score)


def dashcam_value(lo: Loaded, cal: Dict[str, Any], L_dash: float = DASH_L_S) -> Dict[str, Any]:
    """Play-indexed streaming AP (D85) through StudyE9b's own engine. Never re-implemented."""
    import metrics
    streams, info = _ap_streams(lo, cal, L_dash)
    meta = info["meta"]
    pos = sorted(p for p, m in meta.items() if m["label"] == "positive"
                 and m["event"] is not None)
    neg = sorted(p for p, m in meta.items() if m["label"] == "negative")
    out: Dict[str, Any] = dict(n_plays=len(meta), n_pos_plays=len(pos), n_neg_plays=len(neg),
                               n_missing_cloud_score=info["n_missing_cloud_score"],
                               caveat=DS.AP_CAVEAT)
    if info["n_missing_cloud_score"]:
        out["ap"] = None
        out["refused"] = ("one or more cloud answers carried no score, so the standing stream "
                          "would mix a cloud DECISION with a DEVICE score; AP is not computed. "
                          f"affected instants: {info['n_missing_cloud_score']}")
        return out
    if not pos or not neg:
        out["ap"] = None
        out["refused"] = ("the completed plays in this run hold no positive or no negative clip, "
                          "so AP is undefined; pool across seeds (D85) or use a longer run")
        return out
    ctx = dict(meta=meta, pos=pos, neg=neg, step=0.25)
    metrics._APENG.clear()                 # the cache is keyed by horizons only, not by play set
    out["ap"] = {str(k): round(v, 6)
                 for k, v in metrics.streaming_ap(ctx, streams, AP_HORIZONS).items()}
    out["streams_digest_n"] = len(streams)
    return out


def device_only_value(lo: Loaded, cal: Dict[str, Any]) -> Dict[str, Any]:
    """The device-only arm, computed FROM THE RECORDINGS with no run (D65).

    Every opportunity's standing answer is the device's, so this needs no coordinator at all.
    """
    import numpy as np
    import metrics
    import study_e9b_dense as B
    clips = DS.nexar_clip_meta()
    dm = cal["maps"]["device_4b_orin"]
    rec_by_play: Dict[str, List[Dict[str, Any]]] = {}
    completed: Dict[str, bool] = {}
    for r in lo.records:
        if r["kind"] == "monitor_opportunity":
            rec_by_play.setdefault(r["play_id"], []).append(r)
            completed[r["play_id"]] = bool(r["play_completed"])
    streams, meta = {}, {}
    for play, recs in rec_by_play.items():
        if not completed[play]:
            continue
        clip = recs[0]["clip"]
        G = clips[clip].grid_points
        arr = np.full(G, B.MISSING, dtype=np.float64)
        for r in sorted(recs, key=lambda x: x["t_local"]):
            v = DS.calibrate(float(lo.device_answers[r["opportunity_id"]]["device_score"]), dm)
            i = int(round((float(r["t_local"]) - B.T0) / B.STEP_DENSE))
            if 0 <= i < G:
                arr[i] = v
                if i + 1 < G:
                    arr[i + 1] = v
        streams[play] = arr
        meta[play] = dict(event=clips[clip].event_s, G=G, clip=clip, label=clips[clip].label)
    pos = sorted(p for p, m in meta.items() if m["label"] == "positive"
                 and m["event"] is not None)
    neg = sorted(p for p, m in meta.items() if m["label"] == "negative")
    ap = None
    if pos and neg:
        metrics._APENG.clear()
        ap = {str(k): round(v, 6) for k, v in
              metrics.streaming_ap(dict(meta=meta, pos=pos, neg=neg, step=0.25),
                                   streams, AP_HORIZONS).items()}
    rec = [d for d in lo.device_answers.values() if d["kind"] == "recall"]
    return dict(dashcam_ap=ap, n_plays=len(meta),
                robot_accuracy=(round(sum(1 for d in rec if d["device_correct"]) / len(rec), 6)
                                if rec else None),
                robot_n=len(rec), caveat=DS.DEVICE_ANSWER_CAVEAT)


# ---------------------------------------------------------------- intervals
def paired_bootstrap(units: Sequence[Any], f_a, f_b, n: int = N_BOOT,
                     seed: int = 0) -> Optional[Dict[str, Any]]:
    """CI of mean(f_a) - mean(f_b) under a resample of the SAME units for both arms."""
    units = list(units)
    if not units:
        return None
    rng = random.Random(seed)
    a0 = sum(f_a(u) for u in units) / len(units)
    b0 = sum(f_b(u) for u in units) / len(units)
    diffs = []
    for _ in range(n):
        idx = [rng.randrange(len(units)) for _ in units]
        sa = sum(f_a(units[i]) for i in idx) / len(idx)
        sb = sum(f_b(units[i]) for i in idx) / len(idx)
        diffs.append(sa - sb)
    diffs.sort()
    def pc(p: float) -> float:
        return diffs[min(len(diffs) - 1, max(0, int(p * len(diffs))))]
    return dict(n_units=len(units), n_boot=n, arm=round(a0, 6), baseline=round(b0, 6),
                diff=round(a0 - b0, 6), ci=[round(pc(0.025), 6), round(pc(0.975), 6)],
                note="paired: the same resampled units are used for both arms. No pass / fail "
                     "margin is applied (D64).")


def ap_diff_bootstrap(streams_a: Dict[str, Any], streams_b: Dict[str, Any],
                      meta: Dict[str, Dict[str, Any]], horizon: float = 1.0,
                      n: int = N_BOOT_AP, seed: int = 0) -> Optional[Dict[str, Any]]:
    """Label-stratified PLAY resample of the AP difference, with StudyE9b's own `ap_point`."""
    import numpy as np
    import study_e9b_dense as B
    pos = sorted(p for p, m in meta.items() if m["label"] == "positive"
                 and m["event"] is not None)
    neg = sorted(p for p, m in meta.items() if m["label"] == "negative")
    if not pos or not neg:
        return None
    ti = {p: B.target_index(meta, p, horizon, 0.25) for p in pos}

    def ap_of(streams, P, N) -> float:
        V = np.array([streams[p][ti[p]] for p in P])
        Ncat = np.concatenate([streams[q] for q in N])
        return float(B.ap_point(V, Ncat))

    a0, b0 = ap_of(streams_a, pos, neg), ap_of(streams_b, pos, neg)
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        P = [pos[rng.randrange(len(pos))] for _ in pos]
        N = [neg[rng.randrange(len(neg))] for _ in neg]
        d.append(ap_of(streams_a, P, N) - ap_of(streams_b, P, N))
    d.sort()
    def pc(p: float) -> float:
        return d[min(len(d) - 1, max(0, int(p * len(d))))]
    return dict(horizon=horizon, n_pos=len(pos), n_neg=len(neg), n_boot=n,
                arm=round(a0, 6), baseline=round(b0, 6), diff=round(a0 - b0, 6),
                ci=[round(pc(0.025), 6), round(pc(0.975), 6)])


# ---------------------------------------------------------------- D97 measurability
REPORTED_SEEDS = (1, 2, 3)              # D97
PILOT_SEED = 0                          # D95 (7), never used in a reported run
NOT_MEASURABLE = "robot part not measurable"


def eligibility_table(paths: Sequence[Path]) -> Dict[str, Dict[int, Dict[int, bool]]]:
    """Read trace metadata into {ratio: {n_devices: {seed: eligible}}}.

    The input is trace metadata, never a run: D97 fixes eligibility from traces, so this never
    needs a server, a GPU or an outcome. `paths` may be trace directories, `trace_meta.json`
    files, or the eligibility CSV that `fleet/eligibility.py` writes.
    """
    out: Dict[str, Dict[int, Dict[int, bool]]] = {}

    def put(ratio: str, n: int, seed: int, ok: bool) -> None:
        prev = out.setdefault(str(ratio), {}).setdefault(int(n), {}).get(int(seed))
        if prev is not None and prev != bool(ok):
            raise ScoringRefused(
                f"two different eligibility verdicts for ratio {ratio} size {n} seed {seed}; "
                f"the same cell cannot be both eligible and not")
        out[str(ratio)][int(n)][int(seed)] = bool(ok)

    for q in paths:
        q = Path(q)
        if q.is_dir():
            q = q / "trace_meta.json"
        if q.suffix == ".csv":
            import csv as _csv
            with open(q) as fh:
                for row in _csv.DictReader(fh):
                    put(row["ratio"], int(row["n_devices"]), int(row["seed"]),
                        int(row["robot_eligible"]) == 1)
            continue
        m = json.loads(Path(q).read_text())
        nq = int(m["stats"]["robot_questions_total"])
        put(m["ratio"], int(m["n_devices"]), int(m["seed"]), nq >= ROB_MIN_QUESTIONS)
    return out


def d97_sweep_sizes(table: Dict[str, Dict[int, Dict[int, bool]]], ratio: str,
                    seeds: Sequence[int] = REPORTED_SEEDS) -> Dict[str, Any]:
    """D97: a size is in the comparison only if eligible at EVERY seed in the reported set.

    `seeds` is the set that WILL BE REPORTED for this comparison, so if a third seed is not run
    (D79 makes it conditional) the caller passes the two it has and the rule is applied to those.
    Returns a per-size verdict and the entry point, which is the smallest INCLUDED size.
    """
    if PILOT_SEED in seeds:
        raise ScoringRefused(
            f"seed {PILOT_SEED} is the PILOT seed and never enters a reported comparison or "
            f"sets an entry point (D95 (7), D97). Use d97_pilot_labels for the pilot.")
    sizes = table.get(str(ratio), {})
    per: Dict[int, Dict[str, Any]] = {}
    for n in sorted(sizes):
        by_seed = {int(s): sizes[n].get(int(s)) for s in seeds}
        missing = sorted(s for s, v in by_seed.items() if v is None)
        included = (not missing) and all(bool(v) for v in by_seed.values())
        per[n] = dict(included=included, per_seed=by_seed, missing_seeds=missing,
                      label=("included" if included else NOT_MEASURABLE),
                      reason=("eligible at every reported seed" if included else
                              (f"no trace for seed(s) {missing}" if missing else
                               "ineligible at seed(s) " + str(sorted(
                                   s for s, v in by_seed.items() if v is False)))))
    inc = [n for n in sorted(per) if per[n]["included"]]
    entry = min(inc) if inc else None
    above = [n for n in sorted(per) if entry is not None and n > entry
             and not per[n]["included"]]
    return dict(ratio=str(ratio), reported_seeds=list(seeds), per_size=per,
                included_sizes=inc, entry_point=entry,
                non_monotone_sizes_above_entry=above, monotone=(not above),
                rule=("D97 (user ruling 2026-11-17, row pending): included only if the robot "
                      "pool is eligible at EVERY reported seed; a size is never made measurable "
                      "by averaging or borrowing across seeds. Eligibility is checked for each "
                      "size actually chosen and never assumed from the entry point upward."))


def d97_pilot_labels(table: Dict[str, Dict[int, Dict[int, bool]]], ratio: str,
                     pilot_seed: int = PILOT_SEED) -> Dict[str, Any]:
    """The pilot reports WHICH sizes were measurable at its own seed, and nothing more (D95 (7)).

    There is deliberately no entry point in the result: the pilot seed never sets one, and a
    caller that wants one must use `d97_sweep_sizes` on the reported seeds.
    """
    sizes = table.get(str(ratio), {})
    per = {n: ("measurable at seed %d" % pilot_seed
               if sizes[n].get(int(pilot_seed)) else
               "not measurable at seed %d" % pilot_seed)
           for n in sorted(sizes) if int(pilot_seed) in sizes[n]}
    return dict(ratio=str(ratio), pilot_seed=int(pilot_seed), per_size=per,
                entry_point=None,
                note=("D95 (7) and D97: the pilot seed is never used in a reported run and NEVER "
                      "sets an entry point. These labels say only which pilot sizes were "
                      "measurable at seed %d." % int(pilot_seed)))


# ---------------------------------------------------------------- diagnostics (D64)
def diagnostics(lo: Loaded) -> Dict[str, Any]:
    """D64's always-reported diagnostics, from the coordinator's own logs where they exist."""
    out: Dict[str, Any] = dict(
        emulator=dict(cpu_s=lo.run_meta.get("cpu_s"),
                      cpu_fraction=lo.run_meta.get("cpu_fraction"),
                      wall_s=lo.run_meta.get("wall_s"),
                      lateness=lo.run_meta.get("lateness"),
                      run_valid=lo.run_meta.get("run_valid"),
                      maxrss_kb=lo.run_meta.get("maxrss_kb")),
        uplink_queue=dict(p99_s_median=lo.run_meta.get("uplink_queue_p99_s_median")),
        decision_log_present=bool(lo.decisions),
        request_log_present=bool(lo.requests))
    if lo.decisions:
        kinds: Dict[str, int] = {}
        pieces: List[int] = []
        lat: List[float] = []
        pred_vs_act: List[Dict[str, Any]] = []
        for d in lo.decisions:
            kinds[d.get("kind", "?")] = kinds.get(d.get("kind", "?"), 0) + 1
            if d.get("piece_tokens"):
                pieces.append(int(d["piece_tokens"]))
            if d.get("decision_latency_ms") is not None:
                lat.append(float(d["decision_latency_ms"]))
            p = (d.get("predicted") or {})
            if p.get("completion_s") is not None:
                pred_vs_act.append(dict(decision_id=d.get("decision_id"),
                                        predicted_completion_s=p["completion_s"],
                                        traffic_mix=d.get("traffic_mix")))
        lat.sort()
        pieces.sort()
        out["decisions"] = dict(
            n=len(lo.decisions), by_kind=kinds,
            hold_or_decline=sum(v for k, v in kinds.items() if k in ("decline", "defer")),
            piece_tokens=dict(n=len(pieces),
                              p50=(pieces[len(pieces) // 2] if pieces else None),
                              min=(pieces[0] if pieces else None),
                              max=(pieces[-1] if pieces else None)),
            decision_latency_ms=dict(n=len(lat),
                                     p50=(lat[len(lat) // 2] if lat else None),
                                     p99=(lat[int(0.99 * (len(lat) - 1))] if lat else None)),
            predicted_vs_actual_rows=len(pred_vs_act),
            predicted_vs_actual_note=("D63: the joiner that pairs these predictions with the "
                                      "measured outcomes is the coordinator session's; where it "
                                      "is absent the rows are carried through unjoined"))
    else:
        out["decisions"] = dict(n=0, note="no coordinator decision log in this run directory "
                                          "(a stub coordinator makes none)")
    if lo.requests:
        paths: Dict[str, int] = {}
        for r in lo.requests:
            paths[str(r.get("cache_path"))] = paths.get(str(r.get("cache_path")), 0) + 1
        out["cache_path_counts"] = paths
        out["cache_path_caveat"] = DS.CACHE_PATH_CAVEAT
    return out


# ---------------------------------------------------------------- the run score
def score_run(trace_dir: Path, run_dir: Path, calibration: Path, arm: str,
              L_dash_grid: Sequence[float] = (DASH_L_S,),
              p_dash_grid: Sequence[float] = (DASH_P,),
              L_rob_grid: Sequence[float] = (ROB_L_S,),
              p_rob_grid: Sequence[float] = (ROB_P,),
              with_value: bool = True) -> Dict[str, Any]:
    lo = load(trace_dir, run_dir)
    cal = DS.calibration(Path(calibration))
    check_calibration(cal, lo.run_meta)
    sweep = []
    for Ld in L_dash_grid:
        for pd in p_dash_grid:
            for Lr in L_rob_grid:
                for pr in p_rob_grid:
                    a = attainment(lo, Ld, pd, Lr, pr)
                    sweep.append(dict(L_dash=Ld, p_dash=pd, L_rob=Lr, p_rob=pr,
                                      **{k: v for k, v in a.__dict__.items()
                                         if k != "dashcam_per_device"},
                                      dashcam_per_device=a.dashcam_per_device))
    base = dict(arm=arm, trace_dir=str(trace_dir), run_dir=str(run_dir),
                seed=lo.meta["seed"], n_devices=lo.meta["n_devices"], ratio=lo.meta["ratio"],
                run_s=lo.meta["run_s"], mode=lo.run_meta.get("mode"),
                server_kind=lo.run_meta.get("server_kind"),
                is_measurement=(lo.run_meta.get("server_kind")
                                not in NON_MEASUREMENT_SERVERS
                                and cal["label"] == "FINAL"),
                calibration=dict(path=cal["path"], sha256=cal["sha256"], label=cal["label"],
                                 note=cal["note"]),
                targets_are_inputs=("D71: targets are INPUTS. Every setting in the sweep is "
                                    "reported. The scorer never selects one."),
                target_defaults=dict(L_dash=DASH_L_S, p_dash=DASH_P,
                                     min_dash_instants=DASH_MIN_INSTANTS, L_rob=ROB_L_S,
                                     p_rob=ROB_P, min_rob_questions_pooled=ROB_MIN_QUESTIONS,
                                     source="D71 as amended by D82"),
                caveats=[DS.AP_CAVEAT, DS.DEVICE_ANSWER_CAVEAT, DS.SEMBER_JPEG_CAVEAT,
                         DS.CACHE_PATH_CAVEAT],
                sweep=sweep, diagnostics=diagnostics(lo))
    if with_value:
        rv = robot_value(lo, L_rob_grid[0])
        rv_rows = rv.pop("rows")
        base["robot_value"] = rv
        base["robot_rows"] = rv_rows
        base["dashcam_value"] = dashcam_value(lo, cal, L_dash_grid[0])
        base["device_only"] = device_only_value(lo, cal)
    return base


# ---------------------------------------------------------------- across arms and fleet sizes
def capacity(scores: Sequence[Dict[str, Any]], setting_index: int = 0) -> Dict[str, Any]:
    """D64 / D82: per arm, the largest fleet size at which the conjunct holds.

    `scores` is one score dict per (arm, fleet size); `setting_index` picks the sweep cell. The
    result also lists every fleet size and whether it met, because "largest at which it held" is
    only meaningful next to the whole ladder (a non-monotone ladder is itself a finding).
    """
    by_arm: Dict[str, List[Tuple[int, bool]]] = {}
    for s in scores:
        cell = s["sweep"][setting_index]
        by_arm.setdefault(s["arm"], []).append((int(s["n_devices"]), bool(cell["capacity_met"])))
    out = {}
    for arm, rows in by_arm.items():
        rows.sort()
        met = [n for n, ok in rows if ok]
        mono = all(not ok for n, ok in rows if met and n > max(met))
        out[arm] = dict(ladder=[dict(n_devices=n, capacity_met=ok) for n, ok in rows],
                        capacity=(max(met) if met else None),
                        monotone=mono,
                        note=("capacity is the largest fleet size at which EVERY eligible "
                              "dashcam device meets its target AND the robot pool meets its "
                              "target (D64, D82). `monotone` false means the ladder is not "
                              "monotone and the single number must not be read alone."))
    return out


def compare(policy: Dict[str, Any], baseline: Dict[str, Any],
            setting_index: int = 0, seed: int = 0) -> Dict[str, Any]:
    """Paired policy-minus-baseline differences within one run (D64: intervals, no margins)."""
    pc = policy["sweep"][setting_index]
    bc = baseline["sweep"][setting_index]
    dash_units = sorted(set(pc["dashcam_per_device"]) & set(bc["dashcam_per_device"]))
    out: Dict[str, Any] = dict(policy=policy["arm"], baseline=baseline["arm"],
                               setting={k: pc[k] for k in ("L_dash", "p_dash", "L_rob", "p_rob")})
    out["dashcam_attainment"] = paired_bootstrap(
        dash_units,
        lambda d: float(pc["dashcam_per_device"][d]["fraction"] or 0.0),
        lambda d: float(bc["dashcam_per_device"][d]["fraction"] or 0.0),
        seed=seed)
    pr = {r["opportunity_id"]: r for r in policy.get("robot_rows", [])}
    br = {r["opportunity_id"]: r for r in baseline.get("robot_rows", [])}
    qs = sorted(set(pr) & set(br))
    out["robot_on_time"] = paired_bootstrap(
        qs, lambda q: 1.0 if pr[q]["source"] == "cloud" else 0.0,
        lambda q: 1.0 if br[q]["source"] == "cloud" else 0.0, seed=seed)
    both = [q for q in qs if pr[q]["standing_correct"] is not None
            and br[q]["standing_correct"] is not None]
    out["robot_standing_accuracy"] = paired_bootstrap(
        both, lambda q: 1.0 if pr[q]["standing_correct"] else 0.0,
        lambda q: 1.0 if br[q]["standing_correct"] else 0.0, seed=seed)
    out["note"] = ("differences are policy minus baseline on the SAME units. The dashcam AP "
                   "difference needs both arms' play streams and is produced by "
                   "`ap_diff_bootstrap` from a scorer run that holds both.")
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trace", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--calibration", default=str(DS.ORIN_CALIBRATION))
    ap.add_argument("--out", default=None)
    ap.add_argument("--L-dash", type=float, nargs="*", default=[DASH_L_S])
    ap.add_argument("--p-dash", type=float, nargs="*", default=[DASH_P])
    ap.add_argument("--L-rob", type=float, nargs="*", default=[ROB_L_S])
    ap.add_argument("--p-rob", type=float, nargs="*", default=[ROB_P])
    ap.add_argument("--no-value", action="store_true")
    a = ap.parse_args(argv)
    s = score_run(Path(a.trace), Path(a.run), Path(a.calibration), a.arm,
                  a.L_dash, a.p_dash, a.L_rob, a.p_rob, not a.no_value)
    txt = json.dumps(s, indent=2, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(txt)
    slim = {k: v for k, v in s.items() if k not in ("robot_rows",)}
    print(json.dumps(slim, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
