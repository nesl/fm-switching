#!/usr/bin/env python3
"""D266 item 2: THE ABANDON CHECK. Run on the FIRST TWO CELLS of scope A, before the other six.
CPU, read-only, no GPU.

*** WHY THIS IS THE MOST IMPORTANT THING IN THE BUILD. The committed grid gives
`robot_pool_on_time` = 121/132 at BOTH k=3 AND k=5, with DISJOINT victim sets and windows 157 s
apart. The runs differ genuinely, so the headline robot metric IS NOT SEPARATING THE DOSES. Under
nesting the two cells differ by exactly two robots at one identical window, which is a SMALLER
difference, so if the metric did not separate disjoint victim sets 157 s apart it may well not
separate nested ones either. If it does not, the k-effect is UNSCORABLE on that metric in Rule 2's
sense and the design rests entirely on the history-cached observable. THIS CHECK EXISTS SO THE
DESIGN CAN BE ABANDONED AFTER 8 CELLS INSTEAD OF 30. ***

THE CRITERIA ARE FIXED HERE, BEFORE ANY CELL RUNS, AND THEY ARE NOT NEGOTIABLE AFTERWARDS.

`--predict` needs no cells at all. It reads the two nested traces and reports BOTH dose channels.

  CHANNEL 1, the forced-miss floor: per added victim, how many of its questions fall inside the
  identical window. Those are device-only at the larger k and were cloud-eligible at the smaller
  one, so a cloud on-time count that is blind to device answers MUST fall by the number of them
  that were on time at the smaller k. The floor is a CONSTRUCTED BOUND, not an observed count, and
  is marked as such in the output.
  CHANNEL 2, the reconnect backlog: adding a victim defers its whole in-window history and releases
  it as a burst at the reconnect instant, which costs queueing and prefill whether or not that
  victim owned a question inside the window.

*** MEASURED AT THE RULED DESIGN POINT BEFORE ANY CELL RAN, AND IT CHANGES HOW THIS CHECK MUST BE
READ: channel 1 is 2 questions at seed 4 (k 1 -> 3), 1 at seed 4 (k 3 -> 5), and EXACTLY ZERO at
seed 5 at BOTH rungs, while channel 2 moves about 10,700 D2 tokens per rung at both seeds. So at
seed 5 nothing REQUIRES any metric to move with k, and a null there on cloud on-time is a null on
the backlog channel and not a blindness to a forced miss. ***

`--score` then reads the two cells and classifies:

  PASS-WITH-A-POLICY-CHANNEL
      the metric moves AND it moves by more than the floor. There is something beyond the forced
      misses, so the metric can carry a policy comparison. Proceed to the rest of scope A.
  PASS-BY-CONSTRUCTION-ONLY
      the metric moves and the movement is exactly the floor (within +/- 0 questions). The metric
      separates k ARITHMETICALLY, through the common additive penalty AMENDMENT 2 describes, and
      NOT through anything the policy did. This is NOT a licence to read a policy effect off it:
      proceed only on the history-cached observable and say so in the report.
  ABANDON
      the metric does not move (delta == 0) while the floor is strictly positive. The metric is
      blind to a dose it is arithmetically required to see. STOP BEFORE SCOPE B AND REPORT.
  ABANDON-ON-THE-BACKLOG-CHANNEL
      delta == 0, the floor is zero, and the backlog delta is NOT zero. Nothing required the metric
      to move, so this is weaker than ABANDON, but the backlog did grow with k and the metric did
      not see it, so it is stronger than UNEXERCISED. Report it as a null on the backlog channel AT
      THAT CELL and do not generalise it to a direction. This is the EXPECTED class at seed 5.
  UNEXERCISED
      delta == 0 and BOTH channels are zero. Nothing was tested at this k and D.
  INCOHERENT
      the metric moves in the WRONG DIRECTION, or the two cells' denominators differ, or the
      k=3 victim set is not contained in the k=5 set, or the windows differ. The cells are not the
      cells this check was designed for; nothing is read off them. STOP.

AND THE CONTROL IS CHECKED BEFORE THE COMPARISON (CLAUDE.md check 7). The denominators are read
from each cell's OWN sweep row and never carried across; the k=3 cell's no-outage reference is
compared if one is given (`--reference`); and the nesting and the window equality are read from the
ARTEFACTS, not assumed from the tag. A broken control passes every check applied to the treatment.

Every recorded robot metric is classified, not only the primary one, per D251 (record all metrics,
choose the headline at plotting time): robot cloud on-time, robot correct-by-deadline, and the
history-cached observable when `--history-cached` is given.

Usage:
  python d262_abandon_check.py --predict --repo DIR --seed 4 --n 16 --ratio 3:11:2 \
      --run-s 1200 --d 120 --k-small 3 --k-large 5 --out FILE
  python d262_abandon_check.py --score --cell-small DIR --cell-large DIR --out FILE \
      [--reference DIR] [--history-cached FILE] [--predicted FILE]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[2]

WORKLOAD = dict(robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                dashcam_min_frames=3, robot_upload="per-frame", robot_reask_mean_s=30.0)

# THE EVIDENCE FIELD, NAMED. `results/sember/study_h/data/sember_mcq.jsonl` carries, per question,
# `answer_start_time` and `answer_end_time`: the annotated interval of the video that the correct
# answer comes from, in the SAME session-time coordinate as `question_time`. `question_time` is
# what `fleet/data_sources.py:454` loads as `Question.t_ask` and what the trace writes as
# `t_ask_session`, so the evidence interval and the ask time are directly comparable without any
# rescaling. See the module docstring for the three other fields that could have been used and why
# they were not.
EVIDENCE_FIELDS = ("answer_start_time", "answer_end_time")
SEMBER_MCQ_REL = "results/sember/study_h/data/sember_mcq.jsonl"

# links.py's committed uplink, for the DRAIN TIME. One UplinkQueue PER DEVICE
# (`fleet/emulator.py:310`), so victims do not queue behind each other.
UPLINK_MBPS = 13.6            # fleet/links.py:38, D75 committed
RTT_MS = 44.0                 # fleet/links.py:39
QUESTION_TEXT_B = 1200        # fleet/emulator.py:73


def _serialise_s(nbytes):
    return nbytes * 8.0 / (UPLINK_MBPS * 1_000_000.0)


def evidence_table(repo: Path) -> dict:
    """{question_id_casefolded: (answer_start_time, answer_end_time)} from the committed MCQ file."""
    import json as _json
    path = repo / SEMBER_MCQ_REL
    if not path.exists():
        raise SystemExit("the committed S-EMBER MCQ file is not in this tree: %s" % path)
    out = {}
    for ln in open(path):
        if not ln.strip():
            continue
        r = _json.loads(ln)
        a, b = r.get("answer_start_time"), r.get("answer_end_time")
        if a is None or b is None:
            continue
        out[str(r["question_id"]).casefold()] = (float(a), float(b))
    return out


def drain_end(records, victim: str, t_out1: float) -> dict:
    """WHEN THE VICTIM'S BACKLOG HAS DRAINED, computed and not assumed.

    The outage BUFFERS: `fleet/trace.py:1037-1047` moves a victim's in-window `history_batch`
    offer time to the reconnect instant and DELETES NOTHING, so the evidence is delayed and not
    lost. The drain is therefore a real quantity and it is the dose's upper edge. This replays the
    victim's OWN committed UplinkQueue arithmetic (`fleet/links.py:112-120`,
    t_start = max(t_offer, free_at), occupancy = bytes * 8 / uplink) over that device's uploadable
    records in offer order, and reports the arrival of the LAST deferred record.
    """
    items = []
    for r in records:
        if str(r.get("device_id")) != victim:
            continue
        if r.get("kind") == "history_batch":
            items.append((float(r["t"]), int(r.get("frame_bytes") or 0), "history_batch",
                          abs(float(r["t"]) - t_out1) < 1e-6))
        elif r.get("kind") == "recall_question":
            items.append((float(r.get("t_offer", r["t"])), QUESTION_TEXT_B, "recall_question",
                          False))
    items.sort(key=lambda x: (x[0], x[2]))
    free_at = 0.0
    last_deferred_arrive = None
    n_def = 0
    def_bytes = 0
    for t_offer, nbytes, kind, deferred in items:
        t_start = max(t_offer, free_at)
        occ = _serialise_s(nbytes)
        free_at = t_start + occ
        arrive = free_at + (RTT_MS / 1000.0) / 2.0
        if deferred and kind == "history_batch":
            n_def += 1
            def_bytes += nbytes
            last_deferred_arrive = arrive
    return {"n_deferred_records": n_def, "deferred_bytes": def_bytes,
            "serialisation_s_alone": round(_serialise_s(def_bytes), 6),
            "drain_end_run_s": (None if last_deferred_arrive is None
                                else round(last_deferred_arrive, 6)),
            "drain_s_after_reconnect": (None if last_deferred_arrive is None
                                        else round(last_deferred_arrive - t_out1, 6)),
            "_how": ("replayed through the committed UplinkQueue arithmetic at "
                     "%g Mbps with the device's own FIFO; one queue per device" % UPLINK_MBPS)}


def _trace_bundle(repo: Path, seed: int, n: int, ratio: str, run_s: float, k: int, d: float,
                  placement: str, deadline_s: float, offset: int = 0,
                  semantics: str = "buffered") -> Dict[str, Any]:
    live2 = repo / "experiments/orchestration/live2"
    for p in (str(live2), str(live2 / "fleet"), str(repo / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import data_sources as _DS
    import trace as TR
    _DS.ROBOT_DEADLINE_S = float(deadline_s)        # D147: set before the call, never after
    return TR.generate_trace(seed, n, ratio, run_s, "A",
                             outage_robots_k=k, outage_duration_s=d, outage_seed_offset=offset,
                             **({} if placement == "band" else dict(outage_placement=placement)),
                             **({} if semantics == "buffered"
                                else dict(outage_semantics=semantics)),
                             **WORKLOAD)


def predict(a) -> Dict[str, Any]:
    repo = Path(a.repo) if a.repo else REPO_DEFAULT
    ev = evidence_table(repo)
    out = {}
    # SPLIT BY DEVICE TYPE, because a pooled join rate is meaningless here: the assistive
    # single-shot questions are VizWiz / EgoThink and have no S-EMBER evidence interval BY
    # CONSTRUCTION, so pooling them makes a complete robot join look like a half-failed one.
    miss = {"robot_questions": 0, "robot_matched": 0,
            "assistive_questions": 0, "assistive_matched": 0}
    for tag, k in (("small", a.k_small), ("large", a.k_large)):
        b = _trace_bundle(repo, a.seed, a.n, a.ratio, a.run_s, k, a.d, a.placement,
                          a.robot_deadline_s, semantics=a.semantics)
        om = b["meta"]["outage"]
        t0, t1 = float(om["t_start"]), float(om["t_end"])
        qs: Dict[str, list] = {}
        for r in b["records"]:
            if r.get("kind") != "recall_question":
                continue
            dev = str(r["device_id"])
            t = float(r["t"])
            tas = r.get("t_ask_session")
            qid = str(r.get("question_id") or "").casefold()
            e = ev.get(qid)
            if dev.startswith("robo"):
                miss["robot_questions"] += 1
                miss["robot_matched"] += (e is not None)
            else:
                miss["assistive_questions"] += 1
                miss["assistive_matched"] += (e is not None)
            # THE MAPPING, and it is one subtraction: the run time at which this play's session
            # time 0 sits is t - t_ask_session, so the evidence interval in RUN time is that plus
            # the annotated interval. No rescaling, because `t_ask_session` and the evidence
            # interval are both `sember_mcq.jsonl` session seconds.
            sess0 = (None if tas is None else t - float(tas))
            ev_run = (None if (e is None or sess0 is None)
                      else (sess0 + e[0], sess0 + e[1]))
            qs.setdefault(dev, []).append(
                {"t": t, "t_ask_session": tas, "question_id": qid, "qid": qid,
                 "evidence_session": e, "evidence_run": ev_run,
                 "asked_in_window": (t0 <= t < t1),
                 "asked_at_or_after_window_start": (t >= t0),
                 # the ruling's dose: evidence INSIDE the window, question asked at or after the
                 # window start. A question asked long after the window still counts.
                 "evidence_in_window": (ev_run is not None
                                        and ev_run[0] < t1 and ev_run[1] > t0)})
        drains = {v: drain_end(b["records"], v, t1) for v in om["robots"]}
        out[tag] = {"k": k, "outage": {kk: om.get(kk) for kk in
                                      ("placement", "robots", "t_start", "t_end",
                                       "victim_permutation", "device_only_questions",
                                       "deferred_history_records", "deferred_history_frames",
                                       "backlog_tokens_d2", "n_robots_total")},
                    "questions_per_device": {kk: len(v) for kk, v in sorted(qs.items())},
                    "in_window_per_device": {
                        kk: sum(1 for q in v if q["asked_in_window"])
                        for kk, v in sorted(qs.items())},
                    "missed_evidence_per_device": {
                        kk: sum(1 for q in v if q["asked_at_or_after_window_start"]
                                and q["evidence_in_window"])
                        for kk, v in sorted(qs.items())},
                    # DISTINCT questions, which is the number the D273 (1) ruling names. A re-ask
                    # carries the same question_id and so the same evidence interval, so an
                    # instance count is partly a re-ask count.
                    "missed_evidence_distinct_per_device": {
                        kk: len({q["qid"] for q in v if q["asked_at_or_after_window_start"]
                                 and q["evidence_in_window"]})
                        for kk, v in sorted(qs.items())},
                    "drain_per_victim": drains,
                    "missed_evidence_before_drain_per_device": {
                        kk: sum(1 for q in v
                                if q["asked_at_or_after_window_start"] and q["evidence_in_window"]
                                and (drains.get(kk, {}).get("drain_end_run_s") is None
                                     or q["t"] < drains[kk]["drain_end_run_s"]))
                        for kk, v in sorted(qs.items())},
                    "_questions": qs,
                    "robot_questions_total": sum(len(v) for kk, v in qs.items()
                                                 if kk.startswith("robo"))}
    out["_evidence_join"] = dict(
        miss,
        robot_unmatched=miss["robot_questions"] - miss["robot_matched"],
        robot_matched_fraction=(round(miss["robot_matched"] / miss["robot_questions"], 6)
                                if miss["robot_questions"] else None),
        _why=("a ROBOT question whose id is not in the committed MCQ file has no evidence "
              "interval and is counted as unmatched rather than as a zero, which would silently "
              "shrink the dose. The assistive questions are VizWiz / EgoThink single shots and "
              "have no S-EMBER interval by construction, so their zero match is correct and is "
              "reported separately rather than mixed into the rate."),
        ROBOT_JOIN_COMPLETE=bool(miss["robot_questions"] > 0
                                 and miss["robot_matched"] == miss["robot_questions"]))
    s, l = out["small"], out["large"]
    sv, lv = set(s["outage"]["robots"]), set(l["outage"]["robots"])
    added = sorted(lv - sv)
    same_window = (s["outage"]["t_start"] == l["outage"]["t_start"]
                   and s["outage"]["t_end"] == l["outage"]["t_end"])
    floor = sum(l["in_window_per_device"].get(rb, 0) for rb in added)
    dose_ev = sum(l["missed_evidence_per_device"].get(rb, 0) for rb in added)
    dose_ev_q = sum(l["missed_evidence_distinct_per_device"].get(rb, 0) for rb in added)
    dose_ev_bounded = sum(l["missed_evidence_before_drain_per_device"].get(rb, 0) for rb in added)
    res = {
        "_what": ("the arithmetic floor on the k-separation of a cloud-on-time count, computed "
                  "from the traces alone, BEFORE any cell runs"),
        "_register": ("CONSTRUCTED BOUND, not an observed count: it assumes every added "
                      "device-only question was on time at the smaller k. The observed drop can "
                      "be SMALLER if some of them were already misses, which is why --score "
                      "reconciles it against the cells rather than asserting it."),
        "nested": bool(sv <= lv), "same_window": bool(same_window),
        "small_victims": sorted(sv), "large_victims": sorted(lv), "added_victims": added,
        "per_added_victim_questions_in_window": {rb: l["in_window_per_device"].get(rb, 0)
                                                 for rb in added},
        "device_only_questions_small_k": s["outage"]["device_only_questions"],
        "device_only_questions_large_k": l["outage"]["device_only_questions"],
        # *** THE RULING'S DOSE, AND IT IS THE PRIMARY ONE. Per added victim, the robot
        # questions asked AT OR AFTER the window start whose ANNOTATED EVIDENCE INTERVAL
        # (`answer_start_time`, `answer_end_time`) falls inside the window. A question asked long
        # after the window counts, which is why this is a different and larger quantity than the
        # forced-miss floor below. ***
        "DOSE_MISSED_EVIDENCE": dose_ev,
        "DOSE_MISSED_EVIDENCE_per_added_victim": {
            rb: l["missed_evidence_per_device"].get(rb, 0) for rb in added},
        # *** THE NUMBER THE RULING NAMES. ***
        "DOSE_MISSED_EVIDENCE_DISTINCT_QUESTIONS": sum(
            l["missed_evidence_distinct_per_device"].get(rb, 0) for rb in added),
        "DOSE_MISSED_EVIDENCE_DISTINCT_per_added_victim": {
            rb: l["missed_evidence_distinct_per_device"].get(rb, 0) for rb in added},
        # the SAME dose bounded by the drain, which is the honest upper edge BECAUSE THE OUTAGE
        # BUFFERS RATHER THAN DROPS: the evidence is delayed, so a question asked after the
        # backlog has drained has its evidence in hand.
        "DOSE_MISSED_EVIDENCE_BEFORE_DRAIN": (dose_ev_bounded if a.semantics == "buffered"
                                              else "NOT APPLICABLE (true semantics)"),
        "DOSE_MISSED_EVIDENCE_BEFORE_DRAIN_per_added_victim": {
            rb: l["missed_evidence_before_drain_per_device"].get(rb, 0) for rb in added},
        "drain_per_added_victim": ({rb: l["drain_per_victim"].get(rb) for rb in added}
                                   if a.semantics == "buffered" else
                                   "NOT APPLICABLE under true semantics: the frames are LOST, "
                                   "never drained, so no drain bounds the dose"),
        "semantics": a.semantics,
        "FRAMES_ARE_BUFFERED_NOT_DROPPED": {
            "verdict": "BUFFERED",
            "evidence": ("fleet/trace.py:1037-1047 moves a victim's in-window `history_batch` "
                         "offer time to the reconnect instant (`r[\"t\"] = round(t_out1, 6)`) and "
                         "deletes no record; fleet/trace.py:1048-1056 moves a `recall_question`'s "
                         "`t_offer` only, never its ask time. The committed UplinkQueue "
                         "(fleet/links.py:112-120) then takes t_start = max(t_offer, free_at), so "
                         "the burst and its queueing delay are produced by the committed link "
                         "model and nothing is lost."),
            "consequence": ("the evidence is DELAYED, not lost, so the dose's upper edge is the "
                            "drain time, which is computed per victim above and never assumed")},
        "FLOOR_added_device_only_questions": floor,
        "_FLOOR_IS_A_DIFFERENT_CHANNEL": (
            "questions ASKED inside the window are forced device-only and are the arithmetic "
            "floor on a CLOUD-ON-TIME count. They are NOT this design's effect and are kept only "
            "as that floor. The missed-evidence dose above bears on CORRECTNESS (the answer is "
            "computed without the interval it needs), and on latency when the answer waits for "
            "the backlog."),
        # THE SECOND CHANNEL, and at seed 5 it is the ONLY one. Adding a victim defers its whole
        # in-window history and releases it as a burst at the reconnect instant, which costs
        # queueing on the uplink and prefill at the cloud whether or not that victim owned a
        # question inside the window. A metric can separate k through this channel with the
        # forced-miss floor at zero.
        "BACKLOG_CHANNEL": {
            "deferred_history_records_small_large": [s["outage"]["deferred_history_records"],
                                                     l["outage"]["deferred_history_records"]],
            "backlog_tokens_d2_small_large": [s["outage"]["backlog_tokens_d2"],
                                              l["outage"]["backlog_tokens_d2"]],
            "delta_backlog_tokens_d2": (l["outage"]["backlog_tokens_d2"]
                                        - s["outage"]["backlog_tokens_d2"]),
            "NON_ZERO": bool(l["outage"]["backlog_tokens_d2"]
                             != s["outage"]["backlog_tokens_d2"])},
        "deferred_history_records": [s["outage"]["deferred_history_records"],
                                     l["outage"]["deferred_history_records"]],
        "backlog_tokens_d2": [s["outage"]["backlog_tokens_d2"], l["outage"]["backlog_tokens_d2"]],
        "robot_questions_total": [s["robot_questions_total"], l["robot_questions_total"]],
        "cells": out,
        "USABLE": bool(sv <= lv and same_window),
        "DOSE_IS_NON_ZERO": bool(dose_ev > 0 or floor > 0
                                 or (l["outage"]["backlog_tokens_d2"]
                                     != s["outage"]["backlog_tokens_d2"])),
        "RULING_DOSE_IS_NON_ZERO": bool(dose_ev > 0),
        # THE VERDICT LEADS WITH THE DOSE THE RULING NAMES, and it is semantics-aware. Leading
        # with the forced-miss channel was right only while the dose was wrongly defined as
        # questions ASKED inside the window; under D273 (1) the deciding dose is the MISSED
        # EVIDENCE, and under TRUE semantics it has no drain to bound it.
        "VERDICT": (
            "STOP: the traces do not nest or the windows differ."
            if not (sv <= lv and same_window) else
            ("*** EVERY DOSE IS ZERO AT THIS PAIR: no distinct question of an added victim has its "
             "evidence inside the window, so nothing is dosed here and a null would be "
             "UNEXERCISED, not a negative. ***"
             if dose_ev <= 0 else
             ("the pair is dosed and the design is live here: %d DISTINCT question(s) (%d ask "
              "instances) of the added victims have their evidence inside the window, and under "
              "TRUE semantics those frames NEVER ARRIVE, so no drain bounds the dose. The "
              "forced-miss channel is %d and decides nothing. WEAK DOSE: label it one wherever it "
              "is quoted, and read distinct questions, never instances."
              % (dose_ev_q, dose_ev, floor)
              if a.semantics == "true" else
              "the pair is dosed on the missed-evidence channel (%d distinct question(s), %d "
              "instances), but under BUFFERED semantics the drain bounds it to %s; the forced-miss "
              "floor is %d and the backlog delta is %d D2 tokens."
              % (dose_ev_q, dose_ev, dose_ev_bounded, floor,
                 l["outage"]["backlog_tokens_d2"] - s["outage"]["backlog_tokens_d2"])))),
    }
    for tag in ("small", "large"):
        res["cells"][tag].pop("_questions", None)        # per-question rows: large and not a claim
    return res


def _find(o: Any, name: str) -> Any:
    """The first value under `name`, at any depth. The score tree's nesting has moved before
    (`/score/score/robot_headline/on_time_beside_it/...`), so a hard-coded path is a silent None
    waiting to happen."""
    if isinstance(o, dict):
        if name in o:
            return o[name]
        for v in o.values():
            r = _find(v, name)
            if r is not None:
                return r
    elif isinstance(o, (list, tuple)):
        for v in o:
            r = _find(v, name)
            if r is not None:
                return r
    return None


def _score_of(cell: Path) -> Dict[str, Any]:
    cj = json.loads((cell / "cell.json").read_text())
    sc = ((cj.get("score") or {}).get("score") or {})
    rh = sc.get("robot_headline") or {}
    ob = rh.get("on_time_beside_it") or {}
    return {"cell": cell.name,
            "arm": cj.get("arm"), "seed": cj.get("seed"), "n_devices": cj.get("n_devices"),
            "run_valid": cj.get("run_valid"), "result_status": cj.get("result_status"),
            "source_agreement": (cj.get("source_agreement") or {}).get("verdict")
            if isinstance(cj.get("source_agreement"), dict) else cj.get("source_agreement"),
            "trace_dir": cj.get("trace_dir"),
            # REPORTED, NOT DECIDING (D273 (1)): this metric read 121/132 at both k in the
            # committed cells, so it is the one already known not to separate the doses.
            "robot_pool_on_time_REPORTED_NOT_DECIDING": ob.get("robot_pool_on_time"),
            "robot_pool_n": ob.get("robot_pool_n"),
            # THE TWO DECIDING METRICS
            "correct_by_deadline": rh.get("correct_answers_delivered_by_deadline"),
            "n_by_deadline": rh.get("n_by_deadline"),
            "cloud_accuracy_on_served": _find(sc, "cloud_accuracy_on_served"),
            "cloud_answers_available": _find(sc, "cloud_answers_available"),
            "n_cloud_standing": _find(sc, "n_cloud_standing")}


def classify(delta: Optional[int], floor: Optional[int], name: str,
             backlog_dose: bool = True) -> Dict[str, Any]:
    if delta is None or floor is None:
        return {"metric": name, "CLASS": "UNREADABLE"}
    if delta > 0:
        return {"metric": name, "delta": delta, "floor": floor, "CLASS": "INCOHERENT",
                "why": "the count ROSE with more victims; a forced device-only question cannot "
                       "raise a cloud-on-time count"}
    mag = -delta
    if mag == 0 and floor > 0:
        cls, why = "ABANDON", ("the metric did not move although %d question(s) were forced "
                               "device-only. It is blind to a dose it is arithmetically required "
                               "to see. STOP BEFORE SCOPE B." % floor)
    elif mag == 0 and backlog_dose:
        cls, why = "ABANDON-ON-THE-BACKLOG-CHANNEL", (
            "the forced-miss floor is zero at this cell, so nothing REQUIRED the metric to move, "
            "but the reconnect backlog does grow with k and the metric did not see it. This is "
            "weaker evidence than ABANDON and stronger than UNEXERCISED: report it as a null on "
            "the backlog channel at this cell and do not generalise it to a direction.")
    elif mag == 0:
        cls, why = "UNEXERCISED", "no dose on either channel and no movement: nothing was tested"
    elif mag > floor:
        cls, why = "PASS-WITH-A-POLICY-CHANNEL", ("the metric moved by %d, more than the %d forced "
                                                  "misses, so something beyond the common penalty "
                                                  "is visible to it" % (mag, floor))
    else:
        cls, why = "PASS-BY-CONSTRUCTION-ONLY", ("the metric moved by %d against a floor of %d: "
                                                 "separation is the forced-miss arithmetic and NOT "
                                                 "evidence of a policy effect" % (mag, floor))
    return {"metric": name, "delta": delta, "floor": floor, "CLASS": cls, "why": why}


def score(a) -> Dict[str, Any]:
    s, l = _score_of(Path(a.cell_small)), _score_of(Path(a.cell_large))
    pred = json.loads(Path(a.predicted).read_text()) if a.predicted else None
    floor = (pred or {}).get("FLOOR_added_device_only_questions")
    ctl = {
        "_what": "THE CONTROL, READ BEFORE THE COMPARISON",
        "denominators_pool": [s["robot_pool_n"], l["robot_pool_n"]],
        "denominators_pool_equal": s["robot_pool_n"] == l["robot_pool_n"],
        "denominators_deadline": [s["n_by_deadline"], l["n_by_deadline"]],
        "denominators_deadline_equal": s["n_by_deadline"] == l["n_by_deadline"],
        "_why": ("under nesting the two cells share one trace structure, so unequal denominators "
                 "mean the cells are not the paired cells this check assumes. Denominators are "
                 "read from each cell's OWN row and never carried between seeds."),
        "arms_match": s["arm"] == l["arm"], "seeds_match": s["seed"] == l["seed"],
        "both_valid": bool(s["run_valid"]) and bool(l["run_valid"]),
        "source_agreement": [s["source_agreement"], l["source_agreement"]],
        "nesting_from_artefact": (pred or {}).get("nested"),
        "same_window_from_artefact": (pred or {}).get("same_window"),
    }
    if a.reference:
        ctl["no_outage_reference"] = _score_of(Path(a.reference))
        ctl["_reference_why"] = ("the no-outage cell for this arm, seed and mix. If the outage "
                                "cells do not sit BELOW it, the outage did not bite and neither "
                                "cell is a treatment.")
    coherent = (ctl["denominators_pool_equal"] and ctl["arms_match"] and ctl["seeds_match"]
                and ctl["both_valid"])
    bdose = bool(((pred or {}).get("BACKLOG_CHANNEL") or {}).get("NON_ZERO"))
    # THE MISSED-EVIDENCE DOSE IS THE DOSE FOR A CORRECTNESS METRIC. The device-only count is the
    # floor for a cloud-on-time COUNT and for nothing else, so it is not used below.
    ev_dose = (pred or {}).get("DOSE_MISSED_EVIDENCE")
    ev_dose_q = (pred or {}).get("DOSE_MISSED_EVIDENCE_DISTINCT_QUESTIONS")
    rows = []
    if None not in (s["cloud_accuracy_on_served"], l["cloud_accuracy_on_served"],
                    s["cloud_answers_available"], l["cloud_answers_available"]):
        cs = round(s["cloud_accuracy_on_served"] * s["cloud_answers_available"])
        cl2 = round(l["cloud_accuracy_on_served"] * l["cloud_answers_available"])
        rows.append(dict(
            classify(cl2 - cs, ev_dose, "cloud_correct_count", backlog_dose=bdose),
            counts=[cs, cl2],
            denominators=[s["cloud_answers_available"], l["cloud_answers_available"]],
            dose_used="DOSE_MISSED_EVIDENCE (instances)",
            dose_distinct_questions=ev_dose_q,
            note=("the SHARPEST metric for this condition: the accuracy of the CLOUD's own answers "
                  "on the questions it served, so a cloud answering with frames missing shows in "
                  "it with no device half to dilute it. Its denominator is arm-dependent and must "
                  "be quoted beside it.")))
    if None not in (s["correct_by_deadline"], l["correct_by_deadline"], s["n_by_deadline"],
                    l["n_by_deadline"]):
        cs = round(s["correct_by_deadline"] * s["n_by_deadline"])
        cl = round(l["correct_by_deadline"] * l["n_by_deadline"])
        rows.append(dict(classify(cl - cs, ev_dose, "correct_by_deadline_count",
                                  backlog_dose=bdose),
                         counts=[cs, cl],
                         dose_used="DOSE_MISSED_EVIDENCE (instances)",
                         dose_distinct_questions=ev_dose_q,
                         note=("a DECIDING metric under D273 (1). Its device half is intact under "
                               "true semantics (the device keeps its own history), so a fall here "
                               "is the cloud answering with frames missing.")))
    # reported and NOT deciding, with its own floor, because it is the metric already known to be
    # flat at both k in the committed cells
    rows.append(dict(classify(
        (None if None in (s["robot_pool_on_time_REPORTED_NOT_DECIDING"],
                          l["robot_pool_on_time_REPORTED_NOT_DECIDING"])
         else l["robot_pool_on_time_REPORTED_NOT_DECIDING"]
         - s["robot_pool_on_time_REPORTED_NOT_DECIDING"]),
        floor, "robot_pool_on_time", backlog_dose=bdose),
        DECIDES_NOTHING=True, dose_used="forced device-only count (its own arithmetic floor)",
        note=("REPORTED ONLY. D273 (1): this metric read 121/132 at both k in the committed "
              "cells, so it does not score the abandon check. Its class is recorded so the "
              "record shows what it did, not so anything is read off it.")))
    hc = None
    if a.history_cached:
        hc = json.loads(Path(a.history_cached).read_text())
        cells = list((hc.get("cells") or {}).values())
        hc = {"victims_cached": [(c.get("victims_first_post_reconnect") or {}).get("cached")
                                 for c in cells],
              "victims_n": [(c.get("victims_first_post_reconnect") or {}).get("n")
                            for c in cells],
              "unscorable": [c.get("UNSCORABLE") for c in cells],
              "_why": ("the fallback observable. If every robot attainment metric is ABANDON, this "
                       "is the only thing the design rests on, so its own n is reported beside it: "
                       "an n of 0 makes it an ABSENT LINK for that arm, not a null.")}
    # only the DECIDING metrics decide
    classes = [r["CLASS"] for r in rows if not r.get("DECIDES_NOTHING")]
    if not coherent:
        verdict = ("STOP: the control failed before the comparison was read (see control). "
                   "Nothing is read off these two cells.")
    elif "INCOHERENT" in classes:
        verdict = "STOP: a metric moved in a direction that cannot happen. Investigate, do not score."
    elif all(c in ("ABANDON", "ABANDON-ON-THE-BACKLOG-CHANNEL") for c in classes):
        verdict = ("*** ABANDON: NO RECORDED ROBOT ATTAINMENT METRIC SEPARATES k UNDER NESTING, "
                   "although the dose is arithmetically non-zero. Do NOT run scope B. The k-effect "
                   "is UNSCORABLE on these metrics in Rule 2's sense, and the design rests "
                   "entirely on the history-cached observable. REPORT TO THE USER. ***")
    elif any(c == "PASS-WITH-A-POLICY-CHANNEL" for c in classes):
        verdict = ("PROCEED: at least one recorded robot metric moves by more than the forced-miss "
                   "floor, so it can carry a policy comparison.")
    else:
        verdict = ("PROCEED WITH A NAMED LIMIT: the metrics separate k only by the forced-miss "
                   "arithmetic. Any k-effect read off them is a dose effect and not a policy "
                   "effect, and the policy comparison must come from the history-cached "
                   "observable. Say this in the report rather than quoting a separation.")
    return {"_what": "D266 item 2 abandon check, scored on the first two cells of scope A",
            "small": s, "large": l, "floor_from_predict": floor,
            "predicted_file": a.predicted, "CONTROL": ctl, "CONTROL_COHERENT": bool(coherent),
            "metrics": rows, "history_cached": hc, "VERDICT": verdict}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--predict", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--k-small", type=int, default=3)
    ap.add_argument("--k-large", type=int, default=5)
    ap.add_argument("--placement", default="centre", choices=("band", "centre"))
    ap.add_argument("--semantics", default="buffered", choices=("buffered", "true"),
                    help="D273 (1): 'true' loses the frames, so no drain bounds the dose")
    ap.add_argument("--robot-deadline-s", type=float, default=3.0)
    ap.add_argument("--cell-small", default=None)
    ap.add_argument("--cell-large", default=None)
    ap.add_argument("--reference", default=None)
    ap.add_argument("--history-cached", default=None)
    ap.add_argument("--predicted", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.predict == a.score:
        ap.error("give exactly one of --predict or --score")
    out = predict(a) if a.predict else score(a)
    if a.score and not (a.cell_small and a.cell_large):
        ap.error("--score needs --cell-small and --cell-large")
    try:
        sys.path.insert(0, str((Path(a.repo) if a.repo else REPO_DEFAULT) / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d262_abandon_check.py", model="qwen3vl32b",
                                   device="read_only_cpu", n=2, args=a)
    except Exception as e:
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in out.items()
                      if k in ("VERDICT", "USABLE", "nested", "same_window",
                               "FLOOR_added_device_only_questions",
                               "per_added_victim_questions_in_window", "CONTROL_COHERENT")},
                     indent=1, default=str))
    if a.score:
        for r in out["metrics"]:
            print(" %-28s delta=%s floor=%s %s" % (r["metric"], r.get("delta"), r.get("floor"),
                                                   r["CLASS"]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
