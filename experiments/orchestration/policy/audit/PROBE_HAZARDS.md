# Probe hazards

**For anyone in any session writing a probe, wrapper or instrument against live2, the policy or the
fleet.** These are the project's hazards, not one session's: the entries below were earned in
three different sessions and each one produced a **confident wrong number rather than an error**,
which is why they are collected here instead of in a report section.

**The question to ask before trusting any instrument:** not *"what can this not see?"* but
**"what have I already had to work around, and what else trusts the thing I worked around?"**
Every workaround is evidence of a gap some other tool is still falling into. The logging hazard
below was found exactly that way, after a workaround built for one analysis left a second
instrument blind.

---

**1. A module-level `from X import y` does not see a patch on `X.y`.**
The importing module binds the name at import time, so patching `X.y` afterwards reaches only the
call sites that resolve it at call time. Patch **both** bindings, or import the module and call
`X.y(...)`. *Instance: this produced the F-A2 dispute. `rollout.py` imports `state_value` INSIDE
the function, so a patch on `readiness` reaches it; `coordinator.py` binds it at module level at
line 21, so the same patch does not. Two sessions patched different bindings, measured different
call sites, and reported contradictory results about the same quantity.*

**2. A field absent from `decision.jsonl` makes any mechanism acting through it read as INERT.**
The decision row carries `H`, `arm`, `arm_version`, `belief`, `cost_model_id`, `decision_id`,
`defer_s`, `kind`, `mu`, `note`, `opportunity_ids`, `piece_tokens`, `predicted`, `t` and
`traffic_mix`. It carries neither `representation` nor the session action, so a diff of decision
rows cannot see representation or placement however often they fire. Capture an **emitted-action
observable** alongside the log. *Instance: a move proof returned 0 differing rows for an arm that
emitted RECENT on all 21 of its recalls.*

**3. A dataclass default is bound at class creation and is not reached by patching the class.**
Changing the attribute afterwards does not affect instances built from the default, and a
constructor that reads the default at definition time keeps the original value. *Instances:
`C_INFLIGHT_DEFAULT`, `placement_enacted`, `pf`.*

**4. A value set at construction may be overwritten by `live2_configure`, and anything DERIVED
from it before the override keeps the old object.** Derive after configuration, or re-derive.
*Instance: the `pf`-derived hybrid kept a stale profile.*

---

## Two consequences worth stating

**A probe that patches the wrong binding does not fail; it reports a number.** Every hazard here
is silent. So a probe needs a positive control: exercise the mechanism in a way you know must
register, and confirm the instrument sees it, before trusting a null.

**Keep two independent routes where you have them.** Once a field is logged at source, the
emitted-action observable becomes a cross-check rather than the only instrument. It is worth
keeping: the log-side route is the one that silently regresses if a field is later dropped, which
is how hazard 2 arose.
