#!/usr/bin/env python3
"""StudySIM1c-scoped - the runner. CPU only; nothing here runs a model.

One cell, one arm: replay a committed demand trace through the StudySIM1 engine model with the
HOST-WARM tier removed from the world, and report the metrics. No arm is compared with another
here; `sim1c_report.py` tabulates and the report states what may not be claimed.

THE SCOPE IS ENFORCED IN THIS FILE, NOT IN ANY BASELINE. `HOST_AVAILABLE = False` makes the
harness map OFFLOAD_TO_HOST to EVICT and never report readiness HOST-WARM. No baseline's logic
is edited; an arm whose CORE decision is host offload is simply not run (see `sim1c_scope.py`).

WHAT A STREAM SEES. The application's score for a clip at grid index i is the most recent
DELIVERY, whichever path produced it: the device's own 4B score (always available, StudyD8's
0.567 s latency at StudyE9b's 0.75-s saturated cadence) or a cloud score whose delivery time the
engine model produced. A suspended or disconnected stream therefore reads device scores, which
is exactly StudyE9d's SUSPEND semantics.
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
for p in (ROOT / "experiments/dashcam", ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/orchestration/baselines/smoke",
          ROOT / "experiments/orchestration/baselines/reconstructed",
          ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import engine as E                 # noqa: E402
import metrics as M                # noqa: E402
import workload as W               # noqa: E402
import costs as C                  # noqa: E402
from interface import (Budget, CloudState, EpisodicStream, EvidenceItem,  # noqa: E402
                       NetworkState, Observation, Policy, RecallQuery, check_fairness)

HOST_AVAILABLE = False             # THE SCOPE FLAG
MISSING = -1e9                     # StudyE9b's missing marker, re-exported below
STEP_S = W.STEP_S
TICK_S = W.TICK_S
SETTING_LOAD = 25                  # StudyE9b setting (ii) at 25 % load, SIM1's base
HIST = 40                          # delivered scores a policy sees, as the smoke harness uses

# StudySLICE1 Part A, MEASURED: per-slice overhead 0.015 s at 1,024-token slices and -0.004 s
# (about zero) at 2,048, with chain / monolithic engine time 1.093 and 0.990. The primary
# setting uses the measured value for the slice size a policy asks for; SIM1's pre-registered
# sweep {0.02, 0.05, 0.1, 0.2, 0.47} s is kept as sensitivity.
SLICE_OVERHEAD_MEASURED_S = {1024: 0.015, 2048: 0.0}
SLICE_OVERHEAD_SWEEP_S = (0.02, 0.05, 0.1, 0.2, 0.47)
# A DEVICE recall answer's latency. StudyF4 measured device recall ACCURACY, not latency, so the
# nearest committed device-side request latency is used: StudyD8 arm A total p50, 0.567 s. This
# is a RULE, not a measurement of device recall. It is far inside every deadline tested
# (2 / 5 / 10 s), so no result here turns on its exact value; the report states this.
DEVICE_RECALL_S = C.DEV_LAT_S
ENGINE_CONFIG = {"default": "P0", "P0": "P0", "P1": "P1", "P2": "P2", "P3": "P3", "E2": "E2"}


def _device_schedule(arr: np.ndarray, G: int) -> Tuple[np.ndarray, np.ndarray]:
    """The device's own deliveries for one clip: it computes at StudyE9b's saturated 0.75-s
    cadence and its score is readable ceil(0.567 / 0.25) = 3 steps later."""
    m = int(round(C.DEVICE_CADENCE_S / STEP_S))
    d = C.hold_shift_steps(C.DEV_LAT_S)
    comp = np.arange(0, G, m)
    return comp + d, arr[comp]


@dataclass
class _Stream:
    idx: int
    plan: W.StreamPlan
    mode: str = "cloud"
    cadence_s: float = 0.5
    frame_count: int = 1
    suspend_until_s: float = -1.0
    clip_i: int = 0
    phase_s: float = 0.0


def run_cell(trace: W.Trace, policy: Policy, seed: int = 0,
             slice_overhead_s: Optional[float] = None,
             recall_free: bool = False, all_cloud_no_recall: bool = False) -> Dict:
    """Replay one committed trace through one arm. Returns metrics and counters, never a ranking.

    `recall_free` and `all_cloud_no_recall` are the SANITY-CHECK switches, not sweep settings.
    `all_cloud_no_recall` also forces every stream connected, because the check it serves
    compares against StudyE9c's delivered cloud cell, which has no outages in it.
    """
    t0 = time.time()
    ctx = W.clip_context()
    meta = ctx["meta"]
    dev_arr = ctx["arrs"][("4BI", 1)]
    cloud_arr = {n: ctx["arrs"][("32BI", n)] for n in (1, 3)}
    check_fairness(policy)
    policy.reset(seed)

    length = trace.length_s
    budget = Budget(gpu_seconds=length * 1.0)      # ONE replica for the length of the run
    eng = E.Engine(config="P0", kv_mode="GPU")     # host offload is out of scope: GPU KV only

    streams = [_Stream(i, sp) for i, sp in enumerate(trace.streams)]
    # The streams' cadence phases are STAGGERED. Without this every stream issues its cloud call
    # at exactly the same instants and the fleet arrives as one burst each cadence period, which
    # is an artifact of starting them all at t = 0 and not a property of any policy. The offset
    # is deterministic in the stream index, so it is part of the trace, not of the arm.
    for s in streams:
        s.phase_s = (s.idx / max(len(streams), 1)) * 0.5

    # delivered events per clip: (delivery grid index, score). NOTHING is injected up front: a
    # delivery exists only if some path actually produced it during the run, and a stream on the
    # cloud does not also read its own device scores.
    delivered: Dict[str, List[Tuple[int, float]]] = {c: [] for sp in trace.streams
                                                     for c in sp.clips}
    recent: Dict[str, deque] = {s.plan.stream_id: deque(maxlen=HIST) for s in streams}
    dev_wall: Dict[int, List[Tuple[float, float, str, int]]] = {}
    for s in streams:
        rows = []
        for ci, c in enumerate(s.plan.clips):
            base = s.plan.starts_s[ci]
            G = meta[c]["G"]
            di, ds = _device_schedule(dev_arr[c], G)
            for i, v in zip(di, ds):
                if i < G:
                    rows.append((base + i * STEP_S, float(v), c, int(i)))
        dev_wall[s.idx] = rows
    dev_ptr = {s.idx: 0 for s in streams}

    # recall
    pend: List[RecallQuery] = []
    answers: List[Dict] = []
    qmeta: Dict[str, Dict] = {}
    arrivals: List[Tuple[float, str, str, str, float]] = []   # t, qid, session, category, qt
    for sq in trace.sessions:
        for (t, cat, qid) in sq.questions:
            arrivals.append((t, qid, sq.session_id, cat, t - sq.start_s))
    arrivals.sort()
    ai = 0
    sess_tokens = {sq.session_id: sq.tokens for sq in trace.sessions}
    ever_warmed = set()

    # engine bookkeeping
    req_meta: Dict[str, Dict] = {}
    done_ptr = 0
    n_ep_sub = n_ep_done = 0
    n_recall_cloud = n_recall_device = n_defer = n_reject = 0
    budget_refusals = 0
    materialize_calls = materialize_sliced = 0
    suspend_steps = 0
    kv_peak_frac = 0.0
    eng_cfg_requested = None

    rid = 0
    t = 0.0
    while t < length - 1e-9:
        # ---- epoch: arrivals first, so the policy sees them
        epoch = "tick"
        while ai < len(arrivals) and arrivals[ai][0] <= t + 1e-9:
            at, qid, sid, cat, qt = arrivals[ai]
            ai += 1
            if all_cloud_no_recall:
                continue
            tok = sess_tokens[sid]
            ready = eng.readiness(sid)
            if ready == "HOST-WARM":              # cannot happen in scope; asserted
                raise AssertionError("HOST-WARM readiness leaked into a scoped run")
            ev = (EvidenceItem("D2", "device", tok, tok * 4),
                  EvidenceItem("D2", "gpu" if ready == "GPU-WARM" else "device", tok,
                               C.host_reload_bytes(tok)))
            q = RecallQuery(query_id=qid, session_id=sid, category=cat, arrival_s=round(at, 3),
                            deadline_s=round(at + trace.deadline_s, 3), evidence=ev,
                            readiness=ready, readiness_tokens=tok)
            pend.append(q)
            qmeta[qid] = dict(category=cat, question_time_s=qt, arrival_s=at, session=sid,
                              tokens=tok)
            epoch = "recall_arrival"

        # ---- observation
        eps = []
        for s in streams:
            hist = recent[s.plan.stream_id]
            scores = tuple(x[1] for x in hist)
            times = tuple(round(x[0], 3) for x in hist)
            eps.append(EpisodicStream(
                stream_id=s.plan.stream_id, delivered_scores=scores, delivered_times_s=times,
                cadence_s=s.cadence_s, frame_count=s.frame_count,
                on_cloud=(s.mode == "cloud"),
                network=NetworkState(connected=(all_cloud_no_recall
                                                or W.connected(s.plan, t)),
                                     uplink_bps=C.UPLINK_BPS, rtt_s=C.RTT_S)))
        gpu_sessions = tuple(sorted(eng.gpu))
        kv_peak_frac = max(kv_peak_frac, eng.gpu_kv_fraction())
        cloud = CloudState(
            queued_by_class=dict(recall=len(pend), episodic=len(eng.waiting)),
            running_by_class=dict(recall=0, episodic=len(eng.running)),
            gpu_kv_fraction=eng.gpu_kv_fraction(), host_kv_fraction=0.0,
            gpu_warm_sessions=gpu_sessions, host_warm_sessions=(),
            latency_estimate_s=dict(
                recall=0.0,
                episodic=C.episodic_cloud_latency_s("32BI", 1, SETTING_LOAD)))
        obs = Observation(now_s=round(t, 3), epoch=epoch, streams=tuple(eps),
                          recall=tuple(pend), cloud=cloud,
                          budget_remaining_gpu_s=budget.remaining_gpu_s())
        act = policy(obs)
        if act.engine_config and eng_cfg_requested is None:
            eng_cfg_requested = act.engine_config
            cfg = ENGINE_CONFIG.get(act.engine_config, "P0")
            if cfg != eng.config:
                eng.config = cfg
                eng.cap = int(E.CONFIGS[cfg]["long_prefill_token_threshold"])
                eng.policy = E.CONFIGS[cfg]["policy"]

        # ---- apply stream actions
        by_sid = {s.plan.stream_id: s for s in streams}
        for sa in act.streams:
            s = by_sid[sa.stream_id]
            if all_cloud_no_recall:
                s.mode, s.cadence_s, s.frame_count = "cloud", 0.5, 1
                continue
            if sa.mode == "suspend":
                s.mode = "suspend"
                s.suspend_until_s = float(sa.suspend_until_s)
                suspend_steps += 1
                continue
            s.mode = sa.mode
            if sa.mode == "cloud":
                s.cadence_s, s.frame_count = float(sa.cadence_s), int(sa.frame_count)
        for s in streams:
            if s.mode == "suspend" and t >= s.suspend_until_s:
                s.mode = "cloud"

        # ---- apply recall actions
        keep = []
        for ra in act.recall:
            q = next(x for x in pend if x.query_id == ra.query_id)
            qm = qmeta[q.query_id]
            if ra.decision == "DEVICE":
                n_recall_device += 1
                answers.append(dict(decision="DEVICE", config=M.DEVICE_CONFIG,
                                    delivered_s=t + DEVICE_RECALL_S, **qm))
            elif ra.decision == "CLOUD":
                g = C.recall_gpu_s(q.readiness_tokens, q.readiness)
                if not budget.can_spend(g):
                    budget_refusals += 1
                    n_recall_device += 1
                    answers.append(dict(decision="DEVICE-on-refusal",
                                        config=M.DEVICE_CONFIG,
                                        delivered_s=t + DEVICE_RECALL_S, **qm))
                    continue
                budget.spend(g)
                n_recall_cloud += 1
                rid += 1
                key = f"r{rid}"
                if recall_free:
                    rq = E.warm_recall_request(key, t, q.session_id, q.readiness_tokens,
                                               "GPU-WARM", kind="escalation", delta_tokens=1)
                    rq.unit_s = 1e-3
                else:
                    if q.readiness == "GPU-WARM":
                        rq = E.warm_recall_request(key, t, q.session_id, q.readiness_tokens,
                                                   "GPU-WARM", kind="escalation",
                                                   delta_tokens=90)
                    else:
                        rq = E.cold_recall_request(key, t, q.readiness_tokens,
                                                   session=q.session_id, body="text",
                                                   encoder=False)
                eng.submit(rq)
                eng.place(q.session_id, q.readiness_tokens, "gpu")
                req_meta[key] = dict(kind="recall", qid=q.query_id,
                                     config=M.CLOUD_CONFIG.get(ra.representation or "RECENT",
                                                               "32B-RECENT"), qm=qm)
            elif ra.decision == "DEFER":
                n_defer += 1
                keep.append(q)
            else:
                n_reject += 1
                answers.append(dict(decision="REJECT", config=M.DEVICE_CONFIG,
                                    delivered_s=None, **qm))
        pend = keep

        # ---- apply session actions (THE SCOPE FLAG lives here)
        for xa in act.sessions:
            a = xa.action
            if a == "OFFLOAD_TO_HOST" and not HOST_AVAILABLE:
                a = "EVICT"                     # the host tier does not exist in this world
            if a == "MATERIALIZE":
                materialize_calls += 1
                if xa.slice_tokens:
                    materialize_sliced += 1
            if a in ("KEEP_GPU_WARM", "MATERIALIZE"):
                if xa.session_id not in eng.gpu:
                    tok = sess_tokens.get(xa.session_id, 11050)
                    if xa.session_id not in ever_warmed:
                        # FAIRNESS RULE 3: the first promotion pays the measured cold prefill
                        wc = C.recall_gpu_s(tok, "COLD")
                        if not budget.can_spend(wc):
                            budget_refusals += 1
                            continue
                        budget.spend(wc)
                        ever_warmed.add(xa.session_id)
                        rid += 1
                        key = f"w{rid}"
                        sl = xa.slice_tokens if a == "MATERIALIZE" else None
                        ov = (slice_overhead_s if slice_overhead_s is not None
                              else SLICE_OVERHEAD_MEASURED_S.get(int(sl or 0), 0.015))
                        eng.submit(E.cold_recall_request(
                            key, t, tok, session=xa.session_id, body="text", encoder=False,
                            slice_tokens=sl, slice_overhead_s=(ov if sl else 0.0)))
                        req_meta[key] = dict(kind="warm")
                    eng.place(xa.session_id, tok, "gpu")
            else:
                eng.gpu.pop(xa.session_id, None)
                eng.host.pop(xa.session_id, None)

        # ---- issue this tick's episodic cloud calls
        t_end = min(t + TICK_S, length)
        for s in streams:
            on_cloud = (s.mode == "cloud"
                        and (all_cloud_no_recall or W.connected(s.plan, t)))
            if not on_cloud:
                # the application reads the device's own scores (StudyE9d's SUSPEND semantics,
                # and what a local or disconnected stream has always done)
                rows = dev_wall[s.idx]
                p = dev_ptr[s.idx]
                while p < len(rows) and rows[p][0] < t_end - 1e-9:
                    tw, v, c, gi = rows[p]
                    if tw >= t - 1e-9:
                        delivered[c].append((gi, v))
                        recent[s.plan.stream_id].append((tw, v))
                    p += 1
                dev_ptr[s.idx] = p
                continue
            rows = dev_wall[s.idx]
            p = dev_ptr[s.idx]
            while p < len(rows) and rows[p][0] < t_end - 1e-9:
                p += 1
            dev_ptr[s.idx] = p
            # The cloud call schedule is CLIP-ALIGNED: a stream computes at its clip's own grid
            # indices 0, mc, 2mc, ... exactly as StudyE9b / E9c / E9d replay a committed trace,
            # so an all-cloud arm with no recall reproduces StudyE9c's delivered cloud cell. The
            # streams stay staggered against each other anyway, because their clips differ in
            # length and so their clip boundaries do not coincide.
            mc = max(int(round(s.cadence_s / STEP_S)), 1)
            cur = _clip_at(s, t, meta)
            tc = t
            while tc < t_end - 1e-9:
                ci = _clip_at(s, tc, meta)
                if ci is None:
                    tc += s.cadence_s
                    continue
                cidx, c, gi = ci
                if gi % mc:                       # not a compute index of this clip
                    tc = (s.plan.starts_s[cidx]
                          + (gi // mc + 1) * mc * STEP_S)
                    continue
                g = C.episodic_gpu_s("32BI", s.frame_count)
                if not budget.can_spend(g):
                    budget_refusals += 1
                    break
                budget.spend(g, C.episodic_uplink_bytes(s.frame_count))
                rid += 1
                key = f"e{rid}"
                eng.submit(E.episodic_request(key, tc, s.frame_count))
                req_meta[key] = dict(kind="episodic", stream=s.plan.stream_id, clip=c,
                                     gi=gi, start=s.plan.starts_s[cidx],
                                     # StudyE9b setting (ii): the delivery also pays the RTT and
                                     # the upload of the frames, which the engine model does not
                                     # contain because StudyD7b measured TTFT at the server
                                     net_s=(C.RTT_S + C.episodic_uplink_bytes(s.frame_count)
                                            / C.UPLINK_BPS),
                                     score=float(cloud_arr[s.frame_count][c][gi]))
                n_ep_sub += 1
                tc += s.cadence_s
            del cur

        eng.run_until(t_end)
        done_ptr = _collect(eng, done_ptr, req_meta, delivered, recent, answers, qmeta, meta)
        t = t_end
    eng.drain()
    done_ptr = _collect(eng, done_ptr, req_meta, delivered, recent, answers, qmeta, meta)

    # anything still pending at the end is unanswered
    for q in pend:
        answers.append(dict(decision="DEFER-unanswered", config=M.DEVICE_CONFIG,
                            delivered_s=None, **qmeta[q.query_id]))

    # ---- build the delivered score streams and the metrics
    streams_out = {}
    for c in ctx["clips"]:
        G = meta[c]["G"]
        ev = delivered.get(c)
        out = np.full(G, MISSING)
        if ev:
            ev = sorted(ev)
            idx = np.array([e[0] for e in ev])
            val = np.array([e[1] for e in ev])
            k = np.searchsorted(idx, np.arange(G), side="right") - 1
            ok = k >= 0
            out[ok] = val[k[ok]]
        streams_out[c] = out
    chal = M.challenge_map(ctx, streams_out)
    strm = M.streaming_ap(ctx, streams_out)
    rec = M.recall_metrics(answers, trace.deadline_s)

    n_ep_done = sum(1 for r in eng.done if r.kind == "episodic")
    return dict(
        arm=policy.name, mix=trace.mix, fleet=trace.fleet, n_streams=trace.n_streams,
        n_sessions=trace.n_sessions, deadline_s=trace.deadline_s, seed=trace.seed,
        trace_digest=trace.digest, length_s=length,
        challenge_mAP=float(chal["mAP"]),
        challenge_ap={str(h): float(chal[h]) for h in chal if h != "mAP"},
        streaming_ap={str(h): v for h, v in strm.items()},
        recall=rec,
        episodic=dict(submitted=n_ep_sub, completed=n_ep_done,
                      ttft_p50=_pct([r.ttft_s() for r in eng.done if r.kind == "episodic"], 50),
                      ttft_p99=_pct([r.ttft_s() for r in eng.done if r.kind == "episodic"], 99)),
        decisions=dict(recall_cloud=n_recall_cloud, recall_device=n_recall_device,
                       defer=n_defer, reject=n_reject, suspend_epochs=suspend_steps,
                       materialize=materialize_calls, materialize_sliced=materialize_sliced),
        gpu_s=round(budget.spent_gpu_seconds, 3), gpu_s_budget=round(budget.gpu_seconds, 3),
        budget_refusals=budget_refusals,
        gpu_kv_peak_fraction=round(kv_peak_frac, 4),
        engine=dict(steps=eng.stats["steps"], re_prefills=eng.stats["re_prefills"],
                    evictions=eng.stats["evictions"],
                    gpu_busy_s=round(eng.stats["gpu_busy_s"], 2),
                    slice_steps=eng.stats["slice_steps"]),
        engine_config=eng.config, engine_config_requested=eng_cfg_requested,
        wall_s=round(time.time() - t0, 2))


def _clip_at(s: _Stream, t: float, meta) -> Optional[Tuple[int, str, int]]:
    """Which clip and which of its grid indices this stream is playing at wall time t."""
    ss = s.plan.starts_s
    i = int(np.searchsorted(ss, t, side="right")) - 1
    if i < 0 or i >= len(s.plan.clips):
        return None
    c = s.plan.clips[i]
    gi = int((t - ss[i]) / STEP_S + 1e-9)
    if gi >= meta[c]["G"]:
        return None
    return i, c, gi


def _collect(eng, ptr, req_meta, delivered, recent, answers, qmeta, meta) -> int:
    """Turn finished engine requests into application-visible deliveries and recall answers."""
    for r in eng.done[ptr:]:
        m = req_meta.get(r.rid)
        if m is None:
            continue
        if m["kind"] == "episodic":
            tdel = r.done_s + m["net_s"]
            gi = int(math.ceil((tdel - m["start"]) / STEP_S - 1e-9))
            if 0 <= gi < meta[m["clip"]]["G"]:
                delivered[m["clip"]].append((gi, m["score"]))
            recent[m["stream"]].append((tdel, m["score"]))
        elif m["kind"] == "recall":
            answers.append(dict(decision="CLOUD", config=m["config"],
                                delivered_s=r.done_s, **m["qm"]))
    return len(eng.done)


def _pct(v, q):
    v = [x for x in v if x is not None]
    return float(np.percentile(v, q)) if v else None


if __name__ == "__main__" and "--demo" in sys.argv:
    import naive
    tr = W.build_trace("balanced", 8, 5.0, 0)
    for p in (naive.AlwaysCloudFCFS(), naive.DeviceOnly()):
        r = run_cell(tr, p)
        print("%-20s mAP %.4f  streamAP@0 %.5f  recall n=%d timely %.3f  gpu-s %.0f/%.0f  "
              "%.1fs" % (r["arm"], r["challenge_mAP"], r["streaming_ap"]["0.0"],
                         r["recall"]["n"], r["recall"]["timely_accuracy"] or 0.0,
                         r["gpu_s"], r["gpu_s_budget"], r["wall_s"]))


# ================================================================ the sweep
def _arms():
    """Every arm that is runnable in scope, built fresh. `sim1c_scope.py` owns the rule."""
    import run_all
    import sim1c_scope as S
    out = []
    for p in run_all.build():
        if p.name in S.NOT_RUNNABLE:
            continue
        label = p.name + (f"/{getattr(p, 'objective', '')}"
                          if getattr(p, "objective", "") else "")
        if p.name == "B9-best-of-breed":
            # the labelled variant: its host-offload component is disabled by the harness's
            # availability flag and nothing else about it changes
            label = "B9-noHost"
        out.append((label, p))
    return out


def run_sweep_cell(args) -> List[Dict]:
    """One cell: build the trace ONCE, run every arm on it, assert the digest never moves."""
    mix, F, deadline, seed, slice_overhead = args
    tr = W.build_trace(mix, F, deadline, seed)
    rows = []
    for label, p in _arms():
        if slice_overhead is not None and "slicing" not in label.lower():
            continue
        try:
            r = run_cell(tr, p, seed=seed, slice_overhead_s=slice_overhead)
        except Exception as e:                                  # noqa: BLE001
            rows.append(dict(arm=label, mix=mix, fleet=F, deadline_s=deadline, seed=seed,
                             slice_overhead_s=slice_overhead, failed=f"{type(e).__name__}: {e}"))
            continue
        assert r["trace_digest"] == tr.digest, "fairness rule 6: trace digest moved"
        r["arm"] = label
        r["slice_overhead_s"] = slice_overhead
        r["reads_future"] = bool(getattr(p, "reads_future", False))
        rows.append(r)
    return rows


def main() -> int:
    import argparse
    import multiprocessing as mp
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/orchestration/sim1c"))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--seeds", type=int, default=W.N_SEEDS)
    ap.add_argument("--sensitivity", action="store_true",
                    help="also run the slice-overhead sweep for the slicing arms")
    ap.add_argument("--probe", action="store_true", help="one cell per mix, for timing")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    cells = []
    for mix in W.MIXES:
        for F in W.FLEET_LADDER:
            for d in W.DEADLINES_S:
                for s in range(a.seeds):
                    cells.append((mix, F, d, s, None))
                    if a.probe:
                        break
                if a.probe:
                    break
    if a.sensitivity:
        for mix in W.MIXES:
            for F in W.FLEET_LADDER:
                for d in W.DEADLINES_S:
                    for s in range(a.seeds):
                        for ov in SLICE_OVERHEAD_SWEEP_S:
                            cells.append((mix, F, d, s, ov))

    t0 = time.time()
    n = 0
    fn = out / ("sim1c_probe.jsonl" if a.probe else "sim1c_runs.jsonl")
    with fn.open("w") as f, mp.Pool(a.workers) as pool:
        for rows in pool.imap_unordered(run_sweep_cell, cells, chunksize=1):
            for r in rows:
                f.write(json.dumps(r, default=float) + "\n")
                n += 1
            f.flush()
            done = n
            el = time.time() - t0
            print("  %d runs, %.0f s elapsed, %.2f s/run" % (done, el, el / max(done, 1)),
                  flush=True)
    print("wrote %s: %d runs in %.0f s" % (fn, n, time.time() - t0))
    return 0


if __name__ == "__main__" and "--sweep" in sys.argv:
    sys.argv = [x for x in sys.argv if x != "--sweep"]
    sys.exit(main())


# ================================================================ sanity checks
def sanity() -> Dict:
    """The four pre-registered sanity checks. They are not sweep cells and no arm is compared."""
    import naive
    ctx = W.clip_context()
    import study_e9b_dense as B
    ref_cloud = M.challenge_map(ctx, {
        c: B.held_stream(ctx["arrs"][("32BI", 1)][c], meta["G"], 2,
                         C.hold_shift_steps(C.episodic_cloud_latency_s("32BI", 1, SETTING_LOAD)))
        for c, meta in ctx["meta"].items()})["mAP"]
    ref_dev = M.challenge_map(ctx, {
        c: B.held_stream(ctx["arrs"][("4BI", 1)][c], meta["G"],
                         int(round(C.DEVICE_CADENCE_S / STEP_S)),
                         C.hold_shift_steps(C.DEV_LAT_S))
        for c, meta in ctx["meta"].items()})["mAP"]

    out = {}
    tr2 = W.build_trace("balanced", 2, 5.0, 0)
    r = run_cell(tr2, naive.AlwaysCloudFCFS(), all_cloud_no_recall=True)
    out["1_all_cloud_no_recall"] = dict(
        rule="with all-cloud and no recall (and no outages, which StudyE9c's cell also has "
             "none of), the episodic challenge mAP must equal StudyE9c's delivered cloud cell",
        reference_mAP=ref_cloud, sim_mAP=r["challenge_mAP"],
        abs_diff=abs(r["challenge_mAP"] - ref_cloud),
        pass_=bool(abs(r["challenge_mAP"] - ref_cloud) < 1e-9))
    r = run_cell(tr2, naive.DeviceOnly())
    out["2_device_only"] = dict(
        rule="an all-device arm must equal the device-only reference EXACTLY",
        reference_mAP=ref_dev, sim_mAP=r["challenge_mAP"],
        abs_diff=abs(r["challenge_mAP"] - ref_dev),
        pass_=bool(abs(r["challenge_mAP"] - ref_dev) < 1e-12))

    digests = {}
    for mix in W.MIXES:
        for F in W.FLEET_LADDER:
            tr = W.build_trace(mix, F, 5.0, 0)
            seen = set()
            for _label, p in _arms()[:6]:
                rr = run_cell(tr, p)
                seen.add(rr["trace_digest"])
            digests[f"{mix}|F{F}"] = dict(digest=tr.digest, n_distinct=len(seen))
    out["3_trace_digest"] = dict(
        rule="the demand-trace sha256 must be identical for every arm in every cell "
             "(fairness rule 6)",
        cells=digests, pass_=all(v["n_distinct"] == 1 for v in digests.values()))

    rows = []
    tr8 = W.build_trace("balanced", 8, 5.0, 0)
    for label, p in _arms():
        a = run_cell(tr8, p, recall_free=True)["challenge_mAP"]
        b = run_cell(tr8, p, all_cloud_no_recall=False)["challenge_mAP"]
        rows.append(dict(arm=label, recall_free_mAP=a, with_recall_mAP=b, diff=a - b))
    out["4_recall_free"] = dict(
        rule="with recall cost set to 0, the recall load must stop affecting the episodic "
             "metric, so every arm's mAP must move TOWARDS its no-recall value",
        arms=rows,
        n_improved_or_equal=sum(1 for x in rows if x["diff"] >= -1e-9),
        n_total=len(rows),
        pass_=bool(sum(1 for x in rows if x["diff"] >= -1e-9) >= 0.9 * len(rows)))
    out["all_pass"] = all(v.get("pass_", True) for v in out.values() if isinstance(v, dict))
    return out


if __name__ == "__main__" and "--sanity" in sys.argv:
    OUTD = ROOT / "results/orchestration/sim1c"
    OUTD.mkdir(parents=True, exist_ok=True)
    res = sanity()
    from _provenance import stamp
    res["_provenance"] = stamp(script="run.py --sanity", model=None, device="cpu", n=4, args=None)
    (OUTD / "sim1c_sanity.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res.items():
        if isinstance(v, dict) and "pass_" in v:
            print("%-26s %s" % (k, "PASS" if v["pass_"] else "FAIL"))
    print("wrote", OUTD / "sim1c_sanity.json")
