#!/usr/bin/env python3
"""StudyB2-h100 inference (vLLM venv; h100nvl GPU 2). ACCURACY ONLY — batched, concurrency 8; no latency is reported.

Stack: identical to StudyB1 — vLLM 0.31.0 via study_x_vllm.Server (FA3, max_model_len 32768, gmu 0.90, TP 1, prefix
caching OFF, bf16, server seed 0) + --mm-processor-cache-gb 0, --limit-mm-per-prompt {"image": 37, "video": 0}.
Input, templates, parsers: b1_common.py UNCHANGED (SHA verified at start; differs -> HALT).
Decoding: b2_common.GEN (Instruct greedy 64 + logprobs top 20; Thinking card VL sampling, 16384, seed 0).

--dataset ovo_rtv : OVO-Bench + RTV-Bench exactly as StudyB1.
  Plan (every arm): batches of 200 alternating RECENT (OVO forward, OVO other, RTV) then HISTORY (same), each part in
  its fixed seed-0 task-stratified order, so any stopping point is a near-proportional sample; the same 100 grey
  requests per input (StudyB1's: first 50 of each dataset's order) after the first full cycle.
  4BI only: StudyB1's 1,200 bridge requests (+ its 200 grey) run FIRST, in StudyB1's bridge order, as a repeat control;
  then the predicted answers (strict parser answer + status) are compared with StudyB1's 4BI rows: < 99 % agreement
  -> HALT. The rest of the plan follows (bridge keys are not repeated).
  Frame check: every new row's frame SHA-256 list must equal StudyB1's 32BI row for the same (item, input, grey) ->
  otherwise HALT.
Rows -> results/benchmarks/study_b2_<dataset>/b2_rows_<model>[.partK].jsonl.gz (resumable; rotated < 90 MB).
Transport errors (no HTTP status) retried up to 2 more times, every attempt logged. An arm stops if > 1 % of its
requests remain failed, or on a server-log error. No retry on non-termination (truncation is recorded).
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cost"))
sys.path.insert(0, str(HERE.parent / "lib"))
import b2_common as C2  # noqa: E402

C2.check_b1_common()  # before importing it: a changed b1_common halts here
import b1_common as B  # noqa: E402
import b2_sb as SB  # noqa: E402
import b2_her as HER  # noqa: E402
import study_x_vllm as X  # noqa: E402

X.REPO.update(C2.MODELS)
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 37, "video": 0}), "--mm-processor-cache-gb", "0",
         "--host", "127.0.0.1"]
CONC, ATTEMPTS, AHEAD, BATCH = 8, 3, 48, 200
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout",
             "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "out of memory", "CUDA error", "OutOfMemory")
B1_OUT = Path("results/benchmarks/study_b1_h100")


def gpu_pids():
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = lambda: gpu_pids()  # the wrapper's session check must look at GPU 2


# ---------------- dataset adapters ----------------
class OvoRtv:
    name = "ovo_rtv"
    parts = ("ovo_forward", "ovo_other", "rtv")
    upstream_correct = staticmethod(B.upstream_correct)
    strict_parse = staticmethod(B.strict_parse)
    guess_floor = staticmethod(B.guess_floor)

    def __init__(self, shard=None):
        self.items = {it["item_id"]: it for it in B.build_items()}
        self.order = B.fixed_order(list(self.items.values()))
        self.by_part = {p: [it for ds in self.order for it in self.order[ds] if it["part"] == p] for p in self.parts}
        self.grey = [it for ds in ("ovo_bench", "rtv_bench") for it in self.order[ds][:50]]

    def bridge(self):
        """StudyB1's bridge plan, verbatim order."""
        reqs = []
        for inp in ("RECENT", "HISTORY"):
            for ds in ("ovo_bench", "rtv_bench"):
                reqs += [("main", it["item_id"], inp, False) for it in self.order[ds][:300]]
            reqs += [("grey", it["item_id"], inp, True) for it in self.grey]
        return reqs

    def reference_frames(self, model=None):
        ref = {}
        for r in C2.read_rows_file(B1_OUT / "b1_rows_32BI.jsonl.gz"):
            if not r["error"]:
                ref[(r["item_id"], r["input"], r["grey"])] = r["frame_sha256"]
        return ref

    def bridge_reference(self):
        return {(r["tag"], r["item_id"], r["input"]): r for r in C2.read_rows_file(B1_OUT / "b1_rows_4BI.jsonl.gz")
                if not r["error"]}


class StreamingBench:
    """b2_sb.py: 3,250 multiple-choice questions (audio and Proactive tasks not run); shards by upstream archive."""
    name = "streaming_bench"
    parts = ("sb_realtime", "sb_contextual", "sb_sequential")
    upstream_correct = staticmethod(SB.upstream_correct)
    strict_parse = staticmethod(SB.strict_parse)
    guess_floor = staticmethod(SB.guess_floor)

    def __init__(self, shard=None):
        self.shard = shard
        all_items = SB.build_items()
        self.items = {it["item_id"]: it for it in all_items}
        order = SB.fixed_order(all_items)
        self.order = {"streaming_bench": order}
        self.by_part = {p: [it for it in order if it["part"] == p and (shard is None or it["shard"] == shard)]
                        for p in self.parts}
        self.grey = order[:100] if shard in (None, 1) else []

    def reference_frames(self, model=None):
        """Frames of this dataset's first arm (4BI); every later arm must match it on every matched request."""
        if model == "4BI":
            return None
        ref = {}
        for r in C2.read_rows(Path(f"results/benchmarks/study_b2_{self.name}"), "b2_rows_4BI"):
            if not r["error"]:
                ref[(r["item_id"], r["input"], r["grey"])] = r["frame_sha256"]
        return ref


class HERBench:
    """b2_her.py: Lite-v2 (1,971 q) + full set (27,566 runnable q); HISTORY only over the whole video; shards by video."""
    name = "herbench"
    parts = ("her_lite_v2", "her_full")
    inputs = ("HISTORY",)
    upstream_correct = staticmethod(HER.upstream_correct)
    strict_parse = staticmethod(HER.strict_parse)
    guess_floor = staticmethod(HER.guess_floor)

    def __init__(self, shard=None):
        self.shard = shard
        all_items = HER.build_items()
        self.items = {it["item_id"]: it for it in all_items}
        runnable = [it for it in all_items if it["runnable"] and not it.get("duplicate_of")]
        lite = HER.fixed_order([it for it in runnable if it["set"] == "lite_v2"])
        full = HER.fixed_order([it for it in runnable if it["set"] == "full"])
        self.order = {"herbench_lite_v2": lite, "herbench": full}
        self.by_part = {"her_lite_v2": [it for it in lite if shard is None or it["shard"] == shard],
                        "her_full": [it for it in full if shard is None or it["shard"] == shard]}
        self.grey = full[:100] if shard in (None, 0) else []

    def reference_frames(self, model=None):
        if model == "4BI":
            return None
        ref = {}
        for r in C2.read_rows(Path(f"results/benchmarks/study_b2_{self.name}"), "b2_rows_4BI"):
            if not r["error"]:
                ref[(r["item_id"], r["input"], r["grey"])] = r["frame_sha256"]
        return ref


DATASETS = {"ovo_rtv": OvoRtv, "streaming_bench": StreamingBench, "herbench": HERBench}


def interleaved(ds):
    by_part, parts = ds.by_part, ds.parts
    inputs = getattr(ds, "inputs", ("RECENT", "HISTORY"))
    cur = {(inp, p): 0 for inp in inputs for p in parts}
    reqs, cycle = [], 0
    while any(cur[(inp, p)] < len(by_part[p]) for inp, p in cur):
        for inp in inputs:
            for p in parts:
                a = cur[(inp, p)]
                reqs += [("main", it["item_id"], inp, False) for it in by_part[p][a:a + BATCH]]
                cur[(inp, p)] = a + BATCH
        if cycle == 0:
            for inp in inputs:
                reqs += [("grey", it["item_id"], inp, True) for it in ds.grey]
        cycle += 1
    return reqs


def dedupe(reqs):
    seen, out = set(), []
    for q in reqs:
        if (q[0], q[1], q[2]) not in seen:
            seen.add((q[0], q[1], q[2]))
            out.append(q)
    return out


_DS = None


def _worker_init(dsname, shard):
    global _DS
    _DS = DATASETS[dsname](shard)


def _build(args):
    item_id, inp, grey = args
    return B.build_content(_DS.items[item_id], inp, grey=grey)


# ---------------- run ----------------
async def run(a, todo, ds, out_dir, stem, srv, ref, label):
    thinking = C2.is_thinking(a.model)
    gen = C2.GEN["thinking" if thinking else "instruct"]
    loop = asyncio.get_running_loop()
    pool = ProcessPoolExecutor(16, initializer=_worker_init, initargs=(ds.name, ds.shard if hasattr(ds, "shard") else None))
    futs = {}
    state = dict(sent=0, first_history_ok=None, frame_checked=0)
    lock = asyncio.Lock()
    X.log(f"B2 {ds.name} {a.model} {label}: {len(todo)} to run")

    def submit(k):
        if k < len(todo) and k not in futs:
            tag, iid, inp, grey = todo[k]
            futs[k] = loop.run_in_executor(pool, _build, (iid, inp, grey))

    for k in range(min(AHEAD, len(todo))):
        submit(k)

    async def one(k, c):
        tag, iid, inp, grey = todo[k]
        it = ds.items[iid]
        submit(k)
        try:
            content, fmeta = await futs.pop(k)
        except Exception as e:  # noqa: BLE001  — a frame that cannot be decoded: recorded as a failed request, never dropped
            submit(k + AHEAD)
            rec = dict(study="StudyB2", dataset_group=ds.name, arm=a.model, revision=C2.MODELS[a.model][1], plan=label,
                       tag=tag, item_id=iid, dataset=it["dataset"], part=it["part"], task=it["task"], input=inp,
                       grey=grey, t=it["t"], video_key=it["video_key"], frame_pts=None, frame_sha256=None,
                       n_distinct=None, span_s=None, short_span=None, before_first_frame=None, prompt_tokens=None,
                       completion_tokens=None, finish_reason=None, text=None, think_closed=None, logprobs=None,
                       correct_upstream=None, strict_answer=None, strict_status="error", gt=it["gt"],
                       error=f"RenderError: {type(e).__name__}: {str(e)[:250]}", attempt=1, wall_s=0.0,
                       at=datetime.now().isoformat())
            async with lock:
                with gzip.open(C2.current_part(out_dir, stem), "at") as f:
                    f.write(json.dumps(rec) + "\n")
            X.log(f"B2 render error {iid} {inp}: {rec['error'][:160]}")
            return rec
        submit(k + AHEAD)
        body = dict(model=a.model, messages=[{"role": "user", "content": content}], stream=False, **gen)
        for attempt in range(1, ATTEMPTS + 1):
            t0 = time.time()
            err, j = None, None
            try:
                r = await c.post(f"{X.BASE}/v1/chat/completions", json=body)
                j = r.json()
                if r.status_code != 200 or "choices" not in j:
                    err = f"HTTP {r.status_code}: {str(j)[:300]}"
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
            text, fin, u, lp = None, None, {}, None
            if not err:
                ch = j["choices"][0]
                text = ch["message"].get("content")
                fin = ch.get("finish_reason")
                u = j.get("usage") or {}
                lpc = (ch.get("logprobs") or {}).get("content")
                if lpc:
                    lp = dict(first_token=lpc[0]["token"],
                              top20=[(t["token"], round(t["logprob"], 4)) for t in lpc[0]["top_logprobs"]],
                              chosen=[(t["token"], round(t["logprob"], 4)) for t in lpc])
            region = B.answer_region(text, thinking)
            sp, status = (None, "error") if err else ds.strict_parse(it, region)
            rec = dict(study="StudyB2", dataset_group=ds.name, arm=a.model, revision=C2.MODELS[a.model][1],
                       plan=label, tag=tag, item_id=iid, dataset=it["dataset"], part=it["part"], task=it["task"],
                       input=inp, grey=grey, t=it["t"], video_key=it["video_key"], **fmeta,
                       prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                       finish_reason=fin, text=text,
                       think_closed=("</think>" in text) if (thinking and text) else None, logprobs=lp,
                       correct_upstream=None if err else bool(ds.upstream_correct(it, region)),
                       strict_answer=sp, strict_status=status, gt=it["gt"], error=err, attempt=attempt,
                       wall_s=round(time.time() - t0, 2), at=datetime.now().isoformat())
            if it.get("row_meta"):
                rec["item_meta"] = it["row_meta"]       # HERBench required_timestamps etc.: offline analysis only
            async with lock:
                with gzip.open(C2.current_part(out_dir, stem), "at") as f:
                    f.write(json.dumps(rec) + "\n")
                if not err and ref is not None:
                    want = ref.get((iid, inp, grey))
                    if want is not None:
                        state["frame_checked"] += 1
                        if want != fmeta["frame_sha256"]:
                            C2.halt(f"B2 {ds.name} {a.model}: frame SHA-256 list differs from the reference arm on "
                                    f"{iid} {inp} grey={grey}")
            if inp == "HISTORY" and not grey and state["first_history_ok"] is None:
                state["first_history_ok"] = err is None
                if err:
                    raise SystemExit(f"B2 {a.model}: first 37-image request failed: {err[:200]} — STOP this arm")
            if err and err.split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                X.log(f"B2 transport error {iid} {inp} attempt {attempt} — retry")
                continue
            return rec

    async def worker(c):
        while True:
            async with lock:
                k = state["sent"]
                if k >= len(todo):
                    return
                if C2.HALT.exists():
                    return
                state["sent"] = k + 1
            await one(k, c)
            if (k + 1) % 200 == 0:
                X.log(f"B2 {ds.name} {a.model} {label}: {k + 1}/{len(todo)}")
                se = server_errors(srv)
                if se:
                    raise SystemExit(f"B2 {a.model}: server log error — STOP: {se[0]}")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=30.0)) as c:
            await asyncio.gather(*(worker(c) for _ in range(CONC)))
    finally:
        pool.shutdown(cancel_futures=True)
    return state


def server_errors(srv):
    if srv is None or not srv.logpath.exists():
        return []
    return [l.strip()[:300] for l in srv.logpath.read_text(errors="replace").splitlines()
            if any(k in l for k in SRV_ERR)]


def bridge_check(ds, out_dir, stem):
    """Repeat control: StudyB1 4BI bridge rows vs this run's rows on the same keys."""
    ref = ds.bridge_reference()
    new = C2.latest_ok(C2.read_rows(out_dir, stem))
    res = {}
    for kind in ("main", "grey"):
        keys = [k for k in ref if k[0] == kind and k in new]
        same_ans = sum((ref[k]["strict_answer"], ref[k]["strict_status"]) == (new[k]["strict_answer"],
                                                                                new[k]["strict_status"]) for k in keys)
        same_text = sum(ref[k]["text"] == new[k]["text"] for k in keys)
        same_correct = sum(bool(ref[k]["correct_upstream"]) == bool(new[k]["correct_upstream"]) for k in keys)
        same_frames = sum(ref[k]["frame_sha256"] == new[k]["frame_sha256"] for k in keys)
        res[kind] = dict(n=len(keys), n_reference=sum(1 for k in ref if k[0] == kind), same_answer=same_ans,
                         same_text=same_text, same_correct=same_correct, same_frames=same_frames,
                         answer_agreement=same_ans / len(keys) if keys else None,
                         differing=[dict(item_id=k[1], input=k[2], b1=ref[k]["text"], b2=new[k]["text"])
                                    for k in keys if ref[k]["text"] != new[k]["text"]][:50])
    out = dict(at=datetime.now().isoformat(), threshold=0.99, **res)
    (out_dir / "b2_repeat_control_4BI.json").write_text(json.dumps(out, indent=1))
    m = res["main"]
    X.log(f"B2 repeat control 4BI: main {m['same_answer']}/{m['n']} same answer, {m['same_text']} same text, "
          f"{m['same_frames']} same frames; grey {res['grey']['same_answer']}/{res['grey']['n']}")
    if m["n"] < m["n_reference"]:
        C2.halt(f"B2 repeat control incomplete: {m['n']}/{m['n_reference']} bridge keys answered")
    if m["answer_agreement"] < 0.99:
        C2.halt(f"B2 repeat control: 4BI answer agreement {m['answer_agreement']:.4f} < 0.99")
    if m["same_frames"] != m["n"]:
        C2.halt(f"B2 repeat control: frame SHA-256 differs on {m['n'] - m['same_frames']} bridge requests")
    return out


def repeat_check(a, out_dir, stem):
    """Step 4 for a new dataset: the same arm twice on identical input; answer agreement < 99 % -> HALT."""
    ok = C2.latest_ok(C2.read_rows(out_dir, stem))
    r1 = {k[1]: r for k, r in ok.items() if k[0] == "mv_repeat1"}
    r2 = {k[1]: r for k, r in ok.items() if k[0] == "mv_repeat2"}
    ks = sorted(set(r1) & set(r2))
    out = dict(at=datetime.now().isoformat(), model=a.model, n=len(ks), threshold=0.99,
               same_answer=sum((r1[k]["strict_answer"], r1[k]["strict_status"]) == (r2[k]["strict_answer"],
                                                                                     r2[k]["strict_status"]) for k in ks),
               same_text=sum(r1[k]["text"] == r2[k]["text"] for k in ks),
               same_correct=sum(r1[k]["correct_upstream"] == r2[k]["correct_upstream"] for k in ks),
               same_frames=sum(r1[k]["frame_sha256"] == r2[k]["frame_sha256"] for k in ks),
               differing=[dict(item_id=k, r1=r1[k]["text"], r2=r2[k]["text"]) for k in ks if r1[k]["text"] != r2[k]["text"]])
    (out_dir / f"b2_repeat_control_mv_{a.model}.json").write_text(json.dumps(out, indent=1))
    X.log(f"B2 repeat control {a.model}: {out['same_answer']}/{out['n']} same answer, {out['same_text']} same text, "
          f"{out['same_frames']} same frames")
    if not ks or out["same_answer"] < 0.99 * len(ks) or out["same_frames"] != len(ks):
        C2.halt(f"B2 repeat control {a.dataset} {a.model}: {out['same_answer']}/{out['n']} same answers, "
                f"{out['same_frames']} same frames (< 99 % or frame difference)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(DATASETS), required=True)
    ap.add_argument("--model", choices=list(C2.MODELS), required=True)
    ap.add_argument("--shard", type=int, default=None, help="StreamingBench / HERBench shard (disk)")
    ap.add_argument("--parts", default=None, help="restrict the plan to these parts (comma list), e.g. her_lite_v2")
    ap.add_argument("--repeat-control", type=int, default=0, help="Step 4 for a new dataset: the first K RECENT "
                    "questions of every part, twice (tags mv_repeat1 / mv_repeat2), rows file b2_mv_<model>; answer "
                    "agreement < 99 %% -> HALT")
    ap.add_argument("--limit", type=int, default=0, help="smoke: the first K main requests of every input x part plus "
                    "the first 2 grey per input (separate rows file b2_smoke_<model>; no bridge, no gate)")
    a = ap.parse_args()
    if C2.HALT.exists():
        raise SystemExit(f"HALT file present: {C2.HALT.read_text().strip()}")
    ds = DATASETS[a.dataset](a.shard)
    if a.parts:
        ds.parts = tuple(x for x in ds.parts if x in a.parts.split(","))
    out_dir = Path(f"results/benchmarks/study_b2_{a.dataset}")
    out_dir.mkdir(parents=True, exist_ok=True)
    X.META_PATH = out_dir / "b2_run_meta_h100nvl.json"
    X.CURRENT = Path("logs/b2_current.json")
    stem = (f"b2_mv_{a.model}" if a.repeat_control else f"b2_smoke_{a.model}" if a.limit else f"b2_rows_{a.model}")
    bridge = ds.bridge() if (a.model == "4BI" and hasattr(ds, "bridge")) else []
    reqs = dedupe(bridge + interleaved(ds))
    if a.limit:
        bridge = []
        ins = getattr(ds, "inputs", ("RECENT", "HISTORY"))
        reqs = [("smoke", it["item_id"], inp, False) for inp in ins for p in ds.parts
                for it in ds.by_part[p][:a.limit]] + [("smoke_grey", it["item_id"], inp, True)
                                                       for inp in ins for it in ds.grey[:2]]
    if a.repeat_control:
        bridge = []
        first = [it for p in ds.parts for it in ds.by_part[p][:a.repeat_control]]
        inp0 = getattr(ds, "inputs", ("RECENT",))[0]
        reqs = [(f"mv_repeat{k}", it["item_id"], inp0, False) for k in (1, 2) for it in first]
    done = set(C2.latest_ok(C2.read_rows(out_dir, stem)))
    todo_b = [q for q in bridge if (q[0], q[1], q[2]) not in done]
    nb = {(q[0], q[1], q[2]) for q in bridge}
    todo_r = [q for q in reqs if (q[0], q[1], q[2]) not in done and (q[0], q[1], q[2]) not in nb]
    X.log(f"B2 {a.dataset} {a.model}: {len(reqs)} planned, {len(done)} done, {len(todo_b)} bridge + {len(todo_r)} to run")
    if not todo_b and not todo_r:
        if bridge and not (out_dir / "b2_repeat_control_4BI.json").exists():
            bridge_check(ds, out_dir, stem)
        if a.repeat_control:
            repeat_check(a, out_dir, stem)
        return
    if gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {gpu_pids()} — STOP")
    snap = C2.snapshot_dir(a.model)
    if not snap.exists():
        raise SystemExit(f"B2 {a.model}: pinned snapshot missing ({snap}) — STOP this arm")
    ref = ds.reference_frames(a.model)
    srv = X.Server(a.model, FLAGS)
    states = []
    try:
        info = srv.start()
        log = srv.logpath.read_text(errors="replace")
        lim_ok = ("'image': 37" in log) or ('"image": 37' in log)
        import torch
        import vllm
        import av
        import PIL
        kind = "thinking" if C2.is_thinking(a.model) else "instruct"
        m = X.meta_load()
        m.setdefault("runs", []).append(dict(dataset=a.dataset, model=a.model, repo=C2.MODELS[a.model][0],
                                             revision=C2.MODELS[a.model][1], started=datetime.now().isoformat(),
                                             server=info, flags=FLAGS, gen=C2.GEN[kind], gen_source=C2.GEN_SOURCE[kind],
                                             concurrency=CONC, limit_mm_37_in_log=lim_ok, vllm=vllm.__version__,
                                             torch=torch.__version__, pyav=av.__version__,
                                             libavcodec=list(av.library_versions.get("libavcodec", ())),
                                             libavformat=list(av.library_versions.get("libavformat", ())),
                                             pil=PIL.__version__, n_planned=len(reqs), n_bridge=len(bridge),
                                             b1_common_sha256=C2.sha256_file(C2.B1_COMMON),
                                             ovo_constant_sha256=B.OVO_CONSTANT_SHA256,
                                             shard=a.shard, frame_reference=("StudyB1 32BI rows" if a.dataset == "ovo_rtv"
                                                                             else "this dataset's 4BI rows") if ref else None))
        X.meta_save(m)
        if todo_b:
            states.append(asyncio.run(run(a, todo_b, ds, out_dir, stem, srv, ref, "bridge_repeat")))
        if bridge:
            bridge_check(ds, out_dir, stem)
        if todo_r and not C2.HALT.exists():
            states.append(asyncio.run(run(a, todo_r, ds, out_dir, stem, srv, ref, "main")))
    finally:
        srv.stop()
    rows = C2.read_rows(out_dir, stem)
    keys = {(r["tag"], r["item_id"], r["input"]) for r in rows}
    ok = set(C2.latest_ok(rows))
    failed = len(keys - ok)
    m = X.meta_load()
    from _provenance import stamp
    m["runs"][-1].update(ended=datetime.now().isoformat(), rows=len(rows), ok=len(ok), still_failed=failed,
                         error_rows=sum(bool(r["error"]) for r in rows),
                         frame_checked=sum(s["frame_checked"] for s in states),
                         first_history_ok=[s["first_history_ok"] for s in states])
    m.setdefault("_provenance", []).append(stamp(script="b2_infer_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                 n=len(ok), args=a))
    X.meta_save(m)
    X.log(f"B2 {a.dataset} {a.model}: {len(ok)} ok, {failed} still failed, "
          f"frame-checked {sum(s['frame_checked'] for s in states)}")
    if a.repeat_control and not C2.HALT.exists():
        repeat_check(a, out_dir, stem)
    if C2.HALT.exists():
        raise SystemExit(f"HALT: {C2.HALT.read_text().strip()}")
    if keys and failed > 0.01 * len(keys):
        raise SystemExit(f"B2 {a.model}: {failed} still failed > 1 % — STOP this arm")


if __name__ == "__main__":
    main()
