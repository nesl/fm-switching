#!/usr/bin/env python3
"""D225 (3): LIST EVERY SWITCH THAT DIFFERS BETWEEN ADJACENT RUNGS, AND REFUSE THE ONES WITH NO D-ROW.

D225 (3) says: "a script lists every switch differing between adjacent rungs; any difference
without a D-row is a defect". This is that script. It reads switch state FROM CODE by constructing
the five rung arms and resolving every switch on each, then diffs rung 0 vs 1, 1 vs 2, 2 vs 3 and
3 vs 4 and checks each difference against ATTRIBUTION below. Unattributed differences are printed
as DEFECTs and make the exit status non-zero.

THE ONE THING THAT MAKES THIS SCRIPT CORRECT RATHER THAN PLAUSIBLE: THE COMPOSITION CHAIN.

The rungs are not a class hierarchy all the way down. Rungs 2, 3 and 4 inherit from `V6StateArm`,
whose MRO is `[V6StateArm, object]`: it does NOT subclass the rung-1 arm. It COMPOSES one, at
`self._rules` (arms_v6state.py:152), and `V5Rules2Arm` in turn composes the rung-0 arm at
`self._base`. Attribute access reaches them through `V6StateArm.__getattr__` (arms_v6state.py:219).

So a diff that reads only the arm's own `vars()` and class MRO finds `warm_ahead`, `just_in_time`,
`chunk_tokens`, `guard`, `guard_backlog`, `guard_lag_s`, `slice_tokens`, `over_limit_infeasible`,
`k_r`, `c3_always`, `cap` and nine more as PRESENT at rungs 0 and 1 and ABSENT at rungs 2 to 4, and
reports twenty inheritance breaks that do not exist. That exact false reading was produced while
building this script, by a walker that skipped `_rules` because these arm classes define
`__call__`, so `callable(_rules)` was true. The switches are all there, at identical values, one
and two objects down.

Hence `resolve()` walks the chain (`arm`, `arm._rules`, `arm._rules._base`, and any further
`_rules` / `_base` / `_feed` link) and records the OWNER of every switch beside its value. A switch
whose value differs between two owners on the SAME arm is reported too, under SHADOWED, because
that is the write-only field's cousin: the value a reader gets then depends on which object it
asks, and `__getattr__` makes the arm's own answer win silently.

WHAT COUNTS AS A SWITCH HERE. Two sources, unioned, because neither alone is enough:
  (a) DISCOVERED: every scalar attribute reachable on the chain. Catches switches nobody declared.
  (b) DECLARED READERS: the strict reader functions the arms themselves use
      (`arms_v6state.qcache_key_fix_enabled`, `release_recheck.arm_enables`, and the two
      counterfactual legs' `arm_enables`). Catches a switch whose stored form is not an attribute,
      and is the register the arms' own construction checks are written in.
A switch found only by (a) is marked DISCOVERED, so a reader can see which rows rest on a declared
contract and which on introspection.

REGISTER OF EVERY VALUE THIS SCRIPT PRINTS: switch state READ FROM CODE, at the sha the header
prints, by construction in this process. It is NOT live evidence that a mechanism fired. That is
the conformance matrix's own column, from committed cells, and this script never touches a cell.

USAGE
    python3 -I d225_switch_diff.py --live2 <path to experiments/orchestration/live2> [--json OUT]
Exit status: 0 if every adjacent-rung difference is attributed, 1 if any is not, 2 on error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RUNGS: List[Tuple[str, str]] = [
    ("rung0", "covex-v6-base"),
    ("rung1", "covex-v6-rules"),
    ("rung2", "covex-v6-state-final"),
    ("rung3", "covex-v6-fair-final"),
    ("rung4", "covex-v6-final"),
]

# ---------------------------------------------------------------------------------------------
# D-ROW ATTRIBUTION. One entry per switch that is ALLOWED to differ between adjacent rungs, with
# the D-row that makes it differ. Anything not in here that differs is a DEFECT under D225 (3).
# A D-row here is a CLAIM about the decision log, checked by `--check-d-rows` against
# research/policy_design_log.md: the row must exist. That the row says what the key claims is the
# verifying session's job, not this script's.
ATTRIBUTION: Dict[str, str] = {
    # rung 0 -> rung 1: chunked just-in-time warming and the saturation guard (D172 names the rung)
    "warm_ahead": "D156 (2), D160 (1)",
    "just_in_time": "D160 (1)",
    "chunk_tokens": "D160 (1)",
    "guard": "D160 (2), D178 (3)",
    "guard_backlog": "D178 (3)",
    "guard_lag_s": "D166 (3), D178 (3)",
    "slice_tokens": "D160 (1)",
    "arm_version": "D172 (naming); not a mechanism",
    "name": "D172 (naming); not a mechanism",
    "live2_source": "D172 (naming); not a mechanism",
    "decides": "D172 (naming); not a mechanism",
    # rung 1 -> rung 2: per-type host retention, touch, belief from telemetry, state pricing
    "live2_offload_controls": "D167, D150 STATE",
    "live2_touch_requests": "D150 STATE, D209 (2) hit 22",
    "live2_belief_apply": "D47, D150 STATE, D211",
    "live2_state_priced_costs": "D173 (2)",
    "live2_d162_pricing": "D162, D173 (1), D174 (1)",
    "live2_charge_mode": "D174 (1)",
    "plan_state": "D26, D150 STATE",
    "live2_qcache_key_fix": "D188 (2), D208 (2)",
    "c5_attr_self_released": "D184 (1), D186",
    # rung 2 -> rung 3: the per-device deficit feed, its consumers, the alert release re-check
    "live2_deficit_feed": "D185 (1), (3)",
    "live2_release_recheck": "D179 (4), D198 (2)(b), D208 (1)",
    "live2_release_recheck_types": "D179 (4), D198 (2)(b)",
    # rung 3 -> rung 4: the two counterfactual legs
    "live2_cf_protect_defer": "D165 (D), D184 (2), D190 (3)",
    "live2_cf_request_defer": "D191 (1), D151 (3)",
    "pd_base_key": "D208 (2); base selector, not a mechanism",
    # The counterfactual's bar register: WHOSE deficit weight scales MARGIN_CF. D171 (1) fixes it
    # to the device the decision is about, which is what "decider" means here.
    "_pd_bar_reading": "D171 (1), D191 (2)",
    # Step 4 negative controls (D124 GATE, D218 (1) "Step 4 controls collapse the branch to BASE").
    # Both default to the inert setting; the scale is the margin-huge control's multiplier.
    "MARGIN_CONTROL_SCALE": "D124, D218 (1) negative control",
    "_pd_control_harm_zero": "D124, D218 (1) negative control",
    "_pd_control_margin_huge": "D124, D218 (1) negative control",
    # The per-period DeltaJ evaluation cap. None means NO cap, which is the state every reported
    # cell runs in: D116 forbids enabling it overnight and no cell sets it. Write arms_v6state.py
    # :187, read arms_v6state.py:212-213 (and arms_v5full.py:112, :125-126 for the v5-full arm).
    "_cf_budget_ms": "D99 (3), D116",
    "_cf": "D99 (3), D116; cached counterfactual engine handle, built by _cf_engine()",
    # A CAPACITY INPUT, not a tuned switch (D56: capacities are inputs). None at CONSTRUCTION is
    # correct: the value arrives through live2_configure(gpu_kv_tokens=...) at arms_v6cf.py:170 and
    # is read at arms_v6cf.py:315. Because this script reads state at construction, this row's
    # value here is NOT the live value; a committed cell must be checked for that.
    "_pd_gpu_kv_tokens": "D56, D223 (2); configure-time capacity input, read arms_v6cf.py:315",
}

# INTERNAL TWINS. A private field that stores the SAME switch as a public `live2_*` one, so its
# D-row is the public switch's. This is an indirection and not a suppression: the diff still
# prints the row, and prints "via <public switch>" beside the D-row, so a verifier can see that
# the attribution is inherited and go check that the two really are one switch.
INTERNAL_OF: Dict[str, str] = {
    "_feed_on": "live2_deficit_feed",
    "_feed_gain": "live2_deficit_feed",
    "_feed_ordering": "live2_deficit_feed",
    "_feed_split": "live2_deficit_feed",
    "gain": "live2_deficit_feed",
    "_fairfeed_base_name": "live2_deficit_feed",
    "n_offers": "live2_deficit_feed",
    "n_completions": "live2_deficit_feed",
    "_pd_base_key": "live2_cf_protect_defer",
    "_pd_w_source": "live2_cf_protect_defer",
}

# Attributes that are run-time state or bookkeeping, not switches. Named explicitly rather than
# pattern-matched, so adding one is a visible decision.
NOT_SWITCHES = {
    "dry", "dry_margin", "stats", "state_deltas", "pd_decisions", "pd_harms", "rd_decisions",
    "rd_nets", "rd_bars", "rd_trace_kept", "rd_trace_crossed", "pd_trace_kept",
    "pd_trace_crossed", "_q_cache", "_q_cache_key", "_qcache_key_fix_resolved",
    "W_WIRED_PROOF", "_planner_reads_feed_declared",
    # A pure memo key: written and compared only to invalidate a cache, never to pick a branch.
    # The read site is named so this exemption is checkable: arms_v6cf.py:203-204.
    "_pd_rows_key",
}

SCALAR = (bool, int, float, str, type(None))

# Attributes that are DICTS OF SWITCHES and must be expanded component by component.
SWITCH_DICTS = {"sw"}


class SwitchDiffError(RuntimeError):
    pass


def _bootstrap(live2: Path) -> None:
    for p in (live2, live2.parent, live2.parent.parent, live2 / "v5", live2 / "fleet",
              live2 / "hybrid", live2.parent / "baselines"):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def _chain(arm: Any) -> List[Tuple[str, Any]]:
    """The composition chain, outermost first. See the module docstring on why this exists."""
    out: List[Tuple[str, Any]] = [("arm", arm)]
    seen = {id(arm)}
    i = 0
    while i < len(out):
        path, obj = out[i]
        i += 1
        # `_b7` is the innermost link: HybridArm wraps a B7EdfFeasibilityArm and delegates to it
        # (hybrid/hybrid_arm.py:303-304), so b7's own switches are reachable from every rung.
        for link in ("_rules", "_base", "_feed", "_b7"):
            nxt = vars(obj).get(link) if hasattr(obj, "__dict__") else None
            if nxt is not None and hasattr(nxt, "__dict__") and id(nxt) not in seen:
                seen.add(id(nxt))
                out.append((path + "." + link, nxt))
    return out


def _scalars(obj: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    names = set(vars(obj)) if hasattr(obj, "__dict__") else set()
    for cls in type(obj).__mro__:
        names |= set(vars(cls))
    for n in sorted(names):
        if n.startswith("__") or n in NOT_SWITCHES:
            continue
        try:
            v = getattr(obj, n)
        except Exception:                                                      # noqa: BLE001
            continue
        if isinstance(v, SCALAR):
            out[n] = v
        elif isinstance(v, (tuple, list)) and v and all(isinstance(x, SCALAR) for x in v):
            out[n] = list(v)
        elif n in SWITCH_DICTS and isinstance(v, dict):
            # A DICT OF SWITCHES IS STILL SWITCHES. `HybridArm.sw` (hybrid/hybrid_arm.py:188)
            # holds C1 to C6, which are the whole of rung 0's mechanism set; a scalar-only walk
            # skips the dict and reports rung 0 as having no switches at all. Expanded as
            # `sw[c1]` so each component diffs on its own.
            for k2, v2 in sorted(v.items()):
                if isinstance(v2, SCALAR):
                    out["%s[%s]" % (n, k2)] = v2
    return out


def _declared_readers(live2: Path, arm: Any) -> Dict[str, Any]:
    """The arms' OWN strict readers. A reader that raises is recorded, never swallowed."""
    out: Dict[str, Any] = {}

    def call(key: str, fn: Any, *a: Any) -> None:
        try:
            out[key] = fn(*a)
        except Exception as e:                                                 # noqa: BLE001
            out[key] = "<reader raised %s: %s>" % (type(e).__name__, e)

    try:
        import arms_v6state as VS
        call("READER:qcache_key_fix_enabled", VS.qcache_key_fix_enabled, arm)
    except Exception as e:                                                     # noqa: BLE001
        out["READER:qcache_key_fix_enabled"] = "<import failed: %s>" % e
    try:
        import release_recheck as RR
        call("READER:release_recheck.arm_enables", RR.arm_enables, arm)
        call("READER:release_recheck.types_for", lambda a: list(RR.types_for(a)), arm)
    except Exception as e:                                                     # noqa: BLE001
        out["READER:release_recheck.arm_enables"] = "<import failed: %s>" % e
    try:
        import cf_request_defer as RD
        call("READER:cf_request_defer.arm_enables", RD.arm_enables, arm)
    except Exception as e:                                                     # noqa: BLE001
        out["READER:cf_request_defer.arm_enables"] = "<import failed: %s>" % e
    try:
        import cf_protect_defer as PD
        if hasattr(PD, "arm_enables"):
            call("READER:cf_protect_defer.arm_enables", PD.arm_enables, arm)
    except Exception as e:                                                     # noqa: BLE001
        out["READER:cf_protect_defer.arm_enables"] = "<import failed: %s>" % e
    src = getattr(arm, "_planner_w_source", None)
    out["READER:planner_w_source.IS_DECLARED_CONSTANT"] = (
        "<no _planner_w_source>" if src is None
        else bool(getattr(src, "IS_DECLARED_CONSTANT", True)))
    return out


def resolve(live2: Path, arm_name: str) -> Dict[str, Any]:
    import arms as A
    arm = A.ARMS[arm_name]()
    owners: Dict[str, List[Tuple[str, Any]]] = {}
    for path, obj in _chain(arm):
        for n, v in _scalars(obj).items():
            owners.setdefault(n, []).append((path, v))
    flat: Dict[str, Any] = {}
    shadowed: Dict[str, List[Tuple[str, Any]]] = {}
    for n, sightings in owners.items():
        flat[n] = sightings[0][1]                      # outermost wins, as __getattr__ does
        vals = {json.dumps(v, default=str) for _, v in sightings}
        if len(vals) > 1:
            shadowed[n] = sightings
    flat.update(_declared_readers(live2, arm))
    return {"arm": arm_name, "cls": type(arm).__name__,
            "mro": [c.__name__ for c in type(arm).__mro__],
            "chain": [p for p, _ in _chain(arm)],
            "switches": flat,
            "owners": {n: [[p, v] for p, v in s] for n, s in owners.items()},
            "shadowed": {n: [[p, v] for p, v in s] for n, s in shadowed.items()}}


def _known_d_rows(log: Path) -> set:
    import re
    if not log.exists():
        return set()
    return set(re.findall(r"\|\s*(D\d+[a-z]?)\s*\|", log.read_text()))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live2", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--design-log", default=None,
                    help="research/policy_design_log.md; every ATTRIBUTION D-row must exist in it")
    args = ap.parse_args(argv)
    live2 = Path(args.live2).resolve()
    if not (live2 / "arm_names_v6.py").exists():
        raise SwitchDiffError("--live2 %s does not hold arm_names_v6.py" % live2)
    _bootstrap(live2)

    # The sha is the register of every value below, so an unresolved sha is announced loudly
    # rather than printed as the word "unknown" in a field a reader skims. A matrix row whose
    # provenance is the string "unknown" is a row nobody can reproduce.
    sha = ""
    p = subprocess.run(["git", "-C", str(live2), "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=False)
    sha = p.stdout.strip()
    if p.returncode != 0 or not sha:
        sha = ("UNRESOLVED (git -C %s rev-parse HEAD exited %d). Every switch value below is "
               "therefore UNATTRIBUTABLE TO A COMMIT: run this inside a real checkout, not an "
               "exported snapshot, before citing it in the conformance matrix."
               % (live2, p.returncode))

    import arm_names_v6 as AN
    import arms_final_ladder as FL
    AN.register()
    FL.register()

    res = {tag: resolve(live2, name) for tag, name in RUNGS}

    print("D225 (3) SWITCH DIFF BETWEEN ADJACENT RUNGS")
    print("register: switch state READ FROM CODE by construction in this process, not live evidence")
    print("tree sha (git -C %s rev-parse HEAD): %s" % (live2, sha))
    for tag, name in RUNGS:
        r = res[tag]
        print("  %-6s %-22s %-22s chain=%s" % (tag, name, r["cls"], " -> ".join(r["chain"])))
    print("")

    defects: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    for (lo_tag, _), (hi_tag, _) in zip(RUNGS, RUNGS[1:]):
        lo, hi = res[lo_tag]["switches"], res[hi_tag]["switches"]
        keys = sorted(set(lo) | set(hi))
        pair_rows = []
        for k in keys:
            a = lo.get(k, "<ABSENT>")
            b = hi.get(k, "<ABSENT>")
            if json.dumps(a, default=str) == json.dumps(b, default=str):
                continue
            d = ATTRIBUTION.get(k)
            via = None
            if d is None and k in INTERNAL_OF:
                via = INTERNAL_OF[k]
                d = ATTRIBUTION.get(via)
                if d is not None:
                    d = "%s (via %s)" % (d, via)
            if d is None and k.startswith("READER:"):
                # A declared reader's value is the public switch's value by construction; its
                # D-row is that switch's. Named explicitly so the reader rows are not silently
                # exempt the way the first draft of this script left them.
                for pub, rd in (("live2_release_recheck", "release_recheck"),
                                ("live2_cf_request_defer", "cf_request_defer"),
                                ("live2_cf_protect_defer", "cf_protect_defer"),
                                ("live2_qcache_key_fix", "qcache_key_fix")):
                    if rd in k:
                        via = pub
                        d = "%s (via reader for %s)" % (ATTRIBUTION.get(pub), pub)
                        break
                if "planner_w_source" in k:
                    via = "planner limb"
                    d = "D203 (1), D206 (2), D208 (2) (via reader for the planner limb)"
            row = {"pair": "%s -> %s" % (lo_tag, hi_tag), "switch": k,
                   "from": a, "to": b, "d_row": d, "via": via,
                   "source": "DECLARED" if k.startswith("READER:") or k in ATTRIBUTION
                             else ("INTERNAL-TWIN" if k in INTERNAL_OF else "DISCOVERED")}
            pair_rows.append(row)
            rows.append(row)
            if d is None:
                defects.append(row)
        print("=== %s -> %s : %d switch differences" % (lo_tag, hi_tag, len(pair_rows)))
        for row in pair_rows:
            mark = "DEFECT: no D-row" if row["d_row"] is None else row["d_row"]
            print("    %-42s %-20s -> %-20s  %s"
                  % (row["switch"], str(row["from"])[:20], str(row["to"])[:20], mark))
        print("")

    print("=== SHADOWED SWITCHES (same arm, two owners, two values)")
    any_shadow = False
    for tag, _ in RUNGS:
        for n, s in sorted(res[tag]["shadowed"].items()):
            any_shadow = True
            print("    %-6s %-30s %s" % (tag, n, s))
    if not any_shadow:
        print("    none")
    print("")

    if args.design_log:
        known = _known_d_rows(Path(args.design_log))
        import re
        missing = sorted({d for v in ATTRIBUTION.values() for d in re.findall(r"D\d+[a-z]?", v)}
                         - known)
        print("=== ATTRIBUTION D-ROWS NOT FOUND IN %s: %s"
              % (args.design_log, missing or "none"))
        print("")

    print("=== VERDICT")
    print("    %d switch differences across 4 adjacent pairs" % len(rows))
    print("    %d UNATTRIBUTED (D225 (3) defects)" % len(defects))
    for row in defects:
        print("      DEFECT %s %s: %r -> %r" % (row["pair"], row["switch"], row["from"], row["to"]))

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"sha": sha, "rungs": res, "differences": rows, "defects": defects}, indent=1,
            default=str))
        print("    json: %s" % args.json)
    return 1 if defects else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SwitchDiffError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        sys.exit(2)
