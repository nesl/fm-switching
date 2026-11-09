#!/usr/bin/env python3
"""StudyB2-h100 latency sample (StudyD10's method), run at the end of each dataset's matrix.

Per arm (4BI, 8BI, 32BI, 4BT, 8BT, 32BT; one vLLM load each, the B2 / StudyB1 server flags) and per sub-dataset and
input: the first 50 questions of that dataset's fixed seed-0 order, sent ONE AT A TIME with streaming.
Cold: prefix caching OFF and multimodal processor cache OFF (vLLM cache-hit counters checked before/after each load
-> growth = STOP); bodies rendered and serialised BEFORE the clock starts. TTFT = immediately before send -> first
streamed token (reasoning or content); total = until the stream closes. The FIRST request after every model load is a
discarded warm-up (logged with warmup=True). Decoding = the arm's B2 decoding (b2_common.GEN).
GPU 2 SM clock / util at 20 ms (pynvml); all-GPU utilisation via `nvidia-smi dmon -s u -o DT` (analysis flags a request
when GPU 0/1/3 steps by >= 50 points between consecutive seconds within [start - 1 s, end + 1 s]; flagged requests
are never dropped). Isolation: no other work of ours may run on this host (checked at start/end and every 30 s; seen
-> the run is marked VOID in the meta). Localhost, no network. Resumable per (arm, sub-dataset, input, question).
STOP: > 1 % errors in a load.
"""
import argparse
import json
import os
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
sys.path.insert(0, str(HERE.parent / "cost"))
sys.path.insert(0, str(HERE.parent / "lib"))
import b2_common as C2  # noqa: E402

C2.check_b1_common()
import b1_common as B  # noqa: E402
import b2_infer_vllm as I  # noqa: E402  (datasets, flags, GPU-2 session check)

X = I.X
N = 50
ARMS = C2.INSTRUCT_ORDER + C2.THINKING_ORDER
IGNORE = ("dseries_watchdog", "dseries_monitor", "b2_supervisor", "b2_status", "nvidia-smi", "tmux", "claude", "sshd",
          "-bash", "bash -l", "b2_chain")
GPU_UUID = I.GPU_UUID
CACHE_METRICS = ("vllm:prefix_cache_hits_total", "vllm:mm_cache_hits_total", "vllm:external_prefix_cache_hits_total")


class Sampler:
    """GPU 2 SM clock / util at 20 ms."""

    def __init__(self):
        import pynvml
        self.nv = pynvml
        pynvml.nvmlInit()
        self.h = pynvml.nvmlDeviceGetHandleByUUID(GPU_UUID)
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


def cache_counters(client):
    txt = client.get(f"{X.BASE}/metrics").text
    out = {}
    for line in txt.splitlines():
        for k in CACHE_METRICS:
            if line.startswith(k):
                out[k] = out.get(k, 0.0) + float(line.rsplit(" ", 1)[1])
    return out


def isolation(iso_path, tag):
    me = os.getsid(0)
    ps = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "pid=,sid=,pcpu=,etime=,args="], capture_output=True,
                        text=True).stdout.splitlines()
    others = []
    for l in ps:
        f = l.split(None, 4)
        if len(f) < 5:
            continue
        pid, sid, pcpu = int(f[0]), int(f[1]), float(f[2])
        if sid == me or "ps -u" in f[4] or any(k in f[4] for k in IGNORE):
            continue
        if pcpu > 5.0:
            others.append(dict(pid=pid, sid=sid, pcpu=pcpu, etime=f[3], cmd=f[4][:160]))
    gp = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                        capture_output=True, text=True).stdout.splitlines()
    ours_gpu = []
    for l in gp:
        u, pid = [x.strip() for x in l.split(",")]
        owner = subprocess.run(["ps", "-o", "user=,sid=", "-p", pid], capture_output=True, text=True).stdout.split()
        if owner and owner[0] == os.environ.get("USER", "pragya") and int(owner[1]) != me:
            ours_gpu.append(dict(gpu=u, pid=int(pid)))
    rec = dict(tag=tag, at=datetime.now().isoformat(), loadavg=Path("/proc/loadavg").read_text().strip(),
               our_busy_processes_outside_session=others, our_gpu_processes_outside_session=ours_gpu,
               overlap=bool(others or ours_gpu))
    with open(iso_path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    X.log(f"B2 latency isolation {tag}: overlap={rec['overlap']} {others[:3]} {ours_gpu}")
    return rec


def one(client, body, sampler, thinking):
    first, first_answer, usage, chunks, err, finish = None, None, None, [], None, None
    clk0 = sampler.now_clock()
    w0 = time.time()
    t0 = time.perf_counter()
    try:
        with client.stream("POST", f"{X.BASE}/v1/chat/completions", content=body,
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
                        d = ch.get("delta") or {}
                        c = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                        if c:
                            now = time.perf_counter()
                            first = first or now
                            chunks.append(c)
                            if first_answer is None and (not thinking or "</think>" in "".join(chunks[-3:])):
                                first_answer = now
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t1 = time.perf_counter()
    w1 = time.time()
    u = usage or {}
    return dict(ttft_s=round(first - t0, 4) if first else None, total_s=round(t1 - t0, 4),
                time_to_think_end_s=round(first_answer - t0, 4) if (thinking and first_answer) else None,
                wall_start=w0, wall_end=w1, prompt_tokens=u.get("prompt_tokens"),
                completion_tokens=u.get("completion_tokens"),
                cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens"), finish_reason=finish,
                text="".join(chunks), error=err, gpu2=sampler.window(w0, w1), sm_mhz_at_send=clk0)


def plan(ds):
    """[(sub_dataset, input, item)] — first N of each sub-dataset's fixed order, per input."""
    out = []
    subs = ("herbench",) if ds.name == "herbench" else tuple(ds.order)   # HERBench: the full set's fixed order
    for sub in subs:
        for inp in getattr(ds, "inputs", ("RECENT", "HISTORY")):
            src = ds.order[sub]
            if ds.name == "herbench":   # disk: the sample runs after shard 0, on shard-0 videos (recorded deviation)
                src = [it for it in src if it["shard"] == 0]
            out += [(sub, inp, it) for it in src[:N]]
    return out


def run_arm(arm, ds, out_dir, req_path, iso_path):
    thinking = C2.is_thinking(arm)
    gen = C2.GEN["thinking" if thinking else "instruct"]
    reqs = plan(ds)
    done = set()
    if req_path.exists():
        done = {(r["arm"], r["sub_dataset"], r["input"], r["item_id"]) for r in map(json.loads, open(req_path))
                if not r["warmup"] and not r["error"]}
    todo = [x for x in reqs if (arm, x[0], x[1], x[2]["item_id"]) not in done]
    if not todo:
        return
    X.log(f"B2 latency {ds.name} {arm}: rendering {len(todo)} bodies before the server starts")
    bodies = []
    for sub, inp, it in todo:
        content, fmeta = B.build_content(it, inp)
        body = dict(model=arm, messages=[{"role": "user", "content": content}], stream=True,
                    stream_options={"include_usage": True}, **{k: v for k, v in gen.items() if k not in ("logprobs", "top_logprobs")})
        bodies.append((sub, inp, it, json.dumps(body).encode(), fmeta))
    if I.gpu_pids():
        raise SystemExit(f"GPU 2 not idle before server start: {I.gpu_pids()} — STOP")
    srv = X.Server(arm, I.FLAGS + ["--enable-prompt-tokens-details"])
    sampler = None
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(arm=arm, started=datetime.now().isoformat(),
                                                gen={k: v for k, v in gen.items() if k not in ("logprobs", "top_logprobs")},
                                                **info))
        X.meta_save(m)
        sampler = Sampler()
        isolation(iso_path, f"start {arm}")
        with httpx.Client(timeout=None) as client:
            c0 = cache_counters(client)
            w = one(client, bodies[0][3], sampler, thinking)        # discarded warm-up (first after load)
            with open(req_path, "a") as f:
                f.write(json.dumps(dict(w, arm=arm, sub_dataset=bodies[0][0], input=bodies[0][1],
                                        item_id=bodies[0][2]["item_id"], warmup=True, at=datetime.now().isoformat())) + "\n")
            errs = 0
            for k, (sub, inp, it, body, fmeta) in enumerate(bodies, 1):
                r = one(client, body, sampler, thinking)
                txt = r.pop("text")
                region = B.answer_region(txt, thinking)
                rec = dict(r, arm=arm, revision=C2.MODELS[arm][1], sub_dataset=sub, input=inp, item_id=it["item_id"],
                           task=it["task"], warmup=False, n_frames=len(fmeta["frame_sha256"]),
                           frame_sha256=fmeta["frame_sha256"], think_closed=("</think>" in txt) if thinking else None,
                           correct_upstream=bool(ds.upstream_correct(it, region)) if not r["error"] else None,
                           text_head=txt[:200], text_tail=txt[-300:], at=datetime.now().isoformat())
                with open(req_path, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                errs += bool(r["error"])
                if r["cached_tokens"]:
                    raise SystemExit(f"B2 latency CACHE CHECK FAILED {arm} {it['item_id']}: cached_tokens={r['cached_tokens']}")
                if k % 25 == 0:
                    X.log(f"B2 latency {ds.name} {arm}: {k}/{len(bodies)}; last ttft {r['ttft_s']} total {r['total_s']}")
            c1 = cache_counters(client)
        grew = {k: c1.get(k, 0) - c0.get(k, 0) for k in c1 if c1.get(k, 0) != c0.get(k, 0)}
        m = X.meta_load()
        m.setdefault("cache_checks", []).append(dict(arm=arm, before=c0, after=c1, grew=grew,
                                                     note="includes the warm-up request"))
        X.meta_save(m)
        isolation(iso_path, f"end {arm}")
        if grew:
            raise SystemExit(f"B2 latency CACHE CHECK FAILED {arm}: counters grew {grew}")
        if errs > 0.01 * len(bodies):
            raise SystemExit(f"B2 latency {arm}: {errs} errors > 1 % — STOP")
    finally:
        if sampler:
            sampler.close()
        srv.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(I.DATASETS), required=True)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--wait-clear-h", type=float, default=6.0)
    a = ap.parse_args()
    if C2.HALT.exists():
        raise SystemExit(f"HALT file present: {C2.HALT.read_text().strip()}")
    ds = I.DATASETS[a.dataset](None)   # full fixed order (StreamingBench: the latency videos are kept across shards)
    out_dir = Path(f"results/benchmarks/study_b2_{a.dataset}")
    out_dir.mkdir(parents=True, exist_ok=True)
    req_path = out_dir / "b2_latency_requests_h100nvl.jsonl"
    iso_path = out_dir / "b2_latency_isolation_h100nvl.jsonl"
    dmon_path = Path(f"logs/b2_latency_{a.dataset}_dmon.log")
    X.META_PATH = out_dir / "b2_latency_meta_h100nvl.json"
    X.CURRENT = Path("logs/b2_latency_current.json")
    t_end, clear = time.time() + 3600 * a.wait_clear_h, 0
    while clear < 2:
        clear = 0 if isolation(iso_path, "pre-start wait")["overlap"] else clear + 1
        if clear < 2:
            if time.time() > t_end:
                raise SystemExit(3)
            time.sleep(60)
    iso0 = isolation(iso_path, "run start")
    dm = subprocess.Popen(["nvidia-smi", "dmon", "-s", "u", "-d", "1", "-o", "DT"], stdout=open(dmon_path, "a"),
                          stderr=subprocess.STDOUT)
    stop_ev = threading.Event()

    def periodic():
        while not stop_ev.wait(30):
            isolation(iso_path, "periodic")

    th = threading.Thread(target=periodic, daemon=True)
    th.start()
    try:
        for arm in a.arms.split(","):
            run_arm(arm, ds, out_dir, req_path, iso_path)
    finally:
        stop_ev.set()
        dm.terminate()
    iso1 = isolation(iso_path, "run end")
    seen = [json.loads(l) for l in open(iso_path)]
    run = [s for s in seen if s["tag"] != "pre-start wait"]
    m = X.meta_load()
    m["isolation"] = dict(void=any(s["overlap"] for s in run), n_checks=len(run), start=iso0["at"], end=iso1["at"],
                          ignored_helpers=list(IGNORE), cpu_threshold_pct=5.0, dmon_log=str(dmon_path),
                          network="localhost (127.0.0.1); no network")
    from _provenance import stamp
    m.setdefault("_provenance", []).append(stamp(script="b2_latency.py", model=a.arms, device=f"{X.DEV}_gpu2",
                                                 n=len(plan(ds)) * len(a.arms.split(",")), args=a))
    X.meta_save(m)
    X.log(f"B2 latency {a.dataset} done; VOID={m['isolation']['void']}")


if __name__ == "__main__":
    main()
