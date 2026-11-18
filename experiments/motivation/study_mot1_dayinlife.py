#!/usr/bin/env python3
"""StudyMOT1-dayinlife: a fleet of dashcams monitored in real time on the shared 32B, and one robot question that needs
its cold ~11k-token history rebuilt, in one go or in pieces. A motivation measurement (claim 6), not a policy test.
Pre-registered in research/EXPERIMENTS.md (StudyMOT1-dayinlife). Request-harness client only (ENG1c / ENG1e pattern):
direct HTTP requests; the live2 coordinator and emulator are NOT used. Bodies are built by live2/bodies.build_body
(kind monitor = the live SH body verified in StudyLIVE2-pre; kind piece / recall = the live robot bodies).

Usage: study_mot1_dayinlife.py all     (one server: host fill, N selection, main runs; then analysis after stop)
       study_mot1_dayinlife.py analyse (CPU only, server down)
"""
import argparse
import asyncio
import gzip
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L2 = REPO / "experiments/orchestration/live2"
for p in (L2, L2 / "fleet", REPO / "experiments/orchestration", REPO / "experiments/cost", REPO / "experiments/lib"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

OUT = REPO / "results/motivation/mot1"
FRAMES = Path.home() / "data/live2/frames_by_ref"
STORE = Path.home() / "data/live2/jpeg"
URL = "http://127.0.0.1:8031/v1/chat/completions"
WINDOW_S, CADENCE_S, Q_AT_S = 60.0, 0.5, 20.0
EVERY = 4                   # AMENDMENT 1: the cloud gets every 4th 0.5 s instant of a dashcam (one request per 2 s)
SEND_PERIOD_S = EVERY * CADENCE_S
DEADLINE_S = 0.916          # 1.0 s target minus the D75 allowance (0.040 s upload at 13.6 Mbit/s + 0.044 s RTT)
N_GRID = (8, 12, 16, 20)    # AMENDMENT 1 (first design: 8, 16, 24, 32 at one request per 0.5 s per stream)
ON_TIME_MIN = 0.99
N_REP = 5
ACTIONS = ("NONE", "ONE-GO", "P2048", "P1024")
NFR = {"P2048": 23, "P1024": 11}
HOST_GIB, TOK_PER_GIB, FILL_X = 27, 4096, 1.5


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "mot1.log", "a") as f:
        f.write(line + "\n")


# ------------------------------------------------------------------------------------------------ plans
def dense_by_clip():
    import data_sources as DS
    by = defaultdict(list)
    for (fn, t) in DS.orin_dense_scores():
        by[fn].append(t)
    return {fn: sorted(ts) for fn, ts in by.items()}


def robot_candidates():
    """EVAL questions whose D2 history (2-s stride frames with t <= t_ask, stored) is 11k +/- 1k tokens
    (StudyRH4 accounting: 90 per image + 31 header)."""
    import data_sources as DS
    stored = defaultdict(list)
    for ln in open(STORE / "sember_d2_q88/encode_log.jsonl"):
        r = json.loads(ln)
        sid, t = r["frame_ref"].split("|f")
        stored[sid].append(float(t))
    out = []
    for sid, sm in sorted(DS.eval_sessions().items()):
        ts = sorted(stored.get(sid, []))
        for q in sm.questions:
            fr = [t for t in ts if t <= q.t_ask + 1e-9]
            est = 31 + 90 * len(fr)
            if 10000 <= est <= 12000:
                out.append(dict(sid=sid, question_id=q.question_id, t_ask=q.t_ask, question=q.question,
                                options=list(q.options), gold=q.gold_letter, frames=[f"{sid}|f{t:08.2f}" for t in fr],
                                est_tokens=est))
    return out


def plan(seed_key, n):
    rng = random.Random(f"mot1a1|{seed_key}")
    dense = dense_by_clip()
    clips = sorted(dense)
    rng.shuffle(clips)
    n_inst = int(WINDOW_S / SEND_PERIOD_S)
    streams = []
    pool = iter(clips)
    for s in range(n):
        seq, insts = [], []
        while len(insts) < n_inst:
            c = next(pool)
            seq.append(c)
            grid = [t for t in dense[c] if abs(2 * t - round(2 * t)) < 1e-6]   # the CTRL1c 0.5 s grid (dense set is 0.25 s)
            insts += [(c, t) for t in grid[::EVERY]]           # every 4th decision instant: clip time advances 2 s
        streams.append(dict(stream=s, offset=round(rng.uniform(0, SEND_PERIOD_S), 4), clips=seq, instants=insts[:n_inst]))
    cands = robot_candidates()
    robot = cands[rng.randrange(len(cands))]
    return dict(seed_key=seed_key, n=n, streams=streams, robot=robot, n_candidates=len(cands))


# ------------------------------------------------------------------------------------------------ requests
async def post(c, body, **meta):
    t0 = time.time()
    first, last, usage, err, n_tok = None, None, {}, None, 0
    try:
        async with c.stream("POST", URL, json=body) as r:
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
                        if (ch.get("delta") or {}).get("content"):
                            now = time.time()
                            first = first or now
                            last = now
                            n_tok += 1
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t_end = time.time()
    return dict(**meta, t_submit=round(t0, 6), t_first=round(first, 6) if first else None,
                t_last=round(last, 6) if last else None, t_end=round(t_end, 6),
                ttft_s=round(first - t0, 5) if first else None, e2e_s=round((last or t_end) - t0, 5),
                prompt_tokens=usage.get("prompt_tokens"),
                cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                completion_tokens=usage.get("completion_tokens"), error=err)


def mon_body(tag, stream, frame_ref):
    import bodies as B
    import cachekeys as K
    dev = f"dash{stream:03d}"
    b = B.build_body(kind="monitor", device_id=dev, session_id=None, run_tag=tag, salt=K.cache_salt(tag, dev),
                     header=B.SH_HEADER, frames=[dict(frame_ref=frame_ref, path=FRAMES / frame_ref)],
                     question=None, options=(), max_tokens=B.SH_GEN["max_tokens"])
    return B.strip_internal(b, strip_hints=True)


async def stream_task(c, t0, tag, st, rows):
    for k, (clip, t) in enumerate(st["instants"]):
        at = t0 + st["offset"] + k * SEND_PERIOD_S
        d = at - time.time()
        if d > 0:
            await asyncio.sleep(d)
        ref = f"{clip}|t{t:07.2f}"
        rows.append(asyncio.create_task(post(c, mon_body(tag, st["stream"], ref), kind="monitor", stream=st["stream"],
                                             k=k, frame_ref=ref, t_sched=round(at, 6))))


async def robot_task(c, t0, tag, robot, action, rows):
    import bodies as B
    import cachekeys as K
    from coordinator import HEADER_TEXT
    d = t0 + Q_AT_S - time.time()
    if d > 0:
        await asyncio.sleep(d)
    tq = time.time()
    dev, sid = "robot000", robot["sid"]
    salt = K.cache_salt(tag, dev)
    fr = robot["frames"]
    cuts = [len(fr)] if action == "ONE-GO" else list(range(NFR[action], len(fr), NFR[action])) + [len(fr)]
    out, prev = [], 0
    for j, e in enumerate(cuts):
        last = j == len(cuts) - 1
        frames = [dict(frame_ref=r, path=None) for r in fr[:prev]] + [dict(frame_ref=r, path=FRAMES / r) for r in fr[prev:e]]
        if last:
            b = B.build_body(kind="recall", device_id=dev, session_id=sid, run_tag=tag, salt=salt, header=HEADER_TEXT,
                             frames=frames, question=robot["question"], options=robot["options"],
                             max_tokens=B.RECALL_GEN["max_tokens"])
        else:
            b = B.build_body(kind="piece", device_id=dev, session_id=sid, run_tag=tag, salt=salt, header=HEADER_TEXT,
                             frames=frames, question=None, options=(), max_tokens=1)
        r = await post(c, B.strip_internal(b, strip_hints=True), kind="robot", part_i=j, n_parts=len(cuts),
                       new_frames=e - prev, t_question=round(tq, 6))
        out.append(r)
        prev = e
    rows.extend(out)


async def run_once(c, label, pl, action, rep):
    tag = f"mot1{label}x{int(time.time() * 1000) % 10 ** 9}"
    t0 = time.time() + 0.5
    pending, robot_rows = [], []
    tasks = [stream_task(c, t0, tag, st, pending) for st in pl["streams"]]
    if action != "NONE":
        tasks.append(robot_task(c, t0, tag, pl["robot"], action, robot_rows))
    await asyncio.gather(*tasks)
    mon = await asyncio.gather(*pending)
    base = dict(label=label, action=action, rep=rep, n=pl["n"], seed_key=pl["seed_key"], tag=tag, t0=round(t0, 6))
    rows = [dict(r, **base) for r in mon] + [dict(r, **base) for r in robot_rows]
    on = sum(1 for r in mon if r["error"] is None and r["t_last"] and r["t_last"] - r["t_submit"] <= DEADLINE_S)
    summ = dict(kind="run_summary", **base, n_instants=len(mon), on_time=on, on_time_frac=round(on / len(mon), 5),
                http_errors=sum(1 for r in rows if r["error"]), robot=pl["robot"]["question_id"] if action != "NONE" else None,
                robot_first_cached=(robot_rows[0]["cached_tokens"] if robot_rows else None),
                robot_ttft_from_q=(round(robot_rows[-1]["t_first"] - robot_rows[-1]["t_question"], 4)
                                   if robot_rows and robot_rows[-1]["t_first"] else None),
                late_dispatch_max_s=round(max(r["t_submit"] - r["t_sched"] for r in mon), 4))
    with open(OUT / "mot1_requests.jsonl", "a") as f:
        for r in rows + [summ]:
            f.write(json.dumps(r, default=str) + "\n")
    log(f"{label} {action} rep {rep} N={pl['n']}: on-time {on}/{len(mon)} ({summ['on_time_frac']:.4f}); errors "
        f"{summ['http_errors']}; robot ttft {summ['robot_ttft_from_q']} first cached {summ['robot_first_cached']}; "
        f"dispatch lag max {summ['late_dispatch_max_s']} s")
    await asyncio.sleep(3.0)
    return summ


async def fill(c, M):
    """Host steady state at server start (ENG1c / ENG1e convention): fresh ~26k p28 histories, max_tokens 1, until
    1.5 x the 27 GiB host capacity in tokens was written."""
    M.load_sessions(warm=False)
    target, done, k = int(FILL_X * HOST_GIB * TOK_PER_GIB), 0, 0
    while done < target:
        p = M.SESS["p28"][k % len(M.SESS["p28"])]
        h = M.Hist(p["frames"], f"MOTF{k}x{int(time.time()) % 10 ** 6}")
        rid = f"motfill{k}x{int(time.time() * 1000) % 10 ** 9}"
        r = await M.post(c, h.body(rid=rid), rid, "fill")
        if r["error"]:
            raise SystemExit(f"fill error {r['error']}: STOP")
        done += r["prompt_tokens"] or 0
        k += 1
    log(f"host fill: {done} tokens in {k} fresh histories (cap {HOST_GIB * TOK_PER_GIB}; 1.5x target {target})")
    return dict(tokens=done, n=k, cap_tokens=HOST_GIB * TOK_PER_GIB)


async def experiment(M):
    import httpx
    res = dict(n_selection=[], main=[])
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None,
                                                                   max_keepalive_connections=None)) as c:
        res["fill"] = await fill(c, M)
        for n in N_GRID:
            res["n_selection"].append(await run_once(c, f"A1NSEL{n}", plan(f"nsel{n}", n), "NONE", 0))
        ok = [s["n"] for s in res["n_selection"] if s["on_time_frac"] >= ON_TIME_MIN]
        if not ok or 8 not in ok:
            log("N SELECTION FAILED: N = 8 below 99 % on time: STOP")
            res["stop"] = "N selection failed"
            return res
        N = max(ok)
        res["N"] = N
        log(f"N selection: on-time {[(s['n'], s['on_time_frac']) for s in res['n_selection']]} -> N = {N}")
        for r in range(1, N_REP + 1):
            pl = plan(f"rep{r}", N)
            order = list(ACTIONS) if r % 2 == 1 else list(reversed(ACTIONS))
            invalid = 0
            for a in order:
                s = await run_once(c, f"A1R{r}", pl, a, r)
                if a == "NONE" and s["on_time_frac"] < ON_TIME_MIN:
                    invalid += 1
                    log(f"rep {r}: NONE below 99 % ({s['on_time_frac']}): INVALID, rerun once")
                    s = await run_once(c, f"A1R{r}rerun", pl, a, r)
                    if s["on_time_frac"] < ON_TIME_MIN:
                        res["stop"] = f"two INVALID control runs in repetition {r}"
                        log(f"rep {r}: control INVALID twice: STOP")
                        return res
                res["main"].append(s)
    return res


def run_all():
    import study_live2_pilot as PL
    PL.OUT = OUT
    PL.WORK = Path.home() / "data/live2/mot1"
    PL.WORK.mkdir(parents=True, exist_ok=True)
    srv, sinfo, M = PL.start_server(float(HOST_GIB))
    log(f"server up: {json.dumps({k: v for k, v in sinfo.items() if k != 'command'})}")
    (OUT / "mot1_server.json").write_text(json.dumps(sinfo, indent=1, default=str) + "\n")
    try:
        res = asyncio.run(experiment(M))
    finally:
        srv.stop()
    (OUT / "mot1_runs.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    log(f"experiment done: {res.get('stop') or 'complete'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("all", "analyse"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.what == "all":
        run_all()
    else:
        import mot1_analyse as AN
        AN.main()


if __name__ == "__main__":
    main()
