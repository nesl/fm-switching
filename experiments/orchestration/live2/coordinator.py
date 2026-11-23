#!/usr/bin/env python3
"""The live round-1 COORDINATOR: one process in front of one OpenAI-compatible server. CPU only.

StudyLIVE2-coord. It consumes fleet events, keeps per-device state, calls the active arm once per
100 ms DECISION PERIOD over that period's batched events (D99), submits through the existing `HttpBackend`, and emits `cloud_answer`.
It is a pure HTTP client of the server (request-harness pattern) and scrapes `/metrics`; nothing
in this process opens an engine.

THINGS THIS LOOP DOES FOR EVERY ARM, IDENTICALLY

* `interface.scrub` on every observation and `interface.validate_action` on every action, both
  inside `interface.Policy.__call__`, plus `interface.check_fairness` before the run. An arm
  declaring `reads_future` is REFUSED.
* DEFER(defer_s) is HONOURED (amendment 2, D90): a deferred opportunity is withheld until
  `defer_s` has elapsed and is then re-decided. Arms that never emit DEFER are unaffected.
* D84 cache isolation: every request carries this device's cache salt and one multimodal uuid
  per (device, frame).
* D87: an arm whose published mechanism waits for the device's own answer is charged StudyD8's
  0.567 s rule, so its opportunities are not actionable before then and its DEVICE outcomes are
  delivered then. None of the eight round-1 arms declares it; the charge is implemented so that
  an arm which does is charged automatically.
* Capacities (D56, D76) and targets (D71, D82) are INPUTS, passed to every arm identically.

MONITORING IS CAPACITY-BASED (D62): every decision instant is a candidate; an instant the arm
does not take simply stands as the device's own answer.

UPLOAD MODES (D69): A pushes every frame; B pulls, and the pull message plus the upload count
toward delivered delay. Robot history batches are pushed in both modes.

NOTHING A RUN AGAINST THE CPU STUB PRODUCES IS A MEASUREMENT.
"""
import resource
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import os

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/baselines/reconstructed"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import costs as C                                                       # noqa: E402
from interface import Budget, check_fairness                            # noqa: E402

import bodies as B                                                      # noqa: E402
import offload_policy as OP                                             # noqa: E402
import d162_price as DP                                                 # noqa: E402
# ---- D179 (4) RELEASE RE-CHECK (session B), import. BEGIN --------------------------------------
import release_recheck as RR                                            # noqa: E402
# ---- END D179 (4) -----------------------------------------------------------------------------
# ---- D179 (1) to (3) SHARE ADMISSION (session A), import. BEGIN --------------------------------
import share_admission as SA                                             # noqa: E402
from share_capacity import FLOORS_TOKENS as SCAP_FLOORS                  # noqa: E402
from share_capacity import W_MAX_TOKENS as SCAP_W_MAX                    # noqa: E402
# ---- END D179 (1) to (3) ----------------------------------------------------------------------
import touch_policy as TP                                               # noqa: E402
import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import schema as SC                                                     # noqa: E402
import scores as S2                                                     # noqa: E402
import engine_actions as EA                                              # noqa: E402
from backend import (Live2Backend, Live2Submission, cached_tokens_of,    # noqa: E402
                     output_tokens_of, prompt_tokens_of)

# C5 ATTRIBUTION SUPPORT (candidate, read by no committed arm). The coordinator records the
# [release, finish] span of every NON-MONITOR request it releases together with the uncached
# token count it CHARGED for it, and reports on each monitor completion whether that monitor's
# wait overlapped such a span. The threshold is the one c5_loss_split.py's ruling fixed: a
# "robot prefill" is a build, touch or recall the coordinator itself released with uncached
# >= 200 tokens. Nothing here changes a decision; the two keys are additive on live2_completed
# and the digest proofs in results/orchestration/live2/frozen_test/c5attr_digest_proofs.json
# show every committed arm unchanged.
C5ATTR_UNCACHED_MIN = 200
C5ATTR_SPAN_KEEP_S = 60.0

DEVICE_ANSWER_CHARGE_S = C.DEV_LAT_S         # StudyD8's 0.567 s RULE (D87, amendment 2 item 3)

# D168 / D154 (5): the five arms that WAIT for the device answer (reads_device_answer = True:
# confidence-cascade, cascade-routing, r3-streaming, streamscout, thinking-qwenvl) must wait the
# MEASURED Orin warm latency for the actual question, not the flat 0.567 s proxy. Both live sites
# are decision timing, so this changes what those arms DO; it is a rerun, never a re-score.
#
# Measured-first with a COUNTED fallback, not a silent one: a question absent from the table would
# otherwise reintroduce the proxy invisibly. The fallback is counted so a cell that used it is
# detectable, and the dry proof shows the count is zero on the real traces.
DEVICE_WAIT_MEASURED = True                  # set False to reproduce a committed proxy-0.567 cell
_DEV_WAIT_TABLE = None


_DEV_WAIT_SS = None
_DEV_WAIT_DASH = None


def _device_wait_table():
    global _DEV_WAIT_TABLE
    if _DEV_WAIT_TABLE is None:
        try:
            import data_sources as _DS
            _DEV_WAIT_TABLE = dict(_DS.device_recall_warm_latency_s())
        except Exception:
            _DEV_WAIT_TABLE = {}
    return _DEV_WAIT_TABLE


def _device_wait_single_shot():
    global _DEV_WAIT_SS
    if _DEV_WAIT_SS is None:
        try:
            import data_sources as _DS
            _DEV_WAIT_SS = dict(_DS.single_shot_total_s())
        except Exception:
            _DEV_WAIT_SS = {}
    return _DEV_WAIT_SS


def _device_wait_dashcam():
    global _DEV_WAIT_DASH
    if _DEV_WAIT_DASH is None:
        try:
            import data_sources as _DS
            _DEV_WAIT_DASH = dict(_DS.dashcam_append_ttft_s())
        except Exception:
            _DEV_WAIT_DASH = {}
    return _DEV_WAIT_DASH
# D99 (1): ONE DECISION PERIOD FOR EVERY ARM, 100 ms, with the events of each period batched.
# It replaces the 50 ms event grid AND the per-arm H tick: H is now the rollout horizon only
# (spec 6.1, 9 as amended). Every arm therefore decides at the same rate, which is what makes
# the decision rate stop being an arm property, and it is recorded in the run header.
DECISION_PERIOD_S = 0.1
# D150 PATCH 2's belief correction: "observe" counts and does not mutate, "apply" mutates.
# Default observe, so no committed or in-flight baseline cell changes behaviour under it.
BELIEF_CORRECTION = os.environ.get("LIVE2_BELIEF_CORRECTION", "observe")
DEFAULT_TICK_S = DECISION_PERIOD_S           # kept as the old name; same value for every arm
HEADER_TEXT = "D2 history"                   # the committed D2 header text, 31 tokens (StudyRH4)


@dataclass
class Logs:
    out_dir: Path
    decision: Any = None
    request: Any = None
    residency: Any = None

    def open(self) -> "Logs":
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.decision = SC.JsonlWriter(self.out_dir / "decision.jsonl")
        self.request = SC.JsonlWriter(self.out_dir / "request.jsonl")
        self.residency = SC.JsonlWriter(self.out_dir / "residency.jsonl")
        return self

    def close(self) -> None:
        for w in (self.decision, self.request, self.residency):
            if w is not None:
                w.close()



def _arm_stats(arm: Any) -> Optional[Dict[str, Any]]:
    """Every Counter in the arm's delegation chain, prefixed where a name would collide.

    WHY THIS IS NOT `arm.stats`. A v6 ladder arm wraps a V5Rules2Arm which holds the BASE
    HybridArm as `_base`, and the base is where the recall decision is actually made. So
    `arm.stats` reported the wrapper's own counters and NOTHING from the policy that decided:
    every committed v5-rules-2 cell carries `warm_ahead_emitted` and `guard_active_epochs` and
    carries NO `c2_throttle_periods`, `c2_throttled_dash` or `c5_dash_held`, although the base
    counts all three on every period. That gap forced the rung-1 submission-gap diagnosis
    (D174 (2)) through a reconstruction and a declared proxy, because the arm's own answer was
    not in the file. An unread counter is the write-only-field failure wearing the other mask.

    Collisions are prefixed by the holder's class rather than summed: `decisions` means a
    different thing on a wrapper than on the base, and adding them would invent a number.
    """
    if arm is None:
        return None
    seen, chain, i = {id(arm)}, [arm], 0
    while i < len(chain):
        o = chain[i]
        i += 1
        for attr in ("_rules", "_base", "_scorer"):
            nxt = getattr(o, attr, None)
            if nxt is not None and id(nxt) not in seen:
                seen.add(id(nxt))
                chain.append(nxt)
    out: Dict[str, Any] = {}
    for o in chain:
        st = getattr(o, "stats", None)
        if not st:
            continue
        for k, v in dict(st).items():
            if k in out and out[k] != v:
                out["%s.%s" % (type(o).__name__, k)] = v
            else:
                out[k] = v
    if out:
        out.update(_planner_time_limit_summary(out) or {})
    return out or None


def _planner_time_limit_summary(st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The planner TIME-LIMIT abandonment rate, by decision kind, in every cell that plans.

    User ruling 2026-11-22. Derived here rather than left to the reader because the quantity that
    matters is a FRACTION and the counters are counts: a cell with 44,300 state decisions and 300
    abandonments is fine, and one with 300 decisions and 300 abandonments is a cell whose planner
    never ran. Without the denominator beside it the count reads the same either way.

    Flagged above 1 percent per kind OR overall, which is the ruling's bar.
    """
    tot = int(st.get("cf_planner_decisions", 0) or 0)
    if not tot:
        return None
    kinds = sorted(k[len("cf_planner_decisions_"):] for k in st
                   if k.startswith("cf_planner_decisions_"))
    by_kind: Dict[str, Any] = {}
    flagged = []
    for kind in kinds:
        n = int(st.get("cf_planner_decisions_" + kind, 0) or 0)
        a = int(st.get("cf_timeout_abandons_" + kind, 0) or 0)
        f = (a / n) if n else None
        by_kind[kind] = {"decisions": n, "abandoned_to_base": a,
                         "fraction": (round(f, 6) if f is not None else None)}
        if f is not None and f > 0.01:
            flagged.append(kind)
    a_tot = int(st.get("cf_timeout_abandons", 0) or 0)
    f_tot = a_tot / tot
    if f_tot > 0.01 and "ALL" not in flagged:
        flagged.append("ALL")
    return {"planner_time_limit": {
        "budget_ms": st.get("cf_budget_ms"),
        "decisions": tot, "abandoned_to_base": a_tot, "fraction": round(f_tot, 6),
        "by_kind": by_kind,
        "over_1_percent": flagged,
        "flag": bool(flagged),
        "_note": ("cf_instrument.over_budget is a WALL-CLOCK limit (D99 (3), D151 (5)), so this "
                  "rate is a property of the host CPU as well as of the policy. The H100 host is "
                  "about 2.2x slower than flash on the committed policy benchmark (D115 (1)), so "
                  "a rate measured on flash is a LOWER BOUND for a live cell and must not be "
                  "quoted for one. Proofs run with the limit OFF so a decision digest is a "
                  "property of the arm; live cells run with it ON because it is a real cost")}}


class Live2Coordinator:
    def __init__(self, arm, backend: Optional[Live2Backend], events: List[Dict[str, Any]],
                 *, gpu_kv_tokens: int, host_tier_gib: float, host_tier_tokens: int,
                 upload_mode: str = "A", window_s: float = 180.0, drain_s: float = 20.0,
                 tick_s: Optional[float] = None, decision_period_s: Optional[float] = None,
                 seed: int = 0, speed: float = 1.0,
                 logs: Optional[Logs] = None, run_tag: str = "live2",
                 frames_root: Optional[Path] = None, dry_run: bool = False,
                 targets: Optional[Dict[str, Any]] = None, on_pull=None,
                 gpu_budget_s: Optional[float] = None,
                 max_wall_s: Optional[float] = None,
                 frame_cache: Any = None, defer_images: bool = False) -> None:
        self.arm = arm
        # D164: per-request host-offload controls are POLICY actions, so only an arm that
        # declares the capability emits them; every baseline keeps vLLM's defaults and so
        # keeps byte-identical bodies. Read once here, never re-read, so it cannot drift.
        self._offload_controls = OP.arm_enables(arm)
        # Component 2: KEEP_GPU_WARM additionally issues a REAL touch request for an
        # arm that declares it. Without this the action only steers the coordinator's
        # own eviction order and cannot move vLLM's LRU recency (D150, D44).
        self._touch_requests = TP.arm_enables(arm)
        # D160: price warm and reload by predicted cache state, not by slice size.
        self._state_priced_costs = TP.arm_enables_state_pricing(arm)
        # ONE PRICE SOURCE (user ruling, 2026-11-21). When the arm declares it, EVERY request this
        # coordinator charges is priced by the D162 predicted first-token time, the same model and
        # the same arithmetic the planner uses for a candidate's harm. Arm-scoped, so no baseline's
        # charge moves. See live2/d162_price.py for why the old charge was wrong-shaped rather
        # than merely conservative.
        self._d162_pricing = DP.arm_enables(arm)
        # D174 (1): the mode comes from the ARM, never from the module global. An arm that
        # declares pricing without a mode gets the ruled one (uncached-only).
        self._charge_mode = DP.arm_charge_mode(arm)
        if self._d162_pricing:
            DP.assert_no_drift()
        # ---- D179 (4) RELEASE RE-CHECK (session B), state. BEGIN contiguous block -------------
        # b7 tests deadline feasibility AT ARRIVAL only. With this on, every DEADLINE request
        # (alert, recall, assistance) is re-tested AT WIRE TIME and is NOT SENT if it can no
        # longer make its deadline; the device answer stands. Background work (piece, whole,
        # touch) carries no deadline and is out of scope. See live2/release_recheck.py for which
        # feasibility quantity is used and why it is not b7's own `est`.
        #
        # ARM-SCOPED INSTANCE attribute, default False. `RR.arm_enables` RAISES on a class-level
        # ON rather than reading it, because a class attribute turns the rung on for every arm in
        # the run and a module global defaulting ON once cost a whole live cell.
        self._release_recheck = RR.arm_enables(arm)
        # the re-check reads the D162 predictor whether or not the arm's CHARGE is D162-priced,
        # so the coefficient drift check has to run on this switch too, not only on pricing.
        if self._release_recheck:
            DP.assert_no_drift()
            RR.assert_no_interface_drift()
            # THE QUEUE INPUT IS ONLY IN THE RIGHT REGISTER ON A D162-PRICED ARM, and this guard
            # exists because the first dry cell found out the hard way: the re-check fired on
            # 12,166 of 12,168 alert requests (99.98 percent) on `covex-v6-base`, which tripped
            # the D179 STOP condition. `_uncached_in_flight` is INCREMENTED unconditionally at
            # four release sites (lines 918, 1052, 1117 and 1206) and DECREMENTED only inside
            # `if self._d162_pricing` in `_collect` (line 1508), and every other read of it is
            # likewise inside that gate. So on an arm that does not declare D162 pricing the
            # field is not a queue depth at all: it is the cumulative sum of every uncached token
            # the run has ever released, which grows without bound and makes the predicted first
            # token exceed any deadline after the first few seconds. A quantity in the wrong
            # register is not a wrong computation and survives every arithmetic check, so it is
            # refused here rather than read. Making the decrement unconditional would be the
            # other remedy; it is NOT applied here, because it changes a committed quantity's
            # semantics on arms this session does not own.
            if not self._d162_pricing:
                raise RuntimeError(
                    "live2_release_recheck needs live2_d162_pricing on the same arm: "
                    "`_uncached_in_flight` is decremented only under D162 pricing "
                    "(coordinator.py:1508), so on %r it is a cumulative run total and not the "
                    "queue ahead of this request" % (getattr(arm, "name", arm),))
        # one row per skipped request, for the report's traced unit; the COUNTERS are the frozen
        # names in `self.counts` and these rows never substitute for them.
        self.release_infeasible_events: List[Dict[str, Any]] = []
        # ---- END D179 (4) block ---------------------------------------------------------------
        # the third term of the price: uncached tokens the engine is already working on. Tracked
        # here because only the coordinator knows what is in flight, and it is what makes the
        # planner's harm and this charge the same arithmetic rather than two similar ones.
        # ---- D179 (1) to (3) SHARE ADMISSION (session A), state. BEGIN contiguous block -------
        # W is per type and is submit to FIRST TOKEN, which is OBSERVABLE: asyncbackend fires
        # on_first at the first content token and `answer_on_first` already consumes it. It is
        # deliberately NOT `_uncached_in_flight`, which drains at COMPLETION and so carries the
        # decode tail: the right queue input for the D174 charge and the wrong resource here.
        #
        # A DENIAL HOLDS, IT DOES NOT DECLINE. Capacity may free before the deadline, so the
        # instant stays "arrived" and is re-offered next period. That composes with D179 (4):
        # shares hold a request while it still has a chance, and the release re-check declines it
        # once it does not. It also means a hold is counted TWICE, deliberately and under two
        # names, because the same instant is re-offered every 100 ms period: `_periods` counts
        # item-periods and `_instants` counts distinct opportunities held at least once. Reporting
        # only the first is the confusion `share_capacity.py` records about c5_dash_held, where
        # 7,149 unsent opportunities could not be reconciled against counters in the tens of
        # thousands.
        self._share_admission = SA.arm_enables(arm)
        self._w = SA.WTracker()
        self._share_held_instants: Dict[str, set] = {t: set() for t in SA.TYPES}
        self._share_events: List[Dict[str, Any]] = []
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        self._uncached_in_flight = 0
        self._uncached_pending: Dict[str, int] = {}
        self._uncached_last_charged = 0
        # request id -> {t0, t1, uncached} for every NON-MONITOR request released, t1 None while
        # it is still in flight. See C5ATTR_UNCACHED_MIN.
        self._released_prefills: Dict[str, Dict[str, Any]] = {}
        # D150 PATCH 2 belief correction, ARM-SCOPED like every other v5 switch (D172 rung 2).
        # It was a process-wide env switch, so turning it on for one arm turned it on for every
        # arm in the same run and made the cells incomparable, which is the thing the env
        # switch's own comment says must not happen. The env value is kept as an override so no
        # committed invocation changes behaviour.
        self._belief_apply = bool(BELIEF_CORRECTION == "apply"
                                  or getattr(arm, "live2_belief_apply", False))
        self.be = backend
        self.events = sorted(events, key=lambda e: (_sched(e), e.get("kind", "")))
        self.upload_mode = upload_mode
        self.window_s = float(window_s)
        self.drain_s = float(drain_s)
        self.seed = int(seed)
        self.speed = float(speed)
        self.logs = logs
        self.run_tag = run_tag
        self.frames_root = Path(frames_root) if frames_root else None
        # StudyLIVE2-harness: with a frame cache the loop never reads a frame or base64-encodes
        # one; `defer_images` leaves the image payloads to the backend's own thread. Both are
        # OFF by default, so an unconfigured run behaves exactly as the pilot's did.
        self.frame_cache = frame_cache
        self.defer_images = bool(defer_images)
        self.dry_run = bool(dry_run)
        # mode B (D69): the fleet answers a pull. Without a live fleet process the caller may
        # supply a responder that returns the monitor_frame the pull would produce, with the pull
        # message and the upload both charged to the delivered delay.
        self.on_pull = on_pull
        self.injected: List[Dict[str, Any]] = []
        self.h_s = getattr(arm, "h_s", None) if getattr(arm, "uses_h", False) else None
        # D99 (1): the decision period is the SAME for every arm and is NOT the arm's H. The
        # period is the grid: each period's events are ingested and then ONE decision is taken
        # over the batch. `tick_s` survives as the old name for the same number so existing
        # callers keep working; it can no longer differ from the period.
        period = decision_period_s if decision_period_s is not None else tick_s
        self.decision_period_s = float(period if period is not None else DECISION_PERIOD_S)
        self.tick_s = self.decision_period_s
        self.event_grid_s = self.decision_period_s
        self.st = CS.CoordState(gpu_kv_tokens=int(gpu_kv_tokens),
                                host_tier_gib=float(host_tier_gib),
                                host_tier_tokens=int(host_tier_tokens),
                                upload_mode=upload_mode,
                                targets=dict(targets or CS.TARGETS))
        # D102: the GPU budget is an explicit INPUT, equal by default to one GPU's time over
        # the run (window length x 1 GPU-second per second), identical for every arm and
        # recorded in the header. It is the PHYSICAL CAPACITY, so it never binds artificially
        # (D58: round 1 has no fixed budget; "budget %" is only a test variable). B8, B9 and
        # edf-service-time admit by a utility-per-GPU-second ratio against a remaining budget
        # and need a finite one, which is why it exists at all. It replaces the harness constant
        # (StudyLIVE2-coord open issue 8).
        self.gpu_budget_s = float(gpu_budget_s if gpu_budget_s is not None
                                  else self.window_s * 1.0)
        self.st.budget = Budget(gpu_seconds=self.gpu_budget_s)
        self.n_dec = 0
        self.n_req = 0
        self.futures: List[Tuple[Any, Live2Submission]] = []
        self.answers: List[Dict[str, Any]] = []
        self.pulls: List[Dict[str, Any]] = []
        self.cloud_answers: List[Dict[str, Any]] = []
        # StudyLIVE2-harness addendum: answers the I/O layer forwarded at stream end, by request
        self.forwarded: Dict[str, Dict[str, Any]] = {}
        self.n_forward_mismatch = 0
        # what a slow decision costs: epoch start -> the request going on the wire (addendum (a))
        self.submit_delays_ms: List[float] = []
        self._epoch_wall0: Optional[float] = None
        self.n_recall_first_token = 0
        self.n_recall_letter_differs = 0
        self.recall_letter_diffs: List[Dict[str, Any]] = []
        self.n_monitor_score_differs = 0
        self.decision_latencies_ms: List[float] = []
        # D115: per decision (t, wall_ms, cpu_ms, candidates)
        self.decision_times: List[Tuple[float, float, float, int]] = []
        self._priority_latest: Dict[str, int] = {}          # vllm-priority, by item key
        self.errors: List[str] = []
        self.counts: Dict[str, int] = defaultdict(int)
        self.builds: Dict[str, Dict[str, Any]] = {}
        self.reads_device = bool(getattr(arm, "reads_device_answer", False))
        # D153: the dashcam format is read OFF THE TRACE, not configured here. A monitor_frame
        # that carries the episode fields puts this run in "epg"; a trace without them keeps the
        # committed one-frame contract. `_mon_sent` is per device the frames whose BYTES this
        # device has already put on the wire, so an already-sent frame goes as a uuid-only
        # reference (StudyRH7 wire form) and only the new frame carries bytes, which is the
        # mechanism behind proof (a).
        self.dashcam_format = "oneframe"
        # D158 (2): `_mon_sent` is submission time and drives the CHARGE; `_mon_confirmed` is
        # 200 time and drives REFERENCE ELIGIBILITY. The session-side pair is documented on
        # `cstate.SessionRec`, and the reason the dashcam side needs the same split is that an
        # EP-G episode re-sends the same frame list every 2 s, so its references outrun the
        # engine exactly as a session's do.
        self._mon_sent: Dict[str, set] = defaultdict(set)
        self._mon_confirmed: Dict[str, set] = defaultdict(set)
        self.epg_requests: List[Dict[str, Any]] = []
        # A cell whose decision loop cannot keep up with its own tick would otherwise run for
        # many times its window and report nothing. The guard stops it and the result SAYS SO,
        # with the virtual time it reached, which is the number that matters.
        self.max_wall_s = float(max_wall_s) if max_wall_s else None
        self.wall_guard_hit = False
        self.t_reached = 0.0
        self.epoch_overruns = 0
        self.max_epoch_lag_s = 0.0

    # ---------------------------------------------------------------- the loop
    def run(self) -> Dict[str, Any]:
        fair = check_fairness(self.arm)
        if fair.get("rule5_reads_future"):
            raise RuntimeError("fairness rule 5: an arm that reads the future is refused in a "
                               "live run (%s)" % self.arm.name)
        self.arm.reset(self.seed)
        ei = 0
        wall0 = time.time()
        cpu0 = _cpu_s()
        t = 0.0
        end = self.window_s + self.drain_s
        while t < end:
            if not self.dry_run:
                target = wall0 + t / self.speed
                lag = time.time() - target
                if lag > 0.5 * self.tick_s / self.speed:
                    self.epoch_overruns += 1
                    self.max_epoch_lag_s = max(self.max_epoch_lag_s, lag * self.speed)
                elif lag < 0:
                    time.sleep(-lag)
            self._collect(t)
            epoch = "tick"
            while ei < len(self.events) and _sched(self.events[ei]) <= t + 1e-9:
                epoch = self._ingest(self.events[ei], t) or epoch
                ei += 1
            while self.injected and _sched(self.injected[0]) <= t + 1e-9:
                epoch = self._ingest(self.injected.pop(0), t) or epoch
            self.st.now = t
            if not self.dry_run and self.be is not None:
                self.st.metrics = self.be.metrics()
            # D99 (1): exactly ONE decision per period, over that period's batched events.
            # The old rule (one decision per arm tick PLUS one on every event) made the
            # policy arm's decision rate a function of the event rate: at 64 devices an event
            # landed in nearly every 50 ms step, so an H = 1 s arm was in fact invoked about 20
            # times a virtual second (StudyLIVE2-coord open issue 10a).
            if t <= self.window_s:
                self._epoch(t, epoch)
            self._expire(t)
            self.t_reached = t
            t = round(t + self.event_grid_s, 9)
            if self.max_wall_s is not None and time.time() - wall0 > self.max_wall_s:
                self.wall_guard_hit = True
                break
        if self.dry_run:
            for _ in range(10_000):
                if not self.futures:
                    break
                self.st.now = round(self.st.now + self.tick_s, 9)
                self._collect(self.st.now)
        else:
            deadline = time.time() + 60.0
            while self.futures and time.time() < deadline:
                self._collect(self.window_s + self.drain_s)
                time.sleep(0.01)
        return self._result(cpu0, time.time() - wall0)

    def _epoch(self, t: float, epoch: str) -> None:
        # D100: the hook is refreshed once per decision period, immediately before the
        # observation, so the instant deadline and the built-prefix size the arm reads describe
        # the same state the observation does. It is O(devices + sessions) per period.
        self._roster(t)
        obs = self.st.observation(t, epoch if epoch in _EPOCHS else "tick",
                                  reads_device_answer=self.reads_device)
        k0 = self._candidates_counter()
        t0 = time.perf_counter()
        c0 = time.thread_time()
        self._epoch_wall0 = t0
        try:
            act = self.arm(obs)                  # scrub + validate_action + apply_defaults
            # D115: the DECIDING THREAD's CPU time over the same call (time.thread_time, so the
            # I/O loop's thread in the same process is not counted), read INSIDE the wall interval
            # so cpu <= wall by construction; and the candidates priced: the delta of the arm's own
            # scoring counter where it keeps one (policy-core's rollout scorings), else the number
            # of pending items the arm ordered (EDF family, which prices nothing).
            cpu_ms = (time.thread_time() - c0) * 1000.0
            dt_ms = (time.perf_counter() - t0) * 1000.0
            k1 = self._candidates_counter()
            cand = (k1 - k0) if (k0 is not None and k1 is not None) else \
                (len(getattr(obs, "streams", ()) or ()) + len(getattr(obs, "recall", ()) or ()))
            self.decision_latencies_ms.append(dt_ms)
            self.decision_times.append((round(t, 4), round(dt_ms, 4), round(cpu_ms, 4), int(cand)))
            self._enact(act, t, dt_ms)
        finally:
            # a submission made OUTSIDE an epoch (a chained recall released by a completion in
            # `_settle`) is stamped at the instant it is made, not charged this epoch's delay
            self._epoch_wall0 = None

    def _priority_for(self, kind, device_id, session_id, opportunity_id) -> Dict[str, Any]:
        """vllm-priority: the priority the arm set for this item, if any (monitor by stream, recall
        by question, build by session); {} for every other arm, so nothing else changes."""
        if not self._priority_latest:
            return {}
        key = ("mon:" + str(device_id) if kind == "monitor" else
               "rc:" + str(opportunity_id) if kind == "recall" else "session:" + str(session_id))
        v = self._priority_latest.get(key)
        return {} if v is None else {"priority_ms": int(v)}

    def _candidates_counter(self) -> Optional[int]:
        """D115: the arm's own count of candidates priced so far, read only (never written)."""
        co = getattr(self.arm, "co", None)
        v = getattr(co, "scoring_calls", None) if co is not None else None
        return int(v) if isinstance(v, (int, float)) else None

    def decision_time_summary(self) -> Dict[str, Any]:
        """D115: decision wall and CPU time, their ratio (contention indicator) and candidates."""
        rows = self.decision_times
        wall = [r[1] for r in rows]
        cpu = [r[2] for r in rows]
        ratio = [r[1] / r[2] for r in rows if r[2] > 0]
        cand = [r[3] for r in rows]
        return dict(n=len(rows), cpu_clock="time.thread_time() of the deciding thread",
                    wall_ms=_pct(wall), cpu_ms=_pct(cpu), wall_over_cpu=_pct(ratio),
                    candidates=_pct(cand),
                    candidates_source=("arm scoring counter delta"
                                       if self._candidates_counter() is not None
                                       else "pending items ordered"))

    def write_decision_times(self, path: Path) -> None:
        import gzip
        import json
        with gzip.open(path, "wt") as f:
            for t, w, c, k in self.decision_times:
                f.write(json.dumps(dict(t=t, wall_ms=w, cpu_ms=c, candidates=k)) + "\n")

    # ---------------------------------------------------------------- fleet events
    def _ingest(self, ev: Dict[str, Any], t: float) -> Optional[str]:
        k = ev["kind"]
        if k == "device_register":
            self.st.register(ev, CK.cache_salt(self.run_tag, ev["device_id"]))
            self._roster()
            return "stream_arrival"
        if k == "session_start":
            self.st.session_start(ev)
            return None
        if k == "session_end":
            self.st.session_end(ev)
            self._log_residency(t, ev["session_id"])
            return None
        if k == "history_preload":
            self.st.history_preload(ev)
            return None
        if k == "history_append":
            self.st.history_append(ev)
            return None
        if k == "monitor_offer":
            o = self.st.monitor_offer(ev)
            self._device_answer(o)
            return "stream_arrival"
        if k == "monitor_frame":
            o = self.st.monitor_frame(ev)
            self._take_episode(o, ev)
            self._device_answer(o)
            return "stream_arrival"
        if k == "recall_question":
            self.st.recall_question(ev)
            self._roster()
            return "recall_arrival"
        raise KeyError(f"the coordinator has no handler for event kind {k!r}")

    def _take_episode(self, o, ev: Dict[str, Any]) -> None:
        """D153: copy the trace's EPISODE context onto the opportunity, unchanged.

        The coordinator DERIVES NOTHING here. The episode frame list is the trace generator's,
        is a function of the capture index alone, and is identical for every arm, which is what
        makes proof (b) hold by construction rather than by scheduling discipline. A run whose
        trace carries the episode fields and then stops carrying them is a plumbing fault, not a
        format change, so it RAISES: mode B's `traces.pull_responder` rebuilds the monitor_frame
        itself and would otherwise silently drop the episode back to one frame.
        """
        refs = ev.get("frame_refs")
        if refs:
            self.dashcam_format = "epg"
            o.episode_id = ev.get("episode_id")
            o.episode_index = ev.get("episode_index")
            o.episode_frame_refs = list(refs)
            if ev.get("episode_frames") is not None \
                    and int(ev["episode_frames"]) != len(o.episode_frame_refs):
                raise RuntimeError(
                    f"monitor_frame {o.opp_id} declares {ev['episode_frames']} episode frames "
                    f"and carries {len(o.episode_frame_refs)}")
            if o.frame_ref is not None and o.episode_frame_refs[-1] != o.frame_ref:
                raise RuntimeError(
                    f"monitor_frame {o.opp_id}: the episode's last frame "
                    f"{o.episode_frame_refs[-1]!r} is not this instant's frame {o.frame_ref!r}; "
                    f"D148's episode is append-only and ends at the current instant")
        elif self.dashcam_format == "epg":
            raise RuntimeError(
                f"monitor_frame {o.opp_id} carries no episode frame list in a run whose earlier "
                f"frames did (D153 EP-G). The episode context must come from the TRACE, so a "
                f"producer that rebuilds the event (mode B `traces.pull_responder`) has to "
                f"forward the four episode fields; it is not optional once the trace has them")

    def _device_answer(self, o) -> None:
        """The device answers every opportunity locally and immediately (spec v4 section 1.2),
        so the application-visible stream carries the device's own answer from the capture
        instant; a cloud answer that arrives in time is appended on top of it and upgrades it.
        The SCORES here are placeholders: task value is scored offline from the recordings
        (D85, D87), never in this process."""
        d = self.st.devices.get(o.device_id)
        if d is None or o.kind != "monitor":
            return
        if any(abs(t - o.t_event) < 1e-9 for t, _v in d.delivered):
            return
        d.delivered.append((o.t_event, 0.0))

    def _roster(self, now: Optional[float] = None) -> None:
        """The arm-side hook (D100): CAUSAL FACTS KNOWN AT ARRIVAL, never the future, and never
        through the scrubbed `Observation`.

        Two D100 facts are added to the device roster:

        * `sh_instant`, per device: the opportunity_id, capture time and ABSOLUTE DEADLINE
          c_i + L_SH of the monitoring instant that device's stream currently stands for. It is
          chosen by exactly the rule `CoordState.observation` uses (the first visible, undecided,
          un-deferred, not-yet-late instant in arrival order), so an arm ordering by this
          deadline is ordering the instant the coordinator will actually act on. It replaces the
          "next call due after the last answer the application received" workaround, under which
          every stream tied on `now + L` and pi_0's tie-break by item_id starved every device but
          the first (StudyLIVE2-coord open issue 9).
        * `built_tokens_by_session`: how much of each history the cloud has ALREADY BUILT
          (partial readiness), so a later reconstruction piece is costed as a piece on a warm
          prefix instead of a cold rebuild (open issue 3b).

        Registry arms (FCFS, B8, B9) declare no `live2_roster` and so receive nothing: they are
        unchanged by D100.
        """
        if not hasattr(self.arm, "live2_roster"):
            return
        now = self.st.now if now is None else float(now)
        mon, _rec = self.st.visible(now)
        first: Dict[str, Any] = {}
        for o in mon:
            first.setdefault(o.device_id, o)
        self.arm.live2_roster(dict(
            devices={d.device_id: dict(type=d.type, uplink_mbps=d.uplink_mbps,
                                       rtt_ms=d.rtt_ms) for d in self.st.devices.values()},
            session_device={s.session_id: s.device_id for s in self.st.sessions.values()},
            frame_bytes={d.device_id: d.frame_bytes for d in self.st.devices.values()
                         if d.frame_bytes},
            sh_instant={did: dict(opportunity_id=o.opp_id, t_capture=round(o.t_event, 6),
                                  deadline_abs=round(o.deadline_abs(), 6))
                        for did, o in first.items()},
            built_tokens_by_session={sid: int(s.built_tokens)
                                     for sid, s in self.st.sessions.items()
                                     if s.built_tokens > 0},
            # D160 (1): `est_tokens` beside `built_tokens`, so an arm can see a session's UNWARMED
            # TAIL (est minus built) and warm it in CHUNKS instead of once per uploaded frame.
            # Without this the tail is not observable at all: `built_tokens_by_session` alone gives
            # no history size, which `arms_v5rules._candidates` records as the reason v5-rules asks
            # for every robot session every epoch, and which is what made warming cost scale with
            # request count (about 84,000 prefills per run). CAUSAL: `est_tokens` is the cumulative
            # history the cloud has ALREADY RECEIVED (`cstate.py:311` on preload, `:330` on each
            # append), never a future upload. ADDITIVE: the base reads only `sh_instant`,
            # `built_tokens_by_session`, `session_device` and `frame_bytes` and never iterates or
            # hashes the roster dict, so no existing arm's behaviour can change.
            est_tokens_by_session={sid: int(s.est_tokens)
                                   for sid, s in self.st.sessions.items()
                                   if s.est_tokens > 0},
            # D172 rung 2: the coordinator's residency BELIEF, which the telemetry corrector
            # writes when belief-apply is on. Without it an arm can price a warm against a cold
            # only by guessing which state the session is in, which is the guess D160 says to
            # replace with the predicted state. ADDITIVE, like est_tokens_by_session: no committed
            # arm reads it.
            belief_by_session={sid: dict(s.belief or {})
                               for sid, s in self.st.sessions.items()},
        ))

    # ---------------------------------------------------------------- enactment
    def _enact(self, act, t: float, dt_ms: float) -> None:
        # vllm-priority: the arm's per-item priorities (Action.notes["priority_ms"]); kept by key so a
        # submission released outside an epoch (a chained recall) still carries its item's priority
        pri = ((getattr(act, "notes", None) or {}).get("priority_ms")) or {}
        if pri:
            self._priority_latest.update(pri)
        preds = getattr(self.arm, "last_predictions", {}) or {}
        mix = self.st.traffic_mix()
        for sa in act.streams:
            d = self.st.devices.get(sa.stream_id)
            if d is None:
                continue
            d.on_cloud = sa.mode == "cloud"
            if sa.mode == "cloud":
                d.cadence_s = float(sa.cadence_s or d.cadence_s)
                d.frame_count = int(sa.frame_count or d.frame_count)
                self._serve_monitor(sa.stream_id, t, dt_ms, preds, mix)
        warmed: Dict[str, str] = {}
        for xa in act.sessions:
            s = self.st.sessions.get(xa.session_id)
            if s is None:
                continue
            self.counts["session_" + xa.action] += 1
            if xa.action in ("KEEP_GPU_WARM", "OFFLOAD_TO_HOST", "EVICT"):
                # A PLACEMENT choice is a decision and belongs in the decision log, or a move
                # proof that diffs decision rows reads a firing mechanism as inert.
                self._log_decision(t, "state_action", [], latency_ms=dt_ms, preds=preds, mix=mix,
                                   session_id=xa.session_id,
                                   desired_tier={"KEEP_GPU_WARM": "gpu",
                                                 "OFFLOAD_TO_HOST": "host",
                                                 "EVICT": "cold"}[xa.action])
            if xa.action == "EVICT":
                # D56: demote to cold. The frames stay on disk; nothing is deleted.
                s.belief = {"gpu": 0.0, "host": 0.0, "cold": 1.0}
                s.built_tokens = 0
            elif xa.action == "OFFLOAD_TO_HOST":
                s.desired_tier = "host"
            elif xa.action == "KEEP_GPU_WARM":
                s.desired_tier = "gpu"
                if self._touch_requests:
                    self._submit_touch(s, t, dt_ms, preds, mix)
            elif xa.action == "MATERIALIZE":
                rid = self._advance_build(s, xa.target_tokens, xa.slice_tokens, t, dt_ms,
                                          preds, mix)
                if rid:
                    warmed[s.session_id] = rid
        for ra in act.recall:
            o = self.st.opps.get(ra.query_id)
            if o is None or o.state not in ("arrived", "offered"):
                continue
            # D133/D134 Part A. `RecallAction.representation` was written by arms, declared in
            # `decides`, and READ NOWHERE, so a RECENT-choosing arm paid full-history cost and
            # received full-history evidence. It is carried to the submit path here.
            o.requested_representation = ra.representation
            # PLAIN ATTRIBUTE ACCESS, deliberately. `getattr(..., False)` is the idiom that
            # produced four confirmed defects in this codebase: budget_total_gpu_s returning 0.0
            # and pinning cascade-routing's lambda, RecallQuery.category carrying "recall",
            # desired_tier written and never read, and a sufficiency proxy that could never fire.
            # An action object lacking this field would be silently recorded as CHOSEN when it was
            # INJECTED, and the credit axis is the only thing distinguishing an arm that decided
            # from one that declined to. A missing field should raise, not default.
            o.representation_defaulted = bool(ra.representation_defaulted)
            self.counts["recall_" + ra.decision] += 1
            if ra.decision == "DEFER":
                o.defer_until = t + max(float(ra.defer_s or 0.0), 0.0)
                o.n_defers += 1
                self._log_decision(t, "defer", [o.opp_id], defer_s=float(ra.defer_s or 0.0),
                                   latency_ms=dt_ms, preds=preds, mix=mix)
                continue
            if ra.decision in ("DEVICE", "REJECT"):
                o.state = "declined"
                o.served_at = (o.t_event + self._device_wait_s(o) if self.reads_device
                               else t)
                self.answers.append(dict(opportunity_id=o.opp_id, kind="recall",
                                         device_id=o.device_id, decision=ra.decision,
                                         delivered_s=o.served_at,
                                         deadline_s=o.deadline_abs(), served_by="device",
                                         on_time=None))
                self._log_decision(t, "decline", [o.opp_id], latency_ms=dt_ms, preds=preds,
                                   mix=mix)
                continue
            s = self.st.sessions.get(o.session_id)
            if s is None:
                continue
            if s.session_id in warmed:
                self.builds[warmed[s.session_id]]["answers"] = o.opp_id
                o.state = "in_flight"
                continue
            if s.built_tokens < s.est_tokens and s.believed_tier() != "gpu":
                # no build was asked for: the answer carries the whole history in one request,
                # which is what an arm that never materializes expresses (monolithic).
                self._submit_recall(o, s, t, dt_ms, preds, mix, whole=True)
            else:
                self._submit_recall(o, s, t, dt_ms, preds, mix, whole=False)

    def _serve_monitor(self, device_id: str, t: float, dt_ms: float, preds, mix) -> None:
        cands = [self.st.opps[i] for i in self.st.order
                 if self.st.opps[i].kind == "monitor"
                 and self.st.opps[i].device_id == device_id
                 and self.st.opps[i].state in ("arrived", "offered")
                 and self.st.opps[i].defer_until <= t + 1e-9
                 and self.st.opps[i].deadline_abs() >= t - 1e-9]
        if not cands:
            return
        o = min(cands, key=lambda x: x.deadline_abs())
        if self.reads_device and t + 1e-9 < o.t_event + self._device_wait_s(o):
            return
        if o.state == "offered":
            if self.upload_mode != "B":
                return
            if o.pulled_at is None:
                o.pulled_at = t
                self.pulls.append(SC.make("pull_request", device_id=device_id,
                                          instant_id=o.instant_id or o.opp_id, t_sent=t))
                self._log_decision(t, "pull", [o.opp_id], latency_ms=dt_ms, preds=preds, mix=mix)
                if self.on_pull is not None:
                    ev = self.on_pull(o, t)
                    if ev is not None:
                        import bisect
                        keys = [_sched(x) for x in self.injected]
                        self.injected.insert(bisect.bisect_right(keys, _sched(ev)), ev)
            return
        # D153: under EP-G the request is the whole append-only episode, so its PROMPT is the
        # episode's and not one frame's, while its PREFILL is only the frames the engine has not
        # already seen. The two are different numbers and both are needed:
        #
        #   est_tokens  the episode's whole prompt, from StudySH-EP's measured token law. It is
        #               what the engine will report as prompt_tokens, so it is what the request
        #               log, the token accounting and the fake server's hint must carry.
        #   cost        the GPU-seconds charged to the budget, which is the NEW tokens only.
        #               Charging the whole prompt every turn would price an append-only episode
        #               as a cold rebuild and deny the mechanism D148 exists to exercise: it is
        #               also not what live2 does anywhere else, since `_advance_build` charges a
        #               history append `recall_gpu_s(piece)` for the PIECE and not for the
        #               cumulative prompt. The difference is not academic - on the proof cell the
        #               whole-prompt charge exhausts the run's GPU budget after 429 of 1,874
        #               decision instants, so the arms would be compared on budget rationing
        #               rather than on scheduling. Conservative by the header's own tokens, which
        #               ARE in the shared prefix and are charged again here, because StudySH-EP
        #               measured the 42 text tokens together and splitting them would be an
        #               invented number.
        #
        # `episodic_gpu_s` is not used for either: it reads a committed PROMPT_TOK table keyed by
        # the three measured frame counts {1, 3, 9} and has no entry for an episode of 10 to 21.
        refs = list(getattr(o, "episode_frame_refs", None) or [])
        epg = self.dashcam_format == "epg" and bool(refs)
        if epg:
            # D158 (2), THE DASHCAM TWIN OF THE SESSION SPLIT, and it is needed here for the
            # same reason and with the same shape. The saturated held-out cell
            # `warm-all-lru_n16_s4_1200s_h27_3t_L3_epg` had 1,113 dashcam 400s against 397 robot
            # ones, each device's first failure arriving while its previous request was still in
            # flight at a TTFT of 97 to 122 s, so the dashcam path is the LARGER half of this bug.
            #
            # `sent` (submission time) decides the CHARGE, so the budget spend and therefore
            # every decision is unchanged. `confirmed` (200 time) decides the WIRE FORM, because
            # a frame whose carrying request has not returned cannot be referenced by uuid alone.
            sent = self._mon_sent[device_id]
            confirmed = self._mon_confirmed[device_id]
            # `_path` is resolved once per frame because the charge depends on it: a frame the
            # store lacks resolves to None, carries no bytes and so prefills nothing, and the
            # pre-fix charge counted exactly the frames that were both new and resolvable.
            # Keeping that identical is what keeps this an unchanged decision.
            paths = {r: self._path(r) for r in refs}
            n_new = sum(1 for r in refs if r not in sent and paths[r] is not None)
            frames = [dict(frame_ref=r, path=(None if r in confirmed else paths[r]))
                      for r in refs]
            est_tokens = B.epg_prompt_tokens(len(refs))
            _uncached = B.epg_prompt_tokens(n_new)
            cost = (DP.price_gpu_s(_uncached, self._uncached_in_flight, self._charge_mode)
                    if self._d162_pricing else _uncached / C.PREFILL_TOK_S["32BI"])
        else:
            est_tokens = 378
            _uncached = est_tokens
            cost = (DP.price_gpu_s(_uncached, self._uncached_in_flight, self._charge_mode)
                    if self._d162_pricing
                    else C.episodic_gpu_s("32BI", self.st.devices[device_id].frame_count))
        # ---- D179 (4) RELEASE RE-CHECK, ALERT PATH (session B). BEGIN contiguous block --------
        # WIRE TIME. `t` here is the release instant: it is the same `t` `_submit` stamps the
        # request with (its own `delay_s` is a real-run wall-clock correction, zero in a dry run),
        # and nothing in this method has been mutated yet, so a skip spends no budget, charges no
        # queue and needs no refund. The deadline comes from the OPPORTUNITY (`o.deadline_abs()`),
        # never from a per-type constant, because the deadline is a property of the instant.
        #
        # THE QUANTITY is `release_recheck.decide`: the committed D162 first-token model, its
        # coefficients IMPORTED from `d162_price`, applied to this request's own predicted
        # uncached tokens (`_uncached`, the same number the charge uses) and to
        # `_uncached_in_flight`, the uncached work already in front of it, against the time left
        # to the deadline. b7's own `est` (costs.recall_ttft_s, hybrid/hybrid_arm.py:364) is an
        # ISOLATED reload TTFT with no queue term and so cannot see that the queue grew since
        # arrival, which is the whole point of re-asking at release.
        #
        # AND ON THIS PATH THERE WAS NOTHING TO RE-ASK: the alert path has never had a
        # feasibility gate at all. `hybrid/hybrid_arm.py:351` computes `slack` for a dashcam
        # instant, line 355 appends the item UNCONDITIONALLY, and the only read of `it["slack"]`
        # is line 443 inside the utility-per-cost ORDERING index. So for alerts this is the FIRST
        # feasibility test the path has ever carried.
        #
        # THE QUESTION FOR THIS INSTANT IS SKIPPED, THE FRAME IS NOT. Returning here is BEFORE
        # `_mon_sent[device_id]` is updated, so this frame is not recorded as sent; the episode is
        # append-only EP-G, so the NEXT instant's `episode_frame_refs` still carries it and that
        # request's `n_new`, and therefore its `_uncached`, RISE by this frame. Asserted on the
        # actual request body in tests/test_release_recheck.py.
        #
        # `o.state = "declined"` IS REQUIRED AND IS NOT COSMETIC. Left "arrived", the same instant
        # would be re-offered every 100 ms decision period and fail the same check each time, so
        # the counter would count ITEM-PERIODS instead of instants - exactly the confusion
        # `share_capacity.py` records about c5_dash_held. Declining it counts it once. The
        # consequence is stated rather than hidden: `_expire` will not also record this instant as
        # NOT-TAKEN, which is how the committed budget-refusal decline at `_submit_recall` already
        # behaves, and the outcome row below says `served_by="device"` with the device's own
        # delivery time, which `_device_answer` appended at ingest (this method is never reached
        # for an instant the device did not already answer locally).
        if self._release_recheck:
            _rr = RR.decide(qtype="alert", uncached=_uncached,
                            queued_uncached_ahead=self._uncached_in_flight,
                            remaining_s=o.deadline_abs() - t)
            if not _rr["feasible"]:
                RR.note_infeasible(self.counts, "alert")
                o.state = "declined"
                self.answers.append(dict(opportunity_id=o.opp_id, kind="monitor",
                                         device_id=device_id, decision=RR.DECISION,
                                         delivered_s=o.t_event,
                                         deadline_s=o.deadline_abs(), served_by="device",
                                         on_time=None))
                self._log_decision(t, RR.LOG_KIND, [o.opp_id], latency_ms=dt_ms, preds=preds,
                                   mix=mix, key="mon:" + device_id)
                self.release_infeasible_events.append(dict(
                    _rr, opportunity_id=o.opp_id, device_id=device_id, kind="monitor", t=t,
                    episode_id=getattr(o, "episode_id", None),
                    episode_index=getattr(o, "episode_index", None),
                    n_episode_frames=len(refs) if epg else 1,
                    skipped_frame_ref=o.frame_ref,
                    est_tokens=int(est_tokens), deadline_abs=o.deadline_abs()))
                return
        # ---- END D179 (4) block ---------------------------------------------------------------
        # ---- D179 (1) to (3) SHARE ADMISSION, ALERT PATH. BEGIN contiguous block -------------
        # After the D179 (4) feasibility decline and BEFORE the budget check: an instant that can
        # no longer make its deadline is declined for good, one that can but has no capacity is
        # HELD, and only then does the budget get a say.
        if not self._share_ok(qtype="alert", uncached=_uncached, kind="monitor", t=t,
                              key=o.opp_id, feasible=True):
            return
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            self.counts["budget_refusal_monitor"] += 1
            return
        self.st.budget.spend(cost)
        self._uncached_in_flight += int(_uncached)
        self._uncached_last_charged = int(_uncached)
        o.state = "in_flight"
        did = self._log_decision(t, "release_monitor", [o.opp_id], latency_ms=dt_ms,
                                 preds=preds, mix=mix, key="mon:" + device_id)
        if epg:
            # Counted off the FRAMES ACTUALLY BUILT, not off the sent-set: `_path` returns None
            # for a frame it cannot find on disk, and `bodies.image_part` then emits the
            # uuid-only reference, so a run with no frames root would otherwise be recorded as
            # sending bytes it did not send. On a real run `preflight.require_frames` refuses to
            # start in that state, and this count is what makes the refusal checkable.
            n_ref = sum(1 for f in frames if f["path"] is None)
            # D158 (2) MOVES THESE TWO COUNTERS, and says so rather than keeping them flattering.
            # They count the WIRE, which is what their names claim, so after the fix a frame that
            # is sent but not yet confirmed is counted as bytes and not as a reference. On a real
            # EP-G run the reference count therefore FALLS and the bytes count RISES by
            # `epg_frames_bytes_resent_unconfirmed`, which is the price of the fix on the dashcam
            # side and is reported, not hidden. `new_tokens_charged` now reads the charge's own
            # basis (`n_new`, the submission-time set) instead of re-deriving it from the body;
            # the two were equal by construction before the fix, so nothing moves on old runs
            # and the record cannot drift from `gpu_s_charged` after it.
            self.counts["epg_monitor_requests"] += 1
            self.counts["epg_frames_sent_as_reference"] += n_ref
            self.counts["epg_frames_sent_as_bytes"] += len(frames) - n_ref
            self.counts["epg_frames_bytes_resent_unconfirmed"] += len(frames) - n_ref - n_new
            self.epg_requests.append(dict(
                opportunity_id=o.opp_id, device_id=device_id, t=t,
                episode_id=getattr(o, "episode_id", None),
                episode_index=getattr(o, "episode_index", None),
                n_frames=len(refs), frame_refs=list(refs),
                n_as_reference=n_ref,
                # A REFERENCE CLAIMED FOR BYTES THE ENGINE HAS NOT ACKNOWLEDGED, which is the
                # 400 this fix exists to remove, and it should now be 0 in every record. The
                # pre-fix expression counted only frames unresolvable on disk; this one also
                # catches a frame referenced while its carrying request is still in flight,
                # which is the actual fault. The two agree exactly before the fix, where
                # `confirmed` and `sent` are the same set.
                n_unresolved=sum(1 for f in frames if f["path"] is None
                                 and f["frame_ref"] not in confirmed),
                n_bytes_resent_unconfirmed=len(frames) - n_ref - n_new,
                prompt_tokens_expected=est_tokens,
                new_tokens_charged=B.epg_prompt_tokens(n_new),
                gpu_s_charged=round(cost, 6)))
        else:
            frames = [dict(frame_ref=o.frame_ref, path=self._path(o.frame_ref))]
        self._submit(kind="monitor", device_id=device_id, session_id=None,
                     opportunity_id=o.opp_id, decision_id=did, frames=frames,
                     est_tokens=est_tokens, question=B.SH_QUERY, options=(),
                     max_tokens=B.SH_GEN["max_tokens"], t=t, mix=mix,
                     dashcam_format=("epg" if epg else "oneframe"))

    def _device_wait_s(self, o) -> float:
        """How long a device-reading arm waits for this question's own device answer (D168).

        The measured Orin WARM completion time for THIS question (StudyORIN-REC WARM, the same
        table the scorer uses), not the flat 0.567 s proxy. Keyed on question_id, which is the
        trace generator's own id, so the live wait and the scored arrival agree by construction
        instead of by coincidence.
        """
        if not DEVICE_WAIT_MEASURED:
            self.counts["device_wait_proxy_by_switch"] += 1
            return float(DEVICE_ANSWER_CHARGE_S)
        # SCOPE. The measured table is StudyORIN-REC WARM over 97 ROBOT RECALL questions. It is
        # the only measured device latency that exists: there is none for single-shot and none for
        # dashcam (data_sources has ORIN_REC_WARM and the superseded ORIN2 in-process curve, and
        # nothing else). So the measured value is used exactly where it was measured, and every
        # other path is counted BY TYPE rather than lumped into one "fallback", because the three
        # cases need different remedies and only one of them is a missing table entry.
        if getattr(o, "kind", None) == "monitor":
            # DASHCAM: measured Orin EP-G warm-append first-token latency at this episode position
            # (D148 / D153 deployment mode). Clamped to the table's range, which is the 21-frame
            # EP-G cap, so a position past the cap is the cap rather than a silent proxy.
            tab = _device_wait_dashcam()
            if tab:
                n = len(getattr(o, "episode_frame_refs", None) or ()) or 1
                n = min(max(int(n), min(tab)), max(tab))
                self.counts["device_wait_measured"] += 1
                self.counts["device_wait_measured_dashcam"] += 1
                return float(tab[n])
            self.counts["device_wait_no_measured_value_monitor"] += 1
            return float(DEVICE_ANSWER_CHARGE_S)
        qid = getattr(o, "question_id", None)
        if qid is not None:
            v = _device_wait_table().get(str(qid))        # ROBOT recall, completion (ORIN-REC WARM)
            if v is not None:
                self.counts["device_wait_measured"] += 1
                self.counts["device_wait_measured_robot"] += 1
                return float(v)
            v = _device_wait_single_shot().get(str(qid))  # SINGLE-SHOT, completion (StudySS2 Orin)
            if v is not None:
                self.counts["device_wait_measured"] += 1
                self.counts["device_wait_measured_single_shot"] += 1
                return float(v)
            self.counts["device_wait_no_measured_value_recall_kind"] += 1
            return float(DEVICE_ANSWER_CHARGE_S)
        self.counts["device_wait_no_measured_value_other"] += 1
        return float(DEVICE_ANSWER_CHARGE_S)

    def _submit_touch(self, s, t: float, dt_ms: float, preds, mix) -> Optional[str]:
        """Component 2. A real TOUCH: one minimal request that re-presents the built prefix.

        It carries NO new frames and asks for one token, so it is the cheapest way to make the
        engine ACCESS the prefix, which is the only thing that moves vLLM's LRU recency (D150;
        residency cannot be commanded, D44).

        Refusals are counted, never silent, and each has its own counter so a proof can tell a
        guard refusal from an empty prefix from a budget refusal. M6's mixed-touch rule is the
        important one: a touch that straddles the tiers LOSES host-warmth, so issuing it would
        destroy the copy it exists to protect.
        """
        built = len(s.confirmed_bytes_for)
        prefix_tokens = int(getattr(s, "built_tokens", 0) or 0)
        d = TP.should_touch(belief=dict(getattr(s, "belief", {}) or {}),
                            prefix_tokens=prefix_tokens, costs=C,
                            budget_ok=self.st.budget.can_spend)
        self.counts["touch_considered"] += 1
        if not d["touch"]:
            self.counts["touch_refused"] += 1
            self.counts["touch_refused_" + ("guard" if "M6" in d["reason"] or "cold" in d["reason"]
                                            else "budget" if "budget" in d["reason"]
                                            else "no_prefix")] += 1
            return None
        if built <= 0:
            self.counts["touch_refused"] += 1
            self.counts["touch_refused_no_confirmed_prefix"] += 1
            return None
        _touch_price = (DP.price_gpu_s(TP.TOUCH_UNCACHED_TOKENS, self._uncached_in_flight,
                                       self._charge_mode)
                        if self._d162_pricing else d["price_gpu_s"])
        if self._d162_pricing and not self.st.budget.can_spend(_touch_price):
            self.counts["touch_refused"] += 1
            self.counts["touch_refused_budget"] += 1
            return None
        self.st.budget.spend(_touch_price)
        # ---- D179 (1) to (3) SHARE ADMISSION, TOUCH (background). BEGIN block ----------------
        _tq = SA.type_of_device(getattr(s, "device_id", "") or "")
        if not self._share_ok(qtype=_tq, uncached=TP.TOUCH_UNCACHED_TOKENS, kind="touch", t=t,
                              key="touch:" + str(s.session_id)):
            return None
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        self._uncached_in_flight += int(TP.TOUCH_UNCACHED_TOKENS)
        self._uncached_last_charged = int(TP.TOUCH_UNCACHED_TOKENS)
        self.counts["touch_price_milli_sum"] += int(round(_touch_price * 1000.0))
        did = self._log_decision(t, "touch", [], latency_ms=dt_ms, preds=preds, mix=mix,
                                 key="touch:" + s.session_id, session_id=s.session_id,
                                 piece_tokens=0)
        # uuid-only references for the frames whose carrying request returned 200 (D158 (2)); a
        # touch never re-sends bytes, because re-sending would make it a rebuild, not a touch.
        frames = [dict(frame_ref=r, path=None) for r in s.frames[:built]
                  if r in s.confirmed_bytes_for]
        if not frames:
            self.counts["touch_refused"] += 1
            self.counts["touch_refused_no_confirmed_prefix"] += 1
            return None
        self.counts["touch_issued"] += 1
        self.counts["touch_issued_" + d["predicted_tier"]] += 1
        return self._submit(kind="touch", device_id=s.device_id, session_id=s.session_id,
                            opportunity_id=None, decision_id=did, frames=frames,
                            est_tokens=prefix_tokens, question=None, options=(),
                            max_tokens=TP.TOUCH_MAX_TOKENS, t=t, mix=mix)

    def _advance_build(self, s, target_tokens: Optional[int], slice_tokens: Optional[int],
                       t: float, dt_ms: float, preds, mix) -> Optional[str]:
        """One MATERIALIZE advances a session's build by ONE piece (or the remainder).

        LIVE SEMANTICS, stated because it differs from StudyLIVE1's adapter, which issued a whole
        chain on one MATERIALIZE: here each piece is a separate decision and a separate request,
        so an arm CAN hold or re-order the next piece. The same rule applies to every arm, so no
        arm gains or loses by it. `slice_tokens = None` builds the remainder in one request,
        which is the monolithic option every pre-amendment baseline can express.
        """
        target = min(int(target_tokens or s.est_tokens), max(int(s.est_tokens), 1))
        if s.built_tokens >= target:
            return None
        left = target - s.built_tokens
        piece = left if slice_tokens is None else min(int(slice_tokens), left)
        n_new = max(1, int(round(piece / float(CS.D2_TOK_PER_IMG))))
        # BUILD PROGRESS, and it reads the SUBMISSION-time set (D158 (2)). It must: `already`
        # chooses which frames this piece builds, so making it wait for a 200 would rebuild the
        # same frames and change DECISIONS rather than only wire bodies. Reference eligibility
        # is the other job, and that one does wait; see `s.confirmed_bytes_for` just below and
        # in `_submit_recall`.
        already = len(s.sent_bytes_for)
        new_refs = s.frames[already:already + n_new]
        if not new_refs:
            return None
        if self._state_priced_costs:
            # The committed charge prices the SLICE only. This also prices re-presenting
            # the built prefix, whose cost depends on whether it survived (D160).
            _pr = TP.build_price_gpu_s(max(piece, 1), int(getattr(s, "built_tokens", 0) or 0),
                                       dict(getattr(s, "belief", {}) or {}), C)
            cost = _pr["total_gpu_s"]
            self.counts["state_priced_build"] += 1
            self.counts["state_priced_build_" + _pr["predicted_tier"]] += 1
        else:
            cost = C.recall_gpu_s(max(piece, 1), "COLD")
        if self._d162_pricing:
            # a build prefills exactly its piece, so the piece IS the uncached count
            cost = DP.price_gpu_s(max(int(piece), 1), self._uncached_in_flight,
                                   self._charge_mode)
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            self.counts["budget_refusal_build"] += 1
            return None
        self.st.budget.spend(cost)
        # ---- D179 (1) to (3) SHARE ADMISSION, WARM BUILD (background). BEGIN block -----------
        # D179 (3) chunks warms at 2,048, which exceeds recall's equal-split share of 1,256.7, so
        # a warm is admitted through the BORROW path and only while recall itself is idle. An
        # oversize test on background would have refused every chunk in every state, which is
        # warming switched off rather than tight floors.
        _bq = SA.type_of_device(getattr(s, "device_id", "") or "")
        if not self._share_ok(qtype=_bq, uncached=max(int(piece), 1), kind="piece", t=t,
                              key="build:" + str(getattr(s, "session_id", ""))):
            return None
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        self._uncached_in_flight += max(int(piece), 1)
        self._uncached_last_charged = max(int(piece), 1)
        kind = "piece" if slice_tokens is not None else "whole"
        did = self._log_decision(t, "release_piece" if kind == "piece" else "release_whole",
                                 [], piece_tokens=int(piece), latency_ms=dt_ms, preds=preds,
                                 mix=mix, key="rc:" + s.session_id, session_id=s.session_id)
        # REFERENCE ELIGIBILITY (D158 (2)). The already-built prefix may go as uuid-only
        # references only for the frames whose carrying request RETURNED 200; the rest carry
        # their bytes again, because the engine has not registered the piece holding them and
        # answers 400 to a reference it cannot resolve. `already` and `new_refs` above are
        # untouched, so this changes the wire body and nothing else.
        frames = ([dict(frame_ref=r, path=(None if r in s.confirmed_bytes_for
                                           else self._path(r))) for r in s.frames[:already]]
                  + [dict(frame_ref=r, path=self._path(r)) for r in new_refs])
        self.counts["racefix_bytes_resent"] += _n_resent(frames, s)
        rid = self._submit(kind=kind, device_id=s.device_id, session_id=s.session_id,
                           opportunity_id=None, decision_id=did, frames=frames,
                           est_tokens=int(s.built_tokens + piece), question=None, options=(),
                           max_tokens=1, t=t, mix=mix)
        self.builds[rid] = dict(session_id=s.session_id, piece_tokens=int(piece),
                                refs=list(new_refs), answers=None)
        return rid

    def _submit_recall(self, o, s, t: float, dt_ms: float, preds, mix, whole: bool) -> None:
        # D133/D134 Part A, the two reads that make the arm's choices reach execution.
        # `tokens_for_representation` sends and charges what was ASKED for (RECENT is the recent
        # window, 467 tokens, not the whole history), and `residency_readiness` costs from WHERE
        # THE KV IS rather than from what the policy believes, so an offloaded history is charged
        # as a host reload. Both helpers are committed in `cstate.py`.
        tokens = s.tokens_for_representation(getattr(o, "requested_representation", None))
        cost = C.recall_gpu_s(tokens, s.residency_readiness())
        # UNCACHED, not tokens: a warm recall re-presents a prefix the engine already holds, and
        # charging it for the whole history is the same wrong shape the touch charge had.
        # D187 (1) COLD-PRICING FIX, pre-registered in reports/prereg_cold_pricing_r1.md before
        # any r1 cell. The previous line subtracted `built_tokens`, which counts only the
        # COORDINATOR'S OWN 1,024-token build pieces, while the engine holds the WHOLE history from
        # the EP-G per-frame uploads. Measured over 210 release-infeasible recall skips at seeds 4
        # to 7: predicted u had a median of 14,712 at s4 against the engine's own 1,050 on the same
        # opportunity in covex-v6-state-uo, a ratio of 15.6x, and the size term ALONE exceeded the
        # slack in 29 of them with zero queue, against 1 using the engine's count. That mispricing
        # is what refused 57 of 70 recall releases at s4.
        #
        # NOT the hypothesis anyone held first: readiness is GPU-WARM at 69 of those 70 skips, so
        # the warm prefix WAS being subtracted. The wrong quantity was.
        #
        # `last_telemetry_cached_tokens` is the engine's OWN report of the prefix it holds
        # (engine_actions.py:358) and was read NOWHERE in the pricing path: written and never read.
        # MAX of the two, not replacement: `built_tokens` exists before a session's first request
        # and the telemetry only after one, and both are LOWER BOUNDS on the true prefix.
        # THE TELEMETRY IS ONLY TRUSTED WHILE THE SESSION IS BELIEVED RESIDENT, and that condition
        # is not cosmetic. `last_telemetry_cached_tokens` is written on a completed request
        # (engine_actions.py:358) and is NEVER RESET ON EVICTION: there is no write to it anywhere
        # else in the tree. So after an eviction it still holds the prefix the engine USED to have.
        # Subtracting it then UNDERSTATES the work and admits a request that cannot make its
        # deadline, which is the mirror image of the bug this block exists to fix, and it would
        # have shown up as lateness rather than as skips. Found by the H100 reading the code rather
        # than by any test here, before the first r1 cell ran.
        #
        # Gating on COLD keeps the fix exactly where the fault was: readiness is GPU-WARM at 69 of
        # the 70 mispriced skips at s4, so the repriced path still covers them.
        _cold = (s.residency_readiness() == "COLD")
        _tel = 0 if _cold else int(getattr(s, "last_telemetry_cached_tokens", 0) or 0)
        _prefix = max(int(getattr(s, "built_tokens", 0) or 0), _tel)
        _uncached = (int(tokens) if _cold and not _prefix
                     else max(int(tokens) - _prefix, 0))
        if self._d162_pricing:
            cost = DP.price_gpu_s(_uncached, self._uncached_in_flight, self._charge_mode)
        # ---- D179 (4) RELEASE RE-CHECK, RECALL AND ASSISTANCE PATHS (session B). BEGIN block --
        # The same wire-time test as the alert path, for the other two DEADLINE types. b7 DOES
        # gate this path at arrival (`est <= qs`, hybrid/hybrid_arm.py:384, with `est` from the
        # committed cost curve at line 364), which is why this one is a RE-check: the arrival test
        # declines 306 of 485 offered recalls in the committed base cells, and what it cannot see
        # is the queue that grew between that decision and this release. The predictor is the
        # committed D162 model with the queue term, coefficients imported from `d162_price`.
        #
        # The type comes from the device-id prefix, which is how the committed cells distinguish
        # robot recall from assistance; a device this module cannot classify is counted under a
        # separate diagnostic name and is NOT re-checked, because its deadline semantics are not
        # established here. Placed before the budget check, so a skip spends nothing and the
        # decline mirrors the committed budget-refusal decline exactly (state, outcome row shape,
        # device delivery time), with its own decision string so the two are never confused.
        if self._release_recheck:
            _qt = RR.type_of_request("recall", o.device_id)
            if _qt is None:
                self.counts[RR.COUNTER_UNCLASSIFIED] += 1
            else:
                _rr = RR.decide(qtype=_qt, uncached=_uncached,
                                queued_uncached_ahead=self._uncached_in_flight,
                                remaining_s=o.deadline_abs() - t)
                if not _rr["feasible"]:
                    RR.note_infeasible(self.counts, _qt)
                    o.state = "declined"
                    o.served_at = (o.t_event + self._device_wait_s(o) if self.reads_device
                                   else t)
                    self.answers.append(dict(opportunity_id=o.opp_id, kind="recall",
                                             device_id=o.device_id, decision=RR.DECISION,
                                             delivered_s=o.served_at,
                                             deadline_s=o.deadline_abs(), served_by="device",
                                             on_time=None))
                    self._log_decision(t, RR.LOG_KIND, [o.opp_id], latency_ms=dt_ms, preds=preds,
                                       mix=mix, key="rc:" + (o.session_id or ""),
                                       session_id=o.session_id)
                    self.release_infeasible_events.append(dict(
                        _rr, opportunity_id=o.opp_id, device_id=o.device_id, kind="recall", t=t,
                        session_id=o.session_id, est_tokens=int(tokens),
                        readiness=s.residency_readiness(),
                        deadline_abs=o.deadline_abs()))
                    return
        # ---- END D179 (4) block ---------------------------------------------------------------
        # ---- D179 (1) to (3) SHARE ADMISSION, RECALL AND ASSISTANCE. BEGIN block -------------
        # The type comes from the device id, so an assistance request is charged against the
        # assistance floor and not lumped in with recall: this method serves both.
        _rq = SA.type_of_device(o.device_id)
        if not self._share_ok(qtype=_rq, uncached=_uncached, kind="recall", t=t,
                              key=o.opp_id, feasible=True):
            return
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        if not self.st.budget.can_spend(cost):
            self.counts["budget_refusal"] += 1
            self.counts["budget_refusal_recall"] += 1
            o.state = "declined"
            self.answers.append(dict(opportunity_id=o.opp_id, kind="recall",
                                     device_id=o.device_id, decision="DEVICE-on-refusal",
                                     delivered_s=t, deadline_s=o.deadline_abs(),
                                     served_by="device", on_time=None))
            return
        self.st.budget.spend(cost)
        self._uncached_in_flight += int(_uncached)
        self._uncached_last_charged = int(_uncached)
        o.state = "in_flight"
        did = self._log_decision(t, "release_recall", [o.opp_id], latency_ms=dt_ms, preds=preds,
                                 mix=mix, key="rc:" + (o.session_id or ""),
                                 session_id=o.session_id,
                                 representation=getattr(o, "requested_representation", None),
                                 representation_defaulted=getattr(
                                     o, "representation_defaulted", False))
        # RECENT-send fix (user ruling 2026-11-20): a recall released as RECENT sends what it is CHARGED, the recent
        # window, not the whole session. Before this fix the budget and est_tokens used tokens_for_representation
        # (467 for RECENT) while the body carried every frame of the session. The window is the session's most recent
        # frames, the count proportional to the charged share of the history: k = ceil(len(frames) * tokens / whole),
        # at least 1. Every other representation is unchanged (byte-identical frame list).
        refs = list(s.frames)
        idx0 = 0
        if str(getattr(o, "requested_representation", None) or "").upper() == "RECENT" and refs:
            whole_tok = max(int(s.est_tokens), 1)
            k = max(1, min(len(refs), -(-len(refs) * int(tokens) // whole_tok)))
            idx0 = len(refs) - k
            self.counts["recent_window_sends"] += 1
        if whole:
            frames = [dict(frame_ref=r, path=self._path(r)) for r in refs[idx0:]]
        else:
            # REFERENCE ELIGIBILITY (D158 (2)), and note that this is now a SET MEMBERSHIP test
            # where it used to be a prefix index. The old line read `sent = len(s.sent_bytes_for)`
            # and sliced `refs[idx0:sent]`, i.e. it used a COUNT as an INDEX, which is sound only
            # while the bytes-sent set is a PREFIX of the frame list. Neither set is a prefix in
            # general: a `whole` recall sends bytes for the TAIL as well, and a 200 can arrive out
            # of submission order. Testing membership needs no such invariant, so the invariant is
            # removed rather than assumed. A frame goes as a uuid-only reference if and only if
            # the request that carried its bytes returned 200; everything else carries bytes
            # again, which costs UPLINK BYTES and is the declared price of the fix. The uuid is
            # unchanged, so whether the engine also re-prefills a re-sent image or serves it from
            # its own multimodal cache is an engine question and is NOT claimed here.
            frames = [dict(frame_ref=r, path=(None if r in s.confirmed_bytes_for
                                              else self._path(r))) for r in refs[idx0:]]
            self.counts["racefix_bytes_resent"] += _n_resent(frames, s)
        self._submit(kind="recall", device_id=o.device_id, session_id=o.session_id,
                     opportunity_id=o.opp_id, decision_id=did, frames=frames,
                     est_tokens=tokens, question=o.question, options=o.options,
                     max_tokens=B.RECALL_GEN["max_tokens"], t=t, mix=mix)

    def _path(self, frame_ref: Optional[str]) -> Optional[Path]:
        if frame_ref is None:
            return None
        if self.frame_cache is not None:
            return self.frame_cache.path_of(frame_ref)
        p = Path(frame_ref)
        if not p.is_absolute() and self.frames_root is not None:
            p = self.frames_root / frame_ref
        return p if p.exists() else None

    # ---------------------------------------------------------------- requests
    def _submit(self, *, kind: str, device_id: str, session_id: Optional[str],
                opportunity_id: Optional[str], decision_id: Optional[str],
                frames: List[Dict[str, Any]], est_tokens: int, question: Optional[str],
                options, max_tokens: int, t: float, mix: Dict[str, int],
                dashcam_format: str = "oneframe") -> str:
        self.n_req += 1
        rid = f"r{self.n_req}"
        # ONE PRICE SOURCE bookkeeping: the charge site has just added its PREDICTED uncached
        # count to `_uncached_in_flight`, and the completion must remove THE SAME NUMBER. Keying
        # it on the request id is what makes that exact. Decrementing by the engine's own
        # `prompt - cached` instead would mix a predicted increment with a measured decrement and
        # the in-flight total would drift, silently inflating every later price.
        # D179: UNCONDITIONAL, where it used to sit under `if self._d162_pricing`. The increments
        # to `_uncached_in_flight` were already unconditional (four sites), so gating only the
        # bookkeeping and the decrement made the field a MONOTONICALLY INCREASING CUMULATIVE TOTAL
        # on any arm that does not declare D162 pricing: the run's whole uncached volume, under a
        # name that says queue depth. Nothing read it there, so nothing was wrong until session
        # B's release re-check became the first reader outside the gate and measured a 1.0 s alert
        # deadline against a number in the tens of thousands, firing the D179 STOP at 0.9998.
        # Decision-neutral by construction: under D162 pricing the condition was already true, and
        # without it no other site reads the field. Proved on a digest for one arm of each kind.
        self._uncached_pending[rid] = int(self._uncached_last_charged)
        # ---- D179 (1) to (3) SHARE ADMISSION, W TRACKING. BEGIN contiguous block --------------
        # Tracked HERE, at the single point where a request id exists for every kind, rather than
        # at the four release sites, so the id W is keyed on is exactly the id the drain pops.
        # Keying on anything else is how an in-flight total drifts, which the note above records.
        if self._share_admission:
            _wq = SA.type_of_device(device_id)
            if _wq is not None:
                self._w.on_submit(rid, _wq, int(self._uncached_last_charged),
                                  background=SA.is_background(kind))
        # ---- END D179 (1) to (3) block --------------------------------------------------------
        d = self.st.devices[device_id]
        # THE TRUE SUBMISSION STAMP (StudyLIVE2-harness addendum (a), from flash's branch). A
        # decision that takes 100 ms puts its requests on the wire 100 ms after the epoch it
        # belongs to; stamping them with the epoch's nominal instant would understate every time
        # derived from them by that delay. The delay is recorded per request and IS what a slow
        # decision costs: later submissions, not held answers. A dry run has no wall clock and
        # keeps the nominal instant, so its logs stay deterministic. Unlike the branch, the
        # delay is charged only inside an epoch (`_epoch_wall0` is cleared when it ends).
        delay_s = 0.0
        if not self.dry_run and self._epoch_wall0 is not None:
            delay_s = max(0.0, time.perf_counter() - self._epoch_wall0)
            self.submit_delays_ms.append(delay_s * 1000.0)
        t = t + delay_s
        body = B.build_body(kind=kind, device_id=device_id, session_id=session_id,
                            run_tag=self.run_tag, salt=d.salt, header=HEADER_TEXT,
                            frames=frames, question=question, options=options,
                            max_tokens=max_tokens, est_tokens=est_tokens,
                            defer_images=self.defer_images,
                            kv_transfer_params=OP.params_for(d.type, self._offload_controls),
                            dashcam_format=dashcam_format)
        sub = Live2Submission(request_id=rid, decision_id=decision_id, kind=kind,
                              device_id=device_id, session_id=session_id,
                              opportunity_id=opportunity_id, body=body,
                              est_tokens=int(est_tokens), sent_s=t, cache_salt=d.salt,
                              mm_uuids=list(body["_live2"]["mm_uuids"]), traffic_mix=dict(mix),
                              meta=dict(nominal_t=t - delay_s, decision_delay_s=delay_s,
                                        # D158 (2): the frames whose BYTES this request carries,
                                        # recorded at submission so `_collect` can promote
                                        # exactly these on a 200. Recorded explicitly rather
                                        # than reconstructed from `mm_uuids`, which are the body
                                        # builder's composite cache keys and not frame refs.
                                        bytes_frame_refs=[f["frame_ref"] for f in frames
                                                          if f.get("path") is not None],
                                        **self._priority_for(kind, device_id, session_id, opportunity_id)))
        self.st.in_flight[kind] += 1
        self.counts["submitted_" + kind] += 1
        if kind != "monitor":
            # the uncached count THIS request was charged: every release path sets
            # `_uncached_last_charged` immediately before calling `_submit`
            self._released_prefills[rid] = dict(t0=float(t), t1=None,
                                                uncached=int(self._uncached_last_charged))
        if session_id is not None:
            s = self.st.sessions[session_id]
            for f in frames:
                if f.get("path") is not None:
                    s.sent_bytes_for.add(f["frame_ref"])
        elif kind == "monitor":
            # the same bookkeeping on the dashcam side, which had no need of it while a
            # monitoring request was one frame that was never sent twice (D153)
            for f in frames:
                if f.get("path") is not None:
                    self._mon_sent[device_id].add(f["frame_ref"])
        if self.dry_run:
            self.futures.append((_DryFuture(sub, self._dry_service_s(sub), t,
                                            lambda: self.st.now), sub))
        else:
            self.futures.append((self.be.submit_live2(sub), sub))
        return rid

    # ---- D179 (1) to (3) SHARE ADMISSION (session A), the one gate. BEGIN contiguous block ----
    def _mirror_d179_stats(self) -> None:
        """Copy the D179 counters onto the ARM's stats dict.

        `test_hybrid.dry` returns only `getattr(arm, "stats", None)`
        (hybrid/test_hybrid.py:46), so a counter that lives on the COORDINATOR is invisible to
        every dry proof. That is not a cosmetic gap: it already made a live share-admission
        mechanism read as a dead one, and it would do the same to the D179 (4) release re-check,
        whose `release_infeasible` counters live in the same place. Both prefixes are mirrored, and
        this is called UNCONDITIONALLY so an arm with only one of the two switches on is still
        measurable.
        """
        _as = getattr(self.arm, "stats", None)
        if not isinstance(_as, dict):
            return
        for _k, _v in self.counts.items():
            _ks = str(_k)
            # `submitted_` is mirrored too, because without it a skip COUNT has no in-cell
            # DENOMINATOR and the rate can only be formed by borrowing another arm's, which is a
            # cross-arm substitution dressed as a rate. It also serves as the positive control on
            # this mirror: submitted_monitor cannot be zero in a cell with decision rows.
            if (_ks.startswith("share_") or _ks.startswith("release_infeasible")
                    or _ks.startswith("submitted_")):
                _as[_ks] = _v
        if self._share_admission:
            _as["share_admission"] = SA.summary(self._w, enabled=True)
            _as["share_w_high_water"] = int(getattr(self, "_w_hi", 0))
            _as["share_w_zero_returns"] = int(getattr(self, "_w_zero", 0))
            _as["share_w_tracked_at_end"] = int(self._w.as_dict()["tracked_requests"])
            _as["share_w_over_wmax_periods"] = int(getattr(self, "_w_over", 0))
            _as["share_w_over_wmax_types"] = {
                k: int(v) for k, v in getattr(self, "_w_over_types", {}).items()}
            _as["share_w_samples_per_gate_call"] = int(getattr(self, "_w_samples", 0))
            _as["share_w_over_wmax_periods_TIME"] = int(getattr(self, "_wp_over", 0))
            _as["share_w_samples_TIME"] = int(getattr(self, "_wp_samples", 0))
            _as["share_w_over_wmax_types_TIME"] = {
                k: int(v) for k, v in getattr(self, "_wp_over_types", {}).items()}

    def _share_ok(self, *, qtype, uncached, kind, t, key, feasible=None) -> bool:
        """One admission gate for all four release sites. True means submit.

        Returns True unchanged when the switch is off, so every other arm keeps its decisions.
        `feasible` carries the b7 conjunct explicitly rather than by convention, because a
        convention no test can reach is the same shape as a write-only field.
        """
        if not self._share_admission or qtype is None:
            return True
        # D182/addendum 12 item 3(b): the FLEXIBLE SPLIT consumer. This argument was the absent
        # link: share_admission.py:162-168 has always READ weights_by_type, and this call site did
        # not PASS it, so the deficit feed was computed, exposed and never consumed. A quantity
        # written and never read is Step 2's stopping condition, and I had told the session
        # building the feed that the consumer was already wired. It was not.
        #
        # Additive by construction: the accessor returns None when the arm has no deficit feed or
        # its switch is off, and SA.allowed treats a falsy value as the equal split, so every
        # other arm's decisions are unchanged. Proved on a digest, not asserted.
        _wbt = None
        _wfn = getattr(self.arm, "live2_share_weights", None)
        if callable(_wfn):
            _wbt = _wfn()
        ok, why = SA.allowed(qtype=qtype, uncached=int(uncached), kind=str(kind),
                             tracker=self._w, feasible=feasible, enabled=True,
                             weights_by_type=_wbt)
        self.counts["share_" + ("admit" if ok else "deny") + "_" + qtype] += 1
        self.counts["share_reason_" + why] += 1
        if not ok:
            # Item-periods AND distinct instants, under two names. See the note in __init__.
            self.counts["share_hold_periods_" + qtype] += 1
            if key is not None and key not in self._share_held_instants[qtype]:
                self._share_held_instants[qtype].add(key)
                self.counts["share_hold_instants_" + qtype] += 1
                # ONE DECISION ROW PER DISTINCT HELD INSTANT, not per period. Without it a hold
                # leaves NO trace in the decision log: it returns before `_log_decision`, so the
                # mechanism would be invisible to the committed logs and to any digest, and a
                # row-count change could not be attributed to this switch rather than to another
                # one on the same arm. That is the "unexpressible" category of Rule 2, and it
                # nearly happened: the first proof of this gate credited a digest change to share
                # admission when the arm also carries the D179 (4) re-check. Per-period logging is
                # deliberately NOT done, because the same instant returns every 100 ms and the log
                # would count item-periods, the confusion `share_capacity.py` records.
                self._log_decision(float(t), "share_hold", [key] if key else [],
                                   latency_ms=0.0, preds=None, mix=None, key=str(key))
        # The counters live on the COORDINATOR, and `test_hybrid.dry` returns only the ARM's stats
        # (hybrid/test_hybrid.py:46), so without this mirror a dry proof cannot see them at all and
        # would read a live mechanism as a dead one. The H100's reader takes the same block.
        # W OVER TIME, which D180 (5) asks for and which is also the only way to tell an
        # end-of-run in-flight residue from a LEAK. A leak in W raises nothing and prints nothing:
        # it drifts upward over a 1,200 s cell and reads as "the floors are too tight". So record
        # the high-water mark, how often W returned to zero (a leak never does), and how long each
        # type sat at or above its floor.
        _wt = self._w.total()
        self._w_hi = max(getattr(self, "_w_hi", 0), _wt)
        self._w_samples = getattr(self, "_w_samples", 0) + 1
        if _wt == 0:
            self._w_zero = getattr(self, "_w_zero", 0) + 1
        # D180 (5) and the user's addendum 10 item 3: how often W is over capacity, and WHICH
        # TYPES are present when it is. Labelled dry-W (submit to SETTLE) wherever it is reported,
        # and used to size NOTHING: the floors come from live submit-to-first-token behaviour.
        if _wt > SCAP_W_MAX:
            self._w_over = getattr(self, "_w_over", 0) + 1
            _ot = getattr(self, "_w_over_types", None)
            if _ot is None:
                _ot = self._w_over_types = {}
            _present = tuple(sorted(t for t in SA.TYPES if self._w.w(t) > 0))
            _key = "+".join(_present) if _present else "none"
            _ot[_key] = _ot.get(_key, 0) + 1
        for _t in SA.TYPES:
            if self._w.w(_t) >= SCAP_FLOORS[_t]:
                self.counts["share_at_or_above_floor_" + _t] += 1
        self._mirror_d179_stats()
        if len(self._share_events) < 20000:
            self._share_events.append(dict(
                t=round(float(t), 6), qtype=qtype, kind=str(kind), uncached=int(uncached),
                admitted=bool(ok), reason=why, key=key,
                w_by_type=dict(self._w.as_dict()["w_by_type"]), w_total=self._w.total()))
        return ok

    def _share_track(self, request_id, qtype, uncached, *, background) -> None:
        if self._share_admission and qtype is not None:
            self._w.on_submit(str(request_id), qtype, int(uncached), background=background)
    # ---- END D179 (1) to (3) block ------------------------------------------------------------

    def _dry_service_s(self, sub: Live2Submission) -> float:
        """The deterministic stand-in used by `--dry-run`, which sends no HTTP at all.

        It is the committed cost curve (`baselines/costs.py`), so the loop advances without a
        server and WITHOUT a wall clock. A dry run is a determinism and legality test, never a
        measurement and never a latency result.
        """
        if sub.kind == "monitor":
            return float(C.episodic_cloud_latency_s("32BI", 1, 25))
        return float(C.recall_ttft_s(max(sub.est_tokens, 1), "COLD"))

    def _promote_confirmed_bytes(self, sub: Live2Submission, r: Dict[str, Any]) -> None:
        """D158 (2). A frame's bytes become REFERENCEABLE when the request carrying them got 200.

        This is the whole fix, and it is the only place reference eligibility advances. Before
        it existed, `_submit` marked a frame sent and the next request on the same session
        referenced it by uuid alone, often while the carrying request was still in flight; the
        engine had not registered the piece holding the bytes and answered HTTP 400, after which
        every later reference on that session pointed at bytes the engine never received. On
        CAL1F `warm-all-lru` that was 226 400s with ZERO preceded by a completed 200 on the same
        session.

        It runs BEFORE `_settle`, on purpose: `_settle` can release a chained recall in this same
        completion, and promoting first lets that recall reference the frames this 200 just
        confirmed instead of re-sending their bytes. Running it after would still be correct,
        only more expensive.

        A DRY RUN HAS NO ENGINE AND NO `http_status`, so nothing is ever promoted and every
        reference goes out as bytes. That is the conservative direction, it changes no decision,
        and it is why the 50-arm dry prescreen proves this change decision-neutral and proves
        nothing about the wire form on a live cell.
        """
        if r.get("http_status") != 200:
            return
        refs = list((sub.meta or {}).get("bytes_frame_refs") or ())
        if not refs:
            return
        if sub.session_id:
            s = self.st.sessions.get(sub.session_id)
            if s is None:
                return
            # Intersected with the submission-time set rather than assigned, which keeps
            # `confirmed_bytes_for` a SUBSET of `sent_bytes_for` by construction. The one way
            # they could diverge is a `session_start` that replaces a SessionRec for a
            # session_id with a request still in flight against the old record
            # (`cstate.session_start`, which only preserves a preloaded history); that frame
            # belongs to a history this record does not have, so it is dropped and counted
            # rather than promoted into the wrong session.
            promote = set(refs) & s.sent_bytes_for
            self.counts["racefix_confirm_dropped_stale"] += len(refs) - len(promote)
            s.confirmed_bytes_for |= promote
            assert s.confirmed_bytes_for <= s.sent_bytes_for, (
                "confirmed bytes outside the submitted set for %s" % sub.session_id)
            self.counts["racefix_bytes_confirmed_session"] += len(promote)
        elif sub.kind == "monitor":
            self._mon_confirmed[sub.device_id] |= set(refs)
            self.counts["racefix_bytes_confirmed_monitor"] += len(refs)

    def _self_released_overlap(self, sub: Live2Submission, first_s: Optional[float],
                               done_s: float) -> Tuple[bool, int]:
        """Did this monitor's WAIT overlap a robot prefill THE COORDINATOR ITSELF RELEASED?

        Causally available at this instant and no more than that: the coordinator knows what it
        released, when, and what has not finished yet. A span with `t1` None is still in flight,
        so it overlaps anything that had not ended before it began. The monitor's wait is
        [submitted, first token]; when the engine reported no first token the whole request is
        used, which is the longer interval and so the conservative choice for a rule that
        SUPPRESSES a back-off.

        The uncached count is the one the coordinator CHARGED at release (its own prediction),
        not the engine's later `prompt - cached`: the predicted number is what exists at release
        time and is identical in a dry run, which is what makes the rule provable off a server.
        """
        t0 = float(sub.sent_s)
        t1 = float(first_s if first_s is not None else done_s)
        worst = 0
        for sp in self._released_prefills.values():
            if int(sp["uncached"]) < C5ATTR_UNCACHED_MIN:
                continue
            end = sp["t1"]
            if float(sp["t0"]) <= t1 and (end is None or float(end) >= t0):
                worst = max(worst, int(sp["uncached"]))
        return bool(worst > 0), worst

    def _collect(self, t: float) -> None:
        still = []
        for fut, sub in self.futures:
            if not fut.done():
                still.append((fut, sub))
                continue
            r = fut.result()
            self.st.in_flight[sub.kind] = max(self.st.in_flight[sub.kind] - 1, 0)
            if r.get("error"):
                self.errors.append(r["error"])
            self._promote_confirmed_bytes(sub, r)
            usage = r.get("usage") or {}
            ct = cached_tokens_of(usage)
            pt = prompt_tokens_of(usage)
            path, frac = SC.cache_path_of(ct, pt)
            # D150 / spec v5 section 8: the engine's OWN per-request cached-token count corrects
            # the residency belief. Until this read existed the belief was a prediction with no
            # correction, which is the write-only shape CLAUDE.md names. The corrector refuses to
            # act on a monitor (no session) and on a None (no usage block is NO EVIDENCE, not a
            # miss), both of which it distinguishes internally.
            if sub.session_id:
                _s = self.st.sessions.get(sub.session_id)
                if _s is not None:
                    # OBSERVE-ONLY BY DEFAULT, and the default is the point. On a DRY cell the
                    # corrector cannot fire (no engine, so no cached_tokens), which is why the
                    # 50-arm byte-identity prescreen proves PATCH 1 harmless and proves NOTHING
                    # about this read. On a LIVE cell it mutates a belief that arms read, so
                    # enabling it mid-sweep would make the cells before and after incomparable
                    # for every arm that reads residency. So the counters always run and the
                    # MUTATION is gated: `observe` measures how often the correction WOULD fire
                    # and changes no decision; `apply` is for v5 cells, which are new cells.
                    _snap = (dict(_s.belief), _s.last_touch_s)
                    _bu = EA.belief_update_from_cached_tokens(
                        _s, ct, pt, now=t,
                        external_tokens=EA.external_cached_tokens_of(usage))
                    self.counts["belief_corrections"] += 1
                    if _bu.changed:
                        self.counts["belief_corrections_changed"] += 1
                        self.counts["belief_to_" + _bu.after] += 1
                    if not self._belief_apply:
                        _s.belief, _s.last_touch_s = _snap
                        if _bu.changed:
                            self.counts["belief_corrections_observed_only"] += 1
            done_s = sub.sent_s + (r["total_s"] * self.speed if r.get("total_s") else 0.0)
            first_s = (sub.sent_s + r["ttft_s"] * self.speed) if r.get("ttft_s") else None
            _sp = self._released_prefills.get(sub.request_id)
            if _sp is not None:
                _sp["t1"] = float(done_s)
            _ovl, _ovl_unc = ((False, 0) if sub.kind != "monitor"
                              else self._self_released_overlap(sub, first_s, done_s))
            if self.logs is not None:
                self.logs.request.write(SC.RequestRecord(
                    request_id=sub.request_id, decision_id=sub.decision_id,
                    device_id=sub.device_id, t_submit=round(sub.sent_s, 6),
                    t_first_token=(round(first_s, 6) if first_s is not None else None),
                    t_done=round(done_s, 6), prompt_tokens=pt, cached_tokens=ct,
                    cache_path=path, cached_fraction=frac,
                    output_tokens=output_tokens_of(usage), http_status=r.get("http_status"),
                    cache_salt=sub.cache_salt, session_id=sub.session_id,
                    opportunity_id=sub.opportunity_id, mm_uuids=list(sub.mm_uuids),
                    traffic_mix=dict(sub.traffic_mix)))
            self.st.ewma("episodic" if sub.kind == "monitor" else "recall", r.get("ttft_s"))
            if hasattr(self.arm, "live2_completed"):
                # An arm that keeps its own model of what the engine is running must be told
                # when a request finishes, or its model never empties.
                # D172 rung 3: the DEADLINE and both on-time flags, so an arm can feed the
                # deficit counters without re-deriving either. The counters measure on-time
                # delivery FROM EITHER SOURCE (D155 (3)), and the two sources are reported
                # SEPARATELY rather than pre-combined, because combining them is a policy choice
                # and belongs in the arm, not here. Additive: every committed arm reads named
                # keys and none of them reads these.
                _o = self.st.opps.get(sub.opportunity_id) if sub.opportunity_id else None
                _dl = _o.deadline_abs() if _o is not None else None
                _devw = self._device_wait_s(_o) if _o is not None else None
                _t_opp = (getattr(_o, "t_arrive", None) or getattr(_o, "t_event", None)
                          ) if _o is not None else None
                self.arm.live2_completed(dict(
                    kind=sub.kind, device_id=sub.device_id, session_id=sub.session_id,
                    opportunity_id=sub.opportunity_id, decision_id=sub.decision_id,
                    t_submit=sub.sent_s, t_first_token=first_s, t_done=done_s,
                    cache_path=path, request_id=sub.request_id,
                    prompt_tokens=(pt if pt is not None else sub.est_tokens),
                    cached_tokens=ct,
                    deadline_abs_s=_dl,
                    cloud_on_time=(None if _dl is None else bool(done_s <= _dl + 1e-9)),
                    device_wait_s=_devw,
                    device_on_time=(None if (_dl is None or _devw is None or _t_opp is None)
                                    else bool(_t_opp + _devw <= _dl + 1e-9)),
                    # C5 attribution support, monitors only; False and 0 on every other kind
                    self_released_prefill_overlap=bool(_ovl),
                    self_released_prefill_uncached=int(_ovl_unc),
                    # D182/addendum 12 item 1 and 3: the PER-DEVICE alert deficit is per EPISODE,
                    # and the arm cannot key an episode without being told which one. Both fields
                    # already exist on the opportunity and are already written to the request log;
                    # they were simply never passed to the arm, which forced a derivation from the
                    # EP-G token law. That derivation is exact on committed data but blind to an
                    # episode with no served instant (4 of 714), and it understates the alert
                    # deficit, which is the wrong direction for the type the rung exists to help.
                    # Additive: every committed arm reads named keys and none reads these.
                    episode_id=getattr(_o, "episode_id", None) if _o is not None else None,
                    episode_index=(getattr(_o, "episode_index", None)
                                   if _o is not None else None)))
            # D179: UNCONDITIONAL, paired with the write above, so the field means the same thing
            # on every arm. See the note at the write site.
            _u = self._uncached_pending.pop(sub.request_id, 0)
            self._uncached_in_flight = max(self._uncached_in_flight - int(_u), 0)
            # ---- D179 (1) SHARE ADMISSION, W DRAIN AT SETTLE. BEGIN block ---------------------
            # NOT redundant with the first-token drain. `on_first` is wired only when a real
            # backend exists (procsplit.py:430-433), so a DRY cell never fires it and a
            # first-token-only drain would let W climb monotonically until the allocator shut for
            # good, which reads as "the floors are too tight" rather than as a bug. This also
            # catches a live request that settled without ever yielding a content token: an error,
            # a refusal, a timeout. Idempotent with the drain above.
            if self._share_admission:
                self._w.on_settled_without_first_token(str(sub.request_id))
            # ---- END D179 (1) block -----------------------------------------------------------
            self._settle(sub, first_s, done_s, path, t, ct, self._score_of(sub, r),
                         http_status=r.get("http_status"))
            self.counts["completed_" + sub.kind] += 1
        for _rid in [k for k, v in self._released_prefills.items()
                     if v["t1"] is not None and float(v["t1"]) < t - C5ATTR_SPAN_KEEP_S]:
            del self._released_prefills[_rid]
        self.futures[:] = still

    def _score_of(self, sub: Live2Submission, r: Dict[str, Any]) -> Dict[str, Any]:
        """The committed extraction on this answer (live2/scores.py), or {} for a build piece.

        A dry run sends no HTTP and so carries no logprobs and no text; the score is then None,
        which the scorer reads as UNKNOWN and refuses AP on, rather than a fabricated number.
        """
        if sub.kind == "monitor":
            return S2.sh_score(S2.first_token_logprobs(r.get("chunks") or ()))
        if sub.kind == "recall":
            return S2.recall_letter(r.get("text") or "")
        return {}

    def _settle(self, sub: Live2Submission, first_s, done_s: float, path, t: float,
                cached_tokens=None, scored: Optional[Dict[str, Any]] = None,
                http_status: Optional[int] = None) -> None:
        if sub.kind in ("piece", "whole") and sub.request_id in self.builds:
            b = self.builds.pop(sub.request_id)
            s = self.st.sessions.get(b["session_id"])
            if s is not None:
                s.built_tokens += b["piece_tokens"]
                # A PARTIALLY built history is not warm: the believed tier becomes GPU only when
                # the whole history is built. The interface's READINESS has no partial value
                # (COLD | HOST-WARM | GPU-WARM), so an incomplete rebuild stays COLD, which is
                # what keeps a chaining arm issuing the next piece. The already-built prefix is
                # still reused on the wire as uuid references, so the request is cheap even
                # while the readiness the arm sees says COLD; that gap is a limitation of the
                # committed action space and is reported.
                if s.built_tokens >= s.est_tokens:
                    s.belief = {"gpu": 1.0, "host": 0.0, "cold": 0.0}
                # the engine's OWN report, not the coordinator's belief (spec 7.6)
                self._log_residency(t, s.session_id, telemetry=cached_tokens)
            if b.get("answers"):
                o = self.st.opps.get(b["answers"])
                if o is not None and s is not None:
                    o.state = "arrived"
                    if s.built_tokens >= s.est_tokens:
                        self._submit_recall(o, s, t, 0.0, {}, self.st.traffic_mix(),
                                            whole=False)
                    # otherwise the chain is unfinished: the question becomes visible again and
                    # the arm decides about the NEXT piece, which is the point of per-piece
                    # release (one unit at a time, spec 7.2 step 3).
            return
        o = self.st.opps.get(sub.opportunity_id) if sub.opportunity_id else None
        if o is None:
            return
        # D144 (user ruling 2026-11-20): a non-200 response is a MISS. Before this, a refused request (e.g. HTTP 400
        # over-context) was settled as an on-time cloud answer with letter "X" because on_time was computed from the
        # completion time alone. Now no cloud answer is emitted: the device answer stands, the question is a miss.
        if http_status is not None and int(http_status) != 200:
            o.state = "failed"
            self.counts["failed_" + sub.kind] += 1
            self.answers.append(dict(opportunity_id=o.opp_id, kind=o.kind, device_id=o.device_id,
                                     decision="CLOUD-failed", delivered_s=None,
                                     deadline_s=o.deadline_abs(), served_by="device", on_time=False,
                                     cache_path=path, request_id=sub.request_id,
                                     http_status=int(http_status)))
            return
        delivered = first_s if first_s is not None else done_s
        o.served_at = delivered
        o.cache_path = path
        ontime = delivered <= o.deadline_abs() + 1e-9
        ev = self._cloud_answer(sub, o, delivered, path, scored)
        o.state = "answered" if ontime else "late"
        if o.kind == "monitor":
            self.st.devices[o.device_id].delivered.append((delivered, 0.0))
        self.answers.append(dict(opportunity_id=o.opp_id, kind=o.kind, device_id=o.device_id,
                                 decision="CLOUD", delivered_s=delivered,
                                 deadline_s=o.deadline_abs(),
                                 served_by="cloud" if ontime else "device",
                                 on_time=bool(ontime), cache_path=path,
                                 request_id=sub.request_id))
        # the coordinator's one output to the fleet: the cloud answer, delivered at t_done. The
        # DEVICE's own answer never passes through here (CONTRACT.md). When the I/O layer has
        # already forwarded it (StudyLIVE2-harness addendum), it is still recorded here, and the
        # bridge does not send it a second time; the two must be the same event.
        early = self.forwarded.get(sub.request_id)
        if early is not None and _comparable(early) != _comparable(ev):
            self.n_forward_mismatch += 1
        self.cloud_answers.append(ev)

    def _cloud_answer(self, sub: Live2Submission, o, delivered: float, path,
                      scored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ontime = delivered <= o.deadline_abs() + 1e-9
        return SC.make(
            "cloud_answer", device_id=o.device_id, opportunity_id=o.opp_id,
            t_done=round(delivered, 6),
            payload=dict(request_id=sub.request_id, kind=o.kind, cache_path=path,
                         on_time=bool(ontime),
                         # D133/D134 Part A. The representation is now a CHARGED quantity, and
                         # anything that changes cost belongs in the record beside the cost or a
                         # later reader cannot reconstruct why two runs differ. Without these the
                         # artifacts cannot say which questions went as RECENT, and every
                         # analysis has to wrap `_submit_recall` to recover it. Both values are
                         # already in scope: `o` carries the request, `sub` carries what was
                         # actually charged.
                         representation=getattr(o, "requested_representation", None),
                         tokens_charged=int(sub.est_tokens),
                         cloud_score=(scored or {}).get("cloud_score"),
                         cloud_letter=(scored or {}).get("cloud_letter"),
                         p_yes=(scored or {}).get("p_yes")))

    def answer_on_completion(self, r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """StudyLIVE2-harness addendum: the cloud_answer for a finished response, built the
        moment its stream ends, on the I/O thread, without waiting for a tick or an epoch.

        It reads only the submission, the response and the opportunity's deadline (fixed when
        the opportunity was created), and builds the event with the same `_cloud_answer` the
        decision thread uses, so the event is identical to the one `_settle` will record (any
        difference is counted in `n_forward_mismatch`). It changes no coordinator state except
        `forwarded`; the arm still learns of the completion in `_collect`, at its next epoch.
        Build pieces carry no answer and return None.
        """
        sub = r.get("sub")
        if sub is None or sub.kind in ("piece", "whole") or not sub.opportunity_id:
            return None
        # D144: a non-200 response is a miss, never forwarded as a cloud answer (the decision thread's _settle records it)
        if r.get("http_status") is not None and int(r.get("http_status")) != 200:
            return None
        o = self.st.opps.get(sub.opportunity_id)
        if o is None:
            return None
        usage = r.get("usage") or {}
        path, _frac = SC.cache_path_of(cached_tokens_of(usage), prompt_tokens_of(usage))
        done_s = sub.sent_s + (r["total_s"] * self.speed if r.get("total_s") else 0.0)
        first_s = (sub.sent_s + r["ttft_s"] * self.speed) if r.get("ttft_s") else None
        delivered = first_s if first_s is not None else done_s
        ev = self._cloud_answer(sub, o, delivered, path, self._score_of(sub, r))
        early = self.forwarded.get(sub.request_id)
        if early is not None:
            # Already sent at its first content token (ruling Option 1): compare what the fleet
            # received with what the full response gives, and count the differences.
            pe, pf = early.get("payload") or {}, ev.get("payload") or {}
            if sub.kind == "recall":
                self.n_recall_first_token += 1
                if pe.get("cloud_letter") != pf.get("cloud_letter"):
                    self.n_recall_letter_differs += 1
                    self.recall_letter_diffs.append(dict(
                        request_id=sub.request_id, first_token=pe.get("cloud_letter"),
                        full_text=pf.get("cloud_letter")))
            elif pe.get("cloud_score") != pf.get("cloud_score"):
                self.n_monitor_score_differs += 1
            return None
        self.forwarded[sub.request_id] = ev
        return ev

    def answer_on_first(self, r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """StudyLIVE2-harness addendum, ruling Option 1: the cloud_answer at the FIRST CONTENT
        TOKEN. t_done is the existing first-token time (unchanged), the monitor score comes from
        the first token's logprobs and the recall letter from the text so far (the first token).
        `cache_path` is not known until the usage block at stream end, so the payload carries
        None; the scorer takes cache_path from request.jsonl. Returns None for build pieces."""
        # ---- D179 (1) SHARE ADMISSION, W DRAIN AT FIRST TOKEN. BEGIN block -------------------
        # The LIVE drain, and the one D179 (1) specifies. Idempotent, so the settle drain below
        # cannot double-subtract. Fires only when a real backend exists, which is why the settle
        # drain is not optional: in a DRY cell this hook is never called at all.
        if self._share_admission:
            _rid = r.get("request_id") or getattr(r.get("sub"), "request_id", None)
            if _rid:
                self._w.on_first_token(str(_rid))
        # ---- END D179 (1) block ---------------------------------------------------------------
        sub = r.get("sub")
        if sub is None or sub.kind in ("piece", "whole") or not sub.opportunity_id:
            return None
        o = self.st.opps.get(sub.opportunity_id)
        if o is None or r.get("ttft_s") is None:
            return None
        delivered = sub.sent_s + r["ttft_s"] * self.speed
        ev = self._cloud_answer(sub, o, delivered, None, self._score_of(sub, r))
        self.forwarded[sub.request_id] = ev
        return ev

    def _expire(self, t: float) -> None:
        # ---- D179 MEASUREMENT MIRROR, called from a per-period hook. BEGIN block --------------
        # The call used to sit inside `_share_ok`, which returns early when share admission is
        # off, so I had made the mirror's CONTENTS unconditional while leaving its CALL SITE
        # gated: the release re-check retest then reported every counter ABSENT, including
        # `submitted_*`, in a 14,968-row cell. It is called here because `_expire` runs every
        # period for every arm regardless of either switch.
        #
        # The fault was caught by a POSITIVE CONTROL ON THE MEASUREMENT CHANNEL, not by the
        # result: the retest printed `submitted_*` alongside the counters it was actually after,
        # and `submitted_monitor` cannot be zero in a cell with 14,968 decision rows. Without that
        # control the run would have read as an alert skip rate of 0.0000, which is a PASS against
        # the D179 50 percent bar, and the gate would have been cleared by a mirror that never ran.
        # A TIME fraction needs a PER-PERIOD sample. The counters above are incremented once per
        # ADMISSION GATE CALL, so 113 of 10,657 is a fraction of gate invocations, not of time,
        # and the two differ because gate calls cluster where traffic does. `_expire` runs once
        # per 100 ms period for every arm, so sampling here gives the quantity the user asked for.
        # Both are kept, under names that say which is which, rather than one being relabelled.
        if self._share_admission:
            self._wp_samples = getattr(self, "_wp_samples", 0) + 1
            if self._w.total() > SCAP_W_MAX:
                self._wp_over = getattr(self, "_wp_over", 0) + 1
                _pt = getattr(self, "_wp_over_types", None)
                if _pt is None:
                    _pt = self._wp_over_types = {}
                _pres = tuple(sorted(_x for _x in SA.TYPES if self._w.w(_x) > 0))
                _pk = "+".join(_pres) if _pres else "none"
                _pt[_pk] = _pt.get(_pk, 0) + 1
        self._mirror_d179_stats()
        # ---- END D179 block ------------------------------------------------------------------

        for oid in self.st.order:
            o = self.st.opps[oid]
            if o.state in ("arrived", "offered") and o.deadline_abs() < t - 1e-9:
                o.state = "late"
                self.answers.append(dict(opportunity_id=o.opp_id, kind=o.kind,
                                         device_id=o.device_id, decision="NOT-TAKEN",
                                         delivered_s=None, deadline_s=o.deadline_abs(),
                                         served_by="device", on_time=False))

    # ---------------------------------------------------------------- logging
    def _log_decision(self, t: float, kind: str, opp_ids: List[str], *, piece_tokens=None,
                      defer_s=None, latency_ms: float = 0.0, preds=None, mix=None,
                      key: Optional[str] = None, session_id: Optional[str] = None,
                      representation: Optional[str] = None,
                      representation_defaulted: bool = False,
                      desired_tier: Optional[str] = None) -> str:
        self.n_dec += 1
        did = f"d{self.n_dec}"
        preds = preds or {}
        pr = (preds.get("by_target") or {}).get(key) if key else None
        rec = SC.DecisionRecord(
            t=round(t, 6), arm=self.arm.name,
            arm_version=getattr(self.arm, "arm_version", "unversioned"), decision_id=did,
            kind=kind, opportunity_ids=list(opp_ids), piece_tokens=piece_tokens,
            predicted=(pr if pr else SC.asdict(SC.Predicted())),
            cost_model_id=preds.get("cost_model_id"), mu=preds.get("mu"), H=preds.get("H"),
            belief=(preds.get("belief") or SC.asdict(SC.Belief())),
            decision_latency_ms=round(float(latency_ms), 4),
            traffic_mix=dict(mix or {}), defer_s=defer_s,
            representation=representation, desired_tier=desired_tier,
            representation_defaulted=bool(representation_defaulted),
            note=(f"session={session_id}" if session_id else None))
        if self.logs is not None:
            self.logs.decision.write(rec)
        return did

    def _log_residency(self, t: float, session_id: str, telemetry=None) -> None:
        s = self.st.sessions.get(session_id)
        if s is None or self.logs is None:
            return
        self.logs.residency.write(SC.ResidencyRecord(
            t=round(t, 6), session_id=session_id, believed_tier=s.believed_tier(),
            telemetry_cached_tokens=telemetry, device_id=s.device_id,
            believed_dist=dict(s.belief)))

    # ---------------------------------------------------------------- result
    def _result(self, cpu0: float, wall_s: float) -> Dict[str, Any]:
        lat = sorted(self.decision_latencies_ms)
        def q(p):
            return round(lat[min(int(p * len(lat)), len(lat) - 1)], 4) if lat else None
        mon = [a for a in self.answers if a["kind"] == "monitor"]
        rec = [a for a in self.answers if a["kind"] == "recall"]
        return dict(
            arm=self.arm.name, arm_version=getattr(self.arm, "arm_version", "unversioned"),
            is_measurement=False,
            tick_s=self.tick_s, decision_period_s=self.decision_period_s, h_s=self.h_s,
            upload_mode=self.upload_mode,
            window_s=self.window_s, n_devices=len(self.st.devices),
            n_sessions=len(self.st.sessions), n_opportunities=len(self.st.opps),
            n_requests=self.n_req, n_decisions=self.n_dec,
            counts=dict(sorted(self.counts.items())),
            n_monitor_answers=len(mon), n_recall_answers=len(rec),
            n_on_time=sum(1 for a in self.answers if a.get("on_time")),
            submit_delay_ms=_pct(self.submit_delays_ms),
            decision_time=self.decision_time_summary(),
            n_pulls=len(self.pulls), n_cloud_answers=len(self.cloud_answers),
            decision_latency_ms=dict(p50=q(0.5), p99=q(0.99),
                                     max=(round(lat[-1], 4) if lat else None), n=len(lat)),
            cpu_s=round(_cpu_s() - cpu0, 3), wall_s=round(wall_s, 3),
            cpu_percent=(round(100.0 * (_cpu_s() - cpu0) / wall_s, 1) if wall_s > 0 else None),
            request_rate_per_s=(round(self.n_req / wall_s, 2) if wall_s > 0 else None),
            budget_gpu_s=round(self.st.budget.gpu_seconds, 2),
            budget_spent_gpu_s=round(self.st.budget.spent_gpu_seconds, 2),
            epoch_overruns=self.epoch_overruns,
            max_epoch_lag_s=round(self.max_epoch_lag_s, 4),
            wall_guard_hit=self.wall_guard_hit, wall_guard_s=self.max_wall_s,
            virtual_t_reached_s=round(self.t_reached, 3),
            n_errors=len(self.errors), first_errors=self.errors[:3],
            mu_time_average=(self.arm.mu_time_average()
                             if hasattr(self.arm, "mu_time_average") else None),
            arm_stats=_arm_stats(self.arm),
            # ---- D187 P0: SERIALISE THE TWO D179 EVENT LISTS. BEGIN block ---------------------
            # Both lists died with the process. That is why the recall-skip diagnosis had to
            # RECONSTRUCT every quantity the re-check used (predicted uncached, queued ahead,
            # estimated first token, remaining slack, readiness) from other logs, with a proxy
            # declared for each, and why `queued_uncached_ahead` could only be BOUNDED rather than
            # read. Step 3 of CLAUDE.md asks for a traced unit; a quantity that reaches no file
            # cannot be traced by anyone later. Capped so a long run cannot bloat the result file,
            # with the cap and the true count both recorded so a truncated list is never mistaken
            # for a short one.
            release_infeasible_events=list(self.release_infeasible_events[:20000]),
            release_infeasible_events_total=len(self.release_infeasible_events),
            share_events=list(self._share_events[:20000]),
            share_events_total=len(self._share_events),
            share_events_cap=20000,
            # ---- END D187 P0 block ------------------------------------------------------------
            dashcam_format=self.dashcam_format,
            epg=self._epg_summary(),
        )

    def _epg_summary(self) -> Optional[Dict[str, Any]]:
        """D153 proof (a) on this run's own requests: how many frames each monitoring request
        carried and how many of them went as uuid-only references, by episode index."""
        if not self.epg_requests:
            return None
        n = [r["n_frames"] for r in self.epg_requests]
        byidx: Dict[int, Dict[str, Any]] = {}
        for r in self.epg_requests:
            d = byidx.setdefault(int(r["episode_index"] or 0),
                                 dict(n=0, frames=0, as_reference=0))
            d["n"] += 1
            d["frames"] += r["n_frames"]
            d["as_reference"] += r["n_as_reference"]
        return dict(requests=len(n), frames_min=min(n), frames_max=max(n),
                    frames_median=sorted(n)[len(n) // 2],
                    frames_total=sum(n),
                    prompt_tokens_total=sum(r["prompt_tokens_expected"]
                                            for r in self.epg_requests),
                    episodes=len({r["episode_id"] for r in self.epg_requests}),
                    by_episode_index={k: byidx[k] for k in sorted(byidx)})


_EPOCHS = ("stream_arrival", "stream_departure", "recall_arrival", "request_completion",
           "connectivity_change", "tick")


def _pct(xs) -> Dict[str, Any]:
    v = sorted(xs)
    if not v:
        return dict(n=0)
    def g(p):
        return round(v[min(int(p * len(v)), len(v) - 1)], 4)
    return dict(n=len(v), p50=g(0.5), p90=g(0.9), p99=g(0.99), max=round(v[-1], 4))


def _comparable(ev: Dict[str, Any]) -> Dict[str, Any]:
    """A cloud_answer without the two fields Option 1 lets differ: cache_path (unknown at the
    first token) and the recall letter (counted separately)."""
    p = dict(ev.get("payload") or {})
    p.pop("cache_path", None)
    p.pop("cloud_letter", None)
    return dict(ev, payload=p)


def _sched(ev: Dict[str, Any]) -> float:
    for k in ("t_arrive", "t_capture", "start_t", "t", "t_ask"):
        if ev.get(k) is not None:
            return float(ev[k])
    return 0.0


def _cpu_s() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def _n_resent(frames: List[Dict[str, Any]], s) -> int:
    """D158 (2): image parts in this body that carry bytes a PREVIOUS request already sent.

    The declared price of the fix, counted the same way at both call sites. A part counts only if
    it actually carries bytes (`_path` resolved) AND the frame is in the submission-time set, so
    a frame the store cannot resolve is not miscounted as a re-send and neither is a frame whose
    bytes are going out for the first time.
    """
    return sum(1 for f in frames
               if f.get("path") is not None
               and f["frame_ref"] in s.sent_bytes_for
               and f["frame_ref"] not in s.confirmed_bytes_for)


class _DryFuture:
    """A completed-at-a-virtual-time stand-in for a thread-pool future (`--dry-run`)."""

    def __init__(self, sub: Live2Submission, service_s: float, t: float, clock) -> None:
        self.sub = sub
        self.service_s = float(service_s)
        self.t = float(t)
        self.clock = clock

    def done(self) -> bool:
        return self.clock() >= self.t + self.service_s - 1e-9

    def result(self) -> Dict[str, Any]:
        return dict(request_id=self.sub.request_id, kind=self.sub.kind, sent_s=self.sub.sent_s,
                    ttft_s=self.service_s, total_s=self.service_s, http_status=None,
                    error=None, usage={}, sub=self.sub, dry_run=True)
