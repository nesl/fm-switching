#!/usr/bin/env python3
"""D213 item 2, Step 2b: the scraped value reaches the DECISION, with its declared type and value.

Three links, each run on both trees, NO SERVER and NO CELL:

  A. `AsyncLive2Backend.metrics()` -> `CoordState.metrics`               (the wire the fix adds)
  B. `CoordState.metrics` -> `Observation.cloud.gpu_kv_fraction`         (`cstate.py:663`)
  C. `Observation.cloud.gpu_kv_fraction` -> rung 4's free-KV estimate    (`arms_v6cf.py:306`)

Link A is exactly what `coordinator.py:489` does (`self.st.metrics = self.be.metrics()`) and is
performed here by that same assignment, so the proof is of the real path and not of a copy of it.
Link C reports `_pd_free_kv` AND the arm's own `pd_kv_bound_by_engine_metric` /
`pd_kv_bound_by_belief` counters, which is the decision the value changes.

ALSO PROVED HERE, because its absence is what made the whole chain inert: `cstate.py:657`'s
`vllm:num_requests_waiting` is NOT published, so `cloud.queued_by_class` is unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GPU_KV = 62_944
HOST_GIB = 27.0
HOST_TOK = 48_000
SCRAPE_FRAC = 0.7215447154471545          # the committed H100 probe's value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tree = Path(a.tree).resolve()
    L = tree / "experiments/orchestration/live2"
    for q in (L, L / "hybrid", L / "fleet", L / "v5",
              tree / "experiments/orchestration/baselines",
              tree / "experiments/orchestration/baselines/reconstructed",
              tree / "experiments/orchestration/sim", tree / "experiments/lib",
              tree / "experiments/dashcam"):
        sys.path.insert(0, str(q))
    import asyncbackend as AB
    import cstate as CS

    fixed = hasattr(AB.AsyncLive2Backend, "KV_KEYS")
    doc = {"tree": str(tree), "fix_present": fixed}

    # ---- link A: build a backend WITHOUT the asyncio loop, hand it one scraped snapshot
    be = AB.AsyncLive2Backend.__new__(AB.AsyncLive2Backend)
    be.first_gap_ms, be.wire_extra_ms, be.submit_total_ms = [], [], []
    be.callback_errors, be.img_parts, be.img_parts_with_uuid = [], {}, {}
    be.n_built, be.build_s, be.cache = 0, 0.0, None
    if fixed:
        be.metrics_scrape = True
        be.metrics_interval_s = 0.2
        be._kv_last_good = (SCRAPE_FRAC, 0.0)
        be._metrics_failures = {"n": 0, "last": None, "n_served_last_good": 0,
                                "n_served_unknown": 0, "n_kv_key_missing": 0,
                                "n_kv_key_aliased": 1,
                                "kv_key_seen": "vllm:kv_cache_usage_perc", "n_polls": 1}
        be._engine_metrics = {
            AB.AsyncLive2Backend.KV_CANONICAL_KEY: SCRAPE_FRAC,
            "fm_kv_state": "observed", "fm_kv_source_key": "vllm:kv_cache_usage_perc",
            "fm_kv_age_s": 0.0, "fm_metrics_degraded": 0.0,
            "fm_host_counters": {"vllm:prompt_tokens_by_source_total|source=external_kv_transfer":
                                 4943072.0}}
    m = be.metrics()
    doc["A_metrics_keys_vllm"] = sorted(k for k in m if str(k).startswith("vllm:"))
    doc["A_metrics_type"] = type(m).__name__
    doc["A_has_metrics_health"] = "metrics_health" in m
    doc["A_num_requests_waiting_published"] = "vllm:num_requests_waiting" in m
    doc["A_reader_gets"] = m.get("vllm:gpu_cache_usage_perc", 0.0)
    doc["A_reader_gets_type"] = type(m.get("vllm:gpu_cache_usage_perc", 0.0)).__name__

    # ---- link B: coordinator.py:489's own assignment, then cstate's own observation()
    st = CS.CoordState(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK)
    st.metrics = m                                     # == coordinator.py:489
    st.sessions["s1"] = CS.SessionRec(session_id="s1", device_id="rob1", est_tokens=11000,
                                      built_tokens=11000,
                                      belief={"gpu": 1.0, "host": 0.0, "cold": 0.0})
    obs = st.observation(now=100.0, epoch="tick")
    doc["B_gpu_kv_fraction"] = obs.cloud.gpu_kv_fraction
    doc["B_gpu_kv_fraction_type"] = type(obs.cloud.gpu_kv_fraction).__name__
    doc["B_queued_by_class"] = dict(obs.cloud.queued_by_class)

    # ---- link C: the one gate the census says should move
    import arms as A
    arm = A.make_arm("covex-v6-cf-pd-c5attr")
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                        host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
    try:
        arm._rules._roster = {"built_tokens_by_session": {"s1": 11000}}
    except Exception as e:                                                # noqa: BLE001
        doc["C_roster_error"] = f"{type(e).__name__}: {e}"
    before_counts = dict(getattr(arm, "stats", {}) or {})
    free = arm._pd_free_kv(obs)
    after_counts = dict(getattr(arm, "stats", {}) or {})
    doc["C_free_kv_tokens"] = free
    doc["C_pool"] = getattr(arm, "_pd_gpu_kv_tokens", None)
    doc["C_bound_by"] = {k: after_counts.get(k, 0) - before_counts.get(k, 0)
                         for k in ("pd_kv_bound_by_engine_metric", "pd_kv_bound_by_belief")}

    Path(a.out).write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
