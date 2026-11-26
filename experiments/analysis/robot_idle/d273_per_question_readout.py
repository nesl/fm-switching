#!/usr/bin/env python3
"""D273: THE PRIMARY READOUT. PER AFFECTED QUESTION, MATCHED ACROSS THE NESTED CELLS THAT SHARE IT.
CPU, read-only, no GPU.

The user ruling moves the NESTOUT verdict off the fleet totals: the doses are 1, 2, 1 and 3 distinct
affected questions, below the robot-cbd same-code observation of 2, so a fleet total cannot carry
the result. The verdict is this readout; fleet robot cbd and cloud-correct are reported BESIDE it
and are not the verdict.

WHY THIS IS STRONGER THAN SEVEN INDEPENDENT OBSERVATIONS, and it is the whole point of the nesting.
Because the victim sets NEST, an affected question appears in a cell where its device IS a victim
AND in a cell where it is NOT, at the SAME window, SAME arm, SAME seed and SAME trace structure.
Each question is therefore ITS OWN CONTROL, and the comparison is within-question, within-arm,
across-k and matched. Seven matched questions can carry a large effect where seven unmatched ones
could not, because the between-question variance that would otherwise swamp them is differenced
away.

THE MATCHING KEY, stated: **(question_id, device_id) against victim membership against k.** Victim
membership is not re-derived: it is read from the cell's own recorded `outage.victim_permutation`,
whose index plus one is the k at which that device first becomes a victim, and because victims are
the permutation PREFIX that single number fixes every cell's role for that question:
  k <  first_victim_k  ->  CONTROL cell: the device is not a victim, its evidence is COMPLETE
  k >= first_victim_k  ->  TREATED cell: the device is a victim, the window's frames are MISSING

THE FOUR FIELDS, exactly as ruled, each from the cell's own committed per-question row
(`cell.json` at `/score/score/robot_rows`, written by `scorer/score.py:890-902`):
  answered   `source_by_deadline != "none"`
  correct    `standing_correct_by_deadline`
  on time    `source_by_deadline != "none"` is delivery WITHIN the deadline by construction
             (D155 (3)), and `device_on_time` is reported beside it for the device half
  served by  `source_by_deadline`: "cloud" means the answer came from the cloud, whose history is
             SHORT in a treated cell, and "device" means it came from the device, whose history is
             COMPLETE under this ruling. THIS IS THE FIELD THAT CARRIES THE MECHANISM.

AND THE MATCH IS PROVED COMPLETE BEFORE ANY OUTCOME IS READ. Every matched question must appear in
every cell of its ladder, the cells must agree on the window and the permutation, and the victim
membership each cell records must agree with the census. If any of that fails the readout REFUSES
rather than scoring a partial match.

Usage:
  python d273_per_question_readout.py --cell DIR [--cell DIR ...] --census FILE --out FILE
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional


def _find(o: Any, name: str) -> Any:
    if isinstance(o, dict):
        if name in o:
            return o[name]
        for v in o.values():
            r = _find(v, name)
            if r is not None:
                return r
    elif isinstance(o, (list, tuple)):
        for v in o:
            r = _find(v, name)
            if r is not None:
                return r
    return None


def read_cell(d: Path) -> Dict[str, Any]:
    cj = json.loads((d / "cell.json").read_text())
    hdr = {}
    if (d / "header.json").exists():
        hdr = json.loads((d / "header.json").read_text())
    outage = hdr.get("outage") or {}
    rows = _find(cj.get("score") or {}, "robot_rows") or []
    return {
        "name": d.name, "arm": cj.get("arm"), "seed": cj.get("seed"),
        "ratio": cj.get("ratio") or hdr.get("ratio"),
        "run_valid": cj.get("run_valid"),
        "k": (outage.get("args") or {}).get("outage_robots_k"),
        "D": (outage.get("args") or {}).get("outage_duration_s"),
        "semantics": outage.get("semantics"), "placement": outage.get("placement"),
        "window": [outage.get("t_start"), outage.get("t_end")],
        "victims": list(outage.get("robots") or ()),
        "permutation": list(outage.get("victim_permutation") or ()),
        "lost_frames": ((outage.get("lost") or {}).get("lost_history_frames")),
        "rows": {(str(r.get("question_id") or "").casefold(), str(r.get("device_id"))): r
                 for r in rows},
        "n_rows": len(rows),
        "fleet_cbd": _find(cj.get("score") or {}, "correct_answers_delivered_by_deadline"),
        "fleet_cbd_n": _find(cj.get("score") or {}, "n_by_deadline"),
        "fleet_cloud_acc": _find(cj.get("score") or {}, "cloud_accuracy_on_served"),
        "fleet_cloud_n": _find(cj.get("score") or {}, "cloud_answers_available"),
    }


def four_fields(r: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if r is None:
        return {"present": False}
    sbd = r.get("source_by_deadline")
    return {
        "present": True,
        "answered": (sbd is not None and sbd != "none"),
        "correct": r.get("standing_correct_by_deadline"),
        "on_time": (sbd is not None and sbd != "none"),
        "served_by": sbd,
        "SERVED_BY_CLOUD_WINDOW_EVIDENCE_MISSING": (sbd == "cloud"),
        "SERVED_BY_DEVICE_EVIDENCE_COMPLETE": (sbd == "device"),
        "_beside_it": {"source_any_time": r.get("source"),
                       "standing_correct_any_time": r.get("standing_correct"),
                       "cloud_correct": r.get("cloud_correct"),
                       "device_correct": r.get("device_correct"),
                       "device_on_time": r.get("device_on_time"),
                       "cache_path": r.get("cache_path")},
    }


def sign_p(b: int, sided: int = 1) -> float:
    return min(1.0, (0.5 ** b) * (2 if sided == 2 else 1)) if b > 0 else 1.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cell", action="append", required=True)
    ap.add_argument("--census", required=True,
                    help="d273_matched_power.json, which carries the matched questions and their "
                         "first_victim_k")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=None)
    a = ap.parse_args(argv)

    cells = [read_cell(Path(c)) for c in a.cell]
    cen = json.loads(Path(a.census).read_text())

    # ---- PRECONDITIONS, CHECKED FIRST. A cell whose header carries no `outage` block cannot be
    # matched at all: k, the window, the permutation and the semantics are all unknown. The
    # committed D244 cells are exactly this case, because `header.json` gained the outage block
    # only with D266 item 2, and the first version of this script CRASHED on them instead of
    # refusing. A crash is not a refusal, so the condition is named and reported.
    missing = [{"cell": c["name"],
                "missing": [f for f in ("k", "semantics", "placement") if c.get(f) is None]
                           + ([] if c["permutation"] else ["victim_permutation"])
                           + ([] if all(x is not None for x in c["window"]) else ["window"])}
               for c in cells
               if c.get("k") is None or not c["permutation"] or c.get("semantics") is None
               or any(x is None for x in c["window"])]
    if missing:
        out = {
            "_what": "D273 PRIMARY READOUT",
            "MATCH_COMPLETENESS_PROOF": {
                "MATCH_COMPLETE": False,
                "VERDICT": ("REFUSED: a cell carries no usable `outage` block in its header, so "
                            "its k, window, permutation or semantics is unknown and it cannot be "
                            "matched. Cells written before D266 item 2 added `outage` to "
                            "header.json are this case and are NOT part of this design: the "
                            "comparator is P3 and the in-regime cells, never the old grid."),
                "cells_without_a_usable_outage_block": missing},
            "per_question": "NOT READ",
        }
        Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
        print(out["MATCH_COMPLETENESS_PROOF"]["VERDICT"])
        for m in missing:
            print("   %s missing %s" % (m["cell"], m["missing"]))
        return 1

    # ---- THE MATCH-COMPLETENESS PROOF, RUN BEFORE ANY OUTCOME IS READ
    by_seed_arm: Dict[tuple, List[Dict[str, Any]]] = {}
    for c in cells:
        by_seed_arm.setdefault((c["seed"], c["arm"]), []).append(c)
    proof: Dict[str, Any] = {"_what": "the match is proved complete before any outcome is read",
                             "groups": {}}
    ok = True
    for (sd, arm), cs in sorted(by_seed_arm.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        cs = sorted(cs, key=lambda c: c["k"] or 0)
        perms = {json.dumps(c["permutation"]) for c in cs}
        wins = {json.dumps(c["window"]) for c in cs}
        sems = {c["semantics"] for c in cs}
        nrows = {c["n_rows"] for c in cs}
        census = (cen.get("design_as_ruled", {}).get("per_seed", {}).get("s%s" % sd) or {})
        matched = census.get("matched_questions") or []
        present = []
        for q in matched:
            key = (str(q["question_id"]).casefold(), str(q["device_id"]))
            where = {c["k"]: (key in c["rows"]) for c in cs}
            # the victim membership each cell records must agree with the census
            agree = all(((q["device_id"] in c["victims"])
                         == (c["k"] >= q["becomes_victim_at_k"])) for c in cs)
            present.append({"question_id": q["question_id"], "device_id": q["device_id"],
                            "becomes_victim_at_k": q["becomes_victim_at_k"],
                            "in_every_cell": all(where.values()), "per_k": where,
                            "victim_membership_agrees_with_census": agree})
        g = {
            "cells": [c["name"] for c in cs], "k_present": [c["k"] for c in cs],
            "one_permutation": len(perms) == 1, "one_window": len(wins) == 1,
            "one_semantics": sems.pop() if len(sems) == 1 else list(sems),
            "same_row_count": len(nrows) == 1, "row_counts": sorted(nrows),
            "all_run_valid": all(bool(c["run_valid"]) for c in cs),
            "n_matched_expected": len(matched),
            "questions": present,
            "ALL_PRESENT_IN_EVERY_CELL": all(p["in_every_cell"] for p in present),
            "ALL_MEMBERSHIP_AGREES": all(p["victim_membership_agrees_with_census"]
                                         for p in present),
        }
        g["PASS"] = bool(g["one_permutation"] and g["one_window"] and g["same_row_count"]
                         and g["all_run_valid"] and g["ALL_PRESENT_IN_EVERY_CELL"]
                         and g["ALL_MEMBERSHIP_AGREES"] and matched)
        ok = ok and g["PASS"]
        proof["groups"]["s%s|%s" % (sd, arm)] = g
    proof["MATCH_COMPLETE"] = bool(ok)
    proof["VERDICT"] = ("PASS: every matched question is present in every cell of its ladder, the "
                        "cells agree on the window and the permutation, and the victim membership "
                        "each cell records agrees with the census."
                        if ok else
                        "REFUSED: the match is not complete. No outcome is read below.")

    out: Dict[str, Any] = {
        "_what": ("D273 PRIMARY READOUT: per affected question, matched across the nested cells "
                  "that share it. The fleet figures are context, not the verdict."),
        "_matching_key": "(question_id, device_id) against victim membership against k",
        "_four_fields": ["answered", "correct", "on_time", "served_by (cloud or device)"],
        "MATCH_COMPLETENESS_PROOF": proof,
        "fleet_context_NOT_THE_VERDICT": {
            c["name"]: {"robot_cbd": c["fleet_cbd"], "robot_cbd_n": c["fleet_cbd_n"],
                        "cloud_accuracy_on_served": c["fleet_cloud_acc"],
                        "cloud_answers_available": c["fleet_cloud_n"],
                        "_why_not_the_verdict": ("the dose is 1 to 3 distinct questions per pair, "
                                                 "below the robot-cbd same-code observation of 2, "
                                                 "so a fleet total cannot carry this result")}
            for c in cells},
    }
    if not ok:
        out["per_question"] = "NOT READ: the match-completeness proof refused"
        out["VERDICT"] = proof["VERDICT"]
        Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
        print(proof["VERDICT"])
        return 1

    # ---- THE READOUT
    per_q: List[Dict[str, Any]] = []
    for (sd, arm), cs in sorted(by_seed_arm.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        cs = sorted(cs, key=lambda c: c["k"] or 0)
        census = (cen.get("design_as_ruled", {}).get("per_seed", {}).get("s%s" % sd) or {})
        for q in (census.get("matched_questions") or []):
            key = (str(q["question_id"]).casefold(), str(q["device_id"]))
            obs = {}
            for c in cs:
                role = "treated" if (c["k"] >= q["becomes_victim_at_k"]) else "control"
                obs["k%s_%s" % (c["k"], role)] = four_fields(c["rows"].get(key))
            ctrl = [v for k2, v in obs.items() if k2.endswith("_control") and v.get("present")]
            trt = [v for k2, v in obs.items() if k2.endswith("_treated") and v.get("present")]
            def agg(vs, field):
                vals = [v[field] for v in vs if v.get(field) is not None]
                return (all(vals) if vals else None)
            row = {"seed": sd, "arm": arm, "question_id": q["question_id"],
                   "device_id": q["device_id"],
                   "becomes_victim_at_k": q["becomes_victim_at_k"],
                   "evidence_overlap_s": q.get("overlap_s"),
                   "ask_instances": q.get("instances"),
                   "observations": obs}
            for f in ("answered", "correct", "on_time"):
                cv, tv = agg(ctrl, f), agg(trt, f)
                row["control_" + f] = cv
                row["treated_" + f] = tv
                row["discordant_" + f] = (None if cv is None or tv is None else (cv != tv))
                row["direction_" + f] = (None if cv is None or tv is None or cv == tv
                                         else ("worse_when_victim" if cv and not tv
                                               else "better_when_victim"))
            cs_by = [v["served_by"] for v in ctrl if v.get("served_by")]
            ts_by = [v["served_by"] for v in trt if v.get("served_by")]
            row["control_served_by"] = cs_by
            row["treated_served_by"] = ts_by
            row["served_by_changed"] = (bool(set(cs_by) != set(ts_by)) if cs_by and ts_by
                                        else None)
            row["TREATED_SERVED_BY_CLOUD_WITH_EVIDENCE_MISSING"] = ("cloud" in ts_by)
            per_q.append(row)
    out["per_question"] = per_q

    summary = {}
    for f in ("answered", "correct", "on_time"):
        disc = [r for r in per_q if r["discordant_" + f]]
        worse = [r for r in disc if r["direction_" + f] == "worse_when_victim"]
        better = [r for r in disc if r["direction_" + f] == "better_when_victim"]
        b = len(disc)
        summary[f] = {
            "n_matched_questions_readable": sum(1 for r in per_q
                                                if r["discordant_" + f] is not None),
            "n_discordant": b, "n_worse_when_victim": len(worse),
            "n_better_when_victim": len(better),
            "exact_sign_test_p_one_sided": round(sign_p(max(len(worse), len(better))), 6),
            "REACHES_0.05_ONE_SIDED": bool(max(len(worse), len(better)) >= 5
                                           and min(len(worse), len(better)) == 0),
            "_rule": ("5 of the matched questions discordant ALL ONE WAY is the smallest result "
                      "that can reach one-sided p <= 0.05 at n = 7, and 6 for two-sided. A "
                      "discordant count below that is a CENSUS and must be reported as one."),
        }
    served = [r for r in per_q if r["served_by_changed"] is not None]
    summary["served_by"] = {
        "n_readable": len(served),
        "n_changed": sum(1 for r in served if r["served_by_changed"]),
        "n_treated_served_by_cloud": sum(1 for r in per_q
                                         if r["TREATED_SERVED_BY_CLOUD_WITH_EVIDENCE_MISSING"]),
        "_why_this_one_carries_the_mechanism": (
            "under this ruling the DEVICE history is complete and the cloud's is short, so a "
            "question served by the device is answered from full evidence and one served by the "
            "cloud is not. Routing to the device is fully expressible (RECALL_ACTIONS includes "
            "DEVICE, honoured at coordinator.py:998-1009), so this split is the reading most "
            "likely to show anything."),
        "_expressibility": ("EXPRESSIBLE: it needs only an arm reacting to a smaller cloud "
                            "history, which it sees through readiness_tokens. It does NOT need the "
                            "arm to recognise the outage, which is unexpressible (prereg "
                            "invalidation condition 13)."),
    }
    out["SUMMARY"] = summary
    out["VERDICT"] = ("READ: the match is complete and the per-question outcomes are below. Any "
                      "discordant count under 5 of 7 all one way is a CENSUS, not a significant "
                      "difference, and must be reported as one.")
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(proof["VERDICT"])
    for f in ("answered", "correct", "on_time", "served_by"):
        print(" %-10s %s" % (f, json.dumps({k2: v for k2, v in summary[f].items()
                                            if not k2.startswith("_")})))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
