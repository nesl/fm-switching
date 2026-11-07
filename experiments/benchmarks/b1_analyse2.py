"""StudyB1 analysis, revision 2 (2026-11-06).

Changes from b1_analyse_flash.py:
  - HERBench excluded (user decision; its rows are kept on disk, see report s13).
  - RTV-Bench Instruct HISTORY remainder rows merged in.
  - The corrected grey control (StudyB1-grey2) replaces the invalid one, and the grey
    accuracy is reported BESIDE every contrast as the no-visual-information reference,
    together with the guessing floor, the majority-letter baseline and the always-A baseline.

Primary accuracy counts unparsed, empty and truncated as wrong. Intervals resample VIDEOS.
"""
import gzip, json, random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/pragya/Desktop/FM-switching")
OUT = ROOT / "results/benchmarks/study_b1_flash"
IDX = OUT / "index"
DATASETS = ("rtv_bench", "ovo_bench", "streaming_bench")
EXCLUDED = ("herbench",)
B, SEED = 2000, 0


def mean(v):
    return sum(v) / len(v) if v else float("nan")


def pct(v, q):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, int(q * len(s)))]


def boot_ci(by_video, stat=mean, b=B, seed=SEED):
    keys = list(by_video)
    if len(keys) < 2:
        return (None, None)
    rnd = random.Random(seed)
    pts = []
    for _ in range(b):
        vals = []
        for _ in keys:
            vals.extend(by_video[keys[rnd.randrange(len(keys))]])
        if vals:
            pts.append(stat(vals))
    if not pts:
        return (None, None)
    pts.sort()
    return (round(pts[int(0.025 * len(pts))], 4),
            round(pts[min(len(pts) - 1, int(0.975 * len(pts)))], 4))


def load_index():
    idx, elig = {}, defaultdict(set)
    for name in DATASETS:
        for line in open(IDX / f"{name}.jsonl"):
            r = json.loads(line)
            idx[r["qid"]] = r
            for m in r["mode_set"]:
                elig[(r["dataset"], r["task"], m)].add(r["qid"])
                elig[(r["dataset"], "ALL", m)].add(r["qid"])
    return idx, elig


def read(globpat):
    rows = []
    for p in sorted(OUT.glob(globpat)):
        with gzip.open(p, "rt") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def primary(rows):
    for r in rows:
        r["correct_lenient"] = bool(r["correct"])
        r["correct"] = bool(r["correct"]) and not (
            r["unparsed"] or r["empty"] or r["truncated"])
    return rows


def floor_of(q):
    if q["answer_kind"] == "letter":
        n = len(q.get("options") or {})
        return 1.0 / n if n else None
    if q["answer_kind"] == "yesno":
        return 0.5
    return None


def main():
    idx, elig = load_index()

    orig = read("model_*/requests.part*.jsonl.gz")
    rem = read("grey2/model_*/requests.part*.jsonl.gz")

    excluded_rows = [r for r in orig if r.get("dataset") in EXCLUDED]
    real = [r for r in orig
            if "error" not in r and not r.get("grey") and r.get("dataset") in DATASETS]
    real += [r for r in rem
             if "error" not in r and not r.get("grey") and r.get("study") == "rtv_remainder"]
    grey2 = [r for r in rem if "error" not in r and r.get("grey")]
    errors = [r for r in orig + rem if "error" in r]
    primary(real)
    primary(grey2)

    # grey reference per (dataset, input, model, arm) plus its three baselines
    greytab, greyref = [], {}
    gb = defaultdict(list)
    for r in grey2:
        gb[(r["dataset"], r["mode"], r["model"], r["arm"])].append(r)
    for k in sorted(gb):
        items = gb[k]
        qs = [idx[r["qid"]] for r in items]
        golds = Counter(q["gold"] for q in qs)
        maj = max(golds.values()) / len(qs)
        alwaysA = golds.get("A", 0) / len(qs)
        floors = [f for f in (floor_of(q) for q in qs) if f is not None]
        by_video = defaultdict(list)
        for r in items:
            by_video[r["video_key"]].append(1.0 if r["correct"] else 0.0)
        acc = mean([1.0 if r["correct"] else 0.0 for r in items])
        lo, hi = boot_ci(by_video)
        greyref[k] = acc
        greytab.append({
            "dataset": k[0], "input": k[1], "model": k[2], "arm": k[3], "n": len(items),
            "grey_accuracy": round(acc, 4), "ci95_lo": lo, "ci95_hi": hi,
            "guessing_floor": round(mean(floors), 4) if floors else None,
            "majority_letter_baseline": round(maj, 4),
            "always_A_baseline": round(alwaysA, 4),
            "pred_dist": dict(Counter(r["pred"] for r in items)),
            "gold_dist": dict(golds),
            "distinct_prompt_sha256": len({r["prompt_sha256"] for r in items}),
            "unparsed_rate": round(mean([1.0 if r["unparsed"] else 0.0 for r in items]), 4),
            "truncated_rate": round(mean([1.0 if r["truncated"] else 0.0 for r in items]), 4),
            "gen_tok_p50": pct([r["gen_tokens"] for r in items], 0.5),
        })

    cells = defaultdict(list)
    for r in real:
        q = idx.get(r["qid"])
        if q is None:
            continue
        for task in (q["task"], "ALL"):
            cells[(r["dataset"], task, r["mode"], r["model"], r["arm"])].append((r, q))

    table = []
    for key in sorted(cells):
        ds, task, mode, model, arm = key
        items = cells[key]
        by_video = defaultdict(list)
        for r, q in items:
            by_video[r["video_key"]].append(1.0 if r["correct"] else 0.0)
        lo, hi = boot_ci(by_video)
        floors = [f for f in (floor_of(q) for _, q in items) if f is not None]
        gen = [r["gen_tokens"] for r, _ in items]
        denom = len(elig[(ds, task, mode)])
        g = greyref.get((ds, mode, model, arm))
        acc = mean([1.0 if r["correct"] else 0.0 for r, _ in items])
        table.append({
            "dataset": ds, "task": task, "input": mode, "model": model, "arm": arm,
            "n": len(items), "eligible": denom,
            "coverage": round(len(items) / denom, 4) if denom else None,
            "videos": len(by_video),
            "guessing_floor": round(mean(floors), 4) if floors else None,
            "grey_reference": round(g, 4) if g is not None else None,
            "accuracy": round(acc, 4), "ci95_lo": lo, "ci95_hi": hi,
            "accuracy_minus_grey": round(acc - g, 4) if g is not None else None,
            "truncated_rate": round(mean([1.0 if r["truncated"] else 0.0 for r, _ in items]), 4),
            "unparsed_rate": round(mean([1.0 if r["unparsed"] else 0.0 for r, _ in items]), 4),
            "empty_rate": round(mean([1.0 if r["empty"] else 0.0 for r, _ in items]), 4),
            "gen_tok_p50": pct(gen, 0.50), "gen_tok_p90": pct(gen, 0.90),
            "gen_tok_max": max(gen) if gen else None,
        })

    def paired(field, a_val, b_val, label, by_task=False):
        out = []
        buckets = defaultdict(dict)
        for r in real:
            q = idx.get(r["qid"])
            if q is None:
                continue
            held = r["mode"] if field == "arm" else r["arm"]
            tk = q["task"] if by_task else "ALL"
            buckets[((r["model"], r["dataset"], tk, held), r["qid"])][r[field]] = r
        agg = defaultdict(list)
        for (grp, _qid), d in buckets.items():
            if a_val in d and b_val in d:
                agg[grp].append((d[a_val], d[b_val]))
        for grp in sorted(agg):
            pairs = agg[grp]
            model, ds, tk, held = grp
            by_video = defaultdict(list)
            for ra, rb in pairs:
                by_video[ra["video_key"]].append(
                    (1.0 if ra["correct"] else 0.0) - (1.0 if rb["correct"] else 0.0))
            diffs = [x for v in by_video.values() for x in v]
            lo, hi = boot_ci(by_video)
            flips = sum(1 for ra, rb in pairs if ra["correct"] != rb["correct"])
            mode_for_grey = held if field == "arm" else a_val
            arm_a = a_val if field == "arm" else held
            arm_b = b_val if field == "arm" else held
            row = {
                "contrast": label, "model": model, "dataset": ds, "task": tk, "held": held,
                "n_matched": len(pairs), "videos": len(by_video),
                f"acc_{a_val}": round(mean([1.0 if ra["correct"] else 0.0 for ra, _ in pairs]), 4),
                f"acc_{b_val}": round(mean([1.0 if rb["correct"] else 0.0 for _, rb in pairs]), 4),
                "diff": round(mean(diffs), 4), "ci95_lo": lo, "ci95_hi": hi,
                "flips": flips, "flip_rate": round(flips / len(pairs), 4),
                f"grey_{a_val}": greyref.get((ds, mode_for_grey, model, arm_a)),
                f"grey_{b_val}": greyref.get((ds, b_val if field == "mode" else mode_for_grey,
                                              model, arm_b)),
                f"gen_tok_p50_{a_val}": pct([ra["gen_tokens"] for ra, _ in pairs], 0.5),
                f"gen_tok_p50_{b_val}": pct([rb["gen_tokens"] for _, rb in pairs], 0.5),
            }
            for kk in (f"grey_{a_val}", f"grey_{b_val}"):
                if row[kk] is not None:
                    row[kk] = round(row[kk], 4)
            out.append(row)
        return out

    contrasts = (paired("arm", "Thinking", "Instruct", "Thinking-Instruct")
                 + paired("arm", "Thinking", "Instruct", "Thinking-Instruct by task", True)
                 + paired("mode", "HISTORY", "RECENT",
                          "HISTORY-RECENT (frame count 37 vs 9)"))

    res = {
        "revision": 2, "date": "2026-11-06",
        "scope": {"datasets": list(DATASETS), "excluded": list(EXCLUDED),
                  "excluded_rows_kept_on_disk": len(excluded_rows),
                  "note": "HERBench removed from StudyB1 by user decision 2026-11-06; "
                          "rows kept, excluded from all analysis."},
        "n_real": len(real), "n_grey2": len(grey2), "n_errors": len(errors),
        "cells": table, "grey": greytab, "contrasts": contrasts,
    }
    (OUT / "analysis_rev2.json").write_text(json.dumps(res, indent=1))
    print(f"real={len(real)} grey2={len(grey2)} excluded_kept={len(excluded_rows)} "
          f"cells={len(table)} grey_cells={len(greytab)} contrasts={len(contrasts)}")


if __name__ == "__main__":
    main()
