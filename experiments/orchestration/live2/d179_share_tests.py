#!/usr/bin/env python3
"""The D179 (6b) unit tests for share-based admission and deadline-aware release re-check.

WRITTEN BEFORE THE BODIES, ON PURPOSE. These are the seven checks the user's item 6b asked for,
plus an eighth of my own, written against session A's FROZEN interface
(`share_admission.py` at f3482026) so that they go green as the allocator body and the release
hook land rather than being written afterwards to fit whatever the code turned out to do.

THERE IS NO PYTEST IN THE `fmtk` ENV, which an earlier session established. So this is a plain
script with an explicit pass/fail summary and a NON-ZERO EXIT on failure, runnable as
`conda run -n fmtk python experiments/orchestration/live2/d179_share_tests.py`.

THE THREE OUTCOMES, AND WHY A PENDING IS NOT A PASS. Each check reports one of:

  GREEN    it ran and asserted, against code that exists now
  PENDING  the mechanism it tests does not exist yet, with the REASON named. `allowed()` raises
           NotImplementedError when `enabled` is true, so a check of the allocator cannot run;
           it is reported PENDING and is NOT counted as a pass. A suite that reported these green
           would be a suite that passes before the thing it tests is built.
  FAIL     it ran and the assertion did not hold

CLAUDE.md Rule 1 in its test-side form: a check that could not reach the mechanism has not tested
the claim, and calling it a pass is exactly the error E36 made at experiment scale. So the summary
prints the three counts separately and never folds PENDING into GREEN.

WHAT IS AND IS NOT CLAIMED about a GREEN half of a split check. Several checks have a half that is
testable now (an arithmetic identity, a classifier, a predicate's reachability) and a half that
needs another session's call site. Where that happens the check is SPLIT and each half carries its
own status, because "T7 green" would otherwise read as "the carry-forward mechanism is verified"
when what was verified is the body arithmetic the mechanism relies on.

NUMBERS ARE IMPORTED, NEVER RETYPED: W_max, the floors and the flexible pool come from
`share_capacity.py`, the EP-G token law from `bodies.py`, the recall TTFT curve from
`baselines/costs.py`. A test that retyped 4323.3 would keep passing after the frozen constant
changed, which is the failure mode the frozen module exists to prevent.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bodies as B                                                      # noqa: E402
import costs as COSTS                                                   # noqa: E402
import share_admission as SA                                            # noqa: E402
import share_capacity as SCAP                                           # noqa: E402

OUT = REPO / "results/orchestration/live2/frozen_test/d179_share_tests.json"

EPS = 1e-6
# the DEADLINE (non-background) request kinds, and the background ones, both taken from the
# interface rather than assumed here
FG_KIND = {"alert": "monitor", "recall": "recall", "assistance": "recall"}
BG_KIND = {"alert": "touch", "recall": "whole", "assistance": "piece"}


class Pending(Exception):
    """Raised by a check whose mechanism does not exist yet. Carries the reason."""


def _allowed(**kw: Any) -> Tuple[bool, str]:
    """`allowed()` with `enabled` true, turning the interface's NotImplementedError into a
    PENDING rather than a failure. Nothing else is caught: a TypeError from a signature that
    drifted, or an AssertionError from a wrong answer, is a real failure and must surface."""
    kw.setdefault("enabled", True)
    try:
        return SA.allowed(**kw)
    except NotImplementedError as exc:
        raise Pending("share_admission.allowed() body not landed yet (session A commit 2): %s"
                      % exc) from exc


def _tracker(load: Dict[str, int], background: Optional[Dict[str, int]] = None) -> SA.WTracker:
    """A WTracker holding `load[t]` uncached tokens in flight for each type, of which
    `background[t]` is background work. Built through on_submit, never by poking the dicts, so
    the fixture exercises the same path the coordinator will."""
    bg = dict(background or {})
    tr = SA.WTracker()
    for t, u in load.items():
        b = int(bg.get(t, 0))
        if b:
            tr.on_submit("bg:%s" % t, t, b, background=True)
        if int(u) - b > 0:
            tr.on_submit("fg:%s" % t, t, int(u) - b, background=False)
    return tr


# ---------------------------------------------------------------------------- T1
def t1_shares_sum_to_wmax() -> Dict[str, Any]:
    """1. The shares sum to W_max exactly: the three floors plus the flexible pool.

    GREEN NOW. Arithmetic on the frozen module, which is the whole point of the module. The
    check is run two ways and the second one is the one that matters: the identity must HOLD on
    the committed numbers, and it must BREAK on a perturbed copy of them. An identity that holds
    no matter what the inputs are is not an identity, and a sum-to-total check written as
    `total = sum(parts)` is exactly that.
    """
    floors = dict(SCAP.FLOORS_TOKENS)
    total = sum(floors.values()) + SCAP.FLEXIBLE_TOKENS
    assert abs(total - SCAP.W_MAX_TOKENS) < EPS, (
        "floors + flexible = %.6f but W_max = %.6f" % (total, SCAP.W_MAX_TOKENS))
    assert set(floors) == set(SA.TYPES), "floors cover %s, types are %s" % (sorted(floors),
                                                                           sorted(SA.TYPES))
    assert all(v > 0 for v in floors.values()), "a non-positive floor reserves nothing"
    assert SCAP.FLEXIBLE_TOKENS > 0, "a non-positive flexible pool leaves nothing to borrow"

    # the negative control for THIS CHECK: perturb one floor by a single token and the identity
    # must fail, or the check cannot see a broken allocation
    bad = dict(floors)
    bad["alert"] += 1.0
    broke = abs(sum(bad.values()) + SCAP.FLEXIBLE_TOKENS - SCAP.W_MAX_TOKENS) >= EPS
    assert broke, "the identity survives a +1 token perturbation, so it is not checking anything"

    # `summary()` must publish the same numbers, or the H100's reader and the allocator disagree
    s = SA.summary(SA.WTracker(), enabled=True)
    assert abs(s["w_max"] - SCAP.W_MAX_TOKENS) < EPS, "summary w_max disagrees with the module"
    assert s["floors"] == floors, "summary floors disagree with the module"

    return {"status": "GREEN", "w_max": SCAP.W_MAX_TOKENS, "floors": floors,
            "flexible": SCAP.FLEXIBLE_TOKENS, "sum": round(total, 6),
            "floor_sum_fraction": round(sum(floors.values()) / SCAP.W_MAX_TOKENS, 4),
            "negative_control": "a +1 token perturbation of the alert floor breaks the identity",
            "_what_would_fail_if_wrong": (
                "a floor table that did not sum with the flexible pool to W_max, which is how a "
                "future edit to one of the four numbers would silently over- or under-commit the "
                "engine; and a summary() block publishing different capacity numbers from the "
                "ones the allocator divides")}


# ---------------------------------------------------------------------------- T2
def t2_floors_honoured_under_contention() -> Dict[str, Any]:
    """2. Floors are honoured under contention: every type pushing at once, each gets at least
    its floor.

    PENDING the allocator body. The fixture puts the OTHER two types at every token they could
    possibly hold - their own floors plus the whole flexible pool - and then asks for a request of
    the third type that fits inside its own floor. D179 (3) says a type is admitted immediately
    within its share, so this must be admitted, and the reason must not be a borrow: it is the
    type's own reserved capacity.
    """
    results = []
    for t in SA.TYPES:
        others = [x for x in SA.TYPES if x != t]
        # the others hold their floors AND the entire flexible pool: maximum legal contention
        load = {o: SCAP.floor_of(o) for o in others}
        load[others[0]] = load[others[0]] + SCAP.FLEXIBLE_TOKENS
        load[t] = 0
        tr = _tracker({k: int(v) for k, v in load.items()})
        ask = int(SCAP.floor_of(t)) - 1
        ok, why = _allowed(qtype=t, uncached=ask, kind=FG_KIND[t], tracker=tr,
                           pending_by_type={o: 1 for o in SA.TYPES},
                           weights_by_type={o: 1.0 for o in SA.TYPES})
        assert ok, ("type %s was denied %d tokens inside its own floor of %.1f while the other "
                    "types held %s; reason %r" % (t, ask, SCAP.floor_of(t), load, why))
        results.append({"type": t, "asked": ask, "floor": SCAP.floor_of(t),
                        "others_hold": {k: int(v) for k, v in load.items() if k != t},
                        "admitted": ok, "reason": why})
    return {"status": "GREEN", "per_type": results,
            "_what_would_fail_if_wrong": (
                "an allocator that divided only the free remainder, or that let the flexible pool "
                "be claimed before floors were met, would deny a type its reserved capacity under "
                "exactly the saturation D179 exists to fix - and would do so silently, as a "
                "lower admit rate and not as an error")}


# ---------------------------------------------------------------------------- T3
def t3a_background_classifier() -> Dict[str, Any]:
    """3a. The background classifier, GREEN NOW and load-bearing for 3b.

    If `is_background` returned False for a touch, 3b's premise evaporates: the request would be
    treated as deadline work, would be allowed to borrow a floor, and 3b would pass while testing
    nothing. So the classifier is checked separately and first. This is the same shape as a port's
    characteristic-decision count: before scoring a rule, confirm the rule's input is what it says.
    """
    for k in SA.BACKGROUND_KINDS:
        assert SA.is_background(k), "%r must be background (D179 (3): no floor)" % k
    for k in sorted(set(FG_KIND.values()) | {"append"}):
        assert not SA.is_background(k), "%r must NOT be background: it is deadline work" % k
    assert not SA.is_background("not-a-kind"), "an unknown kind must not default to background"
    # the type classifier too, because a floor is per TYPE and a misread prefix charges the
    # wrong floor
    for prefix, want in SA.PREFIX_TO_TYPE.items():
        assert SA.type_of_device(prefix + "-07") == want
    assert SA.type_of_device("other-1") is None
    assert SA.type_of_device("") is None and SA.type_of_device(None) is None
    return {"status": "GREEN", "background_kinds": list(SA.BACKGROUND_KINDS),
            "foreground_checked": sorted(set(FG_KIND.values()) | {"append"}),
            "prefix_to_type": dict(SA.PREFIX_TO_TYPE),
            "_what_would_fail_if_wrong": (
                "a touch classified as deadline work would be allowed into another type's floor "
                "by 3b's own rule, and 3b would still pass")}


def t3b_background_never_enters_another_floor() -> Dict[str, Any]:
    """3b. Background work NEVER enters another type's floor.

    PENDING the allocator body. Two conditions, and the pair is the test: with the flexible pool
    FREE a background warm may borrow it, and with the flexible pool EXHAUSTED but another type's
    floor standing idle the same warm must be DENIED. One condition alone cannot distinguish
    "background is admitted" from "background is admitted into a floor".
    """
    t, other = "recall", "alert"
    free = _tracker({"alert": 0, "recall": 0, "assistance": 0})
    ask = int(SCAP.FLEXIBLE_TOKENS // 4)
    ok_free, why_free = _allowed(qtype=t, uncached=ask, kind=BG_KIND[t], tracker=free,
                                 pending_by_type={t: 1}, weights_by_type={t: 1.0})

    # the flexible pool is gone and so is t's own floor; `other`'s floor is entirely idle, and it
    # is the ONLY capacity left. A background request must not take it.
    load = {t: int(SCAP.floor_of(t) + SCAP.FLEXIBLE_TOKENS), "assistance": 0, other: 0}
    tight = _tracker(load)
    ok_tight, why_tight = _allowed(qtype=t, uncached=ask, kind=BG_KIND[t], tracker=tight,
                                   pending_by_type={t: 1}, weights_by_type={t: 1.0})
    assert ok_free, "a background warm may borrow a FREE flexible pool; denied with %r" % why_free
    assert not ok_tight, (
        "a background %s warm of %d tokens was admitted with the flexible pool exhausted and only "
        "%s's floor of %.1f tokens free; reason %r" % (t, ask, other, SCAP.floor_of(other),
                                                       why_tight))
    return {"status": "GREEN", "kind": BG_KIND[t], "asked": ask,
            "free_pool": {"admitted": ok_free, "reason": why_free},
            "only_other_floor_left": {"admitted": ok_tight, "reason": why_tight,
                                      "other": other, "other_floor": SCAP.floor_of(other)},
            "_what_would_fail_if_wrong": (
                "an allocator that compared a background request against W_max minus total W, "
                "rather than against the capacity outside other types' floors, would admit "
                "warming into the alert reservation and recreate the dashcam loss D179 is "
                "fixing - while every aggregate counter looked healthier")}


# ---------------------------------------------------------------------------- T4
def t4_borrowing_path() -> Dict[str, Any]:
    """4. The borrowing path works: a deadline request takes unused capacity when its own share
    is exhausted.

    PENDING the allocator body. The fixture exhausts the asking type's OWN share - its floor plus
    its equal split of the flexible pool - and leaves the other two types idle. D179 (3) says
    deadline requests may borrow ANY unused capacity, so this must be admitted while the total
    stays under W_max, and must be denied once the total would exceed W_max. The second half is
    what separates borrowing from no limit at all.
    """
    t = "alert"
    own_share = SCAP.floor_of(t) + SCAP.FLEXIBLE_TOKENS / len(SA.TYPES)
    tr = _tracker({t: int(own_share), "recall": 0, "assistance": 0})
    ask = int(SCAP.floor_of("recall") // 2)
    ok, why = _allowed(qtype=t, uncached=ask, kind=FG_KIND[t], tracker=tr,
                       pending_by_type={t: 1}, weights_by_type={t: 1.0})
    assert ok, ("a deadline %s request of %d tokens was denied with its own share of %.1f "
                "exhausted and %.1f tokens of W_max unused; reason %r"
                % (t, ask, own_share, SCAP.W_MAX_TOKENS - own_share, why))

    # and the borrow is BOUNDED: an ask that would carry total W past W_max must be denied
    over = int(SCAP.W_MAX_TOKENS - own_share) + 1
    ok_over, why_over = _allowed(qtype=t, uncached=over, kind=FG_KIND[t], tracker=tr,
                                 pending_by_type={t: 1}, weights_by_type={t: 1.0})
    assert not ok_over or "alone" in str(why_over), (
        "a borrow of %d tokens carried total W past W_max = %.1f and was admitted for a reason "
        "other than the oversize-when-alone rule: %r" % (over, SCAP.W_MAX_TOKENS, why_over))
    return {"status": "GREEN", "type": t, "own_share": round(own_share, 1), "asked": ask,
            "borrowed": {"admitted": ok, "reason": why},
            "over_wmax": {"asked": over, "admitted": ok_over, "reason": why_over},
            "_what_would_fail_if_wrong": (
                "an allocator that capped every type at its own share would leave W_max unused "
                "whenever demand was uneven, which is every real cell: the shares would cost "
                "throughput for no reason and the arm would lose to C5 for a reason that has "
                "nothing to do with D179's claim")}


# ---------------------------------------------------------------------------- T5
def t5_oversize_only_when_alone() -> Dict[str, Any]:
    """5. An oversize deadline request is admitted ONLY when nothing else of its type is in flight
    AND it is b7-feasible.

    PENDING the allocator body, AND SPLIT BY REGISTER, which the report must carry. The
    `allowed()` signature has no feasibility argument, so the b7-feasible CONJUNCT IS NOT
    OBSERVABLE THROUGH THIS INTERFACE: it is enforced upstream, by the arm's own feasibility
    decision, before `allowed()` is consulted at all. What this check can test is the second
    conjunct - nothing else of its type in flight - in both directions:

        own type idle      an oversize ask is admitted
        own type in flight the same ask is denied

    If a later commit routes feasibility INTO `allowed()`, this check must grow a third condition.
    Until then the conjunction is tested by T6's predicate half plus the caller's own ordering,
    and this docstring is the record that T5 does not test it.
    """
    t = "assistance"
    oversize = int(SCAP.W_MAX_TOKENS) + 1          # larger than all of W_max, so certainly
    #                                                larger than any share
    alone = _tracker({"alert": 0, "recall": 0, "assistance": 0})
    ok_alone, why_alone = _allowed(qtype=t, uncached=oversize, kind=FG_KIND[t], tracker=alone,
                                   pending_by_type={t: 1}, weights_by_type={t: 1.0})
    busy = _tracker({t: 1, "alert": 0, "recall": 0})
    ok_busy, why_busy = _allowed(qtype=t, uncached=oversize, kind=FG_KIND[t], tracker=busy,
                                 pending_by_type={t: 2}, weights_by_type={t: 1.0})
    assert ok_alone, ("an oversize %s request was denied with nothing of its type in flight, so "
                      "it can never be sent at all; reason %r" % (t, why_alone))
    assert not ok_busy, ("an oversize %s request of %d tokens was admitted while %d tokens of its "
                         "own type were in flight; reason %r"
                         % (t, oversize, busy.w(t), why_busy))
    # a background request of the same size must NEVER get the oversize exemption: D179 (3)
    # chunks warms at 2,048 and they never exceed available share
    ok_bg, why_bg = _allowed(qtype=t, uncached=oversize, kind=BG_KIND[t], tracker=alone,
                             pending_by_type={t: 1}, weights_by_type={t: 1.0})
    assert not ok_bg, ("an oversize BACKGROUND %s request took the deadline exemption; D179 (3) "
                       "chunks warms and never lets them exceed available share; reason %r"
                       % (t, why_bg))
    return {"status": "GREEN", "type": t, "oversize_tokens": oversize,
            "own_type_idle": {"admitted": ok_alone, "reason": why_alone},
            "own_type_in_flight": {"admitted": ok_busy, "reason": why_busy},
            "background_same_size": {"admitted": ok_bg, "reason": why_bg},
            "_register": ("the b7-feasible CONJUNCT IS NOT TESTED HERE and cannot be: allowed() "
                          "takes no feasibility argument, so feasibility is the caller's and is "
                          "enforced before allowed() is reached. T6's predicate half covers the "
                          "predicate; the ordering is session B's"),
            "_what_would_fail_if_wrong": (
                "without the exemption an assistance request larger than its share could never be "
                "sent and that type would go to zero; with the exemption unguarded, two oversize "
                "requests of one type would be in flight together and W would exceed W_max, which "
                "is the one thing the capacity number means")}


# ---------------------------------------------------------------------------- T6
def t6a_recheck_predicate_is_reachable() -> Dict[str, Any]:
    """6a. The release re-check has a REACHABLE PATH, GREEN NOW.

    CLAUDE.md Step 0 asks whether the mechanism has a reachable path at this size and in this
    regime, before the run rather than after the null. D179 (4) re-checks b7 feasibility at the
    moment of RELEASE rather than only at arrival, so the mechanism only ever fires if a request
    can be feasible at arrival and infeasible at release. If that never happened the re-check
    would be UNEXERCISED - the classification E36, E36b and E36c earned - and would produce a null
    for a reason that has nothing to do with the policy.

    So this asserts the flip exists on the COMMITTED curve: b7's own rule is
    `recall_ttft_s(readiness_tokens, readiness) <= slack`
    (baselines/constructed.py B7EDFFeasibility.decide), and slack shrinks by exactly the time the
    request waited in the coordinator. With the committed recall deadline of 3.0 s and the
    measured median recall size, a hold of a fraction of a second is enough to flip it.
    """
    tokens = int(SCAP.FACTORS["recall"]["median_uncached"])
    deadline_s = SA.DEADLINE_S["recall"]
    flips: List[Dict[str, Any]] = []
    for readiness in ("GPU-WARM", "HOST-WARM", "COLD"):
        est = COSTS.recall_ttft_s(tokens, readiness)
        if not est < deadline_s:
            # infeasible even at arrival: b7 declines it at arrival and the re-check never sees it
            flips.append({"readiness": readiness, "est_ttft_s": round(est, 4),
                          "feasible_at_arrival": False, "flip_hold_s": None})
            continue
        hold = deadline_s - est            # the smallest hold that makes it infeasible
        assert est <= deadline_s + EPS, "arrival feasibility"
        assert est > deadline_s - hold - EPS, "release infeasibility after a %.3f s hold" % hold
        flips.append({"readiness": readiness, "est_ttft_s": round(est, 4),
                      "feasible_at_arrival": True, "flip_hold_s": round(hold, 4)})
    reachable = [f for f in flips if f["flip_hold_s"] is not None]
    assert reachable, (
        "no recall readiness is feasible at arrival on the committed curve, so the release "
        "re-check can never fire and D179 (4) would be UNEXERCISED, not a negative")
    return {"status": "GREEN", "tokens": tokens, "deadline_s": deadline_s,
            "predicate": ("costs.recall_ttft_s(readiness_tokens, readiness) <= slack_s, which is "
                          "b7's own rule in baselines/constructed.py"),
            "readiness_rows": flips,
            "smallest_flipping_hold_s": min(f["flip_hold_s"] for f in reachable),
            "_what_would_fail_if_wrong": (
                "if every request were infeasible at arrival, b7 would already decline it and the "
                "re-check would change nothing; if none could become infeasible, the re-check "
                "would never fire. Either way a null from the share cells would be an absent "
                "mechanism and not a finding about the policy")}


def t6b_recheck_skips_the_infeasible_request() -> Dict[str, Any]:
    """6b. The release re-check SKIPS an infeasible request: the observable effect.

    PENDING SESSION B's call site. Session B owns the mechanism; this tests its effect, which is
    that a deadline request found infeasible at the moment of release is NOT SENT. The observable
    is a counter and an absence: the release counter does not advance for that opportunity and the
    device answer stands.

    I cannot write the assertion against a hook that does not exist, and I will not write one
    against a name I guessed, because a check that greps for the wrong string passes for free -
    the reason `v6_harness_name_proof.py` carries a negative control. So this records WHAT SESSION
    B MUST EXPOSE for the check to be written, and stays PENDING until it exists. See the report.
    """
    needed = getattr(SA, "release_recheck", None)
    if needed is None:
        raise Pending(
            "session B's release re-check has no entry point yet. For this check to be written it "
            "needs: (i) a predicate callable, taking the request's predicted first-token time and "
            "its slack at the release instant, returning feasible/infeasible; and (ii) a counter "
            "incremented on each skip, distinguishable from an arrival-time b7 decline, so a "
            "release skip cannot be read as an arrival decline. Both named in arm_stats.")
    raise Pending("entry point appeared but this check has not been written against it")


# ---------------------------------------------------------------------------- T7
def t7a_epg_carry_forward_body() -> Dict[str, Any]:
    """7a. A skipped alert frame is carried by the NEXT request, at the level of the REQUEST BODY.

    GREEN NOW, AND IT ASSERTS ON THE BODY AND NOT ONLY ON A COUNT, which the task asked me to say
    either way. `bodies.build_body` puts the whole frame list on the request as
    `_live2["frame_refs"]` (bodies.py:241), so the check that the skipped frame is present in the
    next request is a check of the frame list itself. The uncached count is reported too, as
    corroboration rather than as the evidence: it must grow by exactly one frame's worth of
    tokens, `EPG_TOK_PER_FRAME`.

    WHY THIS IS THE MECHANISM AND NOT A RE-IMPLEMENTATION OF IT. D148's EP-G episode is
    APPEND-ONLY and the coordinator derives nothing: the frame list comes from the trace and ends
    at the current instant (coordinator.py:546-577, which raises if it does not). The uncached
    charge is `epg_prompt_tokens(n_new)` where `n_new` counts the frames NOT IN `_mon_sent`
    (coordinator.py:818-822), and `_mon_sent` only gains a frame when a request is RELEASED. So
    skipping the question at instant k leaves frame k out of the sent set, and instant k+1's
    episode list - which already contained frame k, by append-onlyness - charges it then. The
    carry-forward is a CONSEQUENCE of the two existing invariants, and this is what asserts them
    together.
    """
    refs = ["f%02d" % i for i in range(1, 6)]
    kw = dict(kind="monitor", device_id="dash-01", session_id=None, run_tag="t7",
              salt="t7", question=None, frames=[], dashcam_format="epg", defer_images=True,
              # `header` is required by the signature and is OVERWRITTEN for kind="monitor":
              # build_body replaces it with `monitor_header(len(frames), dashcam_format)`, which
              # is the count-free multi-frame literal. Passed empty so this fixture cannot be the
              # thing that decides the header.
              header="")

    def body(n: int, sent: set) -> Dict[str, Any]:
        frames = [dict(frame_ref=r, path=None if r in sent else Path("/nonexistent/%s" % r))
                  for r in refs[:n]]
        d = dict(kw)
        d["frames"] = frames
        # the EPISODE's whole prompt, which is what the coordinator passes as est_tokens
        d["est_tokens"] = B.epg_prompt_tokens(n)
        return B.build_body(**d)

    # instant 4 is RELEASED: frames 1 to 4 become sent
    sent_after_4 = set(refs[:4])
    b4 = body(4, set(refs[:3]))
    # instant 5's question is SKIPPED by the release re-check, so frame 5 is never sent
    # instant 6 does not exist in this fixture; instead compare the two possible instant-5 bodies
    b5_after_release = body(5, sent_after_4)
    b5_after_skip = body(5, set(refs[:3]))        # instant 4 skipped too: 4 and 5 both unsent

    assert b4["_live2"]["frame_refs"] == refs[:4], "the EP-G body carries the episode's frame list"
    assert refs[4] in b5_after_release["_live2"]["frame_refs"], (
        "the frame of the skipped instant must appear in the next request's own frame list")
    assert refs[3] in b5_after_skip["_live2"]["frame_refs"] and \
        refs[4] in b5_after_skip["_live2"]["frame_refs"], (
        "two consecutive skips must both be carried, not just the last")

    # the charge: n_new is the frames not yet sent, and one extra carried frame costs exactly one
    # frame's tokens
    n_new_release = sum(1 for r in refs[:5] if r not in sent_after_4)
    n_new_skip = sum(1 for r in refs[:5] if r not in set(refs[:3]))
    u_release = B.epg_prompt_tokens(n_new_release)
    u_skip = B.epg_prompt_tokens(n_new_skip)
    assert n_new_skip - n_new_release == 1, "one skipped instant leaves exactly one extra frame"
    assert u_skip - u_release == B.EPG_TOK_PER_FRAME, (
        "carrying one extra frame must cost exactly EPG_TOK_PER_FRAME = %d, got %d"
        % (B.EPG_TOK_PER_FRAME, u_skip - u_release))
    # the EPISODE's own prompt is unchanged by who sent what: the frame STAYS IN THE EPISODE,
    # which is the half of D179 (4) that is a promise about the task and not about latency
    assert b5_after_skip["fm_tokens"] == B.epg_prompt_tokens(5) == b5_after_release["fm_tokens"], (
        "the episode prompt differs between the skip and the release paths, so skipping the "
        "question changed the episode")
    assert b5_after_skip["_live2"]["frame_refs"] == b5_after_release["_live2"]["frame_refs"], (
        "the EPISODE is the same either way: skipping the question never drops the frame")
    # and the carried frame goes as BYTES, not as a uuid-only reference, because the engine never
    # received it: a reference to bytes the engine lacks is the silent failure 7b names
    parts = b5_after_skip["messages"][0]["content"]
    assert len(parts) >= 6, "an EP-G body of 5 frames carries a header and five image parts"

    return {"status": "GREEN",
            "asserted_on": ("the request BODY's _live2.frame_refs, not only the uncached count; "
                            "the count is reported as corroboration"),
            "episode_refs": refs[:5],
            "next_request_frame_refs": b5_after_skip["_live2"]["frame_refs"],
            "uncached_after_release": u_release, "uncached_after_skip": u_skip,
            "delta_tokens": u_skip - u_release, "epg_tok_per_frame": B.EPG_TOK_PER_FRAME,
            "_what_would_fail_if_wrong": (
                "if a skip dropped the frame, the episode would lose an instant permanently and "
                "the alert task would be answered off an incomplete episode - a QUALITY loss that "
                "no latency counter would show, and the exact thing D179 (4) promises not to do. "
                "If instead the skip marked the frame sent, the next request would reference bytes "
                "the engine never received")}


def t7b_recheck_skip_leaves_the_frame_unsent() -> Dict[str, Any]:
    """7b. The coordinator half of 7: a release skip must NOT add the frame to `_mon_sent`.

    PENDING SESSION B's call site, and this is the half that carries the risk. 7a proves that IF
    the frame is left unsent THEN the next request carries it. Whether session B's skip path leaves
    it unsent is session B's code, and the failure mode is silent in the worst way: marking the
    frame sent on a skip would make the next request reference bytes the engine never received, the
    body would still be well formed, the uncached charge would be LOWER - so every cost counter
    would look better - and only the answer would be wrong.
    """
    raise Pending(
        "needs session B's skip path. The check is: release one EP-G monitor at instant k, skip "
        "instant k+1 through the re-check, and assert the frame of k+1 is absent from the "
        "coordinator's `_mon_sent[device]` and present in instant k+2's `_live2.frame_refs` with "
        "its bytes (path not None). Session B need expose only that the skip returns without "
        "touching `_mon_sent`; the assertion is then readable off `co.epg_requests`.")


# ---------------------------------------------------------------------------- T8, mine
def t8_w_is_conserved() -> Dict[str, Any]:
    """8 (mine). W returns to zero and never goes negative, under adversarial interleavings,
    including the background accumulator.

    WHY I CHOSE THIS ONE. W is the resource every D179 decision divides, and a leak in it is the
    most silent failure available here. It raises nothing, prints nothing and fails no consistency
    check: W drifts upward over a 1,200 s cell, the allocator admits less and less, and the cell
    reports a plausible spread of lower admits that reads as "the shares are too tight" rather
    than as a bug. `share_admission.py`'s own docstring names the consequence - "W leaks upward and
    the allocator closes for good" - and session A already found and fixed one bug of exactly this
    shape in the background accumulator before anything was built on the interface. A quantity
    that is wrong by accumulation is the one a constant-versus-distribution check cannot see,
    because a drift IS a distribution.

    GREEN NOW: `WTracker` is implemented at the interface commit. The interleavings are the ones
    the coordinator will really produce, each a known way to break a stored-amount accumulator:
    a duplicate first-token, a settle after a first token, a settle with no first token, an
    unknown id, a zero-token request, a negative token count, and a foreground request completing
    while a background one of the same type is still in flight.
    """
    tr = SA.WTracker()
    trace: List[Dict[str, Any]] = []

    def snap(note: str) -> None:
        trace.append({"after": note, "w": {t: tr.w(t) for t in SA.TYPES},
                      "bg": {t: tr.w_background(t) for t in SA.TYPES},
                      "total": tr.total(), "tracked": tr.as_dict()["tracked_requests"]})
        for t in SA.TYPES:
            assert tr.w(t) >= 0, "W went negative for %s after %s" % (t, note)
            assert tr.w_background(t) >= 0, "background W went negative for %s after %s" % (t,
                                                                                            note)
            assert tr.w_background(t) <= tr.w(t), (
                "background W %d exceeds total W %d for %s after %s - the background share can "
                "never be more than the whole" % (tr.w_background(t), tr.w(t), t, note))

    # the bug session A caught: a large FOREGROUND request's first token must not clear the
    # background accumulator while a background request is still in flight
    tr.on_submit("bg1", "alert", 300, background=True)
    tr.on_submit("fg1", "alert", 3000, background=False)
    snap("one background and one large foreground alert in flight")
    assert tr.w("alert") == 3300 and tr.w_background("alert") == 300
    tr.on_first_token("fg1")
    snap("the large foreground reached first token")
    assert tr.w_background("alert") == 300, (
        "the foreground first token cleared the background accumulator: this is session A's own "
        "bug and it is back")
    assert tr.w("alert") == 300

    # idempotence and the settle paths
    tr.on_first_token("fg1")
    snap("duplicate first token for an id already removed")
    assert tr.w("alert") == 300, "a duplicate first token double-subtracted"
    tr.on_settled_without_first_token("fg1")
    snap("settle after first token, same id")
    assert tr.w("alert") == 300, "a settle after a first token double-subtracted"
    tr.on_first_token("never-submitted")
    snap("first token for an id never submitted")
    assert tr.w("alert") == 300

    # a request that dies before any content token must still leave W
    tr.on_submit("err1", "recall", 7000, background=False)
    snap("a recall submitted")
    tr.on_settled_without_first_token("err1")
    snap("that recall failed with no content token")
    assert tr.w("recall") == 0, "a request that never yielded a token leaked %d tokens" % tr.w(
        "recall")

    # degenerate amounts must not corrupt the accumulator
    tr.on_submit("zero", "assistance", 0, background=False)
    tr.on_submit("neg", "assistance", -500, background=False)
    snap("a zero-token and a negative-token submission")
    assert tr.w("assistance") == 0, "a negative uncached count moved W"
    tr.on_first_token("zero")
    tr.on_first_token("neg")

    # an unknown TYPE must be refused, not silently become a fourth bucket
    tr.on_submit("badtype", "not-a-type", 999, background=False)
    snap("a submission with an unknown type")
    assert tr.total() == 300, "an unknown type entered W: total is %d" % tr.total()

    # drain everything and require EXACT zero
    tr.on_first_token("bg1")
    snap("drained")
    assert tr.total() == 0, "W did not return to zero: %r" % tr.as_dict()
    assert all(tr.w_background(t) == 0 for t in SA.TYPES), "background W did not return to zero"
    assert tr.as_dict()["tracked_requests"] == 0, (
        "%d requests are still tracked after draining, so the per-request map leaks even where W "
        "does not" % tr.as_dict()["tracked_requests"])

    return {"status": "GREEN", "why_this_invariant": (
        "W is the resource every D179 decision divides and a leak in it is silent: it raises "
        "nothing, drifts upward over a cell, and reads as 'the shares are too tight' rather than "
        "as a bug. Session A already fixed one bug of this exact shape in the background "
        "accumulator"),
        "interleavings": [r["after"] for r in trace], "trace": trace,
        "_what_would_fail_if_wrong": (
            "a decrement that recomputed the amount instead of removing the stored one; a "
            "non-idempotent first-token hook; a settle path that double-subtracted; an unknown "
            "type creating a fourth bucket that no floor covers")}


CHECKS: List[Tuple[str, str, Callable[[], Dict[str, Any]]]] = [
    ("T1", "shares sum to W_max (floors plus flexible, exactly)", t1_shares_sum_to_wmax),
    ("T2", "floors are honoured under contention", t2_floors_honoured_under_contention),
    ("T3a", "the background classifier (load-bearing for T3b)", t3a_background_classifier),
    ("T3b", "background work never enters another type's floor",
     t3b_background_never_enters_another_floor),
    ("T4", "the borrowing path works, and is bounded by W_max", t4_borrowing_path),
    ("T5", "an oversize deadline request is admitted only when alone",
     t5_oversize_only_when_alone),
    ("T6a", "the release re-check has a reachable path", t6a_recheck_predicate_is_reachable),
    ("T6b", "the release re-check skips an infeasible request",
     t6b_recheck_skips_the_infeasible_request),
    ("T7a", "a skipped alert frame is carried by the next request (body level)",
     t7a_epg_carry_forward_body),
    ("T7b", "a release skip leaves the frame unsent (coordinator level)",
     t7b_recheck_skip_leaves_the_frame_unsent),
    ("T8", "W is conserved and never negative (mine)", t8_w_is_conserved),
]


# ---------------------------------------------------------------------------- the stub controls
# WHICH PENDING CHECKS WOULD ACTUALLY CATCH A WRONG BODY, proved and not asserted.
#
# A check that is PENDING today will run against session A's allocator tomorrow, and the thing I
# cannot know from a PENDING is whether it DISCRIMINATES: a check that admits anything the
# allocator says would go green against a wrong body just as happily. CLAUDE.md's seventh
# consistency check is the same point at experiment scale - validate the control, not only the
# result - and the port rule is its twin: a proof that an arm is legal and fairly treated does not
# establish that it does anything.
#
# So each allocator-dependent check is re-run against two DELIBERATELY WRONG allocators:
#
#   always-admit   admits every request. An allocator with no floors, no pool and no cap.
#   always-deny    denies every request. An allocator that closed.
#
# A check that passes under BOTH is not testing the allocator and is reported as such. These stubs
# are installed by monkeypatching `share_admission.allowed` inside this process only; nothing is
# written to session A's file.
STUBS = {
    "always-admit": lambda **kw: (True, "stub: admit everything"),
    "always-deny": lambda **kw: (False, "stub: deny everything"),
}
ALLOCATOR_CHECKS = ("T2", "T3b", "T4", "T5")


def _stub_controls() -> Dict[str, Any]:
    real = SA.allowed
    by_stub: Dict[str, Dict[str, str]] = {}
    try:
        for sname, stub in STUBS.items():
            SA.allowed = stub                                           # noqa: B010
            got: Dict[str, str] = {}
            for tid, _what, fn in CHECKS:
                if tid not in ALLOCATOR_CHECKS:
                    continue
                try:
                    fn()
                    got[tid] = "PASSED"
                except Pending as exc:                                  # pragma: no cover
                    got[tid] = "PENDING: %s" % exc
                except AssertionError as exc:
                    got[tid] = "CAUGHT: %s" % str(exc).splitlines()[0][:140]
                except Exception as exc:                                # noqa: BLE001
                    got[tid] = "ERROR %s: %s" % (type(exc).__name__, exc)
            by_stub[sname] = got
    finally:
        SA.allowed = real                                               # noqa: B010

    discriminating = {}
    for tid in ALLOCATOR_CHECKS:
        caught = [s for s, g in by_stub.items() if g.get(tid, "").startswith("CAUGHT")]
        discriminating[tid] = {"caught_by": caught,
                               "verdict": ("DISCRIMINATING" if caught else
                                           "NOT DISCRIMINATING: passes against a wrong body")}
    return {"_what": ("which PENDING checks would catch a wrong allocator body, proved by running "
                      "them against two deliberately wrong ones"),
            "stubs": {k: "admits everything" if k == "always-admit" else "denies everything"
                      for k in STUBS},
            "by_stub": by_stub, "per_check": discriminating,
            "all_discriminating": all(v["caught_by"] for v in discriminating.values())}


def main() -> int:
    rows: List[Dict[str, Any]] = []
    for tid, what, fn in CHECKS:
        try:
            r = dict(fn())
        except Pending as exc:
            r = {"status": "PENDING", "reason": str(exc)}
        except Exception:                                               # noqa: BLE001
            r = {"status": "FAIL", "traceback": traceback.format_exc().splitlines()[-6:]}
        r["id"] = tid
        r["what"] = what
        rows.append(r)

    green = [r["id"] for r in rows if r["status"] == "GREEN"]
    pending = [r["id"] for r in rows if r["status"] == "PENDING"]
    failed = [r["id"] for r in rows if r["status"] == "FAIL"]
    out = {
        "_what": "the D179 (6b) unit tests for share admission and deadline-aware release",
        "_runner": ("a plain script, because pytest is NOT installed in the fmtk env. Explicit "
                    "pass/fail summary, non-zero exit on any FAIL"),
        "_register": ("PENDING IS NOT A PASS. A check whose mechanism does not exist has not "
                      "tested the claim (CLAUDE.md Rule 1 in its test-side form), so the counts "
                      "are kept separate and PENDING is never folded into GREEN"),
        "interface_commit": "f3482026 experiments/orchestration/live2/share_admission.py",
        "capacity": SCAP.as_dict(),
        "checks": rows,
        "green": green, "pending": pending, "failed": failed,
        "counts": {"green": len(green), "pending": len(pending), "failed": len(failed)},
        "stub_controls": _stub_controls(),
    }
    out["verdict"] = ("FAIL: %s" % failed if failed else
                      "NO_FAILURES: %d green, %d pending a body that is not landed"
                      % (len(green), len(pending)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    for r in rows:
        line = "  %-4s %-8s %s" % (r["id"], r["status"], r["what"])
        print(line)
        if r["status"] == "PENDING":
            print("         reason: %s" % r["reason"][:160])
        if r["status"] == "FAIL":
            for t in r["traceback"]:
                print("         %s" % t)
    sc = out["stub_controls"]
    print("  stub controls (would a wrong allocator body be caught?)")
    for tid, v in sc["per_check"].items():
        print("    %-4s %-18s caught by %s" % (tid, v["verdict"].split(":")[0], v["caught_by"]))
    print(out["verdict"])
    print("wrote", OUT)
    return 1 if (failed or not sc["all_discriminating"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
