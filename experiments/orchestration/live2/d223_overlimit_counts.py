#!/usr/bin/env python3
"""D223 (2): ROBOT RECALL QUESTIONS WHOSE FULL HISTORY EXCEEDS THE 0.5x LIMIT, PER SEED.

THE NUMBER THE H100 NEEDS. D223 (1) sets the real 0.5x condition at pool 31,488 tokens and MAX
PROMPT 31,472, and the engine's own argv in the committed `kv0.5r` cells carries
`--max-model-len 31472`. So the population of robot recall questions that an engine CANNOT answer
at 0.5x is the set whose full history exceeds 31,472 tokens, and that set is strictly larger than
the >32,768 set the 1x cells were analysed against. This reports both, per seed, s4 to s7.

THE DEFINITION IS D170's, UNCHANGED, AND ONLY THE THRESHOLD MOVES (CLAUDE.md check 4). The offered
side is recomputed from the trace, which is deterministic in the seed, exactly as
`d170_overlimit.py:offered` does it: a recall record's `history_tokens`, over the threshold. The
same cell arguments are used, from `d170_overlimit.CELL_ARGS`, so "a robot question" means here
what it means there. Nothing is read from an arm's output, because this is a property of the
WORKLOAD and not of any policy.

THE POSITIVE CONTROL IS THE COMMITTED 18 (CLAUDE.md check 7). D176 records the over-32,768 set as
18 questions, all at seed 7, on `robo004 s000`. This script recomputes that set at 32,768 and
CHECKS it against those committed facts before the 31,472 count is reported. If the control fails,
the counting method is broken and the new number must not be read; an impossible success is as
diagnostic as an impossible failure, so the check prints what it found either way.

DISTRIBUTION, NOT ONLY A COUNT (CLAUDE.md check 3). Per seed it reports the max history, the full
sorted list of histories above the LOWER threshold, and the questions that fall BETWEEN the two
thresholds, which are exactly the ones 0.5x newly excludes and 1x did not. A bare count of zero at
seeds 4 to 6 would read as an equivalence; the max beside it shows those seeds are UNEXERCISED
(CLAUDE.md Rule 2) rather than clean, because no history there comes near either threshold.

Usage: python d223_overlimit_counts.py --out FILE
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d170_overlimit as D170                                                  # noqa: E402
import trace as TR                                                            # noqa: E402

LIMIT_05X = 31472          # the real 0.5x max prompt: D223 (1), and --max-model-len in the argv
LIMIT_1X = 32768           # the 1x limit D170 and D176 analysed against
SEEDS = (4, 5, 6, 7)


def histories(seed: int) -> List[Dict[str, Any]]:
    """Every robot RECALL opportunity in the seed's trace, with its full-history token count.

    D170's `offered` with its threshold removed, so the distribution below each limit is visible
    instead of only the tail above one.
    """
    A = D170.CELL_ARGS
    b = TR.generate_trace(seed, A["n_devices"], A["ratio"], A["run_s"], A["mode"],
                          robot_question_set=A["robot_question_set"],
                          ss_question_set=A["ss_question_set"],
                          dashcam_format=A["dashcam_format"],
                          robot_upload=A["robot_upload"],
                          robot_reask_mean_s=A["robot_reask_mean_s"])
    return [{"opportunity_id": r["opportunity_id"],
             "history_tokens": int(r.get("history_tokens") or 0),
             "device_id": r.get("device_id"), "session_id": r.get("session_id")}
            for r in b["records"] if "recall" in str(r.get("kind") or "")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--crosscheck", default=None,
                    help="a committed d223_context_limit_offered.json to agree with (CLAUDE.md "
                         "check 1: an independent recomputation of the same quantity)")
    a = ap.parse_args(argv)

    per_seed: Dict[str, Any] = {}
    tot05 = tot1x = 0
    for s in SEEDS:
        rows = histories(s)
        toks = sorted(r["history_tokens"] for r in rows)
        over05 = [r for r in rows if r["history_tokens"] > LIMIT_05X]
        over1x = [r for r in rows if r["history_tokens"] > LIMIT_1X]
        between = [r for r in rows
                   if LIMIT_05X < r["history_tokens"] <= LIMIT_1X]
        tot05 += len(over05)
        tot1x += len(over1x)
        per_seed[str(s)] = {
            "n_recall_opportunities": len(rows),
            "max_history_tokens": (toks[-1] if toks else 0),
            "median_history_tokens": (toks[len(toks) // 2] if toks else 0),
            "n_over_31472_the_0.5x_limit": len(over05),
            "n_over_32768_for_reference": len(over1x),
            "n_NEWLY_excluded_at_0.5x_between_31472_and_32768": len(between),
            "newly_excluded": sorted(
                (r["opportunity_id"], r["history_tokens"]) for r in between),
            "devices_over_31472": sorted({str(r["device_id"]) for r in over05}),
            "sessions_over_31472": sorted({str(r["session_id"]) for r in over05}),
            "all_histories_over_31472_sorted": sorted(r["history_tokens"] for r in over05),
            "top5_histories": toks[-5:],
            "UNEXERCISED": (not over05 and not over1x),
            "unexercised_note": (
                None if (over05 or over1x) else
                "no recall history at this seed reaches either limit (max %d tokens), so a zero "
                "here is UNEXERCISED (CLAUDE.md Rule 2) and says nothing about any arm's "
                "over-limit behaviour" % (toks[-1] if toks else 0)),
        }

    # THE POSITIVE CONTROL, against D176's committed facts, before the new number is read.
    s7 = per_seed["7"]
    ctl = {
        "_what": ("POSITIVE CONTROL on the counting method: D176 records the over-32,768 set as "
                  "18 questions, all at seed 7, on robo004 s000."),
        "committed": {"n": 18, "seed": 7, "device": "robo004", "session": "s000"},
        "recomputed_n_over_32768_at_seed_7": s7["n_over_32768_for_reference"],
        "recomputed_total_over_32768_all_seeds": tot1x,
        "recomputed_devices_over_31472_at_seed_7": s7["devices_over_31472"],
        "other_seeds_have_none_over_32768": all(
            per_seed[str(s)]["n_over_32768_for_reference"] == 0 for s in SEEDS if s != 7),
    }
    ctl["PASS"] = bool(ctl["recomputed_n_over_32768_at_seed_7"] == 18
                       and ctl["other_seeds_have_none_over_32768"])
    ctl["VERDICT"] = ("PASS: the method reproduces the committed 18 at seed 7 and none elsewhere, "
                      "so the 31,472 count below is produced by a method that is known to agree "
                      "with a committed result."
                      if ctl["PASS"] else
                      "FAIL: THE METHOD DISAGREES WITH THE COMMITTED D176 SET (recomputed %s "
                      "against a committed 18). The 31,472 count must NOT be read until this is "
                      "explained: either the definition moved or the committed value did."
                      % ctl["recomputed_n_over_32768_at_seed_7"])

    # CLAUDE.md CHECK 1: CROSS-CHECK AGAINST THE COMMITTED MEASUREMENT OF THE SAME QUANTITY.
    # A second session computed this table independently and committed it as
    # frozen_test/d223_context_limit_offered.json. Two independent recomputations agreeing, each
    # with its own control against d170_overlimit.json, is a far stronger warrant than either
    # alone, and a DISAGREEMENT would mean one of the two definitions had moved. So it is checked
    # here rather than asserted in prose, and any mismatch is listed field by field.
    xc = None
    if a.crosscheck:
        other = json.loads(Path(a.crosscheck).read_text())
        rows = []
        for s in SEEDS:
            mine = per_seed[str(s)]
            theirs = (other.get("per_seed") or {}).get("s%d" % s) or {}
            for field, m, t_ in (
                    ("n_recall_opportunities", mine["n_recall_opportunities"], theirs.get("n")),
                    ("over_31472", mine["n_over_31472_the_0.5x_limit"], theirs.get("over_31472")),
                    ("over_32768", mine["n_over_32768_for_reference"], theirs.get("over_32768")),
                    ("between", mine["n_NEWLY_excluded_at_0.5x_between_31472_and_32768"],
                     theirs.get("between")),
                    ("max_history", mine["max_history_tokens"], theirs.get("max"))):
                rows.append({"seed": s, "quantity": field, "this_run": m, "committed": t_,
                             "agree": (m == t_)})
        bad = [r for r in rows if not r["agree"]]
        xc = {"_what": ("CLAUDE.md check 1: this run against the committed independent "
                        "recomputation in frozen_test/d223_context_limit_offered.json"),
              "source": a.crosscheck, "n_quantities": len(rows), "rows": rows,
              "disagreements": bad, "PASS": not bad,
              "VERDICT": ("PASS: two independently written recomputations of this table agree on "
                          "every quantity at every seed." if not bad else
                          "DISAGREEMENT on %d quantities: STOP and reconcile before either table "
                          "is cited; the same name is carrying two definitions." % len(bad))}

    out = {
        "crosscheck_against_committed": xc,
        "_what": ("D223 (2): robot recall questions whose FULL HISTORY exceeds the 0.5x limit "
                  "(31,472) and, for reference, the 1x limit (32,768), per seed s4 to s7"),
        "_definition": ("D170's, unchanged: a recall record's `history_tokens` from the trace, "
                        "which is deterministic in the seed, under d170_overlimit.CELL_ARGS. Only "
                        "the threshold moves. This is a property of the WORKLOAD, not of an arm."),
        "limits": {"0.5x_max_prompt": LIMIT_05X, "1x": LIMIT_1X,
                   "0.5x_source": "D223 (1), and --max-model-len 31472 in the kv0.5r cells' argv"},
        "positive_control": ctl,
        "per_seed": per_seed,
        "totals": {"over_31472_s4_to_s7": tot05, "over_32768_s4_to_s7": tot1x,
                   "newly_excluded_at_0.5x": tot05 - tot1x},
        "cell_args": D170.CELL_ARGS,
    }
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({
        "CONTROL": ctl["VERDICT"],
        "CROSSCHECK": (xc["VERDICT"] if xc else "not run"),
        "per_seed": {s: {"over_31472": per_seed[s]["n_over_31472_the_0.5x_limit"],
                         "over_32768": per_seed[s]["n_over_32768_for_reference"],
                         "max_history": per_seed[s]["max_history_tokens"]}
                     for s in per_seed},
        "totals": out["totals"]}, indent=1))
    return 0 if (ctl["PASS"] and (xc is None or xc["PASS"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
