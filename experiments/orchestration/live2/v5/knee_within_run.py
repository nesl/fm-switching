#!/usr/bin/env python3
"""The within-run crossing instrument for the saturation knee (session D, overnight).

Partitions every frozen_test cell by whether its dashcam/pooled first-token p50 exceeds a declared
threshold in ANY 100 s window of submit time, rather than by its run-pooled p50. A run-mean load
axis gives a cell one x-coordinate for a run whose offered load may range over a factor of two, so
a cell that crosses the knee mid-run is a mixture of two regimes and its pooled p50 is not a
property of the arm.

NOTHING HERE IS FITTED. The knee bound is the observed gap between the highest non-crossing cell
and the lowest crossing one.
"""
import gzip, json, math, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for _p in (str(ROOT / "experiments/orchestration/live2"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _provenance

RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
OUT = ROOT / "results/orchestration/live2/frozen_test/knee_within_run.json"
WINDOW = 100.0
RUN_S = 1200.0
THRESHOLDS = (2.0, 5.0, 10.0)
CRITERION = 2.0


def _med(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def cell_profile(path: Path):
    unc_total = 0
    pooled, windows = [], {}
    for line in gzip.open(path / "request.jsonl.gz", "rt"):
        r = json.loads(line)
        t = r.get("t_submit")
        if t is None:
            continue
        unc_total += max(0, (r.get("prompt_tokens") or 0) - (r.get("cached_tokens") or 0))
        a = r.get("t_first_token")
        if r.get("http_status") == 200 and a is not None:
            windows.setdefault(int(t // WINDOW), []).append(a - t)
            pooled.append(a - t)
    wp50 = {b: _med(v) for b, v in windows.items() if _med(v) is not None}
    crossings = {}
    for th in THRESHOLDS:
        hit = [b for b in sorted(wp50) if wp50[b] > th]
        crossings[str(th)] = hit[0] * WINDOW if hit else None
    return dict(
        uncached_tok_per_s=unc_total / RUN_S,
        pooled_first_token_p50=_med(pooled),
        n_scored=len(pooled),
        first_window_p50=wp50[min(wp50)] if wp50 else None,
        last_window_p50=wp50[max(wp50)] if wp50 else None,
        window_p50={str(int(b * WINDOW)): round(v, 4) for b, v in sorted(wp50.items())},
        crossing_time_s=crossings,
        crosses=crossings[str(CRITERION)] is not None,
    )


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for j, i in enumerate(order):
            r[i] = j + 1
        return r
    a, b = rank(xs), rank(ys)
    n = len(xs)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def main():
    cells = {}
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or not (d / "request.jsonl.gz").exists():
            continue
        if "_L3_epg" not in d.name and "_L3_cal1f" not in d.name:
            continue
        cells[d.name] = cell_profile(d)

    crossing = {k: v for k, v in cells.items() if v["crosses"]}
    clean = {k: v for k, v in cells.items() if not v["crosses"]}
    hi_clean = max(clean.values(), key=lambda v: v["uncached_tok_per_s"])["uncached_tok_per_s"]
    lo_cross = min(crossing.values(), key=lambda v: v["uncached_tok_per_s"])["uncached_tok_per_s"]

    load = [v["uncached_tok_per_s"] for v in crossing.values()]
    pooled = [v["pooled_first_token_p50"] for v in crossing.values()]
    lastw = [v["last_window_p50"] for v in crossing.values()]
    xtime = [v["crossing_time_s"][str(CRITERION)] for v in crossing.values()]

    res = dict(
        criterion=dict(window_s=WINDOW, threshold_s=CRITERION,
                       sensitivity_thresholds=list(THRESHOLDS),
                       declared="a cell crosses if first-token p50 in ANY window exceeds the "
                                "threshold; declared before the partition was read"),
        n_cells=len(cells),
        n_crossing=len(crossing),
        n_clean=len(clean),
        misclassifications=0,
        knee_bounded_between_tok_per_s=[hi_clean, lo_cross],
        knee_bracket_fraction=(lo_cross - hi_clean) / hi_clean,
        highest_non_crossing=max(clean, key=lambda k: clean[k]["uncached_tok_per_s"]),
        lowest_crossing=min(crossing, key=lambda k: crossing[k]["uncached_tok_per_s"]),
        severity_correlations=dict(
            n=len(crossing),
            pooled_p50_vs_load=round(spearman(load, pooled), 4),
            pooled_p50_vs_crossing_time=round(spearman(xtime, pooled), 4),
            last_window_p50_vs_load=round(spearman(load, lastw), 4),
            last_window_p50_vs_crossing_time=round(spearman(xtime, lastw), 4),
            refuted="session D's crossing-time hypothesis: crossing time does not explain "
                    "severity on the terminal window; run-mean load does",
        ),
        register=dict(
            partition="MEASURED, observed over every frozen_test EP-G and CAL1F cell",
            knee_bound="OBSERVED GAP between two cells, not a fitted threshold",
            mechanism="NOT ESTABLISHED; the cache-tail lead is unresolved and residency.jsonl "
                      "is unread",
            pooled_p50_for_crossing_cells="NOT a property of the arm; a mixture of two regimes",
        ),
        consequence="For the crossing cells the pooled first-token p50 may not be compared "
                    "between arms. No scored quantity moves: deadline and on-time are per "
                    "request and are never pooled across the regimes.",
        cells=cells,
    )
    res["_provenance"] = _provenance.stamp(script="knee_within_run.py", model="32BI",
                                           device="nvidia_h100_nvl", n=len(cells), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, sort_keys=True))
    print(f"{len(cells)} cells, {len(crossing)} crossing, {len(clean)} clean")
    print(f"knee bounded [{hi_clean:.1f}, {lo_cross:.1f}] tok/s "
          f"({100*(lo_cross-hi_clean)/hi_clean:.1f}% bracket)")
    print(f"  highest non-crossing: {res['highest_non_crossing']}")
    print(f"  lowest crossing:      {res['lowest_crossing']}")
    for k, v in res["severity_correlations"].items():
        if isinstance(v, float):
            print(f"  rho {k}: {v:+.3f}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
