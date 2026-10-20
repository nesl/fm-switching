#!/usr/bin/env python3
"""StudyRH5 analysis (original .venv, CPU). Pre-registered metrics and decision rule (research/EXPERIMENTS.md, StudyRH5).

Part A: TTFT median / min / max per (state, size); reload bandwidth = kv_offload load bytes / load time (metric) and
load bytes / (TTFT_HOST-WARM - TTFT_GPU-WARM of the same session and repetition); verification per row.
Part B: per cell (cfg, D) as RH2 — warm escalation TTFT / latency distributions, token hit, errors (+ kinds),
preemptions, KV usage, waiting, in flight at window end, drain, computed prompt tok/s — plus window deltas of the
GPU-local vs external (host) prefix-cache hit counters, kv_offload load/store bytes (PCIe KV traffic), host RSS.
DECISION: OFFLOAD REMOVES SCARCITY if at D=16 and D=24 GPU+host keeps warm TTFT median <= 1.5 s and p99 <= 10 s while
GPU-only median > 5 s; OFFLOAD SHIFTS THE KNEE if GPU+host is better than GPU-only but exceeds those bounds at D=24;
OFFLOAD DOES NOT HELP otherwise.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
from study_r5_analyse import dist as _dist  # noqa: E402


def dist(v):
    d = _dist(v)
    if d:
        d["min"] = float(min(x for x in v if x is not None))
    return d

D_ = Path("results/cost/study_rh5")
DEV = "h100nvl"
KV_BYTES_PER_TOKEN = 262144


def tl_delta(tl, key, t0, t1):
    xs = [x for x in tl if t0 <= x["t"] <= t1 and key in x]
    return (xs[-1][key] - xs[0][key]) if len(xs) >= 2 else None


def tl_sum_prefix(row, prefix):
    return sum(v for k, v in row.items() if k.startswith(prefix))


def main():
    meta = json.loads((D_ / f"study_rh5_run_meta_{DEV}.json").read_text())
    out = dict(servers=[{k: s.get(k) for k in ("cfg", "stage", "kv_cache_tokens", "kv_offloading",
                                               "flash_attention_version", "cuda_graphs", "host_mem", "extra_server_args")}
                        for s in meta["servers"]],
               partA_verification={k: dict(all=v["host_warm_all_verified"],
                                           n_verified=sum(r["verified"] for r in v["rows"]), n=len(v["rows"]))
                                   for k, v in meta.get("partA_verification", {}).items()},
               partA={}, cells={}, estimate=meta.get("estimate"))

    # ---------------- Part A
    A = list(read_jsonl(D_ / f"study_rh5_partA_{DEV}.jsonl"))
    for r in A:
        d = r["metric_deltas"]
        r["load_bytes"] = d.get("kv_offload_load_bytes_total", 0.0)
        r["load_time_s"] = d.get("kv_offload_load_time_total", 0.0)
        r["local_hits"] = d.get("prefix_cache_hits_total", 0.0)
        r["external_hits"] = d.get("external_prefix_cache_hits_total", 0.0)
    for cfg in ("host", "gpu"):
        for state in ("GPU-WARM", "HOST-WARM", "COLD"):
            for size in ("11k", "28k"):
                rr = [r for r in A if r["cfg"] == cfg and r["state"] == state and r["size"] == size and not r["error"]]
                if not rr:
                    continue
                key = f"{cfg}/{state}/{size}"
                tt = [r["ttft_s"] for r in rr]
                o = dict(n=len(rr), sessions=len({r["video_id"] for r in rr}), ttft_s=dist(tt), ttft_all=tt,
                         prompt_tokens=dist([r["prompt_tokens"] for r in rr]),
                         cached_tokens=dist([r["cached_tokens"] for r in rr]),
                         local_hits=dist([r["local_hits"] for r in rr]),
                         external_hits=dist([r["external_hits"] for r in rr]))
                if state == "HOST-WARM":
                    gw = {(r["video_id"], r["rep"]): r for r in A if r["cfg"] == cfg and r["state"] == "GPU-WARM"
                          and r["size"] == size}
                    bw_metric = [r["load_bytes"] / r["load_time_s"] / 1e9 for r in rr if r["load_time_s"] > 0]
                    bw_ttft = [r["load_bytes"] / (r["ttft_s"] - gw[(r["video_id"], r["rep"])]["ttft_s"]) / 1e9
                               for r in rr if (r["video_id"], r["rep"]) in gw
                               and r["ttft_s"] > gw[(r["video_id"], r["rep"])]["ttft_s"]]
                    o.update(load_gb=dist([r["load_bytes"] / 1e9 for r in rr]),
                             load_bytes_per_external_token=dist([r["load_bytes"] / r["external_hits"] for r in rr
                                                                 if r["external_hits"]]),
                             load_time_s=dist([r["load_time_s"] for r in rr]),
                             reload_gbps_metric=dist(bw_metric), reload_gbps_from_ttft=dist(bw_ttft),
                             extra_ttft_vs_gpu_warm_s=dist([r["ttft_s"] - gw[(r["video_id"], r["rep"])]["ttft_s"]
                                                            for r in rr if (r["video_id"], r["rep"]) in gw]))
                if state == "COLD":
                    o["prefill_tok_per_s"] = dist([(r["prompt_tokens"] - (r["cached_tokens"] or 0)) / r["ttft_s"]
                                                   for r in rr])
                out["partA"][key] = o

    # ---------------- Part B
    R = list(read_jsonl(D_ / f"study_rh5_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_rh5_metrics_{DEV}.jsonl")}
    for tag, e in meta["experiments"].items():
        rr = [r for r in R if r["cell"] == tag]
        win = [r for r in rr if r["in_window"] and not r["error"]]
        esc = [r for r in win if r["kind"] == "escalation"]
        app = [r for r in win if r["kind"] == "append"]
        comp = lambda xs: sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in xs)  # noqa: E731
        t0, t1 = e["window_start"], e["window_start"] + e["window_s"]
        tl = M.get(tag, [])
        tend = tl[-1]["t"] if tl else t1
        kv = [x["kv_cache_usage_perc"] for x in tl if "kv_cache_usage_perc" in x and t0 <= x["t"] <= t1]
        wai = [x.get("num_requests_waiting", 0) for x in tl if t0 <= x["t"] <= t1]
        local_h = tl_delta(tl, "prefix_cache_hits_total", t0, tend)
        local_q = tl_delta(tl, "prefix_cache_queries_total", t0, tend)
        ext_h = tl_delta(tl, "external_prefix_cache_hits_total", t0, tend)
        ext_q = tl_delta(tl, "external_prefix_cache_queries_total", t0, tend)
        tt = [r["ttft_s"] for r in esc if r["ttft_s"] is not None]
        errs = [r for r in rr if r["error"]]
        out["cells"][tag] = dict(
            cfg=e["cfg"], D=e["D"], warmup_s=e["warmup_s"], inflight_at_window_end=e["inflight_at_window_end"],
            drain_s=e["drain_s"], n_requests=len(rr), errors=len(errs),
            error_kinds=sorted({(r["error"] or "")[:70] for r in errs}),
            errors_over_context=sum("maximum context length" in (r["error"] or "") or "Input length" in (r["error"]
                                                                                                      or "")
                                    for r in errs),
            escalations=len(esc), ttft_s=dist(tt), latency_s=dist([r["latency_s"] for r in esc]),
            esc_hit_token_weighted=sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0
                                                                                        for r in esc)),
            esc_hit_per_request=dist([(r["cached_tokens"] or 0) / r["prompt_tokens"] for r in esc
                                      if r["prompt_tokens"]]),
            esc_prompt_tokens=dist([r["prompt_tokens"] for r in esc]),
            appends=len(app), append_hit_token_weighted=sum(r["cached_tokens"] or 0 for r in app)
            / max(1, sum(r["prompt_tokens"] or 0 for r in app)),
            computed_prompt_tok_per_s=comp(win) / e["window_s"],
            preemptions=tl_delta(tl, "num_preemptions_total", t0, tend),
            kv_usage_mean=float(np.mean(kv)) if kv else None, kv_usage_max=float(max(kv)) if kv else None,
            waiting_mean=float(np.mean(wai)) if wai else None, waiting_max=float(max(wai)) if wai else None,
            gpu_local_hit_tokens=local_h, gpu_local_query_tokens=local_q, host_hit_tokens=ext_h,
            host_query_tokens=ext_q,
            host_share_of_hits=(ext_h / (ext_h + local_h)) if ext_h is not None and local_h and (ext_h + local_h)
            else (0.0 if local_h else None),
            pcie_load_gb=(tl_delta(tl, "kv_offload_load_bytes_total", t0, tend) or 0) / 1e9 if e["cfg"] == "host"
            else None,
            pcie_store_gb=(tl_delta(tl, "kv_offload_store_bytes_total", t0, tend) or 0) / 1e9 if e["cfg"] == "host"
            else None,
            host_buffer_usage_max=max((x.get("kv_offload_cpu_cache_usage_perc", 0) for x in tl), default=None)
            if e["cfg"] == "host" else None,
            host_mem=dict(start=e.get("host_mem_start"), window_end=e.get("host_mem_window_end"),
                          end=e.get("host_mem_end")))

    # ---------------- decision
    C = out["cells"]

    def g(cfg, D, k):
        c = C.get(f"RH5_{cfg}_D{D}")
        return c and c["ttft_s"] and c["ttft_s"].get(k)
    cond = {}
    for D in (16, 24):
        cond[f"D{D}_host_median_le_1p5"] = (g("HOST", D, "median") or 1e9) <= 1.5
        cond[f"D{D}_host_p99_le_10"] = (g("HOST", D, "p99") or 1e9) <= 10
        cond[f"D{D}_gpu_median_gt_5"] = (g("GPU", D, "median") or 0) > 5
    better24 = (g("HOST", 24, "median") or 1e9) < (g("GPU", 24, "median") or 0)
    outcome = ("OFFLOAD REMOVES SCARCITY" if all(cond.values()) else
               "OFFLOAD SHIFTS THE KNEE" if better24 else "OFFLOAD DOES NOT HELP")
    out["decision"] = dict(conditions=cond, host_better_than_gpu_at_D24=better24, outcome=outcome)
    out["_provenance"] = stamp(script="study_rh5_analyse.py", model="qwen3vl-32b-instruct", device=DEV,
                               n=len(R) + len(A))
    (D_ / f"study_rh5_results_{DEV}.json").write_text(json.dumps(out, indent=1))

    print("DECISION:", json.dumps(out["decision"]))
    print("verification:", out["partA_verification"])
    for k, o in out["partA"].items():
        t = o["ttft_s"]
        print(f"A {k:22s} n {o['n']:2d} ttft med {t['median']:.3f} [{t['min']:.3f}, {t['max']:.3f}] prompt "
              f"{o['prompt_tokens']['median']:.0f} cached {o['cached_tokens']['median']:.0f} local "
              f"{o['local_hits']['median']:.0f} ext {o['external_hits']['median']:.0f}"
              + (f" | load {o['load_gb']['median']:.2f} GB, {o['load_time_s']['median']:.3f} s, metric "
                 f"{o['reload_gbps_metric']['median'] if o['reload_gbps_metric'] else None} GB/s, ttft-based "
                 f"{o['reload_gbps_from_ttft']['median'] if o['reload_gbps_from_ttft'] else None} GB/s, extra "
                 f"{o['extra_ttft_vs_gpu_warm_s']['median']:.3f} s, B/tok {o['load_bytes_per_external_token']}"
                 if "load_gb" in o else "")
              + (f" | prefill {o['prefill_tok_per_s']['median']:.0f} tok/s" if "prefill_tok_per_s" in o else ""))
    for t, c in C.items():
        tt = c["ttft_s"] or {}
        print(f"B {t:14s} n {c['escalations']:3d} hit {c['esc_hit_token_weighted']:.2f} TTFT med "
              f"{tt.get('median', 0):8.2f} p90 {tt.get('p90', 0):8.2f} p99 {tt.get('p99', 0):8.2f} max "
              f"{tt.get('max', 0):8.2f} | app hit {c['append_hit_token_weighted']:.2f} comp "
              f"{c['computed_prompt_tok_per_s']:.0f} tok/s preempt {c['preemptions']} kvmax {c['kv_usage_max']} "
              f"wait max {c['waiting_max']} infl {c['inflight_at_window_end']} drain {c['drain_s']} err "
              f"{c['errors']} ({c['errors_over_context']} ctx) | local {c['gpu_local_hit_tokens']} host "
              f"{c['host_hit_tokens']} share {c['host_share_of_hits']} pcie load {c['pcie_load_gb']} store "
              f"{c['pcie_store_gb']} GB")


if __name__ == "__main__":
    main()
