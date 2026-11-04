#!/usr/bin/env python3
"""StudyD11 GPU runner — arms U (real older frames), I (donor frames), F (format control), h100nvl GPU 2.

Stack: StudyClean's (vLLM 0.31.0 venv, FA3, max_model_len 32768, gmu 0.90, prefix caching OFF, conc 8, greedy,
max_tokens 512, request seed 42, R1's engine-level --mm-processor-kwargs fps 1.0 / do_sample_frames False,
--trust-request-mm-kwargs) with TWO changes, both checked by the CHECK stage before any arm runs:
  (1) --limit-mm-per-prompt {"image": 0, "video": 2} (was video 1) and --mm-processor-cache-gb 0;
  (2) videos sent through the 'npz_frames' loader (d11_npz_video_loader.py; registered in the server processes via
      d11_site/sitecustomize.py) because R1's jpeg-sequence transport takes one frames_indices list per request.
      Each video carries its own uint8 frames (R1's / D11's npz arrays, unchanged) and frames_indices.
CHECK (per model): first 30 R1-order K3 requests (a) in R1's original jpeg transport and (b) as one npz video, on the
new config: letters and prompt tokens must equal the reference (32B: R1 K3; 4B: StudyClean H1) — STOP on any
difference. Max prompt tokens vs 32,768: bound = K1 + K3 tokens per question (U and I send a subset of K1's frames plus
K3's video) — STOP if any bound exceeds it (no truncation). 32B also writes one complete decoded prompt (U, trace
question) to results/cost/study_d11/study_d11_prompt_trace.txt.
Arms (cells U32/U4, I32/I4, F32/F4; inputs from study_d11_inputs.py):
  U  [K1 older-frames video (if any), K3 video]   I  [donor video (if any), K3 video]   F  K3 split at k (qt > 120 only)
Negative control after U: at qt <= 120 U is K3's one video, so U letters must equal the reference arm — STOP on any
mismatch (to be explained before I runs). STOP: > 1 % errors in a cell.
Usage: study_d11_vllm.py --model 32BI|4BI --stages CHECK,U,I,F
"""
import argparse
import asyncio
import base64
import gzip
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_clean_vllm as C  # noqa: E402  (R.manifest -> committed .jsonl.gz; GPU check -> CLEAN_GPU_UUID)
from rawio import read_jsonl  # noqa: E402

X, R = C.X, C.R
OUT = Path("results/cost/study_d11")
REQ = OUT / f"study_d11_requests_{X.DEV}.jsonl"
META = OUT / f"study_d11_run_meta_{X.DEV}.json"
MAN = OUT / "study_d11_inputs_manifest.jsonl"
TRACE = OUT / "study_d11_prompt_trace.txt"
DIN = Path.home() / ".cache/fm-switching/d11_inputs"
X.META_PATH = META
X.CURRENT = Path("logs/study_d11_current.json")
R.REQ = REQ
W = 120.0
MAXLEN = 32768
CHECK_N = 30
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 0, "video": 2}),
         "--mm-processor-kwargs", json.dumps({"fps": 1.0, "do_sample_frames": False}),
         "--trust-request-mm-kwargs", "--mm-processor-cache-gb", "0", "--host", "127.0.0.1"]
GREEDY = dict(temperature=0.0, max_tokens=512)
REF = {"32BI": ("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "K3"),
       "4BI": ("results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz", "H1")}
SHORT = {"32BI": "32", "4BI": "4"}


def npz_url(frames_chw, idx, total):
    buf = io.BytesIO()
    np.savez(buf, frames=np.ascontiguousarray(frames_chw.transpose(0, 2, 3, 1)), frames_indices=np.array(idx, np.int64),
             fps=np.float64(1.0), total_num_frames=np.int64(max(total, len(idx))))
    return "data:video/x-npz;base64," + base64.b64encode(buf.getvalue()).decode()


def load_r1(cons, q):
    z = np.load(R.INP / cons / f"{q}.npz")
    return z["frames"], [int(i) for i in z["frames_indices"]]


def videos(arm, row, m):
    """[(frames CHW uint8, frames_indices)] for the arm, in order."""
    q = row["question_id"]
    k3 = load_r1("RECENT", q)
    if arm in ("K3N",):
        return [k3]
    if arm == "F":
        k = m["F_split"]["k"]
        return [(k3[0][:k], k3[1][:k]), (k3[0][k:], k3[1][k:])]
    if m["n_old"] == 0:
        return [k3]
    if arm == "U":
        fr, idx = load_r1("RICH", q)
        n = m["n_old"]
        fr, idx = fr[:n], idx[:n]
        if n % 2:
            fr, idx = np.concatenate([fr, fr[-1:]], 0), idx + [idx[-1]]
        v1 = (fr, idx)
    else:  # I
        z = np.load(DIN / "I" / f"{q}.npz")
        v1 = (z["frames"], [int(i) for i in z["frames_indices"]])
    return [v1, k3]


def body(arm, row, m, model, max_tokens=None, token_ids=False, stream=True):
    vs = videos(arm, row, m)
    total = int(row["total_num_frames"])
    content = [{"type": "video_url", "video_url": {"url": npz_url(f, i, total)}} for f, i in vs]
    content.append({"type": "text", "text": row["text"]})
    p = dict(GREEDY)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    b = dict(model=model, stream=stream, seed=R.SEED, messages=[{"role": "user", "content": content}],
             media_io_kwargs={"video": {"video_backend": "npz_frames", "num_frames": -1}}, **p)
    if stream:
        b["stream_options"] = {"include_usage": True}
    if token_ids:
        b["return_token_ids"] = True
    return b, [len(i) for _, i in vs]


async def run(cell, arm, model, rows, order, man, qs, conc=R.CONC):
    have = R.done(cell, "batched")
    todo = [q for q in qs if q not in have]
    X.log(f"D11 {cell}: {len(todo)} to run (conc {conc})")
    sem = asyncio.Semaphore(conc)
    n = 0

    async def one(c, q):
        nonlocal n
        async with sem:
            row = rows[(q, "RECENT")]
            if arm == "K3J":
                b, _, _ = await asyncio.to_thread(C.R1_BODY, row, cell, model, GREEDY)
                nv = [row["n_frames"]]
            else:
                b, nv = await asyncio.to_thread(body, arm, row, man[q], model)
            X.CURRENT.write_text(json.dumps(dict(cell=cell, q=q)))
            rec = await R.send(c, b, row, cell, "batched")
            rec.update(arm=arm, model=model, frames_per_video=nv, n_videos=len(nv), stratum_qt_le_120=row[
                "question_time"] <= W)
            R.append(rec)
            n += 1
            if n % 100 == 0:
                X.log(f"D11 {cell}: {n}/{len(todo)}")
    async with httpx.AsyncClient(timeout=None) as c:
        await asyncio.gather(*(one(c, q) for q in todo))
    rs = [r for r in read_jsonl(REQ) if r["cell"] == cell]
    err = sum(bool(r["error"]) for r in rs)
    X.log(f"D11 {cell}: {len(rs)} rows, {err} errors, acc {sum(r['correct'] for r in rs) / max(1, len(rs)):.4f}")
    if err > 0.01 * len(rs):
        raise SystemExit(f"D11 {cell}: {err} errors > 1 % — STOP")
    return {r["question_id"]: r for r in rs if not r["error"]}


def ref_rows(model):
    p, cell = REF[model]
    return {r["question_id"]: r for r in read_jsonl(Path(p)) if r["cell"] == cell and r["mode"] == "batched"}


def gate(name, got, ref, qs, m, key):
    bad = [dict(question_id=q, pred=got[q]["pred"], ref_pred=ref[q]["pred"], tokens=got[q]["prompt_tokens"],
                ref_tokens=ref[q]["prompt_tokens"]) for q in qs
           if got[q]["pred"] != ref[q]["pred"] or got[q]["prompt_tokens"] != ref[q]["prompt_tokens"]]
    res = dict(n=len(qs), letters_equal=sum(got[q]["pred"] == ref[q]["pred"] for q in qs),
               tokens_equal=sum(got[q]["prompt_tokens"] == ref[q]["prompt_tokens"] for q in qs), mismatches=bad,
               passed=not bad and len(qs) == len([q for q in qs if q in got]))
    mm = X.meta_load()
    mm.setdefault("gates", {})[f"{key}_{name}"] = res
    X.meta_save(mm)
    X.log(f"D11 GATE {key} {name}: letters {res['letters_equal']}/{len(qs)} tokens {res['tokens_equal']}/{len(qs)}")
    if not res["passed"]:
        raise SystemExit(f"D11 GATE {name} FAILED for {key} — STOP")


async def prompt_trace(model, rows, man, tq):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(X.snapshot(model))
    b, nv = body("U", rows[(tq, "RECENT")], man[tq], model, max_tokens=1, token_ids=True, stream=False)
    async with httpx.AsyncClient(timeout=None) as c:
        r = (await c.post(f"{X.BASE}/v1/chat/completions", json=b)).json()
    ids = r.get("prompt_token_ids") or []
    pieces, run_tok, run_n = [], None, 0
    for t in ids:
        s = tok.decode([t])
        if s == run_tok:
            run_n += 1
            continue
        if run_tok is not None:
            pieces.append(run_tok if run_n == 1 else f"{run_tok}×{run_n}")
        run_tok, run_n = s, 1
    if run_tok is not None:
        pieces.append(run_tok if run_n == 1 else f"{run_tok}×{run_n}")
    m = man[tq]
    hdr = (f"# StudyD11 arm U, one complete prompt as tokenised by the server (vLLM return_token_ids; repeated "
           f"identical tokens collapsed as TOKEN×N)\n# model {model}; question {tq}; qt {m['question_time']}; "
           f"videos {nv} frames; prompt_tokens {r.get('usage', {}).get('prompt_tokens')}\n"
           f"# video 1 = K1 older frames (sha256 {m.get('u_v1_sha256')}), video 2 = K3 (sha256 {m['k3_sha256']})\n\n")
    TRACE.write_text(hdr + "".join(pieces))
    X.log(f"prompt trace written ({len(ids)} ids)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["32BI", "4BI"], required=True)
    ap.add_argument("--stages", default="CHECK,U,I,F")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    man = {r["question_id"]: r for r in map(json.loads, open(MAN))}
    rows, order = R.manifest()
    assert len(order) == 845 and set(man) == set(order)
    s = SHORT[a.model]
    ref = ref_rows(a.model)
    # token bound (no truncation): U / I <= K1 + K3 tokens
    bound = {q: rows[(q, "RICH")]["n_input_instruct"] + rows[(q, "RECENT")]["n_input_instruct"] for q in order}
    mm = X.meta_load()
    mm["token_bound"] = dict(max=max(bound.values()), limit=MAXLEN, over=[q for q, v in bound.items() if v > MAXLEN],
                             note="U/I prompt <= K1 + K3 prompt tokens (video 1 is a subset of K1's frames)")
    X.meta_save(mm)
    if mm["token_bound"]["over"]:
        raise SystemExit("token bound exceeds --max-model-len — STOP (no truncation)")
    os.environ["PYTHONPATH"] = str(HERE / "d11_site") + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.environ["D11_NPZ_LOADER"] = "1"
    srv = X.Server(a.model, FLAGS)
    try:
        info = srv.start()
        import torch
        import vllm
        mm = X.meta_load()
        mm["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu_uuid=C.GPU_UUID,
                           flags=FLAGS, transport="npz_frames loader (d11_npz_video_loader.py)")
        mm.setdefault("servers", []).append(dict(model=a.model, started=datetime.now().isoformat(), **info))
        X.meta_save(mm)
        st = a.stages.split(",")
        if "CHECK" in st:
            qs = order[:CHECK_N]
            got = asyncio.run(run(f"CHKJ{s}", "K3J", a.model, rows, order, man, qs))
            gate("jpeg_transport_video2", got, ref, qs, None, a.model)
            got = asyncio.run(run(f"CHKN{s}", "K3N", a.model, rows, order, man, qs))
            gate("npz_transport_video2", got, ref, qs, None, a.model)
            if a.model == "32BI":
                tq = next(q for q in order if man[q]["question_time"] > 300 and man[q]["n_old"] > 0)
                asyncio.run(prompt_trace(a.model, rows, man, tq))
        if "U" in st:
            got = asyncio.run(run(f"U{s}", "U", a.model, rows, order, man, order))
            le = [q for q in order if man[q]["question_time"] <= W]
            mis = [dict(question_id=q, pred=got[q]["pred"], ref=ref[q]["pred"]) for q in le if got[q]["pred"] != ref[q]["pred"]]
            mm = X.meta_load()
            mm.setdefault("negative_control", {})[a.model] = dict(n=len(le), mismatches=mis,
                                                                  tokens_equal=sum(got[q]["prompt_tokens"] == ref[q]["prompt_tokens"] for q in le))
            X.meta_save(mm)
            X.log(f"D11 NEGATIVE CONTROL {a.model}: qt<=120 letter mismatches {len(mis)}/{len(le)}")
            if mis:
                raise SystemExit("negative control: U != reference at qt <= 120 — STOP")
        if "I" in st:
            gi = asyncio.run(run(f"I{s}", "I", a.model, rows, order, man, order))
            gu = {r["question_id"]: r for r in read_jsonl(REQ) if r["cell"] == f"U{s}" and not r["error"]}
            rel = {q: (gi[q]["prompt_tokens"] - gu[q]["prompt_tokens"]) / gu[q]["prompt_tokens"] for q in gi if q in gu}
            bad = [q for q, v in rel.items() if abs(v) > 0.01]
            mm = X.meta_load()
            mm.setdefault("i_vs_u_tokens", {})[a.model] = dict(
                n=len(rel), exact=sum(v == 0 for v in rel.values()), max_abs_rel=max(abs(v) for v in rel.values()),
                outside_1pct=bad)
            X.meta_save(mm)
            X.log(f"D11 I vs U tokens {a.model}: exact {mm['i_vs_u_tokens'][a.model]['exact']}/{len(rel)}, "
                  f"outside 1 % {len(bad)}")
            if bad:
                raise SystemExit("I prompt tokens differ from U by > 1 % — STOP")
        if "F" in st:
            asyncio.run(run(f"F{s}", "F", a.model, rows, order, man, [q for q in order if man[q]["question_time"] > W]))
    finally:
        srv.stop()
    from _provenance import stamp
    mm = X.meta_load()
    mm.setdefault("_provenance", []).append(stamp(script="study_d11_vllm.py", model=a.model, device=f"{X.DEV}_gpu2",
                                                  n=845, args=a))
    X.meta_save(mm)


if __name__ == "__main__":
    main()
