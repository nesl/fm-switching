"""StudyX — vLLM serving at 32B on h100nvl. Runs in the SEPARATE vLLM venv (~/.venvs/fm-switching-vllm), never .venv.

Stack: vLLM 0.31.0+cu129 (torch 2.13.0+cu129), OpenAI-compatible server launched by this script as a child process
(same session as the chain, so the GPU-3 watchdog recognises it). tensor_parallel_size=1,
gpu_memory_utilization=0.90, max_model_len=32768, prefix caching DISABLED (every request is a cold prefill; no
cross-request cache hits — CLAUDE.md caching rule), chunked prefill at vLLM default. Attention backend: vLLM's own
choice, parsed from the server log and recorded.

Inputs: the prompt pack from experiments/cost/study_x_prep.py (exact HF-preprocessed images + HF prompt token count).

Stages (chain order):
  step0i   32B-Instruct: smoke (1 multimodal ERQA q; prompt_tokens vs HF), session/pgid check, drift check
           (StudyU's 40 questions, greedy 512, sequential) vs committed HF H100 arm C (SDPA and flash-attn).
  step0t   32B-Thinking: smoke (1 q, CFG-A), then Part C, then Part B (vLLM side).
  A        Part A for --model 32BT or 32BI.
Timing study except the step0i drift check (answer letters only).
"""
import argparse
import asyncio
import base64
import itertools
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

PACK = Path.home() / ".cache/fm-switching/study_x_prompts/pack.json"
HUB = Path.home() / ".cache/huggingface/hub"
REPO = {"32BI": ("Qwen/Qwen3-VL-32B-Instruct", "0cfaf48183f594c314753d30a4c4974bc75f3ccb"),
        "32BT": ("Qwen/Qwen3-VL-32B-Thinking", "7edd10ffd1196091948fb245ff63e406ccb2d4d1")}
PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
OUT = Path("results/cost/study_x")
DEV = "h100nvl"
REQ_PATH = OUT / f"study_x_requests_{DEV}.jsonl"
MET_PATH = OUT / f"study_x_metrics_{DEV}.jsonl"
STAMP_PATH = OUT / f"study_x_stamps_{DEV}.jsonl"
META_PATH = OUT / f"study_x_run_meta_{DEV}.json"
DRIFT_PATH = OUT / f"study_x_drift_{DEV}.json"
CURRENT = Path("logs/study_x_current.json")
SERVER_CFG = dict(max_model_len=32768, gpu_memory_utilization=0.90, tensor_parallel_size=1)

CFG_A = dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0)
GREEDY = dict(temperature=0.0)
SIGN_CAP = 24576
LONG_FORCE = 8192
ERQA_THINK_MAX = 16384

# StudyT H100 signs that ran to 24,576 tokens without closing </think> -- each under only ONE HF backend
# (IMG_6431, IMG_6443: SDPA only; IMG_0037: flash-attn only). Not "known non-terminators": all three terminate
# under vLLM (StudyX C1).
CAP_HITTERS = ["IMG_6431_frame_0015_0.jpg", "IMG_6443_frame_0023_0.jpg", "IMG_0037_frame_0014_0.jpg"]
FORCED_HITTER = "IMG_0037_frame_0014_0.jpg"


# --------------------------------------------------------------------------- bookkeeping

def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def meta_load():
    return json.loads(META_PATH.read_text()) if META_PATH.exists() else {"done": []}


def meta_save(m):
    META_PATH.write_text(json.dumps(m, indent=1, default=str))


def is_done(tag):
    return tag in meta_load()["done"]


def mark_done(tag, **info):
    m = meta_load()
    m["done"].append(tag)
    m.setdefault("experiments", {})[tag] = dict(finished=datetime.now().isoformat(), **info)
    meta_save(m)


def snapshot(key):
    repo, rev = REPO[key]
    return str(HUB / f"models--{repo.replace('/', '--')}" / "snapshots" / rev)


# --------------------------------------------------------------------------- prompts

_PACK = None
_B64 = {}


def pack():
    global _PACK
    if _PACK is None:
        _PACK = {e["id"]: e for e in json.loads(PACK.read_text())}
    return _PACK


def oa_content(entry):
    out = []
    for part in entry["content"]:
        if part["type"] == "image":
            if part["path"] not in _B64:
                _B64[part["path"]] = base64.b64encode(Path(part["path"]).read_bytes()).decode()
            out.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_B64[part['path']]}"}})
        else:
            out.append({"type": "text", "text": part["text"]})
    return out


def extract_letter(text):  # identical to study_r_erqa.extract_letter
    t = text.strip()
    if t and t[0] in 'ABCD' and (len(t) == 1 or t[1] in '.\n ):,'):
        return t[0], "direct"
    m = re.search(r'(?:answer is|answer:|the answer)\s*[:\s]*([A-D])\b', t, re.IGNORECASE)
    if m:
        return m.group(1).upper(), "extracted"
    m = re.search(r'\b([A-D])\b', t[-80:])
    if m:
        return m.group(1).upper(), "last_found"
    return None, "no_letter"


# --------------------------------------------------------------------------- server

class Server:
    def __init__(self, key, extra=None):
        self.key = key
        self.extra = list(extra or [])
        self.logpath = Path(f"logs/study_x_server_{key}_{datetime.now():%m%d_%H%M%S}.log")
        self.proc = None
        self.info = {}

    def start(self):
        vllm = str(Path(sys.executable).parent / "vllm")
        cmd = [vllm, "serve", snapshot(self.key), "--served-model-name", self.key, "--port", str(PORT),
               "--max-model-len", str(SERVER_CFG["max_model_len"]),
               "--gpu-memory-utilization", str(SERVER_CFG["gpu_memory_utilization"]),
               "--tensor-parallel-size", str(SERVER_CFG["tensor_parallel_size"]),
               "--no-enable-prefix-caching", "--limit-mm-per-prompt", json.dumps({"image": 16}),
               "--dtype", "bfloat16", "--seed", "0"] + self.extra
        log(f"starting vLLM server: {' '.join(cmd)}")
        t0 = time.time()
        # FlashInfer's top-k/top-p sampler JIT-compiles on first use (needs ninja + a CUDA>=12 nvcc; this host has
        # nvcc 11.1) -> use vLLM's PyTorch-native top-k/top-p sampler. Same sampling semantics; recorded in meta.
        env = dict(os.environ, VLLM_USE_FLASHINFER_SAMPLER="0")
        self.proc = subprocess.Popen(cmd, stdout=open(self.logpath, "w"), stderr=subprocess.STDOUT, env=env)
        while True:
            if self.proc.poll() is not None:
                raise SystemExit(f"!!! vLLM server exited rc={self.proc.returncode}; see {self.logpath}")
            try:
                if httpx.get(f"{BASE}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(3)
        txt = self.logpath.read_text(errors="replace")

        def grab(pat):
            m = re.search(pat, txt)
            return m.group(1) if m else None
        self.info = dict(
            key=self.key, repo=REPO[self.key][0], revision=REPO[self.key][1], server_cmd=cmd,
            startup_s=round(time.time() - t0, 1), log=str(self.logpath), **SERVER_CFG, prefix_caching=False,
            kv_cache_tokens=int(grab(r"KV cache size: ([\d,]+) tokens").replace(",", "")) if grab(
                r"KV cache size: ([\d,]+) tokens") else None,
            max_concurrency_at_max_len=float(grab(r"Maximum concurrency for [\d,]+ tokens per request: ([\d.]+)x")
                                              or "nan"),
            available_kv_gib=grab(r"Available KV cache memory: ([\d.]+) GiB"),
            model_weights_gib=grab(r"Model loading took ([\d.]+) Gi?B"),
            attention_backend_lines=sorted(set(re.findall(r"[^\n]*(?:[Aa]ttention backend|_ATTN|FLASHINFER|"
                                                          r"FlashAttention|backend for)[^\n]*", txt)))[:12],
            cuda_graphs=bool(re.search(r"[Cc]apturing CUDA graph|Graph capturing finished", txt)),
            sampler="vLLM PyTorch-native top-k/top-p (VLLM_USE_FLASHINFER_SAMPLER=0)",
            extra_server_args=self.extra,
            flash_attention_version=grab(r"Using FlashAttention version (\d+)"),
        )
        self.info["session_check"] = session_check()
        log(f"server up: {json.dumps({k: v for k, v in self.info.items() if k != 'server_cmd'})[:1500]}")
        return self.info

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        for _ in range(120):   # wait until GPU 3 holds no process of ours
            if not gpu3_pids():
                break
            time.sleep(1)
        log(f"server {self.key} stopped")


def gpu3_pids():
    uuid = "GPU-b3c6399e-00c9-2ba7-8bd4-88570c884250"
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout
    return [int(l.split(", ")[1]) for l in out.strip().splitlines() if l.startswith(uuid)]


def session_check():
    """Every GPU-3 process must share this process's session id (what the watchdog checks)."""
    my_sid, my_pgid = os.getsid(0), os.getpgid(0)
    rows = []
    for pid in gpu3_pids():
        try:
            rows.append(dict(pid=pid, sid=os.getsid(pid), pgid=os.getpgid(pid),
                             cmd=Path(f"/proc/{pid}/cmdline").read_text().replace("\0", " ")[:120]))
        except (ProcessLookupError, FileNotFoundError):
            pass
    ok = all(r["sid"] == my_sid for r in rows) and bool(rows)
    res = dict(my_sid=my_sid, my_pgid=my_pgid, gpu3=rows, all_same_session=ok,
               all_same_pgid=all(r["pgid"] == my_pgid for r in rows))
    if not ok:
        raise SystemExit(f"!!! SESSION CHECK FAILED — GPU-3 processes outside our session: {res}")
    return res


# --------------------------------------------------------------------------- client

class Run:
    """One experiment: request records + /metrics timeline."""
    def __init__(self, tag, model):
        self.tag, self.model = tag, model
        self.t0 = time.time()
        self.records, self.timeline = [], []
        self.client = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=256))
        self._stop = False
        self.guard_hit = False

    async def scrape(self):
        while not self._stop:
            try:
                txt = (await self.client.get(f"{BASE}/metrics")).text
                row = dict(t=round(time.time() - self.t0, 3))
                for line in txt.splitlines():
                    if line.startswith("#"):
                        continue
                    for k in ("vllm:kv_cache_usage_perc", "vllm:num_requests_running",
                              "vllm:num_requests_waiting", "vllm:num_preemptions_total",
                              "vllm:external_prefix_cache_hits_total", "vllm:external_prefix_cache_queries_total"):
                        if line.startswith(k + "{") or line.startswith(k + " "):
                            row[k.split(":")[1]] = float(line.rsplit(" ", 1)[1])
                self.timeline.append(row)
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)

    async def request(self, entry, params, role, seed, keep_text=False):
        # client-only keys (never sent): _abort_after = close the stream after N streamed tokens (vLLM aborts the
        # request on disconnect and frees its KV) — the token-budget policy
        abort_after = params.get("_abort_after")
        body = dict(model=self.model, messages=[{"role": "user", "content": oa_content(entry)}], stream=True,
                    stream_options={"include_usage": True}, seed=seed,
                    **{k: v for k, v in params.items() if not k.startswith("_")})
        rec = dict(tag=self.tag, model=self.model, id=entry["id"], role=role, seed=seed,
                   params={k: v for k, v in params.items()}, hf_n_input_tokens=entry["hf_n_input_tokens"])
        t_sub = time.time()
        rec["t_submit"] = round(t_sub - self.t0, 3)
        CURRENT.write_text(json.dumps(dict(tag=self.tag, last_submit=entry["id"], at=datetime.now().isoformat())))
        stamps, text, usage, finish, err = [], [], None, None, None
        try:
            async with self.client.stream("POST", f"{BASE}/v1/chat/completions", json=body) as r:
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
                else:
                    async for line in r.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        d = line[6:]
                        if d == "[DONE]":
                            break
                        j = json.loads(d)
                        now = time.time()
                        if j.get("usage"):
                            usage = j["usage"]
                        for ch in j.get("choices", []):
                            delta = ch.get("delta") or {}
                            c = delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning")
                            if c:
                                stamps.append(now)
                                text.append(c)
                            if ch.get("finish_reason"):
                                finish = ch["finish_reason"]
                        if abort_after and len(stamps) >= abort_after and finish is None:
                            finish = "client_abort_budget"
                            break
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        t_end = time.time()
        full = "".join(text)
        rec.update(t_first=round(stamps[0] - self.t0, 3) if stamps else None,
                   t_end=round(t_end - self.t0, 3), latency_s=round(t_end - t_sub, 3),
                   ttft_s=round(stamps[0] - t_sub, 3) if stamps else None,
                   completion_tokens=usage["completion_tokens"] if usage else None,
                   prompt_tokens=usage["prompt_tokens"] if usage else None,
                   finish_reason=finish, think_closed="</think>" in full, n_chunks=len(stamps), error=err)
        if keep_text:
            rec["text"] = full
        self.records.append(rec)
        with open(STAMP_PATH, "a") as f:
            f.write(json.dumps(dict(tag=self.tag, id=entry["id"], role=role, seed=seed, t_submit=rec["t_submit"],
                                    stamps=[round(s - self.t0, 3) for s in stamps])) + "\n")
        return rec

    async def close(self):
        self._stop = True
        await asyncio.sleep(0.6)
        await self.client.aclose()
        with open(REQ_PATH, "a") as f:
            for r in self.records:
                f.write(json.dumps(r) + "\n")
        with open(MET_PATH, "a") as f:
            f.write(json.dumps(dict(tag=self.tag, timeline=self.timeline)) + "\n")


async def wait_idle(model):
    async with httpx.AsyncClient() as c:
        for _ in range(600):
            txt = (await c.get(f"{BASE}/metrics")).text
            run = [l for l in txt.splitlines() if l.startswith("vllm:num_requests_running")]
            wai = [l for l in txt.splitlines() if l.startswith("vllm:num_requests_waiting{")]
            if run and float(run[0].rsplit(" ", 1)[1]) == 0 and (not wai or float(wai[0].rsplit(" ", 1)[1]) == 0):
                return
            await asyncio.sleep(1)


async def closed_loop(run, first, refill, until_done_ids=None, total=None, concurrency=None, refill_until_s=None):
    """Submit `first` (list of (entry, params, role, seed)) at once; whenever a request finishes, submit the next
    item of `refill` until (a) every id in until_done_ids has finished, or (b) `total` requests were submitted."""
    scraper = asyncio.create_task(run.scrape())
    pending, submitted = set(), 0
    watch = set(until_done_ids or [])

    def submit(item):
        nonlocal submitted
        e, p, role, s = item
        t = asyncio.create_task(run.request(e, p, role, s))
        t.meta = (e["id"], role)
        pending.add(t)
        submitted += 1
    for it in first:
        submit(it)
    refill = iter(refill or [])
    while pending:
        done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            pending.discard(t)
            rid, role = t.meta
            if role in ("long", "stuck", "hitter"):
                watch.discard(rid)
            keep = (until_done_ids is not None and watch) or (total is not None and submitted < total)
            if keep and refill_until_s is not None and time.time() - run.t0 > refill_until_s:
                run.guard_hit = True   # starvation guard: stop refilling (reported)
                keep = False
            if keep and (concurrency is None or len(pending) < concurrency):
                nxt = next(refill, None)
                if nxt is not None:
                    submit(nxt)
    run._stop = True
    await scraper


# --------------------------------------------------------------------------- stages

def studyu_selection():
    return json.loads(Path("results/erqa/study_u/study_u_selection.json").read_text())


def normal_signs():
    ok = None
    for f in ("results/signs/study_t/study_t_trials_h100nvl.jsonl", "results/signs/study_t/study_t_trials_h100nvl_fa2.jsonl"):
        s = {r["sign_id"] for r in map(json.loads, open(f))
             if r["arm"] == "T32" and r["budget"] == 8192 and r["think_closed"] and r["phase"] == "core"}
        ok = s if ok is None else ok & s
    return sorted(ok - set(CAP_HITTERS))


async def stage_step0i():
    P = pack()
    sel = studyu_selection()
    qids = [q["question_id"] for q in sel["questions"]]
    tag = "step0i_smoke"
    run = Run(tag, "32BI")
    e = P[f"erqa{qids[0]}"]
    r = await run.request(e, dict(GREEDY, max_tokens=512), "smoke", 0, keep_text=True)
    run._stop = True
    await run.close()
    if r["error"] or not r["completion_tokens"]:
        raise SystemExit(f"!!! STEP0 SMOKE (Instruct) FAILED: {r}")
    log(f"smoke instruct: prompt_tokens vLLM={r['prompt_tokens']} HF={e['hf_n_input_tokens']} out={r['text']!r}")
    mark_done(tag, prompt_tokens_vllm=r["prompt_tokens"], prompt_tokens_hf=e["hf_n_input_tokens"])
    # drift check: sequential (concurrency 1), greedy 512, answer letters vs committed HF H100 arm C
    tag = "step0i_drift"
    run = Run(tag, "32BI")
    recs = []
    for qid in qids:
        recs.append(await run.request(P[f"erqa{qid}"], dict(GREEDY, max_tokens=512), "drift", 0, keep_text=True))
    run._stop = True
    await run.close()
    hf = {}
    for lab, f in (("sdpa", "results/erqa/study_r/study_r_trials_h100nvl.jsonl"),
                   ("fa2", "results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl")):
        hf[lab] = {r["question_id"]: r["predicted_letter"] for r in map(json.loads, open(f)) if r["arm"] == "C"}
    rows = []
    for qid, r in zip(qids, recs):
        letter, status = extract_letter(r["text"])
        rows.append(dict(question_id=qid, vllm=letter, parse=status, hf_sdpa=hf["sdpa"][qid], hf_fa2=hf["fa2"][qid],
                         prompt_tokens_vllm=r["prompt_tokens"], prompt_tokens_hf=P[f"erqa{qid}"]["hf_n_input_tokens"],
                         completion_tokens=r["completion_tokens"]))
    n = len(rows)
    res = dict(n=n, decoding="greedy temperature=0 max_tokens=512, sequential (concurrency 1)",
               differ_vs_hf_sdpa=sum(r["vllm"] != r["hf_sdpa"] for r in rows),
               differ_vs_hf_fa2=sum(r["vllm"] != r["hf_fa2"] for r in rows),
               hf_sdpa_vs_hf_fa2=sum(r["hf_sdpa"] != r["hf_fa2"] for r in rows),
               prompt_token_mismatch=sum(r["prompt_tokens_vllm"] != r["prompt_tokens_hf"] for r in rows),
               rows=rows)
    for k in ("differ_vs_hf_sdpa", "differ_vs_hf_fa2", "hf_sdpa_vs_hf_fa2"):
        res[k + "_frac"] = round(res[k] / n, 4)
    res["FLAG_over_10pct"] = max(res["differ_vs_hf_sdpa_frac"], res["differ_vs_hf_fa2_frac"]) > 0.10
    DRIFT_PATH.write_text(json.dumps(res, indent=1))
    log(f"DRIFT: vs HF-SDPA {res['differ_vs_hf_sdpa']}/{n}, vs HF-FA2 {res['differ_vs_hf_fa2']}/{n}, "
        f"HF-SDPA vs HF-FA2 {res['hf_sdpa_vs_hf_fa2']}/{n}, prompt-token mismatches {res['prompt_token_mismatch']}"
        + ("  !!! >10% DRIFT — vLLM and HF numbers must not be pooled !!!" if res["FLAG_over_10pct"] else ""))
    mark_done(tag, **{k: v for k, v in res.items() if k != "rows"})


async def stage_step0t():
    P = pack()
    sel = studyu_selection()
    if not is_done("step0t_smoke"):
        run = Run("step0t_smoke", "32BT")
        e = P[f"erqa{sel['questions'][0]['question_id']}"]
        r = await run.request(e, dict(CFG_A, max_tokens=ERQA_THINK_MAX), "smoke", 42, keep_text=True)
        run._stop = True
        await run.close()
        if r["error"] or not r["completion_tokens"]:
            raise SystemExit(f"!!! STEP0 SMOKE (Thinking) FAILED: {r}")
        log(f"smoke thinking: prompt_tokens vLLM={r['prompt_tokens']} HF={e['hf_n_input_tokens']} "
            f"gen={r['completion_tokens']} closed={r['think_closed']} tail={r['text'][-120:]!r}")
        mark_done("step0t_smoke", prompt_tokens_vllm=r["prompt_tokens"], prompt_tokens_hf=e["hf_n_input_tokens"],
                  completion_tokens=r["completion_tokens"], think_closed=r["think_closed"])
    await part_c()
    await part_b_vllm()


def normal_stream(normals, start_cycle=0):
    """Endless stream of normal sign requests; repeats get a new seed (42 + 1000 * cycle)."""
    P = pack()
    for cyc in itertools.count(start_cycle):
        for s in normals:
            yield (P[f"sign:{s}"], dict(CFG_A, max_tokens=SIGN_CAP), "normal", 42 + 1000 * cyc)


async def part_c():
    P = pack()
    normals = normal_signs()
    log(f"Part C: {len(normals)} normal signs available")
    # C1 natural: each StudyT cap-hitter at seed 42 + 7 normal, closed-loop refill until the hitter finishes
    for h in CAP_HITTERS:
        tag = f"C1_natural_{h}"
        if is_done(tag):
            continue
        run = Run(tag, "32BT")
        stream = normal_stream(normals)
        first = [(P[f"sign:{h}"], dict(CFG_A, max_tokens=SIGN_CAP), "hitter", 42)] + [next(stream) for _ in range(7)]
        await closed_loop(run, first, stream, until_done_ids={f"sign:{h}"}, concurrency=8)
        await run.close()
        hr = next(r for r in run.records if r["role"] == "hitter")
        log(f"{tag}: hitter gen={hr['completion_tokens']} closed={hr['think_closed']} finish={hr['finish_reason']} "
            f"hold={hr['latency_s']}s normals done={sum(r['role'] == 'normal' for r in run.records)}")
        mark_done(tag, hitter=hr)
        await wait_idle("32BT")
    # C2 forced single stuck request (min_tokens = max_tokens = 24576, ignore_eos) + 7 normal, refill
    # C3 scaling: k forced stuck requests + 7 normal closed-loop, k = 1 (= C2), 2, 3, 4
    for k in (1, 2, 3, 4):
        tag = f"C3_forced_k{k}"
        if is_done(tag):
            continue
        run = Run(tag, "32BT")
        stream = normal_stream(normals)
        hitters = [FORCED_HITTER] + [h for h in CAP_HITTERS if h != FORCED_HITTER] + normals
        stuck = [(P[f"sign:{hitters[i]}"], dict(CFG_A, max_tokens=SIGN_CAP, min_tokens=SIGN_CAP, ignore_eos=True),
                  "stuck", 42 + 7 * i) for i in range(k)]
        ids = {e["id"] for e, *_ in stuck}
        await closed_loop(run, stuck + [next(stream) for _ in range(7)], stream, until_done_ids=ids,
                          concurrency=7 + k)
        await run.close()
        st = [r for r in run.records if r["role"] == "stuck"]
        tl = run.timeline
        log(f"{tag}: stuck gen={[r['completion_tokens'] for r in st]} hold={[r['latency_s'] for r in st]}s "
            f"normals done={sum(r['role'] == 'normal' for r in run.records)} "
            f"max waiting={max((x.get('num_requests_waiting', 0) for x in tl), default=None)} "
            f"preemptions={(tl[-1].get('num_preemptions_total', 0) - tl[0].get('num_preemptions_total', 0)) if tl else None} "
            f"max KV={max((x.get('kv_cache_usage_perc', 0) for x in tl), default=None)}")
        mark_done(tag, k=k)
        await wait_idle("32BT")


def part_b_batches():
    sel = studyu_selection()
    longest = [q["question_id"] for q in sel["questions"] if q["stratum"] == "long"][:5]
    short = [q["question_id"] for q in sel["questions"] if q["stratum"] == "short"]
    return [dict(b=b, long=longest[b], short=[short[(b * 7 + j) % len(short)] for j in range(7)]) for b in range(5)]


async def part_b_vllm():
    P = pack()
    short_all = [q["question_id"] for q in studyu_selection()["questions"] if q["stratum"] == "short"]
    for bt in part_b_batches():
        long_item = (P[f"erqa{bt['long']}"], dict(CFG_A, max_tokens=ERQA_THINK_MAX, min_tokens=LONG_FORCE),
                     "long", 42 + bt["long"])
        shorts = [(P[f"erqa{q}"], dict(CFG_A, max_tokens=ERQA_THINK_MAX), "short", 42 + q) for q in bt["short"]]
        tag = f"B_vllm_batch8_b{bt['b']}"
        if not is_done(tag):          # (primary) the same 8 requests at once, no further arrivals
            run = Run(tag, "32BT")
            await closed_loop(run, [long_item] + shorts, [], until_done_ids=None, total=8)
            await run.close()
            lr = next(r for r in run.records if r["role"] == "long")
            sl = sorted(r["latency_s"] for r in run.records if r["role"] == "short")
            log(f"{tag}: long {lr['completion_tokens']} tok {lr['latency_s']}s; short latencies {sl}")
            mark_done(tag, batch=bt)
            await wait_idle("32BT")
        tag = f"B_vllm_refill_b{bt['b']}"
        if not is_done(tag):          # (secondary) closed-loop 8: short requests keep refilling while the long runs
            run = Run(tag, "32BT")

            def refill():
                for cyc in itertools.count(1):
                    for q in short_all:
                        yield (P[f"erqa{q}"], dict(CFG_A, max_tokens=ERQA_THINK_MAX), "short", 42 + q + 1000 * cyc)
            await closed_loop(run, [long_item] + shorts, refill(), until_done_ids={long_item[0]["id"]},
                              concurrency=8)
            await run.close()
            lr = next(r for r in run.records if r["role"] == "long")
            log(f"{tag}: long {lr['latency_s']}s; short completed during it: "
                f"{sum(r['role'] == 'short' and r['t_end'] <= lr['t_end'] for r in run.records)}")
            mark_done(tag, batch=bt)
            await wait_idle("32BT")


async def part_a(model):
    P = pack()
    order = list(np.random.default_rng(0).permutation(400))
    dec = CFG_A if model == "32BT" else GREEDY
    nat_max = ERQA_THINK_MAX if model == "32BT" else 512
    workloads = {"natural": dict(dec, max_tokens=nat_max),
                 "fixed1024": dict(dec, max_tokens=1024, min_tokens=1024, ignore_eos=True)}
    # warm-up (excluded)
    run = Run(f"A_warmup_{model}", model)
    await run.request(P[f"erqa{order[0]}"], dict(dec, max_tokens=64), "warmup", 0)
    run._stop = True
    await run.close()
    for wl, params in workloads.items():
        for n in (1, 2, 4, 8, 16, 32):
            tag = f"A_{model}_{wl}_c{n}"
            if is_done(tag):
                continue
            total = max(4 * n, 16)
            items = [(P[f"erqa{int(q)}"], params, "req", 42 + int(q)) for q in order[:total]]
            run = Run(tag, model)
            await closed_loop(run, items[:n], items[n:], total=total, concurrency=n)
            await run.close()
            rs = [r for r in run.records if not r["error"]]
            span = max(r["t_end"] for r in rs) - min(r["t_submit"] for r in rs)
            agg = sum(r["completion_tokens"] for r in rs) / span
            lat = np.array([r["latency_s"] for r in rs])
            tl = run.timeline
            log(f"{tag}: n_req={len(rs)} errors={len(run.records) - len(rs)} agg={agg:.1f} tok/s "
                f"lat p50/p90/p99={np.percentile(lat, 50):.1f}/{np.percentile(lat, 90):.1f}/{np.percentile(lat, 99):.1f}s "
                f"maxKV={max((x.get('kv_cache_usage_perc', 0) for x in tl), default=None)} "
                f"preempt={(tl[-1].get('num_preemptions_total', 0) - tl[0].get('num_preemptions_total', 0)) if tl else None}")
            mark_done(tag, agg_tok_s=round(agg, 2), n_req=len(rs))
            await wait_idle(model)


POLICY_GUARD_S = 2700   # stop refilling normals after 45 min (guards against priority starvation; reported if hit)


async def part_c_policy(policy):
    """Part C policy comparison. Exactly C3's request sequence (same signs, seeds, concurrency 7 + k), one policy
    changed per run. Baseline = C3_forced_k{1,2} (FCFS, no budget, no offload)."""
    P = pack()
    normals = normal_signs()
    hitters = [FORCED_HITTER] + [h for h in CAP_HITTERS if h != FORCED_HITTER] + normals
    configs = {
        # priority policy: eviction victim = max(priority, arrival); waiting queue ordered by priority
        "prio": [("C4_prio_equal_k1", 1, dict(priority=0), dict(priority=0)),        # control: equal priority
                 ("C4_prio_stucklow_k1", 1, dict(priority=10), dict(priority=0)),    # stuck deprioritized
                 ("C4_prio_stucklow_k2", 2, dict(priority=10), dict(priority=0))],
        # token budget applied to EVERY request (a gateway policy), abort at 8,192 streamed tokens
        "abort": [("C5_abort8192_k1", 1, dict(_abort_after=8192), dict(_abort_after=8192)),
                  ("C5_abort8192_k2", 2, dict(_abort_after=8192), dict(_abort_after=8192))],
        "offload": [("C6_offload64_k2", 2, {}, {})],
    }[policy]
    for tag, k, sx, nx in configs:
        if is_done(tag):
            continue
        run = Run(tag, "32BT")
        stuck = [(P[f"sign:{hitters[i]}"], dict(CFG_A, max_tokens=SIGN_CAP, min_tokens=SIGN_CAP, ignore_eos=True,
                                                **sx), "stuck", 42 + 7 * i) for i in range(k)]
        ids = {e["id"] for e, *_ in stuck}

        def stream(nx=nx):
            for e, p, role, s in normal_stream(normals):
                yield e, dict(p, **nx), role, s
        st = stream()
        await closed_loop(run, stuck + [next(st) for _ in range(7)], st, until_done_ids=ids, concurrency=7 + k,
                          refill_until_s=POLICY_GUARD_S)
        await run.close()
        sr = [r for r in run.records if r["role"] == "stuck"]
        tl = run.timeline
        log(f"{tag}: stuck gen={[r['completion_tokens'] or r['n_chunks'] for r in sr]} "
            f"finish={[r['finish_reason'] for r in sr]} hold={[r['latency_s'] for r in sr]}s "
            f"normals done={sum(r['role'] == 'normal' for r in run.records)} guard_hit={run.guard_hit} "
            f"max waiting={max((x.get('num_requests_waiting', 0) for x in tl), default=None)} "
            f"preemptions={(tl[-1].get('num_preemptions_total', 0) - tl[0].get('num_preemptions_total', 0)) if tl else None}")
        mark_done(tag, k=k, policy=policy, stuck_params=sx, normal_params=nx, guard_hit=run.guard_hit)
        await wait_idle("32BT")


async def part_b_vllm_8k():
    """Part B at a MATCHED cap: every request max_tokens=8192; long request forced to exactly 8,192."""
    P = pack()
    short_all = [q["question_id"] for q in studyu_selection()["questions"] if q["stratum"] == "short"]
    for bt in part_b_batches():
        long_item = (P[f"erqa{bt['long']}"], dict(CFG_A, max_tokens=LONG_FORCE, min_tokens=LONG_FORCE),
                     "long", 42 + bt["long"])
        shorts = [(P[f"erqa{q}"], dict(CFG_A, max_tokens=LONG_FORCE), "short", 42 + q) for q in bt["short"]]
        tag = f"B8k_vllm_batch8_b{bt['b']}"
        if not is_done(tag):
            run = Run(tag, "32BT")
            await closed_loop(run, [long_item] + shorts, [], until_done_ids=None, total=8)
            await run.close()
            lr = next(r for r in run.records if r["role"] == "long")
            log(f"{tag}: long {lr['completion_tokens']} tok {lr['latency_s']}s; short latencies "
                f"{sorted(r['latency_s'] for r in run.records if r['role'] == 'short')}")
            mark_done(tag, batch=bt, cap=LONG_FORCE)
            await wait_idle("32BT")
        tag = f"B8k_vllm_refill_b{bt['b']}"
        if not is_done(tag):
            run = Run(tag, "32BT")

            def refill():
                for cyc in itertools.count(1):
                    for q in short_all:
                        yield (P[f"erqa{q}"], dict(CFG_A, max_tokens=LONG_FORCE), "short", 42 + q + 1000 * cyc)
            await closed_loop(run, [long_item] + shorts, refill(), until_done_ids={long_item[0]["id"]},
                              concurrency=8)
            await run.close()
            lr = next(r for r in run.records if r["role"] == "long")
            log(f"{tag}: long {lr['latency_s']}s; short completed during it: "
                f"{sum(r['role'] == 'short' and r['t_end'] <= lr['t_end'] for r in run.records)}")
            mark_done(tag, batch=bt, cap=LONG_FORCE)
            await wait_idle("32BT")


async def stage_c_abort_b8k():
    await part_c_policy("abort")
    await part_b_vllm_8k()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["step0i", "step0t", "A", "C_prio", "C_abort_B8k", "C_offload"],
                    required=True)
    ap.add_argument("--model", choices=list(REPO), default=None)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    key = {"step0i": "32BI", "step0t": "32BT", "C_prio": "32BT", "C_abort_B8k": "32BT",
           "C_offload": "32BT"}.get(args.stage, args.model)
    extra = {"C_prio": ["--scheduling-policy", "priority"],
             "C_offload": ["--kv-offloading-size", "64", "--kv-offloading-backend", "native"]}.get(args.stage, [])
    srv = Server(key, extra)
    try:
        info = srv.start()
        m = meta_load()
        m.setdefault("servers", []).append(dict(stage=args.stage, started=datetime.now().isoformat(), **info))
        import torch
        import vllm
        m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, cuda=torch.version.cuda)
        meta_save(m)
        coro = {"step0i": stage_step0i, "step0t": stage_step0t, "C_abort_B8k": stage_c_abort_b8k,
                "C_prio": lambda: part_c_policy("prio"), "C_offload": lambda: part_c_policy("offload")}.get(args.stage)
        asyncio.run(coro() if coro else part_a(key))
    finally:
        srv.stop()


if __name__ == "__main__":
    main()
