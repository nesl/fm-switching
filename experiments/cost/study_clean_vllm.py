#!/usr/bin/env python3
"""StudyClean — comparisons that were never clean (vLLM venv; h100nvl GPU 1). Pre-registered in research/EXPERIMENTS.md.

GPU: the chain exports CUDA_VISIBLE_DEVICES=<GPU 1 UUID> and CLEAN_GPU_UUID=<same>; study_x_vllm's GPU-3 process
check is pointed at that UUID (the watchdog checks the same GPU). References K1, K3 and RH4 ran on GPU 3.

Stages (each invocation starts one server, runs its stages, stops it):
  estimate            CPU: runtime estimate from committed timings (STOP if > 10 h)
  SAN                 32B-I, first 30 R1-order questions with K3's request/mode (conc 8); gate >= 29/30 letters = K3
  H1 / H2             4B-I on K3's / K1's exact 845 requests (study_r1_vllm.body; same mode, conc 8)
  H3                  32B-I, RH4 D2 construction (2 s stride, 352x256, separate images, D2 header verbatim) restricted
                      to frames with t >= qt - 120 (RH4 server flags; conc 8)
  h5build             CPU: rebuild the Orin's 560x560 PNGs (system ffmpeg, device_latency_sember's command) and verify
                      every frame's sha256 against results/device/identical_input_manifest.json (STOP on mismatch)
  H5                  --model 32BI|4BI --pass 1|2: N = 37, 18, 9, 1 x 120 questions, serial; bodies pre-serialized;
                      prefix caching off, processor cache off, prompt-token details on (cached_tokens must be 0)
STOP: any cell > 1 % errors; a cache check fails; sanity < 29/30; a frame hash differs.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "sember"))
sys.path.insert(0, str(HERE.parent / "lib"))
sys.path.insert(0, str(HERE.parent.parent))
import study_x_vllm as X  # noqa: E402
import study_r1_vllm as R  # noqa: E402
R1_BODY = R.body            # R1's own request builder (study_rh3_warmable replaces R.body on import)
import study_rh3_warmable as W3  # noqa: E402  (mutates R.* on import; ours are set below)
import study_rh4_inputs as B4  # noqa: E402
from rawio import read_jsonl  # noqa: E402
import experiments.device.dev_inputs as dev  # noqa: E402

OUT = Path("results/cost/study_clean")
REQ = OUT / f"study_clean_requests_{X.DEV}.jsonl"
H5REQ = OUT / f"study_clean_h5_requests_{X.DEV}.jsonl"
H5SNAP = OUT / f"study_clean_h5_snapshots_{X.DEV}.jsonl"
META = OUT / f"study_clean_run_meta_{X.DEV}.json"
GPU_UUID = os.environ.get("CLEAN_GPU_UUID", "GPU-235c6d2d-40df-9060-e2f8-6524c4928d2d")
GPU_LABEL = "h100nvl GPU 1"
H5_FRAMES = Path.home() / ".cache/fm-switching/clean_h5_frames"
H5_MANIFEST = Path("results/device/identical_input_manifest.json")
VIDEOS = Path.home() / ".cache/fm-switching/sember_videos"
H5_NS = (37, 18, 9, 1)
H5_GEN = dict(temperature=0.0, max_tokens=512, seed=0)        # the Orin's (dev_fast_latency MODELS 4bi)
H5_WARMUP = 2
GREEDY = dict(temperature=0.0, max_tokens=512)
SAN_N, SAN_MIN = 30, 29
ERR_MAX = 0.01
BUDGET_H = 10.0

X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
X.META_PATH = META
X.CURRENT = Path("logs/study_clean_current.json")
R.OUT, R.REQ, R.META = OUT, REQ, META
R.CELLS = {"SAN": ("32BI", "RECENT", GREEDY), "H1": ("4BI", "RECENT", GREEDY), "H2": ("4BI", "RICH", GREEDY),
           "H3": ("32BI", "H3", GREEDY)}


def r1_manifest():
    """study_r1_vllm.manifest, reading the committed .jsonl.gz (rawio)."""
    rows = {(r["question_id"], r["construction"]): r for r in read_jsonl(R.MANIFEST)}
    order = sorted({(r["video_id"], r["question_id"]) for r in rows.values()})
    return rows, [q for _, q in order]


R.manifest = r1_manifest


def gpu_pids():
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(GPU_UUID)]


X.gpu3_pids = gpu_pids      # Server.stop / session_check now watch GPU 1


# ------------------------------------------------------------------------------------------------ H3 inputs
def mcq():
    return {r["question_id"]: r for r in map(json.loads, open(B4.B3.MCQ))}


def h3_select(video_id, qt):
    return [s for s in B4.select("D2", video_id, qt) if s[0] >= qt - 120 - 1e-6]


def h3_rows():
    M = mcq()
    rows = {}
    for r in read_jsonl(B4.MANIFEST):
        if r["cell"] != "D2":
            continue
        qt = float(r["question_time"])
        ts = [t for t, _, _ in h3_select(r["video_id"], qt)]
        a, b = sorted((float(M[r["question_id"]]["answer_start_time"]), float(M[r["question_id"]]["answer_end_time"])))
        rows[(r["question_id"], "H3")] = dict(r, cell="H3", construction="H3", n_images=len(ts), n_frames=len(ts),
                                             frame_t=ts, evidence_covered=any(a <= t <= b for t in ts),
                                             n_input_instruct=None, over_context=False)
    return rows


def body(row, cell, model, params, max_tokens=None, stream=True, token_ids=False):
    if row["construction"] != "H3":
        return R1_BODY(row, cell, model, params, max_tokens, stream, token_ids)
    p = dict(params)
    if max_tokens is not None:
        p["max_tokens"] = max_tokens
    c = [{"type": "text", "text": B4.HEADERS["D2"]}]
    c += [{"type": "image_url", "image_url": {"url": W3.img_url(pth, hw)}}
          for _, pth, hw in h3_select(row["video_id"], float(row["question_time"]))]
    c.append({"type": "text", "text": row["text"]})
    b = dict(model=model, stream=stream, seed=R.SEED, **p, messages=[{"role": "user", "content": c}])
    if stream:
        b["stream_options"] = {"include_usage": True}
    return b, None, row["n_images"]


R.body = body


def cell_check(cell, mode="batched"):
    rs = [r for r in read_jsonl(REQ) if r["cell"] == cell and r["mode"] == mode]
    err = sum(bool(r["error"]) for r in rs)
    X.log(f"{cell}: {len(rs)} rows, {err} errors, acc {sum(r['correct'] for r in rs) / max(1, len(rs)):.4f}")
    if err > ERR_MAX * len(rs):
        raise SystemExit(f"{cell}: {err}/{len(rs)} errors > 1 % — STOP")
    return rs


def sanity_gate():
    K3 = {r["question_id"]: r for r in read_jsonl(Path("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz"))
          if r["cell"] == "K3" and r["mode"] == "batched"}
    rs = cell_check("SAN")
    same = [r["pred"] == K3[r["question_id"]]["pred"] for r in rs]
    res = dict(n=len(rs), letters_match=int(sum(same)), required=SAN_MIN, passed=sum(same) >= SAN_MIN and len(rs) == SAN_N,
               mismatches=[dict(question_id=r["question_id"], pred=r["pred"], k3_pred=K3[r["question_id"]]["pred"])
                           for r, s in zip(rs, same) if not s],
               prompt_tokens_equal=int(sum(r["prompt_tokens"] == K3[r["question_id"]]["prompt_tokens"] for r in rs)))
    m = X.meta_load()
    m["sanity"] = res
    X.meta_save(m)
    X.log(f"SANITY: {res}")
    if not res["passed"]:
        raise SystemExit(f"SANITY {res['letters_match']}/{len(rs)} < {SAN_MIN} — STOP")


# ------------------------------------------------------------------------------------------------ H5 inputs
def h5_manifest():
    return json.loads(H5_MANIFEST.read_text())


def h5build():
    """Rebuild every manifest frame with device_latency_sember's ffmpeg command; verify sha256 (no substitution)."""
    man = h5_manifest()
    M = mcq()
    by_q = {}
    for e in man["entries"]:
        by_q.setdefault(e["question_id"], []).append(e)
    bad, n_ok = [], 0
    t0 = time.time()
    for i, (q, es) in enumerate(by_q.items(), 1):
        rec = M[q]
        qt = float(rec["question_time"])
        want = {f["t"]: f for e in es for f in e["frames"]}
        outd = H5_FRAMES / q
        outd.mkdir(parents=True, exist_ok=True)
        if not all((outd / f"{t}.png").exists() for t in want):
            lo = max(0.0, qt - dev.WINDOW_S)
            dur = max(1.0, qt - lo)
            tmp = outd / "tmp"
            tmp.mkdir(exist_ok=True)
            subprocess.run(["ffmpeg", "-nostdin", "-ss", str(lo), "-t", str(dur + 0.5), "-i",
                            str(VIDEOS / f"{rec['video_id']}.mp4"), "-vf", "fps=1,scale=560:560:flags=lanczos",
                            "-start_number", str(int(round(lo))), "-frames:v", str(int(dur) + 2),
                            str(tmp / "f_%d.png"), "-y"], capture_output=True)
            for t in want:
                src = tmp / f"f_{t}.png"
                if src.exists():
                    src.replace(outd / f"{t}.png")
            for p in tmp.glob("*.png"):
                p.unlink()
            tmp.rmdir()
        for t, f in want.items():
            p = outd / f"{t}.png"
            h = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
            if h != f["sha256"]:
                bad.append(dict(question_id=q, t=t, got=h, want=f["sha256"]))
            else:
                n_ok += 1
        for e in es:
            if hashlib.sha256(dev.question_text(rec).encode()).hexdigest() != e["question_text_sha256"]:
                bad.append(dict(question_id=q, N=e["N"], question_text="sha256 differs"))
        if i % 20 == 0:
            X.log(f"h5build {i}/{len(by_q)} questions, {n_ok} frames ok, {len(bad)} bad, {time.time() - t0:.0f}s")
    res = dict(at=datetime.now().isoformat(), questions=len(by_q), unique_frames_ok=n_ok, mismatches=bad[:50],
               n_mismatch=len(bad), ffmpeg=subprocess.run(["ffmpeg", "-version"], capture_output=True,
                                                           text=True).stdout.splitlines()[0],
               passed=not bad)
    m = X.meta_load()
    m["h5_input_identity"] = res
    X.meta_save(m)
    X.log(f"H5 INPUT IDENTITY: {n_ok} frames match, {len(bad)} mismatches")
    if bad:
        raise SystemExit("H5 frame sha256 mismatch — STOP: ask the user to transfer the Orin's files (no substitution)")


def h5_bodies(model):
    """{N: [(question_id, body_bytes, n_frames)]} in manifest order; every frame re-hashed at build time."""
    man = h5_manifest()
    M = mcq()
    out = {n: [] for n in H5_NS}
    for e in man["entries"]:
        items = []
        for f in e["frames"]:
            b = (H5_FRAMES / e["question_id"] / f"{f['t']}.png").read_bytes()
            assert hashlib.sha256(b).hexdigest() == f["sha256"], (e["question_id"], f["t"])
            items.append((f["t"], base64.b64encode(b).decode()))
        content = dev.build_chat_content(M[e["question_id"]], items)
        assert [c["text"] for c in content if c["type"] == "text"][:-1] == [f["marker"] for f in e["frames"]]
        payload = {"model": model, "messages": [{"role": "user", "content": content}], "stream": True,
                   "stream_options": {"include_usage": True}, **H5_GEN}
        out[e["N"]].append((e["question_id"], json.dumps(payload).encode(), len(items)))
    return out


# ------------------------------------------------------------------------------------------------ H5 measurement
class Sampler:
    """GPU 1 SM clock / util / power at 20 ms, plus all-GPU util for neighbour context."""

    def __init__(self):
        import pynvml
        self.nv = pynvml
        pynvml.nvmlInit()
        self.h = pynvml.nvmlDeviceGetHandleByUUID(GPU_UUID)
        self.all = [pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(pynvml.nvmlDeviceGetCount())]
        self.buf, self.stop_ev = [], threading.Event()
        self.th = threading.Thread(target=self.loop, daemon=True)
        self.th.start()

    def loop(self):
        nv = self.nv
        while not self.stop_ev.is_set():
            try:
                self.buf.append((time.time(), nv.nvmlDeviceGetClockInfo(self.h, nv.NVML_CLOCK_SM),
                                 nv.nvmlDeviceGetUtilizationRates(self.h).gpu))
            except nv.NVMLError:
                pass
            if len(self.buf) > 200000:
                del self.buf[:100000]
            time.sleep(0.02)

    def window(self, a, b):
        s = [x for x in self.buf if a <= x[0] <= b]
        if not s:
            return dict(n=0)
        clk = [x[1] for x in s]
        return dict(n=len(s), sm_mhz_min=min(clk), sm_mhz_median=statistics.median(clk), sm_mhz_max=max(clk),
                    util_max=max(x[2] for x in s))

    def now_clock(self):
        return self.nv.nvmlDeviceGetClockInfo(self.h, self.nv.NVML_CLOCK_SM)

    def close(self):
        self.stop_ev.set()
        self.th.join(timeout=2)


def snapshot(tag):
    """Processes + utilization on all GPUs, host CPU load, PCIe throughput (nvidia-smi dmon -s t, 3 x 1 s)."""
    q = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,utilization.gpu,memory.used,power.draw,clocks.sm,"
                        "pcie.link.gen.current,pcie.link.width.current", "--format=csv,noheader"],
                       capture_output=True, text=True).stdout.strip().splitlines()
    apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip().splitlines()
    procs = []
    for a in apps:
        u, pid, mem = [x.strip() for x in a.split(",")]
        user = subprocess.run(["ps", "-o", "user=", "-p", pid], capture_output=True, text=True).stdout.strip()
        procs.append(dict(gpu_uuid=u, pid=int(pid), mem=mem, user=user))
    dmon = subprocess.run(["nvidia-smi", "dmon", "-s", "ut", "-c", "3"], capture_output=True, text=True,
                          timeout=30).stdout.strip().splitlines()
    rec = dict(tag=tag, at=datetime.now().isoformat(), gpus=q, procs=procs, loadavg=Path("/proc/loadavg").read_text().strip(),
               ncpu=os.cpu_count(), dmon=dmon)
    with open(H5SNAP, "a") as f:
        f.write(json.dumps(rec) + "\n")
    X.log(f"snapshot {tag}: load {rec['loadavg']}; procs {[(p['gpu_uuid'][:12], p['user']) for p in procs]}")
    return rec


def h5_one(client, body_bytes, sampler):
    first, usage, chunks, err, finish = None, None, [], None, None
    clk0 = sampler.now_clock()
    w0 = time.time()
    t0 = time.perf_counter()               # immediately before send
    try:
        with client.stream("POST", f"{X.BASE}/v1/chat/completions", content=body_bytes,
                           headers={"Content-Type": "application/json"}) as r:
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
                        c = (ch.get("delta") or {}).get("content")
                        if c:
                            if first is None:
                                first = time.perf_counter()
                            chunks.append(c)
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t1 = time.perf_counter()
    w1 = time.time()
    text = "".join(chunks)
    m = re.search(r"\b([A-E])\b", text)                     # the Orin's parse (dev_fast_latency.run_one)
    u = usage or {}
    return dict(ttft_s=round(first - t0, 4) if first else None, total_s=round(t1 - t0, 4), wall_start=w0, wall_end=w1,
                prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                body_bytes=len(body_bytes), text=text, pred=m.group(1) if m else None, finish_reason=finish,
                error=err, sm_mhz_at_send=clk0, gpu1=sampler.window(w0, w1))


CACHE_METRICS = ("vllm:prefix_cache_hits_total", "vllm:mm_cache_hits_total", "vllm:external_prefix_cache_hits_total")


def cache_counters(client):
    """Sum of vLLM's cache-hit counters (prefix and multimodal processor cache); both caches are off, so 0 growth."""
    txt = client.get(f"{X.BASE}/metrics").text
    out = {}
    for line in txt.splitlines():
        for k in CACHE_METRICS:
            if line.startswith(k):
                out[k] = out.get(k, 0.0) + float(line.rsplit(" ", 1)[1])
    return out


def run_h5(model, pss):
    M = mcq()
    bodies = h5_bodies(model)
    sampler = Sampler()
    done = set()
    if H5REQ.exists():
        done = {(r["model"], r["pass"], r["N"], r["question_id"]) for r in read_jsonl(H5REQ) if not r["warmup"]}
    try:
        with httpx.Client(timeout=None) as client:
            for N in H5_NS:
                todo = [b for b in bodies[N] if (model, pss, N, b[0]) not in done]
                if not todo:
                    continue
                snapshot(f"before {model} pass{pss} N{N}")
                X.CURRENT.write_text(json.dumps(dict(cell="H5", model=model, pss=pss, N=N)))
                for k in range(H5_WARMUP):          # warm-up: last question of the cell, logged separately
                    q, bb, nf = bodies[N][-1]
                    r = h5_one(client, bb, sampler)
                    rec = dict(r, model=model, **{"pass": pss}, N=N, question_id=q, n_frames=nf, warmup=True,
                               warmup_k=k, gpu=GPU_LABEL, label="shared host, GPU 1, localhost, no network",
                               at=datetime.now().isoformat())
                    with open(H5REQ, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                X.log(f"H5 {model} pass{pss} N{N}: {len(todo)} requests")
                c0 = cache_counters(client)
                rows = []
                for q, bb, nf in todo:
                    r = h5_one(client, bb, sampler)
                    rec = dict(r, model=model, **{"pass": pss}, N=N, question_id=q, n_frames=nf, warmup=False,
                               correct_letter=M[q]["correct_letter"], correct=r["pred"] == M[q]["correct_letter"],
                               gpu=GPU_LABEL, label="shared host, GPU 1, localhost, no network",
                               at=datetime.now().isoformat())
                    with open(H5REQ, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    rows.append(rec)
                    if r["cached_tokens"]:            # None = not reported (prefix caching off); counters below
                        raise SystemExit(f"H5 CACHE CHECK FAILED {q} N{N}: cached_tokens={r['cached_tokens']} — STOP")
                c1 = cache_counters(client)
                grew = {k: c1.get(k, 0) - c0.get(k, 0) for k in c1 if c1.get(k, 0) != c0.get(k, 0)}
                m = X.meta_load()
                m.setdefault("h5_cache_checks", []).append(dict(model=model, pss=pss, N=N, before=c0, after=c1,
                                                                grew=grew, passed=not grew))
                X.meta_save(m)
                if grew:
                    raise SystemExit(f"H5 CACHE CHECK FAILED {model} pass{pss} N{N}: counters grew {grew} — STOP")
                err = sum(bool(r["error"]) for r in rows)
                tt = sorted(r["ttft_s"] for r in rows if r["ttft_s"])
                X.log(f"H5 {model} pass{pss} N{N}: done; errors {err}; ttft median {statistics.median(tt):.3f}s; "
                      f"prompt tokens median {statistics.median(r['prompt_tokens'] or 0 for r in rows)}; "
                      f"acc {sum(r['correct'] for r in rows)}/{len(rows)}")
                if err > ERR_MAX * len(rows):
                    raise SystemExit(f"H5 {model} N{N}: {err} errors > 1 % — STOP")
            snapshot(f"after {model} pass{pss}")
    finally:
        sampler.close()


# ------------------------------------------------------------------------------------------------ estimate
def estimate():
    r1 = json.loads(Path("results/sember/study_r1/study_r1_run_meta_h100nvl.json").read_text())
    k3_seq = statistics.mean(r1["timing5"]["K3"]["latency_s"])
    speed = 1.51                                      # R1's measured batched speed-up (RH3/RH4 estimate)
    est = dict(SAN=SAN_N * k3_seq / speed, H1=845 * k3_seq / speed, H2=34.3 * 60,
               H3=32.3 * 60,                          # RH4 D2's measured wall (H3 has fewer frames: upper bound)
               H4=401 * 1.0,                          # 4B-I HF greedy, ~1 s/question (StudyS2 prior for arm I)
               H5=2 * 2 * 120 * (37 + 18 + 9 + 1) / 37 * k3_seq,   # 2 models x 2 passes; 32B 12.4k-token rate as bound
               H5_gap=30 * 60, server_starts=10 * 4 * 60)
    est["total_h"] = sum(est.values()) / 3600
    m = X.meta_load()
    m["estimate"] = dict(est, basis="R1 K3 timing5 sequential latency / 1.51 batched speed-up; K1 34.3 min and RH4 D2 "
                                    "32.3 min measured walls; 32B rates used for 4B (upper bound)")
    X.meta_save(m)
    X.log(f"ESTIMATE {est['total_h']:.2f} h: {est}")
    if est["total_h"] > BUDGET_H:
        raise SystemExit(f"estimate {est['total_h']:.2f} h > {BUDGET_H} h — STOP")


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stages", required=True, help="estimate | h5build | SAN,H1,H2,H3 (one server) | H5")
    ap.add_argument("--model", choices=["32BI", "4BI"])
    ap.add_argument("--pass", dest="pss", type=int, choices=[1, 2])
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stages = args.stages.split(",")
    if stages == ["estimate"]:
        return estimate()
    if stages == ["h5build"]:
        return h5build()
    if stages == ["H5"]:
        flags = ["--limit-mm-per-prompt", json.dumps({"image": max(H5_NS), "video": 0}), "--mm-processor-cache-gb", "0",
                 "--enable-prompt-tokens-details", "--host", "127.0.0.1"]
        key = args.model
    else:
        keys = {R.CELLS[s][0] for s in stages}
        assert len(keys) == 1, keys
        key = keys.pop()
        flags = W3.IMAGE_FLAGS if stages == ["H3"] else R.MM_LIMIT
    srv = X.Server(key, flags)
    try:
        info = srv.start()
        m = X.meta_load()
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        m.setdefault("servers", []).append(dict(stages=args.stages, model=key, h5_pass=args.pss, gpu=GPU_LABEL,
                                                gpu_uuid=GPU_UUID, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        if stages == ["H5"]:
            run_h5(key, args.pss)
        else:
            rows, order = R.manifest()
            assert len(order) == 845
            if "H3" in stages:
                rows.update(h3_rows())
            for st in stages:
                if st == "SAN":
                    asyncio.run(R.run_cell("SAN", rows, order, "batched", limit=SAN_N))
                    sanity_gate()
                else:
                    asyncio.run(R.run_cell(st, rows, order, "batched"))
                    cell_check(st)
    finally:
        srv.stop()
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_clean_vllm.py", model=key, device=f"{X.DEV}_gpu1",
                                                 args=args))
    X.meta_save(m)


if __name__ == "__main__":
    main()
