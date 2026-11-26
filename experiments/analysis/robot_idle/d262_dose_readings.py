#!/usr/bin/env python3
"""D266 item 2: THE DOSE UNDER EVERY FIELD THAT COULD STAND FOR "THE EVIDENCE THIS ANSWER
REQUIRES". CPU, read-only, no GPU, no cell.

The user ruling on the build fixed the dose as: per ADDED victim, the robot questions asked AT OR
AFTER the window start whose EVIDENCE falls inside the window. More than one field in this harness
could stand for that evidence, so all of them are named here, the chosen one is stated, and the
dose is reported under each.

  R1  ANNOTATED GROUND-TRUTH INTERVAL  [answer_start_time, answer_end_time]  <-- CHOSEN
      `results/sember/study_h/data/sember_mcq.jsonl` carries both per question, in the SAME
      session-time coordinate as `question_time`, which `fleet/data_sources.py:454` loads as
      `Question.t_ask` and the trace writes as `t_ask_session`. So the interval and the ask time
      are directly comparable with one subtraction and no rescaling. CHOSEN because it is the
      ruling's own words ("ground-truth event time") and because it is an ANNOTATION of the data
      rather than a property of the harness: it does not move if the upload contract changes.
  R2  THE D2 FRAMES THE ANSWER NEEDS
      the same interval, but counted only when a D2 capture instant actually falls inside the
      intersection of the evidence interval and the window. R2 is the operational form of R1 and
      is never larger than it: a 1 s evidence interval can fall between two capture instants.
      Reported because the thing physically withheld is frames, not seconds.
  R3  THE WHOLE HISTORY UP TO THE ASK
      every question asked after the window start "requires" the window's frames, because its
      prompt is the cumulative D2 history (`DS.d2_frames_in(0, t_ask)`). This is the MAXIMAL
      reading and it is defensible, so it is reported; it is an upper bound and not the ruling's
      quantity.
  NOT USABLE as evidence, and said so rather than left out:
      `question_time` / `t_ask_session` is the ASK time. Counting questions asked inside the
      window uses it and is the dose this build had WRONG; it is kept only as the arithmetic floor
      on a cloud-on-time count, which is a different channel.
      `history_tokens` is HOW MUCH history the cloud holds at the ask, not WHEN the evidence is.
      It cannot localise evidence in time at all.

INSTANCES ARE NOT QUESTIONS, AND THE DIFFERENCE IS AN ORDER OF MAGNITUDE HERE. With
`robot_reask_mean_s=30` the same question is asked again about every 30 s, and a re-ask carries the
SAME `question_id` and therefore the same evidence interval. So one affected question can appear as
eleven affected instances. Both are reported, and the DISTINCT count is the one to read: at the
ruled design point the instance counts 5, 9, 1 and 22 are 1, 2, 1 and 3 distinct questions.

EVERY READING IS BOUNDED BY THE DRAIN, because the outage BUFFERS and does not drop:
`fleet/trace.py:1037-1047` moves a victim's in-window `history_batch` offer time to the reconnect
instant and deletes nothing. The evidence is therefore DELAYED, and a question asked after the
victim's backlog has drained has its evidence in hand. The drain is computed from the committed
`UplinkQueue` arithmetic, never assumed.

Usage:
  python d262_dose_readings.py --repo DIR --out FILE [--seed 4 --seed 5] [--k 1 --k 3 --k 5]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[2]

WORKLOAD = dict(robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                dashcam_min_frames=3, robot_upload="per-frame", robot_reask_mean_s=30.0)
UPLINK_MBPS = 13.6
RTT_MS = 44.0
QUESTION_TEXT_B = 1200


def _ser(nbytes: int) -> float:
    return nbytes * 8.0 / (UPLINK_MBPS * 1_000_000.0)


def load(repo: Path):
    live2 = repo / "experiments/orchestration/live2"
    for p in (str(live2), str(live2 / "fleet"), str(repo / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import data_sources as DS
    import trace as TR
    return DS, TR


def evidence(repo: Path) -> Dict[str, Any]:
    out = {}
    for ln in open(repo / "results/sember/study_h/data/sember_mcq.jsonl"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("answer_start_time") is None or r.get("answer_end_time") is None:
            continue
        out[str(r["question_id"]).casefold()] = (float(r["answer_start_time"]),
                                                float(r["answer_end_time"]))
    return out


def drain(records, victim: str, t1: float) -> Dict[str, Any]:
    items = []
    for r in records:
        if str(r.get("device_id")) != victim:
            continue
        if r.get("kind") == "history_batch":
            items.append((float(r["t"]), int(r.get("frame_bytes") or 0), "h",
                          abs(float(r["t"]) - t1) < 1e-6))
        elif r.get("kind") == "recall_question":
            items.append((float(r.get("t_offer", r["t"])), QUESTION_TEXT_B, "q", False))
    items.sort(key=lambda x: (x[0], x[2]))
    free = 0.0
    last = None
    n = 0
    nb = 0
    for t_offer, nbytes, kind, deferred in items:
        t_start = max(t_offer, free)
        free = t_start + _ser(nbytes)
        arrive = free + (RTT_MS / 1000.0) / 2.0
        if deferred and kind == "h":
            n += 1
            nb += nbytes
            last = arrive
    return {"n_deferred_records": n, "deferred_bytes": nb,
            "uplink_serialisation_s": round(_ser(nb), 6),
            "drain_end_run_s": (None if last is None else round(last, 6)),
            "drain_s_after_reconnect": (None if last is None else round(last - t1, 6))}


def one(DS, TR, ev, seed: int, k: int, d: float, ratio: str, n: int, run_s: float,
        deadline_s: float, semantics: str = "buffered") -> Dict[str, Any]:
    DS.ROBOT_DEADLINE_S = float(deadline_s)
    kw = dict(WORKLOAD)
    if semantics != "buffered":
        kw["outage_semantics"] = semantics
    b = TR.generate_trace(seed, n, ratio, run_s, "A", outage_robots_k=k, outage_duration_s=d,
                          outage_placement="centre", **kw)
    om = b["meta"]["outage"]
    t0, t1 = float(om["t_start"]), float(om["t_end"])
    # *** UNDER TRUE SEMANTICS THERE IS NO DRAIN, SO THERE IS NO UPPER EDGE TO BOUND THE DOSE BY.
    # Reporting a bounded column of zeros here would read as "the dose is zero", which is exactly
    # backwards: the frames never arrive at all, so every affected question is affected for the
    # rest of the run. The bounded columns are NOT APPLICABLE and say so. ***
    drains = ({v: drain(b["records"], v, t1) for v in om["robots"]}
              if semantics == "buffered" else
              {v: {"n_deferred_records": 0, "deferred_bytes": 0, "uplink_serialisation_s": 0.0,
                   "drain_end_run_s": None, "drain_s_after_reconnect": None,
                   "_NOT_APPLICABLE": ("true semantics: the frames are LOST, never drained, so "
                                       "there is no drain and no bound")}
               for v in om["robots"]})
    # the D2 capture instants inside the window, which is what is physically withheld
    win_frames = [float(x) for x in DS.d2_frames_in(0.0, run_s)] if hasattr(DS, "d2_frames_in") else []
    per: Dict[str, Dict[str, Any]] = {}
    joined = unjoined = 0
    for r in b["records"]:
        if r.get("kind") != "recall_question":
            continue
        dev = str(r["device_id"])
        if not dev.startswith("robo"):
            continue
        t = float(r["t"])
        tas = r.get("t_ask_session")
        e = ev.get(str(r.get("question_id") or "").casefold())
        if e is None or tas is None:
            unjoined += 1
            continue
        joined += 1
        sess0 = t - float(tas)
        a, z = sess0 + e[0], sess0 + e[1]
        after = t >= t0
        r1 = bool(after and a < t1 and z > t0)
        # R2: a D2 capture instant inside BOTH the evidence interval and the window. The capture
        # instants are session-relative, so they are shifted by the same sess0.
        lo, hi = max(a, t0), min(z, t1)
        r2 = bool(after and hi > lo
                  and any(lo <= sess0 + f < hi for f in win_frames))
        r3 = bool(after)
        de = drains.get(dev, {}).get("drain_end_run_s")
        bounded = (de is None or t < de)
        row = per.setdefault(dev, {"n_questions": 0, "R1": 0, "R2": 0, "R3": 0,
                                   "R1_before_drain": 0, "R2_before_drain": 0,
                                   "R3_before_drain": 0, "asked_in_window": 0,
                                   "_R1_qids": [], "_R2_qids": [], "_R1_detail": []})
        row["n_questions"] += 1
        row["asked_in_window"] += int(t0 <= t < t1)
        qid = str(r.get("question_id") or "").casefold()
        for key, val in (("R1", r1), ("R2", r2), ("R3", r3)):
            row[key] += int(val)
            if val and bounded:
                row[key + "_before_drain"] += 1
        if r1:
            if qid not in row["_R1_qids"]:
                row["_R1_qids"].append(qid)
                row["_R1_detail"].append(
                    {"question_id": qid, "evidence_run_s": [round(a, 3), round(z, 3)],
                     "overlap_with_window_s": round(min(z, t1) - max(a, t0), 3),
                     "d2_frames_in_overlap": sum(1 for f in win_frames
                                                 if max(a, t0) <= sess0 + f < min(z, t1)),
                     "first_ask_run_s": round(t, 3)})
            else:
                for dd in row["_R1_detail"]:
                    if dd["question_id"] == qid:
                        dd["instances"] = dd.get("instances", 1) + 1
        if r2 and qid not in row["_R2_qids"]:
            row["_R2_qids"].append(qid)
    return {"k": k, "victims": list(om["robots"]), "t_start": t0, "t_end": t1,
            "victim_permutation": om.get("victim_permutation"),
            "deferred_history_records": om.get("deferred_history_records"),
            "backlog_tokens_d2": om.get("backlog_tokens_d2"),
            "semantics": semantics,
            "drain_applies": bool(semantics == "buffered"),
            "drain_per_victim": drains, "per_device": per,
            "evidence_join": {"robot_questions_joined": joined,
                              "robot_questions_unjoined": unjoined,
                              "COMPLETE": bool(unjoined == 0)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--k", type=int, action="append", default=None)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--robot-deadline-s", type=float, default=3.0)
    ap.add_argument("--semantics", default="buffered", choices=("buffered", "true"),
                    help="D273 (1): 'true' loses the frames, so no drain bounds the dose")
    a = ap.parse_args(argv)
    seeds = sorted(a.seed) if a.seed else [4, 5]
    ks = sorted(a.k) if a.k else [1, 3, 5]
    repo = Path(a.repo) if a.repo else REPO_DEFAULT
    DS, TR = load(repo)
    ev = evidence(repo)

    cells: Dict[str, Any] = {}
    for s in seeds:
        for k in ks:
            cells["s%d_k%d" % (s, k)] = one(DS, TR, ev, s, k, a.d, a.ratio, a.n, a.run_s,
                                            a.robot_deadline_s, a.semantics)
    pairs = {}
    for s in seeds:
        for i in range(len(ks) - 1):
            k1, k2 = ks[i], ks[i + 1]
            c1, c2 = cells["s%d_k%d" % (s, k1)], cells["s%d_k%d" % (s, k2)]
            added = sorted(set(c2["victims"]) - set(c1["victims"]))
            row = {"added_victims": added,
                   "nested": set(c1["victims"]) <= set(c2["victims"]),
                   "same_window": (c1["t_start"] == c2["t_start"]
                                   and c1["t_end"] == c2["t_end"]),
                   "drain_s_after_reconnect": {
                       rb: c2["drain_per_victim"].get(rb, {}).get("drain_s_after_reconnect")
                       for rb in added},
                   "delta_backlog_tokens_d2": (c2["backlog_tokens_d2"] - c1["backlog_tokens_d2"])}
            for key in ("R1", "R2", "R3", "R1_before_drain", "R2_before_drain",
                        "R3_before_drain", "asked_in_window"):
                row[key] = sum(c2["per_device"].get(rb, {}).get(key, 0) for rb in added)
                row[key + "_per_victim"] = {rb: c2["per_device"].get(rb, {}).get(key, 0)
                                            for rb in added}
            # *** THE NUMBER TO READ. An instance count is inflated by the re-asks; a distinct
            # question is one piece of evidence actually withheld. ***
            row["R1_DISTINCT_QUESTIONS"] = sum(
                len(c2["per_device"].get(rb, {}).get("_R1_qids", [])) for rb in added)
            row["R2_DISTINCT_QUESTIONS"] = sum(
                len(c2["per_device"].get(rb, {}).get("_R2_qids", [])) for rb in added)
            row["R1_per_question"] = [d for rb in added
                                      for d in c2["per_device"].get(rb, {}).get("_R1_detail", [])]
            row["READINGS_AGREE"] = (row["R1"] == row["R2"])
            row["_instances_vs_questions"] = (
                "%d instances of %d distinct question(s); a re-ask carries the same question_id "
                "and so the same evidence interval"
                % (row["R1"], row["R1_DISTINCT_QUESTIONS"]))
            pairs["s%d_k%d-%d" % (s, k1, k2)] = row

    allzero_r1 = all(v["R1"] == 0 for v in pairs.values())
    allzero_q = all(v["R1_DISTINCT_QUESTIONS"] == 0 for v in pairs.values())
    allzero_bounded = all(v["R1_before_drain"] == 0 for v in pairs.values())
    out = {
        "_what": ("D266 item 2: the added-victim dose under every field that could stand for the "
                  "evidence an answer requires, with the drain computed from the committed uplink "
                  "model. CPU, no cell."),
        "_chosen_field": "R1: [answer_start_time, answer_end_time] from sember_mcq.jsonl",
        "_semantics": a.semantics,
        "_drain_bound_applies": bool(a.semantics == "buffered"),
        "_drain_bound_note": (
            "under TRUE semantics the frames are LOST and never drained, so the bounded "
            "columns are NOT APPLICABLE and must not be read as zeros"
            if a.semantics != "buffered" else
            "under BUFFERED semantics the frames arrive after the drain, so the bounded "
            "columns are the honest upper edge"),
        "_semantics_of_the_run": {
            "selected": a.semantics,
            "buffered_file_line": "experiments/orchestration/live2/fleet/trace.py:1037-1047",
            "true_file_line": ("experiments/orchestration/live2/fleet/trace.py:1097 marks the "
                               "record for removal, :1135 removes it, and :1136-1210 "
                               "re-attributes the D2 header and corrects the cloud's cumulative "
                               "history and every later question's history (D273 (1))"),
            "verdict_for_the_default": "BUFFERED",
            "what_the_code_does": ("a victim's in-window `history_batch` has its offer time `t` "
                                   "set to the reconnect instant and NO record is deleted; a "
                                   "`recall_question` gains `t_offer` and keeps its ask time. The "
                                   "committed UplinkQueue (fleet/links.py:112-120) then takes "
                                   "t_start = max(t_offer, free_at)."),
            "consequence": ("the evidence is DELAYED, not lost, so every reading is also reported "
                            "bounded by the drain")},
        "cells": cells, "pairs": pairs,
        "ALL_ADDED_VICTIM_DOSES_ZERO_UNBOUNDED": bool(allzero_r1),
        "ALL_ADDED_VICTIM_DISTINCT_QUESTION_DOSES_ZERO": bool(allzero_q),
        "PROCEED_RULE": ("the ruling stops the design only if EVERY added-victim dose is zero at "
                         "both seeds. %s"
                         % ("EVERY DOSE IS ZERO: STOP AND REPORT." if allzero_r1 else
                            "At least one dose is non-zero, so scope A proceeds. The dose is a "
                            "WEAK-DOSE condition and must be labelled one wherever it is quoted: "
                            "read the DISTINCT question counts, not the instance counts.")),
        "ALL_ADDED_VICTIM_DOSES_ZERO_AFTER_DRAIN_BOUND": bool(allzero_bounded),
    }
    try:
        sys.path.insert(0, str(repo / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d262_dose_readings.py", model="none-cpu",
                                   device="flash_cpu", n=len(cells), args=a)
    except Exception as e:
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("%-14s %-22s %6s %6s %6s %6s %6s %9s %7s %9s" % (
        "pair", "added victims", "R1", "R1_q", "R2", "R2_q", "R3", "R1<drain", "in-win",
        "drain_s"))
    for k, v in pairs.items():
        print("%-14s %-22s %6d %6d %6d %6d %6d %9d %7d %9s" % (
            k, ",".join(v["added_victims"]), v["R1"], v["R1_DISTINCT_QUESTIONS"], v["R2"],
            v["R2_DISTINCT_QUESTIONS"], v["R3"], v["R1_before_drain"], v["asked_in_window"],
            sorted(set(str(x) for x in v["drain_s_after_reconnect"].values()))[0]))
    for k, v in pairs.items():
        for d in v["R1_per_question"]:
            print("   %-12s %s evidence[%.1f,%.1f] overlap %.2f s frames %d instances %d"
                  % (k, d["question_id"][:8], d["evidence_run_s"][0], d["evidence_run_s"][1],
                     d["overlap_with_window_s"], d["d2_frames_in_overlap"],
                     d.get("instances", 1)))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
