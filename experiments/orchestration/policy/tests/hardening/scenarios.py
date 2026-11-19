#!/usr/bin/env python3
"""StudyCOVEX-harden Part 2: the behaviour scenarios.

Expectations are PRE-REGISTERED in `results/orchestration/live2/covex_harden/
scenario_preregistration.json` and were committed BEFORE COVEX was run against any of them. This
file reads that JSON and never restates an expectation of its own, so an expectation cannot drift
after a result is seen.

Each scenario is a crafted event list built with the committed `schema.make`, so history size,
device count and deadlines are exact. `history_append.est_tokens` is CUMULATIVE, per the
committed contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HARDEN = Path(__file__).resolve().parent
AUDIT = HARDEN.parents[1] / "audit"
sys.path.insert(0, str(AUDIT))

import _harness as H                                                   # noqa: E402

H.setup_paths()

import arms as A                                                       # noqa: E402
import cachekeys as CK                                                 # noqa: E402
import cstate as CS                                                    # noqa: E402
import fix_checks as FX                                                # noqa: E402
import run_live2_cell as RC                                            # noqa: E402
import schema as SC                                                    # noqa: E402
from coordinator import Live2Coordinator, Logs                         # noqa: E402

TOK_PER_IMG, HEADER_TOK = 90, 31
DASHCAM_L_S, ROBOT_L_S = 1.0, 5.0
CADENCE_S = 0.5
UPLINK_MBPS, RTT_MS = 13.6, 44.0
FRAME_BYTES = 120_000
PREREG = (H.ROOT / "results/orchestration/live2/covex_harden"
          / "scenario_preregistration.json")


def frames_for_tokens(tokens: int) -> int:
    return max(1, int(round((int(tokens) - HEADER_TOK) / float(TOK_PER_IMG))))


def _upload_s(nbytes: int) -> float:
    return RTT_MS / 1000.0 + nbytes * 8.0 / (UPLINK_MBPS * 1e6)


def dashcams(n: int, duration_s: float, start_t: float = 0.0) -> List[Dict[str, Any]]:
    ev = []
    for i in range(n):
        did = "dash%03d" % i
        ev.append(SC.make("device_register", device_id=did, type="dashcam",
                          uplink_mbps=UPLINK_MBPS, rtt_ms=RTT_MS, start_t=start_t))
        k, t = 0, start_t
        while t <= duration_s:
            opp = "%s|i%05d" % (did, k)
            ev.append(SC.make("monitor_frame", device_id=did, opportunity_id=opp,
                              instant_id="%s/i%05d" % (did, k), t_capture=round(t, 4),
                              t_arrive=round(t + _upload_s(FRAME_BYTES), 4),
                              deadline_s=DASHCAM_L_S, frame_ref="%s_i%05d.bin" % (did, k),
                              frame_bytes=FRAME_BYTES))
            k += 1
            t = round(start_t + k * CADENCE_S, 4)
    return ev


def robot(did: str, history_tokens: int, question_at_s: float, duration_s: float,
          deadline_s: float = ROBOT_L_S, n_questions: int = 1,
          build_at_s: float = 1.0, preload: bool = False,
          question_gap_s: float = 0.0) -> List[Dict[str, Any]]:
    """One robot session whose history is delivered as a single batch before the question.

    The history is delivered in ONE batch at `build_at_s` so the size at question time is exact,
    which is what the scenarios need; the generator's 30 s batching is not required here and the
    contract only fixes that `est_tokens` is cumulative.
    """
    sid = "%s/s0/play0" % did
    nf = frames_for_tokens(history_tokens)
    refs = ["%s_f%05d.bin" % (did, m) for m in range(nf)]
    ev = [SC.make("device_register", device_id=did, type="robot", uplink_mbps=UPLINK_MBPS,
                  rtt_ms=RTT_MS, start_t=0.0),
          SC.make("session_start", device_id=did, session_id=sid, t=0.0)]
    if preload:
        ev.append(SC.make("history_preload", device_id=did, session_id=sid, frame_refs=refs,
                          est_tokens=int(history_tokens), t=0.0))
    else:
        ev.append(SC.make("history_append", device_id=did, session_id=sid,
                          batch_id="%s/b0" % sid, t_arrive=round(build_at_s, 4),
                          frame_refs=refs, est_tokens=int(history_tokens)))
    for qi in range(n_questions):
        tq = round(question_at_s + qi * question_gap_s, 4)
        ev.append(SC.make("recall_question", device_id=did,
                          opportunity_id="%s|q%d" % (sid, qi), session_id=sid,
                          question_id="%s/q%d" % (sid, qi), t_ask=tq,
                          t_arrive=round(tq + _upload_s(2_000), 4), deadline_s=deadline_s,
                          question="HARDEN scenario question %d" % qi,
                          options=["A", "B", "C", "D"]))
    ev.append(SC.make("session_end", device_id=did, session_id=sid,
                      t=round(duration_s + 1.0, 4)))
    return ev


def run_events(events: List[Dict[str, Any]], outdir: Path, window_s: float,
               switches: Optional[Dict[str, bool]] = None, arm_name: str = "policy-core",
               host_gib: Optional[float] = None) -> Dict[str, Any]:
    """Drive the committed coordinator over a crafted event list, dry run."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ev = sorted(events, key=lambda e: (float(e.get("t", e.get("t_capture",
                e.get("t_arrive", e.get("t_ask", 0.0))) or 0.0)), e["kind"]))
    gib = float(FX.HOST_GIB if host_gib is None else host_gib)
    htok = RC.host_tokens(gib)
    if arm_name == "policy-core":
        arm = A.make_arm("policy-core", **H._arm_kwargs(switches or {}))
    else:
        arm = A.make_arm(arm_name)
    arm.live2_configure(gpu_kv_tokens=FX.GPU_KV, host_tier_gib=gib, host_tier_tokens=htok,
                        targets=CS.TARGETS)
    logs = Logs(outdir).open()
    co = Live2Coordinator(arm, None, ev, gpu_kv_tokens=FX.GPU_KV, host_tier_gib=gib,
                          host_tier_tokens=htok, upload_mode="A", window_s=float(window_s),
                          drain_s=10.0, seed=0, logs=logs,
                          run_tag=CK.run_tag(0, arm_name), dry_run=True)
    try:
        res = co.run()
    finally:
        logs.close()
    dec = [json.loads(l) for l in open(outdir / "decision.jsonl")]
    return dict(result=res, decisions=dec, arm=arm, coordinator=co, outdir=outdir,
                questions={e["opportunity_id"]: e for e in ev if e["kind"] == "recall_question"},
                monitor_offered=sum(1 for e in ev if e["kind"] == "monitor_frame"))


def question_outcome(run: Dict[str, Any], opp_id: str) -> Dict[str, Any]:
    """What happened to one question: released when, declined, or never seen."""
    q = run["questions"][opp_id]
    dl = float(q["t_ask"]) + float(q["deadline_s"])
    rel, kinds = [], []
    for r in run["decisions"]:
        if r["kind"] in ("release_recall", "release_whole", "release_piece"):
            if opp_id in (r.get("opportunity_ids") or []):
                rel.append(float(r["t"]))
                kinds.append(r["kind"])
    declines = [r for r in run["decisions"] if r["kind"] == "decline"]
    return dict(opportunity_id=opp_id, t_ask=float(q["t_ask"]), deadline_abs=dl,
                history_tokens=None, released_at=(min(rel) if rel else None),
                release_kinds=sorted(set(kinds)),
                released_before_deadline=bool(rel and min(rel) < dl),
                n_releases=len(rel), n_declines_in_run=len(declines))


def monitor_releases(run: Dict[str, Any]) -> int:
    return sum(1 for r in run["decisions"] if r["kind"] == "release_monitor")


def load_prereg() -> Dict[str, Any]:
    return json.loads(PREREG.read_text())["scenarios"]
