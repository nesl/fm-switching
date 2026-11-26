#!/usr/bin/env python3
"""D273: THE PER-QUESTION MATCHED CENSUS AND THE POWER INVERSION. CPU, read-only, no GPU, no cell.

The user ruling moves the NESTOUT verdict off the fleet totals and onto a PER AFFECTED QUESTION
readout, matched across the nested cells that share the question. This computes the three things the
ruling asks for rather than estimating them.

  1. THE CENSUS. Every distinct robot question whose evidence interval overlaps the window, with the
     k at which its device FIRST becomes a victim. Because the victim sets nest, that single number
     decides every cell's role for that question: at any k below it the device is NOT a victim and
     the question's evidence is COMPLETE (a CONTROL cell); at any k at or above it the device IS a
     victim and the window's frames are MISSING (a TREATED cell). A question whose device is a
     victim at the lowest rung has NO control cell in that seed and is reported separately, because
     the matched readout cannot use it.

  2. THE MINIMUM DETECTABLE EFFECT, as a count of discordant pairs. The matched readout is a
     within-question, within-arm, across-k comparison, so the test is the exact sign test on
     discordant pairs (McNemar's exact form). With b discordant pairs all in one direction the
     one-sided p is 0.5**b, so b >= 5 is needed for p <= 0.05 one-sided and b >= 6 two-sided. That
     is stated as a count, not a p-value, because at these n the count is the honest unit.

  3. THE INVERSION, on both axes the ruling names: SEEDS and VICTIM RUNGS. The yield of matched
     questions per seed and the MARGINAL yield of each new rung are MEASURED from the traces, not
     assumed, and then priced at 1,295 s per cell.

Usage:
  python d273_matched_power.py --repo DIR --out FILE [--seed 4 ...] [--k 1 --k 3 --k 5 ...]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[2]

WORKLOAD = dict(robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                dashcam_min_frames=3, robot_upload="per-frame", robot_reask_mean_s=30.0)
SEC_PER_CELL = 1295.0          # the measured median start-to-start over six consecutive cells


def load(repo: Path):
    live2 = repo / "experiments/orchestration/live2"
    for p in (str(live2), str(live2 / "fleet"), str(repo / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import data_sources as DS
    import trace as TR
    return DS, TR


def evidence(repo: Path) -> Dict[str, Any]:
    out = {}
    for ln in open(repo / "results/sember/study_h/data/sember_mcq.jsonl"):
        if not ln.strip():
            continue
        r = json.loads(ln)
        if r.get("answer_start_time") is None or r.get("answer_end_time") is None:
            continue
        out[str(r["question_id"]).casefold()] = (float(r["answer_start_time"]),
                                                float(r["answer_end_time"]))
    return out


def census_one_seed(DS, TR, ev, seed: int, ks: List[int], a) -> Dict[str, Any]:
    """One trace is enough per seed: the permutation is k-INDEPENDENT, so every k's victim set is a
    prefix of it and the window is the same. Generating one trace at the largest k and reading its
    recorded `victim_permutation` is therefore exact, and it is also the nesting property being
    used rather than assumed."""
    DS.ROBOT_DEADLINE_S = float(a.robot_deadline_s)
    b = TR.generate_trace(seed, a.n, a.ratio, a.run_s, "A", outage_robots_k=max(ks),
                          outage_duration_s=a.d, outage_placement="centre",
                          outage_semantics="true", **WORKLOAD)
    om = b["meta"]["outage"]
    perm = list(om["victim_permutation"])
    t0, t1 = float(om["t_start"]), float(om["t_end"])
    first_victim_k = {}
    for i, dev in enumerate(perm):
        # the device is a victim at every k >= i+1, because victims are the permutation prefix
        first_victim_k[dev] = i + 1
    rows: Dict[tuple, Dict[str, Any]] = {}
    for r in b["records"]:
        if r.get("kind") != "recall_question":
            continue
        dev = str(r["device_id"])
        if not dev.startswith("robo"):
            continue
        tas = r.get("t_ask_session")
        qid = str(r.get("question_id") or "").casefold()
        e = ev.get(qid)
        if e is None or tas is None:
            continue
        t = float(r["t"])
        if t < t0:
            continue                      # asked before the window: no evidence can be missing yet
        sess0 = t - float(tas)
        aa, zz = sess0 + e[0], sess0 + e[1]
        if not (aa < t1 and zz > t0):
            continue                      # evidence does not overlap the window
        key = (dev, qid)
        row = rows.setdefault(key, {
            "device_id": dev, "question_id": qid, "instances": 0,
            "first_ask_run_s": round(t, 3),
            "evidence_run_s": [round(aa, 3), round(zz, 3)],
            "overlap_s": round(min(zz, t1) - max(aa, t0), 3),
            "device_becomes_victim_at_k": first_victim_k.get(dev)})
        row["instances"] += 1
    for row in rows.values():
        fk = row["device_becomes_victim_at_k"]
        row["control_cells_k"] = [k for k in ks if k < fk]
        row["treated_cells_k"] = [k for k in ks if k >= fk]
        row["MATCHED"] = bool(row["control_cells_k"] and row["treated_cells_k"])
    return {"seed": seed, "window": [t0, t1], "victim_permutation": perm,
            "first_victim_k_by_device": first_victim_k,
            "ladder": list(ks),
            "questions": sorted(rows.values(),
                                key=lambda r: (r["device_becomes_victim_at_k"], r["device_id"])),
            "n_affected_total": len(rows),
            "n_matched": sum(1 for r in rows.values() if r["MATCHED"]),
            "n_unmatched_victim_at_lowest_rung": sum(1 for r in rows.values()
                                                     if not r["MATCHED"])}


def sign_test_threshold(alpha: float, sided: int) -> int:
    """The smallest number of ALL-ONE-DIRECTION discordant pairs whose exact sign-test p is <=
    alpha. 0.5**b one-sided, 2*0.5**b two-sided."""
    b = 1
    while b < 200:
        p = (0.5 ** b) * (2 if sided == 2 else 1)
        if p <= alpha:
            return b
        b += 1
    return -1


def binom_sf(n: int, k: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), exact."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def n_needed(delta: float, b_req: int, power: float) -> int:
    """The smallest number of matched questions n such that, if each flips with probability delta
    all in one direction, P(discordant >= b_req) >= power."""
    for n in range(b_req, 4001):
        if binom_sf(n, b_req, delta) >= power:
            return n
    return -1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--k", type=int, action="append", default=None)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--robot-deadline-s", type=float, default=3.0)
    ap.add_argument("--arms-scope-a", type=int, default=2)
    ap.add_argument("--arms-scope-b", type=int, default=5)
    a = ap.parse_args(argv)
    seeds = sorted(a.seed) if a.seed else [4, 5, 6, 7]
    ks = sorted(a.k) if a.k else [1, 3, 5, 7, 9, 11]
    repo = Path(a.repo) if a.repo else REPO_DEFAULT
    DS, TR = load(repo)
    ev = evidence(repo)

    per_seed = {}
    for sd in seeds:
        per_seed["s%d" % sd] = census_one_seed(DS, TR, ev, sd, ks, a)

    # ---- the design as ruled: seeds 4 and 5, ladder {1, 3, 5}
    design_seeds = [s for s in (4, 5) if s in seeds]
    design_ladder = [k for k in (1, 3, 5) if k in ks]
    design = {}
    tot_matched = 0
    tot_affected = 0
    shared = []
    seen = {}
    for sd in design_seeds:
        c = per_seed["s%d" % sd]
        qs = [q for q in c["questions"] if q["device_becomes_victim_at_k"] <= max(design_ladder)]
        m = [q for q in qs if any(k < q["device_becomes_victim_at_k"] for k in design_ladder)
             and any(k >= q["device_becomes_victim_at_k"] for k in design_ladder)]
        design["s%d" % sd] = {
            "n_affected_in_ladder": len(qs), "n_matched_in_ladder": len(m),
            "matched_questions": [{"device_id": q["device_id"], "question_id": q["question_id"],
                                   "becomes_victim_at_k": q["device_becomes_victim_at_k"],
                                   "control_k": [k for k in design_ladder
                                                 if k < q["device_becomes_victim_at_k"]],
                                   "treated_k": [k for k in design_ladder
                                                 if k >= q["device_becomes_victim_at_k"]],
                                   "instances": q["instances"],
                                   "overlap_s": q["overlap_s"]} for q in m],
            "unmatched_questions": [{"device_id": q["device_id"],
                                     "question_id": q["question_id"],
                                     "becomes_victim_at_k": q["device_becomes_victim_at_k"],
                                     "why": ("its device is a victim at the lowest rung in the "
                                             "ladder, so this seed has no control cell for it")}
                                    for q in qs if q not in m]}
        tot_matched += len(m)
        tot_affected += len(qs)
        for q in m:
            seen.setdefault(q["question_id"], []).append("s%d" % sd)
    for qid, where in seen.items():
        if len(where) > 1:
            shared.append({"question_id": qid, "seeds": where})

    # ---- the MDE, as a count of discordant pairs
    b1 = sign_test_threshold(0.05, 1)
    b2 = sign_test_threshold(0.05, 2)
    mde = {
        "_test": ("the exact sign test on discordant pairs, which is McNemar's exact form. The "
                  "readout is within-question, within-arm and across-k, so each affected question "
                  "contributes AT MOST ONE discordant pair per comparison."),
        "n_matched_questions_scope_a": tot_matched,
        "discordant_pairs_needed_one_sided_0.05": b1,
        "discordant_pairs_needed_two_sided_0.05": b2,
        "SMALLEST_READABLE_DIFFERENCE": (
            "with %d matched questions, nothing smaller than %d of the %d changing outcome ALL IN "
            "THE SAME DIRECTION can reach one-sided p <= 0.05, and %d of %d for two-sided. In "
            "proportion terms that is %.0f and %.0f percent of the affected questions."
            % (tot_matched, b1, tot_matched, b2, tot_matched,
               100.0 * b1 / tot_matched, 100.0 * b2 / tot_matched)
            if tot_matched >= b1 else
            "with %d matched questions NO result can reach one-sided p <= 0.05 at all, because "
            "even %d of %d all in one direction gives p = %.3f. The readout can only be a census."
            % (tot_matched, tot_matched, tot_matched, 0.5 ** tot_matched)),
        "p_if_every_matched_question_flips_one_way": round(0.5 ** tot_matched, 6),
        "CAN_REACH_SIGNIFICANCE_AT_ALL": bool(tot_matched >= b1),
    }

    # ---- the inversion, on both axes, with the yields MEASURED
    yields = {}
    for sd in seeds:
        c = per_seed["s%d" % sd]
        yields["s%d" % sd] = {
            "matched_in_ladder_1_3_5": sum(
                1 for q in c["questions"]
                if 1 < q["device_becomes_victim_at_k"] <= 5),
            "marginal_by_rung": {
                "k%d" % k: sum(1 for q in c["questions"]
                               if q["device_becomes_victim_at_k"] == k)
                for k in ks},
            "cumulative_matched_by_top_rung": {
                "k%d" % k: sum(1 for q in c["questions"]
                               if 1 < q["device_becomes_victim_at_k"] <= k)
                for k in ks},
        }
    mean_per_seed = (sum(y["matched_in_ladder_1_3_5"] for y in yields.values()) / len(yields)
                     if yields else 0.0)

    targets = []
    for delta in (0.8, 0.6, 0.5, 0.4, 0.3, 0.2):
        n_req = n_needed(delta, b1, 0.80)
        if n_req < 0:
            targets.append({"effect_per_question": delta, "n_matched_needed": None,
                            "note": "unreachable"})
            continue
        # SEED AXIS: ladder {1,3,5}, 2 arms (scope A) and 5 arms (scope B)
        seeds_req = math.ceil(n_req / mean_per_seed) if mean_per_seed else None
        cells_a = (seeds_req * len(design_ladder) * a.arms_scope_a) if seeds_req else None
        cells_b = (seeds_req * len(design_ladder) * a.arms_scope_b) if seeds_req else None
        # RUNG AXIS: how far up the ladder, at the two ruled seeds, before n_req is reached
        rung_needed = None
        for k in ks:
            got = sum(yields["s%d" % sd]["cumulative_matched_by_top_rung"]["k%d" % k]
                      for sd in design_seeds)
            if got >= n_req:
                rung_needed = k
                break
        rung_cells = None
        if rung_needed is not None:
            n_rungs = len([k for k in ks if k <= rung_needed])
            rung_cells = len(design_seeds) * n_rungs * a.arms_scope_a
        targets.append({
            "effect_per_question": delta,
            "n_matched_needed_for_80pc_power": n_req,
            "SEED_AXIS": {"seeds_needed": seeds_req,
                          "cells_scope_a_2_arms": cells_a,
                          "hours_scope_a": (round(cells_a * SEC_PER_CELL / 3600.0, 2)
                                            if cells_a else None),
                          "cells_scope_b_5_arms": cells_b,
                          "hours_scope_b": (round(cells_b * SEC_PER_CELL / 3600.0, 2)
                                            if cells_b else None)},
            "RUNG_AXIS": {"top_rung_needed_at_seeds_4_and_5": rung_needed,
                          "cells_2_arms": rung_cells,
                          "hours_2_arms": (round(rung_cells * SEC_PER_CELL / 3600.0, 2)
                                           if rung_cells else None),
                          "note": ("None means the rung axis alone cannot reach it even at k = 11, "
                                   "the ceiling at this mix"
                                   if rung_needed is None else "")},
        })

    out = {
        "_what": ("D273: the per-question matched census, the minimum detectable effect as a count "
                  "of discordant pairs, and the inversion onto the seed and rung axes, priced at "
                  "%g s per cell." % SEC_PER_CELL),
        "_why_matched": ("because the victim sets NEST, an affected question appears in a cell "
                         "where its device IS a victim and in a cell where it is NOT, at the same "
                         "window, same arm, same seed and same trace structure. Each question is "
                         "therefore its own control, which is the quantity the nesting was built "
                         "to create."),
        "_matching_key": ("(question_id, device_id) against victim membership against k. Victim "
                          "membership is read from the recorded `victim_permutation`: the device's "
                          "index in it plus one is the k at which it first becomes a victim, and "
                          "because victims are the permutation PREFIX that one number decides "
                          "every cell's role for that question."),
        "design_as_ruled": {"seeds": design_seeds, "ladder": design_ladder,
                            "per_seed": design,
                            "TOTAL_MATCHED_QUESTIONS": tot_matched,
                            "TOTAL_AFFECTED_QUESTIONS": tot_affected,
                            "questions_shared_between_pairs_or_seeds": shared,
                            "_sharing_note": ("a question affected at two rungs is ONE question: "
                                              "it has one control set and one or two treated "
                                              "cells, and it is counted once here.")},
        "MDE": mde,
        "measured_yields": {"per_seed": yields,
                            "mean_matched_per_seed_ladder_1_3_5": round(mean_per_seed, 3)},
        "INVERSION": targets,
        "seeds_censused": seeds, "rungs_censused": ks,
    }
    try:
        sys.path.insert(0, str(repo / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d273_matched_power.py", model="none-cpu",
                                   device="flash_cpu", n=len(seeds), args=a)
    except Exception as e:
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")

    print("MATCHED QUESTIONS, design as ruled (seeds %s, ladder %s): %d matched, %d affected"
          % (design_seeds, design_ladder, tot_matched, tot_affected))
    for sd in design_seeds:
        d = design["s%d" % sd]
        print("  s%d: matched %d, unmatched %d" % (sd, d["n_matched_in_ladder"],
                                                   len(d["unmatched_questions"])))
        for q in d["matched_questions"]:
            print("     %s %s victim@k%d control_k=%s treated_k=%s inst=%d overlap=%.2fs"
                  % (q["device_id"], q["question_id"][:8], q["becomes_victim_at_k"],
                     q["control_k"], q["treated_k"], q["instances"], q["overlap_s"]))
    print("SHARED between pairs or seeds:", shared or "none")
    print("MDE:", mde["SMALLEST_READABLE_DIFFERENCE"])
    print()
    print("MEASURED YIELD per seed (ladder 1,3,5):",
          {k: v["matched_in_ladder_1_3_5"] for k, v in yields.items()})
    print("MARGINAL by rung, per seed:")
    for k, v in yields.items():
        print("   %s %s" % (k, v["marginal_by_rung"]))
    print()
    print("%-8s %-8s | %-7s %-7s %-7s | %-7s %-7s %-7s" % (
        "effect", "n_need", "seeds", "cellsA", "hoursA", "rung", "cells", "hours"))
    for t in targets:
        sa, ra = t["SEED_AXIS"], t["RUNG_AXIS"]
        print("%-8s %-8s | %-7s %-7s %-7s | %-7s %-7s %-7s" % (
            t["effect_per_question"], t.get("n_matched_needed_for_80pc_power"),
            sa["seeds_needed"], sa["cells_scope_a_2_arms"], sa["hours_scope_a"],
            ra["top_rung_needed_at_seeds_4_and_5"], ra["cells_2_arms"], ra["hours_2_arms"]))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
