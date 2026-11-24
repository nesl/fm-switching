import sys, re
from pathlib import Path
p = Path(sys.argv[1])
s = p.read_text()

# ---- 1. imports
old = "import asyncio\nimport json\nimport threading\nimport time\n"
new = "import asyncio\nimport json\nimport os\nimport threading\nimport time\nimport urllib.request\n"
assert s.count(old) == 1
s = s.replace(old, new)

old = "from typing import Any, Dict, List, Optional\n"
new = "from typing import Any, Dict, List, Optional, Tuple\n"
assert s.count(old) == 1
s = s.replace(old, new)

# ---- 2. the class docstring line, then the scrape block before `# ---- the loop thread`
anchor = '''        self.first_gap_ms: List[float] = []      # first SSE line -> first content token
        self.callback_errors: List[str] = []

    # ---- the loop thread
'''
assert s.count(anchor) == 1
repl = '''        self.first_gap_ms: List[float] = []      # first SSE line -> first content token
        self.callback_errors: List[str] = []
        # ---- D213 item 2 (D209 (2) hit 6, live2 half). See THE /metrics SCRAPE below.
        self.metrics_scrape = (bool(metrics_scrape) if metrics_scrape is not None
                               else os.environ.get("FM_LIVE2_METRICS_SCRAPE", "1") != "0")
        self.metrics_interval_s = float(metrics_interval_s)
        self._kv_last_good: Optional[Tuple[float, float]] = None
        self._metrics_failures: Dict[str, Any] = {
            "n": 0, "last": None,
            # D209 (2): what the DECISION was handed when a fetch failed or a key was absent
            "n_served_last_good": 0,     # a cached value at most LAST_GOOD_MAX_AGE_S old
            "n_served_unknown": 0,       # no usable recent value: UNKNOWN and CONSERVATIVE
            "n_kv_key_missing": 0,       # the scrape succeeded and carried no KV-usage key
            "n_kv_key_aliased": 0,       # served from the engine's CURRENT key name
            "kv_key_seen": None,         # which spelling this engine actually emits
            "n_polls": 0,
        }
        # The pre-first-poll value is UNKNOWN AND CONSERVATIVE, not `{}`. `{}` is a second route to
        # the permissive 0.0, reached by any decision taken inside the first poll interval, and it
        # would survive a fix that only touched the exception path (Session A, `live/adapter.py`).
        # With the scrape OFF this block is EMPTY, so `metrics()` publishes no `vllm:` key and
        # every reader falls back exactly as it did before this change. That is what makes
        # `metrics_scrape=False` (or `FM_LIVE2_METRICS_SCRAPE=0`) an exact negative control rather
        # than a third behaviour: the off switch reverts to committed, it does not substitute 1.0.
        self._engine_metrics: Dict[str, Any] = {} if not self.metrics_scrape else {
            self.KV_CANONICAL_KEY: float(self.KV_UNKNOWN_CONSERVATIVE),
            "fm_kv_state": "unknown_conservative_before_first_poll", "fm_kv_missing": 1.0,
            # 0.0 on purpose: `degraded` is computed from the failure counters and NO FETCH HAS
            # HAPPENED YET, so nothing has failed. A reader that wants to know it is holding a
            # placeholder reads `fm_kv_state`, which says so by name.
            "fm_metrics_degraded": 0.0, "fm_host_counters": {}}
        self._metrics_stop = threading.Event()
        self._metrics_thread: Optional[threading.Thread] = None
        if self.metrics_scrape:
            self._metrics_thread = threading.Thread(target=self._metrics_loop,
                                                    name="live2-metrics", daemon=True)
            self._metrics_thread.start()

    # ---------------------------------------------------------------- THE /metrics SCRAPE
    #
    # D213 item 2, the live2 half of D209 (2) hit 6. WHY THIS EXISTS AT ALL, which is the finding
    # that makes it necessary rather than cosmetic: LIVE2 NEVER SCRAPED /metrics. `st.metrics` has
    # exactly one writer, `coordinator.py:489` (`self.st.metrics = self.be.metrics()`, skipped on a
    # dry cell), and in every reported live2 cell `be` is THIS class, which is not an `HttpBackend`
    # subclass, contained no `/metrics` string, and whose `metrics()` returned build and wire
    # statistics with no `vllm:` key at any time. `HttpBackend.start_poller`, the only thing that
    # would have made `live/adapter.py`'s scrape run, has one caller in the tree:
    # `live/run_live_cell.py:91`, the StudyLIVE1 v1 harness. So `cloud.gpu_kv_fraction`
    # (`cstate.py:663`) read its 0.0 default - the MINIMUM of [0, 1] and the most permissive value
    # an admission gate can be handed - in every reported live2 cell, NOT because a fetch failed
    # and NOT because a key was renamed, but because nothing read the endpoint. Session A's fixes to
    # `live/adapter.py` are correct and reach ZERO live2 cells; fixing only the key name here would
    # have looked like a pass for the same reason.
    #
    # THE KEY NAMES ARE THE ENGINE'S OWN, not guessed. Confirmed by the committed H100 probe
    # `results/orchestration/live2/frozen_test/engine_probe_hit26/metrics_scrape_h100.txt`
    # (vLLM 0.31.0+cu129, Qwen3-VL-32B "32BI"): the KV gauge is `vllm:kv_cache_usage_perc`
    # (0.7215447154471545 at capture) and this engine emits NO `vllm:gpu_cache_usage_perc` at all.
    # BOTH spellings are accepted and the value is republished under the OLD one, so no reader
    # changes and a future build that reverts the name does not silently regress to 0.0 again.
    #
    # THE MISSING-VALUE POLICY, as ruled in D209 (2) and as Session A implemented it in the v1
    # adapter. A failed fetch NEVER substitutes 0.0:
    #   1. the KV fraction is MARKED MISSING, never defaulted;
    #   2. the decision uses the LAST GOOD VALUE if it is at most LAST_GOOD_MAX_AGE_S old;
    #   3. otherwise capacity is UNKNOWN AND CONSERVATIVE: KV_UNKNOWN_CONSERVATIVE = 1.0, the
    #      MAXIMUM of [0, 1]. That 1.0 is the PRESSURE end at each live2 read site, checked and not
    #      assumed: `arms_v6cf.py:306` computes a free-KV estimate from `1 - frac`, so 1.0 gives a
    #      zero free pool and the gate tightens; `engine_actions.py:288` computes
    #      `free = max(1 - frac, 0) * pool` the same way. An unknown is never permissive;
    #   4. the cell RECORDS THE COUNT, split by which of 2 and 3 it got; and
    #   5. the run is FLAGGED through `metrics_health()`, whose `metrics_degraded` field is the cell
    #      flag, reusing Session A's shape rather than inventing a second one.
    # The counter committed at `29742254` is BUILT ON, not reverted: `n` and `last` keep their
    # existing names and meanings so any existing reader is unaffected.
    #
    # WHAT IS PUBLISHED INTO `st.metrics`, AND WHY IT IS AN ALLOWLIST AND NOT THE WHOLE SCRAPE.
    # `st.metrics` is read in exactly two places, both in `cstate.observation()`:
    #   `cstate.py:663`  gpu_kv_fraction = metrics.get("vllm:gpu_cache_usage_perc", 0.0)   <- the fix
    #   `cstate.py:657`  episodic queued  = metrics.get("vllm:num_requests_waiting", in_flight)
    # Publishing the raw scrape, as the v1 adapter does, would ALSO connect the second one for the
    # first time, which would change `cloud.queued_by_class` for EVERY arm on EVERY live cell [CORRECTED 2026-11-23 by the n5 census, StudyQCLASS-CENSUS: that is true of the VALUE and overstated for the DECISIONS. Exactly ONE paper-set arm reads the field (mooncake), NO scored result would move because coordinator.py:863 merges DEVICE and REJECT and scorer/score.py never reads REJECT, and our rungs are unexercised on it (guard_backlog 100 against an observed max of 28). What WOULD move is mooncake's recall_REJECT counter, which is its characteristic decision under the port rule, so the blast radius is one arm's decision LABEL and the proofs citing it, not the paper set's numbers]. That
    # is a methodological change nobody ruled, and it would have ridden in invisibly behind a fix
    # whose stated blast radius is one gate. So `vllm:num_requests_waiting` is DELIBERATELY NOT
    # PUBLISHED and `cstate.py:657` keeps its committed in-flight fallback; whether to connect it is
    # the user's call, recorded as an escalation.
    #
    # The D211 host and offload counters ARE published, under `fm_host_counters` and NOT under their
    # `vllm:` names, so they cannot reach a `cstate` read by accident. LABELS ARE KEPT: the
    # D209 (2) report's E7 records that the v25 driver stripped labels and summed by bare key, which
    # collapsed `prompt_tokens_by_source_total`'s `local_compute`, `local_cache_hit` and
    # `external_kv_transfer` into one number and made the host share unrecoverable. Each series is
    # keyed `<name>|<label=value>,...`, so that cannot happen here.
    KV_KEYS = ("vllm:gpu_cache_usage_perc", "vllm:kv_cache_usage_perc")
    KV_CANONICAL_KEY = "vllm:gpu_cache_usage_perc"
    KV_UNKNOWN_CONSERVATIVE = 1.0
    LAST_GOOD_MAX_AGE_S = 1.0
    # Names CHECKED against the committed probe scrape (sha256 ec198bcd4951982e788a1a2592425658
    # 7a44c716711c943236a1e3a672f762c3), and ONE NEGATIVE CLAIM ABOUT IT IS CORRECTED HERE, recorded
    # with its own command so a later reader does not repeat the mistake. I reported that this engine
    # emits NEITHER `vllm:kv_offload_load_bytes_total` NOR `vllm:kv_offload_store_bytes_total`. IT
    # EMITS BOTH, and I had asserted their absence from a `head`-truncated grep:
    #   grep -h '^vllm:kv_offload_\(load\|store\|total\)_bytes_total' metrics_scrape_h100.txt
    #     vllm:kv_offload_total_bytes_total{...,transfer_type="CPU_to_GPU"} 1.29650130944e+12
    #     vllm:kv_offload_total_bytes_total{...,transfer_type="GPU_to_CPU"} 9.50735470592e+11
    #     vllm:kv_offload_load_bytes_total{engine="0",model_name="32BI"}   1.29650130944e+12
    #     vllm:kv_offload_store_bytes_total{engine="0",model_name="32BI"}  9.50735470592e+11
    # The unlabelled pair is EXACTLY EQUAL to the labelled total's two transfer types, so
    # `engine_actions.HOST_RESIDENCY_AGGREGATE_KEYS:460-461` is NOT a dead lookup.
    # The LABELLED family is nevertheless what this block publishes, now for a stated reason rather
    # than by accident: it carries direction IN THE SERIES, where the unlabelled pair encodes
    # direction in the metric NAME, which is the shape that breaks when an engine renames or
    # deprecates one half.
    HOST_SERIES = (
        "vllm:prompt_tokens_by_source_total",      # source=local_compute|local_cache_hit|external_kv_transfer
        "vllm:prompt_tokens_cached_total",
        "vllm:external_prefix_cache_hits_total",
        "vllm:external_prefix_cache_queries_total",
        "vllm:prefix_cache_hits_total",
        "vllm:prefix_cache_queries_total",
        "vllm:kv_offload_total_bytes_total",       # transfer_type=CPU_to_GPU|GPU_to_CPU
        "vllm:kv_offload_total_time_total",
        "vllm:kv_offload_size_count",
        "vllm:kv_offload_size_sum",
        "vllm:kv_offload_cpu_cache_usage_perc",
        "vllm:kv_offload_cpu_cache_read_usage_perc",
        "vllm:kv_offload_cpu_cache_write_usage_perc",
        "vllm:kv_cache_usage_perc",
    )

    @property
    def metrics_failures(self) -> Dict[str, Any]:
        return self._metrics_failures

    def metrics_health(self) -> Dict[str, Any]:
        """The cell flag, in Session A's shape. `metrics_degraded` is true for ANY cell in which a
        fetch failed or a KV key was absent, so no such cell can be read as clean."""
        c = dict(self._metrics_failures)
        degraded = bool(c["n"] or c["n_kv_key_missing"] or c["n_served_last_good"]
                        or c["n_served_unknown"])
        return {"metrics_degraded": degraded, "metrics_failures": c,
                "metrics_scrape_enabled": bool(self.metrics_scrape),
                "kv_unknown_conservative_value": self.KV_UNKNOWN_CONSERVATIVE,
                "last_good_max_age_s": self.LAST_GOOD_MAX_AGE_S,
                "published_keys": [self.KV_CANONICAL_KEY],
                "not_published": ["vllm:num_requests_waiting"],
                "policy": ("D209 (2) / D213 item 2: a failed fetch or an absent KV key never "
                           "substitutes 0.0; the last good value at most %.1f s old, else UNKNOWN "
                           "and CONSERVATIVE (%.1f)"
                           % (self.LAST_GOOD_MAX_AGE_S, self.KV_UNKNOWN_CONSERVATIVE))}

    def _metrics_loop(self) -> None:
        while not self._metrics_stop.is_set():
            try:
                self._engine_metrics = self._fetch_engine_metrics()
            except Exception as e:                                    # noqa: BLE001
                # a defect in this method must never take the cell down, and must never leave a
                # permissive value behind either: the previous snapshot stands and is already
                # marked, and the failure is counted.
                c = self._metrics_failures
                c["n"] = int(c["n"]) + 1
                c["last"] = f"{type(e).__name__}: {e}"[:200]
            self._metrics_stop.wait(self.metrics_interval_s)

    def _kv_fraction_from(self, scraped: Dict[str, float]) -> Tuple[Optional[float], str]:
        """The KV fraction this scrape carries, under whichever name the engine uses, or None.

        None is MISSING, and it is returned rather than a number so the caller must choose a
        policy. That is the whole point: `.get(key, 0.0)` made that choice invisibly.
        """
        c = self._metrics_failures
        for i, k in enumerate(self.KV_KEYS):
            if k in scraped:
                c["kv_key_seen"] = k
                if i:
                    c["n_kv_key_aliased"] = int(c["n_kv_key_aliased"]) + 1
                return float(scraped[k]), k
        return None, ""

    def _fetch_engine_metrics(self) -> Dict[str, Any]:
        c = self._metrics_failures
        c["n_polls"] = int(c["n_polls"]) + 1
        failed: Optional[str] = None
        txt = ""
        try:
            with urllib.request.urlopen(self.base_url + "/metrics", timeout=5) as r:
                txt = r.read().decode()
        except Exception as e:                                        # noqa: BLE001
            failed = type(e).__name__
            c["n"] = int(c["n"]) + 1
            c["last"] = failed
        bare: Dict[str, float] = {}
        host: Dict[str, float] = {}
        for line in txt.splitlines():
            if line.startswith("#") or " " not in line:
                continue
            name, _, val = line.rpartition(" ")
            try:
                v = float(val)
            except ValueError:
                continue
            key = name.split("{")[0]
            bare[key] = v
            if key in self.HOST_SERIES:
                host[_labelled(name)] = v

        out: Dict[str, Any] = {"fm_host_counters": host}
        kv, seen = self._kv_fraction_from(bare)
        now = time.time()
        if kv is not None:
            self._kv_last_good = (float(kv), now)
            out[self.KV_CANONICAL_KEY] = float(kv)
            out["fm_kv_state"] = "observed"
            out["fm_kv_source_key"] = seen
            out["fm_kv_age_s"] = 0.0
        else:
            if failed is None:
                # the scrape succeeded and carried neither spelling: still a MISSING value, and
                # the same 0.0 if it were defaulted, so it takes the same policy
                c["n_kv_key_missing"] = int(c["n_kv_key_missing"]) + 1
            last = self._kv_last_good
            age = (now - last[1]) if last else None
            if last is not None and age is not None and age <= self.LAST_GOOD_MAX_AGE_S:
                c["n_served_last_good"] = int(c["n_served_last_good"]) + 1
                out[self.KV_CANONICAL_KEY] = float(last[0])
                out["fm_kv_state"] = "last_good"
                out["fm_kv_age_s"] = round(float(age), 4)
            else:
                c["n_served_unknown"] = int(c["n_served_unknown"]) + 1
                out[self.KV_CANONICAL_KEY] = float(self.KV_UNKNOWN_CONSERVATIVE)
                out["fm_kv_state"] = "unknown_conservative"
                out["fm_kv_age_s"] = (round(float(age), 4) if age is not None else None)
            out["fm_kv_missing"] = 1.0
            out["fm_metrics_fetch_error"] = failed
        out["fm_metrics_degraded"] = 1.0 if self.metrics_health()["metrics_degraded"] else 0.0
        return out

    # ---- the loop thread
'''
s = s.replace(anchor, repl)

# ---- 3. ctor signature
old = ("                 record_bodies: bool = True, time_scale: float = 1.0) -> None:")
new = ("                 record_bodies: bool = True, time_scale: float = 1.0,\n"
       "                 metrics_scrape: Optional[bool] = None,\n"
       "                 metrics_interval_s: float = 0.2) -> None:")
assert s.count(old) == 1
s = s.replace(old, new)

# ---- 4. close() stops the poller
old = '''    def close(self) -> None:
        try:
'''
new = '''    def close(self) -> None:
        self._metrics_stop.set()
        if self._metrics_thread is not None:
            self._metrics_thread.join(2.0)
        try:
'''
assert s.count(old) == 1
s = s.replace(old, new)

# ---- 5. metrics() merges the engine block in
old = '''    def metrics(self) -> Dict[str, Any]:
        g = sorted(self.first_gap_ms)
'''
new = '''    def metrics(self) -> Dict[str, Any]:
        """Build and wire statistics, PLUS the engine block the /metrics scrape publishes.

        Dict[str, Any] as before. `coordinator.py:489` assigns this straight into
        `cstate.CState.metrics`, so the engine block being here is what connects
        `cloud.gpu_kv_fraction` to the server for the first time on the live2 path. Returning the
        poller's cached snapshot, never scraping: this is called once per event-grid tick.
        """
        g = sorted(self.first_gap_ms)
'''
assert s.count(old) == 1
s = s.replace(old, new)

old = '''                    cache=(self.cache.stats() if self.cache is not None else None))
'''
new = '''                    cache=(self.cache.stats() if self.cache is not None else None),
                    metrics_health=self.metrics_health(),
                    **dict(self._engine_metrics))
'''
assert s.count(old) == 1
s = s.replace(old, new)

# ---- 6. _labelled helper
old = '''def _sha16(data: bytes) -> str:
'''
new = '''def _labelled(name: str) -> str:
    """`vllm:x{b="2",a="1"} ` -> `vllm:x|a=1,b=2`. The labels are KEPT and sorted, so a series with
    a `source` or `transfer_type` label stays separable (D209 (2) report, E7)."""
    base, _, rest = name.partition("{")
    if not rest:
        return base
    labs = []
    for part in rest.rstrip("}").split(","):
        k, _, v = part.partition("=")
        k = k.strip()
        if k and k not in ("engine", "model_name"):
            labs.append(f"{k}={v.strip().strip(chr(34))}")
    return base + "|" + ",".join(sorted(labs)) if labs else base


def _sha16(data: bytes) -> str:
'''
assert s.count(old) == 1
s = s.replace(old, new)

p.write_text(s)
print("patched", p, len(s))
