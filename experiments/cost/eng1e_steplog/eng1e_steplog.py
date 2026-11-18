"""StudyENG1e-chain per-step membership logger (vLLM 0.31.0). OBSERVE ONLY. Loaded only by StudyENG1e servers, through
PYTHONPATH (this directory holds the module and a `vllm.general_plugins` entry-point dist-info); nothing is installed
into the venv and no engine flag changes. Active only when $ENG1E_STEPLOG_PATH is set.

Hook (no scheduler patch; the executor's execute_model is wrapped only to read the call / return time). vLLM 0.31.0 EngineCore.capture_iteration_details (active with
--enable-logging-iteration-details) calls the module-level `compute_iteration_details(scheduler_output)` of
vllm.v1.engine.core once per non-empty engine step, in the engine-core process, immediately before it starts timing the
wait for that step's model output (the ENG1 plugin's `elapsed_ms`). This add-on wraps that function: it calls the
original, returns its result unchanged, and copies (read only) the step's per-request scheduled tokens. It also wraps
EngineCore._attach_iteration_details (called after update_from_output with the same step's details) to read the
iteration index and elapsed_ms. Neither wrapper changes any argument, return value or engine state. Rows are put on a
queue and written by a background thread (plain jsonl, flushed once per second); the runner gzips the file after the
server stops.

Row schema (one per engine step that scheduled at least one token):
  i     iteration index (== the ENG1 plugin row's it[0])
  t0    wall clock (time.time()) when the engine core began waiting for this step's output (start of elapsed_ms)
  el    elapsed_ms (same value as the ENG1 plugin's it[5])
  t1    wall clock when _attach_iteration_details ran (after update_from_output)
  ts    wall clock when the engine core called model_executor.execute_model(scheduler_output) for this step (the
        step's dispatch, right after schedule()); null if not seen
  tr    wall clock when that execute_model call returned. With async scheduling the call can block on the CPU side
        (input preparation, multimodal encoder) BEFORE the timed wait starts, so elapsed_ms alone can understate a
        step: its end is t0 + el, its start max(ts, end of the previous step).
  r     [[engine request id, scheduled tokens, "p" | "d", computed tokens before this step, encoder inputs], ...]
        "p" = context phase (new request, or cached request with 0 output tokens), else "d"; the same test as
        vllm.v1.utils.compute_iteration_details, so sum of "p" tokens == it[2], count == it[1], "d" tokens == it[4].
        The engine request id is the client request id ("chatcmpl-<rid>") plus "-" and 8 random hex characters.
Special rows: {"init": ...} at install, {"err": ...} on a hook exception (the hook never raises into the engine).
"""
import atexit
import json
import os
import queue
import sys
import threading
import time

_Q = queue.SimpleQueue()
_STATE = dict(pid=None, pending=None, n=0, err=0, thread=None)
_EXEC = {}                                           # id(scheduler_output) -> [ts, tr]


_BUF = []
_LOCK = threading.Lock()


def _flush(f):
    with _LOCK:
        while True:
            try:
                _BUF.append(_Q.get_nowait())
            except queue.Empty:
                break
        if _BUF:
            f.write("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in _BUF))
            f.flush()
            _BUF.clear()


def _writer(path):
    """Writes at most once per second while steps keep coming, and as soon as the engine has been idle for 0.5 s;
    an atexit hook flushes whatever is left when the engine-core process exits normally."""
    f = open(path, "a")
    _STATE["file"] = f
    atexit.register(_flush, f)
    last = time.time()
    while True:
        try:
            item = _Q.get(timeout=0.5)
            with _LOCK:
                _BUF.append(item)
            idle = False
        except queue.Empty:
            idle = True
        now = time.time()
        if _BUF and (idle or now - last >= 1.0 or len(_BUF) >= 2000):
            _flush(f)
            last = now


def _ensure_thread():
    pid = os.getpid()
    if _STATE["pid"] != pid:                         # first call in this process (threads do not survive fork)
        _STATE["pid"] = pid
        path = os.environ["ENG1E_STEPLOG_PATH"]
        th = threading.Thread(target=_writer, args=(path,), daemon=True, name="eng1e_steplog")
        th.start()
        _STATE["thread"] = th
        _Q.put({"init": True, "pid": pid, "t": round(time.time(), 6)})


def _copy_members(so):
    new = {n.req_id: n.num_computed_tokens for n in so.scheduled_new_reqs}
    cr = so.scheduled_cached_reqs
    cc = dict(zip(cr.req_ids, cr.num_computed_tokens))
    enc = so.scheduled_encoder_inputs or {}
    out = []
    for rid, n in so.num_scheduled_tokens.items():
        ctx = rid in new or cr.is_context_phase(rid)
        out.append([rid, n, "p" if ctx else "d", new[rid] if rid in new else cc.get(rid), len(enc.get(rid, ()))])
    return out


def register():
    if not os.environ.get("ENG1E_STEPLOG_PATH"):
        return
    import vllm.v1.engine.core as core

    if getattr(core, "_eng1e_steplog", False):
        return
    orig_compute = core.compute_iteration_details
    orig_attach = core.EngineCore._attach_iteration_details

    def compute_iteration_details(scheduler_output):
        res = orig_compute(scheduler_output)
        try:
            _ensure_thread()
            ex = _EXEC.pop(id(scheduler_output), (None, None))
            _STATE["pending"] = (round(time.time(), 6), _copy_members(scheduler_output), ex)
        except Exception as e:  # noqa: BLE001
            _STATE["err"] += 1
            if _STATE["err"] <= 3:
                _Q.put({"err": f"compute: {type(e).__name__}: {e}"[:300], "t": time.time()})
        return res

    def _attach_iteration_details(self, outputs, iteration_details):
        try:
            p, _STATE["pending"] = _STATE["pending"], None
            if iteration_details is not None and p is not None and not iteration_details.is_dummy:
                _Q.put({"i": iteration_details.iteration_index, "t0": p[0],
                        "el": round(iteration_details.elapsed_ms, 3), "t1": round(time.time(), 6),
                        "ts": p[2][0], "tr": p[2][1], "r": p[1]})
        except Exception as e:  # noqa: BLE001
            _STATE["err"] += 1
            if _STATE["err"] <= 3:
                _Q.put({"err": f"attach: {type(e).__name__}: {e}"[:300], "t": time.time()})
        return orig_attach(self, outputs, iteration_details)

    def wrap_exec(cls):
        orig = cls.__dict__.get("execute_model")
        if orig is None or getattr(orig, "_eng1e", False):
            return

        def execute_model(self, *a, **kw):
            ts = time.time()
            res = orig(self, *a, **kw)
            try:
                so = a[0] if a else kw.get("scheduler_output")
                _EXEC[id(so)] = (round(ts, 6), round(time.time(), 6))
                if len(_EXEC) > 64:                  # entries of 0-token steps are never popped
                    for k in list(_EXEC)[:32]:
                        _EXEC.pop(k, None)
            except Exception:  # noqa: BLE001
                pass
            return res
        execute_model._eng1e = True
        setattr(cls, "execute_model", execute_model)

    from vllm.v1.executor.uniproc_executor import UniProcExecutor
    wrap_exec(UniProcExecutor)
    try:
        from vllm.v1.executor.multiproc_executor import MultiprocExecutor
        wrap_exec(MultiprocExecutor)
    except Exception:  # noqa: BLE001
        pass
    core.compute_iteration_details = compute_iteration_details
    core.EngineCore._attach_iteration_details = _attach_iteration_details
    core._eng1e_steplog = True
    print(f"eng1e_steplog installed (observe-only) pid={os.getpid()}", file=sys.stderr, flush=True)
