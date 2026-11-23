#!/usr/bin/env python3
"""D206 ITEMS 1a AND 1b, AS AN IDEMPOTENT PATCH SCRIPT OVER A CLEAN CHECKOUT.

Run it from the repo root (or pass --root). It edits five committed files and writes none of its
own. Every edit asserts its anchor first, so a drifted file STOPS the script instead of being
half-patched, and re-running it on an already-patched tree reports ALREADY APPLIED per file rather
than corrupting anything.

WHY A PATCH SCRIPT AND NOT A DIFF. This session cannot commit (CLAUDE.md's read-only git rule), and
origin/main moved six times during the work, so a context diff would rot. A script that asserts its
own anchors either applies cleanly to the tip or refuses, which is the property a reviewer needs.

WHAT IT DOES, by file:

  v5/cf_objective.py   adds `NoPlannerDeficitFeed`, the DECLARED CONSTANT 1 for a rung whose
                       deficit feed does not reach the state planner; marks `DeficitCounters`
                       SUPERSEDED, COMMITTED PROOFS AND TESTS ONLY, NO LIVE PATH (D206 keeps it,
                       reversing D203's "deleted", so the four committed proof scripts and the
                       30-check test suite keep working and no committed JSON is regenerated under
                       its own label); and rewrites the module docstring's w_d paragraph, which
                       claimed a link to the live feed that no rung provided.
  v5/cf_planner.py     REMOVES THE NEUTRAL DEFAULT. A Counterfactual built without a declared
                       weight source now raises `WeightSourceUndeclared`. The default is how the
                       D200 (1) defect survived: it returned 1.0 for every device, which is a
                       believable number no consistency check could catch.
  arms_v6state.py      rungs 2 and 3 DECLARE the constant at the construction site.
  arms_v5full.py       the plan_request family declares it too.
  arms_v6fair.py       the pre-D177 family stops sending observations to the superseded counter
                       and counts them by type instead. DECISION-IDENTICAL BY MEASUREMENT: that
                       hook fed the counter 11,751 times on a dry seed-4 cell and every one of the
                       16 devices still ended at weight exactly 1.0, because its numerator is
                       OR-combined over cloud and device and the device always answers inside
                       these deadlines, so the target is met by construction and the shortfall is
                       structurally 0. `live2/deficit_feed.py` predicted exactly that.
  arms_v6cfr3.py       adds `PlannerDeficitWeights` and an `_cf_engine` override so RUNG 4's state
                       planner reads THE SAME live feed object its two counterfactual legs already
                       read (D206 item 1b, D185 (4)). The swap is read back and RAISES if it did
                       not take, and the fail-loud raises on a feed that received nothing for a
                       whole run, deliberately NOT per read: at the first decision the feed
                       legitimately holds no data, which is why W_WIRED_PROOF records that 1.0 at
                       construction is correct.

AFTER RUNNING IT, the proofs are:
  c1  tests/test_d206_no_live_deficitcounters.py   18 of 18, with positive controls
  c2  one dry s4 cell per construction-site family, byte-identical except rung 4
  c3  covex-v6-fair-c5attr must still read 12e4f73ce0ebd865 / 13,812
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DONE, SKIP, FAIL = [], [], []


def edit(path: Path, pairs, marker: str) -> None:
    """Apply (old, new) pairs to `path`. `marker` present already means ALREADY APPLIED."""
    s = path.read_text()
    if marker in s:
        SKIP.append(path.name)
        return
    for old, new in pairs:
        if old not in s:
            FAIL.append("%s: anchor not found: %s" % (path.name, old.strip().splitlines()[0][:70]))
            return
        s = s.replace(old, new, 1)
    path.write_text(s)
    DONE.append(path.name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    L = Path(a.root).resolve() / "experiments/orchestration/live2"
    if not L.is_dir():
        print("not a repo root: %s" % (a.root,))
        return 2

    # ---------------- v5/cf_objective.py ----------------
    CONST = '''class NoPlannerDeficitFeed:
    """THE EXPLICIT CONSTANT WEIGHT 1 for a rung whose deficit feed does not reach this planner.

    D206 item 1a. This is NOT a fallback and NOT an unfed counter: it is a DECLARATION, and the
    difference is the whole point. An unfed counter that happens to return 1.0 and a constant 1.0
    that is declared are decision-identical and are not equally honest, because only the second
    tells a reader that no deficit reaches this limb, and only the second cannot later be mistaken
    for a live weight that is merely quiet.

    WHY THE RUNGS THAT USE IT ARE ENTITLED TO IT, in their own words rather than by omission:

        rung 2   has no deficits by design. The deficit mechanism enters the ladder at rung 3.
        rung 3   HAS a live per-device deficit feed, and D185 (3) gives it exactly two consumers,
                 the ORDERING hook (`hybrid/hybrid_arm.py:399, 483, 486`) and the FLEXIBLE SPLIT
                 (`share_admission.py:162-168`). NEITHER IS THIS PLANNER. Rung 3's weight is
                 therefore correctly absent here, and that is a scope fact, not a gap.

    MEASURED CONSEQUENCE OF THAT SCOPE FACT, so nobody reads this constant as harmless: if rung 3's
    planner limb DID read its feed, 687 of 60,473 rung-3 state decisions would choose a different
    candidate on the dry seed-4 cell (63,242 weight reads, 0 unresolved, 53,597 above the w = 1
    floor). OBSERVED by decision-log diff in
    `results/orchestration/live2/frozen_test/d200_r3_planner_weight_probe.json`. The user has ruled
    that the change is APPLIED AT THE FINAL LADDER RERUN (D190 (6)) and NOT NOW, so this constant
    is correct for rung 3 TODAY and is scheduled to stop being correct.

    IT DOES NOT RAISE, deliberately, and this is the one place D206 (3)'s fail-loud does not apply:
    a source that is SUPPOSED to be fed and is not must raise, and this source is declared never to
    be fed. The fail-loud lives on `arms_v6cfr3.PlannerDeficitWeights`, the source that IS fed.
    """

    IS_DECLARED_CONSTANT = True
    WEIGHT = 1.0
    DECLARATION = ("no deficit feed in the state planner at this rung (D206 item 1a); rung 2 has "
                   "no deficits by design and rung 3's D185 (3) consumers are the ordering hook "
                   "and the flexible split, neither of which is this planner")

    def __init__(self, rung: str = "unspecified", why: str = "") -> None:
        self.rung = str(rung)
        self.why = str(why) or self.DECLARATION
        self.reads = 0

    def weight(self, device_id: str) -> float:
        self.reads += 1
        return self.WEIGHT

    def shortfall(self, device_id: str) -> float:
        return 0.0

    def starving(self, device_id: str, threshold: float = 0.10) -> bool:
        return False

    def as_dict(self) -> Dict[str, Any]:
        return {"source": "NoPlannerDeficitFeed (D206 item 1a)",
                "is_declared_constant": True, "weight": self.WEIGHT,
                "rung": self.rung, "declaration": self.why, "reads": self.reads,
                "supersedes": ("the unfed cf_objective.DeficitCounters default removed from "
                               "cf_planner.Counterfactual by D206"),
                "equivalence": ("bit-identical to what the unfed DeficitCounters returned at all "
                                "five read sites: the weight reads in plan_request, plan_state "
                                "and plan_sync, the counters= argument of harm_to_others, and the "
                                "counters= argument of harm_warm_from_queue_delay")}


'''
    edit(L / "v5/cf_objective.py", [
        ('''    w_d         = 1 + 2.0 * shortfall_d / target_d, floored at 1 (D185), supplied by the live
                  deficit feed (`live2/deficit_feed.py`, `deficit_gain_d178.GAIN = 2.0`) at the
                  rungs that feed it; `DeficitCounters` below is the v5 fallback and keeps its
                  own declared form, `1 + DEFICIT_GAIN * shortfall`, which is 1.0 for every
                  device whose counter is never fed''',
         '''    w_d         ONE DEFICIT SOURCE, DECLARED AT EVERY CONSTRUCTION SITE (D206, which
                  supersedes D203's "DeficitCounters deleted"). This module supplies NO DEFAULT,
                  because a neutral default is how the defect D200 (1) names survived from
                  2026-11-20 to 2026-11-23. The two live sources are
                  `NoPlannerDeficitFeed` (rungs 2 and 3, the declared constant 1) and
                  `live2/deficit_feed.DeficitFeed.weight_device` adapted at
                  `arms_v6cfr3.PlannerDeficitWeights` (rung 4), so rung 4's planner limb and its
                  two counterfactual legs read THE SAME FEED OBJECT and cannot drift apart.
                  `DeficitCounters` below is SUPERSEDED and has NO LIVE PATH; it is kept so the
                  four committed proof scripts and the 30-check committed test suite that name it
                  keep working, and `d206_guard_proofs.py` is what keeps
                  "no live path" true AS THE TREE CHANGES rather than resting on one reading'''),
        ("class DeficitCounters:", CONST + "class DeficitCounters:"),
        ('''    """Per-device deficit counters, updated from the REALISED on-time outcome of each opportunity.
''',
         '''    """SUPERSEDED (D200, D206): COMMITTED PROOFS AND TESTS ONLY. NO LIVE PATH.

    DO NOT CONSTRUCT THIS FROM AN ARM. `w = 1 + DEFICIT_GAIN * shortfall` with `DEFICIT_GAIN = 1.0`
    and `ON_TIME_TARGET` 0.90 for every type with no per-episode reset is the PRE-D178 form: the
    targets are stale by D178 (1) and the gain is stale by D185 (2).

    MEASURED, so that "no live path" is not merely asserted: the one arm family that ever fed this
    object, `arms_v6fair` (registered at `arms.py:725`, hook at `arms_v6fair.py:131`), fed it
    11,751 times on a dry seed-4 cell and EVERY ONE of its 16 devices still ended at weight exactly
    1.0, because that family's numerator is OR-combined over cloud and device and the device always
    answers inside these deadlines, so the target is met by construction and the shortfall is
    structurally 0. So moving it to the declared constant is DECISION-IDENTICAL, measured rather
    than assumed, which is why D206's byte-identity requirement can be met at all.

    Per-device deficit counters, updated from the REALISED on-time outcome of each opportunity.
'''),
    ], marker="class NoPlannerDeficitFeed:")

    # ---------------- v5/cf_planner.py ----------------
    edit(L / "v5/cf_planner.py", [
        ("                 counters: Optional[CO.DeficitCounters] = None,",
         "                 counters: Any = None,"),
        ("        self.counters = counters if counters is not None else CO.DeficitCounters()",
         '''        # D206: NO NEUTRAL DEFAULT. A default here is exactly how the defect D200 (1) names
        # survived: `DeficitCounters()` with no feeder returns 1.0 for every device, which is a
        # believable number, so no consistency check could see it while the docstring kept
        # claiming a link to the live feed that no rung provided. Every caller now DECLARES its
        # source, and a caller that declares none RAISES rather than being handed a quiet 1.
        if counters is None:
            raise WeightSourceUndeclared(
                "cf_planner.Counterfactual was constructed with no declared deficit weight "
                "source. D206 removed the default. Pass cf_objective.NoPlannerDeficitFeed(rung=) "
                "if this rung's deficit feed genuinely does not reach the state planner (rungs 2 "
                "and 3), or arms_v6cfr3.PlannerDeficitWeights(arm) if it does (rung 4). "
                "cf_objective.DeficitCounters is SUPERSEDED and has no live path.")
        self.counters = counters'''),
        ("def effective_margin(margin_value: float, weight: float) -> float:",
         '''class WeightSourceUndeclared(RuntimeError):
    """A Counterfactual was built without declaring where its deficit weight comes from (D206)."""


def effective_margin(margin_value: float, weight: float) -> float:'''),
    ], marker="WeightSourceUndeclared")

    # ---------------- arms_v6state.py ----------------
    edit(L / "arms_v6state.py", [
        ('''            kw: Dict[str, Any] = dict(dry=self.dry, dry_margin=self.dry_margin,
                                      clock=CI.DecisionClock())''',
         '''            import cf_objective as _CO
            # D206 item 1a: the weight source is DECLARED at the construction site, never
            # defaulted. Rung 4 does not come through here: `arms_v6cfr3` overrides `_cf_engine`
            # and injects the live feed, so this line is the rung-2 and rung-3 declaration only.
            kw: Dict[str, Any] = dict(dry=self.dry, dry_margin=self.dry_margin,
                                      clock=CI.DecisionClock(),
                                      counters=_CO.NoPlannerDeficitFeed(
                                          rung=getattr(self, "name", "covex-v6-state")))'''),
    ], marker="NoPlannerDeficitFeed")

    # ---------------- arms_v5full.py ----------------
    edit(L / "arms_v5full.py", [
        ("            self._cf = CP.Counterfactual(**kw)",
         '''            import cf_objective as _CO
            # D206 item 1a: declared, not defaulted. This family has no deficit feed at all.
            kw.setdefault("counters", _CO.NoPlannerDeficitFeed(
                rung=getattr(self, "name", "v5-full")))
            self._cf = CP.Counterfactual(**kw)'''),
    ], marker="NoPlannerDeficitFeed")

    # ---------------- arms_v6fair.py ----------------
    edit(L / "arms_v6fair.py", [
        ('''        kind = {"monitor": "dashcam"}.get(str(rec.get("kind")), "robot")
        try:
            self._cf_engine().counters.observe(str(did), on_time=on_time, kind=kind)
        except Exception:                                                      # noqa: BLE001
            self.stats["deficit_feed_observe_failed"] += 1''',
         '''        kind = {"monitor": "dashcam"}.get(str(rec.get("kind")), "robot")
        # D206 item 1a: THIS FEED NO LONGER REACHES THE STATE PLANNER, and the move is
        # DECISION-IDENTICAL BY MEASUREMENT rather than by argument. On a dry seed-4 cell this hook
        # fed `cf_objective.DeficitCounters` 11,751 times and every one of the 16 devices still
        # ended at weight exactly 1.0, because `on_time` above is OR-COMBINED over cloud and device
        # and the device always answers inside these deadlines, so the 0.90 target is met by
        # construction and the shortfall is structurally 0. `live2/deficit_feed.py` predicted
        # exactly that, and this family is the PRE-D177 rung 3 that D178 and D185 replaced. The
        # observation is COUNTED BY TYPE AND NOT APPLIED, rather than sent to a superseded counter
        # or swallowed by an `except` that would have logged 11,751 silent failures.
        self.stats["deficit_feed_counted_not_applied"] += 1
        self.stats["deficit_feed_counted_not_applied_" + kind] += 1'''),
        ('''            try:
                c = self._cf_engine().counters
                ws = [c.weight(d) for d in c.devices]''',
         '''            try:
                c = self._cf_engine().counters
                # D206: the planner's source is the DECLARED CONSTANT 1 for this family, so the
                # reported maximum is 1.0 BY DECLARATION and is labelled, not presented as a
                # measured weight that happens to be 1.
                if getattr(c, "IS_DECLARED_CONSTANT", False):
                    self.stats["deficit_weight_max_milli"] = 1000
                    self.stats["deficit_weight_is_declared_constant"] = 1
                    ws = []
                else:
                    ws = [c.weight(d) for d in c.devices]'''),
    ], marker="deficit_feed_counted_not_applied")

    # ---------------- arms_v6cfr3.py ----------------
    ADAPTER = '''class DeficitSourceNeverFed(RuntimeError):
    """A weight source that is SUPPOSED to be fed received nothing for a whole run (D206 item 3)."""


class PlannerDeficitWeights:
    """THE SAME per-device `w_d` the two legs read, adapted to the v5 planner's interface.

    D206 item 1b, and the point is ONE SOURCE AND NOT TWO. The two counterfactual legs already read
    `self._feed.weight_device` through `_weight_of` below; this hands the STATE PLANNER the same
    object, so the limb and the legs cannot disagree about a device's weight at a given instant.
    They are equal BY CONSTRUCTION rather than by agreement, and a proof that compares them is an
    IDENTITY and must say so: n reads of one object, maximum absolute difference exactly 0.

    THE DEVICE RESOLVER IS THE ARM'S OWN, `_fairfeed_resolve_device`, which is what rung 3's
    ordering consumer uses, so the planner weight and the ordering weight cannot disagree about
    WHICH DEVICE a decision is about either. An id that does not resolve takes the floor and is
    COUNTED, because the device set is the roster's and an unresolved id means the resolver failed.

    FAIL-LOUD, AND DELIBERATELY NOT PER READ. D206 item 3 says a source supposed to be fed must
    raise rather than return a neutral value. The condition that let the original defect live is
    "never fed across a whole run", NOT "holds no data at this instant": at the first decision the
    feed legitimately has no observations, which is why `W_WIRED_PROOF` records that 1.0 at
    construction is correct and not a failure. So the raises are at CONSTRUCTION when the feed
    object is absent, and at REPORT TIME when reads happened and the feed received zero
    observations all run. A per-read raise would fire on decision one of a correct run.
    """

    IS_DECLARED_CONSTANT = False

    def __init__(self, arm: Any) -> None:
        if getattr(arm, "_feed", None) is None:
            raise WeightWiringError(
                "PlannerDeficitWeights was built with no live feed on the arm; _fairfeed_init has "
                "not run, so the rung-4 planner limb would have silently priced every device at "
                "1.0 (D206 item 1b)")
        self._arm = arm
        self.reads = 0
        self.unresolved = 0
        self.reads_above_floor = 0

    def _resolve(self, device_id: Any) -> Optional[str]:
        return self._arm._fairfeed_resolve_device(device_id, None)

    def weight(self, device_id: Any) -> float:
        self.reads += 1
        did = self._resolve(device_id)
        if did is None:
            self.unresolved += 1
            self._arm.stats["planner_w_device_unresolved"] += 1
            return 1.0
        w = float(self._arm._feed.weight_device(did))
        if not (w == w) or w < 1.0:
            # the D178 (2) floor RESTATED AT THE POINT OF USE: the bar is w_R * MARGIN_CF and a
            # weight under 1 would lower it below the committed margin by another route.
            self._arm.stats["planner_w_below_floor_clamped"] += 1
            return 1.0
        if w > 1.0:
            self.reads_above_floor += 1
        return w

    def shortfall(self, device_id: Any) -> float:
        did = self._resolve(device_id)
        return 0.0 if did is None else float(self._arm._feed.shortfall_device(did))

    def starving(self, device_id: Any, threshold: float = 0.10) -> bool:
        return self.shortfall(device_id) >= float(threshold)

    def _n_observations(self) -> int:
        f = self._arm._feed
        return int(getattr(f, "n_offers", 0)) + int(getattr(f, "n_completions", 0))

    def as_dict(self) -> Dict[str, Any]:
        n_obs = self._n_observations()
        if self.reads and n_obs == 0:
            raise DeficitSourceNeverFed(
                "the rung-4 planner deficit source was READ %d times and the feed received ZERO "
                "observations for the whole run, so every weight it returned was the floor. That "
                "is the condition that let the D200 (1) defect survive, and D206 item 3 requires "
                "it to raise rather than report a neutral default." % (self.reads,))
        return {"source": ("live2/deficit_feed.DeficitFeed.weight_device, THE SAME FEED OBJECT "
                           "the two counterfactual legs read (D206 item 1b)"),
                "is_declared_constant": False,
                "gain": float(getattr(self._arm, "_feed_gain", float("nan"))),
                "reads": self.reads, "unresolved": self.unresolved,
                "reads_above_the_w1_floor": self.reads_above_floor,
                "feed_observations": n_obs,
                "identity_note": ("the legs and this limb read ONE object, so an equality proof "
                                  "between them is an IDENTITY with maximum absolute difference "
                                  "exactly 0, not a measurement of agreement")}


'''
    edit(L / "arms_v6cfr3.py", [
        ("def _weight_of(arm: Any, device_id: str) -> float:",
         ADAPTER + "def _weight_of(arm: Any, device_id: str) -> float:"),
        ("    def rd_report(self) -> Dict[str, Any]:",
         '''    def _cf_engine(self) -> Any:
        """RUNG 4'S STATE PLANNER READS THE LIVE DEFICIT FEED (D206 item 1b).

        The base builds the engine with `cf_objective.NoPlannerDeficitFeed`, which is the correct
        DECLARATION for rungs 2 and 3 and is wrong for rung 4: spec v6 section 7 deficit-weights
        the counterfactual's state decisions, and D185 (4) says rung 4 uses the same per-device
        w_d in harm and in `w_d * MARGIN_CF`. The source is swapped HERE, in rung 4's own module,
        the only place that knows both that the feed exists and that this rung may read it.

        THE SWAP IS READ BACK AND ASSERTED, so a construction that silently kept the constant
        RAISES instead of producing a plausible null, which is the shape of the defect this rung
        is being repaired for.
        """
        cf = super()._cf_engine()                                       # type: ignore[misc]
        if not getattr(cf, "_rung4_planner_wired", False):
            src = PlannerDeficitWeights(self)
            cf.counters = src
            cf._rung4_planner_wired = True
            self._planner_w_source = src
            if getattr(cf.counters, "IS_DECLARED_CONSTANT", True):
                raise WeightWiringError(
                    "the rung-4 planner weight source did not take: the engine still holds %r, a "
                    "declared constant, so plan_state would price every device at 1.0"
                    % (type(cf.counters).__name__,))
            if cf.counters._arm._feed is not self._feed:                # pragma: no cover
                raise WeightWiringError(
                    "the rung-4 planner source is not reading THE SAME feed object as the two "
                    "legs, so the limb and the legs could disagree (D206 item 1b)")
        return cf

    def planner_weight_report(self) -> Dict[str, Any]:
        """The planner limb's own source, so a cell can show it is live and not constant."""
        src = getattr(self, "_planner_w_source", None)
        return src.as_dict() if src is not None else {"source": None, "wired": False}

    def rd_report(self) -> Dict[str, Any]:'''),
        ('                     w_source=getattr(self, "_pd_w_source", None),',
         '                     w_source=getattr(self, "_pd_w_source", None),\n'
         '                     planner_limb_w_source=self.planner_weight_report(),'),
    ], marker="class PlannerDeficitWeights:")

    for n in DONE:
        print("PATCHED        %s" % n)
    for n in SKIP:
        print("ALREADY APPLIED %s" % n)
    for m in FAIL:
        print("FAILED         %s" % m)
    print("\n%d patched, %d already applied, %d failed" % (len(DONE), len(SKIP), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
