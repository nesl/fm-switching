#!/usr/bin/env python3
"""ASSEMBLES the StudyD216-KV025 check-3 report from the cells `d216_final_kv025_driver.py` wrote.

READ-ONLY over the cell files, and it RE-USES Session D's assembler rather than restating it:
`d210_kv025_report`'s `diff`, `characteristic`, `rows_of` and `cell_of` are IMPORTED, so the
decision-diff rule and the port-rule wording are the same ones the committed report was written
with. Only the PAIRS and the tag list are this study's. A second copy of a diff rule is how two
counts of the same rows stop agreeing.

WHAT THE BINDING VERDICT IS ALLOWED TO SAY is Session D's rule, unchanged: the 0.25x setting
reaches a dry decision through at most two paths, the ARM'S OWN READ of the pool
(`arms_v6cf.py:277`, `_pd_free_kv`, consumed by `PD.decide(free_kv_tokens=...)`, visible with
enforcement off) and the COORDINATOR'S EVICTION (`cstate.py:520`, which needs
`kv_capacity_enforced` and is arm-independent). If both are flat, the verdict is Rule 2
`unexercised`, never an equivalence and never a finding about the policy.

THE ONE BAR THIS STUDY CREATES RATHER THAN CHECKS. `covex-v6-fair-final` and `covex-v6-final` have
no committed digest: these cells are their first measurement. So the off-switch identity pair
(F3 against F1, F6 against F4) is the only internal consistency test available at 1x, and it is the
one that matters, because on the COMMITTED family the same pair failed by 711 rows (Session D 3.0).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d210_kv025_report as D210                                               # noqa: E402

# the committed digests a POSITIVE CONTROL must reproduce through THIS wrapper
CONTROLS = {
    "F0a_base_1x": {
        "arm": "covex-v6-base", "digest": "af8befb9420ad86a", "rows": 12085,
        "source": "frozen_test/c5attr_digest_proofs.json P1 (via d210_kv025_report.COMMITTED)",
        "register": "ADMISSIBLE BAR: rung 0, so D216 (1)'s unfixed-rung-2 rule does not apply.",
    },
    "F0_state_uo_1x": {
        "arm": "covex-v6-state-uo", "digest": "9a4be873eb3c5fba", "rows": 14218,
        "source": "frozen_test/c5attr_digest_proofs.json P1 (via d210_kv025_report.COMMITTED)",
        "register": ("REPRODUCTION DATUM, NOT A BAR. D216 (1): an unfixed rung-2 digest (the "
                     "id(obs) cache-key fix OFF) is never used as a bar. Session D withdrew the "
                     "same cell for the same reason."),
    },
}

PAIRS = [
    ("offswitch_identity_at_1x", "F3_r4_off_1x", "F1_r3_final_1x",
     "THE CELL THIS STUDY TURNS ON: both compounds off must collapse to rung 3 of the FINAL "
     "ladder byte-identically. On the committed family the same pair was 711 rows apart because "
     "`arms_v6cfr3._Rung4Mixin._cf_engine` swaps the planner's deficit weight unconditionally "
     "while committed rung 3 does not read the feed. Final rung 3 DOES read it "
     "(`arms_final_ladder._PlannerFeedMixin`), so a 0 here is the cure and a non-zero is a "
     "SECOND, DIFFERENT cause that must be traced, not explained."),
    ("offswitch_identity_at_0p25x", "F6_r4_off_kv025", "F4_r3_final_kv025",
     "the same identity at the memory setting under test"),
    ("step2b_rung4_vs_off_at_1x", "F2_r4_final_1x", "F3_r4_off_1x",
     "CLAUDE.md Step 2b at 1x: does the final rung 4 move a decision against its own off arm"),
    ("step2b_rung4_vs_off_at_0p25x", "F5_r4_final_kv025", "F6_r4_off_kv025",
     "Step 2b at 0.25x, coordinator eviction off"),
    ("binding_rung4_1x_vs_0p25x", "F2_r4_final_1x", "F5_r4_final_kv025",
     "THE BINDING TEST for the final rung 4: the same arm at the two memory settings"),
    ("binding_rung3_1x_vs_0p25x", "F1_r3_final_1x", "F4_r3_final_kv025",
     "THE BINDING TEST for the final rung 3. Flat means the pool never reached a rung-3 "
     "decision: Rule 2 unexercised, which under the 2026-11-23 ruling is capacity-blindness BY "
     "DESIGN and not a defect, PROVIDED the reactive path is alive (this study's check 1)"),
    ("enforcement_channel_rung4", "F5_r4_final_kv025", "F7_r4_final_kv025_enf",
     "the COORDINATOR-EVICTION channel on rung 4, which also reads the pool itself"),
    ("enforcement_channel_rung3", "F4_r3_final_kv025", "F8_r3_final_kv025_enf",
     "the coordinator-eviction channel alone, on a rung that reads no pool"),
    ("leg_pd_only_vs_off_at_0p25x", "F9_r4_pdonly_kv025", "F6_r4_off_kv025",
     "protect-and-defer ALONE at 0.25x (addendum 12 item 5: attribute each leg)"),
    ("leg_rq_only_vs_off_at_0p25x", "F10_r4_rqonly_kv025", "F6_r4_off_kv025",
     "question-deferral ALONE at 0.25x"),
    ("legs_additive_check", "F5_r4_final_kv025", "F9_r4_pdonly_kv025",
     "the compound against protect-and-defer alone. Session D measured the two legs NOT additive "
     "at 0.25x (protect-and-defer strictly pre-empted question deferral); this is that test "
     "re-pointed, and its answer does not transfer"),
    ("step4_negative_control_harm0", "F11_harm0_kv025", "F6_r4_off_kv025",
     "CLAUDE.md Step 4: harm zeroed at source on both legs must COLLAPSE to the off arm"),
    ("step4_negative_control_margin_huge", "F12_marginhuge_kv025", "F6_r4_off_kv025",
     "CLAUDE.md Step 4, the other direction: the BAR alone scaled must collapse to the off arm"),
]

CHAR_TAGS = ("F2_r4_final_1x", "F5_r4_final_kv025", "F7_r4_final_kv025_enf",
             "F9_r4_pdonly_kv025", "F10_r4_rqonly_kv025", "F11_harm0_kv025",
             "F12_marginhuge_kv025")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.cells)
    man = D210.jload(d / "manifest.json") or {}

    res: Dict[str, Any] = {
        "_what": ("StudyD216-KV025 check 3: the 0.25x dry cells re-run on the FINAL ladder "
                  "(covex-v6-final), not on covex-v6-cf-c5attr, and run ALONE under D216 (1)"),
        "_register": {
            "every_number_here": ("DRY and LOGICAL. --kv-scale scales test_live2_coord.GPU_KV, "
                                  "the coordinator's own logical pool. No engine, no "
                                  "--num-gpu-blocks-override, no --max-model-len."),
            "the_real_engine_condition_is_different": (
                "the posted live 0.25x cells run --num-gpu-blocks-override 985 "
                "--max-model-len 15744, engine pool of record 15,760 = 985 x 16, logical 15,736. "
                "None of that applies to a cell here."),
            "decision_latency": ("flash CPU wall clock inside the arm's decide "
                                 "(coordinator.py:2127), at the loadavg the manifest records "
                                 "per cell. NOT an H100 number and not an engine number."),
            "what_transfers_from_session_D": ("the cell STRUCTURE, the channel split and the "
                                              "classification scheme. NOT the counts: "
                                              "covex-v6-final differs from covex-v6-cf-c5attr by "
                                              "the id(obs) fix, the rung-3 planner limb on the "
                                              "deficit feed and the alert release re-check."),
        },
        "alone_rule": {
            "_rule": "D216 (1): every cell polls until no other live2 process runs, then "
                     "re-checks that nothing started during it.",
            "per_cell": [{"tag": r.get("tag"), "alone": r.get("alone"),
                          "loadavg_at_start": r.get("loadavg_at_start"),
                          "loadavg_at_end": r.get("loadavg_at_end"),
                          "waited_for_alone_s": r.get("waited_for_alone_s"),
                          "started_during_the_cell": r.get("started_during_the_cell"),
                          "SKIPPED": r.get("SKIPPED")}
                         for r in (man.get("cells") or [])],
        },
        "cells": man,
        "positive_controls": {},
        "pairs": {},
        "characteristic_decisions": {},
        "latency": {},
    }

    for tag, exp in CONTROLS.items():
        c = D210.cell_of(d, tag)
        res["positive_controls"][tag] = {
            "arm": exp["arm"], "expected": exp,
            "measured_digest": (c or {}).get("digest"),
            "measured_rows": (c or {}).get("rows"),
            "VERDICT": ("CELL MISSING" if c is None else
                        ("PASS" if (c.get("digest") == exp["digest"]
                                    and c.get("rows") == exp["rows"]) else
                         "FAIL: a known-good COMMITTED arm did not reproduce through this "
                         "wrapper. CLAUDE.md check 7 - the CHECK (the registration wrapper) is "
                         "broken, not the arm")),
        }

    for name, A, B, why in PAIRS:
        res["pairs"][name] = dict(D210.diff(d, A, B), _why=why)
    for tag in CHAR_TAGS:
        res["characteristic_decisions"][tag] = D210.characteristic(d, tag)
    for row in (man.get("cells") or []):
        lat = D210.jload(d / ("%s.lat.json" % row.get("tag")))
        if lat is not None:
            res["latency"][row["tag"]] = lat

    Path(a.out).write_text(json.dumps(res, indent=1, default=float))
    print("wrote %s" % a.out)
    for k, v in res["positive_controls"].items():
        print("control %-18s %s" % (k, v["VERDICT"]))
    for k, v in res["pairs"].items():
        print("%-40s setwise=%s positional=%s digests_equal=%s"
              % (k, v.get("differing_setwise"), v.get("differing_positional"),
                 v.get("digests_equal")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
