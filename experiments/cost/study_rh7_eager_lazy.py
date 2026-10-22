#!/usr/bin/env python3
"""StudyRH7 — eager vs lazy at matched fleet sizes with the history re-send protocol artifact removed (vLLM venv).
Pre-registered in research/EXPERIMENTS.md (StudyRH7). Systems only.

Reference path (vLLM 0.31.0, no upgrade): a chat image item may carry a client "uuid"; with "image_url": null the
item is served from the multimodal processor cache (mirrored LRU: metadata in the API server, data in the engine core;
a miss returns HTTP 400 "Cache miss ... data is not provided"). An item sent with bytes and a uuid is cached under
that uuid. uuids are session-scoped: "<cell>|<device>|<session>|<frame path>" (no reuse across devices or cells).

Server: RH6's GPU+host server (study_rh5_host_offload.SERVER_BASE + native offload 256 GiB) plus
--mm-processor-cache-gb 128 (the reference path needs every referenced item to stay cached; default 4 GiB), restarted
for every fleet cell. Harness: RH6's (RH2 plans/seeds, per-device headers, 1x real time, 15-min window, escalation
rate 1.0, greedy, max_tokens 1 append / 4 escalation, D2 frames, pre-serialised bodies, 1-s /metrics + CPU sampler).
  --stage step0     3 sessions x {FULL, FULLU, DELTA}: token ids, cached tokens, body bytes, API CPU; negative control
  --stage estimate  runtime estimate (no GPU); STOP if > 8 h
  --stage smoke     D=4, 60-s window, the three policies (code path only; not a result)
  --stage fleet     EAGER-DELTA, LAZY, LAZY-DELTA x D in {32, 48, 64, 96}
Policies: EAGER  = append every 10 s with only new frames' bytes + uuid refs (warm-up sends the history once);
          LAZY   = no appends; each escalation sends the full history bytes, no uuids (= RH6 B3);
          LAZYD  = no appends; bytes for frames not sent at the device-session's previous escalation, refs for the rest.
A DELTA request rejected with a cache miss is re-sent once with every frame's bytes (TTFT from the original submit).
Drain is capped at DRAIN_CAP_S; requests still in flight then are cancelled and recorded as censored.
"""
import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sember"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_rh6_offload_knee as R6  # noqa: E402
import study_x_vllm as X  # noqa: E402

F, H, R5 = R6.F, R6.H, R6.R5
OUT = Path("results/cost/study_rh7")
REQ = OUT / f"study_rh7_requests_{X.DEV}.jsonl"
MET = OUT / f"study_rh7_metrics_{X.DEV}.jsonl"
CPU = OUT / f"study_rh7_cpu_{X.DEV}.jsonl"
STEP0 = OUT / f"study_rh7_step0_{X.DEV}.json"
X.META_PATH = OUT / f"study_rh7_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_rh7_current.json")
MM_CACHE_GB = 128
SERVER_FLAGS = R5.SERVER_BASE + ["--kv-offloading-backend", "native", "--kv-offloading-size", "256",
                                 "--mm-processor-cache-gb", str(MM_CACHE_GB)]
DS = (32, 48, 64, 96)           # amended 2026-10-21 (user): D=128 -> D=64 (D128 offers ~D96's window load)
POLICIES = ("EAGER", "LAZY", "LAZYD")
DRAIN_CAP_S = 2400
BUDGET_S = 8 * 3600
VISION_START = 151652
# RH5's scrape pattern + the processor-cache counters
R5.METRIC_PAT = re.compile(R5.METRIC_PAT.pattern.replace(r"external[a-z_]*))", r"external[a-z_]*|mm_cache[a-z_]*))"))


def spec(policy, D, tag=None):
    return dict(tag=tag or f"RH7_{policy}_D{D}", part=policy, policy=policy, D=D, fmt="D2",
                cadence=10 if policy == "EAGER" else None, lazy=policy != "EAGER", offload=256)


def cells():
    return [spec(p, D) for D in DS for p in POLICIES]


# ------------------------------------------------------------------------------------------------ bodies
def frag_bytes(fmt, path, uid):
    f = R6._FRAG[(fmt, path)]
    return f if uid is None else b'{"uuid": ' + json.dumps(uid).encode() + b", " + f[1:]


def frag_ref(uid):
    return json.dumps({"type": "image_url", "image_url": None, "uuid": uid}).encode()


def body7(fmt, hdr, sess, upto_s, question, max_tokens, mode, ns, sent_upto=-1.0, stream=True, token_ids=False):
    """mode: 'full' = RH6 bytes, no uuid; 'fullu' = bytes + uuid for every frame; 'delta' = bytes + uuid for frames
    with t > sent_upto, uuid-only reference for the rest. Returns (body, n_frames, n_new, new_frag_bytes,
    full_equiv_bytes) — the last is the size of the RH6 full-bytes body for the same request."""
    fr = R6.frames(sess, upto_s)
    parts = [json.dumps({"type": "text", "text": hdr}).encode()]
    n_new = new_b = 0
    full_b = len(parts[0]) + sum(len(R6._FRAG[(fmt, p)]) + 2 for _, p in fr)
    for t, p in fr:
        uid = None if mode == "full" else f"{ns}|{p}"
        if mode == "delta" and t <= sent_upto + 1e-6:
            parts.append(frag_ref(uid))
        else:
            parts.append(frag_bytes(fmt, p, uid))
            n_new += 1
            new_b += len(parts[-1])
    if question:
        parts.append(json.dumps({"type": "text", "text": question}).encode())
        full_b += len(parts[-1]) + 2
    hd = dict(model="32BI", temperature=0.0, max_tokens=max_tokens, stream=stream)
    if stream:
        hd["stream_options"] = {"include_usage": True}
    if token_ids:
        hd["return_token_ids"] = True
    head = json.dumps(hd)[:-1].encode()
    tail = b', "messages": [{"role": "user", "content": ['
    return (head + tail + b", ".join(parts) + b"]}]}", len(fr), n_new, new_b,
            len(head) + len(tail) + full_b + 4)


# ------------------------------------------------------------------------------------------------ cell
class Cell(R6.Cell):
    def __init__(self, sp, seed=0):
        super().__init__(sp, seed)
        self.sent = {}            # (device, session) -> session time up to which frame bytes were sent

    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True, t_sched=None):
        sp = self.spec
        fmt, pol = sp["fmt"], sp["policy"]
        mt = F.ESC_MAX_TOKENS if kind == "escalation" else 1
        ns = f"{self.tag}|{dev}|{sess_i}"
        key = (dev, sess_i)
        mode = "full" if pol == "LAZY" else "delta"
        sent = self.sent.get(key, -1.0)
        if mode == "delta":                       # synchronous (before the first await): spawn order = send order
            self.sent[key] = max(sent, upto_s)
        hdr = R6.header(self.tag, dev, sess_i)
        data, n_frames, n_new, new_b, full_eq = await asyncio.to_thread(body7, fmt, hdr, sess, upto_s, question, mt, mode, ns,
                                                               sent)
        t_sub = time.time()
        first, usage, err, fb, fb_err, body_mb_sent = None, None, None, False, None, len(data) / 1e6
        try:
            for attempt in (0, 1):
                retry = False
                async with self.client.stream("POST", f"{X.BASE}/v1/chat/completions", content=data,
                                              headers={"Content-Type": "application/json"}) as r:
                    if r.status_code != 200:
                        txt = (await r.aread())[:400]
                        if attempt == 0 and mode == "delta" and b"Cache miss" in txt:
                            retry, fb, fb_err = True, True, txt[:200].decode(errors="replace")
                        else:
                            err = f"HTTP {r.status_code}: {txt[:300]!r}"
                    else:
                        async for line in r.aiter_lines():
                            if not line.startswith("data: ") or line == "data: [DONE]":
                                continue
                            j = json.loads(line[6:])
                            if j.get("usage"):
                                usage = j["usage"]
                            for ch in j.get("choices", []):
                                if (ch.get("delta") or {}).get("content") and first is None:
                                    first = time.time()
                if not retry:
                    break
                data = (await asyncio.to_thread(body7, fmt, hdr, sess, upto_s, question, mt, "fullu", ns))[0]
                body_mb_sent += len(data) / 1e6
        except asyncio.CancelledError:
            err = f"censored: still in flight at the {DRAIN_CAP_S}-s drain cap"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        t_end = time.time()
        rec = dict(cell=self.tag, policy=pol, part=pol, fmt=fmt, cadence=sp["cadence"], lazy=sp["lazy"],
                   offload_gib=sp["offload"], D=self.D, kind=kind, device=dev, session=sess_i,
                   video_id=sess["video_id"], session_t=round(upto_s, 1), n_frames=n_frames, n_new_frames=n_new,
                   body_mode=mode, body_mb=round(len(data) / 1e6 if not fb else body_mb_sent, 4),
                   new_frames_mb=round(new_b / 1e6, 4), full_equiv_mb=round(full_eq / 1e6, 4), fallback=fb, fallback_error=fb_err, question_id=qid,
                   in_window=in_window, t_sched=None if t_sched is None else round(t_sched - self.t0, 3),
                   t_submit=round(t_sub - self.t0, 3),
                   submit_lag_s=None if t_sched is None else round(t_sub - t_sched, 3),
                   ttft_s=round(first - t_sub, 3) if first else None, latency_s=round(t_end - t_sub, 3),
                   t_end=round(t_end - self.t0, 3), prompt_tokens=usage and usage["prompt_tokens"],
                   cached_tokens=((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
                   completion_tokens=usage and usage["completion_tokens"], error=err, warm_device=not sp["lazy"])
        self.records.append(rec)
        return rec


def mem_split(pid):
    """Host memory (GiB): RSS of the API-server process, of its children (engine core: KV offload buffer + processor
    cache data), the tree total, and MemAvailable."""
    import psutil
    try:
        p = psutil.Process(pid)
        api = p.memory_info().rss
        eng = sum(c.memory_info().rss for c in p.children(recursive=True))
    except psutil.Error:
        api = eng = None
    m = R5.host_mem(pid)
    g = lambda x: None if x is None else round(x / 2 ** 30, 2)  # noqa: E731
    return dict(api_rss_gib=g(api), engine_rss_gib=g(eng), tree_rss_gib=g(api + eng) if api is not None else None,
                mem_available_gib=round(m["host_mem_available_gib"], 1))


async def mem_sampler(cell, pid, stop):
    while not stop.is_set():
        row = await asyncio.to_thread(mem_split, pid)
        row["t"] = round(time.time() - cell.t0, 1)
        cell.mem.append(row)
        try:
            await asyncio.wait_for(stop.wait(), 10.0)
        except asyncio.TimeoutError:
            pass


async def run_cell(sp, srv_pid, seed=0):
    """R6.run_cell with RH7 Cell, RH7 output files and a drain cap."""
    t = sp["tag"]
    D = sp["D"]
    plans, offsets = H.plan(D, seed)
    cell = Cell(sp, seed)
    cell.t0 = time.time()
    cell.mem = []
    mem0 = R5.host_mem(srv_pid)
    stop = asyncio.Event()
    sampler = R6.Sampler(srv_pid)
    scr = asyncio.create_task(cell.scrape(stop))
    smp = asyncio.create_task(sampler.run(cell, stop))
    msm = asyncio.create_task(mem_sampler(cell, srv_pid, stop))
    m_start = await R5.scrape_once(cell.client)
    if not sp["lazy"]:
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False)
                               for d in range(D)))
    t_w0 = time.time()
    X.log(f"{t}: warm-up {t_w0 - cell.t0:.1f}s; window starts")
    m_w0 = await R5.scrape_once(cell.client)
    window_end = t_w0 + F.WINDOW_S
    await asyncio.gather(*(R6.device(cell, d, plans[d], offsets[d], window_end) for d in range(D)))
    await asyncio.sleep(max(0.0, window_end - time.time()))
    n_inflight = len(cell.inflight)
    m_w1 = await R5.scrape_once(cell.client)
    mem1 = R5.host_mem(srv_pid)
    t_d0 = time.time()
    censored = 0
    if cell.inflight:
        done, pend = await asyncio.wait(list(cell.inflight), timeout=DRAIN_CAP_S)
        censored = len(pend)
        for p in pend:
            p.cancel()
        if pend:
            await asyncio.gather(*pend, return_exceptions=True)
            X.log(f"{t}: DRAIN CAP {DRAIN_CAP_S}s reached; {censored} requests censored")
    drain = time.time() - t_d0
    await asyncio.sleep(1.5)
    m_end = await R5.scrape_once(cell.client)
    stop.set()
    await scr
    await smp
    await msm
    await cell.client.aclose()
    meta = dict(spec=sp, seed=seed, window_s=F.WINDOW_S, window_start=round(t_w0 - cell.t0, 2),
                warmup_s=round(t_w0 - cell.t0, 2), inflight_at_window_end=n_inflight, drain_s=round(drain, 1),
                drain_capped=censored > 0, censored=censored,
                elapsed_window_plus_drain_s=round(time.time() - t_w0, 1), coverage=R6.plan_coverage(D, seed),
                host_mem_start=mem0, host_mem_window_end=mem1, host_mem_end=R5.host_mem(srv_pid), mem_timeline=cell.mem,
                counters=dict(start=m_start, window_start=m_w0, window_end=m_w1, end=m_end))
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=t, timeline=cell.timeline)) + "\n")
    with open(CPU, "a") as f:
        f.write(json.dumps(dict(cell=t, samples=cell.cpu)) + "\n")
    summ = R6.summarise(cell.records, meta)
    summ["fallbacks"] = sum(r["fallback"] for r in cell.records)
    summ["fallback_frac"] = summ["fallbacks"] / max(1, len(cell.records))
    summ["engine_rss_peak_gib"] = max((x["engine_rss_gib"] or 0 for x in cell.mem), default=None)
    summ["api_rss_peak_gib"] = max((x["api_rss_gib"] or 0 for x in cell.mem), default=None)
    if summ["fallback_frac"] > 0.01:
        X.log(f"{t}: FLAG — cache-miss fallbacks {summ['fallbacks']} = {summ['fallback_frac']:.1%} of requests (> 1 %)")
    ver = R6.verify_host(meta, sp)
    X.log(f"{t}: {len(cell.records)} requests; {summ}; inflight at end {n_inflight}; drain {drain:.0f}s; "
          f"host verification {ver}")
    X.mark_done(t, **meta, summary=summ, host_verification=ver)
    return summ, ver


# ------------------------------------------------------------------------------------------------ step 0
STEP0_NS = ("FULL", "FULLU", "DELTA")


async def step0(srv_pid):
    import psutil
    api = psutil.Process(srv_pid)

    def api_cpu():
        c = api.cpu_times()
        return c.user + c.system

    plans, offs = H.plan(48, 0)
    picks = [(d, plans[d][0], offs[d]) for d in range(3)]
    client = httpx.AsyncClient(timeout=None)
    recs = []
    for d, sess, off in picks:
        q = next((x for x in sess["questions"]), None)
        t_app = [k * 10 for k in range(int(off // 10) + 1, int(sess["duration"] // 10) + 1)][:3]
        steps = [("warmup", off)] + [("append", t) for t in t_app] + [("escalation", t_app[-1])]
        sent = {ns: -1.0 for ns in STEP0_NS}
        hdr = R6.header("RH7_STEP0", d, 0)                    # identical header for the three namespaces
        for kind, t in steps:
            for ns in STEP0_NS:
                mode = {"FULL": "full", "FULLU": "fullu", "DELTA": "delta"}[ns]
                data, n_fr, n_new, new_b, _ = body7("D2", hdr, sess, t, q["text"] if kind == "escalation" else None,
                                                 F.ESC_MAX_TOKENS if kind == "escalation" else 1, mode,
                                                 f"RH7_STEP0|{ns}|{d}|0", sent[ns], stream=False, token_ids=True)
                await asyncio.sleep(0.5)
                c0, t0 = api_cpu(), time.time()
                r = await client.post(f"{X.BASE}/v1/chat/completions", content=data,
                                      headers={"Content-Type": "application/json"})
                lat = time.time() - t0
                await asyncio.sleep(0.5)
                cpu_s = api_cpu() - c0
                j = r.json() if r.status_code == 200 else {}
                ids = j.get("prompt_token_ids") or ((j.get("choices") or [{}])[0].get("prompt_token_ids"))
                u = j.get("usage") or {}
                recs.append(dict(device=d, video_id=sess["video_id"], kind=kind, session_t=t, ns=ns,
                                 status=r.status_code, error=None if r.status_code == 200 else r.text[:300],
                                 body_bytes=len(data), n_frames=n_fr, n_new_frames=n_new, new_frag_bytes=new_b,
                                 text_and_envelope_bytes=len(data) - sum(
                                     len(R6._FRAG[("D2", p)]) for _, p in R6.frames(sess, t)) if mode == "full"
                                 else None,
                                 prompt_tokens=u.get("prompt_tokens"),
                                 cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                                 prompt_token_ids=ids, output=(j.get("choices") or [{}])[0].get("message", {}).get(
                                     "content"), latency_s=round(lat, 3), api_cpu_s=round(cpu_s, 4)))
                X.log(f"step0 d{d} {kind} t={t} {ns}: HTTP {r.status_code} body {len(data) / 1e6:.2f} MB "
                      f"new {n_new}/{n_fr} prompt {u.get('prompt_tokens')} cached "
                      f"{(u.get('prompt_tokens_details') or {}).get('cached_tokens')} api cpu {cpu_s:.3f}s "
                      f"lat {lat:.2f}s")
                sent[ns] = t
    # negative control: a uuid never sent
    d, sess, off = picks[0]
    hdr = R6.header("RH7_STEP0_NEG", d, 0)
    data = body7("D2", hdr, sess, off, None, 1, "delta", "RH7_STEP0|NEVER_SENT|0|0", 1e9, stream=False)[0]
    r = await client.post(f"{X.BASE}/v1/chat/completions", content=data, headers={"Content-Type": "application/json"})
    neg = dict(status=r.status_code, text=r.text[:400])
    await client.aclose()
    return recs, neg


def step0_verdict(recs, neg):
    by = {}
    for r in recs:
        by.setdefault((r["device"], r["kind"], r["session_t"]), {})[r["ns"]] = r
    a_rows, b_rows = [], []
    for k, g in sorted(by.items()):
        f, fu, de = g["FULL"], g["FULLU"], g["DELTA"]
        ok_status = all(x["status"] == 200 for x in (f, fu, de))
        ids_eq = ok_status and f["prompt_token_ids"] is not None and \
            f["prompt_token_ids"] == fu["prompt_token_ids"] == de["prompt_token_ids"]
        a_rows.append(dict(device=k[0], kind=k[1], session_t=k[2], all_http_200=ok_status, token_ids_identical=ids_eq,
                           n_prompt_ids=len(f["prompt_token_ids"] or []),
                           prompt_tokens=[f["prompt_tokens"], fu["prompt_tokens"], de["prompt_tokens"]],
                           cached_tokens=[f["cached_tokens"], fu["cached_tokens"], de["cached_tokens"]],
                           cached_delta_eq_fullu=de["cached_tokens"] == fu["cached_tokens"],
                           outputs=[f["output"], fu["output"], de["output"]],
                           images_in_ids=(f["prompt_token_ids"] or []).count(VISION_START)))
        if k[1] == "append":
            env = f["text_and_envelope_bytes"]
            allowed = 1.2 * (de["new_frag_bytes"] + env)
            b_rows.append(dict(device=k[0], session_t=k[2], full_body=f["body_bytes"], delta_body=de["body_bytes"],
                               new_frames=de["n_new_frames"], frames=de["n_frames"],
                               new_frag_bytes=de["new_frag_bytes"], text_envelope_bytes=env,
                               delta_over_allowed=de["body_bytes"] / allowed, delta_over_full=de["body_bytes"] /
                               f["body_bytes"], api_cpu_s=[f["api_cpu_s"], fu["api_cpu_s"], de["api_cpu_s"]]))
    cpu = {ns: float(np.mean([r["api_cpu_s"] for r in recs if r["ns"] == ns and r["kind"] == "append"]))
           for ns in STEP0_NS}
    a = all(r["all_http_200"] and r["token_ids_identical"] and r["prompt_tokens"][0] == r["prompt_tokens"][1] ==
            r["prompt_tokens"][2] and r["cached_delta_eq_fullu"] for r in a_rows)
    b = all(r["delta_over_allowed"] <= 1.0 and r["delta_over_full"] <= 0.10 for r in b_rows)
    c = cpu["DELTA"] <= 0.5 * cpu["FULL"]
    n = neg["status"] == 400 and "Cache miss" in neg["text"]
    return dict(a_identical_ids_and_cached=a, b_body_shrinks=b, c_api_cpu_drops=c, negative_control_cache_miss=n,
                passed=bool(a and b and c and n), api_cpu_s_per_append_mean=cpu,
                api_cpu_delta_over_full=cpu["DELTA"] / cpu["FULL"] if cpu["FULL"] else None,
                a_rows=a_rows, b_rows=b_rows, negative_control=neg)


# ------------------------------------------------------------------------------------------------ estimate
LOAD_BPS = 12e9           # conservative host->GPU load rate (RH6 best 30-s rolling: 10-16 GB/s)
SERVER_START_S = 160      # RH6: 118-161 s
API_MB_S = 72             # RH6 API-server body ingestion (lazy full-history bodies)


def est_cell(sp):
    D = sp["D"]
    plans, offs = H.plan(D)
    ev = R6.window_events(plans, offs, sp["cadence"], sp["lazy"])
    tok = R6.TOK_IMG["D2"]
    hist = np.array([len(R6.frames(s, st)) * tok for _, _, st, s in ev], float)
    peak, mean = R6.live_resident(plans, offs, tok) if not sp["lazy"] else (0.0, 0.0)
    cap = (sp["offload"] * 2 ** 30) / R6.BYTES_PER_TOKEN + R6.KV_TOKENS
    warm = 0.0
    if sp["policy"] == "EAGER":
        warm = sum(len(R6.frames(p[0], o)) * tok for p, o in zip(plans, offs)) / R6.PREFILL_TOK_S
        if peak > cap:
            miss = min(1.0, 0.35 + max(0.0, mean / cap - 0.5))
            busy = hist.sum() * miss / R6.ACHIEVED_TOK_S
            mode = f"host thrash (recompute, miss {miss:.2f})"
        else:
            busy = hist.sum() * R6.BYTES_PER_TOKEN / LOAD_BPS + len(ev) * 5 * tok / R6.ACHIEVED_TOK_S
            mode = "host load (serial load + new-frame compute)"
    else:
        busy = max(hist.sum() * 0.7 / R6.ACHIEVED_TOK_S,
                   (len(ev) * hist.mean() / tok * 0.19 / API_MB_S) if sp["policy"] == "LAZY" else 0.0)
        mode = "lazy (cold escalations; LAZY also API bytes)"
    drain = min(DRAIN_CAP_S, max(0.0, busy - F.WINDOW_S))
    return dict(events=len(ev), req_per_s=round(len(ev) / F.WINDOW_S, 2), mean_history=round(hist.mean()),
                live_peak_over_capacity=round(peak / cap, 2), warmup_s=round(warm), busy_s=round(busy),
                drain_s=round(drain), s=round(SERVER_START_S + warm + F.WINDOW_S + drain + 30), mode=mode)


def estimate():
    out = {}
    for ds in (DS,):
        cs = {c["tag"]: est_cell(c) for c in cells() if c["D"] in ds}
        out[f"D={list(ds)}"] = dict(cells=cs, total_s=round(sum(v["s"] for v in cs.values()) + 120 + 600))
    return dict(scenarios=out, overhead="frame pre-encode 120 s + smoke 600 s",
                model=dict(load_bps=LOAD_BPS, achieved_tok_s=R6.ACHIEVED_TOK_S, prefill_tok_s=R6.PREFILL_TOK_S,
                           server_start_s=SERVER_START_S, api_mb_s=API_MB_S, drain_cap_s=DRAIN_CAP_S),
                coverage={D: R6.plan_coverage(D) for D in DS})


# ------------------------------------------------------------------------------------------------ main
def start_server(stage):
    srv = X.Server("32BI", SERVER_FLAGS)
    info = srv.start()
    info["prefix_caching"] = True
    info["kv_offloading_gib"] = 256
    info["mm_processor_cache_gb"] = MM_CACHE_GB
    txt = Path(info["log"]).read_text(errors="replace")
    info["offload_log_lines"] = sorted(set(re.findall(r"[^\n]*(?:OffloadingConnector|CPUOffloadingSpec|"
                                                      r"kv_offloading_size|mm_processor_cache)[^\n]*", txt)))[:8]
    info["host_mem"] = R5.host_mem(srv.proc.pid)
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(stage=stage, started=datetime.now().isoformat(), **info))
    import torch
    import vllm
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
    X.meta_save(m)
    X.log(f"[{stage}] KV {info.get('kv_cache_tokens')} tokens; offload 256 GiB; mm cache {MM_CACHE_GB} GiB; "
          f"attention {info.get('flash_attention_version')}; mem {info['host_mem']}")
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["step0", "estimate", "smoke", "fleet"], required=True)
    ap.add_argument("--smoke-dir", help="smoke stage: output directory (not results/)")
    args = ap.parse_args()
    global REQ, MET, CPU
    if args.stage == "smoke":
        d = Path(args.smoke_dir)
        d.mkdir(parents=True, exist_ok=True)
        REQ, MET, CPU = d / "req.jsonl", d / "met.jsonl", d / "cpu.jsonl"
        X.META_PATH = d / "meta.json"
        F.WINDOW_S = 60
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "estimate":
        est = estimate()
        m = X.meta_load()
        m["estimate"] = est
        X.meta_save(m)
        tot = {k: v["total_s"] for k, v in est["scenarios"].items()}
        X.log("RUNTIME ESTIMATE (h): " + json.dumps({k: round(v / 3600, 2) for k, v in tot.items()}))
        full = list(tot.values())[0]
        if full > BUDGET_S:
            raise SystemExit(f"RH7 estimate {full / 3600:.2f} h > 8 h — STOP")
        return
    S = F.sessions()
    if args.stage == "step0":
        plans, _ = H.plan(48, 0)
        R6.preencode("D2", [plans[d][0] for d in range(3)], procs=8)
        srv = start_server("step0")
        try:
            recs, neg = asyncio.run(step0(srv.proc.pid))
        finally:
            srv.stop()
        v = step0_verdict(recs, neg)
        from _provenance import stamp
        STEP0.write_text(json.dumps(dict(verdict=v, records=recs, server=X.meta_load()["servers"][-1],
                                         _provenance=stamp(script="study_rh7_eager_lazy.py",
                                                           model="qwen3vl-32b-instruct", device=X.DEV,
                                                           n=len(recs), args=args)), indent=1))
        X.log(f"STEP0 verdict: a={v['a_identical_ids_and_cached']} b={v['b_body_shrinks']} "
              f"c={v['c_api_cpu_drops']} (cpu {v['api_cpu_s_per_append_mean']}) neg={v['negative_control_cache_miss']}"
              f" -> {'PASS' if v['passed'] else 'FAIL'}")
        if not v["passed"]:
            raise SystemExit("RH7 Step 0 FAILED — STOP")
        return
    if args.stage == "smoke":
        specs = [spec(p, 4, tag=f"RH7_SMOKE_{p}_D4") for p in POLICIES]
    else:
        specs = cells()
    specs = [s for s in specs if not X.is_done(s["tag"])]
    if not specs:
        return
    R6.preencode("D2", S)
    for sp in specs:
        srv = start_server(sp["tag"])
        try:
            X.CURRENT.write_text(json.dumps(dict(cell=sp["tag"])))
            summ, ver = asyncio.run(run_cell(sp, srv.proc.pid))
        finally:
            srv.stop()
        if ver["verified"] is False and args.stage != "smoke":
            raise SystemExit(f"{sp['tag']}: offload host-hit verification FAILED {ver} — STOP")
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_rh7_eager_lazy.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
