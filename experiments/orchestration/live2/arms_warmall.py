#!/usr/bin/env python3
"""WARM-ALL + LRU: the warm-regime baseline and calibration instrument (spec v5 section 15, G10).

WHY THIS ARM EXISTS, and it is not primarily as a baseline. The D151 (6) cost-model gate cannot
pass on committed data: of 304,867 committed requests only 720 are warm, all of them in two
cells at one seed, so every held-out split contains ZERO warm requests and the warm branch of
the cost model is fitted on nothing (gap G10). `study_frozen_test.md` 16.1 measures the
consequence from the other side: f was fitted on arms whose every request is cold, and on the
warm side the model is out by 1.5x on builds and 3.7x on warm single-shot. WARM-ALL is the only
arm that produces warm requests in quantity, so it is a CALIBRATION INSTRUMENT first and a
baseline second, and it must run before the gate.

WHAT IT IS. The live counterpart of P1 in `study_frozen_test.md` 15.1 and 16.2: prefill every
uploaded batch on arrival, let the harness and the engine evict by their own LRU, and do no
value reasoning at all.

  * BASE: `b7-edf-feasibility`, the committed control, unchanged. Every request decision, every
    feasibility decline and every representation is b7's. WARM-ALL adds ONE channel and nothing
    else, which is what makes the Step 2b diff against b7 readable as the warming channel.
  * ADDED: `engine_actions.plan_warm_ahead`, prefill-only, small pieces, lowest priority,
    yielding to deadline work.
  * NOT ADDED, deliberately: no KEEP_GPU_WARM, no OFFLOAD_TO_HOST, no EVICT, no reload, no
    hold-back, no slicing of a deadline request. "Let vLLM evict by its own LRU" means the arm
    emits no placement steering, so `desired_tier` stays at its default for every session and
    the eviction order `cstate.enact_placement` applies is least-recently-touched, which IS
    LRU. An arm that also steered placement would not be the P1 of sections 15 and 16.

W1 IS NOT BUILT. `study_frozen_test.md` 16.3 point 5: W1's worst single-shot queue wait is
3.746 s against a 2 s deadline, longer than the deadline itself, and the calibration that
produced it understates warm and build service, so a real engine would be worse. W2 is the only
discipline here and `--w1` does not exist.

THE BLOCKER THIS ARM RAN INTO, stated here because the arm's characteristic decision count is
ZERO without it and a zero must never be read as a policy result. `interface.validate_action`
accepts a MATERIALIZE only for a session that is already believed warm or already has a pending
question, so the FIRST warm-ahead prefill of every session is rejected and the session is then
still cold, so it is rejected for ever. Warming ahead is therefore UNEXPRESSIBLE in the
committed action space (CLAUDE.md Rule 2's second bullet: the mechanism fires but the harness
discards the channel it acts through). `engine_actions.plan_warm_ahead` counts both halves, and
`proofs()` runs BOTH conditions so the difference between them is the measurement of the
blocker rather than an argument about it. The one-line widening that removes it is specified in
`reports/study_engine_actions.md` and is owned by the coordinator's owner.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib",
           REPO / "experiments/orchestration"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import engine_actions as EA                                            # noqa: E402
from interface import Action, Observation                              # noqa: E402

WARMALL_VERSION = "warm-all-1.0"

# The shim set the proofs use to emulate the proposed widening of `validate_action`'s known
# sessions. It is EMPTY in every normal run and nothing but `proofs()` ever fills it: an arm
# whose legality depended on a module global would be exactly the plumbing fault CLAUDE.md
# Step 2b exists to catch, so the arm reads it through `Observation.live_sessions` (absent
# today, hence the shim) and never through this name.
_SHIM_LIVE_SESSIONS: set = set()


class WarmAllLruArm:
    """b7 plus one channel. Every live2 hook is delegated to the committed b7 wrapper."""

    def __init__(self, name: str = "warm-all-lru", warm_ahead: bool = True,
                 yield_to_deadline: bool = True,
                 slice_tokens: Optional[int] = EA.WARM_AHEAD_SLICE_TOKENS,
                 reactive: bool = False) -> None:
        from arms_published import B7EdfFeasibilityArm
        self._b7 = B7EdfFeasibilityArm()
        self.name = name
        self.warm_ahead = bool(warm_ahead)
        self.yield_to_deadline = bool(yield_to_deadline)
        self.slice_tokens = None if slice_tokens is None else int(slice_tokens)
        # The legal fallback. NOT warming ahead; see engine_actions.plan_warm_reactive.
        self.reactive = bool(reactive)
        self.arm_version = WARMALL_VERSION
        self.live2_source = ("baselines/constructed.py::B7EDFFeasibility AS COMMITTED, plus "
                             "live2/engine_actions.py::plan_warm_ahead (W2 discipline)")
        self.stats: Counter = Counter()
        self._roster: Dict[str, Any] = {}

    # ---- delegation, identical in shape to hybrid/hybrid_arm.py ----------------------------
    def __getattr__(self, k):
        return getattr(self.__dict__["_b7"], k)

    def __call__(self, obs: Observation) -> Action:
        return self._b7.__class__.__call__(self, obs)

    def live2_roster(self, roster: Dict[str, Any]) -> None:
        """b7 declares no `live2_roster` and receives nothing, so storing it here cannot change
        the base's decisions. That is what the warm_ahead=False identity proof checks."""
        self._roster = dict(roster or {})

    def live2_configure(self, **kw: Any) -> None:
        self._b7.live2_configure(**kw)

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(self._b7.live2_describe()) if hasattr(self._b7, "live2_describe") else {}
        d.update(arm=self.name, arm_version=WARMALL_VERSION,
                 warm_all=dict(warm_ahead=self.warm_ahead, reactive=self.reactive,
                               discipline="W2" if self.yield_to_deadline else "none",
                               slice_tokens=self.slice_tokens,
                               placement_steering=False),
                 source=self.live2_source)
        return d

    # ---- the one added channel --------------------------------------------------------------
    def _candidates(self, obs: Observation) -> List[str]:
        """Every session the cloud holds frames for. The D100 roster's `session_device` is the
        causal fact "this session exists and has uploaded"; nothing here reads the future.

        The arm does NOT try to work out which sessions have unbuilt frames. It cannot: the
        roster carries `built_tokens_by_session` but no history size, so there is no local test
        for "fully built". It does not need one. `coordinator._advance_build` clamps the target
        to `est_tokens` and returns None when `new_refs` is empty, so a standing request for
        every session is a no-op for every session with nothing newly uploaded, and the GPU is
        charged only for pieces actually issued. Asking every epoch IS "prefill every uploaded
        batch on arrival", expressed without a batch-arrival detector the arm could get wrong.
        """
        return sorted((self._roster or {}).get("session_device", {}).keys())

    def _count_release_states(self, obs: Observation, act: Action) -> None:
        """BOTH STATES UNDER ONE POLICY, which is what this arm exists to provide.

        The cost-model gate does not fail only because warm requests are scarce. They are
        CONFOUNDED WITH ARM: edf n16 s4 carries 358 gpu beliefs and 512,992 engine prefix hits
        and llf 362 and 424,224, while b7 and hybrid-F-lhreq carry zero of both. Arms that
        rebuild histories go warm and arms that do not never do, so the warm coefficient is
        fitted entirely on edf and llf and applied to arms that never go warm, and a by-arm
        held-out split therefore has zero warm rows BY CONSTRUCTION. More cells of the existing
        arms cannot fix that; only an arm that goes warm AND cold under the SAME policy can,
        because that is what identifies the warm regime out of arm.

        So the arm's proof is not one count. It is the pair: the warm-ahead prefills it makes,
        and the readiness its own released recalls were at. A WARM-ALL that released everything
        warm would be as useless to the gate as b7, which releases everything cold.

        Readiness is the arm's BELIEF at release time (`RecallQuery.readiness`), which is the
        only residency signal available in a dry run: `cached_tokens` needs an engine. The live
        cell must report the engine's own `cache_path` split beside this, and the two are
        different quantities and must not be substituted for each other.
        """
        ready = {q.query_id: q.readiness for q in obs.recall}
        for r in act.recall:
            if r.decision != "CLOUD":
                continue
            self.stats["release_at_" + str(ready.get(r.query_id, "UNKNOWN"))] += 1

    def decide(self, obs: Observation) -> Action:
        act = self._b7.decide(obs)
        self._count_release_states(obs, act)
        if not self.warm_ahead:
            return act
        if self.reactive:
            plan = EA.plan_warm_reactive(obs, slice_tokens=self.slice_tokens,
                                         yield_to_deadline=self.yield_to_deadline,
                                         targets=getattr(self._b7, "_targets", None))
            key = "warm_reactive"
        else:
            plan = EA.plan_warm_ahead(obs, self._candidates(obs),
                                      slice_tokens=self.slice_tokens,
                                      yield_to_deadline=self.yield_to_deadline,
                                      targets=getattr(self._b7, "_targets", None))
            key = "warm_ahead"
        self.stats[key + "_wanted"] += len(plan.wanted)
        self.stats[key + "_emitted"] += plan.n_warm_ahead
        self.stats[key + "_unexpressible"] += len(plan.unexpressible)
        if plan.yielded:
            self.stats[key + "_yielded_epochs"] += 1
        if plan.actions:
            act.sessions = list(act.sessions) + list(plan.actions)
        return act


WARMALL_ARMS = {
    "warm-all-lru": lambda **kw: WarmAllLruArm(name="warm-all-lru", **kw),
    # CLAUDE.md Step 4, the negative control: the same arm with the mechanism disabled. It must
    # collapse to b7 BYTE-IDENTICALLY, which is a stronger statement than "converges": if it does
    # not, the difference measured for warm-all-lru is not the warming channel.
    "warm-all-lru-off": lambda **kw: WarmAllLruArm(name="warm-all-lru-off", warm_ahead=False,
                                                   **kw),
    # The discipline ablation. NOT W1: it still plans at the same trigger, it simply does not
    # yield. Kept constructible so the W2 claim is checkable, and deliberately absent from any
    # run plan, as 16.3 point 5 requires.
    "warm-all-lru-noyield": lambda **kw: WarmAllLruArm(name="warm-all-lru-noyield",
                                                       yield_to_deadline=False, **kw),
    # THE LEGAL FALLBACK, runnable on the committed harness with no patch. It warms REACTIVELY,
    # at the question, so it cannot show that warming helps on-time and is not offered for that.
    # It exists because a sliced build reuses its own prefix on the wire, so it produces warm AND
    # cold ENGINE rows under one policy, which is what the cost-model gate needs and what no
    # committed arm provides. Its characteristic decision has a DIFFERENT NAME,
    # `warm_reactive_emitted`, so it can never be counted as a warm-ahead prefill.
    "warm-all-lru-reactive": lambda **kw: WarmAllLruArm(name="warm-all-lru-reactive",
                                                        reactive=True, **kw),
}


def register() -> None:
    """Same contract as `hybrid.register()`: put the names in live2's registry so
    `arms.make_arm(name)` builds them without any change to a file this session does not own."""
    import arms as A
    A.ARMS.update(WARMALL_ARMS)


# ---------------------------------------------------------------- the four proofs
def _shim_validate():
    """Emulate the proposed widening of `validate_action`'s known-session set, for the proof
    only. It is exactly the change requested in `reports/study_engine_actions.md`: a session the
    coordinator already holds frames for is a causally known entity and may be named.

    This is a SHIM IN THE PROOF HARNESS, not an edit to any file. The patched condition below is
    therefore labelled `shimmed`, and it is not evidence about the committed harness.

    It has TWO halves because the real patch does: the observation must CARRY the live sessions,
    so that `engine_actions.known_sessions` (which already reads `obs.live_sessions`) can see
    them, and `validate_action` must ACCEPT them. Shimming only the validator leaves the arm
    self-censoring and produces a zero indistinguishable from the blocker the shim exists to
    remove, which is how this shim failed on its first run.
    """
    import interface as I
    if getattr(I, "_warmall_shimmed", False):
        return
    _ea_known = EA.known_sessions
    EA.known_sessions = lambda obs: _ea_known(obs) | set(_SHIM_LIVE_SESSIONS)
    orig = I.validate_action

    def patched(action, obs):
        extra = set(_SHIM_LIVE_SESSIONS)
        if not extra:
            return orig(action, obs)
        keep = [x for x in action.sessions if x.session_id in extra]
        action.sessions = [x for x in action.sessions if x.session_id not in extra]
        out = orig(action, obs)
        out.sessions = list(out.sessions) + keep
        return out
    I.validate_action = patched
    I._warmall_shimmed = True


def _dry(arm_name, seed=4, n=16, run_s=1200.0, ratio="40:40:20", shim=False):
    sys.path.insert(0, str(HERE / "hybrid"))
    import test_hybrid as TH
    global _SHIM_LIVE_SESSIONS
    _SHIM_LIVE_SESSIONS = set()
    if shim:
        _shim_validate()

        def patch(arm):
            inner = arm.live2_roster

            def wrapped(roster):
                inner(roster)
                _SHIM_LIVE_SESSIONS.update((roster or {}).get("session_device", {}).keys())
            arm.live2_roster = wrapped
        rows, st = TH.dry(arm_name, seed, n, run_s=run_s, ratio=ratio, patch=patch,
                          robot_question_set="lh_req", ss_question_set="ss2")
    else:
        rows, st = TH.dry(arm_name, seed, n, run_s=run_s, ratio=ratio,
                          robot_question_set="lh_req", ss_question_set="ss2")
    _SHIM_LIVE_SESSIONS = set()
    return rows, dict(st or {})


def proofs(seed=4, n=16, run_s=1200.0) -> Dict[str, Any]:
    """The four proofs CLAUDE.md's citing rules require of a new arm, in order.

    Proof 3 is the one that matters here and is the one the other three cannot substitute for:
    an arm that passes well-formedness and fairness while making ZERO decisions of its own kind
    has proved nothing.
    """
    import hashlib
    import json
    sys.path.insert(0, str(HERE / "hybrid"))
    import test_hybrid as TH
    register()

    # `test_hybrid.STRIP` removes "arm", "decision_latency_ms" and "decision_id" but NOT
    # `arm_version`, which the coordinator writes into every decision row. A new arm declaring
    # its own version therefore differs from its base in ALL rows on a label, which made the
    # first run of this proof report `control_identical_to_base: false` with a positional diff of
    # 13,570 of 13,570 and a SETWISE diff of 0. That is CLAUDE.md check 3's artefact spread: a
    # full-log difference that cannot mean what the column says. The digest strips the label so
    # the identity claim is about decisions.
    IGNORE = ("arm_version",)

    def _strip(rows):
        return [{k: v for k, v in r.items() if k not in IGNORE} for r in rows]

    def digest(rows):
        return hashlib.sha256(json.dumps(_strip(rows), sort_keys=True, separators=(",", ":"),
                                         default=float).encode()).hexdigest()[:16]

    out: Dict[str, Any] = dict(version=WARMALL_VERSION,
                               cell=dict(seed=seed, n_devices=n, run_s=run_s,
                                         ratio="40:40:20", dry=True,
                                         robot_question_set="lh_req", ss_question_set="ss2"))

    base, base_st = _dry("b7-edf-feasibility", seed, n, run_s)
    off, off_st = _dry("warm-all-lru-off", seed, n, run_s)
    wa, wa_st = _dry("warm-all-lru", seed, n, run_s)
    wa_s, wa_s_st = _dry("warm-all-lru", seed, n, run_s, shim=True)

    # 1. WELL-FORMEDNESS. Every action passes `validate_action` inside `Policy.__call__`, so an
    # illegal action raises and the dry run dies. Completing the cell with a non-empty log IS the
    # zero-illegal-actions proof, and the count below makes that explicit rather than implied.
    out["proof1_well_formedness"] = dict(
        completed=True, decisions=len(wa), illegal_actions=0,
        decisions_shimmed=len(wa_s),
        note=("validate_action runs on every epoch inside Policy.__call__; a cell that completes "
              "emitted no action outside the registered domain"))

    # 2. FAIRNESS DIGEST against the base, plus the POSITIVE CONTROL CLAUDE.md check 7 requires:
    # the control arm must reproduce ITS OWN behaviour in this harness, or the check is broken
    # rather than the arm. `warm-all-lru-off` byte-identical to b7 is that control.
    # CONSISTENCY CHECK 1 and the POSITIVE CONTROL in one number. `study_frozen_test.md` 13.4
    # records b7's characteristic decision count at THIS cell (seed 4, 16 devices, 1200 s,
    # 40:40:20, lh_req / ss2) as 5 feasibility actions. If this harness does not reproduce that,
    # the check is broken and not the arm, and nothing below may be read.
    import baseline_prescreen as BP
    base_census = BP.census(base)
    out["check1_positive_control"] = dict(
        quantity="b7-edf-feasibility feasibility_actions (decline + defer) at this cell",
        this_run=int(base_census["feasibility_actions"]),
        prior_run=5, source_of_prior="reports/study_frozen_test.md section 13.4",
        agree=(int(base_census["feasibility_actions"]) == 5),
        base_decisions_this_run=len(base), base_census=base_census)

    out["proof2_fairness_digest"] = dict(
        base="b7-edf-feasibility", base_digest=digest(base), base_decisions=len(base),
        control_arm="warm-all-lru-off", control_digest=digest(off),
        control_identical_to_base=(_strip(off) == _strip(base)),
        control_identical_including_arm_version=(off == base),
        _register=("identity is asserted on the decision rows with `arm_version` removed, "
                   "because the coordinator writes that label into every row and a new arm "
                   "necessarily carries a new one. The unstripped comparison is reported beside "
                   "it so the label difference is visible rather than hidden."),
        treatment_digest=digest(wa), treatment_digest_shimmed=digest(wa_s),
        note=("the control shares the base's digest, so the arm adds nothing outside its one "
              "channel; a treatment digest equal to the base's would be an ABSENT LINK"))

    # 3. CHARACTERISTIC DECISION: a warm-ahead prefill ACTUALLY ISSUED.
    #
    # REGISTER, and getting this wrong would have put a four-figure number in a column that
    # cannot carry it. The arm's `warm_ahead_emitted` counts MATERIALIZE actions emitted, once
    # per candidate session per epoch, and a standing request for a session with nothing newly
    # uploaded is a NO-OP inside `coordinator._advance_build` (`new_refs` empty -> None). So
    # `warm_ahead_emitted` reached 91,592 on an 8-device 300 s shakedown cell while the number of
    # prefills actually issued was 77. The emitted count is a count of ASKS; the characteristic
    # DECISION is the prefill the coordinator issued, which is one `release_piece` row each.
    # The headline count below is therefore read off the decision log, not off the arm's stats,
    # and the arm's stats are reported beside it and labelled.
    def _piece_rows(rows):
        return sum(1 for r in rows if str(r.get("kind")) in ("release_piece", "release_whole"))
    n_pieces, n_pieces_shim = _piece_rows(wa), _piece_rows(wa_s)
    n_pieces_base = _piece_rows(base)
    out["proof3_characteristic_decision"] = dict(
        prefills_issued_committed=n_pieces,
        prefills_issued_shimmed=n_pieces_shim,
        prefills_issued_base=n_pieces_base,
        _register=("prefills_issued is an OBSERVED COUNT of release_piece / release_whole rows "
                   "in the coordinator's own decision log. warm_ahead_* below are the arm's "
                   "ASKS, one per candidate session per epoch, most of which no-op; they are "
                   "not a decision count and must not be reported as one."),
        characteristic=("warm_ahead_prefill (a MATERIALIZE for a session with no pending "
                        "question), reported WITH the readiness split of the arm's own released "
                        "recalls, because the gate needs an arm that goes warm AND cold under "
                        "one policy, not merely an arm that warms"),
        release_readiness_committed={k: int(v) for k, v in sorted(wa_st.items())
                                     if k.startswith("release_at_")},
        release_readiness_shimmed={k: int(v) for k, v in sorted(wa_s_st.items())
                                   if k.startswith("release_at_")},
        release_readiness_base={k: int(v) for k, v in sorted(off_st.items())
                                if k.startswith("release_at_")},
        arm_asks_committed=dict(
            emitted=int(wa_st.get("warm_ahead_emitted", 0)),
            wanted=int(wa_st.get("warm_ahead_wanted", 0)),
            unexpressible=int(wa_st.get("warm_ahead_unexpressible", 0)),
            yielded_epochs=int(wa_st.get("warm_ahead_yielded_epochs", 0))),
        arm_asks_shimmed=dict(
            emitted=int(wa_s_st.get("warm_ahead_emitted", 0)),
            wanted=int(wa_s_st.get("warm_ahead_wanted", 0)),
            unexpressible=int(wa_s_st.get("warm_ahead_unexpressible", 0)),
            yielded_epochs=int(wa_s_st.get("warm_ahead_yielded_epochs", 0))))
    n_char, n_char_shim = n_pieces, n_pieces_shim

    def _states(st):
        return {k.replace("release_at_", ""): int(v) for k, v in st.items()
                if k.startswith("release_at_")}
    st_c, st_s = _states(wa_st), _states(wa_s_st)
    # BOTH STATES, the gate's actual requirement: the arm must release recalls at more than one
    # readiness, or the warm coefficient is still fitted on one regime and the confound with arm
    # has only been moved, not removed.
    out["proof3_characteristic_decision"]["both_states"] = dict(
        committed=dict(distinct_readiness=len([k for k, v in st_c.items() if v > 0]),
                       split=st_c),
        shimmed=dict(distinct_readiness=len([k for k, v in st_s.items() if v > 0]),
                     split=st_s),
        verdict=("PASS: both warm and cold releases under one policy"
                 if len([k for k, v in st_s.items() if v > 0]) > 1 else
                 "SINGLE REGIME: the gate's confound with arm is not removed by this arm as "
                 "configured; report it rather than fitting a warm coefficient on it"),
        note=("readiness is the arm's BELIEF at release time, the only residency signal a dry "
              "run has. The live cell must report the engine's own cache_path split beside it; "
              "the two are different quantities."))
    out["proof3_characteristic_decision"]["verdict"] = (
        "PASS: %d warm-ahead prefills issued where the base issues %d" % (n_char, n_pieces_base)
        if n_char > n_pieces_base else
        ("UNEXPRESSIBLE on the committed harness: the arm asked %d times and was rejected %d "
         "times and issued %d prefills, against the base's %d. With the known-session widening "
         "shimmed in it issues %d. The mechanism is present; the channel it acts through is "
         "what is missing, so this is CLAUDE.md Rule 2 'unexpressible' and NOT a negative."
         % (int(wa_st.get("warm_ahead_wanted", 0)),
            int(wa_st.get("warm_ahead_unexpressible", 0)), n_char, n_pieces_base,
            n_char_shim)))

    # 4. STEP 2b: does the switch reach a decision? Setwise, because a reordering is not a
    # decision (`test_hybrid._differing_setwise`'s own docstring).
    first = next((i for i, (x, y) in enumerate(zip(base, wa)) if x != y), None)
    first_s = next((i for i, (x, y) in enumerate(zip(base, wa_s)) if x != y), None)
    out["proof4_step2b_decision_diff"] = dict(
        vs="b7-edf-feasibility",
        differing_setwise=TH._differing_setwise(base, wa),
        differing_positional=TH._differing(base, wa),
        first_differing_index=first,
        first_differing_row=(wa[first] if first is not None else None),
        differing_setwise_shimmed=TH._differing_setwise(base, wa_s),
        first_differing_index_shimmed=first_s,
        first_differing_row_shimmed=(wa_s[first_s] if first_s is not None else None))
    out["proof4_step2b_decision_diff"]["verdict"] = (
        "PASS" if TH._differing_setwise(base, wa) > 0 else
        "ABSENT LINK on the committed harness; shimmed diff is %d"
        % TH._differing_setwise(base, wa_s))

    out["summary"] = dict(
        all_four_pass=bool(out["proof2_fairness_digest"]["control_identical_to_base"]
                           and n_char > n_pieces_base
                           and TH._differing_setwise(base, wa) > 0),
        both_states_under_one_policy=out["proof3_characteristic_decision"]["both_states"]["verdict"],
        blocking=("none" if n_char > n_pieces_base else
                  "validate_action known-session widening (see reports/study_engine_actions.md)"))
    return out


def proofs_reactive(seed=4, n=16, run_s=1200.0) -> Dict[str, Any]:
    """The same four proofs for `warm-all-lru-reactive`, THE LEGAL FALLBACK.

    Separate entry point rather than a fifth column in `proofs()`, because the two arms make
    DIFFERENT characteristic decisions and merging them into one table is how a reactive prefill
    gets counted as a warm-ahead one. Run with `python arms_warmall.py reactive`.
    """
    import hashlib
    import json
    sys.path.insert(0, str(HERE / "hybrid"))
    import baseline_prescreen as BP
    import test_hybrid as TH
    register()

    def digest(rows):
        return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                         default=float).encode()).hexdigest()[:16]

    def pieces(rows):
        return sum(1 for r in rows if str(r.get("kind")) in ("release_piece", "release_whole"))

    base, base_st = _dry("b7-edf-feasibility", seed, n, run_s)
    rx, rx_st = _dry("warm-all-lru-reactive", seed, n, run_s)
    bc = BP.census(base)
    out = dict(
        version=WARMALL_VERSION, arm="warm-all-lru-reactive",
        _label=("THE LEGAL FALLBACK. It warms REACTIVELY, at the question, so it CANNOT show "
                "that warming helps on-time and is not offered for that. It exists because a "
                "sliced build reuses its own prefix on the wire, so it produces warm and cold "
                "ENGINE rows under one policy with no patch to the action space."),
        cell=dict(seed=seed, n_devices=n, run_s=run_s, ratio="40:40:20", dry=True,
                  robot_question_set="lh_req", ss_question_set="ss2"),
        check1_positive_control=dict(
            quantity="b7-edf-feasibility feasibility_actions at this cell",
            this_run=int(bc["feasibility_actions"]), prior_run=5,
            source_of_prior="reports/study_frozen_test.md section 13.4",
            agree=(int(bc["feasibility_actions"]) == 5)),
        proof1_well_formedness=dict(completed=True, decisions=len(rx), illegal_actions=0),
        proof2_fairness_digest=dict(base="b7-edf-feasibility", base_digest=digest(base),
                                    base_decisions=len(base), treatment_digest=digest(rx),
                                    treatment_decisions=len(rx),
                                    control_arm="warm-all-lru-off",
                                    control_note=("the byte-identity control is shared with "
                                                  "proofs(); it is the same base and the same "
                                                  "off switch")),
        proof3_characteristic_decision=dict(
            characteristic="warm_reactive prefill (a sliced MATERIALIZE of a PENDING session)",
            prefills_issued=pieces(rx), prefills_issued_base=pieces(base),
            arm_asks={k: int(v) for k, v in sorted(rx_st.items())
                      if k.startswith("warm_reactive")},
            release_readiness={k: int(v) for k, v in sorted(rx_st.items())
                               if k.startswith("release_at_")},
            release_readiness_base={k: int(v) for k, v in sorted(base_st.items())
                                    if k.startswith("release_at_")},
            _register=("prefills_issued is an OBSERVED COUNT of release_piece / release_whole "
                       "rows in the coordinator's decision log. The release_readiness split is "
                       "the arm's BELIEF, which promotes only on a COMPLETE build and therefore "
                       "stays COLD for this arm; the warm rows this arm exists to produce are at "
                       "the ENGINE level, in each sliced piece's own cached_tokens, which a dry "
                       "run cannot see and the live cell must report.")),
        proof4_step2b_decision_diff=dict(
            vs="b7-edf-feasibility",
            differing_setwise=TH._differing_setwise(base, rx),
            differing_positional=TH._differing(base, rx)))
    fd = next((i for i, (x, y) in enumerate(zip(base, rx)) if x != y), None)
    out["proof4_step2b_decision_diff"]["first_differing_index"] = fd
    out["proof4_step2b_decision_diff"]["first_differing_row"] = (rx[fd] if fd is not None
                                                                 else None)
    np_, nb = pieces(rx), pieces(base)
    out["proof3_characteristic_decision"]["verdict"] = (
        "PASS: %d reactive prefills issued where the base issues %d" % (np_, nb)
        if np_ > nb else "FAIL: no prefill issued")
    out["proof4_step2b_decision_diff"]["verdict"] = (
        "PASS" if TH._differing_setwise(base, rx) > 0 else "ABSENT LINK")
    out["summary"] = dict(
        all_four_pass=bool(out["check1_positive_control"]["agree"] and np_ > nb
                           and TH._differing_setwise(base, rx) > 0),
        runnable_on_committed_harness=True,
        what_it_does_not_show=("that warming ahead helps. The question pays the materialisation, "
                               "which study_frozen_test.md 15.4 measured as edf's 5.483 s median "
                               "wait. Only the patched warm-all-lru tests warming ahead."))
    return out


def main(argv=None) -> int:
    import json
    argv = list(sys.argv[1:] if argv is None else argv)
    reactive = bool(argv and argv[0] == "reactive")
    res = proofs_reactive() if reactive else proofs()
    out = REPO / ("results/orchestration/live2/v5/engine_actions_warmall_"
                  + ("reactive_proofs.json" if reactive else "proofs.json"))
    try:
        import _provenance
        res["_provenance"] = _provenance.stamp(script="arms_warmall.py", model="none-dry",
                                               device="nvidia_rtx_a6000", n=16)
    except Exception as e:                                                     # noqa: BLE001
        res["_provenance"] = {"git_commit": "unstamped", "script": "arms_warmall.py",
                              "note": "stamp failed: %r" % (e,)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "_provenance"}, indent=2,
                     default=float))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
