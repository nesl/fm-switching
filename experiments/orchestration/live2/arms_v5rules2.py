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

import catchup_prefill as CU
import engine_actions as EA
import share_admission as SA
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

# ---------------------------------------------------- D230 (2) / D178 (3) THE PER-TYPE GUARD
# WHY THIS EXISTS, from the measurement and not from a preference. `d230_guard_107.json`
# (79eef689) replayed the guard's own EWMA over the four committed rung-3 1x cells and found
# the single `GUARD_LAG_S_DEFAULT = 2.0` above UNREACHABLE ON THE ALERT CHANNEL at half the
# seeds: the episodic EWMA never reached 2.0 s at all at s6 (max 1.879 s) or s7 (max 0.964 s),
# while alert lag exceeded its own D178 (3) threshold of 0.8 s in 92 and 48 periods there. The
# guard's 277 pooled firings were 257 recall against 16 alert. Pooled, the alert channel
# crossed 0.8 s in 497 of 47,997 periods (1.0355 percent), above D230 (2)'s pre-declared 1
# percent bar, so D178 (3) is NOT amended and this variant is built.
#
# WHAT IT IS, SAID HERE BECAUSE THE NAME INVITES THE WRONG READING. This is still the
# D160 (2) SATURATION EARLY WARNING: when it fires, the base action is returned UNTOUCHED and
# only the background warming channel is shed (and, at rung 2+, state actions deferred). It is
# NOT a per-request deadline rescue and must not be justified as rescuing individual late
# alerts. What the per-type form changes is WHEN the policy stops adding speculative prefill
# work on behalf of a type, measured against that type's own deadline.
#
# DEFAULT OFF (D187). It is ON only in the labelled rung-3 variant `covex-v6-fair-final-ptg`.
# Every other arm keeps the single 2.0 s bar and the two-channel read, byte-identically.
#
# NOT IN SCOPE, said here rather than discovered later: D166 (3)'s EXIT HYSTERESIS (all
# signals below 0.5x entry for 2 s) is NOT ruled out by the measurement and is NOT built here.
GUARD_PER_TYPE_SWITCH = "guard_per_type"
# The three thresholds, taken from `share_admission` so there is ONE definition of "80 percent
# of each type's deadline" in the tree and it is derived from the committed deadlines.
GUARD_LAG_S_BY_CLASS_D178 = dict(SA.GUARD_LAG_S_BY_CLASS)
# ("episodic", "recall", "assistance"): the two committed channels plus the third one added at
# `coordinator._collect`. `DEADLINE_CLASSES` above is NOT widened, because it is what the
# committed single-threshold read and the committed backlog sum are defined over.
GUARD_PER_TYPE_CLASSES = tuple(GUARD_LAG_S_BY_CLASS_D178)
# D230 (2) limitation 1: one row per decision period. 1,200 s at a 0.1 s period is 12,000
# rows, so the cap is a bound on a pathological run and not on a normal one.
# D166 (3) / D178 (3) EXIT HYSTERESIS: "exit after ALL signals below 0.5x entry for 2 s".
# The guard without it is MEMORYLESS: it re-decides from scratch in every 100 ms period, so a
# signal sitting on its threshold toggles the warming channel on and off at 10 Hz. The latch
# makes the guard a state machine: ENTRY on any signal above its own entry threshold, EXIT
# only after every signal has been continuously below 0.5x its entry threshold for 2 s. In
# between is the hysteresis band, where the latch HOLDS whatever it already was.
#
# BOTH NUMBERS ARE D166 (3) AS WRITTEN and neither is tuned here.
GUARD_EXIT_FACTOR_D166 = 0.5
GUARD_EXIT_HOLD_S_D166 = 2.0
GUARD_HYSTERESIS_SWITCH = "guard_hysteresis"
GUARD_LOG_CAP_DEFAULT = 200000


class GuardPerTypeSwitchError(RuntimeError):
    """The per-type guard switch did not take on the instance it was set on."""


def guard_hysteresis_enabled(arm) -> bool:
    """Instance-only, same strictness and same reason as `guard_per_type_enabled`."""
    if getattr(type(arm), GUARD_HYSTERESIS_SWITCH, False):
        raise GuardPerTypeSwitchError(
            "%s is set on the CLASS %s. It must be an arm-scoped INSTANCE attribute."
            % (GUARD_HYSTERESIS_SWITCH, type(arm).__name__))
    return bool(vars(arm).get(GUARD_HYSTERESIS_SWITCH, False))


def guard_per_type_enabled(arm) -> bool:
    """Read the switch from the INSTANCE only, the strictness `release_recheck.arm_enables`
    uses and for the same reason: a truthy CLASS attribute would turn the per-type guard on
    for every arm that inherits this one and make the cells incomparable."""
    if getattr(type(arm), GUARD_PER_TYPE_SWITCH, False):
        raise GuardPerTypeSwitchError(
            "%s is set on the CLASS %s. It must be an arm-scoped INSTANCE attribute."
            % (GUARD_PER_TYPE_SWITCH, type(arm).__name__))
    return bool(vars(arm).get(GUARD_PER_TYPE_SWITCH, False))


class V5Rules2Arm:
    """The base plus one channel, as v5-rules is, with the channel gated two ways."""

    def __init__(self, name: str = "v5-rules-2",
                 warm_ahead: bool = True,
                 chunk_tokens: int = CHUNK_TOKENS_DEFAULT,
                 guard_lag_s: float = GUARD_LAG_S_DEFAULT,
                 guard_backlog: int = GUARD_BACKLOG_DEFAULT,
                 guard_per_type: bool = False,
                 guard_lag_s_by_class: Optional[Dict[str, float]] = None,
                 guard_hysteresis: bool = False,
                 guard_exit_factor: float = GUARD_EXIT_FACTOR_D166,
                 guard_exit_hold_s: float = GUARD_EXIT_HOLD_S_D166,
                 guard_log: bool = False,
                 guard: bool = True,
                 just_in_time: bool = True,
                 slice_tokens: Optional[int] = EA.WARM_AHEAD_SLICE_TOKENS,
                 over_limit_infeasible: bool = False) -> None:
        from hybrid.hybrid_arm import CONFIGS, HybridArm
        if V5RULES2_BASE not in CONFIGS:
            raise KeyError("committed base config %r is absent from hybrid_arm.CONFIGS"
                           % (V5RULES2_BASE,))
        # The committed config taken whole, exactly as arms_v5rules does. Not re-derived.
        self._base = HybridArm(name=V5RULES2_BASE, **CONFIGS[V5RULES2_BASE])
        # D170, default OFF. Set on BOTH: `self` is what HybridArm.__call__ runs against, and
        # `self._base` is the config mirror, so leaving one unset is how a switch reads as live
        # and decides nothing.
        self._base.over_limit_infeasible = bool(over_limit_infeasible)
        self.over_limit_infeasible = bool(over_limit_infeasible)
        self.name = name
        self.warm_ahead = bool(warm_ahead)
        self.chunk_tokens = int(chunk_tokens)
        self.guard_lag_s = float(guard_lag_s)
        self.guard_backlog = int(guard_backlog)
        # D230 (2) / D178 (3). All three default OFF, so this block changes nothing for any
        # arm that does not ask for it. `guard_lag_s_by_class` is populated either way and is
        # UNREAD while `guard_per_type` is False.
        self.guard_per_type = bool(guard_per_type)
        self.guard_lag_s_by_class: Dict[str, float] = (
            dict(GUARD_LAG_S_BY_CLASS_D178) if guard_lag_s_by_class is None
            else {str(k): float(v) for k, v in dict(guard_lag_s_by_class).items()})
        if self.guard_per_type and not self.guard_lag_s_by_class:
            raise GuardPerTypeSwitchError(
                "guard_per_type is on with an EMPTY threshold table, which would make the\n"
                "per-type test vacuously false in every period: the arm would read as a\n"
                "guarded arm and would never fire. Refuse rather than return the null.")
        # D166 (3). OFF by default, so the guard stays the memoryless committed one for every
        # arm that does not ask for the latch.
        self.guard_hysteresis = bool(guard_hysteresis)
        self.guard_exit_factor = float(guard_exit_factor)
        self.guard_exit_hold_s = float(guard_exit_hold_s)
        # the latch and its clock. `_g_last_t` is SEPARATE from the log's `_guard_log_last_t`
        # on purpose: the latch must advance exactly once per decision period whether or not
        # the log is on, and tying them would make the state machine depend on a log switch.
        self._g_latched = False
        self._g_below_since: Optional[float] = None
        self._g_last_t: Optional[float] = None
        self.guard_log = bool(guard_log)
        self.GUARD_LOG_CAP = int(GUARD_LOG_CAP_DEFAULT)
        # Present ONLY when asked for: `coordinator.write_guard_log` keys on the attribute
        # being absent, so an arm without the log creates no file at all.
        if self.guard_log:
            self.guard_log_rows: List[Dict[str, Any]] = []
            self._guard_log_last_t = None
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
                                guard_per_type=self.guard_per_type,
                                guard_lag_s_by_class=(dict(self.guard_lag_s_by_class)
                                                      if self.guard_per_type else None),
                                guard_hysteresis=self.guard_hysteresis,
                                guard_exit_factor=(self.guard_exit_factor
                                                   if self.guard_hysteresis else None),
                                guard_exit_hold_s=(self.guard_exit_hold_s
                                                   if self.guard_hysteresis else None),
                                guard_log=self.guard_log,
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
        # ---- D230 (2) / D178 (3) PER-TYPE TEST. DEFAULT OFF; nothing below executes for any
        # other arm, which is why every other arm stays byte-identical BY CONSTRUCTION.
        # The per-type test REPLACES the single-threshold one in `by_lag`. `lag_s` KEEPS ITS
        # COMMITTED MEANING (the max over the two committed deadline classes) so that a reader
        # comparing that field across arms is comparing one quantity; the per-type decision is
        # in `by_lag`, and the per-type signal is reported beside it under `per_type`.
        lag_by_class: Dict[str, float] = {}
        fired: tuple = ()
        if self.guard_per_type:
            thr = self.guard_lag_s_by_class
            lag_by_class = {k: float(lat.get(k, 0.0) or 0.0) for k in thr}
            fired = tuple(k for k in GUARD_PER_TYPE_CLASSES
                          if k in thr and lag_by_class[k] >= float(thr[k]))
            by_lag = bool(fired)
        # ---- D166 (3) EXIT HYSTERESIS. DEFAULT OFF; nothing below executes otherwise, so the
        # guard stays the memoryless committed one for every other arm.
        #
        # `by_lag` and `by_backlog` KEEP THEIR COMMITTED MEANING: they are the ENTRY tests,
        # i.e. what crossed in THIS period. The latched state is reported separately as
        # `latched`, and it is `active` that the consumers read. Overwriting `by_lag` with the
        # latch would make the committed counters `guard_by_lag` / `guard_by_backlog` count
        # something other than what their names have always meant.
        #
        # THE LATCH ADVANCES EXACTLY ONCE PER DECISION PERIOD. `guard_state` is read up to
        # four times in one period by one rung (here, arms_v6state.py:382, arms_v6cf.py:442,
        # arms_v6cfr3.py:371) and every read sees the SAME observation. A state machine that
        # advanced per READ would make the exit clock run at the number of consumers the rung
        # happens to have, so the 2 s hold would mean 2 s on rung 1 and 0.5 s on rung 4. Keyed
        # on `obs.now_s`, so repeat reads in the same period are IDEMPOTENT by construction.
        entry = bool(by_lag or by_backlog)
        latched = entry
        below_exit = None
        if self.guard_hysteresis:
            f = self.guard_exit_factor
            if self.guard_per_type:
                thr_exit = {k: f * float(v) for k, v in self.guard_lag_s_by_class.items()}
                lag_ok = all(float(lat.get(k, 0.0) or 0.0) < v for k, v in thr_exit.items())
            else:
                thr_exit = {"lag_s": f * self.guard_lag_s}
                lag_ok = lag < thr_exit["lag_s"]
            thr_exit["backlog"] = f * float(self.guard_backlog)
            below_exit = bool(lag_ok and backlog < thr_exit["backlog"])
            t_now = float(getattr(obs, "now_s", 0.0) or 0.0)
            if self._g_last_t is None or t_now != self._g_last_t:
                self._g_last_t = t_now
                if entry:
                    # ENTRY always wins and restarts the exit clock.
                    if not self._g_latched:
                        self.stats["guard_hyst_entries"] += 1
                    self._g_latched = True
                    self._g_below_since = None
                elif below_exit:
                    if self._g_below_since is None:
                        self._g_below_since = t_now
                    if (self._g_latched
                            and t_now - self._g_below_since >= self.guard_exit_hold_s):
                        self._g_latched = False
                        self._g_below_since = None
                        self.stats["guard_hyst_exits"] += 1
                else:
                    # the HYSTERESIS BAND: above the exit bar, below every entry bar. The
                    # latch holds and the exit clock is reset, which is the whole mechanism.
                    self._g_below_since = None
                    if self._g_latched:
                        self.stats["guard_hyst_held_in_band"] += 1
            else:
                self.stats["guard_hyst_repeat_reads"] += 1
            latched = self._g_latched
            if latched and not entry:
                self.stats["guard_hyst_active_without_entry"] += 1
        g = dict(lag_s=lag, backlog=backlog, by_lag=by_lag, by_backlog=by_backlog,
                 active=bool(self.guard and latched))
        if self.guard_hysteresis:
            g["hysteresis"] = dict(latched=bool(latched), entry=entry,
                                   below_exit=below_exit,
                                   exit_factor=self.guard_exit_factor,
                                   exit_hold_s=self.guard_exit_hold_s,
                                   exit_thresholds=thr_exit,
                                   below_since=self._g_below_since)
        if self.guard_per_type:
            g["per_type"] = dict(thresholds_s=dict(self.guard_lag_s_by_class),
                                 lag_s_by_class=dict(lag_by_class),
                                 fired_classes=list(fired))
        # ---- D230 (2) limitation 1: the per-decision-period log. LOGGING ONLY: the rows are
        # appended and never read back by anything, and `coordinator.write_guard_log` writes
        # them after the run. `guard_state` is read more than once in a period (here, plus
        # `arms_v6state.py:382`, `arms_v6cf.py:442`, `arms_v6cfr3.py:371`), and all those reads
        # see the SAME observation, so the FIRST read of a period is the row and the rest are
        # counted. Without that the "per decision period" denominator would be wrong by the
        # number of consumers the rung happens to have.
        if self.guard_log:
            t = float(getattr(obs, "now_s", 0.0) or 0.0)
            if self._guard_log_last_t is not None and t == self._guard_log_last_t:
                self.stats["guard_log_repeat_reads"] += 1
            elif len(self.guard_log_rows) < self.GUARD_LOG_CAP:
                self._guard_log_last_t = t
                self.stats["guard_log_periods"] += 1
                row = dict(t=round(t, 6), lag_s=round(lag, 6), backlog=backlog,
                           by_lag=bool(by_lag), by_backlog=bool(by_backlog),
                           active=bool(g["active"]))
                if self.guard_hysteresis:
                    row["latched"] = bool(latched)
                    row["entry"] = entry
                    row["below_exit"] = below_exit
                if self.guard_per_type:
                    row["lag_s_by_class"] = {k: round(v, 6)
                                             for k, v in sorted(lag_by_class.items())}
                    row["fired_classes"] = list(fired)
                self.guard_log_rows.append(row)
            else:
                self.stats["guard_log_dropped_cap"] += 1
        return g

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
        _cu = CU.arm_enables(self)                  # READ SITE of live2_catchup_prefill
        if _cu:
            CU.observe(self, obs, self._roster)
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
        _cu_extra: List[str] = []
        if _cu:
            _cu_extra = CU.order(self, CU.candidates(self, obs, self._roster, set(cands)), float(obs.now_s))
        if not cands and not _cu_extra:
            return act
        # advance the chunk edge for every session we are about to ask for, so the next ask needs
        # another full chunk of new material. Done on the ASK and not on the build, because the
        # coordinator may serve an ask with a partial slice and the arm must not re-ask per slice.
        est_now = self._roster.get("est_tokens_by_session") or {}
        for sid in cands:
            self._est_at_last_ask[sid] = int(est_now.get(sid, 0))
        plan = EA.plan_warm_ahead(obs, list(cands) + _cu_extra, slice_tokens=self.slice_tokens,
                                  yield_to_deadline=True,
                                  targets=getattr(self._base, "_targets", None))
        _acts = list(plan.actions)
        if _cu_extra:
            CU.account(self, plan, _cu_extra, float(obs.now_s))
            _x = set(_cu_extra)
            _acts = ([a for a in _acts if a.session_id not in _x]
                     + sorted([a for a in _acts if a.session_id in _x],
                              key=lambda a: _cu_extra.index(a.session_id)))
        self.stats["warm_ahead_wanted"] += len(plan.wanted)
        self.stats["warm_ahead_emitted"] += plan.n_warm_ahead
        self.stats["warm_ahead_unexpressible"] += len(plan.unexpressible)
        if plan.yielded:
            self.stats["warm_ahead_yielded_epochs"] += 1
        if _acts:
            act.sessions = list(act.sessions) + _acts
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
