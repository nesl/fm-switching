#!/usr/bin/env python3
"""StudyE10d-blocking — which part of a cold RICH recall request is the unsplittable unit? EXCLUSIVE (vLLM venv; GPU 2).
Pre-registered in research/EXPERIMENTS.md (StudyE10d-blocking).

Harness: study_e10b_mixed.py as used by StudyE10c (Episodic, run_cell, monitor, snapshot, D7 open loop, 30-s discard,
240-s window, 300-s drain cap, exclusivity monitor ignoring <defunct>, VOID on overlap), UNCHANGED except:
  cold request   V1 PNG video  = E10c's cold K1 RICH request (control)
                 V2 JPEG video = the same npz frames JPEG q88-encoded on the client (E10a's jpeg_b64, copied verbatim)
                 V3 text-only  = R1 question text + seeded pseudo-word filler, token-matched to the K1 request's prompt
                                 tokens (R1 n_input_instruct) with the server's /tokenize (STOP if > 1 % off); no images
                 V4            = V1 with its encoder output pre-cached — run ONLY if stage `reuse` shows vLLM keeps it
                 Every cold body carries a `request_id` (e10d-...) so it can be found in the server log.
  logging only   `--enable-log-requests` and a vLLM logging config with millisecond timestamps
                 (logs/e10d_vllm_logging.json): 'Received request' = after the API server rendered / preprocessed the
                 body; 'Added request' = handed to the engine core.
  engines        E0 = E10c's E0 (defaults); E2 = --max-num-batched-tokens 2048
  condition      C1: KV-GPU, k = 0, r = 0.05; episodic N = 1 at 10 % (seed index 4) and 25 % (index 0) of 15.1 req/s;
                 cold seed 1000 + index; cold questions in E10c's order (shuffle seed 0, cursor reset per cell).
Stages: prep (E0 server: build + token-match V3 prompts), idle (E0 server: 5 sequential requests per variant, phases
from the log + per-request histogram deltas), reuse (E0 server with prefix caching OFF: does a repeated K1 request
reuse the encoder output, immediately and after 20 episodic requests?), run (the cells; V1 first per engine, control
gate vs E10c / E10b within 2x).
Rows -> results/cost/study_e10/e10d_{requests,metrics,cpu,monitor,cold_phases,idle,reuse}_h100nvl.jsonl,
        e10d_v3_prompts.jsonl.gz, meta e10d_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import base64
import gzip
import io
import itertools
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOGCFG = REPO / "logs/e10d_vllm_logging.json"
LOGCFG.write_text(json.dumps({
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"vllm": {"()": "vllm.logging_utils.NewLineFormatter", "datefmt": "%Y-%m-%d %H:%M:%S",
                            "format": "(%(vllm_process_name)s pid=%(process)d) %(levelname)s %(asctime)s.%(msecs)03d "
                                      "[%(fileinfo)s:%(lineno)d] %(message)s"}},
    "handlers": {"vllm": {"class": "logging.StreamHandler", "formatter": "vllm", "level": "INFO",
                          "stream": "ext://sys.stdout"}},
    "loggers": {"vllm": {"handlers": ["vllm"], "level": "INFO", "propagate": False}}}, indent=1))
os.environ["VLLM_LOGGING_CONFIG_PATH"] = str(LOGCFG)

import httpx  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(HERE))
import study_e10b_mixed as E  # noqa: E402

X, F, R = E.X, E.F, E.R
OUT = E.OUT
E.REQ = OUT / "e10d_requests_h100nvl.jsonl"
E.MET = OUT / "e10d_metrics_h100nvl.jsonl"
E.CPU = OUT / "e10d_cpu_h100nvl.jsonl"
E.MON = OUT / "e10d_monitor_h100nvl.jsonl"
COLD = OUT / "e10d_cold_phases_h100nvl.jsonl"
IDLE = OUT / "e10d_idle_h100nvl.jsonl"
REUSE = OUT / "e10d_reuse_h100nvl.jsonl"
V3P = OUT / "e10d_v3_prompts.jsonl.gz"
X.META_PATH = OUT / "e10d_run_meta_h100nvl.json"
X.CURRENT = REPO / "logs/e10d_current.json"

E.FRACS = (0.25, 0.50, 0.75, 0.90, 0.10, 0.20, 0.30, 0.40, 0.35)     # E10c's level -> seed-index map
LEVELS = (0.10, 0.25)
LOGFLAGS = ["--enable-log-requests"]
ENGINE = {"E0": [], "E2": ["--max-num-batched-tokens", "2048"]}
VARIANTS = ["V1", "V2", "V3"]
NQ = 15                                    # cold questions used by any cell (max over the two cold schedules)
CONTROL = {("E0", 0.10): ("E10c E0 C1 N1 10 %", 2.739087), ("E2", 0.10): ("E10c E2 C1 N1 10 %", 2.947098),
           ("E0", 0.25): ("E10b KV-GPU k0 r0.05 N1 25 %", 2.941999), ("E2", 0.25): (None, None)}
HIST = ("request_queue_time_seconds", "request_prefill_time_seconds", "time_to_first_token_seconds",
        "request_inference_time_seconds", "e2e_request_latency_seconds")
SEQ = itertools.count()
CUR = {"engine": "E0", "variant": "V1"}
LAST_RID = {}
V3 = {}


def tag(kv, k, r, n, frac):
    return f"E10D_{CUR['engine']}_{CUR['variant']}_N{n}_L{int(round(frac * 100))}"


E.tag = tag


def jpeg_b64(fr, q=88):           # verbatim copy of study_e10a_parity_vllm.jpeg_b64 (as used by StudyE10a-full)
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(fr.transpose(1, 2, 0))).save(buf, format="JPEG", quality=q)
    return base64.b64encode(buf.getvalue()).decode()


def with_rid(data, rid):
    assert data[:1] == b"{"
    return b'{"request_id": "%s", ' % rid.encode() + data[1:]


_k1 = E.k1_body


def v3_body(q):
    b = dict(model="32BI", stream=True, seed=R.SEED,
             messages=[{"role": "user", "content": [{"type": "text", "text": V3[q]["text"]}]}],
             temperature=0.0, max_tokens=4, stream_options={"include_usage": True})
    return b


def cold_body(q, variant=None):
    v = variant or CUR["variant"]
    rid = f"e10d-{CUR['engine']}-{v}-{q[:12]}-{next(SEQ)}"
    if v in ("V1", "V4"):
        data, nf = _k1(q)
    elif v == "V2":
        row = E.R1ROWS[(q, "RICH")]
        b, _, nf = E.R1_BODY(row, "K1", "32BI", dict(temperature=0.0, max_tokens=4), stream=True)
        b["mm_processor_kwargs"] = {"size": E.VIDEO_SIZE}
        z = np.load(R.INP / row["construction"] / f"{q}.npz")
        b["messages"][0]["content"][0]["video_url"]["url"] = "data:video/jpeg;base64," + ",".join(
            jpeg_b64(f) for f in z["frames"])
        data = json.dumps(b).encode()
    elif v == "V3":
        data, nf = json.dumps(v3_body(q)).encode(), 0
    else:
        raise ValueError(v)
    LAST_RID[q] = rid
    return with_rid(data, rid), nf


E.k1_body = cold_body

_tp = E.timed_post


async def timed_post(client, kind, rid, body, sched, t0, extra):
    rec = await _tp(client, kind, rid, body, sched, t0, extra)
    rec["t_sched_abs"] = round(sched, 4)
    if kind == "cold_recall":
        rec["vllm_request_id"] = LAST_RID.get(rid)
        rec["variant"] = CUR["variant"]
    return rec


E.timed_post = timed_post

LOGLINE = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{3}) .*?(Received request|Added request) "
                     r"chatcmpl-(e10d-[\w-]+)")


def log_times(logpath):
    """vllm request id prefix -> {'received': epoch, 'added': epoch} from the server log."""
    out = {}
    for line in Path(logpath).read_text(errors="replace").splitlines():
        m = LOGLINE.search(line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() + int(m.group(2)) / 1000
            key = "received" if m.group(3).startswith("Received") else "added"
            out.setdefault(m.group(4), {}).setdefault(key, ts)
    return out


def match_times(times, rid):
    out = {}                       # 'Added request' ids carry an extra '-<8 hex>' suffix: merge both entries
    for k, v in times.items():
        if k == rid or k.startswith(rid + "-"):
            for kk, t in v.items():
                out.setdefault(kk, t)
    return out


async def metrics(c):
    txt = (await c.get(f"{X.BASE}/metrics")).text
    out = {}
    for line in txt.splitlines():
        if line.startswith("#"):
            continue
        for h in HIST:
            for suf in ("_sum", "_count"):
                if line.startswith(f"vllm:{h}{suf}"):
                    out[h + suf] = out.get(h + suf, 0.0) + float(line.rsplit(" ", 1)[1])
        for k in ("vllm:mm_cache_hits_total", "vllm:mm_cache_queries_total", "vllm:prefix_cache_hits_total"):
            if line.startswith(k):
                out[k.split(":")[1]] = out.get(k.split(":")[1], 0.0) + float(line.rsplit(" ", 1)[1])
    return out


def start_server(eng, label, prefix_caching=True):
    F.require_idle()
    flags = E.KV["KVGPU"] + ENGINE[eng] + LOGFLAGS
    if not prefix_caching:
        flags = [f for f in flags if f != "--enable-prefix-caching"]
    srv = X.Server("32BI", flags)
    info = srv.start()
    txt = Path(srv.logpath).read_text(errors="replace")
    mnbt = re.findall(r"max_num_batched_tokens[=': ]+(\d+)", txt)
    info.update(prefix_caching=prefix_caching, engine=eng, engine_flags=ENGINE[eng], log_flags=LOGFLAGS,
                logging_config=str(LOGCFG), log_max_num_batched_tokens=mnbt[-1] if mnbt else None,
                encoder_cache_budget=(re.findall(r"Encoder cache will be initialized with a budget of (\d+)", txt)
                                      or [None])[-1])
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    X.log(f"[{label}] {eng}: max_num_batched_tokens {info['log_max_num_batched_tokens']}, encoder cache "
          f"{info['encoder_cache_budget']}, prefix caching {prefix_caching}")
    E.snapshot(f"server_up_{label}")
    return srv


# ------------------------------------------------------------------------------------------------ prep: V3 prompts
SYL = ["ka", "lo", "mi", "ren", "ta", "vu", "sel", "dor", "pi", "nam", "ush", "ve", "gri", "ol", "tes", "bar", "fin",
       "zu", "ex", "mor", "an", "qui", "lep", "sto", "hal", "rin", "co", "dap", "e", "nis"]


def filler(q, n):
    rng = random.Random(f"e10d-{q}")
    return " ".join("".join(rng.choice(SYL) for _ in range(rng.randint(1, 3))) for _ in range(n))


async def count_tokens(c, text):
    r = await c.post(f"{X.BASE}/tokenize", json=dict(model="32BI", add_generation_prompt=True,
                                                     messages=[{"role": "user", "content": [
                                                         {"type": "text", "text": text}]}]))
    r.raise_for_status()
    return r.json()["count"]


async def build_v3(c, q):
    row = E.R1ROWS[(q, "RICH")]
    target = row["n_input_instruct"]
    tail = "\n\n" + row["text"]
    lo, hi = 0, 3 * target
    best = None
    while lo <= hi:                                     # largest filler word count with count <= target
        mid = (lo + hi) // 2
        n = await count_tokens(c, filler(q, mid) + tail)
        if n <= target:
            best, lo = (mid, n), mid + 1
        else:
            hi = mid - 1
    words, n = best
    text = filler(q, words) + tail
    pad = 0
    while n < target and pad < 50:                     # top up with single-token " ." pieces
        cand = filler(q, words) + " ." * (pad + 1) + tail
        n2 = await count_tokens(c, cand)
        if n2 > target:
            break
        pad, text, n = pad + 1, cand, n2
    return dict(question_id=q, target_tokens=target, tokenized=n, diff=n - target, rel_diff=(n - target) / target,
                filler_words=words, pad=pad, text=text, n_frames_k1=None)


async def stage_prep(order):
    srv = start_server("E0", "E0_prep")
    try:
        async with httpx.AsyncClient(timeout=None) as c:
            rows = [await build_v3(c, q) for q in order[:NQ]]
    finally:
        srv.stop()
    with gzip.open(V3P, "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    worst = max(abs(r["rel_diff"]) for r in rows)
    X.log(f"V3 prompts: {len(rows)}, token diff {[r['diff'] for r in rows]}, worst {worst:.4%}")
    m = X.meta_load()
    m["v3"] = dict(n=len(rows), diffs=[r["diff"] for r in rows], worst_rel=worst, passed=worst <= 0.01)
    X.meta_save(m)
    if worst > 0.01:
        raise SystemExit("V3 cannot be token-matched within 1 % — STOP")


def load_v3():
    for r in map(json.loads, gzip.open(V3P, "rt")):
        V3[r["question_id"]] = r


# ------------------------------------------------------------------------------------------------ idle + reuse
async def one_idle(c, label, v, q, srv, body=None):
    if body is None:
        body, nf = cold_body(q, v)
    else:
        nf = None
    rid = json.loads(body[:200].split(b",", 1)[0] + b"}")["request_id"]
    m0 = await metrics(c)
    t = time.time()
    rec = await _tp(c, label, q, body, t, t, dict(variant=v))
    await asyncio.sleep(0.5)
    m1 = await metrics(c)
    d = {k: round(m1.get(k, 0) - m0.get(k, 0), 4) for k in m1}
    lt = match_times(log_times(srv.logpath), rid)
    out = dict(rec, stage=label, variant=v, engine=CUR["engine"], vllm_request_id=rid, n_frames=nf,
               t_sent_abs=round(t + rec["dispatch_late_s"], 4), t_first_abs=round(t + rec["ttft_s"], 4) if rec["ttft_s"] else None,
               t_received_abs=lt.get("received"), t_added_abs=lt.get("added"), metric_delta=d,
               expected_prompt_tokens=E.R1ROWS[(q, "RICH")]["n_input_instruct"])
    for k, a, b in (("render_s", "t_sent_abs", "t_received_abs"), ("frontend_s", "t_sent_abs", "t_added_abs"),
                    ("added_to_first_s", "t_added_abs", "t_first_abs")):
        out[k] = round(out[b] - out[a], 4) if out.get(a) and out.get(b) else None
    for h in ("request_queue_time_seconds", "request_prefill_time_seconds", "time_to_first_token_seconds"):
        out[h.replace("_seconds", "_s")] = d.get(h + "_sum") if d.get(h + "_count") == 1 else None
    return out


async def stage_idle(order):
    srv = start_server("E0", "E0_idle")
    rows = []
    try:
        async with httpx.AsyncClient(timeout=None) as c:
            for v in VARIANTS:
                CUR["variant"] = v
                for q in order[:5]:
                    rows.append(await one_idle(c, "idle", v, q, srv))
                    await asyncio.sleep(1.0)
    finally:
        srv.stop()
    with open(IDLE, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    bad = [(r["variant"], r["prompt_tokens"], r["expected_prompt_tokens"]) for r in rows
           if r["error"] or r["prompt_tokens"] is None or abs(r["prompt_tokens"] - r["expected_prompt_tokens"]) >
           0.01 * r["expected_prompt_tokens"]]
    X.log(f"idle: {len(rows)} rows; token mismatches {bad}")
    for v in VARIANTS:
        rr = [r for r in rows if r["variant"] == v]
        X.log(f"idle {v}: median frontend {np.median([r['frontend_s'] for r in rr if r['frontend_s'] is not None]):.3f}s "
              f"queue {np.median([r['request_queue_time_s'] or 0 for r in rr]):.3f}s "
              f"prefill {np.median([r['request_prefill_time_s'] or 0 for r in rr]):.3f}s "
              f"client ttft {np.median([r['ttft_s'] for r in rr]):.3f}s body {rr[0]['body_mb']} MB")
    m = X.meta_load()
    m["idle"] = dict(rows=len(rows), token_mismatches=bad, passed=not bad)
    X.meta_save(m)
    if bad:
        raise SystemExit("idle stage: prompt-token mismatch (V1/V2 must equal R1, V3 within 1 %) — STOP")


async def stage_reuse(order):
    """Prefix caching OFF. Per question: K1 (A1), the identical body again (A2), 20 episodic N1 requests, again (A3)."""
    srv = start_server("E0", "E0_reuse", prefix_caching=False)
    rows = []
    ep = E.Episodic(1)
    try:
        async with httpx.AsyncClient(timeout=None) as c:
            CUR["variant"] = "V1"
            for q in order[:3]:
                body, _ = _k1(q)
                for step in ("A1", "A2", "between", "A3"):
                    if step == "between":
                        for rid, b in ep.take(20):
                            t = time.time()
                            await _tp(c, "episodic", rid, b, t, t, {})
                        continue
                    vid = f"e10d-E0-V4-{q[:12]}-{next(SEQ)}"
                    rows.append(dict(await one_idle(c, f"reuse_{step}", "V1", q, srv, body=with_rid(body, vid)),
                                     step=step))
                    await asyncio.sleep(0.5)
    finally:
        srv.stop()
    with open(REUSE, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    pf = {s: [r["request_prefill_time_s"] for r in rows if r["step"] == s] for s in ("A1", "A2", "A3")}
    X.log(f"reuse prefill A1 {pf['A1']} A2 {pf['A2']} A3 {pf['A3']}")
    m = X.meta_load()
    m["reuse"] = dict(prefill=pf, rows=len(rows))
    X.meta_save(m)


# ------------------------------------------------------------------------------------------------ cells
def write_cold_phases(tg, srv, eng, var):
    rows = [json.loads(l) for l in open(E.REQ) if f'"cell": "{tg}"' in l]
    lt = log_times(srv.logpath)
    out = []
    for r in rows:
        if r["kind"] != "cold_recall":
            continue
        t = match_times(lt, r.get("vllm_request_id") or "~")
        sent = r["t_sched_abs"] + r["dispatch_late_s"]
        first = r["t_sched_abs"] + r["ttft_s"] if r["ttft_s"] is not None else None
        out.append(dict(cell=tg, engine=eng, variant=var, question_id=r["request_id"], vllm_request_id=r.get("vllm_request_id"),
                        in_window=r["in_window"], body_mb=r["body_mb"], prompt_tokens=r["prompt_tokens"],
                        expected_prompt_tokens=r.get("expected_prompt_tokens"), cached_tokens=r["cached_tokens"],
                        t_sched_abs=r["t_sched_abs"], t_sent_abs=round(sent, 4), t_received_abs=t.get("received"),
                        t_added_abs=t.get("added"), t_first_abs=round(first, 4) if first else None,
                        render_s=round(t["received"] - sent, 4) if t.get("received") else None,
                        frontend_s=round(t["added"] - sent, 4) if t.get("added") else None,
                        added_to_first_s=round(first - t["added"], 4) if t.get("added") and first else None,
                        ttft_s=r["ttft_s"], error=r["error"]))
    with open(COLD, "a") as f:
        for x in out:
            f.write(json.dumps(x) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["prep", "idle", "reuse", "run", "all"], required=True)
    ap.add_argument("--v4", action="store_true", help="include V4 cells (only if the reuse stage showed reuse)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    E.R1ROWS = {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(
        E.REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt"))}
    order = sorted({q for q, _ in E.R1ROWS})
    random.Random(0).shuffle(order)
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV["KVGPU"], engine=ENGINE, log_flags=LOGFLAGS,
                      logging_config=json.loads(LOGCFG.read_text()), peak=E.PEAK, levels=LEVELS,
                      seed_index=list(E.FRACS), budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD, drain_cap=E.DRAIN_CAP,
                      cold_questions=order[:NQ])
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    try:
        if a.stage in ("prep", "all") and not X.meta_load().get("v3", {}).get("passed"):
            asyncio.run(stage_prep(order))
        load_v3()
        if a.stage in ("idle", "all") and not X.meta_load().get("idle", {}).get("passed"):
            asyncio.run(stage_idle(order))
        if a.stage in ("reuse", "all") and "reuse" not in X.meta_load():
            asyncio.run(stage_reuse(order))
        if E.VOID.is_set():
            raise SystemExit("run VOID — STOP")
        if a.stage in ("run", "all"):
            variants = VARIANTS + (["V4"] if a.v4 else [])
            for eng in ENGINE:
                for var in variants:
                    for f in LEVELS:
                        CUR.update(engine=eng, variant=var)
                        tg = tag("KVGPU", 0, 0.05, 1, f)
                        if X.is_done(tg):
                            continue
                        srv = start_server(eng, tg)
                        try:
                            s = asyncio.run(E.run_cell("KVGPU", 0, 0.05, 1, f, srv.proc.pid, E.Episodic(1),
                                                       dict(order=order, i=0)))
                            ph = write_cold_phases(tg, srv, eng, var)
                        finally:
                            srv.stop()
                        m = X.meta_load()
                        m["experiments"][tg].update(engine=eng, variant=var, cold_logged=sum(
                            bool(p["t_added_abs"]) for p in ph), cold_n=len(ph))
                        X.meta_save(m)
                        X.log(f"{tg}: cold logged {sum(bool(p['t_added_abs']) for p in ph)}/{len(ph)}; tokens "
                              f"{[(p['prompt_tokens'], p['expected_prompt_tokens']) for p in ph][:3]}")
                        if E.VOID.is_set():
                            raise SystemExit("run VOID — STOP")
                        bad = [p for p in ph if p["prompt_tokens"] is None or abs(
                            p["prompt_tokens"] - p["expected_prompt_tokens"]) > 0.01 * p["expected_prompt_tokens"]]
                        if bad:
                            raise SystemExit(f"{tg}: cold prompt tokens off by > 1 % ({len(bad)}) — STOP")
                        if var == "V1":
                            name, ref = CONTROL[(eng, f)]
                            if ref:
                                ratio = s["episodic_p99"] / ref
                                X.log(f"CONTROL {tg}: p99 {s['episodic_p99']:.3f} vs {name} {ref:.3f} (ratio {ratio:.2f})")
                                m = X.meta_load()
                                m.setdefault("control", {})[tg] = dict(p99=s["episodic_p99"], ref=ref, ref_name=name,
                                                                       ratio=ratio, within_2x=0.5 <= ratio <= 2.0)
                                X.meta_save(m)
                                if not 0.5 <= ratio <= 2.0:
                                    raise SystemExit(f"V1 does not reproduce {name} within 2x — STOP")
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_e10d_blocking.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
