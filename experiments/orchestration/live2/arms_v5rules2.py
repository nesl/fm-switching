#!/usr/bin/env python3
"""v5-rules-2 (D160): base `hybrid-F-lhreq-noc3` + CHUNKED just-in-time warming + a SATURATION
GUARD on live engine feedback. It replaces v5-rules-1.0's per-frame warming and its bare W2 yield.

WHY BOTH CHANGES, in the user's words condensed to the mechanism each one fixes.

D160 (1) WARMING GRANULARITY. v5-rules asked `plan_warm_ahead` for EVERY robot session EVERY epoch
and relied on `coordinator._advance_build` to no-op when nothing new had arrived. Under per-frame
upload (D154 (4)) something new arrives on every frame, so a prefill was issued per frame: about
84,000 prefills per run, driving engine overlap from about 10 to about 2,000. That coupled upload to
warming, contrary to D150 SYNC (1), and made warming cost scale with REQUEST COUNT. D152 (3) is
withdrawn. Upload stays per frame; warming happens in CHUNKS.

D160 (2) SATURATION GUARD. `engine_actions.deadline_work_at_risk` never fired in 12,001 epochs, and
the diagnosis (`reports/study_v5rules2_design.md`) is that it is UNEXERCISED rather than broken:
firing needs a robot question still unanswered 2.1 s after arrival (laxity 0.3 of a 3.0 s deadline)
while the run offers 20 robot questions and answers them at 0.27 to 0.45 s. It is also the wrong
signal, because by the time it could fire the deadline is already blown by one to two orders of
magnitude. The guard reads LIVE ENGINE FEEDBACK instead, and sheds background warming first.

NEVER A LOAD THRESHOLD. D159 (A) forbids throttling on offered load, and that is forced by
measurement rather than preference: the bracketed knee is WITHDRAWN because crossing and
non-crossing cells interleave across 4,670 to 4,707 uncached tok/s
(`reports/study_saturation_knee.md`). Offered load does not determine the regime; observed lag does.

WHAT THE ARM READS, and every one of these is causal, known at the current epoch, never a future
trace value:

  obs.cloud.latency_estimate_s   the coordinator's EWMA of OBSERVED ttft_s per class, fed at
                                 `coordinator.py:967` from each completion's own ttft_s. Keys
                                 "episodic" (dashcam, 1.0 s deadline) and "recall" (robot and
                                 pieces, 3.0 s deadline). Both are deadline classes.
  obs.cloud.queued_by_class      pending work per class
  obs.cloud.running_by_class     in-flight work per class
  roster est_tokens_by_session   cumulative history the cloud HAS RECEIVED (D160 (1), added to the
                                 roster for this arm; `cstate.py:311` and `:330`)
  roster built_tokens_by_session how much of it the cloud has already built
  obs.recall arrival times       the arm's OWN observed inter-question intervals, for the horizon

THE HORIZON IS ESTIMATED FROM THE ARM'S OWN HISTORY, never from the trace. `_expected_gap_s` is an
EWMA over intervals between recall questions this arm has ALREADY SEEN on that device (D11 / D48).
A horizon that could see real next-ask times would measure an oracle, not a policy, and
`reask_trace_proofs`-style future reads are exactly the failure this arm must not have. The
no-future-read proof is in `v5/v5rules2_proofs.py`.

EVERY CAPACITY CONSTANT IS A PARAMETER, per D159 (A), with its default declared here and its
provenance given. Nothing is a magic number inside a branch.

NOTHING HERE MEASURES ANYTHING.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import engine_actions as EA
from interface import Action, Observation

V5RULES2_VERSION = "v5-rules-2.0"
V5RULES2_BASE = "hybrid-F-lhreq-noc3"

# ---------------------------------------------------------------- declared constants (D159 A)
# D160 (1): a session's unwarmed tail is prefilled when it reaches this many tokens. 2,048 tokens is
# about 22 robot frames under the committed D2 accounting, so warming cost scales with MATERIAL
# instead of with request count. Declared default, swept later.
CHUNK_TOKENS_DEFAULT = 2048

# D160 (2) guard thresholds, DECLARED BEFORE ANY LIVE RUN and taken from COMMITTED CELLS ONLY.
# Measured over 680 windows and 712,902 requests in 58 committed cells
# (`v5/regime_zones.py`, `v5/guard_thresholds.py`), classified by each 100 s window's own
# first-token p50 into healthy (<= 2.781 s), unclassified, and collapsed (> 31 s):
#
#   zone        lag p50   p90     p99      backlog p50  p90   p99   max
#   healthy     0.350 s   0.929   5.309              5   13    71   177
#   middle     11.161 s  32.237  74.632            160  403  1109  1149
#   collapsed 104.204 s 370.199 479.199           1011 1740  3764  4111
#
# GUARD_LAG_S = 2.0: above the 90th percentile of healthy operation (0.929 s) and far below the
# middle zone's median (11.161 s). It therefore fires as a WARNING while the engine is still
# healthy, which is the whole point: shed warming BEFORE the regime turns, not after.
GUARD_LAG_S_DEFAULT = 2.0
# GUARD_BACKLOG = 100: between the healthy 99th percentile (71) and the middle median (160).
GUARD_BACKLOG_DEFAULT = 100
# The EWMA is per class and a single slow request can reach 39.9 s inside an otherwise healthy
# window, so the guard needs both signals and fires on EITHER. One slow request must not shed
# warming on its own; a sustained lag or a real backlog must.
DEADLINE_CLASSES = ("episodic", "recall")


class V5Rules2Arm:
    """The base plus one channel, as v5-rules is, with the channel gated two ways."""

    def __init__(self, name: str = "v5-rules-2",
                 warm_ahead: bool = True,
                 chunk_tokens: int = CHUNK_TOKENS_DEFAULT,
                 guard_lag_s: float = GUARD_LAG_S_DEFAULT,
                 guard_backlog: int = GUARD_BACKLOG_DEFAULT,
                 guard: bool = True,
                 just_in_time: bool = True,
                 slice_tokens: Optional[int] = EA.WARM_AHEAD_SLICE_TOKENS) -> None:
        from hybrid.hybrid_arm import CONFIGS, HybridArm
        if V5RULES2_BASE not in CONFIGS:
            raise KeyError("committed base config %r is absent from hybrid_arm.CONFIGS"
                           % (V5RULES2_BASE,))
        # The committed config taken whole, exactly as arms_v5rules does. Not re-derived.
        self._base = HybridArm(name=V5RULES2_BASE, **CONFIGS[V5RULES2_BASE])
        self.name = name
        self.warm_ahead = bool(warm_ahead)
        self.chunk_tokens = int(chunk_tokens)
        self.guard_lag_s = float(guard_lag_s)
        self.guard_backlog = int(guard_backlog)
        self.guard = bool(guard)
        self.just_in_time = bool(just_in_time)
        self.slice_tokens = None if slice_tokens is None else int(slice_tokens)
        self.arm_version = V5RULES2_VERSION
        self.live2_source = ("hybrid/hybrid_arm.py::HybridArm(CONFIGS['%s']) AS COMMITTED, plus "
                             "live2/engine_actions.py::plan_warm_ahead gated by a CHUNK trigger "
                             "and a SATURATION GUARD (D160)" % V5RULES2_BASE)
        self.stats: Counter = Counter()
        self._roster: Dict[str, Any] = {}
        # causal per-device question-interval estimate (D11 / D48)
        self._last_q_t: Dict[str, float] = {}
        self._gap_ewma: Dict[str, float] = {}
        self._seen_q: set = set()
        # D160 (1): the est_tokens at which this session was LAST asked for. Without it the chunk
        # test is a LEVEL test on the tail, which stays open permanently once uploads outpace
        # builds, so it re-fires every epoch and barely reduces prefills at all (measured: 800
        # pieces against v5-rules' 827, a 3 percent reduction, with chunk_trigger_size firing
        # 73,564 times). The trigger must be ONE ASK PER CHUNK OF NEW MATERIAL, which is an EDGE
        # on cumulative uploaded tokens, and that is what makes warming cost scale with material
        # instead of with request count.
        self._est_at_last_ask: Dict[str, int] = {}
        # D160 (1) addendum: at most ONE early (JIT) warm per session per expected question cycle,
        # reset when that session's next question arrives. Without this cap the JIT branch is
        # unbounded, and under rq30 re-asks it degenerates completely: the horizon IS the expected
        # inter-question gap, so the test `now >= last + gap - horizon` reduces to `now >= last`,
        # which is true in every epoch after the session's first question. The cap is what makes
        # the branch finite, and it bounds JIT warms at one per question rather than one per epoch.
        self._jit_used: Dict[str, bool] = {}

    # ---- delegation, identical in shape to arms_v5rules.py ------------------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_base"], k)

    def __call__(self, obs: Observation) -> Action:
        # THE CLASS IS NAMED STATICALLY, and that is the whole fix. `self._base.__class__`
        # resolves against whatever object is actually running: when a V5FullArm borrows this
        # method, its `_base` is a V5Rules2Arm, so the lookup returned THIS method again and the
        # call recursed until the stack ran out. The behaviour this line wants is "run the HYBRID
        # arm's decision step with my state", and HybridArm is what it must say.
        from hybrid.hybrid_arm import HybridArm                                # noqa: PLC0415
        return HybridArm.__call__(self, obs)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        self._roster = dict(roster or {})
        self._base.live2_roster(roster)

    def live2_configure(self, **kw: Any) -> None:
        self._base.live2_configure(**kw)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._base.live2_describe()) if hasattr(self._base, "live2_describe") else {}
        d.update(arm=self.name, arm_version=V5RULES2_VERSION,
                 v5_rules2=dict(base=V5RULES2_BASE, warm_ahead=self.warm_ahead,
                                chunk_tokens=self.chunk_tokens,
                                just_in_time=self.just_in_time,
                                guard=self.guard, guard_lag_s=self.guard_lag_s,
                                guard_backlog=self.guard_backlog,
                                guard_signal="observed ttft EWMA per deadline class and "
                                             "queued+running deadline work; NEVER offered load",
                                horizon="causal EWMA of this arm's own observed inter-question "
                                        "intervals per device (D11 / D48)",
                                slice_tokens=self.slice_tokens,
                                candidates="robot sessions with an unwarmed tail at or above the "
                                           "chunk, or a question expected within the horizon",
                                counterfactual=False, planner=False, margin_cf=None,
                                engine_actions_version=EA.ENGINE_ACTIONS_VERSION),
                 source=self.live2_source)
        return d

    # ---- the saturation guard (D160 (2)) ------------------------------------------------------
    def guard_state(self, obs: Observation) -> Dict[str, Any]:
        """Live feedback only. Reported as a dict so a proof can read it without re-deriving it."""
        c = obs.cloud
        lat = dict(getattr(c, "latency_estimate_s", None) or {})
        lag = max([float(lat.get(k, 0.0) or 0.0) for k in DEADLINE_CLASSES] or [0.0])
        q = dict(getattr(c, "queued_by_class", None) or {})
        r = dict(getattr(c, "running_by_class", None) or {})
        backlog = sum(int(q.get(k, 0) or 0) + int(r.get(k, 0) or 0) for k in DEADLINE_CLASSES)
        by_lag = lag >= self.guard_lag_s
        by_backlog = backlog >= self.guard_backlog
        return dict(lag_s=lag, backlog=backlog, by_lag=by_lag, by_backlog=by_backlog,
                    active=bool(self.guard and (by_lag or by_backlog)))

    # ---- the causal horizon (D11 / D48) -------------------------------------------------------
    def _observe_questions(self, obs: Observation) -> None:
        """EWMA of intervals between questions THIS ARM HAS ALREADY SEEN. No future read."""
        for qy in obs.recall:
            if qy.query_id in self._seen_q:
                continue
            self._seen_q.add(qy.query_id)
            # a new question on this session opens a new expected-question cycle
            self._jit_used.pop(qy.session_id, None)
            did = (self._roster.get("session_device") or {}).get(qy.session_id)
            if did is None:
                continue
            prev = self._last_q_t.get(did)
            t = float(qy.arrival_s)
            if prev is not None and t > prev:
                gap = t - prev
                cur = self._gap_ewma.get(did)
                self._gap_ewma[did] = gap if cur is None else 0.3 * gap + 0.7 * cur
            self._last_q_t[did] = t

    def _expected_gap_s(self, device_id: str) -> Optional[float]:
        return self._gap_ewma.get(device_id)

    # ---- chunked, just-in-time candidate selection (D160 (1)) ---------------------------------
    def _candidates(self, obs: Observation) -> List[str]:
        r = self._roster or {}
        devs = r.get("devices") or {}
        sdev = r.get("session_device") or {}
        est = r.get("est_tokens_by_session") or {}
        built = r.get("built_tokens_by_session") or {}
        if not est:
            # The observable D160 (1) needs is absent: without `est_tokens_by_session` there is no
            # local test for an unwarmed tail and this arm would silently degrade to v5-rules'
            # every-session-every-epoch behaviour, which is the thing it exists to replace. Refuse.
            self.stats["chunk_roster_missing_est_tokens"] += 1
            return []
        out = []
        for sid, did in sdev.items():
            if str((devs.get(did) or {}).get("type")) != "robot":
                continue
            est_now = int(est.get(sid, 0))
            tail = est_now - int(built.get(sid, 0))
            if tail <= 0:
                continue
            # EDGE on cumulative uploaded tokens: at least one chunk of NEW material since the
            # last ask for this session. The tail must also still be unbuilt, or there is nothing
            # to warm.
            since = est_now - self._est_at_last_ask.get(sid, 0)
            if tail >= self.chunk_tokens and since >= self.chunk_tokens:
                self.stats["chunk_trigger_size"] += 1
                out.append(sid)
                continue
            if not self.just_in_time:
                continue
            # Earlier than the chunk, because a question is expected soon on this device. Capped
            # at one per session per expected question cycle (D160 (1) addendum) and requiring a
            # non-empty tail, which `tail <= 0: continue` above already guarantees.
            if self._jit_used.get(sid):
                self.stats["jit_suppressed_already_used"] += 1
                continue
            gap = self._expected_gap_s(did)
            if gap is None:
                continue
            last = self._last_q_t.get(did)
            if last is None:
                continue
            if float(obs.now_s) >= last + gap - self._horizon_s(gap):
                self.stats["chunk_trigger_horizon"] += 1
                self._jit_used[sid] = True
                out.append(sid)
        return sorted(set(out))

    def _horizon_s(self, gap: float) -> float:
        """D160 (1): the horizon IS the policy's own expected inter-question time estimate."""
        return float(gap)

    def decide(self, obs: Observation) -> Action:
        act = self._base.decide(obs)
        self._observe_questions(obs)
        if not self.warm_ahead:
            return act
        g = self.guard_state(obs)
        self.stats["epochs"] += 1
        if g["active"]:
            # D160 (2): background warming is shed FIRST, and nothing else changes. The arm returns
            # the base's action untouched, so no other channel is altered by the guard.
            self.stats["guard_active_epochs"] += 1
            self.stats["guard_by_lag"] += 1 if g["by_lag"] else 0
            self.stats["guard_by_backlog"] += 1 if g["by_backlog"] else 0
            self.stats["guard_shed_warming_epochs"] += 1
            return act
        cands = self._candidates(obs)
        if not cands:
            return act
        # advance the chunk edge for every session we are about to ask for, so the next ask needs
        # another full chunk of new material. Done on the ASK and not on the build, because the
        # coordinator may serve an ask with a partial slice and the arm must not re-ask per slice.
        est_now = self._roster.get("est_tokens_by_session") or {}
        for sid in cands:
            self._est_at_last_ask[sid] = int(est_now.get(sid, 0))
        plan = EA.plan_warm_ahead(obs, cands, slice_tokens=self.slice_tokens,
                                  yield_to_deadline=True,
                                  targets=getattr(self._base, "_targets", None))
        self.stats["warm_ahead_wanted"] += len(plan.wanted)
        self.stats["warm_ahead_emitted"] += plan.n_warm_ahead
        self.stats["warm_ahead_unexpressible"] += len(plan.unexpressible)
        if plan.yielded:
            self.stats["warm_ahead_yielded_epochs"] += 1
        if plan.actions:
            act.sessions = list(act.sessions) + list(plan.actions)
        return act


V5RULES2_ARMS = {
    "v5-rules-2": lambda **kw: V5Rules2Arm(name="v5-rules-2", **kw),
    # CLAUDE.md Step 4 negative control: the channel disabled must collapse to the base
    # BYTE-IDENTICALLY, which is stronger than converging.
    "v5-rules-2-off": lambda **kw: V5Rules2Arm(name="v5-rules-2-off", warm_ahead=False, **kw),
    # Ablations, constructible so each claim is checkable one factor at a time.
    "v5-rules-2-noguard": lambda **kw: V5Rules2Arm(name="v5-rules-2-noguard", guard=False, **kw),
    "v5-rules-2-nojit": lambda **kw: V5Rules2Arm(name="v5-rules-2-nojit", just_in_time=False, **kw),
}


def register() -> None:
    """Same contract as `arms_v5rules.register()`: put the names in live2's registry so
    `arms.make_arm(name)` builds them."""
    import arms as A
    A.ARMS.update(V5RULES2_ARMS)
