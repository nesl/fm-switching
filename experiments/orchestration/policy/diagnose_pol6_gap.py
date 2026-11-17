#!/usr/bin/env python3
"""StudyPOL6-chain Part A: the inter-piece gap hypothesis, pre-checked on StudyENG1c Part D FIT.

THE HYPOTHESIS (StudyPOL5-engine section 3A, recorded there as an UNTESTED hypothesis). A chained
rebuild is a sequence of separate requests: piece k returns to the client, the client builds and
submits piece k+1, and piece k+1 re-enters the front end before the engine sees it. In that gap
the engine is free of the chain and can serve queued background work. A cost model that treats
the chain as contiguous occupancy charges background requests for blocking that did not happen,
which over-states the delay the chain imposes.

WHAT THIS SCRIPT DOES. It measures those gaps on StudyENG1c Part D's FIT pairs, counts the
background requests whose first token lands inside one, and compares that against where the
frozen pol4 model puts the same requests. It fits nothing.

DATA FENCE. FIT pairs only. The loader is `score_t0b.load_part_d_trials(split="fit")`, which
never constructs a holdout trial; the 120 ENG1c Part D HOLDOUT pairs were spent once by
StudyT0b's one-shot and are not read here.

DERIVED, NOT MEASURED. Per-request step membership is NOT in the ENG1c record. Every per-piece
engine time below is DERIVED by StudyENG1d's own method (experiments/cost/study_eng1d_analyse.py
docstring, "Action timing (engine)"), applied unchanged to ENG1c:
  * a piece's first scheduled time  t_sched = client first-token time - the plugin's prefill_time
    for that request id (`fin[...]["pf"]`, scheduled -> first token);
  * a piece's prefill end  t_end_eng = the time of the last step row at or before the client
    first-token time (+2 ms, ENG1d's own slack);
  * a step "carries other work" if its first-output computed tokens (`pts`[0]) are positive or it
    reports generation requests (`it`[3] > 0).
`it` is [iteration_index, num_ctx_requests, num_ctx_tokens, num_generation_requests,
num_generation_tokens, elapsed_ms, num_encoder_inputs, num_encoder_output_tokens, is_dummy]
(experiments/cost/eng1_statlog/eng1_statlog.py). The gap is therefore an ESTIMATE whose error is
one step boundary at each end; the per-gap step count is reported so a reader can bound it.

CLOCKS. ENG1c's client rows and the engine's step log carry the same wall clock (verified: for
every chained piece, t_first - pf lies strictly between t_submit and t_first). No calibration.

METRIC. Per-request attribution uses TTFT, because the gap mechanism acts on when a request
reaches its first token. Trial-level over-prediction is reported for BOTH of T0b's definitions
(latency sum, the ENG1c primary, and TTFT sum, the secondary).
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import trace_replay as tr
from .eng1_engine import EngineSim, make_sim
from .score_t0b import METRIC_FIELD, _measured_sum, _pred_value, load_part_d_trials

STEPS_DIR = "results/cost/study_eng1c/eng1c_steps"
OUT_PATH = "results/orchestration/study_pol6/pol6_partA_gap.json"
FIRST_TOKEN_SLACK_S = 0.002          # StudyENG1d's own slack on the last prefill step
CHAINED_ACTIONS = ("piece2048", "piece1024")

DERIVED_LABEL = (
    "DERIVED and FIT. Per-request step membership is not recorded by StudyENG1c; every per-piece "
    "engine time here is derived by StudyENG1d's attribution method (first scheduled time = "
    "client first-token time minus the plugin's prefill_time; prefill end = the last step row at "
    "or before the client first-token time). StudyENG1e-chain measures the membership directly. "
    "All pairs are StudyENG1c Part D FIT pairs; no HOLDOUT pair is read.")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


class Steps:
    """One ENG1c step log, indexed for window and last-at-or-before queries."""

    def __init__(self, path: Path):
        self.rows: List[Dict[str, Any]] = []
        self.fin: Dict[str, Dict[str, Any]] = {}
        with gzip.open(path, "rt") as fh:
            for line in fh:
                d = json.loads(line)
                for f in d.get("fin", []):
                    self.fin[str(f["id"])] = f
                if "it" in d:
                    self.rows.append(d)
        self.rows.sort(key=lambda r: r["t"])
        self.t = [float(r["t"]) for r in self.rows]

    def _bisect(self, x: float) -> int:
        lo, hi = 0, len(self.t)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.t[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def last_le(self, x: float) -> Optional[int]:
        i = self._bisect(x) - 1
        return i if i >= 0 else None

    def window(self, t0: float, t1: float) -> List[Dict[str, Any]]:
        """Step rows with t in (t0, t1]."""
        return self.rows[self._bisect(t0):self._bisect(t1)]

    def window_idx(self, t0: float, t1: float) -> List[int]:
        return list(range(self._bisect(t0), self._bisect(t1)))

    def dur(self, i: int) -> Optional[float]:
        """A step's wall duration is the difference of consecutive row times (StudyENG1d's own
        definition). The plugin's `elapsed_ms` is NOT the step's wall duration and is not used
        for it: on a monolithic 11k prefill its median is 0.03 ms."""
        return (self.t[i] - self.t[i - 1]) if i > 0 else None


def _carries_other_work(row: Dict[str, Any]) -> bool:
    pts = row.get("pts") or [0]
    return bool((pts[0] or 0) > 0 or (row["it"][3] or 0) > 0)


def piece_timing(st: Steps, pieces: Sequence[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """StudyENG1d's derived timing for every piece of one chain, in part order."""
    out = []
    for p in pieces:
        f = st.fin.get("chatcmpl-" + str(p["rid"]))
        if f is None or p.get("t_first") is None:
            return None
        i = st.last_le(float(p["t_first"]) + FIRST_TOKEN_SLACK_S)
        if i is None:
            return None
        out.append(dict(part_i=int(p.get("part_i") or 0), rid=str(p["rid"]),
                        t_submit=float(p["t_submit"]), t_first=float(p["t_first"]),
                        t_end_client=float(p["t_end"]),
                        t_sched=float(p["t_first"]) - float(f["pf"]),
                        t_end_eng=float(st.t[i]), pf_s=float(f["pf"]),
                        queued_s=float(f["q"]),
                        new_tokens=int(p.get("prompt_tokens", 0) or 0)
                        - int(p.get("cached_tokens", 0) or 0),
                        body_mb=float(p.get("body_mb") or 0.0)))
    return out


def measured_gaps(st: Steps, timing: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Between consecutive pieces: the window in which the engine is free of the chain, split
    into the client's own turnaround and the next piece's front-end window."""
    gaps = []
    for k in range(len(timing) - 1):
        a, b = timing[k], timing[k + 1]
        t0, t1 = a["t_end_eng"], b["t_sched"]
        rows = st.window(t0, t1)
        gaps.append(dict(
            after_part=a["part_i"], before_part=b["part_i"],
            t0=t0, t1=t1, gap_s=t1 - t0,
            client_turnaround_s=float(b["t_submit"]) - float(a["t_end_client"]),
            frontend_window_s=float(b["t_sched"]) - float(b["t_submit"]),
            engine_tail_s=float(a["t_end_client"]) - float(a["t_end_eng"]),
            n_steps_in_gap=len(rows),
            n_steps_with_other_work=sum(1 for r in rows if _carries_other_work(r)),
            other_prefill_tokens_in_gap=sum(int((r.get("pts") or [0])[0] or 0) for r in rows),
            next_piece_body_mb=b["body_mb"]))
    return gaps


def piece_step_composition(st: Steps, timing: Sequence[Dict[str, Any]],
                           pieces: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per piece, the steps the piece prefilled in and how much of each step was OTHER work.

    StudyENG1d's derived composition, applied unchanged: a step's other-request prefill tokens =
    the step row's first-output computed tokens (`pts`[0]) minus the piece's own computed tokens
    on its last step; the piece's tokens = step context tokens minus other. This is the direct
    test of whether the engine batches background prefill INTO a piece's own steps, which is the
    alternative to the inter-piece gap as an explanation (H-merge against H-gap)."""
    comp_by_rid = {str(p["rid"]): (int(p.get("prompt_tokens", 0) or 0)
                                   - int(p.get("cached_tokens", 0) or 0)) for p in pieces}
    out = []
    for tm in timing:
        idx = st.window_idx(tm["t_sched"], tm["t_end_eng"] + 1e-9)
        comp = comp_by_rid.get(tm["rid"], 0)
        steps = []
        for n, i in enumerate(idx):
            r = st.rows[i]
            first_out = int((r.get("pts") or [0])[0] or 0)
            last = (n == len(idx) - 1)
            other = first_out - (comp if last else 0)
            d = st.dur(i)
            if n == 0 and d is not None:
                # an engine idle before the piece: the step effectively starts at scheduling
                d = min(d, r["t"] - tm["t_sched"])
            steps.append(dict(t=r["t"], ctx_req=r["it"][1], ctx_tok=r["it"][2],
                              dec_req=r["it"][3], dur_s=d, elapsed_ms=r["it"][5],
                              first_out=first_out, other_prefill=other,
                              piece_tok=r["it"][2] - other))
        tot_other = sum(max(x["other_prefill"], 0) for x in steps)
        out.append(dict(part_i=tm["part_i"], rid=tm["rid"], n_steps=len(steps),
                        piece_new_tokens=comp,
                        n_steps_sharing=sum(1 for x in steps
                                            if x["other_prefill"] > 0 or x["dec_req"] > 0),
                        n_steps_other_prefill=sum(1 for x in steps if x["other_prefill"] > 0),
                        n_steps_decoding=sum(1 for x in steps if x["dec_req"] > 0),
                        other_prefill_tokens=tot_other,
                        max_ctx_req=max((x["ctx_req"] for x in steps), default=0),
                        prefill_span_s=tm["t_end_eng"] - tm["t_sched"], steps=steps))
    return out


def _in_any_gap(t: float, gaps: Sequence[Dict[str, Any]]) -> Optional[int]:
    for i, g in enumerate(gaps):
        if g["t0"] < t <= g["t1"]:
            return i
    return None


def pol4_sim_placement(trial: tr.Trial, sim: EngineSim) -> Dict[str, Any]:
    """Where the frozen pol4 model puts the chain and the background requests of the same arm.

    pol4's own step log names the requests prefilling in each step, so the chain's simulated
    occupancy is read off it directly rather than assumed. A simulated inter-piece gap is the
    time between piece k's last prefill step end and piece k+1's first prefill step start."""
    res_w = sim.run(tr._arm_requests(trial.arms["with"], include_action=True))
    res_o = sim.run(tr._arm_requests(trial.arms["without"], include_action=False))
    acts = sorted(trial.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
    span: Dict[str, Tuple[float, float]] = {}
    for s in res_w["steps"]:
        for rid in s.get("prefilling", []):
            lo, hi = span.get(rid, (s["t_start"], s["t_end"]))
            span[rid] = (min(lo, s["t_start"]), max(hi, s["t_end"]))
    nsteps: Dict[str, int] = defaultdict(int)
    sdur: Dict[str, List[float]] = defaultdict(list)
    for s in res_w["steps"]:
        for rid in s.get("prefilling", []):
            nsteps[rid] += 1
            sdur[rid].append(s["duration_s"])
    sim_gaps = []
    for k in range(len(acts) - 1):
        a, b = span.get(str(acts[k]["rid"])), span.get(str(acts[k + 1]["rid"]))
        if a is None or b is None:
            continue
        sim_gaps.append(dict(after_part=int(acts[k].get("part_i") or 0),
                             before_part=int(acts[k + 1].get("part_i") or 0),
                             t0=a[1], t1=b[0], gap_s=b[0] - a[1]))
    busy = []
    for s in res_w["steps"]:
        if any(str(r.get("rid")) in s.get("prefilling", []) for r in acts):
            busy.append((s["t_start"], s["t_end"]))
    act_rids = [str(r.get("rid")) for r in acts]
    piece_steps = [nsteps.get(r, 0) for r in act_rids]
    piece_durs = [d for r in act_rids for d in sdur.get(r, [])]
    return dict(res_with=res_w, res_without=res_o, sim_gaps=sim_gaps,
                sim_n_piece_steps=sum(piece_steps),
                sim_step_dur_median_s=(statistics.median(piece_durs) if piece_durs else None),
                sim_steps_per_piece=(statistics.fmean(piece_steps) if piece_steps else None),
                sim_chain_busy=busy,
                sim_chain_span_s=((max(h for _, h in busy) - min(l for l, _ in busy))
                                  if busy else None),
                sim_chain_busy_s=sum(h - l for l, h in busy))


def trial_report(trial: tr.Trial, st: Steps, sim: EngineSim) -> Optional[Dict[str, Any]]:
    acts = sorted(trial.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
    if not acts:
        return None
    n_parts = int(acts[0].get("n_parts") or 1)
    timing = piece_timing(st, acts)
    if timing is None:
        return None
    gaps = measured_gaps(st, timing)
    pcomp = piece_step_composition(st, timing, acts)
    place = pol4_sim_placement(trial, sim)
    t0w = trial.arms["with"].t0_trace
    pw, po = place["res_with"]["per_request"], place["res_without"]["per_request"]
    w = {tr._bg_key(r): r for r in trial.arms["with"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    o = {tr._bg_key(r): r for r in trial.arms["without"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    chain_t0, chain_t1 = timing[0]["t_sched"], timing[-1]["t_end_eng"]
    per = []
    for k in sorted(set(w) & set(o), key=lambda x: str(x)):
        rw, ro = w[k], o[k]
        if rw.get("t_first") is None:
            continue
        gi = _in_any_gap(float(rw["t_first"]), gaps)
        tf = float(rw["t_first"])
        if tf <= chain_t0:
            pos = "pre_chain"
        elif tf > chain_t1:
            pos = "post_chain"
        else:
            pos = "gap" if gi is not None else "busy"
        meas = (float(rw["ttft_s"]) - float(ro["ttft_s"])
                if rw.get("ttft_s") is not None and ro.get("ttft_s") is not None else None)
        a = _pred_value(pw, rw, "ttft", t0w)
        b = _pred_value(po, ro, "ttft", trial.arms["without"].t0_trace)
        pred = (float(a) - float(b)) if (a is not None and b is not None) else None
        sim_first = pw.get(str(rw.get("rid")), {}).get("t_first")
        sgi = (_in_any_gap(float(sim_first), place["sim_gaps"])
               if sim_first is not None else None)
        # The delta is a DIFFERENCE of two arms, so an over-predicted delta can come from an
        # over-predicted with-arm TTFT or an under-predicted without-arm TTFT. Both arms' own
        # measured and predicted TTFT are kept so the report can say which.
        per.append(dict(key=str(k), rid=str(rw.get("rid")),
                        in_measured_gap=gi, in_sim_gap=sgi, position=pos,
                        offset=((tf - chain_t0) / (chain_t1 - chain_t0)
                                if chain_t1 > chain_t0 else None),
                        meas_ttft_with_s=rw.get("ttft_s"),
                        meas_ttft_without_s=ro.get("ttft_s"),
                        pred_ttft_with_s=a, pred_ttft_without_s=b,
                        err_ttft_with_s=((float(a) - float(rw["ttft_s"]))
                                         if (a is not None and rw.get("ttft_s") is not None)
                                         else None),
                        err_ttft_without_s=((float(b) - float(ro["ttft_s"]))
                                            if (b is not None and ro.get("ttft_s") is not None)
                                            else None),
                        measured_delta_s=meas, predicted_delta_s=pred,
                        over_s=((pred - meas) if (pred is not None and meas is not None)
                                else None)))
    out = dict(key=trial.key(), cell=trial.cell(), load=trial.load, action=trial.action,
               trial=trial.trial, cap=int(trial.load.split("_", 1)[0]),
               bg_load=trial.load.split("_", 1)[1], n_parts=n_parts,
               n_pieces_timed=len(timing), timing=timing, gaps=gaps,
               piece_steps=[{k: v for k, v in c.items() if k != "steps"} for c in pcomp],
               n_piece_steps=sum(c["n_steps"] for c in pcomp),
               n_piece_steps_sharing=sum(c["n_steps_sharing"] for c in pcomp),
               n_piece_steps_other_prefill=sum(c["n_steps_other_prefill"] for c in pcomp),
               n_piece_steps_decoding=sum(c["n_steps_decoding"] for c in pcomp),
               other_prefill_tokens_in_piece_steps=sum(c["other_prefill_tokens"]
                                                       for c in pcomp),
               max_ctx_req_in_piece_steps=max((c["max_ctx_req"] for c in pcomp), default=0),
               sim_n_piece_steps=place["sim_n_piece_steps"],
               sim_step_dur_median_s=place["sim_step_dur_median_s"],
               sim_steps_per_piece=place["sim_steps_per_piece"],
               steps_per_piece=(sum(c["n_steps"] for c in pcomp) / len(pcomp)
                                if pcomp else None),
               step_dur_median_s=(statistics.median(
                   [x["dur_s"] for c in pcomp for x in c["steps"] if x["dur_s"] is not None])
                   if any(x["dur_s"] is not None for c in pcomp for x in c["steps"])
                   else None),
               sim_gaps=place["sim_gaps"], sim_chain_span_s=place["sim_chain_span_s"],
               sim_chain_busy_s=place["sim_chain_busy_s"], per_request=per)
    out["measured_chain_span_s"] = timing[-1]["t_end_eng"] - timing[0]["t_sched"]
    out["measured_gap_total_s"] = sum(g["gap_s"] for g in gaps)
    out["sim_gap_total_s"] = sum(g["gap_s"] for g in place["sim_gaps"])
    for metric in METRIC_FIELD:
        m = _measured_sum(trial, "without", metric)
        a_tot, n = 0.0, 0
        for k in sorted(set(w) & set(o), key=lambda x: str(x)):
            a = _pred_value(pw, w[k], metric, t0w)
            b = _pred_value(po, o[k], metric, trial.arms["without"].t0_trace)
            if a is None or b is None:
                continue
            a_tot += float(a) - float(b)
            n += 1
        out["measured_delay_%s_s" % metric] = (m["total_s"] if m else None)
        out["predicted_delay_%s_s" % metric] = a_tot
        out["over_prediction_%s_s" % metric] = (
            a_tot - m["total_s"] if m else None)
        out["ratio_%s" % metric] = (
            a_tot / m["total_s"] if (m and m["total_s"] not in (None, 0)) else None)
    by_pos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in per:
        by_pos[p["position"]].append(p)
    out["by_position"] = {k: dict(
        n=len(v),
        measured_delta_s=sum(x["measured_delta_s"] or 0.0 for x in v),
        predicted_delta_s=sum(x["predicted_delta_s"] or 0.0 for x in v),
        over_s=sum(x["over_s"] or 0.0 for x in v),
        err_with_s=sum(x["err_ttft_with_s"] or 0.0 for x in v),
        err_without_s=sum(x["err_ttft_without_s"] or 0.0 for x in v))
        for k, v in sorted(by_pos.items())}
    gap_served = [p for p in per if p["in_measured_gap"] is not None]
    out["n_background_matched"] = len(per)
    out["n_background_in_measured_gap"] = len(gap_served)
    out["n_background_in_sim_gap"] = sum(1 for p in per if p["in_sim_gap"] is not None)
    out["gap_served_measured_delta_s"] = sum(p["measured_delta_s"] or 0.0 for p in gap_served)
    out["gap_served_predicted_delta_s"] = sum(p["predicted_delta_s"] or 0.0 for p in gap_served)
    out["gap_attributable_over_s"] = sum(p["over_s"] or 0.0 for p in gap_served)
    ov = out["over_prediction_ttft_s"]
    out["gap_attributable_share_ttft"] = (
        out["gap_attributable_over_s"] / ov if ov not in (None, 0) else None)
    return out


def _agg(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    v = [r[key] for r in rows if r.get(key) is not None]
    if not v:
        return dict(n=0)
    return dict(n=len(v), median=round(statistics.median(v), 5),
                mean=round(statistics.fmean(v), 5), min=round(min(v), 5), max=round(max(v), 5),
                iqr=[round(statistics.quantiles(v, n=4)[0], 5),
                     round(statistics.quantiles(v, n=4)[2], 5)] if len(v) >= 4 else None)


def summarize(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    keys = ("sim_n_piece_steps", "sim_step_dur_median_s", "sim_steps_per_piece",
            "steps_per_piece", "step_dur_median_s",
            "n_piece_steps", "n_piece_steps_sharing", "n_piece_steps_other_prefill",
            "n_piece_steps_decoding", "other_prefill_tokens_in_piece_steps",
            "max_ctx_req_in_piece_steps",
            "measured_gap_total_s", "sim_gap_total_s", "measured_chain_span_s",
            "sim_chain_span_s", "sim_chain_busy_s", "over_prediction_ttft_s",
            "over_prediction_latency_s", "ratio_ttft", "ratio_latency",
            "gap_attributable_over_s", "gap_attributable_share_ttft",
            "n_background_in_measured_gap", "n_background_in_sim_gap",
            "n_background_matched")
    out: Dict[str, Any] = {}
    for name, sel in (("by_action", lambda r: r["action"]),
                      ("by_action_load", lambda r: "%s|%s" % (r["action"], r["bg_load"])),
                      ("by_action_cap", lambda r: "%s|%d" % (r["action"], r["cap"]))):
        g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            g[sel(r)].append(r)
        out[name] = {k: dict(n_trials=len(v), **{kk: _agg(v, kk) for kk in keys})
                     for k, v in sorted(g.items())}
    pos_tot: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        for k, v in r.get("by_position", {}).items():
            for kk, vv in v.items():
                pos_tot[k][kk] += vv
    out["by_position_totals"] = {k: {kk: round(vv, 4) for kk, vv in sorted(v.items())}
                                 for k, v in sorted(pos_tot.items())}
    gaps = [g for r in rows for g in r["gaps"]]
    out["per_gap"] = dict(
        n=len(gaps),
        gap_s=_agg(gaps, "gap_s"), frontend_window_s=_agg(gaps, "frontend_window_s"),
        client_turnaround_s=_agg(gaps, "client_turnaround_s"),
        engine_tail_s=_agg(gaps, "engine_tail_s"),
        n_steps_in_gap=_agg(gaps, "n_steps_in_gap"),
        n_steps_with_other_work=_agg(gaps, "n_steps_with_other_work"),
        other_prefill_tokens_in_gap=_agg(gaps, "other_prefill_tokens_in_gap"),
        n_gaps_with_other_work=sum(1 for g in gaps if g["n_steps_with_other_work"] > 0),
        n_gaps_with_any_step=sum(1 for g in gaps if g["n_steps_in_gap"] > 0))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args(argv)
    trials, audit = load_part_d_trials(split="fit")
    sim = make_sim("pol4")
    caps = sorted({int(t.load.split("_", 1)[0]) for t in trials})
    steps = {c: Steps(_root() / STEPS_DIR / ("DE_c%d.jsonl.gz" % c)) for c in caps}
    rows, skipped = [], []
    for t in trials:
        cap = int(t.load.split("_", 1)[0])
        r = trial_report(t, steps[cap], sim)
        if r is None:
            skipped.append(t.key())
            continue
        rows.append(r)
    chained = [r for r in rows if r["action"] in CHAINED_ACTIONS and r["n_parts"] > 1]
    single = [r for r in rows if r["n_parts"] == 1]
    out = dict(
        study="StudyPOL6-chain Part A, inter-piece gap pre-check",
        model="pol4 (frozen)", label=DERIVED_LABEL, holdout_audit=audit,
        n_trials=len(rows), n_skipped=len(skipped), skipped=skipped[:10],
        n_chained=len(chained), n_single_request=len(single),
        chained=summarize(chained),
        single_request_control=summarize(single),
        trials=rows)
    p = _root() / args.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, sort_keys=True))
    print("wrote %s: %d trials (%d chained, %d single-request), %d skipped"
          % (args.out, len(rows), len(chained), len(single), len(skipped)))
    for name in ("chained", "single_request_control"):
        print("--- %s ---" % name)
        print("  by position of the background first token (sums over trials, TTFT):")
        for pos, d in out[name]["by_position_totals"].items():
            print("    %-10s n=%-5d meas %-9.3f pred %-9.3f over %-9.3f "
                  "err_with %-9.3f err_without %.3f"
                  % (pos, d["n"], d["measured_delta_s"], d["predicted_delta_s"], d["over_s"],
                     d["err_with_s"], d["err_without_s"]))
        for act, d in out[name]["by_action"].items():
            print("  %-10s n=%-3d gap_tot med %-8s over_ttft med %-8s ratio_ttft med %-7s "
                  "gap_share med %s"
                  % (act, d["n_trials"], d["measured_gap_total_s"].get("median"),
                     d["over_prediction_ttft_s"].get("median"),
                     d["ratio_ttft"].get("median"),
                     d["gap_attributable_share_ttft"].get("median")))
            print("             steps per piece: measured %s vs pol4 %s; median step "
                  "duration: measured %s s vs pol4 %s s"
                  % (d["steps_per_piece"].get("median"),
                     d["sim_steps_per_piece"].get("median"),
                     d["step_dur_median_s"].get("median"),
                     d["sim_step_dur_median_s"].get("median")))
            print("             piece steps med %s, of which sharing %s "
                  "(other prefill %s, decoding %s); other prefill tokens med %s; "
                  "max ctx_req med %s"
                  % (d["n_piece_steps"].get("median"),
                     d["n_piece_steps_sharing"].get("median"),
                     d["n_piece_steps_other_prefill"].get("median"),
                     d["n_piece_steps_decoding"].get("median"),
                     d["other_prefill_tokens_in_piece_steps"].get("median"),
                     d["max_ctx_req_in_piece_steps"].get("median")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
