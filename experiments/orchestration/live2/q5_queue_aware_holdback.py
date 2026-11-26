#!/usr/bin/env python3
"""q5: QUEUE-AWARE HOLD_BACK ONLY (pre-registered `research/study_q5_queue_aware_holdback_prereg.md`).

BASE IS RUNG 3 (`covex-v6-fair-final`), NOT `-q2m` AND NOT `-q4*`. Rung 3's TOUCH logic is untouched:
margin 0.65824 (the committed default, because the D259 scope keys on the D249 switch, which is OFF),
no credit, no queue term in the TOUCH gain or the warm/cold pricing. Switches D249 and q2 stay OFF.
The ONLY thing q5 changes is the HOLD_BACK / WARM / SLICE harm of a session that is being rebuilt:

    harm_warm(q5) = harm_warm(rung 3)                       (i)  delay to requests QUEUED BEHIND the
                                                                  rebuild: the committed per-queue-token
                                                                  coefficient on the arrived-undecided
                                                                  rows, exactly as rung 3 prices it
                  + harm_inflight                           (ii) the decode-step slowdown the held-back
                                                                  prefill would impose on requests the
                                                                  ENGINE IS ALREADY WORKING ON

WHY NOT THE FULL QUEUE DELAY FOR (ii). `-q` priced in-flight rows with the full queue delay
(u x per_queue_token, up to the 2.781 s cap) and HOLD_BACK fired 87 to 93 times (a blanket brake);
`-q2` removed in-flight rows from the HOLD_BACK harm altogether (HOLD_BACK 6, 4). Requests already
in the engine are AHEAD of the rebuild in the FCFS queue; what a concurrent prefill chunk does to
them is lengthen the steps they share. That is the priced form used here.

(ii)'s COEFFICIENT IS COMMITTED, NOT FITTED HERE: StudyENG1's step-time model, read from
`results/cost/study_eng1/eng1_step_model.json` (the engine model D18 and M7 rest on; fit data are
the StudyENG1 busy-interval steps, holdout unspent; no s4 log, no new fit). A chunk of `tok` new
tokens (chunk <= CHUNK_TOKENS 8,192, StudyENG1 section 1.2) over `ctx` cached context tokens adds to
the step it shares, against a decode-only step:

    extra_ms(tok, ctx) = per_tok*tok + sum_k per_tok_above_k*max(0, tok-k) + per_prefill_req
                         + per_tok_x_ctx_per_1e6 * tok * ctx / 1e6
    (the intercept and per_decode_req terms are in BOTH steps and cancel)

Every running request pays `sum over chunks extra_ms` seconds. That delay is applied to the in-flight
deadline rows of OTHER devices through `cf_objective.harm_warm_from_queue_delay` (the same function
as every harm term: deficit weights via counters.weight, the D256 healthy-bound cap, the rows' own
slack), by passing the delay's per-queue-token equivalent token count. No new CC.predict site is
added; the literal `0, 0` queue args are untouched.
Tokens: the real remaining history (est_tokens_by_session minus built), NOT MATERIALIZE's
10**9 `target_tokens` sentinel, which rung 3's own queue term sees (and which keeps that term at the
D256 cap on every warming evaluation, unchanged here).
The 12.7 ms + 1.15 ms/image admission stall (`admission` block of the same JSON) is for IMAGE
admission steps; a held-back text/KV prefill carries no new images here, so it is not charged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

Q5_SWITCH = "live2_q5_queue_aware_holdback"
FORCE_ZERO_ATTR = "q5_force_zero_inflight"       # NEGATIVE-CONTROL hook only; default absent
STEP_MODEL_REL = "results/cost/study_eng1/eng1_step_model.json"
CHUNK_TOKENS = 8192                              # StudyENG1 section 1.2 (chunked prefill step budget)


class Q5SwitchError(RuntimeError):
    """The q5 switch was a truthy CLASS attribute, or a non-bool."""


def arm_enables(arm: Any) -> bool:
    """Is q5 on for THIS ARM INSTANCE? Default False; instance-dict lookup only. READ SITES:
    `arms_v6state.V6StateArm._q5_on` (decide: the in-flight term) and `coordinator.__init__` (the
    in-flight rows are published to the Observation)."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if Q5_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(Q5_SWITCH, False)):
                raise Q5SwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; q5 "
                    "requires an arm-scoped INSTANCE attribute" % (Q5_SWITCH, klass.__name__))
    v = own.get(Q5_SWITCH, False)
    if not isinstance(v, bool):
        raise Q5SwitchError("%s must be a bool, got %r" % (Q5_SWITCH, type(v).__name__))
    return v


def enabled_cached(arm: Any) -> bool:
    d = vars(arm)
    v = d.get("_q5_resolved")
    if v is None:
        v = arm_enables(arm)
        d["_q5_resolved"] = v
    return bool(v)


_MODEL: Optional[Dict[str, Any]] = None


def step_model() -> Dict[str, Any]:
    """The committed StudyENG1 step model, loaded once, never refitted. Refuses a file that does
    not state its fit data (same provenance rule as `policy.eng1_engine.StepModel.load`)."""
    global _MODEL
    if _MODEL is None:
        p = Path(__file__).resolve().parents[3] / STEP_MODEL_REL
        raw = json.loads(p.read_text())
        if raw.get("fit_data", "").find("HOLDOUT") < 0:
            raise ValueError("%s does not state its fit data" % p)
        _MODEL = dict(coef=dict(raw["coef"]), knots=tuple(raw["knots"]), path=str(p), n=raw.get("n"))
    return _MODEL


def extra_step_ms(tok: int, ctx: int) -> float:
    m = step_model()
    c, t = m["coef"], max(int(tok), 0)
    ms = c["per_tok_ms"] * t
    ms += c["per_tok_above_512_ms"] * max(0, t - 512)
    ms += c["per_tok_above_2048_ms"] * max(0, t - 2048)
    ms += c["per_tok_above_4096_ms"] * max(0, t - 4096)
    ms += c["per_prefill_req_ms"]
    ms += c["per_tok_x_ctx_per_1e6_ms"] * t * max(int(ctx), 0) / 1e6
    return max(ms, 0.0)


def interference_s(uncached_tokens: int, ctx_tokens: int) -> float:
    """Seconds every running request is slowed by a prefill of `uncached_tokens` over `ctx_tokens`
    of cached context, in chunks of at most CHUNK_TOKENS (one lengthened step per chunk)."""
    left, ctx, tot = max(int(uncached_tokens), 0), max(int(ctx_tokens), 0), 0.0
    while left > 0:
        n = min(left, CHUNK_TOKENS)
        tot += extra_step_ms(n, ctx)
        left -= n
        ctx += n
    return tot / 1000.0
