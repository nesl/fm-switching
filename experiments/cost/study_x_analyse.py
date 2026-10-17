"""StudyX analysis (CPU). Timing / capacity only; no accuracy (except the step-0 drift file, read as-is).

Inputs: results/cost/study_x/study_x_{requests,metrics,stamps,run_meta}_h100nvl.*
Output: results/cost/study_x/study_x_results_h100nvl.json + printed markdown tables.

KV bytes/token for Qwen3-VL-32B: 64 layers x 8 KV heads x 128 dim x 2 (K,V) x 2 B = 262,144 B — matches the server
log (15.37 GiB / 62,944 tokens = 262,200 B).
A "stall" is a gap > 2 s between consecutive streamed tokens of one request (normal inter-token gap 28-60 ms);
in Part C every preemption event in /metrics coincides with the start of one stall.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402

D = Path("results/cost/study_x")
DEV = "h100nvl"
KV_BYTES_PER_TOKEN = 262144
STALL_S = 2.0


def load():
    req = defaultdict(list)
    for r in read_jsonl(D / f"study_x_requests_{DEV}.jsonl"):
        req[r["tag"]].append(r)
    met = {}
    for m in read_jsonl(D / f"study_x_metrics_{DEV}.jsonl"):
        met[m["tag"]] = m["timeline"]
    stamps = defaultdict(dict)
    for s in read_jsonl(D / f"study_x_stamps_{DEV}.jsonl"):
        stamps[s["tag"]][(s["id"], s["t_submit"])] = np.array(s["stamps"])
    meta = json.loads((D / f"study_x_run_meta_{DEV}.json").read_text())
    return req, met, stamps, meta


def pct(x, p):
    return round(float(np.percentile(x, p)), 2) if len(x) else None


def stalls(st):
    if len(st) < 2:
        return []
    g = np.diff(st)
    return [(float(st[i]), float(g[i])) for i in np.where(g > STALL_S)[0]]


def timeline_stats(tl, t0, t1):
    w = [x for x in tl if t0 <= x["t"] <= t1]
    if not w:
        return {}
    kv = np.array([x.get("kv_cache_usage_perc", np.nan) for x in w])
    wt = np.array([x.get("num_requests_waiting", 0) for x in w])
    pre = [x.get("num_preemptions_total", 0) for x in w]
    return dict(kv_mean=round(float(np.nanmean(kv)), 3), kv_max=round(float(np.nanmax(kv)), 3),
                frac_time_kv_ge_99=round(float(np.mean(kv >= 0.99)), 3),
                waiting_mean=round(float(wt.mean()), 2), waiting_max=int(wt.max()),
                preemptions=int(pre[-1] - pre[0]))


def part_c(req, met, stamps, kv_cap):
    out = {}
    for tag in sorted(t for t in req if t.startswith(("C1_", "C3_", "C4_", "C5_", "C6_"))):
        rs = req[tag]
        lead_role = "hitter" if tag.startswith("C1") else "stuck"
        leads = [r for r in rs if r["role"] == lead_role]
        normals = [r for r in rs if r["role"] == "normal"]
        hold_end = max(r["t_end"] for r in leads)
        st = stamps[tag]
        lead_rows = []
        for r in leads:
            s = st[(r["id"], r["t_submit"])]
            ntok = r["completion_tokens"] if r["completion_tokens"] is not None else r["n_chunks"]
            nprm = r["prompt_tokens"] if r["prompt_tokens"] is not None else r["hf_n_input_tokens"]
            # KV held by this request over its lifetime: (prompt + tokens generated so far) x bytes, vs capacity
            occ = (nprm + np.arange(1, len(s) + 1)) / kv_cap
            lead_rows.append(dict(
                id=r["id"], tokens=ntok, finish=r["finish_reason"], closed=r["think_closed"],
                hold_s=r["latency_s"], ttft_s=r["ttft_s"],
                kv_tokens_at_end=nprm + ntok,
                kv_gb_at_end=round((nprm + ntok) * KV_BYTES_PER_TOKEN / 1e9, 2),
                kv_frac_capacity_at_end=round((nprm + ntok) / kv_cap, 3),
                kv_frac_capacity_lifetime_mean=round(float(occ.mean()), 3) if len(occ) else None,
                n_stalls=len(stalls(s)), stall_s=round(sum(g for _, g in stalls(s)), 1),
                decode_ms_median=round(float(np.median(np.diff(s))) * 1000, 1) if len(s) > 1 else None))
        during = [r for r in normals if r["t_end"] <= hold_end]
        lead_windows = [(a, a + g) for r in leads for a, g in stalls(st[(r["id"], r["t_submit"])])]
        nstall = [(r, stalls(st[(r["id"], r["t_submit"])])) for r in normals]
        lat = np.array([r["latency_s"] for r in normals])
        n_while = sum(1 for _, ss in nstall for t, _ in ss if any(a - 1 <= t <= b for a, b in lead_windows))
        out[tag] = dict(
            leads=lead_rows, hold_end_s=round(hold_end, 1),
            normals_submitted=len(normals), normals_completed_during_hold=len(during),
            normals_hit_cap=sum(r["finish_reason"] == "length" for r in normals),
            normals_aborted_by_budget=sum(r["finish_reason"] == "client_abort_budget" for r in normals),
            normals_stalled_while_lead_evicted=n_while,
            normal_stall_events=sum(len(ss) for _, ss in nstall),
            normal_latency=dict(p50=pct(lat, 50), p90=pct(lat, 90), max=pct(lat, 100)),
            normal_ttft_p50=pct([r["ttft_s"] for r in normals if r["ttft_s"] is not None], 50),
            normal_ttft_p90=pct([r["ttft_s"] for r in normals if r["ttft_s"] is not None], 90),
            normals_stalled=sum(1 for _, s in nstall if s),
            normal_stall_total_s=round(sum(g for _, s in nstall for _, g in s), 1),
            lead_stall_total_s=round(sum(x["stall_s"] for x in lead_rows), 1),
            normal_tokens_during_hold=int(sum((r["completion_tokens"] if r["completion_tokens"] is not None
                                               else r["n_chunks"]) for r in during)),
            normal_completions_per_min_of_hold=round(len(during) / hold_end * 60, 2),
            timeline=timeline_stats(met.get(tag, []), 0, hold_end))
    return out


def part_b(req, stamps, prefix="B"):
    out = {}
    for b in range(5):
        t8 = f"{prefix}_vllm_batch8_b{b}"
        if t8 not in req:
            continue
        rs = req[t8]
        lr = next(r for r in rs if r["role"] == "long")
        ls = stamps[t8][(lr["id"], lr["t_submit"])]
        sh = sorted(r["latency_s"] for r in rs if r["role"] == "short")
        row = dict(long_id=lr["id"], long_tokens=lr["completion_tokens"], long_finish=lr["finish_reason"],
                   long_latency_s=lr["latency_s"],
                   long_time_to_8192_s=round(float(ls[8191] - lr["t_submit"]), 1) if len(ls) >= 8192 else None,
                   short_latencies_s=sh, short_median_s=pct(sh, 50), short_max_s=max(sh),
                   short_tokens=sorted(r["completion_tokens"] for r in rs if r["role"] == "short"))
        tr = f"{prefix}_vllm_refill_b{b}"
        if tr in req:
            rr = req[tr]
            lr2 = next(r for r in rr if r["role"] == "long")
            done = [r for r in rr if r["role"] == "short" and r["t_end"] <= lr2["t_end"]]
            row.update(refill_long_latency_s=lr2["latency_s"], refill_long_tokens=lr2["completion_tokens"],
                       refill_short_completed_during_long=len(done),
                       refill_short_latency_p50=pct([r["latency_s"] for r in done], 50),
                       refill_short_latency_p90=pct([r["latency_s"] for r in done], 90),
                       refill_short_tokens_during_long=int(sum(r["completion_tokens"] for r in done)))
        out[b] = row
    return out


def part_b_hf():
    """HF static batching at the matched 8,192 cap (original .venv, flash_attention_2). Every request in a static
    batch is delivered when generate() returns: its latency = batch wall time."""
    f = D / f"study_x_hf_static_partB_cap8192_{DEV}.jsonl"
    out = {}
    if not f.exists():
        return out
    for rec in map(json.loads, open(f)):
        rows = rec["rows"]
        out[rec["b"]] = dict(long_qid=rec["long"], wall_s=rec["wall_s"], steps=rec["steps"],
                             ms_per_step=round(rec["wall_s"] / rec["steps"] * 1000, 1),
                             long_tokens=rows[0]["n_real_tokens"],
                             short_delivered_latency_s=rec["wall_s"],
                             short_internal_finish_s=sorted(r["internal_finish_s"] for r in rows[1:]),
                             short_tokens=sorted(r["n_real_tokens"] for r in rows[1:]),
                             peak_alloc_gb=rec["peak_alloc_gb"], peak_reserved_gb=rec["peak_reserved_gb"],
                             attn_implementation=rec["attn_implementation"])
    return out


def part_a(req, met):
    out = {}
    for tag in sorted(t for t in req if t.startswith("A_32B")):
        rs = [r for r in req[tag] if not r["error"]]
        t0 = min(r["t_submit"] for r in rs)
        t1 = max(r["t_end"] for r in rs)
        span = t1 - t0
        lat = np.array([r["latency_s"] for r in rs])
        ttft = np.array([r["ttft_s"] for r in rs if r["ttft_s"] is not None])
        toks = np.array([r["completion_tokens"] for r in rs])
        # per-request decode rate (tokens after the first / time after the first token)
        dec = np.array([(r["completion_tokens"] - 1) / (r["latency_s"] - r["ttft_s"]) for r in rs
                        if r["completion_tokens"] > 50 and r["latency_s"] > r["ttft_s"]])
        _, model, wl, c = tag.split("_")
        out[tag] = dict(model=model, workload=wl, concurrency=int(c[1:]), n_req=len(rs),
                        agg_tok_s=round(toks.sum() / span, 1), req_s=round(len(rs) / span, 3),
                        lat_p50=pct(lat, 50), lat_p90=pct(lat, 90), lat_p99=pct(lat, 99),
                        ttft_p50=pct(ttft, 50), ttft_p90=pct(ttft, 90),
                        per_req_decode_tok_s_p50=pct(dec, 50),
                        tokens_p50=pct(toks, 50), tokens_max=int(toks.max()),
                        **timeline_stats(met.get(tag, []), t0, t1))
    return out


def main():
    req, met, stamps, meta = load()
    srv = meta["servers"][-1]
    kv_cap = srv["kv_cache_tokens"]
    res = dict(stack=meta["stack"], servers=[{k: s.get(k) for k in (
        "stage", "key", "kv_cache_tokens", "available_kv_gib", "model_weights_gib", "max_concurrency_at_max_len",
        "flash_attention_version", "sampler", "startup_s", "max_model_len", "gpu_memory_utilization",
        "tensor_parallel_size", "prefix_caching")} for s in meta["servers"]],
        kv_bytes_per_token=KV_BYTES_PER_TOKEN, kv_capacity_tokens=kv_cap,
        drift=json.loads((D / f"study_x_drift_{DEV}.json").read_text()),
        part_c=part_c(req, met, stamps, kv_cap), part_b=part_b(req, stamps),
        part_b_cap8192_vllm=part_b(req, stamps, "B8k"), part_b_cap8192_hf=part_b_hf(), part_a=part_a(req, met))
    res["drift"].pop("rows", None)
    (D / f"study_x_results_{DEV}.json").write_text(json.dumps(res, indent=1))

    print("## Part C")
    for tag, c in res["part_c"].items():
        print(f"\n{tag}: hold_end {c['hold_end_s']}s normals {c['normals_completed_during_hold']}/{c['normals_submitted']} "
              f"(cap-hit {c['normals_hit_cap']}) normal lat p50/p90/max {c['normal_latency']} ttft p50/p90 "
              f"{c['normal_ttft_p50']}/{c['normal_ttft_p90']} stalled {c['normals_stalled']} normal-stall "
              f"{c['normal_stall_total_s']}s lead-stall {c['lead_stall_total_s']}s tl {c['timeline']}")
        for x in c["leads"]:
            print("   lead", json.dumps(x))
    for key in ("part_b", "part_b_cap8192_vllm", "part_b_cap8192_hf"):
        print(f"\n## {key}")
        for b, r in res[key].items():
            print(b, json.dumps(r))
    print("\n## Part A")
    print("| model | workload | c | n | agg tok/s | req/s | lat p50/p90/p99 | TTFT p50/p90 | per-req decode tok/s | "
          "KV max | preempt | waiting max |")
    for tag, a in res["part_a"].items():
        print(f"| {a['model']} | {a['workload']} | {a['concurrency']} | {a['n_req']} | {a['agg_tok_s']} | {a['req_s']} | "
              f"{a['lat_p50']}/{a['lat_p90']}/{a['lat_p99']} | {a['ttft_p50']}/{a['ttft_p90']} | "
              f"{a['per_req_decode_tok_s_p50']} | {a.get('kv_max')} | {a.get('preemptions')} | {a.get('waiting_max')} |")


if __name__ == "__main__":
    main()
