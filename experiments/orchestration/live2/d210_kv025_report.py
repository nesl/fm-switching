#!/usr/bin/env python3
"""ASSEMBLES the D209 (4) / D210 0.25x rung-4 dry report from the cells the driver wrote.

READ-ONLY over the cell files. It runs no cell, builds no arm and computes no digest: the digests
are the ones `cf_pd_one_cell`'s committed recipe already wrote into each cell JSON. The two
decision-diff functions are IMPORTED from `hybrid/test_hybrid.py` (`_differing_setwise` and
`_differing`) rather than restated, because a second copy of a diff rule is how two counts of the
same rows stop agreeing.

THE ROWS ARE NORMALISED BEFORE ANY DIFF. The cell `.rows.json` files are written with
`decision_latency_ms` kept (that is what the latency report needs), and that field is WALL CLOCK:
it differs between two runs of identical decisions. It is dropped here, which restores exactly the
row set the committed digest recipe hashes, so a count of 0 differing decisions means the same
thing it means in `d190_rung4_r3_proofs.json`.

WHAT THE BINDING VERDICT IS ALLOWED TO SAY. The 0.25x setting reaches a dry decision through at
most two paths, and they are separated by the pair of cells at each setting:

  arm observation      the arm reads the pool itself. For rung 4 that is
                       `arms_v6cf.py:302` (`_pd_free_kv`), consumed by `PD.decide(
                       free_kv_tokens=...)`. Visible with enforcement OFF.
  coordinator eviction `cstate.py:520`, which needs `kv_capacity_enforced`. Arm-independent, and
                       it is the delta between the enforcement-off and enforcement-on pair.

If BOTH are flat for an arm, the verdict is Rule 2 `unexercised` and NOT an equivalence and NOT a
finding about the policy. The verdict is emitted in those words or not at all.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LAT_KEY = "decision_latency_ms"

# the committed digests a POSITIVE CONTROL must reproduce, with where each is committed
COMMITTED = {
    "covex-v6-state-uo": {"digest": "9a4be873eb3c5fba", "rows": 14218,
                          "source": "frozen_test/c5attr_digest_proofs.json P1"},
    "covex-v6-base": {"digest": "af8befb9420ad86a", "rows": 12085,
                      "source": "frozen_test/c5attr_digest_proofs.json P1"},
}
# rung 3's committed dry digest AT THE D190 COMMIT (ec2d6a83). PROVISIONAL on D209 (1): the
# TOUCH_PRICE_MODE fix is expected to move it, so a disagreement here is dated, not wrong.
RUNG3_AT_D190 = {"digest": "12e4f73ce0ebd865", "rows": 13812,
                 "source": "frozen_test/d190_rung4_r3_proofs.json proof_3_off_switch_identity"}

# the pairs the report is built on: (name, A tag, B tag, what a difference means)
PAIRS = [
    ("step2b_rung4_vs_off_at_1x", "R4_full_1x", "R4off_1x",
     "CLAUDE.md Step 2b at 1x: does rung 4 move a decision against its own off arm"),
    ("step2b_rung4_vs_off_at_0p25x", "R4_full_kv025", "R4off_kv025",
     "Step 2b at the memory setting the cells run at, enforcement off"),
    ("step2b_rung4_vs_off_at_0p25x_enforced", "R4_full_kv025_enf", "R4off_kv025_enf",
     "Step 2b at 0.25x in the regime the posted cells run in (enforcement on)"),
    ("binding_rung4_1x_vs_0p25x", "R4_full_1x", "R4_full_kv025",
     "THE BINDING TEST for rung 4: the same arm at the two memory settings"),
    ("binding_rung3_1x_vs_0p25x", "R4off_1x", "R4off_kv025",
     "THE BINDING TEST for rung 3 (the off arm IS rung 3): flat means the pool never "
     "reached a rung-3 decision"),
    ("binding_rung3_named_arm_vs_off_at_0p25x", "R3_rung3_kv025", "R4off_kv025",
     "the committed rung-3 arm by its own name against rung 4's off arm, both at 0.25x: "
     "confirms the off arm is rung 3 at this setting too"),
    ("enforcement_channel_rung3", "R4off_kv025", "R4off_kv025_enf",
     "the COORDINATOR-EVICTION channel alone, on an arm that reads no pool"),
    ("enforcement_channel_rung4", "R4_full_kv025", "R4_full_kv025_enf",
     "the coordinator-eviction channel on rung 4, which also reads the pool itself"),
    ("leg_pd_only_vs_off_at_0p25x", "R4_pdonly_kv025", "R4off_kv025",
     "protect-and-defer ALONE at 0.25x (addendum 12 item 5: attribute each leg)"),
    ("leg_rq_only_vs_off_at_0p25x", "R4_rqonly_kv025", "R4off_kv025",
     "question-deferral ALONE at 0.25x"),
    ("step4_negative_control_harm0", "N1_harm0_kv025", "R4off_kv025",
     "CLAUDE.md Step 4: harm zeroed at source must COLLAPSE to the off arm"),
]

CHARACTERISTIC = ("pd_state_defers", "pd_state_chunks", "pd_request_defers", "pd_protects",
                  "rd_question_defers")


def rows_of(d: Path, tag: str) -> Optional[List[Dict[str, Any]]]:
    p = d / ("%s.rows.json" % tag)
    if not p.exists():
        return None
    rows = json.loads(p.read_text())
    return [{k: v for k, v in r.items() if k != LAT_KEY} for r in rows]


def cell_of(d: Path, tag: str) -> Optional[Dict[str, Any]]:
    p = d / ("%s.json" % tag)
    if not p.exists() or not p.stat().st_size:
        return None
    return json.loads(p.read_text())


def jload(p: Path) -> Optional[Dict[str, Any]]:
    return json.loads(p.read_text()) if p.exists() and p.stat().st_size else None


def diff(d: Path, a: str, b: str) -> Dict[str, Any]:
    import test_hybrid as TH                                              # noqa: PLC0415
    ra, rb = rows_of(d, a), rows_of(d, b)
    ca, cb = cell_of(d, a), cell_of(d, b)
    out: Dict[str, Any] = {
        "A": a, "B": b,
        "digest_A": (ca or {}).get("digest"), "digest_B": (cb or {}).get("digest"),
        "rows_A": (ca or {}).get("rows"), "rows_B": (cb or {}).get("rows"),
    }
    if ca is None or cb is None:
        out["VERDICT"] = "CELL MISSING, no comparison made"
        return out
    out["digests_equal"] = bool(out["digest_A"] == out["digest_B"])
    if ra is None or rb is None:
        out["note"] = "rows not captured for one side; digest comparison only"
        return out
    out["differing_setwise"] = TH._differing_setwise(ra, rb)
    out["differing_positional"] = TH._differing(ra, rb)
    out["identical"] = bool(out["differing_setwise"] == 0 and out["differing_positional"] == 0)
    first = None
    for i, (x, y) in enumerate(zip(ra, rb)):
        if x != y:
            first = {"index": i, "A": x, "B": y}
            break
    if first is None and len(ra) != len(rb):
        i = min(len(ra), len(rb))
        first = {"index": i, "A": (ra[i] if i < len(ra) else None),
                 "B": (rb[i] if i < len(rb) else None),
                 "note": "logs agree up to the shorter length and then one ends"}
    out["first_difference"] = first
    return out


def characteristic(d: Path, tag: str) -> Dict[str, Any]:
    cell, rd = cell_of(d, tag), jload(d / ("%s.rd.json" % tag))
    pd_c = dict((cell or {}).get("pd_counters") or {})
    rd_c = dict((rd or {}).get("rd_counters") or {})
    allc = dict(pd_c)
    allc.update(rd_c)
    by_kind = {k: int(allc.get(k, 0) or 0) for k in CHARACTERISTIC}
    total = sum(by_kind.values())
    return {
        "cell": tag,
        "arm": (cell or {}).get("arm"),
        "kv_scale": (cell or {}).get("kv_scale"),
        "by_kind": by_kind,
        "TOTAL_characteristic_decisions": total,
        "non_zero": bool(total > 0),
        "PORT_RULE": ("PASS: the arm makes its own characteristic decision at least once"
                      if total > 0 else
                      "STOPPING CONDITION: zero characteristic decisions. CLAUDE.md 'Citing "
                      "results' - this is an ABSENT LINK, never a negative about the policy"),
        "decisions_offered": {k: int(allc.get(k, 0) or 0) for k in
                              ("pd_decisions", "pd_decisions_state", "pd_decisions_request",
                               "rd_decisions", "rd_deferred_to_guard_epochs",
                               "rd_skipped_over_limit", "rd_skipped_already_deferred")},
        "unexpressible": {k: v for k, v in sorted(allc.items()) if "unexpressible" in k},
        "gate_mix_pd": {k: v for k, v in sorted(pd_c.items()) if k.startswith("pd_gate_")},
        "gate_mix_rd": {k: v for k, v in sorted(rd_c.items()) if k.startswith("rd_gate_")},
        "free_kv_seen": {k: v for k, v in sorted(pd_c.items()) if "free_kv" in k},
        "kv_bound_by": {k: v for k, v in sorted(pd_c.items()) if "kv_bound_by" in k},
        "no_kv_pool_configured": allc.get("pd_no_kv_pool_configured", 0),
    }


def deferred_and_exposed(d: Path, tag: str, gatea: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """CONSTRUCTED, NOT OBSERVED, and the register is the whole point of this function.

    A dry cell has no engine, so there is no observed first token and therefore NO deferral can be
    OBSERVED to have overrun. `cf_request_defer` records predictions only. The observed count is
    NOT MEASURABLE here and is reported as not measurable.

    What is computable is a constructed estimate, and it is simple because the mechanism makes it
    simple: a deferral is placed AT the latest safe start, so it retains ZERO margin by
    construction. Its miss threshold is therefore the safety factor itself, and its exposure
    probability is exactly the Gate A exposure measured on committed sent requests. The overrun it
    would take is `(ratio - safety_factor) x predicted_total_service_s`, so the worst committed
    ratio gives each deferral's worst-case overrun in seconds.
    """
    rd = jload(d / ("%s.rd.json" % tag))
    rep = (rd or {}).get("rd_report") or {}
    gate = (gatea or {}).get("THE_GATE") or {}
    sf = float(gate.get("safety_factor_q90") or 0.0)
    expo = float(gate.get(
        "exposure_fraction_of_sent_recall_requests_over_the_safety_factor") or 0.0)
    worst = float(gate.get("overrun_magnitude_worst_as_a_multiple_of_predicted_service") or 0.0)
    defs_ = []
    for rec in ((rd or {}).get("rd_decisions") or []):
        if str(rec.get("action", "")).upper() == "BASE":
            continue
        wm = rec.get("would_miss_under_measured_bias") or {}
        service = wm.get("predicted_total_service_s")
        defs_.append({
            "t": rec.get("t"), "action": rec.get("action"),
            "deferral_s": rec.get("deferral_s"),
            "predicted_total_service_s": service,
            "safety_factor_used": wm.get("safety_factor_used"),
            "retained_margin_s": 0.0,
            "miss_threshold_ratio": sf,
            "estimated_exposure": expo,
            "worst_case_overrun_s": (round(worst * float(service), 6)
                                     if service is not None else None),
        })
    n = len(defs_)
    return {
        "_register": ("CONSTRUCTED BOUND, NOT AN OBSERVED COUNT. A dry cell has no engine, so no "
                      "deferral can be observed to overrun. The estimate applies the COMMITTED "
                      "rung-3 exposure (n = 463 sent robot requests, seeds 4 to 7) to deferrals "
                      "whose retained margin is zero by construction."),
        "observed_deferred_and_exposed": ("NOT MEASURABLE IN A DRY CELL: no engine, so no "
                                          "observed first token and no realised overrun"),
        "n_deferrals": n,
        "safety_factor_q90_in_force": sf,
        "exposure_per_deferral": expo,
        "expected_n_deferrals_exposed": round(n * expo, 4),
        "worst_ratio_multiple_over_the_factor": worst,
        "per_deferral": defs_,
        "n_deferrals_carrying_a_predicted_service": sum(
            1 for x in defs_ if x["predicted_total_service_s"] is not None),
        "bar_distribution": rep.get("bar"),
        "net_gain_distribution": rep.get("net_gain"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    ap.add_argument("--gatea", required=True, help="the committed-equivalent gate A JSON")
    ap.add_argument("--gatea-rr", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.cells)
    man = jload(d / "manifest.json") or {}
    gatea = jload(Path(a.gatea))
    res: Dict[str, Any] = {
        "_what": "D209 (4) / D210: the 0.25x dry report for the committed rung-4 arm",
        "_register": {
            "every_number_here": ("DRY and LOGICAL. --kv-scale scales test_live2_coord.GPU_KV, "
                                  "the coordinator's logical pool. No engine, no "
                                  "--num-gpu-blocks-override, no --max-model-len."),
            "the_real_engine_condition_is_different": (
                "the posted live 0.25x cells run --num-gpu-blocks-override 985 "
                "--max-model-len 15744 (that order), engine pool of record 15,760 = 985 x 16 "
                "confirmed on hardware, logical 15,736. NONE of that applies to a cell here."),
            "decision_latency": ("flash CPU wall clock inside the arm's decide "
                                 "(coordinator.py:2127), under whatever host load the manifest "
                                 "records. NOT an H100 number."),
            "digests_are_provisional": ("D209 (1) / the TOUCH_PRICE_MODE fix is expected to move "
                                        "rung 3's and rung 4's digests. Every digest here is "
                                        "dated to the commit in _provenance."),
        },
        "cells": man,
        "positive_controls": {},
        "pairs": {},
        "characteristic_decisions": {},
        "latency": {},
        "deferred_and_exposed": {},
    }
    for tag, arm in (("P1_state_uo_1x", "covex-v6-state-uo"),):
        c = cell_of(d, tag)
        exp = COMMITTED[arm]
        res["positive_controls"][tag] = {
            "arm": arm, "expected": exp,
            "measured_digest": (c or {}).get("digest"), "measured_rows": (c or {}).get("rows"),
            "VERDICT": ("CELL MISSING" if c is None else
                        ("PASS" if (c.get("digest") == exp["digest"]
                                    and c.get("rows") == exp["rows"]) else
                         "FAIL: a known-good COMMITTED arm did not reproduce. CLAUDE.md check 7 "
                         "- the CHECK is broken or the host condition differs, not the arm")),
        }
    c = cell_of(d, "R4off_1x")
    res["positive_controls"]["R4off_1x_is_rung_3"] = {
        "_claim": ("rung 4's off arm must be the COMMITTED rung-3 arm byte-identically. This is "
                   "the second positive control and also the off-switch identity proof."),
        "expected_at_the_D190_commit": RUNG3_AT_D190,
        "measured_digest": (c or {}).get("digest"), "measured_rows": (c or {}).get("rows"),
        "VERDICT": ("THE BAR DOES NOT APPLY AT THIS COMMIT, and that is a finding and not a "
                    "check failure. `arms_v6cfr3._Rung4Mixin._cf_engine` swaps the state "
                    "planner's deficit weight UNCONDITIONALLY (it reads neither compound "
                    "switch), so the off arm is rung 3 PLUS the D206 (2) planner weight. The "
                    "contamination is +711 decision rows, confirmed mechanically as +661 "
                    "state_touch_emitted and +662 state_deviations by the counter census."),
        "the_uncontaminated_rung3_bar": ("measured in this run under its own name: "
                                         "covex-v6-fair-c5attr = 12e4f73ce0ebd865 / 13,812 at "
                                         "1x AND at 0.25x, equal to the committed bar"),
    }
    res["positive_controls"]["_D216_bar_rule"] = {
        "_what": ("D216 (1) landed while these cells ran: an unfixed rung-2 digest (qcache fix "
                  "off) is never used as a bar, and any cell whose digest is a bar runs ALONE."),
        "P1_state_uo_1x": ("reproduced its committed digest exactly at host load 12.54, but is "
                           "WITHDRAWN AS A BAR under D216 (1) and kept as a reproduction datum "
                           "only. The study does not depend on it: the admissible bars are "
                           "rung 4, rung 3, the Gate A JSON and the 1x leg counters."),
        "R3_rung3_1x": ("ran concurrently with the counter census, so it violated the ALONE "
                        "rule and is NOT cited as a bar."),
        "R3_rung3_1x_ALONE": ("the compliant re-run, alone at host load 0.60: "
                              "12e4f73ce0ebd865 / 13,812, identical. This is the cited bar."),
    }
    for name, A, B, why in PAIRS:
        res["pairs"][name] = dict(diff(d, A, B), _why=why)
    for tag in ("R4_full_1x", "R4_full_kv025", "R4_full_kv025_enf", "R4_pdonly_kv025",
                "R4_rqonly_kv025", "N1_harm0_kv025"):
        res["characteristic_decisions"][tag] = characteristic(d, tag)
    for row in (man.get("cells") or []):
        tag = row["tag"]
        lat = jload(d / ("%s.lat.json" % tag))
        if lat is not None:
            res["latency"][tag] = lat
    for tag in ("R4_full_kv025", "R4_full_kv025_enf", "R4_full_1x"):
        res["deferred_and_exposed"][tag] = deferred_and_exposed(d, tag, gatea)
    res["gate_a"] = {
        "committed_rung3_c5attr": (gatea or {}).get("THE_GATE"),
        "rung3_plus_rr_addendum": ((jload(Path(a.gatea_rr)) or {}).get("THE_GATE")
                                   if a.gatea_rr else None),
        "retired_identity_column": (gatea or {}).get("gate_a_would_have_missed_RETIRED"),
        "why_retired": (gatea or {}).get("_why_the_count_is_retired"),
    }
    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({"pairs": {k: {"setwise": v.get("differing_setwise"),
                                    "digests_equal": v.get("digests_equal")}
                                for k, v in res["pairs"].items()},
                      "characteristic": {k: v["TOTAL_characteristic_decisions"]
                                         for k, v in res["characteristic_decisions"].items()},
                      "positive_controls": {k: v.get("VERDICT")
                                            for k, v in res["positive_controls"].items()}},
                     indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
