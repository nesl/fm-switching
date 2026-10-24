#!/usr/bin/env python3
"""StudyRH8 analysis (original .venv, CPU). Pre-registered decision rule (research/EXPERIMENTS.md, StudyRH8).

Per cell: RH7's metrics (study_rh6_analyse.cell_stats + study_rh7_analyse.extra; RH7 binding-attribution rule), over ALL
in-window escalations and separately for high- and low-demand devices (and, in the MIX cells, for eager vs lazy
devices): escalation TTFT p50/p90/p99/max, computed tokens per escalation, host reload TB, analytic live set (eager
devices) vs 256 GiB, fallbacks, and the fraction of escalations meeting T in {2, 5, 15} s.
Fraction within T (fixed before the fleet): denominator = in-window escalations excluding over-context HTTP 400s (the
prompt is identical in every policy, so these are policy-independent invalid requests); numerator = escalations with
TTFT <= T (TTFT of a cache-miss fallback is from the original submit); censored or other failed escalations count as
misses.
DECISION (per D): DEMAND-AWARE ALLOCATION WINS iff frac5(MIX-DEMAND) - max(frac5(ALL-EAGER), frac5(ALL-LAZY),
frac5(MIX-RANDOM)) >= 0.05; else COORDINATION NOT SHOWN, and the pure policy that dominates (higher frac5) is reported
with its binding resource. T = 2 and 15 s reported alongside. Not pre-registered (reported as supplementary): device-
clustered bootstrap CI of each difference; the D=64 repeats vs RH7 (run-to-run variance).
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402
import study_rh6_analyse as A6  # noqa: E402
import study_rh7_analyse as A7  # noqa: E402

D_ = Path("results/cost/study_rh8")
DEV = "h100nvl"
TS = (2.0, 5.0, 15.0)
POL = ("ALL-EAGER", "ALL-LAZY", "MIX-RANDOM", "MIX-DEMAND")
MARGIN = 0.05
NBOOT = 2000


def over_context(r):
    e = r["error"] or ""
    return e.startswith("HTTP 400") and ("context" in e or "length" in e) and "Cache miss" not in e


def esc_rows(rr):
    return [r for r in rr if r["kind"] == "escalation" and r["in_window"] and not over_context(r)]


def within(rows, T):
    return sum(1 for r in rows if not r["error"] and r["ttft_s"] is not None and r["ttft_s"] <= T)


def group(rows):
    tt = [r["ttft_s"] for r in rows if not r["error"] and r["ttft_s"] is not None]
    ok = [r for r in rows if not r["error"]]
    comp = sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in ok)
    return dict(n=len(rows), failed=sum(bool(r["error"]) for r in rows), ttft_s=A6.dist(tt),
                computed_tokens_per_escalation_esc_only=comp / len(ok) if ok else None,
                fallbacks=sum(bool(r.get("fallback")) for r in rows),
                frac_within={f"{T:g}s": within(rows, T) / len(rows) if rows else None for T in TS})


def live_set(sp):
    try:
        import study_rh2_knee_surface as H
        import study_rh6_offload_knee as R6
    except Exception:  # noqa: BLE001
        return None
    eg = set(sp["eager_devices"])
    if not eg:
        return None
    p, o = H.plan(sp["D"])
    pk, mn = R6.live_resident([x for d, x in enumerate(p) if d in eg], [x for d, x in enumerate(o) if d in eg],
                              R6.TOK_IMG["D2"])
    return dict(peak_tokens=pk, mean_tokens=mn, peak_gib=pk * A6.BPT / 2 ** 30, peak_over_capacity=pk / A6.CAP_TOKENS[256])


def boot_diff(a_rows, b_rows, T, seed=0):
    """Device-clustered bootstrap of frac_T(a) - frac_T(b) (both cells share the device index; resample devices)."""
    by_a, by_b = {}, {}
    for r in a_rows:
        by_a.setdefault(r["device"], []).append(r)
    for r in b_rows:
        by_b.setdefault(r["device"], []).append(r)
    devs = sorted(set(by_a) | set(by_b))
    rng = random.Random(seed)
    out = []
    for _ in range(NBOOT):
        s = [rng.choice(devs) for _ in devs]
        ra = [r for d in s for r in by_a.get(d, [])]
        rb = [r for d in s for r in by_b.get(d, [])]
        if ra and rb:
            out.append(within(ra, T) / len(ra) - within(rb, T) / len(rb))
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))] if out else None


def main():
    meta = json.loads((D_ / f"study_rh8_run_meta_{DEV}.json").read_text())
    R = list(read_jsonl(D_ / f"study_rh8_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_rh8_metrics_{DEV}.jsonl")}
    P = {m["cell"]: m["samples"] for m in read_jsonl(D_ / f"study_rh8_cpu_{DEV}.jsonl")}
    out = dict(servers=[{k: s.get(k) for k in ("stage", "kv_cache_tokens", "kv_offloading_gib", "mm_processor_cache_gb",
                                               "flash_attention_version", "cuda_graphs", "host_mem", "startup_s")}
                        for s in meta["servers"]], stack=meta.get("stack"), estimate=meta.get("estimate"), cells={})
    ESC = {}
    for tag, e in meta["experiments"].items():
        sp = e["spec"]
        rr = [r for r in R if r["cell"] == tag]
        o = A6.cell_stats(tag, e, rr, M.get(tag, []), P.get(tag, []))
        o.update(policy=sp["policy"], demand=sp["demand"], eager_devices=len(sp["eager_devices"]),
                 eager_and_high=len(set(sp["eager_devices"]) & set(sp["high_demand_devices"])),
                 window_plan=e.get("window_plan"), **A7.extra(e, rr, M.get(tag, [])))
        o["binding"] = A7.binding(o)
        o["host_reload_tb"] = o["pcie_load_gb"] / 1000
        o["live_set"] = live_set(sp)
        es = esc_rows(rr)
        ESC[tag] = es
        o["all"] = group(es)
        o["high_demand"] = group([r for r in es if r["high_demand"]])
        o["low_demand"] = group([r for r in es if not r["high_demand"]])
        o["eager_devices_esc"] = group([r for r in es if r["device_policy"] == "EAGER"])
        o["lazy_devices_esc"] = group([r for r in es if r["device_policy"] == "LAZYD"])
        o["escalations_excluded_over_context"] = sum(1 for r in rr if r["kind"] == "escalation" and r["in_window"]
                                                     and over_context(r))
        out["cells"][tag] = o
    C = out["cells"]
    dec = {}
    for D in sorted({c["D"] for c in C.values() if c["policy"] in POL}):
        cs = {p: C.get(f"RH8_{p}_D{D}") for p in POL}
        if not all(cs.values()):
            dec[D] = dict(complete=False)
            continue
        fr = {p: {k: cs[p]["all"]["frac_within"][k] for k in ("2s", "5s", "15s")} for p in POL}
        row = dict(frac_within=fr, binding={p: cs[p]["binding"] for p in POL})
        for k in ("2s", "5s", "15s"):
            rivals = {p: fr[p][k] for p in POL if p != "MIX-DEMAND"}
            best = max(rivals, key=rivals.get)
            T = float(k[:-1])
            row[f"margin_{k}"] = dict(mix_demand=fr["MIX-DEMAND"][k], best_rival=best, best_rival_value=rivals[best],
                                      margin=fr["MIX-DEMAND"][k] - rivals[best],
                                      boot95_device_clustered=boot_diff(ESC[f"RH8_MIX-DEMAND_D{D}"],
                                                                        ESC[f"RH8_{best}_D{D}"], T))
        m5 = row["margin_5s"]["margin"]
        row["verdict"] = "DEMAND-AWARE ALLOCATION WINS" if m5 >= MARGIN else "COORDINATION NOT SHOWN"
        pure = max(("ALL-EAGER", "ALL-LAZY"), key=lambda p: fr[p]["5s"])
        row["dominant_pure_policy"] = dict(policy=pure, frac5=fr[pure]["5s"], binding=cs[pure]["binding"],
                                           tie=fr["ALL-EAGER"]["5s"] == fr["ALL-LAZY"]["5s"])
        dec[D] = row
    # run-to-run variance (not pre-registered as a decision): repeats vs RH7
    rh7 = json.loads(Path("results/cost/study_rh7/study_rh7_results_h100nvl.json").read_text())["cells"]
    var = {}
    for rep, ref in (("RH8_REP-EAGER_D64", "RH7_EAGER_D64"), ("RH8_REP-LAZYD_D64", "RH7_LAZYD_D64")):
        if rep in C and ref in rh7:
            a, b = C[rep]["esc_ttft_s"], rh7[ref]["esc_ttft_s"]
            var[rep] = dict(reference=ref, **{f"{k}_rh8": a[k] for k in ("median", "p90", "p99", "max")},
                            **{f"{k}_rh7": b[k] for k in ("median", "p90", "p99", "max")},
                            **{f"{k}_ratio": a[k] / b[k] for k in ("median", "p90", "p99", "max")},
                            hit_rh8=C[rep]["esc_hit"], hit_rh7=rh7[ref]["esc_hit"],
                            n_rh8=C[rep]["escalations"], n_rh7=rh7[ref]["escalations"])
    out["decision"] = dict(per_D=dec, rule=f"MIX-DEMAND frac(TTFT<=5 s) - best rival >= {MARGIN}",
                           run_to_run_variance=var,
                           stop_checks=dict(host_verification={t: (c["host_verification"] or {}).get("verified")
                                                               for t, c in C.items()},
                                            fallback_frac={t: c["fallback_frac"] for t, c in C.items()}))
    out["_provenance"] = stamp(script="study_rh8_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(R))
    (D_ / f"study_rh8_results_{DEV}.json").write_text(json.dumps(out, indent=1, default=float))
    print("DECISION:", json.dumps(out["decision"], indent=1, default=float))
    f = lambda d, k="median": "—" if not d else f"{d[k]:.2f}"  # noqa: E731
    for t, c in C.items():
        g = c["diagnostics"]
        print(f"{t:22s} esc {c['all']['n']:3d} p50 {f(c['all']['ttft_s'])} p90 {f(c['all']['ttft_s'], 'p90')} p99 "
              f"{f(c['all']['ttft_s'], 'p99')} max {f(c['all']['ttft_s'], 'max')} | within2/5/15 "
              f"{'/'.join(f'{v:.3f}' for v in c['all']['frac_within'].values())} | hi "
              f"{f(c['high_demand']['ttft_s'])}/{f(c['high_demand']['ttft_s'], 'p99')} lo "
              f"{f(c['low_demand']['ttft_s'])}/{f(c['low_demand']['ttft_s'], 'p99')} | app {c['appends']} | reload "
              f"{c['host_reload_tb']:.2f} TB | comp/esc {c['computed_tokens_per_escalation']} | up "
              f"{f(g['upstream_of_engine_window'])} engq {f(g['engine_queue_window'])} | drain {c['drain_s']} cens "
              f"{c['censored']} fb {c['fallbacks']} ({c['fallback_frac']:.4f}) | {c['binding']}")


if __name__ == "__main__":
    main()
