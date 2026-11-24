#!/usr/bin/env python3
"""THE PASS-1 SAFETY FACTOR AND DECODE QUANTITY, READ FROM A COMMITTED FILE (D222 (1) item 4).

    "safety factor = q90 of (ENGINE COMPLETION / D162 PREDICTED), on the committed RUNG-3 cells,
     HEALTHY WINDOWS ONLY, with NETWORK OUTSIDE THE FACTOR"        (user ruling, 2026-11-24)

THIS FILE READS THE NUMBER. IT DOES NOT CHOOSE ONE. Same contract as `d190_measured_safety`, which
it supersedes on the question-deferral path: the value is parsed out of a committed result file at
import time, the quantile and the sample are named, and a missing file RAISES rather than becoming
a quiet default. A default here would make every deferral look safe and the mechanism look as
though it worked.

WHAT CHANGED AND WHY, because the old value was not merely imprecise. `d190_measured_safety`'s
1.8721 is the nearest-rank q90 of observed FIRST TOKEN over D162's predicted FIRST TOKEN on n = 5
rows. Two things were wrong with using it where it was used:

  1. IT WAS APPLIED IN THE WRONG REGISTER. `cf_cost.latest_safe_start` multiplies it into
     `pred.total_s`, which is first token PLUS decode PLUS the link. Measured on the same rung-3
     cells with the predictor the code ACTUALLY used (the old `cost_model_gate.json` by-arm split,
     whose queue feature is a COUNT OF REQUESTS and whose queue term was being passed a literal
     zero), the completion ratio's q90 is 8.2901 against the 1.8721 in force: a 4.43x register
     mismatch, and the direct cause of deferrals long enough to push a question past its deadline.
  2. AT n = 5 THE NEAREST-RANK q90 IS THE SAMPLE MAXIMUM, which is an algebraic identity and not
     a tail estimate.

The value here is measured on n = 255 in ONE register throughout: engine-reported completion over
the D162 model's predicted ENGINE service, with no link term on either side, because the ruling
puts the network outside the factor. It is then APPLIED as `need = safety * engine_s + link`
(`cf_cost.latest_safe_start_network_outside`), which is the only form in which that phrase is
literally true; multiplying a link-inclusive total by a factor fitted without the link would put
the network back inside it at about a tenth of a typical predicted service.

NOT TUNING, AND THE PROVENANCE IS THE CHECK. The ratios come from `covex-v6-fair-final` at seeds 4
and 5, the RUNG-3 BASE rung 4 is built on, never from a rung-4 cell. That is the practice D180 to
D182 used to derive the D179 floors from committed `covex-v6-base` cells.

THE DECODE QUANTITY IS HERE TOO, because it has the same provenance and the same owner. Item 1
needs a queued-ahead DECODE token count, and D162's `queue_decode_ahead` is summed OUTPUT tokens.
Measured on the same cells: every request emits exactly 2 output tokens and a touch emits 1
(min = p50 = max over 18,643 requests). That is a CONSTANT where a distribution was checked for,
and it is chased to its source rather than trusted: the answer is one letter plus a stop and the
committed `max_tokens` (`bodies.SH_GEN` 8, `bodies.RECALL_GEN` 512) is never approached. A
constant that is correct is still a constant, so it is declared as a measured PROXY and the
`PROXY` dict below says what it is and is not valid for.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE_REL = "results/orchestration/live2/d222_pass1/d222_safety_refit.json"
SOURCE = REPO / SOURCE_REL


class MeasuredSafetyUnavailable(RuntimeError):
    """The committed source could not be read. NOT silently replaced by a default."""


def load() -> Dict[str, Any]:
    if not SOURCE.exists():
        raise MeasuredSafetyUnavailable(
            "the committed source %s is not in this tree, so the pass-1 safety factor cannot be "
            "MEASURED and will not be defaulted" % SOURCE_REL)
    d = json.loads(SOURCE.read_text())
    for k in ("safety_factor", "n", "decode_tokens_by_kind"):
        if k not in d:
            raise MeasuredSafetyUnavailable(
                "%s carries no %r, so the value this module exists to read is absent"
                % (SOURCE_REL, k))
    # THE CONSUMER CONTRACT `d190_measured_safety` ESTABLISHED IS KEPT, so `cf_request_defer` reads
    # the same key names from either module and the swap is a one-line import rather than a set of
    # edits at every read. A missing `source` here would have surfaced as a KeyError inside a
    # decision - it did, in the first smoke run - which is the right place for it to surface and
    # the reason the key is supplied rather than the reader loosened to `.get`.
    d.setdefault("source", SOURCE_REL)
    return d


INFO: Dict[str, Any] = load()
SAFETY_FACTOR: float = float(INFO["safety_factor"])

# Output tokens per queued-ahead request, by the kind the harm rows carry. `alert` is the dashcam
# monitor request (`kind == "monitor"` in the request log, 2 tokens); `recall` and `assistance` are
# the recall path (2 tokens). Keyed by the `qtype` `arms_v6cf._pd_others` puts on every row, so the
# caller never has to translate a name.
_DK = INFO["decode_tokens_by_kind"]
DECODE_TOKENS_BY_QTYPE: Dict[str, int] = {
    "alert": int(_DK["monitor"]["p50"]),
    "recall": int(_DK["recall_robot"]["p50"]),
    "assistance": int(_DK["recall_assistance"]["p50"]),
}
DECODE_TOKENS_DEFAULT = int(_DK["recall_robot"]["p50"])

PROXY = {
    "quantity": "queued-ahead DECODE tokens, per pending request, by query type",
    "proxy": "the committed p50 output_tokens of that type in the rung-3 cells: %r"
             % (DECODE_TOKENS_BY_QTYPE,),
    "what_it_actually_measures": (
        "the output tokens the engine actually emitted for 18,643 requests in "
        "covex-v6-fair-final at seeds 4 and 5: monitor 2, robot recall 2, assistance 2, touch 1, "
        "each with min = p50 = max"),
    "valid_for": ("sizing D162's queue_decode_ahead term for a pending request on THIS workload, "
                  "where the answer is one letter plus a stop and max_tokens is never approached"),
    "not_valid_for": ("a workload whose answers are long. It is a population constant, so a "
                      "request that generated more would be under-priced, and the under-pricing "
                      "would be in the OPTIMISTIC direction (a shorter predicted service, a later "
                      "latest safe start), which is the direction that costs deadlines"),
    "committed_upper_bounds_not_used": ("bodies.SH_GEN max_tokens 8 and bodies.RECALL_GEN "
                                        "max_tokens 512 are the BOUNDS; using them would "
                                        "over-price decode by 4x and 256x respectively"),
}


def report() -> Dict[str, Any]:
    """Everything a cell should record about where this factor came from."""
    return {"safety_factor": SAFETY_FACTOR,
            "quantile": INFO.get("quantile"), "quantile_method": INFO.get("quantile_method"),
            "n": INFO.get("n"), "min": INFO.get("min"), "p50": INFO.get("p50"),
            "max": INFO.get("max"),
            "fit_cells": INFO.get("fit_cells"), "fit_sample": INFO.get("fit_sample"),
            "healthy_window_filter": INFO.get("healthy_window_filter"),
            "superseded_value": INFO.get("superseded_value"),
            "source": SOURCE_REL,
            "decode_tokens_by_qtype": dict(DECODE_TOKENS_BY_QTYPE),
            "decode_proxy": PROXY,
            "applied_as": ("need = safety * engine_s + LINK_RTT_S "
                           "(cf_cost.latest_safe_start_network_outside), so the network is "
                           "outside the factor as ruled")}


def main() -> int:
    print(json.dumps(report(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
