#!/usr/bin/env python3
"""D213 item 2: unit proofs for `AsyncLive2Backend`'s /metrics scrape, and item 3's recording site.

NO SERVER IS CONTACTED. `urllib.request.urlopen` is stubbed inside the `asyncbackend` module and
fed VERBATIM LINES from the committed H100 probe
`results/orchestration/live2/frozen_test/engine_probe_hit26/metrics_scrape_h100.txt`, so the key
names under test are the engine's own and not this script's.

Run it with `--tree` pointing at a `git archive` tree (`before/` for the control column, `after/`
for the fix). The BEFORE column is the Step 4 negative control, MEASURED rather than asserted:
with the fix absent a reader's `m.get("vllm:gpu_cache_usage_perc", 0.0)` gets the permissive 0.0
in every state, because `AsyncLive2Backend.metrics()` carries no `vllm:` key at all.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

READER_KEY = "vllm:gpu_cache_usage_perc"          # what cstate.py:663 asks for
CSTATE_QUEUE_KEY = "vllm:num_requests_waiting"    # what cstate.py:657 asks for


def _probe_lines(root: Path, names) -> dict:
    """Verbatim lines from the committed scrape, keyed by bare metric name."""
    txt = (root / "results/orchestration/live2/frozen_test/engine_probe_hit26"
                  "/metrics_scrape_h100.txt").read_text()
    out = {}
    for line in txt.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        bare = line.rpartition(" ")[0].split("{")[0]
        if bare in names:
            out.setdefault(bare, []).append(line)
    return out


class _Resp:
    def __init__(self, text: str) -> None:
        self._t = text.encode()

    def read(self):
        return self._t

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--repo-root", required=True, help="a tree that carries results/ (the probe)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tree = Path(a.tree).resolve()
    L = tree / "experiments/orchestration/live2"
    for q in (L, L / "fleet", tree / "experiments/orchestration/baselines",
              tree / "experiments/lib"):
        sys.path.insert(0, str(q))
    import asyncbackend as AB

    be = AB.AsyncLive2Backend.__new__(AB.AsyncLive2Backend)
    fixed = hasattr(AB.AsyncLive2Backend, "KV_KEYS")
    doc = {"tree": str(tree), "fix_present": fixed, "reader_key": READER_KEY,
           "asyncbackend_has_metrics_string": "/metrics" in (L / "asyncbackend.py").read_text()}

    # ---- the five states, in order, on one backend object
    probe = _probe_lines(Path(a.repo_root).resolve(),
                         {"vllm:kv_cache_usage_perc", "vllm:prompt_tokens_by_source_total",
                          "vllm:external_prefix_cache_hits_total",
                          "vllm:kv_offload_total_bytes_total",
                          "vllm:kv_offload_cpu_cache_usage_perc"})
    current = "\n".join(sum(probe.values(), []))
    older = 'vllm:gpu_cache_usage_perc{engine="0",model_name="32BI"} 0.4242'
    neither = 'vllm:num_requests_waiting{engine="0",model_name="32BI"} 7.0'

    states = [
        ("1 scrape with the engine's CURRENT key, vllm:kv_cache_usage_perc", current, None),
        ("2 scrape with the OLDER key (fake_server spelling), 0.4242", older, None),
        ("3 fetch RAISES, 0 s after a good value", None, 0.0),
        ("4 fetch RAISES again, >1.0 s after the last good value", None, 1.2),
        ("5 scrape SUCCEEDS carrying NEITHER key", neither, None),
    ]

    if not fixed:
        # the control column: no scrape exists, so every state hands the reader the same default
        doc["states"] = [{"state": n, "reader_gets": None,
                          "reader_gets_with_default_0": 0.0,
                          "why": "AsyncLive2Backend.metrics() carries no vllm: key"}
                         for n, _, _ in states]
        doc["metrics_health"] = None
        Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
        print(json.dumps(doc, indent=1))
        return 0

    # instantiate the scrape machinery without the asyncio loop or httpx
    be.base_url = "http://127.0.0.1:1"
    be.metrics_scrape = True
    be.metrics_interval_s = 0.2
    be._kv_last_good = None
    be._metrics_failures = {"n": 0, "last": None, "n_served_last_good": 0, "n_served_unknown": 0,
                            "n_kv_key_missing": 0, "n_kv_key_aliased": 0, "kv_key_seen": None,
                            "n_polls": 0}
    be._engine_metrics = {}

    rows = []
    for name, body, backdate in states:
        if backdate is not None and be._kv_last_good is not None:
            be._kv_last_good = (be._kv_last_good[0], time.time() - float(backdate))

        def fake(url, timeout=None, _b=body):
            assert url.endswith("/metrics"), url
            if _b is None:
                raise OSError("stubbed fetch failure")
            return _Resp(_b)

        AB.urllib.request.urlopen = fake
        be._engine_metrics = be._fetch_engine_metrics()
        m = dict(be._engine_metrics)
        rows.append({
            "state": name,
            "reader_gets": m.get(READER_KEY, 0.0),
            "fm_kv_state": m.get("fm_kv_state"),
            "fm_kv_source_key": m.get("fm_kv_source_key"),
            "fm_kv_age_s": m.get("fm_kv_age_s"),
            "fm_kv_missing": m.get("fm_kv_missing"),
            "fm_metrics_degraded": m.get("fm_metrics_degraded"),
            "counters": dict(be._metrics_failures),
            "host_counter_keys": sorted(m.get("fm_host_counters") or {}),
            "queue_key_published": CSTATE_QUEUE_KEY in m,
        })
    doc["states"] = rows
    doc["metrics_health_after_five_states"] = be.metrics_health()
    doc["host_counters_after_state_1"] = rows[0]["host_counter_keys"]
    doc["probe_lines_used"] = {k: v for k, v in probe.items()}

    # ---- the off switch is an exact revert (the negative control, in code)
    off = AB.AsyncLive2Backend.__new__(AB.AsyncLive2Backend)
    off.metrics_scrape = False
    off._engine_metrics = {} if not off.metrics_scrape else {"x": 1}
    doc["off_switch_publishes"] = sorted(off._engine_metrics)

    Path(a.out).write_text(json.dumps(doc, indent=1) + "\n")
    print(json.dumps({k: doc[k] for k in ("tree", "fix_present")}, indent=1))
    for r in rows:
        print(r["state"], "->", r["reader_gets"], r["fm_kv_state"], r["counters"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
