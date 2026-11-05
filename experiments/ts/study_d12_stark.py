#!/usr/bin/env python3
"""StudyD12-stark — STARK-only time-series snapshot on the D-series vLLM stack (h100nvl GPU 2). Pre-registered.

Stages:
  sample  CPU. Waits for the STARK_10k download (tier families) to finish, then replicates study_d12_prep.build_stark's
          rule over the 41 tiered families (one CSV = one item; per family a np.random.default_rng(0) permutation;
          families visited round-robin in sorted order), skipping any item whose query equals a StudyD12-pilot item's
          query, until 500 items. Manifest -> results/ts/study_d12_stark/stark_manifest.jsonl.
  acc     --arm 4BI | 32BI (greedy, max_tokens 2048) | 32BT (model-card sampling T 1.0, top_p 0.95, top_k 20, min_p 0,
          max_tokens 16384, request seed 0); conc 8; streamed; text kept. Thinking: after 64 completions the full
          500 is projected from elapsed time; if > 4 h, only the first 250 items (manifest order) are run (recorded).
          Transport errors retried up to 2 more times (logged); STOP if > 1 % remain failed or the server logs an error
          before requests complete.
  lat     single-request latency, 50 items per arm (random.Random(0).sample of the manifest), StudyD10's method
          (study_d10_latency: isolation wait / VOID on overlap, pre-serialised bodies, cold, prefix + processor caches
          off, first request per load discarded, GPU-2 SM clock, dmon neighbour log).
Questions are the benchmark's own `query`, verbatim, as the only user message (TEXT only).
"""
import argparse
import asyncio
import glob
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cost"))
sys.path.insert(0, str(HERE.parent / "lib"))
RAW = Path.home() / "data/stark/STARK_10k"
FAMS = Path.home() / "data/stark/tier_families.txt"
DL_LOG = Path.home() / "data/stark/dl10k_tier.log"
OUT = Path("results/ts/study_d12_stark")
MAN = OUT / "stark_manifest.jsonl"
PILOT = Path("results/ts/study_d12_prep/manifest.json")
N_ITEMS = 500
ARMS = {"4BI": dict(temperature=0.0, max_tokens=2048, seed=0),
        "32BI": dict(temperature=0.0, max_tokens=2048, seed=0),
        "32BT": dict(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, repetition_penalty=1.0, presence_penalty=0.0,
                     max_tokens=16384, seed=0)}
CONC, ATTEMPTS = 8, 3
TRANSPORT = ("ReadError", "RemoteProtocolError", "ConnectError", "WriteError", "ReadTimeout", "ConnectTimeout",
             "PoolTimeout", "WriteTimeout", "CloseError")
SRV_ERR = ("ERROR", "Traceback", "Exception", "out of memory", "CUDA error", "OutOfMemory")


def tiers():
    sys.path.insert(0, str(HERE))
    import study_d12_prep as P
    return P.STARK_TIERS, P.STARK_CATEGORICAL


def stage_sample(wait_h):
    import numpy as np
    import pandas as pd
    t_end = time.time() + wait_h * 3600
    while "DONE" not in (DL_LOG.read_text() if DL_LOG.exists() else ""):
        if time.time() > t_end:
            raise SystemExit("STARK_10k tier-family download not complete — STOP")
        time.sleep(120)
    T, CAT = tiers()
    fams = sorted(FAMS.read_text().split())
    pilot = {x["query"] for x in json.load(open(PILOT))["stark"]}
    by_fam = {f: sorted(glob.glob(str(RAW / f / "*.csv"))) for f in fams}
    rng = np.random.default_rng(0)
    idx = {f: rng.permutation(len(by_fam[f])).tolist() for f in fams}
    cur = {f: 0 for f in fams}
    picked, skipped = [], 0
    while len(picked) < N_ITEMS:
        progressed = False
        for f in fams:
            if len(picked) >= N_ITEMS:
                break
            while cur[f] < len(idx[f]):
                p = by_fam[f][idx[f][cur[f]]]
                cur[f] += 1
                df = pd.read_csv(p)
                q = str(df["query"].iloc[0])
                if q in pilot:
                    skipped += 1
                    continue
                tier = next((t for t, fl in T.items() if f in fl), None)
                picked.append(dict(item_id=f"stark_{len(picked):04d}", family=f, tier=tier,
                                   path=str(Path(p).relative_to(RAW.parent)), query=q, answer=str(df["answer"].iloc[0]),
                                   categorical=f in CAT))
                progressed = True
                break
        if not progressed:
            break
    OUT.mkdir(parents=True, exist_ok=True)
    with open(MAN, "w") as fo:
        for it in picked:
            fo.write(json.dumps(it) + "\n")
    meta = dict(n=len(picked), pilot_skipped=skipped, families=len(fams),
                per_family={f: sum(it["family"] == f for it in picked) for f in fams},
                per_tier={str(t): sum(it["tier"] == t for it in picked) for t in (1, 2, 3)},
                categorical=sum(it["categorical"] for it in picked), source="HF prquan/STARK_10k (41 tiered families)")
    (OUT / "stark_sample.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta)[:600])
    if len(picked) < N_ITEMS:
        raise SystemExit(f"only {len(picked)} items available — STOP")


def setup(arm):
    import study_x_vllm as X
    X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
    gpu = os.environ.get("CLEAN_GPU_UUID", "GPU-4f1d7e47-e769-a289-4860-e71c0d97267c")

    def gpu_pids():
        import subprocess
        o = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                           capture_output=True, text=True).stdout
        return [int(l.split(", ")[1]) for l in o.strip().splitlines() if l.startswith(gpu)]
    X.gpu3_pids = gpu_pids
    return X, gpu_pids


def body(it, arm, stream=True):
    b = dict(model=arm, messages=[{"role": "user", "content": it["query"]}], stream=stream, **ARMS[arm])
    if stream:
        b["stream_options"] = {"include_usage": True}
    return b


async def send_once(c, X, it, arm, attempt, req):
    t0 = time.time()
    first, chunks, usage, finish, err = None, [], None, None, None
    try:
        async with c.stream("POST", f"{X.BASE}/v1/chat/completions", json=body(it, arm)) as r:
            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {(await r.aread())[:300]!r}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    j = json.loads(line[6:])
                    if j.get("usage"):
                        usage = j["usage"]
                    for ch in j.get("choices", []):
                        d = ch.get("delta") or {}
                        x = d.get("content") or d.get("reasoning_content") or d.get("reasoning")
                        if x:
                            first = first or time.time()
                            chunks.append(x)
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    u = usage or {}
    rec = dict(arm=arm, item_id=it["item_id"], family=it["family"], tier=it["tier"], categorical=it["categorical"],
               attempt=attempt, text="".join(chunks), finish_reason=finish, prompt_tokens=u.get("prompt_tokens"),
               completion_tokens=u.get("completion_tokens"), error=err, latency_s=round(time.time() - t0, 3),
               at=datetime.now().isoformat())
    with open(req, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def run_acc(X, arm, items, req, srv):
    have = set()
    if req.exists():
        have = {(r["arm"], r["item_id"]) for r in map(json.loads, open(req)) if not r["error"]}
    todo = [it for it in items if (arm, it["item_id"]) not in have]
    X.log(f"D12S {arm}: {len(todo)} to run")
    sem = asyncio.Semaphore(CONC)
    t0, done = time.time(), [0]
    state = dict(capped=False)

    async def one(c, it, k):
        async with sem:
            if state["capped"] and k >= 250:
                return
            for attempt in range(1, ATTEMPTS + 1):
                rec = await send_once(c, X, it, arm, attempt, req)
                if rec["error"] and rec["error"].split(":")[0] in TRANSPORT and attempt < ATTEMPTS:
                    X.log(f"D12S transport error {it['item_id']} attempt {attempt} — retry")
                    continue
                break
            done[0] += 1
            if done[0] % 50 == 0:
                X.log(f"D12S {arm}: {done[0]}/{len(todo)} in {(time.time() - t0) / 60:.1f} min")
            if arm == "32BT" and done[0] == 64 and not state["capped"]:
                proj = (time.time() - t0) / 64 * len(items) / 3600
                m = X.meta_load()
                m.setdefault("thinking_projection", {})["projected_h_500"] = proj
                if proj > 4.0:
                    state["capped"] = True
                    m["thinking_projection"]["capped_to_first_250"] = True
                    X.log(f"D12S 32BT projected {proj:.1f} h > 4 h — running the first 250 items only")
                X.meta_save(m)
    order = {it["item_id"]: k for k, it in enumerate(items)}
    async with httpx.AsyncClient(timeout=None) as c:
        await asyncio.gather(*(one(c, it, order[it["item_id"]]) for it in todo))
    se = [l for l in srv.logpath.read_text(errors="replace").splitlines() if any(k in l for k in SRV_ERR)]
    if se:
        raise SystemExit(f"D12S {arm}: server log error before requests completed — STOP: {se[0][:200]}")


def stage_acc(arm):
    X, gpu_pids = setup(arm)
    req = OUT / "stark_requests_h100nvl.jsonl"
    X.META_PATH = OUT / "stark_run_meta_h100nvl.json"
    X.CURRENT = Path("logs/d12s_current.json")
    items = [json.loads(l) for l in open(MAN)]
    if gpu_pids():
        raise SystemExit("GPU 2 not idle — STOP")
    srv = X.Server(arm, ["--mm-processor-cache-gb", "0", "--host", "127.0.0.1"])
    try:
        info = srv.start()
        m = X.meta_load()
        m.setdefault("servers", []).append(dict(arm=arm, started=datetime.now().isoformat(), gen=ARMS[arm], **info))
        X.meta_save(m)
        asyncio.run(run_acc(X, arm, items, req, srv))
    finally:
        srv.stop()
    rows = [r for r in map(json.loads, open(req)) if r["arm"] == arm]
    keys = {r["item_id"] for r in rows}
    ok = {r["item_id"] for r in rows if not r["error"]}
    failed = len(keys - ok)
    X.log(f"D12S {arm}: {len(ok)} answered, {failed} still failed, {sum(bool(r['error']) for r in rows)} error rows")
    if failed > 0.01 * len(keys):
        raise SystemExit(f"D12S {arm}: {failed} still failed > 1 % — STOP")


def stage_lat(wait_h):
    import study_d10_latency as L
    C, X = L.C, L.X
    X.REPO["4BI"] = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
    L.ISO = OUT / "stark_latency_isolation_h100nvl.jsonl"
    L.DMON = Path("logs/d12s_dmon.log")
    C.H5SNAP = OUT / "stark_latency_snapshots_h100nvl.jsonl"
    X.META_PATH = OUT / "stark_latency_meta_h100nvl.json"
    X.CURRENT = Path("logs/d12s_lat_current.json")
    req = OUT / "stark_latency_requests_h100nvl.jsonl"
    items = [json.loads(l) for l in open(MAN)]
    pick = random.Random(0).sample(items, 50)
    t_end, clear = time.time() + 3600 * wait_h, 0
    while clear < 2:
        clear = 0 if L.isolation("pre-start wait")["overlap"] else clear + 1
        if clear < 2:
            if time.time() > t_end:
                raise SystemExit(3)
            time.sleep(60)
    L.isolation("run start")
    import subprocess
    dm = subprocess.Popen(["nvidia-smi", "dmon", "-s", "u", "-d", "1", "-o", "DT"], stdout=open(L.DMON, "a"),
                          stderr=subprocess.STDOUT)
    wt = L.IsoWatch()
    wt.start()
    try:
        for arm in ("4BI", "32BI", "32BT"):
            done = set()
            if req.exists():
                done = {(r["arm"], r["item_id"]) for r in map(json.loads, open(req)) if not r["warmup"]}
            if all((arm, it["item_id"]) in done for it in pick):
                continue
            srv = X.Server(arm, ["--mm-processor-cache-gb", "0", "--enable-prompt-tokens-details", "--host", "127.0.0.1"])
            sampler = None
            try:
                srv.start()
                sampler = C.Sampler()
                with httpx.Client(timeout=None) as client:
                    bodies = [(it, json.dumps(body(it, arm)).encode()) for it in pick]
                    w = L.one(client, bodies[0][1], sampler, arm == "32BT")
                    with open(req, "a") as f:
                        f.write(json.dumps(dict(w, arm=arm, item_id=bodies[0][0]["item_id"], warmup=True,
                                                text=w["text"][:200])) + "\n")
                    for it, b in bodies:
                        r = L.one(client, b, sampler, arm == "32BT")
                        txt = r.pop("text")
                        r.update(arm=arm, item_id=it["item_id"], warmup=False, text_tail=txt[-300:],
                                 runaway=r["finish_reason"] == "length", at=datetime.now().isoformat())
                        with open(req, "a") as f:
                            f.write(json.dumps(r) + "\n")
            finally:
                if sampler:
                    sampler.close()
                srv.stop()
    finally:
        wt.stop_ev.set()
        dm.terminate()
    L.isolation("run end")
    seen = [json.loads(l) for l in open(L.ISO)]
    run = [s for s in seen if s["tag"] != "pre-start wait"]
    m = X.meta_load()
    m["isolation"] = dict(void=any(s["overlap"] for s in run), n_checks=len(run))
    X.meta_save(m)
    X.log(f"D12S latency done; VOID={m['isolation']['void']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["sample", "acc", "lat"])
    ap.add_argument("--arm", choices=list(ARMS))
    ap.add_argument("--wait-h", type=float, default=10.0)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.stage == "sample":
        stage_sample(a.wait_h)
    elif a.stage == "acc":
        stage_acc(a.arm)
    else:
        stage_lat(a.wait_h)


if __name__ == "__main__":
    main()
