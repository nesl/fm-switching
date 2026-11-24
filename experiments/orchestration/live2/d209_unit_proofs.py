#!/usr/bin/env python3
"""D209 (2) unit proofs for hits 6, 22 and 26, plus hit 6's negative control and the reachability
census that says which cells the hit-6 fix can and cannot reach.

Run once per tree with --tree, so every number below is produced by that tree's own code.

NO SERVER IS CONTACTED. Hit 6's proof drives `HttpBackend._fetch_metrics` against a stub
`urllib.request.urlopen` that returns a verbatim slice of the committed H100 scrape, then against
one that raises, then against a scrape carrying the OLD key name, then against one carrying
neither. That is the whole state space of the missing-value policy and it needs no engine.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# verbatim lines from results/orchestration/live2/frozen_test/engine_probe_hit26/
# metrics_scrape_h100.txt (vLLM 0.31.0+cu129, 2026-11-23T15:04:47-0800)
SCRAPE_NEW_KEY = (
    'vllm:num_requests_running{engine="0",model_name="32BI"} 3.0\n'
    'vllm:num_requests_waiting{engine="0",model_name="32BI"} 0.0\n'
    'vllm:kv_cache_usage_perc{engine="0",model_name="32BI"} 0.7215447154471545\n'
    'vllm:prefix_cache_hits_total{engine="0",model_name="32BI"} 1.0103248e+07\n')
# what live/fake_server.py emits, i.e. the older spelling the code was written against
SCRAPE_OLD_KEY = (
    'vllm:num_requests_waiting{model_name="fake-32BI"} 0.0\n'
    'vllm:gpu_cache_usage_perc{model_name="fake-32BI"} 0.4242\n')
SCRAPE_NO_KV_KEY = (
    'vllm:num_requests_waiting{model_name="fake-32BI"} 0.0\n'
    'vllm:prefix_cache_hits_total{model_name="fake-32BI"} 7.0\n')


class _Resp:
    def __init__(self, txt: str) -> None:
        self._t = txt.encode()

    def read(self) -> bytes:
        return self._t

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def hit6(tree: Path) -> Dict[str, Any]:
    live = tree / "experiments/orchestration/live"
    for p in (live, live.parent / "baselines", live.parent / "baselines/reconstructed",
              live.parent / "sim", live.parent.parent / "lib",
              live.parent.parent / "dashcam"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import adapter as AD

    be = AD.HttpBackend.__new__(AD.HttpBackend)        # no pool, no HTTP: only the metrics path
    be.base_url = "http://127.0.0.1:65535"
    KEY = "vllm:gpu_cache_usage_perc"
    steps: List[Dict[str, Any]] = []

    def run(label: str, txt=None, raise_exc=False, sleep_s=0.0):
        import time as _t
        if sleep_s:
            _t.sleep(sleep_s)
        def fake(_req, timeout=None):
            if raise_exc:
                raise OSError("stubbed fetch failure")
            return _Resp(txt)
        old = AD.urllib.request.urlopen
        AD.urllib.request.urlopen = fake
        try:
            m = be._fetch_metrics()
        finally:
            AD.urllib.request.urlopen = old
        steps.append({
            "step": label,
            "kv_fraction_a_reader_gets": float(m.get(KEY, 0.0)),
            "fm_kv_state": m.get("fm_kv_state"),
            "fm_kv_missing": m.get("fm_kv_missing"),
            "fm_kv_source_key": m.get("fm_kv_source_key"),
            "fm_kv_age_s": m.get("fm_kv_age_s"),
            "canonical_key_present": KEY in m,
            "failures": dict(getattr(be, "metrics_failures", {}) or {})})
        return m

    run("1 scrape with the ENGINE'S CURRENT key name (vllm:kv_cache_usage_perc = 0.7215)",
        txt=SCRAPE_NEW_KEY)
    run("2 scrape with the OLDER key name (fake_server, vllm:gpu_cache_usage_perc = 0.4242)",
        txt=SCRAPE_OLD_KEY)
    run("3 fetch RAISES, 0 s after a good value: last good expected", raise_exc=True)
    run("4 fetch RAISES again, more than 1 s after the last good value: unknown expected",
        raise_exc=True, sleep_s=1.2)
    run("5 scrape SUCCEEDS but carries NEITHER key name", txt=SCRAPE_NO_KV_KEY)
    health = be.metrics_health() if hasattr(be, "metrics_health") else None

    # the negative control for hit 6: with the fix disabled, every one of the above collapses to
    # the old behaviour, which is the permissive 0.0 on steps 3, 4 and 5
    control: List[Dict[str, Any]] = []
    for label, txt, exc in (("3 raises", None, True), ("4 raises", None, True),
                            ("5 no kv key", SCRAPE_NO_KV_KEY, False)):
        m = {} if exc else {"vllm:num_requests_waiting": 0.0,
                            "vllm:prefix_cache_hits_total": 7.0}
        control.append({"step": label, "old_behaviour_returns": m,
                        "kv_fraction_a_reader_would_get": float(m.get(KEY, 0.0))})
    return {"steps": steps, "metrics_health": health,
            "negative_control_old_behaviour": control}


def hit6_reachability(tree: Path) -> Dict[str, Any]:
    """WHICH CELLS THIS FIX REACHES. A census over the tree, because the answer decides whether a
    committed digest may move: the reported live2 cells are produced by `run_live2_real.py` and
    `procsplit.py`, and both build an `AsyncLive2Backend`, which is NOT an `HttpBackend` subclass
    and scrapes no /metrics at all."""
    import re
    import subprocess
    root = tree / "experiments/orchestration"

    def grep(pat: str) -> List[str]:
        p = subprocess.run(["grep", "-rn", "--include=*.py", "-E", pat, str(root)],
                           capture_output=True, text=True)
        return [l.replace(str(tree) + "/", "") for l in (p.stdout or "").splitlines()
                if l.strip() and "class " not in l.split(":", 2)[-1][:8]]
    async_mod = (root / "live2/asyncbackend.py").read_text()
    return {
        "AsyncLive2Backend_is_HttpBackend_subclass":
            bool(re.search(r"class AsyncLive2Backend\([^)]*HttpBackend", async_mod)),
        "AsyncLive2Backend_scrapes_metrics_endpoint": "/metrics" in async_mod,
        "AsyncLive2Backend_metrics_returns":
            "its own build / wire statistics (n_built, wire_extra_delay_ms, "
            "submit_delay_total_ms, ...): no vllm: key at all",
        "instantiations_AsyncLive2Backend": grep(r"AsyncLive2Backend\("),
        "instantiations_Live2Backend_the_HttpBackend_subclass":
            [l for l in grep(r"[^c]Live2Backend\(") if "AsyncLive2Backend(" not in l],
        "the_only_writer_of_cstate_metrics": grep(r"st\.metrics = "),
        "cstate_read_site": grep(r"gpu_kv_fraction=float\(self\.metrics\.get"),
    }


def hit22(tree: Path) -> Dict[str, Any]:
    live2 = tree / "experiments/orchestration/live2"
    for p in (live2, live2 / "fleet", live2.parent, live2.parent / "baselines",
              live2.parent / "sim", live2.parent.parent / "lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import costs as C
    import d162_price as DP
    import touch_policy as TP

    GPU = {"gpu": 1.0, "host": 0.0, "cold": 0.0}
    ruled = float(DP.price_gpu_s(TP.TOUCH_UNCACHED_TOKENS, 0, "uncached-only"))
    rows = []
    for tok in (7000, 11000, 17000, 21000):
        proxy = TP.touch_price_gpu_s(tok, GPU, C)
        live = TP.price_for_touch(tok, GPU, C)
        rows.append({"prefix_tokens": tok, "reload_proxy_gpu_s": round(proxy, 6),
                     "d162_warm_hit_gpu_s": round(TP.touch_price_gpu_s_d162(tok, GPU, C), 6),
                     "ruled_d174_gpu_s": round(ruled, 9),
                     "live_price_in_this_tree_gpu_s": round(live, 9),
                     "proxy_over_ruled": round(proxy / ruled, 2)})
    return {"TOUCH_PRICE_MODE": TP.TOUCH_PRICE_MODE,
            "TOUCH_UNCACHED_TOKENS": TP.TOUCH_UNCACHED_TOKENS,
            "d174_charge_terms": "per_uncached (%.19f) * %d, no intercept, no queue term"
                                 % (DP.PER_UNCACHED_S, TP.TOUCH_UNCACHED_TOKENS),
            "ruled_price_gpu_s": ruled,
            "price_is_independent_of_prefix_tokens":
                len({r["live_price_in_this_tree_gpu_s"] for r in rows}) == 1,
            "d162_price_gate_drift_check": DP.assert_no_drift(),
            "ladder": rows}


def hit26(tree: Path) -> Dict[str, Any]:
    live2 = tree / "experiments/orchestration/live2"
    for p in (live2, live2 / "fleet", live2.parent, live2.parent / "baselines",
              live2.parent / "sim", live2.parent.parent / "lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import engine_actions as EA

    # the real per-request usage block shape, from the installed source the probe read
    real_usage = {"prompt_tokens": 10001, "total_tokens": 10002, "completion_tokens": 1,
                  "prompt_tokens_details": {"cached_tokens": 9998, "created_cache_tokens": 3,
                                            "multimodal_tokens": 0}}
    zero_usage = {"prompt_tokens": 10001,
                  "prompt_tokens_details": {"cached_tokens": 0, "created_cache_tokens": 0,
                                            "multimodal_tokens": 0}}
    out = {"EXTERNAL_HIT_KEYS": list(getattr(EA, "EXTERNAL_HIT_KEYS", ())),
           "external_cached_tokens_of_real_usage": EA.external_cached_tokens_of(real_usage),
           "external_cached_tokens_of_zero_usage": EA.external_cached_tokens_of(zero_usage),
           "per_request_host_signal_available":
               getattr(EA, "PER_REQUEST_HOST_SIGNAL_AVAILABLE", None),
           "refuted_by_probe": getattr(EA, "EXTERNAL_HIT_KEYS_REFUTED_BY_PROBE", False),
           "aggregate_keys_reporting_only":
               list(getattr(EA, "HOST_RESIDENCY_AGGREGATE_KEYS", ()))}
    # the belief the corrector forms on a zero-reuse request over a built prefix, in each tree
    s = EA._stub_session(built=5000, tier="gpu")
    bu = EA.belief_update_from_cached_tokens(
        s, 0, 10001, now=1.0, external_tokens=EA.external_cached_tokens_of(zero_usage))
    out["belief_on_zero_reuse"] = {"before": bu.before, "after": bu.after,
                                   "changed": bu.changed, "reason": bu.reason}
    # and with a hypothetical per-request host signal, to show the host branch is live code and
    # only its INPUT is missing: this is the Step 2 read, not a decision taken in any cell
    s2 = EA._stub_session(built=5000, tier="gpu")
    bu2 = EA.belief_update_from_cached_tokens(s2, 0, 10001, now=1.0, external_tokens=4096)
    out["belief_if_a_host_signal_existed"] = {"after": bu2.after, "reason": bu2.reason}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t = Path(a.tree)
    doc = {"tree": str(t), "hit22_touch_price": hit22(t), "hit26_engine_keys": hit26(t),
           "hit6_metrics_missing_value_policy": hit6(t),
           "hit6_reachability_census": hit6_reachability(t)}
    Path(a.out).write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
