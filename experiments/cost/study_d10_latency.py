#!/usr/bin/env python3
"""StudyD10 — single-request latency snapshot, 32B on h100nvl GPU 2 (vLLM 0.31.0, StudyClean stack).

Pre-registered in research/EXPERIMENTS.md (StudyD10). One request at a time, cold: prefix caching OFF, multimodal
processor cache OFF, bodies pre-serialized before the clock starts; TTFT from immediately before send to the first
streamed token (reasoning or content); total = until the stream closes. The FIRST request after every model load is a
discarded warm-up (logged with warmup=True, the cell's first question).
Loads (one server each, run in this order):
  sember_T  32B-T, R1 K1 (RICH) video requests with K2's exact settings (model-card VL sampling T 1.0, top_p 0.95,
            top_k 20, max 16384, request seed 42; study_r1_vllm.body + MM_LIMIT); 50 questions, random.Random(0)
            .sample of R1's question order
  images_T  32B-T, ERQA then MV-RoboBench, 50 each (Random(0).sample per benchmark of the D9 manifest), D9 Thinking
            params (T 1.0, top_p 0.95, top_k 20, max 16384, request seed 0)
  images_I  32B-I, the same 100 image questions, greedy, max 512
Isolation (spec: no CPU, disk or GPU work of ours may overlap): at start and end, and every 30 s, every process owned
by this user outside this script's session that uses > 5 % CPU, or any GPU process of ours outside the session, is
logged; the run is marked VOID if any is seen. GPU 2 SM clock/util at 20 ms (pynvml); all-GPU utilisation via
`nvidia-smi dmon -s u -o DT` for neighbour flags (analysis: a >= 50-point step on GPU 0/1/3 between consecutive
seconds within [start - 1 s, end + 1 s] flags the request; flagged requests are never dropped).
Resumable per (load, bench, question). STOP: > 1 % errors in a load.
"""
import argparse
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "erqa"))
import study_clean_vllm as C  # noqa: E402  (R.manifest / R1 body; gpu check -> CLEAN_GPU_UUID)
import study_d9_vllm as D9  # noqa: E402

X, R = C.X, C.R
OUT = Path("results/cost/study_d10")
REQ = OUT / "study_d10_requests_h100nvl.jsonl"
META = OUT / "study_d10_run_meta_h100nvl.json"
ISO = OUT / "study_d10_isolation_h100nvl.jsonl"
DMON = Path("logs/study_d10_dmon.log")
X.META_PATH = META
X.CURRENT = Path("logs/study_d10_current.json")
N = 50
SEMBER_T = dict(R.CARD_VL, min_p=0.0, max_tokens=16384)          # K2's
LOADS = ["sember_T", "images_T", "images_I"]
C.H5SNAP = OUT / "study_d10_snapshots_h100nvl.jsonl"     # C.snapshot() appends here
# Our own always-on helpers that are not experiment work (excluded from the overlap test, listed in the meta):
# the chain's watchdog / monitor loops and their nvidia-smi calls, tmux, the interactive Claude Code session, sshd/bash.
IGNORE = ("dseries_watchdog", "dseries_monitor", "nvidia-smi", "tmux", "claude", "sshd", "-bash", "bash -l")


def isolation(tag):
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
    with open(ISO, "a") as f:
        f.write(json.dumps(rec) + "\n")
    X.log(f"isolation {tag}: overlap={rec['overlap']} {others[:3]} {ours_gpu}")
    return rec


class IsoWatch(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_ev = threading.Event()

    def run(self):
        while not self.stop_ev.wait(30):
            isolation("periodic")


def requests_for(load):
    """[(bench, qid, body_bytes, meta)] in a fixed order."""
    out = []
    if load == "sember_T":
        rows, order = R.manifest()
        qs = random.Random(0).sample(order, N)
        for q in qs:
            b, _, nfr = C.R1_BODY(rows[(q, "RICH")], "K2", "32BT", SEMBER_T)
            out.append(("sember", q, json.dumps(b).encode(), dict(n_frames=nfr, correct_letter=rows[(q, "RICH")]
                                                                   ["correct_letter"], letters="ABCDE")))
        return out
    man = [json.loads(l) for l in open(D9.MAN)]
    model, params, seed = ("32BT", D9.THINKING, 0) if load == "images_T" else ("32BI", D9.INSTRUCT, None)
    for bench in ("erqa", "mvrb"):
        rows = [r for r in man if r["bench"] == bench]
        for r in random.Random(0).sample(rows, N):
            b = D9.build(r, model, params, seed)
            out.append((bench, r["qid"], json.dumps(b).encode(), dict(correct_letter=r["correct_letter"],
                                                                      letters=r["letters"])))
    return out


def one(client, body, sampler, thinking):
    first, first_answer, usage, chunks, err, finish = None, None, None, [], None, None
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
                            if first_answer is None and (not thinking or D9.END in "".join(chunks[-3:])):
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
                text="".join(chunks), error=err, gpu2=sampler.window(w0, w1), sm_mhz_at_send=sampler.now_clock())


def run_load(load):
    thinking = load.endswith("_T")
    key = "32BT" if thinking else "32BI"
    if load == "sember_T":
        flags = R.MM_LIMIT + ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details"]
    else:
        flags = ["--limit-mm-per-prompt", json.dumps({"image": 16, "video": 0}), "--mm-processor-cache-gb", "0",
                 "--enable-prompt-tokens-details", "--host", "127.0.0.1"]
    reqs = requests_for(load)
    done = set()
    if REQ.exists():
        done = {(r["load"], r["bench"], r["qid"]) for r in map(json.loads, open(REQ)) if not r["warmup"]
                and not r["error"]}
    todo = [x for x in reqs if (load, x[0], x[1]) not in done]
    if not todo:
        return
    srv = X.Server(key, flags)
    sampler = None
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(load=load, started=datetime.now().isoformat(), **info))
        X.meta_save(m)
        sampler = C.Sampler()
        isolation(f"start {load}")
        C.snapshot(f"before {load}")
        with httpx.Client(timeout=None) as client:
            c0 = C.cache_counters(client)
            w = one(client, todo[0][2], sampler, thinking)                 # discarded warm-up (first after load)
            with open(REQ, "a") as f:
                f.write(json.dumps(dict(w, load=load, bench=todo[0][0], qid=todo[0][1], warmup=True,
                                        at=datetime.now().isoformat())) + "\n")
            errs = 0
            for k, (bench, qid, body, meta) in enumerate(todo, 1):
                X.CURRENT.write_text(json.dumps(dict(load=load, bench=bench, qid=qid)))
                r = one(client, body, sampler, thinking)
                txt = r["text"]
                closed = (D9.END in txt) if thinking else None
                ans = txt.split(D9.END, 1)[1].strip() if closed else txt.strip()
                if bench == "sember":
                    _, pred = R.score(txt, thinking)
                else:
                    pred, _ = D9.extract_letter(ans, meta["letters"])
                rec = dict(r, load=load, bench=bench, qid=qid, warmup=False, model=key, think_closed=closed,
                           runaway=bool(thinking and (r["finish_reason"] == "length" or not closed)),
                           pred=pred, correct=pred == meta["correct_letter"], at=datetime.now().isoformat())
                rec.pop("text")
                rec["text_head"], rec["text_tail"] = txt[:200], txt[-300:]
                with open(REQ, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                errs += bool(r["error"])
                if r["cached_tokens"]:
                    raise SystemExit(f"D10 CACHE CHECK FAILED {load} {qid}: cached_tokens={r['cached_tokens']}")
                if k % 10 == 0:
                    X.log(f"D10 {load}: {k}/{len(todo)}; last ttft {r['ttft_s']} total {r['total_s']}")
            c1 = C.cache_counters(client)
        grew = {k: c1.get(k, 0) - c0.get(k, 0) for k in c1 if c1.get(k, 0) != c0.get(k, 0)}
        m = X.meta_load()
        m.setdefault("cache_checks", []).append(dict(load=load, before=c0, after=c1, grew=grew,
                                                     note="includes the warm-up request"))
        X.meta_save(m)
        C.snapshot(f"after {load}")
        isolation(f"end {load}")
        if grew:
            raise SystemExit(f"D10 CACHE CHECK FAILED {load}: counters grew {grew}")
        if errs > 0.01 * len(todo):
            raise SystemExit(f"D10 {load}: {errs} errors > 1 % — STOP")
    finally:
        if sampler:
            sampler.close()
        srv.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loads", default=",".join(LOADS))
    ap.add_argument("--wait-clear-h", type=float, default=6.0,
                    help="before starting, wait (up to this many hours) until two consecutive 60-s-apart isolation "
                         "checks see no other work of ours; exit 3 if never clear")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t_end, clear = time.time() + 3600 * a.wait_clear_h, 0
    while clear < 2:
        clear = 0 if isolation("pre-start wait")["overlap"] else clear + 1
        if clear < 2:
            if time.time() > t_end:
                raise SystemExit(3)
            time.sleep(60)
    iso0 = isolation("run start")
    dm = subprocess.Popen(["nvidia-smi", "dmon", "-s", "u", "-d", "1", "-o", "DT"], stdout=open(DMON, "a"),
                          stderr=subprocess.STDOUT)
    wt = IsoWatch()
    wt.start()
    try:
        for load in a.loads.split(","):
            run_load(load)
    finally:
        wt.stop_ev.set()
        dm.terminate()
    iso1 = isolation("run end")
    seen = [json.loads(l) for l in open(ISO)]
    m = X.meta_load()
    run = [s for s in seen if s["tag"] != "pre-start wait"]          # pre-start waits are expected to see overlap
    m["isolation"] = dict(void=any(s["overlap"] for s in run), n_checks=len(run), n_prestart_waits=len(seen) - len(run),
                          start=iso0["at"], end=iso1["at"], ignored_helpers=list(IGNORE), cpu_threshold_pct=5.0)
    from _provenance import stamp
    m.setdefault("_provenance", []).append(stamp(script="study_d10_latency.py", model="32BT,32BI",
                                                 device=f"{X.DEV}_gpu2", n=5 * N, args=a))
    X.meta_save(m)
    X.log(f"D10 done; VOID={m['isolation']['void']}")


if __name__ == "__main__":
    main()
