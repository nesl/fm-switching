"""StudyB1-flash analysis: descriptive capability pass, no threshold or policy fitting.

Primary accuracy counts unparsed, empty and truncated responses as wrong
(task spec), and reports each of those rates separately alongside.
Confidence intervals resample VIDEOS, not questions, because questions from
one video share frames and are not independent.
"""
import gzip, json, math, random, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/home/pragya/Desktop/FM-switching")
OUT = ROOT / "results/benchmarks/study_b1_flash"
IDX = OUT / "index"
B = 2000
SEED = 0


def load_index():
    idx, elig = {}, defaultdict(set)
    for name in ("rtv_bench", "ovo_bench", "herbench", "streaming_bench"):
        with open(IDX / f"{name}.jsonl") as f:
            for line in f:
                r = json.loads(line)
                idx[r["qid"]] = r
                for m in r["mode_set"]:
                    elig[(r["dataset"], r["task"], m)].add(r["qid"])
                    elig[(r["dataset"], "ALL", m)].add(r["qid"])
    return idx, elig


def load_rows():
    rows = []
    for mdir in ("model_4B", "model_8B"):
        for p in sorted((OUT / mdir).glob("requests.part*.jsonl.gz")):
            with gzip.open(p, "rt") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))
    return rows


def floor_of(r):
    """Guessing floor for one indexed question."""
    if r["answer_kind"] == "letter":
        n = len(r.get("options") or {})
        return 1.0 / n if n else None
    if r["answer_kind"] == "yesno":
        return 0.5
    return None  # open-ended count: no finite option set, floor undefined


def boot_ci(by_video, stat, b=B, seed=SEED):
    """Cluster bootstrap over videos. by_video: {video: [values]}."""
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
    lo = pts[int(0.025 * len(pts))]
    hi = pts[min(len(pts) - 1, int(0.975 * len(pts)))]
    return (round(lo, 4), round(hi, 4))


def mean(v):
    return sum(v) / len(v) if v else float("nan")


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def main():
    idx, elig = load_index()
    rows = load_rows()
    # Rows carrying "error" never reached the model (frame decode failed), so they
    # are a coverage gap, not a wrong answer: excluded from accuracy, reported as errors.
    errors = [r for r in rows if "error" in r]
    ok = [r for r in rows if "error" not in r]
    real = [r for r in ok if not r["grey"]]
    grey = [r for r in ok if r["grey"]]

    # Task spec: unparsed, empty and truncated count as WRONG in the primary accuracy,
    # whatever the parser recovered from the text. The parser's own verdict is kept as
    # correct_lenient so the two can be compared instead of silently diverging.
    for r in real + grey:
        r["correct_lenient"] = bool(r["correct"])
        r["correct"] = bool(r["correct"]) and not (r["unparsed"] or r["empty"] or r["truncated"])
    n_demoted = sum(1 for r in real if r["correct_lenient"] and not r["correct"])

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
        acc = mean([1.0 if r["correct"] else 0.0 for r, _ in items])
        lo, hi = boot_ci(by_video, mean)
        floors = [f for f in (floor_of(q) for _, q in items) if f is not None]
        gen = [r["gen_tokens"] for r, _ in items]
        denom = len(elig[(ds, task, mode)])
        table.append({
            "dataset": ds, "task": task, "input": mode, "model": model, "arm": arm,
            "n": len(items), "eligible": denom,
            "coverage": round(len(items) / denom, 4) if denom else None,
            "videos": len(by_video),
            "guessing_floor": round(mean(floors), 4) if floors else None,
            "floor_defined_frac": round(len(floors) / len(items), 4),
            "accuracy": round(acc, 4), "ci95_lo": lo, "ci95_hi": hi,
            "truncated_rate": round(mean([1.0 if r["truncated"] else 0.0 for r, _ in items]), 4),
            "unparsed_rate": round(mean([1.0 if r["unparsed"] else 0.0 for r, _ in items]), 4),
            "empty_rate": round(mean([1.0 if r["empty"] else 0.0 for r, _ in items]), 4),
            "accuracy_lenient": round(mean([1.0 if r["correct_lenient"] else 0.0 for r, _ in items]), 4),
            "gen_tok_p50": pct(gen, 0.50), "gen_tok_p90": pct(gen, 0.90), "gen_tok_max": max(gen),
        })

    def paired(split_key, a_val, b_val, label):
        """Matched-question contrast; bootstrap by video. split_key indexes the row field."""
        out = []
        buckets = defaultdict(dict)
        for r in real:
            q = idx.get(r["qid"])
            if q is None:
                continue
            fixed = tuple(r[f] for f in ("model", "dataset") if True)
            grp = (r["model"], r["dataset"],
                   r["mode"] if split_key == "arm" else r["arm"])
            buckets[(grp, r["qid"])][r[split_key]] = r
        agg = defaultdict(list)
        for (grp, qid), d in buckets.items():
            if a_val in d and b_val in d:
                agg[grp].append((d[a_val], d[b_val]))
        for grp in sorted(agg):
            pairs = agg[grp]
            by_video = defaultdict(list)
            for ra, rb in pairs:
                by_video[ra["video_key"]].append(
                    (1.0 if ra["correct"] else 0.0) - (1.0 if rb["correct"] else 0.0))
            diffs = [d for v in by_video.values() for d in v]
            lo, hi = boot_ci(by_video, mean)
            flips = sum(1 for ra, rb in pairs if ra["correct"] != rb["correct"])
            out.append({
                "contrast": label, "model": grp[0], "dataset": grp[1], "held": grp[2],
                "n_matched": len(pairs), "videos": len(by_video),
                f"acc_{a_val}": round(mean([1.0 if ra["correct"] else 0.0 for ra, _ in pairs]), 4),
                f"acc_{b_val}": round(mean([1.0 if rb["correct"] else 0.0 for _, rb in pairs]), 4),
                "diff": round(mean(diffs), 4), "ci95_lo": lo, "ci95_hi": hi,
                "flips": flips, "flip_rate": round(flips / len(pairs), 4),
                "agreement": round(1 - flips / len(pairs), 4),
                f"gen_tok_p50_{a_val}": pct([ra["gen_tokens"] for ra, _ in pairs], 0.5),
                f"gen_tok_p50_{b_val}": pct([rb["gen_tokens"] for _, rb in pairs], 0.5),
            })
        return out

    contrasts = paired("arm", "Thinking", "Instruct", "Thinking-Instruct")
    contrasts += paired("mode", "HISTORY", "RECENT", "HISTORY-RECENT (fixed frame count differs: 37 vs 9)")

    greyt = []
    gb = defaultdict(list)
    for r in grey:
        gb[(r["model"], r["arm"], r["mode"])].append(r)
    for k in sorted(gb):
        items = gb[k]
        dist = Counter(r["pred"] for r in items)
        greyt.append({
            "model": k[0], "arm": k[1], "input": k[2], "n": len(items),
            "accuracy": round(mean([1.0 if r["correct"] else 0.0 for r in items]), 4),
            "gold_dist": dict(Counter(r["gold"] for r in items)),
            "pred_dist": dict(dist),
            "unparsed_rate": round(mean([1.0 if r["unparsed"] else 0.0 for r in items]), 4),
            "truncated_rate": round(mean([1.0 if r["truncated"] else 0.0 for r in items]), 4),
            "gen_tok_p50": pct([r["gen_tokens"] for r in items], 0.5),
            "gen_tok_max": max(r["gen_tokens"] for r in items),
        })

    errt = [{"model": r["model"], "input": r["mode"], "dataset": r.get("dataset"),
             "qid": r["qid"], "error": r["error"]} for r in errors]
    res = {"cells": table, "contrasts": contrasts, "grey": greyt, "errors": errt,
           "n_rows": len(rows), "n_real": len(real), "n_grey": len(grey),
           "n_error": len(errors), "n_demoted_truncated_or_unparsed": n_demoted}
    (OUT / "analysis.json").write_text(json.dumps(res, indent=1))
    print(f"rows={len(rows)} real={len(real)} grey={len(grey)} cells={len(table)} contrasts={len(contrasts)}")


if __name__ == "__main__":
    main()
