#!/usr/bin/env python3
"""`covex-v6-fair-c5attr-rr`: rung 3 plus the ALERT release re-check, and nothing else.

    rung 3   covex-v6-fair-c5attr        the c5attr base plus the D178 (2) deficit feed
    this arm + release_recheck ON FOR THE ALERT TYPE ONLY (D179 (4), already proven)

An alert instant that can no longer make its 1 s deadline has its QUESTION skipped at wire time.
THE FRAME STAYS IN THE EPISODE and is carried by reference on the next request: the coordinator's
skip returns before `_mon_sent` is touched, the EP-G episode context is append-only, so the next
instant's `episode_frame_refs` still carries this frame and that request's `n_new` RISES by it.
That property is load-bearing here and it is not asserted by this module: it is asserted on the
actual request body in `tests/test_release_recheck.py`, which is why this arm reuses the committed
component instead of restating it.

WHY THIS ARM EXISTS, AND IT IS A MEASURED REASON RATHER THAN A HUNCH. The rung-4 margin diagnosis
(`reports/study_rung4_margin_diagnosis.md`, committed at a15a1792) attributed alert lateness in the
committed rung-3 s4 cell by what was actually in front of each late instant. Of 2,290 sent-and-late
alert instants:

    OTHER ALERT FRAMES dominant     84.1 percent
    single-shot dominant             4.8 percent
    RECALL QUESTIONS dominant        6.9 percent   (present at all: 9.4 percent)
    recall warm or touch dominant    2.8 percent
    nothing ahead                    1.2 percent

Rung 4's question-deferral leg acts on the 6.9 percent and is reach-limited there. THIS mechanism
acts on the 84.1 percent, because an alert question that cannot make its own deadline is occupying
the engine in front of the next alert instant for no return at all.

THREE THINGS THIS ARM DELIBERATELY DOES NOT DO.

  NO SHARE ADMISSION. Rung 3 runs on the c5attr base, which carries none; `SA.arm_enables` is
  False here and stays False. The arm is rung 3 plus ONE switch.

  NO FLOORS. D188's floors are PARKED, and the reason is structural rather than a preference: the
  floors exist only INSIDE share admission, so there is no way to have them here without pulling
  in shares, which would be a second change. They are not re-derived either.

  NO RECALL OR ASSISTANCE RE-CHECK. `live2_release_recheck_types = ("alert",)`. The recall path is
  the one that cost: the r1 cells ran the re-check over all three types and skipped 34 recall
  questions at s4, taking robot on time to 95 against rung 3's 122. Running both paths in one arm
  would change two things at once and the alert contribution could not be read out of the result.

THE PREREQUISITE IS ALREADY SATISFIED AND IS CHECKED, NOT ASSUMED. `coordinator.py` REFUSES
`live2_release_recheck` on an arm that does not also declare `live2_d162_pricing`, because
`_uncached_in_flight` is decremented only under D162 pricing and is otherwise a cumulative run
total in the wrong register. Rung 3 on the c5attr base ALREADY declares `live2_d162_pricing = True`,
so this arm changes exactly ONE switch and the comparison against rung 3 is a one-factor
comparison. `rr_prerequisite_proof` records the value read off the built instance rather than
trusting this paragraph.

AN INDEPENDENT SWITCH, SO THE FOURTH ARM IS POSSIBLE. Another session is building
`covex-v6-fair-c5attr-exit` (the D192 (3) episode early exit) as a separate switch on the same rung
3. Nothing here changes rung 3's behaviour or any shared decision rule: this arm only sets two
arm-scoped INSTANCE attributes. So an arm carrying both switches can be built later and the two
contributions separated and stacked, which is what the plan asks for.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_v6fairfeed as FF                                                   # noqa: E402
import deficit_gain_d178 as GAIND                                             # noqa: E402
import release_recheck as RR                                                   # noqa: E402

RR_VERSION = "covex-v6-fair-c5attr-rr-1.0"

RUNG2_BASE = "covex-v6-state-uo-c5attr"
RUNG3_ARM = "covex-v6-fair-c5attr"

# The one type this arm re-checks. A TUPLE, declared once, and the reason is in the docstring.
RECHECK_TYPES = ("alert",)


class PrerequisiteNotMet(RuntimeError):
    """The D162 pricing prerequisite the coordinator requires is not on the built arm."""


class _AlertRecheckMixin:
    """Two instance attributes and a report. No decision rule is defined or changed here."""

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())                                 # type: ignore[misc]
        d.update(arm=self.name, arm_version=RR_VERSION,
                 covex_v6_fair_c5attr_rr=dict(
                     built_on=RUNG3_ARM,
                     adds="release_recheck (D179 (4)) for the ALERT type only",
                     switch=RR.SWITCH_ATTR,
                     switch_on=RR.arm_enables(self),
                     types_attr=RR.TYPES_ATTR,
                     types=list(RR.types_for(self)),
                     types_default_for_other_arms=list(RR.TYPES),
                     share_admission="OFF; the c5attr base carries none",
                     floors=("PARKED (D188). They exist only inside share admission, so there is "
                             "no way to have them here without pulling in shares, which would be "
                             "a second change. Not re-derived."),
                     recall_path=("DELIBERATELY OUT OF SCOPE. r1 ran all three types and skipped "
                                  "34 recall questions at s4, taking robot on time to 95 against "
                                  "rung 3's 122."),
                     why_the_alert_path=("84.1 percent of the 2,290 sent-and-late alert instants "
                                         "in the committed rung-3 s4 cell are dominant-blocked by "
                                         "OTHER ALERT FRAMES; recall questions dominate 6.9 "
                                         "percent (d190_rung4_margin_diagnosis.json)"),
                     prerequisite=self.rr_prerequisite_proof(),
                     frame_is_kept=("the skip returns before _mon_sent, and EP-G is append-only, "
                                    "so the frame is carried by reference on the next request and "
                                    "that request's n_new rises by it; asserted on the real "
                                    "request body in tests/test_release_recheck.py")))
        return d

    def rr_prerequisite_proof(self) -> Dict[str, Any]:
        """What the coordinator will read off this instance, read off it HERE instead of assumed.

        The coordinator refuses `live2_release_recheck` without `live2_d162_pricing`, so the only
        thing that makes this a ONE-FACTOR arm against rung 3 is that rung 3 already carries the
        pricing switch. That is a fact about the base, so it is measured on the object.
        """
        own = vars(self)
        return {"live2_d162_pricing_on_the_instance": own.get("live2_d162_pricing"),
                "live2_release_recheck_on_the_instance": own.get(RR.SWITCH_ATTR),
                "live2_release_recheck_types_on_the_instance": own.get(RR.TYPES_ATTR),
                "share_admission_on_the_instance": own.get("live2_share_admission"),
                "arm_enables_reads": RR.arm_enables(self),
                "types_reads": list(RR.types_for(self)),
                "why_one_factor": ("rung 3 on the c5attr base already declares "
                                   "live2_d162_pricing, so enabling the re-check changes exactly "
                                   "one switch and nothing else")}

    def rr_switch_chain(self) -> List[Dict[str, Any]]:
        """The switch as read on EVERY object the decide path can bind `self` to.

        The coordinator reads the switch off the ARM OBJECT IT WAS GIVEN, so the wrapper is the one
        that must carry it. The chain is reported anyway, because a single getattr on the wrapper
        is exactly the check that passes while an inner object behaves differently, and this
        project has paid for that twice.
        """
        out: List[Dict[str, Any]] = []
        o: Any = self
        seen = set()
        while o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append({"class": type(o).__name__,
                        "switch_declared_on_instance": RR.SWITCH_ATTR in vars(o),
                        "switch_value": vars(o).get(RR.SWITCH_ATTR),
                        "types_value": vars(o).get(RR.TYPES_ATTR)})
            o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        return out


def _build_class() -> Any:
    rung3 = FF.make_class(RUNG2_BASE)
    return type("V6FairC5AttrRR", (_AlertRecheckMixin, rung3),
                {"__doc__": "rung 3 (%s) plus the ALERT release re-check" % (RUNG3_ARM,)})


V6FairC5AttrRR = _build_class()


def make(name: str, *, release_recheck: bool = True,
         recheck_types: Any = RECHECK_TYPES,
         deficit_feed: bool = True, gain: float = GAIND.GAIN,
         ordering: bool = True, split: bool = True, **kw: Any) -> Any:
    """Build the arm. Two phases, because the rung-3 feed is initialised after construction."""
    arm = V6FairC5AttrRR(name=name, **kw)
    arm._fairfeed_init(deficit_feed=deficit_feed, gain=gain, ordering=ordering, split=split)
    # ---- the ONE switch this arm adds, on the instance, never on the class -----------------
    # Set on the wrapper, which is the object the coordinator is handed and reads. `object
    # .__setattr__` for the same reason `arms_v6fairfeed` uses it: a base that defines __slots__
    # or a property must not silently swallow the write.
    object.__setattr__(arm, RR.SWITCH_ATTR, bool(release_recheck))
    if release_recheck:
        object.__setattr__(arm, RR.TYPES_ATTR, tuple(recheck_types))
    # ---- read back through the strict readers, so a construction that did not take RAISES ----
    if RR.arm_enables(arm) != bool(release_recheck):                       # pragma: no cover
        raise RR.ReleaseRecheckSwitchError(
            "%s did not take on the instance of %s" % (RR.SWITCH_ATTR, type(arm).__name__))
    if release_recheck and tuple(RR.types_for(arm)) != tuple(recheck_types):  # pragma: no cover
        raise RR.ReleaseRecheckSwitchError(
            "%s did not take: reads %r" % (RR.TYPES_ATTR, RR.types_for(arm)))
    # ---- and the prerequisite the COORDINATOR will refuse on, checked HERE so the failure is at
    # construction in a proof rather than 80 s into a live cell ------------------------------
    if release_recheck and not bool(vars(arm).get("live2_d162_pricing")):   # pragma: no cover
        raise PrerequisiteNotMet(
            "%s enables %s but the built arm does not declare live2_d162_pricing, which the "
            "coordinator refuses (coordinator.py, the D179 (4) block): _uncached_in_flight is "
            "decremented only under D162 pricing and is otherwise a cumulative run total, so the "
            "queue input would be in the wrong register." % (name, RR.SWITCH_ATTR))
    return arm


_N = "covex-v6-fair-c5attr-rr"
V6RR_ARMS: Dict[str, Any] = {
    # THE ARM: rung 3 plus the alert release re-check.
    _N: (lambda **kw: make(_N, **kw)),
    # CLAUDE.md Step 4 and the off-switch identity bar: the switch off must collapse to the
    # COMMITTED RUNG-3 arm byte-identically, 12e4f73ce0ebd865 / 13,812. Not to rung 2.
    _N + "-off": (lambda **kw: make(_N + "-off", release_recheck=False, **kw)),
    # THE SCOPE ABLATION, so "alert only" is a cell and not a claim: the same arm with the
    # re-check on ALL THREE types, which is what r1 did. It exists to show that the alert-only
    # restriction is what makes this arm different from r1, and it is NOT the headline arm.
    _N + "-alltypes": (lambda **kw: make(_N + "-alltypes",
                                         recheck_types=("alert", "recall", "assistance"), **kw)),
}


def register() -> List[str]:
    """Additive registration into the shared `arms.ARMS`, the pattern every v6 family uses."""
    import arms as A
    A.ARMS.update(V6RR_ARMS)
    return sorted(V6RR_ARMS)


ARMS = V6RR_ARMS
