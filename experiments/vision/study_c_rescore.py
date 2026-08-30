#!/usr/bin/env python3
"""
Study C re-scoring: tolerance-based accuracy, error distribution, Spearman correlation.
CPU only. No model loading. No new inference.
"""
import csv
import math
import json
from collections import defaultdict
import statistics

TRIALS_CSV = "results/vision/study_c/study_c_trials.csv"
REPORT_PATH = "reports/study_c_rescore.md"
RESULTS_JSON = "results/vision/study_c/study_c_rescore.json"
PLOTS_DIR = "figures/vision"

LEVELS = ["L1", "L2", "L3", "L4"]
MODELS = ["qwenvl3b", "qwenvl7b"]
MODES = ["direct", "stepwise"]
LEVEL_BINS = {"L1": (1, 1), "L2": (2, 3), "L3": (4, 7), "L4": (8, 999)}

# Original exact-match accuracies from study_c_difficulty.md for sanity check
ORIGINAL_ACC = {
    ("qwenvl3b", "direct",   "L1"): 0.9667,
    ("qwenvl3b", "direct",   "L2"): 0.7000,
    ("qwenvl3b", "direct",   "L3"): 0.2333,
    ("qwenvl3b", "direct",   "L4"): 0.0667,
    ("qwenvl3b", "stepwise", "L1"): 0.8214,
    ("qwenvl3b", "stepwise", "L2"): 0.5862,
    ("qwenvl3b", "stepwise", "L3"): 0.3000,
    ("qwenvl3b", "stepwise", "L4"): 0.0333,
    ("qwenvl7b", "direct",   "L1"): 0.9333,
    ("qwenvl7b", "direct",   "L2"): 0.7000,
    ("qwenvl7b", "direct",   "L3"): 0.3667,
    ("qwenvl7b", "direct",   "L4"): 0.1333,
    ("qwenvl7b", "stepwise", "L1"): 0.9667,
    ("qwenvl7b", "stepwise", "L2"): 0.7000,
    ("qwenvl7b", "stepwise", "L3"): 0.1667,
    ("qwenvl7b", "stepwise", "L4"): 0.0000,
}


def spearman(xs, ys):
    """Spearman rank correlation."""
    n = len(xs)
    if n < 2:
        return float("nan")

    def rank(arr):
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n and arr[sorted_idx[j]] == arr[sorted_idx[i]]:
                j += 1
            avg = (i + j - 1) / 2.0 + 1
            for k in range(i, j):
                ranks[sorted_idx[k]] = avg
            i = j
        return ranks

    rx = rank(xs)
    ry = rank(ys)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - 6 * d2 / (n * (n * n - 1))


def load_trials():
    rows = []
    with open(TRIALS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_row(row):
    gt = int(row["n_persons_gt"])
    parse_status = row["parse_status"]
    parsed_raw = row["parsed_answer"]
    budget_hit = row["budget_hit"].strip().lower() == "true"

    if parse_status in ("ok", "fallback_last_number") and parsed_raw not in ("", "None", "nan"):
        try:
            parsed = int(float(parsed_raw))
        except ValueError:
            parsed = None
    else:
        parsed = None

    return {
        "model": row["model"],
        "level": row["level"],
        "mode": row["mode"],
        "rep": int(row["rep"]),
        "image_id": row["image_id"],
        "gt": gt,
        "parsed": parsed,
        "parse_status": parse_status,
        "budget_hit": budget_hit,
        "n_generated": int(row["n_generated"]),
        "latency_ms": float(row["latency_ms"]),
    }


def compute_cell_stats(trials):
    """Compute all metrics for a list of trials in one cell."""
    n_total = len(trials)
    parseable = [t for t in trials if t["parsed"] is not None]
    n_unparseable = n_total - len(parseable)

    if not parseable:
        return {
            "n_total": n_total,
            "n_parseable": 0,
            "n_unparseable": n_unparseable,
            "exact_conservative": 0.0,
            "exact_restricted": float("nan"),
            "within1_conservative": 0.0,
            "within1_restricted": float("nan"),
            "within2_conservative": 0.0,
            "within2_restricted": float("nan"),
            "reltol25_conservative": 0.0,
            "reltol25_restricted": float("nan"),
            "mean_error": float("nan"),
            "median_error": float("nan"),
            "mean_abs_error": float("nan"),
            "median_abs_error": float("nan"),
            "spearman": float("nan"),
            "gt_values": [],
            "parsed_values": [],
            "errors": [],
        }

    n_p = len(parseable)
    gts = [t["gt"] for t in parseable]
    preds = [t["parsed"] for t in parseable]
    errors = [p - g for p, g in zip(preds, gts)]
    abs_errors = [abs(e) for e in errors]

    exact_hits = sum(1 for e in errors if e == 0)
    w1_hits = sum(1 for e in errors if abs(e) <= 1)
    w2_hits = sum(1 for e in errors if abs(e) <= 2)
    rt25_hits = sum(1 for p, g in zip(preds, gts) if abs(p - g) / max(g, 1) <= 0.25)

    return {
        "n_total": n_total,
        "n_parseable": n_p,
        "n_unparseable": n_unparseable,
        "exact_conservative": exact_hits / n_total,
        "exact_restricted": exact_hits / n_p,
        "within1_conservative": w1_hits / n_total,
        "within1_restricted": w1_hits / n_p,
        "within2_conservative": w2_hits / n_total,
        "within2_restricted": w2_hits / n_p,
        "reltol25_conservative": rt25_hits / n_total,
        "reltol25_restricted": rt25_hits / n_p,
        "mean_error": sum(errors) / n_p,
        "median_error": statistics.median(errors),
        "mean_abs_error": sum(abs_errors) / n_p,
        "median_abs_error": statistics.median(abs_errors),
        "spearman": spearman(gts, preds),
        "gt_values": gts,
        "parsed_values": preds,
        "errors": errors,
    }


def main():
    rows = load_trials()

    # Sanity check 1: row count
    assert len(rows) == 1440, f"Expected 1440 rows, got {len(rows)}"
    print("SC1 PASS: 1440 rows")

    # Parse all rows
    trials = [parse_row(r) for r in rows]

    # Sanity check 2: GT bins
    bin_fails = []
    for t in trials:
        lo, hi = LEVEL_BINS[t["level"]]
        if not (lo <= t["gt"] <= hi):
            bin_fails.append(t)
    if bin_fails:
        print(f"SC3 FAIL: {len(bin_fails)} rows with gt outside level bin")
        for t in bin_fails[:5]:
            print(f"  {t}")
    else:
        print("SC3 PASS: all GT values within level bin definitions")

    # Sanity check 3: every row in exactly one cell
    cell_counts = defaultdict(int)
    for t in trials:
        key = (t["model"], t["mode"], t["level"])
        cell_counts[key] += 1
    expected_keys = {(m, mo, l) for m in MODELS for mo in MODES for l in LEVELS}
    missing = expected_keys - set(cell_counts.keys())
    extra = set(cell_counts.keys()) - expected_keys
    if missing:
        print(f"SC4 FAIL: missing cells: {missing}")
    elif extra:
        print(f"SC4 FAIL: unexpected cells: {extra}")
    else:
        print(f"SC4 PASS: all 16 cells present, counts: {sorted(set(cell_counts.values()))}")

    # Compute per-cell stats
    cells = {}
    for model in MODELS:
        for mode in MODES:
            for level in LEVELS:
                key = (model, mode, level)
                cell_trials = [t for t in trials if t["model"] == model and t["mode"] == mode and t["level"] == level]
                cells[key] = compute_cell_stats(cell_trials)

    # Sanity check 2: exact-match replication
    # Original report claimed conservative scoring but used restricted for cells with
    # parse_status='unparseable' rows (fallback_last_number rows were included in denominator).
    # Compare against restricted denominator for cells where original==restricted, else conservative.
    print("\n=== Sanity check: exact-match replication ===")
    sc2_pass = True
    sc2_notes = []
    for key, orig in ORIGINAL_ACC.items():
        s = cells[key]
        cons = s["exact_conservative"]
        rest = s["exact_restricted"]
        # choose whichever matches within tolerance
        close_cons = abs(cons - orig) < 0.002
        close_rest = (not math.isnan(rest)) and abs(rest - orig) < 0.002
        if close_cons:
            match = "conservative"
            diff = abs(cons - orig)
        elif close_rest:
            match = "restricted"
            diff = abs(rest - orig)
            sc2_notes.append(f"  NOTE: {key} — original used restricted denominator (n_unparseable={s['n_unparseable']})")
        else:
            match = "FAIL"
            diff = min(abs(cons - orig), abs(rest - orig) if not math.isnan(rest) else 999)
            print(f"SC2 FAIL: {key}: orig={orig:.4f} cons={cons:.4f} rest={rest:.4f}")
            sc2_pass = False
    if sc2_pass:
        print("SC2 PASS: recomputed exact-match matches original for all 16 cells")
        for note in sc2_notes:
            print(note)
        if sc2_notes:
            print("  Interpretation: the original script used restricted denominator for cells with")
            print("  parse_status='unparseable' rows, contrary to the report claim of conservative scoring.")

    # Print full metric table
    print("\n=== Per-cell metric table ===")
    header = f"{'model':12} {'mode':10} {'lvl':4} {'n':4} {'unp':4} | {'ex_c':6} {'w1_c':6} {'w2_c':6} {'rt25':6} | {'me':7} {'mae':6} {'sp':6}"
    print(header)
    print("-" * len(header))
    for model in MODELS:
        for mode in MODES:
            for level in LEVELS:
                s = cells[(model, mode, level)]
                me = s["mean_error"]
                mae = s["mean_abs_error"]
                sp = s["spearman"]
                print(f"{model:12} {mode:10} {level:4} {s['n_total']:4} {s['n_unparseable']:4} | "
                      f"{s['exact_conservative']:6.3f} {s['within1_conservative']:6.3f} {s['within2_conservative']:6.3f} {s['reltol25_conservative']:6.3f} | "
                      f"{me:7.2f} {mae:6.2f} {sp:6.3f}")

    # Gap analysis by tolerance
    print("\n=== 7B-minus-3B gap by tolerance and level ===")
    print(f"{'mode':10} {'lvl':4} | {'ex_gap':8} {'w1_gap':8} {'w2_gap':8} {'rt25_gap':9}")
    for mode in MODES:
        for level in LEVELS:
            s3 = cells[("qwenvl3b", mode, level)]
            s7 = cells[("qwenvl7b", mode, level)]
            print(f"{mode:10} {level:4} | "
                  f"{s7['exact_conservative']-s3['exact_conservative']:+8.3f} "
                  f"{s7['within1_conservative']-s3['within1_conservative']:+8.3f} "
                  f"{s7['within2_conservative']-s3['within2_conservative']:+8.3f} "
                  f"{s7['reltol25_conservative']-s3['reltol25_conservative']:+9.3f}")

    # Signed error analysis
    print("\n=== Signed error by level ===")
    print(f"{'model':12} {'mode':10} {'lvl':4} | {'mean_err':9} {'med_err':9} | direction")
    for model in MODELS:
        for mode in MODES:
            for level in LEVELS:
                s = cells[(model, mode, level)]
                me = s["mean_error"]
                med = s["median_error"]
                if abs(me) < 0.3:
                    direction = "unbiased"
                elif me < 0:
                    direction = f"undercount ({me:.1f})"
                else:
                    direction = f"overcount (+{me:.1f})"
                print(f"{model:12} {mode:10} {level:4} | {me:9.2f} {med:9.2f} | {direction}")

    # Spearman summary
    print("\n=== Spearman correlation by level ===")
    print(f"{'model':12} {'mode':10} {'L1':6} {'L2':6} {'L3':6} {'L4':6}")
    for model in MODELS:
        for mode in MODES:
            sps = [f"{cells[(model,mode,l)]['spearman']:6.3f}" for l in LEVELS]
            print(f"{model:12} {mode:10} {' '.join(sps)}")

    # Pooled Spearman per (model, mode)
    print("\n=== Pooled Spearman per (model, mode) ===")
    for model in MODELS:
        for mode in MODES:
            all_gt, all_pred = [], []
            for level in LEVELS:
                s = cells[(model, mode, level)]
                all_gt.extend(s["gt_values"])
                all_pred.extend(s["parsed_values"])
            sp = spearman(all_gt, all_pred)
            print(f"{model:12} {mode:10} pooled_spearman={sp:.4f} n={len(all_gt)}")

    # Save results JSON
    results = {}
    for key, s in cells.items():
        k = "|".join(key)
        results[k] = {
            k2: v for k2, v in s.items()
            if k2 not in ("gt_values", "parsed_values", "errors")
        }
    import json
    with open(RESULTS_JSON, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {RESULTS_JSON}")

    return cells, trials


if __name__ == "__main__":
    cells, trials = main()
