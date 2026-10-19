#!/usr/bin/env python3
"""StudyRH2 analysis (original .venv, CPU). Metrics as pre-registered (research/EXPERIMENTS.md, StudyRH2).

Per cell (policy, D, rate, rep), and for every cell separately over warm devices, cold devices and all devices:
in-window escalation TTFT / total latency (median, p90, p99, max), per-request cached tokens and hit rate
(distribution) and token-weighted hit, errors. Per cell: preemptions, KV usage, waiting queue (window deltas /
ranges from the 1-s /metrics timeline), append computed tokens, append GPU time = sum over appends of
(a + b * computed tokens) from the isolated calibration fit, summed contended append latency, computed prompt tok/s,
in flight at window end, drain time.
Comparisons: P-HALF warm devices at D vs P-WARM at D/2 (RH2 D=8 vs HALF D=16, D=12 vs HALF D=24; R5 WARM D=4 for
HALF D=8). P-HALF cold devices vs P-COLD at D. rep2 vs rep1 at D=12.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_r5_analyse import delta, dist  # noqa: E402  (same distribution / counter-delta code as R5)

D_ = Path("results/cost/study_rh2")
R5 = Path("results/cost/study_r5")
DEV = "h100nvl"


def group(esc):
    if not esc:
        return None
    hits = [(r["cached_tokens"] or 0) / r["prompt_tokens"] for r in esc if r["prompt_tokens"]]
    return dict(n=len(esc), ttft_s=dist([r["ttft_s"] for r in esc]), latency_s=dist([r["latency_s"] for r in esc]),
                prompt_tokens=dist([r["prompt_tokens"] for r in esc]),
                cached_tokens=dist([r["cached_tokens"] or 0 for r in esc]),
                hit_per_request=dist(hits),
                hit_token_weighted=sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0
                                                                                         for r in esc)))


def main():
    meta = json.loads((D_ / f"study_rh2_run_meta_{DEV}.json").read_text())
    R = list(read_jsonl(D_ / f"study_rh2_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_rh2_metrics_{DEV}.jsonl")}
    cal = meta["calib"]
    a, b = cal["a_s"], cal["b_s_per_token"]
    out = dict(kv_capacity=[s.get("kv_cache_tokens") for s in meta.get("servers", [])], calib=cal,
               mechanism_check=meta.get("mechanism_check"), estimate=meta.get("estimate"), cells={})
    for tag, e in meta["experiments"].items():
        rr = [r for r in R if r["cell"] == tag]
        win = [r for r in rr if r["in_window"] and not r["error"]]
        esc = [r for r in win if r["kind"] == "escalation"]
        app = [r for r in win if r["kind"] == "append"]
        comp = lambda xs: sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in xs)  # noqa: E731
        t0 = e["window_start"]
        t1 = t0 + e["window_s"]
        tl = M.get(tag, [])
        kv = [x["kv_cache_usage_perc"] for x in tl if "kv_cache_usage_perc" in x and t0 <= x["t"] <= t1]
        wai = [x.get("num_requests_waiting", 0) for x in tl if t0 <= x["t"] <= t1]
        q = delta(tl, "prefix_cache_queries_total", t0, t1)
        h = delta(tl, "prefix_cache_hits_total", t0, t1)
        out["cells"][tag] = dict(
            policy=e["policy"], D=e["D"], rate=e["esc_frac"], rep=e["rep"], warm_devices=e["warm_devices"],
            warmup_s=e["warmup_s"], inflight_at_window_end=e["inflight_at_window_end"], drain_s=e["drain_s"],
            n_requests=len(rr), errors=sum(bool(r["error"]) for r in rr),
            errors_http400=sum(bool(r["error"]) and "HTTP 400" in r["error"] for r in rr),
            all=group(esc), warm=group([r for r in esc if r["warm_device"]]),
            cold=group([r for r in esc if not r["warm_device"]]),
            server_prefix_hit_rate=(h / q) if q else None, preemptions=delta(tl, "num_preemptions_total", t0, t1),
            kv_usage_mean=float(np.mean(kv)) if kv else None, kv_usage_max=float(max(kv)) if kv else None,
            waiting_mean=float(np.mean(wai)) if wai else None, waiting_max=float(max(wai)) if wai else None,
            appends=len(app), append_hit_token_weighted=(sum(r["cached_tokens"] or 0 for r in app)
                                                         / max(1, sum(r["prompt_tokens"] or 0 for r in app))),
            append_computed_tokens=comp(app), append_share_of_computed=comp(app) / max(1, comp(win)),
            append_gpu_time_est_s=float(sum(a + b * ((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0))
                                            for r in app)),
            append_latency_sum_s=float(sum(r["latency_s"] for r in app)),
            computed_prompt_tok_per_s=comp(win) / e["window_s"], escalations_per_min=len(esc) / (e["window_s"] / 60))

    C = out["cells"]

    def med(tag, grp):
        c = C.get(tag)
        g = c and c.get(grp)
        return None if not g else dict(ttft_median=g["ttft_s"]["median"], ttft_p90=g["ttft_s"]["p90"],
                                       ttft_p99=g["ttft_s"]["p99"], hit=g["hit_token_weighted"], n=g["n"])
    r5 = json.loads((R5 / f"study_r5_results_{DEV}.json").read_text())["cells"]
    cmp_ = []
    for rate in ("100", "020"):
        for D in (8, 16, 24):
            half = f"RH2_HALF_D{D}_r{rate}"
            ref = f"RH2_WARM_D{D // 2}_r{rate}" if D // 2 in (8, 12) else None
            row = dict(rate=rate, D=D, half_warm=med(half, "warm"), half_cold=med(half, "cold"),
                       cold_at_D=med(f"RH2_COLD_D{D}_r{rate}", "all"))
            if ref:
                row["warm_at_D_half"] = med(ref, "all")
                row["warm_at_D_half_tag"] = ref
            elif rate == "100":
                c5 = r5.get("R5_WARM_D4")
                row["warm_at_D_half"] = c5 and dict(ttft_median=c5["escalation_ttft_s"]["median"],
                                                    ttft_p90=c5["escalation_ttft_s"]["p90"],
                                                    hit=c5["escalation_token_hit"], n=c5["escalations"])
                row["warm_at_D_half_tag"] = "R5_WARM_D4 (R5 run, same construction)"
            cmp_.append(row)
        row = dict(rate=rate, D=12, half_warm=med(f"RH2_HALF_D12_r{rate}", "warm"),
                   half_cold=med(f"RH2_HALF_D12_r{rate}", "cold"), cold_at_D=med(f"RH2_COLD_D12_r{rate}", "all"))
        row["warm_at_D_half_tag"] = "none (P-WARM at D=6 was not run)"
        cmp_.append(row)
    out["half_vs_reference"] = cmp_
    out["rep2"] = {p: dict(rep1=med(f"RH2_{p}_D12_r100", "all"), rep2=med(f"RH2_{p}_D12_r100_rep2", "all"),
                           rep1_warm=med(f"RH2_{p}_D12_r100", "warm"), rep2_warm=med(f"RH2_{p}_D12_r100_rep2", "warm"),
                           rep1_cold=med(f"RH2_{p}_D12_r100", "cold"), rep2_cold=med(f"RH2_{p}_D12_r100_rep2", "cold"))
                   for p in ("COLD", "WARM", "HALF")}
    out["_provenance"] = stamp(script="study_rh2_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(R))
    (D_ / f"study_rh2_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print("KV:", out["kv_capacity"], "calib:", {k: v for k, v in cal.items() if k != "rows"})
    print("mechanism:", out["mechanism_check"])
    for t, c in C.items():
        for grp in ("all", "warm", "cold"):
            g = c[grp]
            if not g or (grp != "all" and c["policy"] != "HALF"):
                continue
            tt = g["ttft_s"] or {}
            print(f"{t:24s} {grp:4s} n {g['n']:4d} hit {g['hit_token_weighted']:.2f} TTFT med {tt.get('median', 0):7.2f} "
                  f"p90 {tt.get('p90', 0):7.2f} p99 {tt.get('p99', 0):7.2f} max {tt.get('max', 0):7.2f}"
                  + (f" | preempt {c['preemptions']} kvmax {c['kv_usage_max']} appGPU {c['append_gpu_time_est_s']:.0f}s "
                     f"comp {c['computed_prompt_tok_per_s']:.0f} tok/s infl {c['inflight_at_window_end']} drain "
                     f"{c['drain_s']} err {c['errors']}" if grp == "all" else ""))


if __name__ == "__main__":
    main()
