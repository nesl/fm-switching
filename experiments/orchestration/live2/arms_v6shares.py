#!/usr/bin/env python3
"""covex-v6-state-shares: covex-v6-state-uo with D179 share-based admission and release re-check.

WHY A DISTINCT NAME AND NOT A FLAG ON covex-v6-state-uo. Four cells of covex-v6-state-uo are
already committed at seeds 4 to 7. The driver never reruns a cell whose name already exists valid,
and a tag suffix carries no flags, so a share cell run under the committed name would either be
skipped or would collide with a cell that decided differently. The name is the only thing the cell
key is built from, so the name is what has to differ. This is the same reason D173 (2) gave the
rerun arms distinct names rather than reusing the rung's.

WHAT THIS ARM IS. covex-v6-state-uo in EVERY respect the D174 (1) pricing ruling fixed - the
per-uncached charge, declared by the arm, in the ruled uncached-only mode - plus exactly two
switches:

    live2_share_admission   D179 (1) to (3): per-type in-flight uncached-token shares, floors from
                            share_capacity.py, the flexible pool, borrowing, the oversize-when-
                            alone rule. Mechanism in share_admission.py (session A).
    live2_release_recheck   D179 (4): b7 deadline feasibility is re-checked AT THE MOMENT OF
                            RELEASE, not only at arrival. A deadline request that can no longer
                            make its deadline is not sent and the device answer stands; for an
                            alert episode this skips the QUESTION for that instant and never the
                            frame, which the append-only EP-G episode then carries forward.

BOTH SWITCHES ARE INSTANCE ATTRIBUTES, and that is not a stylistic choice. arms_v6state.py's own
docstring records what class attributes cost here: `covex-v6-state-off` left the rung's four
capability flags ON because they were class attributes, state pricing kept changing the budget
charge, and the "negative control" differed from covex-v6-rules by 4,376 rows of decisions while
claiming to be the rung with its channel disabled. A control that does not collapse is not a
control. So these are set on instances, by this module, and by nothing else.

THEY ARE SET ON EVERY OBJECT THE DECIDE PATH CAN BIND `self` TO, for the reason arms_v6c5.py
records: `V5Rules2Arm.__call__` runs `HybridArm.__call__(self, obs)` with `self` being the
wrapper, and `V5Rules2Arm.decide` then calls `self._base.decide`, so a reader that runs against
the inner object sees the attribute only if the attribute is there. Leaving one unset is how a
switch reads as live and is not.

REGISTER RULE, STATED PLAINLY AND NOT GLOSSED. At this commit NOTHING READS EITHER SWITCH:
`share_admission.allowed()` still returns (True, "disabled") and the coordinator has no call site
for it. So what this module proves is that the switch is SET ON THIS ARM AND ON NO OTHER, read
back off the constructed object and off every object in its delegation chain. It does NOT prove
that the switch moves a decision; under CLAUDE.md Step 2b that proof is a diff of two decision
logs and it cannot be run until session A's allocator body and session B's call site exist. Until
then these are write-only fields and this docstring says so rather than letting the registration
read as a live mechanism.

covex-v6-state-uo itself is defined in arms_v6state.py, which another session owns, so this arm
SUBCLASSES it and is registered here and in `arms.py` beside the other v6 families - never only
in this module's `register()`, which is the mistake that skipped the first covex-v6-state cell
list (a name registered in a module the harness does not import does not exist in the harness's
process; see `arms.py`'s comment and `v6_harness_name_proof.py`).
"""
from __future__ import annotations

from typing import Any, Dict, List

import arms_v6state as VS

SHARES_VERSION = "covex-v6-state-shares-1.0"
SHARES_ARM_NAME = "covex-v6-state-shares"

# the two switch names, in one place, so a test and a reader cannot drift apart
SWITCH_SHARE_ADMISSION = "live2_share_admission"
SWITCH_RELEASE_RECHECK = "live2_release_recheck"
SWITCHES = (SWITCH_SHARE_ADMISSION, SWITCH_RELEASE_RECHECK)


class V6StateSharesArm(VS.V6StateArm):
    """covex-v6-state-uo plus D179 share admission and deadline-aware release re-check."""

    def __init__(self, name: str = SHARES_ARM_NAME, *,
                 share_admission: bool = True,
                 release_recheck: bool = True, **kw: Any) -> None:
        # IDENTICAL to the registered covex-v6-state-uo in everything D174 (1) ruled
        kw.setdefault("d162_pricing", True)
        kw.setdefault("charge_mode", "uncached-only")
        super().__init__(name=name, **kw)
        self.arm_version = SHARES_VERSION
        for obj in self.switch_targets():
            setattr(obj, SWITCH_SHARE_ADMISSION, bool(share_admission))
            setattr(obj, SWITCH_RELEASE_RECHECK, bool(release_recheck))

    def switch_targets(self) -> List[Any]:
        """Every object the decide path can bind `self` to: this wrapper and its whole delegation
        chain. Walked rather than hard-coded, because the chain's depth is arms_v6state's and
        arms_v5rules2's business and not this module's."""
        out: List[Any] = []
        o: Any = self
        seen = set()
        while o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append(o)
            o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        return out

    def hybrid_core(self) -> Any:
        """The innermost object of the chain, for the proofs to read."""
        return self.switch_targets()[-1]

    def switch_report(self) -> Dict[str, Any]:
        """What each switch reads as, on EVERY object of the chain. A single getattr on the
        wrapper is the check that passes while the inner object decides differently."""
        return {s: [bool(getattr(o, s, False)) for o in self.switch_targets()] for s in SWITCHES}

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())
        d.update(arm=self.name, arm_version=SHARES_VERSION,
                 share_admission=dict(
                     enabled=bool(getattr(self, SWITCH_SHARE_ADMISSION, False)),
                     release_recheck=bool(getattr(self, SWITCH_RELEASE_RECHECK, False)),
                     resource=("W, the predicted uncached tokens of requests submitted and not "
                               "yet at first token, per query type (D179 (1))"),
                     capacity_source="experiments/orchestration/live2/share_capacity.py (frozen)",
                     mechanism="experiments/orchestration/live2/share_admission.py",
                     switch_chain=self.switch_report(),
                     status=("the switches are SET here and READ nowhere at this commit; no "
                             "Step 2b decision diff exists yet")))
        return d


V6SHARES_ARMS = {
    SHARES_ARM_NAME: lambda **kw: V6StateSharesArm(name=SHARES_ARM_NAME, **kw),
    # CLAUDE.md Step 4 negative control: both switches off must collapse to covex-v6-state-uo.
    # Named, so the control is a cell and not a code edit.
    SHARES_ARM_NAME + "-off": lambda **kw: V6StateSharesArm(
        name=SHARES_ARM_NAME + "-off", share_admission=False, release_recheck=False, **kw),
    # one-factor ablations, so each of D179's two additions is checkable alone
    SHARES_ARM_NAME + "-noadmit": lambda **kw: V6StateSharesArm(
        name=SHARES_ARM_NAME + "-noadmit", share_admission=False, **kw),
    SHARES_ARM_NAME + "-norecheck": lambda **kw: V6StateSharesArm(
        name=SHARES_ARM_NAME + "-norecheck", release_recheck=False, **kw),
    # D187 (1): the r1 LABEL. The arm configuration is IDENTICAL to covex-v6-state-shares in every
    # respect; what differs is the COORDINATOR, which now prices a recall against the prefix the
    # engine actually reports instead of against the coordinator's own build pieces
    # (coordinator.py, the D187 (1) block). The label exists so r1 cells cannot collide with the
    # four committed covex-v6-state-shares cells, which were produced by the mispriced code and
    # stay valid as the before-condition. A label, not a variant: if this arm ever differs from
    # covex-v6-state-shares in any ARM-side respect, the comparison it exists to support is void.
    SHARES_ARM_NAME + "-r1": lambda **kw: V6StateSharesArm(
        name=SHARES_ARM_NAME + "-r1", **kw),
    # D187 r2: the QUEUE-REGISTER label. Arm-side identical to -r1 and to the base arm; what
    # differs is again the COORDINATOR, which now feeds the release re-check the W quantity the
    # D162 model was actually fitted on (submit to FIRST TOKEN) instead of _uncached_in_flight
    # (submit to COMPLETION, which includes decode). The r1 cells stay valid as the
    # before-condition for this change, exactly as the shares cells did for r1.
    SHARES_ARM_NAME + "-r2": lambda **kw: V6StateSharesArm(
        name=SHARES_ARM_NAME + "-r2", **kw),
}


def register() -> None:
    import arms as A
    A.ARMS.update(V6SHARES_ARMS)
