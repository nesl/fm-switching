#!/usr/bin/env python3
"""StudySLICE1 Part D (live mixed test: one coordinated background lane, and cadence-only knowledge). EXCLUSIVE (vLLM
venv; h100nvl GPU 2). Pre-registered in research/EXPERIMENTS.md (StudySLICE1 row, Part D extension) and
reports/study_slice1.md section 17, before any Part D run.

D1: does one background lane (P6: at most ONE background unit in flight; queue escalations > cold slices by EDF > appends
by due time; release only when the lane is empty and now + EWMA-predicted service < next predicted episodic arrival -
margin; slack guard releases one unit, never a chain; append coalescing; escalations absorb their session's queued
append) remove bunching and restore capacity?
D2: how much survives when the orchestrator knows only stream cadences? D-a = Part C's Poisson schedule, known exactly
(oracle, as in B / C). D-b = S streams at a 0.5-s cadence, random phase, per-call half-normal jitter (p90 0.044 s, an
ASSUMPTION = one E9b setting (ii) RTT); the orchestrator predicts each stream's next call at its last observed arrival +
0.5 s and uses margin = jitter p90.
D3: live baselines under D-b.

Harness: Part C's study_slice1_partc (warm post with letters, server / sanity), Part B's study_slice1_live (cold
sessions, fresh namespaces, chains, P0-P4 cold logic) and study_e10b_mixed.run_cell, through the existing default-off
WARM_DEVICE hook and module monkeypatch points (E.dispatch, L.run_recall, L.next_ep_due, L.align_after_due,
E.FRACS). No shared file is changed; Part B / C defaults are untouched.
Rows -> results/cost/study_slice1/slice1_partd_{requests,slices,warm,lane,metrics,cpu,monitor}_h100nvl.jsonl, meta
slice1_partd_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import json
import math
import random
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_slice1_partc as C  # noqa: E402  (-> study_slice1_live as L -> study_e10b_mixed as E)

L, E, X, F, G = C.L, C.E, C.X, C.F, C.G
R6, R7 = C.R6, C.R7
OUT = C.OUT

LADDER_A = (0.10, 0.20, 0.25, 0.30, 0.40)
STREAMS = (1, 2, 3, 4, 5)
CADENCE = 0.5
FRAC_B = {s: round(s / CADENCE / E.PEAK[1], 6) for s in STREAMS}          # 2S / 15.1
E.FRACS = tuple(E.FRACS) + tuple(FRAC_B[s] for s in STREAMS)              # new seed indices 9..13 for D-b rungs
COND = {"C1a": ("KVGPU", 0, 0.05), "C4a": ("KVHOST", 8, 0.05), "C4": ("KVHOST", 8, 0.1),
        "C1b": ("KVGPU", 0, 0.1), "C2": ("KVHOST", 8, 0.0), "C0": ("KVGPU", 0, 0.0)}
COND_IDX = {c: i for i, c in enumerate(COND)}
# policy -> (cold build label, cold run label, slice n, lane mode)   lane mode: None | "single" | "unlimited"
POLD = {"P0": ("P0", "P0", None, None), "P2": ("P2", "P2", None, None), "P3_1024": ("P3_1024", "P3_1024", 1024, None),
        "P4": ("P4", "P4", 2048, None), "P4_1024": ("P3_1024", "P4", 1024, None),
        "P6": ("P4", None, 2048, "single"), "P6_1024": ("P3_1024", None, 1024, "single"),
        "P6_nolane": ("P4", None, 2048, "unlimited"), "P6b": ("P4", None, 2048, "single")}
P6B = {"P6b"}                        # P6 + deadline guards + stream-ended rule + catch-up slicing (report section 17a)
DEADLINE_ESC = 5.0
APP_CADENCE = 10.0                   # warm appends: every 10 s of session time at 1x real time
L.LAT_FACTOR[1024] = 1.467
ENG_FLAGS = {"E0": [], "T1": ["--long-prefill-token-threshold", "1024"]}
JIT = {"b": (0.044, 0.044), "s0": (0.0, 0.005), "s20": (0.20, 0.20)}   # mode -> (jitter p90, margin)
MARGIN_A = 0.005
ALIGN = L.ALIGN
EWMA_ALPHA = 0.3
INIT = {"cold2048_link": 0.478, "cold2048_final": 0.367, "cold1024_link": 0.285, "cold1024_final": 0.346,
        "append_le5": 0.288, "append_6to10": 0.484, "append_gt10": 0.660, "esc_le5": 0.311, "esc_gt5": 0.539}
SLACK_FACTOR, SLACK_MARGIN = 1.373, 0.25
DRIFT_REF, DRIFT_TOL = 0.544, 0.25
GUARD_H = 8.0
BLOCK = 545
CFG = dict(mode="a", eng="E0", pol="P0", cond="C4a", margin=MARGIN_A, jit=0.0, lane=None, p6b=False)
ST = {}          # per cell runtime state (lane, streams, plan, sessions)


def set_paths(prefix):
    C.set_paths(prefix)
    ST["lane_file"] = OUT / f"{prefix}_lane_h100nvl.jsonl"
    X.CURRENT = E.REPO / "logs/slice1_partd_current.json"


set_paths("slice1_partd")


def lev_label(frac):
    if CFG["mode"] == "a":
        return f"L{int(round(frac * 100))}"
    return f"S{[s for s, f in FRAC_B.items() if f == frac][0]}"


def tag(kv, k, r, n, frac):
    return f"SLICE1D_{CFG['mode']}_{CFG['eng']}_{CFG['pol']}_{CFG['cond']}_{lev_label(frac)}"


E.tag = tag


def k1_body(q):
    build, run, _, _ = POLD[CFG["pol"]]
    L.CUR["pol"] = build
    try:
        return L.k1_body(q)
    finally:
        L.CUR["pol"] = run or "P4"


E.k1_body = k1_body


# ------------------------------------------------------------------------------------------------ D-b streams
class StreamEp:
    """S episodic N = 1 streams at a 0.5-s cadence; contiguous D14 manifest block per stream; per-call jitter."""

    def __init__(self, S, jit_p90, seed):
        self.S, self.jit, self.seed = S, jit_p90, seed
        self.reqs = E.Episodic(1).reqs

    def take(self, _m):
        rng = np.random.default_rng(self.seed)
        sigma = self.jit / 1.6448536269514722 if self.jit > 0 else 0.0     # half-normal p90 = sigma * z(0.95)
        phases = rng.uniform(0.0, CADENCE, size=self.S)
        plan = []
        for s in range(self.S):
            blk = self.reqs[s * BLOCK:(s + 1) * BLOCK]
            k = 0
            while True:
                nom = phases[s] + k * CADENCE
                if nom >= E.DUR:
                    break
                if k >= len(blk):
                    raise SystemExit("stream block exhausted: STOP")
                j = float(abs(rng.normal(0.0, sigma))) if sigma > 0 else 0.0
                r = blk[k]
                b, _, _ = E.D3.body(r, "32BI")
                b = dict(b, stream=True, stream_options={"include_usage": True}, **E.GEN_EP)
                for kk in ("logprobs", "top_logprobs"):
                    b.pop(kk, None)
                plan.append(dict(rid=r["request_id"], body=json.dumps(b).encode(), stream=s, call_k=k,
                                 nominal=round(float(nom), 4), jitter=round(j, 4), arrival=float(nom + j),
                                 clip=r["file_name"], t_index=r["t"]))
                k += 1
        plan.sort(key=lambda x: x["arrival"])
        ST["plan"] = plan
        ST["phases"] = [round(float(p), 4) for p in phases]
        return [(x["rid"], x["body"]) for x in plan]


def stream_next(s, now):
    a = ST["last"].get(s)
    if a is None:
        return now                       # not yet seen: due now
    p = a + CADENCE
    m = CFG["margin"]
    missed = 0
    while now > p + m:                   # overdue beyond the margin: move on one period
        p += CADENCE
        missed += 1
    if CFG["p6b"] and missed >= 2:       # P6b: 2 consecutive missed calls -> stream treated as ended
        return math.inf
    return now if p <= now else p


def pred_next_point(now):
    """D-b: predicted next episodic arrival (point estimate) from past arrivals only. D-a: the exact schedule."""
    if CFG["mode"] == "a":
        nxt = ORIG["next_ep_due"](now)
        return nxt if nxt is not None else math.inf
    if not ST.get("streams_on"):
        return math.inf
    return min(stream_next(s, now) for s in range(ST["S"]))


def next_ep_due_b(now):
    """For P2 / P4 under D-b: earliest plausible arrival = prediction - margin (never before now)."""
    p = pred_next_point(now)
    return None if p == math.inf else max(now, p - CFG["margin"])


async def align_after_due_b(pred):
    """P3 under D-b: if a call is predicted within `pred` (+ margin), wait until it is observed (or the margin
    passes), then 5 ms."""
    t0 = time.time()
    nxt = pred_next_point(t0)
    if nxt - CFG["margin"] - t0 > pred:
        return 0.0
    n0 = len(ST["arrivals"])
    while time.time() < nxt + CFG["margin"]:
        if any(a >= nxt - CFG["margin"] for a in ST["arrivals"][n0:]):
            break
        await asyncio.sleep(0.002)
    await asyncio.sleep(ALIGN)
    return time.time() - t0


ORIG = dict(next_ep_due=L.next_ep_due, align_after_due=L.align_after_due, run_recall=L.run_recall,
            dispatch=E.dispatch)


async def dispatch(client, kind, times, items, t_w0, t0, tasks, extra):
    get_lane()
    if kind == "episodic":
        if CFG["mode"] == "a":
            return await ORIG["dispatch"](client, kind, times, items, t_w0, t0, tasks, extra)
        L.STATE["ep_abs"] = []
        ST.update(last={}, arrivals=[], streams_on=True, t_w0=t_w0)
        for x in ST["plan"]:
            sched = t_w0 + x["arrival"]
            d = sched - time.time()
            if d > 0:
                await asyncio.sleep(d)
            s = x["stream"]
            prev = ST["last"].get(s)
            ex = dict(stream=s, call_k=x["call_k"], nominal_s=x["nominal"], jitter_s=x["jitter"],
                      arrival_s=round(x["arrival"], 4),
                      predicted_arrival_s=round(prev + CADENCE - t_w0, 4) if prev is not None else None,
                      clip=x["clip"], t_index=x["t_index"])
            ST["last"][s] = sched                 # observed only now, when the call reaches the replica
            ST["arrivals"].append(sched)
            tasks.append(asyncio.create_task(E.timed_post(client, kind, x["rid"], x["body"], sched, t0,
                                                          dict(extra, **ex))))
            if ST.get("lane"):
                ST["lane"].changed.set()
        return
    return await ORIG["dispatch"](client, kind, times, items, t_w0, t0, tasks, extra)


E.dispatch = dispatch


# ------------------------------------------------------------------------------------------------ the lane (P6)
class Unit:
    __slots__ = ("kind", "prio", "bucket_fn", "fn", "deadline", "rem_fn", "t_enq", "t_rel", "t_fin", "reason",
                 "pred", "meas", "done", "result", "dropped", "on_release", "info", "qlen_at_rel", "guard_fn")

    def __init__(self, kind, prio, bucket_fn, fn, deadline=None, rem_fn=None, on_release=None, info=None):
        self.kind, self.prio, self.bucket_fn, self.fn = kind, prio, bucket_fn, fn
        self.deadline, self.rem_fn, self.on_release, self.info = deadline, rem_fn, on_release, info or {}
        self.t_enq = time.time()
        self.t_rel = self.t_fin = self.reason = self.pred = self.meas = self.result = self.qlen_at_rel = None
        self.dropped = None
        self.guard_fn = None             # P6b: per-unit deadline guard (absolute time) or None
        self.done = asyncio.Event()


class Lane:
    def __init__(self, single):
        self.single = single
        self.q = []
        self.inflight = 0
        self.max_inflight = 0
        self.violations = 0
        self.changed = asyncio.Event()
        self.ewma = dict(INIT)
        self.units = []
        self.qlog = []
        self.busy = []                    # (t_rel, t_fin) intervals
        self.task = asyncio.create_task(self.loop())

    def _ql(self):
        self.qlog.append((round(time.time(), 4), len(self.q), self.inflight))

    def put(self, u):
        self.q.append(u)
        self.units.append(u)
        self._ql()
        self.changed.set()

    def drop(self, u, why):
        if u in self.q:
            self.q.remove(u)
            u.dropped = why
            u.t_rel = time.time()
            u.done.set()
            self._ql()
            self.changed.set()
            return True
        return False

    def head(self):
        return min(self.q, key=lambda u: u.prio)

    def rem_pred(self, u):
        return sum(self.ewma[b] for b in u.rem_fn())

    async def loop(self):
        while True:
            if not self.q or (self.single and self.inflight):
                await self._wait(None)
                continue
            u = self.head()
            now = time.time()
            b = u.bucket_fn()
            pred = u.info["pred_fn"]() if u.info.get("pred_fn") else self.ewma[b]
            nxt = pred_next_point(now)
            m = CFG["margin"]
            gap = now + pred < nxt - m
            slack, t_slack = False, math.inf
            if u.kind == "cold":
                t_slack = u.deadline - (self.rem_pred(u) * SLACK_FACTOR + SLACK_MARGIN)
                slack = now >= t_slack
            elif u.guard_fn is not None:     # P6b deadline guard (escalation / catch-up / append)
                t_slack = u.guard_fn()
                slack = now >= t_slack
            if gap or slack:
                self.release(u, "gap" if gap else ("slack" if u.kind == "cold" else "deadline"), b, pred)
                continue
            wake = min(t_slack, nxt + ALIGN if nxt != math.inf else math.inf)
            await self._wait(max(0.001, wake - now) if wake != math.inf else None)

    async def _wait(self, timeout):
        self.changed.clear()
        try:
            await asyncio.wait_for(self.changed.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    def release(self, u, reason, bucket, pred):
        self.q.remove(u)
        u.t_rel, u.reason, u.pred, u.qlen_at_rel = time.time(), reason, pred, len(self.q)
        u.info["bucket"] = bucket
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        if self.single and self.inflight > 1:
            self.violations += 1
        if u.on_release:
            u.on_release(u)
        self._ql()
        asyncio.create_task(self.run(u))

    async def run(self, u):
        try:
            u.result = await u.fn()
        except asyncio.CancelledError:
            u.result = None
            raise
        except Exception as e:  # noqa: BLE001
            u.result = dict(error=f"{type(e).__name__}: {e}")
        finally:
            u.t_fin = time.time()
            u.meas = u.t_fin - u.t_rel
            b = u.info["bucket"]
            if u.result and not (isinstance(u.result, dict) and u.result.get("error")):
                self.ewma[b] = EWMA_ALPHA * u.meas + (1 - EWMA_ALPHA) * self.ewma[b]
            u.info["ewma_after"] = round(self.ewma[b], 4)
            self.busy.append((u.t_rel, u.t_fin))
            self.inflight -= 1
            self._ql()
            u.done.set()
            self.changed.set()


def get_lane():
    if CFG["lane"] and ST.get("lane") is None:
        ST["lane"] = Lane(CFG["lane"] == "single")
    return ST.get("lane")


# ------------------------------------------------------------------------------------------------ cold via the lane
def cold_bucket(n, final):
    return f"cold{n}_{'final' if final else 'link'}"


async def run_recall_lane(client, w, sched, t0):
    try:
        return await _run_recall_lane(client, w, sched, t0)
    except asyncio.CancelledError:
        return dict(kind="cold_recall", request_id=w["recall_id"], t_sched=round(sched - t0, 3), ttft_s=None,
                    total_s=round(time.time() - sched, 4), letter=None, ref_letter=w["ref_letter"], letter_equal=None,
                    meets_5s=False, meets_10s=False, first_cached=None, gap_max=None, policy=CFG["pol"],
                    error="unfinished after drain cap")


async def _run_recall_lane(client, w, sched, t0):
    lane = get_lane()
    deadline = sched + L.DEADLINES[-1]
    parts = w["parts"]
    n = w["n"]
    recs, hold_total, released, first_send = [], 0.0, [], None
    for j, part in enumerate(parts):
        bk = cold_bucket(n, part["final"])
        rem = [cold_bucket(n, p["final"]) for p in parts[j:]]
        data = part["data"]
        u = Unit("cold", (1, deadline), (lambda bk=bk: bk), (lambda data=data: G.post(client, data)), deadline=deadline,
                 rem_fn=(lambda rem=rem: rem), info=dict(recall_id=w["recall_id"], slice=j))
        lane.put(u)
        await u.done.wait()
        r = u.result or dict(error="no result", output="", t_send=u.t_rel, ttft_s=None, prompt_tokens=None,
                             cached_tokens=None, completion_tokens=None, latency_s=None)
        held = u.t_rel - u.t_enq
        hold_total += held
        released.append(u.reason)
        first_send = first_send or r.get("t_send")
        m = G.LETTER.search(r.get("output") or "")
        r.update(slice=j, n_slices=len(parts), final=part["final"], held_s=round(held, 4), released_by=u.reason,
                 pred_s=round(u.pred, 4), body_bytes=len(data), letter=m.group(1) if m else None,
                 t_send_rel=round((r.get("t_send") or u.t_rel) - sched, 4), lane_qlen=u.qlen_at_rel)
        recs.append(r)
        if r.get("error"):
            break
    end = time.time()
    fin = recs[-1]
    ok = fin["final"] and not fin.get("error")
    t_ans = (fin["t_send"] + fin["ttft_s"] - sched) if ok and fin.get("ttft_s") is not None else None
    with open(L.SLICES, "a") as f:
        for r in recs:
            f.write(json.dumps(dict({k: v for k, v in r.items() if k != "output"}, recall_id=w["recall_id"],
                                    cell=L.STATE["tag"], policy=CFG["pol"])) + "\n")
    comp = sum((r["prompt_tokens"] or 0) - (r["cached_tokens"] or 0) for r in recs if r.get("prompt_tokens"))
    gaps = [recs[i - 1]["prompt_tokens"] - (recs[i]["cached_tokens"] or 0) for i in range(1, len(recs))
            if recs[i - 1].get("prompt_tokens") is not None]
    return dict(kind="cold_recall", request_id=w["recall_id"], t_sched=round(sched - t0, 3), t_sched_abs=round(sched, 4),
                dispatch_late_s=round(first_send - sched, 4) if first_send else None,
                admitted_after_s=round(first_send - sched, 4) if first_send else None, held_s=round(hold_total, 4),
                released_by=released, ttft_s=round(t_ans, 4) if t_ans is not None else None,
                total_s=round(end - sched, 4), prompt_tokens=fin.get("prompt_tokens"),
                cached_tokens=fin.get("cached_tokens"), computed_tokens=comp,
                completion_tokens=fin.get("completion_tokens"),
                body_mb=round(sum(len(p["data"]) for p in parts) / 1e6, 3), n_slices=len(parts), slices_done=len(recs),
                slice_n=n, gap_max=max(gaps) if gaps else None, first_cached=recs[0].get("cached_tokens"),
                letter=fin["letter"] if ok else None, ref_letter=w["ref_letter"],
                letter_equal=(fin["letter"] == w["ref_letter"]) if ok else None,
                meets_5s=t_ans is not None and t_ans <= 5.0, meets_10s=t_ans is not None and t_ans <= 10.0,
                pred_total_s=round(w["pred_total_s"], 4), sess_i=w["sess_i"], video_id=w["video_id"], qid=w["qid"],
                policy=CFG["pol"], error=fin.get("error") or (None if ok else "chain incomplete"),
                expected_prompt_tokens=w["expected_prompt_tokens"])


# ------------------------------------------------------------------------------------------------ warm via the lane
def wsess(dev, s_i):
    return ST["wsess"].setdefault((dev, s_i), dict(queued_append=None, disp_upto=-1.0, last_ev=None))


def app_bucket(fr):
    return "append_le5" if fr <= 5 else ("append_6to10" if fr <= 10 else "append_gt10")


def esc_bucket(fr):
    return "esc_le5" if fr <= 5 else "esc_gt5"


async def _warm_post(cell, e):
    S = wsess(e["device"], e["session"])
    prev, ev = S["last_ev"], asyncio.Event()
    S["last_ev"] = ev
    try:
        if prev is not None and not prev.is_set():          # only possible without the single lane
            try:
                await asyncio.wait_for(prev.wait(), 5.0)
            except asyncio.TimeoutError:
                e["order_wait_timeout"] = True
        q = e["q"]
        return await C.post_c(cell, e["kind"], e["device"], e["session"], e["sess"], e["session_t"],
                              question=q and q["text"], qid=q and q["qid"], t_sched=e["wall"], on_submit=ev)
    finally:
        ev.set()


def warm_unit(cell, e, prio=None, fixed_bucket=None):
    S = wsess(e["device"], e["session"])
    kind = e["kind"]

    def bucket():
        fr = C.n_frames(e["sess"], S["disp_upto"], e["session_t"])
        e["new_frames_at_eval"] = fr
        if fixed_bucket:
            return fixed_bucket
        return app_bucket(fr) if kind == "append" else esc_bucket(fr)

    def on_release(u):
        S["disp_upto"] = max(S["disp_upto"], e["session_t"])
        if kind == "escalation":
            qa = S["queued_append"]
            if qa is not None and qa.info["e"]["session_t"] <= e["session_t"] and get_lane().drop(qa, "absorbed"):
                qa.info["e"]["absorbed"] = True
                S["queued_append"] = None
        elif S["queued_append"] is u:
            S["queued_append"] = None

    if prio is None:
        prio = (0, e["wall"]) if kind == "escalation" else (2, e["wall"])
    u = Unit("escalation" if kind == "escalation" else "append", prio, bucket, lambda: _warm_post(cell, e),
             on_release=on_release, info=dict(e=e, fixed_bucket=fixed_bucket, catchup=bool(e.get("catchup"))))
    e["unit"] = u
    return u


async def _await_unit(u):
    await u.done.wait()


def on_append_lane(cell, dev, s_i, sess, st, wall):
    S = wsess(dev, s_i)
    lane = get_lane()
    old = S["queued_append"]
    if old is not None and lane.drop(old, "coalesced"):
        old.info["e"]["coalesced"] = True
    e = dict(kind="append", device=dev, session=s_i, sess=sess, session_t=st, wall=wall, q=None, coalesced=False,
             absorbed=False)
    ST["wlog"].append(e)
    u = warm_unit(cell, e)
    if CFG["p6b"]:                       # P6b append guard: finish before the next append would supersede it
        u.guard_fn = lambda: wall + APP_CADENCE - (lane.ewma[u.bucket_fn()] * SLACK_FACTOR + SLACK_MARGIN)
    S["queued_append"] = u
    lane.put(u)
    C.track(cell, _await_unit(u))


def gap_estimate(now):
    """P6b catch-up sizing: median predicted inter-arrival gap over the next 2 s, minus the margin."""
    if CFG["mode"] == "a":
        ts = [t for t in L.STATE.get("ep_abs") or [] if now <= t <= now + 2.0]
    else:
        ts = []
        for s in range(ST.get("S", 0)):
            p = stream_next(s, now) if ST.get("streams_on") else math.inf
            while p <= now + 2.0:
                ts.append(p)
                p += CADENCE
        ts.sort()
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    return (float(np.median(gaps)) if gaps else 2.0) - CFG["margin"]


def catchup_pred(n, lane):
    """Predicted service of an n-frame catch-up append: Part C fit scaled by the current append EWMA / 0.288."""
    return (C.FIT["a"] + C.FIT["b"] * (C.FIT["app"][0] + C.FIT["app"][1] * n)) * lane.ewma["append_le5"] / INIT["append_le5"]


def catchup_frames_per_unit(gap, lane):
    """Largest frame count whose predicted append service fits `gap` (Part C fit scaled by the append EWMA)."""
    scale = lane.ewma["append_le5"] / INIT["append_le5"]
    f = ((gap / scale - C.FIT["a"]) / C.FIT["b"] - C.FIT["app"][0]) / C.FIT["app"][1]
    return max(1, int(math.floor(f)))


def on_escalation_lane(cell, dev, s_i, sess, st, q, wall):
    S = wsess(dev, s_i)
    lane = get_lane()
    stale = C.n_frames(sess, S["disp_upto"], st)
    e = dict(kind="escalation", device=dev, session=s_i, sess=sess, session_t=st, wall=wall, q=q,
             stale_frames=stale, pending_append_at_arrival=S["queued_append"] is not None,
             pred_before_s=round(lane.ewma[esc_bucket(stale)], 4), catchup_units=0, catchup_frames=0)
    ST["wlog"].append(e)
    if not CFG["p6b"]:
        u = warm_unit(cell, e)
        lane.put(u)
        C.track(cell, _await_unit(u))
        return
    chain = []
    fr = [t for t, _ in R6.frames(sess, st) if t > S["disp_upto"] + 1e-6]
    if fr:                               # P6b catch-up slicing: pending frames first, as gap-sized append units
        qa = S["queued_append"]
        if qa is not None and lane.drop(qa, "absorbed_catchup"):
            qa.info["e"]["absorbed"] = True
            qa.info["e"]["absorbed_catchup"] = True
            S["queued_append"] = None
        gap = gap_estimate(time.time())
        f = catchup_frames_per_unit(gap, lane)
        chunks = [fr[i:i + f] for i in range(0, len(fr), f)]
        for i, ch in enumerate(chunks):
            ce = dict(kind="append", device=dev, session=s_i, sess=sess, session_t=ch[-1], wall=wall, q=None,
                      coalesced=False, absorbed=False, catchup=True, catchup_for=q["qid"], catchup_index=i,
                      catchup_n_frames=len(ch))
            ST["wlog"].append(ce)
            cu = warm_unit(cell, ce, prio=(0, wall, i), fixed_bucket=app_bucket(len(ch)))
            cu.info["pred_fn"] = (lambda n=len(ch): catchup_pred(n, lane))     # the same prediction it was sized by
            chain.append(cu)
        e.update(catchup_units=len(chunks), catchup_frames=len(fr), gap_est_s=round(gap, 4), frames_per_unit=f)
    eu = warm_unit(cell, e, prio=(0, wall, len(chain)), fixed_bucket="esc_le5" if chain else None)
    chain.append(eu)

    def guard():                         # escalation deadline guard over its remaining chain (catch-ups + itself)
        rem = sum(x.info["pred_fn"]() if x.info.get("pred_fn") else lane.ewma[x.info["fixed_bucket"] or x.bucket_fn()]
                  for x in chain if x.t_rel is None)
        return wall + DEADLINE_ESC - (rem * SLACK_FACTOR + SLACK_MARGIN)
    for x in chain:
        x.guard_fn = guard
        lane.put(x)
        C.track(cell, _await_unit(x))


async def device_lane(cell, dev, plan_d, offset, window_end):
    """R6.device's event loop (as Part C's device_c) handing each warm event to the lane."""
    s_i, sess, start_s = 0, plan_d[0], offset
    t_start = time.time()
    cad = cell.spec["cadence"]
    wsess(dev, 0)["disp_upto"] = cell.sent.get((dev, 0), -1.0)
    ST["t0"] = cell.t0
    while True:
        ev = []
        if not cell.spec["lazy"]:
            k0 = int(start_s // cad) + 1
            ev += [(k * cad, "append", None) for k in range(k0, int(sess["duration"] // cad) + 1)]
        ev += [(q["qt"], "escalation", q) for q in sess["questions"] if q["qt"] > start_s + 1e-6]
        ev.sort(key=lambda e: (e[0], e[1] != "append"))
        for st, kind, q in ev:
            wall = t_start + (st - start_s)
            if wall > window_end:
                return
            await asyncio.sleep(max(0.0, wall - time.time()))
            if kind == "append":
                on_append_lane(cell, dev, s_i, sess, st, wall)
            else:
                on_escalation_lane(cell, dev, s_i, sess, st, q, wall)
        t_start = t_start + (sess["duration"] - start_s)
        s_i += 1
        if s_i >= len(plan_d) or t_start > window_end:
            return
        sess, start_s = plan_d[s_i], 0.0
        await asyncio.sleep(max(0.0, t_start - time.time()))


def lane_warm_rows(tg, w0_rel):
    out = []
    t0 = ST.get("t0")
    for e in ST["wlog"]:
        u = e.get("unit")
        r = (u.result if u is not None and isinstance(u.result, dict) else None) or {}
        ts = e["wall"] - t0
        rel = (u.dropped if u is not None and u.dropped else (u.reason if u is not None else None))
        row = dict(cell=tg, kind="recall_" + e["kind"], device=e["device"], session=e["session"], session_t=e["session_t"],
                   question_id=e["q"] and e["q"]["qid"], t_sched=round(ts, 3),
                   t_dispatch=round(u.t_rel - t0, 3) if u is not None and u.t_rel and not u.dropped else None,
                   held_s=round(u.t_rel - e["wall"], 4) if u is not None and u.t_rel else None, release=rel,
                   coalesced=bool(e.get("coalesced")), absorbed=bool(e.get("absorbed")),
                   pred_s=round(u.pred, 4) if u is not None and u.pred is not None else None,
                   measured_s=round(u.meas, 4) if u is not None and u.meas is not None else None,
                   bucket=u.info.get("bucket") if u is not None else None,
                   new_frames_pred=e.get("new_frames_at_eval"), stale_frames=e.get("stale_frames"),
                   order_wait_timeout=e.get("order_wait_timeout", False), in_window=ts - w0_rel >= E.DISCARD,
                   catchup=bool(e.get("catchup")), catchup_for=e.get("catchup_for"), catchup_units=e.get("catchup_units"),
                   catchup_frames=e.get("catchup_frames"), frames_per_unit=e.get("frames_per_unit"),
                   gap_est_s=e.get("gap_est_s"), pred_before_s=e.get("pred_before_s"),
                   absorbed_catchup=bool(e.get("absorbed_catchup")))
        row.update({k: r.get(k) for k in ("t_submit", "ttft_s", "latency_s", "t_end", "prompt_tokens", "cached_tokens",
                                          "n_frames", "n_new_frames", "letter", "output", "fallback", "error")})
        row["computed_tokens"] = (r["prompt_tokens"] - (r["cached_tokens"] or 0)) if r.get("prompt_tokens") else None
        row["t_answer_s"] = (round(r["t_submit"] + r["ttft_s"] - ts, 4)
                             if r.get("ttft_s") is not None and r.get("t_submit") is not None else None)
        out.append(row)
    return out


def lane_rows(tg, t0, w0_abs, w1_abs):
    lane = ST.get("lane")
    if lane is None:
        return []
    rows = []
    for u in lane.units:
        rows.append(dict(cell=tg, type="unit", kind=u.kind, bucket=u.info.get("bucket"),
                         t_enq=round(u.t_enq - t0, 4), t_rel=round(u.t_rel - t0, 4) if u.t_rel else None,
                         t_fin=round(u.t_fin - t0, 4) if u.t_fin else None,
                         hold_s=round(u.t_rel - u.t_enq, 4) if u.t_rel else None, reason=u.reason, dropped=u.dropped,
                         pred_s=round(u.pred, 4) if u.pred is not None else None,
                         meas_s=round(u.meas, 4) if u.meas is not None else None,
                         ewma_after=u.info.get("ewma_after"), qlen_at_rel=u.qlen_at_rel,
                         in_window=u.t_enq >= w0_abs + E.DISCARD and u.t_enq <= w1_abs,
                         recall_id=u.info.get("recall_id"), slice=u.info.get("slice"),
                         catchup=bool(u.info.get("catchup"))))
    busy_w = sum(max(0.0, min(b, w1_abs) - max(a, w0_abs + E.DISCARD)) for a, b in lane.busy)
    occ = busy_w / max(1e-9, (w1_abs - w0_abs - E.DISCARD))
    rows.append(dict(cell=tg, type="summary", single=lane.single, max_inflight=lane.max_inflight,
                     violations=lane.violations, occupancy_window=round(occ, 4),
                     units=len(lane.units), dropped=sum(bool(u.dropped) for u in lane.units),
                     ewma_final={k: round(v, 4) for k, v in lane.ewma.items()},
                     qlog=[(round(t - t0, 3), q, i) for t, q, i in lane.qlog]))
    return rows


# ------------------------------------------------------------------------------------------------ server
def start_server(kv, label, eng):
    F.require_idle()
    flags = E.KV[kv] + L.D.LOGFLAGS + ENG_FLAGS[eng]
    srv = X.Server("32BI", flags)
    info = srv.start()
    txt = Path(srv.logpath).read_text(errors="replace")
    nd = re.findall(r"non-default args: (.*)", txt)
    nd = nd[-1] if nd else ""
    keys = ("long_prefill_token_threshold", "scheduling_policy", "max_num_batched_tokens", "async_scheduling")
    present = [k for k in keys if k in nd]
    if eng == "E0":
        ok = not present
    else:
        ok = present == ["long_prefill_token_threshold"] and re.search(r"'long_prefill_token_threshold': 1024\b", nd)
    mnbt = re.findall(r"max_num_batched_tokens[=': ]+(\d+)", txt)
    info.update(prefix_caching=True, kv_config=kv, kv_offloading_gib=256 if kv == "KVHOST" else 0, engine=eng,
                log_flags=L.D.LOGFLAGS, engine_flags=ENG_FLAGS[eng],
                log_max_num_batched_tokens=mnbt[-1] if mnbt else None, non_default_args=nd,
                flags_verified=bool(ok), host_mem=E.R5.host_mem(srv.proc.pid))
    m = X.meta_load()
    m.setdefault("servers", []).append(dict(label=label, started=F.now(), flags=flags, **info))
    X.meta_save(m)
    if not ok:
        srv.stop()
        raise SystemExit(f"{label}: server scheduler args {present} / '{nd[:300]}' do not match engine {eng}: STOP")
    E.snapshot(f"server_up_{label}")
    return srv


# ------------------------------------------------------------------------------------------------ cell
def configure(mode, eng, cond, pol):
    build, run, n, lane = POLD[pol]
    jit, margin = (0.0, MARGIN_A) if mode == "a" else JIT[mode]
    CFG.update(mode=mode, eng=eng, cond=cond, pol=pol, margin=margin, jit=jit, lane=lane, p6b=pol in P6B)
    L.CUR.update(pol=run or "P4", cond=cond)
    L.P4_N = n or 2048
    L.run_recall = run_recall_lane if lane else ORIG["run_recall"]
    if mode == "a":
        L.next_ep_due, L.align_after_due = ORIG["next_ep_due"], ORIG["align_after_due"]
    else:
        L.next_ep_due, L.align_after_due = next_ep_due_b, align_after_due_b
    E.WARM_DEVICE = device_lane if lane else None
    C.W.update(on=False, coalesce=True, sess={}, log=[], t0=None)


def run_one(mode, eng, cond, pol, lev, order, guard_t0, guard=True):
    configure(mode, eng, cond, pol)
    kv, k, r = COND[cond]
    frac = lev if mode == "a" else FRAC_B[lev]
    tg = tag(kv, k, r, 1, frac)
    if X.is_done(tg):
        return X.meta_load()["experiments"][tg]["summary"]
    el = (time.time() - guard_t0) / 3600
    if guard and el > GUARD_H:
        raise GuardStop(f"{el:.2f} h of GPU time elapsed > {GUARD_H} h before {tg}: STOP and report")
    L.STATE.update(tag=tg, work={}, ep_abs=[])
    ST.clear()
    ST.update(lane=None, wsess={}, wlog=[], last={}, arrivals=[], streams_on=False, S=lev if mode != "a" else 0,
              lane_file=OUT / str(C.W["file"]).split("/")[-1].replace("_warm_", "_lane_"))
    ep = E.Episodic(1) if mode == "a" else StreamEp(lev, CFG["jit"], 5000 + 100 * lev + COND_IDX[cond])
    srv = start_server(kv, tg, eng)
    try:
        s = asyncio.run(E.run_cell(kv, k, r, 1, frac, srv.proc.pid, ep, dict(order=order, i=0)))
    finally:
        srv.stop()
        E.WARM_DEVICE = None
    m = X.meta_load()
    w0 = m["experiments"][tg]["window_start"]
    rows = [json.loads(x) for x in open(E.REQ)]
    t0s = [x["t_sched_abs"] - x["t_sched"] for x in rows if x.get("cell") == tg and x["kind"] == "cold_recall"
           and x.get("t_sched_abs")]
    t0 = ST.get("t0") or (float(np.median(t0s)) if t0s else None)
    if CFG["lane"]:
        wr = lane_warm_rows(tg, w0) if ST.get("wlog") is not None and ST.get("t0") else []
        if t0 is not None:
            w0_abs = t0 + w0
            with open(ST["lane_file"], "a") as fh:
                for x in lane_rows(tg, t0, w0_abs, w0_abs + E.DUR):
                    fh.write(json.dumps(x) + "\n")
    else:
        wr = C.warm_rows(tg, w0)
    with open(C.W["file"], "a") as fh:
        for x in wr:
            fh.write(json.dumps(x) + "\n")
    cold = [x for x in rows if x.get("cell") == tg and x["kind"] == "cold_recall" and x["in_window"]]
    cs = dict(n=len(cold), meets_10s=sum(bool(x["meets_10s"]) for x in cold), meets_5s=sum(bool(x["meets_5s"]) for x in cold),
              letters_equal=sum(bool(x["letter_equal"]) for x in cold),
              first_cached_max=max((x["first_cached"] or 0 for x in cold), default=None),
              gap_max=max((x["gap_max"] or 0 for x in cold), default=None), t_answer=[x["ttft_s"] for x in cold])
    ww = [x for x in wr if x["in_window"]]
    esc = [x for x in ww if x["kind"] == "recall_escalation"]
    app = [x for x in ww if x["kind"] == "recall_append"]
    lane = ST.get("lane")
    ls = dict(max_inflight=lane.max_inflight, violations=lane.violations, units=len(lane.units),
              coalesced=sum(1 for u in lane.units if u.dropped == "coalesced"),
              absorbed=sum(1 for u in lane.units if u.dropped == "absorbed"),
              slack=sum(1 for u in lane.units if u.reason == "slack"),
              deadline={k2: sum(1 for u in lane.units if u.reason == "deadline" and
                                ("catchup" if u.info.get("catchup") else u.kind) == k2)
                        for k2 in ("escalation", "catchup", "append")},
              catchup_units=sum(1 for u in lane.units if u.info.get("catchup")),
              absorbed_catchup=sum(1 for u in lane.units if u.dropped == "absorbed_catchup"),
              ewma_final={k2: round(v, 3) for k2, v in lane.ewma.items()}) if lane else None
    ws = dict(appends=len(app), escalations=len(esc), esc_meets_5s=sum((x["t_answer_s"] or 99) <= 5 for x in esc),
              warm_errors=sum(bool(x.get("error")) for x in wr), fallbacks=sum(bool(x.get("fallback")) for x in wr))
    m = X.meta_load()
    m["experiments"][tg].update(mode=CFG["mode"], engine=eng, policy=pol, cond=cond, lev=lev, frac=frac,
                                margin=CFG["margin"], jitter_p90=CFG["jit"], lane_mode=CFG["lane"], cold=cs, warm=ws,
                                lane=ls, phases=ST.get("phases"))
    X.meta_save(m)
    X.log(f"{tg}: p99 {s['episodic_p99']} meets {s['meets_budget']} | cold {cs['n']} 10s {cs['meets_10s']} 5s "
          f"{cs['meets_5s']} letters {cs['letters_equal']} fc {cs['first_cached_max']} gap {cs['gap_max']} | warm {ws} "
          f"| lane {ls and {k2: v for k2, v in ls.items() if k2 != 'ewma_final'}}")
    if E.VOID.is_set():
        raise SystemExit("run VOID: STOP")
    if cs["first_cached_max"] is not None and cs["first_cached_max"] > 16:
        raise SystemExit(f"{tg}: a cold recall's first request was served from cache: STOP")
    if cs["gap_max"] is not None and cs["gap_max"] > 32:
        raise SystemExit(f"{tg}: cached tokens do not equal the previous prefix (gap {cs['gap_max']}): STOP")
    if ls and CFG["lane"] == "single" and (ls["max_inflight"] > 1 or ls["violations"]):
        raise SystemExit(f"{tg}: P6 had {ls['max_inflight']} background units in flight (bug): STOP")
    if ws["warm_errors"] > 3:
        raise SystemExit(f"{tg}: {ws['warm_errors']} warm request errors: STOP")
    return s


class GuardStop(SystemExit):
    pass


def capacity(mode, eng, cond, pol):
    m = X.meta_load()["experiments"]
    levels = LADDER_A if mode == "a" else STREAMS
    cap = 0
    for lv in levels:
        CFG["mode"] = mode
        lab = f"L{int(round(lv * 100))}" if mode == "a" else f"S{lv}"
        tg = f"SLICE1D_{mode}_{eng}_{pol}_{cond}_{lab}"
        if tg not in m or not m[tg]["summary"]["meets_budget"]:
            break
        cap = lv
    return cap


def ladder(mode, eng, cond, pol, order, g0):
    for lv in (LADDER_A if mode == "a" else STREAMS):
        s = run_one(mode, eng, cond, pol, lv, order, g0)
        if not s["meets_budget"]:
            break


def sweep(order, g0):
    # D-a (known schedule)
    ladder("a", "E0", "C4a", "P6", order, g0)
    cap = capacity("a", "E0", "C4a", "P6")
    if cap and cap != 0.10:
        run_one("a", "E0", "C4a", "P6_nolane", cap, order, g0)          # Step 5 cell
    ladder("a", "E0", "C1b", "P6_1024", order, g0)
    ladder("a", "E0", "C1b", "P6", order, g0)
    s = run_one("a", "E0", "C4", "P4", 0.10, order, g0)
    p99 = s["episodic_p99"]
    m = X.meta_load()
    m["drift_check"] = dict(p99=p99, ref=DRIFT_REF, ratio=p99 / DRIFT_REF, ok=abs(p99 / DRIFT_REF - 1) <= DRIFT_TOL)
    X.meta_save(m)
    if not m["drift_check"]["ok"]:
        raise SystemExit(f"drift check failed: C4 P4 10 % p99 {p99:.3f} vs {DRIFT_REF}: STOP and ask")
    ladder("a", "E0", "C4", "P6", order, g0)
    ladder("a", "E0", "C2", "P6", order, g0)
    # D-b (cadence only), priority order
    # report section 17a (user decision 2026-11-13): the D-b P6 lane deadlocks with warm sessions. C4a P6 stopped after
    # the cells already run (S1-S3, DEGENERATE); C2 P6 not run (deadlocked by construction). P6b takes their slots,
    # then D-a C4a P6b for comparison with P6.
    for pol in ("P0", "P2", "P3_1024", "P4", "P6"):
        ladder("b", "E0", "C1a", pol, order, g0)
    for pol in ("P0", "P2", "P3_1024", "P4", "P6b"):
        ladder("b", "E0", "C4a", pol, order, g0)
    for pol in ("P0", "P4_1024", "P6_1024"):
        ladder("b", "E0", "C1b", pol, order, g0)
    for pol in ("P0", "P6b"):
        ladder("b", "E0", "C2", pol, order, g0)
    ladder("a", "E0", "C4a", "P6b", order, g0)
    for cond in ("C1a", "C4a", "C2"):
        ladder("b", "T1", cond, "P0", order, g0)
    for eng in ("E0", "T1"):
        ladder("b", eng, "C0", "P0", order, g0)
    # sensitivity (only if the guard leaves time)
    for mode in ("s0", "s20"):
        for pol in ("P4", "P6"):
            ladder(mode, "E0", "C1a", pol, order, g0)


def plan():
    return ["smoke: D-a C4a P6 10 % (60-s window)", "step4: D-a C4a P6_nolane 10 % (full window)",
            "D-a: C4a P6 ladder; Step 5 P6_nolane at P6's C4a capacity (if not 10 %); C1b P6_1024; C1b P6; "
            "C4 P4 10 % drift (0.544 +/- 25 %); C4 P6; C2 P6",
            "D-b 1: C1a x P0, P2, P3_1024, P4, P6; C4a x P0, P2, P3_1024, P4, P6b (P6 S1-S3 DEGENERATE, 17a)",
            "D-b 2: C1b x P0, P4_1024, P6_1024", "D-b 3: C2 x P0, P6b (C2 P6 not run, 17a)", "D-a: C4a P6b ladder",
            "D-b 4: tuned engine (E10e P1) P0 at C1a, C4a, C2", "D-b 5: C0 P0 at E0 and tuned",
            "sensitivity: C1a P4, P6 at zero jitter and p90 0.20 s"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--step4", action="store_true")
    ap.add_argument("--no-guard", action="store_true", help="lift the 8-h GPU-time guard (user decision 2026-11-13)")
    a = ap.parse_args()
    if a.no_guard:
        global GUARD_H
        GUARD_H = float("inf")
    if a.dry:
        print("\n".join(plan()))
        return
    if a.smoke:
        set_paths("slice1_partd_smoke")
        E.DUR, E.DISCARD = 60.0, 10.0
    L.load_ref()
    S = E.FL.sessions()
    L.STATE["S"] = S
    L.PICKS.extend(p for p in G.pick_sessions(S) if p["target"] == 11000)
    assert len(L.PICKS) == 20 and all(p["video_id"] in L.REF for p in L.PICKS), "Part A ~11k picks not reproduced"
    order = list(range(len(L.PICKS)))
    random.Random(0).shuffle(order)
    E.R1ROWS = L.RefRows()
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']}: STOP")
    import torch
    import vllm
    m = X.meta_load()
    m.setdefault("t_start", time.time())
    if not a.smoke:                                   # GPU-time guard counts from the smoke run's start
        try:
            sm = json.load(open(OUT / "slice1_partd_smoke_run_meta_h100nvl.json"))
            m.setdefault("gpu_t0", sm["t_start"])
        except FileNotFoundError:
            m.setdefault("gpu_t0", m["t_start"])
    g0 = m.get("gpu_t0", m["t_start"])
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, log_flags=L.D.LOGFLAGS, eng_flags=ENG_FLAGS, peak=E.PEAK,
                      ladder_a=LADDER_A, streams=STREAMS, cadence=CADENCE, frac_b=FRAC_B, seed_index=list(E.FRACS),
                      budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD, drain_cap=E.DRAIN_CAP, deadlines=L.DEADLINES,
                      align_s=ALIGN, margin_a=MARGIN_A, jitter=JIT, ewma_alpha=EWMA_ALPHA, ewma_init=INIT,
                      slack=(SLACK_FACTOR, SLACK_MARGIN), lat_factor={str(k): v for k, v in L.LAT_FACTOR.items()},
                      policies={k: list(v) for k, v in POLD.items()}, drift_ref=DRIFT_REF, drift_tol=DRIFT_TOL,
                      guard_h=GUARD_H, block=BLOCK, smoke=a.smoke)
    m["plan"] = plan()
    m["conditions"] = COND
    m["cold_sessions"] = [dict({k: v for k, v in p.items() if k != "question"}, ref=L.REF[p["video_id"]])
                          for p in L.PICKS]
    m["cold_order"] = order
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    stopped = None
    try:
        R6.preencode("D2", S)
        if a.smoke:
            run_one("a", "E0", "C4a", "P6", 0.10, order, g0, guard=False)
        elif a.step4:
            run_one("a", "E0", "C4a", "P6_nolane", 0.10, order, g0)
        else:
            sweep(order, g0)
    except GuardStop as e:
        stopped = str(e)
        X.log(stopped)
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        if stopped:
            m["guard_stop"] = stopped
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_slice1_partd.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
