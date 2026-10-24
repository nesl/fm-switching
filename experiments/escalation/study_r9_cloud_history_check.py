#!/usr/bin/env python3
"""StudyR9 — can the cloud cheaply tell whether a question needs history the device has pruned? (vLLM venv; H100 GPU 3)
Pre-registered in research/EXPERIMENTS.md (StudyR9). Accuracy and cost only; no fleet. Runs after StudyRH8.

Questions: the 845 S-EMBER questions of R1 (manifest order). Ground truth (analysis): R1 K3 evidence_covered == false.
Detectors (one vLLM server each, shared study_x_vllm.Server; bf16, greedy, prefix caching OFF, processor cache OFF
(--mm-processor-cache-gb 0), RH3's image flags; requests strictly one at a time):
  C0  32B-I, question + options only (no frames): single digit 0-9, max_tokens 1, top_logprobs 20;
      score = sum(d p(d)) / sum(p(d)) over the digit tokens.
  C1  4B-I on the RH3 A-format history (every 1-fps cache frame t <= qt, last 640, 160x128 oriented as RH3, RH3 A
      header) with a "[t=XXs]" text marker before each image (amendment: RH3 A has no per-frame time); asked for the
      time (s) where the evidence appears; max_tokens 16; score = (qt - 120) - t_pred.
  C2  C1 with 32B-I.
Pilot gate (mechanism check, before each detector's sweep): the first 30 manifest questions; STOP if parse rate < 80 %
or (C1/C2) every parsed timestamp is identical. GPU-seconds per question = end-to-end request latency.
"""
import argparse
import base64
import io
import json
import math
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cost"))
sys.path.insert(0, str(ROOT / "sember"))
sys.path.insert(0, str(ROOT / "lib"))
import study_x_vllm as X  # noqa: E402
import study_rh3_inputs as B  # noqa: E402
from rawio import read_jsonl  # noqa: E402

OUT = Path("results/escalation/study_r9")
REQ = OUT / f"study_r9_requests_{X.DEV}.jsonl"
X.META_PATH = OUT / f"study_r9_run_meta_{X.DEV}.json"
X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": B.MAX_IMAGES, "video": 0}),
         "--mm-processor-kwargs", json.dumps({"size": B.PROC_SIZE}), "--host", "127.0.0.1",
         "--mm-processor-cache-gb", "0"]
DETECTORS = {"C0": "32BI", "C2": "32BI", "C1": "4BI"}
ORDER = ("C0", "C1", "C2")
PILOT_N, PILOT_PARSE = 30, 0.80
RECENT_S = 120
R1_MANIFEST = Path("results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz")
MCQ = Path("results/sember/study_h/data/sember_mcq.jsonl")
DIGITS = [str(d) for d in range(10)]

C0_PROMPT = ("An assistant answers questions about a person's egocentric camera video, but it can see only the last "
             "120 seconds of video before each question is asked.\n\nQuestion: {q}\n\n{opts}\n\nHow likely is it that "
             "answering this question needs observations from MORE than 120 seconds before the question was asked? "
             "Reply with a single digit from 0 (certainly answerable from the last 120 seconds) to 9 (certainly needs "
             "older observations).")
LOC_PROMPT = ("The question below is asked at t={qt}s.\n\nQuestion: {q}\n\n{opts}\n\nAt what time (in seconds from the "
              "start of this camera history) does the evidence needed to answer this question appear? Reply with only "
              "a number of seconds.")


# ------------------------------------------------------------------------------------------------ inputs
def questions():
    mcq = {r["question_id"]: r for r in map(json.loads, open(MCQ))}
    rows = [r for r in read_jsonl(R1_MANIFEST) if r["construction"] == "RECENT"]
    out = []
    for r in rows:
        m = mcq[r["question_id"]]
        out.append(dict(question_id=r["question_id"], video_id=r["video_id"], qt=float(r["question_time"]),
                        question=m["question"], options=m["options"], category=r["question_category"],
                        answer_start=m["answer_start_time"], answer_end=m["answer_end_time"]))
    return out


def history(q):
    idx = B.frames_index(q["video_id"])
    ts = sorted(t for t in idx if t <= q["qt"] + 1e-6)[-B.MAX_IMAGES:]
    return [(t, idx[t]) for t in ts]


def _enc(job):
    vid, t, path = job
    im = B.load(path, B.SIZE_A)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return (vid, t), "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


_IMG = {}


def preencode(qs, procs=24):
    jobs = sorted({(q["video_id"], t, str(p)) for q in qs for t, p in history(q)})
    t0 = time.time()
    with Pool(procs) as pool:
        for k, v in pool.imap_unordered(_enc, jobs, chunksize=64):
            _IMG[k] = v
    X.log(f"pre-encoded {len(jobs)} frames (160x128 PNG) in {time.time() - t0:.0f}s "
          f"({sum(len(v) for v in _IMG.values()) / 2 ** 30:.2f} GiB b64)")


def body(det, q):
    opts = "\n".join(q["options"])
    if det == "C0":
        content = [{"type": "text", "text": C0_PROMPT.format(q=q["question"], opts=opts)}]
        extra = dict(max_tokens=1, logprobs=True, top_logprobs=20)
        n_img = 0
    else:
        content = [{"type": "text", "text": B.HEADERS["A"]}]
        h = history(q)
        for t, _ in h:
            content.append({"type": "text", "text": f"[t={int(round(t))}s]"})
            content.append({"type": "image_url", "image_url": {"url": _IMG[(q["video_id"], t)]}})
        content.append({"type": "text", "text": LOC_PROMPT.format(qt=int(round(q["qt"])), q=q["question"], opts=opts)})
        extra = dict(max_tokens=16)
        n_img = len(h)
    return dict(model=DETECTORS[det], temperature=0.0, seed=0, messages=[{"role": "user", "content": content}],
                **extra), n_img


# ------------------------------------------------------------------------------------------------ scoring
def digit_score(choice):
    lp = (((choice.get("logprobs") or {}).get("content") or [{}])[0]).get("top_logprobs") or []
    p = {}
    for x in lp:
        tok = x["token"].strip()
        if tok in DIGITS:
            p[tok] = p.get(tok, 0.0) + math.exp(x["logprob"])
    tot = sum(p.values())
    return (sum(int(d) * v for d, v in p.items()) / tot if tot > 0 else None), p, tot


def parse_time(text):
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else None


def interval_distance(t, a, b):
    lo, hi = min(a, b), max(a, b)
    return 0.0 if lo <= t <= hi else min(abs(t - lo), abs(t - hi))


def run_one(client, det, q):
    data, n_img = body(det, q)
    t0 = time.time()
    err, j = None, {}
    try:
        r = client.post(f"{X.BASE}/v1/chat/completions", json=data)
        if r.status_code == 200:
            j = r.json()
        else:
            err = f"HTTP {r.status_code}: {r.text[:300]}"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    lat = time.time() - t0
    ch = (j.get("choices") or [{}])[0]
    text = (ch.get("message") or {}).get("content")
    u = j.get("usage") or {}
    rec = dict(detector=det, model=DETECTORS[det], question_id=q["question_id"], video_id=q["video_id"], qt=q["qt"],
               category=q["category"], n_images=n_img, prompt_tokens=u.get("prompt_tokens"),
               completion_tokens=u.get("completion_tokens"), text=text, latency_s=round(lat, 4), error=err,
               answer_start=q["answer_start"], answer_end=q["answer_end"])
    if det == "C0":
        s, p, tot = digit_score(ch)
        rec.update(score=s, digit_probs=p, digit_mass=tot, parse_ok=s is not None,
                   text_digit=int(text.strip()) if text and text.strip() in DIGITS else None)
    else:
        t = parse_time(text)
        rec.update(t_pred=t, parse_ok=t is not None, score=(q["qt"] - RECENT_S) - t if t is not None else None,
                   dist_to_interval_s=interval_distance(t, q["answer_start"], q["answer_end"]) if t is not None
                   else None, older_than_window=(t < q["qt"] - RECENT_S) if t is not None else None)
    return rec


def pilot_gate(recs, det):
    pr = sum(r["parse_ok"] for r in recs) / len(recs)
    ts = {r.get("t_pred") for r in recs if r["parse_ok"]}
    degenerate = det != "C0" and len(ts) <= 1
    return dict(n=len(recs), parse_rate=pr, distinct_values=len(ts) if det != "C0" else None,
                passed=pr >= PILOT_PARSE and not degenerate)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--detectors", default=",".join(ORDER))
    ap.add_argument("--limit", type=int, default=None, help="smoke only: questions per detector")
    ap.add_argument("--out", default=None, help="smoke only: output dir (not results/)")
    args = ap.parse_args()
    global REQ
    if args.out:
        d = Path(args.out)
        d.mkdir(parents=True, exist_ok=True)
        REQ, X.META_PATH = d / "req.jsonl", d / "meta.json"
    OUT.mkdir(parents=True, exist_ok=True)
    qs = questions()
    if args.limit:
        qs = qs[:args.limit]
    X.log(f"{len(qs)} questions")
    dets = [d for d in args.detectors.split(",") if not X.is_done(f"R9_{d}")]
    if any(d != "C0" for d in dets):
        preencode(qs)
    for det in dets:
        srv = X.Server(DETECTORS[det], FLAGS)
        info = srv.start()
        m = X.meta_load()
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        m.setdefault("servers", []).append(dict(detector=det, **info))
        X.meta_save(m)
        recs = []
        try:
            with httpx.Client(timeout=600) as client:
                run_one(client, det, qs[0])                       # warm-up request (not recorded), as RH3/R1
                for i, q in enumerate(qs):
                    recs.append(run_one(client, det, q))
                    if i + 1 == min(PILOT_N, len(qs)):
                        g = pilot_gate(recs, det)
                        X.log(f"R9 {det} pilot gate: {g}")
                        m = X.meta_load()
                        m.setdefault("pilot", {})[det] = dict(g, rows=recs[:PILOT_N])
                        X.meta_save(m)
                        if not g["passed"] and not args.limit:
                            raise SystemExit(f"R9 {det} pilot gate FAILED {g} — STOP")
                    if (i + 1) % 100 == 0:
                        X.log(f"R9 {det}: {i + 1}/{len(qs)}; median latency "
                              f"{sorted(r['latency_s'] for r in recs)[len(recs) // 2]:.2f}s; parse "
                              f"{sum(r['parse_ok'] for r in recs) / len(recs):.3f}")
        finally:
            srv.stop()
            with open(REQ, "a") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")
        X.mark_done(f"R9_{det}", n=len(recs), errors=sum(bool(r["error"]) for r in recs),
                    parse_rate=sum(r["parse_ok"] for r in recs) / max(1, len(recs)))
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_r9_cloud_history_check.py",
                                                 model="qwen3vl-32b-instruct+qwen3vl-4b-instruct", device=X.DEV,
                                                 n=len(qs), args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
