#!/usr/bin/env python3
"""StudyACC2 analysis (CPU, server down): accuracy by representation with bootstrap CIs, overall and per split,
against StudyRH4's committed rc_accuracy table and StudyR1; HELPS / HURTS flows (D2 vs RECENT) by history-length
bucket including > 19.4k tokens; the same by category (exploratory); idle TTFT vs history tokens against the
committed cost curve. Writes results/sember/study_acc2/acc2_results.json."""
import json
import random
import statistics as S
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/sember/study_acc2"
for p in ("experiments/orchestration/baselines", "experiments/orchestration/sim", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
B = 10000
BUCKETS = [(0, 5000), (5000, 10000), (10000, 15000), (15000, 19400), (19400, 1e9)]


def boot(xs, seed=0):
    if not xs:
        return dict(n=0)
    import numpy as np                       # vectorised (same estimator: B resamples with replacement)
    a = np.asarray(xs, dtype=float)
    n = len(a)
    m = np.sort(a[np.random.default_rng(seed).integers(0, n, size=(B, n))].mean(axis=1)).tolist()
    return dict(n=n, acc=round(sum(xs) / n, 4), ci95=[round(m[int(0.025 * B)], 4), round(m[int(0.975 * B)], 4)])


def bucket(t):
    for lo, hi in BUCKETS:
        if lo <= t < hi:
            return f"{lo}-{int(hi) if hi < 1e8 else 'inf'}"


def flows(pairs):
    """pairs: (d2_correct, recent_correct). HELPS = D2 right and RECENT wrong; HURTS = the reverse."""
    n = len(pairs)
    h = sum(1 for a, b in pairs if a and not b)
    u = sum(1 for a, b in pairs if b and not a)
    return dict(n=n, helps=h, hurts=u, changes_pct=round(100 * (h + u) / n, 2) if n else None,
                helps_pct=round(100 * h / n, 2) if n else None, hurts_pct=round(100 * u / n, 2) if n else None,
                net_pp=round(100 * (h - u) / n, 2) if n else None, net_pp_ci95=net_ci(pairs))


def net_ci(pairs, seed=0):
    """Paired bootstrap of the net (helps - hurts) / n, in pp: resample questions, keep each pair intact."""
    import numpy as np
    if not pairs:
        return None
    d = np.asarray([(1 if a and not b else 0) - (1 if b and not a else 0) for a, b in pairs], dtype=float)
    m = np.sort(d[np.random.default_rng(seed).integers(0, len(d), size=(B, len(d)))].mean(axis=1))
    return [round(100 * m[int(0.025 * B)], 2), round(100 * m[int(0.975 * B)], 2)]


def main():
    rows = [json.loads(l) for l in open(OUT / "acc2_requests.jsonl")]
    bad = [r for r in rows if r["error"]]
    ok = [r for r in rows if not r["error"]]
    by = defaultdict(dict)
    for r in ok:
        if r["rep"] in ("D2", "RECENT"):
            by[r["question_id"]][r["rep"]] = r
    acc = {}
    for rep in ("D2", "RECENT", "D2-LIVE-TRACE"):
        rr = [r for r in ok if r["rep"] == rep]
        acc[rep] = dict(all=boot([1 if r["correct"] else 0 for r in rr]),
                        DEV=boot([1 if r["correct"] else 0 for r in rr if r["split"] == "DEV"]),
                        EVAL=boot([1 if r["correct"] else 0 for r in rr if r["split"] == "EVAL"]))
    # StudyR1 (K1 32B-I RICH capped, K3 RECENT) on the same questions
    import gzip
    r1 = [json.loads(l) for l in gzip.open(REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "rt")]
    r1k = defaultdict(dict)
    for r in r1:
        if r["mode"] == "batched":
            r1k[r["cell"]][r["question_id"]] = 1 if r["correct"] else 0
    split = {q: next(iter(v.values()))["split"] for q, v in by.items()}
    r1acc = {c: dict(all=boot(list(r1k[c].values())),
                     DEV=boot([v for q, v in r1k[c].items() if split.get(q) == "DEV"]),
                     EVAL=boot([v for q, v in r1k[c].items() if split.get(q) == "EVAL"])) for c in ("K1", "K3")}
    # flows by history bucket (D2 prompt tokens) and by category
    pairs_b, pairs_c, pairs_s = defaultdict(list), defaultdict(list), defaultdict(list)
    for q, v in by.items():
        if "D2" not in v or "RECENT" not in v:
            continue
        p = (v["D2"]["correct"], v["RECENT"]["correct"])
        pairs_b[bucket(v["D2"]["prompt_tokens"] or 0)].append(p)
        pairs_c[v["D2"]["category"]].append(p)
        pairs_s[v["D2"]["split"]].append(p)
        pairs_b["ALL"].append(p)
    fl_b = {k: flows(v) for k, v in pairs_b.items()}
    fl_c = {k: flows(v) for k, v in sorted(pairs_c.items())}
    fl_s = {k: flows(v) for k, v in pairs_s.items()}
    # long live-trace prompts vs RECENT of the same question
    lt = defaultdict(list)
    for r in ok:
        if r["rep"] == "D2-LIVE-TRACE" and r["question_id"] in by and "RECENT" in by[r["question_id"]]:
            lt[bucket(r["prompt_tokens"] or 0)].append((r["correct"], by[r["question_id"]]["RECENT"]["correct"]))
    fl_lt = {k: flows(v) for k, v in lt.items()}
    # idle TTFT vs history tokens, D2 only, against the committed cold curve
    import costs as C
    tt = defaultdict(list)
    for r in ok:
        if r["rep"] in ("D2", "D2-LIVE-TRACE") and r["ttft_s"] and r["prompt_tokens"]:
            tt[bucket(r["prompt_tokens"])].append((r["prompt_tokens"], r["ttft_s"]))
    ttft = {}
    for k, v in tt.items():
        pt = S.median(x[0] for x in v)
        ttft[k] = dict(n=len(v), median_prompt_tokens=pt, median_ttft_s=round(S.median(x[1] for x in v), 3),
                       committed_cold_s=round(C.recall_ttft_s(int(pt), "COLD"), 3),
                       ratio=round(S.median(x[1] for x in v) / C.recall_ttft_s(int(pt), "COLD"), 3))
    # the policy's committed quality model (StudyRH4, DEV, results/orchestration/prof1/profiles_dev.json)
    prof = json.loads((REPO / "results/orchestration/prof1/profiles_dev.json").read_text())["RC"]["tables"]
    qm = {}
    for rep, tab in (("D2", "32B-D2"), ("RECENT", "32B-RECENT"), ("RICH", "32B-RICH")):
        t = prof.get(tab, {}).get("by_category", {})
        mine = rep if rep != "RICH" else "D2"
        cats = {}
        for cat, v in sorted(t.items()):
            for sp in ("DEV", "EVAL"):
                xs = [1 if r["correct"] else 0 for r in ok if r["rep"] == mine and r["split"] == sp
                      and r["category"] == cat]
                cats.setdefault(cat, dict(committed=v.get("accuracy"), committed_n=v.get("n")))[sp] = boot(xs)
        qm[tab] = cats
    res = dict(n_requests=len(rows), n_errors=len(bad), errors=[r["error"] for r in bad][:10],
               quality_model_vs_acc2=qm,
               cold_check=dict(max_cached_tokens=max((r["cached_tokens"] or 0) for r in ok)),
               accuracy=acc, studyr1=r1acc, flows_by_history=fl_b, flows_by_split=fl_s,
               flows_by_category_exploratory=fl_c, flows_live_trace_long=fl_lt, ttft_by_history=ttft)
    (OUT / "acc2_results.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("n_requests", "n_errors", "cold_check")}))
    for rep, v in acc.items():
        print(rep, {s: (x.get("acc"), x.get("ci95"), x.get("n")) for s, x in v.items()})
    print("R1", {c: {s: (x.get("acc"), x.get("n")) for s, x in v.items()} for c, v in r1acc.items()})
    print("flows by history", json.dumps(fl_b))
    print("flows live-trace long", json.dumps(fl_lt))
    print("ttft", json.dumps(ttft))


if __name__ == "__main__":
    main()
