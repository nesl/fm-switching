#!/usr/bin/env python3
"""D155 (5): give the KV-cache baselines the PROACTIVE mechanism their own card claims.

WHY THIS FILE EXISTS. `reports/policy_v5_assessment.md` section I records that six of the
KV-cache family publish a proactive mechanism and that none of them could express it, because
`interface.validate_action` accepts a MATERIALIZE only for a session that is already warm or
already has a pending question. A session that had uploaded frames and had no question yet was
rejected, stayed cold, and was therefore rejected for ever. Every committed comparison against
those six was a comparison against an adapter that could not do what its paper describes. The
user ruled that each should be given its published mechanism, per its card, now that warming
ahead is expressible.

STEP 0 FINDING, AND IT IS THE FIRST THING A READER NEEDS. **Warming ahead is still NOT
expressible at `origin/main`.** PATCH 1 of `reports/study_engine_actions.md` section 3.1 is not
applied: at `55ec283` there is no `Observation.live_sessions` field, `validate_action`'s
`known_sessions` is still the committed three-way union, and `cstate.CoordState.observation`
emits no live-session tuple. The only reference to the name anywhere in the tree is the tolerant
`getattr(obs, "live_sessions", ())` already inside `engine_actions.known_sessions`. So every
warm-ahead arm in this file self-censors on the committed harness and its characteristic
decision count is ZERO there. Under CLAUDE.md Rule 2 that zero is **unexpressible** and is NOT a
negative and NOT a finding about any baseline.

Every proof below is therefore run in BOTH conditions, exactly as `arms_warmall.proofs()` does
and reusing that module's own reviewed shim: the committed harness, and a harness with PATCH 1
emulated in process. The difference between the two columns is the measurement of the blocker
rather than an argument about it. The shimmed column is labelled `shimmed` and is NOT evidence
about the committed harness.

WHAT A CARD HAS TO SAY FOR A BASELINE TO GET A PROACTIVE MECHANISM. The card is the committed
record of the adaptation (`arms_published.py`: "the card is the committed record of the
adaptation and the arm's behaviour is the thing under test"), so the card decides. Giving a
baseline a capability its paper does not claim is as unfair as denying it one it does, in the
opposite direction, and it is the easier mistake to make here because the ruling asks for
mechanisms to be added. The per-card audit is in `reports/study_kv_prefetch.md`; its verdicts:

  attentionstore  YES. "fetch for the sessions the job scheduler will run next, NOT ON DEMAND AT
                  REQUEST TIME" (card, section 4.2 row), mapped FAITHFUL. Unambiguous.
  kvflow          YES. "fully overlapped prefetch -> `prefetch` + `exposed_prefetch_s`, FAITHFUL
                  in arithmetic", with a CAUSAL trigger the card already supplies.
  mooncake        NO. Its card quotes early rejection and a reuse-first ORDER, and claims no
                  prefetch. Measured besides: its reuse SIGNAL is constant. See
                  `mooncake_card_audit()` below, which is this file's mooncake deliverable.
  preble          NO on the card. Its reuse is placement and ordering; cross-GPU placement and
                  migration are NOT REPRODUCED (one replica).
  lmcache         NO on the card. "admission: every session that asks"; the card puts it in the
                  suite as "the LRU contrast", so prefetching would delete its role.
  pensieve        NO on the card. Its "ahead-of-time swapping" is a pipelined transfer
                  overlapping computation for work in hand, and its ADAPTATION A3 states that
                  predicting reuse "would be a new policy, not Pensieve's. FLAGGED."

NOTHING COMMITTED CHANGES. No committed adapter, arm or card is edited by this file. Each new
behaviour is a new labelled arm with its own name and its own `arm_version`, so committed cells
stay interpretable; they are relabelled `no-prefetch` and queued for rerun.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, HERE / "hybrid", REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/baselines/reconstructed",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib",
           REPO / "experiments/orchestration"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import engine_actions as EA                                              # noqa: E402
from attentionstore import DRAM, HBM, Session, scheduler_aware_fetch     # noqa: E402
from interface import Action, Observation                                # noqa: E402

KVPREFETCH_VERSION = "kv-prefetch-1.0"


class AttentionStorePrefetchArm:
    """AttentionStore with its card's SCHEDULER-AWARE FETCH read proactively. NEW LABELLED ARM.

    WHAT THE CARD CLAIMS, quoted from `baselines/cards/attentionstore.md`:

        | scheduler-aware fetching | 4.1, 4.2 | fetch for the sessions the **job scheduler** will
        | run next, not on demand at request time. |

    mapped `4.2 fetch -> scheduler_aware_fetch` and marked **FAITHFUL**. The reconstruction's own
    docstring repeats it in the same words: "the cache of a session about to be scheduled is
    fetched first, instead of fetching on demand at request time." The card's own summary of what
    survives adaptation names it first: "what the policy uses is scheduler-aware fetching and
    eviction, which is what the paper fundamentally decides."

    WHY THE COMMITTED ADAPTER DOES NOT DO THAT, and it is not the adapter's fault. The card's
    ADAPTATION A3 proxies "the scheduler's queue" with "our recall queue in deadline order", and
    `AttentionStoreAdapted.decide` builds that queue out of `obs.recall`, i.e. out of questions
    that have ALREADY ARRIVED. So the committed arm fetches exactly ON DEMAND AT REQUEST TIME,
    which is the one thing section 4.2 is defined against. A3 was the only reading available
    while warming ahead was unexpressible, and it is the baseline most disadvantaged by that.

    WHAT THIS ARM CHANGES, and nothing else. The queue handed to `scheduler_aware_fetch` is
    widened from "sessions with a pending question" to "sessions the scheduler holds", which in
    live2 is the open-session roster. `scheduler_aware_fetch` is the paper's own reconstructed
    function and is called UNCHANGED, with the card's own `gpu_warm_slots = 4`.

    THE ORDER OF THE WIDENED QUEUE IS THE NARROW READING, deliberately. Section 4.2 reads a queue
    the scheduler KNOWS; it does not predict who will ask next. Predicting that from observed
    inter-arrival history is KVFlow's mechanism (`cards/kvflow.md`, "steps-to-execution"), and
    handing it to AttentionStore would give this baseline a capability its paper does not claim.
    So the widened tail is ordered by the paper's OWN stated tie-break, "least-recently-used,
    which is the paper's fallback when the scheduler has no opinion" (`scheduler_aware_evict`,
    section 4.2), and by nothing else. Pending sessions keep their deadline order and come FIRST,
    so A3's committed reading is preserved as the head of the queue rather than replaced.

    ADAPTATION A5, NEW, AND STATED RATHER THAN SILENT. The prefetch yields to deadline work (W2,
    `engine_actions.deadline_work_at_risk`, D143 ruling B). That discipline is the harness's, not
    the paper's: section 4.1's fetch is asynchronous and layer-overlapped and preempts nothing,
    and live2 has no asynchronous prefill, so a background MATERIALIZE that did not yield would
    take a slot from a request already under a deadline. `attentionstore-prefetch-noyield` exists
    so the discipline is checkable rather than assumed, and is in no run plan.

    WHAT IT STILL DOES NOT DO. The layer-wise pre-loading and the disk tier (card A1) stay
    unexpressible and are not attempted. The fetch is whole-session, one MATERIALIZE with
    `slice_tokens=None`, because the card records that "the paper loads a whole prefix". It adds
    no eviction rule: `scheduler_aware_evict` is the committed adapter's and is untouched.
    """

    def __init__(self, name: str = "attentionstore-prefetch", prefetch_ahead: bool = True,
                 yield_to_deadline: bool = True, gpu_warm_slots: Optional[int] = None) -> None:
        from arms_published import AttentionStoreArm
        self._base = (AttentionStoreArm() if gpu_warm_slots is None
                      else AttentionStoreArm(gpu_warm_slots=int(gpu_warm_slots)))
        self.name = name
        self.prefetch_ahead = bool(prefetch_ahead)
        self.yield_to_deadline = bool(yield_to_deadline)
        self.arm_version = KVPREFETCH_VERSION
        self.live2_source = ("baselines/attentionstore_adapted.py::AttentionStoreAdapted AS "
                             "COMMITTED, plus live2/engine_actions.py::plan_warm_ahead driven by "
                             "reconstructed/attentionstore.py::scheduler_aware_fetch on the "
                             "WIDENED scheduler queue (card section 4.2)")
        self.stats: Dict[str, int] = {}
        self._roster: Dict[str, Any] = {}
        self._last_seen: Dict[str, float] = {}

    # ---- delegation, same shape as arms_warmall.WarmAllLruArm -------------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_base"], k)

    def __call__(self, obs: Observation) -> Action:
        return self._base.__class__.__call__(self, obs)

    def live2_configure(self, **kw: Any) -> None:
        self._base.live2_configure(**kw)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """The scheduler's own holdings, handed to the arm rather than guessed.

        `session_device` is the D100 roster's record that a session EXISTS and HAS UPLOADED,
        which is a causal fact known at arrival; nothing here reads the future. The committed
        `AttentionStoreAdapted` declares no `live2_roster` and receives nothing, so storing it
        here cannot change the base's decisions, which is what the `prefetch_ahead=False`
        byte-identity control checks.
        """
        self._roster = dict(roster or {})

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._base.live2_describe()) if hasattr(self._base, "live2_describe") else {}
        d.update(arm=self.name, arm_version=KVPREFETCH_VERSION,
                 kv_prefetch=dict(
                     card="baselines/cards/attentionstore.md",
                     card_claim=("scheduler-aware fetching, section 4.2: fetch for the sessions "
                                 "the job scheduler will run next, not on demand at request "
                                 "time (mapped FAITHFUL)"),
                     prefetch_ahead=self.prefetch_ahead,
                     discipline="W2" if self.yield_to_deadline else "none",
                     queue_tail_order="LRU, the paper's own tie-break; NO reuse predictor",
                     slice_tokens=None,
                     eviction_rule="the committed adapter's scheduler_aware_evict, untouched"),
                 source=self.live2_source)
        return d

    # ---- the one added channel --------------------------------------------------------------
    def _bump(self, k: str, n: int = 1) -> None:
        self.stats[k] = self.stats.get(k, 0) + int(n)

    def _held_sessions(self) -> List[str]:
        return sorted((self._roster or {}).get("session_device", {}).keys())

    def _scheduler_queue(self, obs: Observation) -> List[str]:
        """The queue section 4.2 reads: what the scheduler will run next.

        Head = the pending recalls in deadline order, which is ADAPTATION A3 exactly as
        committed. Tail = the sessions the scheduler holds and has no question for yet, ordered
        by the paper's own LRU tie-break. A session never yet seen sorts last, which is the
        honest position for "the scheduler has no opinion".
        """
        head = [q.session_id for q in sorted(obs.recall, key=lambda x: x.deadline_s)]
        pend = set(head)
        tail = sorted((s for s in self._held_sessions() if s not in pend),
                      key=lambda s: (-self._last_seen.get(s, -1.0), s))
        return head + tail

    def decide(self, obs: Observation) -> Action:
        act = self._base.decide(obs)
        for q in obs.recall:
            self._last_seen[q.session_id] = float(obs.now_s)
        if not self.prefetch_ahead:
            return act
        queue = self._scheduler_queue(obs)
        pend = {q.session_id for q in obs.recall}
        named = {a.session_id for a in act.sessions}
        # The Session table the paper's function reads. Tier is the arm's believed residency:
        # HBM for a GPU-warm session, DRAM otherwise, which is the two-tier reading of card A1.
        sess: Dict[str, Session] = {}
        for sid in obs.cloud.gpu_warm_sessions:
            sess[sid] = Session(sid, 1, HBM, last_access_s=self._last_seen.get(sid, 0.0))
        for sid in obs.cloud.host_warm_sessions:
            sess.setdefault(sid, Session(sid, 1, DRAM,
                                         last_access_s=self._last_seen.get(sid, 0.0)))
        for sid in queue:
            sess.setdefault(sid, Session(sid, 1, DRAM,
                                         last_access_s=self._last_seen.get(sid, 0.0)))
        promote = [s for s in scheduler_aware_fetch(queue, sess, self._base.gpu_warm_slots)
                   if s not in pend and s not in named]
        self._bump("queue_head", len(pend))
        self._bump("queue_tail", len(queue) - len(pend))
        self._bump("prefetch_wanted", len(promote))
        if not promote:
            return act
        # Routed through engine_actions so the count is a WARM-AHEAD count and can never be
        # summed with the reactive fetch the committed arm already makes: plan_warm_ahead drops
        # any session with a pending question by construction, and reports `unexpressible`
        # separately from `legal`, so a harness refusal is never read as a policy decision.
        plan = EA.plan_warm_ahead(obs, promote, slice_tokens=None,
                                  yield_to_deadline=self.yield_to_deadline,
                                  targets=getattr(self._base, "_targets", None))
        self._bump("prefetch_ahead_emitted", plan.n_warm_ahead)
        self._bump("prefetch_ahead_unexpressible", len(plan.unexpressible))
        if plan.yielded:
            self._bump("prefetch_yielded_epochs")
        if plan.actions:
            act.sessions = list(act.sessions) + list(plan.actions)
        return act


class KVFlowPrefetchArm:
    """KVFlow with its card's FULLY OVERLAPPED PREFETCH given something to prefetch. NEW ARM.

    WHAT THE CARD CLAIMS, quoted from `baselines/cards/kvflow.md`:

        | fully overlapped prefetch | `prefetch` + `exposed_prefetch_s` | FAITHFUL in arithmetic |

    and, from the paper's algorithm as the card states it, "a fine-grained eviction policy at the
    KV node level, allowing KVFlow to preserve entries likely to be reused, plus a fully
    overlapped KV prefetching mechanism". So prefetch is on the card, explicitly, and marked
    FAITHFUL. This is the second of the six, with attentionstore, whose card justifies a
    proactive mechanism.

    AND ITS TRIGGER IS ALREADY COMMITTED, which is what separates kvflow from the other four.
    KVFlow's own signal, steps-to-execution, is read off a known workflow graph and is forbidden
    here under fairness rule 5, and the card resolves that rather than dropping it: the adapted
    policy "ESTIMATES steps-to-execution from each session's OWN observed inter-arrival history -
    an exponentially-weighted mean gap, turned into expected seconds until the next arrival".
    `KVFlowAdapted._steps_to_execution` is that estimator and it is used UNCHANGED here. No new
    predictor is added, and the card's own warning travels with every number: "KVFlow's advantage
    over LRU comes from exact future knowledge; a causal estimate is strictly weaker, and any
    result must say so."

    WHY THE COMMITTED ADAPTER CANNOT PREFETCH, although it calls `prefetch` and emits
    `materialize`. Its node set is built from `obs.recall` plus the warm-session lists:

        tokens[q.session_id] ... for q in obs.recall
        for sid in list(obs.cloud.gpu_warm_sessions) + list(obs.cloud.host_warm_sessions)

    Measured on this fleet, both warm lists are EMPTY in every epoch, so the node set is exactly
    the pending questions and `prefetch` can only ever name a session that is already asking.
    That is reactive warming, which is the thing a prefetch is defined against. The emitted
    `materialize` was legal only because the session was pending, which is why this fault never
    raised and never showed up as an illegal action.

    WHAT THIS ARM CHANGES, and nothing else. The node set is widened to the sessions the cloud
    holds frames for. `evict` and `prefetch` are the paper's own reconstructed functions, called
    UNCHANGED with the committed `gpu_capacity_tokens`, `prefetch_horizon_s` and `slots=2`, and
    `_steps_to_execution` is the committed estimator. Only sessions the base did not already name
    and that have no pending question are added, through `plan_warm_ahead`, so the base's
    decisions are untouched and a reactive materialize can never be counted as a prefetch.

    WHAT TO EXPECT, STATED BEFORE THE RUN RATHER THAN AFTER IT (CLAUDE.md Step 0). The estimator
    returns `inf` for a session never seen twice, and `prefetch` selects on a finite horizon, so
    a fleet of single-ask sessions gives this lever nothing to fire on even with the channel
    open. On the audited cell 371 of 374 sessions ask exactly once. If the count is near zero the
    correct classification is **unexercised**, not a negative: the mechanism is reachable and no
    condition in the run reaches it. That prediction is recorded here so the result cannot be
    read as a discovery either way.

    WHAT IT STILL DOES NOT DO. Tree-structured shared prefixes are NOT REPRODUCED (our sessions
    share no prefix). KV-node granularity stays one node per session (card A2). The overlap
    arithmetic `exposed_prefetch_s` is a cost model and is not a policy decision; live2 has no
    asynchronous prefill, so the overlap the paper's name refers to does not exist here and the
    W2 yield stands in for it, recorded as the same ADAPTATION A5 as attentionstore's.
    """

    def __init__(self, name: str = "kvflow-prefetch", prefetch_ahead: bool = True,
                 yield_to_deadline: bool = True) -> None:
        from arms_published import KVFlowArm
        self._base = KVFlowArm()
        self.name = name
        self.prefetch_ahead = bool(prefetch_ahead)
        self.yield_to_deadline = bool(yield_to_deadline)
        self.arm_version = KVPREFETCH_VERSION
        self.live2_source = ("baselines/kvflow_adapted.py::KVFlowAdapted AS COMMITTED, plus "
                             "live2/engine_actions.py::plan_warm_ahead driven by "
                             "reconstructed/kvflow.py::evict and ::prefetch on the WIDENED node "
                             "set, with the committed _steps_to_execution estimator unchanged")
        self.stats: Dict[str, int] = {}
        self._roster: Dict[str, Any] = {}

    def __getattr__(self, k):
        return getattr(self.__dict__["_base"], k)

    def __call__(self, obs: Observation) -> Action:
        return self._base.__class__.__call__(self, obs)

    def live2_configure(self, **kw: Any) -> None:
        self._base.live2_configure(**kw)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """The cloud's own holdings. `KVFlowAdapted` declares no `live2_roster` and receives
        nothing, so storing it here cannot change the base's decisions, which is what the
        `prefetch_ahead=False` byte-identity control checks."""
        self._roster = dict(roster or {})

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._base.live2_describe()) if hasattr(self._base, "live2_describe") else {}
        d.update(arm=self.name, arm_version=KVPREFETCH_VERSION,
                 kv_prefetch=dict(
                     card="baselines/cards/kvflow.md",
                     card_claim=("fully overlapped prefetch -> `prefetch` + "
                                 "`exposed_prefetch_s`, FAITHFUL in arithmetic"),
                     prefetch_ahead=self.prefetch_ahead,
                     discipline="W2" if self.yield_to_deadline else "none",
                     trigger=("the committed _steps_to_execution estimator, an EW mean of this "
                              "session's own observed inter-arrival gaps; no new predictor"),
                     card_caveat=("KVFlow's advantage over LRU comes from exact future "
                                  "knowledge; the causal estimate is strictly weaker"),
                     slice_tokens=None),
                 source=self.live2_source)
        return d

    def _bump(self, k: str, n: int = 1) -> None:
        self.stats[k] = self.stats.get(k, 0) + int(n)

    def decide(self, obs: Observation) -> Action:
        act = self._base.decide(obs)
        if not self.prefetch_ahead:
            return act
        from kvflow import KVNode, evict, prefetch
        b = self._base
        pend = {q.session_id for q in obs.recall}
        named = {a.session_id for a in act.sessions}
        tokens: Dict[str, int] = {}
        for q in obs.recall:
            tokens[q.session_id] = max(tokens.get(q.session_id, 0), q.readiness_tokens)
        for sid in list(obs.cloud.gpu_warm_sessions) + list(obs.cloud.host_warm_sessions):
            tokens.setdefault(sid, 11000)
        # THE ONE WIDENING. 11000 is the committed adapter's own default node size for a session
        # whose token count the observation does not carry, reused rather than re-chosen.
        held = sorted((self._roster or {}).get("session_device", {}).keys())
        for sid in held:
            tokens.setdefault(sid, 11000)
        nodes = [KVNode(sid, tok, sid in obs.cloud.gpu_warm_sessions,
                        b._steps_to_execution(sid, obs.now_s))
                 for sid, tok in sorted(tokens.items())]
        after = evict(nodes, b.cap)
        pull = [nid for nid in prefetch(after, b.horizon_s, slots=2)
                if nid not in pend and nid not in named]
        self._bump("node_set_widened_by", len([s for s in held if s not in pend]))
        self._bump("prefetch_wanted", len(pull))
        self._bump("steps_finite",
                   len([n for n in nodes if n.node_id not in pend
                        and b._steps_to_execution(n.node_id, obs.now_s) != float("inf")]))
        if not pull:
            return act
        plan = EA.plan_warm_ahead(obs, pull, slice_tokens=None,
                                  yield_to_deadline=self.yield_to_deadline,
                                  targets=getattr(self._base, "_targets", None))
        self._bump("prefetch_ahead_emitted", plan.n_warm_ahead)
        self._bump("prefetch_ahead_unexpressible", len(plan.unexpressible))
        if plan.yielded:
            self._bump("prefetch_yielded_epochs")
        if plan.actions:
            act.sessions = list(act.sessions) + list(plan.actions)
        return act


KVPREFETCH_ARMS = {
    "kvflow-prefetch": lambda **kw: KVFlowPrefetchArm(name="kvflow-prefetch", **kw),
    "kvflow-prefetch-off": lambda **kw: KVFlowPrefetchArm(
        name="kvflow-prefetch-off", prefetch_ahead=False, **kw),
    "kvflow-prefetch-noyield": lambda **kw: KVFlowPrefetchArm(
        name="kvflow-prefetch-noyield", yield_to_deadline=False, **kw),
    "attentionstore-prefetch": lambda **kw: AttentionStorePrefetchArm(
        name="attentionstore-prefetch", **kw),
    # CLAUDE.md Step 4, the negative control: the same arm with the mechanism disabled. It must
    # collapse to the committed `attentionstore` BYTE-IDENTICALLY, which is a stronger statement
    # than "converges": if it does not, what the treatment measures is not the prefetch channel.
    "attentionstore-prefetch-off": lambda **kw: AttentionStorePrefetchArm(
        name="attentionstore-prefetch-off", prefetch_ahead=False, **kw),
    # The discipline ablation for ADAPTATION A5. Kept constructible so the W2 claim is checkable,
    # and deliberately absent from any run plan.
    "attentionstore-prefetch-noyield": lambda **kw: AttentionStorePrefetchArm(
        name="attentionstore-prefetch-noyield", yield_to_deadline=False, **kw),
}


def register() -> None:
    """Same contract as `hybrid.register()` and `arms_warmall.register()`: put the names in
    live2's registry so `arms.make_arm(name)` builds them with no edit to any committed file."""
    import arms as A
    A.ARMS.update(KVPREFETCH_ARMS)


# ---------------------------------------------------------------- the mooncake deliverable
def mooncake_card_audit(seed: int = 4, n: int = 16, run_s: float = 1200.0) -> Dict[str, Any]:
    """MOONCAKE WAS FIRST IN THE USER'S ORDER, AND ITS CARD DOES NOT CLAIM A PREFETCH.

    This function is mooncake's deliverable. It is an audit and not an arm, because the honest
    answer to "give mooncake its published proactive mechanism per its card" is that its card
    publishes none, and inventing one would be the unfairness the ruling warns against, running
    the other way.

    WHAT THE CARD ACTUALLY QUOTES, in full. `cards/mooncake.md` has exactly two mechanism claims:

      (a) "we developed a **prediction-based early rejection policy**", mapped to `REJECT` when
          the predicted TTFT exceeds the slack and the replica is overloaded. This is a
          per-request admission test at the moment the request arrives. It is reactive by
          definition and has nothing ahead of a question in it.
      (b) "its architecture maximises KVCache reuse across a disaggregated prefill/decode pool",
          mapped as "maximise KVCache reuse -> serve GPU-warm, then host-warm, then cold
          (`MOONCAKE-REUSE-FIRST` order)", marked "FAITHFUL **in effect**".

    Neither (a) nor (b) creates cache for a request that has not arrived. Mooncake reuses cache
    that previous turns left behind and schedules to maximise the hit; the card's "Not reproduced"
    section disposes of the rest ("the disaggregated architecture; the transfer engine and its
    storage tiers"), and the transfer engine is where any prefetch would live. So the correct
    ruling on `policy_v5_assessment.md` section I's "probably yes, needs a ruling" is **NO on the
    card**, and the section's reason, that cache-centric scheduling is "the closest published
    analogue to warm-ahead", is an analogy and not a claim the card makes.

    WHAT THIS AUDIT MEASURES INSTEAD, and it is a stronger result than a ruling. Section I's row
    for mooncake reads "reactive only; 0 gpu beliefs, 0 engine prefix hits in its committed
    cells", which describes the OUTCOME. The question Step 2 asks is whether mooncake's reuse
    mechanism is a live causal link at all, and the answer is that it is CONSTANT, which is a
    CLAUDE.md Step 2 stopping condition in its own right and is independent of the prefetch
    ruling:

      * `MooncakeAdapted.decide` sorts by `{"GPU-WARM": 0, "HOST-WARM": 1, "COLD": 2}[q.readiness]`
        and then by deadline. If every query is COLD the first key is the constant 2 and the sort
        degenerates to deadline order, which is EDF. That is `b7-edf-feasibility`'s order, and it
        explains the convergence the D130 port note measured at the level of the SIGNAL rather
        than at the level of the channel. The note had already established the channel half:
        `coordinator.py` never reads `Action.order`, so even a non-degenerate order could not
        reach a decision.
      * `warm = [q.session_id for q in order[:gpu_warm_slots]]` is drawn from `obs.recall` only,
        so mooncake's retention names nothing that does not already have a question pending.

    Both counts below are OBSERVED COUNTS from a DRY decision-path run with a stub bridge and no
    engine. They are counts of decisions and beliefs, never of seconds.
    """
    import collections
    import arms_warmall as WA
    import interface as I

    seen_q: set = set()
    asks: collections.Counter = collections.Counter()
    emitted: collections.Counter = collections.Counter()
    readiness: collections.Counter = collections.Counter()
    ready_by_nth: collections.Counter = collections.Counter()
    obs_gpu_max = [0]
    obs_host_max = [0]
    epochs = [0]

    orig = I.validate_action

    def patched(action, obs):
        epochs[0] += 1
        obs_gpu_max[0] = max(obs_gpu_max[0], len(obs.cloud.gpu_warm_sessions))
        obs_host_max[0] = max(obs_host_max[0], len(obs.cloud.host_warm_sessions))
        for q in obs.recall:
            if q.query_id not in seen_q:
                seen_q.add(q.query_id)
                asks[q.session_id] += 1
                readiness[q.readiness] += 1
                ready_by_nth[(asks[q.session_id], q.readiness)] += 1
        for s in action.sessions:
            emitted[s.action] += 1
        return orig(action, obs)

    I.validate_action = patched
    try:
        rows, _ = WA._dry("mooncake", seed, n, run_s)
    finally:
        I.validate_action = orig

    kinds = collections.Counter(str(r.get("kind")) for r in rows)
    distinct_readiness = len([k for k, v in readiness.items() if v > 0])
    return dict(
        version=KVPREFETCH_VERSION,
        baseline="mooncake",
        register=("OBSERVED COUNTS from a DRY decision-path run, stub bridge, no engine. Counts "
                  "of decisions and beliefs, never of seconds."),
        cell=dict(seed=seed, n_devices=n, run_s=run_s, ratio="40:40:20", dry=True,
                  robot_question_set="lh_req", ss_question_set="ss2"),
        card_ruling=dict(
            verdict="NO PROACTIVE MECHANISM ON THE CARD",
            card="baselines/cards/mooncake.md",
            claims_quoted=[
                "we developed a prediction-based early rejection policy",
                "its architecture maximises KVCache reuse across a disaggregated prefill/decode "
                "pool",
                "maximise KVCache reuse -> serve GPU-warm, then host-warm, then cold "
                "(MOONCAKE-REUSE-FIRST order) | FAITHFUL in effect"],
            not_reproduced_quoted=("The disaggregated architecture; the transfer engine and its "
                                   "storage tiers; the TBT SLO; the paper's throughput results."),
            reasoning=("Both quoted mechanisms are triggered BY a request. Neither creates cache "
                       "for a request that has not arrived. The transfer engine, which is where "
                       "any prefetch would live, is explicitly NOT REPRODUCED. Giving mooncake a "
                       "warm-ahead lever would hand it a capability its card does not claim."),
            revises=("reports/policy_v5_assessment.md section I, which recorded 'probably yes, "
                     "needs a ruling' on the grounds that cache-centric scheduling is 'the "
                     "closest published analogue to warm-ahead'. An analogy is not a claim.")),
        measured=dict(
            epochs=epochs[0],
            session_actions_emitted={k: int(v) for k, v in sorted(emitted.items())},
            recall_readiness_at_first_sight={k: int(v) for k, v in sorted(readiness.items())},
            distinct_readiness_values=distinct_readiness,
            readiness_by_nth_ask={"ask%d/%s" % (k[0], k[1]): int(v)
                                  for k, v in sorted(ready_by_nth.items())},
            ask_count_histogram={str(k): int(v)
                                 for k, v in sorted(collections.Counter(asks.values()).items())},
            distinct_sessions_asked=len(asks),
            max_gpu_warm_sessions_in_obs=obs_gpu_max[0],
            max_host_warm_sessions_in_obs=obs_host_max[0],
            decision_kinds={k: int(v) for k, v in sorted(kinds.items())}),
        step2_verdict=dict(
            causal_link="KVCache reuse -> MOONCAKE-REUSE-FIRST order -> which recall is served "
                        "first -> more reuse, lower TTFT, more on-time answers",
            implementing_quantity="RecallQuery.readiness, the first sort key of "
                                  "MooncakeAdapted.decide",
            varies_as_expected=(distinct_readiness > 1),
            classification=("CONSTANT: the sort key takes one value in every epoch, so the "
                            "reuse-first order is identical to deadline order and the mechanism "
                            "cannot affect any decision. A CLAUDE.md Step 2 stopping condition."
                            if distinct_readiness <= 1 else
                            "VARIES: the reuse signal takes more than one value, so the Step 2 "
                            "stopping condition does not apply and the channel half of the D130 "
                            "port note is the remaining blocker."),
            independent_of_prefetch_ruling=True,
            prior_channel_finding=("cards/mooncake.md D130 port note: coordinator.py never reads "
                                   "Action.order, so the reuse-first order cannot reach a "
                                   "decision in live2 even when the signal varies. This audit "
                                   "adds the SIGNAL half.")),
        no_arm_added=("No mooncake arm is registered by this file. Its committed cells are "
                      "unaffected and need no relabelling, because no proactive mechanism was "
                      "withheld from it."))


# ---------------------------------------------------------------- the four proofs
def proofs(arm: str = "attentionstore-prefetch", base: str = "attentionstore",
           control: str = "attentionstore-prefetch-off",
           seed: int = 4, n: int = 16, run_s: float = 1200.0) -> Dict[str, Any]:
    """The four proofs CLAUDE.md's citing rules require of a new arm, in order.

    Proof 3 is the one the other three cannot substitute for: "The required well-formedness and
    fairness checks establish that an arm is legal and fairly treated; neither establishes that
    it does anything." An arm that passes 1, 2 and 4 while making zero decisions of its own kind
    has proved nothing.

    Run in BOTH conditions. The committed harness column is the answer to "can this baseline
    express its published mechanism today"; the shimmed column is the answer to "is the mechanism
    present and does it reach a decision once the channel is open". Conflating them is how an
    unexpressible mechanism gets written up as a negative.
    """
    import hashlib
    import json
    import arms_warmall as WA
    import baseline_prescreen as BP
    import test_hybrid as TH
    register()

    # `test_hybrid.STRIP` removes "arm", "decision_latency_ms" and "decision_id" but NOT
    # `arm_version`, which the coordinator writes into every decision row, so a new arm differs
    # from its base in ALL rows on a LABEL. That is CLAUDE.md check 3's artefact spread: a
    # full-log difference that cannot mean what the column says. The identity claim is made on
    # the decisions, with the label stripped, and the unstripped comparison is reported beside it.
    IGNORE = ("arm_version",)

    def _strip(rows):
        return [{k: v for k, v in r.items() if k not in IGNORE} for r in rows]

    def digest(rows):
        return hashlib.sha256(json.dumps(_strip(rows), sort_keys=True, separators=(",", ":"),
                                         default=float).encode()).hexdigest()[:16]

    def pieces(rows):
        return sum(1 for r in rows if str(r.get("kind")) in ("release_piece", "release_whole"))

    out: Dict[str, Any] = dict(
        version=KVPREFETCH_VERSION, arm=arm, base=base, control=control,
        register=("DRY decision-path runs, stub bridge, no engine. Every number below is a COUNT "
                  "OF DECISIONS, never of seconds, and nothing here is a measured latency, "
                  "quality or capacity result."),
        cell=dict(seed=seed, n_devices=n, run_s=run_s, ratio="40:40:20", dry=True,
                  robot_question_set="lh_req", ss_question_set="ss2"))

    # Unshimmed first, deliberately: `arms_warmall._shim_validate` installs a process-wide
    # monkeypatch, and although it is a no-op with an empty shim set, running the committed
    # conditions before it is installed keeps that claim from needing to be trusted.
    b_rows, b_st = WA._dry(base, seed, n, run_s)
    c_rows, c_st = WA._dry(control, seed, n, run_s)
    t_rows, t_st = WA._dry(arm, seed, n, run_s)
    s_rows, s_st = WA._dry(arm, seed, n, run_s, shim=True)
    b_st, c_st, t_st, s_st = (dict(x or {}) for x in (b_st, c_st, t_st, s_st))

    # CONSISTENCY CHECK 7 / THE POSITIVE CONTROL, first, because nothing below may be read if it
    # fails. The BASE arm must reproduce its own committed behaviour in this harness. A broken
    # control passes every check applied to the treatment, because the treatment is fine.
    b_census = BP.census(b_rows)
    out["check7_positive_control"] = dict(
        quantity="committed `%s` decision-kind census at this cell" % base,
        base_decisions=len(b_rows), base_census=b_census,
        base_state_actions=int(b_census.get("state_action", 0) or 0),
        why=("the base is the committed arm this treatment is measured against; if its own "
             "numbers are not its own, the comparison is unreadable and the check is broken "
             "rather than the arm"))

    # 1. WELL-FORMEDNESS. `validate_action` runs on every epoch inside `Policy.__call__`, so an
    # illegal action raises and the dry run dies. Completing the cell with a non-empty log IS the
    # zero-illegal-actions proof; the count makes that explicit rather than implied.
    out["proof1_well_formedness"] = dict(
        completed=True, illegal_actions=0,
        decisions_committed=len(t_rows), decisions_shimmed=len(s_rows),
        decisions_base=len(b_rows), decisions_control=len(c_rows),
        note=("validate_action runs on every epoch inside Policy.__call__; a cell that completes "
              "emitted no action outside the registered domain"))

    # 2. FAIRNESS DIGEST against the arm's OWN committed version, plus the byte-identity control.
    out["proof2_fairness_digest"] = dict(
        base=base, base_digest=digest(b_rows), base_decisions=len(b_rows),
        control_arm=control, control_digest=digest(c_rows),
        control_identical_to_base=(_strip(c_rows) == _strip(b_rows)),
        control_identical_including_arm_version=(c_rows == b_rows),
        treatment_digest=digest(t_rows), treatment_digest_shimmed=digest(s_rows),
        _register=("identity is asserted on the decision rows with `arm_version` removed, "
                   "because the coordinator writes that label into every row and a new arm "
                   "necessarily carries a new one. The unstripped comparison is reported beside "
                   "it so the label difference is visible rather than hidden."),
        note=("the control shares the base's digest, so the arm adds nothing outside its one "
              "channel; a treatment digest equal to the base's would be an ABSENT LINK"))

    # 3. CHARACTERISTIC DECISION: a scheduler-aware FETCH AHEAD of a question, actually issued.
    #
    # REGISTER, and getting it wrong would put a five-figure number in a column that cannot carry
    # it. `prefetch_ahead_emitted` counts MATERIALIZE actions EMITTED, once per promoted session
    # per epoch, and a standing request for a session with nothing newly uploaded is a NO-OP
    # inside `coordinator._advance_build` (`new_refs` empty -> None). The arm's asks are not a
    # decision count. The headline is read off the coordinator's own decision log.
    n_t, n_s, n_b, n_c = (pieces(t_rows), pieces(s_rows), pieces(b_rows), pieces(c_rows))
    out["proof3_characteristic_decision"] = dict(
        characteristic=("prefetch_ahead: a MATERIALIZE for a session the cloud holds frames for "
                        "and that has NO pending question. Every committed emitter of "
                        "MATERIALIZE names `q.session_id`, so this decision kind does not exist "
                        "in any committed cell of %s." % base),
        _register=("prefills_issued is an OBSERVED COUNT of release_piece / release_whole rows "
                   "in the coordinator's own decision log. prefetch_* below are the arm's ASKS, "
                   "one per promoted session per epoch, most of which no-op; they are not a "
                   "decision count and must not be reported as one."),
        prefills_issued_committed=n_t, prefills_issued_shimmed=n_s,
        prefills_issued_base=n_b, prefills_issued_control=n_c,
        arm_asks_committed={k: int(v) for k, v in sorted(t_st.items())},
        arm_asks_shimmed={k: int(v) for k, v in sorted(s_st.items())})
    out["proof3_characteristic_decision"]["verdict"] = (
        "PASS: %d prefetch-ahead prefills issued where the committed base issues %d"
        % (n_t, n_b) if n_t > n_b else
        ("UNEXPRESSIBLE on the committed harness: the arm wanted %d fetches and was refused %d "
         "times by validate_action, and issued %d prefills against the base's %d. With PATCH 1 "
         "shimmed in it issues %d. The mechanism is present and reaches a decision; the channel "
         "it acts through is what is missing. CLAUDE.md Rule 2 'unexpressible', NOT a negative "
         "and NOT a finding about this published system."
         % (int(t_st.get("prefetch_wanted", 0)),
            int(t_st.get("prefetch_ahead_unexpressible", 0)), n_t, n_b, n_s)))

    # 4. STEP 2b: does the switch reach a decision? SETWISE, because a reordering is not a
    # decision (`test_hybrid._differing_setwise`'s own docstring: its only non-zero cell on the
    # value-term control was two release_recall rows swapping places with both released either
    # way).
    first = next((i for i, (x, y) in enumerate(zip(b_rows, t_rows)) if x != y), None)
    first_s = next((i for i, (x, y) in enumerate(zip(b_rows, s_rows)) if x != y), None)
    out["proof4_step2b_decision_diff"] = dict(
        vs=base,
        differing_setwise=TH._differing_setwise(b_rows, t_rows),
        differing_positional=TH._differing(b_rows, t_rows),
        first_differing_index=first,
        first_differing_row=(t_rows[first] if first is not None else None),
        differing_setwise_shimmed=TH._differing_setwise(b_rows, s_rows),
        differing_positional_shimmed=TH._differing(b_rows, s_rows),
        first_differing_index_shimmed=first_s,
        first_differing_row_shimmed=(s_rows[first_s] if first_s is not None else None))
    out["proof4_step2b_decision_diff"]["verdict"] = (
        "PASS" if TH._differing_setwise(b_rows, t_rows) > 0 else
        "ABSENT LINK on the committed harness; shimmed diff is %d"
        % TH._differing_setwise(b_rows, s_rows))

    out["summary"] = dict(
        all_four_pass_committed=bool(
            out["proof2_fairness_digest"]["control_identical_to_base"]
            and n_t > n_b and TH._differing_setwise(b_rows, t_rows) > 0),
        all_four_pass_shimmed=bool(
            out["proof2_fairness_digest"]["control_identical_to_base"]
            and n_s > n_b and TH._differing_setwise(b_rows, s_rows) > 0),
        blocking=("none" if n_t > n_b else
                  "PATCH 1 of reports/study_engine_actions.md section 3.1 "
                  "(Observation.live_sessions and validate_action's known_sessions) is NOT "
                  "applied at origin/main 55ec283, and interface.py and cstate.py are outside "
                  "this session's file ownership"),
        scoreable_today=bool(n_t > n_b))
    return out


def main(argv=None) -> int:
    import json
    argv = list(sys.argv[1:] if argv is None else argv)
    what = argv[0] if argv else "all"
    outdir = REPO / "results/orchestration/live2/kv_prefetch"
    outdir.mkdir(parents=True, exist_ok=True)
    jobs = []
    if what in ("all", "mooncake"):
        jobs.append(("mooncake_card_audit.json", mooncake_card_audit))
    if what in ("all", "attentionstore"):
        jobs.append(("attentionstore_prefetch_proofs.json", proofs))
    if what in ("all", "kvflow"):
        jobs.append(("kvflow_prefetch_proofs.json",
                     lambda: proofs(arm="kvflow-prefetch", base="kvflow",
                                    control="kvflow-prefetch-off")))
    for fname, fn in jobs:
        res = fn()
        try:
            import _provenance
            res["_provenance"] = _provenance.stamp(script="arms_kvprefetch.py",
                                                   model="none-dry",
                                                   device="nvidia_rtx_a6000", n=16)
        except Exception as e:                                                   # noqa: BLE001
            res["_provenance"] = {"git_commit": "unstamped", "script": "arms_kvprefetch.py",
                                 "note": "stamp failed: %r" % (e,)}
        (outdir / fname).write_text(json.dumps(res, indent=2, default=float))
        print(json.dumps({k: v for k, v in res.items() if k != "_provenance"}, indent=2,
                         default=float))
        print("wrote", outdir / fname)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
