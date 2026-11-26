#!/usr/bin/env python3
"""q4: THE AVOIDED-REBUILD CREDIT ON TOUCH (pre-registered `research/study_q4_avoided_rebuild_credit_prereg.md`).

STATUS: DEV BUILD, DEFAULT OFF on every arm. The only arm that turns it on is
`covex-v6-fair-final-q4` = `-q2m` plus this credit. Nothing here moves the margin (0.6582), a bar,
or a committed constant.

WHAT IT ADDS. The state planner scores TOUCH as `w * P(q) * (P_warm - P_cold) - harm_touch` (the
robot's own on-time gain) and deviates from KEEP when that beats the margin. It never credited a
touch for the REBUILD it avoids. A history that goes cold is rebuilt on the robot's next question,
and the rebuild's uncached tokens sit in front of every deadline request queued behind it. So

    credit(session) = P(cold | idle gap) x harm_rebuild_to_others
    TOUCH value     = (robot's own gain - harm_touch) + credit          (KEEP stays 0)

KEEP is the reference the delta is taken against ("let the history go"); charging KEEP
-credit instead of crediting TOUCH +credit is the same delta, so the credit is carried on TOUCH.
It is applied only where a touch can be emitted (session NOT being rebuilt this epoch), so the
WARM / HOLD_BACK / SLICE competition of a session that is warming is bit-for-bit `-q2m`'s.

harm_rebuild_to_others = `arms_v6state._harm_warm(obs, sid, EST)`: the SAME function, the SAME
per-queue-token coefficient (cf_objective.QUEUE_TOKEN_S = d162_price.PER_QUEUE_S, 0.00015358 s per
queued-ahead uncached TOKEN; the 0.00018243 per_uncached_token is the request's own service term and
is not the queue term), the SAME deficit weights (counters.weight per delayed row), the SAME
D256 cap (HEALTHY_FIRST_TOKEN_BOUND_S = 2.781 s), the SAME rows (recall rows + D249 in-flight
deadline rows of other devices). No new CC.predict site; the literal `0, 0` queue args are untouched.
EST = `roster["est_tokens_by_session"][sid]` (fallback built tokens), the quantity
`_p_warm_cold` already prices the COLD question with (all of it uncached).

THE ESTIMATOR, PRE-DECLARED AND FIXED BEFORE ANY CELL. P(cold | idle gap) is learned WITHIN THE RUN,
from THIS ARM'S OWN robot responses only (`live2_completed`, kind "recall", robot devices):
  * idle gap  = request submit time minus the session's previous request DONE time (any kind);
  * cold      = cached_tokens / prompt_tokens < COLD_CACHED_FRAC (0.5); a response with no
                cached_tokens (a dry run, an error) is NO EVIDENCE and is counted, not a miss;
  * bins      = EDGES_S (5, 15, 30, 60, 120 s) -> 6 bins [0,5) [5,15) [15,30) [30,60) [60,120) [120,inf);
  * posterior = (PRIOR_ALPHA + cold_b) / (PRIOR_ALPHA + PRIOR_BETA + n_b), a Beta(0.1, 1.9) prior
                per bin (mean 0.05, a declared weak prior, see PRIOR_ALPHA), running counts, updated only from this run's own previous robot responses. No committed-cell fit, no s4 data, no constant fitted
                to a prior cell appears in this file.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

Q4_SWITCH = "live2_q4_avoided_rebuild_credit"
FORCE_ZERO_ATTR = "q4_force_zero_credit"        # NEGATIVE-CONTROL hook only; default absent/False

EDGES_S: Tuple[float, ...] = (5.0, 15.0, 30.0, 60.0, 120.0)
N_BINS = len(EDGES_S) + 1
COLD_CACHED_FRAC = 0.5
# A WEAK, DECLARED PRIOR favouring warm: Beta(0.1, 1.9), mean 0.05, strength 2 pseudo-observations,
# fitted to nothing. A flat Beta(1, 1) was built first and rejected on its first 300 s dry: it
# credits every idle gap, including under 5 s, at 0.5 before any evidence, which gave 4,964 touches
# against 0. (A residency-belief gate was also tried and dropped: the belief reads COLD for 6,308 of
# 7,537 decisions in that dry because it promotes only on a COMPLETE build, so it is not a usable
# "is this resident" signal for a partially built history.)
PRIOR_ALPHA = 0.1
PRIOR_BETA = 1.9


class Q4SwitchError(RuntimeError):
    """The q4 switch was a truthy CLASS attribute, a non-bool, or on without `-q2m`."""


def arm_enables(arm: Any) -> bool:
    """Is q4 on for THIS ARM INSTANCE? Default False. Instance-dict lookup only; a truthy CLASS
    attribute RAISES, so does a non-bool, and so does ON without the q2m switch (and so without
    D249 and q2, which q2m itself requires). READ SITES: `arms_v6state.V6StateArm._q4_on`
    (decide: credit computed and passed to plan_state) and `arms_v6fairfeed.live2_completed`
    (estimator updated)."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if Q4_SWITCH not in own:
        for klass in type(arm).__mro__:
            if bool(klass.__dict__.get(Q4_SWITCH, False)):
                raise Q4SwitchError(
                    "%s is ON as a CLASS attribute of %s and the instance declares nothing; q4 "
                    "requires an arm-scoped INSTANCE attribute" % (Q4_SWITCH, klass.__name__))
    v = own.get(Q4_SWITCH, False)
    if not isinstance(v, bool):
        raise Q4SwitchError("%s must be a bool, got %r" % (Q4_SWITCH, type(v).__name__))
    if v:
        import d261_margin_scope as _MS                                        # noqa: PLC0415
        if not _MS.q2m_arm_enables(arm):
            raise Q4SwitchError("q4 requires the q2m switch on the same instance")
    return v


def enabled_cached(arm: Any) -> bool:
    """`arm_enables`, resolved once per instance and memoised (it runs on every completion)."""
    d = vars(arm)
    v = d.get("_q4_resolved")
    if v is None:
        v = arm_enables(arm)
        d["_q4_resolved"] = v
    return bool(v)


def bin_of(gap_s: float) -> int:
    g = max(float(gap_s), 0.0)
    for i, e in enumerate(EDGES_S):
        if g < e:
            return i
    return len(EDGES_S)


class ColdEstimator:
    """Binned running fraction with a Beta prior. Pure; no I/O, no clock."""

    def __init__(self, alpha: float = PRIOR_ALPHA, beta: float = PRIOR_BETA) -> None:
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.n: List[int] = [0] * N_BINS
        self.cold: List[int] = [0] * N_BINS

    def update(self, gap_s: float, cold: bool) -> int:
        b = bin_of(gap_s)
        self.n[b] += 1
        if cold:
            self.cold[b] += 1
        return b

    def p_cold_bin(self, b: int) -> float:
        return (self.alpha + self.cold[b]) / (self.alpha + self.beta + self.n[b])

    def p_cold(self, gap_s: float) -> Tuple[float, int]:
        b = bin_of(gap_s)
        return self.p_cold_bin(b), b

    def as_dict(self) -> Dict[str, Any]:
        return {"edges_s": list(EDGES_S), "cold_cached_frac": COLD_CACHED_FRAC,
                "prior": [self.alpha, self.beta], "n": list(self.n), "cold": list(self.cold),
                "p_cold": [round(self.p_cold_bin(i), 6) for i in range(N_BINS)]}


class Q4State:
    def __init__(self) -> None:
        self.est = ColdEstimator()
        self.last_done: Dict[str, float] = {}


def state_of(arm: Any) -> Q4State:
    d = vars(arm)
    s = d.get("_q4_state")
    if s is None:
        s = Q4State()
        d["_q4_state"] = s
    return s


def _is_robot(arm: Any, device_id: Any) -> bool:
    rules = vars(arm).get("_rules")
    roster = (getattr(rules, "_roster", None) or {}) if rules is not None else {}
    return str(((roster.get("devices") or {}).get(device_id) or {}).get("type")) == "robot"


def observe(arm: Any, rec: Dict[str, Any]) -> None:
    """READ-SIDE of the learning: one completion. Updates the session's last-done time for EVERY
    completion that carries a session, and the cold estimator for ROBOT QUESTIONS only."""
    st = state_of(arm)
    stats = arm.stats
    sid = rec.get("session_id")
    if not sid:
        stats["q4_obs_no_session"] += 1
        return
    sid = str(sid)
    prev = st.last_done.get(sid)
    t_sub = rec.get("t_submit")
    t_done = rec.get("t_done")
    if (str(rec.get("kind")) == "recall" and _is_robot(arm, rec.get("device_id"))):
        ct, pt = rec.get("cached_tokens"), rec.get("prompt_tokens")
        if ct is None or not pt:
            stats["q4_obs_no_cached_evidence"] += 1
        elif prev is None or t_sub is None:
            stats["q4_obs_no_previous_request"] += 1
        else:
            cold = (float(ct) / float(pt)) < COLD_CACHED_FRAC
            b = st.est.update(float(t_sub) - float(prev), cold)
            stats["q4_obs_n"] += 1
            stats["q4_obs_bin%d_n" % b] += 1
            if cold:
                stats["q4_obs_cold"] += 1
                stats["q4_obs_bin%d_cold" % b] += 1
            stats["q4_estimator"] = st.est.as_dict()
    if t_done is not None:
        st.last_done[sid] = max(float(t_done), st.last_done.get(sid, float("-inf")))


def credit_terms(arm: Any, sid: str, now_s: float) -> Optional[Tuple[float, int, float]]:
    """(P(cold | idle gap), bin, gap) for this session now, or None when no previous request of
    the session has completed (no gap exists; counted by the caller)."""
    st = state_of(arm)
    prev = st.last_done.get(str(sid))
    if prev is None:
        return None
    gap = max(float(now_s) - float(prev), 0.0)
    p, b = st.est.p_cold(gap)
    return p, b, gap


def would_choose_without(cands: Any, credit: float, m_eff: float) -> str:
    """The chosen action had the credit not been added: TOUCH's value less `credit`, same rule
    (`best = max by (value, name)`, deviate only if best.value - KEEP.value > margin_effective)."""
    best_v, best_n = None, "KEEP"
    for c in cands or ():
        if not (c.scored and c.value is not None):
            continue
        v = float(c.value) - (float(credit) if c.name == "TOUCH" else 0.0)
        if best_v is None or (v, c.name) > (best_v, best_n):
            best_v, best_n = v, c.name
    if best_v is None or best_n == "KEEP":
        return "KEEP"
    return best_n if best_v - 0.0 > float(m_eff) else "KEEP"
