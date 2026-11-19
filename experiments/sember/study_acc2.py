#!/usr/bin/env python3
"""StudyACC2: per-question 32B accuracy by evidence choice, including LONG histories, both splits.

  prep     (CPU, server down) encode D2 frames for the DEV sessions into the D91 store with the same recipe,
           build the request plan: every StudyR1 question (845, DEV and EVAL) as D2 (full history in the
           live format: every 2-s D2 frame from session start to the question) and RECENT (the device's
           last RECENT_W = 120 s, as D2 frames), plus the LONG-HISTORY set: histories exactly as the live
           traces build them at question arrival (seeds 0, 4, 5, 6, 64 devices, 600 s; D101 preload plus
           the history batches captured by the question; D83: one session only) for every question whose
           trace history exceeds its StudyR1 history, deduplicated.
  run      the round-1 server (restarted once), requests ONE AT A TIME, each with a fresh run tag (fresh
           cache_salt and image uuids, so cold), the exact live recall body (bodies.build_body, the
           coordinator's HEADER_TEXT and RECALL_GEN), greedy; records prompt / cached tokens, idle TTFT,
           answer letter (scores.recall_letter) and correctness. Resumable.
  analyse  (CPU) accuracy with bootstrap CIs, HELPS / HURTS flows by history-length bucket, by category,
           idle TTFT vs history tokens against the committed cost curve.
RICH = D2 in the live request format (the live body carries exactly the D2 history), so one is run.
"""
import asyncio
import gzip
import hashlib
import io
import json
import os
import random
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in ("experiments/orchestration/live2", "experiments/orchestration/live2/fleet", "experiments/orchestration",
          "experiments/orchestration/baselines", "experiments/orchestration/sim", "experiments/lib", "experiments/sember"):
    sys.path.insert(0, str(REPO / p))
OUT = REPO / "results/sember/study_acc2"
STORE = Path.home() / "data/live2/jpeg/sember_d2_q88"
SRC = Path.home() / ".cache/fm-switching/sember_frames"
R1 = REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"
COMBINED = Path.home() / "data/live2/jpeg/combined_manifest.jsonl"
URL = "http://127.0.0.1:8031/v1/chat/completions"
RECENT_W = 120.0
SEEDS, N_DEV, RUN_S = (0, 4, 5, 6), 64, 600.0


def r1_questions():
    rows = [json.loads(l) for l in gzip.open(R1, "rt")]
    k1 = {r["question_id"]: r for r in rows if r["mode"] == "batched" and r["cell"] == "K1"}
    k3 = {r["question_id"]: r for r in rows if r["mode"] == "batched" and r["cell"] == "K3"}
    return k1, k3


def mcq():
    import ast
    out = {}
    for ln in open(REPO / "results/sember/study_h/data/sember_mcq.jsonl"):
        r = json.loads(ln)
        o = r["options"]
        out[r["question_id"]] = dict(question=r["question"], options=list(ast.literal_eval(o) if isinstance(o, str) else o),
                                     gold=r["correct_letter"], category=r.get("question_category", ""),
                                     video_id=r["video_id"], t=float(r["question_time"]))
    return out


def ref(vid, t):
    return f"{vid}|f{t:08.2f}"


def path_of(vid, t):
    return STORE / "frames" / vid / f"f{t:08.2f}.jpg"


def encode_dev(qs, ev):
    """D2 frames for DEV sessions, same recipe as Part 1 (study_rh3_inputs.load (352, 256), q88), store-once."""
    import study_rh3_inputs as B3
    need = defaultdict(float)
    for q, m in qs.items():
        if q not in ev:
            need[m["video_id"]] = max(need[m["video_id"]], m["t"])
    have = {json.loads(l)["frame_ref"] for l in open(STORE / "encode_log.jsonl")}
    rows = []
    for vid, tmax in sorted(need.items()):
        idx = json.load(open(SRC / vid / "index.json"))
        for t, fn in idx["frames"]:
            t = float(t)
            if t % 2.0 != 0 or t > tmax + 1e-9 or ref(vid, t) in have:
                continue
            dst = path_of(vid, t)
            if dst.exists():
                continue
            im = B3.load(str(SRC / vid / fn), (352, 256))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=88)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(buf.getvalue())
            rows.append(dict(file=f"{vid}/f{t:08.2f}.jpg", frame_ref=ref(vid, t), src=str(SRC / vid / fn),
                             size=[im.width, im.height], acc2_dev=True,
                             sha256=hashlib.sha256(buf.getvalue()).hexdigest()))
    with open(STORE / "encode_log.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    return len(rows), len(need)


def d2_times(t_q, t_from=0.0):
    out, t = [], 2.0 * (int(t_from // 2.0) + 1) if t_from > 0 else 2.0
    while t <= t_q + 1e-9:
        out.append(round(t, 2))
        t += 2.0
    return out


def prep():
    import data_sources as DS
    import trace as TR
    OUT.mkdir(parents=True, exist_ok=True)
    ev = DS._eval_question_ids()
    k1, k3 = r1_questions()
    M = mcq()
    qs = {q: M[q] for q in k1}
    n_new, n_dev_vids = encode_dev(qs, ev)
    plan = []
    for q, m in sorted(qs.items()):
        vid, tq = m["video_id"], m["t"]
        full = [t for t in d2_times(tq) if path_of(vid, t).exists()]
        miss = len(d2_times(tq)) - len(full)
        rec = [t for t in full if t > tq - RECENT_W + 1e-9]
        base = dict(question_id=q, split=("EVAL" if q in ev else "DEV"), category=m["category"], video_id=vid,
                    question_time=tq, r1_prompt_tokens=k1[q]["prompt_tokens"], frames_missing=miss)
        plan.append(dict(base, rep="D2", frame_times=full, source="r1-instant"))
        plan.append(dict(base, rep="RECENT", frame_times=rec, source="r1-instant"))
    # LONG-HISTORY set: exactly what the live trace carries at question arrival
    longs, seen = [], set()
    for seed in SEEDS:
        b = TR.generate_trace(seed, N_DEV, "50:50", RUN_S, "A", frame_manifest=COMBINED)
        hist = defaultdict(list)
        for r in b["records"]:
            if r["kind"] in ("history_preload", "history_batch"):
                hist[r["session_id"]].append(r)
        for r in b["records"]:
            if r["kind"] != "recall_question" or r["question_id"] not in k1:
                continue
            hs = sorted((h for h in hist[r["session_id"]] if h["t"] <= r["t"] + 1e-9), key=lambda h: h["t"])
            refs = [x for h in hs for x in h["frame_refs"]]
            cum = hs[-1].get("cum_tokens") if hs else 0
            if not refs or cum <= k1[r["question_id"]]["prompt_tokens"]:
                continue
            key = (r["question_id"], tuple(refs))
            if key in seen:
                continue
            seen.add(key)
            m = qs[r["question_id"]]
            longs.append(dict(question_id=r["question_id"], split=("EVAL" if r["question_id"] in ev else "DEV"),
                              category=m["category"], video_id=m["video_id"], question_time=m["t"],
                              r1_prompt_tokens=k1[r["question_id"]]["prompt_tokens"], rep="D2-LIVE-TRACE",
                              frame_refs=refs, trace_cum_tokens=cum, source=f"trace seed {seed} n{N_DEV}",
                              frames_missing=sum(1 for x in refs if not (Path.home() / "data/live2/frames_by_ref" / x).exists())))
    plan += longs
    for i, p in enumerate(plan):
        p["req"] = f"q{i:05d}"
    (OUT / "acc2_plan.json").write_text(json.dumps(dict(n=len(plan), n_long=len(longs), dev_frames_encoded=n_new,
                                                         dev_videos=n_dev_vids, plan=plan), indent=0) + "\n")
    tok = lambda p: len(p.get("frame_times") or p.get("frame_refs") or []) * 90
    print(json.dumps(dict(requests=len(plan), long=len(longs), dev_frames_encoded=n_new, dev_videos=n_dev_vids,
                          missing_frames=sum(p["frames_missing"] for p in plan),
                          est_prefill_tokens=sum(tok(p) for p in plan),
                          long_over_19400=sum(1 for p in plan if tok(p) > 19400))))


async def _one(c, p, model):
    import bodies as B
    import scores as S2
    from coordinator import HEADER_TEXT
    if p.get("frame_refs"):
        frames = [dict(frame_ref=x, path=Path.home() / "data/live2/frames_by_ref" / x) for x in p["frame_refs"]]
    else:
        frames = [dict(frame_ref=ref(p["video_id"], t), path=path_of(p["video_id"], t)) for t in p["frame_times"]]
    M = _MCQ[p["question_id"]]
    tag = "acc2-" + uuid.uuid4().hex[:12]
    body = B.build_body(kind="recall", device_id="acc2", session_id=p["video_id"], run_tag=tag,
                        salt=uuid.uuid4().hex, header=HEADER_TEXT, frames=frames, question=M["question"],
                        options=M["options"], max_tokens=B.RECALL_GEN["max_tokens"], est_tokens=len(frames) * 90)
    wire = dict(B.strip_internal(B.materialize(body, None), strip_hints=True), model=model)
    t0 = time.time()
    first, text, usage, err = None, [], {}, None
    try:
        async with c.stream("POST", URL, json=wire) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {(await r.aread())[:200]!r}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    j = json.loads(line[6:])
                    if j.get("usage"):
                        usage = j["usage"]
                    for ch in j.get("choices", []):
                        piece = (ch.get("delta") or {}).get("content")
                        if piece:
                            first = first or time.time()
                            text.append(piece)
    except Exception as e:                                                        # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    letter = S2.recall_letter("".join(text)).get("cloud_letter")
    return dict(req=p["req"], question_id=p["question_id"], rep=p["rep"], split=p["split"], category=p["category"],
                n_frames=len(frames), prompt_tokens=usage.get("prompt_tokens"),
                cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                ttft_s=(round(first - t0, 4) if first else None), e2e_s=round(time.time() - t0, 4),
                letter=letter, gold=M["gold"], correct=(letter == M["gold"]), text="".join(text)[:300], error=err,
                source=p["source"], question_time=p["question_time"], r1_prompt_tokens=p["r1_prompt_tokens"])


def run():
    global _MCQ
    import httpx
    import study_live2_pilot as PL
    _MCQ = mcq()
    plan = json.loads((OUT / "acc2_plan.json").read_text())["plan"]
    resf = OUT / "acc2_requests.jsonl"
    done = {json.loads(l)["req"] for l in open(resf)} if resf.exists() else set()
    todo = [p for p in plan if p["req"] not in done]
    PL.OUT = OUT
    PL.WORK = Path.home() / "data/acc2"
    PL.WORK.mkdir(parents=True, exist_ok=True)
    srv, sinfo, _M = PL.start_server(27.0)
    (OUT / "acc2_server.json").write_text(json.dumps(sinfo, indent=1, default=str) + "\n")
    print(f"server up; {len(todo)} requests to run", flush=True)

    async def go():
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as c:
            for i, p in enumerate(todo):
                r = await _one(c, p, "32BI")
                with open(resf, "a") as f:
                    f.write(json.dumps(r) + "\n")
                if i % 50 == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(todo)} {r['rep']} pt={r['prompt_tokens']} "
                          f"ct={r['cached_tokens']} ttft={r['ttft_s']} ok={r['correct']} err={r['error']}", flush=True)
    try:
        asyncio.run(go())
    finally:
        srv.stop()
    print("run done", flush=True)


_MCQ = {}

if __name__ == "__main__":
    {"prep": prep, "run": run}[sys.argv[1]]()
