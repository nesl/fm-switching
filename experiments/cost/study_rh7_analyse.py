#!/usr/bin/env python3
"""StudyRH7 analysis (original .venv, CPU). Pre-registered decision rules (research/EXPERIMENTS.md, StudyRH7).

Per cell: RH6's metrics (study_rh6_analyse.cell_stats: escalation TTFT median/p90/p99/max, append TTFT, token hit,
host share, KV median/max, PCIe, achieved/demand computed tok/s, API cores, GPU util, queue location, waiting max,
in flight at end, drain, errors, warm misses) plus: body MB/s offered/served, processor-cache queries/hits, DELTA
fallbacks, censored requests, computed tokens per escalation, analytic live-set peak vs the 256 GiB host buffer.
Binding resource per cell (rule fixed after Step 0, before the fleet ran; from RH6's queue-location evidence):
  api_server     upstream-of-engine queue median (window) > 10
  else, if the engine queue (running + waiting) median > 1 or any request waited:
    host_capacity  warm-miss fraction > 0.05 or offload allocation failures > 0
    gpu_compute    in-window GPU util median >= 90 % and achieved computed tok/s >= 4,000
    pcie           load GB/s average or best 30-s >= 35
    kv_running_set GPU KV max >= 0.95 with waiting > 0 or preemptions
    (several may hold; none -> 'engine (unattributed)')
  else 'none (below knee)'.
Decisions: (1) PROTOCOL ARTIFACT REMOVED; (2) per-D EAGER vs LAZY / LAZYD gaps and MATERIAL at T in {2, 5, 15} s;
(3) largest D sustained (p99 <= T) per policy and T, and its binding resource.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
import study_rh6_analyse as A6  # noqa: E402

D_ = Path("results/cost/study_rh7")
DEV = "h100nvl"
TS = (2.0, 5.0, 15.0)
ITEM_MB = 2.162688            # processed D2 image (pixel_values 352 x 1536 fp32 + grid), measured offline
RH6_B3 = dict(median=2.294, p99=13.85036, hit=0.5084512884384261)   # RH6 B3 D48 (results/cost/study_rh6)
POL = ("EAGER", "LAZY", "LAZYD")


def live_peaks():
    """Analytic live-set peak (tokens) per D, as RH6 (needs the frame index; None if unavailable here)."""
    try:
        import study_rh2_knee_surface as H
        import study_rh6_offload_knee as R6
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for D in (32, 48, 64, 96):
        p, o = H.plan(D)
        pk, mn = R6.live_resident(p, o, R6.TOK_IMG["D2"])
        out[D] = dict(peak_tokens=pk, mean_tokens=mn, peak_gib=pk * A6.BPT / 2 ** 30,
                      peak_over_capacity=pk / A6.CAP_TOKENS[256])
    return out


def binding(o):
    g = o["diagnostics"]
    up = (g["upstream_of_engine_window"] or {}).get("median", 0)
    eq = (g["engine_queue_window"] or {}).get("median", 0)
    wmax = (o["waiting"] or {}).get("max", 0)
    if up > 10:
        return ["api_server"]
    if eq > 1 or wmax > 0:
        b = []
        if (o["warm_miss_frac"] or 0) > 0.05 or o["allocation_failures"] > 0:
            b.append("host_capacity")
        if (g["gpu_util_window"] or {}).get("median", 0) >= 90 and o["computed_tok_s_achieved"] >= 4000:
            b.append("gpu_compute")
        if o["pcie_load_gbps_avg"] >= 35 or o["pcie_load_gbps_best_30s"] >= 35:
            b.append("pcie")
        if (o["kv_usage"] or {}).get("max", 0) >= 0.95 and (wmax > 0 or (o["preemptions"] or 0) > 0):
            b.append("kv_running_set")
        return b or ["engine (unattributed)"]
    return ["none (below knee)"]


def extra(e, rr, tl):
    t0 = e["window_start"]
    tend = t0 + e["elapsed_window_plus_drain_s"]
    win = [r for r in rr if r["in_window"] and not r["error"]]
    esc = [r for r in win if r["kind"] == "escalation"]
    comp = lambda xs: sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in xs)  # noqa: E731
    warm = [r for r in rr if r["kind"] == "warmup" and not r["error"]]
    C = e["counters"]
    a, b = C["window_start"], C["end"]
    mem = e.get("mem_timeline") or []
    pk = lambda k: max((x[k] for x in mem if x.get(k) is not None), default=None)  # noqa: E731
    ok_ = [r for r in rr if not r["error"]]
    if e["spec"]["policy"] == "LAZY":           # content-hashed: distinct frames per video (prefix-closed sessions)
        per_video = {}
        for r in ok_:
            per_video[r["video_id"]] = max(per_video.get(r["video_id"], 0), r["n_frames"])
        items = sum(per_video.values())
    else:                                       # session-scoped uuids: every frame whose bytes were sent once
        items = sum(r["n_new_frames"] for r in ok_ if not r.get("fallback"))
    app = [r for r in rr if r["kind"] in ("append", "escalation") and r.get("full_equiv_mb")]
    ratio = [r["body_mb"] / r["full_equiv_mb"] for r in app if not r.get("fallback")]
    nf = np.array([r["n_frames"] for r in app]) if app else np.array([])
    near = [r["body_mb"] / r["full_equiv_mb"] for r in app if abs(r["n_frames"] - np.median(nf)) <= 5] if app else []
    return dict(
        fallbacks=sum(bool(r.get("fallback")) for r in rr),
        fallback_frac=sum(bool(r.get("fallback")) for r in rr) / max(1, len(rr)),
        fallback_flag=sum(bool(r.get("fallback")) for r in rr) / max(1, len(rr)) > 0.01,
        host_memory=dict(api_rss_peak_gib=pk("api_rss_gib"), engine_rss_peak_gib=pk("engine_rss_gib"),
                         tree_rss_peak_gib=pk("tree_rss_gib"),
                         mem_available_min_gib=min((x["mem_available_gib"] for x in mem), default=None),
                         kv_offload_buffer_gib=e["spec"]["offload"],
                         processor_cache_items_est=items,
                         processor_cache_est_gib=min(128.0, items * ITEM_MB / 1024),
                         processor_cache_note="estimate: items cached x 2.16 MB (vLLM exposes no cache-size metric); "
                                              "LRU cap 128 GiB; engine-core RSS includes both"),
        body_over_full=A6.dist(ratio), median_history_frames=float(np.median(nf)) if len(nf) else None,
        body_over_full_at_median_history=A6.dist(near),
        censored=e.get("censored", 0), drain_capped=e.get("drain_capped", False),
        errors_non_censored=sum(bool(r["error"]) and not r["error"].startswith("censored") for r in rr),
        computed_tokens_window=comp(win),
        computed_tokens_per_escalation=comp(win) / len(esc) if esc else None,
        computed_tokens_per_escalation_esc_only=comp(esc) / len(esc) if esc else None,
        warmup_computed_tokens=comp(warm),
        body_mb_window=sum(r["body_mb"] for r in rr if r["in_window"]),
        body_mb=A6.dist([r["body_mb"] for r in rr if r["in_window"]]),
        mm_cache_queries=A6.cdelta(a, b, "mm_cache_queries"), mm_cache_hits=A6.cdelta(a, b, "mm_cache_hits"),
        whole_counter_window=[t0, tend], timeline_points=len(tl))


def main():
    meta = json.loads((D_ / f"study_rh7_run_meta_{DEV}.json").read_text())
    R = list(read_jsonl(D_ / f"study_rh7_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_rh7_metrics_{DEV}.jsonl")}
    P = {m["cell"]: m["samples"] for m in read_jsonl(D_ / f"study_rh7_cpu_{DEV}.jsonl")}
    step0 = json.loads((D_ / f"study_rh7_step0_{DEV}.json").read_text())["verdict"]
    lp = live_peaks()
    out = dict(servers=[{k: s.get(k) for k in ("stage", "kv_cache_tokens", "kv_offloading_gib", "mm_processor_cache_gb",
                                               "flash_attention_version", "cuda_graphs", "host_mem", "startup_s")}
                        for s in meta["servers"]],
               stack=meta.get("stack"), estimate=meta.get("estimate"),
               step0={k: v for k, v in step0.items() if k not in ("a_rows", "b_rows")}, live_set=lp, cells={})
    for tag, e in meta["experiments"].items():
        rr = [r for r in R if r["cell"] == tag]
        o = A6.cell_stats(tag, e, rr, M.get(tag, []), P.get(tag, []))
        o.update(policy=e["spec"]["policy"], **extra(e, rr, M.get(tag, [])))
        o["binding"] = binding(o)
        o["live_set"] = lp.get(e["spec"]["D"]) if e["spec"]["policy"] == "EAGER" else None
        out["cells"][tag] = o
    C = out["cells"]
    get = lambda p, D: C.get(f"RH7_{p}_D{D}")  # noqa: E731
    ok = lambda c: c and c["esc_ttft_s"] and not c["drain_capped"]  # noqa: E731
    # rule 1
    e48 = get("EAGER", 48)
    r1 = None
    if e48:
        up = (e48["diagnostics"]["upstream_of_engine_window"] or {}).get("median")
        r1 = dict(upstream_median=up, ttft_median=e48["esc_ttft_s"]["median"], ttft_p99=e48["esc_ttft_s"]["p99"],
                  removed=bool(up is not None and up <= 10 and e48["esc_ttft_s"]["median"] <= 1.5 and
                               e48["esc_ttft_s"]["p99"] <= 10))
    # rule 2
    r2 = {}
    for D in sorted({c["D"] for c in C.values()}):
        e = get("EAGER", D)
        row = dict(EAGER=None, LAZY=None, LAZYD=None)
        for p in POL:
            c = get(p, D)
            if c and c["esc_ttft_s"]:
                row[p] = dict(p50=c["esc_ttft_s"]["median"], p99=c["esc_ttft_s"]["p99"], binding=c["binding"],
                              computed_tokens_per_escalation=c["computed_tokens_per_escalation"],
                              censored=c["censored"])
        for p in ("LAZY", "LAZYD"):
            if row["EAGER"] and row[p]:
                row[f"EAGER_minus_{p}"] = dict(p50=row["EAGER"]["p50"] - row[p]["p50"],
                                               p99=row["EAGER"]["p99"] - row[p]["p99"])
                row[f"material_vs_{p}"] = {f"{T:g}s": (row["EAGER"]["p99"] <= T) != (row[p]["p99"] <= T)
                                           for T in TS}
        r2[D] = row
    # rule 3
    r3 = {}
    for p in POL:
        r3[p] = {}
        for T in TS:
            Ds = [c["D"] for c in C.values() if c["policy"] == p and ok(c) and c["esc_ttft_s"]["p99"] <= T]
            dmax = max(Ds) if Ds else None
            r3[p][f"{T:g}s"] = dict(largest_D=dmax, binding=get(p, dmax)["binding"] if dmax else None,
                                    binding_at_next_D=next((get(p, D)["binding"] for D in sorted(
                                        c["D"] for c in C.values() if c["policy"] == p) if dmax and D > dmax),
                                        None))
    l48 = get("LAZY", 48)
    repro = None
    if l48 and l48["esc_ttft_s"]:
        m, h = l48["esc_ttft_s"]["median"], l48["esc_hit"]
        repro = dict(rh7_median=m, rh6_b3_median=RH6_B3["median"], rh7_p99=l48["esc_ttft_s"]["p99"],
                     rh6_b3_p99=RH6_B3["p99"], rh7_hit=h, rh6_b3_hit=RH6_B3["hit"],
                     median_rel=m / RH6_B3["median"] - 1, hit_rel=h / RH6_B3["hit"] - 1,
                     reproduces=abs(m / RH6_B3["median"] - 1) <= 0.10 and abs(h / RH6_B3["hit"] - 1) <= 0.10)
        repro["verdict"] = "reproduces RH6 B3" if repro["reproduces"] else \
            "does NOT reproduce RH6 B3 within 10 % — processor-cache confound (reported; run continued)"
    out["decision"] = dict(rule1_protocol_artifact_removed=r1, rule2_gaps=r2, rule3_sustained=r3,
                           lazy_d48_reproduction=repro,
                           fallback_flags={t: c["fallback_frac"] for t, c in C.items() if c["fallback_flag"]})
    out["_provenance"] = stamp(script="study_rh7_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(R))
    (D_ / f"study_rh7_results_{DEV}.json").write_text(json.dumps(out, indent=1, default=float))
    print("DECISION:", json.dumps(out["decision"], indent=1, default=float))
    f = lambda d, k="median": "—" if not d else f"{d[k]:.2f}"  # noqa: E731
    for t, c in C.items():
        g = c["diagnostics"]
        print(f"{t:16s} req/s {c['req_per_s_window']:.2f} esc {c['escalations']:3d} med {f(c['esc_ttft_s'])} p90 "
              f"{f(c['esc_ttft_s'], 'p90')} p99 {f(c['esc_ttft_s'], 'p99')} max {f(c['esc_ttft_s'], 'max')} | app "
              f"{f(c['append_ttft_s'])}/{f(c['append_ttft_s'], 'p99')} | hit {c['token_hit']:.3f} host "
              f"{c['host_share_of_hits']} | kv {f(c['kv_usage'])}/{f(c['kv_usage'], 'max')} | pcie avg "
              f"{c['pcie_load_gbps_avg']:.1f} 30s {c['pcie_load_gbps_best_30s']:.1f} | comp {c['computed_tok_s_achieved']:.0f}"
              f"/{c['computed_tok_s_demand']:.0f} per-esc {c['computed_tokens_per_escalation']} | api "
              f"{f(c['api_cores'])} gpu {f(g['gpu_util_window'])} | up {f(g['upstream_of_engine_window'])} engq "
              f"{f(g['engine_queue_window'])} wait {f(c['waiting'], 'max')} infl {c['inflight_at_window_end']} drain "
              f"{c['drain_s']} cens {c['censored']} err {c['errors_non_censored']} fb {c['fallbacks']} miss "
              f"{c['warm_misses']}/{c['warm_requests_checked']} | body {g['offered_body_mb_per_s']:.1f}/"
              f"{g['served_body_mb_per_s_window']:.1f} MB/s | mm {c['mm_cache_hits']:.0f}/{c['mm_cache_queries']:.0f}"
              f" | B/tok {c['load_bytes_per_host_hit_token']} | {c['binding']}")
        hm = c["host_memory"]
        print(f"   mem: api {hm['api_rss_peak_gib']} eng {hm['engine_rss_peak_gib']} tree {hm['tree_rss_peak_gib']} GiB "
              f"avail min {hm['mem_available_min_gib']} | mm cache est {hm['processor_cache_est_gib']:.1f} GiB "
              f"({hm['processor_cache_items_est']} items) | body/full {f(c['body_over_full'])} at median history "
              f"({c['median_history_frames']} frames) {f(c['body_over_full_at_median_history'])} | fb frac "
              f"{c['fallback_frac']:.4f}")


if __name__ == "__main__":
    main()
