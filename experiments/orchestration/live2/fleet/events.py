#!/usr/bin/env python3
"""The round-1 fleet/coordinator wire events, as the shared interface defines them.

StudyLIVE2-fleet. `experiments/orchestration/live2/schema.py` is owned by the coordinator
session; this module is the FLEET side's own copy of the same spec, so that the fleet can be
built and tested before schema.py lands. `check_against_schema()` compares the two and RAISES on
any difference rather than silently preferring one, because a schema mismatch between the two
sessions is a stop condition.

Times are seconds on ONE run clock, t = 0 at run start.

D96 (1): EVERY OPPORTUNITY CARRIES AN `opportunity_id`, UNIQUE WITHIN THE RUN AND ASSIGNED BY
THE TRACE GENERATOR, present in `monitor_offer`, `monitor_frame` and `recall_question`, echoed
unchanged in `cloud_answer` and in every log. The coordinator NEVER constructs one: a bare
instant or question id is ambiguous once D84 allows repeated clips and sessions.

FLEET -> COORDINATOR
  device_register  {device_id, type: dashcam|robot, uplink_mbps, rtt_ms, start_t}
  session_start    {device_id, session_id, t}                         robots (D83)
  session_end      {device_id, session_id, t}                         robots (D83)
  monitor_offer    {device_id, opportunity_id, instant_id, t_capture, deadline_s, frame_bytes}
                                                                      mode B only
  monitor_frame    {device_id, opportunity_id, instant_id, t_capture, t_arrive, deadline_s,
                    frame_ref, frame_bytes}                 mode A pushed; mode B after a pull
  history_preload  {device_id, session_id, frame_refs[], est_tokens, t}      robots (D101)
  history_append   {device_id, session_id, batch_id, t_arrive, frame_refs[], est_tokens}
  recall_question  {device_id, opportunity_id, session_id, question_id, t_ask, t_arrive,
                    deadline_s, question, options[]}

COORDINATOR -> FLEET
  pull_request     {device_id, instant_id, t_sent}
  cloud_answer     {device_id, opportunity_id, t_done, payload}
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent

DEVICE_TYPES = ("dashcam", "robot")

FIELDS: Dict[str, tuple] = {
    "device_register": ("device_id", "type", "uplink_mbps", "rtt_ms", "start_t"),
    "session_start": ("device_id", "session_id", "t"),
    "session_end": ("device_id", "session_id", "t"),
    "monitor_offer": ("device_id", "opportunity_id", "instant_id", "t_capture", "deadline_s",
                      "frame_bytes"),
    "monitor_frame": ("device_id", "opportunity_id", "instant_id", "t_capture", "t_arrive",
                      "deadline_s", "frame_ref", "frame_bytes"),
    # D101: the frames the cloud ALREADY HOLDS at t = 0 for a session joined part-way. NO
    # batch_id and NO t_arrive, because nothing arrived during the run, and NO UPLINK TIME is
    # charged for it.
    "history_preload": ("device_id", "session_id", "frame_refs", "est_tokens", "t"),
    "history_append": ("device_id", "session_id", "batch_id", "t_arrive", "frame_refs",
                       "est_tokens"),
    "recall_question": ("device_id", "opportunity_id", "session_id", "question_id", "t_ask",
                        "t_arrive", "deadline_s", "question", "options"),
    "pull_request": ("device_id", "instant_id", "t_sent"),
    "cloud_answer": ("device_id", "opportunity_id", "t_done", "payload"),
}


def make(kind: str, **kw: Any) -> Dict[str, Any]:
    """Build one wire event, rejecting a missing or unknown field outright."""
    want = FIELDS.get(kind)
    if want is None:
        raise KeyError(f"unknown event kind {kind!r}")
    missing = [f for f in want if f not in kw]
    extra = [f for f in kw if f not in want]
    if missing or extra:
        raise ValueError(f"{kind}: missing={missing} extra={extra}")
    if kind == "device_register" and kw["type"] not in DEVICE_TYPES:
        raise ValueError(f"device type {kw['type']!r} not in {DEVICE_TYPES}")
    return dict(kind=kind, **kw)


def opportunity_id_of(event: Dict[str, Any]) -> str:
    """The `opportunity_id` an event carries. D96 (1): it is READ, never constructed.

    Before D96 this helper built a recall id as f"{session_id}|{question_id}" while
    `live2/CONTRACT.md` said the id was the bare instant or question id. D96 settled it: the
    trace generator ASSIGNS the id, every one of the three fleet events carries it, and both the
    coordinator and the fleet echo it unchanged. So there is nothing left to derive, and this
    helper exists only to give the read one name and to refuse an event that has no opportunity.
    """
    k = event.get("kind")
    if k not in ("monitor_offer", "monitor_frame", "recall_question"):
        raise ValueError(f"{k!r} does not define an opportunity")
    opp = event.get("opportunity_id")
    if not opp:
        raise ValueError(f"{k} carries no opportunity_id; D96 (1) requires one on every "
                         f"opportunity, assigned by the trace generator")
    return str(opp)


# D96 (1) adds `opportunity_id` to these three events. Subagent A owns `live2/schema.py` and is
# mid-build, so until its change lands the ONLY difference the schema check may tolerate is the
# absence of exactly this field on exactly these events. Anything else still raises.
PENDING_D96: Dict[str, str] = {
    "monitor_offer": "opportunity_id",
    "monitor_frame": "opportunity_id",
    "recall_question": "opportunity_id",
}


def _load_schema_module():
    p = LIVE2 / "schema.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("live2_schema", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_against_schema() -> Dict[str, Any]:
    """Compare this module's field lists with schema.py's. RAISE on any difference.

    Returns a dict describing what was compared so the report can record it. If schema.py is
    absent the result says so and nothing is raised: the fleet is then running on the inline
    spec, which the report must state.
    """
    mod = _load_schema_module()
    if mod is None:
        return dict(schema_present=False, compared=[], note="live2/schema.py absent; the fleet "
                                                            "is built on the inline D69 spec")
    theirs: Dict[str, tuple] = {}
    for name in ("FIELDS", "EVENT_FIELDS", "SCHEMA"):
        obj = getattr(mod, name, None)
        if isinstance(obj, dict):
            theirs = {k: tuple(v) for k, v in obj.items()}
            break
    if not theirs:
        raise RuntimeError("live2/schema.py exists but exposes no FIELDS / EVENT_FIELDS / SCHEMA "
                           "mapping this module can compare against; STOP and reconcile by hand")
    diffs, pending = [], []
    for kind, want in FIELDS.items():
        got = theirs.get(kind)
        if got is None:
            diffs.append(f"{kind}: absent from schema.py")
            continue
        if tuple(got) == tuple(want):
            continue
        f = PENDING_D96.get(kind)
        if f is not None and tuple(x for x in want if x != f) == tuple(got):
            pending.append(f"{kind}: schema.py does not yet carry {f!r} (D96 (1), subagent A)")
        else:
            diffs.append(f"{kind}: fleet {want} vs schema.py {tuple(got)}")
    for kind in theirs:
        if kind not in FIELDS:
            diffs.append(f"{kind}: present in schema.py, absent here")
    if diffs:
        raise RuntimeError("SCHEMA MISMATCH between live2/fleet/events.py and live2/schema.py; "
                           "this is a STOP condition:\n  " + "\n  ".join(diffs))
    if pending:
        return dict(schema_present=True, compared=sorted(FIELDS), d96_pending=True,
                    pending=pending,
                    note="ONLY the D96 (1) opportunity_id addition is missing from schema.py; "
                         "every other field list is identical. This is the expected mid-build "
                         "state and must be re-checked once subagent A's change lands.")
    return dict(schema_present=True, compared=sorted(FIELDS), d96_pending=False,
                note="field lists identical")
