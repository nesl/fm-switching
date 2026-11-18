#!/usr/bin/env python3
"""The D97 robot-measurability table: which fleet sizes are eligible, at which seeds.

StudyLIVE2-fleet, amendments 2 and 3. CPU only; no server, no GPU, no model. Every number here
is a property of the TRACE, which is why D97 can fix eligibility before any GPU run happens.

RECOMPUTED UNDER D101 (amendment 3). D101 makes each robot join its first session part-way, so
the questions before the join point are no longer emitted and the pooled robot count per run
CHANGES. D101 orders the D97 entry points recomputed from traces before any GPU run, which is
what this module now produces. The table also carries, per cell, what the join removed
(`questions_before_join`) and what the cloud already holds at t = 0 (`preloads_emitted`,
`preload_tokens_*`, `join_offset_*`), because the preload is the cold-rebuild pressure D101
exists to create.

D97. Robot-pool eligibility (at least 20 pooled questions
per run, D82) is a property of the trace, so it is fixed from traces before any GPU run. A fleet
size enters a main-sweep comparison only if its robot pool is eligible at EVERY seed that will be
reported for that comparison: seeds 1, 2 and 3. The pilot (seed 0) only reports which of its
sizes were measurable at seed 0; seed 0 never sets an entry point. A size is never made
measurable by averaging or borrowing across seeds.

THE ROUNDING RULE FOR ODD SIZES. `trace._split_fleet` computes

    n_dashcam = int(round(n_devices * d / (d + r))),   n_robot = n_devices - n_dashcam

with Python's `round`, which is ROUND-HALF-TO-EVEN. So at 50:50 an odd size does not alternate
regularly: size 5 gives 2 dashcam and 3 robot (round(2.5) = 2), size 7 gives 4 and 3
(round(3.5) = 4), size 9 gives 4 and 5 (round(4.5) = 4), size 11 gives 6 and 5. At 75:25 and
25:75 the quarter points land on .25, .5 and .75, so only the .5 cases are affected. The rule is
the existing implemented behaviour and was not changed here; the table states the actual split
for every size so nothing is hidden behind it.

Counting uses `trace.generate_trace(..., count_only=True)`, which runs the generator's own
control flow and skips only the construction of wire records and device-answer rows. It is a
skip, not a second implementation; `tests/test_live2_fleet.py` check (h) asserts the two modes
agree exactly on a sample of cells.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import trace as TR
import data_sources as DS

MAIN_RUN_S = 600.0                  # D95 (1): the pilot is the same length as a main run
ROB_MIN = 20                        # D82, POOLED over the run
DASH_MIN_INSTANTS = 200             # D71, per dashcam device
REPORTED_SEEDS = (1, 2, 3)          # D97
PILOT_SEED = 0                      # D95 (7), never used in a reported run

FIELDS = ("ratio", "seed", "n_devices", "n_dashcam", "n_robot", "robot_questions",
          "robot_eligible", "dashcam_min_instants", "dashcam_meeting_200",
          "clip_plays_started", "clip_plays_distinct", "clip_repeats", "clip_pool",
          "sessions_started", "sessions_distinct", "session_repeats", "session_pool",
          "sessions_completed", "history_batches", "n_opportunities",
          # D101: the part-way join. `questions_before_join` is what the join point removed.
          "questions_before_join", "preloads_emitted", "preload_tokens_min",
          "preload_tokens_median", "preload_tokens_max", "preload_tokens_total",
          "join_offset_min_s", "join_offset_median_s", "join_offset_max_s")


def cell(seed: int, n_devices: int, ratio: str, run_s: float = MAIN_RUN_S) -> Dict[str, Any]:
    st = TR.generate_trace(seed, n_devices, ratio, run_s, "A", count_only=True)["stats"]
    nq = int(st["robot_questions_total"])
    inst = st["dashcam_instants"]
    off = sorted(st["robot_join_offset_s"].values())
    return dict(ratio=ratio, seed=seed, n_devices=n_devices,
                questions_before_join=int(st["robot_questions_before_join"]),
                preloads_emitted=int(st["robot_preloads_emitted"]),
                preload_tokens_min=st["robot_preload_tokens_min"],
                preload_tokens_median=st["robot_preload_tokens_median"],
                preload_tokens_max=st["robot_preload_tokens_max"],
                preload_tokens_total=st["robot_preload_tokens_total"],
                join_offset_min_s=(round(off[0], 3) if off else None),
                join_offset_median_s=(round(off[len(off) // 2], 3) if off else None),
                join_offset_max_s=(round(off[-1], 3) if off else None),
                n_dashcam=int(st["n_dashcam"]), n_robot=int(st["n_robot"]),
                robot_questions=nq, robot_eligible=int(nq >= ROB_MIN),
                dashcam_min_instants=(min(inst.values()) if inst else None),
                dashcam_meeting_200=int(st["dashcam_meeting_200"]),
                clip_plays_started=int(st["dashcam_plays_started"]),
                clip_plays_distinct=len(st["clip_play_counts"]),
                clip_repeats=int(st["clip_repeats"]),
                clip_pool=len(DS.nexar_clip_meta()),
                sessions_started=int(st["robot_sessions_started"]),
                sessions_distinct=len(st["session_play_counts"]),
                session_repeats=int(st["session_repeats"]),
                session_pool=len(DS.eval_sessions()),
                sessions_completed=int(st["robot_sessions_completed"]),
                history_batches=int(st["robot_history_batches"]),
                n_opportunities=sum(inst.values()) + nq)


def summarise(rows: Sequence[Dict[str, Any]],
              seeds: Sequence[int] = REPORTED_SEEDS) -> Dict[str, Any]:
    """Per ratio: the D97 entry point, and every larger size that is NOT eligible at all seeds."""
    out: Dict[str, Any] = {}
    by = {}
    for r in rows:
        by.setdefault(r["ratio"], {}).setdefault(int(r["n_devices"]), {})[int(r["seed"])] = r
    for ratio, sizes in by.items():
        elig, ineligible = [], []
        for n in sorted(sizes):
            have = [sizes[n].get(s) for s in seeds]
            if any(h is None for h in have):
                continue
            if all(int(h["robot_eligible"]) for h in have):
                elig.append(n)
            else:
                ineligible.append(n)
        entry = min(elig) if elig else None
        above = [n for n in ineligible if entry is not None and n > entry]
        out[ratio] = dict(
            reported_seeds=list(seeds), entry_point=entry,
            n_sizes_eligible_at_all_seeds=len(elig),
            non_monotone_sizes_above_entry=above,
            monotone=(not above),
            per_seed_entry_point={s: (min((n for n in sorted(sizes)
                                           if sizes[n].get(s)
                                           and int(sizes[n][s]["robot_eligible"])),
                                          default=None)) for s in seeds},
            pilot_seed_measurable={n: bool(sizes[n][PILOT_SEED]["robot_eligible"])
                                   for n in sorted(sizes) if PILOT_SEED in sizes[n]},
            # D101: what the cloud already holds at t = 0 at the entry point, per reported seed.
            preload_at_entry=({s: dict(
                tokens_min=sizes[entry][s]["preload_tokens_min"],
                tokens_median=sizes[entry][s]["preload_tokens_median"],
                tokens_max=sizes[entry][s]["preload_tokens_max"],
                tokens_total=sizes[entry][s]["preload_tokens_total"],
                preloads_emitted=sizes[entry][s]["preloads_emitted"],
                questions_before_join=sizes[entry][s]["questions_before_join"],
                robot_questions=sizes[entry][s]["robot_questions"])
                for s in seeds if entry is not None and s in sizes.get(entry, {})}
                if entry is not None else {}),
            dashcam_min_instants_over_all_cells=min(
                (r["dashcam_min_instants"] for n in sizes for r in sizes[n].values()
                 if r["dashcam_min_instants"] is not None), default=None),
            first_size_with_clip_repeats=min(
                (n for n in sorted(sizes)
                 if any(r["clip_repeats"] > 0 for r in sizes[n].values())), default=None),
            first_size_with_session_repeats=min(
                (n for n in sorted(sizes)
                 if any(r["session_repeats"] > 0 for r in sizes[n].values())), default=None),
            note=("D97: a size enters a main-sweep comparison only if its robot pool is eligible "
                  "at EVERY reported seed. `non_monotone_sizes_above_entry` is why eligibility "
                  "is checked for each size actually chosen and never assumed from the entry "
                  "point upward. The pilot seed never sets an entry point (D95 (7))."))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-devices", type=int, default=4)
    ap.add_argument("--max-devices", type=int, default=128)
    ap.add_argument("--run-s", type=float, default=MAIN_RUN_S)
    ap.add_argument("--seeds", type=int, nargs="*", default=[PILOT_SEED, *REPORTED_SEEDS])
    ap.add_argument("--ratios", nargs="*", default=sorted(TR.RATIOS))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    for ratio in a.ratios:
        for seed in a.seeds:
            for n in range(a.min_devices, a.max_devices + 1):
                rows.append(cell(seed, n, ratio, a.run_s))
            print(f"{ratio} seed {seed}: done", flush=True)
    with open(out / "robot_eligibility_4_to_128.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    summary = dict(
        rule=("D97: a fleet size enters a main-sweep "
              "comparison only if its robot pool is eligible (>= 20 pooled questions per run, "
              "D82) at EVERY reported seed. The pilot seed 0 only reports which of its sizes "
              "were measurable at seed 0 and never sets an entry point. A size is never made "
              "measurable by averaging or borrowing across seeds."),
        provenance=("recomputed under D101; design-log row pending (planner will log as D107). "
                    "Robots join their first session part-way, so the questions before the join "
                    "point are not emitted and not counted and the pooled count per run is NOT "
                    "the pre-D101 count."),
        run_s=a.run_s, robot_min_questions=ROB_MIN, dashcam_min_instants=DASH_MIN_INSTANTS,
        reported_seeds=list(REPORTED_SEEDS), pilot_seed=PILOT_SEED,
        sizes=[a.min_devices, a.max_devices], ratios=list(a.ratios),
        rounding_rule=("n_dashcam = int(round(n_devices * d / (d + r))) with Python's "
                       "round-half-to-even; n_robot = n_devices - n_dashcam"),
        counting=("trace.generate_trace(count_only=True): the generator's own control flow with "
                  "record construction skipped; equivalence asserted by test (h)"),
        is_measurement=False,
        per_ratio=summarise(rows))
    (out / "robot_eligibility_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["per_ratio"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
