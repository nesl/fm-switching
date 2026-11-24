#!/usr/bin/env python3
"""Engine-side state actions for policy v5 (spec v5 section 8, D150 STATE). CPU only.

WHAT THIS MODULE IS. v5 owns no pin, no reservation and no guarantee: vLLM cannot pin KV, a
running request's blocks are never evicted, and a finished request's blocks are LRU-evictable,
spilling to the 27 GiB native host tier and then cold (D150). So the policy STEERS, and this
module is the four levers it steers with, expressed in the committed action space and nothing
else, so that reader 2 (`v5/value_readers.py::warm_keep_reader`) can score them as options:

  1. `warm_ahead`   a prefill-only MATERIALIZE of the frames a session has uploaded but the
                    cloud has not yet built, at lowest priority, yielding to deadline work;
  1b. `warm_reactive` THE LEGAL FALLBACK: the same sliced build, but of a session that already
                    has a pending question, which `validate_action` accepts today. It is NOT
                    warming ahead and its count has a different name for that reason; see
                    `plan_warm_reactive`.
  2. `touch`        KEEP_GPU_WARM, which refreshes `SessionRec.last_touch_s` through
                    `cstate.enact_placement` and so moves the session DOWN the harness eviction
                    order. It is not a pin and this module does not call it one;
  3. `reload`       a MATERIALIZE issued against a history believed to be on the host tier, just
                    in time before a likely question;
  4. `hold_back` / `slice_plan`   control of what ENTERS the GPU, which D150 calls "above all"
                    and which is the only lever acting on the eviction of someone else's state.

Plus the belief corrector D150 names by its defect:

  5. `belief_update_from_cached_tokens`, the read that turns the engine's own per-request
     `cached_tokens` into a correction of `SessionRec.belief`.

REGISTERS, because three of these are in different ones and a reader who misses that will
misread the module.

  * MEASURED: nothing here. This module decides and is scored by the harness; it measures
    nothing and contains no cost curve.
  * COMMITTED: the action space (`baselines/interface.py`), the eviction order
    (`cstate.enact_placement`), and the build semantics (`coordinator._advance_build`).
  * CONSTRUCTED: the W2 discipline thresholds and the default slice size, which are declared
    constants below and are NOT fitted on anything.

THREE THINGS THIS MODULE REFUSES TO PRETEND, each because the evidence says so.

(a) WARM-AHEAD IS NOT EXPRESSIBLE IN THE COMMITTED ACTION SPACE, TODAY.
    `interface.validate_action` accepts a MATERIALIZE only for a session in
    `gpu_warm_sessions | host_warm_sessions | {q.session_id for q in obs.recall}`. A session
    that has uploaded frames but has no pending question and has never been built is in none of
    the three, so the FIRST warm-ahead prefill for every session is rejected, and after the
    rejection the session is still cold, so it is rejected again for ever. Every committed
    emitter of MATERIALIZE (`arms.py:277`, `arms.py:413`, `arms_builder.py:317-320`,
    `arms_policy.py:1042`) names `q.session_id`, which is why no committed arm has met this:
    every one of them warms REACTIVELY, at the question, which is the behaviour
    `study_frozen_test.md` 15.4 measured as edf paying the whole warming latency inside the
    deadline. `plan_warm_ahead` therefore returns BOTH what it wanted and what was legal, and
    `WarmAheadPlan.unexpressible` is non-zero until the observation carries live sessions. Under
    CLAUDE.md Rule 2 a null produced in that state is `unexpressible`, not a negative.

(b) RELOAD-FROM-HOST HAS NO OBSERVED TRIGGER STATE. `cstate.py:169` assigns `belief["host"]`
    and `set_tier("host", now)` is reachable at `cstate.py:447` and `:486`, so the branch EXISTS
    in code. Across all 39 committed 16-device cells the believed tier is cold 14,472 and gpu
    1,442 and host NEVER, so no committed run has reached the state in which a reload is the
    right action. `plan_reload` is built, counts its own firings, and this module does not
    assume the branch is exercised: an arm that reports zero reloads has reported the state of
    the fleet, not a defect.

(c) THE BELIEF IS WRITE-ONLY UNTIL SOMETHING READS IT BACK. `SessionRec.last_telemetry_cached_
    tokens` is DECLARED at `cstate.py:98` and has no write and no read anywhere in live2, which
    is one step worse than the write-only `desired_tier` CLAUDE.md names. `coordinator._settle`
    already HAS the value (`cached_tokens`, passed to `_log_residency(telemetry=...)`) and
    throws it away. `belief_update_from_cached_tokens` is the function that consumes it; the
    patch that calls it is owned by the coordinator's owner and is specified in
    `reports/study_engine_actions.md`.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (REPO / "experiments/orchestration/baselines", REPO / "experiments/orchestration/sim",
           REPO / "experiments/lib", REPO / "experiments/orchestration"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from interface import Observation, SessionAction, materialize    # noqa: E402

ENGINE_ACTIONS_VERSION = "v5-engine-actions-1.0"

# ---------------------------------------------------------------- declared constants
# CONSTRUCTED, not fitted. `study_frozen_test.md` 16.3 point 5 is the whole reason W2 exists:
# W1 (warm immediately into one FIFO with deadline work) drove the worst single-shot queue wait
# to 3.746 s against a 2 s deadline, worse than the deadline itself, and the calibration that
# produced that number UNDERSTATES warm and build service by 1.5x to 3.7x (16.1). So the default
# is W2 and W1 is not built here.
W2_LAXITY_FRACTION = 0.3          # D143 ruling B, the policy's own committed at-risk test
WARM_AHEAD_SLICE_TOKENS = 1024    # "small pieces": one piece per session per epoch
WARM_AHEAD_TARGET = 10 ** 9       # coordinator._advance_build clamps to est_tokens

# A MATERIALIZE target the arm cannot size itself. `_advance_build` computes
# `target = min(target_tokens or est_tokens, est_tokens)`, so naming a number far above any
# history asks for "all of it", and `new_refs = s.frames[already:already + n_new]` makes the
# request empty, and the whole call a no-op, exactly when nothing new has been uploaded. That is
# what makes "prefill every uploaded batch on arrival" a single standing request rather than a
# batch-arrival event the arm would have to detect and could get wrong.


@dataclass(frozen=True)
class WarmAheadPlan:
    """What the arm wanted, what it may legally say, and why the difference exists.

    `wanted` and `legal` are reported separately on purpose. A plan that silently dropped the
    illegal half would show a zero that looks like a policy decision; CLAUDE.md's Step 2b calls
    that an ABSENT LINK and requires it be named rather than scored.
    """
    actions: Tuple[SessionAction, ...] = ()
    wanted: Tuple[str, ...] = ()
    legal: Tuple[str, ...] = ()
    unexpressible: Tuple[str, ...] = ()
    yielded: bool = False
    reason: str = ""

    @property
    def n_warm_ahead(self) -> int:
        """The arm's CHARACTERISTIC DECISION count: prefills issued AHEAD of a question.

        A MATERIALIZE for a session that already has a pending question is reactive warming,
        which edf and llf already do, so it is deliberately NOT counted here.
        """
        return len(self.actions)


def known_sessions(obs: Observation) -> set:
    """Exactly `interface.validate_action`'s own set, duplicated here so the arm can ask BEFORE
    emitting rather than be rejected after. Kept in one place so a widening of the real rule is
    a one-line change here too."""
    return (set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
            | {q.session_id for q in obs.recall}
            | set(getattr(obs, "live_sessions", ()) or ()))


def deadline_work_at_risk(obs: Observation, targets: Optional[Dict[str, Any]] = None,
                          laxity_fraction: float = W2_LAXITY_FRACTION) -> bool:
    """W2: may a background prefill start at all this epoch?

    Strict priority for deadline work. A prefill occupies a slot for 0.3 to 0.9 s and is not
    preemptible once started, because a prefill is not resumable, so the test is made BEFORE
    starting one and never after. The test is the policy's own committed at-risk rule, laxity
    below `laxity_fraction` times the item's own deadline (D143 ruling B), applied to the
    pending recall set, which is the only pending set carrying per-item deadlines.
    """
    now = float(obs.now_s)
    for q in obs.recall:
        bound = max(float(q.deadline_s) - float(q.arrival_s), 1e-9)
        if (float(q.deadline_s) - now) < laxity_fraction * bound:
            return True
    return False


def plan_warm_ahead(obs: Observation, candidate_sessions: Iterable[str],
                    *, slice_tokens: Optional[int] = WARM_AHEAD_SLICE_TOKENS,
                    yield_to_deadline: bool = True,
                    targets: Optional[Dict[str, Any]] = None) -> WarmAheadPlan:
    """Lever 1. Prefill-only, small pieces, lowest priority, yielding to deadline work.

    `candidate_sessions` is every session the arm believes has uploaded frames the cloud has not
    built. The arm supplies it from the D100 roster (`session_device`, `built_tokens_by_session`),
    which are causal facts known at arrival, so nothing here reads the future.

    "Lowest priority" is expressed by WHEN the action is emitted, not by a priority field: the
    action space has none for sessions, and `Action.notes["priority_ms"]` is read only for
    per-item submissions (`coordinator._enact`). Yielding is therefore the whole of the
    discipline, which is why `yielded` is reported and not inferred.
    """
    wanted = tuple(sorted(str(s) for s in candidate_sessions))
    if not wanted:
        return WarmAheadPlan(reason="no candidate session")
    if yield_to_deadline and deadline_work_at_risk(obs, targets):
        return WarmAheadPlan(wanted=wanted, yielded=True,
                             reason="W2: deadline work at risk this epoch")
    allowed = known_sessions(obs)
    pending = {q.session_id for q in obs.recall}
    legal, bad = [], []
    for sid in wanted:
        # A session with a pending question is warmed by the request path, not by this lever.
        # Counting it here would inflate the characteristic decision with reactive warming.
        if sid in pending:
            continue
        (legal if sid in allowed else bad).append(sid)
    acts = tuple(materialize(sid, WARM_AHEAD_TARGET, slice_tokens) for sid in legal)
    return WarmAheadPlan(actions=acts, wanted=wanted, legal=tuple(legal),
                         unexpressible=tuple(bad),
                         reason=("ok" if not bad else
                                 "validate_action does not accept a MATERIALIZE for a session "
                                 "that is neither warm nor pending; see module docstring (a)"))


def plan_warm_reactive(obs: Observation, *, slice_tokens: Optional[int] = WARM_AHEAD_SLICE_TOKENS,
                       yield_to_deadline: bool = True,
                       targets: Optional[Dict[str, Any]] = None) -> WarmAheadPlan:
    """Lever 1b, THE LEGAL FALLBACK. Slice-build the history of a session that already has a
    pending question.

    THIS IS NOT WARMING AHEAD AND MUST NEVER BE REPORTED AS IT. The session is in `obs.recall`,
    so `validate_action` accepts it today with no patch, and that is the entire reason this
    function exists: warming ahead is unexpressible (module docstring (a)) and the cost-model
    gate needs warm engine rows tonight. The question still pays the materialisation latency,
    which is exactly what `study_frozen_test.md` 15.4 measured as edf's 5.483 s median wait, so
    this lever cannot show that warming helps on-time and is not offered for that.

    WHAT IT IS GOOD FOR, and it is the one thing the gate actually needs. A sliced build reuses
    its own prefix on the wire as uuid references, so piece k+1 reports `cached_tokens > 0` while
    the readiness the arm sees still says COLD (`coordinator.py:745-752`). Measured over 213
    committed residency logs, 72 of the 95 rows with positive telemetry are on the piece-chaining
    arms and none are on an arm that rebuilds whole. So this lever produces WARM AND COLD engine
    rows under ONE policy, which is what identifies the warm coefficient out of arm, and it does
    so without the patch.

    `WarmAheadPlan.legal` carries the sessions; `unexpressible` is empty by construction here.
    """
    if yield_to_deadline and deadline_work_at_risk(obs, targets):
        return WarmAheadPlan(yielded=True, reason="W2: deadline work at risk this epoch")
    sids = sorted({q.session_id for q in obs.recall if q.readiness != "GPU-WARM"})
    if not sids:
        return WarmAheadPlan(reason="no pending session below GPU-WARM")
    acts = tuple(materialize(sid, WARM_AHEAD_TARGET, slice_tokens) for sid in sids)
    return WarmAheadPlan(actions=acts, wanted=tuple(sids), legal=tuple(sids),
                         reason="reactive slice-build of a pending session (legal today)")


def touch(session_id: str) -> SessionAction:
    """Lever 2. KEEP_GPU_WARM.

    It is READ: `coordinator._enact` sets `desired_tier = "gpu"` and `cstate.enact_placement`
    refreshes `last_touch_s` and sorts a keep-warm request LAST in the eviction order
    (`cstate.py`, `order = sorted(on_gpu, key=lambda x: (x.desired_tier == "gpu", last_touch_s,
    session_id))`). It does NOT make the history unevictable and this function's name is the
    only claim it makes.
    """
    return SessionAction(str(session_id), "KEEP_GPU_WARM")


def plan_reload(obs: Observation, session_ids: Iterable[str],
                *, slice_tokens: Optional[int] = None) -> Tuple[List[SessionAction], List[str]]:
    """Lever 3. Reload a history believed to be on the host tier, just in time.

    Returns the actions and the sessions that were asked for but are not believed host-resident,
    so an empty result is distinguishable from a result that was never asked for. See module
    docstring (b): across all 39 committed 16-device cells the believed tier is host ZERO times,
    so this lever is expected to fire zero times on committed traces and that is a fact about
    the fleet.
    """
    host = set(obs.cloud.host_warm_sessions)
    hit = [sid for sid in sorted(set(str(s) for s in session_ids)) if sid in host]
    miss = [sid for sid in sorted(set(str(s) for s in session_ids)) if sid not in host]
    return [materialize(sid, WARM_AHEAD_TARGET, slice_tokens) for sid in hit], miss


def slice_plan(tokens_to_build: int, slice_tokens: Optional[int]) -> List[int]:
    """Lever 4a. How a background rebuild is cut up.

    SCOPE, from spec v5 section 15: slicing applies to BACKGROUND WARMING ONLY, never to a
    deadline request (D151 (3)). Nothing here is applied to a recall.
    """
    n = max(int(tokens_to_build), 0)
    if n == 0:
        return []
    if not slice_tokens:
        return [n]
    k = max(int(slice_tokens), 1)
    out = [k] * (n // k)
    if n % k:
        out.append(n % k)
    return out


def hold_back(obs: Observation, session_id: str, tokens_to_build: int,
              gpu_kv_tokens: int, *, due_within_s: float = 120.0) -> Tuple[bool, str]:
    """Lever 4b, the one D150 calls "above all": refuse to let a large cold rebuild enter the GPU
    when it would evict a history whose question is due.

    This is the only lever that acts on someone else's state, and it is the reason reader 2's
    `harm` term cannot be dropped: `study_frozen_test.md` 19.4 has warm-all at 65 of 65 at the
    committed capacity and 34 of 65 at 0.25x, and a reader without `harm` ranks a warm
    identically at both.
    """
    if gpu_kv_tokens <= 0:
        return False, "no capacity model"
    free = max(1.0 - float(obs.cloud.gpu_kv_fraction), 0.0) * float(gpu_kv_tokens)
    if float(tokens_to_build) <= free:
        return False, "fits in free pool"
    now = float(obs.now_s)
    due = [q for q in obs.recall
           if q.session_id != session_id and (float(q.deadline_s) - now) <= due_within_s]
    if not due:
        return False, "would evict, but nothing is due"
    return True, "would evict a history whose question is due within %.0f s" % due_within_s


# ---------------------------------------------------------------- 5: the belief corrector
@dataclass
class BeliefUpdate:
    """The outcome of one correction, returned so a caller can count corrections that CHANGED a
    belief separately from corrections that merely confirmed one. A corrector that only ever
    confirms is the write-only shape wearing a read's clothes."""
    session_id: str
    before: str
    after: str
    cached_tokens: Optional[int]
    prompt_tokens: Optional[int]
    changed: bool
    reason: str
    external: Optional[int] = None


def belief_update_from_cached_tokens(session, cached_tokens: Optional[int],
                                     prompt_tokens: Optional[int] = None,
                                     now: Optional[float] = None,
                                     external_tokens: Optional[int] = None) -> BeliefUpdate:
    """D150: correct the residency belief with the engine's OWN per-request cached-token count.

    `session` is a `cstate.SessionRec`, duck-typed so this module does not import the
    coordinator's state and so the unit proof can run on a stub.

    THE RULE, and every clause of it has a reason.

    * `cached_tokens > 0` means the engine served this request partly from KV it already held,
      so the history IS resident. The belief is promoted to `gpu`. `study_frozen_test.md` 17.6
      records this measured on the same build: appended requests in StudySH-EP carry
      `cached_tokens` 3,056 to 6,768.
    * `cached_tokens == 0` on a request that offered a prefix the belief says is resident is
      evidence the belief is WRONG, so it is demoted to `cold`. This is the correction that
      matters: section 17.3 shows the frozen grid turning its 62,944-token pool over 89 times in
      1,200 s, so a belief formed at build time is stale within seconds and nothing told it.
    * `cached_tokens is None` is NO EVIDENCE, not evidence of a miss. A dry run sends no HTTP and
      carries no usage block, and `backend.cached_tokens_of` returns None rather than 0 for an
      engine that does not report the field. Treating None as a miss would make every dry cell
      demote every belief and would be a correction driven by the absence of an engine.
    * A demotion is NOT applied to a request that offered nothing to reuse. A single-frame
      dashcam monitor offers 12 to 18 shared tokens against vLLM's 16-token block (17.2), so its
      zero is a property of the request and not of residency. The guard is `prompt_tokens`
      against the session's own built prefix.

    PROVISIONAL, and it must be carried into every report that reads this belief:
    under write-through host offload (`--kv-offloading-backend native --kv-offloading-size 27`)
    a block evicted from the GPU may still be resident on the host tier while the engine reports
    `cached_tokens = 0` for a GPU lookup. This function therefore says COLD where HOST is
    likely, which is the conservative direction for cost (a host reload is charged as a cold
    rebuild) and the wrong direction for a reload decision. `external_tokens` is the separate
    channel for the engine's connector-hit count if vLLM 0.31.0 exposes one; when it is supplied
    and non-zero the belief goes to `host` rather than `cold`.

    D209 (4) UPGRADES "PROVISIONAL" TO "MEASURED, AND PERMANENT ON THIS ENGINE". The probe (see
    `EXTERNAL_HIT_KEYS` above) found host hits carrying 26 percent of the engine's prompt tokens
    AND no per-request field that distinguishes them, so `external_tokens` is None on every
    request and the `cold` branch below is taken for every zero-reuse request whose prefix was in
    fact on the host. Read `cold` here as "NOT IN GPU KV", which is what the evidence supports; it
    is an UPPER BOUND on reconstruction cost and a LOWER BOUND on residency, and it is not
    evidence that the host tier was empty.
    """
    before = session.believed_tier()
    if cached_tokens is None:
        return BeliefUpdate(session.session_id, before, before, None, prompt_tokens, False,
                            "no usage reported: no evidence, belief untouched")
    ct = int(cached_tokens)
    session.last_telemetry_cached_tokens = ct
    if now is not None:
        session.last_touch_s = float(now)
    if ct > 0:
        after = "gpu"
        reason = "engine reused %d prompt tokens: resident" % ct
    else:
        built = int(getattr(session, "built_tokens", 0) or 0)
        offered = int(prompt_tokens) if prompt_tokens is not None else built
        if built <= 0 or offered < built:
            return BeliefUpdate(session.session_id, before, before, ct, prompt_tokens, False,
                                "zero hit on a request that offered no built prefix: not "
                                "evidence about residency")
        if external_tokens:
            after, reason = "host", ("zero GPU reuse but %d external/connector tokens: host"
                                     % int(external_tokens))
        else:
            after = "cold"
            reason = ("zero reuse on a %d-token request over a %d-token built prefix: not in GPU "
                      "KV (D209 (4): no per-request host signal exists on this engine, and 26 "
                      "percent of its prompt tokens came from the host tier, so this is a lower "
                      "bound on residency and not evidence of a cold prefix)" % (offered, built))
    session.belief = {"gpu": 0.0, "host": 0.0, "cold": 0.0}
    session.belief[after] = 1.0
    return BeliefUpdate(session.session_id, before, after, ct, prompt_tokens,
                        after != before, reason, external=external_tokens)


# ---------------------------------------------------------------- the external-hit channel
# User ruling 2026-11-20: log the engine's external / connector-hit tokens SEPARATELY if vLLM
# 0.31.0 exposes them, so a GPU hit and a host hit can be told apart.
#
# D209 (4), 2026-11-23: THE PROBE HAS BEEN RUN AND THE ANSWER IS NO, STRUCTURALLY. The register of
# this block changes from CONSTRUCTED to OBSERVED, and so does its verdict.
# Source: `results/orchestration/live2/frozen_test/engine_probe_hit26/` (README plus the raw
# `metrics_scrape_h100.txt`), one read-only GET of /metrics on the live H100 server, vLLM
# 0.31.0+cu129, Qwen3-VL-32B, native CPU offload on, captured 2026-11-23T15:04:47-0800 during a
# `covex-v6-base` s4 `_kv0.25` cell.
#
# WHAT THE PROBE SETTLED, in two parts that point opposite ways.
#
# (1) HOST RESIDENCY IS REAL AND FREQUENT. 26 percent of the engine's prompt tokens came from the
#     host tier: `vllm:prompt_tokens_by_source_total{source="external_kv_transfer"}` 4,943,072 of
#     18,707,015, against `local_cache_hit` 10,094,768 and `local_compute` 3,669,175;
#     `vllm:external_prefix_cache_hits_total` 4,945,760 of 8,618,089 queries; 1,847 CPU-to-GPU
#     loads moving 1.2965e12 bytes. So a belief that says "cold" on a zero GPU reuse is wrong a
#     large fraction of the time, and in the MAXIMUM-COST direction.
#
# (2) AND IT IS NOT OBSERVABLE PER REQUEST ON THIS ENGINE. The per-request usage schema is fixed by
#     the installed source (`vllm/entrypoints/serve/engine/protocol.py:121-140`):
#       UsageInfo            = prompt_tokens, total_tokens, completion_tokens,
#                              prompt_tokens_details, completion_tokens_details
#       PromptTokenUsageInfo = cached_tokens, created_cache_tokens, multimodal_tokens
#     A host hit and a GPU hit are BOTH folded into `prompt_tokens_details.cached_tokens` and
#     cannot be told apart from it. `vllm:prompt_tokens_cached_total` equals local_cache_hit +
#     external_kv_transfer EXACTLY, which is the same folding seen from the counter side.
#
# SO THE KEY LIST IS NOT REPLACED WITH BETTER GUESSES, AND NOT WITH A REAL NAME, BECAUSE THERE IS
# NO REAL NAME TO PUT IN IT. The five names stay in the tuple, now labelled REFUTED, and
# `external_cached_tokens_of` therefore returns None on every request of this engine exactly as it
# did before - but now by MEASUREMENT rather than by a guess that happened to miss, which is a
# different claim about the same return value and the reason this edit moves no decision.
#
# WHY THE TUPLE IS NOT EMPTIED, which was the first thing written here and was wrong to do.
# `confirm_engine_actions_32b.py:1358` indexes `EA.EXTERNAL_HIT_KEYS[0]` to prove the lookup
# mechanism reads an external key WHEN one is present, and `:684` reports the probed list. That
# file belongs to another session, an empty tuple makes its self-test raise IndexError, and
# emptying the tuple would therefore have been a silent break of someone else's proof for a
# cosmetic gain. The refutation is recorded in `EXTERNAL_HIT_KEYS_REFUTED_BY_PROBE` instead, and
# removing the names is left as a one-line follow-up for that file's owner.
#
# WHY NOT DIFFERENCE THE AGGREGATE COUNTERS INSTEAD. `external_prefix_cache_hits_total` is exact
# per request only when a single request is in flight, which is not our regime (16 devices, three
# traffic types, `num_requests_running` 3 at capture). Attributing a counter delta to one of
# several concurrent requests would manufacture a per-request signal that the engine does not
# emit, so it is NOT wired into any decision path. The aggregate names are recorded in
# `HOST_RESIDENCY_AGGREGATE_KEYS` for REPORTING ONLY and nothing reads them to decide.
#
# CONSEQUENCE FOR THE RELOAD LEVER, which is the finding and must travel with it. RELOAD is offered
# only at HOST-WARM, and no per-request signal can put a session at HOST-WARM on this engine, so
# the lever is UNEXERCISED in CLAUDE.md Rule 2's sense for a STRUCTURAL reason (the engine does not
# expose the state) and not for a coding one (a wrong key name). That is a statement about vLLM
# 0.31.0's usage schema, not about the policy, and it does not become a negative about RELOAD.
# Guessed 2026-11-20. REFUTED by the D209 (4) probe: not one of these appears in the per-request
# usage block of vLLM 0.31.0+cu129, so this lookup returns None on every request of this engine.
EXTERNAL_HIT_KEYS: Tuple[str, ...] = ("external_computed_tokens", "num_external_computed_tokens",
                                      "connector_cached_tokens", "kv_connector_cached_tokens",
                                      "offloaded_cached_tokens")
EXTERNAL_HIT_KEYS_REFUTED_BY_PROBE = True
# OBSERVED in the probe scrape. AGGREGATE, cumulative since server start, REPORTING ONLY: no
# decision path reads these, because a counter delta cannot be attributed to one of several
# concurrent requests (see above).
HOST_RESIDENCY_AGGREGATE_KEYS = ("vllm:prompt_tokens_by_source_total",
                                 "vllm:external_prefix_cache_hits_total",
                                 "vllm:external_prefix_cache_queries_total",
                                 "vllm:kv_offload_load_bytes_total",
                                 "vllm:kv_offload_store_bytes_total",
                                 "vllm:kv_offload_cpu_cache_usage_perc")
# OBSERVED: the whole per-request prompt-token schema this engine emits. Written down so the next
# reader checks a list against the source rather than inventing a sixth candidate.
PER_REQUEST_PROMPT_TOKEN_FIELDS = ("cached_tokens", "created_cache_tokens", "multimodal_tokens")
PER_REQUEST_HOST_SIGNAL_AVAILABLE = False
PER_REQUEST_HOST_SIGNAL_SOURCE = (
    "results/orchestration/live2/frozen_test/engine_probe_hit26/ (D209 (4); vLLM 0.31.0+cu129, "
    "UsageInfo / PromptTokenUsageInfo at vllm/entrypoints/serve/engine/protocol.py:121-140)")


def external_cached_tokens_of(usage: Optional[Dict[str, Any]]) -> Optional[int]:
    """The engine's connector / external-hit token count, or None if it reports none.

    Kept here rather than in `backend.py` so that wiring it needs no edit to a file this session
    does not own.

    ON THIS ENGINE IT RETURNS None FOR EVERY REQUEST, BY MEASUREMENT (D209 (4)). `EXTERNAL_HIT_KEYS`
    is empty because the probe read the installed per-request schema and found no external-hit
    field in it; the loop below is kept rather than replaced by `return None` so that an engine
    which DOES expose one needs a name added to that tuple and no other change. A non-empty tuple
    whose names are guessed is what this hit was, so a name goes in there only from a capture.
    """
    if not usage:
        return None
    d = usage.get("prompt_tokens_details")
    for src in (d if isinstance(d, dict) else None, usage):
        if not isinstance(src, dict):
            continue
        for k in EXTERNAL_HIT_KEYS:
            if src.get(k) is not None:
                return int(src[k])
    return None


# ---------------------------------------------------------------- unit proof
def _stub_session(sid="robo001_s000", built=5000, tier="gpu"):
    class S:
        session_id = sid
        built_tokens = built
        est_tokens = built
        last_telemetry_cached_tokens = None
        last_touch_s = 0.0
        belief = None

        def believed_tier(self):
            return max(self.belief, key=lambda k: self.belief[k])
    s = S()
    s.belief = {"gpu": 0.0, "host": 0.0, "cold": 0.0}
    s.belief[tier] = 1.0
    return s


def unit_proof() -> Dict[str, Any]:
    """CLAUDE.md Step 2b, asked of the belief read: does the new read CHANGE a belief?

    Every case states what it asserts, so a case that silently stops asserting is visible.
    """
    cases: List[Dict[str, Any]] = []

    s = _stub_session(tier="cold", built=5000)
    u = belief_update_from_cached_tokens(s, 4940, 5000, now=10.0)
    cases.append(dict(case="warm hit promotes cold to gpu", before=u.before, after=u.after,
                      changed=u.changed, ok=(u.after == "gpu" and u.changed),
                      field_written=s.last_telemetry_cached_tokens))

    s = _stub_session(tier="gpu", built=5000)
    u = belief_update_from_cached_tokens(s, 0, 5000, now=11.0)
    cases.append(dict(case="zero hit on a full-prefix request demotes gpu to cold",
                      before=u.before, after=u.after, changed=u.changed,
                      ok=(u.after == "cold" and u.changed)))

    s = _stub_session(tier="gpu", built=5000)
    u = belief_update_from_cached_tokens(s, 0, 378, now=12.0)
    cases.append(dict(case="zero hit on a 378-token monitor does NOT demote",
                      before=u.before, after=u.after, changed=u.changed,
                      ok=(u.after == "gpu" and not u.changed)))

    s = _stub_session(tier="gpu", built=5000)
    u = belief_update_from_cached_tokens(s, None, None)
    cases.append(dict(case="no usage block is no evidence", before=u.before, after=u.after,
                      changed=u.changed, ok=(u.after == "gpu" and not u.changed)))

    s = _stub_session(tier="gpu", built=5000)
    u = belief_update_from_cached_tokens(s, 0, 5000, now=13.0, external_tokens=4900)
    cases.append(dict(case="zero gpu reuse with connector hits goes to host, not cold",
                      before=u.before, after=u.after, changed=u.changed,
                      ok=(u.after == "host" and u.changed)))

    s = _stub_session(tier="cold", built=5000)
    u = belief_update_from_cached_tokens(s, 4940, 5000, now=14.0)
    u2 = belief_update_from_cached_tokens(s, 4940, 5000, now=15.0)
    cases.append(dict(case="a confirming correction is reported as changed=False",
                      before=u2.before, after=u2.after, changed=u2.changed,
                      ok=(u2.after == "gpu" and not u2.changed)))

    sliced = slice_plan(5000, 1024)
    cases.append(dict(case="slice_plan partitions without overlap or loss",
                      value=sliced, ok=(sum(sliced) == 5000 and max(sliced) <= 1024)))

    n_changed = sum(1 for c in cases if c.get("changed"))
    return dict(version=ENGINE_ACTIONS_VERSION, cases=cases,
                all_ok=all(bool(c["ok"]) for c in cases),
                corrections_that_changed_a_belief=n_changed,
                step2b="PASS" if n_changed > 0 else "ABSENT LINK: no case changed a belief")


def main(argv: Optional[Sequence[str]] = None) -> int:
    import json
    res = unit_proof()
    out = REPO / "results/orchestration/live2/v5/engine_actions_unit.json"
    try:
        import _provenance
        res["_provenance"] = _provenance.stamp(script="engine_actions.py", model="none-cpu",
                                               device="nvidia_rtx_a6000", n=len(res["cases"]))
    except Exception as e:                                                     # noqa: BLE001
        res["_provenance"] = {"git_commit": "unstamped", "script": "engine_actions.py",
                              "note": "stamp failed: %r" % (e,)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "_provenance"}, indent=2,
                     default=float))
    print("wrote", out)
    return 0 if res["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
