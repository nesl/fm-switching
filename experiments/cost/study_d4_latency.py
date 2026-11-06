#!/usr/bin/env python3
"""StudyD4-latency — H100 single-request latency for the dashcam input (h100nvl GPU 2). Pre-registered (StudyD4).

Requests: StudyD3 SMALL frames (development clips). 50 (clip, offset) pairs = random.Random(0).sample of the sorted N = 9
request ids; the SAME pairs are used for N = 3 and N = 1 (their frames are subsets of N = 9's). Body = D3's request
(header, N PNG images oldest first, D2 query), greedy, max_tokens 8, stream with usage, pre-serialised before the clock.
Models (one server load each): 4BI @ebb281ec, then 32BI @0cfaf481; D-series vLLM 0.31.0, prefix caching off,
--mm-processor-cache-gb 0, --enable-prompt-tokens-details; one request at a time, localhost; the first request after
each load is discarded (logged). Order per load: N = 1, 3, 9.
Measured: TTFT (immediately before send -> first streamed token), total, prompt / completion tokens, request bytes as
sent (lossless PNG) and the bytes the same request would have with each frame re-encoded as JPEG quality 90 (PIL,
4:2:0) — byte counts only, for later uplink arithmetic. GPU-2 SM clock / utilisation at 20 ms (pynvml), all-GPU
`nvidia-smi dmon -o DT`, other users' GPU processes and per-user CPU load at start / every 30 s / end.
Isolation (study_d10_latency.isolation): waits until no other work of ours runs; any overlap during the run -> VOID.
"""
import argparse
import base64
import io
import json
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "dashcam"))
import study_d10_latency as L  # noqa: E402
import d3_infer_vllm as D3  # noqa: E402

C, X = L.C, L.X
X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
OUT = Path("results/cost/study_d4")
OTHERS = "study_d4_others_h100nvl.jsonl"  # StudyD7 / D7b set their own name
REQ = OUT / "study_d4_requests_h100nvl.jsonl"
META = OUT / "study_d4_run_meta_h100nvl.json"
L.ISO = OUT / "study_d4_isolation_h100nvl.jsonl"
L.DMON = Path("logs/study_d4_dmon.log")
C.H5SNAP = OUT / "study_d4_snapshots_h100nvl.jsonl"
X.META_PATH = META
X.CURRENT = Path("logs/study_d4_current.json")
FLAGS = ["--limit-mm-per-prompt", json.dumps({"image": 9, "video": 0}), "--mm-processor-cache-gb", "0",
         "--enable-prompt-tokens-details", "--host", "127.0.0.1"]
GEN = dict(temperature=0.0, max_tokens=8, seed=0)
NPAIRS = 50


def others(tag):
    """Other users' GPU processes and per-user CPU (sum of %CPU over their processes)."""
    gp = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                        capture_output=True, text=True).stdout.strip().splitlines()
    g = []
    for l in gp:
        u, pid, mem = [x.strip() for x in l.split(",")]
        g.append(dict(gpu=u, pid=int(pid), mem=mem,
                      user=subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip()))
    ps = subprocess.run(["ps", "-eo", "user=,pcpu="], capture_output=True, text=True).stdout.splitlines()
    cpu = {}
    for l in ps:
        f = l.split()
        if len(f) == 2:
            cpu[f[0]] = cpu.get(f[0], 0.0) + float(f[1])
    rec = dict(tag=tag, at=datetime.now().isoformat(), gpu_processes=g,
               cpu_pct_by_user={k: round(v, 1) for k, v in sorted(cpu.items(), key=lambda x: -x[1])[:8]},
               loadavg=Path("/proc/loadavg").read_text().strip())
    with open(OUT / OTHERS, "a") as f:
        f.write(json.dumps(rec) + "\n")


def jpeg_bytes(body):
    """Bytes of the same JSON body with every PNG data URL re-encoded as JPEG q90."""
    from PIL import Image
    b = json.loads(body)
    n_img, img_png, img_jpg = 0, 0, 0
    for c in b["messages"][0]["content"]:
        if c["type"] == "image_url":
            png = base64.b64decode(c["image_url"]["url"].split(",", 1)[1])
            buf = io.BytesIO()
            Image.open(io.BytesIO(png)).convert("RGB").save(buf, format="JPEG", quality=90)
            c["image_url"]["url"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            n_img += 1
            img_png += len(png)
            img_jpg += buf.tell()
    return len(json.dumps(b).encode()), img_png, img_jpg, n_img


def requests_for(model):
    man = [json.loads(l) for l in open(D3.MAN)]
    n9 = sorted(r["request_id"] for r in man if r["n"] == 9)
    pick = random.Random(0).sample(n9, NPAIRS)
    byid = {r["request_id"]: r for r in man}
    out = []
    for n in (1, 3, 9):
        for rid in pick:
            q = byid[rid.replace("_N9", f"_N{n}")]
            b, _, _ = D3.body(q, model)
            b = dict(b, stream=True, stream_options={"include_usage": True}, **GEN)
            for k in ("logprobs", "top_logprobs"):
                b.pop(k, None)
            out.append((n, q["request_id"], json.dumps(b).encode()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-clear-h", type=float, default=8.0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t_end, clear = time.time() + 3600 * a.wait_clear_h, 0
    while clear < 2:
        clear = 0 if L.isolation("pre-start wait")["overlap"] else clear + 1
        if clear < 2:
            if time.time() > t_end:
                raise SystemExit(3)
            time.sleep(60)
    L.isolation("run start")
    others("run start")
    dm = subprocess.Popen(["nvidia-smi", "dmon", "-s", "u", "-d", "1", "-o", "DT"], stdout=open(L.DMON, "a"),
                          stderr=subprocess.STDOUT)
    wt = L.IsoWatch()
    wt.start()
    try:
        for model in ("4BI", "32BI"):
            if D3.gpu_pids():
                raise SystemExit(f"GPU 2 not idle before {model} server start — STOP")
            reqs = requests_for(model)
            srv = X.Server(model, FLAGS)
            sampler = None
            try:
                info = srv.start()
                m = X.meta_load()
                m.setdefault("servers", []).append(dict(model=model, started=datetime.now().isoformat(), **info))
                X.meta_save(m)
                sampler = C.Sampler()
                C.snapshot(f"before {model}")
                others(f"before {model}")
                with httpx.Client(timeout=None) as client:
                    c0 = C.cache_counters(client)
                    w = L.one(client, reqs[0][2], sampler, False)
                    with open(REQ, "a") as f:
                        f.write(json.dumps(dict(w, model=model, n=reqs[0][0], request_id=reqs[0][1], warmup=True,
                                                at=datetime.now().isoformat())) + "\n")
                    for n, rid, body in reqs:
                        X.CURRENT.write_text(json.dumps(dict(model=model, n=n, rid=rid)))
                        r = L.one(client, body, sampler, False)
                        jb, ip, ij, ni = jpeg_bytes(body)
                        r.update(model=model, n=n, request_id=rid, warmup=False, body_bytes_png=len(body),
                                 body_bytes_jpeg90=jb, image_bytes_png=ip, image_bytes_jpeg90=ij, n_images=ni,
                                 text_head=r.pop("text")[:40], gpu_uuid=C.GPU_UUID, at=datetime.now().isoformat())
                        with open(REQ, "a") as f:
                            f.write(json.dumps(r) + "\n")
                        if r["error"]:
                            X.log(f"D4 {model} N{n} {rid}: error {r['error'][:80]}")
                    c1 = C.cache_counters(client)
                grew = {k: c1.get(k, 0) - c0.get(k, 0) for k in c1 if c1.get(k, 0) != c0.get(k, 0)}
                m = X.meta_load()
                m.setdefault("cache_checks", []).append(dict(model=model, before=c0, after=c1, grew=grew))
                X.meta_save(m)
                C.snapshot(f"after {model}")
                others(f"after {model}")
                se = [l for l in srv.logpath.read_text(errors="replace").splitlines()
                      if any(k in l for k in D3.SRV_ERR)]
                if se:
                    raise SystemExit(f"D4 {model}: server log error before requests completed — STOP: {se[0][:200]}")
                if grew:
                    raise SystemExit(f"D4 {model}: cache counters grew {grew} — STOP")
            finally:
                if sampler:
                    sampler.close()
                srv.stop()
    finally:
        wt.stop_ev.set()
        dm.terminate()
    L.isolation("run end")
    others("run end")
    seen = [json.loads(l) for l in open(L.ISO)]
    run = [s for s in seen if s["tag"] != "pre-start wait"]
    m = X.meta_load()
    m["isolation"] = dict(void=any(s["overlap"] for s in run), n_checks=len(run), n_prestart_waits=len(seen) - len(run))
    from _provenance import stamp
    m.setdefault("_provenance", []).append(stamp(script="study_d4_latency.py", model="4BI,32BI",
                                                 device=f"{X.DEV}_gpu2", n=2 * 3 * NPAIRS, args=a))
    X.meta_save(m)
    X.log(f"D4 done; VOID={m['isolation']['void']}")


if __name__ == "__main__":
    main()
