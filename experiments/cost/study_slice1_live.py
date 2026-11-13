#!/usr/bin/env python3
"""StudySLICE1 Part B (live mixed test) — does an orchestrator that slices the cold D2 history prefill into
prefix-chained requests, dispatched in the gaps between episodic calls, restore episodic capacity under cold recall?
EXCLUSIVE (vLLM venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudySLICE1; Part B design decisions by
the user 2026-11-12: cold recall = the ~11k D2 histories; E0 only; order C1 r 0.05 -> C4 -> C0 25/40 % -> C1 r 0.1,
P0 first in each condition; finish the current cell and stop to ask once 5 h have elapsed).

Harness: study_e10b_mixed.run_cell as used by StudyE10c / E10e (Episodic N = 1 open loop over distinct D14 requests,
D7 Poisson arrivals with E10c's seed-index map, 30-s discard, 240-s scored window, 300-s drain cap, RH7 warm sessions
for C4, 1-s /metrics + CPU timelines, exclusivity monitor, VOID on overlap), UNCHANGED except the cold-recall path:
`E.dispatch` for kind "cold_recall" hands the cold arrivals to the orchestrator below instead of posting them.
Server per cell: 32B-I, vLLM 0.31.0 defaults (E0: chunked prefill, 8,192-token steps, fcfs, async scheduling), prefix
caching ON, processor cache 128 GiB, --enable-log-requests (E10d logging config); KV-HOST adds the native offloading
connector (256 GiB) for C4.
Cold recall: one of the 20 Part A ~11k D2 sessions (10,923-11,517 prompt tokens; order random.Random(0)), each recall
in a FRESH namespace (new header tag + new frame uuids) so nothing is served from the prefix or processor cache:
the first request of every recall carries all its frame bytes (monolithic) or its first slice's bytes (chained).
Reference answer = the session's Part A monolithic letter (majority of 5). Deadlines 5 s and 10 s from the scheduled
arrival. Predicted engine time = computed tokens / the session's Part A monolithic prefill rate (5,307-5,419 tok/s).
Orchestrator policies (episodic calls are never delayed: they are dispatched on schedule, as in E10c; the episodic
arrival schedule is known to the orchestrator, i.e. devices declare their call times; warm C4 traffic passes through):
  P0   pass-through: the monolithic cold request is posted at its arrival (= E10c / E10e).
  P1   EDF admission: cold requests wait in an EDF queue (deadline = arrival + 10 s) and at most one cold request is
       in the engine at a time; episodic calls (deadline arrival + 0.45 s) always precede it.
  P2   P1 + blocking-aware admission: the head cold request is held while any episodic call is due within its
       predicted engine time, unless its slack is exhausted (now + predicted >= deadline) -> dispatched anyway.
  P3n  P1 queue + sliced materialization, n in {1024, 2048} (Part A's chain: slice = cached prefix + next n // 90
       frames, max_tokens 1; the question with the last slice, max_tokens 4): each slice is dispatched only after
       the previous one finished AND, if an episodic call is due within the slice's predicted time, right after that
       call has been dispatched (+5 ms); otherwise immediately.
  P4   P3(2048) (Part A's best n by cost: chain/monolithic 0.990, overhead -0.004 s) + P2's guard per slice: each
       slice is held while any episodic call is due within its predicted time, unless the recall's slack is
       exhausted (now + predicted remaining chain time >= deadline) -> remaining slices back-to-back.
Rows -> results/cost/study_slice1/slice1_live_{requests,metrics,cpu,monitor,slices}_h100nvl.jsonl, meta
slice1_live_run_meta_h100nvl.json. Cold-recall rows carry time-to-answer, letters, slices, computed tokens.
"""
import argparse
import asyncio
import bisect
import itertools
import json
import random
import re
import sys
import threading
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_e10d_blocking as D  # noqa: E402  (logging config + metrics)
import study_slice1_gate as G  # noqa: E402  (Part A session picks + post())

E, X, F = D.E, D.X, D.F
R6, R7 = E.R6, E.R7
OUT = E.REPO / "results/cost/study_slice1"
E.REQ = OUT / "slice1_live_requests_h100nvl.jsonl"
E.MET = OUT / "slice1_live_metrics_h100nvl.jsonl"
E.CPU = OUT / "slice1_live_cpu_h100nvl.jsonl"
E.MON = OUT / "slice1_live_monitor_h100nvl.jsonl"
SLICES = OUT / "slice1_live_slices_h100nvl.jsonl"
X.META_PATH = OUT / "slice1_live_run_meta_h100nvl.json"
X.CURRENT = E.REPO / "logs/slice1_live_current.json"
G.X.META_PATH = X.META_PATH

E.FRACS = (0.25, 0.50, 0.75, 0.90, 0.10, 0.20, 0.30, 0.40, 0.35)     # E10c's level -> seed-index map
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
POLICIES = ("P0", "P1", "P2", "P3_1024", "P3_2048", "P4")
COND = {"C1a": ("KVGPU", 0, 0.05), "C4": ("KVHOST", 8, 0.1), "C0": ("KVGPU", 0, 0.0), "C1b": ("KVGPU", 0, 0.1)}
DEADLINES = (5.0, 10.0)
EP_DEADLINE = E.BUDGET[1]
ALIGN = 0.005
P4_N = 2048
MAX_H = 5.0
# Slack guard (P2 / P4): predicted time to answer = predicted engine time x Part A's max client-latency / engine-time
# ratio (monolithic 1.276-1.321, n 2,048 chain 1.307-1.373 over the 20 ~11k sessions) + 0.25 s margin for load.
# Implementation fix after the smoke run (engine time alone released slack-exhausted recalls ~0.8 s too late).
LAT_FACTOR = {None: 1.321, 2048: 1.373}
SLACK_MARGIN = 0.25
CUR = {"pol": "P0", "cond": "C1a"}
SEQ = itertools.count()
REF = {}          # sess_i -> dict(letter, rate, mono_engine_s, ...)
PICKS = []        # Part A ~11k picks
STATE = {}        # per cell: episodic absolute schedule, prebuilt cold work


def tag(kv, k, r, n, frac):
    return f"SLICE1B_{CUR['pol']}_{CUR['cond']}_N{n}_L{int(round(frac * 100))}"


E.tag = tag


def load_ref():
    res = json.load(open(OUT / "slice1_gate_results.json"))
    for s in res["sessions"]:
        if s["target"] != 11000:
            continue
        REF[s["video_id"]] = dict(letter=Counter(s["mono_letters"]).most_common(1)[0][0],
                                  letters=s["mono_letters"], rate=s["mono_rate_tok_s"], mono_engine_s=s["mono_engine_s"],
                                  prompt_tokens=s["prompt_tokens"])


# ------------------------------------------------------------------------------------------------ cold work
def build_cold(i):
    """Prebuild one cold recall (fresh namespace) for the current policy. Returns a work dict."""
    p = PICKS[i]
    S = STATE["S"]
    sess = S[p["sess_i"]]
    ref = REF[p["video_id"]]
    seq = next(SEQ)
    tg = f"S1B{seq}"
    ns = f"{tg}|{p['sess_i']}"
    hdr = R6.header(tg, 0, p["sess_i"])
    fr = R6.frames(sess, p["qt"])
    pol = CUR["pol"]
    n = 1024 if pol == "P3_1024" else (2048 if pol in ("P3_2048", "P4") else None)
    if n is None:
        data = R7.body7("D2", hdr, sess, p["qt"], p["question"], R7.F.ESC_MAX_TOKENS, "fullu", ns, -1.0)[0]
        parts = [dict(data=data, frames=len(fr), final=True)]
    else:
        k = max(1, n // G.TOK_PER_FRAME)
        chunks = [fr[j:j + k] for j in range(0, len(fr), k)]
        parts, sent = [], -1.0
        for j, ch in enumerate(chunks):
            last = j == len(chunks) - 1
            upto = ch[-1][0]
            data = R7.body7("D2", hdr, sess, upto, p["question"] if last else None,
                            R7.F.ESC_MAX_TOKENS if last else 1, "delta", ns, sent)[0]
            parts.append(dict(data=data, frames=len(ch), final=last))
            sent = upto
    tot_frames = len(fr)
    for x in parts:            # predicted engine time of each part = its new tokens / the session's mono rate
        x["pred_s"] = (x["frames"] * G.TOK_PER_FRAME + (G.HDR_TOK if x is parts[0] else 0)) / ref["rate"]
    return dict(recall_id=tg, sess_i=p["sess_i"], video_id=p["video_id"], qid=p["qid"], n=n, parts=parts,
                ref_letter=ref["letter"], frames=tot_frames, pred_total_s=sum(x["pred_s"] for x in parts),
                expected_prompt_tokens=ref["prompt_tokens"])


def k1_body(q):
    """E.run_cell's make_cold calls this per cold arrival (in a worker thread, before the window)."""
    w = build_cold(q)
    STATE["work"][w["recall_id"]] = w
    return w["recall_id"].encode(), w["frames"]


E.k1_body = k1_body


class RefRows(dict):
    def __missing__(self, key):
        return {"n_input_instruct": REF[PICKS[key[0]]["video_id"]]["prompt_tokens"]}


# ------------------------------------------------------------------------------------------------ orchestrator
def next_ep_due(now):
    """Absolute time of the next episodic call scheduled at or after `now` (None if none)."""
    ts = STATE["ep_abs"]
    i = bisect.bisect_left(ts, now)
    return ts[i] if i < len(ts) else None


async def wait_gap(pred, deadline_start, label):
    """Hold until no episodic call is due within `pred` s, or until `deadline_start` (slack exhausted).
    Returns (held_s, released_by) with released_by in {'gap', 'slack'}."""
    t0 = time.time()
    while True:
        now = time.time()
        if now >= deadline_start:
            return now - t0, "slack"
        nxt = next_ep_due(now)
        if nxt is None or nxt - now > pred:
            return now - t0, "gap"
        # the call at `nxt` blocks: wait until just after it is dispatched, then re-check
        await asyncio.sleep(max(0.0, min(nxt + ALIGN, deadline_start) - time.time()))


async def align_after_due(pred):
    """P3: if an episodic call is due within `pred` s, wait until right after it is dispatched."""
    now = time.time()
    nxt = next_ep_due(now)
    if nxt is not None and nxt - now <= pred:
        await asyncio.sleep(max(0.0, nxt + ALIGN - time.time()))
        return time.time() - now
    return 0.0


async def run_recall(client, w, sched, t0):
    try:
        return await _run_recall(client, w, sched, t0)
    except asyncio.CancelledError:
        return dict(kind="cold_recall", request_id=w["recall_id"], t_sched=round(sched - t0, 3), ttft_s=None,
                    total_s=round(time.time() - sched, 4), letter=None, ref_letter=w["ref_letter"], letter_equal=None,
                    meets_5s=False, meets_10s=False, first_cached=None, gap_max=None, policy=CUR["pol"],
                    error="unfinished after drain cap")


async def _run_recall(client, w, sched, t0):
    pol = CUR["pol"]
    deadline = sched + DEADLINES[-1]
    q = STATE["cold_q"]
    hold_total, released, first_send = 0.0, [], None
    if pol != "P0":                                     # EDF admission, one cold request in the engine at a time
        await q["lock"].acquire()
    adm = time.time()
    try:
        recs = []
        for j, part in enumerate(w["parts"]):
            held, rel = 0.0, None
            if pol == "P2":
                held, rel = await wait_gap(part["pred_s"], deadline - (part["pred_s"] * LAT_FACTOR[None] + SLACK_MARGIN),
                                           w["recall_id"])
            elif pol in ("P3_1024", "P3_2048"):
                held, rel = await align_after_due(part["pred_s"]), "align"
            elif pol == "P4":
                rem = sum(x["pred_s"] for x in w["parts"][j:])
                held, rel = await wait_gap(part["pred_s"], deadline - (rem * LAT_FACTOR[P4_N] + SLACK_MARGIN), w["recall_id"])
            hold_total += held
            released.append(rel)
            r = await G.post(client, part["data"])
            first_send = first_send or r["t_send"]
            m = G.LETTER.search(r["output"] or "")
            r.update(slice=j, n_slices=len(w["parts"]), final=part["final"], held_s=round(held, 4), released_by=rel,
                     pred_s=round(part["pred_s"], 4), body_bytes=len(part["data"]), letter=m.group(1) if m else None,
                     t_send_rel=round(r["t_send"] - sched, 4))
            recs.append(r)
            if r["error"]:
                break
    finally:
        if pol != "P0":
            q["lock"].release()
    end = time.time()
    fin = recs[-1]
    ok = fin["final"] and not fin["error"]
    t_ans = (fin["t_send"] + fin["ttft_s"] - sched) if ok and fin["ttft_s"] is not None else None
    with open(SLICES, "a") as f:
        for r in recs:
            f.write(json.dumps(dict({k: v for k, v in r.items() if k != "output"}, recall_id=w["recall_id"],
                                    cell=STATE["tag"], policy=pol)) + "\n")
    comp = sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in recs)
    gaps = [recs[i - 1]["prompt_tokens"] - (recs[i]["cached_tokens"] or 0) for i in range(1, len(recs))
            if recs[i - 1]["prompt_tokens"] is not None]
    return dict(kind="cold_recall", request_id=w["recall_id"], t_sched=round(sched - t0, 3), t_sched_abs=round(sched, 4),
                dispatch_late_s=round(first_send - sched, 4) if first_send else None,
                admitted_after_s=round(adm - sched, 4), held_s=round(hold_total, 4), released_by=released,
                ttft_s=round(t_ans, 4) if t_ans is not None else None, total_s=round(end - sched, 4),
                prompt_tokens=fin["prompt_tokens"], cached_tokens=fin["cached_tokens"], computed_tokens=comp,
                completion_tokens=fin["completion_tokens"], body_mb=round(sum(len(p["data"]) for p in w["parts"]) / 1e6, 3),
                n_slices=len(w["parts"]), slices_done=len(recs), slice_n=w["n"], gap_max=max(gaps) if gaps else None,
                first_cached=recs[0]["cached_tokens"], letter=fin["letter"] if ok else None, ref_letter=w["ref_letter"],
                letter_equal=(fin["letter"] == w["ref_letter"]) if ok else None,
                meets_5s=t_ans is not None and t_ans <= 5.0, meets_10s=t_ans is not None and t_ans <= 10.0,
                pred_total_s=round(w["pred_total_s"], 4), sess_i=w["sess_i"], video_id=w["video_id"], qid=w["qid"],
                policy=pol, error=fin["error"] or (None if ok else "chain incomplete"),
                expected_prompt_tokens=w["expected_prompt_tokens"])


_dispatch = E.dispatch


async def dispatch(client, kind, times, items, t_w0, t0, tasks, extra):
    if kind == "episodic":
        STATE["ep_abs"] = [t_w0 + t for t in times]
        return await _dispatch(client, kind, times, items, t_w0, t0, tasks, extra)
    assert kind == "cold_recall"
    STATE["cold_q"] = dict(lock=asyncio.Lock())        # asyncio.Lock is FIFO = EDF for equal relative deadlines
    for (rid, body, ex), t in zip(items, times):
        sched = t_w0 + t
        d = sched - time.time()
        if d > 0:
            await asyncio.sleep(d)
        w = STATE["work"][body.decode()]
        tasks.append(asyncio.create_task(run_recall(client, w, sched, t0)))


E.dispatch = dispatch


# ------------------------------------------------------------------------------------------------ server + plan
def start_server(kv, label):
    F.require_idle()
    flags = E.KV[kv] + D.LOGFLAGS
    srv = X.Server("32BI", flags)
    info = srv.start()
    txt = Path(srv.logpath).read_text(errors="replace")
    nd = re.findall(r"non-default args: (.*)", txt)
    nd = nd[-1] if nd else ""
    bad = [k for k in ("long_prefill_token_threshold", "scheduling_policy", "max_num_batched_tokens",
                       "async_scheduling") if k in nd]
    mnbt = re.findall(r"max_num_batched_tokens[=': ]+(\d+)", txt)
    info.update(prefix_caching=True, kv_config=kv, kv_offloading_gib=256 if kv == "KVHOST" else 0, engine="E0",
                log_flags=D.LOGFLAGS, log_max_num_batched_tokens=mnbt[-1] if mnbt else None,
                non_default_args=nd, flags_verified=not bad, host_mem=E.R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    if bad:
        srv.stop()
        raise SystemExit(f"{label}: E0 server shows non-default scheduler args {bad} — STOP")
    E.snapshot(f"server_up_{label}")
    return srv


def plan():
    """[(cond, policy, levels, ladder?)] in the user's run order; P0 first within each condition."""
    out = []
    for cond in ("C1a", "C4"):
        out += [(cond, p, LADDER, True) for p in POLICIES]
    out.append(("C0", "P0", (0.25, 0.40), False))
    out += [("C1b", p, LADDER, True) for p in POLICIES]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="print the plan and exit")
    ap.add_argument("--smoke", action="store_true", help="P0 / P2 / P3_1024 / P4 at C1 r 0.1, 10 %, 60-s window")
    a = ap.parse_args()
    if a.dry:
        for p in plan():
            print(p)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    if a.smoke:
        for nm in ("REQ", "MET", "CPU", "MON"):
            setattr(E, nm, Path(str(getattr(E, nm)).replace("slice1_live_", "slice1_live_smoke_")))
        globals()["SLICES"] = OUT / "slice1_live_smoke_slices_h100nvl.jsonl"
        X.META_PATH = OUT / "slice1_live_smoke_run_meta_h100nvl.json"
        E.DUR, E.DISCARD = 60.0, 10.0
    load_ref()
    S = E.FL.sessions()
    STATE["S"] = S
    PICKS.extend(p for p in G.pick_sessions(S) if p["target"] == 11000)
    assert len(PICKS) == 20 and all(p["video_id"] in REF for p in PICKS), "Part A ~11k picks not reproduced"
    order = list(range(len(PICKS)))
    random.Random(0).shuffle(order)
    E.R1ROWS = RefRows()
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']} — STOP")
    import torch
    import vllm
    m = X.meta_load()
    t_start = m.setdefault("t_start", time.time())
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, log_flags=D.LOGFLAGS, peak=E.PEAK, ladder=LADDER,
                      seed_index=list(E.FRACS), budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD,
                      drain_cap=E.DRAIN_CAP, deadlines=DEADLINES, align_s=ALIGN, p4_n=P4_N,
                      tok_per_frame=G.TOK_PER_FRAME, smoke=a.smoke,
                      lat_factor={str(k): v for k, v in LAT_FACTOR.items()}, slack_margin=SLACK_MARGIN)
    m["plan"] = plan()
    m["conditions"] = COND
    m["cold_sessions"] = [dict({k: v for k, v in p.items() if k != "question"}, ref=REF[p["video_id"]]) for p in PICKS]
    m["cold_order"] = order
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    work = ([("C1b", p, (0.10,), False) for p in ("P0", "P2", "P3_1024", "P4")] if a.smoke else plan())
    try:
        R6.preencode("D2", S)
        for cond, pol, levels, ladder in work:
            CUR.update(pol=pol, cond=cond)
            kv, k, r = COND[cond]
            for f in levels:
                tg = tag(kv, k, r, 1, f)
                if X.is_done(tg):
                    if ladder and not X.meta_load()["experiments"][tg]["summary"]["meets_budget"]:
                        break
                    continue
                el = (time.time() - t_start) / 3600
                if el > MAX_H:
                    raise SystemExit(f"{el:.2f} h elapsed > {MAX_H} h before {tg} — STOP and ask")
                STATE.update(tag=tg, work={}, ep_abs=[])
                srv = start_server(kv, tg)
                try:
                    s = asyncio.run(E.run_cell(kv, k, r, 1, f, srv.proc.pid, E.Episodic(1), dict(order=order, i=0)))
                finally:
                    srv.stop()
                rows = [json.loads(x) for x in open(E.REQ)]
                cold = [x for x in rows if x.get("cell") == tg and x["kind"] == "cold_recall" and x["in_window"]]
                tta = [x["ttft_s"] for x in cold]
                cs = dict(n=len(cold), meets_10s=sum(x["meets_10s"] for x in cold),
                          meets_5s=sum(x["meets_5s"] for x in cold),
                          letters_equal=sum(bool(x["letter_equal"]) for x in cold),
                          first_cached_max=max((x["first_cached"] or 0 for x in cold), default=None),
                          gap_max=max((x["gap_max"] or 0 for x in cold), default=None),
                          t_answer=tta)
                m = X.meta_load()
                m["experiments"][tg].update(policy=pol, cond=cond, cold=cs)
                X.meta_save(m)
                X.log(f"{tg}: cold {cs['n']} in window, meet 10 s {cs['meets_10s']}, 5 s {cs['meets_5s']}, letters "
                      f"{cs['letters_equal']}, first cached max {cs['first_cached_max']}, gap max {cs['gap_max']}")
                if E.VOID.is_set():
                    raise SystemExit("run VOID — STOP")
                if cs["first_cached_max"] is not None and cs["first_cached_max"] > 16:
                    raise SystemExit(f"{tg}: a cold recall's first request was served from cache — STOP")
                if cs["gap_max"] is not None and cs["gap_max"] > 32:
                    raise SystemExit(f"{tg}: cached tokens do not equal the previous prefix (gap {cs['gap_max']}) — STOP")
                if ladder and not s["meets_budget"]:
                    break
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_slice1_live.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
