#!/usr/bin/env python3
"""StudyF3-latency — single-request latency, EXCLUSIVE (vLLM venv; h100nvl GPU 1). Pre-registered in EXPERIMENTS.md.

Runs only when nothing else of ours runs on the host (GPU or CPU). A monitor thread logs, at start, every 30 s and at
end: every GPU process on the host with its owner and memory, GPU 1's UUID / SM clock / utilisation, CPU use per user
(ps), and any process of ours outside this job's process tree. If one of ours appears (python / vllm / ffmpeg /
torch, or > 20 % CPU), the run is marked VOID in the meta and stopped.
Protocol: one request at a time, localhost, streaming with usage; each body is serialised to bytes BEFORE the clock
starts; TTFT = first streamed chunk carrying content; total = last byte. max_tokens 8, greedy. After every server
load the first request (a question outside the cell's sample) is sent and discarded (`discarded: true`).
Prefix caching OFF (cached_tokens must be 0) except cell d (WARM, prefix caching ON). Processor cache off everywhere.
Cells (model x format x cache state; one server load per group):
  a  F1 short windows N = 1, 3, 9 (separate 560x560 images): 50 questions (seed 0), 4B and 32B
  b  D11 arm U (two videos, npz transport, D11 flags), COLD: 60 = 6 equal-width prompt-token bins x 10, 4B and 32B
  c  RH4 D2 (separate 352x256 images, RH4 image flags), COLD: 60 as b, 32B only
  d  RH4 D2 WARM (same + --enable-prefix-caching): 10 sessions (videos, seed 0), each session's questions in time
     order, append-only (each request's images extend the previous one's); cached tokens per request; 32B only
  e  F2 summary + K3 video (R1 transport, R1 flags): 50 questions with qt > 120 (seed 0), 4B and 32B
  f  K1 and K3, 32B: 30 each (seed 0) in VIDEO format (R1 transport, as their accuracy runs) and 30 each as SEPARATE
     IMAGES of the same npz frames (image flags, processor size = PROC_SIZE so frames are not rescaled)
Rows -> results/cost/study_f3/f3_requests_h100nvl.jsonl; monitor -> f3_monitor_h100nvl.jsonl. Resumable per group.
Usage: study_f3_latency.py [--groups ...]
"""
import argparse
import base64
import gzip
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sember"))
sys.path.insert(0, str(HERE.parent / "lib"))
import study_d11_vllm as D  # noqa: E402  (imports study_clean_vllm -> study_r1_vllm, study_rh3_warmable)
import study_rh4_fixed_stride as RH  # noqa: E402
import study_f_common as F  # noqa: E402  (sets port 8031, GPU 1 checks; imported last so its X settings win)
import study_f1_infer_vllm as F1  # noqa: E402
import study_f2_infer_vllm as F2  # noqa: E402

X, C, R, W3, B3 = F.X, D.C, D.R, D.C.W3, D.C.W3.B
F2.R1BODY = C.R1_BODY      # R1's original body (R.body is rebound by the RH4 import)
OUT = REPO / "results/cost/study_f3"
REQ = OUT / "f3_requests_h100nvl.jsonl"
MON = OUT / "f3_monitor_h100nvl.jsonl"
META = OUT / "f3_run_meta_h100nvl.json"
X.META_PATH = META
X.CURRENT = REPO / "logs/f3_current.json"
GEN = dict(temperature=0.0, max_tokens=8)
CACHE_OFF = ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
F1_FLAGS = F1.FLAGS
R1_FLAGS = F2.FLAGS
D11_FLAGS = D.FLAGS + ["--enable-prompt-tokens-details"]
IMG_FLAGS = W3.IMAGE_FLAGS + CACHE_OFF
IMG256_FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 256, "video": 0}),
                "--mm-processor-kwargs", json.dumps({"size": B3.PROC_SIZE}), "--host", "127.0.0.1"] + CACHE_OFF
WARM_FLAGS = IMG_FLAGS + ["--enable-prefix-caching"]
OURS_PAT = ("python", "vllm", "ffmpeg", "torch")
SAFE_CMDS = ("claude", "node", "sshd", "bash", "tmux", "systemd", "sd-pam", "pipewire", "dbus", "ps ", "nvidia-smi",
             "sleep", "sh ", "code-server", "/bin/sh", "tail", "grep", "awk", "cat")
VOID = threading.Event()
STOP = threading.Event()


# ------------------------------------------------------------------------------------------------ monitor
def tree(root):
    out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True).stdout.split("\n")
    kids = {}
    for l in out:
        if l.strip():
            p, pp = map(int, l.split())
            kids.setdefault(pp, []).append(p)
    seen, st = set(), [root]
    while st:
        p = st.pop()
        if p not in seen:
            seen.add(p)
            st += kids.get(p, [])
    return seen


def snapshot(tag):
    procs = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                           capture_output=True, text=True).stdout.strip().splitlines()
    gpu = []
    for l in procs:
        u, pid, mem = l.split(", ")
        try:
            user = subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip()
        except Exception:  # noqa: BLE001
            user = "?"
        gpu.append(dict(gpu_uuid=u, pid=int(pid), user=user, mem=mem))
    ps = subprocess.run(["ps", "-eo", "user=,pid=,pcpu=,args="], capture_output=True, text=True).stdout.splitlines()
    cpu_by_user, ours_outside = {}, []
    mine = tree(os.getpid())
    for l in ps:
        parts = l.split(None, 3)
        if len(parts) < 4:
            continue
        user, pid, pcpu, args = parts[0], int(parts[1]), float(parts[2]), parts[3]
        cpu_by_user[user] = round(cpu_by_user.get(user, 0.0) + pcpu, 1)
        if user == F.ME and pid not in mine:
            low = args.lower()
            if (any(k in low for k in OURS_PAT) or pcpu > 20) and not any(low.startswith(s) or f"/{s}" in low.split()[0]
                                                                          for s in SAFE_CMDS):
                ours_outside.append(dict(pid=pid, pcpu=pcpu, args=args[:160]))
    rec = dict(tag=tag, at=F.now(), gpu1_uuid=F.GPU_UUID, gpu1=F.sm_clock(), gpu_procs=gpu,
               cpu_pct_by_user=dict(sorted(cpu_by_user.items(), key=lambda kv: -kv[1])[:8]),
               ours_outside_job=ours_outside, foreign_on_gpu1=F.foreign())
    with open(MON, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def monitor():
    while not STOP.wait(30):
        rec = snapshot("30s")
        if rec["ours_outside_job"]:
            X.log(f"!!! process of ours outside the job: {rec['ours_outside_job'][:3]} — VOID")
            VOID.set()
        if rec["foreign_on_gpu1"]:
            X.log(f"!!! foreign process on GPU 1: {rec['foreign_on_gpu1']} — STOP")
            VOID.set()


# ------------------------------------------------------------------------------------------------ timing
def timed(body, meta):
    if VOID.is_set():
        raise SystemExit("run VOID (overlap or foreign GPU process) — STOP")
    body = dict(body, stream=True, stream_options={"include_usage": True}, **GEN)
    body.pop("logprobs", None)
    body.pop("top_logprobs", None)
    bb = json.dumps(body).encode()
    sm0 = F.sm_clock()
    err, ttft, usage, text, fin = None, None, {}, "", None
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=None) as c:
            with c.stream("POST", f"{X.BASE}/v1/chat/completions", content=bb,
                          headers={"content-type": "application/json"}) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {r.read()[:300]!r}"
                else:
                    for line in r.iter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        j = json.loads(line[6:])
                        if j.get("usage"):
                            usage = j["usage"]
                        for ch in j.get("choices", []):
                            d = (ch.get("delta") or {}).get("content")
                            if d:
                                if ttft is None:
                                    ttft = time.perf_counter() - t0
                                text += d
                            if ch.get("finish_reason"):
                                fin = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    total = time.perf_counter() - t0
    rec = dict(meta, ttft_s=None if ttft is None else round(ttft, 5), total_s=round(total, 5),
               prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
               cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"), text=text,
               finish_reason=fin, body_bytes=len(bb), sm_at_send=sm0, error=err, at=F.now())
    with open(REQ, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


# ------------------------------------------------------------------------------------------------ samples
def r1_rows():
    return {(r["question_id"], r["construction"]): r for r in map(json.loads, gzip.open(REPO / R.MANIFEST.with_suffix(
        ".jsonl.gz") if not str(R.MANIFEST).endswith(".gz") else REPO / R.MANIFEST, "rt"))}


def binned(tok, k=6, per=10, seed=0):
    qs = sorted(tok)
    lo, hi = min(tok.values()), max(tok.values())
    edges = [lo + (hi - lo) * i / k for i in range(k + 1)]
    rng = random.Random(seed)
    out, counts = [], []
    for i in range(k):
        b = [q for q in qs if edges[i] <= tok[q] < edges[i + 1] or (i == k - 1 and tok[q] == hi)]
        pick = rng.sample(b, min(per, len(b)))
        counts.append(dict(bin=i, lo=round(edges[i]), hi=round(edges[i + 1]), available=len(b), sampled=len(pick)))
        out += [(q, i) for q in pick]
    return out, counts


def plan():
    r1 = {}
    for r in map(json.loads, gzip.open(REPO / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz", "rt")):
        r1[(r["question_id"], r["construction"])] = r
    qids = sorted({q for q, _ in r1})
    rng = random.Random(0)
    p = {}
    p["a"] = sorted(rng.sample(qids, 50))
    u_tok = {}
    for r in map(json.loads, open(REPO / "results/cost/study_d11/study_d11_requests_h100nvl.jsonl")):
        if r.get("cell") == "U32" and not r["error"]:
            u_tok[r["question_id"]] = r["prompt_tokens"]
    p["b"], p["b_bins"] = binned(u_tok)
    d2_tok = {}
    for r in map(json.loads, gzip.open(REPO / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz", "rt")):
        if r["cell"] == "D2" and r["mode"] == "batched" and not r["error"]:
            d2_tok[r["question_id"]] = r["prompt_tokens"]
    p["c"], p["c_bins"] = binned(d2_tok)
    rh4 = {r["question_id"]: r for r in map(json.loads, gzip.open(REPO / "results/sember/study_rh4/study_rh4_inputs_manifest.jsonl.gz", "rt"))
           if r["cell"] == "D2"}
    byv = {}
    for q, r in rh4.items():
        if q in d2_tok:
            byv.setdefault(r["video_id"], []).append((float(r["question_time"]), q))
    vids = sorted(v for v, l in byv.items() if len(l) >= 3)
    sess = random.Random(0).sample(vids, 11)
    p["d_warmup_session"] = sess[0]
    p["d"] = [(v, [q for _, q in sorted(byv[v])]) for v in sess[1:]]
    p["e"] = sorted(random.Random(0).sample([q for q in qids if float(r1[(q, "RECENT")]["question_time"]) > 120], 50))
    p["f"] = sorted(random.Random(0).sample(qids, 30))
    return p, r1, rh4


# ------------------------------------------------------------------------------------------------ bodies
F1ROWS = None


def f1_body(q, n, model):
    row = F1ROWS[(q, n)]
    b, _ = F1.body(row, model)
    return b, dict(n_frames=row["n_frames"])


def k_images_body(row, model):
    z = np.load(R.INP / row["construction"] / f"{row['question_id']}.npz")
    content = []
    for fr in z["frames"]:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + R.png_b64(fr)}})
    content.append({"type": "text", "text": row["text"]})
    return dict(model=model, seed=R.SEED, messages=[{"role": "user", "content": content}]), dict(n_frames=len(z["frames"]))


GROUPS = [  # (group, model, flags, env_extra)
    ("a_4BI", "4BI", F1_FLAGS, {}), ("b_4BI", "4BI", D11_FLAGS, {"d11": 1}), ("e_4BI", "4BI", R1_FLAGS, {}),
    ("a_32BI", "32BI", F1_FLAGS, {}), ("b_32BI", "32BI", D11_FLAGS, {"d11": 1}), ("c_32BI", "32BI", IMG_FLAGS, {}),
    ("d_32BI", "32BI", WARM_FLAGS, {}), ("ef_32BI", "32BI", R1_FLAGS, {}), ("fimg_32BI", "32BI", IMG256_FLAGS, {}),
]


def items(group, model, p, r1, rh4, f2rows, d11man):
    """[(cell, label, question_id, extra_meta, body_fn)] in send order; the first item is the discarded warm-up."""
    out = []
    qids = sorted({q for q, _ in r1})
    if group.startswith("a_"):
        wq = next(q for q in qids if q not in p["a"])
        out.append(("a", "discard", wq, dict(n=9), lambda q=wq: f1_body(q, 9, model)))
        for n in (1, 3, 9):
            for q in p["a"]:
                out.append((f"a_N{n}", "cold", q, dict(n=n), lambda q=q, n=n: f1_body(q, n, model)))
    elif group.startswith("b_"):
        sel = {q for q, _ in p["b"]}
        wq = next(q for q in qids if q not in sel)
        def ub(q):
            b, nv = D.body("U", r1[(q, "RECENT")], d11man[q], model, max_tokens=8)
            return b, dict(frames_per_video=nv)
        out.append(("b", "discard", wq, {}, lambda q=wq: ub(q)))
        out += [("b_U", "cold", q, dict(bin=i), lambda q=q: ub(q)) for q, i in p["b"]]
    elif group.startswith("c_"):
        sel = {q for q, _ in p["c"]}
        wq = next(q for q in rh4 if q not in sel and not rh4[q]["over_context"])
        def cb(q):
            b, _, n = RH.body(dict(rh4[q]), "D2", model, dict(temperature=0.0))
            return b, dict(n_images=n)
        out.append(("c", "discard", wq, {}, lambda q=wq: cb(q)))
        out += [("c_D2", "cold", q, dict(bin=i), lambda q=q: cb(q)) for q, i in p["c"]]
    elif group.startswith("d_"):
        def cb(q):
            b, _, n = RH.body(dict(rh4[q]), "D2", model, dict(temperature=0.0))
            return b, dict(n_images=n)
        wv = p["d_warmup_session"]
        wq = min((q for q in rh4 if rh4[q]["video_id"] == wv), key=lambda q: float(rh4[q]["question_time"]))
        out.append(("d", "discard", wq, {}, lambda q=wq: cb(q)))
        for si, (v, qs) in enumerate(p["d"]):
            for j, q in enumerate(qs):
                out.append(("d_D2_WARM", "WARM", q, dict(session=si, video_id=v, pos=j), lambda q=q: cb(q)))
    elif group.startswith("e_") or group.startswith("ef_"):
        wq = next(q for q in qids if q not in p["e"] and float(r1[(q, "RECENT")]["question_time"]) > 120)
        def eb(q):
            b, nf = F2.body(f2rows[q], model)
            return b, dict(n_chunks=f2rows[q]["n_chunks"], n_frames=nf)
        out.append(("e", "discard", wq, {}, lambda q=wq: eb(q)))
        out += [("e_F2", "cold", q, {}, lambda q=q: eb(q)) for q in p["e"]]
        if group.startswith("ef_"):
            for cons, cell in (("RICH", "K1"), ("RECENT", "K3")):
                def vb(q, cons=cons):
                    b, _, nf = C.R1_BODY(r1[(q, cons)], cell, model, dict(temperature=0.0), max_tokens=8)
                    return b, dict(n_frames=nf)
                out += [(f"f_{cell}_video", "cold", q, {}, lambda q=q, vb=vb: vb(q)) for q in p["f"]]
    elif group.startswith("fimg_"):
        wq = next(q for q in qids if q not in p["f"])
        out.append(("fimg", "discard", wq, {}, lambda q=wq: k_images_body(r1[(q, "RECENT")], model)))
        for cons, cell in (("RICH", "K1"), ("RECENT", "K3")):
            out += [(f"f_{cell}_images", "cold", q, {}, lambda q=q, cons=cons: k_images_body(r1[(q, cons)], model))
                    for q in p["f"]]
    return out


def run_group(g, model, flags, env, p, r1, rh4, f2rows, d11man):
    tag = f"group_{g}"
    if X.is_done(tag):
        X.log(f"{g}: done already")
        return
    if os.path.exists(REQ):  # resume: a partially run group is re-run from its start (its rows are marked superseded)
        rows = [json.loads(l) for l in open(REQ)]
        if any(r["group"] == g for r in rows):
            with open(REQ, "w") as f:
                for r in rows:
                    if r["group"] == g:
                        r["superseded"] = True
                    f.write(json.dumps(r) + "\n")
    F.require_idle()
    old = os.environ.get("PYTHONPATH", "")
    if env.get("d11"):
        os.environ["PYTHONPATH"] = str(HERE / "d11_site") + os.pathsep + old
        os.environ["D11_NPZ_LOADER"] = "1"
    srv = X.Server(model, flags)
    F.SRV = srv
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(group=g, model=model, started=F.now(), **info))
        X.meta_save(m)
        snapshot(f"server_up_{g}")
        its = items(g, model, p, r1, rh4, f2rows, d11man)
        for k, (cell, label, q, extra, fn) in enumerate(its):
            b, bmeta = fn()
            rec = timed(b, dict(group=g, model=model, cell=cell, label=label, discarded=label == "discard",
                                question_id=q, prefix_caching="--enable-prefix-caching" in flags,
                                fmt=("video" if g.startswith(("b_", "e_")) or cell.endswith("_video") or cell == "e_F2"
                                     else "images"), **extra, **bmeta))
            if rec["error"]:
                X.log(f"{g} {cell} {q[:10]}: ERROR {rec['error'][:200]}")
            if label == "cold" and rec["cached_tokens"]:
                raise SystemExit(f"{g}: cold request served {rec['cached_tokens']} cached tokens — STOP")
            if k % 20 == 0:
                X.log(f"{g}: {k + 1}/{len(its)} {cell} ttft {rec['ttft_s']} total {rec['total_s']} tok {rec['prompt_tokens']}")
        se = F.server_errors(srv)
        if se:
            raise SystemExit(f"{g}: server log error — STOP: {se[0]}")
    finally:
        srv.stop()
        os.environ["PYTHONPATH"] = old
        os.environ.pop("D11_NPZ_LOADER", None)
    rows = [json.loads(l) for l in open(REQ)]
    rows = [r for r in rows if r["group"] == g and not r.get("superseded")]
    err = sum(bool(r["error"]) for r in rows)
    if err > 0.01 * len(rows):
        raise SystemExit(f"{g}: {err}/{len(rows)} errors > 1 % — STOP")
    X.mark_done(tag, rows=len(rows), errors=err)


def main():
    global F1ROWS
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", default=",".join(g for g, *_ in GROUPS))
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    p, r1, rh4 = plan()
    (OUT / "f3_plan.json").write_text(json.dumps(p, indent=0))
    if a.plan_only:
        print(json.dumps({k: (v if "bins" in k else len(v) if isinstance(v, list) else v) for k, v in p.items()}, indent=0))
        return
    F1ROWS = {(r["question_id"], r["n"]): r for r in map(json.loads, open(REPO / F1.MAN))}
    F1.GREY = F1.grey_png()
    f2rows = F2.summaries()
    d11man = {r["question_id"]: r for r in map(json.loads, open(REPO / D.MAN))}
    start = snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    m = X.meta_load()
    import torch
    import vllm
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu=F.GPU_LABEL,
                      gpu_uuid=F.GPU_UUID, gen=GEN, protocol="one request at a time, localhost, streaming, bodies "
                      "serialised before the clock, first request after each load discarded")
    X.meta_save(m)
    th = threading.Thread(target=monitor, daemon=True)
    th.start()
    try:
        for g, model, flags, env in GROUPS:
            if g in a.groups.split(","):
                run_group(g, model, flags, env, p, r1, rh4, f2rows, d11man)
                if VOID.is_set():
                    raise SystemExit("run VOID — STOP")
    finally:
        STOP.set()
        snapshot("end")
        m = X.meta_load()
        m["void"] = VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_f3_latency.py", model="4BI,32BI", device="h100nvl_gpu1",
                                                 n=sum(1 for _ in open(REQ)), args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
