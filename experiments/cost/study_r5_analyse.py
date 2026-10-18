#!/usr/bin/env python3
"""StudyR5 analysis (original .venv, CPU). Metrics as pre-registered (research/EXPERIMENTS.md, StudyR5).

Per cell (policy, D, escalation fraction): in-window escalation TTFT / latency distributions, escalation token hit
rate (sum cached / sum prompt), server prefix-cache hit rate over the window (counter deltas), preemptions, KV usage,
append compute (sum of prompt - cached over appends; share of all computed prompt tokens; summed append latency),
throughput, and D* = smallest D where P-WARM escalation hit rate < 50%.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from rawio import read_jsonl  # noqa: E402
from _provenance import stamp  # noqa: E402

D_ = Path("results/cost/study_r5")
DEV = "h100nvl"


def dist(v):
    v = np.array([x for x in v if x is not None], float)
    if not len(v):
        return None
    return dict(n=int(len(v)), median=float(np.median(v)), p90=float(np.percentile(v, 90)),
                p99=float(np.percentile(v, 99)), max=float(v.max()))


def delta(tl, key, t0, t1):
    w = [x for x in tl if key in x and t0 <= x["t"] <= t1]
    return (w[-1][key] - w[0][key]) if len(w) >= 2 else None


def main():
    meta = json.loads((D_ / f"study_r5_run_meta_{DEV}.json").read_text())
    R = list(read_jsonl(D_ / f"study_r5_requests_{DEV}.jsonl"))
    M = {m["cell"]: m["timeline"] for m in read_jsonl(D_ / f"study_r5_metrics_{DEV}.jsonl")}
    out = dict(kv_capacity={s["stage"]: s.get("kv_cache_tokens") for s in meta.get("servers", [])},
               probe=meta.get("probe"), mechanism_check_D1=meta.get("mechanism_check_D1"), cells={})
    for tag, e in meta["experiments"].items():
        rr = [r for r in R if r["cell"] == tag]
        win = [r for r in rr if r["in_window"] and not r["error"]]
        esc = [r for r in win if r["kind"] == "escalation"]
        app = [r for r in win if r["kind"] == "append"]
        comp = lambda xs: sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in xs)  # noqa: E731
        t0 = e["window_start"]
        t1 = t0 + e["window_s"]
        tl = M.get(tag, [])
        q = delta(tl, "prefix_cache_queries_total", t0, t1)
        h = delta(tl, "prefix_cache_hits_total", t0, t1)
        kv = [x["kv_cache_usage_perc"] for x in tl if "kv_cache_usage_perc" in x and t0 <= x["t"] <= t1]
        wai = [x.get("num_requests_waiting", 0) for x in tl if t0 <= x["t"] <= t1]
        out["cells"][tag] = dict(
            policy=e["policy"], D=e["D"], esc_frac=e["esc_frac"], seed=e["seed"], warmup_s=e["warmup_s"],
            inflight_at_window_end=e["inflight_at_window_end"], drain_s=e["drain_s"],
            n_requests=len(rr), errors=sum(bool(r["error"]) for r in rr),
            escalations=len(esc), escalation_ttft_s=dist([r["ttft_s"] for r in esc]),
            escalation_latency_s=dist([r["latency_s"] for r in esc]),
            escalation_prompt_tokens=dist([r["prompt_tokens"] for r in esc]),
            escalation_token_hit=(sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0
                                                                                         for r in esc))),
            escalation_hit_per_request_median=float(np.median([(r["cached_tokens"] or 0) / r["prompt_tokens"]
                                                               for r in esc])) if esc else None,
            server_prefix_hit_rate=(h / q) if q else None, preemptions=delta(tl, "num_preemptions_total", t0, t1),
            kv_usage_mean=float(np.mean(kv)) if kv else None, kv_usage_max=float(max(kv)) if kv else None,
            waiting_mean=float(np.mean(wai)) if wai else None, waiting_max=float(max(wai)) if wai else None,
            appends=len(app), append_computed_tokens=comp(app),
            append_share_of_computed=comp(app) / max(1, comp(win)),
            append_latency_sum_s=float(sum(r["latency_s"] for r in app)),
            computed_prompt_tok_per_s=comp(win) / e["window_s"],
            escalations_per_min=len(esc) / (e["window_s"] / 60))
    full = {c["D"]: c for t, c in out["cells"].items() if c["policy"] == "WARM" and c["esc_frac"] == 1.0
            and t.startswith("R5_WARM_D") and "rep" not in t}
    below = sorted(D for D, c in full.items() if c["escalation_token_hit"] < 0.5)
    out["D_star_warm_hit_below_50pct"] = below[0] if below else None
    out["_provenance"] = stamp(script="study_r5_analyse.py", model="qwen3vl-32b-instruct", device=DEV, n=len(R))
    (D_ / f"study_r5_results_{DEV}.json").write_text(json.dumps(out, indent=1))
    print("KV capacity:", out["kv_capacity"], "D*:", out["D_star_warm_hit_below_50pct"])
    for t, c in out["cells"].items():
        tt = c["escalation_ttft_s"] or {}
        print(f"{t:22s} esc {c['escalations']:4d} hit {c['escalation_token_hit']:.2f} srv {c['server_prefix_hit_rate'] or 0:.2f} "
              f"TTFT med {tt.get('median', 0):.2f} p90 {tt.get('p90', 0):.2f} p99 {tt.get('p99', 0):.2f} max {tt.get('max', 0):.2f} "
              f"preempt {c['preemptions']} kvmax {c['kv_usage_max']} appends {c['appends']} share {c['append_share_of_computed']:.2f} "
              f"err {c['errors']} inflight {c['inflight_at_window_end']}")


if __name__ == "__main__":
    main()
