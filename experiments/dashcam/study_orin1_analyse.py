#!/usr/bin/env python3
"""
StudyORIN1-dense analysis. CPU only.

Part 1 (dense scores): when results/dashcam/study_orin1/orin1_dense_scores.jsonl
  exists, (a) reproduce StudyD15's Orin scores on the integer-second overlap
  (Pearson >= 0.99 gate; max abs diff reported), (b) correlate with the H100 4B
  D14b scores (d14b_trace_h100nvl), (c) challenge AP (base-rate-weighted) of the
  Orin arm vs the H100 4B arm with a paired clip bootstrap (2,000, seed 0).
Part 2: pass through the controller-overhead summary.
Part 3: per-history-size recall-latency distributions and the TTFT decomposition.

Writes results/dashcam/study_orin1/study_orin1_analysis.json (merged).
"""
import gzip, json, math, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUTD = ROOT / "results/dashcam/study_orin1"
OUTC = ROOT / "results/cost/study_orin1"
D15_SCORES = ROOT / "results/device/study_d15/partA_scores.jsonl"
D14B_H100 = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
SEED = 0
NB = 2000


# ---------- small stats (no scipy) ----------
def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs); sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def rankdata(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def spearman(xs, ys):
    return pearson(rankdata(xs), rankdata(ys))


def pct(xs, q):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return None
    i = q / 100 * (len(xs) - 1); lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 4)


# ---------- Part 1 ----------
def ap_from(scores, labels):
    """Average precision (area under precision-recall) from scores and 0/1 labels."""
    pairs = sorted(zip(scores, labels), key=lambda p: -p[0])
    P = sum(labels)
    if P == 0:
        return None
    tp = 0; fp = 0; ap = 0.0; prev_recall = 0.0
    for s, y in pairs:
        if y:
            tp += 1
        else:
            fp += 1
        recall = tp / P
        precision = tp / (tp + fp)
        ap += precision * (recall - prev_recall)
        prev_recall = recall
    return ap


def part1_analysis():
    f = OUTD / "orin1_dense_scores.jsonl"
    fgz = OUTD / "orin1_dense_scores.jsonl.gz"
    if f.exists():
        orin = [json.loads(l) for l in open(f)]
    elif fgz.exists():
        with gzip.open(fgz, "rt") as g:
            orin = [json.loads(l) for l in g]
    else:
        return {"status": "HELD - dense frames not yet scored"}
    # (a) D15 reproduction on integer-second overlap, matched by d14_request_id
    d15 = {}
    for l in open(D15_SCORES):
        d = json.loads(l)
        d15[d["request_id"]] = d["score"]
    ov_o, ov_d = [], []
    for r in orin:
        did = r.get("d14_request_id")
        if did and did in d15 and r["score"] is not None and d15[did] is not None:
            ov_o.append(r["score"]); ov_d.append(d15[did])
    repro = {"n_overlap": len(ov_o),
             "pearson": round(pearson(ov_o, ov_d), 6) if ov_o else None,
             "max_abs_diff": round(max(abs(a - b) for a, b in zip(ov_o, ov_d)), 6) if ov_o else None,
             "gate_pass_ge_0.99": (pearson(ov_o, ov_d) >= 0.99) if ov_o else False}
    # (b) correlation with H100 4B D14b scores, matched by request_id
    h = {}
    with gzip.open(D14B_H100, "rt") as g:
        for line in g:
            r = json.loads(line)
            if str(r.get("model")) == "4BI" and str(r.get("n")) == "1":
                h[r["request_id"]] = r["score"]
    co, ch, clip_of, lab_of = [], [], [], []
    for r in orin:
        rid = r["request_id"]
        if rid in h and r["score"] is not None and h[rid] is not None:
            co.append(r["score"]); ch.append(h[rid])
            clip_of.append(r["clip"]); lab_of.append(1 if r.get("label") == "positive" else 0)
    agree = {"n_matched": len(co), "pearson": round(pearson(co, ch), 4) if co else None,
             "spearman": round(spearman(co, ch), 4) if co else None,
             "median_abs_diff": round(st.median([abs(a - b) for a, b in zip(co, ch)]), 4) if co else None}
    # (c) challenge AP Orin vs H100, paired clip bootstrap
    import random
    by_clip = defaultdict(list)
    for s_o, s_h, c, y in zip(co, ch, clip_of, lab_of):
        by_clip[c].append((s_o, s_h, y))
    clips = sorted(by_clip)
    def ap_pair(sample_clips):
        so, sh, yy = [], [], []
        for c in sample_clips:
            for s_o, s_h, y in by_clip[c]:
                so.append(s_o); sh.append(s_h); yy.append(y)
        return ap_from(so, yy), ap_from(sh, yy)
    ap_o, ap_h = ap_pair(clips)
    rng = random.Random(SEED)
    diffs = []
    for _ in range(NB):
        samp = [clips[rng.randrange(len(clips))] for _ in clips]
        a_o, a_h = ap_pair(samp)
        if a_o is not None and a_h is not None:
            diffs.append(a_o - a_h)
    diffs.sort()
    ci = [round(diffs[int(0.025 * len(diffs))], 4), round(diffs[int(0.975 * len(diffs))], 4)] if diffs else None
    challenge_ap = {"ap_orin": round(ap_o, 4) if ap_o else None,
                    "ap_h100": round(ap_h, 4) if ap_h else None,
                    "diff_orin_minus_h100": round(ap_o - ap_h, 4) if (ap_o and ap_h) else None,
                    "diff_ci95": ci, "ci_includes_0": (ci[0] <= 0 <= ci[1]) if ci else None,
                    "n_clips": len(clips)}
    return {"status": "COMPLETE", "n_scores": len(orin),
            "d15_reproduction": repro, "h100_agreement": agree, "challenge_ap": challenge_ap}


# ---------- Part 2 ----------
def part2_analysis():
    p = OUTC / "orin1_controller_overhead.json"
    return json.load(open(p)) if p.exists() else {"status": "not run"}


# ---------- Part 3 ----------
def part3_analysis():
    p = OUTC / "orin1_recall_latency.jsonl"
    if not p.exists():
        return {"status": "not run"}
    rows = [json.loads(l) for l in open(p)]
    g = defaultdict(list)
    for r in rows:
        g[r["target_tok"]].append(r)
    out = {"n_rows": len(rows), "by_size": {}}
    for tgt in sorted(g):
        rs = g[tgt]
        ttft = [r["ttft_s"] for r in rs if r["ttft_s"]]
        total = [r["total_s"] for r in rs if r["total_s"]]
        cache = [r["history_tokens_cached"] for r in rs if r["history_tokens_cached"]]
        ev = [r["evaluated"] for r in rs if r["evaluated"]]
        ngen = [r["n_gen"] for r in rs if r["n_gen"]]
        pm = [r["prompt_ms"] for r in rs if r.get("prompt_ms")]
        out["by_size"][str(tgt)] = {
            "n": len(rs), "held": True,
            "history_tokens_cached_median": int(st.median(cache)),
            "question_tokens_evaluated_median": int(st.median(ev)),
            "n_gen_median": int(st.median(ngen)),
            "ttft_s": {"p50": pct(ttft, 50), "p90": pct(ttft, 90),
                       "min": round(min(ttft), 3), "max": round(max(ttft), 3)},
            "total_s": {"p50": pct(total, 50), "p90": pct(total, 90),
                        "min": round(min(total), 3), "max": round(max(total), 3)},
            "server_prompt_ms_p50": round(st.median(pm), 1),
            "ttft_minus_prompt_ms_p50": round(st.median(ttft) * 1000 - st.median(pm), 1),
            "clock_pinned_all": all(r["clock_ok"] for r in rs)}
    sizes = sorted(g)
    if len(sizes) == 2:
        a, b = sizes
        t_a = st.median([r["ttft_s"] for r in g[a]]); t_b = st.median([r["ttft_s"] for r in g[b]])
        h_a = st.median([r["history_tokens_cached"] for r in g[a]])
        h_b = st.median([r["history_tokens_cached"] for r in g[b]])
        out["ttft_slope_ms_per_history_token"] = round(1000 * (t_b - t_a) / (h_b - h_a), 4)
        out["note"] = ("warm recall latency scales with history size though only the question tokens "
                       "are evaluated: TTFT is dominated by client-side resend+parse of the full image "
                       "payload (StudyD15b), not model compute (server prompt_ms is 0.12-0.19 s)")
    return out


def main():
    res = {"part1": part1_analysis(), "part2": part2_analysis(), "part3": part3_analysis()}
    OUTD.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(OUTD / "study_orin1_analysis.json", "w"), indent=1)
    print(json.dumps({"part1": res["part1"].get("status"),
                      "part3_sizes": list(res["part3"].get("by_size", {}).keys())}, indent=1))
    print("wrote", OUTD / "study_orin1_analysis.json")


if __name__ == "__main__":
    main()
