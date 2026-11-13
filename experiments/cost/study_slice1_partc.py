#!/usr/bin/env python3
"""StudySLICE1 Part C (live mixed test, warm management). EXCLUSIVE (vLLM venv; h100nvl GPU 2).
Pre-registered in research/EXPERIMENTS.md (StudySLICE1 row, Part C extension) and reports/study_slice1.md section 11,
before any Part C run.

Question: does managing warm traffic the way P4 manages cold slices (defer the deferrable, gap-align the
latency-sensitive) restore episodic capacity when KV-HOST warm sessions and cold recall coexist?

Harness: Part B's study_slice1_live (cold orchestrator, E0 server start + flag check, cold sessions / order / fresh
namespaces, sanity checks) on top of study_e10b_mixed.run_cell, unchanged except:
  * the hook study_e10b_mixed.WARM_DEVICE (default None = R6.device; set only for P5 cells) routes the warm sessions'
    appends and escalations through the warm manager below;
  * R7.Cell.post is replaced, in this process only, by a copy that also accumulates the streamed output (escalation
    letters) and sets an optional `on_submit` event just before the HTTP request. Bodies, kinds, order unchanged.
Policies: P0 (Part B P0, warm pass-through), P4 (Part B P4, warm pass-through), P5 (P4 cold path + warm management),
P4_1024 (P4 logic with 1,024-token slices; slack factor 1.467 from Part A), P5nc (P5 with coalescing OFF).
P5 warm management, per session (device, session index):
  recall_warmup     pass-through (before the window).
  recall_append     held while an episodic call is due within its predicted time; released on a gap. Coalescing:
                    a held append is dropped when the session's next append becomes due (the later delta body carries
                    its frames). Forced back-to-back releases: flush before an escalation of the session; with
                    coalescing OFF, release when the next append is due.
  recall_escalation gap-aligned only (P3 rule: if an episodic call is due within its predicted time, dispatch 5 ms
                    after that call's dispatch; else immediately).
  Within a session, each request is submitted only after the previous one was submitted.
Predicted warm time (committed E10c E0 C2 10 % appends, in-window, n 189; OLS): t = 0.1273 + 0.000390 x new tokens;
new tokens = 10.6 + 90.3 x frames (append), 142.8 + 91.2 x frames (escalation), frames = not yet dispatched.
Rows -> results/cost/study_slice1/slice1_partc_{requests,slices,warm,metrics,cpu,monitor}_h100nvl.jsonl,
meta slice1_partc_run_meta_h100nvl.json.
"""
import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study_slice1_live as L  # noqa: E402  (Part B: sets E.dispatch / E.k1_body / E.tag for the cold path)

E, X, F, G = L.E, L.X, L.F, L.G
R6, R7 = L.R6, L.R7
OUT = L.OUT

LADDER = L.LADDER
COND = {"C4a": ("KVHOST", 8, 0.05), "C4": ("KVHOST", 8, 0.1), "C2": ("KVHOST", 8, 0.0), "C1b": ("KVGPU", 0, 0.1)}
# policy -> (cold logic label used by study_slice1_live, cold slice n, warm managed?, coalesce?)
POL = {"P0": ("P0", None, False, True), "P4": ("P4", 2048, False, True), "P5": ("P4", 2048, True, True),
       "P5nc": ("P4", 2048, True, False), "P4_1024": ("P4", 1024, False, True)}
L.LAT_FACTOR[1024] = 1.467          # Part A: max client-latency / engine ratio, n 1,024 chain, 20 ~11k sessions
FIT = dict(a=0.1273, b=0.000390, app=(10.6, 90.3), esc=(142.8, 91.2))
DRIFT_REF, DRIFT_TOL = 0.531, 0.25
MAX_H = 5.0
PC = {"pol": "P0", "cond": "C4a"}
W = {"on": False, "coalesce": True, "sess": {}, "log": [], "t0": None}


def set_paths(prefix):
    E.REQ = OUT / f"{prefix}_requests_h100nvl.jsonl"
    E.MET = OUT / f"{prefix}_metrics_h100nvl.jsonl"
    E.CPU = OUT / f"{prefix}_cpu_h100nvl.jsonl"
    E.MON = OUT / f"{prefix}_monitor_h100nvl.jsonl"
    L.SLICES = OUT / f"{prefix}_slices_h100nvl.jsonl"
    W["file"] = OUT / f"{prefix}_warm_h100nvl.jsonl"
    X.META_PATH = OUT / f"{prefix}_run_meta_h100nvl.json"
    G.X.META_PATH = X.META_PATH
    X.CURRENT = E.REPO / "logs/slice1_partc_current.json"


set_paths("slice1_partc")


def tag(kv, k, r, n, frac):
    return f"SLICE1C_{PC['pol']}_{PC['cond']}_N{n}_L{int(round(frac * 100))}"


E.tag = tag


def k1_body(q):
    """Cold work prebuild: P4_1024 builds 1,024-token slices (Part A chain) and runs them with P4's logic."""
    if POL[PC["pol"]][1] == 1024:
        L.CUR["pol"] = "P3_1024"
    try:
        return L.k1_body(q)
    finally:
        L.CUR["pol"] = POL[PC["pol"]][0]


E.k1_body = k1_body


# ------------------------------------------------------------------------------------------------ warm post (letters)
async def post_c(self, kind, dev, sess_i, sess, upto_s, question=None, qid=None, in_window=True, t_sched=None,
                 on_submit=None):
    """Copy of R7.Cell.post (EAGER delta path) + output text / letter + optional on_submit event."""
    sp = self.spec
    fmt, pol = sp["fmt"], sp["policy"]
    mt = R7.F.ESC_MAX_TOKENS if kind == "escalation" else 1
    ns = f"{self.tag}|{dev}|{sess_i}"
    key = (dev, sess_i)
    mode = "full" if pol == "LAZY" else "delta"
    sent = self.sent.get(key, -1.0)
    if mode == "delta":
        self.sent[key] = max(sent, upto_s)
    hdr = R6.header(self.tag, dev, sess_i)
    try:
        data, n_frames, n_new, new_b, full_eq = await asyncio.to_thread(R7.body7, fmt, hdr, sess, upto_s, question, mt,
                                                                       mode, ns, sent)
    except BaseException:
        if on_submit is not None:
            on_submit.set()
        raise
    t_sub = time.time()
    first, usage, err, fb, fb_err, body_mb_sent, text = None, None, None, False, None, len(data) / 1e6, ""
    try:
        for attempt in (0, 1):
            retry = False
            if on_submit is not None:
                on_submit.set()
            async with self.client.stream("POST", f"{X.BASE}/v1/chat/completions", content=data,
                                          headers={"Content-Type": "application/json"}) as r:
                if r.status_code != 200:
                    txt = (await r.aread())[:400]
                    if attempt == 0 and mode == "delta" and b"Cache miss" in txt:
                        retry, fb, fb_err = True, True, txt[:200].decode(errors="replace")
                    else:
                        err = f"HTTP {r.status_code}: {txt[:300]!r}"
                else:
                    async for line in r.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        j = json.loads(line[6:])
                        if j.get("usage"):
                            usage = j["usage"]
                        for ch in j.get("choices", []):
                            dl = (ch.get("delta") or {}).get("content")
                            if dl:
                                if first is None:
                                    first = time.time()
                                text += dl
            if not retry:
                break
            data = (await asyncio.to_thread(R7.body7, fmt, hdr, sess, upto_s, question, mt, "fullu", ns))[0]
            body_mb_sent += len(data) / 1e6
    except asyncio.CancelledError:
        err = f"censored: still in flight at the {R7.DRAIN_CAP_S}-s drain cap"
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    t_end = time.time()
    m = G.LETTER.search(text)
    rec = dict(cell=self.tag, policy=pol, part=pol, fmt=fmt, cadence=sp["cadence"], lazy=sp["lazy"],
               offload_gib=sp["offload"], D=self.D, kind=kind, device=dev, session=sess_i,
               video_id=sess["video_id"], session_t=round(upto_s, 1), n_frames=n_frames, n_new_frames=n_new,
               body_mode=mode, body_mb=round(len(data) / 1e6 if not fb else body_mb_sent, 4),
               new_frames_mb=round(new_b / 1e6, 4), full_equiv_mb=round(full_eq / 1e6, 4), fallback=fb,
               fallback_error=fb_err, question_id=qid,
               in_window=in_window, t_sched=None if t_sched is None else round(t_sched - self.t0, 3),
               t_submit=round(t_sub - self.t0, 3),
               submit_lag_s=None if t_sched is None else round(t_sub - t_sched, 3),
               ttft_s=round(first - t_sub, 3) if first else None, latency_s=round(t_end - t_sub, 3),
               t_end=round(t_end - self.t0, 3), prompt_tokens=usage and usage["prompt_tokens"],
               cached_tokens=((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
               completion_tokens=usage and usage["completion_tokens"], error=err, warm_device=not sp["lazy"],
               output=text[:40], letter=m.group(1) if m else None)
    self.records.append(rec)
    return rec


R7.Cell.post = post_c


# ------------------------------------------------------------------------------------------------ warm manager (P5)
def n_frames(sess, a, b):
    """Frames with session time in (a, b]."""
    return len(R6.frames(sess, b)) - (len(R6.frames(sess, a)) if a >= 0 else 0)


def pred(kind, frames):
    c0, c1 = FIT["app"] if kind == "append" else FIT["esc"]
    return FIT["a"] + FIT["b"] * (c0 + c1 * frames)


def track(cell, coro):
    t = asyncio.create_task(coro)
    cell.inflight.add(t)
    t.add_done_callback(cell.inflight.discard)
    return t


def sess_state(dev, s_i):
    return W["sess"].setdefault((dev, s_i), dict(pending=None, sub_ev=None, disp_upto=-1.0))


def entry(kind, dev, s_i, sess, st, wall, q=None):
    e = dict(kind=kind, device=dev, session=s_i, session_t=st, wall=wall, q=q, state="held", coalesced=False,
             release=None, t_dispatch=None, rec=None, held_s=None)
    W["log"].append(e)
    return e


def submit(cell, e, reason):
    """Dispatch decision, synchronous: mark released, advance the session's dispatched state and register this
    request in the session's submission chain NOW; returns the coroutine that waits for the previous submission of
    the session (if any) and posts."""
    S = sess_state(e["device"], e["session"])
    prev = S["sub_ev"]
    ev = asyncio.Event()
    S["sub_ev"] = ev
    S["disp_upto"] = max(S["disp_upto"], e["session_t"])
    e.update(state="released", release=reason, t_dispatch=time.time())
    e["held_s"] = round(e["t_dispatch"] - e["wall"], 4)
    return _post_after(cell, e, prev, ev)


async def _post_after(cell, e, prev, ev):
    try:
        if prev is not None and not prev.is_set():
            t = time.time()
            try:
                await asyncio.wait_for(prev.wait(), 5.0)
            except asyncio.TimeoutError:
                e["order_wait_timeout"] = True
            e["order_wait_s"] = round(time.time() - t, 4)
        q = e["q"]
        e["rec"] = await post_c(cell, e["kind"], e["device"], e["session"], e["sess"], e["session_t"],
                                question=q and q["text"], qid=q and q["qid"], t_sched=e["wall"], on_submit=ev)
    finally:
        ev.set()


def release_now(cell, e, reason):
    S = sess_state(e["device"], e["session"])
    if S["pending"] is e:
        S["pending"] = None
    h = e.pop("holder", None)
    if h is not None:
        h.cancel()
    return track(cell, submit(cell, e, reason))


async def hold_append(cell, e):
    await L.wait_gap(e["pred_s"], float("inf"), "")
    if e["state"] != "held":                         # flushed / coalesced meanwhile (cancel raced the wake-up)
        return
    S = sess_state(e["device"], e["session"])
    if S["pending"] is e:
        S["pending"] = None
    e.pop("holder", None)
    await submit(cell, e, "gap")


def on_append(cell, dev, s_i, sess, st, wall):
    S = sess_state(dev, s_i)
    old = S["pending"]
    if old is not None and old["state"] == "held":
        if W["coalesce"]:
            old.update(state="coalesced", coalesced=True, release="coalesced", held_s=round(time.time() - old["wall"], 4))
            S["pending"] = None
            h = old.pop("holder", None)
            if h is not None:
                h.cancel()
        else:
            release_now(cell, old, "next_append_due")
    e = entry("append", dev, s_i, sess, st, wall)
    e["sess"] = sess
    e["new_frames_pred"] = n_frames(sess, S["disp_upto"], st)
    e["pred_s"] = pred("append", e["new_frames_pred"])
    S["pending"] = e
    e["holder"] = track(cell, hold_append(cell, e))


async def on_escalation(cell, dev, s_i, sess, st, q, wall):
    S = sess_state(dev, s_i)
    e = entry("escalation", dev, s_i, sess, st, wall, q)
    e["sess"] = sess
    e["stale_frames"] = n_frames(sess, S["disp_upto"], st)          # at arrival, before any flush
    e["pending_append_at_arrival"] = S["pending"] is not None
    e["pred_s"] = pred("escalation", e["stale_frames"])
    held = await L.align_after_due(e["pred_s"])
    p = S["pending"]
    if p is not None and p["state"] == "held":
        release_now(cell, p, "flush_for_escalation")
        e["flushed_append"] = True
    await submit(cell, e, "aligned" if held > 0 else "immediate")


async def device_c(cell, dev, plan_d, offset, window_end):
    """R6.device's event loop (P-WARM, rate 1.0, appends every `cadence` s, escalations at real offsets) with each
    warm event handed to the warm manager instead of cell.spawn(cell.post(...))."""
    s_i, sess, start_s = 0, plan_d[0], offset
    t_start = time.time()
    cad = cell.spec["cadence"]
    # the pre-window warm-up (pass-through) already dispatched this session's history up to its offset
    sess_state(dev, 0)["disp_upto"] = cell.sent.get((dev, 0), -1.0)
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
            W["t0"] = cell.t0
            if kind == "append":
                on_append(cell, dev, s_i, sess, st, wall)
            else:
                track(cell, on_escalation(cell, dev, s_i, sess, st, q, wall))
        t_start = t_start + (sess["duration"] - start_s)
        s_i += 1
        if s_i >= len(plan_d) or t_start > window_end:
            return
        sess, start_s = plan_d[s_i], 0.0
        await asyncio.sleep(max(0.0, t_start - time.time()))


# ------------------------------------------------------------------------------------------------ per-cell warm rows
def warm_rows(tg, w0_rel):
    """One row per warm event. P5: from the manager's log. Pass-through: from the cell's request rows."""
    out = []
    if W["on"]:
        t0 = W["t0"]
        for e in W["log"]:
            r = e["rec"] or {}
            ts = e["wall"] - t0
            row = dict(cell=tg, kind="recall_" + e["kind"], device=e["device"], session=e["session"],
                       session_t=e["session_t"], question_id=e["q"] and e["q"]["qid"], t_sched=round(ts, 3),
                       t_dispatch=round(e["t_dispatch"] - t0, 3) if e["t_dispatch"] else None, held_s=e["held_s"],
                       release=e["release"], coalesced=e["coalesced"], pred_s=round(e["pred_s"], 4),
                       new_frames_pred=e.get("new_frames_pred"), stale_frames=e.get("stale_frames"),
                       flushed_append=e.get("flushed_append", False), order_wait_s=e.get("order_wait_s"),
                       order_wait_timeout=e.get("order_wait_timeout", False),
                       in_window=ts - w0_rel >= E.DISCARD)
            row.update({k: r.get(k) for k in ("t_submit", "ttft_s", "latency_s", "t_end", "prompt_tokens",
                                              "cached_tokens", "n_frames", "n_new_frames", "letter", "output",
                                              "fallback", "error")})
            row["computed_tokens"] = (r["prompt_tokens"] - (r["cached_tokens"] or 0)) if r.get("prompt_tokens") else None
            row["t_answer_s"] = (round(r["t_submit"] + r["ttft_s"] - ts, 4)
                                 if r.get("ttft_s") is not None and r.get("t_submit") is not None else None)
            out.append(row)
    else:
        for x in sorted((json.loads(l) for l in open(E.REQ)), key=lambda x: (x.get("t_submit") or 0)):
            if x.get("cell") != tg or not x["kind"].startswith("recall_"):
                continue
            ts = x["t_sched"]
            row = dict(cell=tg, kind=x["kind"], device=x["device"], session=x["session"], session_t=x["session_t"],
                       question_id=x["question_id"], t_sched=ts, t_dispatch=x["t_submit"],
                       held_s=0.0 if ts is not None else None, release="passthrough", coalesced=False,
                       in_window=x["in_window"])
            if x["kind"] == "recall_escalation":       # frames since the last dispatched request of the session
                row["stale_frames"] = x["n_new_frames"]
            row.update({k: x.get(k) for k in ("t_submit", "ttft_s", "latency_s", "t_end", "prompt_tokens",
                                              "cached_tokens", "n_frames", "n_new_frames", "letter", "output",
                                              "fallback", "error")})
            row["computed_tokens"] = (x["prompt_tokens"] - (x["cached_tokens"] or 0)) if x.get("prompt_tokens") else None
            row["t_answer_s"] = (round(x["t_submit"] + x["ttft_s"] - ts, 4)
                                 if x.get("ttft_s") is not None and ts is not None else None)
            out.append(row)
    return out


# ------------------------------------------------------------------------------------------------ cell
def run_one(cond, pol, f, order, t_start, guard=True):
    """Returns the cell summary (run or recorded)."""
    PC.update(pol=pol, cond=cond)
    cold_pol, cold_n, managed, coal = POL[pol]
    L.CUR.update(pol=cold_pol, cond=cond)
    L.P4_N = cold_n or 2048
    kv, k, r = COND[cond]
    tg = tag(kv, k, r, 1, f)
    if X.is_done(tg):
        return X.meta_load()["experiments"][tg]["summary"]
    el = (time.time() - t_start) / 3600
    if guard and el > MAX_H:
        raise SystemExit(f"{el:.2f} h elapsed > {MAX_H} h before {tg}: STOP and ask")
    L.STATE.update(tag=tg, work={}, ep_abs=[])
    W.update(on=managed, coalesce=coal, sess={}, log=[], t0=None)
    E.WARM_DEVICE = device_c if managed else None
    srv = L.start_server(kv, tg)
    try:
        s = asyncio.run(E.run_cell(kv, k, r, 1, f, srv.proc.pid, E.Episodic(1), dict(order=order, i=0)))
    finally:
        srv.stop()
        E.WARM_DEVICE = None
    m = X.meta_load()
    w0 = m["experiments"][tg]["window_start"]
    wr = warm_rows(tg, w0)
    with open(W["file"], "a") as fh:
        for x in wr:
            fh.write(json.dumps(x) + "\n")
    rows = [json.loads(x) for x in open(E.REQ)]
    cold = [x for x in rows if x.get("cell") == tg and x["kind"] == "cold_recall" and x["in_window"]]
    cs = dict(n=len(cold), meets_10s=sum(x["meets_10s"] for x in cold), meets_5s=sum(x["meets_5s"] for x in cold),
              letters_equal=sum(bool(x["letter_equal"]) for x in cold),
              first_cached_max=max((x["first_cached"] or 0 for x in cold), default=None),
              gap_max=max((x["gap_max"] or 0 for x in cold), default=None), t_answer=[x["ttft_s"] for x in cold])
    ww = [x for x in wr if x["in_window"]]
    app = [x for x in ww if x["kind"] == "recall_append"]
    esc = [x for x in ww if x["kind"] == "recall_escalation"]
    warm_in_window_warmups = sum(1 for x in rows if x.get("cell") == tg and x["kind"] == "recall_warmup"
                                 and x["t_end"] is not None and x["t_end"] >= w0)
    rel = {}
    for x in app + esc:
        rel[x["release"]] = rel.get(x["release"], 0) + 1
    ws = dict(appends=len(app), appends_dispatched=sum(not x["coalesced"] for x in app),
              coalesced=sum(x["coalesced"] for x in app),
              append_held_median=sorted(x["held_s"] for x in app)[len(app) // 2] if app else None,
              append_held_max=max((x["held_s"] for x in app), default=None), releases=rel,
              escalations=len(esc), esc_meets_5s=sum((x["t_answer_s"] or 99) <= 5 for x in esc),
              esc_t_answer=[x["t_answer_s"] for x in esc],
              warm_computed=sum(x["computed_tokens"] or 0 for x in ww),
              fallbacks=sum(bool(x["fallback"]) for x in wr), warm_errors=sum(bool(x["error"]) for x in wr),
              order_timeouts=sum(bool(x.get("order_wait_timeout")) for x in wr),
              warmups_ending_in_window=warm_in_window_warmups)
    m = X.meta_load()
    m["experiments"][tg].update(policy=pol, cond=cond, cold_logic=cold_pol, cold_n=cold_n, warm_managed=managed,
                                coalesce=coal, cold=cs, warm=ws)
    X.meta_save(m)
    X.log(f"{tg}: cold {cs['n']} in window, meet 10 s {cs['meets_10s']}, 5 s {cs['meets_5s']}, letters "
          f"{cs['letters_equal']}, first cached max {cs['first_cached_max']}, gap max {cs['gap_max']} | warm "
          f"{ {k: v for k, v in ws.items() if k != 'esc_t_answer'} }")
    if E.VOID.is_set():
        raise SystemExit("run VOID: STOP")
    if cs["first_cached_max"] is not None and cs["first_cached_max"] > 16:
        raise SystemExit(f"{tg}: a cold recall's first request was served from cache: STOP")
    if cs["gap_max"] is not None and cs["gap_max"] > 32:
        raise SystemExit(f"{tg}: cached tokens do not equal the previous prefix (gap {cs['gap_max']}): STOP")
    if ws["warm_errors"]:
        raise SystemExit(f"{tg}: {ws['warm_errors']} warm request errors: STOP")
    return s


def capacity(cond, pol):
    """Highest passing ladder level (fraction) among recorded cells, bottom-up; 0.0 if none."""
    m = X.meta_load()["experiments"]
    cap = 0.0
    for f in LADDER:
        tg = f"SLICE1C_{pol}_{cond}_N1_L{int(round(f * 100))}"
        if tg not in m or not m[tg]["summary"]["meets_budget"]:
            break
        cap = f
    return cap


def ladder(cond, pol, order, t_start):
    for f in LADDER:
        s = run_one(cond, pol, f, order, t_start)
        if not s["meets_budget"]:
            break


def sweep(order, t_start):
    # 1. C4a [PRIMARY]
    run_one("C4a", "P0", 0.10, order, t_start)
    ladder("C4a", "P4", order, t_start)
    ladder("C4a", "P5", order, t_start)
    run_one("C4a", "P5nc", capacity("C4a", "P5") or 0.10, order, t_start)
    # 2. C4 (drift check first)
    s = run_one("C4", "P4", 0.10, order, t_start)
    p99 = s["episodic_p99"]
    m = X.meta_load()
    m["drift_check"] = dict(p99=p99, ref=DRIFT_REF, ratio=p99 / DRIFT_REF, ok=abs(p99 / DRIFT_REF - 1) <= DRIFT_TOL)
    X.meta_save(m)
    if not m["drift_check"]["ok"]:
        raise SystemExit(f"drift check failed: C4 P4 10 % p99 {p99:.3f} vs {DRIFT_REF}: STOP and ask")
    ladder("C4", "P5", order, t_start)
    # 3. C2
    ladder("C2", "P0", order, t_start)
    ladder("C2", "P5", order, t_start)
    # 4. C1b
    ladder("C1b", "P4_1024", order, t_start)


def plan():
    return ["smoke: C4a P5 10 % (60-s window)",
            "1 C4a: P0 10 %; P4 ladder; P5 ladder; P5nc at P5's C4a capacity (10 % if < 10 %)",
            "2 C4: P4 10 % (drift check 0.531 s +/- 25 %); P5 ladder",
            "3 C2: P0 ladder; P5 ladder", "4 C1b: P4_1024 ladder"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="C4a P5 at 10 %, 60-s window")
    a = ap.parse_args()
    if a.dry:
        print("\n".join(plan()))
        return
    if a.smoke:
        set_paths("slice1_partc_smoke")
        E.DUR, E.DISCARD = 60.0, 10.0
    L.load_ref()
    S = E.FL.sessions()
    L.STATE["S"] = S
    L.PICKS.extend(p for p in G.pick_sessions(S) if p["target"] == 11000)
    assert len(L.PICKS) == 20 and all(p["video_id"] in L.REF for p in L.PICKS), "Part A ~11k picks not reproduced"
    order = list(range(len(L.PICKS)))
    import random
    random.Random(0).shuffle(order)
    E.R1ROWS = L.RefRows()
    start = E.snapshot("start")
    if start["ours_outside_job"]:
        raise SystemExit(f"not exclusive at start: {start['ours_outside_job']}: STOP")
    import torch
    import vllm
    m = X.meta_load()
    t_start = m.setdefault("t_start", time.time())
    m["stack"] = dict(venv=sys.prefix, vllm=vllm.__version__, torch=torch.__version__, gpu="h100nvl GPU 2",
                      gpu_uuid=F.GPU_UUID, kv_flags=E.KV, log_flags=L.D.LOGFLAGS, peak=E.PEAK, ladder=LADDER,
                      seed_index=list(E.FRACS), budget=E.BUDGET, dur=E.DUR, discard=E.DISCARD,
                      drain_cap=E.DRAIN_CAP, deadlines=L.DEADLINES, align_s=L.ALIGN, tok_per_frame=G.TOK_PER_FRAME,
                      smoke=a.smoke, lat_factor={str(k): v for k, v in L.LAT_FACTOR.items()},
                      slack_margin=L.SLACK_MARGIN, warm_fit=FIT, policies={k: list(v) for k, v in POL.items()},
                      drift_ref=DRIFT_REF, drift_tol=DRIFT_TOL, hook="study_e10b_mixed.WARM_DEVICE")
    m["plan"] = plan()
    m["conditions"] = COND
    m["cold_sessions"] = [dict({k: v for k, v in p.items() if k != "question"}, ref=L.REF[p["video_id"]])
                          for p in L.PICKS]
    m["cold_order"] = order
    X.meta_save(m)
    th = threading.Thread(target=E.monitor, daemon=True)
    th.start()
    try:
        R6.preencode("D2", S)
        if a.smoke:
            run_one("C4a", "P5", 0.10, order, t_start, guard=False)
        else:
            sweep(order, t_start)
    finally:
        E.STOP_MON.set()
        E.snapshot("end")
        m = X.meta_load()
        m["void"] = E.VOID.is_set()
        X.meta_save(m)
    from _provenance import stamp
    m = X.meta_load()
    m.setdefault("_provenance", []).append(stamp(script="study_slice1_partc.py", model="qwen3vl-32b-instruct",
                                                 device="h100nvl_gpu2", args=a))
    X.meta_save(m)


if __name__ == "__main__":
    main()
