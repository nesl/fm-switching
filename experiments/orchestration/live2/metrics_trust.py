#!/usr/bin/env python3
"""E3 (D227): IS THIS CELL'S ENGINE /metrics SCRAPE EVIDENCE, OR AN ABSENCE?

    "every cell.json carries a one-line metrics_health field recording whether that cell's engine
     /metrics scrape succeeded (scrape count, failures, last-success time, metric names found); a
     cell whose scrape failed or never ran is flagged and its engine-metric quantities are not
     trusted"                                                           (D227, source STATUS.md:75)

WHY A FLAG WOULD NOT HAVE DONE, which is the whole reason this module exists rather than a boolean
in `cell.json`. THREE situations produce the SAME BYTES today:

    1. the scrape never ran            `gpu_kv_fraction` is 0.0 and `pd_kv_bound_by_engine_metric`
                                       is absent because NOTHING READ THE ENGINE
    2. the scrape ran and failed       the same two, because a failed fetch is served the D209 (2)
                                       conservative value or the last good one
    3. the scrape ran and the metric   the same two, and THIS ONE IS A RESULT: the engine metric
       never bound                     was observed and the residency belief was tighter on every
                                       decision

That is the exact state of all four committed rung-4 1x cells: `pd_kv_bound_by_engine_metric` is
ABSENT at every seed and `pd_kv_bound_by_belief` equals `pd_decisions`, and before E1 there was no
way to tell case 1 from case 3 from inside the cell. Case 1 is an ABSENT LINK (CLAUDE.md Step 2),
case 2 is a degraded run, and only case 3 is a finding about the policy. `state` separates them and
`engine_metrics_trusted` is true in case 3 alone.

THIS MODULE INVENTS NO STATE THE COUNTERS DO NOT SUPPORT. It reads the backend's own health block,
which `live/adapter.py` computes from counters it increments at the fetch, and the list of
affected quantities is `adapter.UNTRUSTED_WHEN_SCRAPE_NOT_OK` rather than a second list here. If
the block is missing altogether the state is `unknown_no_backend_block`, which is NOT folded into
`never_scraped`: an old cell written before E1 and a new cell whose backend went missing are
different facts and are reported differently.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent / "live")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TRUSTED_STATE = "scraped_ok"
STATES = ("scraped_ok", "scraped_and_failed", "never_scraped", "dry_no_server",
          "unknown_no_backend_block")


def _untrusted_names():
    try:
        from adapter import UNTRUSTED_WHEN_SCRAPE_NOT_OK                       # noqa: PLC0415
        return list(UNTRUSTED_WHEN_SCRAPE_NOT_OK)
    except Exception:                                                          # noqa: BLE001
        # The list lives with the scrape policy and is not restated here; if the module cannot be
        # imported the cell says so rather than carrying a second, drifting copy.
        return []


def cell_metrics_health(res: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    """The one-line field for `cell.json`, from the coordinator result's backend block."""
    be = (res or {}).get("backend") or {}
    h = be.get("metrics_health") if isinstance(be, dict) else None
    if dry_run:
        return {"state": "dry_no_server", "engine_metrics_trusted": False,
                "n_scrapes": 0, "n_failures": 0, "last_success_t": None,
                "metric_names_found": [], "untrusted_quantities": _untrusted_names(),
                "why": ("a dry cell has no engine, so coordinator.py never sets st.metrics and "
                        "every engine-metric quantity in this cell is identically its default")}
    if not isinstance(h, dict) or not h:
        return {"state": "unknown_no_backend_block", "engine_metrics_trusted": False,
                "n_scrapes": None, "n_failures": None, "last_success_t": None,
                "metric_names_found": [], "untrusted_quantities": _untrusted_names(),
                "why": ("the backend published no metrics_health block, so this cell cannot say "
                        "whether its scrape ran; it predates E1 or lost its backend block")}
    state = str(h.get("state") or "unknown_no_backend_block")
    trusted = bool(h.get("engine_metrics_trusted", False)) and state == TRUSTED_STATE
    out = {"state": state, "engine_metrics_trusted": trusted,
           "n_scrapes": h.get("n_scrapes"), "n_failures": h.get("n_failures"),
           "last_success_t": h.get("last_success_t"),
           "metric_names_found": list(h.get("metric_names_found") or ()),
           "metric_names_missing": list(h.get("metric_names_missing") or ()),
           "kv_key_seen": h.get("kv_key_seen"),
           "metrics_degraded": h.get("metrics_degraded"),
           "scrape_enabled": h.get("scrape_enabled")}
    if not trusted:
        out["untrusted_quantities"] = _untrusted_names()
        out["why"] = ("state %r: the engine-metric quantities listed in untrusted_quantities are "
                      "NOT observations of the engine in this cell and must not be reported as "
                      "though a zero among them were a policy outcome" % (state,))
    else:
        out["why"] = ("state scraped_ok: every scrape attempt succeeded and the KV gauge was "
                      "observed, so a zero pd_kv_bound_by_engine_metric in this cell IS a policy "
                      "outcome (the engine metric never bound) and not an absent link")
    return out


def engine_metrics_trusted(cell: Dict[str, Any]) -> bool:
    """THE READER EVERY TABLE USES, so the marking is applied at the point of use (CLAUDE.md).

    A table that prints an engine-metric number for a cell where this is False is printing an
    absence as a measurement. `False` on a cell with no field at all is deliberate: a cell written
    before E1 carries no field, and the safe reading of a missing flag is not-trusted.
    """
    h = (cell or {}).get("metrics_health") or {}
    return bool(h.get("engine_metrics_trusted", False))


def mark(cell: Dict[str, Any], value: Any, label: str = "") -> str:
    """Format one engine-metric value with its trust marking attached to the NUMBER."""
    if engine_metrics_trusted(cell):
        return str(value)
    state = ((cell or {}).get("metrics_health") or {}).get("state") or "unknown"
    return "%s [UNTRUSTED: %s%s]" % (value, state, (" " + label) if label else "")


def main() -> int:
    import json
    for p in sys.argv[1:]:
        c = json.loads(Path(p).read_text())
        h = c.get("metrics_health") or {}
        print("%-70s %-24s trusted=%s n_scrapes=%s n_failures=%s"
              % (p, h.get("state"), h.get("engine_metrics_trusted"),
                 h.get("n_scrapes"), h.get("n_failures")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
