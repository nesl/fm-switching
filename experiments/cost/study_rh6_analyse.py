#!/usr/bin/env python3
"""StudyRH6 analysis (original .venv, CPU). Pre-registered metrics, binding-resource thresholds and decision rules
(research/EXPERIMENTS.md, StudyRH6).

Per cell (window = window start .. +900 s; "whole" = window start .. drain end):
  warm escalation TTFT median/p90/p99/max; append TTFT median/p99; token hit; host share of hits; GPU KV usage
  median/max; PCIe load/store GB (whole), average GB/s, 1-s peak and best 30-s rolling load rate; computed prompt
  tok/s ACHIEVED (completed in whole / elapsed) and DEMAND (submitted in window / 900 s); CPU cores (API process,
  its busiest thread, engine tree, harness) and GPU-3 SM util; submit lag; waiting max, preemptions, in flight at
  window end, drain; errors (over-context 400s separate); warm misses (cached < 0.5x the prompt of the same
  device-session's previous completed request) and kv_offload_allocation_failure; analytic live-set peak.
Binding flags (pre-registered): KV running set, GPU compute, PCIe, host capacity, API CPU; harness-validity flag.
Decisions: KNEE (D*, binding resource) / NO KNEE IN RANGE; LEVERS per B cell.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402

D_ = Path("results/cost/study_rh6")
DEV = "h100nvl"
BPT = 262144
CAP_TOKENS = {256: 256 * 2 ** 30 // BPT + 62944, 64: 64 * 2 ** 30 // BPT + 62944}
# which resource each lever acts on (pre-registered Step 1)
LEVER_TARGETS = {"B1": {"kv_running_set", "pcie", "api_cpu", "host_capacity"},
                 "B2": {"kv_running_set", "pcie", "host_capacity", "gpu_compute", "api_cpu"},
                 "B3": {"kv_running_set", "pcie", "host_capacity", "api_cpu"}}


def dist(v):
    v = [x for x in v if x is not None]
    if not v:
        return None
    a = np.array(v, float)
    return dict(n=len(a), median=float(np.median(a)), p90=float(np.percentile(a, 90)),
                p99=float(np.percentile(a, 99)), max=float(a.max()), min=float(a.min()), mean=float(a.mean()))


def csum(row, prefix):
    return sum(v for k, v in (row or {}).items() if k.startswith(prefix) and not k.endswith("_created"))


def cdelta(a, b, prefix):
    return csum(b, prefix) - csum(a, prefix)


def warm_misses(rr):
    """Per in-window append/escalation: previous completed request of the same device-session (t_end < t_submit)."""
    by = {}
    for r in rr:
        if r["error"] or r["prompt_tokens"] is None:
            continue
        by.setdefault((r["device"], r["session"]), []).append(r)
    n = miss = 0
    for xs in by.values():
        done = sorted(xs, key=lambda r: r["t_end"])
        for r in xs:
            if not r["in_window"] or r["kind"] not in ("append", "escalation"):
                continue
            prev = [p for p in done if p["t_end"] < r["t_submit"]]
            if not prev:
                continue
            n += 1
            miss += (r["cached_tokens"] or 0) < 0.5 * prev[-1]["prompt_tokens"]
    return n, miss


def rolling_max(t, y, w):
    best = 0.0
    j = 0
    for i in range(len(t)):
        while t[i] - t[j] > w:
            j += 1
        if t[i] - t[j] >= w * 0.9:
            best = max(best, (y[i] - y[j]) / (t[i] - t[j]))
    return best


def cell_stats(tag, e, rr, tl, cpu):
    spec = e["spec"]
    t0 = e["window_start"]
    t1 = t0 + e["window_s"]
    tend = t0 + e["elapsed_window_plus_drain_s"]
    whole = tend - t0
    ok = [r for r in rr if not r["error"]]
    win = [r for r in ok if r["in_window"]]
    esc = [r for r in win if r["kind"] == "escalation"]
    app = [r for r in win if r["kind"] == "append"]
    comp = lambda xs: sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in xs)  # noqa: E731
    achieved = comp([r for r in ok if t0 <= r["t_end"] <= tend]) / whole
    demand = comp(win) / e["window_s"]
    errs = [r for r in rr if r["error"]]
    ctx = [r for r in errs if r["error"].startswith("HTTP 400") and ("context" in r["error"] or "length" in
                                                                      r["error"] or "image" in r["error"])]
    C = e["counters"]
    a, b = C["window_start"], C["end"]
    local_h, ext_h = cdelta(a, b, "prefix_cache_hits"), cdelta(a, b, "external_prefix_cache_hits")
    load, store = cdelta(a, b, "kv_offload_load_bytes"), cdelta(a, b, "kv_offload_store_bytes")
    tw = [x for x in tl if t0 <= x["t"] <= tend]
    kv = [x["kv_cache_usage_perc"] for x in tw if "kv_cache_usage_perc" in x]
    wai = [x.get("num_requests_waiting", 0) for x in tw]
    run = [x.get("num_requests_running", 0) for x in tw]
    lt = [x["t"] for x in tw if "kv_offload_load_bytes_total" in x]
    ly = [x["kv_offload_load_bytes_total"] for x in tw if "kv_offload_load_bytes_total" in x]
    peak1 = max(((ly[i] - ly[i - 1]) / (lt[i] - lt[i - 1]) for i in range(1, len(lt)) if lt[i] > lt[i - 1]),
                default=0.0)
    cw = [x for x in cpu if t0 <= x["t"] <= tend]
    lag = [r["submit_lag_s"] for r in rr if r.get("submit_lag_s") is not None and r["in_window"]]
    n_w, n_miss = warm_misses(rr)
    tt = [r["ttft_s"] for r in esc if r["ttft_s"] is not None]
    o = dict(
        part=spec["part"], D=spec["D"], fmt=spec["fmt"], cadence=spec["cadence"], lazy=spec["lazy"],
        offload_gib=spec["offload"], coverage=e["coverage"], warmup_s=e["warmup_s"],
        inflight_at_window_end=e["inflight_at_window_end"], drain_s=e["drain_s"], whole_s=round(whole, 1),
        n_requests=len(rr), appends=len(app), escalations=len(esc),
        req_per_s_window=len([r for r in rr if r["in_window"]]) / e["window_s"],
        esc_ttft_s=dist(tt), esc_latency_s=dist([r["latency_s"] for r in esc]), append_ttft_s=dist(
            [r["ttft_s"] for r in app]),
        esc_hit=sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0 for r in esc)),
        append_hit=sum(r["cached_tokens"] or 0 for r in app) / max(1, sum(r["prompt_tokens"] or 0 for r in app)),
        token_hit=sum(r["cached_tokens"] or 0 for r in win) / max(1, sum(r["prompt_tokens"] or 0 for r in win)),
        esc_prompt_tokens=dist([r["prompt_tokens"] for r in esc]),
        body_mb=dist([r["body_mb"] for r in rr if r["in_window"]]),
        gpu_local_hit_tokens=local_h, host_hit_tokens=ext_h,
        host_share_of_hits=ext_h / (ext_h + local_h) if (ext_h + local_h) else None,
        pcie_load_gb=load / 1e9, pcie_store_gb=store / 1e9, pcie_load_gbps_avg=load / whole / 1e9,
        pcie_store_gbps_avg=store / whole / 1e9, pcie_load_gbps_peak_1s=peak1 / 1e9,
        pcie_load_gbps_best_30s=rolling_max(lt, ly, 30.0) / 1e9 if lt else 0.0,
        load_bytes_per_host_hit_token=load / ext_h if ext_h else None,
        allocation_failures=cdelta(a, b, "kv_offload_allocation_failure"),
        computed_tok_s_achieved=achieved, computed_tok_s_demand=demand,
        kv_usage=dist(kv), waiting=dist(wai), running=dist(run),
        preemptions=cdelta(a, b, "num_preemptions"),
        api_cores=dist([x["api_cores"] for x in cw]), api_max_thread_cores=dist([x["api_max_thread_cores"]
                                                                                   for x in cw]),
        engine_cores=dist([x["engine_cores"] for x in cw]), harness_cores=dist([x["harness_cores"] for x in cw]),
        gpu_util=dist([x["gpu_util"] for x in cw]), submit_lag_s=dist(lag),
        errors=len(errs), errors_over_context=len(ctx), error_kinds=sorted({r["error"][:80] for r in errs}),
        warm_requests_checked=n_w, warm_misses=n_miss, warm_miss_frac=n_miss / n_w if n_w else None,
        host_verification=e.get("host_verification"), host_mem_end=e.get("host_mem_end"))
    # binding flags (pre-registered thresholds)
    kvmax = o["kv_usage"]["max"] if o["kv_usage"] else 0
    flags = dict(
        kv_running_set=kvmax >= 0.95 and ((o["waiting"] or {}).get("max", 0) > 0 or (o["preemptions"] or 0) > 0),
        gpu_compute=achieved >= 4000,
        pcie=o["pcie_load_gbps_avg"] >= 35 or o["pcie_load_gbps_best_30s"] >= 35,
        host_capacity=(o["warm_miss_frac"] or 0) > 0.05 or o["allocation_failures"] > 0,
        api_cpu=bool(o["api_cores"]) and (o["api_cores"]["median"] >= 0.9 or
                                          (o["api_max_thread_cores"] or {}).get("median", 0) >= 0.9))
    o["binding_flags"] = flags
    # ---- diagnostics (NOT pre-registered; added after Part A showed the flags fire in non-breaching cells too)
    tw_ = [x for x in tl if t0 <= x["t"] <= t1]
    starts = np.array(sorted(r["t_submit"] for r in rr))
    ends = np.array(sorted(r["t_end"] for r in rr))
    up, eng = [], []
    for x in tw_:
        infl = int(np.searchsorted(starts, x["t"], "right") - np.searchsorted(ends, x["t"], "right"))
        e_q = x.get("num_requests_running", 0) + x.get("num_requests_waiting", 0)
        up.append(infl - e_q)
        eng.append(e_q)
    cww = [x for x in cpu if t0 <= x["t"] <= t1]
    o["diagnostics"] = dict(
        scrape_coverage_window=len(tw_) / e["window_s"],
        upstream_of_engine_window=dist(up), engine_queue_window=dist(eng),
        engine_waiting_window=dist([x.get("num_requests_waiting", 0) for x in tw_]),
        kv_usage_window=dist([x["kv_cache_usage_perc"] for x in tw_ if "kv_cache_usage_perc" in x]),
        gpu_util_window=dist([x["gpu_util"] for x in cww]),
        api_cores_window=dist([x["api_cores"] for x in cww]),
        api_max_thread_cores_window=dist([x["api_max_thread_cores"] for x in cww]),
        served_req_per_s_window=sum(1 for r in rr if t0 <= r["t_end"] <= t1) / e["window_s"],
        served_req_per_s_drain=(sum(1 for r in rr if t1 < r["t_end"] <= tend) / (tend - t1)) if tend - t1 > 5
        else None,
        offered_body_mb_per_s=sum(r["body_mb"] for r in rr if r["in_window"]) / e["window_s"],
        served_body_mb_per_s_window=sum(r["body_mb"] for r in rr if t0 <= r["t_end"] <= t1) / e["window_s"])
    o["harness_valid"] = not (o["submit_lag_s"] and o["submit_lag_s"]["p99"] > 1.0)
    o["breach"] = bool(o["esc_ttft_s"]) and (o["esc_ttft_s"]["median"] > 1.5 or o["esc_ttft_s"]["p99"] > 10)
    return o


def main():
    meta = json.loads((D_ / f"study_rh6_run_meta_{DEV}.json").read_text())
    R = list(read_jsonl(D_ / f"study_rh6_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_rh6_metrics_{DEV}.jsonl")}
    P = {m["cell"]: m["samples"] for m in read_jsonl(D_ / f"study_rh6_cpu_{DEV}.jsonl")}
    out = dict(servers=[{k: s.get(k) for k in ("stage", "kv_cache_tokens", "kv_offloading_gib",
                                               "flash_attention_version", "cuda_graphs", "host_mem", "startup_s")}
                        for s in meta["servers"]],
               stack=meta.get("stack"), estimate=meta.get("estimate"), d_star=meta.get("d_star"), cells={})
    for tag, e in meta["experiments"].items():
        out["cells"][tag] = cell_stats(tag, e, [r for r in R if r["cell"] == tag], M.get(tag, []), P.get(tag, []))
    C = out["cells"]
    ds = meta.get("d_star") or {}
    Ds = ds.get("D")
    base = C.get(f"RH6_A_D{Ds}")
    knee = dict(D_star=Ds, breached=ds.get("breached"),
                outcome=("KNEE" if ds.get("breached") else "NO KNEE IN RANGE") if Ds else None,
                binding=[k for k, v in (base or {}).get("binding_flags", {}).items() if v] if base else None)
    if base is not None and not knee["binding"]:
        knee["binding"] = ["cannot attribute"]
    levers = {}
    for k in ("B1", "B2", "B3"):
        c = C.get(f"RH6_{k}_D{Ds}")
        if not (c and base and c["esc_ttft_s"] and base["esc_ttft_s"]):
            continue
        m, p = c["esc_ttft_s"]["median"], c["esc_ttft_s"]["p99"]
        bp = base["esc_ttft_s"]["p99"]
        within = m <= 1.5 and p <= 10
        cut = (bp - p) / bp if bp else None
        levers[k] = dict(median=m, p99=p, base_median=base["esc_ttft_s"]["median"], base_p99=bp,
                         within_bounds=within, p99_cut_frac=cut, effective=bool(within or (cut or 0) >= 0.5),
                         targets_binding=sorted(LEVER_TARGETS[k] & set(knee["binding"] or [])))
    out["decision"] = dict(knee=knee, levers=levers,
                           binding_not_affected_by_any_lever=bool(knee["binding"]) and not any(
                               LEVER_TARGETS[k] & set(knee["binding"]) for k in LEVER_TARGETS))
    out["_provenance"] = stamp(script="study_rh6_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(R))
    (D_ / f"study_rh6_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print("DECISION:", json.dumps(out["decision"], indent=1))
    f = lambda d, k="median": "—" if not d else f"{d[k]:.2f}"  # noqa: E731
    for t, c in C.items():
        print(f"{t:16s} req/s {c['req_per_s_window']:.2f} n_esc {c['escalations']:3d} esc med {f(c['esc_ttft_s'])} "
              f"p90 {f(c['esc_ttft_s'], 'p90')} p99 {f(c['esc_ttft_s'], 'p99')} max {f(c['esc_ttft_s'], 'max')} | "
              f"app med {f(c['append_ttft_s'])} p99 {f(c['append_ttft_s'], 'p99')} | hit {c['token_hit']:.3f} host "
              f"{c['host_share_of_hits']} | kv med {f(c['kv_usage'])} max {f(c['kv_usage'], 'max')} | pcie "
              f"{c['pcie_load_gb']:.0f}/{c['pcie_store_gb']:.0f} GB avg {c['pcie_load_gbps_avg']:.1f} 30s "
              f"{c['pcie_load_gbps_best_30s']:.1f} pk {c['pcie_load_gbps_peak_1s']:.1f} | comp ach "
              f"{c['computed_tok_s_achieved']:.0f} dem {c['computed_tok_s_demand']:.0f} | api {f(c['api_cores'])}/"
              f"{f(c['api_cores'], 'max')} thr {f(c['api_max_thread_cores'])} eng {f(c['engine_cores'])} har "
              f"{f(c['harness_cores'])} gpu {f(c['gpu_util'])} lag99 {f(c['submit_lag_s'], 'p99')} | wait "
              f"{f(c['waiting'], 'max')} pre {c['preemptions']} infl {c['inflight_at_window_end']} drain "
              f"{c['drain_s']} err {c['errors']} ({c['errors_over_context']}) miss {c['warm_misses']}/"
              f"{c['warm_requests_checked']} alloc {c['allocation_failures']} | flags "
              f"{[k for k, v in c['binding_flags'].items() if v]} breach {c['breach']} harness_ok "
              f"{c['harness_valid']} B/tok {c['load_bytes_per_host_hit_token']}")
        g = c["diagnostics"]
        print(f"   diag: scrape cov {g['scrape_coverage_window']:.2f} upstream med {f(g['upstream_of_engine_window'])} "
              f"max {f(g['upstream_of_engine_window'], 'max')} | engine q med {f(g['engine_queue_window'])} max "
              f"{f(g['engine_queue_window'], 'max')} wait max {f(g['engine_waiting_window'], 'max')} | kv med "
              f"{f(g['kv_usage_window'])} | gpu {f(g['gpu_util_window'])} | api {f(g['api_cores_window'])} thr "
              f"{f(g['api_max_thread_cores_window'])} | served {g['served_req_per_s_window']:.2f} req/s window, "
              f"{g['served_req_per_s_drain']} drain | body offered {g['offered_body_mb_per_s']:.0f} MB/s served "
              f"{g['served_body_mb_per_s_window']:.0f}")


if __name__ == "__main__":
    main()
