#!/usr/bin/env python3
"""StudyE10b-mixed analysis (CPU). Per cell: episodic in-window latency (n, p50, p99, errors, dispatch lateness),
recall append / escalation / cold TTFT, warm misses (an append or escalation whose cached tokens are < 0.5 x the same
session's previous prompt tokens), and window-averaged server state from /metrics (waiting, running, KV usage,
preemptions, offload load / store bytes, computed = prompt - local hits - external hits tokens/s) and the Sampler
(GPU util, API cores). Per condition (KV, k, r, N): capacity = highest level meeting the p99 budget, drop vs
k = 0, r = 0 of the same KV config. Negative control vs D7 (N = 3) / D7b (N = 1) 32B open-loop levels.
Writes results/cost/study_e10/e10b_results.json."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_e10"
PEAK = {1: 15.1, 3: 5.38}
BUDGET = {1: 0.45, 3: 1.21}
DISCARD, DUR = 30.0, 270.0


def pct(x, q):
    return float(np.percentile(x, q)) if len(x) else None


def window_metrics(m, c):
    """Average / delta of /metrics over [window_start + DISCARD, window_start + DUR]."""
    w0 = m["window_start"] + DISCARD
    w1 = m["window_start"] + DUR
    tl = [s for s in m["timeline"] if w0 <= s["t"] <= w1]
    if len(tl) < 2:
        return {}
    a, b = tl[0], tl[-1]
    dt = b["t"] - a["t"]

    def d(k):
        return (b.get(k, 0.0) - a.get(k, 0.0)) if k in b else None

    computed = d("prompt_tokens_total") - d("prefix_cache_hits_total") - (d("external_prefix_cache_hits_total") or 0)
    out = dict(samples=len(tl),
               waiting_mean=float(np.mean([s["num_requests_waiting"] for s in tl])),
               waiting_max=float(max(s["num_requests_waiting"] for s in tl)),
               running_mean=float(np.mean([s["num_requests_running"] for s in tl])),
               kv_usage_mean=float(np.mean([s["kv_cache_usage_perc"] for s in tl])),
               kv_usage_max=float(max(s["kv_cache_usage_perc"] for s in tl)),
               preemptions=d("num_preemptions_total"),
               prompt_tok_s=d("prompt_tokens_total") / dt,
               computed_tok_s=computed / dt,
               local_hit_frac=d("prefix_cache_hits_total") / max(d("prompt_tokens_total"), 1))
    if "kv_offload_load_bytes_total" in b:
        out.update(offload_load_gb=d("kv_offload_load_bytes_total") / 1e9, offload_store_gb=d("kv_offload_store_bytes_total") / 1e9,
                   offload_load_s=d("kv_offload_load_time_total"), external_hit_tok_s=(d("external_prefix_cache_hits_total") or 0) / dt)
    s = [x for x in c["samples"] if w0 <= x["t"] <= w1]
    if s:
        out.update(gpu_util_mean=float(np.mean([x["gpu_util"] for x in s])),
                   api_cores_mean=float(np.mean([x["api_cores"] for x in s])),
                   api_max_thread_cores_p99=pct([x["api_max_thread_cores"] for x in s], 99),
                   engine_cores_mean=float(np.mean([x["engine_cores"] for x in s])))
    return out


def main():
    rows = [json.loads(l) for l in open(OUT / "e10b_requests_h100nvl.jsonl")]
    mets = {m["cell"]: m for m in map(json.loads, open(OUT / "e10b_metrics_h100nvl.jsonl"))}
    cpus = {c["cell"]: c for c in map(json.loads, open(OUT / "e10b_cpu_h100nvl.jsonl"))}
    meta = json.load(open(OUT / "e10b_run_meta_h100nvl.json"))
    by = defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    cells = {}
    for cell in meta["done"]:
        rs = by[cell]
        ep = [r for r in rs if r["kind"] == "episodic" and r["in_window"]]
        ok = [r for r in ep if not r["error"]]
        lat = [r["ttft_s"] for r in ok]
        r0 = rs[0]
        N = r0["N"]
        # an errored / unfinished request counts as a budget violation (infinite latency) for p99
        lat_all = lat + [float("inf")] * (len(ep) - len(ok))
        p99_all = (float(np.percentile(lat_all, 99)) if len(ok) == len(ep) else float(np.percentile(lat_all, 99, method="higher"))) if lat_all else None  # D7 linear; nearest-rank only when errors (inf) present
        c_p99_nearest_rank = float(np.percentile(lat_all, 99, method="higher")) if lat_all else None
        c = dict(kv=r0["kv"], k=r0["k"], r=r0["r"], N=N, frac=r0["frac"], rate=r0["rate"],
                 episodic_n=len(ep), episodic_errors=len(ep) - len(ok),
                 error_types=dict(Counter(str(r["error"])[:80] for r in ep if r["error"])),
                 p50=pct(lat, 50), p90=pct(lat, 90), p99=p99_all, p99_nearest_rank=c_p99_nearest_rank, service_p50=pct([r["service_ttft_s"] for r in ok], 50),
                 dispatch_late_p99=pct([r["dispatch_late_s"] for r in ep], 99),
                 episodic_cached_median=pct([r["cached_tokens"] for r in ok], 50),
                 episodic_prompt_median=pct([r["prompt_tokens"] for r in ok], 50))
        c["meets_budget"] = p99_all is not None and p99_all <= BUDGET[N]
        # recall: whole-cell rows inside the window (warm sessions run on session time, report in_window ones)
        for kind in ("recall_append", "recall_escalation", "cold_recall"):
            k_rows = [r for r in rs if r["kind"] == kind and r.get("in_window")]
            kok = [r for r in k_rows if not r["error"]]
            c[kind] = dict(n=len(k_rows), errors=len(k_rows) - len(kok),
                           ttft_p50=pct([r["ttft_s"] for r in kok], 50), ttft_p99=pct([r["ttft_s"] for r in kok], 99),
                           prompt_median=pct([r["prompt_tokens"] for r in kok], 50),
                           cached_frac_median=pct([r["cached_tokens"] / max(r["prompt_tokens"], 1) for r in kok], 50))
        # warm misses: per session (device, session, video), in order of submission
        sess = defaultdict(list)
        for r in rs:
            if r["kind"] in ("recall_warmup", "recall_append", "recall_escalation") and not r["error"]:
                sess[(r["device"], r["session"], r["video_id"])].append(r)
        miss = tot = 0
        for v in sess.values():
            v.sort(key=lambda r: r["t_submit"])
            for prev, cur in zip(v, v[1:]):
                if cur.get("in_window"):
                    tot += 1
                    miss += cur["cached_tokens"] < 0.5 * prev["prompt_tokens"]
        c["warm_followups"], c["warm_misses"] = tot, miss
        c["warm_miss_frac"] = miss / tot if tot else None
        c["recall_unfinished_or_err"] = sum(1 for r in rs if r["kind"].startswith("recall") and r["error"])
        c["server"] = window_metrics(mets[cell], cpus[cell]) if cell in mets and cell in cpus else {}
        cells[cell] = c
    # capacity per condition
    cond = defaultdict(dict)
    for name, c in cells.items():
        cond[(c["kv"], c["k"], c["r"], c["N"])][c["frac"]] = c
    cap = []
    for (kv, k, r, N), lv in sorted(cond.items()):
        passing = [f for f, c in lv.items() if c["meets_budget"]]
        best = max(passing) if passing else None
        base = cond[(kv, 0, 0.0, N)]
        bp = [f for f, c in base.items() if c["meets_budget"]]
        bbest = max(bp) if bp else None
        cap.append(dict(kv=kv, k=k, r=r, N=N, levels_run=sorted(lv), passing=sorted(passing),
                        capacity_frac=best, capacity_rps=best * PEAK[N] if best else None,
                        capacity_label=(f"{int(best * 100)} %" if best else "< 25 %"),
                        drop_vs_baseline_rps=(bbest * PEAK[N] - (best * PEAK[N] if best else 0)) if bbest else None,
                        drop_label=("none" if best == bbest else (f">= {(bbest - (best or 0)) * PEAK[N]:.2f} req/s"
                                                                   if best is None else f"{(bbest - best) * PEAK[N]:.2f} req/s")),
                        p99_by_level={f: round(c["p99"], 3) if c["p99"] not in (None, float('inf')) else c["p99"] for f, c in sorted(lv.items())}))
    # negative control
    ref = {}
    for f, n in (("study_d7/study_d7_levels_h100nvl.jsonl", 3), ("study_d7b/study_d7b_levels_h100nvl.jsonl", 1)):
        for l in open(REPO / "results/cost" / f):
            x = json.loads(l)
            if x["model"] == "32BI" and x["part"] == "B_open" and x["n"] == n:
                ref[(n, x["level"])] = x
    neg = []
    for c in cells.values():
        if c["k"] == 0 and c["r"] == 0:
            d = ref.get((c["N"], c["frac"]))
            ratio = c["p99"] / d["ttft_p99"] if d else None
            neg.append(dict(kv=c["kv"], N=c["N"], frac=c["frac"], p99=c["p99"], ref_p99=d["ttft_p99"] if d else None,
                            p50=c["p50"], ref_p50=d["ttft_p50"] if d else None, ratio_p99=ratio,
                            within_2x=bool(ratio and 0.5 <= ratio <= 2.0), ref_meets=d["ttft_p99"] <= BUDGET[c["N"]] if d else None,
                            meets=c["meets_budget"]))
    res = dict(label="StudyE10b-mixed: episodic capacity under recall load, 32B-I, one replica, H100 GPU 2 (vLLM 0.31.0, prefix caching ON)",
               budget=BUDGET, peak=PEAK, cells=cells, capacity=cap,
               negative_control=sorted(neg, key=lambda x: (x["kv"], x["N"], x["frac"])),
               negative_control_all_within_2x=all(x["within_2x"] for x in neg),
               negative_control_same_pass_fail=sum(x["meets"] == x["ref_meets"] for x in neg), negative_control_n=len(neg))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10b_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / "e10b_results.json").write_text(json.dumps(res, indent=1, default=float))
    for x in cap:
        print(x["kv"], "k", x["k"], "r", x["r"], "N", x["N"], "cap", x["capacity_label"], "drop", x["drop_label"], x["p99_by_level"])
    print("neg ctrl within 2x:", res["negative_control_all_within_2x"], res["negative_control_same_pass_fail"], "/", len(neg))


if __name__ == "__main__":
    main()
