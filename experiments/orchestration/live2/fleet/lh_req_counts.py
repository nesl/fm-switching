"""Per-cell robot question counts on the LH-REQ workload, and the run-length choice.

Two jobs, one script, because they read the same traces:

  * D142's per-cell table: for each cell, the POOLED robot question count and the number of
    DISTINCT LH-REQ questions asked, flagging any cell below D82's minimum of 20 pooled.
  * Overnight rule 1's run-length choice: the shortest length at which EVERY cell in the fixed
    set (12 and 16 devices, seeds 0/4/5/6, mix 40:40:20) reaches 20 pooled questions. If even
    the longest candidate fails, the longest is used and the robot result is labelled
    "not measurable" wherever it is below 20.

Pooled and distinct are reported side by side because they can diverge: one question asked by
three devices is three pooled and one distinct, and an on-time fraction over the pooled count
then rests on fewer questions than its denominator suggests. On the EVAL workload the pool is 602
questions over 164 sessions and this hardly matters; on LH-REQ it is 69 over 51 and it does.

count_only is used throughout. It runs the identical control flow and skips only the wire records,
and the fleet suite's check (h) asserts the two agree exactly, so the counts are the run's counts.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import trace as TR  # noqa: E402

D82_MIN_POOLED = 20
RULE1_SIZES = (12, 16)
RULE1_SEEDS = (0, 4, 5, 6)
RULE1_LENGTHS = (600.0, 900.0, 1200.0)
# Development seeds only. Seeds 1, 2 and 3 and any HOLDOUT seed are never used here.
ALLOWED_SEEDS = (0, 4, 5, 6)


def cell(seed, n, ratio, run_s, question_set):
    if seed not in ALLOWED_SEEDS:
        raise ValueError("seed %r is not a development seed %r" % (seed, ALLOWED_SEEDS))
    st = TR.generate_trace(seed=seed, n_devices=n, ratio=ratio, run_s=run_s, mode="A",
                           count_only=True, robot_question_set=question_set)["stats"]
    return dict(seed=seed, n_devices=n, ratio=ratio, run_s=run_s,
                n_robot=st["n_robot"], n_dashcam=st["n_dashcam"], n_assistive=st["n_assistive"],
                pooled=st["robot_questions_total"],
                distinct=st["robot_distinct_questions_asked"],
                repeats=st["robot_question_repeats"],
                asks_per_distinct=st["robot_asks_per_distinct_question"],
                pool_coverage=st["robot_pool_coverage"],
                question_pool_n=st["robot_question_pool_n"],
                session_pool_n=st["robot_session_pool_n"],
                sessions_started=st["robot_sessions_started"],
                session_repeats=st["session_repeats"],
                questions_before_join=st["robot_questions_before_join"],
                meets_20_pooled=bool(st["robot_pool_meets_20"]),
                meets_20_distinct=bool(st["robot_distinct_meets_20"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question-set", default="lh_req", choices=TR.DS.ROBOT_QUESTION_SETS)
    ap.add_argument("--ratio", default="40:40:20")
    ap.add_argument("--sizes", default="10,12,16,20,24,28,32")
    ap.add_argument("--seeds", default="0,4,5,6")
    ap.add_argument("--run-s", default="600")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sizes = [int(x) for x in a.sizes.split(",")]
    seeds = [int(x) for x in a.seeds.split(",")]
    lengths = [float(x) for x in a.run_s.split(",")]

    cells = [cell(s, n, a.ratio, r, a.question_set)
             for r in lengths for n in sizes for s in seeds]

    # Rule 1's choice, over its OWN fixed set, not over whatever --sizes was passed.
    rule1 = {}
    for r in RULE1_LENGTHS:
        sub = [cell(s, n, a.ratio, r, a.question_set) for n in RULE1_SIZES for s in RULE1_SEEDS]
        rule1[str(int(r))] = dict(
            n_cells=len(sub),
            all_meet_20=all(c["meets_20_pooled"] for c in sub),
            min_pooled=min(c["pooled"] for c in sub),
            min_distinct=min(c["distinct"] for c in sub),
            failing_cells=[dict(n=c["n_devices"], seed=c["seed"], pooled=c["pooled"])
                           for c in sub if not c["meets_20_pooled"]])
    passing = [r for r in RULE1_LENGTHS if rule1[str(int(r))]["all_meet_20"]]
    chosen = min(passing) if passing else max(RULE1_LENGTHS)
    out = dict(
        _what="per-cell robot question counts and the run-length choice",
        question_set=a.question_set, ratio=a.ratio,
        d82_min_pooled=D82_MIN_POOLED,
        rule1=dict(
            fixed_set=dict(sizes=list(RULE1_SIZES), seeds=list(RULE1_SEEDS),
                           lengths=list(RULE1_LENGTHS), ratio=a.ratio),
            by_length=rule1,
            any_length_passes=bool(passing),
            chosen_run_s=chosen,
            rule=("the SHORTEST length at which all 8 cells reach 20 pooled questions; if none "
                  "does, the longest candidate is used and the robot result is labelled NOT "
                  "MEASURABLE in every cell below 20"),
            fallback_in_force=not bool(passing),
            not_measurable_cells=(rule1[str(int(chosen))]["failing_cells"] if not passing else [])),
        cells=cells)
    Path(a.out).write_text(json.dumps(out, indent=1, default=float))

    print("%-7s %-4s %-5s %-5s %-8s %-9s %-8s %-7s %s"
          % ("run_s", "n", "seed", "rob", "pooled", "distinct", "repeats", "cov", "flag"))
    for c in cells:
        print("%-7.0f %-4d %-5d %-5d %-8d %-9d %-8d %-7s %s"
              % (c["run_s"], c["n_devices"], c["seed"], c["n_robot"], c["pooled"],
                 c["distinct"], c["repeats"], c["pool_coverage"],
                 "" if c["meets_20_pooled"] else "BELOW D82 MINIMUM OF 20 POOLED"))
    print("\nrule 1: chosen run_s = %.0f s, fallback in force = %s"
          % (chosen, not bool(passing)))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
