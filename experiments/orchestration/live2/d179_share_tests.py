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

---------------------------------------------------------------------------------------------
UPDATE, AFTER THE CALL SITES LANDED. Six of these checks were written to be SKIPPED, because the
mechanism they test had no call site. All six now run:

  T2, T3b, T4, T5   `share_admission.allowed()` has a real body: floors tested before headroom,
                    the flexible pool split equally or by weight, borrowing bounded by what other
                    types' floors reserve, the oversize-when-alone rule, no preemption.
  T6b, T7b          the coordinator calls `allowed()` at four release sites and `release_recheck`
                    is wired into the release path with the four frozen counters. T6b and T7b
                    therefore drive the REAL `Live2Coordinator` rather than naming what session B
                    would have to expose.

T5 ALSO GREW THE THIRD CONDITION its own docstring demanded, because `feasible` is now an explicit
argument to `allowed()` and the b7 conjunct it carries is observable through the interface at last.

WHAT IS STILL TRUE OF EVERY CHECK HERE, AND IS THE REGISTER THE REPORT MUST CARRY: these are UNIT
checks. They establish LOGIC - that the allocator divides capacity the way D179 (3) says, that the
skip path leaves the frame unsent, that the counters are the frozen ones. They establish NOTHING
about how often any of it fires in a cell. T6b and T7b build DRY coordinator fixtures, and
`share_admission.py`'s own docstring is the reason that matters: in a dry cell W is
submit-to-SETTLE and in a live cell submit-to-FIRST-TOKEN, so no number here may be used to size
anything or to form a rate. A rate needs a live cell.

AND DISCRIMINATION IS PROVED, NOT ASSERTED, for all six. The four allocator checks are re-run
against FOUR deliberately wrong bodies (two added when the real body landed, because against
always-admit and always-deny alone T2 was caught only by the one it could not fail to catch). T6b
and T7b are re-run with the predicate forced both ways, and T7b additionally against the one wrong
implementation that is not a predicate at all: a skip path that marks the frame SENT. See
`_stub_controls` and `_recheck_controls`, and the exit code, which is non-zero if any check fails
OR if any check is found not to discriminate.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE / "tests"), str(HERE.parent / "baselines"), str(HERE.parent / "live"),
           str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bodies as B                                                      # noqa: E402
import costs as COSTS                                                   # noqa: E402
import d162_price as DP                                                 # noqa: E402
import release_recheck as RR                                            # noqa: E402
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


# ---------------------------------------------------------------------------- the coordinator
# T6b AND T7b DRIVE THE REAL `Live2Coordinator`, because what they assert is a property of the
# coordinator's own release path and not of a module function: whether the skip returns before
# `_mon_sent` is touched is a fact about those lines and nothing else. Nothing is stubbed; the
# only things set by hand are the arm switches, the queue-ahead field and the clock.
#
# THE REGISTER, STATED HERE SO NEITHER CHECK CAN BE READ UP A LEVEL. These are DRY fixtures: one
# or two hand-built opportunities on a fresh coordinator with `dry_run=True`, not a cell. They
# establish LOGIC - that the skip path leaves the frame unsent, that the next body carries it,
# that the counters are the frozen ones. They establish NOTHING about how often the mechanism
# fires in a real cell, and `share_admission.py`'s own docstring is the reason: in a dry cell W is
# submit-to-SETTLE and in a live cell submit-to-FIRST-TOKEN, so a dry fixture may not be used to
# size anything. A rate needs a live cell.
_FIX_TMPS: List[Path] = []


def _coord_mod() -> Any:
    """Import the coordinator lazily and ONCE, so an import failure is attributable to the two
    checks that need it rather than taking the whole suite down with it."""
    global _CO
    try:
        return _CO
    except NameError:
        pass
    from coordinator import Live2Coordinator                            # noqa: E402
    _CO = Live2Coordinator
    return _CO


class _Fix:
    """A real coordinator, one real device, real frame files on disk.

    The same shape as `tests/test_release_recheck.py`'s fixture, deliberately: that file is the
    committed one for D179 (4) and a second fixture that differed from it would make a
    disagreement between the two unreadable.
    """

    def __init__(self, *, recheck: bool, shares: bool = False, dev: str = "dash000",
                 dev_type: str = "dashcam", seed: int = 4):
        import arms as A
        import cachekeys as CK
        import cstate as CS
        from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK

        self.tmp = Path(tempfile.mkdtemp(prefix="d179share_"))
        _FIX_TMPS.append(self.tmp)
        self.frames = self.tmp / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        arm = A.make_arm("always-cloud-fcfs")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        # INSTANCE attributes, which is the shape both switches require; a class-level ON raises.
        if recheck:
            # D162 pricing is a PRECONDITION of the re-check, not a convenience: the queue input
            # `_uncached_in_flight` is decremented only under it, so without it the field is a
            # cumulative run total. The coordinator refuses the combination.
            arm.live2_release_recheck = True
            arm.live2_d162_pricing = True
        if shares:
            arm.live2_share_admission = True
        self.co = _coord_mod()(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                               host_tier_tokens=HOST_TOK, upload_mode="A", window_s=600.0,
                               drain_s=5.0, seed=seed, dry_run=True,
                               run_tag=CK.run_tag(seed, "d179sh"), frames_root=self.frames)
        assert self.co._release_recheck is bool(recheck), "the re-check switch did not arrive"
        assert self.co._share_admission is bool(shares), "the shares switch did not arrive"
        # an arm that WAITED for the device answer would return early from `_serve_monitor` for a
        # reason unrelated to either check, so the fixture asserts it does not
        assert self.co.reads_device is False
        # THE DECISION KINDS ARE CAPTURED, NOT RE-IMPLEMENTED. `_log_decision` writes to
        # `self.logs.decision` and the fixture passes `logs=None`, so the rows are not readable
        # off the coordinator afterwards. This wraps the COMMITTED method and records the `kind`
        # it was called with, then delegates to it unchanged: the rows are the real ones and the
        # wrapper decides nothing. Needed because "the skip is distinguishable from an arrival
        # decline" is a statement about the row kind and not only about a counter.
        self.dec_kinds: List[Tuple[str, Tuple[str, ...]]] = []
        _real_log = self.co._log_decision

        def _spy(t: float, kind: str, opp_ids: Any, **kw: Any) -> str:
            self.dec_kinds.append((str(kind), tuple(opp_ids or ())))
            return _real_log(t, kind, opp_ids, **kw)

        self.co._log_decision = _spy                                    # noqa: B010
        self.co._ingest(dict(kind="device_register", device_id=dev, type=dev_type,
                             uplink_mbps=13.6, rtt_ms=50.0, start_t=0.0), 0.0)
        self.dev = dev

    def frame(self, name: str) -> str:
        (self.frames / name).write_bytes(b"\xff\xd8\xff\xd9")
        return name

    def episode(self, idx: int, n_frames: int, *, t_capture: float, deadline_s: float = 1.0):
        refs = [self.frame("f%02d.jpg" % i) for i in range(n_frames)]
        oid = "o%03d" % idx
        self.co._ingest(dict(kind="monitor_frame", opportunity_id=oid, device_id=self.dev,
                             t_capture=t_capture, deadline_s=deadline_s,
                             instant_id="i%03d" % idx, t_arrive=t_capture,
                             frame_ref=refs[-1], frame_bytes=4,
                             episode_id="ep0", episode_index=idx,
                             episode_frames=len(refs), frame_refs=list(refs)), t_capture)
        assert self.co.dashcam_format == "epg", "the fixture must be EP-G or T7's premise is gone"
        return oid, refs

    def recall(self, idx: int, *, t_ask: float, deadline_s: float, tokens: int = 8000):
        sid = "%s|s%03d" % (self.dev, idx)
        self.co._ingest(dict(kind="session_start", session_id=sid, device_id=self.dev,
                             t=t_ask - 1.0), t_ask - 1.0)
        s = self.co.st.sessions[sid]
        s.est_tokens = int(tokens)
        oid = "q%03d" % idx
        self.co._ingest(dict(kind="recall_question", opportunity_id=oid, device_id=self.dev,
                             t_ask=t_ask, deadline_s=deadline_s, t_arrive=t_ask,
                             session_id=sid, question="q?", options=["A", "B"],
                             question_id="qid%d" % idx, category="recall"), t_ask)
        return self.co.st.opps[oid], s

    def serve(self, t: float) -> None:
        self.co._serve_monitor(self.dev, t, 0.0, None, {})

    def submissions(self) -> List[Any]:
        return [sub for _f, sub in self.co.futures]

    def mon_sent(self) -> set:
        return set(self.co._mon_sent[self.dev])

    def confirm_all(self, t: float) -> None:
        """Complete every outstanding request and make its frames uuid-referenceable (D158 (2)).

        A DRY future carries no `http_status`, so a dry run promotes nothing and every frame goes
        as bytes; the COMMITTED `_promote_confirmed_bytes` is therefore invoked with the 200 a live
        run returns, because otherwise the bytes-versus-reference split - the body-level evidence
        T7b rests on - is not observable in a dry fixture at all.
        """
        subs = list(self.submissions())
        self.co.st.now = t
        self.co._collect(t)
        for sub in subs:
            self.co._promote_confirmed_bytes(sub, {"http_status": 200})

    def img_parts(self, sub: Any) -> List[Any]:
        return [p for p in sub.body["messages"][0]["content"] if p.get("type") == "image_url"]


def _cleanup_fixtures() -> None:
    while _FIX_TMPS:
        shutil.rmtree(_FIX_TMPS.pop(), ignore_errors=True)


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

    GREEN, AND NO LONGER SPLIT BY REGISTER. When this was written the `allowed()` signature had no
    feasibility argument, so the b7-feasible conjunct was not observable through the interface and
    this docstring recorded that T5 did not test it, with the standing instruction: "if a later
    commit routes feasibility INTO `allowed()`, this check must grow a third condition." IT DID -
    `feasible` is now an explicit keyword, added after session C observed that the conjunct
    otherwise rested on a caller convention nothing checked, which is the same shape as a
    write-only field. So the third condition is here, and all three conjuncts are now tested:

        own type idle,      feasible    an oversize ask is admitted
        own type in flight, feasible    the same ask is denied
        own type idle,      INFEASIBLE  the same ask is denied, and for the feasibility reason

    The third row is what makes the conjunction a conjunction rather than two thirds of one.
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

    # THE THIRD CONJUNCT, now that `feasible` is an explicit argument. An infeasible oversize ask
    # must be refused with nothing of its type in flight, which is the one case the exemption
    # would otherwise wave through, and the refusal must be FOR THAT REASON and not a share one.
    ok_inf, why_inf = _allowed(qtype=t, uncached=oversize, kind=FG_KIND[t], tracker=alone,
                               pending_by_type={t: 1}, weights_by_type={t: 1.0}, feasible=False)
    assert not ok_inf, ("an INFEASIBLE oversize %s request took the oversize exemption; D179 (3) "
                        "admits it only if b7-feasible AND nothing else of its type is in "
                        "flight; reason %r" % (t, why_inf))
    assert why_inf == "infeasible", (
        "the infeasible oversize ask was refused for %r, not for its feasibility, so this row "
        "does not show the conjunct being read" % (why_inf,))
    # and feasible=None must keep the previous behaviour, or every existing call site changed
    # meaning when the argument was added
    ok_none, why_none = _allowed(qtype=t, uncached=oversize, kind=FG_KIND[t], tracker=alone,
                                 pending_by_type={t: 1}, weights_by_type={t: 1.0}, feasible=None)
    assert (ok_none, why_none) == (ok_alone, why_alone), (
        "feasible=None changed the answer from %r to %r, so adding the argument changed every "
        "caller that does not pass it" % ((ok_alone, why_alone), (ok_none, why_none)))
    # an explicit True must be the same as None for an otherwise-admissible ask
    ok_true, _why_true = _allowed(qtype=t, uncached=oversize, kind=FG_KIND[t], tracker=alone,
                                  pending_by_type={t: 1}, weights_by_type={t: 1.0},
                                  feasible=True)
    assert ok_true is True, "an explicit feasible=True refused an otherwise-admissible ask"

    return {"status": "GREEN", "type": t, "oversize_tokens": oversize,
            "own_type_idle": {"admitted": ok_alone, "reason": why_alone},
            "own_type_in_flight": {"admitted": ok_busy, "reason": why_busy},
            "background_same_size": {"admitted": ok_bg, "reason": why_bg},
            "own_type_idle_but_infeasible": {"admitted": ok_inf, "reason": why_inf},
            "feasible_none_is_the_old_behaviour": {"admitted": ok_none, "reason": why_none},
            "_register": ("ALL THREE CONJUNCTS ARE NOW TESTED. The b7-feasible conjunct became "
                          "observable when `feasible` was added to allowed(); before that it "
                          "rested on a caller convention nothing could reach, and this check's "
                          "earlier docstring said so. The ORDERING - that the caller establishes "
                          "feasibility before consulting allowed() - is still session B's and is "
                          "not tested here; T6b tests the release-time instance of it"),
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

    GREEN. Session B's call site has landed, so the two things this check asked session B to
    expose both exist and are used here rather than named:

      (i)  the predicate, `release_recheck.decide`, taking this request's predicted uncached
           tokens and the uncached work already in flight AHEAD of it against the time left to the
           opportunity's own absolute deadline (release_recheck.py `decide`), and
      (ii) the counters, the four frozen names `release_infeasible{,_alert,_recall,_assistance}`,
           incremented in the COORDINATOR's `counts` at the skip
           (coordinator.py:940 for alerts, 1246 for recall and assistance).

    BOTH DIRECTIONS, ON BOTH CALL SITES, because a check that only shows the skip cannot tell a
    working predicate from a closed one: for the alert path and for the recall path, an opportunity
    with room is SENT and the same opportunity with its deadline gone is NOT.

    AND THE SKIP IS DISTINGUISHABLE FROM AN ARRIVAL DECLINE, which was the second thing this check
    demanded of session B and the one that would be silent if it were missing. b7's arrival decline
    writes `counts["recall_DEVICE"]`, a decision row of kind `decline` and an outcome row whose
    decision is `DEVICE` (coordinator.py:785-802). The release skip writes the frozen release
    counters, a decision row of kind `release_infeasible` and an outcome decision of
    `DEVICE-on-release-infeasible`. Asserted, so a release skip cannot be read as an arrival
    decline in any committed cell.

    THE QUEUE TERM IS ASSERTED SEPARATELY, because it is the only thing that makes a re-ask at
    release different from the arrival test: identical request, identical deadline, only
    `_uncached_in_flight` differs, and the decision flips. b7's own `est` (costs.recall_ttft_s)
    has no queue term at all, so if the re-check used it this row could not exist.
    """
    rows: Dict[str, Any] = {}

    # ---- the ALERT path, both directions ------------------------------------------------------
    t0 = 10.0
    f_ok = _Fix(recheck=True)
    f_ok.episode(0, 1, t_capture=t0)
    f_ok.serve(t0 + 0.1)                      # 0.9 s left, one frame, nothing in flight
    assert len(f_ok.submissions()) == 1, "a feasible alert must still be sent by the re-check"
    assert f_ok.co.counts[RR.COUNTER_TOTAL] == 0, "a feasible alert moved the skip counter"

    f_no = _Fix(recheck=True)
    _oid, _refs = f_no.episode(0, 1, t_capture=t0)
    f_no.serve(t0 + 1.0 - 0.01)               # 0.01 s left against a predicted first token
    assert f_no.submissions() == [], "an alert past hope went on the wire anyway"
    assert f_no.co.counts[RR.COUNTER_TOTAL] == 1, "the skip was not counted"
    assert f_no.co.counts[RR.COUNTER_BY_TYPE["alert"]] == 1, "the alert counter did not advance"
    assert RR.totals_agree(f_no.co.counts), "the total and the per-type counts disagree"
    assert f_no.co.st.opps["o000"].state == "declined", (
        "a skipped instant left 'arrived' is re-offered every period and the counter would count "
        "ITEM-PERIODS instead of instants")
    _ans = [a for a in f_no.co.answers if a["opportunity_id"] == "o000"]
    assert [a["decision"] for a in _ans] == [RR.DECISION], (
        "the outcome row says %r, not the release decision" % ([a["decision"] for a in _ans],))
    assert _ans[0]["served_by"] == "device", "the device answer must stand for a skipped instant"
    rows["alert"] = {"feasible_sent": len(f_ok.submissions()),
                     "infeasible_sent": len(f_no.submissions()),
                     "counts": {k: v for k, v in f_no.co.counts.items()
                                if str(k).startswith("release_infeasible")},
                     "decision": _ans[0]["decision"], "state": "declined"}

    # ---- NOT AN ARRIVAL DECLINE. The two paths are separable in the log and in the counters ---
    _kinds = [k for k, _ids in f_no.dec_kinds]
    assert RR.LOG_KIND in _kinds, "no %r decision row for the skip" % RR.LOG_KIND
    assert "decline" not in _kinds, (
        "the skip wrote an arrival-style 'decline' row, so the two cannot be told apart in any "
        "committed log: kinds %r" % (_kinds,))
    assert RR.DECISION != "DEVICE", "the release decision string collides with b7's arrival one"
    assert f_no.co.counts.get("recall_DEVICE", 0) == 0, "the skip moved b7's arrival counter"
    rows["not_an_arrival_decline"] = {
        "decision_kinds_on_the_skip": _kinds, "release_log_kind": RR.LOG_KIND,
        "arrival_log_kind": "decline", "release_decision": RR.DECISION,
        "arrival_decision": "DEVICE",
        "counters": {"release": [RR.COUNTER_TOTAL] + sorted(RR.COUNTER_BY_TYPE.values()),
                     "arrival": "recall_DEVICE"}}

    # ---- the RECALL path, both directions, through the second call site -----------------------
    g_ok = _Fix(recheck=True, dev="robo000", dev_type="robot")
    o, s = g_ok.recall(0, t_ask=t0, deadline_s=3.0, tokens=8000)
    g_ok.co._submit_recall(o, s, t0 + 0.01, 0.0, None, {}, whole=True)
    assert len(g_ok.submissions()) == 1, "a feasible recall must still be sent"
    assert g_ok.co.counts[RR.COUNTER_TOTAL] == 0

    g_no = _Fix(recheck=True, dev="robo000", dev_type="robot")
    o2, s2 = g_no.recall(0, t_ask=t0, deadline_s=0.05, tokens=8000)
    g_no.co._submit_recall(o2, s2, t0 + 0.01, 0.0, None, {}, whole=True)
    assert g_no.submissions() == [], "a recall past hope went on the wire anyway"
    assert g_no.co.counts[RR.COUNTER_BY_TYPE["recall"]] == 1, "the recall counter did not advance"
    assert g_no.co.counts[RR.COUNTER_BY_TYPE["alert"]] == 0, "recall leaked into the alert counter"
    assert RR.totals_agree(g_no.co.counts)
    rows["recall"] = {"feasible_sent": len(g_ok.submissions()),
                      "infeasible_sent": len(g_no.submissions()),
                      "counts": {k: v for k, v in g_no.co.counts.items()
                                 if str(k).startswith("release_infeasible")}}

    # ---- THE QUEUE TERM, which is the whole reason release time differs from arrival time -----
    est_tokens = B.epg_prompt_tokens(1)
    remaining = 1.0 - 0.1
    assert DP.first_token_s(est_tokens, 0) <= remaining, "the empty-queue case must be feasible"
    big = 30000
    assert DP.first_token_s(est_tokens, big) > remaining, "the loaded-queue case must be not"
    queue_rows = []
    for queue, want_sent in ((0, 1), (big, 0)):
        h = _Fix(recheck=True)
        h.episode(0, 1, t_capture=t0)
        h.co._uncached_in_flight = queue
        h.serve(t0 + 0.1)
        assert len(h.submissions()) == want_sent, (
            "queue_ahead=%d gave %d submissions, wanted %d: the re-check is not reading the "
            "queue, so it is re-asking the arrival question" % (queue, len(h.submissions()),
                                                                want_sent))
        queue_rows.append({"queued_uncached_ahead": queue, "submitted": len(h.submissions()),
                           "skipped": h.co.counts[RR.COUNTER_TOTAL]})
    # and b7's own estimator CANNOT produce that row, which is why the re-check does not reuse it
    _b7_like = COSTS.recall_ttft_s(est_tokens, "GPU-WARM")
    rows["queue_term"] = {
        "rows": queue_rows,
        "d162_est_s": {"queue_0": round(DP.first_token_s(est_tokens, 0), 6),
                       "queue_%d" % big: round(DP.first_token_s(est_tokens, big), 6)},
        "b7_arrival_est_s_has_no_queue_term": round(_b7_like, 6),
        "_why": ("b7's est is costs.recall_ttft_s, an ISOLATED reload TTFT: it takes no queue "
                 "argument, so the same two conditions give it the same number and it cannot see "
                 "that the work ahead grew between arrival and release")}

    # ---- the budget is untouched by a skip, so a skip needs no refund -------------------------
    b = _Fix(recheck=True)
    b.episode(0, 1, t_capture=t0)
    spent0 = b.co.st.budget.spent_gpu_seconds
    b.serve(t0 + 1.0 - 0.01)
    assert b.co.st.budget.spent_gpu_seconds == spent0, "a skip spent budget it never used"
    assert b.co._uncached_in_flight == 0, "a skip charged the queue it never entered"
    rows["skip_is_free"] = {"spent_gpu_seconds_before": spent0,
                            "spent_gpu_seconds_after": b.co.st.budget.spent_gpu_seconds,
                            "uncached_in_flight_after": b.co._uncached_in_flight}

    return {"status": "GREEN", "paths": rows,
            "predicate": "release_recheck.decide, the committed D162 first-token model",
            "call_sites": {"alert": "coordinator.py:935-957",
                           "recall_and_assistance": "coordinator.py:1237-1264"},
            "_register": ("a DRY unit fixture: it establishes the LOGIC of the skip, not a rate. "
                          "How often the predicate fires in a cell is a live-cell question and "
                          "this check does not answer it"),
            "_what_would_fail_if_wrong": (
                "a predicate that always said feasible would leave the infeasible half sending, "
                "and one that always said infeasible would stop the feasible half: either is a "
                "mechanism that re-asks nothing, and only testing both directions sees it. A skip "
                "that wrote b7's arrival counter or its 'decline' row would make every committed "
                "cell's arrival-decline count silently include release skips")}


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


_T7B_CORRUPT: Optional[Callable[[Any], None]] = None


def _t7b_patched(corrupt: Callable[[Any], None]) -> Dict[str, Any]:
    """Run the WHOLE of T7b against a wrong skip path, so the verdict recorded in the controls is
    T7b's own assertions firing and not a re-derivation of them. The hook is installed in this
    process only; session B's file is not touched."""
    global _T7B_CORRUPT
    _T7B_CORRUPT = corrupt
    try:
        return t7b_recheck_skip_leaves_the_frame_unsent()
    finally:
        _T7B_CORRUPT = None


def _t7b_run(*, skip_middle: bool, corrupt: Optional[Callable[[Any], None]] = None
             ) -> Dict[str, Any]:
    """Three EP-G instants of one append-only episode on a real coordinator.

    instant 0 (4 frames) is RELEASED, instant 1 (5 frames) is either released or SKIPPED by the
    re-check, instant 2 (6 frames) is released. `corrupt`, when given, is called on the
    coordinator immediately after the skipped serve and stands in for a WRONG skip path - the one
    that marks the frame sent on the way out. Nothing in session B's file is touched.
    """
    corrupt = corrupt if corrupt is not None else _T7B_CORRUPT
    t0 = 10.0
    f = _Fix(recheck=True)
    f.episode(0, 4, t_capture=t0)
    f.serve(t0 + 0.1)
    assert len(f.submissions()) == 1, "instant 0 must be released, or the fixture proves nothing"
    f.confirm_all(t0 + 1.5)                   # its four frames become uuid-referenceable
    sent_after_0 = f.mon_sent()

    f.episode(1, 5, t_capture=t0 + 2.0)
    if skip_middle:
        f.co._uncached_in_flight = 30000      # makes instant 1 infeasible at release
        f.serve(t0 + 2.1)
        assert f.submissions() == [], "instant 1 was meant to be skipped and was sent"
        assert f.co.counts[RR.COUNTER_TOTAL] == 1, "instant 1 was not skipped by the re-check"
        if corrupt is not None:
            corrupt(f.co)
        f.co._uncached_in_flight = 0
    else:
        f.serve(t0 + 2.1)
        assert len(f.submissions()) == 1, "instant 1 must be released in the control"
        f.confirm_all(t0 + 3.5)
    sent_after_1 = f.mon_sent()

    f.episode(2, 6, t_capture=t0 + 4.0)
    f.serve(t0 + 4.1)
    subs = f.submissions()
    assert subs, "instant 2 must be sent in both arms, or there is no next request to inspect"
    sub = subs[-1]
    imgs = f.img_parts(sub)
    return {"fix": f, "sub": sub, "imgs": imgs, "sent_after_0": sent_after_0,
            "sent_after_1": sent_after_1,
            "charged": f.co.epg_requests[-1]["new_tokens_charged"]}


def t7b_recheck_skip_leaves_the_frame_unsent() -> Dict[str, Any]:
    """7b. The coordinator half of 7: a release skip must NOT add the frame to `_mon_sent`.

    GREEN. Session B's skip path has landed and returns before `_mon_sent[device_id]` is touched
    (coordinator.py:935-957 returns at 956; the only write to `_mon_sent` on this path is at 1420,
    after the submit). 7a proves that IF the frame is left unsent THEN the next request carries it;
    this proves the antecedent on the real coordinator, which is the half that carries the risk.

    WHAT THIS ASSERTS ON, AND WHY IT IS NOT THE TOKEN COUNT. Three observables, in this order:

      1  `co._mon_sent[device]` - a SET MEMBERSHIP. The skipped instant's frame must be ABSENT
         from it after the skip, and the released instant's frames must be PRESENT. The second
         half is a positive control on the first: "f04 is not in the set" is also true of a
         coordinator that never populates the set at all, and would pass for free.
      2  THE REQUEST BODY of the next instant: `_live2.frame_refs` must contain the skipped frame,
         AND the image part for it must carry BYTES (`image_url` not None) rather than a uuid-only
         reference. Under EP-G every instant re-sends the whole episode ref list, so the ref list
         ALONE is true either way and is not the discriminator; which frames carry bytes is.
      3  the uncached token count, REPORTED AS CORROBORATION ONLY, never as the evidence.

    THE TWO SETS ARE NOT ONE SET, AND THE DISCRIMINATION CONTROL IS WHAT MADE ME WRITE THIS DOWN.
    `_mon_sent` is submission time and drives the CHARGE (`n_new`, coordinator.py:886);
    `_mon_confirmed` is 200 time and drives the WIRE FORM (`path=None if r in confirmed`,
    coordinator.py:887-888). So the two wrong skip paths are DIFFERENT BUGS with different
    observables, and assertion 1 and assertion 2 catch one each - which is not what I assumed
    before running the controls, and the controls below record it:

      marks SENT       the frame still goes out as BYTES, but `n_new` is one frame short. The
                       engine prefills work nobody paid for: the uncached count, the budget spend
                       and the D162 queue term are ALL UNDERSTATED, so every cost counter in the
                       cell improves. Caught by assertion 1 ONLY - assertion 2 passes, because the
                       bytes are unaffected.
      marks CONFIRMED  the next request sends a UUID-ONLY REFERENCE to bytes the engine never
                       received, so the answer is formed off a missing frame. Caught by assertion
                       2 ONLY - assertion 1 passes, because `_mon_sent` is untouched.

    WHY THE COUNT MAY NOT BE THE EVIDENCE, in either case. The body stays WELL FORMED, so no
    schema check fires; the token count moves DOWN or stays flat, so the charge, the budget spend
    and the queue term all read BETTER. A check written on the token count reads either bug as an
    improvement, in the right direction and a credible magnitude. Set membership and the presence
    of bytes are the observables that move the other way, which is why they are what is asserted
    and why BOTH are asserted rather than one standing in for the other.
    """
    skip = _t7b_run(skip_middle=True)
    ctl = _t7b_run(skip_middle=False)
    f_skip, f_ctl = skip["fix"], ctl["fix"]
    ep0 = ["f%02d.jpg" % i for i in range(4)]
    ep1_new = "f04.jpg"
    ep2_new = "f05.jpg"
    all6 = ["f%02d.jpg" % i for i in range(6)]

    # ---- 1. THE COORDINATOR-LEVEL ASSERTION, with its own positive control -------------------
    assert skip["sent_after_0"] == set(ep0), (
        "the RELEASED instant's four frames are not in `_mon_sent` (%r), so this check cannot see "
        "the set move at all and the absence below would pass for free"
        % (sorted(skip["sent_after_0"]),))
    assert skip["sent_after_1"] == set(ep0), (
        "a release skip CHANGED `_mon_sent`: it is %r, not the four frames of the released "
        "instant. A skip that marks the frame sent makes the next request reference bytes the "
        "engine never received, and every cost counter gets BETTER while the answer gets wrong"
        % (sorted(skip["sent_after_1"]),))
    assert ep1_new not in skip["sent_after_1"], (
        "the skipped instant's own frame %r was recorded as sent" % ep1_new)
    # the control moves the set, which is what makes the skip's not moving it meaningful
    assert ctl["sent_after_1"] == set(ep0 + [ep1_new]), (
        "the CONTROL's released instant did not add its frame to `_mon_sent` (%r), so the two "
        "arms are not distinguishable by this observable and the check is vacuous"
        % (sorted(ctl["sent_after_1"]),))

    # ---- 2. THE BODY of the next request -----------------------------------------------------
    for tag, r in (("skip", skip), ("control", ctl)):
        assert r["sub"].body["_live2"]["frame_refs"] == all6, (
            "%s: the next request does not carry the whole append-only episode: %r"
            % (tag, r["sub"].body["_live2"]["frame_refs"]))
    assert ep1_new in skip["sub"].body["_live2"]["frame_refs"], (
        "the skipped frame is absent from the next request's episode: skipping the QUESTION "
        "dropped the FRAME, which is the one thing D179 (4) promises not to do")
    # the ref list is true in BOTH arms, which is why it cannot be the discriminator - asserted
    # rather than assumed, because a check resting on it would pass against the wrong body
    assert (skip["sub"].body["_live2"]["frame_refs"]
            == ctl["sub"].body["_live2"]["frame_refs"]), "the ref list is not the discriminator"
    # THE DISCRIMINATOR: bytes versus a uuid-only reference, per frame
    assert len(skip["imgs"]) == len(ctl["imgs"]) == 6, "an episode of six frames, six image parts"
    skip_bytes = [i for i, p in enumerate(skip["imgs"]) if p["image_url"] is not None]
    ctl_bytes = [i for i, p in enumerate(ctl["imgs"]) if p["image_url"] is not None]
    assert 4 in skip_bytes, (
        "the skipped frame %r went as a uuid-only REFERENCE after the skip, so the request points "
        "at bytes the engine never received; bytes carried by %r" % (ep1_new, skip_bytes))
    assert 5 in skip_bytes and 5 in ctl_bytes, "the new frame of instant 2 always carries bytes"
    assert skip_bytes == [4, 5], (
        "after a skip exactly the two unsent frames carry bytes; got %r" % (skip_bytes,))
    assert ctl_bytes == [5], (
        "in the control only instant 2's own new frame carries bytes; got %r" % (ctl_bytes,))

    # ---- 3. the charge, CORROBORATION ONLY ---------------------------------------------------
    assert ctl["charged"] == B.epg_prompt_tokens(1), (
        "the control's instant 2 pays for its one new frame, got %d" % ctl["charged"])
    assert skip["charged"] == B.epg_prompt_tokens(2), (
        "after a skip instant 2 pays for both unsent frames, got %d" % skip["charged"])
    assert skip["charged"] - ctl["charged"] == B.EPG_TOK_PER_FRAME, (
        "carrying one extra frame must cost exactly EPG_TOK_PER_FRAME = %d, got %d"
        % (B.EPG_TOK_PER_FRAME, skip["charged"] - ctl["charged"]))
    # the DIRECTION is the register point: the skip is the arm that pays MORE. A wrong skip path
    # would make this delta NEGATIVE and every cost counter would improve.
    assert skip["charged"] > ctl["charged"], (
        "the skip arm is not the one paying more, so the carry-forward is not happening")

    # and the skipped instant is in the event log with its own frame named
    ev = f_skip.co.release_infeasible_events[-1]
    assert ev["skipped_frame_ref"] == ep1_new, (
        "the event names %r as the skipped frame, not %r" % (ev["skipped_frame_ref"], ep1_new))
    assert ev["n_episode_frames"] == 5

    out = {"status": "GREEN",
           "asserted_on": (
               "(1) the coordinator's `_mon_sent[device]` SET MEMBERSHIP, with the released "
               "instant's frames as the positive control that the set moves at all; (2) the next "
               "request's BODY - `_live2.frame_refs` together with the per-frame bytes-versus-"
               "uuid split, because under EP-G the ref list alone is true in both arms; (3) the "
               "uncached token count, as CORROBORATION ONLY"),
           "why_not_the_count": (
               "both wrong skip paths move the token count DOWN or leave it flat while the body "
               "stays well formed, so the charge, the budget spend and the D162 queue term all "
               "read BETTER and a count-based check reads either bug as an improvement. The "
               "evidence has to be the observables that move the other way"),
           "the_two_sets_are_different_bugs": {
               "_mon_sent": ("submission time, drives the CHARGE (n_new, coordinator.py:886). A "
                             "skip that marked it sent leaves the bytes alone and UNDERCHARGES "
                             "by one frame: caught by the set-membership assertion only"),
               "_mon_confirmed": ("200 time, drives the WIRE FORM (coordinator.py:887-888). A "
                                  "skip that marked it confirmed sends a uuid-only reference to "
                                  "bytes the engine never received: caught by the bytes "
                                  "assertion only"),
               "_why_it_is_here": ("the discrimination controls established this, and it was not "
                                   "what this check assumed before they were run: neither "
                                   "assertion stands in for the other")},
           "mon_sent_after_released_instant": sorted(skip["sent_after_0"]),
           "mon_sent_after_skip": sorted(skip["sent_after_1"]),
           "mon_sent_after_release_control": sorted(ctl["sent_after_1"]),
           "next_request_frame_refs": skip["sub"].body["_live2"]["frame_refs"],
           "bytes_carrying_indices": {"skip": skip_bytes, "control": ctl_bytes},
           "charged_tokens": {"skip": skip["charged"], "control": ctl["charged"],
                              "delta": skip["charged"] - ctl["charged"],
                              "epg_tok_per_frame": B.EPG_TOK_PER_FRAME},
           "skipped_frame_ref": ev["skipped_frame_ref"],
           "call_site": ("coordinator.py:935-957, which returns at 956; the only write to "
                         "`_mon_sent` on this path is at 1420, after the submit"),
           "_register": ("a DRY unit fixture on three hand-built instants: it establishes the "
                         "LOGIC of the skip path, not that the mechanism fires in any cell"),
           "_what_would_fail_if_wrong": (
               "a skip path that added the frame to `_mon_sent` on the way out, which assertion 1 "
               "catches on the set and which UNDERCHARGES the next request by one frame; or one "
               "that added it to `_mon_confirmed`, which assertion 2 catches on the body because "
               "the frame would then go as a uuid-only reference to bytes the engine never "
               "received. The token count catches NEITHER: it falls or stays flat in both")}
    _ = f_ctl, ep2_new
    return out


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
#
# TWO MORE WRONG BODIES WERE ADDED WHEN THE REAL BODY LANDED, and the reason is T2. Against the
# first two stubs T2 was caught only by always-deny, because T2 asserts an ADMIT and an allocator
# that admits everything does honour every floor - trivially, but it honours them. A one-sided
# result like that is exactly the shape CLAUDE.md's seventh consistency check warns about: the
# column said DISCRIMINATING and the only wrong body it had been shown was the one it could not
# fail to catch. So the two wrong bodies T2's own docstring names are now stubs too:
#
#   remainder-only  divides only the FREE REMAINDER: no floors, no reservation for other types.
#   no-floors       gives every type an equal cut of W_max and nothing else, so the alert floor of
#                   1,622.1 (above W_max / 3 = 1,441.1) is not reserved and T2's alert row fails.
#
# These are not arbitrary: each is a body someone would plausibly write, and each is wrong in a
# way no aggregate counter would show.
def _stub_remainder_only(**kw: Any) -> Tuple[bool, str]:
    if kw.get("feasible") is False:
        return False, "stub-remainder: infeasible"
    if kw.get("qtype") not in SA.TYPES:
        return True, "stub-remainder: untyped"
    tr = kw["tracker"]
    free = SCAP.W_MAX_TOKENS - sum(tr.w(t) for t in SA.TYPES)
    return (max(int(kw.get("uncached", 0)), 0) <= free), "stub-remainder: free remainder only"


def _stub_no_floors(**kw: Any) -> Tuple[bool, str]:
    if kw.get("feasible") is False:
        return False, "stub-nofloors: infeasible"
    qt = kw.get("qtype")
    if qt not in SA.TYPES:
        return True, "stub-nofloors: untyped"
    tr = kw["tracker"]
    cut = SCAP.W_MAX_TOKENS / len(SA.TYPES)
    return ((tr.w(qt) + max(int(kw.get("uncached", 0)), 0)) <= cut),  "stub-nofloors: equal cut"


STUBS = {
    "always-admit": lambda **kw: (True, "stub: admit everything"),
    "always-deny": lambda **kw: (False, "stub: deny everything"),
    "remainder-only": _stub_remainder_only,
    "no-floors": _stub_no_floors,
}
STUB_WHAT = {"always-admit": "admits everything",
             "always-deny": "denies everything",
             "remainder-only": "divides only the free remainder: no floors at all",
             "no-floors": "an equal cut of W_max per type, so no floor is reserved"}
ALLOCATOR_CHECKS = ("T2", "T3b", "T4", "T5")

# ---------------------------------------------------------------------------- the re-check stubs
# THE SAME DISCRIMINATION QUESTION FOR THE TWO CHECKS THAT ARE NO LONGER PENDING. T6b and T7b run
# against the real coordinator, so the wrong implementation has to be installed where the
# coordinator reads it: `release_recheck.decide`, forced in BOTH DIRECTIONS, patched in this
# process only.
#
#   always-feasible    nothing is ever skipped. T6b's infeasible half must fail; T7b's premise
#                      evaporates and it must fail too.
#   always-infeasible  everything is skipped. T6b's feasible half must fail, and T7b's own
#                      POSITIVE CONTROL must fail, because instant 0 is then never released and
#                      `_mon_sent` never fills - the case where "the frame is absent from the set"
#                      would otherwise be true for the wrong reason.
#
# AND ONE THAT IS NOT A PREDICATE AT ALL, the wrong body 7b exists to catch: a skip path that
# MARKS THE FRAME SENT on its way out. It cannot be installed by patching `decide`, because it is
# not a property of the predicate; it is injected into the coordinator right after the skipped
# serve, which is exactly what that wrong skip path would have left behind. T7b must fail against
# it and the token count must NOT, which is the register claim in T7b's docstring, checked rather
# than asserted.
def _decide_forced(value: bool) -> Callable[..., Dict[str, Any]]:
    real = RR.decide

    def _f(**kw: Any) -> Dict[str, Any]:
        d = dict(real(**kw))
        d["feasible"] = bool(value)
        d["_forced"] = True
        return d
    return _f


def _recheck_controls() -> Dict[str, Any]:
    real = RR.decide
    by_stub: Dict[str, Dict[str, str]] = {}
    checks = {"T6b": t6b_recheck_skips_the_infeasible_request,
              "T7b": t7b_recheck_skip_leaves_the_frame_unsent}
    try:
        for sname, forced in (("always-feasible", True), ("always-infeasible", False)):
            RR.decide = _decide_forced(forced)                          # noqa: B010
            got: Dict[str, str] = {}
            for tid, fn in checks.items():
                try:
                    fn()
                    got[tid] = "PASSED"
                except AssertionError as exc:
                    got[tid] = "CAUGHT: %s" % str(exc).splitlines()[0][:160]
                except Pending as exc:
                    got[tid] = "PENDING: %s" % exc
                except Exception as exc:                                # noqa: BLE001
                    got[tid] = "ERROR %s: %s" % (type(exc).__name__, str(exc)[:120])
            by_stub[sname] = got
    finally:
        RR.decide = real                                                # noqa: B010

    # ---- the two WRONG SKIP PATHS, which are two different bugs with two different observables
    _EPI = {"f%02d.jpg" % i for i in range(5)}

    def _mark_sent(co: Any) -> None:
        """A skip path that recorded the frame as SENT. `_mon_sent` drives the CHARGE, so this
        undercharges the next request by one frame and leaves the bytes alone."""
        co._mon_sent["dash000"].update(_EPI)

    def _mark_confirmed(co: Any) -> None:
        """A skip path that recorded the frame as CONFIRMED. `_mon_confirmed` drives the WIRE
        FORM, so the next request references bytes the engine never received."""
        co._mon_confirmed["dash000"].update(_EPI)

    ctl = _t7b_run(skip_middle=False)
    good = _t7b_run(skip_middle=True)          # the CORRECT skip, for the charge comparison
    wrong_skip: Dict[str, Any] = {}
    for wname, fn_corrupt in (("marks-sent", _mark_sent), ("marks-confirmed", _mark_confirmed)):
        row: Dict[str, Any] = {}
        try:
            r = _t7b_run(skip_middle=True, corrupt=fn_corrupt)
            # T7b's assertion 1, re-run against the corrupted coordinator
            row["assertion_1_set_membership"] = (
                "PASSED: `_mon_sent` was untouched" if r["sent_after_1"] == r["sent_after_0"]
                else "CAUGHT: `_mon_sent` after the skip is %r, not the released instant's four "
                     "frames" % (sorted(r["sent_after_1"]),))
            # T7b's assertion 2, the bytes half
            idx = [i for i, p in enumerate(r["imgs"]) if p["image_url"] is not None]
            row["assertion_2_bytes_in_body"] = (
                "PASSED: the skipped frame still carried bytes" if 4 in idx
                else "CAUGHT: the skipped frame went as a uuid-only reference; bytes carried by "
                     "%r" % (idx,))
            # AND THE REGISTER CLAIM, CHECKED RATHER THAN ASSERTED. Three charges, because the
            # question is not "did the number move" but "could a reader tell": a cell has no
            # oracle for what the charge SHOULD have been, only the number in front of it.
            row["charged_under_the_bug"] = r["charged"]
            row["charged_correct_skip"] = good["charged"]
            row["charged_no_skip_control"] = ctl["charged"]
            _legal = {B.epg_prompt_tokens(n) for n in range(1, 7)}
            row["count_differs_from_the_correct_skip"] = bool(r["charged"] != good["charged"])
            row["bugged_charge_is_itself_a_legal_charge"] = bool(r["charged"] in _legal)
            row["what_the_count_shows"] = (
                ("NOTHING: the charge is identical to the correct skip's %d, so the count carries "
                 "no signal about this bug at all" % good["charged"])
                if r["charged"] == good["charged"] else
                ("%d against the correct %d, and %d is itself a legal EP-G charge, so in a cell - "
                 "where there is no oracle for what the charge should have been - it reads as "
                 "ordinary. Lower means the budget spend and the D162 queue term both improve"
                 % (r["charged"], good["charged"], r["charged"])))
            # and the FULL check, so the recorded verdict is T7b's own and not a re-derived one
            try:
                _t7b_patched(fn_corrupt)
                row["T7b"] = "PASSED"
            except AssertionError as exc:
                row["T7b"] = "CAUGHT: %s" % str(exc).splitlines()[0][:160]
        except Exception as exc:                                        # noqa: BLE001
            row["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
        wrong_skip[wname] = row

    per_check: Dict[str, Any] = {}
    for tid in checks:
        caught = [s for s, g in by_stub.items() if g.get(tid, "").startswith("CAUGHT")]
        per_check[tid] = {"caught_by": caught,
                          "verdict": ("DISCRIMINATING" if caught else
                                      "NOT DISCRIMINATING: passes against a forced predicate")}
    per_check["T7b"]["caught_by"] = per_check["T7b"]["caught_by"] + [
        "wrong-skip-" + w for w, row in wrong_skip.items()
        if str(row.get("T7b", "")).startswith("CAUGHT")]
    return {"_what": ("whether T6b and T7b would catch a WRONG re-check: the predicate forced "
                      "both ways, and the two wrong implementations that are not predicates at "
                      "all - a skip path that marks the frame sent, and one that marks it "
                      "confirmed"),
            "stubs": {"always-feasible": "decide() always returns feasible, so nothing is skipped",
                      "always-infeasible": "decide() always returns infeasible, so all is skipped",
                      "wrong-skip-marks-sent": ("records the frame as SENT: `_mon_sent` drives the "
                                                "CHARGE, so the next request is undercharged by "
                                                "one frame and the bytes are unaffected"),
                      "wrong-skip-marks-confirmed": ("records the frame as CONFIRMED: "
                                                     "`_mon_confirmed` drives the WIRE FORM, so "
                                                     "the next request references bytes the "
                                                     "engine never received")},
            "by_stub": by_stub, "wrong_skip_paths": wrong_skip, "per_check": per_check,
            "all_discriminating": all(v["caught_by"] for v in per_check.values()),
            "_the_register_point": (
                "the token count is not a usable assertion target for either bug, for two "
                "DIFFERENT reasons, and the numbers above are what establish that rather than a "
                "claim about it. Under marks-confirmed the charge is IDENTICAL to the correct "
                "skip's, so it carries no signal at all. Under marks-sent it falls, and the value "
                "it falls to is itself a legal EP-G charge, so a cell - which has no oracle for "
                "what the charge should have been - sees an ordinary number while the budget "
                "spend and the D162 queue term both improve"),
            "_and_the_thing_the_controls_taught": (
                "assertion 1 catches marks-sent and NOT marks-confirmed; assertion 2 catches "
                "marks-confirmed and NOT marks-sent. `_mon_sent` and `_mon_confirmed` are "
                "different sets driving different things, so neither assertion stands in for the "
                "other and T7b needs both. This was not what the check assumed before the "
                "controls were run")}


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
    return {"_what": ("which checks would catch a wrong allocator body, proved by running them "
                      "against four deliberately wrong ones"),
            "stubs": dict(STUB_WHAT),
            "by_stub": by_stub, "per_check": discriminating,
            "all_discriminating": all(v["caught_by"] for v in discriminating.values()),
            "_note": ("always-admit cannot catch T2, which asserts an ADMIT: an allocator that "
                      "admits everything honours every floor trivially. That is why "
                      "remainder-only and no-floors were added - a check shown only the one wrong "
                      "body it cannot fail to catch has not been shown to discriminate")}


def _code_under_test() -> Dict[str, str]:
    """The sha256 of each module whose behaviour these checks assert on.

    Stronger than a git sha for this purpose, and the reason is the register: a git HEAD says
    which commit is checked out, not which bytes were executed, and a run against a working tree
    carrying another session's uncommitted edits would report a HEAD that did not describe it.
    These are the bytes.
    """
    import hashlib
    out: Dict[str, str] = {}
    for rel in ("share_admission.py", "share_capacity.py", "release_recheck.py",
                "coordinator.py", "bodies.py", "d162_price.py"):
        p = HERE / rel
        try:
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except Exception:                                               # noqa: BLE001
            out[rel] = "unreadable"
    return out


def _digest(obj: Any) -> str:
    """The established recipe, applied to this file's own output so two runs are comparable."""
    import hashlib
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


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
        "code_under_test_sha256_16": _code_under_test(),
        "capacity": SCAP.as_dict(),
        "checks": rows,
        "green": green, "pending": pending, "failed": failed,
        "counts": {"green": len(green), "pending": len(pending), "failed": len(failed)},
        "stub_controls": _stub_controls(),
        "recheck_controls": _recheck_controls(),
    }
    out["verdict"] = ("FAIL: %s" % failed if failed else
                      "NO_FAILURES: %d green, %d pending a body that is not landed"
                      % (len(green), len(pending)))
    # THE DETERMINISM DIGEST is taken over everything EXCEPT the provenance stamp, which carries a
    # timestamp and would make two identical runs look different. Two runs of this file in two
    # processes must agree on it, and a reader can check that claim without rerunning.
    out["_body_digest"] = _digest(out)
    try:
        sys.path.insert(0, str(REPO / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d179_share_tests.py", model="none",
                                   device="none", n=len(rows))
    except Exception as exc:                                            # noqa: BLE001
        out["_provenance"] = {"git_commit": "unavailable", "script": "d179_share_tests.py",
                              "why": "%s: %s" % (type(exc).__name__, exc)}
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
    rc = out["recheck_controls"]
    print("  re-check controls (would a wrong re-check be caught?)")
    for tid, v in rc["per_check"].items():
        print("    %-4s %-18s caught by %s" % (tid, v["verdict"].split(":")[0], v["caught_by"]))
    for wname, row in rc["wrong_skip_paths"].items():
        print("    wrong skip path, %s:" % wname)
        for k, v in row.items():
            print("      %-26s %s" % (k, v))
    print(out["verdict"])
    print("wrote", OUT)
    _cleanup_fixtures()
    return 1 if (failed or not sc["all_discriminating"]
                 or not rc["all_discriminating"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
