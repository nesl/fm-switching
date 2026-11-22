#!/usr/bin/env python3
"""D172: the spec v6 ABLATION LADDER, its names, and the aliases that resolve them.

    covex-v6-base   hybrid-F-lhreq-noc3 rules
    covex-v6-rules  + chunked just-in-time warming + saturation guard      (was v5-rules-2)
    covex-v6-state  + per-type host retention, touch, belief from telemetry, state pricing
    covex-v6-fair   + deficit feed + value reader
    covex-v6        + counterfactual: request, state, sync, compounds, episode-rule switch
                                                                          (was "full v5" / v5-full)

THREE RULES THIS MODULE EXISTS TO ENFORCE, and the third is the one that can do damage.

1. COMMITTED CELLS KEEP THEIR ORIGINAL NAMES (D172 (1)). Nothing here renames a committed file,
   a committed digest or a committed row. The map is in `research/arm_name_map.md` and is READ in
   both directions: a reader meeting `v5-rules-2` in a committed cell can find its rung, and a
   reader meeting `covex-v6-rules` in a new cell can find the committed cells that are the same
   arm.

2. AN ALREADY-RUN CELL OF AN IDENTICAL ARM IS REUSED, NEVER RERUN FOR THE NAME (D172 (2)). The
   alias builds the SAME class with the SAME keyword arguments, so identity is a property of the
   construction and not of a comparison that happened once. It is PROVED anyway, by decision
   digest on a dry cell, in `v6_alias_proof.py`: construction identity is the claim, the digest
   is the check, and a check that agrees with its claim by construction is still worth running
   because the thing it catches is the construction being wrong.

3. A RUNG THAT IS NOT BUILT MUST NOT RESOLVE TO A LOWER RUNG. `covex-v6-state` and `covex-v6-fair`
   name components that do not exist yet. Registering either as an alias of the rung below would
   be the worst failure available here: every cell would run, every proof would pass, every
   output would be well formed, and the arm would not contain the mechanism its name claims. So
   they are registered to a factory that RAISES and names exactly which components are missing.
   A driver that asks for one gets a recorded blocker, which is what D172's overnight rules want,
   instead of a silent rung below.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

V6_LADDER: List[Dict[str, Any]] = [
    {"rung": 0, "name": "covex-v6-base", "adds": "hybrid-F-lhreq-noc3 rules",
     "implemented_by": "hybrid-F-lhreq-noc3", "ready": True,
     "committed_as": ["hybrid-F-lhreq-noc3"]},
    {"rung": 1, "name": "covex-v6-rules",
     "adds": "chunked just-in-time warming + saturation guard",
     "implemented_by": "v5-rules-2", "ready": True,
     "committed_as": ["v5-rules-2"]},
    {"rung": 2, "name": "covex-v6-state",
     "adds": ("per-type host retention (max_offload_tokens = 0 for alert and single-shot), TOUCH "
              "chosen by plan_state, residency belief corrected from engine telemetry including "
              "host hits, state-based pricing"),
     "implemented_by": None, "ready": False, "committed_as": [],
     "missing": ["plan_state has no caller outside the proofs",
                 "residency belief is not corrected from telemetry (telemetry_cached_tokens NULL)",
                 "no arm class exists for this rung"]},
    {"rung": 3, "name": "covex-v6-fair",
     "adds": "deficit feed (observe() called by the coordinator) + value reader on",
     "implemented_by": None, "ready": False, "committed_as": [],
     "missing": ["DeficitCounters.observe() has no caller, so every weight is 1.0",
                 "the value reader is off",
                 "the D165 lexicographic objective is not built",
                 "no arm class exists for this rung"]},
    {"rung": 4, "name": "covex-v6",
     "adds": ("the counterfactual: request, state and sync decisions, compound candidates, the "
              "episode-rule switch"),
     "implemented_by": "v5-full", "ready": True,
     "committed_as": ["v5-full"]},
]

# The OLD name -> rung map, for reading committed cells. `v5-rules` is NOT a rung: it is the
# naive per-frame warm-ahead design that `v5-rules-2` replaced, and it is recorded as superseded
# rather than mapped, because mapping it would put a different mechanism on rung 1.
OLD_TO_RUNG: Dict[str, Optional[str]] = {
    "hybrid-F-lhreq-noc3": "covex-v6-base",
    "v5-rules-2": "covex-v6-rules",
    "v5-rules-2-off": "covex-v6-rules (negative control: warming off)",
    "v5-rules-2-noguard": "covex-v6-rules (ablation: saturation guard off)",
    "v5-rules-2-nojit": "covex-v6-rules (ablation: chunked just-in-time warming off)",
    "v5-full": "covex-v6",
    "v5-full-off": "covex-v6 (negative control: counterfactual off, collapses to covex-v6-rules)",
    "v5-full-noguarddefer": "covex-v6 (ablation: defer-to-guard off)",
    "v5-full-nohealthy": "covex-v6 (ablation: healthy-regime filter off)",
    "v5-rules": None,          # superseded design, not a rung; see SUPERSEDED below
    "v5-rules-off": None,
    "v5-rules-noyield": None,
}

SUPERSEDED = {
    "v5-rules": ("the NAIVE PER-FRAME warm-ahead design (D150), replaced by v5-rules-2's CHUNKED "
                 "just-in-time warming and saturation guard (D160). It is NOT rung 1 under "
                 "another name: it is a different mechanism, and mapping it onto covex-v6-rules "
                 "would make a superseded design look like the committed one"),
}


class RungNotBuilt(RuntimeError):
    """A ladder rung was asked for by name before its components exist (D172 (3))."""


def _not_built(name: str) -> Callable[..., Any]:
    row = rung(name)

    def _raise(**_kw: Any) -> Any:
        raise RungNotBuilt(
            "%s is a spec v6 ladder rung whose components are NOT BUILT, so it has no arm and "
            "MUST NOT resolve to the rung below. Missing: %s. Build the rung, prove it, and "
            "register it; until then this is a recorded blocker and the driver should skip the "
            "item." % (name, "; ".join(row["missing"])))
    return _raise


def rung(name: str) -> Dict[str, Any]:
    for r in V6_LADDER:
        if r["name"] == name:
            return r
    raise KeyError("%r is not a spec v6 ladder rung; the rungs are %s"
                   % (name, [r["name"] for r in V6_LADDER]))


def rung_of_committed(arm_name: str) -> Optional[str]:
    """The rung a COMMITTED cell's arm belongs to, or None if it is not on the ladder."""
    return OLD_TO_RUNG.get(arm_name)


def describe(name: str) -> Dict[str, Any]:
    """The rung block every arm built under a v6 name puts in its own describe (D172 (3))."""
    r = rung(name)
    return {"ladder": "spec v6 section 10 (D172)", "rung": r["rung"], "name": r["name"],
            "adds_over_the_rung_below": r["adds"],
            "implemented_by": r["implemented_by"],
            "committed_under": list(r["committed_as"]),
            "cells_are_reused_not_rerun": bool(r["committed_as"]),
            "identity_proof": "live2/v6_alias_proof.py (decision digest on a dry cell)"}


def register() -> None:
    """Put the v6 names in live2's registry, so `arms.make_arm(name)` builds them.

    The ready rungs alias the EXACT class and keyword arguments of the committed arm, with the v6
    name passed through as the arm's own name so a NEW cell is labelled by its rung. The decision
    digest must be unchanged by that relabelling, which is what `v6_alias_proof.py` checks: if it
    is not, the name is reaching a decision and the alias is not an alias.
    """
    import arms as A
    import hybrid.hybrid_arm as HA
    HA.register()
    try:
        import arms_v5rules2 as R2
        R2.register()
    except Exception:                                                          # noqa: BLE001
        pass
    try:
        import arms_v5full as VF
        VF.register()
    except Exception:                                                          # noqa: BLE001
        pass

    # The committed registry's entries for v5-rules-2 and v5-full are lambdas that have already
    # bound `name=`, so an alias cannot go through them: it builds the SAME CLASS with the SAME
    # defaults and its own name. The class, not the lambda, is the thing the two share.
    def _alias(v6_name: str, target: str) -> None:
        if target in HA.CONFIGS:
            kw = dict(HA.CONFIGS[target])
            A.ARMS[v6_name] = (lambda n=v6_name, k=kw: HA.HybridArm(name=n, **k))
            return
        if target == "v5-rules-2":
            import arms_v5rules2 as _R2
            A.ARMS[v6_name] = (lambda n=v6_name, **kw: _R2.V5Rules2Arm(name=n, **kw))
            return
        if target == "v5-full":
            import arms_v5full as _VF
            A.ARMS[v6_name] = (lambda n=v6_name, **kw: _VF.V5FullArm(name=n, **kw))
            return
        raise KeyError("no alias construction is defined for target %r; an alias must name the "
                       "CLASS it shares with the committed arm, never go through a registry "
                       "lambda that has already bound a name" % target)

    for r in V6_LADDER:
        if r["ready"] and r["implemented_by"]:
            _alias(r["name"], r["implemented_by"])
        else:
            A.ARMS[r["name"]] = _not_built(r["name"])


def as_dict() -> Dict[str, Any]:
    return {"ladder": V6_LADDER, "old_to_rung": OLD_TO_RUNG, "superseded": SUPERSEDED,
            "rule_1": "committed cells keep their original names (D172 (1))",
            "rule_2": "an identical arm's cell is reused under the mapping, never rerun (D172 (2))",
            "rule_3": ("a rung that is not built raises rather than resolving to the rung below "
                       "(D172 (3) as implemented here)")}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
