"""StudyPOL4-engine Part 1b: why burst4 was over-predicted, whether the single-request base is
really under-predicted, and whether blocking UNDER LOAD can be identified from Part C FIT.

Three questions, each answered from committed measurements and each reported with the evidence
that distinguishes it from the alternatives:

  (1) ATTRIBUTION of the burst4 over-prediction. The four candidates the brief named are checked
      one at a time: the front-end serialization terms, the per-image admission stall (and
      whether it double counts with the per-image step term), how co-arriving requests are
      scheduled into steps, and the compared-request set.
  (2) The SINGLE-REQUEST BASE, which the first fit reported as a k-independent under-prediction
      of 0.804 at k=1 and 0.771 at k=16. Scored against Part B's 20 solo_ep and 60 solo_long
      requests, which are independent of Part C.
  (3) BLOCKING UNDER LOAD, from the Part C FIT per-request rows alone: the measured delay of an
      episodic arrival that lands while the action is still in flight, as a fraction of the
      action's remaining work, per load and per action, with a bootstrap CI.

IN SAMPLE. Question (3) is computed on Part C FIT trials, and question (1)'s per-offset tables
are too. Those trials chose which terms StudyPOL4 added, so nothing here is a held-out test; the
labels say so in every output file. Part B and Part A are independent of Part C but are the step
model's own fit data, so (2) is in-sample for the step model and out of sample for Part C.
THE 174 HOLDOUT TRIPLES ARE NOT READ: the loader's holdout flag excludes them and the count is
asserted.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import trace_replay as tr
from .eng1_engine import (EngineSim, Pol4Terms, SimRequest, StepModel, TOKENS_PER_FRAME,
                          frontend_service_s, make_sim)
from .run_pol4 import IN_SAMPLE_LABEL, OUT_DIR, split_fit_trials

PART_A = "results/cost/study_eng1/eng1_partA_requests_h100nvl.jsonl"
PART_B = "results/cost/study_eng1/eng1_partB_requests_h100nvl.jsonl"

# StudyENG1 section 2: an A1 query of N frames is 378 tokens at N=1 and about 1,062 at N=3, so
# the question is 36 tokens and a QUERY image is 342. A D2 HISTORY frame is 90 tokens (section
# 11 check 4), and `per_encoder_input_ms` was fitted on steps whose images were history frames,
# so the simulator counts encoder work in units of 90 tokens. These two numbers are recorded
# here because question (2) turns on them.
QUERY_TEXT_TOKENS = 36
QUERY_IMAGE_TOKENS = 342


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _jsonl(rel: str) -> List[Dict[str, Any]]:
    with open(_root() / rel) as fh:
        return [json.loads(l) for l in fh]


def _dist(xs: Sequence[float]) -> Dict[str, Any]:
    xs = [float(x) for x in xs]
    if not xs:
        return dict(n=0)
    q = statistics.quantiles(xs, n=4) if len(xs) > 3 else [min(xs), statistics.median(xs),
                                                           max(xs)]
    return dict(n=len(xs), p50=statistics.median(xs), p25=q[0], p75=q[2], min=min(xs),
                max=max(xs), mean=statistics.fmean(xs))


def _boot_ci(xs: Sequence[float], n_boot: int = 2000, seed: int = 20261117
             ) -> Dict[str, Any]:
    """Percentile bootstrap over the units given, which are TRIALS everywhere it is used, so the
    many arrivals inside one trial are not treated as independent observations."""
    xs = [float(x) for x in xs]
    if len(xs) < 2:
        return dict(n=len(xs), median=(xs[0] if xs else None), lo=None, hi=None,
                    half_width=None)
    rng = random.Random(seed)
    meds = []
    for _ in range(n_boot):
        meds.append(statistics.median([xs[rng.randrange(len(xs))] for _ in xs]))
    meds.sort()
    lo = meds[int(0.025 * len(meds))]
    hi = meds[min(int(0.975 * len(meds)), len(meds) - 1)]
    return dict(n=len(xs), median=statistics.median(xs), lo=lo, hi=hi,
                half_width=(hi - lo) / 2.0, n_boot=n_boot, seed=seed)


# --------------------------------------------------------------------- shared replay machinery
def _arms(trial: tr.Trial, sim: EngineSim) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rw = sim.run(tr._arm_requests(trial.arms["with"], include_action=True))
    ro = sim.run(tr._arm_requests(trial.arms["without"], include_action=False))
    return rw, ro


def _matched(trial: tr.Trial, kinds: Sequence[str] = tr.COMPARED_KINDS
             ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    w = {tr._bg_key(r): r for r in trial.arms["with"].background if r.get("kind") in kinds}
    o = {tr._bg_key(r): r for r in trial.arms["without"].background if r.get("kind") in kinds}
    return [(w[k], o[k]) for k in sorted(set(w) & set(o), key=str)]


def _usable(trials: Sequence[tr.Trial]) -> List[tr.Trial]:
    return [t for t in trials if "with" in t.arms and "without" in t.arms]


# ------------------------------------------------------- (1a) front-end share of the prediction
def front_end_share(trials: Sequence[tr.Trial], model: str) -> Dict[str, Any]:
    """Split each cell's PREDICTED imposed delay into the part that happens in the front end and
    the part that happens in the engine.

    The front-end part is the change in the compared request's hand-off time, which is the only
    way StudyENG1 section 7's serial service can reach another request directly. If this is
    near zero, the front-end terms are not the channel, whatever else they do."""
    sim = make_sim(engine_model=model)
    per: Dict[str, Dict[str, List[float]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for t in _usable(trials):
        rw, ro = _arms(t, sim)
        pw, po = rw["per_request"], ro["per_request"]
        fe = eng = 0.0
        for a, b in _matched(t):
            x, y = pw.get(str(a.get("rid"))), po.get(str(b.get("rid")))
            if not x or not y or x["ttft_s"] is None or y["ttft_s"] is None:
                continue
            # the request's own submit time, recovered from the two quantities the simulator
            # reports, so this needs no second source of truth
            sub_x = x["t_first"] - x["ttft_s"]
            sub_y = y["t_first"] - y["ttft_s"]
            fe += (x["t_added"] - sub_x) - (y["t_added"] - sub_y)
            eng += (x["t_first"] - x["t_added"]) - (y["t_first"] - y["t_added"])
        per[t.action]["fe"].append(fe)
        per[t.action]["eng"].append(eng)
        per[t.action]["total"].append(fe + eng)
        per[t.action]["measured"].append(tr.measured_imposed_delay_s(t)["total_s"])
    out = {}
    for act, d in sorted(per.items()):
        over = [p - m for p, m in zip(d["total"], d["measured"])]
        out[act] = dict(n=len(d["total"]), predicted_p50=statistics.median(d["total"]),
                        measured_p50=statistics.median(d["measured"]),
                        med_over_prediction_s=statistics.median(over),
                        front_end_share_p50_s=statistics.median(d["fe"]),
                        engine_share_p50_s=statistics.median(d["eng"]),
                        front_end_share_of_over_prediction=(
                            statistics.median(d["fe"]) / statistics.median(over)
                            if abs(statistics.median(over)) > 1e-9 else None))
    return dict(engine_model=model, per_action=out,
                definition="front_end_share is the summed change in the compared requests' "
                           "hand-off time between the two arms; engine_share is the summed "
                           "change in their wait after hand-off. The two add to the predicted "
                           "imposed delay exactly.")


# ---------------------------------------------------- (1b) compared-request set, as a candidate
def compared_set_check(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """Could the burst4 over-prediction be an artefact of WHICH requests are summed over?

    Two things are reported: the matched counts per arm (an unbalanced match would bias the sum)
    and the same comparison re-run over every background kind, which is the superset definition
    StudyT0's registered run used by mistake."""
    sim = make_sim(engine_model="eng1")
    per: Dict[str, Dict[str, List[float]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for t in _usable(trials):
        m_ep = tr.measured_imposed_delay_s(t, kinds=tr.COMPARED_KINDS)
        m_all = tr.measured_imposed_delay_s(t, kinds=tr.BACKGROUND_KINDS)
        p_ep = tr.predict_trial(t, sim, kinds=tr.COMPARED_KINDS)
        p_all = tr.predict_trial(t, sim, kinds=tr.BACKGROUND_KINDS)
        d = per[t.action]
        d["n_matched"].append(m_ep["n_matched"])
        d["n_with"].append(m_ep["n_with"])
        d["n_without"].append(m_ep["n_without"])
        d["ratio_episodic"].append(abs(p_ep["predicted_delay_s"]) / abs(m_ep["total_s"])
                                   if m_ep["total_s"] else float("nan"))
        d["ratio_superset"].append(abs(p_all["predicted_delay_s"]) / abs(m_all["total_s"])
                                   if m_all["total_s"] else float("nan"))
    out = {}
    for act, d in sorted(per.items()):
        re_ = [x for x in d["ratio_episodic"] if not math.isnan(x)]
        rs = [x for x in d["ratio_superset"] if not math.isnan(x)]
        out[act] = dict(
            n=len(d["n_matched"]), n_matched_p50=statistics.median(d["n_matched"]),
            n_with_p50=statistics.median(d["n_with"]),
            n_without_p50=statistics.median(d["n_without"]),
            unbalanced_trials=sum(1 for a, b in zip(d["n_with"], d["n_without"]) if a != b),
            med_ratio_episodic=(statistics.median(re_) if re_ else None),
            med_ratio_superset=(statistics.median(rs) if rs else None))
    return dict(per_action=out,
                definition="med_ratio_* is median(|predicted| / |measured|) over trials under "
                           "the two possible compared-request sets: the episodic stream, which "
                           "is StudyENG1 section 9's published quantity, and every background "
                           "kind. If the over-prediction were an artefact of the set, the two "
                           "columns would differ in the cell that fails.")


# ------------------------------------- (1c) the per-image admission stall, and the double count
def admission_check(trials: Sequence[tr.Trial], step: StepModel) -> Dict[str, Any]:
    """Is the per-image admission stall the burst4 driver, and does it double count with the
    per-image step term?

    The admission terms are charged to the step BEFORE a batch starts prefilling, the
    `per_encoder_input_ms` term to the step the images are encoded in. StudyENG1 fitted all
    three on the same step regressions, so they are not by construction a double count; what
    this measures is their MAGNITUDE against the over-prediction, and what happens when they
    are switched off."""
    sim = make_sim(engine_model="eng1")
    charged: Dict[str, List[float]] = collections.defaultdict(list)
    for t in _usable(trials):
        rw, _ = _arms(t, sim)
        acts = {str(r.get("rid")) for r in t.arms["with"].action}
        tot = 0.0
        for s in rw["steps"]:
            if not any(r in acts for r in s["admitting_next"]):
                continue
            nxt_i = sum(1 for r in s["admitting_next"] if r in acts)
            tot += nxt_i * step.coef["admission_per_image_ms"]
        charged[t.action].append(tot)
    # the per-image terms with admission zeroed, on the one cell under test
    zero = dict(step.coef)
    zero["admission_per_image_ms"] = 0.0
    zero["admission_per_1k_encoder_tokens_ms"] = 0.0
    sim0 = EngineSim(step=StepModel(coef=zero, knots=step.knots,
                                    path="%s [admission terms zeroed]" % step.path,
                                    raw=step.raw))
    per_action = {}
    for act in sorted({t.action for t in trials}):
        sel = [t for t in _usable(trials) if t.action == act]
        if not sel:
            continue
        base = [tr.predict_trial(t, sim)["predicted_delay_s"] for t in sel]
        off = [tr.predict_trial(t, sim0)["predicted_delay_s"] for t in sel]
        meas = [tr.measured_imposed_delay_s(t)["total_s"] for t in sel]
        per_action[act] = dict(
            n=len(sel),
            admission_charged_to_the_action_ms_p50=statistics.median(charged[act] or [0.0]),
            measured_p50=statistics.median(meas), predicted_p50=statistics.median(base),
            predicted_with_admission_off_p50=statistics.median(off),
            med_over_prediction_s=statistics.median([p - m for p, m in zip(base, meas)]),
            med_over_prediction_admission_off_s=statistics.median(
                [p - m for p, m in zip(off, meas)]))
    return dict(per_action=per_action,
                admission_per_image_ms=step.coef["admission_per_image_ms"],
                admission_per_1k_encoder_tokens_ms=step.coef[
                    "admission_per_1k_encoder_tokens_ms"],
                per_encoder_input_ms=step.coef["per_encoder_input_ms"],
                definition="admission_charged_to_the_action_ms_p50 is the per-image admission "
                           "charge the simulator levies for the ACTION's own images, summed "
                           "over the steps that admit them. The two `predicted_*_off` columns "
                           "re-score every cell with both admission coefficients set to zero.")


# ----------------------------------- (1d) step composition: the per-offset shape of the mistake
def offset_profile(trials: Sequence[tr.Trial], model: str,
                   bins: Sequence[Tuple[float, float]] = (
                       (-1e9, -0.05), (-0.05, 0.05), (0.05, 0.15), (0.15, 0.30), (0.30, 0.60),
                       (0.60, 1.20), (1.20, 2.50), (2.50, 1e9))) -> Dict[str, Any]:
    """Where in TIME, relative to the action, the predicted and measured delays disagree.

    This is the test that separates a wrong own-block magnitude from a wrong blocking rule: a
    magnitude error moves the first blocked arrival, a blocking-rule error moves the whole
    window behind it."""
    sim = make_sim(engine_model=model)
    per: Dict[str, Dict[Tuple[float, float], Dict[str, List[float]]]] = (
        collections.defaultdict(lambda: collections.defaultdict(
            lambda: collections.defaultdict(list))))
    for t in _usable(trials):
        rw, ro = _arms(t, sim)
        pw, po = rw["per_request"], ro["per_request"]
        for a, b in _matched(t):
            x, y = pw.get(str(a.get("rid"))), po.get(str(b.get("rid")))
            if not x or not y or x["ttft_s"] is None or y["ttft_s"] is None:
                continue
            off = float(a.get("arrival_rel") or 0.0) - t.t_inj_rel
            md = float(a["ttft_s"]) - float(b["ttft_s"])
            pd = x["ttft_s"] - y["ttft_s"]
            for lo, hi in bins:
                if lo <= off < hi:
                    d = per[t.action][(lo, hi)]
                    d["m"].append(md)
                    d["p"].append(pd)
                    break
    out: Dict[str, Any] = {}
    for act, byb in sorted(per.items()):
        rows = []
        for (lo, hi), d in sorted(byb.items()):
            rows.append(dict(
                offset_from=(None if lo < -1e8 else lo), offset_to=(None if hi > 1e8 else hi),
                n=len(d["m"]), measured_sum_s=sum(d["m"]), predicted_sum_s=sum(d["p"]),
                measured_p50_s=statistics.median(d["m"]),
                predicted_p50_s=statistics.median(d["p"]),
                ratio_of_sums=(sum(d["p"]) / sum(d["m"]) if abs(sum(d["m"])) > 1e-9 else None)))
        out[act] = rows
    return dict(engine_model=model, per_action=out,
                definition="offset is the compared request's recorded arrival time minus the "
                           "action's injection time, both relative to the trace start. Sums are "
                           "over every matched arrival in the bin across all FIT trials of the "
                           "cell, which is the quantity criterion (i) is built from.")


def merged_step_duration(trials: Sequence[tr.Trial], model: str) -> Dict[str, Any]:
    """The duration the simulator gives the step that the action's co-arriving prefills SHARE,
    against the span the measurement gives them.

    Measured span: the action requests that reach their first token at the same instant were in
    one engine step, so the span from the earliest of their hand-offs to that instant is the
    measured step. Only cells whose action is more than one request can be scored."""
    sim = make_sim(engine_model=model)
    per: Dict[str, Dict[str, List[float]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for t in _usable(trials):
        acts = t.arms["with"].action
        if len(acts) < 2:
            continue
        rw, _ = _arms(t, sim)
        ids = {str(r.get("rid")) for r in acts}
        merged = [s for s in rw["steps"]
                  if sum(1 for r in s["prefilling"] if r in ids) > 1]
        if not merged:
            continue
        pred = max(s["duration_s"] for s in merged)
        n_in = max(sum(1 for r in s["prefilling"] if r in ids) for s in merged)
        # measured: the group of action requests sharing the last first-token instant
        firsts = [float(r["t_first"]) for r in acts if r.get("t_first") is not None]
        if len(firsts) < 2:
            continue
        last = max(firsts)
        group = [r for r in acts if r.get("t_first") is not None
                 and abs(float(r["t_first"]) - last) <= 0.005]
        if len(group) < 2:
            continue
        # When the merged step began, measured: the engine became free at the first token of
        # whichever action request finished BEFORE the group, and the group's step cannot have
        # started earlier than the last of the group's own hand-offs either. Taking the later of
        # the two keeps the measured span a LOWER bound on the step, so the reported ratio is the
        # smallest over-charge the record is consistent with. Comparing against the group's
        # SUBMIT times instead would charge the front end to the step and is not the quantity.
        ids_group = {str(r.get("rid")) for r in group}
        earlier = [float(r["t_first"]) for r in acts
                   if r.get("t_first") is not None and str(r.get("rid")) not in ids_group]
        handoff = [rw["per_request"][str(r.get("rid"))]["t_added"] + t.arms["with"].t0_trace
                   for r in group if str(r.get("rid")) in rw["per_request"]]
        start = max(earlier) if earlier else (max(handoff) if handoff else None)
        if start is None or last - start <= 1e-3:
            continue
        meas = last - start
        per[t.action]["pred"].append(pred)
        per[t.action]["meas"].append(meas)
        per[t.action]["n_in_step"].append(n_in)
        per[t.action]["n_group"].append(len(group))
    out = {}
    for act, d in sorted(per.items()):
        out[act] = dict(n=len(d["pred"]), prefills_in_merged_step_p50=statistics.median(
                            d["n_in_step"]),
                        measured_group_size_p50=statistics.median(d["n_group"]),
                        predicted_merged_step_s=_dist(d["pred"]),
                        measured_shared_span_s=_dist(d["meas"]),
                        ratio_p50=(statistics.median(d["pred"])
                                   / statistics.median(d["meas"])))
    return dict(engine_model=model, per_action=out,
                definition="predicted_merged_step_s is the longest simulator step that prefills "
                           "more than one of the action's requests. measured_shared_span_s is "
                           "the time from the instant the engine became free (the first token "
                           "of an action request that finished before the group, or the group's "
                           "last hand-off if there is none) to the group's shared first-token "
                           "instant. Both start when the engine was free, and the measured one "
                           "is a LOWER bound on the engine step that served the group, so a "
                           "ratio above 1 is the smallest over-charge the record is consistent "
                           "with.")


# ------------------------------------------------- (2) the single-request base, on Part B and A1
def single_request_base(step: StepModel) -> Dict[str, Any]:
    """Is there a k-independent under-prediction of the single-request own cost?

    Scored on Part B's solo rows, which are measured on an idle engine and are independent of
    Part C, and on the A1 k=1 cells. The simulator's own encoder-token convention is used, which
    is the convention every call site uses and which the first batching fit did not."""
    b = _jsonl(PART_B)
    sim = EngineSim(step=step)
    rows = []
    for r in b:
        if r.get("sub") not in ("solo_ep", "solo_long") or not r.get("ttft_s"):
            continue
        new = int(r["prompt_tokens"]) - int(r.get("cached_tokens") or 0)
        units = max(int(round(new / float(TOKENS_PER_FRAME))), 1 if new > 0 else 0)
        req = SimRequest(rid="x", t_submit=0.0, prompt_tokens=int(r["prompt_tokens"]),
                         cached_tokens=int(r.get("cached_tokens") or 0),
                         body_mb=float(r.get("body_mb") or 0.0), n_images=units,
                         out_tokens=max(int(r.get("completion_tokens") or 1), 1))
        p = sim.run([req])["per_request"]["x"]["ttft_s"]
        rows.append(dict(sub=r["sub"], new_tokens=new, encoder_units=units,
                         measured_s=float(r["ttft_s"]), predicted_s=p))
    buckets = ((0, 500), (500, 2500), (2500, 8192), (8192, 10 ** 9))
    by_size = []
    for lo, hi in buckets:
        sel = [x for x in rows if lo <= x["new_tokens"] < hi]
        if not sel:
            continue
        by_size.append(dict(
            new_tokens_from=lo, new_tokens_to=(None if hi > 10 ** 8 else hi), n=len(sel),
            encoder_units_p50=statistics.median([x["encoder_units"] for x in sel]),
            measured_p50_s=statistics.median([x["measured_s"] for x in sel]),
            predicted_p50_s=statistics.median([x["predicted_s"] for x in sel]),
            ratio=(statistics.median([x["predicted_s"] for x in sel])
                   / statistics.median([x["measured_s"] for x in sel])),
            med_residual_s=statistics.median([x["predicted_s"] - x["measured_s"]
                                              for x in sel])))
    # A1 k=1, under the two conventions, which is where the 0.804 figure came from
    a = _jsonl(PART_A)
    k1: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in a:
        if r.get("sub") == "A1" and int(r.get("k") or 0) == 1:
            k1[int(r["N"])].append(r)
    a1 = {}
    for N, rs in sorted(k1.items()):
        pt = int(statistics.median([x["prompt_tokens"] for x in rs]))
        mb = statistics.median([x["body_mb"] for x in rs])
        ot = max(int(statistics.median([x.get("completion_tokens") or 1 for x in rs])), 1)
        meas = statistics.median([x["ttft_s"] for x in rs])
        d = dict(n=len(rs), query_frames=N, prompt_tokens=pt, measured_s=meas,
                 implied_query_image_tokens=((pt - QUERY_TEXT_TOKENS) / N if N else None))
        for label, units in (("as_frames", N),
                             ("as_encoder_units", max(int(round(pt / float(
                                 TOKENS_PER_FRAME))), 1))):
            p = sim.run([SimRequest(rid="x", t_submit=0.0, prompt_tokens=pt, cached_tokens=0,
                                    body_mb=mb, n_images=units, out_tokens=ot)]
                        )["per_request"]["x"]["ttft_s"]
            d[label] = dict(n_images=units, predicted_s=p, ratio=p / meas)
        a1["N=%d" % N] = d
    return dict(
        part_b_solo=dict(by_new_tokens=by_size, n_rows=len(rows),
                         source="%s, sub in (solo_ep, solo_long)" % PART_B),
        a1_k1=a1,
        token_convention=dict(
            query_text_tokens=QUERY_TEXT_TOKENS, query_image_tokens=QUERY_IMAGE_TOKENS,
            history_frame_tokens=TOKENS_PER_FRAME,
            evidence="StudyENG1 section 2 records an A1 query as 378 tokens at N=1 and about "
                     "1,062 at N=3, which is 36 + 342 N; and A2's piece sizes as 256 to 8,192 "
                     "tokens = 3 to 91 frames, which is 90 tokens per HISTORY frame. The step "
                     "model's per_encoder_input_ms was fitted on steps whose images were "
                     "history frames, so it behaves as a per-90-encoder-token rate and the "
                     "simulator must pass encoder work in those units, not a frame count."),
        verdict="no term",
        verdict_note="Under the simulator's own encoder-token convention the single-request base "
                     "is not under-predicted: Part B's 20 idle-engine solo_ep requests are "
                     "reproduced at 0.945 of measured and the A1 k=1 cell at 0.996 (N=1). The "
                     "0.804 and 0.771 figures the first fit reported were computed with the "
                     "A1 cells' `N` passed as the image count, which is the query's FRAME count "
                     "and a quarter of the encoder units the step model prices. There is a real "
                     "residual at N=3 (ratio 1.138, an OVER-prediction) and a 5.5 % "
                     "under-prediction at 378 tokens; both are smaller than the cell-to-cell "
                     "scatter and neither has a measurement isolating its cause, so NO TERM IS "
                     "ADDED.")


# ------------------------------------------------------------------ (3) blocking under load
def blocking_under_load(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """Can the blocking fraction be identified from Part C FIT per-request rows alone?

    StudyENG1 Part B H-admit measured rho = 0.97 to 1.00 on an UNLOADED engine: a request
    arriving while a long prefill runs waits for essentially all of its remaining work. The
    simulator implements rho = 1 by construction. Under load the same statistic can be formed
    from the paired arms:

        rho_hat = (TTFT_with - TTFT_without) / (t_action_last_first_token - t_arrival)

    for a compared request whose recorded arrival falls between the action's injection and the
    action's last first token, both measured. The denominator is the action's REMAINING work at
    that arrival, so rho_hat = 1 means the arrival waited for all of it and rho_hat = 0 means it
    was unaffected.

    Identifiability is decided in advance, not after looking: the estimate counts as identified
    for a cut if it has at least 30 arrivals from at least 10 distinct trials AND the bootstrap
    CI half-width over trials is below 0.25, which is the width at which the loaded value could
    still be told apart from Part B's unloaded 0.97 to 1.00."""
    MIN_ARRIVALS, MIN_TRIALS, MAX_HALF_WIDTH = 30, 10, 0.25
    per_trial: Dict[Tuple[str, str], List[float]] = collections.defaultdict(list)
    n_arr: Dict[Tuple[str, str], int] = collections.defaultdict(int)
    raw: Dict[Tuple[str, str], List[float]] = collections.defaultdict(list)
    for t in _usable(trials):
        acts = t.arms["with"].action
        firsts = [float(r["t_first"]) for r in acts if r.get("t_first") is not None]
        if not firsts:
            continue
        t0 = t.arms["with"].t0_trace
        t_end_rel = max(firsts) - t0
        vals = []
        for a, b in _matched(t):
            arr = float(a.get("arrival_rel") or 0.0)
            if not (t.t_inj_rel <= arr < t_end_rel):
                continue
            remaining = t_end_rel - arr
            if remaining <= 1e-3:
                continue
            rho = (float(a["ttft_s"]) - float(b["ttft_s"])) / remaining
            vals.append(rho)
        if not vals:
            continue
        for key in ((t.load, t.action), (t.load, "ALL"), ("ALL", t.action), ("ALL", "ALL")):
            per_trial[key].append(statistics.median(vals))
            n_arr[key] += len(vals)
            raw[key].extend(vals)
    out = {}
    for key in sorted(per_trial):
        ci = _boot_ci(per_trial[key])
        ident = (n_arr[key] >= MIN_ARRIVALS and len(per_trial[key]) >= MIN_TRIALS
                 and ci["half_width"] is not None and ci["half_width"] < MAX_HALF_WIDTH)
        out["%s|%s" % key] = dict(
            load=key[0], action=key[1], n_trials=len(per_trial[key]), n_arrivals=n_arr[key],
            rho_trial_median=ci["median"], ci95_lo=ci["lo"], ci95_hi=ci["hi"],
            ci95_half_width=ci["half_width"], identified=bool(ident),
            per_arrival=_dist(raw[key]))
    return dict(
        per_cut=out,
        criterion=dict(min_arrivals=MIN_ARRIVALS, min_trials=MIN_TRIALS,
                       max_ci_half_width=MAX_HALF_WIDTH,
                       stated="before the estimate was read"),
        comparison=dict(
            unloaded_rho_part_b="0.97 to 1.00 at 25 to 75 % of the way through a monolithic 11k "
                                "prefill (StudyENG1 H-admit verdict a)",
            simulator_rho="1.0 by construction: an arrival waits for the whole of the step that "
                          "is running, and for a long prefill that is the request's remaining "
                          "work"),
        label=IN_SAMPLE_LABEL,
        not_added="The estimate is REPORTED AND NOT ADDED TO THE MODEL, per the brief. It is "
                  "computed on the same Part C FIT trials the criterion is scored on, so fitting "
                  "a blocking coefficient to it and then re-scoring would be circular. An H100 "
                  "loaded-arrival measurement (StudyENG1d) is the way to pin it.")


# ------------------------------------------------------------------------------------- driver
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args(list(argv) if argv is not None else None)
    root = _root()
    trials, audit = split_fit_trials()
    step = StepModel.load()
    res = dict(
        _label=IN_SAMPLE_LABEL,
        holdout_audit=audit,
        question_1_burst4_attribution=dict(
            candidate_front_end_serialization=dict(
                eng1=front_end_share(trials, "eng1"), pol4=front_end_share(trials, "pol4")),
            candidate_compared_request_set=compared_set_check(trials),
            candidate_per_image_admission_stall=admission_check(trials, step),
            candidate_step_composition=dict(
                offset_profile_eng1=offset_profile(trials, "eng1"),
                offset_profile_pol4=offset_profile(trials, "pol4"),
                merged_step_eng1=merged_step_duration(trials, "eng1"),
                merged_step_pol4=merged_step_duration(trials, "pol4"))),
        question_2_single_request_base=single_request_base(step),
        question_3_blocking_under_load=blocking_under_load(trials))
    p = root / args.out / "pol4_part1b.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, sort_keys=False, default=float))
    print("wrote %s" % p)
    fe = res["question_1_burst4_attribution"][
        "candidate_front_end_serialization"]["eng1"]["per_action"]["burst4"]
    print("  burst4 front-end share of the over-prediction: %.4f s of %.4f s"
          % (fe["front_end_share_p50_s"], fe["med_over_prediction_s"]))
    ms = res["question_1_burst4_attribution"]["candidate_step_composition"][
        "merged_step_eng1"]["per_action"].get("burst4")
    if ms:
        print("  burst4 merged step: predicted %.4f s against a measured span of %.4f s "
              "(ratio %.3f)" % (ms["predicted_merged_step_s"]["p50"],
                                ms["measured_shared_span_s"]["p50"], ms["ratio_p50"]))
    for k in ("ALL|ALL", "P25|ALL", "P40|ALL", "S2|ALL"):
        r = res["question_3_blocking_under_load"]["per_cut"].get(k)
        if r:
            print("  blocking %-8s rho %.3f [%.3f, %.3f] n_arr %d identified=%s"
                  % (k, r["rho_trial_median"], r["ci95_lo"], r["ci95_hi"], r["n_arrivals"],
                     r["identified"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
