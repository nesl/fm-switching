#!/usr/bin/env python3
"""Amendment 2's fitting audit: where every tunable in the suite was fitted. CPU only.

Two questions the amendment asks, answered by scanning the arms' own source and by naming the
measurement behind every profile a policy reads:

  1. S-EMBER: any threshold, floor, profile, lookup table or prior fitted from S-EMBER data must
     be fitted on the pre-registered DEV split (`sember_split.py`) and never on the questions a
     recall metric is reported over.
  2. Nexar: the same role is played by StudyD3's DEVELOPMENT clips. Any EPISODIC tunable fitted
     on the EVALUATION clips (StudyD14 / D14b's 300 validation clips) must be listed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# (marker in the source, what it is, what it is fitted on)
MARKERS = (
    ("DS.router_dataset", "a router / threshold fitted on StudyD3 DEVELOPMENT clips",
     "Nexar DEV (StudyD3)"),
    ("DS.load", "a score quantile fitted on StudyD3 DEVELOPMENT clips", "Nexar DEV (StudyD3)"),
    ("recall_accuracy", "the committed S-EMBER recall-accuracy lookup table", "S-EMBER"),
    ("_DC.dev_median", "the device-confidence floor fitted on S-EMBER DEV questions",
     "S-EMBER DEV"),
    # D164 / ruling 2026-11-22 item 2: the SAME floor, fitted once per CONFIDENCE TYPE. Listed
    # here so the auditor that exists to enumerate fitted constants does not stop seeing this one
    # when it moves from a scalar to a per-type table.
    ("_DC.fitted_floors", "the per-confidence-type device-confidence floors, DEV-fitted "
                          "(research/prereg_cascade_calibration.md)",
     "LH-REQ DEV (robot) and the committed StudySS2 30/70 DEV part (single shot)"),
    ("P.stream_profile", "the measured resource-quality profile (quality, demand, lag)",
     "Nexar EVALUATION clips (StudyE9b / E9c on StudyD14b's 300 validation clips)"),
    ("P.d_star_s", "StudyE9d's d* delay curve",
     "Nexar EVALUATION clips (StudyE9d on StudyD14b)"),
    ("P.delay_curve", "StudyE9d's V(d) delay curve",
     "Nexar EVALUATION clips (StudyE9d on StudyD14b)"),
    ("device_answer_confidence", "the committed per-question DEVICE answer probability",
     "S-EMBER, per question (a measurement, not a fitted constant)"),
)


def audit() -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    for f in sorted(HERE.glob("*.py")):
        if f.name in ("interface.py", "devsplit.py", "profiles.py", "recall_profiles.py",
                      "costs.py", "make_report.py", "sember_split.py", "device_confidence.py",
                      "amend2_audit.py", "slice_rules.py"):
            continue
        src = f.read_text()
        declares = "reads_device_answer = True" in src
        found = []
        for m, w, o in MARKERS:
            if m not in src:
                continue
            if m == "device_answer_confidence":
                found.append(dict(marker=m, what=w, fitted_on=o,
                                  receives_the_field=declares,
                                  note=("the published mechanism observes the device's own "
                                        "answer before deciding, so the harness supplies the "
                                        "field and charges the device answer" if declares else
                                        "the published mechanism decides from the QUERY before "
                                        "either model answers, so the harness does NOT supply "
                                        "the field (the name appears only in the comment that "
                                        "records this)")))
            else:
                found.append(dict(marker=m, what=w, fitted_on=o))
        if found:
            rows.append(dict(module=f.name, uses=found))
    sember = [dict(module=r["module"], **u) for r in rows for u in r["uses"]
              if "S-EMBER" in str(u["fitted_on"])
              and u.get("receives_the_field", True) is not False]
    on_eval_clips = [dict(module=r["module"], **u) for r in rows for u in r["uses"]
                     if "EVALUATION" in str(u["fitted_on"])]
    return dict(
        label="StudyB-baselines amendment 2 fitting audit. A marker is a call site in the arm's "
              "own source, so this table is checkable by grep.",
        modules=rows,
        sember_fitted=sember,
        episodic_inputs_measured_on_evaluation_clips=on_eval_clips,
        conclusion=dict(
            sember="the only S-EMBER-FITTED constant in the suite is confidence-cascade's "
                   "recall confidence floor, and amendment 2 fits it on the DEV split. The "
                   "committed S-EMBER recall-accuracy table (`recall_profiles.py`) is read by no "
                   "arm - only by the report generator - so no arm carries a constant fitted on "
                   "the full question set. Every per-question device-answer probability a policy "
                   "reads is a MEASUREMENT of that question, not a constant fitted across "
                   "questions, and the harness supplies it only to the arms whose published "
                   "mechanism observes the device's answer.",
            nexar="every FITTED episodic tunable in the suite (every router, every score "
                  "quantile, every window selection) comes from `devsplit`, which is StudyD3's "
                  "DEVELOPMENT clips. NOT fitted but MEASURED ON THE EVALUATION CLIPS, and "
                  "listed here as the amendment requires: the resource-quality profile "
                  "(`profiles.stream_profile`: quality from StudyE9b / E9c, lag from StudyE9b's "
                  "hold shift, demand from StudyE9 / E9b) and StudyE9d's V(d) and d* curves, "
                  "all measured on StudyD14b's 300 validation clips. They are inputs to "
                  "videostorm, eco-llm, inar-vl, perllm, B3, B6, B8, B9 and B10. This is the "
                  "suite's documented ADAPTATION A2 (the paper profiles online; we substitute a "
                  "measured profile), and it is a KNOWN leak of evaluation-clip information "
                  "into a decision rule, reported and not fixed: re-measuring the profile on "
                  "StudyD3's development clips needs GPU time."))


if __name__ == "__main__":
    print(json.dumps(audit(), indent=1, default=str))
