#!/usr/bin/env python3
"""StudySIM1d Part C - StudySLICE1 Part B's orchestrator policies, in the simulator.

CPU ONLY. Nothing here runs a model.

P0, P1, P2, P3_1024, P3_2048 and P4 are mirrored from `experiments/cost/study_slice1_live.py`,
which is the DEFINITION. The line ranges mirrored are named in `MIRRORED_FROM` below and in the
report, and the rules are reproduced here without reinterpretation: the same single-cold-request
admission queue, the same gap wait, the same slack guard with the same predicted-time formula,
the same 5-ms alignment and 0.25-s margin, the same 1,024 / 2,048-token slices.

StudySLICE1 Part B is HELD-OUT GROUND TRUTH: it was measured live on the H100 and the simulator
has never seen it. **No parameter in this file or anywhere else in the simulator is fitted or
changed using any Part B number.** Every workload constant comes from StudySLICE1 PART A (the
gate, `results/cost/study_slice1/slice1_gate_results.json`), which StudySIM1c already used, or
from the simulator's own committed calibration.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import engine as E                                                     # noqa: E402

MIRRORED_FROM = {
    "source": "experiments/cost/study_slice1_live.py",
    "P0 pass-through": "l. 204 (no admission lock) and l. 221; docstring l. 22",
    "P1 EDF admission, one cold request in the engine": "l. 204-205, 231-232 and l. 267 "
                                                        "(asyncio.Lock is FIFO = EDF for equal "
                                                        "relative deadlines); docstring l. 23-24",
    "P2 blocking-aware guard": "l. 211-213 calling wait_gap, l. 164-176; docstring l. 25-26",
    "P3_n slice alignment": "l. 214-215 calling align_after_due, l. 179-186; docstring l. 27-30",
    "P4 = P3(2048) + per-slice slack guard": "l. 216-218 (rem = sum of the remaining parts' "
                                             "predicted times); docstring l. 31-33",
    "slice construction": "l. 118-135 (k = max(1, n // TOK_PER_FRAME); the question rides the "
                          "last slice; per-part predicted time = its new tokens / the session's "
                          "Part A monolithic rate)",
    "constants": "l. 68 LADDER, l. 70 COND, l. 71 DEADLINES, l. 72 EP_DEADLINE = 0.45, "
                 "l. 73 ALIGN = 0.005, l. 74 P4_N = 2048, l. 79 LAT_FACTOR, l. 80 SLACK_MARGIN",
    "answer time": "l. 236 t_ans = last part's send time + its TTFT, minus the scheduled arrival",
    "window": "study_e10b_mixed.py l. 74 BUDGET and l. 76 DUR / DISCARD / DRAIN_CAP",
}

# ---------------------------------------------------------------- Part B's conditions (workload)
COND: Dict[str, Tuple[str, int, float]] = {
    "C0": ("GPU", 0, 0.0), "C1a": ("GPU", 0, 0.05), "C1b": ("GPU", 0, 0.10),
    "C4": ("HOST", 8, 0.10),
}
LADDER = (10, 20, 25, 30, 40)
C0_LEVELS = (25, 40)
POLICIES = ("P0", "P1", "P2", "P3_1024", "P3_2048", "P4")
DEADLINE_S = 10.0
EP_BUDGET_S = 0.45
ALIGN_S = 0.005
LAT_FACTOR = {None: 1.321, 2048: 1.373}
SLACK_MARGIN_S = 0.25
P4_N = 2048
TOK_PER_FRAME = 90
HDR_TOK = 31
PEAK_REQ_S = 15.10
DISCARD_S, WINDOW_S, DRAIN_CAP_S = 30.0, 240.0, 300.0
# StudySLICE1 Part B's own warm traffic at C4 is StudyRH7's, the same as StudyE10b's k = 8 cell.
APPEND_PERIOD_S = 10.0
ESCALATION_EVERY = 9

_PROFILE: Optional[Dict] = None


def part_a_profile() -> Dict:
    """Every cold-recall constant, from StudySLICE1 PART A only (the gate), never Part B."""
    global _PROFILE
    if _PROFILE is not None:
        return _PROFILE
    g = json.loads((ROOT / "results/cost/study_slice1/slice1_gate_results.json").read_text())
    ss = [s for s in g["sessions"] if s["target"] == 11000]
    med = lambda f: float(np.median([f(s) for s in ss]))              # noqa: E731
    chains = {}
    for n in ("1024", "2048"):
        sel = [s for s in ss if n in s.get("chains", {}) and s["chains"][n].get("complete")]
        chains[int(n)] = dict(
            n_sessions=len(sel),
            engine_ratio=float(np.median([s["chains"][n]["ratio"] for s in sel])),
            n_slices=float(np.median([s["chains"][n]["n_slices"] for s in sel])),
            nonengine_total_s=float(np.median([s["chains"][n]["wall_minus_pauses_s"]
                                               - s["chains"][n]["engine_s"] for s in sel])))
        chains[int(n)]["nonengine_per_slice_s"] = (chains[int(n)]["nonengine_total_s"]
                                                   / max(chains[int(n)]["n_slices"], 1))
    _PROFILE = dict(
        source="results/cost/study_slice1/slice1_gate_results.json (StudySLICE1 PART A)",
        n_sessions=len(ss),
        prompt_tokens=int(round(med(lambda s: s["prompt_tokens"]))),
        n_frames=int(round(med(lambda s: s["n_frames"]))),
        mono_rate_tok_s=med(lambda s: s["mono_rate_tok_s"]),
        mono_engine_s=med(lambda s: s["mono_engine_s"]),
        mono_ttft_s=med(lambda s: s["mono_ttft_s"]),
        mono_nonengine_s=med(lambda s: s["mono_ttft_s"] - s["mono_engine_s"]),
        chains=chains)
    return _PROFILE


# ---------------------------------------------------------------- the cold recall's parts
@dataclass
class Part:
    frames: int
    new_tokens: int
    compute_tokens: float
    pred_s: float
    frontend_s: float
    final: bool


def build_parts(policy: str, prof: Dict) -> List[Part]:
    """study_slice1_live.build_cold l. 118-135, with Part A's measured chain costs."""
    n = {"P3_1024": 1024, "P3_2048": 2048, "P4": P4_N}.get(policy)
    F = prof["n_frames"]
    rate = prof["mono_rate_tok_s"]
    if n is None:
        new = HDR_TOK + TOK_PER_FRAME * F
        return [Part(F, new, float(new), new / rate, prof["mono_nonengine_s"], True)]
    k = max(1, n // TOK_PER_FRAME)
    ratio = prof["chains"][n]["engine_ratio"]
    fe = prof["chains"][n]["nonengine_per_slice_s"]
    out, start = [], 0
    while start < F:
        ch = min(k, F - start)
        last = (start + ch) >= F
        new = TOK_PER_FRAME * ch + (HDR_TOK if start == 0 else 0)
        out.append(Part(ch, new, new * ratio, new / rate, fe, last))
        start += ch
    return out


# ---------------------------------------------------------------- the orchestrator
def _next_ep_due(ep_abs: Sequence[float], now: float) -> Optional[float]:
    """study_slice1_live.next_ep_due, l. 157-161."""
    i = int(np.searchsorted(ep_abs, now, side="left"))
    return float(ep_abs[i]) if i < len(ep_abs) else None


def _wait_gap_release(now: float, pred: float, deadline_start: float,
                      ep_abs: Sequence[float]) -> Tuple[float, str]:
    """study_slice1_live.wait_gap, l. 164-176, as a release TIME rather than an await."""
    t = now
    for _ in range(100000):
        if t >= deadline_start:
            return t, "slack"
        nxt = _next_ep_due(ep_abs, t)
        if nxt is None or nxt - t > pred:
            return t, "gap"
        t = min(nxt + ALIGN_S, deadline_start)
    return t, "gap"


def _align_release(now: float, pred: float, ep_abs: Sequence[float]) -> Tuple[float, str]:
    """study_slice1_live.align_after_due, l. 179-186."""
    nxt = _next_ep_due(ep_abs, now)
    if nxt is not None and nxt - now <= pred:
        return nxt + ALIGN_S, "align"
    return now, "align"


@dataclass
class Recall:
    rid: str
    arrival_s: float
    parts: List[Part]
    deadline_s: float
    idx: int = 0
    submitted: Optional[object] = None      # the engine Request now in flight, if any
    done_s: Optional[float] = None
    holds_s: float = 0.0
    released_by: List[str] = field(default_factory=list)
    n_submitted: int = 0
    trace: List[Dict] = field(default_factory=list)


def _release_time(policy: str, rc: Recall, now: float,
                  ep_abs: Sequence[float]) -> Tuple[float, str]:
    part = rc.parts[rc.idx]
    if policy in ("P0", "P1"):
        return now, "none"
    if policy == "P2":
        start = rc.deadline_s - (part.pred_s * LAT_FACTOR[None] + SLACK_MARGIN_S)
        return _wait_gap_release(now, part.pred_s, start, ep_abs)
    if policy in ("P3_1024", "P3_2048"):
        return _align_release(now, part.pred_s, ep_abs)
    if policy == "P4":
        rem = sum(p.pred_s for p in rc.parts[rc.idx:])
        start = rc.deadline_s - (rem * LAT_FACTOR[P4_N] + SLACK_MARGIN_S)
        return _wait_gap_release(now, part.pred_s, start, ep_abs)
    raise ValueError(policy)


# ---------------------------------------------------------------- one cell
def run_cell(cond: str, policy: str, level_pct: int, seed_level_index: int = 0,
             host_mode_cost_s: float = 0.0, overlap_step_cost_s: float = 0.0,
             cold_rate_tok_s: Optional[float] = None, trace: bool = False) -> Dict:
    """One StudySLICE1 Part B cell under one policy. Part B's ladder, budget, discard and window
    lengths and cold-session mix; the simulator's own engine, unchanged."""
    prof = part_a_profile()
    kv, k, r = COND[cond]
    eng = E.Engine(config="P0", kv_mode=kv, host_mode_cost_s=host_mode_cost_s,
                   overlap_step_cost_s=overlap_step_cost_s)
    total_s = DISCARD_S + WINDOW_S
    rate = PEAK_REQ_S * level_pct / 100.0
    # the simulator's own committed cold re-prefill rate at 11k (StudyRH5 Part A), unless the
    # declared sensitivity overrides it with Part A's own measured monolithic rate
    cold_rate = float(cold_rate_tok_s or E.RATE_COLD_BY_SIZE[11050])

    rng = np.random.default_rng(seed_level_index)
    ep_times: List[float] = []
    t = 0.0
    while t < total_s:
        t += rng.exponential(1.0 / rate)
        if t < total_s:
            ep_times.append(t)
    for i, ta in enumerate(ep_times):
        eng.submit(E.episodic_request(f"ep{i}", ta, 1))
    ep_abs = np.asarray(ep_times, dtype=float)

    recalls: List[Recall] = []
    if r > 0:
        rc_rng = np.random.default_rng(1000 + seed_level_index)
        t, i = 0.0, 0
        while True:
            t += rc_rng.exponential(1.0 / r)
            if t >= total_s:
                break
            recalls.append(Recall(f"cold{i}", t, build_parts(policy, prof), t + DEADLINE_S))
            i += 1

    # C4's warm traffic, exactly as calibrate.py builds StudyE10b's k = 8 cell
    warm_queue: List[Tuple[float, str, str]] = []
    sess_start_s: Dict[str, float] = {}
    for j in range(k):
        sid = f"warm{j}"
        sess_start_s[sid] = -(j + 1) / max(k, 1) * 600.0
        htok = int(min(E.D2_TOKENS_PER_S * max(0.0 - sess_start_s[sid], 0.0),
                       E.D2_MAX_HISTORY_TOKENS))
        eng.place(sid, htok, "gpu" if kv == "GPU" else "host")
        off = (j / max(k, 1)) * APPEND_PERIOD_S
        m, tt = 0, off
        while tt < total_s:
            warm_queue.append((tt, sid, "escalation"
                               if (m % ESCALATION_EVERY == ESCALATION_EVERY - 1) else "append"))
            m += 1
            tt += APPEND_PERIOD_S
    warm_queue.sort()

    req_of: Dict[str, Recall] = {}
    wi, guard = 0, 0
    while guard < 4_000_000:
        guard += 1
        now = eng.clock

        # ---- collect finished slices
        for rc in recalls:
            if rc.submitted is not None and rc.submitted.done_s is not None:
                rc.idx += 1
                if rc.idx >= len(rc.parts):
                    rc.done_s = rc.submitted.done_s
                rc.submitted = None

        # ---- the orchestrator
        wake: Optional[float] = None
        lock_free = not any(rc.submitted is not None or (0 < rc.idx < len(rc.parts))
                            for rc in recalls)
        for rc in recalls:
            if rc.done_s is not None or rc.arrival_s > now + 1e-12:
                if rc.done_s is None and rc.arrival_s > now:
                    wake = rc.arrival_s if wake is None else min(wake, rc.arrival_s)
                continue
            if rc.submitted is not None:
                continue
            if policy != "P0":
                # P1-P4: ONE cold request in the engine at a time, FIFO by arrival
                if not lock_free and rc.idx == 0:
                    continue
            rel, why = _release_time(policy, rc, now, ep_abs)
            if rel > now + 1e-9:
                wake = rel if wake is None else min(wake, rel)
                continue
            part = rc.parts[rc.idx]
            rid = f"{rc.rid}s{rc.idx}"
            req = E.Request(
                rid=rid, kind=("cold" if len(rc.parts) == 1 else "slice"), arrival_s=now,
                prompt_tokens=prof["prompt_tokens"], compute_tokens=part.compute_tokens,
                session=rc.rid, frontend_s=part.frontend_s, rate_tok_s=cold_rate,
                meta=dict(recall=rc.rid, slice=rc.idx, final=part.final))
            eng.submit(req)
            rc.submitted = req
            rc.n_submitted += 1
            rc.holds_s += max(rel - rc.arrival_s if rc.idx == 0 else 0.0, 0.0)
            rc.released_by.append(why)
            req_of[rid] = rc
            if trace:
                rc.trace.append(dict(slice=rc.idx, now_s=round(now, 4),
                                     released_by=why, pred_s=round(part.pred_s, 4),
                                     frames=part.frames, new_tokens=part.new_tokens,
                                     compute_tokens=round(part.compute_tokens, 1),
                                     frontend_s=round(part.frontend_s, 4),
                                     next_episodic_due_s=_next_ep_due(ep_abs, now),
                                     slack_start_s=round(
                                         rc.deadline_s - (sum(p.pred_s for p in rc.parts[rc.idx:])
                                                          * LAT_FACTOR[P4_N] + SLACK_MARGIN_S), 4)
                                     if policy == "P4" else None))
            if policy != "P0":
                lock_free = False

        # ---- warm injections, as calibrate.py does them
        while wi < len(warm_queue) and warm_queue[wi][0] <= eng.clock + 1e-9:
            ta, sid, kind = warm_queue[wi]
            wi += 1
            htok = int(min(E.D2_TOKENS_PER_S * max(ta - sess_start_s[sid], 0.0),
                           E.D2_MAX_HISTORY_TOKENS))
            ready = "HOST-WARM" if kv == "HOST" else "GPU-WARM"
            rq = E.warm_recall_request(f"{sid}-{kind}{ta:.1f}", ta, sid, htok, ready, kind=kind,
                                       delta_tokens=(E.WARM_DELTA_TOKENS if kind == "append"
                                                     else 90))
            eng.submit(rq)
            eng.place(sid, htok, "host" if ready == "HOST-WARM" else "gpu")

        eng._admit_visible()
        if eng.waiting or eng.running:
            eng.step()
            continue
        cands = [x for x in (eng.next_event_s(),
                             warm_queue[wi][0] if wi < len(warm_queue) else None,
                             wake) if x is not None]
        if not cands:
            break
        nxt = min(cands)
        if nxt <= eng.clock + 1e-12:
            eng.clock += 1e-6                       # never stall
        else:
            eng.clock = nxt
        if eng.clock > total_s + DRAIN_CAP_S:
            break

    # ---- metrics, StudyE10b / StudySLICE1 Part B definitions
    ep = [x for x in eng.done if x.kind == "episodic" and DISCARD_S <= x.arrival_s < total_s]
    unfinished = [x for x in (eng.waiting + eng.running + [y[2] for y in eng._pending])
                  if x.kind == "episodic" and x.arrival_s >= DISCARD_S]
    lat = sorted(x.ttft_s() for x in ep)
    if unfinished:
        allv = lat + [float("inf")] * len(unfinished)
        p99 = float(allv[min(int(math.ceil(0.99 * len(allv))) - 1, len(allv) - 1)]) \
            if lat else float("inf")
        p50 = float(np.percentile(lat, 50)) if lat else None
        p90 = float(np.percentile(lat, 90)) if lat else None
    else:
        p50 = float(np.percentile(lat, 50)) if lat else None
        p90 = float(np.percentile(lat, 90)) if lat else None
        p99 = float(np.percentile(lat, 99)) if lat else None

    scored = [rc for rc in recalls if DISCARD_S <= rc.arrival_s < total_s]
    ans = [rc.done_s - rc.arrival_s for rc in scored if rc.done_s is not None]
    return dict(
        condition=cond, policy=policy, level_pct=level_pct, seed_level_index=seed_level_index,
        n_episodic=len(ep), n_unfinished=len(unfinished),
        p50_s=p50, p90_s=p90, p99_s=p99,
        meets_budget=bool(p99 is not None and p99 <= EP_BUDGET_S),
        cold_n=len(scored), cold_answered=len(ans),
        t_answer_p50=(float(np.percentile(ans, 50)) if ans else None),
        t_answer_p90=(float(np.percentile(ans, 90)) if ans else None),
        t_answer_max=(float(np.max(ans)) if ans else None),
        frac_5s=(float(np.mean([a <= 5.0 for a in ans])) if ans else None),
        frac_10s=(float(np.mean([a <= 10.0 for a in ans])) if ans else None),
        unanswered=len(scored) - len(ans),
        n_slices_per_recall=(float(np.mean([rc.n_submitted for rc in scored]))
                             if scored else None),
        hold_s_p50=(float(np.percentile([rc.holds_s for rc in scored], 50)) if scored else None),
        released_by=dict(zip(*np.unique([w for rc in scored for w in rc.released_by],
                                        return_counts=True))) if scored else {},
        engine=dict(eng.stats),
        traces=(_build_traces(scored, eng, req_of) if trace else None))


def _build_traces(scored, eng, req_of) -> List[Dict]:
    """Every slice with its hold, its release reason, its engine window, and every episodic
    call that overlapped it. CLAUDE.md Step 3 must be checkable by hand from this."""
    ep = [(x.visible_s, x.done_s, x.rid, x.arrival_s) for x in eng.done
          if x.kind == "episodic" and x.done_s is not None]
    out = []
    for rc in scored:
        if not rc.trace:
            continue
        rows = []
        for i, tr in enumerate(rc.trace):
            req = next((x for x in eng.done if x.rid == f"{rc.rid}s{i}"), None)
            a = None if req is None else req.visible_s
            b = None if req is None else req.done_s
            ov = ([dict(rid=r3, arrival_s=round(r4, 4), visible_s=round(e0, 4),
                        done_s=round(e1, 4))
                   for (e0, e1, r3, r4) in ep if a is not None and e0 < b and a < e1]
                  if a is not None else [])
            rows.append(dict(tr, submitted_s=(None if req is None else round(req.arrival_s, 4)),
                             visible_s=(None if a is None else round(a, 4)),
                             done_s=(None if b is None else round(b, 4)),
                             engine_steps=(None if req is None else req.steps),
                             n_episodic_overlapped=len(ov), episodic_overlapped=ov))
        out.append(dict(recall=rc.rid, arrival_s=round(rc.arrival_s, 4),
                        deadline_s=round(rc.deadline_s, 4),
                        answer_s=(None if rc.done_s is None
                                  else round(rc.done_s - rc.arrival_s, 4)),
                        n_slices=len(rc.parts), slices=rows))
    return out


def cell_median(cond: str, policy: str, level_pct: int, n_seeds: int = 5, **kw) -> Dict:
    """Part B's 5 arrival seeds; the MEDIAN p99 is reported with its min and max."""
    runs = [run_cell(cond, policy, level_pct,
                     seed_level_index=1000 * s + (LADDER.index(level_pct)
                                                  if level_pct in LADDER else 0), **kw)
            for s in range(n_seeds)]
    v = [x["p99_s"] for x in runs if x["p99_s"] is not None]
    fin = [x for x in v if not math.isinf(x)]
    out = dict(runs[0])
    out["p99_s"] = (float(np.median(v)) if v and len(fin) == len(v)
                    else (float("inf") if len(fin) < len(v) / 2.0 else float(np.median(fin))))
    out["p99_seeds"] = v
    out["p99_min"] = min(fin) if fin else None
    out["p99_max"] = max(fin) if fin else None
    out["meets_budget"] = bool(out["p99_s"] is not None and out["p99_s"] <= EP_BUDGET_S)
    for key in ("t_answer_p50", "t_answer_p90", "frac_5s", "frac_10s"):
        vals = [x[key] for x in runs if x[key] is not None]
        out[key] = float(np.median(vals)) if vals else None
    out["cold_n"] = int(sum(x["cold_n"] for x in runs))
    out["unanswered"] = int(sum(x["unanswered"] for x in runs))
    out["n_seeds"] = n_seeds
    out.pop("traces", None)
    return out


def capacity(cond: str, policy: str, levels=LADDER, **kw) -> Tuple[Optional[int], Dict[int, float]]:
    """Part B's rule: the highest ladder level whose episodic p99 meets 0.45 s, bottom-up,
    stopping at the first failure."""
    best, p99 = None, {}
    for lvl in levels:
        c = cell_median(cond, policy, lvl, **kw)
        p99[lvl] = c["p99_s"]
        if c["meets_budget"]:
            best = lvl
        else:
            break
    return best, p99
