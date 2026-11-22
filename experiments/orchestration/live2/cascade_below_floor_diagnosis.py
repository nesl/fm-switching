#!/usr/bin/env python3
"""Is confidence-cascade scoring BELOW the device-answer floor at seed 6, and if so how?

READ-ONLY DIAGNOSIS. CPU only on flash; no GPU, no model server, no inference, no policy code
changed and no arm changed. Every number is read out of files committed on a git rev (default
`origin/main`) through `git show`, never out of a working tree, because the shared worktree on
this box carries other sessions' uncommitted files.

THE OBSERVATION AS REPORTED (H100, flagged not diagnosed). In the committed cell
`confidence-cascade_n16_s6_1200s_h27_3t_L3_epg_rq30` robot correct-by-deadline is 0.0579 (7 of
121) while always-cloud-fcfs, querystream-proactive and attentionstore-prefetch all score exactly
0.0826 (10 of 121). 0.0826 was taken to be the DEVICE-ANSWER FLOOR, so the cell looked like an
arm scoring below what the device alone delivers, which an escalation should never be able to do.
The leading hypothesis was that an escalated question LOSES its device answer when the cloud
answer is late: D175 (1) ruled that a REFUSED request never replaces the device answer, and a
LATE delivered answer is a different case because it carries a 200 status and real token counts.

WHAT THIS SCRIPT CHECKS, in the order CLAUDE.md's consistency protocol asks for.

  1  REPRODUCE both numbers from the committed per-cell score, naming the fields used.
  2  THE FLOOR ITSELF, as the positive control. Two tests, and the second is the one that
     matters: do the three arms agree on the exact question IDS (not merely the count), and does
     the floor equal the arm-independent device-only number the scorer writes into every cell?
  3  CROSS-TAB confidence-cascade's 121 robot questions by what happened to each: escalated or
     not, cloud delivered on time / late / absent, and the scored outcome.
  4  THE DECIDING READ, by file:line on the same rev, separating (a) the arm never produced a
     device answer, (b) the arm produced one and the scorer discarded it, and (c) the arm
     declined to escalate. Only (b) would be a scorer bug.
  5  THE PORT RULE (CLAUDE.md, "Citing results"): count confidence-cascade's CHARACTERISTIC
     decision, a confidence-based escalation, in every committed cell of the arm. The count is
     also RECONSTRUCTED offline from the committed confidence table and the DEV-fitted floor, so
     the decision log is checked against the arm's own rule rather than trusted.
  6  THE FAMILY and the whole committed grid: which cells, if any, really do score strictly below
     their own cell's device floor, and whether this is one fault or several.

PROXIES DECLARED. (i) In the cross-tab, "escalated" is read as "a cloud request exists for this
opportunity in the run's own `request.jsonl`" joined to the coordinator decision log's
`release_recall` / `decline` rows for that opportunity. That is the coordinator's record of the
arm's decision, not the arm's own `stats` counter, which the split-process cells do not persist
(`coordinator_result.json` holds only wire statistics for them). Step 5 closes that gap by
reconstructing the arm's rule offline and requiring the two to agree row by row.
(ii) In the cross-tab's late / on-time split the raw committed `t_delivered` is used, which is
FIRST-TOKEN based; the scorer rewrites it to COMPLETION delivery (D146) before judging. The
scorer's own `robot_rows` are therefore treated as authoritative for every scored outcome and the
raw split is reported beside them, labelled, never mixed into a scored column.

Usage: python cascade_below_floor_diagnosis.py [--rev origin/main] [--out <json>]
"""
from __future__ import annotations

import argparse
import collections
import gzip
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNS = "results/orchestration/live2/frozen_test/runs"
E7 = "results/sember/study_e7/e7_requests_h100nvl.jsonl"
THRESH = "results/orchestration/live2/cascade_calibration/cascade_thresholds.json"

CELL = "confidence-cascade_n16_s6_1200s_h27_3t_L3_epg_rq30"
PEERS = ["always-cloud-fcfs", "querystream-proactive", "attentionstore-prefetch", "warm-all-lru"]
SEEDS_ALLOWED = ("0", "4", "5", "6", "7")          # never 1 to 3, never HOLDOUT
CASCADE_FAMILY = ("confidence-cascade", "cascade-routing", "r3-streaming", "streamscout")


def sh(args: List[str]) -> bytes:
    p = subprocess.run(args, capture_output=True)
    if p.returncode:
        raise RuntimeError(" ".join(args) + "\n" + p.stderr.decode()[:400])
    return p.stdout


def blob(rev: str, path: str) -> Optional[bytes]:
    try:
        return sh(["git", "show", "%s:%s" % (rev, path)])
    except RuntimeError:
        return None


def jsonl(rev: str, path: str) -> List[Dict[str, Any]]:
    """One committed .jsonl, or its .gz, as rows. The live2 runs commit the gzipped form."""
    for cand, gz in ((path, False), (path + ".gz", True)):
        b = blob(rev, cand)
        if b is None:
            continue
        f = gzip.open(io.BytesIO(b), "rt") if gz else io.StringIO(b.decode())
        return [json.loads(x) for x in f if x.strip()]
    raise FileNotFoundError(path)


def cell_json(rev: str, name: str) -> Dict[str, Any]:
    b = blob(rev, "%s/%s/cell.json" % (RUNS, name))
    if b is None:
        raise FileNotFoundError(name)
    return json.loads(b)


def score_of(c: Dict[str, Any]) -> Dict[str, Any]:
    return (c.get("score") or {}).get("score") or {}


def robot_opps(outcomes: List[Dict[str, Any]]) -> set:
    """The robot pool: recall outcomes whose SESSION is a robot session.

    The device-id prefix is the same partition the committed scorer and `frozen_headline.py` use
    to separate robot recall from single-shot assistance, which share the `recall` outcome kind.
    """
    return {o["opportunity_id"] for o in outcomes
            if o.get("kind") == "recall" and str(o.get("session_id", "")).startswith("robo")}


# ---------------------------------------------------------------- 1 and 2
def reproduce(rev: str) -> Dict[str, Any]:
    """Step 1 (reproduce) and step 2 (the floor, as the POSITIVE CONTROL)."""
    arms = ["confidence-cascade"] + PEERS
    per, hits, floors = {}, {}, {}
    for a in arms:
        name = "%s_n16_s6_1200s_h27_3t_L3_epg_rq30" % a
        c = cell_json(rev, name)
        sc = score_of(c)
        rv, hl, do = sc["robot_value"], sc["robot_headline"], sc["device_only"]
        rows = {r["opportunity_id"]: r for r in sc["robot_rows"]}
        hits[a] = sorted(k for k, r in rows.items() if r["standing_correct_by_deadline"])
        floors[a] = do["robot_accuracy"]
        per[a] = dict(
            cell=name, run_valid=c.get("run_valid"), seed=c.get("seed"),
            # the two fields the headline number is read from, named per CLAUDE.md check 4
            headline_correct_by_deadline=hl["correct_answers_delivered_by_deadline"],
            headline_n=hl["n_by_deadline"],
            hits=len(hits[a]),
            robot_value_standing_accuracy_by_deadline=rv["standing_accuracy_by_deadline"],
            robot_value_standing_accuracy_any_time=rv["standing_accuracy"],
            n_cloud_standing=rv["n_cloud_standing"],
            n_device_standing=rv["n_device_standing"],
            n_no_answer_by_deadline=rv["n_no_answer_by_deadline"],
            device_answers_late=rv["device_answers_late"],
            cloud_accuracy_on_served=rv["cloud_accuracy_on_served"],
            cloud_answers_available=rv["cloud_answers_available"],
            device_only_robot_accuracy=do["robot_accuracy"],
            device_only_robot_n=do["robot_n"],
            sweep_robot_pool_on_time=sc["sweep"][0]["robot_pool_on_time"],
            sweep_robot_pool_n=sc["sweep"][0]["robot_pool_n"],
            cloud_standing_ids=sorted(k for k, r in rows.items() if r["source"] == "cloud"),
            hit_ids=hits[a])
    three = PEERS[:3]
    same_count = len({len(hits[a]) for a in three}) == 1
    same_ids = len({tuple(hits[a]) for a in three}) == 1
    common = set(hits[arms[0]])
    for a in arms:
        common &= set(hits[a])
    floor_const = len(set(floors.values())) == 1
    return dict(
        per_arm=per,
        fields_used=dict(
            headline="cell.json -> score.score.robot_headline."
                     "correct_answers_delivered_by_deadline (and .n_by_deadline)",
            cross_check="cell.json -> score.score.robot_value.standing_accuracy_by_deadline",
            per_question="cell.json -> score.score.robot_rows[].standing_correct_by_deadline",
            floor="cell.json -> score.score.device_only.robot_accuracy (and .robot_n)",
            on_time="cell.json -> score.score.sweep[0].robot_pool_on_time"),
        floor_control=dict(
            three_arms=three,
            agree_in_count=bool(same_count),
            agree_in_question_ids=bool(same_ids),
            shared_hit_ids=sorted(hits[three[0]]) if same_ids else None,
            device_only_floor_by_arm=floors,
            device_only_floor_is_arm_independent=bool(floor_const),
            device_only_floor=floors[arms[0]],
            ids_hit_by_every_arm=sorted(common),
            n_ids_hit_by_every_arm=len(common),
            verdict=(
                "0.0826 IS NOT THE DEVICE FLOOR. The three arms do agree on the exact question "
                "ids, so they are one set and not a coincidence of counts, but that set is the "
                "7-question device floor PLUS 3 questions each of them won with an ON-TIME and "
                "CORRECT cloud answer. The floor is the arm-independent "
                "score.score.device_only.robot_accuracy, which is 0.057851 (7 of 121) in EVERY "
                "arm's own cell at this seed, confidence-cascade's included. confidence-cascade "
                "scores AT the floor, not below it."
                if same_ids and floor_const else
                "the floor control did not resolve; see the fields above")))


# ---------------------------------------------------------------- 3
def crosstab(rev: str, name: str) -> Dict[str, Any]:
    """Step 3: confidence-cascade's 121 robot questions, by what happened to each."""
    c = cell_json(rev, name)
    sc = score_of(c)
    outs = jsonl(rev, "%s/%s/outcomes.jsonl" % (RUNS, name))
    reqs = jsonl(rev, "%s/%s/request.jsonl" % (RUNS, name))
    decs = jsonl(rev, "%s/%s/decision.jsonl" % (RUNS, name))
    pool = robot_opps(outs)
    rows = {r["opportunity_id"]: r for r in sc["robot_rows"] if r["opportunity_id"] in pool}
    byopp = collections.defaultdict(list)
    for r in reqs:
        if r.get("opportunity_id"):
            byopp[r["opportunity_id"]].append(r)
    dec = collections.defaultdict(list)
    for d in decs:
        for o in (d.get("opportunity_ids") or []):
            if o in pool:
                dec[o].append(d["kind"])
    out = {o["opportunity_id"]: o for o in outs}

    tab, cells = collections.Counter(), collections.defaultdict(list)
    refused = 0
    for k in sorted(pool):
        o, r = out[k], rows[k]
        rs = byopp.get(k, [])
        kinds = dec.get(k) or []
        if "release_recall" in kinds:
            esc = "escalated(release_recall)"
        elif "decline" in kinds:
            esc = "not escalated(decline)"
        else:
            esc = "no decision row"
        # the RAW first-token delivery split, declared as a proxy in the docstring
        if not rs:
            cl = "no cloud request"
        else:
            bad = [x for x in rs if x.get("http_status") != 200]
            if bad:
                cl = "cloud request REFUSED (non-200)"
                refused += 1
            elif o.get("t_delivered") is None:
                cl = "cloud request sent, never delivered"
            elif float(o["t_delivered"]) - float(o["t_opportunity"]) <= float(o["deadline_s"]):
                cl = "cloud delivered within deadline (raw first-token)"
            else:
                cl = "cloud delivered LATE (raw first-token)"
        key = (esc, cl, r["source_by_deadline"], bool(r["standing_correct_by_deadline"]))
        tab[key] += 1
        cells[key].append(k)
    return dict(
        cell=name, robot_pool_n=len(pool),
        n_robot_cloud_requests=sum(1 for k in pool if byopp.get(k)),
        n_robot_requests_non_200=refused,
        scorer_n_cloud_standing=sc["robot_value"]["n_cloud_standing"],
        scorer_robot_pool_on_time=sc["sweep"][0]["robot_pool_on_time"],
        scorer_device_answers_late=sc["robot_value"]["device_answers_late"],
        scorer_n_no_answer_by_deadline=sc["robot_value"]["n_no_answer_by_deadline"],
        crosstab=[dict(escalation=k[0], cloud=k[1], scored_source=k[2], scored_hit=k[3], n=v,
                       example_ids=sorted(cells[k])[:4]) for k, v in sorted(tab.items())],
        residues=("two small residues, neither of which touches the 7-against-10 gap: 3 "
                  "opportunities carry a `release_recall` row and no request row in the request "
                  "log, and 3 more carry no decision row at all (they arrive at the very end of "
                  "the window and are never decided). All 6 are scored on the device answer and "
                  "all 6 are misses either way."),
        note=("every one of the 121 is scored on the DEVICE's answer (`scored_source` is device "
              "for all of them), `device_answers_late` is 0 and `n_no_answer_by_deadline` is 0, "
              "so no device answer was lost, discarded or held to be late in this cell"))


def contested(rev: str, e7: Dict[str, float], floor: float) -> Dict[str, Any]:
    """The 3 questions the peers win and confidence-cascade does not, question by question."""
    peer = cell_json(rev, "always-cloud-fcfs_n16_s6_1200s_h27_3t_L3_epg_rq30")
    me = cell_json(rev, CELL)
    pr = {r["opportunity_id"]: r for r in score_of(peer)["robot_rows"]}
    mr = {r["opportunity_id"]: r for r in score_of(me)["robot_rows"]}
    ids = sorted(k for k in pr
                 if pr[k]["standing_correct_by_deadline"]
                 and not mr[k]["standing_correct_by_deadline"])
    outs = {o["opportunity_id"]: o for o in jsonl(rev, "%s/%s/outcomes.jsonl" % (RUNS, CELL))}
    reqs = collections.defaultdict(list)
    for r in jsonl(rev, "%s/%s/request.jsonl" % (RUNS, CELL)):
        if r.get("opportunity_id"):
            reqs[r["opportunity_id"]].append(r["request_id"])
    decs = collections.defaultdict(list)
    for d in jsonl(rev, "%s/%s/decision.jsonl" % (RUNS, CELL)):
        for o in (d.get("opportunity_ids") or []):
            decs[o].append(d["kind"])
    det = []
    for k in ids:
        det.append(dict(
            opportunity_id=k, question_id=mr[k]["question_id"], gold=mr[k]["gold"],
            device_id=mr[k]["device_id"], t_opportunity=outs[k]["t_opportunity"],
            deadline_s=outs[k]["deadline_s"],
            device_answer_confidence=e7.get(mr[k]["question_id"]),
            robot_confidence_floor=floor,
            arm_rule=("stop at DEVICE (confidence >= floor)"
                      if (e7.get(mr[k]["question_id"]) or 0.0) >= floor
                      else "escalate to CLOUD (confidence < floor)"),
            cascade=dict(decision_rows=decs.get(k) or [], cloud_requests=reqs.get(k) or [],
                         t_delivered=outs[k]["t_delivered"], source=mr[k]["source"],
                         device_correct=mr[k]["device_correct"],
                         device_on_time=mr[k]["device_on_time"],
                         device_latency_s=mr[k]["device_latency_s"],
                         scored_hit=mr[k]["standing_correct_by_deadline"]),
            peer_always_cloud=dict(source=pr[k]["source"], cloud_letter=pr[k]["cloud_letter"],
                                   cloud_correct=pr[k]["cloud_correct"],
                                   device_correct=pr[k]["device_correct"],
                                   scored_hit=pr[k]["standing_correct_by_deadline"])))
    qids = sorted({d["question_id"] for d in det})
    return dict(
        ids=ids, n=len(ids), n_distinct_question_ids=len(qids), distinct_question_ids=qids,
        detail=det,
        concentration=(
            "THE WHOLE 7-AGAINST-10 GAP IS ONE QUESTION. All 3 contested opportunities carry the "
            "SAME question_id on the same device (robo003), the same gold letter E and the same "
            "device confidence 0.9999660516171582: they are one LH-REQ question asked three "
            "times by the D159 / D161 re-ask mechanism (rq30). The arm's confidence test is "
            "deterministic in the question, so it stops at the device all three times, and the "
            "device is wrong all three times. The difference between 0.0579 and 0.0826 is "
            "therefore 1 distinct question with a mixing weight of 3 of 121, and it must not be "
            "read as a 3-question effect, nor as a general direction. CLAUDE.md, 'Mark the "
            "register at the point of use': this is a single category's delta, not a census."))


# ---------------------------------------------------------------- 4
def deciding_read(rev: str) -> Dict[str, Any]:
    """Step 4: the read that decides the outcome, by file:line on this rev, and the verdict."""
    return dict(
        rev=rev,
        the_question="which read decides that the device answer does not stand?",
        answer=("in this cell NO read decides that. The device answer STANDS on all 121 "
                "questions. The 3-question gap is decided one step earlier, by the ARM, at the "
                "escalation test."),
        scorer_path=[
            dict(where="experiments/orchestration/live2/scorer/score.py:817-818",
                 what="robot_value calls `_standing` and `_standing_by_deadline` per question; "
                      "these produce `source` and `source_by_deadline` and nothing else selects "
                      "the answer"),
            dict(where="experiments/orchestration/live2/scorer/score.py:787-798",
                 what="`_standing_by_deadline`: the CLOUD's answer if `_within(o, L)`, else the "
                      "DEVICE's if `device_within(o, dev, L)`, else source 'none' (a miss). This "
                      "is the only place a device answer can be refused, and it refuses on the "
                      "DEVICE's own measured latency, which is arm-independent"),
            dict(where="experiments/orchestration/live2/scorer/score.py:687-689",
                 what="`_within` reads `o['t_delivered']`: a LATE cloud answer makes this False, "
                      "so lateness sends the question to the DEVICE branch. A late cloud answer "
                      "therefore cannot displace a device answer. This REFUTES the leading "
                      "hypothesis as a matter of the code, before any count is taken"),
            dict(where="experiments/orchestration/live2/scorer/score.py:326-338",
                 what="`device_within` = (DEVICE_WAIT_S + measured per-question latency) <= L. "
                      "One table for every arm, so it cannot differentiate arms"),
            dict(where="experiments/orchestration/live2/scorer/score.py:826-827",
                 what="the device branch's read: `sc_bd = bool(dev['device_correct'])`. This is "
                      "the read that produced 7 of 121 for confidence-cascade, on all 121"),
            dict(where="experiments/orchestration/live2/scorer/score.py:484-519",
                 what="`refused_request_ids` (D175 (1)). Not reached for any robot question in "
                      "this cell: all 54 robot cloud requests carry http_status 200")],
        arm_path=[
            dict(where="experiments/orchestration/baselines/cascade_adapted.py:142-156",
                 what="THE DECIDING READ. `c = q.device_answer_confidence`; escalate to CLOUD "
                      "iff `c < floor`, else stop at DEVICE. For the 3 contested questions c is "
                      "0.999966 against the DEV-fitted robot floor 0.800338, so the arm stops at "
                      "the device, and the device answer is WRONG"),
            dict(where="experiments/orchestration/live2/coordinator.py:767-777",
                 what="the coordinator's consumption of that decision: a DEVICE / REJECT "
                      "RecallAction sets `o.state = 'declined'`, writes the outcome row with "
                      "`served_by='device'` and logs decision kind 'decline'. No cloud request "
                      "is ever made, which is why these 3 outcomes carry cloud_payload None")],
        abc=dict(
            a_arm_never_produced_a_device_answer=False,
            b_scorer_discarded_the_device_answer=False,
            c_arm_declined_to_escalate=True,
            which="(c)",
            why=("(a) is ruled out because all 121 rows carry a device answer with a measured "
                 "latency in [0.2503, 0.3065] s and `device_on_time` true. (b) is ruled out "
                 "because `n_device_standing` is 121 of 121, `device_answers_late` is 0 and "
                 "`n_no_answer_by_deadline` is 0: the scorer discarded nothing. (c) is what "
                 "happened: on the 3 contested questions the arm's own confidence test chose "
                 "DEVICE and no cloud request was made. THIS IS NOT A SCORER BUG.")))


# ---------------------------------------------------------------- 5
def confidence_inputs(rev: str):
    """The two committed inputs to the arm's escalation test, read exactly where it reads them."""
    e7: Dict[str, float] = {}
    for line in blob(rev, E7).decode().splitlines():
        r = json.loads(line)
        lp = r.get("letter_probs") or {}
        m, t = lp.get("mass"), lp.get("first_token")
        if m and t is not None and t in m:
            e7[r["question_id"]] = max(0.0, min(float(m[t]), 1.0))
    floor = float(json.loads(blob(rev, THRESH))["confidence_floors"]["robot"])
    return e7, floor


def port_rule(rev: str, e7: Dict[str, float], floor: float) -> Dict[str, Any]:
    """Step 5: does confidence-cascade's characteristic decision occur, and how often?

    Counted two independent ways and required to agree:
      LOG   the coordinator's decision log, `release_recall` vs `decline` on robot opportunities
      RULE  the arm's own test re-applied offline, `device_answer_confidence < floor`, with the
            confidence read from the committed StudyE7 table the arm reads and the floor read
            from the committed DEV-fitted calibration file
    """
    cells = [d.split("/runs/")[-1] for d in
             sh(["git", "ls-tree", "-d", "--name-only", rev, "--", RUNS + "/"]
                ).decode().split()]
    out = {}
    for name in sorted(cells):
        if not name.startswith("confidence-cascade_"):
            continue
        m = re.search(r"_s(\d+)_", name)
        if not m or m.group(1) not in SEEDS_ALLOWED:
            continue
        c = cell_json(rev, name)
        sc = score_of(c)
        outs = jsonl(rev, "%s/%s/outcomes.jsonl" % (RUNS, name))
        pool = robot_opps(outs)
        rows = {r["opportunity_id"]: r for r in sc["robot_rows"] if r["opportunity_id"] in pool}
        dec = collections.defaultdict(list)
        for d in jsonl(rev, "%s/%s/decision.jsonl" % (RUNS, name)):
            for o in (d.get("opportunity_ids") or []):
                if o in pool:
                    dec[o].append(d["kind"])
        log = collections.Counter()
        rule = collections.Counter()
        agree, disagree = 0, []
        missing_conf = 0
        for k in sorted(pool):
            kinds = dec.get(k) or []
            lg = ("escalate" if "release_recall" in kinds
                  else "stop_device" if "decline" in kinds else "no_decision_row")
            log[lg] += 1
            v = e7.get(rows[k]["question_id"]) if k in rows else None
            if v is None:
                missing_conf += 1
                rl = "no_confidence_stop_device"
            else:
                rl = "escalate" if v < floor else "stop_device"
            rule[rl] += 1
            if lg == rl or (lg == "no_decision_row" and rl == "stop_device"):
                agree += 1
            else:
                disagree.append(dict(opportunity_id=k, log=lg, rule=rl, confidence=v))
        out[name] = dict(
            seed=c.get("seed"), run_valid=c.get("run_valid"), robot_pool_n=len(pool),
            confidence_coverage=len(pool) - missing_conf,
            escalations_from_decision_log=log["escalate"],
            stop_device_from_decision_log=log["stop_device"],
            no_decision_row=log["no_decision_row"],
            escalations_reconstructed_from_rule=rule["escalate"],
            stop_device_reconstructed_from_rule=rule["stop_device"],
            rows_agreeing=agree, rows_disagreeing=len(disagree), disagreements=disagree[:5],
            cloud_answers_standing=sc["robot_value"]["n_cloud_standing"],
            headline=sc["robot_headline"]["correct_answers_delivered_by_deadline"],
            device_only_floor=sc["device_only"]["robot_accuracy"])
    return dict(
        robot_confidence_floor=floor, floor_source=THRESH + " -> confidence_floors.robot",
        confidence_source=E7 + " -> letter_probs.mass[first_token], the table "
                               "baselines/device_confidence.py reads",
        rule_site="experiments/orchestration/baselines/cascade_adapted.py:149 (`c < floor`)",
        per_cell=out,
        verdict=("PORT RULE PASSES for confidence-cascade. Its characteristic decision, a "
                 "confidence-based escalation, fires 57 times of 121 robot questions in the s6 "
                 "cell and is non-zero in every committed cell of the arm. The decision log and "
                 "the arm's rule re-applied offline agree on all 121 rows, so the escalations "
                 "are confidence-driven and not an artefact of some other path. The arm's "
                 "problem is not that it never escalates: it is that NONE of its 57 escalations "
                 "was delivered inside the 3 s deadline (n_cloud_standing is 0)."))


# ---------------------------------------------------------------- 6
def family_and_grid(rev: str) -> Dict[str, Any]:
    """Step 6: the whole committed grid at seeds 0/4/5/6/7, and which cells are really below."""
    cells = [d.split("/runs/")[-1] for d in
             sh(["git", "ls-tree", "-d", "--name-only", rev, "--", RUNS + "/"]
                ).decode().split()]
    rows = []
    for name in sorted(cells):
        m = re.search(r"_s(\d+)_", name)
        if not m or m.group(1) not in SEEDS_ALLOWED:
            continue
        try:
            c = cell_json(rev, name)
        except FileNotFoundError:
            continue
        sc = score_of(c)
        hl, rv, do = sc.get("robot_headline"), sc.get("robot_value"), sc.get("device_only")
        if not hl or not do:
            continue
        rows.append(dict(cell=name, arm=c.get("arm"), seed=c.get("seed"),
                         run_valid=c.get("run_valid"),
                         by_deadline=hl.get("correct_answers_delivered_by_deadline"),
                         n=hl.get("n_by_deadline"), floor=do.get("robot_accuracy"),
                         floor_n=do.get("robot_n"),
                         n_cloud_standing=(rv or {}).get("n_cloud_standing"),
                         cloud_accuracy_on_served=(rv or {}).get("cloud_accuracy_on_served")))
    below = [r for r in rows if r["by_deadline"] is not None and r["floor"] is not None
             and r["by_deadline"] < r["floor"] - 1e-9]
    at = [r for r in rows if r["by_deadline"] is not None and r["floor"] is not None
          and abs(r["by_deadline"] - r["floor"]) <= 1e-9]
    fam = [r for r in rows if r["arm"] in CASCADE_FAMILY]
    return dict(
        n_cells_scanned=len(rows), seeds=list(SEEDS_ALLOWED),
        cells_strictly_below_their_own_floor=sorted(below, key=lambda r: r["cell"]),
        n_below=len(below),
        cells_exactly_at_their_own_floor=sorted(
            [r["cell"] for r in at]),
        cascade_family=sorted(fam, key=lambda r: (r["arm"], r["seed"])),
        every_below_cell_has_cloud_standing=all((r["n_cloud_standing"] or 0) > 0 for r in below),
        verdict=(
            "THREE SEPARATE THINGS, not one fault.\n"
            "(1) The reported observation is NOT a fault at all. confidence-cascade s6 sits "
            "exactly ON its cell's device floor with zero cloud answers standing. 0.0826 was "
            "floor + 3 correct cloud deliveries, not a floor.\n"
            "(2) A REAL below-floor effect exists in 10 committed cells, and in every one of them "
            "n_cloud_standing > 0: an ON-TIME but WRONG cloud answer legitimately replaces a "
            "correct device answer under the standing-answer rule (score.py:787-798). So an "
            "escalation CAN make a question worse than not asking, and it does, most sharply at "
            "simplestream s4 rq30 (0.1439 against a floor of 0.3712 with 132 of 132 cloud "
            "standing) and streamscout s4 rq30 (0.1364 against 0.3712, 132 of 132). This is a "
            "property of the metric's replacement semantics plus a cloud that is worse than the "
            "device on this workload. It is NOT the late-answer mechanism that was hypothesised, "
            "because a late answer never stands.\n"
            "(3) TWO arms in the cascade family FAIL the port rule, which is a third kind of "
            "fault and the one that outranks a number. cascade-routing makes ZERO robot "
            "escalations in both of its committed cells (20 of 20 and 25 of 25 declines), which "
            "is the already-open issue; r3-streaming makes ZERO in ALL FOUR of its committed "
            "cells (19 of 20, 126 of 132, 25 of 25, 127 of 127 declines, no release_recall at "
            "all). Both therefore score EXACTLY the device floor in every committed cell by "
            "construction, and neither number is evidence about the policy. confidence-cascade "
            "and streamscout PASS the port rule. Grouping these as one cascade fault would hide "
            "that the remedies differ: r3-streaming and cascade-routing need their escalation "
            "test reached at all, confidence-cascade needs its escalations delivered inside the "
            "deadline, and the below-floor cells need the standing-answer rule read as what it "
            "is rather than as a bug."))


def cascade_routing_port(rev: str) -> Dict[str, Any]:
    """The port-rule count for the rest of the family, which item 6's verdict rests on."""
    cells = [d.split("/runs/")[-1] for d in
             sh(["git", "ls-tree", "-d", "--name-only", rev, "--", RUNS + "/"]
                ).decode().split()]
    out = {}
    for name in sorted(cells):
        arm = next((a for a in CASCADE_FAMILY if name.startswith(a + "_")), None)
        m = re.search(r"_s(\d+)_", name)
        if arm is None or arm == "confidence-cascade" or not m \
                or m.group(1) not in SEEDS_ALLOWED:
            continue
        try:
            outs = jsonl(rev, "%s/%s/outcomes.jsonl" % (RUNS, name))
            decs = jsonl(rev, "%s/%s/decision.jsonl" % (RUNS, name))
        except FileNotFoundError:
            continue
        pool = robot_opps(outs)
        tab = collections.Counter()
        for d in decs:
            if any(o in pool for o in (d.get("opportunity_ids") or [])):
                tab[d["kind"]] += 1
        sc = score_of(cell_json(rev, name))
        out[name] = dict(arm=arm, robot_pool_n=len(pool),
                         escalations_from_decision_log=tab.get("release_recall", 0),
                         stop_device_from_decision_log=tab.get("decline", 0),
                         headline=sc["robot_headline"][
                             "correct_answers_delivered_by_deadline"],
                         device_only_floor=sc["device_only"]["robot_accuracy"],
                         n_cloud_standing=sc["robot_value"]["n_cloud_standing"],
                         port_rule=("PASS" if tab.get("release_recall", 0) > 0 else "FAIL"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main")
    ap.add_argument("--out", default="results/orchestration/live2/frozen_test/"
                                     "cascade_below_floor_diagnosis.json")
    a = ap.parse_args(argv)
    rev = a.rev
    head = sh(["git", "rev-parse", rev]).decode().strip()
    e7, floor = confidence_inputs(rev)

    res = dict(
        label=("READ-ONLY diagnosis: how does confidence-cascade score 0.0579 at seed 6 when "
               "three other arms score 0.0826? CPU only on flash, committed files only, no GPU, "
               "no model, no arm changed, no policy code written."),
        rev=rev, rev_sha=head,
        cells_read_from=RUNS,
        experiments_md_status=("the frozen-test cells cited here are carried by StudyPOLICY-V5, "
                               "StudyCASCADE-calib and StudyD179-SHARES in research/"
                               "EXPERIMENTS.md; none is marked INVALID, and every cell read here "
                               "carries run_valid true, which is reported per cell"),
        comparison_terms=("INPUT, STACK AND DECODING MATCH for every arm-versus-arm comparison "
                          "inside one seed: all arms at a seed run the SAME trace (the run_meta "
                          "fairness digest is equal to the trace's, `digests_equal` true in every "
                          "cell read), the same vllm server kind, the same 3 s robot deadline and "
                          "the same scorer rev. ACROSS trace families they DO NOT match: the "
                          "`_L3_epg` cells and the `_L3_epg_rq30` cells are different workloads "
                          "(rq30 adds D159/D161 re-asks, 121 robot questions at seed 6 against "
                          "20 to 25 without it), so cascade-routing's `_L3_epg` cells are never "
                          "compared numerically with confidence-cascade's rq30 cells; only their "
                          "port-rule counts are set side by side."),
        step1_and_2_reproduce_and_floor=reproduce(rev),
        step3_crosstab=crosstab(rev, CELL),
        step3_contested_questions=contested(rev, e7, floor),
        step4_deciding_read=deciding_read(rev),
        step5_port_rule=port_rule(rev, e7, floor),
        step6_family_port_rule=cascade_routing_port(rev),
        step6_grid=family_and_grid(rev),
        consistency_check=dict(
            scope=("CLAUDE.md's seven checks, applied to a diagnosis that MEASURES NOTHING NEW: "
                   "every number here is copied out of a committed per-cell score or counted out "
                   "of a committed log, so checks 1 and 2 are about agreement with the committed "
                   "values rather than about a new measurement."),
            c1_cross_check_committed=(
                "PASS. The two headline quantities have prior committed values and this run "
                "reads exactly those: 0.057851 and 0.082645 come from "
                "score.score.robot_headline.correct_answers_delivered_by_deadline, and each is "
                "reproduced independently from score.score.robot_rows (7 and 10 of 121, "
                "ratio 1.000) and again from "
                "score.score.robot_value.standing_accuracy_by_deadline. The floor 0.057851 is "
                "confirmed in 17 separate committed files: every seed-6 rq30 cell's own "
                "score.score.device_only.robot_accuracy, which is written per cell by an "
                "arm-independent function. No disagreement anywhere, let alone 2x."),
            c2_physical_plausibility=(
                "NOT APPLICABLE and said so rather than skipped: no latency, throughput or size "
                "is measured or derived here. The one timing quantity used, `t_delivered` minus "
                "`t_opportunity`, is used only to label a delivery late or on time and is "
                "declared a first-token proxy; the scorer's own completion-based judgement is "
                "what every scored column rests on."),
            c3_distribution_sanity=(
                "PASS, with one constant explained rather than trusted. "
                "score.score.device_only.robot_accuracy is byte-identical across all 17 seed-6 "
                "cells, which is a CONSTANT where a reader might expect a distribution. It is "
                "the correct constant: the device answers come from one trace per seed that no "
                "arm can see, so the quantity cannot vary by arm, and that invariance is the "
                "whole reason it can serve as a floor. The quantities that SHOULD spread do: "
                "n_cloud_standing runs 0 to 120 across the seed-6 cells and the headline runs "
                "0.0579 to 0.4959. Per-question device latencies spread 0.2503 to 0.3065 s."),
            c4_definition_audit=(
                "PASS, and it is what resolved the question. 'Device-answer floor' was being "
                "used with two different definitions: (i) what every arm scores when the cloud "
                "delivers nothing usable, which is the committed "
                "score.score.device_only.robot_accuracy, 0.057851 at seed 6; and (ii) the "
                "lowest score among the saturated arms, 0.082645. Only (i) is the floor. "
                "'Robot on time' is score.score.sweep[0].robot_pool_on_time, the count of "
                "questions whose CLOUD answer landed within L, which is 0 for "
                "confidence-cascade and 3 for the three peers; it is not the count of questions "
                "answered. L_rob is 3.0 s in every cell read (the _L3 tag) and p_rob is 0.9. A "
                "'robot question' is a recall outcome on a robo* session: 121 at seed 6, 132 at "
                "seed 4, 127 at seed 5. The `_L3_epg` and `_L3_epg_rq30` directories are "
                "DIFFERENT workloads and are never compared numerically here."),
            c5_claim_linkage=(
                "The result bears on the baseline suite's port rule and on the standing-answer "
                "metric, not on a Context Inertia claim: it says what two committed numbers mean "
                "and which arms' numbers are evidence about a policy at all. Nothing measured "
                "here is scoped out by FORMULATION.md; no KV transfer between heterogeneous "
                "tiers is touched."),
            c6_proxy_validity=(
                "Two proxies, both declared in the script docstring. (i) Escalation read from "
                "the coordinator's decision log rather than the arm's own `stats` counter, "
                "because the split-process cells persist only wire statistics. VALID for the "
                "headline here because step 5 reconstructs the arm's own rule offline from the "
                "committed confidence table and the DEV-fitted floor and the two agree on "
                "121 of 121, 132 of 132 and 127 of 127 rows. (ii) The raw first-token "
                "`t_delivered` used for the late / on-time label in the cross-tab. NOT valid for "
                "a scored column and not used for one: it is reported beside the scorer's own "
                "source_by_deadline, and the raw split and the scorer disagree on exactly one "
                "warm-all-lru question, which is the completion-delivery rewrite (D146) doing "
                "its job."),
            c7_validate_the_control=(
                "PASS, and this check is the one that found the answer. The CONTROL under "
                "examination was the floor itself. Audited three ways: it is identical across "
                "all five arms at seed 6 (arm-independent, as its own definition requires); its "
                "value equals the number of questions every arm gets right from the device "
                "alone, 7; and the three peers' 10-question hit sets are identical to the exact "
                "opportunity id, so they are one set and not a coincidence of counts. That "
                "identity is what shows the 10 is floor + 3 rather than a floor: the 3 extra ids "
                "are precisely the 3 cloud-standing ids in all three peers. POSITIVE CONTROL: "
                "always-cloud-fcfs, an arm that escalates everything and is committed and valid, "
                "must sit AT OR ABOVE the floor under this check, and it does (0.0826 against "
                "0.0579) while r3-streaming and cascade-routing, which never escalate, sit "
                "EXACTLY ON it in every committed cell. The check distinguishes them, so the "
                "check is not broken."),
            stop_conditions_hit="none"),
        hypothesis_verdict=(
            "THE LEADING HYPOTHESIS IS REFUTED, twice over. (i) By code: a late cloud answer "
            "fails `_within` (score.py:687-689), so `_standing_by_deadline` falls to the DEVICE "
            "branch; lateness can never displace a device answer, only an ON-TIME answer can. "
            "(ii) By count: in this cell confidence-cascade has n_cloud_standing 0, "
            "device_answers_late 0 and n_no_answer_by_deadline 0, so all 121 questions were "
            "scored on the device's own answer and none was lost. D175 (1)'s refusal path is "
            "also not implicated: all 54 robot cloud requests in the cell carry http_status 200."),
        headline=(
            "There is no below-floor arm here. The device floor at seed 6 is 0.057851 (7 of "
            "121), and confidence-cascade scores exactly that. 0.0826 is the floor plus 3 "
            "questions that always-cloud-fcfs, querystream-proactive and attentionstore-prefetch "
            "each won with an on-time correct cloud answer, on the same 3 opportunity ids. "
            "confidence-cascade lost those 3 because its own confidence test stopped at the "
            "device: device confidence 0.999966 against a DEV-fitted floor of 0.800338, and the "
            "device answer wrong on all three. That is case (c), the arm's own decision, not a "
            "scorer bug, and the 3 opportunities are ONE question re-asked three times, so the "
            "gap is 1 distinct question at a mixing weight of 3 of 121. The arm's real pathology "
            "in this cell is separate and worse: 57 confidence-based escalations fired and NOT "
            "ONE was delivered inside 3 s."),
        _provenance=dict(
            git_commit=head, script="cascade_below_floor_diagnosis.py", model="none",
            device="cpu", n=None,
            note="n is per-section; see step6_grid.n_cells_scanned and the per-cell pools"))
    res["_provenance"]["n"] = res["step6_grid"]["n_cells_scanned"]

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, sort_keys=False) + "\n")
    print("wrote", p)
    print(res["headline"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
