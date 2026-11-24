#!/usr/bin/env python3
"""The offline scorer for live round 1: attainment, capacity, task value, intervals.

StudyLIVE2-fleet, part 5. CPU only. It reads a trace, one run per arm, and the input calibration
maps; it writes a score file per run and a comparison across arms. It never runs a model and
never touches a GPU, so it can be re-run on any box against committed run outputs.

THE STANDING ANSWER (the object every metric is computed on)

  standing answer = the CLOUD's answer if it was DELIVERED within L, else the DEVICE's answer.

D155 (3), amending D152 (1), splits that sentence in two and the robot headline takes the FIRST:

  BY DEADLINE (the headline)  the cloud's answer if delivered within L, else the DEVICE's answer
                              IF IT TOO ARRIVES WITHIN L, else NO answer and the question misses.
  ANY TIME (reported beside)  the cloud's answer if delivered within L, else the device's answer
                              whenever it lands. This is the D152 (1) behaviour, kept and labelled.

The two are never mixed in one column or one sentence. Every output carries them in separate
fields suffixed `_by_deadline` and `_any_time`, and the device-latency source that decides the
first is recorded beside them (`device_delivery_rule`). The on-time-only tables are untouched.

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

WHAT D99, D101, D103 AND D105 ADD

  D101   robots join their first session part-way, so a `history_preload` declares what the
         cloud already held at t = 0 and the questions before the join point do not exist. The
         preload is never an opportunity and is never scored; it is REPORTED (`history_preload`),
         and a run whose preload count differs from its trace is refused, because a different
         holding at t = 0 is a different experiment.
  D103   (e) the AP-difference bootstrap is n = 1,000; (f) every comparison is labelled PRIMARY
         or EXPLORATORY against the pre-registered primary family, with the break sizes passed
         IN so the family cannot be chosen after the result; (h) the committed E10a median frame
         size is for flash tests only, and a MEASURED run whose `frame_bytes_source` is not the
         Part-2 encode manifest (D91) is REFUSED.
  D105   each clip is scored with the map from the folds that EXCLUDE it, the fold assignment
         taken from the calibration file. A FINAL map with no fold assignment is REFUSED rather
         than applied pooled.
  D99    the decision period (100 ms, one for every arm) and the coordinator's own latency are
         recorded settings and stay in the diagnostics.

CALIBRATION MAPS ARE INPUT FILES, AND AN INTERIM MAP CANNOT SCORE A MEASUREMENT (D86)

The dense refit of both tiers is an H100 task. Until it exists, `orin2_calibration.json`'s maps
are INTERIM: fitted on an event-anchored 10-offset sample while round 1 scores every instant on a
dense trajectory, with the D3-fitted device slope 3.007x steeper than a dense D14b-DEV fit. The
scorer therefore REFUSES to score a run whose server is not a stub when the map is INTERIM. A
stub run is scored, and every output says `is_measurement: false`.

ROBOT MEASURABILITY (D97)

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
import os
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
# D154 (5) needs the LIVE cascade device-answer charge in order to LABEL a cascade cell, and that
# charge lives in the baselines cost table (`costs.DEV_LAT_S`), read by `coordinator.py:63`.
# Importing the table is cheap: it holds constants only and loads no model and no score data.
import costs as C              # noqa: E402

DASH_L_S = DS.NEXAR_DEADLINE_S          # 1.0 (D71)
DASH_P = 0.25                           # D71
DASH_MIN_INSTANTS = 200                 # D71
ROB_L_S = DS.ROBOT_DEADLINE_S           # 5.0 (D71)
ROB_P = 0.90                            # D71
ROB_MIN_QUESTIONS = 20                  # D82, POOLED over the run
# D142 item 3 / D143: single-shot is a THIRD device type and must not be scored as a robot. Its
# opportunities reuse the committed `recall_question` record kind on purpose, so the OUTCOME's kind
# is "recall" for both and cannot separate them. The DEVICE ANSWER's kind can: the trace writes
# kind="assistive" for a single-shot answer and kind="recall" for a robot one.
SS_L_S = 2.0                            # D142 item 3, the single-shot deadline
SS_P = 0.90                             # same target shape as the robot pool; reported, not a gate


# The fleet names devices by type (`fleet/trace.py`: dash###, robo###, asst###), so the device id
# is a fallback discriminator when the device answers are not in hand. It is a FALLBACK, not the
# rule: the authoritative field is the device answer's own kind.
ASSISTIVE_DEVICE_PREFIX = "asst"


# D146: the delivery rule, read ONCE at import. `load` applies it and `score_run` records it in
# every returned dict, so a committed cell says which rule produced it.
DELIVERY = os.environ.get("LIVE2_DELIVERY", "completion")
if DELIVERY not in ("completion", "first_token"):
    raise SystemExit("LIVE2_DELIVERY must be completion or first_token")

# ---------------------------------------------------------------- D155: the DEVICE side of the
# delivery rule. These names are the ONE definition both scorers use.
#
# D152 (1) made the robot headline CORRECT ANSWERS DELIVERED and credited the DEVICE's answer
# whenever the cloud missed the deadline, with no regard for when the device's own answer would
# land. D155 (3) AMENDS that: a device answer counts only if it ARRIVES WITHIN THE DEADLINE, and
# the old rule ("correct at any time") is reported BESIDE it. The two are never mixed in one
# column or one sentence, which is why `robot_value` returns two separate fields and
# `robot_headline` carries two separate numbers rather than one number and a footnote.
#
# These are MODULE-LEVEL on purpose, and `frozen_headline.py` IMPORTS them from here rather than
# reading an environment variable of its own. The D146 `DELIVERY` switch was module-level in this
# file and local in that one, the two scorers disagreed, and the switch had to be hoisted by
# hand. One definition, one read, one place to change.
#
# WHERE THE DEVICE LATENCY COMES FROM, and it is a SLOT, not a constant:
#   "orin_rec_warm"    THE DEFAULT from 2026-11-20. StudyORIN-REC's MEASURED WARM per-question
#                      device COMPLETION latency on the 97 LH-REQ questions (Jetson AGX Orin,
#                      qwen3vl4b under vLLM, commit 00a223d): p50 0.2697 s, p90 0.2894 s, min
#                      0.2503 s, max 0.3108 s over 97 questions. Read per question from the
#                      committed `results/sember/study_orin_rec/orin_rec_warm.jsonl` through
#                      `data_sources.device_recall_warm_latency_s`, never copied into a constant
#                      here. WARM PATH, labelled: the exact RECENT frames are prefilled first and
#                      `cached_tokens` covers them on all 97, so it must not be read against a
#                      cold prefill curve.
#   "trace"            SUPERSEDED, kept so a cell scored before the measurement reproduces
#                      exactly. The per-question `device_latency_s` the trace generator wrote
#                      into `device_answers.jsonl`, which for robot recall is
#                      `data_sources.device_recall_latency_s(history_tokens)`: D87's ORIN2
#                      IN-PROCESS harness cost, 0.146 s at 11k tokens and 0.225 s at 28k,
#                      interpolated between and clamped outside. D146 (2) REPLACES exactly this
#                      substitution, so every output produced under it says `superseded`.
#   "measured:<path>"  a JSON table of MEASURED per-question device latencies, keyed by
#                      `question_id` or by `opportunity_id`, either as {key: seconds} or as
#                      {key: {"device_latency_s": seconds}}. The generic drop-in slot, kept for a
#                      later device or a sensitivity run.
#
# The DEFAULT was moved off "trace" deliberately, rather than left to an environment variable a
# run might forget to set. A quantity the whole by-deadline column turns on must not have a
# superseded default: `trace` is now something a run has to ASK for, and says so when it does.
#
# WHAT MUST NOT GO IN THAT SLOT (D155 (1)): the device's own answer latency on the 97 LH-REQ
# questions, end-to-end median 3.354 s of which 3.296 s is TTFT (D155a; the earlier 6.651 s added
# TTFT to an end-to-end figure that already contained it), is the COLD RE-SEND path. D61 (b)
# classifies the resend path as an API ARTIFACT and NOT the device baseline, so those numbers are
# not a device latency and are wired nowhere in this file. D155a also settles that the WARM figure
# needs no caveat on answer length: post-first-token time is 0.058 s cold and 0.059 s warm, so the
# 2-token answer costs the same either way and the whole cold excess is a re-prefill of frames the
# device already holds, charged before the first token.
DEVICE_LATENCY_SOURCE = os.environ.get("LIVE2_DEVICE_LATENCY", "orin_rec_warm")
if not (DEVICE_LATENCY_SOURCE in ("orin_rec_warm", "trace")
        or DEVICE_LATENCY_SOURCE.startswith("measured:")):
    raise SystemExit("LIVE2_DEVICE_LATENCY must be 'orin_rec_warm' (measured warm, the default), "
                     "'trace' (D87 interpolation, SUPERSEDED) or 'measured:<path to json>'")
# The device's clock starts at the QUESTION instant by default: D1 gives every device a local
# model it can run itself, so it is not waiting on the cloud to fail first. A cascade arm that
# makes the device wait for the cloud sets this instead of editing the rule.
DEVICE_WAIT_S = float(os.environ.get("LIVE2_DEVICE_WAIT_S", "0.0"))
_DEV_LAT_TABLE: Optional[Dict[str, float]] = None


def device_latency_table() -> Optional[Dict[str, float]]:
    """The measured warm per-question table, or None when the trace's own field is the source."""
    global _DEV_LAT_TABLE
    if DEVICE_LATENCY_SOURCE == "trace":
        return None
    if DEVICE_LATENCY_SOURCE == "orin_rec_warm":
        if _DEV_LAT_TABLE is None:
            _DEV_LAT_TABLE = DS.device_recall_warm_latency_s()
        return _DEV_LAT_TABLE
    if _DEV_LAT_TABLE is None:
        raw = json.loads(Path(DEVICE_LATENCY_SOURCE.split(":", 1)[1]).read_text())
        rows = raw
        if isinstance(raw, dict) and isinstance(raw.get("device_latency_s"), dict):
            rows = raw["device_latency_s"]
        _DEV_LAT_TABLE = {
            str(k): float(v["device_latency_s"] if isinstance(v, dict) else v)
            for k, v in rows.items()}
    return _DEV_LAT_TABLE


def device_latency_s(dev: Dict[str, Any]) -> float:
    """Seconds from the device's start to its own answer, for ONE opportunity.

    It REFUSES rather than guessing. A missing latency used to be invisible, because the device
    answer was credited whatever happened and there was no quantity to be missing. Under D155 it
    decides whether that answer counts at all, so an absent one is a stop condition, not a zero.
    """
    tab = device_latency_table()
    if tab is not None:
        for key in ("question_id", "opportunity_id"):
            k = dev.get(key)
            if k is not None and str(k) in tab:
                return float(tab[str(k)])
        raise ScoringRefused(
            "LIVE2_DEVICE_LATENCY=%s holds no measured device latency for question_id %r / "
            "opportunity_id %r, and D155 scores a device answer by WHEN IT ARRIVES, so there is "
            "nothing to fall back to" % (DEVICE_LATENCY_SOURCE, dev.get("question_id"),
                                         dev.get("opportunity_id")))
    v = dev.get("device_latency_s")
    if v is None:
        raise ScoringRefused(
            "device answer for opportunity %r carries no `device_latency_s`, so D155 cannot say "
            "whether it arrived within the deadline" % (dev.get("opportunity_id"),))
    return float(v)


_SS_LAT_TABLE: Optional[Dict[str, float]] = None
_DASH_LAT_TABLE: Optional[Dict[int, float]] = None


def single_shot_latency_table() -> Dict[str, float]:
    """Measured Orin SINGLE-SHOT completion per question (StudySS2). Separate table from the robot
    one, because the robot table is 97 LH-REQ questions and holds no single-shot id."""
    global _SS_LAT_TABLE
    if _SS_LAT_TABLE is None:
        try:
            _SS_LAT_TABLE = dict(DS.single_shot_total_s())
        except Exception:
            _SS_LAT_TABLE = {}
    return _SS_LAT_TABLE


def dashcam_latency_table() -> Dict[int, float]:
    """Measured Orin EP-G warm-append first token by episode frame position."""
    global _DASH_LAT_TABLE
    if _DASH_LAT_TABLE is None:
        try:
            _DASH_LAT_TABLE = dict(DS.dashcam_append_ttft_s())
        except Exception:
            _DASH_LAT_TABLE = {}
    return _DASH_LAT_TABLE


def device_latency_any_type_s(o: Dict[str, Any], dev: Dict[str, Any]) -> Optional[float]:
    """The measured device latency for THIS opportunity, whatever its type (D155 (3) for all types).

    Per type, because the three tables are different measurements and none of them covers another's
    ids: robot recall from StudyORIN-REC WARM (completion), single-shot from StudySS2 (completion,
    D146 (1)), dashcam from StudySH-EP EP-G warm append by episode frame position (first token,
    which D146 (1) allows for a Yes/No alert).

    Returns None when no measured value exists for this opportunity, so a caller can REPORT the gap
    rather than be handed a silent number. It never falls back to another type's table: that is the
    cross-type substitution that produced the proxy-0.567-cross-type label.
    """
    qid = o.get("question_id") or dev.get("question_id")
    if o.get("kind") == "monitor":
        tab = dashcam_latency_table()
        if not tab:
            return None
        n = o.get("episode_frames") or dev.get("episode_frames") or len(
            o.get("episode_frame_refs") or ()) or 1
        n = min(max(int(n), min(tab)), max(tab))
        return float(tab[n])
    if qid is not None:
        rob = device_latency_table()
        if rob is not None and str(qid) in rob:
            return float(rob[str(qid)])
        ss = single_shot_latency_table()
        if str(qid) in ss:
            return float(ss[str(qid)])
    v = dev.get("device_latency_s")
    return float(v) if v is not None else None


def device_within(o: Dict[str, Any], dev: Dict[str, Any], L: float) -> bool:
    """D155 (3): did the DEVICE's own answer arrive within the deadline?

    Measured from the same `t_opportunity` the cloud's deadline is measured from, so both sides
    of the comparison are on one clock. Applies to EVERY type: the per-type measured latency comes
    from `device_latency_any_type_s`, and an opportunity with NO measured device latency is treated
    as NOT within the deadline, because crediting it would be the unconditional device credit this
    rule exists to remove.
    """
    v = device_latency_any_type_s(o, dev)
    if v is None:
        return False
    return (DEVICE_WAIT_S + v) <= L + 1e-9


_MEANING = {
    "trace": ("trace: the per-question `device_latency_s` in device_answers.jsonl, which for "
              "robot recall is D87's ORIN2 IN-PROCESS cost, 0.146 s at 11k tokens to 0.225 s "
              "at 28k, interpolated and clamped. SUPERSEDED by D146 (2); kept only so a cell "
              "scored before StudyORIN-REC's warm measurement reproduces exactly."),
    "orin_rec_warm": ("orin_rec_warm: StudyORIN-REC's MEASURED WARM per-question device "
                      "COMPLETION latency on the 97 LH-REQ questions (Jetson AGX Orin, "
                      "qwen3vl4b under vLLM, commit 00a223d). WARM PATH: the exact RECENT "
                      "frames are prefilled first and cached_tokens covers them on all 97, so "
                      "it is not comparable to a cold prefill curve."),
}


def cascade_device_wait() -> Dict[str, Any]:
    """D154 (5): what the five cascade-style arms pay for the device answer, and its REGISTER.

    This is a LABEL, not a behaviour change, and the distinction is the whole point of the entry.
    The live wait those arms pay is `baselines/costs.py:37 DEV_LAT_S = 0.567`, read by
    `coordinator.py:63 DEVICE_ANSWER_CHARGE_S` and applied at `coordinator.py:471` (the device
    answer's service time) and `coordinator.py:505` (the earliest instant such an arm may act).
    Both are LIVE decision-timing sites, so adopting the measured value changes what the arm DOES
    and needs a RERUN, which is what D154 (5) queues. No re-score can produce it.

    `data_sources.DEVICE_WAIT_RULE_S` is NOT that site: it has one reference in the repository,
    its own declaration, so it is write-only and wiring a number into it would change nothing.
    """
    applied = abs(float(C.DEV_LAT_S) - float(DS.DEVICE_WAIT_MEASURED_S)) <= 1e-9
    return dict(
        arms=list(DS.CASCADE_ARMS),
        live_charge_s=float(C.DEV_LAT_S),
        live_charge_site="baselines/costs.py:37 -> coordinator.py:63, applied at :471 and :505",
        measured_warm_s=float(DS.DEVICE_WAIT_MEASURED_S),
        measured_warm_source="StudyORIN-REC warm p50 (commit 00a223d), per question where keyed",
        measured_device_wait_applied=applied,
        label=("measured-warm" if applied else "proxy-0.567"),
        register=("the live cascade wait is a RERUN item, not a re-score: it changes when the arm "
                  "may act. Until coordinator.py adopts the measured value every cascade cell is "
                  "labelled proxy-0.567 per D154 (5), whatever the scorer's device latency "
                  "source is. The scorer's own device-answer arrival IS on the measured table."),
        superseded=("data_sources.DEVICE_WAIT_RULE_S = 0.567 is kept and labelled superseded; it "
                    "is write-only (one reference, its own declaration) and is not what these "
                    "arms pay"))


def device_delivery_rule() -> Dict[str, Any]:
    """The device-side rule, recorded in every output so a cell says what produced it."""
    return dict(
        device_latency_source=DEVICE_LATENCY_SOURCE,
        device_wait_s=DEVICE_WAIT_S,
        superseded_source=(DEVICE_LATENCY_SOURCE == "trace"),
        meaning=_MEANING.get(DEVICE_LATENCY_SOURCE,
                             "measured: a MEASURED per-question device latency table"),
        excluded=("D155 (1): the LH-REQ device answer latencies, end-to-end median 3.354 s of "
                  "which 3.296 s is TTFT (D155a corrects the earlier 6.651 s, which had added "
                  "TTFT to an end-to-end figure that already contained it), are the COLD RE-SEND "
                  "path, which D61 (b) classifies as an API artifact and not the device "
                  "baseline. Not used here."),
        answer_length=("D146 (1) / P20: a robot answer is 2 OUTPUT TOKENS (completion_tokens == 2 "
                       "on all 97 measured questions), so the 512-token answer cap is not the "
                       "device's latency lever and a 0.270 s completion is almost entirely "
                       "prefill plus fixed overhead."),
        cascade_device_wait=cascade_device_wait(),
        source="D155 (3) amending D152 (1), user decision 2026-11-20")


def _is_assistive(lo: "Loaded", opp: str, outcome: Optional[Dict[str, Any]] = None) -> bool:
    """Is this opportunity single-shot? From the DEVICE ANSWER's own kind where available.

    The partition is EXHAUSTIVE on purpose. The bug this replaces was a fall-through: `attainment`
    put every non-monitor outcome in the robot pool with an `else`, so single-shot questions were
    scored as robot questions at the 5 s robot deadline instead of 2 s. That did not crash. It
    silently inflated the robot pool (24 robot questions and 356 SS at n=16, so the pool read 380)
    and corrupted both the headline on-time fraction and D82's 20-question minimum. A loud failure
    would have been better, which is why this one is loud.

    TWO CALLERS PASS A SHIM WITH NO `device_answers` AT ALL: `policy/audit/leaderboard.py` and
    `policy/audit/robot_denominators.py` build an object carrying only `outcomes`. They predate
    single-shot and raising on them would break committed audit tooling, so the device id prefix is
    used instead and the fallback is not silent: `attainment` records which rule classified the
    run, so a three-type run scored through a shim cannot quietly look like a robot-only one.
    """
    answers = getattr(lo, "device_answers", None)
    if answers is None:
        did = (outcome or {}).get("device_id") or ""
        return bool(did.startswith(ASSISTIVE_DEVICE_PREFIX))
    dev = answers.get(opp)
    if dev is None:
        raise ScoringRefused("no device answer recorded for opportunity %r, so it cannot be "
                             "classified as robot or single-shot" % (opp,))
    k = dev.get("kind")
    if k == "assistive":
        return True
    if k == "recall":
        return False
    raise ScoringRefused("device answer for opportunity %r carries kind %r, which is neither "
                         "'recall' nor 'assistive'; refusing to guess which pool it belongs to"
                         % (opp, k))
N_BOOT = 2000
N_BOOT_AP = 1000                        # D103 (e): raised from 200. AP is recomputed per resample
AP_HORIZONS = (0.0, 0.5, 1.0, 1.5)

# D103 (f): THE PRIMARY FAMILY, fixed in advance. No multiplicity correction is applied and none
# is claimed; what D103 fixes is WHICH comparisons are primary, so the family cannot be chosen
# after seeing a result. Everything outside it is EXPLORATORY and is labelled so in every output.
PRIMARY_MEMORY = "tight"
PRIMARY_RATIO = "50:50"
PRIMARY_MODE = "A"                      # push-all
PRIMARY_FAMILY_RULE = (
    "D103 (f): the PRIMARY family is policy vs each of the 7 GPU baselines at the two break "
    "sizes, tight memory, 50:50, push-all (block 1). Every other comparison is EXPLORATORY. No "
    "multiplicity correction is applied and none is claimed; the intervals are descriptive "
    "(D64). The break sizes are an INPUT to the labelling: they come from the pilot (block 0) "
    "and are passed in, so the family is fixed before the comparison is read.")
EXPLORATORY = "EXPLORATORY"
PRIMARY = "PRIMARY"
POLICY_ARM = "policy-core"
# The seven non-policy arms of the round-1 arm list (D65 as corrected by D90), copied from
# `live2/arms.py::ARM_NAMES` rather than imported, so the scorer pulls in no coordinator code.
# `device-only` is among the seven although D65 scores it from the recordings with no run at all;
# see the report's open issues for the one reading of "GPU baselines" this leaves open.
GPU_BASELINES = ("device-only", "always-cloud-fcfs", "edf", "edf-piece1024", "edf-piece2048",
                 "utility-per-cost", "b9")


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



def refused_request_ids(reqs: Sequence[Dict[str, Any]]) -> set:
    """Requests that NEVER DELIVERED AN ANSWER, so no cloud answer of theirs may stand.

    D175 (1) (user ruling 2026-11-22): under replacement semantics (D165 B) only a DELIVERED cloud
    answer replaces the device's, so a REFUSED request leaves the device answer standing. D144 (2)
    already nulled the delivery of any NON-200 response; the hole D175 closes is the request that
    never got a status at all.

    THE HOLE, MEASURED. The over-context request at always-cloud-fcfs seed 7 came back with
    http_status None, prompt_tokens None and output_tokens None, and the coordinator had already
    settled it as an on-time cloud answer with the 'X' no-letter sentinel, delivered 17 ms after
    submission for a 38,821-token prefill. `http_status is not None and != 200` is False for it,
    so the D144 pass skipped it and the scorer's `cloud_stands` then let a refusal REPLACE a
    device answer.

    WHY THE TEST IS NOT THE LETTER. 'X' is StudyR1's "no A-E found in the answer" sentinel, which
    a genuinely delivered answer can also produce, so treating 'X' as refusal would discard real
    cloud answers and silently improve every arm that generates poor text. The test is whether the
    REQUEST completed: a non-200 status, or no status at all with no prompt and no output tokens.

    WHY THE SECOND CLAUSE IS NARROW. Across the 49 committed rq30 cells there are 441,023 requests
    with status 200 and tokens, 3,568 with status 200 and no token fields (kept: they answered),
    700 with no status and no tokens (refused: caught here), and 82 non-200 (already caught). The
    3,568 are the reason the clause requires BOTH token fields to be absent rather than keying on
    the status alone.
    """
    out = set()
    for r in reqs:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    out.add(r.get("request_id"))
            except (TypeError, ValueError):
                out.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            out.add(r.get("request_id"))
    return out


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
    for name in ("requests.jsonl", "request.jsonl"):        # live2 writes the singular name
        if (run_dir / name).exists():
            reqs = [json.loads(l) for l in open(run_dir / name)]
            break
    # D144 (user ruling 2026-11-20): any NON-200 response is a MISS. A refused request (e.g. HTTP 400 over-context) was
    # settled by the pre-fix coordinator as an on-time cloud answer with letter "X"; strip such cloud deliveries here so
    # every downstream check (_within, robot_value, assistive scoring) sees the device answer standing and a miss.
    failed = refused_request_ids(reqs)
    if failed:
        for o in out.values():
            cp = o.get("cloud_payload") or {}
            if cp.get("request_id") in failed:
                o["t_delivered"] = None
                o["cloud_payload"] = None
                o["d144_failed_request"] = True
    # D226 (3): the refusal test above reads the request log; if the request log DROPPED rows
    # (observed in the 11-21..11-23 request.jsonl writes), a refused request whose row is absent is
    # never caught, and a refusal then silently REPLACES a device answer. The outcome record carries
    # no refusal signal of its own (http_status and the token fields live only in the request log),
    # so a refusal cannot be recovered from outcomes.jsonl. The only choice that cannot silently
    # mis-score is to FAIL LOUD: a cloud answer that still stands (t_delivered set) but whose request
    # id is absent from the request log is UNVERIFIABLE, and the scorer refuses rather than trust it.
    # With a complete request log this guard never fires (every delivered answer has its row).
    present_ids = {r.get("request_id") for r in reqs}
    unverifiable = sorted(
        cp.get("request_id")
        for o in out.values()
        for cp in (o.get("cloud_payload") or {},)
        if o.get("t_delivered") is not None and cp.get("request_id") not in present_ids)
    if unverifiable:
        raise ScoringRefused(
            "D226: %d delivered cloud answer(s) in %s have request ids absent from the request "
            "log (%d rows); their refusal status is unverifiable and keeping them risks a silent "
            "mis-score. First few: %s" % (len(unverifiable), run_dir.name, len(reqs),
                                          unverifiable[:5]))
    # ---- D146: COMPLETION DELIVERY, and it is the DEFAULT from 2026-11-20.
    # A robot or single-shot answer counts as delivered when generation COMPLETES, prefill plus
    # decode; a dashcam Yes/No may stay at first token. The committed `t_delivered` is first-token
    # based: in all 40 frozen-grid runs `outcomes.t_cloud_done` equals the request log's
    # `t_first_token` exactly, and `t_delivered` is that plus a per-row forward delay. So the
    # completion stamp is the request's `t_done` plus the SAME per-row delay, taken from the data
    # rather than assumed to be the 0.0222 s constant it turns out to be.
    #
    # It is rewritten HERE, beside the D144 pass that nulls a failed request's delivery, for the
    # same reason: `_within`, `robot_value` and the assistive scoring all read `t_delivered`, so one
    # rewrite reaches every downstream check and none of them has to learn a new field.
    #
    # Why it matters rather than merely shifting a number: decode time scales with CONTEXT LENGTH.
    # Pooled over the 16-device cells, recall decode is 0.072 s below 1,000 prompt tokens and
    # 1.197 s above 15,000, for the same two output tokens. The first-token stamp hid that
    # entirely, so an arm that sends a whole history was paying a cost no metric could see.
    if DELIVERY == "completion":
        done = {r["opportunity_id"]: float(r["t_done"]) for r in reqs
                if r.get("opportunity_id") and r.get("t_done") is not None}
        for oid, o in out.items():
            # `out` is keyed by opportunity_id (line 223), so the KEY is the join and is used
            # rather than a field inside the row, which need not be present.
            if o.get("kind") != "recall" or o.get("t_delivered") is None:
                continue
            if o.get("t_cloud_done") is None or oid not in done:
                continue
            o["t_delivered_first_token"] = o["t_delivered"]
            o["t_delivered"] = (done[oid]
                                + (float(o["t_delivered"]) - float(o["t_cloud_done"])))
            o["delivery_rule"] = "completion"

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


def is_measured_run(run_meta: Dict[str, Any], cal: Dict[str, Any]) -> bool:
    """A run is a MEASUREMENT only if a real server produced it and the map is FINAL."""
    return (run_meta.get("server_kind") not in NON_MEASUREMENT_SERVERS
            and cal.get("label") == "FINAL")


def check_frame_bytes_source(meta: Dict[str, Any], run_meta: Dict[str, Any],
                             cal: Dict[str, Any]) -> None:
    """D103 (h): the E10a median frame size is for FLASH TESTS ONLY.

    A measured run must charge per-frame bytes from the Part-2 encode manifest (D91). The trace
    records which source it used in `frame_bytes_source`; the scorer refuses a measured run whose
    source is not the manifest, rather than reporting uplink timings computed from a median that
    stands in for a distribution.
    """
    if not is_measured_run(run_meta, cal):
        return
    src = str(meta.get("frame_bytes_source") or "")
    if not src.startswith("Part-2 manifest"):
        raise ScoringRefused(
            "SCORING REFUSED: this is a MEASURED run but its trace charged frame bytes from "
            f"{src!r}. D103 (h) allows the committed E10a median for flash tests ONLY; a "
            "measured run must read per-frame bytes from the Part-2 JPEG encode manifest (D91). "
            "Regenerate the trace with --frame-manifest.")


def check_calibration(cal: Dict[str, Any], run_meta: Dict[str, Any]) -> None:
    """D86 / ruling 10-11: an INTERIM map may score a fake / stub run and nothing else.

    D105 adds a second condition on a FINAL map: it must carry its 5-fold cross-fitting BY CLIP,
    because each clip is scored with the map from the folds that exclude it and the scorer takes
    the fold assignment FROM THE FILE. A FINAL map with no fold assignment cannot be used
    out-of-fold, so it is refused rather than applied pooled.
    """
    is_stub = run_meta.get("server_kind") in NON_MEASUREMENT_SERVERS
    if cal["label"] == "FINAL":
        folds = cal.get("folds")
        if not folds or not folds.get("assignment") or not folds.get("maps"):
            raise ScoringRefused(
                "SCORING REFUSED: the calibration map declares label FINAL but carries no fold "
                "assignment and per-fold maps. D105 requires both maps to be Platt-fitted with "
                "5-fold cross-fitting BY CLIP (D6) and each clip to be scored with the map from "
                "the folds that EXCLUDE it, with the fold assignment taken from this file. A "
                f"pooled FINAL map would score every clip in-fold. Map: {cal['path']} sha256 "
                f"{cal['sha256'][:16]}")
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
    # D142 item 3: single-shot, scored at its OWN 2 s deadline and kept out of the robot pool.
    ss_pool_n: int = 0
    ss_pool_on_time: int = 0
    ss_pool_fraction: Optional[float] = None
    ss_per_device: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ss_classified_by: Optional[str] = None
    capacity_met: bool = False


def _within(o: Dict[str, Any], L: float) -> bool:
    td = o.get("t_delivered")
    return td is not None and (float(td) - float(o["t_opportunity"])) <= L + 1e-9


def attainment(lo: Loaded, L_dash: float = DASH_L_S, p_dash: float = DASH_P,
               L_rob: float = ROB_L_S, p_rob: float = ROB_P,
               min_dash: int = DASH_MIN_INSTANTS,
               min_rob: int = ROB_MIN_QUESTIONS,
               L_ss: float = SS_L_S) -> Attainment:
    a = Attainment()
    by_dev: Dict[str, List[Dict[str, Any]]] = {}
    rob: List[Dict[str, Any]] = []
    ss: List[Dict[str, Any]] = []
    for opp, o in lo.outcomes.items():
        if o["kind"] == "monitor":
            by_dev.setdefault(o["device_id"], []).append(o)
        elif _is_assistive(lo, opp, o):
            ss.append(o)
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
    # D142 item 3: single-shot on-time at ITS OWN deadline, reported beside the other two and
    # NOT folded into capacity. D64's capacity definition is dashcam-all-meet AND robot-pool-meets;
    # adding a third conjunct would change a committed definition, which is the user's call.
    a.ss_classified_by = ("device answer kind" if getattr(lo, "device_answers", None) is not None
                          else "DEVICE ID PREFIX fallback: this run was scored through an object "
                               "carrying no device answers, so single-shot was identified by the "
                               "%r device-id prefix rather than by the authoritative field"
                               % (ASSISTIVE_DEVICE_PREFIX,))
    a.ss_pool_n = len(ss)
    a.ss_pool_on_time = sum(1 for o in ss if _within(o, L_ss))
    if a.ss_pool_n:
        a.ss_pool_fraction = round(a.ss_pool_on_time / a.ss_pool_n, 6)
    ssdev: Dict[str, List[Dict[str, Any]]] = {}
    for o in ss:
        ssdev.setdefault(o["device_id"], []).append(o)
    for d, os_ in sorted(ssdev.items()):
        n = len(os_)
        k = sum(1 for o in os_ if _within(o, L_ss))
        a.ss_per_device[d] = dict(n_questions=n, on_time=k,
                                  fraction=(round(k / n, 6) if n else None))

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
    """The standing answer under the ANY-TIME rule (D152 (1)): the device always stands in.

    D155 (3) does not change this function. The any-time standing answer stays exactly as
    committed, because D155 requires it to be REPORTED BESIDE the new rule rather than replaced,
    and a quantity that is re-derived in two places drifts. `_standing_by_deadline` is the new
    rule and is a separate function for the same reason.
    """
    if _within(o, L):
        return dict(source="cloud", payload=o.get("cloud_payload") or {})
    return dict(source="device", payload=dev)


def _standing_by_deadline(o: Dict[str, Any], dev: Dict[str, Any], L: float) -> Dict[str, Any]:
    """D155 (3): the cloud's answer if it arrived in time, else the DEVICE's IF IT ARRIVED IN TIME.

    The third branch is the whole amendment: when neither side made the deadline there is NO
    answer by the deadline, so the opportunity is a miss and not a device credit. Under D152 (1)
    that third branch did not exist.
    """
    if _within(o, L):
        return dict(source="cloud", payload=o.get("cloud_payload") or {})
    if device_within(o, dev, L):
        return dict(source="device", payload=dev)
    return dict(source="none", payload=None)


def robot_value(lo: Loaded, L_rob: float = ROB_L_S) -> Dict[str, Any]:
    """Standing-answer accuracy, the cloud's own accuracy, and the D81 WARM / COLD split."""
    path_by_opp = {r.get("opportunity_id"): r.get("cache_path")
                   for r in lo.requests if r.get("opportunity_id")}
    rows = []
    for opp, o in sorted(lo.outcomes.items()):
        if o["kind"] != "recall":
            continue
        # D142 item 3: single-shot answers reuse this record kind but carry no gold letter and are
        # not MCQ, so they are scored by `assistive_value` instead. Reading dev["gold_letter"] on
        # one raised KeyError and blocked the score of every three-type run.
        if _is_assistive(lo, opp):
            continue
        dev = lo.device_answers.get(opp)
        if dev is None:
            raise ScoringRefused(f"no device answer recorded for recall opportunity {opp!r}")
        st = _standing(o, dev, L_rob)
        stbd = _standing_by_deadline(o, dev, L_rob)
        gold = dev["gold_letter"]
        cl = (o.get("cloud_payload") or {}).get("cloud_letter")
        # D155 (3): the by-deadline row. `source_by_deadline == "none"` is a DEFINITE miss, not an
        # unknown, so it enters the denominator as a False and never as a None. A None here would
        # silently shrink the denominator and make the amendment look like it changed nothing.
        if stbd["source"] == "none":
            sc_bd: Optional[bool] = False
        elif stbd["source"] == "device":
            sc_bd = bool(dev["device_correct"])
        else:
            sc_bd = None if cl is None else (cl == gold)
        rows.append(dict(opportunity_id=opp, device_id=o["device_id"],
                         question_id=o.get("question_id"), gold=gold,
                         source=st["source"], device_correct=bool(dev["device_correct"]),
                         cloud_letter=cl,
                         cloud_correct=(None if cl is None else (cl == gold)),
                         standing_correct=(bool(dev["device_correct"])
                                           if st["source"] == "device"
                                           else (None if cl is None else cl == gold)),
                         source_by_deadline=stbd["source"],
                         device_latency_s=device_latency_s(dev),
                         device_on_time=device_within(o, dev, L_rob),
                         standing_correct_by_deadline=sc_bd,
                         cache_path=path_by_opp.get(opp)))
    def acc(sel) -> Optional[float]:
        v = [r for r in rows if sel(r) and r["standing_correct"] is not None]
        return round(sum(1 for r in v if r["standing_correct"]) / len(v), 6) if v else None

    def acc_bd(sel) -> Optional[float]:
        v = [r for r in rows if sel(r) and r["standing_correct_by_deadline"] is not None]
        return (round(sum(1 for r in v if r["standing_correct_by_deadline"]) / len(v), 6)
                if v else None)
    served = [r for r in rows if r["source"] == "cloud"]
    cloud_known = [r for r in served if r["cloud_correct"] is not None]
    out = dict(
        n=len(rows), n_cloud_standing=len(served), n_device_standing=len(rows) - len(served),
        standing_accuracy=acc(lambda r: True),
        standing_accuracy_n=sum(1 for r in rows if r["standing_correct"] is not None),
        # D155 (3): the by-deadline rule, kept in its OWN fields beside the any-time ones above.
        standing_accuracy_by_deadline=acc_bd(lambda r: True),
        standing_accuracy_by_deadline_n=sum(
            1 for r in rows if r["standing_correct_by_deadline"] is not None),
        n_device_standing_by_deadline=sum(1 for r in rows
                                          if r["source_by_deadline"] == "device"),
        n_no_answer_by_deadline=sum(1 for r in rows if r["source_by_deadline"] == "none"),
        device_answers_late=sum(1 for r in rows if not r["device_on_time"]),
        device_latency_s_range=([round(min(r["device_latency_s"] for r in rows), 6),
                                 round(max(r["device_latency_s"] for r in rows), 6)]
                                if rows else None),
        device_delivery_rule=device_delivery_rule(),
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


def map_for(cal: Dict[str, Any], key: str, clip: str) -> Dict[str, float]:
    """The map to score ONE CLIP with (D105): out-of-fold when the file carries folds.

    `folds.maps[k]` is the map fitted with fold k held out, and the clip's own fold comes from
    the file's assignment, so a clip is never scored with a map its own data trained. A file with
    no folds is the INTERIM case, which D86 confines to flash builds and tests; there the single
    pooled map is used and the output says so.
    """
    folds = cal.get("folds")
    if not folds:
        return cal["maps"][key]
    k = folds["assignment"].get(str(clip))
    if k is None:
        raise ScoringRefused(
            f"the calibration file places no fold on clip {clip!r}, so it cannot be scored "
            f"out-of-fold (D105). The scorer takes the fold assignment FROM THE FILE and never "
            f"invents one, and it does not fall back to the pooled map for a measured run.")
    m = (folds["maps"].get(str(k)) or {}).get(key)
    if m is None:
        raise ScoringRefused(
            f"the calibration file has no {key!r} map for fold {k!r}, which clip {clip!r} is "
            f"assigned to (D105)")
    return m


def calibration_use(cal: Dict[str, Any]) -> Dict[str, Any]:
    """What the output header says about HOW the maps were applied (D86, D105)."""
    folds = cal.get("folds")
    return dict(path=cal["path"], sha256=cal["sha256"], label=cal["label"],
                note=cal.get("note"),
                fold_fitted=bool(folds),
                n_folds=(folds.get("n_folds") if folds else None),
                folds_by=(folds.get("by") if folds else None),
                n_clips_assigned=(len(folds["assignment"]) if folds else 0),
                application=("D105: each clip is scored with the map from the folds that EXCLUDE "
                             "it, the fold assignment taken from the calibration file"
                             if folds else
                             "a single pooled map, with no cross-fitting: INTERIM only, flash "
                             "builds and tests (D86)"))


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
        # D105: the out-of-fold maps for THIS clip.
        dm, cm = map_for(cal, device_map_key, clip), map_for(cal, cloud_map_key, clip)
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
        dm = map_for(cal, "device_4b_orin", clip)       # D105, out of fold
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
                rule=("D97: included only if the robot "
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
def history_preload(lo: Loaded) -> Dict[str, Any]:
    """D101: what the cloud already held at t = 0, and the join that put it there.

    The preload is NOT an opportunity and is never scored: it changes which questions exist and
    what a first answer has to rebuild. The scorer reports it so that a run's robot pool can be
    read next to the join that produced it, and refuses a run whose preloads do not match the
    trace, because a different holding at t = 0 is a different experiment (D96 (2) coverage).
    """
    pre = [r for r in lo.records if r["kind"] == "history_preload"]
    tok = sorted(int(r["est_tokens"]) for r in pre)
    join = lo.meta.get("robot_join") or {}
    offs = sorted(float(v["join_offset_s"]) for v in join.values())
    n_run = lo.run_meta.get("n_history_preload")
    if n_run is not None and int(n_run) != len(pre):
        raise ScoringRefused(
            f"the run presented {n_run} history_preload events and the trace holds {len(pre)}; "
            f"a different holding at t = 0 is a different experiment (D101), so this run is not "
            f"comparable with the others")
    return dict(
        n_preloads=len(pre), n_robots_with_join=len(join),
        all_at_t_zero=all(float(r["t"]) == 0.0 for r in pre),
        uplink_charged=False,
        est_tokens=dict(min=(tok[0] if tok else None),
                        median=(tok[len(tok) // 2] if tok else None),
                        max=(tok[-1] if tok else None), total=sum(tok)),
        join_offset_s=dict(min=(round(offs[0], 3) if offs else None),
                           median=(round(offs[len(offs) // 2], 3) if offs else None),
                           max=(round(offs[-1], 3) if offs else None)),
        join_frac_max=lo.meta.get("robot_join_frac_max"),
        rule=lo.meta.get("robot_join_rule"),
        note=("D101: questions before a join point are not emitted and not counted, so the "
              "robot pool of a run under D101 is NOT the pool the pre-D101 traces produced; the "
              "D97 entry points were recomputed from traces for this reason."))


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
        # D99: the decision period is the same 100 ms for every arm and is a RECORDED setting,
        # separate from the horizon H; the coordinator's own latency stays in the results (M4).
        decision_period=dict(
            period_ms=lo.run_meta.get("decision_period_ms"),
            full_eval_cap_K=lo.run_meta.get("decision_full_eval_cap_k"),
            rule=("D99: one fixed 100-ms decision period for every arm, events batched per "
                  "period, separate from H; a cap K on full DeltaJ evaluations per period is "
                  "reported as a setting if one was used; the coordinator's own latency is "
                  "counted and reported, never netted out"),
            recorded=(lo.run_meta.get("decision_period_ms") is not None)),
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
    check_frame_bytes_source(lo.meta, lo.run_meta, cal)
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
                # D146: the delivery rule this score was computed under, recorded HERE so every
                # cell carries it. The H100 found that a driver-scored cell.json had no such
                # string anywhere, so from the record alone a reader could not tell whether a
                # post-D146 cell used completion or first token. frozen_headline wrote the rule
                # into its own output; score_run did not, and the claim that "every output carries
                # it" was therefore wrong for the production scorer.
                delivery_rule=DELIVERY,
                on_time_rule=("an answer is delivered at COMPLETION, prefill plus decode (D146, "
                              "the default from 2026-11-20); a dashcam Yes/No stays at first token"
                              if DELIVERY == "completion" else
                              "an answer is delivered at FIRST TOKEN (the pre-D146 rule, selected "
                              "by LIVE2_DELIVERY=first_token)"),
                seed=lo.meta["seed"], n_devices=lo.meta["n_devices"], ratio=lo.meta["ratio"],
                run_s=lo.meta["run_s"], mode=lo.run_meta.get("mode"),
                server_kind=lo.run_meta.get("server_kind"),
                memory=(lo.run_meta.get("memory") or lo.run_meta.get("memory_setting")
                        or lo.run_meta.get("kv_memory") or lo.run_meta.get("memory_label")),
                is_measurement=is_measured_run(lo.run_meta, cal),
                frame_bytes_source=lo.meta.get("frame_bytes_source"),
                calibration=calibration_use(cal),
                history_preload=history_preload(lo),
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
        # D152: the robot headline is CORRECT ANSWERS DELIVERED, the cloud's answer when it
        # arrives on time and the device's otherwise, scored on the representation actually sent.
        # robot_value already computes it as `standing_accuracy`; it is surfaced HERE as the
        # headline, with on time reported beside it rather than as the metric.
        #
        # Why it is the headline, in one measured line: at a 3 s deadline post-fix, hybrid-F
        # delivered 2.3x b7's on-time rate and no more correct answers, because 18 of its 47
        # on-time answers were sent as RECENT, which is right about 11 percent of the time.
        # On time counts answers that arrive; this counts answers that are right.
        # D155 (3) AMENDS D152 (1): the headline metric is now
        # `correct_answers_delivered_by_deadline`, in which a DEVICE answer counts only if it
        # ARRIVES WITHIN THE DEADLINE. `correct_answers_delivered_any_time`, the D152 (1)
        # behaviour that credits a device answer whenever it lands, is reported BESIDE it in its
        # own field. The two must never be mixed in one column or one sentence, so there is no
        # field here called `correct_answers_delivered` any more: a reader cannot pick up the
        # ambiguous name by accident.
        base["robot_headline"] = dict(
            metric="correct_answers_delivered_by_deadline",
            definition=("D155 (3): the cloud's answer when it is delivered within the deadline, "
                        "otherwise the DEVICE's answer IF THE DEVICE'S ANSWER ALSO ARRIVES "
                        "WITHIN THE DEADLINE, otherwise no answer and the question is a miss; "
                        "each answer scored on the representation actually sent"),
            correct_answers_delivered_by_deadline=rv.get("standing_accuracy_by_deadline"),
            n_by_deadline=rv.get("standing_accuracy_by_deadline_n"),
            beside_it_any_time=dict(
                metric="correct_answers_delivered_any_time",
                definition=("D152 (1), reported beside the headline and never mixed with it: the "
                            "cloud's answer when it is delivered within the deadline, otherwise "
                            "the device's answer REGARDLESS OF WHEN IT LANDS"),
                correct_answers_delivered_any_time=rv.get("standing_accuracy"),
                n=rv.get("standing_accuracy_n")),
            device_side=dict(
                rule=rv.get("device_delivery_rule"),
                device_latency_s_range=rv.get("device_latency_s_range"),
                device_answers_late=rv.get("device_answers_late"),
                n_device_standing_any_time=rv.get("n_device_standing"),
                n_device_standing_by_deadline=rv.get("n_device_standing_by_deadline"),
                n_no_answer_by_deadline=rv.get("n_no_answer_by_deadline")),
            amendment="D155 (3) amends D152 (1), user decision 2026-11-20",
            on_time_beside_it=dict(
                robot_pool_on_time=sweep[0].get("robot_pool_on_time") if sweep else None,
                robot_pool_n=sweep[0].get("robot_pool_n") if sweep else None,
                robot_pool_fraction=sweep[0].get("robot_pool_fraction") if sweep else None,
                note="D152: deficit counters stay on observable on time; the HEADLINE does not"),
            device_only_accuracy=rv.get("device_only_accuracy"),
            cloud_accuracy_on_served=rv.get("cloud_accuracy_on_served"),
            source="D152 (user decision 2026-11-20)")
        base["dashcam_value"] = dashcam_value(lo, cal, L_dash_grid[0])
        av = assistive_value(lo)
        base["assistive_rows"] = av.pop("rows")
        base["assistive_value"] = av
        base["device_only"] = device_only_value(lo, cal)
    return base


def assistive_value(lo: Loaded, L_ss: float = SS_L_S) -> Dict[str, Any]:
    """Single-shot on-time and accuracy, on StudySS2's OWN metrics (D142 item 3).

    The standing answer follows the same rule as the robot pool: the cloud's answer if it arrived
    within the deadline, otherwise the device's own. Accuracy is then reported per dataset, because
    the two datasets do not share a metric and averaging them would invent a number:

      * refspatial   `point_accuracy`, the fraction of predicted points inside the ground-truth mask
      * realworldqa  `exact_match` after the benchmark's own normalisation

    THE CLOUD SIDE IS NOT SCORED HERE. The live harness records the cloud's answer text, and
    scoring it needs each benchmark's own scorer (the mask for RefSpatial, the normaliser for
    RealWorldQA), which lives in `experiments/casestudy/ss2_kit.py` and is not importable from a
    live2 score. So `standing_accuracy` below is the DEVICE accuracy over opportunities whose
    standing answer is the device's, and it is `None` for those served by the cloud rather than
    counted as wrong. The count of each is reported, so a reader can see how much of the pool is
    unscored instead of inferring it. Closing this needs the SS2 scorers wired into the live
    scorer, and it is named rather than papered over.
    """
    rows = []
    for opp, o in sorted(lo.outcomes.items()):
        if o["kind"] != "recall" or not _is_assistive(lo, opp):
            continue
        dev = lo.device_answers[opp]
        on_time = _within(o, L_ss)
        qid = o.get("question_id") or dev.get("question_id") or ""
        dataset = qid.split("/")[0] if "/" in qid else None
        sc = dev.get("device_score") or {}
        metric = "point_accuracy" if dataset == "refspatial" else "exact_match"
        dev_score = float(sc[metric]) if metric in sc else None
        # D155 (3) FOR SINGLE-SHOT. Previously the device answer was credited whenever the cloud
        # missed, with no check that it ARRIVED in time. It frequently does not: refspatial device
        # completion is p50 1.9947 s against a 2.0 s deadline and 126 of 1,042 single-shot
        # questions (45.5 percent of refspatial) exceed it. Both readings are reported, because
        # D155 (3) requires the any-time figure BESIDE the new rule, not replaced by it.
        stbd = _standing_by_deadline(o, dev, L_ss)
        dev_lat = device_latency_any_type_s(o, dev)
        rows.append(dict(opportunity_id=opp, device_id=o["device_id"], question_id=qid,
                         dataset=dataset, on_time=bool(on_time),
                         source=("cloud" if on_time else "device"),
                         source_by_deadline=stbd["source"],
                         device_latency_s=dev_lat,
                         device_within_deadline=bool(device_within(o, dev, L_ss)),
                         metric=metric, device_score=dev_score,
                         standing_score=(None if on_time else dev_score),
                         standing_score_by_deadline=(
                             None if stbd["source"] != "device" else dev_score)))
    def agg(sel):
        v = [r for r in rows if sel(r) and r["standing_score"] is not None]
        return dict(n=len(v), mean=(round(sum(r["standing_score"] for r in v) / len(v), 6)
                                    if v else None))
    datasets = sorted({r["dataset"] for r in rows if r["dataset"]})
    return dict(
        n=len(rows),
        deadline_s=L_ss,
        on_time=sum(1 for r in rows if r["on_time"]),
        on_time_fraction=(round(sum(1 for r in rows if r["on_time"]) / len(rows), 6)
                          if rows else None),
        n_cloud_standing=sum(1 for r in rows if r["source"] == "cloud"),
        n_device_standing=sum(1 for r in rows if r["source"] == "device"),
        # D155 (3) for single-shot, reported BESIDE the any-time figures above rather than
        # replacing them. `n_no_answer_by_deadline` is the branch that did not exist before: the
        # cloud missed AND the device's own answer was late, so there is no answer by the deadline
        # and the opportunity is a miss, not a device credit.
        by_deadline=dict(
            n_cloud_standing=sum(1 for r in rows if r["source_by_deadline"] == "cloud"),
            n_device_standing=sum(1 for r in rows if r["source_by_deadline"] == "device"),
            n_no_answer_by_deadline=sum(1 for r in rows if r["source_by_deadline"] == "none"),
            n_device_late=sum(1 for r in rows
                              if not r["on_time"] and not r["device_within_deadline"]),
            n_device_latency_unknown=sum(1 for r in rows if r["device_latency_s"] is None),
            device_accuracy_by_dataset={
                d: dict(n=sum(1 for r in rows if r["dataset"] == d
                              and r["standing_score_by_deadline"] is not None),
                        mean=(round(sum(r["standing_score_by_deadline"] for r in rows
                                        if r["dataset"] == d
                                        and r["standing_score_by_deadline"] is not None)
                                    / max(sum(1 for r in rows if r["dataset"] == d
                                              and r["standing_score_by_deadline"] is not None), 1),
                                    6)
                              if any(r["dataset"] == d
                                     and r["standing_score_by_deadline"] is not None
                                     for r in rows) else None))
                for d in datasets},
            rule=("a device answer counts only if it arrived by the 2.0 s single-shot deadline. "
                  "refspatial device completion is p50 1.9947 s against that deadline and 126 of "
                  "1,042 measured single-shot questions exceed it, all of them refspatial "
                  "(45.5 percent of that dataset); realworldqa has none.")),
        device_accuracy_by_dataset={d: agg(lambda r, d=d: r["dataset"] == d) for d in datasets},
        device_accuracy_all_opportunities={
            d: dict(n=sum(1 for r in rows if r["dataset"] == d and r["device_score"] is not None),
                    mean=(round(sum(r["device_score"] for r in rows
                                    if r["dataset"] == d and r["device_score"] is not None)
                                / max(sum(1 for r in rows if r["dataset"] == d
                                          and r["device_score"] is not None), 1), 6)
                          if any(r["dataset"] == d and r["device_score"] is not None
                                 for r in rows) else None))
            for d in datasets},
        metrics_not_comparable=("refspatial point_accuracy and realworldqa exact_match are "
                                "DIFFERENT metrics and are never averaged together here"),
        cloud_side_unscored=("the cloud's SS answers are recorded but NOT scored in this function; "
                             "scoring them needs each benchmark's own scorer from "
                             "experiments/casestudy/ss2_kit.py. standing_accuracy over "
                             "cloud-served opportunities is therefore absent, not zero."),
        rows=rows)


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


def classify_family(policy: Dict[str, Any], baseline: Dict[str, Any],
                    break_sizes: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """D103 (f): is this comparison in the PRIMARY family, or is it EXPLORATORY?

    The family is fixed in advance: policy vs each of the 7 GPU baselines at the two break
    sizes, tight memory, 50:50, push-all (block 1). `break_sizes` is an INPUT, taken from the
    pilot, so the family cannot be chosen after the comparison is read; with no break sizes
    given, nothing can be PRIMARY and the result says why.

    Anything the run header does not record cannot be claimed, so a missing memory setting makes
    the comparison EXPLORATORY and names the missing field. The labelling never changes a
    number: it only says which family the comparison belongs to.
    """
    mem = None
    for k in ("memory", "memory_setting", "kv_memory", "memory_label"):
        if policy.get(k) is not None or (policy.get("run_meta") or {}).get(k) is not None:
            mem = policy.get(k) or (policy.get("run_meta") or {}).get(k)
            break
    reasons: List[str] = []
    if policy.get("arm") != POLICY_ARM:
        reasons.append(f"the first arm is {policy.get('arm')!r}, not {POLICY_ARM!r}")
    if baseline.get("arm") not in GPU_BASELINES:
        reasons.append(f"{baseline.get('arm')!r} is not one of the 7 round-1 baselines")
    if policy.get("n_devices") != baseline.get("n_devices"):
        reasons.append("the two arms are at different fleet sizes")
    if not break_sizes:
        reasons.append("no break sizes were supplied, so no size can be claimed PRIMARY")
    elif int(policy.get("n_devices") or -1) not in [int(x) for x in break_sizes]:
        reasons.append(f"fleet size {policy.get('n_devices')} is not one of the break sizes "
                       f"{list(break_sizes)}")
    if policy.get("ratio") != PRIMARY_RATIO:
        reasons.append(f"ratio {policy.get('ratio')!r} is not {PRIMARY_RATIO}")
    if policy.get("mode") != PRIMARY_MODE:
        reasons.append(f"mode {policy.get('mode')!r} is not push-all ({PRIMARY_MODE})")
    if mem is None:
        reasons.append("the run header records no memory setting, so tight memory cannot be "
                       "confirmed (looked for memory / memory_setting / kv_memory / "
                       "memory_label)")
    elif str(mem) != PRIMARY_MEMORY:
        reasons.append(f"memory setting {mem!r} is not {PRIMARY_MEMORY!r}")
    return dict(family=(PRIMARY if not reasons else EXPLORATORY),
                why=("every condition of the pre-registered primary family holds"
                     if not reasons else "; ".join(reasons)),
                break_sizes=(list(break_sizes) if break_sizes else None),
                rule=PRIMARY_FAMILY_RULE)


def compare(policy: Dict[str, Any], baseline: Dict[str, Any],
            setting_index: int = 0, seed: int = 0,
            break_sizes: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Paired policy-minus-baseline differences within one run (D64: intervals, no margins)."""
    pc = policy["sweep"][setting_index]
    bc = baseline["sweep"][setting_index]
    dash_units = sorted(set(pc["dashcam_per_device"]) & set(bc["dashcam_per_device"]))
    out: Dict[str, Any] = dict(policy=policy["arm"], baseline=baseline["arm"],
                               setting={k: pc[k] for k in ("L_dash", "p_dash", "L_rob", "p_rob")})
    out["family"] = classify_family(policy, baseline, break_sizes)
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
    # The ANY-TIME interval (D152 (1)) keeps its committed key and definition, so every committed
    # comparison recomputes to the same numbers.
    out["robot_standing_accuracy"] = paired_bootstrap(
        both, lambda q: 1.0 if pr[q]["standing_correct"] else 0.0,
        lambda q: 1.0 if br[q]["standing_correct"] else 0.0, seed=seed)
    # D155 (3): the HEADLINE interval, on its own key. Keys ending `_any_time` and `_by_deadline`
    # are the two rules; a key with neither suffix is the committed any-time one.
    bd = [q for q in qs if pr[q].get("standing_correct_by_deadline") is not None
          and br[q].get("standing_correct_by_deadline") is not None]
    out["robot_standing_accuracy_by_deadline"] = paired_bootstrap(
        bd, lambda q: 1.0 if pr[q]["standing_correct_by_deadline"] else 0.0,
        lambda q: 1.0 if br[q]["standing_correct_by_deadline"] else 0.0, seed=seed)
    out["robot_standing_accuracy_any_time"] = out["robot_standing_accuracy"]
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
