#!/usr/bin/env python3
"""StudyF2-summary, stage 1: question-independent chunk captions (vLLM venv; h100nvl GPU 1; 32B-I).

Fixed before any answer is seen. Each S-EMBER video (the 234 behind R1's 845 questions) is split into consecutive 30 s
chunks [30k, 30k + 30). A chunk is captioned iff some question of that video uses it, i.e. 30k + 30 <= qt - 120 for
some qt of the video (chunks no question can reach are not built). Frames: StudyO's 1 fps frame cache; the chunk's
cached timestamps t with 30k <= t < 30k + 30, 8 picked evenly by index (round(i * (m - 1) / 7)), resized to RH4 D2's
352x256 (study_rh3_inputs.load: orientation-aware, BICUBIC), sent as 8 separate PNG images followed by the fixed
prompt (no question, no header, no timestamp):
  "Describe what happens in these frames: people, objects, actions, and where objects are placed. Be factual and concise."
32B-I, greedy, max_tokens 128, seed 0. Server: study_f_common stack + RH4's image flags (--mm-processor-kwargs size
= PROC_SIZE so the processor does not rescale) + --mm-processor-cache-gb 0, prefix caching off.
Cost: the batched stage (concurrency 8) records its wall time -> GPU-seconds per chunk (amortised, one GPU); then 30
chunks are re-sent ONE AT A TIME (pre-serialized bodies, first discarded) for isolated per-chunk latency; caption tokens
per chunk from usage. Captions are append-only: a chunk's caption is never rewritten.
Rows -> results/sember/study_f2/f2_captions_h100nvl.jsonl. Resumable.
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_f_common as F  # noqa: E402
import study_rh3_inputs as B3  # noqa: E402

X = F.X
OUT = Path("results/sember/study_f2")
CAP = OUT / "f2_captions_h100nvl.jsonl"
SER = OUT / "f2_caption_serial_h100nvl.jsonl"
META = OUT / "f2_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = Path("logs/f2_current.json")
R1MAN = Path("results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz")
PROMPT = ("Describe what happens in these frames: people, objects, actions, and where objects are placed. "
          "Be factual and concise.")
CHUNK_S, K_FRAMES, HISTORY_GAP = 30, 8, 120
GEN = dict(temperature=0.0, max_tokens=128, seed=0)
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": K_FRAMES, "video": 0}),
         "--mm-processor-kwargs", json.dumps({"size": B3.PROC_SIZE}), "--mm-processor-cache-gb", "0",
         "--enable-prompt-tokens-details", "--host", "127.0.0.1"]
SIZE = (352, 256)
CONC, N_SERIAL = 8, 30
SRV = None


def chunk_plan():
    import gzip
    qts = {}
    for l in gzip.open(R1MAN, "rt"):
        r = json.loads(l)
        if r["construction"] == "RECENT":
            qts.setdefault(r["video_id"], []).append(float(r["question_time"]))
    plan = []
    for vid in sorted(qts):
        top = max(qts[vid]) - HISTORY_GAP
        idx = B3.frames_index(vid)
        k = 0
        while (k + 1) * CHUNK_S <= top + 1e-9:
            ts = sorted(t for t in idx if k * CHUNK_S <= t < (k + 1) * CHUNK_S)
            m = len(ts)
            pick = [ts[round(i * (m - 1) / (K_FRAMES - 1))] for i in range(K_FRAMES)] if m >= K_FRAMES else ts
            plan.append(dict(chunk_id=f"{vid}#{k}", video_id=vid, k=k, start_s=k * CHUNK_S, end_s=(k + 1) * CHUNK_S,
                             frame_t=pick, frame_paths=[str(idx[t]) for t in pick]))
            k += 1
    return plan


def body(ch):
    content, hashes = [], []
    for p in ch["frame_paths"]:
        im = B3.load(p, SIZE)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        b = buf.getvalue()
        hashes.append(hashlib.sha256(b).hexdigest())
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}})
    content.append({"type": "text", "text": PROMPT})
    return dict(model="32BI", messages=[{"role": "user", "content": content}], stream=False, **GEN), hashes


async def one(c, ch, sem):
    async with sem:
        b, hashes = await asyncio.to_thread(body, ch)
        t0 = time.time()
        j, err, attempts, seen = await F.post(c, b)
        text, u, fin = "", {}, None
        if not err:
            text = j["choices"][0]["message"].get("content") or ""
            u = j.get("usage") or {}
            fin = j["choices"][0].get("finish_reason")
        rec = dict(chunk_id=ch["chunk_id"], video_id=ch["video_id"], k=ch["k"], start_s=ch["start_s"],
                   end_s=ch["end_s"], frame_t=ch["frame_t"], frame_sha256=hashes, caption=text.strip(),
                   prompt_tokens=u.get("prompt_tokens"), caption_tokens=u.get("completion_tokens"), finish_reason=fin,
                   cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"), error=err,
                   attempts=attempts, transport_errors=seen, wall_s=round(time.time() - t0, 3), at=F.now())
        with open(CAP, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


async def run(plan):
    have = set()
    if CAP.exists():
        have = {r["chunk_id"] for r in map(json.loads, open(CAP)) if not r["error"]}
    todo = [ch for ch in plan if ch["chunk_id"] not in have]
    X.log(f"F2 captions: {len(plan)} chunks planned, {len(todo)} to run")
    sem = asyncio.Semaphore(CONC)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=None) as c:
        for i in range(0, len(todo), 200):
            fo = F.foreign()
            if fo:
                raise SystemExit(f"foreign process on GPU 1 — STOP: {fo}")
            await asyncio.gather(*(one(c, ch, sem) for ch in todo[i:i + 200]))
            X.log(f"F2 captions {min(i + 200, len(todo))}/{len(todo)}  sm {F.sm_clock()}")
            se = F.server_errors(SRV)
            if se:
                raise SystemExit(f"server log error — STOP: {se[0]}")
        wall = time.time() - t0
        m = X.meta_load()
        m.setdefault("caption_batched_segments", []).append(dict(chunks=len(todo), wall_s=round(wall, 1),
                                                                 concurrency=CONC, at=F.now()))
        X.meta_save(m)
        # isolated per-chunk latency: N_SERIAL + 1 chunks (first discarded), one at a time, bodies pre-serialized
        done_serial = sum(1 for _ in open(SER)) if SER.exists() else 0
        if done_serial < N_SERIAL + 1:
            import random
            sample = random.Random(0).sample(plan, N_SERIAL + 1)
            bodies = [(ch, json.dumps(body(ch)[0]).encode()) for ch in sample]
            for j, (ch, bb) in enumerate(bodies):
                t1 = time.perf_counter()
                r = await c.post(f"{X.BASE}/v1/chat/completions", content=bb, headers={"content-type": "application/json"})
                dt = time.perf_counter() - t1
                u = r.json().get("usage") or {}
                with open(SER, "a") as f:
                    f.write(json.dumps(dict(chunk_id=ch["chunk_id"], discarded=j == 0, total_s=round(dt, 4),
                                            prompt_tokens=u.get("prompt_tokens"),
                                            caption_tokens=u.get("completion_tokens"),
                                            cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                                            sm=F.sm_clock(), at=F.now())) + "\n")


def main():
    global SRV
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    plan = chunk_plan()
    (OUT / "f2_chunk_plan.json").write_text(json.dumps(dict(n_chunks=len(plan), n_videos=len({c["video_id"] for c in plan}),
                                                            chunk_s=CHUNK_S, frames=K_FRAMES, prompt=PROMPT,
                                                            chunks=[{k: v for k, v in c.items() if k != "frame_paths"}
                                                                    for c in plan]), indent=0))
    X.log(f"plan: {len(plan)} chunks over {len({c['video_id'] for c in plan})} videos; "
          f"short chunks (<8 frames): {sum(len(c['frame_t']) < K_FRAMES for c in plan)}")
    if a.plan_only:
        return
    F.require_idle()
    srv = X.Server("32BI", FLAGS)
    SRV = srv
    try:
        info = srv.start()
        import torch
        import vllm
        m = X.meta_load()
        m["stack_captions"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                                   gpu_uuid=F.GPU_UUID, flags=FLAGS, gen=GEN, concurrency=CONC, prompt=PROMPT)
        m.setdefault("servers", []).append(dict(stage="captions", started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        asyncio.run(run(plan))
    finally:
        srv.stop()
    rows = [json.loads(l) for l in open(CAP)]
    ok = {r["chunk_id"] for r in rows if not r["error"]}
    failed = len({c["chunk_id"] for c in plan} - ok)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_f2_captions_vllm.py", model="32BI",
                                                 device="h100nvl_gpu1", n=len(ok), args=a))
    m["caption_summary"] = dict(planned=len(plan), ok=len(ok), still_failed=failed)
    X.meta_save(m)
    if failed > 0.01 * len(plan):
        raise SystemExit(f"F2 captions: {failed} still failed > 1 % — STOP")
    if failed:
        raise SystemExit(f"F2 captions: {failed} missing — rerun to resume (every chunk is needed)")


if __name__ == "__main__":
    main()
