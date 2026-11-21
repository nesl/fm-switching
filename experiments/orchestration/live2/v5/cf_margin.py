#!/usr/bin/env python3
"""THE ONE DECLARED CONSTANT the v5 counterfactual reads for its deviation margin (D151 (1),
D154 (2)), plus the safety factor of the latest-safe-start rule (spec v5 section 5.2).

WHY A MODULE FOR ONE CONSTANT. D151 (1) requires the margin to be fixed in advance and NEVER
TUNED, and spec v5 section 4 says "never tuned" is an AUDITABLE CLAIM and not a promise. An
auditable claim needs a single place the value can come from: if the counterfactual could take a
margin from a per-cell argument, a config, a sweep registry or a default parameter, a reader could
not tell from the code whether it had been tuned. So:

  * `MARGIN_CF` is declared here and nowhere else in `cf_*`;
  * no `cf_*` function takes a margin argument on its scorable path;
  * `resolve_margin()` is the only read, and it RAISES while the constant is unset;
  * `margin_declaration_audit()` greps the tree for every other declaration of the name, so a
    second declaration is a reported conflict and not a silent fork.

WHY IT IS UNSET, AND WHY THAT BLOCKS EVERY v5 CELL. D154 (2) fixes the VALUE: it is set ONCE,
when the D151 (6) cost-model gate passes, equal to that gate's HELD-OUT 90th-percentile ABSOLUTE
PREDICTION ERROR in the objective's units (expected correct on-time answers), frozen before any
v5 cell and identical in every cell. The gate does NOT pass (`reports/study_policy_v2_gate.md`,
spec v5 section 12: decode over-predicts by 25 to 32 percent in every held-out class, and warm is
confounded with arm). So the value cannot be computed yet and the constant stays `None`.

TWO SEPARATE REASONS v5 CANNOT RUN, and they are not the same reason:
  1. the gate FAILS, so D154 (2)'s quantity is not available (a MEASUREMENT gate);
  2. even if the gate passed, D154 (2) names a p90 absolute prediction error "in the objective's
     units", and the gate's error is in SECONDS of service time while the objective is in expected
     correct answers. No committed conversion exists. `UNIT_CONVERSION_GAP` states that, because a
     margin set by an invented conversion would be a tuned margin wearing a measurement's clothes.

`DRY` RUNS. Everything in `cf_*` can be exercised without a margin by passing `dry=True` with an
explicit `dry_value`. Every output of a dry path carries `scorable: False` and
`margin_source: "DRY_OVERRIDE"`, and `cf_planner` refuses to emit a scorable decision in that
mode. A dry proof is a proof about the code, never a result about the policy.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[4]
GATE_JSON = REPO / "results/orchestration/live2/frozen_test/cost_model_gate.json"

# ---------------------------------------------------------------------------
# THE CONSTANT. Do not give it a number until D154 (2) is satisfiable (see module docstring).
# A placeholder number here would be read by a later session as a ruling.
MARGIN_CF: Optional[float] = None

MARGIN_CF_RULE = (
    "D154 (2): MARGIN_CF is set ONCE, when the D151 (6) cost-model gate passes, equal to that "
    "gate's held-out p90 ABSOLUTE prediction error in the objective's units (expected correct "
    "on-time answers); frozen before any v5 cell, identical in every cell, never swept. The gate "
    "does not pass, so it is not set, so NO v5 CELL MAY RUN (spec v5 section 12.1, gap G8).")

UNIT_CONVERSION_GAP = (
    "D154 (2) names the gate's p90 absolute prediction error IN THE OBJECTIVE'S UNITS. The gate "
    "(`cost_model_gate.py`) predicts first-token and decode SECONDS, so its error is in seconds; "
    "the objective is in expected correct answers delivered by the deadline. No committed rule "
    "converts one into the other. `cf_cost.service_error_to_objective_units` shows the only "
    "defensible route (push the p90 service error through the delivery-probability curve and the "
    "committed accuracy table, which makes the margin a function of the question population) and "
    "REFUSES to return a number. Until the conversion is RULED, MARGIN_CF cannot be set even by a "
    "gate that passes.")


class MarginUnset(RuntimeError):
    """A scorable deviation was asked for while MARGIN_CF is unset (D154 (2), gap G8)."""


@dataclass(frozen=True)
class Margin:
    value: float
    source: str
    scorable: bool


def resolve_margin(dry: bool = False, dry_value: Optional[float] = None) -> Margin:
    """The ONLY read of MARGIN_CF anywhere in `cf_*`.

    Scorable path: returns the declared constant, or raises `MarginUnset`. Dry path: returns the
    caller's explicit value, marked NOT SCORABLE, so a dry proof can never be mistaken for a cell.
    """
    if dry:
        if dry_value is None:
            raise ValueError("a dry margin must be explicit: pass dry_value")
        return Margin(float(dry_value), "DRY_OVERRIDE", False)
    if MARGIN_CF is None:
        raise MarginUnset(MARGIN_CF_RULE)
    return Margin(float(MARGIN_CF), "cf_margin.MARGIN_CF", True)


def margin_declaration_audit(root: Optional[Path] = None) -> Dict[str, Any]:
    """Every declaration of the name `MARGIN_CF` in the repository, so "one constant" is checkable.

    A second declaration is not a style problem. `v5/value_readers.py` carries `MARGIN_CF = 0.05`,
    a placeholder written before D154 (2) existed; a counterfactual that imported THAT one would
    be deviating from base on a number no ruling ever set. This audit reports the conflict; the
    file belongs to another session, so it is reported and not edited.
    """
    root = root or REPO
    pat = re.compile(r"^\s*MARGIN_CF\b\s*[:=]")
    hits: List[Dict[str, Any]] = []
    try:
        files = subprocess.run(["git", "grep", "-l", "MARGIN_CF", "--", "*.py"],
                               cwd=str(root), capture_output=True, text=True, timeout=60)
        names = [x for x in files.stdout.splitlines() if x.strip()]
    except Exception:                                                          # noqa: BLE001
        names = [str(p.relative_to(root)) for p in root.rglob("*.py")]
    # `git grep` lists TRACKED files only, so this file is missing from it until it is committed.
    # A self-audit that cannot see its own declaration would report the conflict and not the
    # constant, which is the wrong half.
    me = str(Path(__file__).resolve().relative_to(root))
    if me not in names:
        names.append(me)
    for name in names:
        p = root / name
        try:
            lines = p.read_text().splitlines()
        except Exception:                                                      # noqa: BLE001
            continue
        for i, line in enumerate(lines, 1):
            if pat.match(line):
                hits.append({"file": name, "line": i, "text": line.strip()})
    mine = [h for h in hits if h["file"].endswith("v5/cf_margin.py")]
    others = [h for h in hits if not h["file"].endswith("v5/cf_margin.py")]
    return {
        "declarations": hits,
        "declared_in_cf_margin": len(mine),
        "declared_elsewhere": len(others),
        "single_declaration_for_cf": len(mine) == 1,
        "conflicts": others,
        "verdict": ("ONE DECLARATION for the counterfactual" if len(mine) == 1 and not others else
                    "CONFLICT: MARGIN_CF is declared in more than one place; the counterfactual "
                    "reads cf_margin.MARGIN_CF and nothing else, and the other declarations must "
                    "be removed or deferred to this one by the sessions that own those files"),
        "note": ("`v5/value_readers.py::MARGIN_CF = 0.05` is a pre-D154 placeholder. It is a "
                 "declaration this session does not own and must not be imported by any cf_* "
                 "module; cf_* never reads it."),
    }


# ---------------------------------------------------------------------------
# The safety factor of the latest-safe-start rule (spec v5 section 5.2)
#
# "The safety factor is MEASURED, not chosen, and comes from the held-out predicted-versus-actual
# check of section 12. Until that check passes, the safety factor and the margin both widen, and
# the run report says so." So it is a FUNCTION of committed data, never a literal: the p90 of
# actual service over predicted service on the held-out split, floored at 1.0. It is widened by
# construction while the gate fails, because the gate's own held-out ratio is what sets it.

SAFETY_QUANTILE = 0.90          # declared: the same p90 register D154 (2) uses for the margin
SAFETY_FLOOR = 1.0              # a factor below 1 would plan to start after the deadline


def safety_factor(residuals: Dict[str, Any], quantile: float = SAFETY_QUANTILE) -> Dict[str, Any]:
    """Derive the latest-safe-start safety factor from a committed residual summary.

    `residuals` is the object `cf_cost.load_residuals()` returns, built by `cf_proofs.py` from the
    committed request logs through the committed `cost_model_gate` model. The factor is the
    quantile of (actual service / predicted service) on the HELD-OUT-BY-ARM split, because v5 is a
    policy no fitted arm produced and section 12 names the by-arm split as the one that matters.
    """
    from cf_cost import ratio_quantile                                         # noqa: PLC0415
    q = ratio_quantile(residuals, quantile)
    return {
        "safety_factor": max(float(q), SAFETY_FLOOR),
        "raw_quantile": float(q),
        "quantile": quantile,
        "floored_at": SAFETY_FLOOR,
        "measured_not_chosen": True,
        "source": residuals.get("_source"),
        "split": residuals.get("split"),
        "widened_because_the_gate_fails": True,
        "gate_status": ("FAILS: decode over-predicts by 25 to 32 percent in every held-out class "
                        "and warm is confounded with arm (spec v5 section 12)"),
    }


def main() -> int:
    out = {
        "_what": "the one declared margin constant, its rule, and its audit",
        "MARGIN_CF": MARGIN_CF,
        "MARGIN_CF_is_set": MARGIN_CF is not None,
        "MARGIN_CF_RULE": MARGIN_CF_RULE,
        "UNIT_CONVERSION_GAP": UNIT_CONVERSION_GAP,
        "audit": margin_declaration_audit(),
        "gate_json_exists": GATE_JSON.exists(),
    }
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
