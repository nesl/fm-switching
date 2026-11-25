#!/usr/bin/env python3
"""Addendum to item 2 (also D241): host-tier OCCUPANCY and whether an idle history can be evicted
from host at all. CPU only, read-only, no images. D240: 1x and kv0.5r reported separately.

TWO host channels, reported side by side because they disagree and the disagreement is the finding:
  ENGINE  (host_counters_d211.log): vllm:kv_offload_store_bytes_total rate (steady vs bursty) and
          vllm:kv_offload_cpu_cache_usage_perc (peak). The vLLM server's own automatic KV offload.
  POLICY  (coordinator_result.json memory_pressure, the TRUSTED channel; arm_stats.pd_free_kv_* and
          cloud.gpu_kv_fraction are UNTRUSTED when metrics_health=never_scraped, so not used):
          pressure.{peak_tokens, host_peak_tokens, epochs_over_cap, host_epochs_over_cap} and
          enact_placement_totals.{offloaded, evicted, kept_warm, resident}.

Decides: does the 27 GiB (110,592-token) host tier ever FILL under rung 3, can an idle robot history
be EVICTED from host, and do engine store bytes count RE-STORES (so turnover is churn not eviction)?
Cross-checks A6000's note that six kv0.5r cells report peak_tokens 32,470 and evicted 6 identically.
"""
from __future__ import annotations
import glob, gzip, json, os, re, statistics, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/lib"))
from _provenance import stamp  # noqa: E402

HOST_CAP_TOKENS = 110592
BYTES_PER_TOKEN = 262144
HOST_CAP_BYTES = HOST_CAP_TOKENS * BYTES_PER_TOKEN
T_RE = re.compile(r"^t=([0-9.]+)")
STORE_RE = re.compile(r"vllm:kv_offload_store_bytes_total=([0-9.eE+]+)")
USAGE_RE = re.compile(r"vllm:kv_offload_cpu_cache_usage_perc=([0-9.eE+]+)")


def agree(d):
    hp = os.path.join(d, "header.json")
    if not os.path.exists(hp):
        return "ABSENT"
    try:
        sa = json.load(open(hp)).get("source_agreement")
    except Exception:
        return "ABSENT"
    if sa is None:
        return "ABSENT"
    if isinstance(sa, dict):
        return sa.get("verdict") or "ABSENT"
    return sa if isinstance(sa, str) else str(sa)


def policy_channel(d):
    """coordinator_result.json memory_pressure (trusted). Returns the policy-side host facts."""
    cp = os.path.join(d, "coordinator_result.json")
    if not os.path.exists(cp):
        return {}
    mp = (json.load(open(cp)).get("memory_pressure") or {})
    pr = mp.get("pressure") or {}
    ept = mp.get("enact_placement_totals") or {}
    return {
        "gpu_kv_tokens": mp.get("gpu_kv_tokens"),
        "peak_tokens": pr.get("peak_tokens"), "host_peak_tokens": pr.get("host_peak_tokens"),
        "epochs_over_cap": pr.get("epochs_over_cap"),
        "host_epochs_over_cap": pr.get("host_epochs_over_cap"),
        "offloaded": ept.get("offloaded"), "evicted": ept.get("evicted"),
        "kept_warm": ept.get("kept_warm"), "resident": ept.get("resident"),
    }


def parse_log(d):
    path = os.path.join(d, "host_counters_d211.log")
    opener, p = (open, path) if os.path.exists(path) else (gzip.open, path + ".gz")
    store, usage = {}, {}
    with opener(p, "rt") as f:
        for line in f:
            mt = T_RE.match(line)
            if not mt:
                continue
            t = float(mt.group(1))
            ms, mu = STORE_RE.search(line), USAGE_RE.search(line)
            if ms:
                store[t] = float(ms.group(1))
            if mu:
                usage[t] = float(mu.group(1))
    return sorted(store.items()), sorted(usage.items())


def mid60_window(pts):
    t0, t1 = pts[0][0], pts[-1][0]
    lo, hi = t0 + 0.2 * (t1 - t0), t0 + 0.8 * (t1 - t0)
    return [(t, v) for t, v in pts if lo <= t <= hi]


def steady_rate(pts):
    w = mid60_window(pts)
    if len(w) < 2 or w[-1][0] == w[0][0]:
        return None
    return (w[-1][1] - w[0][1]) / (w[-1][0] - w[0][0])


def burstiness(store):
    """Per-60 s bin store rate over the whole run; return (mean, max, max/mean) in tokens/s."""
    if len(store) < 3:
        return None
    bins = {}
    for i in range(1, len(store)):
        (ta, va), (tb, vb) = store[i - 1], store[i]
        dt = tb - ta
        if dt <= 0:
            continue
        rate = (vb - va) / dt / BYTES_PER_TOKEN
        bins.setdefault(int(ta // 60), []).append(rate)
    binrates = [statistics.mean(v) for v in bins.values() if v]
    if not binrates:
        return None
    mean = statistics.mean(binrates)
    mx = max(binrates)
    return {"bin_mean_tokens_s": round(mean, 2), "bin_max_tokens_s": round(mx, 2),
            "max_over_mean": round(mx / mean, 2) if mean > 0 else None,
            "n_bins": len(binrates), "bursty": (mx / mean > 2.0) if mean > 0 else None}


def cells_for():
    out = {"1x": [], "kv0.5r": []}
    for mem, tag in (("1x", ""), ("kv0.5r", "_kv0.5r")):
        for seed in (4, 5, 6, 7):
            base = f"covex-v6-fair-final_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30"
            for suf in ("_rerun", ""):
                d = RUNS / (base + suf)
                if (d / "host_counters_d211.log").exists() and not agree(str(d)).upper().startswith("INVALID"):
                    out[mem].append(("covex-v6-fair-final", seed, str(d)))
                    break
        for seed in (4, 5, 6, 7):
            d = RUNS / f"llf_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30"
            if (d / "host_counters_d211.log").exists() and not agree(str(d)).upper().startswith("INVALID"):
                out[mem].append(("llf", seed, str(d)))
                break
    return out


def main():
    res = {"1x": {}, "kv0.5r": {}}
    for mem, cells in cells_for().items():
        for arm, seed, d in cells:
            store, usage = parse_log(d)
            rate_b = steady_rate(store)
            uvals = [v for _, v in usage]
            pol = policy_channel(d)
            store_max = store[-1][1] if store else None
            res[mem][f"{arm}_s{seed}"] = {
                "arm": arm, "seed": seed, "agreement": agree(d),
                "engine_store_rate_tokens_s": round(rate_b / BYTES_PER_TOKEN, 3) if rate_b else None,
                "engine_store_max_bytes": store_max,
                "engine_store_max_over_capacity": round(store_max / HOST_CAP_BYTES, 2) if store_max else None,
                "engine_usage_perc_max": round(max(uvals), 4) if uvals else None,
                "engine_host_fills_ever": (max(uvals) >= 0.999) if uvals else None,
                "engine_burstiness": burstiness(store),
                "policy_host_peak_tokens": pol.get("host_peak_tokens"),
                "policy_peak_tokens": pol.get("peak_tokens"),
                "policy_gpu_kv_tokens": pol.get("gpu_kv_tokens"),
                "policy_epochs_over_cap": pol.get("epochs_over_cap"),
                "policy_host_epochs_over_cap": pol.get("host_epochs_over_cap"),
                "policy_offloaded": pol.get("offloaded"), "policy_evicted": pol.get("evicted"),
                "policy_kept_warm": pol.get("kept_warm"), "policy_resident": pol.get("resident"),
            }
    # conclusions over rung-3 cells
    concl = {}
    for mem in ("1x", "kv0.5r"):
        r3 = [v for v in res[mem].values() if v["arm"] == "covex-v6-fair-final"]
        umax = [v["engine_usage_perc_max"] for v in r3 if v["engine_usage_perc_max"] is not None]
        ratios = [v["engine_store_max_over_capacity"] for v in r3
                  if v["engine_store_max_over_capacity"] is not None]
        hpk = [v["policy_host_peak_tokens"] for v in r3 if v["policy_host_peak_tokens"] is not None]
        offl = [v["policy_offloaded"] for v in r3 if v["policy_offloaded"] is not None]
        evic = [v["policy_evicted"] for v in r3 if v["policy_evicted"] is not None]
        concl[mem] = {
            "engine_host_fills_ever": any(v["engine_host_fills_ever"] for v in r3),
            "engine_max_usage_perc": max(umax) if umax else None,
            "engine_store_counts_restores": (max(ratios) > 1.5) if ratios else None,
            "engine_max_store_over_capacity": max(ratios) if ratios else None,
            "policy_max_host_peak_tokens": max(hpk) if hpk else None,
            "policy_total_offloaded": sum(offl) if offl else None,
            "policy_total_evicted": sum(evic) if evic else None,
            "idle_history_evictable_from_host": (
                "NO: policy host_peak_tokens is 0 and offloaded/evicted are 0 (nothing on the policy "
                "host tier to evict); engine host tier peaks well below full"
                if (hpk and max(hpk) == 0 and offl and sum(offl) == 0 and umax and max(umax) < 0.999)
                else "see per-cell"),
        }
    # A6000 cross-check: identical peak_tokens / evicted across kv0.5r cells?
    kv_peak = {k: v["policy_peak_tokens"] for k, v in res["kv0.5r"].items()}
    kv_evic = {k: v["policy_evicted"] for k, v in res["kv0.5r"].items()}
    out = {
        "_what": "Host-tier occupancy addendum (item 2 / D241): engine vs policy host channels, "
                 "does the host fill under rung 3, can an idle history be evicted, do store bytes "
                 "count re-stores. D240: 1x and kv0.5r separate.",
        "constants": {"host_capacity_tokens": HOST_CAP_TOKENS, "host_capacity_bytes": HOST_CAP_BYTES,
                      "bytes_per_token": BYTES_PER_TOKEN, "host_tier_gib": 27},
        "per_cell": res, "conclusions": concl,
        "a6000_crosscheck_kv0.5r": {"policy_peak_tokens": kv_peak, "policy_evicted": kv_evic},
    }
    out["_provenance"] = stamp(script="host_occupancy_addendum.py", model="qwen3vl32b",
                               device="jetson_orin", n=sum(len(v) for v in res.values()))
    outdir = REPO / "results/orchestration/live2/robot_idle"
    (outdir / "host_occupancy_addendum.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "host_occupancy_addendum.json")
    for mem in ("1x", "kv0.5r"):
        c = concl[mem]
        print(f"  rung3 {mem}: engine_fills={c['engine_host_fills_ever']} "
              f"engine_max_usage={c['engine_max_usage_perc']} restores={c['engine_store_counts_restores']} "
              f"policy_host_peak={c['policy_max_host_peak_tokens']} offloaded={c['policy_total_offloaded']} "
              f"evicted={c['policy_total_evicted']}")
    print("  kv0.5r policy peak_tokens:", kv_peak)
    print("  kv0.5r policy evicted:", kv_evic)
    return out


if __name__ == "__main__":
    main()
