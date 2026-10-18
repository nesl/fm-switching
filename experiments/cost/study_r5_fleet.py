#!/usr/bin/env python3
"""StudyR5 — cloud fleet with warm per-device history: escalation latency and warm-state capacity (vLLM venv).

Systems construction (accuracy NOT measured). Qwen3-VL-32B-Instruct @0cfaf481, StudyX server config (vLLM 0.31.0, FA3,
CUDA graphs, gmu 0.90, max_model_len 32768) with prefix caching ON, --enable-prompt-tokens-details (per-request
cached_tokens), images up to 640 per prompt, server bound to localhost.

History: frames at 1 fps from session start, each a separate image in time order, every frame resized to a FIXED
160x128 (HxW; 128x160 for landscape videos) -> 5x4 = 20 visual tokens + 2 vision delimiters per frame (verified by
the 'probe' stage). The image processor's pixel bounds are set server-side so these frames are not rescaled.
Each prompt starts with a text header naming cell, device and session, so no two devices or cells share a prefix.

Devices: D distinct S-EMBER sessions from StudyO's 845-question pool (234 videos, shuffled with seed 0, dealt
round-robin; each device chains its own videos). Replay is REAL TIME (1x). Each device starts at a seeded uniform
offset into its first session; its real questions arrive at their question_time. A session ends at its last
question (frames exist up to there).
Policies:  P-COLD  no uploads; each escalation sends header + all frames so far + question.
           P-WARM  every 10 s of session time an append request (header + all frames so far, max_tokens 1) keeps
                   the prefix warm; escalations send header + frames + question.
Warm-up (not measured): P-WARM uploads each device's history up to its start offset. Then a 15-minute window;
requests submitted inside it are measured, then in-flight requests drain.
"""
import argparse
import asyncio
import base64
import io
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import study_x_vllm as X  # noqa: E402
from rawio import read_jsonl  # noqa: E402

FRAMES = Path.home() / ".cache/fm-switching/sember_frames"
MANIFEST = Path("results/sember/study_r1/study_r1_inputs_manifest.jsonl")
OUT = Path("results/cost/study_r5")
REQ = OUT / f"study_r5_requests_{X.DEV}.jsonl"
MET = OUT / f"study_r5_metrics_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_r5_run_meta_{X.DEV}.json"
X.CURRENT = Path("logs/study_r5_current.json")
HW_PORTRAIT, HW_LANDSCAPE = (160, 128), (128, 160)
SERVER_EXTRA = ["--enable-prefix-caching", "--enable-prompt-tokens-details",
                "--limit-mm-per-prompt", json.dumps({"image": 640, "video": 0}),
                "--mm-processor-kwargs", json.dumps({"size": {"shortest_edge": 4096, "longest_edge": 20480}}),
                "--host", "127.0.0.1"]
WINDOW_S = 900
APPEND_EVERY_S = 10
ESC_MAX_TOKENS = 4
METRICS = ("vllm:prefix_cache_queries_total", "vllm:prefix_cache_hits_total", "vllm:num_preemptions_total",
           "vllm:kv_cache_usage_perc", "vllm:num_requests_running", "vllm:num_requests_waiting",
           "vllm:prompt_tokens_total", "vllm:generation_tokens_total")


# ----------------------------------------------------------------------------------------------- sessions / frames
def sessions():
    rows = [r for r in read_jsonl(MANIFEST) if r["construction"] == "RICH"]
    by = {}
    for r in rows:
        by.setdefault(r["video_id"], []).append(dict(qid=r["question_id"], qt=float(r["question_time"]),
                                                     text=r["text"]))
    out = []
    for v, qs in sorted(by.items()):
        idx = json.load(open(FRAMES / v / "index.json"))["frames"]
        qs.sort(key=lambda q: q["qt"])
        out.append(dict(video_id=v, questions=qs, frames=[(t, FRAMES / v / f) for t, f in idx],
                        duration=max(q["qt"] for q in qs)))
    return out


_B64 = {}


def frame_b64(path):
    if path not in _B64:
        im = Image.open(path).convert("RGB")
        hw = HW_PORTRAIT if im.height >= im.width else HW_LANDSCAPE
        im = im.resize((hw[1], hw[0]), Image.BICUBIC)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        _B64[path] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _B64[path]


def content(header, sess, upto_s, question=None):
    c = [{"type": "text", "text": header}]
    c += [{"type": "image_url", "image_url": {"url": frame_b64(p)}} for t, p in sess["frames"] if t <= upto_s + 1e-6]
    if question:
        c.append({"type": "text", "text": question})
    return c


# ----------------------------------------------------------------------------------------------- client
class Cell:
    def __init__(self, tag, policy, D, esc_frac, seed=0):
        self.tag, self.policy, self.D, self.esc_frac = tag, policy, D, esc_frac
        self.client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=1024))
        self.records, self.timeline, self.inflight = [], [], set()
        self.t0 = None
        self.rng = random.Random(seed)

    async def post(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True):
        header = f"[{self.tag}] device {dev:02d} session {sess_i}: egocentric camera history, one frame per second."
        body = dict(model="32BI", temperature=0.0, max_tokens=1 if kind != "escalation" else ESC_MAX_TOKENS,
                    stream=True, stream_options={"include_usage": True},
                    messages=[{"role": "user", "content": content(header, sess, upto_s, question)}])
        n_frames = sum(1 for t, _ in sess["frames"] if t <= upto_s + 1e-6)
        t_sub = time.time()
        first, usage, err = None, None, None
        try:
            async with self.client.stream("POST", f"{X.BASE}/v1/chat/completions", json=body) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
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
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        t_end = time.time()
        cached = ((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
        rec = dict(cell=self.tag, policy=self.policy, D=self.D, esc_frac=self.esc_frac, kind=kind, device=dev,
                   session=sess_i, video_id=sess["video_id"], session_t=round(upto_s, 1), n_frames=n_frames,
                   question_id=qid, in_window=in_window, t_submit=round(t_sub - self.t0, 3),
                   ttft_s=round(first - t_sub, 3) if first else None, latency_s=round(t_end - t_sub, 3),
                   prompt_tokens=usage and usage["prompt_tokens"], cached_tokens=cached,
                   completion_tokens=usage and usage["completion_tokens"], error=err)
        self.records.append(rec)
        return rec

    def spawn(self, coro):
        t = asyncio.create_task(coro)
        self.inflight.add(t)
        t.add_done_callback(self.inflight.discard)

    async def scrape(self, stop):
        while not stop.is_set():
            try:
                txt = (await self.client.get(f"{X.BASE}/metrics")).text
                row = dict(t=round(time.time() - self.t0, 2))
                for line in txt.splitlines():
                    for k in METRICS:
                        if line.startswith(k + "{") or line.startswith(k + " "):
                            row[k.split(":")[1]] = float(line.rsplit(" ", 1)[1])
                self.timeline.append(row)
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)


async def device(cell, dev, plan, offset, window_end, warm_done):
    """Replay one device in real time from `offset` seconds into its first session."""
    s_i, sess, start_s = 0, plan[0], offset
    t_start = time.time()
    while True:
        # events in this session from start_s: appends every APPEND_EVERY_S, questions at qt
        ev = []
        if cell.policy == "WARM":
            k0 = int(start_s // APPEND_EVERY_S) + 1
            ev += [(k * APPEND_EVERY_S, "append", None) for k in range(k0, int(sess["duration"] // APPEND_EVERY_S) + 1)]
        ev += [(q["qt"], "escalation", q) for q in sess["questions"] if q["qt"] > start_s + 1e-6]
        ev.sort(key=lambda e: (e[0], e[1] != "append"))
        for st, kind, q in ev:
            wall = t_start + (st - start_s)
            if wall > window_end:
                return
            await asyncio.sleep(max(0.0, wall - time.time()))
            if kind == "escalation" and cell.rng.random() >= cell.esc_frac:
                continue
            cell.spawn(cell.post(kind, dev, s_i, sess, st, question=q and q["text"], qid=q and q["qid"]))
        # next session starts when this one ends (at its duration)
        t_start = t_start + (sess["duration"] - start_s)
        s_i += 1
        if s_i >= len(plan):
            return
        sess, start_s = plan[s_i], 0.0
        await asyncio.sleep(max(0.0, t_start - time.time()))


async def run_cell(tag, policy, D, esc_frac, seed=0):
    S = sessions()
    rng = random.Random(seed)
    order = list(range(len(S)))
    rng.shuffle(order)
    plans = [[S[order[j]] for j in range(d, len(order), D)] for d in range(D)]
    offsets = [rng.uniform(0, p[0]["duration"]) for p in plans]
    cell = Cell(tag, policy, D, esc_frac, seed)
    cell.t0 = time.time()
    stop = asyncio.Event()
    scr = asyncio.create_task(cell.scrape(stop))
    # warm-up (P-WARM): upload each device's history up to its offset (not measured)
    if policy == "WARM":
        await asyncio.gather(*(cell.post("warmup", d, 0, plans[d][0], offsets[d], in_window=False) for d in range(D)))
    t_w0 = time.time()
    X.log(f"{tag}: warm-up {t_w0 - cell.t0:.1f}s; window starts ({D} devices, policy {policy}, esc {esc_frac})")
    window_end = t_w0 + WINDOW_S
    await asyncio.gather(*(device(cell, d, plans[d], offsets[d], window_end, None) for d in range(D)))
    n_inflight = len(cell.inflight)
    t_drain0 = time.time()
    if cell.inflight:
        await asyncio.gather(*list(cell.inflight))
    stop.set()
    await scr
    await cell.client.aclose()
    meta = dict(tag=tag, policy=policy, D=D, esc_frac=esc_frac, seed=seed, window_s=WINDOW_S,
                window_start=round(t_w0 - cell.t0, 2), warmup_s=round(t_w0 - cell.t0, 2),
                inflight_at_window_end=n_inflight, drain_s=round(time.time() - t_drain0, 1),
                devices=[dict(device=d, videos=[s["video_id"] for s in plans[d]][:6], offset_s=round(offsets[d], 1))
                         for d in range(D)])
    with open(REQ, "a") as f:
        for r in cell.records:
            f.write(json.dumps(r) + "\n")
    with open(MET, "a") as f:
        f.write(json.dumps(dict(cell=tag, timeline=cell.timeline)) + "\n")
    esc = [r for r in cell.records if r["kind"] == "escalation" and r["in_window"] and not r["error"]]
    hit = (sum(r["cached_tokens"] or 0 for r in esc) / max(1, sum(r["prompt_tokens"] or 0 for r in esc)))
    X.log(f"{tag}: {len(cell.records)} requests; escalations {len(esc)}; escalation token hit {hit:.2f}; "
          f"TTFT median {np.median([r['ttft_s'] for r in esc if r['ttft_s']]) if esc else None}; "
          f"errors {sum(bool(r['error']) for r in cell.records)}; inflight at end {n_inflight}")
    X.mark_done(tag, **{k: v for k, v in meta.items() if k != "tag"}, escalations=len(esc),
                escalation_token_hit=round(hit, 4))
    return hit, esc


async def probe():
    """Token count per history frame + a P-WARM hit sanity check on one session."""
    S = sessions()
    sess = S[0]
    cell = Cell("probe", "WARM", 1, 1.0)
    cell.t0 = time.time()
    a = await cell.post("probe", 0, 0, sess, 9.0)
    b = await cell.post("probe", 0, 0, sess, 19.0)
    c = await cell.post("probe", 0, 0, sess, 19.0, question=sess["questions"][0]["text"])
    await cell.client.aclose()
    per = (b["prompt_tokens"] - a["prompt_tokens"]) / (b["n_frames"] - a["n_frames"])
    res = dict(frames_a=a["n_frames"], tokens_a=a["prompt_tokens"], frames_b=b["n_frames"],
               tokens_b=b["prompt_tokens"], tokens_per_frame=per, tokens_10min=per * 600,
               append_cached=b["cached_tokens"], escalation_cached=c["cached_tokens"],
               escalation_prompt=c["prompt_tokens"], errors=[r["error"] for r in (a, b, c) if r["error"]])
    X.log(f"probe: {res}")
    m = X.meta_load()
    m["probe"] = res
    X.meta_save(m)
    return res


CELLS = ([(f"R5_{p}_D{D}", p, D, 1.0, 0) for D in (1, 2, 4, 8, 16, 32) for p in ("COLD", "WARM")]
         + [(f"R5_{p}_D{D}_esc20", p, D, 0.2, 0) for D in (8, 32) for p in ("COLD", "WARM")]
         + [("R5_WARM_D8_rep2", "WARM", 8, 1.0, 1)])
CELLS_FP8 = [(f"R5fp8_WARM_D{D}", "WARM", D, 1.0, 0) for D in (8, 16, 32)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["probe", "sweep", "fp8"], required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    extra = SERVER_EXTRA + (["--kv-cache-dtype", "fp8"] if args.stage == "fp8" else [])
    srv = X.Server("32BI", extra)
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(stage=args.stage, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        X.meta_save(m)
        X.log(f"KV cache capacity: {info.get('kv_cache_tokens')} tokens ({args.stage})")
        if args.stage == "probe":
            asyncio.run(probe())
            return
        cells = CELLS if args.stage == "sweep" else CELLS_FP8
        for tag, pol, D, ef, seed in cells:
            if X.is_done(tag):
                continue
            hit, esc = asyncio.run(run_cell(tag, pol, D, ef, seed))
            if tag == "R5_WARM_D1":     # pre-registered mechanism check
                cold = [r for r in map(json.loads, open(REQ)) if r["cell"] == "R5_COLD_D1"
                        and r["kind"] == "escalation" and r["in_window"] and not r["error"]]
                wt = np.median([r["ttft_s"] for r in esc if r["ttft_s"]]) if esc else None
                ct = np.median([r["ttft_s"] for r in cold if r["ttft_s"]]) if cold else None
                X.log(f"MECHANISM CHECK D=1: WARM escalation token hit {hit:.2f}, TTFT median WARM {wt} vs COLD {ct}")
                mm = X.meta_load()
                mm["mechanism_check_D1"] = dict(warm_hit=hit, warm_ttft_median=wt, cold_ttft_median=ct)
                X.meta_save(mm)
                if not hit > 0:
                    raise SystemExit("MECHANISM CHECK FAILED: P-WARM shows no prefix-cache hits at D=1 — STOP")
    finally:
        srv.stop()
    from _provenance import stamp  # noqa: E402
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_r5_fleet.py", model="qwen3vl-32b-instruct",
                                                 device=X.DEV, args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
