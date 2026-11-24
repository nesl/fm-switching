#!/usr/bin/env python3
"""StudyNET-QDELTA: does the absent question-time frame delta (D150 SYNC (2)) affect any
committed main-operating-point result?

READ-ONLY over committed artefacts. CPU only. No cell is run, no server is touched.

THE QUESTION. D150 SYNC (2) says "a question carries any frames the cloud lacks (on-demand
delta)". StudyNET-TIER1 (N1) recorded that this is ABSENT: the only query-side upload is
`QUESTION_TEXT_B = 1200` bytes of text (`fleet/emulator.py:73`, `:417`). An absent on-demand
delta can only change a result if, at the moment a unit is asked, the cloud is referencing a
frame whose upload had not finished. This module measures exactly that, per unit, over the
committed 1x-memory uniform-link cells of the `_L3_epg_rq30` tag.

WHAT IS OBSERVED AND WHAT IS CONSTRUCTED, per the brief.

  OBSERVED, read straight out of the committed cell:
    - `outcomes.jsonl`  `t_opportunity`, `t_frame_arrive`, `uplink_queue_s`, `play_id`,
      `t_local`, `clip`, `question_id`, `kind`, `device_id`, `session_id`.
      `t_frame_arrive` IS the emulator's `tr.t_arrive` (`fleet/links.py:117`), persisted per
      monitor opportunity at `fleet/emulator.py:387` / `:407` and written out at
      `fleet/emulator.py:621`. So for DASHCAM frames the completion time is OBSERVED and
      nothing is reconstructed.
    - `request.jsonl`  `mm_uuids` (the exact frame set the cloud request carried) and
      `t_submit`. This is the definition of "references": not a derived episode, the literal
      multimodal payload of the request that served the unit.
    - `run_meta.json`  per-device `uplink` {n, busy_s, queue_p50, queue_p99, queue_max}, which
      is `links.UplinkQueue.stats()`.

  CONSTRUCTED, from the committed link arithmetic only:
    - HISTORY frame completion times (robot per-frame uploads and the single-shot image).
      `links.UplinkQueue.log` is not persisted per transfer; only `stats()` is. So a history
      frame's completion is reconstructed as
          t_offer + queue + serialise(nbytes) + RTT/2
      with serialise and RTT/2 exactly as `fleet/links.py:59` / `:48` compute them, the queue
      term taken from the FIFO ordering of the trace's own record order (see below), and
      nbytes = E10A_SEMBER_Q88_D2_MEDIAN_B = 24,570 B (`fleet/data_sources.py:67`), which is a
      committed constant for both the robot history frame and the single-shot image.
    - ROBOT `t_ask` in session time, read from the committed `sember_mcq.jsonl`
      `question_time`. The frame's absolute capture time is never needed: the gap collapses to
          (x_max - t_ask) + serialise + RTT/2 - (the ask-side terms)
      because the session origin t0 cancels between the frame and the question of the same
      session.

THE THREE ASK REGISTERS. "Ask time" is ambiguous and the answer depends on which one is meant,
so all three are reported for every unit.

  ask_device  the instant the device asks / captures (`t_opportunity`). The strictest reading.
  ask_cloud   the instant the cloud is handed the unit and can first act on it: for a dashcam
              instant that is `t_frame_arrive`; for a question it is the question's own arrival
              at the coordinator. This is the register that decides whether the harness let the
              cloud use evidence it did not have.
  ask_submit  `t_submit`, the instant the serving request actually went to the engine. OBSERVED.

FIFO ORDERING IS LOAD-BEARING and is taken from the trace generator's record order, which is
the order `fleet/emulator.py:_plan` pushes and therefore the order `UplinkQueue.send` sees at
equal time: for the single shot `session_start`, `history_batch`, `recall_question`
(`fleet/trace.py:602-624`), and for a robot every `history_batch` of the session before any of
its questions (`fleet/trace.py:688-740`). So an evidence frame offered at the same instant as
the question occupies the uplink FIRST and the question queues behind it.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# -- committed constants, spelled here so every number in the output is traceable ------------
UPLINK_MBPS = 13.6               # D75, fleet/links.py:51
RTT_MS = 44.0                    # D75, fleet/links.py:52
MBIT = 1_000_000.0
QUESTION_TEXT_B = 1200           # fleet/emulator.py:73
HIST_FRAME_B = 24_570            # E10A_SEMBER_Q88_D2_MEDIAN_B, fleet/data_sources.py:67
RUNS_DIR = "results/orchestration/live2/frozen_test/runs"
TAG = "_L3_epg_rq30"
MCQ = "results/sember/study_h/data/sember_mcq.jsonl"
EPS = 1e-9


def serialise_s(nbytes: float, mbps: float = UPLINK_MBPS) -> float:
    return nbytes * 8.0 / (mbps * MBIT)


def flight_s(rtt_ms: float = RTT_MS) -> float:
    return (rtt_ms / 1000.0) / 2.0


SER_HIST = serialise_s(HIST_FRAME_B)
SER_Q = serialise_s(QUESTION_TEXT_B)
FLIGHT = flight_s()


# -- reading the committed tree ---------------------------------------------------------------
class Repo:
    """Every byte read in this module comes from `git show <sha>:<path>`, never the checkout."""

    def __init__(self, sha: str) -> None:
        self.sha = sha

    def raw(self, path: str) -> bytes:
        p = subprocess.run(["git", "show", f"{self.sha}:{path}"], cwd=str(ROOT),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise FileNotFoundError(f"{path} @ {self.sha}: {p.stderr.decode()[:200]}")
        return p.stdout

    def text(self, path: str) -> str:
        b = self.raw(path)
        if path.endswith(".gz"):
            b = gzip.decompress(b)
        return b.decode()

    def jsonl(self, path: str) -> List[Dict[str, Any]]:
        """Some cells commit `outcomes.jsonl` / `request.jsonl` gzipped and some plain (the
        confidence-cascade s7 rerun is plain), so BOTH spellings are tried rather than one
        being assumed and the cell silently skipped as incomplete."""
        try:
            t = self.text(path)
        except FileNotFoundError:
            alt = path[:-3] if path.endswith(".gz") else path + ".gz"
            t = self.text(alt)
        return [json.loads(l) for l in t.splitlines() if l.strip()]

    def json(self, path: str) -> Any:
        return json.loads(self.text(path))

    def ls(self, prefix: str) -> List[str]:
        p = subprocess.run(["git", "ls-tree", "-r", "--name-only", self.sha, prefix],
                           cwd=str(ROOT), stdout=subprocess.PIPE, check=True)
        return p.stdout.decode().splitlines()


def cell_names(repo: Repo) -> List[str]:
    """The committed MAIN-OPERATING-POINT cells: tag `_L3_epg_rq30`, 1x memory (no `kv*`
    suffix), uniform link (there is no other: N1 found no injection point)."""
    names = set()
    for p in repo.ls(RUNS_DIR):
        rest = p[len(RUNS_DIR) + 1:]
        if TAG not in rest:
            continue
        d = rest.split("/")[0]
        if d.endswith(".stdout"):
            d = d[: -len(".stdout")]
        if "_kv0" in d:
            continue
        names.add(d)
    return sorted(names)


def parse_name(d: str) -> Tuple[str, Optional[int], str]:
    """`<arm>_n16_s<seed>_1200s_h27_3t_L3_epg_rq30[_suffix]` -> (arm, seed, suffix)."""
    i = d.find("_n16_s")
    if i < 0:
        return d, None, ""
    arm = d[:i]
    rest = d[i + len("_n16_s"):]
    seed = int(rest.split("_", 1)[0])
    suf = rest.split(TAG, 1)[1] if TAG in rest else ""
    return arm, seed, suf.lstrip("_")


# -- mm_uuid parsing --------------------------------------------------------------------------
def mm_tail(uuid: str) -> str:
    return uuid.rsplit("|", 1)[-1]


def dash_ref(uuid: str) -> Tuple[str, float]:
    """`<salt>|<dev>|-|<clip>|t0003.00` -> (clip, t_local)."""
    parts = uuid.split("|")
    tail = parts[-1]
    if not tail.startswith("t"):
        raise ValueError(f"not a dashcam mm_uuid: {uuid!r}")
    return parts[-2], float(tail[1:])


def hist_x(uuid: str) -> Optional[float]:
    """`...|f00002.00` -> 2.0; an `...|img` single-shot tail -> None."""
    tail = mm_tail(uuid)
    if tail.startswith("f"):
        return float(tail[1:])
    return None


# -- the per-cell audit -----------------------------------------------------------------------
def audit_cell(repo: Repo, name: str, t_ask: Dict[str, float]) -> Dict[str, Any]:
    d = f"{RUNS_DIR}/{name}"
    outs = repo.jsonl(f"{d}/outcomes.jsonl.gz")
    reqs = repo.jsonl(f"{d}/request.jsonl.gz")
    meta = repo.json(f"{d}/run_meta.json")
    cell = repo.json(f"{d}/cell.json")

    by_opp = {o["opportunity_id"]: o for o in outs}
    req_by_opp: Dict[str, Dict[str, Any]] = {}
    for r in reqs:
        opp = r.get("opportunity_id")
        if opp is None:
            continue
        # a unit served more than once: keep the FIRST submission, which is the one whose
        # evidence set has to have landed by then.
        if opp not in req_by_opp or float(r["t_submit"]) < float(req_by_opp[opp]["t_submit"]):
            req_by_opp[opp] = r

    # play -> opportunities sorted by t_local, for the dashcam charging map
    play: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for o in outs:
        if o["kind"] == "monitor":
            play[o["play_id"]].append(o)
    for v in play.values():
        v.sort(key=lambda o: float(o["t_local"]))

    # OBSERVED monotonicity of frame arrival inside a play: the per-device uplink is FIFO and
    # a dashcam offers nothing but frames, so t_frame_arrive must rise with t_local. If it does
    # not, the "latest referenced frame completes at this instant's own arrival" shortcut is
    # invalid and the per-reference maximum below is what catches it.
    nonmono = 0
    for v in play.values():
        prev = -1.0
        for o in v:
            ta = o.get("t_frame_arrive")
            if ta is None:
                continue
            if ta < prev - EPS:
                nonmono += 1
            prev = ta

    units: List[Dict[str, Any]] = []
    leaks: List[Dict[str, Any]] = []

    # ---- type 1: DASHCAM decision instants ---------------------------------------------
    for pid, opps in play.items():
        tl = [float(o["t_local"]) for o in opps]
        for k, o in enumerate(opps):
            opp = o["opportunity_id"]
            r = req_by_opp.get(opp)
            own_arr = o.get("t_frame_arrive")
            if own_arr is None:
                continue
            if r is not None:
                refs = [dash_ref(u) for u in r["mm_uuids"]]
            else:
                # not served by the cloud: the episode frames up to and including this instant
                # are what a request would have carried, and their bytes were charged at the
                # decision instants at or before this one.
                refs = None
            comps: List[float] = []
            if refs is None:
                comps = [float(own_arr)]
            else:
                for clip, x in refs:
                    if clip != o["clip"]:
                        leaks.append(dict(kind="cross_clip", opportunity_id=opp,
                                          clip=o["clip"], ref_clip=clip, ref_t_local=x))
                        continue
                    # the charging instant: the first decision instant of this play at or
                    # after the frame's capture (fleet/trace.py:519-536, `pending_b`).
                    j = None
                    for m in range(len(tl)):
                        if tl[m] >= x - EPS:
                            j = m
                            break
                    if j is None:
                        leaks.append(dict(kind="never_charged", opportunity_id=opp,
                                          ref_t_local=x))
                        continue
                    if j > k:
                        leaks.append(dict(kind="charged_later", opportunity_id=opp,
                                          ref_t_local=x, charged_at_t_local=tl[j]))
                    ca = opps[j].get("t_frame_arrive")
                    if ca is None:
                        leaks.append(dict(kind="charging_instant_never_arrived",
                                          opportunity_id=opp, ref_t_local=x))
                        continue
                    comps.append(float(ca))
            if not comps:
                continue
            units.append(dict(
                type="dashcam", opp=opp, device=o["device_id"], n_refs=len(comps),
                served=r is not None,
                max_completion=max(comps),
                ask_device=float(o["t_opportunity"]),
                ask_cloud=float(own_arr),
                ask_submit=(float(r["t_submit"]) if r is not None else None),
                upload_s=float(own_arr) - float(o["t_opportunity"]),
                queue_s=float(o.get("uplink_queue_s") or 0.0),
            ))

    # ---- the session origin t0, for the robot recall arithmetic -------------------------
    # A recall question is RE-ASKED in these cells (the `rq30` tag, "reask-device" in the cell
    # label): 132 robot recall outcomes in the s4 always-cloud cell come from 20 distinct
    # (play, question) pairs, one of them asked 16 times. A re-ask carries the SAME
    # `question_id` at a LATER `t_opportunity`, so `t_opportunity - t_ask` is the session
    # origin ONLY for the FIRST ask. t0 is therefore the MINIMUM of that difference over the
    # play, and the dispersion above the minimum is reported as a diagnostic: it is the re-ask
    # delay, and if it were not that it would show up here as an inconsistent origin.
    diffs: Dict[str, List[float]] = defaultdict(list)
    for o in outs:
        if o["kind"] != "recall" or not str(o["device_id"]).startswith("robo"):
            continue
        ta = t_ask.get(str(o["question_id"]).lower())
        if ta is None:
            continue
        diffs[o["session_id"]].append(float(o["t_opportunity"]) - ta)
    t0_by_sess = {k: min(v) for k, v in diffs.items()}
    t0_spread = {k: round(max(v) - min(v), 6) for k, v in diffs.items()}

    # ---- types 2 and 3: recall questions and single-shot questions ---------------------
    miss_t_ask = 0
    for o in outs:
        if o["kind"] != "recall":
            continue
        opp = o["opportunity_id"]
        r = req_by_opp.get(opp)
        t_opp = float(o["t_opportunity"])
        qq = float(o.get("uplink_queue_s") or 0.0)      # OBSERVED queueing of the 1200 B ask
        ask_cloud = t_opp + qq + SER_Q + FLIGHT
        is_ss = str(o["device_id"]).startswith("asst")
        if r is None:
            # no cloud request: the cloud referenced nothing, so there is nothing that could
            # have been missing. Counted, with no referenced frame.
            units.append(dict(type=("single_shot" if is_ss else "recall"), opp=opp,
                              device=o["device_id"], n_refs=0, served=False,
                              max_completion=None, ask_device=t_opp, ask_cloud=ask_cloud,
                              ask_submit=None, upload_s=None, queue_s=qq))
            continue
        xs = [hist_x(u) for u in r["mm_uuids"]]
        if is_ss:
            # ONE image, offered at the question's own instant and ahead of it in record
            # order, so the image occupies the uplink first and the question queues behind it.
            if any(x is not None for x in xs) or len(xs) != 1:
                leaks.append(dict(kind="ss_unexpected_refs", opportunity_id=opp,
                                  mm_uuids=r["mm_uuids"]))
            comp = t_opp + SER_HIST + FLIGHT
            units.append(dict(type="single_shot", opp=opp, device=o["device_id"],
                              n_refs=len(xs), served=True, max_completion=comp,
                              ask_device=t_opp, ask_cloud=ask_cloud,
                              ask_submit=float(r["t_submit"]), upload_s=SER_HIST + FLIGHT,
                              queue_s=qq, x_max=None, t_ask=None,
                              within_L=bool(o["within_L"]),
                              deadline_s=float(o["deadline_s"])))
            continue
        # robot recall
        qid = str(o["question_id"]).lower()
        ta = t_ask.get(qid)
        t0 = t0_by_sess.get(o["session_id"])
        if ta is None or t0 is None:
            miss_t_ask += 1
            continue
        # this ask's own position in session time: its first ask sits at the annotated
        # `question_time`, a re-ask sits later, and both are t_opportunity - t0.
        ask_sess = float(o["t_opportunity"]) - t0
        fx = [x for x in xs if x is not None]
        if len(fx) != len(xs):
            leaks.append(dict(kind="recall_nonframe_ref", opportunity_id=opp,
                              mm_uuids=r["mm_uuids"][:3]))
        if not fx:
            units.append(dict(type="recall", opp=opp, device=o["device_id"], n_refs=0,
                              served=True, max_completion=None, ask_device=t_opp,
                              ask_cloud=ask_cloud, ask_submit=float(r["t_submit"]),
                              upload_s=None, queue_s=qq))
            continue
        x_max = max(fx)
        if x_max > ask_sess + EPS:
            leaks.append(dict(kind="frame_after_ask", opportunity_id=opp, x_max=x_max,
                              ask_session_s=round(ask_sess, 6), t_ask_first=ta))
        # completion of the frame captured at session time x_max is
        #   t0 + x_max + queue + SER_HIST + FLIGHT
        # The queue term is the FIFO one: a frame offered at the same instant as a question is
        # ahead of it in the trace's record order, so the frame queues behind nothing of the
        # question's and the question queues behind IT (that is the OBSERVED `qq`).
        comp = t0 + x_max + SER_HIST + FLIGHT
        units.append(dict(type="recall", opp=opp, device=o["device_id"], n_refs=len(fx),
                          served=True, max_completion=comp, ask_device=t_opp,
                          ask_cloud=ask_cloud, ask_submit=float(r["t_submit"]),
                          upload_s=SER_HIST + FLIGHT, queue_s=qq,
                          x_max=x_max, t_ask=ta, ask_session_s=ask_sess,
                          within_L=bool(o["within_L"]), deadline_s=float(o["deadline_s"]),
                          t_delivered=o.get("t_delivered"),
                          slack_session_s=ask_sess - x_max))

    # ---- the emulated rate, OBSERVED per cell -------------------------------------------
    # An assistive device uploads nothing but (24,570 B image, 1,200 B question) pairs, both
    # committed constants, so `busy_s` from links.UplinkQueue.stats() pins the emulated rate:
    #   busy_s = n_pairs * (24570 + 1200) * 8 / R   =>   R = n_pairs * 25770 * 8 / busy_s
    # A robot uploads n-nq frames of 24,570 B plus nq questions of 1,200 B, which pins it too.
    nq_by_dev: Dict[str, int] = defaultdict(int)
    for o in outs:
        if o["kind"] == "recall":
            nq_by_dev[o["device_id"]] += 1
    rate_rows = []
    for dev, st in sorted((meta.get("uplink") or {}).items()):
        n, busy = int(st["n"]), float(st["busy_s"])
        if busy <= 0:
            continue
        if dev.startswith("asst"):
            pairs = n / 2.0
            byt = pairs * (HIST_FRAME_B + QUESTION_TEXT_B)
        elif dev.startswith("robo"):
            nq = nq_by_dev.get(dev, 0)
            byt = (n - nq) * HIST_FRAME_B + nq * QUESTION_TEXT_B
        else:
            rate_rows.append(dict(device=dev, kind="dashcam", n=n, busy_s=busy,
                                  implied_mbps=None,
                                  note="per-ref manifest bytes, not a committed constant",
                                  queue_max=st["queue_max"], queue_p50=st["queue_p50"]))
            continue
        rate_rows.append(dict(device=dev, kind=("single_shot" if dev.startswith("asst")
                                                else "robot"),
                              n=n, busy_s=busy,
                              implied_mbps=round(byt * 8.0 / busy / MBIT, 6),
                              queue_max=st["queue_max"], queue_p50=st["queue_p50"]))

    return dict(cell=name, units=units, leaks=leaks, rate_rows=rate_rows,
                nonmono_frame_arrivals=nonmono, missing_t_ask=miss_t_ask,
                n_outcomes=len(outs), n_requests_logged=len(reqs),
                t0_spread_by_session=t0_spread,
                control=control_figures(outs, reqs, cell, meta))


def control_figures(outs, reqs, cell, meta) -> Dict[str, Any]:
    """POSITIVE CONTROL (CLAUDE.md check 7). Recompute committed figures from the very files
    this module parses, BEFORE reading anything new out of them, so a parsing error cannot
    masquerade as a finding. Three figures, each committed by a different writer:

      n_devices              `cell.json` score block
      robot_recall_units     `cell.json` robot_headline.n_by_deadline, against the robot
                             recall rows of outcomes.jsonl
      assistive_units        `cell.json` assistive_value.n_cloud_standing + n_device_standing,
                             a committed identity over the partition of the single-shot
                             questions, against the assistive recall rows of outcomes.jsonl

    `run_meta.completion_to_emulator_ms.n` is NOT used: it counts cloud answers forwarded to
    the emulator, which differs from the rows of request.jsonl in BOTH directions across these
    cells (attentionstore s4: 7,752 against 8,168 rows; always-cloud s6: 8,340 against 8,322),
    so it is not the same object and a disagreement there is not a parse error.

    `n_plays` is reported BESIDE them and is NOT a control: the committed `dashcam_value.
    n_plays` applies D85's exclusion of plays cut by the run end, which outcomes.jsonl alone
    cannot reconstruct, so a difference there is a definition difference and not a parse error.
    """
    sc = (cell.get("score") or {}).get("score") or {}
    plays = {o["play_id"] for o in outs if o["kind"] == "monitor"}
    devs = {o["device_id"] for o in outs}
    nrob = sum(1 for o in outs
               if o["kind"] == "recall" and str(o["device_id"]).startswith("robo"))
    nass = sum(1 for o in outs
               if o["kind"] == "recall" and str(o["device_id"]).startswith("asst"))
    av = sc.get("assistive_value") or {}
    want_ass = (None if av.get("n_cloud_standing") is None
                else int(av["n_cloud_standing"]) + int(av["n_device_standing"]))
    got = dict(n_devices=len(devs), robot_recall_units=nrob, assistive_units=nass)
    want = dict(n_devices=sc.get("n_devices"),
                robot_recall_units=((sc.get("robot_headline") or {}).get("n_by_deadline")),
                assistive_units=want_ass)
    return dict(recomputed=got, committed=want,
                agree={k: (want.get(k) is None or want[k] == got[k]) for k in got},
                beside=dict(n_plays_recomputed=len(plays),
                            n_plays_committed_D85=(sc.get("dashcam_value") or {}).get(
                                "n_plays")))


def q(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def summarise(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for reg in ("ask_device", "ask_cloud", "ask_submit"):
        gaps = []
        n_eval = 0
        for u in rows:
            if u["max_completion"] is None or u.get(reg) is None:
                continue
            n_eval += 1
            gaps.append(u["max_completion"] - float(u[reg]))
        late = [g for g in gaps if g > EPS]
        out[reg] = dict(
            n_units=len(rows), n_evaluable=n_eval, n_late=len(late),
            frac_late=(round(len(late) / n_eval, 6) if n_eval else None),
            worst_gap_s=(round(max(gaps), 6) if gaps else None),
            gap_p50_s=(round(q(gaps, 0.50), 6) if gaps else None),
            gap_min_s=(round(min(gaps), 6) if gaps else None),
            gap_p90_s=(round(q(gaps, 0.90), 6) if gaps else None),
            gap_p99_s=(round(q(gaps, 0.99), 6) if gaps else None),
            n_distinct_gaps=len({round(g, 9) for g in gaps}),
        )
    ups = [u["upload_s"] for u in rows if u.get("upload_s") is not None]
    out["upload_s"] = dict(n=len(ups), min=(round(min(ups), 6) if ups else None),
                           p50=(round(q(ups, 0.5), 6) if ups else None),
                           max=(round(max(ups), 6) if ups else None),
                           n_distinct=len({round(x, 9) for x in ups}))
    qs = [u["queue_s"] for u in rows if u.get("queue_s") is not None]
    out["queue_s"] = dict(n=len(qs), min=(round(min(qs), 6) if qs else None),
                          p50=(round(q(qs, 0.5), 6) if qs else None),
                          max=(round(max(qs), 6) if qs else None),
                          n_distinct=len({round(x, 9) for x in qs}))
    sl = [u["slack_session_s"] for u in rows if u.get("slack_session_s") is not None]
    if sl:
        out["recall_session_slack_s"] = dict(n=len(sl), min=round(min(sl), 6),
                                             p50=round(q(sl, 0.5), 6), max=round(max(sl), 6),
                                             n_zero=sum(1 for v in sl if abs(v) < EPS))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    repo = Repo(a.sha)
    t_ask = {}
    for r in repo.jsonl(MCQ):
        t_ask[str(r["question_id"]).lower()] = float(r["question_time"])

    names = cell_names(repo)
    if a.limit:
        names = names[: a.limit]
    per_cell: Dict[str, Any] = {}
    skipped: Dict[str, str] = {}
    all_units: List[Tuple[str, Dict[str, Any]]] = []
    all_leaks: List[Dict[str, Any]] = []
    rates: List[Dict[str, Any]] = []
    for n in names:
        try:
            res = audit_cell(repo, n, t_ask)
        except FileNotFoundError as e:
            skipped[n] = f"incomplete cell: {e}"
            continue
        arm, seed, suf = parse_name(n)
        by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for u in res["units"]:
            by_type[u["type"]].append(u)
            all_units.append((n, u))
        for lk in res["leaks"]:
            all_leaks.append(dict(cell=n, **lk))
        for rr in res["rate_rows"]:
            rates.append(dict(cell=n, **rr))
        per_cell[n] = dict(
            arm=arm, seed=seed, suffix=suf,
            n_outcomes=res["n_outcomes"], n_requests_logged=res["n_requests_logged"],
            nonmono_frame_arrivals=res["nonmono_frame_arrivals"],
            missing_t_ask=res["missing_t_ask"],
            control=res["control"],
            t0_reask_spread_s=dict(
                n_sessions=len(res["t0_spread_by_session"]),
                max=(max(res["t0_spread_by_session"].values())
                     if res["t0_spread_by_session"] else None),
                n_zero=sum(1 for v in res["t0_spread_by_session"].values() if abs(v) < EPS)),
            by_type={k: summarise(v) for k, v in sorted(by_type.items())},
            emulated_rate=dict(
                implied_mbps=sorted({r["implied_mbps"] for r in res["rate_rows"]
                                     if r["implied_mbps"] is not None}),
                dashcam_queue_max=sorted({r["queue_max"] for r in res["rate_rows"]
                                          if r["kind"] == "dashcam"}),
                nondashcam_queue_max=sorted({r["queue_max"] for r in res["rate_rows"]
                                             if r["kind"] != "dashcam"}),
            ),
        )
        print(f"  {n}: {len(res['units'])} units, {len(res['leaks'])} leaks", flush=True)

    # fleet-wide rollups
    by_arm: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_seed: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    by_type_all: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cellname, u in all_units:
        arm, seed, _ = parse_name(cellname)
        by_arm[arm].append(u)
        by_seed[seed].append(u)
        by_type_all[u["type"]].append(u)

    late_cloud = []
    for cellname, u in all_units:
        if u["max_completion"] is None or u.get("ask_cloud") is None:
            continue
        gap = u["max_completion"] - float(u["ask_cloud"])
        if gap > EPS:
            late_cloud.append(dict(
                cell=cellname, type=u["type"], opp=u["opp"], device=u["device"],
                gap_vs_ask_cloud_s=round(gap, 6),
                gap_vs_ask_submit_s=(None if u.get("ask_submit") is None
                                     else round(u["max_completion"]
                                                - float(u["ask_submit"]), 6)),
                submit_minus_ask_cloud_s=(None if u.get("ask_submit") is None
                                          else round(float(u["ask_submit"])
                                                     - float(u["ask_cloud"]), 6)),
                within_L=u.get("within_L"), deadline_s=u.get("deadline_s"),
                n_refs=u["n_refs"]))
    late_cloud.sort(key=lambda d: -d["gap_vs_ask_cloud_s"])

    result = dict(
        question=("does the absent question-time frame delta (D150 SYNC (2)) affect any "
                  "committed main-operating-point result"),
        sha=a.sha,
        constants=dict(uplink_mbps=UPLINK_MBPS, rtt_ms=RTT_MS,
                       question_text_b=QUESTION_TEXT_B, hist_frame_b=HIST_FRAME_B,
                       serialise_hist_s=round(SER_HIST, 9),
                       serialise_question_s=round(SER_Q, 9), flight_s=round(FLIGHT, 9)),
        registers=dict(
            ask_device="t_opportunity, the device's own capture/ask instant (OBSERVED)",
            ask_cloud=("the instant the cloud can first act: t_frame_arrive for a dashcam "
                       "instant (OBSERVED); t_opportunity + uplink_queue_s + serialise(1200) "
                       "+ RTT/2 for a question (queue OBSERVED, rest CONSTRUCTED)"),
            ask_submit="t_submit of the serving request (OBSERVED)"),
        completion_register=dict(
            dashcam="OBSERVED (outcomes.jsonl t_frame_arrive of the charging instant)",
            recall="CONSTRUCTED (committed link arithmetic; t_ask OBSERVED from sember_mcq)",
            single_shot="CONSTRUCTED (committed link arithmetic; offer instant OBSERVED)"),
        n_cells=len(per_cell), skipped=skipped,
        overall_by_type={k: summarise(v) for k, v in sorted(by_type_all.items())},
        by_arm={k: summarise(v) for k, v in sorted(by_arm.items())},
        by_seed={str(k): summarise(v) for k, v in sorted(by_seed.items())},
        per_cell=per_cell,
        leaks=all_leaks[:200], n_leaks=len(all_leaks),
        late_at_ask_cloud=dict(
            n=len(late_cloud),
            n_within_L=sum(1 for d in late_cloud if d["within_L"]),
            types=sorted({d["type"] for d in late_cloud}),
            units=late_cloud),
        emulated_rate_rows=rates,
    )
    try:
        from _provenance import stamp  # type: ignore
        result["_provenance"] = stamp(script="n4_question_delta_audit.py", model=None,
                                      device="cpu", n=len(per_cell), args=a)
    except Exception:
        result["_provenance"] = dict(git_commit=a.sha,
                                     script="n4_question_delta_audit.py",
                                     model=None, device="cpu", n=len(per_cell))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result["overall_by_type"], indent=1))
    print("leaks:", len(all_leaks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
