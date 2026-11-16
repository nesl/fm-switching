"""StudyENG1-steptime stat-logger plugin (vLLM 0.31.0). Loaded ONLY by StudyENG1 servers, through PYTHONPATH (this
directory holds the module and an entry-point dist-info); nothing is installed into the venv and no engine flag changes.
It writes one JSON row per engine output batch that the API server receives (one per engine step that produced outputs
or carried scheduler stats) to $ENG1_STATLOG_PATH:
  t        wall clock (time.time()) when the frontend recorded the batch
  it       iteration details (only with --enable-logging-iteration-details): step index, context requests / tokens,
           generation requests / tokens, elapsed_ms (time the engine core waited for this step's model output)
  run/wait running / waiting requests; kv KV usage; pc / xpc local / external prefix-cache (queries, hits) this batch
  pts      prompt tokens of requests that produced their first output this batch, by source
           (computed, local_cache_hit, external_kv_transfer, cached)
  gen      generation tokens; pre preempted requests; ev KV block eviction samples (--kv-cache-metrics only)
  fin      finished requests: request id, prompt / cached tokens, queued, prefill (scheduled -> first token),
           inference, decode, e2e seconds, preemptions
"""
import json
import os
import time

from vllm.v1.metrics.loggers import StatLoggerBase


def _jsonable(o):
    """Make nested stats JSON-serialisable: the offloading connector's stats use tuple label keys (e.g. ()), which
    json.dumps rejects even with default=. Fix 2026-11-16: before it, every row of a KV-HOST server failed to
    serialise and was dropped silently (StudyENG1 KV-HOST servers have no plugin rows)."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (int, float, str, bool)) or o is None:
        return o
    return str(o)


class Eng1StatLogger(StatLoggerBase):
    def __init__(self, vllm_config, engine_index=0):
        self.path = os.environ.get("ENG1_STATLOG_PATH")
        self.f = open(self.path, "a", buffering=1 << 16) if self.path else None
        self.n = 0
        self.errors = 0

    def record(self, scheduler_stats, iteration_stats, mm_cache_stats=None, engine_idx=0):
        if self.f is None:
            return
        row = {"t": round(time.time(), 6)}
        s = scheduler_stats
        if s is not None:
            d = s.iteration_details
            if d is not None:
                row["it"] = [d.iteration_index, d.num_ctx_requests, d.num_ctx_tokens, d.num_generation_requests,
                             d.num_generation_tokens, round(d.elapsed_ms, 3), d.num_encoder_inputs,
                             d.num_encoder_output_tokens, int(d.is_dummy)]
            row["run"], row["wait"], row["kv"] = s.num_running_reqs, s.num_waiting_reqs, round(s.kv_cache_usage, 5)
            pc = s.prefix_cache_stats
            if pc is not None and (pc.queries or pc.hits):
                row["pc"] = [pc.requests, pc.queries, pc.hits]
            xc = s.connector_prefix_cache_stats
            if xc is not None and (xc.queries or xc.hits):
                row["xpc"] = [xc.requests, xc.queries, xc.hits]
            if s.kv_cache_eviction_events:
                row["ev"] = [[round(e.lifetime_seconds, 4), round(e.idle_seconds, 4)] for e in
                             s.kv_cache_eviction_events]
            if s.kv_connector_stats:
                row["kvc"] = _jsonable(s.kv_connector_stats)
        it = iteration_stats
        if it is not None:
            p = it.prompt_token_stats
            if p.total:
                row["pts"] = [p.computed, p.local_cache_hit, p.external_kv_transfer, p.cached_tokens, p.total]
            if it.num_generation_tokens:
                row["gen"] = it.num_generation_tokens
            if it.num_preempted_reqs:
                row["pre"] = it.num_preempted_reqs
            if it.finished_requests:
                row["fin"] = [dict(id=r.request_id, pt=r.num_prompt_tokens, ct=r.num_cached_tokens,
                                   q=round(r.queued_time, 5), pf=round(r.prefill_time, 5),
                                   inf=round(r.inference_time, 5), dec=round(r.decode_time, 5),
                                   e2e=round(r.e2e_latency, 5), gt=r.num_generation_tokens, pre=r.num_preemptions)
                              for r in it.finished_requests]
        if len(row) > 1:
            try:
                self.f.write(json.dumps(row, default=str) + "\n")
            except Exception as e:  # noqa: BLE001  (never break the engine's output loop; record the failure)
                self.errors += 1
                if self.errors <= 3 or self.errors % 1000 == 0:
                    try:
                        self.f.write(json.dumps({"t": row["t"], "plugin_error": f"{type(e).__name__}: {e}"[:300],
                                                 "n_errors": self.errors}) + "\n")
                    except Exception:  # noqa: BLE001
                        pass
            self.n += 1
            if self.n % 200 == 0:
                self.f.flush()

    def log(self):
        if self.f is not None:
            self.f.flush()

    def log_engine_initialized(self):
        if self.f is not None:
            self.f.write(json.dumps({"t": round(time.time(), 6), "init": True}) + "\n")
            self.f.flush()
