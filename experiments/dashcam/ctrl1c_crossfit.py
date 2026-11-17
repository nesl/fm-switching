#!/usr/bin/env python3
"""StudyCTRL1c-calibrated: StudyCTRL1b's trigger comparison redone without its three defects, so
that the v3.1 addendum's open question Q11 can be decided. CPU only; no GPU, no model server, no
inference, no scikit-learn. Every score is a committed StudyD14b trace.

Pre-registered before anything was computed. A concurrent session holds research/EXPERIMENTS.md,
so the row text was frozen in the session scratchpad first and inserted verbatim afterwards; the
report says so and why.

WHAT CHANGES FROM StudyCTRL1b, and nothing else changes. StudyCTRL1b's own report named three
defects and decisions D57 and D58 require them removed:

  (C1) PER-TIER CALIBRATION (D57). The 32B's raw log P(Yes) runs a median -5.125 log units below
       the 4B's, so an arm that mixes tiers is penalized by the offset alone. Primary: Platt
       scaling per tier on the training folds' decision instants with the clip-level label, stored
       and applied as the calibrated log-odds a*s + b. Sensitivities: isotonic, and Platt with an
       instant-level label. `ctrl1c_calibrate.py` holds the fits.

  (C2) THE PRIMARY METRIC IS STREAMING AP (D58), averaged over horizons 0.5 / 1.0 / 1.5 s, because
       the challenge mAP reads one crop per clip. Challenge mAP stays as the secondary, computed on
       the same arms. THE FITTING OBJECTIVE FOLLOWS THE PRIMARY METRIC: StudyCTRL1b maximized the
       training folds' challenge mAP at a fixed budget, and this row maximizes the training folds'
       streaming AP at a fixed budget. That is a consequence of the metric change the brief
       pre-registers, not an extra change: selecting tunables on a metric the row declares
       defective would carry the defect into the comparison. It is recorded here because it is a
       decision and not a transcription.

  (C3) THE BACKGROUND CADENCE GRID IS EXTENDED (D58) from {1, 2, 4} s to {1, 2, 4, 5, 6, 8, 10} s
       for the cloud-initiated arm and the context-modulated trickle, because 4 s alone costs
       0.1250 of the decision instants and so exceeded the 5 % and 10 % budgets.

  (C4) The learned ceiling's signed per-instant gain target is retargeted onto the calibrated
       scale, which happens automatically because every array the target is built from is
       calibrated.

  (C5) A LOAD column is added beside the budget: the number of devices an H100 could serve at that
       call rate, DERIVED from the committed ENG1 step model. It is not measured here.

THRESHOLD SEARCH RANGES (C6). StudyCTRL1b bisected the absolute-confidence and cloud-initiated
thresholds over [-30, 0.5] log units, a range chosen for the RAW score. On the calibrated log-odds
scale that range is meaningless, so the search bounds here are the training folds' own observed
min and max of the thresholded quantity, which is what StudyCTRL1b already did for its learned
arms. A search bound is not a model parameter and every arm's realized budget is reported next to
its target.

WHAT IS CARRIED FORWARD UNCHANGED, declared rather than re-derived: the folds, the arms, the
tunable grid, the 0.5-s decision cadence, every latency, the call-fraction budget metric (B1), the
oracle's two readings (B2b) and its CONSTANT lead link (B2c), the episode-close rule (B3), the
background-charging rule (B4), trigger causality (B5), the signed-gain target (B8) and the context
threshold rule (B9, 0.5 for a binary feature and the median for a continuous one). The three
feature families StudyCTRL1b declared NOT AVAILABLE stay NOT AVAILABLE and nothing is substituted
for them: no image features (the d14b frame store is absent from this machine and opencv is not
installed), no Nexar ego speed (not in the committed clip table), and elapsed time in the clip
excluded by decision as an event-placement leak.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import ctrl1_controller as C                              # noqa: E402
import ctrl1b_crossfit as CB                              # noqa: E402
import ctrl1b_learned as LN                               # noqa: E402
import ctrl1c_calibrate as CAL                            # noqa: E402
import ctrl1c_metrics as CM                               # noqa: E402
import d14b_folds as FD                                   # noqa: E402
import d14b_split as SP                                   # noqa: E402

OUT = ROOT / "results/dashcam/ctrl1c"
STEP, T0, BUDGETS, E_K = C.STEP, C.T0, C.BUDGETS, C.E_K
N_FOLDS = FD.N_FOLDS
TOL = CB.TOL
ARMS_ORDER = CB.ARMS_ORDER
ARM_LABEL = CB.ARM_LABEL

BG_CADENCES_S = (1.0, 2.0, 4.0, 5.0, 6.0, 8.0, 10.0)
CB.BG_CADENCES_S = BG_CADENCES_S        # the reused fitters read this module global

COMMITTED_CHALLENGE = dict(always_cloud=0.5675307471627266, device_only=0.4776042449177038)
E9B_CELL = dict(setting="measured@25", cadence_s=0.5, far=0.05, resolver=("32BI", 1),
                k=2, q=0.75, lmax=10, cooldown=0, horizon=0.0,
                committed_capture={"0.05": 0.03048, "0.10": 0.13311, "0.20": 0.12742,
                                   "0.40": 0.17753})


# ---------------------------------------------------------------- calibration stage
def build_calibration(ctx, sched, kinds: Sequence[str] = CAL.KINDS) -> Dict[str, Any]:
    """Every calibration fitted on the four training folds of each fold, plus two single-map fits
    the policy library can load: the committed DEV-90 side and all 300 clips."""
    fi = FD.folds()
    allc = list(ctx["clips"])
    out: Dict[str, Any] = dict(
        kinds=list(kinds), tiers=[CAL.tier_key(t) for t in CAL.TIERS],
        fold_rule=fi["rule"], by_fold={}, single_map={}, reliability={}, held_out_reliability={})
    for kind in kinds:
        by_fold, rel_tr, rel_ho = {}, {}, {}
        for f in range(N_FOLDS):
            te = FD.train_eval(f)
            m = CAL.fit_maps(ctx, sched, te["train"], kind)
            by_fold[str(f)] = m
            rel_tr[str(f)] = CAL.reliability(ctx, sched, m, te["train"],
                                             instant_label=(kind == "platt_instant"))
            rel_ho[str(f)] = CAL.reliability(ctx, sched, m, te["held"],
                                             instant_label=(kind == "platt_instant"))
        out["by_fold"][kind] = by_fold
        out["reliability"][kind] = rel_tr
        out["held_out_reliability"][kind] = rel_ho
        out["single_map"][kind] = dict(
            dev90=CAL.fit_maps(ctx, sched, SP.split()["dev"], kind),
            all300=CAL.fit_maps(ctx, sched, allc, kind))
    d3 = CAL.fit_maps_d3dev()
    out["kinds"] = list(out["kinds"]) + [CAL.KIND_D3DEV]
    out["by_fold"][CAL.KIND_D3DEV] = {str(f): d3 for f in range(N_FOLDS)}
    out["single_map"][CAL.KIND_D3DEV] = dict(dev90=d3, all300=d3)
    out["reliability"][CAL.KIND_D3DEV] = {
        str(f): CAL.reliability(ctx, sched, d3, FD.train_eval(f)["train"]) for f in range(N_FOLDS)}
    out["held_out_reliability"][CAL.KIND_D3DEV] = {
        str(f): CAL.reliability(ctx, sched, d3, FD.train_eval(f)["held"]) for f in range(N_FOLDS)}
    out["d3dev_note"] = (
        "d3dev is ONE Platt map per tier fitted on the StudyD3 Nexar DEV clips, which are "
        "DISJOINT from the 300 evaluation clips (overlap asserted 0), and it is used for BOTH the "
        "trigger decisions AND the scoring of the delivered stream. Because it never saw any of "
        "the 300 clips it needs no cross-fitting, and because it is ONE map per tier the per-tier "
        "monotone invariance holds exactly, so sanity check (a) passes as written. Its by_fold "
        "entries are deliberately the SAME map for all five folds, so the cross-fitted and the "
        "single-map contexts coincide.")
    out["assignment"] = fi["assignment"]
    out["how_to_load"] = (
        "by_fold[kind][fold][tier] and single_map[kind][scope][tier]. For a platt map the "
        "calibrated log-odds is a * raw_score + b and the probability is its sigmoid; for an "
        "isotonic map the probability is y[searchsorted(x, raw_score, 'left')] clipped to the end "
        "blocks. The policy library should prefer single_map['platt']['dev90'], which is fitted "
        "only on the committed D14b DEV side.")
    out["cross_fitting_note"] = (
        "by_fold[kind][f] is fitted on the FOUR TRAINING FOLDS of fold f and is applied to fold "
        "f's held-out clips. Five folds therefore carry five different maps, and because every "
        "metric in this row is a rank metric ACROSS clips, five different monotone maps are not "
        "one monotone map: the per-tier invariance of a single-tier arm holds for single_map and "
        "NOT for the cross-fitted application. Section 'sanity checks' of the report measures "
        "that difference rather than hiding it.")
    return out


def runners(ctx, sched, cal: Dict[str, Any], kind: str):
    """One Runner per fold on that fold's calibrated arrays, one on the cross-fitted arrays (the
    object every pooled number is computed on), and one on the single all-300 map (used only to
    re-score the identical episodes on ONE common scale, never to make a decision)."""
    maps = cal["by_fold"][kind]
    asg = {k: int(v) for k, v in cal["assignment"].items()}
    per = {f: C.Runner(CAL.calibrated_ctx(ctx, maps[str(f)]), sched) for f in range(N_FOLDS)}
    cross = C.Runner(CAL.crossfit_ctx(ctx, maps, asg), sched)
    one = C.Runner(CAL.calibrated_ctx(ctx, cal["single_map"][kind]["all300"]), sched)
    return per, cross, one


# ---------------------------------------------------------------- per-fold training fits
def _range_of(vals: Sequence[np.ndarray]) -> Tuple[float, float]:
    lo = float(min(float(np.nanmin(v)) for v in vals if len(v)))
    hi = float(max(float(np.nanmax(v)) for v in vals if len(v)))
    pad = max(1e-6, 1e-3 * (hi - lo))
    return lo - pad, hi + pad


def fit_fold(R, chA, train: Sequence[str], fold: int) -> Dict[str, Any]:
    """Every tunable chosen on the four training folds only, on the CALIBRATED scale, against the
    primary metric: maximize the training folds' STREAMING AP of escalation-only at a fixed
    call-fraction budget (C2)."""
    sub_tr = CB.sub_for(R.ctx, train)

    def ap_tr(epi, bg=None) -> float:
        return CM.primary_point(sub_tr, CB.arm_stream(R, train, epi, bg))

    rows: List[Dict[str, Any]] = []
    for w_c in C.GRID_W_C:
        for delta in C.GRID_DELTA:
            for n_c in C.GRID_N_C:
                for mode in C.GRID_MODE:
                    key = (w_c, delta, n_c, mode)
                    for k_c in C.GRID_K_C:
                        def frac(th, key=key, k_c=k_c):
                            return CB.call_fraction(R, R.episodes_all(train, key, th, k_c), None,
                                                    train)
                        for B in BUDGETS:
                            th, f = CB.solve_down(frac, B, -2.0, 12.0, iters=22)
                            epi = R.episodes_all(train, key, th, k_c)
                            rows.append(dict(w_c=w_c, delta=delta, n_c=n_c, mode=mode, k_c=k_c,
                                             budget=B, theta=th, train_call_fraction=f,
                                             train_streaming_ap=ap_tr(epi),
                                             hit_budget=bool(abs(f - B) <= TOL)))
    best = {}
    for B in BUDGETS:
        cand = [r for r in rows if r["budget"] == B and r["hit_budget"]]
        if not cand:
            cand = [r for r in rows if r["budget"] == B]
            cand.sort(key=lambda r: abs(r["train_call_fraction"] - B))
            keep = abs(cand[0]["train_call_fraction"] - B) + 1e-9
            cand = [r for r in cand if abs(r["train_call_fraction"] - B) <= keep]
        cand.sort(key=lambda r: -r["train_streaming_ap"])
        best[str(B)] = cand[0]

    dev_lo, dev_hi = _range_of([R.S[c][2] for c in train])
    cl_lo, cl_hi = _range_of([R.ctx["arrs"][C.CLOUD][c] for c in train])
    absolute, random_cfg, oracle, cloud = {}, {}, {}, {}
    for B in BUDGETS:
        cb = best[str(B)]
        k_c = cb["k_c"]

        def fa(t, k_c=k_c):
            return CB.call_fraction(R, R.abs_episodes_all(train, t, k_c), None, train)
        tau, fv = CB.solve_down(fa, B, dev_lo, dev_hi, iters=34)
        absolute[str(B)] = dict(tau=tau, train_call_fraction=fv, k_c=k_c,
                                search_range=[dev_lo, dev_hi],
                                hit_budget=bool(abs(fv - B) <= TOL))

        epi_b = R.episodes_all(train, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]),
                               cb["theta"], k_c)
        calls = [len(e["calls"]) for c in train for e in epi_b[c]]
        n_call = max(1, int(round(float(np.median(calls)))) if calls else 1)
        lo, hi = 0.0, 1.0
        for _ in range(28):
            mid = 0.5 * (lo + hi)
            if CB.call_fraction(R, R.random_episodes_all(train, mid, n_call), None, train) < B:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        p = 0.5 * (lo + hi)
        random_cfg[str(B)] = dict(
            p_open=p, calls_per_episode=n_call, seed=C.SEED,
            train_call_fraction=CB.call_fraction(
                R, R.random_episodes_all(train, p, n_call), None, train))

        def fit_lead(fn):
            cands = []
            for L in range(0, 400):
                ep = fn(R, chA, train, L)
                f = CB.call_fraction(R, ep, None, train)
                cands.append((abs(f - B), L, f))
                if f > B + 0.5:
                    break
            cands.sort()
            _, L, f = cands[0]
            return dict(lead_calls=L, lead_s=L * R.sched["call_cadence_steps"] * STEP,
                        train_call_fraction=f, hit_budget=bool(abs(f - B) <= TOL),
                        non_causal=True)
        oracle[str(B)] = fit_lead(CB.oracle_episodes)
        oracle[str(B)]["timing_bound"] = fit_lead(CB.oracle_episodes_all)

        feas = []
        for cs in BG_CADENCES_S:
            cstep = int(round(cs / STEP))
            floor = CB.bg_floor(R, cstep)
            if floor > B + TOL:
                feas.append(dict(cadence_s=cs, background_floor=floor, feasible=False,
                                 reason="background sampling alone exceeds the budget"))
                continue

            def fc(t, cstep=cstep, k_c=k_c):
                e, b = CB.cloud_initiated(R, train, cstep, t, k_c)
                return CB.call_fraction(R, e, b, train)
            t_, f_ = CB.solve_down(fc, B, cl_lo, cl_hi, iters=34)
            e, b = CB.cloud_initiated(R, train, cstep, t_, k_c)
            n_ep = sum(len(v) for v in e.values())
            feas.append(dict(cadence_s=cs, background_floor=floor, feasible=True, tau=t_,
                             train_call_fraction=f_, train_streaming_ap=ap_tr(e, b), k_c=k_c,
                             search_range=[cl_lo, cl_hi],
                             hit_budget=bool(abs(f_ - B) <= TOL),
                             n_episodes=n_ep, n_background=sum(len(v) for v in b.values()),
                             trigger_degenerate=bool(n_ep == 0),
                             episode_budget_headroom=float(B - floor)))
        ok = [x for x in feas if x["feasible"]]
        ok.sort(key=lambda x: -x["train_streaming_ap"])
        cloud[str(B)] = dict(
            candidates=feas, chosen=(ok[0] if ok else None),
            infeasible_reason=(None if ok else
                               "no background cadence in %s s fits this budget: the cheapest, "
                               "%.0f s, already costs %.4f of the decision instants"
                               % (list(BG_CADENCES_S), max(BG_CADENCES_S),
                                  CB.bg_floor(R, int(round(max(BG_CADENCES_S) / STEP))))))
    return dict(fold=fold, n_train=len(train), controller=best, absolute=absolute,
                random=random_cfg, oracle=oracle, cloud_initiated=cloud,
                objective=("maximize TRAINING-fold STREAMING AP (mean over horizons 0.5 / 1.0 / "
                           "1.5 s) of escalation-only at a fixed call-fraction budget (C2)"),
                search_ranges=dict(device_score=[dev_lo, dev_hi], cloud_score=[cl_lo, cl_hi],
                                   controller_theta=[-2.0, 12.0]),
                train_references=dict(
                    device_only_streaming_ap=CM.primary_point(sub_tr, R.device_only(train)),
                    always_cloud_streaming_ap=CM.primary_point(sub_tr, R.always_cloud(train))))


def fit_context_trickle(R, train: Sequence[str], fit_l: Dict[str, Any],
                        controller: Dict[str, Any]) -> Dict[str, Any]:
    """Arm (e) on the extended cadence grid, with the calibrated search range and the primary
    metric as the objective. StudyCTRL1b's threshold rule (B9) is carried over unchanged."""
    sub_tr = CB.sub_for(R.ctx, train)
    cl_lo, cl_hi = _range_of([R.ctx["arrs"][C.CLOUD][c] for c in train])
    out = {}
    for B in BUDGETS:
        k_c = controller[str(B)]["k_c"]
        picked, cands = None, []
        for cs in BG_CADENCES_S:
            cstep = int(round(cs / STEP))
            per = CB.context_cstep(R, train, fit_l, cstep)
            floor = float(np.mean([R.sched["call_cadence_steps"] / per[c] for c in train]))
            if floor > B + TOL:
                cands.append(dict(cadence_s=cs, mean_background_floor=floor, feasible=False))
                continue

            def fc(x, per=per, k_c=k_c):
                e, b = CB.cloud_initiated(R, train, per, x, k_c)
                return CB.call_fraction(R, e, b, train)
            tsel, f = CB.solve_down(fc, B, cl_lo, cl_hi, iters=34)
            e, b = CB.cloud_initiated(R, train, per, tsel, k_c)
            n_ep = sum(len(v) for v in e.values())
            cand = dict(cadence_s=cs, tau=tsel, k_c=k_c, train_call_fraction=f, feasible=True,
                        train_streaming_ap=CM.primary_point(sub_tr,
                                                            CB.arm_stream(R, train, e, b)),
                        mean_background_floor=floor, n_episodes=n_ep,
                        trigger_degenerate=bool(n_ep == 0),
                        n_clips_modulated=int(sum(1 for c in train if per[c] != cstep)),
                        search_range=[cl_lo, cl_hi], hit_budget=bool(abs(f - B) <= TOL))
            cands.append(cand)
            if picked is None or cand["train_streaming_ap"] > picked["train_streaming_ap"]:
                picked = cand
        out[str(B)] = dict(chosen=picked, candidates=cands,
                           infeasible_reason=(None if picked else
                                              "no background cadence in %s s fits this budget "
                                              "once the context modulation is applied"
                                              % list(BG_CADENCES_S)))
    return out


# ---------------------------------------------------------------- the load column (C5)
def load_column(budgets: Sequence[float] = BUDGETS) -> Dict[str, Any]:
    """DERIVED, NOT MEASURED. How many devices an H100 could serve at each call-fraction budget,
    from the committed ENG1 step model for one N1 Nexar call."""
    sm = json.loads((ROOT / "results/cost/study_eng1/eng1_step_model.json").read_text())
    k = sm["coef"]
    import study_e9_episodes as E9
    tok = int(E9.PROMPT_TOK[1])
    ms = (k["intercept_ms"] + k["per_tok_ms"] * tok
          + k["per_tok_above_512_ms"] * max(0, tok - 512)
          + k["per_tok_above_2048_ms"] * max(0, tok - 2048)
          + k["per_tok_above_4096_ms"] * max(0, tok - 4096)
          + k["per_encoder_input_ms"] * 1.0
          + k["per_prefill_req_ms"] * 1.0
          + k["per_tok_x_ctx_per_1e6_ms"] * tok * tok / 1e6)
    stall = sm["admission"]["a_ms"] + sm["admission"]["b_ms_per_image"] * 1.0
    per_device_calls_s = {str(b): float(b) / C.T_K for b in budgets}
    rows = []
    for b in budgets:
        r = float(b) / C.T_K
        rows.append(dict(
            budget=float(b), calls_per_second_per_device=r,
            devices_step_only=1000.0 / (ms * r),
            devices_with_admission_stall=1000.0 / ((ms + stall) * r),
            in_flight_requests_at_0395s_latency=r * 0.395))
    return dict(
        label="DERIVED from the committed ENG1 step model; NOT measured in this row",
        source="results/cost/study_eng1/eng1_step_model.json",
        prompt_tokens_n1=tok, prompt_tokens_source="StudyD3 / D4 / D14 PROMPT_TOK[1]",
        step_ms_per_call=float(ms), admission_stall_ms_per_call=float(stall),
        decision_cadence_s=C.T_K, cloud_latency_s=0.395,
        calls_per_second_per_device=per_device_calls_s, rows=rows,
        assumptions=[
            "one escalation call is one N1 Nexar request of %d prompt tokens with one image, "
            "entering the engine as a single prefill request in its own step" % tok,
            "the step model is evaluated at tok = %d, images_in_step = 1, prefill_reqs = 1, "
            "decode_reqs = 0 and ctx = tok, which is the isolated-call reading of a model fitted "
            "on BUSY intervals; the ENG1 report measured the engine to be SUB-LINEAR in batched "
            "small prefills (16-batch / 16 x single = 0.51 at N = 1), so a batched fleet would "
            "fit MORE devices than this column states and the column is a LOWER bound in that "
            "respect" % tok,
            "the device count is a pure throughput bound at 100 % accelerator utilization: "
            "queueing is ignored, so the 0.395 s cloud latency is NOT guaranteed at the stated "
            "count. The in-flight column is Little's law at that arrival rate and is what the "
            "latency budget would have to accommodate",
            "the admission-stall column charges each call the measured multimodal admission stall "
            "(%.1f ms + %.1f ms per image) as if no two calls shared a step, which is the "
            "pessimistic end" % (sm["admission"]["a_ms"], sm["admission"]["b_ms_per_image"]),
            "every device is assumed to run the same workload at the same budget, with no "
            "correlation between devices' escalation times; correlated escalation bursts would "
            "reduce the count",
            "the ENG1 step model was fitted on the H100 NVL (sn4622120321) and on Part A and "
            "Part B E0 steps only; Part C and the HOLDOUT were not used in the fit"],
        interpretation=(
            "the budget is a TEST VARIABLE standing for cloud spare capacity (D58). Read as load: "
            "5 %% of the call rate is about %d devices per H100 and 40 %% about %d, so the budget "
            "axis is a fleet-size axis, and the cells at 5 to 20 %% are the ones a shared H100 "
            "could actually serve."
            % (round(1000.0 / (ms * (0.05 / C.T_K))), round(1000.0 / (ms * (0.40 / C.T_K))))))


# ---------------------------------------------------------------- mechanism verification (C1-C4)
def mechanism_ctrl1c(ctx, sched, cal, per, cross, R_one, fits, chA, kind: str) -> Dict[str, Any]:
    """CLAUDE.md Steps 1 to 5 for what this row CHANGES, on TRAINING folds only and before any
    pooled number is written. StudyCTRL1b's own Steps 1 to 5 for the arms themselves are re-run
    unchanged on the calibrated scale and attached under `ctrl1b_protocol`."""
    f0 = 0
    te = FD.train_eval(f0)
    train = te["train"]
    R = per[f0]
    R_raw = C.Runner(ctx, sched)
    sub_tr = CB.sub_for(R.ctx, train)
    ts, dc = sched["call_cadence_steps"], sched["cloud_shift_steps"]
    chT = C.challenge_for(CB.sub_for(ctx, train))
    pos = CB.sub_for(ctx, train)["pos"]

    chain = (
        "If the two tiers' raw scores are on different scales (StudyCTRL1b measured a median "
        "-5.125 log-unit offset), then a rank metric over a MIXED stream is partly reading tier "
        "identity rather than evidence, so an arm whose calls are label-correlated is rewarded or "
        "punished by the offset alone; a PER-TIER calibration maps each tier's score to the same "
        "quantity, the probability that the clip contains the event (FORMULATION / POLICY_SPEC "
        "v3.1 spec 4.1 as the addendum reads it: u_SH must be a CALIBRATED utility and never a "
        "raw tier score); with the offset removed, the measured ordering of the trigger families "
        "is a statement about WHEN each trigger spends and not about WHICH TIER it spends on, and "
        "the positives-only oracle, which spends only where the label is, must stop scoring below "
        "device-only. In parallel, because the challenge mAP reads one crop per clip, the primary "
        "metric moves to StudyE9b's STREAMING AP over all decision instants, so a trigger that "
        "improves the displayed score away from the single crop is now credited for it; and "
        "because the cheapest pre-registered background cadence cost more than the 5 % and 10 % "
        "budgets, extending the cadence grid is what makes the cloud-initiated family TESTABLE at "
        "those budgets at all.")

    links: List[Dict[str, Any]] = []

    # L1 the offset the calibration exists to remove, raw against calibrated
    def offsets(Rx):
        d = []
        for c in pos:
            for h in chA.incl[c]:
                i = chA.pos_idx[(c, h)]
                if i - dc < 0:
                    continue
                cap = (i - dc) // ts * ts
                d.append(float(Rx.ctx["arrs"][C.CLOUD][c][cap]) - float(Rx.dev[c][i]))
        a = np.asarray([x for x in d if abs(x) < 1e6])
        return dict(n=int(a.size), p50=float(np.median(a)), mean=float(a.mean()),
                    fraction_cloud_higher=float(np.mean(a > 0)))
    raw_all = np.concatenate([ctx["arrs"][C.CLOUD][c] for c in train])
    raw_dev = np.concatenate([ctx["arrs"][C.DEVICE][c] for c in train])
    cal_all = np.concatenate([R.ctx["arrs"][C.CLOUD][c] for c in train])
    cal_dev = np.concatenate([R.ctx["arrs"][C.DEVICE][c] for c in train])
    o_raw, o_cal = offsets(R_raw), offsets(R)
    links.append(dict(
        change="C1 calibration", link="per-tier calibration -> the tiers' scale offset",
        quantity="median of (cloud minus device) at the crop instants of training positives, and "
                 "the two tiers' median over all training instants",
        value=dict(raw_median_offset_all_instants=float(np.median(raw_all) - np.median(raw_dev)),
                   calibrated_median_offset_all_instants=float(np.median(cal_all)
                                                               - np.median(cal_dev)),
                   raw_at_crops=o_raw, calibrated_at_crops=o_cal),
        varies=bool(abs(float(np.median(cal_all) - np.median(cal_dev)))
                    < abs(float(np.median(raw_all) - np.median(raw_dev))) - 1e-9),
        evidence="the quantity the calibration exists to remove is non-zero before it and smaller "
                 "after it; if it were zero before, the calibration could not matter"))

    # L2 calibration -> the oracle artifact
    orc = {}
    for lbl, Rx in (("raw", R_raw), ("calibrated_crossfit", cross), ("calibrated_one_map", R_one)):
        ep_p = CB.oracle_episodes(Rx, chA, train, 0)
        ep_a = CB.oracle_episodes_all(Rx, chA, train, 0)
        orc[lbl] = dict(
            oracle_positives_only_challenge=float(chT.point(CB.arm_stream(Rx, train, ep_p))["mAP"]),
            oracle_every_crop_challenge=float(chT.point(CB.arm_stream(Rx, train, ep_a))["mAP"]),
            device_only_challenge=float(chT.point(Rx.device_only(train))["mAP"]),
            always_cloud_challenge=float(chT.point(Rx.always_cloud(train))["mAP"]),
            oracle_positives_only_streaming=CM.primary_point(
                CB.sub_for(Rx.ctx, train), CB.arm_stream(Rx, train, ep_p)),
            device_only_streaming=CM.primary_point(CB.sub_for(Rx.ctx, train),
                                                   Rx.device_only(train)))
    links.append(dict(
        change="C1 calibration", link="scale offset -> the positives-only oracle's sign",
        quantity="training-fold challenge mAP of the positives-only oracle against device-only, "
                 "raw and calibrated",
        value=orc,
        varies=bool(orc["raw"]["oracle_positives_only_challenge"]
                    != orc["calibrated_crossfit"]["oracle_positives_only_challenge"]),
        evidence="this is the artifact D57 identified; the control in Step 4 is the raw row, which "
                 "is the mechanism-off condition for the calibration"))

    # L3 the primary metric responds to the arms at all
    esc = {}
    for B in BUDGETS:
        cb = fits[str(f0)]["controller"][str(B)]
        e = R.episodes_all(train, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]), cb["theta"],
                           cb["k_c"])
        esc[str(B)] = dict(streaming_ap=CM.primary_point(sub_tr, CB.arm_stream(R, train, e)),
                           call_fraction=CB.call_fraction(R, e, None, train),
                           n_episodes=sum(len(v) for v in e.values()))
    dev_ap = CM.primary_point(sub_tr, R.device_only(train))
    cloud_ap = CM.primary_point(sub_tr, R.always_cloud(train))
    vals = [esc[str(B)]["streaming_ap"] for B in BUDGETS]
    links.append(dict(
        change="C2 primary metric", link="episodes -> delivered score -> STREAMING AP",
        quantity="training-fold streaming AP of the device filter by budget, against the two "
                 "references",
        value=dict(by_budget=esc, device_only=dev_ap, always_cloud=cloud_ap,
                   spread=float(max(vals) - min(vals)),
                   gap=float(cloud_ap - dev_ap)),
        varies=bool(max(vals) - min(vals) > 1e-9 and cloud_ap - dev_ap > 1e-9),
        evidence="the primary metric moves with the budget and the denominator it is divided by is "
                 "non-zero; a constant primary or a zero gap would make every capture fraction "
                 "undefined"))

    # L4 the extended cadence grid is what makes the cloud arm testable
    floors = {("%.0f" % cs): CB.bg_floor(R, int(round(cs / STEP))) for cs in BG_CADENCES_S}
    feas = {}
    for B in BUDGETS:
        ch = fits[str(f0)]["cloud_initiated"][str(B)]
        feas[str(B)] = dict(
            chosen_cadence_s=(ch["chosen"]["cadence_s"] if ch["chosen"] else None),
            n_feasible_cadences=sum(1 for x in ch["candidates"] if x["feasible"]),
            n_feasible_in_ctrl1b_grid=sum(1 for x in ch["candidates"]
                                          if x["feasible"] and x["cadence_s"] in (1.0, 2.0, 4.0)),
            trigger_degenerate=(ch["chosen"]["trigger_degenerate"] if ch["chosen"] else None),
            episode_budget_headroom=(ch["chosen"]["episode_budget_headroom"]
                                     if ch["chosen"] else None))
    links.append(dict(
        change="C3 extended cadences", link="background cadence -> budget floor -> feasibility",
        quantity="the budget each cadence costs before any episode, and how many cadences are "
                 "feasible per budget in the extended grid against StudyCTRL1b's",
        value=dict(background_floor_by_cadence_s=floors, by_budget=feas),
        varies=bool(len(set(round(v, 10) for v in floors.values())) > 1
                    and any(feas[str(B)]["n_feasible_cadences"]
                            > feas[str(B)]["n_feasible_in_ctrl1b_grid"] for B in BUDGETS)),
        evidence="the floor varies across the grid and the extension adds feasible cadences at the "
                 "budgets where StudyCTRL1b had none; where the floor EQUALS the budget the "
                 "trigger has no room to fire and that cell is marked trigger_degenerate, which "
                 "is reported as such and not as a measured arm"))

    # L5 the ceiling target on the calibrated scale
    fl = fits[str(f0)].get("learned")
    if fl is not None:
        w = fl["window"]
        Xc, yc, _sp = CB.learned_matrix(R, train, w["w_c"], w["delta"], w["n_c"])
        Xr, yr, _sp2 = CB.learned_matrix(R_raw, train, w["w_c"], w["delta"], w["n_c"])
        okc = np.isfinite(yc) & np.all(np.isfinite(Xc), axis=1)
        okr = np.isfinite(yr) & np.all(np.isfinite(Xr), axis=1)
        g, l = CB.rebuild_models(fl)
        pg = g.predict(Xc)
        links.append(dict(
            change="C4 retargeted ceiling",
            link="calibrated signed per-instant gain -> the learned prediction",
            quantity="the target's distribution on the calibrated scale against the raw scale, and "
                     "the fitted model's spread",
            value=dict(calibrated=dict(n=int(okc.sum()), mean=float(yc[okc].mean()),
                                       sd=float(yc[okc].std()),
                                       fraction_positive=float(np.mean(yc[okc] > 0))),
                       raw=dict(n=int(okr.sum()), mean=float(yr[okr].mean()),
                                sd=float(yr[okr].std()),
                                fraction_positive=float(np.mean(yr[okr] > 0))),
                       prediction_sd=float(np.std(pg[okc])),
                       gbt_train_r2=LN.r2(yc[okc], pg[okc])),
            varies=bool(yc[okc].std() > 1e-12 and np.std(pg[okc]) > 1e-12),
            evidence="the retargeted objective is non-degenerate and the model's prediction varies "
                     "across instants; a flat prediction would make the ceiling identical to "
                     "random at the same budget"))

    # the affine-invariance check the primary calibration implies
    inv = {}
    for B in BUDGETS:
        cb = fits[str(f0)]["controller"][str(B)]
        key = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
        e_cal = R.episodes_all(train, key, cb["theta"], cb["k_c"])
        e_raw = R_raw.episodes_all(train, key, cb["theta"], cb["k_c"])
        same = all([x["open_i"] for x in e_cal[c]] == [x["open_i"] for x in e_raw[c]]
                   and [x["calls"] for x in e_cal[c]] == [x["calls"] for x in e_raw[c]]
                   for c in train)
        inv[str(B)] = dict(episodes_identical=bool(same),
                           n_episodes_calibrated=sum(len(v) for v in e_cal.values()),
                           n_episodes_raw=sum(len(v) for v in e_raw.values()))

    trace = _trace_unit(R, chA, chT, fits[str(f0)], train, pos, sched)

    controls = dict(
        calibration_disabled=dict(
            control=("the identity map in place of the fitted one, which is the row's raw scale: "
                     "the mechanism-off condition for C1, holding every episode and every budget "
                     "fixed"),
            value=orc,
            reading=("if the positives-only oracle sits below device-only without the calibration "
                     "and at or above it with the calibration, the calibration is what removed "
                     "the artifact. If it sits below in BOTH, the calibration did not fix the "
                     "defect and the sanity-check gate fails")),
        device_scores_through_the_cloud_path=dict(
            control=("the cloud's score replaced by the device's own while the call pattern is "
                     "unchanged, so an escalation buys the cloud PATH and nothing else "
                     "(StudyCTRL1b's control, recomputed on the calibrated scale)"),
            per_budget=_freshness_control(R, chA, fits[str(f0)], train, sub_tr)),
        affine_invariance_of_the_device_filter=dict(
            control=("the device filter's episodes under the fitted theta, computed on the raw "
                     "arrays and on the calibrated ones. Platt is affine with a > 0 and every "
                     "controller signal is divided by the window IQR, so the episodes MUST be "
                     "identical; if they are not, the calibration has changed the controller and "
                     "not only the scale"),
            per_budget=inv))

    alt = (
        "The headline could be produced by (a) the calibration removing the tier offset so that "
        "the metric reads evidence rather than tier identity [the claimed mechanism], or (b) the "
        "calibration merely compressing the score range so that every arm's values crowd together "
        "and the rank metric is driven by ties, or (c) the change of primary metric alone, since "
        "the streaming AP reads every instant and the challenge mAP one crop per clip, so the two "
        "could reorder the arms without any calibration. The three are separated by: for (b), the "
        "affine-invariance control, because an affine map with a > 0 creates no ties and leaves "
        "every single-tier arm's AP bit-identical, which is measured; for (c), the secondary "
        "challenge-mAP table, which is computed on the SAME arms, so the metric change and the "
        "calibration change are reported as separate columns and not as one number. A fourth "
        "explanation cannot be separated here and is stated with the numbers: because the "
        "calibration is CROSS-FITTED, the five folds carry five different affine maps, so a "
        "cross-clip rank metric also sees fold identity; the report measures that by re-scoring "
        "the identical episodes on one common map.")

    return dict(step1_causal_chain=chain, step2_links=links, step3_trace=trace,
                step4_controls=controls,
                step4_cell=dict(side="TRAINING folds of fold 0", clips=len(train),
                                budgets=list(BUDGETS), setting=C.SETTING, calibration=kind),
                step5_alternative=alt,
                calibration_kind=kind)


def _trace_unit(R, chA, chT, fit, train, pos, sched) -> Dict[str, Any]:
    """One traced decision instant and its episode on the calibrated scale, arithmetic included."""
    ts, dc = sched["call_cadence_steps"], sched["cloud_shift_steps"]
    B = BUDGETS[1]
    cb = fit["controller"][str(B)]
    key = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
    for c in pos:
        e = R.episodes_all([c], key, cb["theta"], cb["k_c"])[c]
        if not e:
            continue
        x = e[0]
        cap, read, val = R.S[c]
        st = CB.arm_stream(R, [c], {c: e})[c]
        arr = R.ctx["arrs"][C.CLOUD][c]
        k = int(np.searchsorted(read, x["open_i"], side="right") - 1)
        w_samples = max(int(round(cb["w_c"] / R.cad_s)), 2)
        lo = max(0, k - w_samples + 1)
        win = val[lo:k + 1]
        iqr = float(np.percentile(win, 75) - np.percentile(win, 25))
        med = float(np.median(win))
        return dict(
            clip=c, label="positive", event_s=R.ctx["meta"][c]["event"], budget=B,
            theta=cb["theta"], k_c=cb["k_c"], window=dict(w_c=cb["w_c"], delta=cb["delta"],
                                                          n_c=cb["n_c"], mode=cb["mode"]),
            calibrated_window_samples=[
                dict(sample=int(j), t_capture_s=round(T0 + cap[j] * STEP, 3),
                     t_readable_s=round(T0 + read[j] * STEP, 3),
                     calibrated_log_odds=float(val[j])) for j in range(lo, k + 1)],
            window_median=med, window_iqr=iqr,
            z=(float((val[k] - med) / iqr) if iqr > C.FLAT_IQR else None),
            episode=dict(open_index=x["open_i"], open_time_s=round(T0 + x["open_i"] * STEP, 3),
                         call_times_s=[round(T0 + i * STEP, 3) for i in x["calls"]],
                         delivery_times_s=[round(T0 + (i + dc) * STEP, 3) for i in x["calls"]],
                         calibrated_call_scores=[float(arr[i]) for i in x["calls"]],
                         close_index=x["close_i"], n_calls=len(x["calls"])),
            budget_charged=dict(calls=len(x["calls"]),
                                decision_instants_on_this_clip=len(
                                    range(0, R.ctx["meta"][c]["G"], ts)),
                                call_fraction_on_this_clip=CB.call_fraction(R, {c: e}, None, [c]),
                                background_samples=0),
            displayed_at_crops=[
                dict(horizon_s=h, crop_index=int(chA.pos_idx[(c, h)]),
                     crop_time_s=round(T0 + chA.pos_idx[(c, h)] * STEP, 3),
                     device_only_calibrated=float(R.dev[c][chA.pos_idx[(c, h)]]),
                     arm_calibrated=float(st[chA.pos_idx[(c, h)]]),
                     upgraded_by_the_cloud=bool(st[chA.pos_idx[(c, h)]]
                                                != R.dev[c][chA.pos_idx[(c, h)]]))
                for h in chA.incl[c]],
            arithmetic=(
                "every score listed is the CALIBRATED log-odds a * raw + b of its own tier. The "
                "window median and IQR are computed from the listed device samples; z = (last "
                "sample - median) / IQR and the episode opens at the first decision instant whose "
                "max signal exceeds theta. Each call is captured at its call time and readable %d "
                "grid steps (%.2f s) later; the displayed score at a crop is the most recent "
                "delivery from either tier. The budget charged is calls divided by the clip's own "
                "decision instants on the 0.5-s cadence." % (dc, dc * STEP)))
    return dict(note="no training positive carried an episode at this budget")


def _freshness_control(R, chA, fit, train, sub_tr) -> List[Dict[str, Any]]:
    rows = []
    saved = R.ctx["arrs"][C.CLOUD]
    for B in BUDGETS:
        cb = fit["controller"][str(B)]
        key = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
        epi = R.episodes_all(train, key, cb["theta"], cb["k_c"])
        live = CM.primary_point(sub_tr, CB.arm_stream(R, train, epi))
        try:
            R.ctx["arrs"][C.CLOUD] = R.ctx["arrs"][C.DEVICE]
            same = CM.primary_point(sub_tr, CB.arm_stream(R, train, epi))
        finally:
            R.ctx["arrs"][C.CLOUD] = saved
        dev = CM.primary_point(sub_tr, R.device_only(train))
        rows.append(dict(budget=B, device_filter_streaming_ap=live,
                         device_scores_through_cloud_path=same, device_only=dev,
                         total_gain=live - dev, gain_from_path_freshness=same - dev,
                         gain_from_cloud_score_quality=live - same))
    return rows


# ---------------------------------------------------------------- pooled held-out evaluation
def pool(ctx, sched, cal, per, cross, R_one, fits, chA, kind: str,
         full: bool = True) -> Dict[str, Any]:
    allc = list(ctx["clips"])
    sub_all = CB.sub_for(ctx, allc)
    pos, neg = sub_all["pos"], sub_all["neg"]
    fi = FD.folds()
    held_by_fold = {f: fi["fold"][str(f)]["clips"] for f in range(N_FOLDS)}
    out: Dict[str, Any] = dict(by_budget={}, per_fold={}, calibration_kind=kind)

    for B in BUDGETS:
        streams = {a: {} for a in ARMS_ORDER}
        epi_pool: Dict[str, Dict[str, Any]] = {}
        bg_pool: Dict[str, Dict[str, Any]] = {}
        feas, degen = {}, {}
        for f in range(N_FOLDS):
            held = held_by_fold[f]
            Rf = per[f]
            arms = CB.held_arms(Rf, chA, fits[str(f)], held, B)
            ch = fits[str(f)]["cloud_initiated"][str(B)]["chosen"]
            feas[str(f)] = arms["cloud_feasible"]
            degen[str(f)] = bool(ch["trigger_degenerate"]) if ch else None
            for a in ARMS_ORDER:
                streams[a].update(arms["streams"][a])
            for a, e in arms["episodes"].items():
                epi_pool.setdefault(a, {}).update(e)
            for a, b in arms["background"].items():
                bg_pool.setdefault(a, {}).update(b)

        ap = CM.arms_full(sub_all, streams)
        boot, pern = C.paired_multi(chA, streams, pos, neg)

        realized = {}
        for a in ARMS_ORDER:
            if a in ("device-only", "always-cloud"):
                realized[a] = dict(call_fraction=(0.0 if a == "device-only" else 1.0),
                                   open_time_fraction=(0.0 if a == "device-only" else 1.0))
                continue
            realized[a] = dict(
                call_fraction=CB.call_fraction(cross, epi_pool[a], bg_pool.get(a), allc),
                open_time_fraction=CB.open_fraction(cross, epi_pool[a], allc),
                label_correlation=CB.label_correlation(cross, epi_pool[a], bg_pool.get(a), allc),
                n_calls=CB.n_calls(epi_pool[a], bg_pool.get(a), allc),
                n_episodes=sum(len(v) for v in epi_pool[a].values()),
                n_background=(sum(len(v) for v in bg_pool[a].values()) if a in bg_pool else 0))

        table = []
        for a in ARMS_ORDER:
            if a in ("device-only", "always-cloud"):
                continue
            cap_s = CM.capture(ap, a)
            cap_c = C.gap_fraction(pern, boot["point"], a)
            br_s = CM.capture_difference(ap, a) if a != "random-escalation" else None
            br_c = (C._diff(pern, boot["point"], a, "random-escalation")
                    if a != "random-escalation" else None)
            table.append(dict(
                arm=a, label=ARM_LABEL.get(a, a),
                streaming_ap=ap["primary"][a]["ap"], streaming_ap_ci=ap["primary"][a]["ci"],
                streaming_ap_by_horizon=ap["by_horizon"][a],
                streaming_capture=cap_s["value"], streaming_capture_ci=cap_s["ci"],
                beats_random_streaming=(br_s["excludes_zero"] if br_s else None),
                beats_random_streaming_difference=(br_s["difference"] if br_s else None),
                beats_random_streaming_ci=(br_s["ci"] if br_s else None),
                power=(dict(bootstrap_sd=br_s["bootstrap_sd"],
                            ci_half_width=br_s["ci_half_width"],
                            mde_80pct_power_alpha05=br_s["mde_80pct_power_alpha05"],
                            ci_upper=br_s["ci_upper"],
                            excludes_above_10_points=br_s["excludes_above_10_points"],
                            rule2_power_label=br_s["rule2_power_label"]) if br_s else None),
                challenge_mAP=boot["point"][a], challenge_mAP_ci=boot["ci"][a],
                challenge_capture=cap_c["value"], challenge_capture_ci=cap_c["ci"],
                beats_random_challenge=(br_c["excludes_zero"] if br_c else None),
                beats_random_challenge_difference=(br_c["difference"] if br_c else None),
                beats_random_challenge_ci=(br_c["ci"] if br_c else None),
                call_fraction=realized[a]["call_fraction"],
                open_time_fraction=realized[a]["open_time_fraction"],
                n_episodes=realized[a].get("n_episodes"),
                positive_over_negative_call_rate=(
                    realized[a]["label_correlation"]["positive_over_negative_rate_ratio"]),
                learned=bool(a.startswith("ceiling")), non_causal=bool(a.startswith("oracle"))))

        cell: Dict[str, Any] = dict(
            target_budget=B, capture_table=table, realized=realized,
            streaming_ap=ap["primary"], streaming_ap_by_horizon=ap["by_horizon"],
            challenge_mAP=boot["point"], challenge_mAP_ci=boot["ci"],
            cloud_initiated_feasible_by_fold=feas,
            cloud_initiated_trigger_degenerate_by_fold=degen,
            references=dict(
                device_only_streaming=ap["primary"]["device-only"]["ap"],
                always_cloud_streaming=ap["primary"]["always-cloud"]["ap"],
                device_only_challenge=boot["point"]["device-only"],
                always_cloud_challenge=boot["point"]["always-cloud"],
                gap_streaming=(ap["primary"]["always-cloud"]["ap"]
                               - ap["primary"]["device-only"]["ap"]),
                gap_challenge=boot["point"]["always-cloud"] - boot["point"]["device-only"],
                gap_streaming_ci=CM.ap_difference(ap, "always-cloud", "device-only")["ci"],
                gap_challenge_ci=C._diff(pern, boot["point"], "always-cloud", "device-only")["ci"]),
            settings_by_fold={str(f): dict(
                controller=fits[str(f)]["controller"][str(B)],
                absolute=fits[str(f)]["absolute"][str(B)],
                random=fits[str(f)]["random"][str(B)],
                oracle=fits[str(f)]["oracle"][str(B)],
                cloud_initiated=fits[str(f)]["cloud_initiated"][str(B)]["chosen"],
                cloud_initiated_infeasible=fits[str(f)]["cloud_initiated"][str(B)][
                    "infeasible_reason"],
                context_trickle=fits[str(f)].get("context_trickle", {}).get(str(B), {})
                .get("chosen"),
                learned_thresholds=fits[str(f)].get("learned", {}).get("thresholds", {})
                .get(str(B))) for f in range(N_FOLDS)})

        if full:
            cell["episode_stats"] = {a: C.episode_stats(cross, epi_pool[a], allc, chA, pos, neg)
                                     for a in epi_pool}
            one = {a: CB.arm_stream(R_one, allc, epi_pool[a], bg_pool.get(a))
                   for a in epi_pool}
            one["device-only"] = R_one.device_only(allc)
            one["always-cloud"] = R_one.always_cloud(allc)
            ap1 = CM.arms_full(sub_all, {a: one[a] for a in ARMS_ORDER})
            b1, p1 = C.paired_multi(chA, {a: one[a] for a in ARMS_ORDER}, pos, neg)
            cell["one_common_scale"] = dict(
                note=("the IDENTICAL episodes of the cross-fitted arms, re-scored with ONE "
                      "per-tier map (the all-300 Platt fit) instead of five. This isolates how "
                      "much of the pooled number is the cross-fold scale heterogeneity that "
                      "cross-fitting a calibration introduces into a cross-clip rank metric. The "
                      "single map is fitted with all 300 clips' labels, which is a 2-parameter "
                      "per-tier leak that touches NO decision, only the units of the delivered "
                      "score; it is reported for exactly that reason and is not the primary."),
                streaming_ap={a: ap1["primary"][a]["ap"] for a in ARMS_ORDER},
                challenge_mAP=b1["point"],
                streaming_capture={a: CM.capture(ap1, a)["value"] for a in ARMS_ORDER
                                   if a not in ("device-only", "always-cloud")},
                challenge_capture={a: C.gap_fraction(p1, b1["point"], a)["value"]
                                   for a in ARMS_ORDER
                                   if a not in ("device-only", "always-cloud")},
                beats_random_streaming={a: CM.capture_difference(ap1, a)["excludes_zero"]
                                        for a in ARMS_ORDER
                                        if a not in ("device-only", "always-cloud",
                                                     "random-escalation")})
        out["by_budget"][str(B)] = cell

        for f in range(N_FOLDS):
            held = held_by_fold[f]
            sub_f = CB.sub_for(ctx, held)
            out["per_fold"].setdefault(str(f), {})[str(B)] = {
                a: CM.primary_point(sub_f, {c: streams[a][c] for c in held}) for a in ARMS_ORDER}

    out["metric"] = dict(
        primary=("StudyE9b streaming AP (metrics.streaming_ap / ApEngine, definition unchanged), "
                 "averaged over horizons 0.5 / 1.0 / 1.5 s; each horizon and h = 0 reported"),
        secondary="StudyE9c challenge mAP through StudyE9d's Challenge (metrics.challenge_map)",
        budget="call fraction: total cloud calls / decision instants on the 0.5-s cadence (B1)",
        bootstrap="2,000 paired clip resamples, seed 0, shared across arms within each metric")
    return out


# ---------------------------------------------------------------- StudyE9b recheck
def e9b_recheck(ctx, sched, cal, kind: str) -> Dict[str, Any]:
    """StudyE9b's device-triggered escalation cell, recomputed with the same calibration, cross-
    fitted the same way. Nothing in StudyE9b is edited: its own `run_escalation` is called."""
    import study_e9b_dense as B
    import study_e9_episodes as E9
    asg = {k: int(v) for k, v in cal["assignment"].items()}
    ctx_cal = CAL.crossfit_ctx(ctx, cal["by_fold"][kind], asg)
    ctx_cal["tau"] = E9.fit_thresholds(ctx_cal["arrs"], ctx_cal["meta"], ctx_cal["clips"],
                                       ctx_cal["fold"])
    ctx_one = CAL.calibrated_ctx(ctx, cal["single_map"][kind]["all300"])
    ctx_one["tau"] = E9.fit_thresholds(ctx_one["arrs"], ctx_one["meta"], ctx_one["clips"],
                                       ctx_one["fold"])
    cell = E9B_CELL
    st, cad, far = cell["setting"], cell["cadence_s"], cell["far"]
    arm = tuple(cell["resolver"])
    eng = ctx["eng"]
    out: Dict[str, Any] = dict(
        cell=dict(cell, resolver="%s_N%d" % arm),
        identification=("the committed cell is "
                        "escalation-32B|32BI_N1|measured@25|cad50|far5|trig{5,10,20,40}|q75|k2|"
                        "L10|c0 in results/dashcam/study_e9b/e9b_study1_results.json, scored at "
                        "horizon h = 0 against device-only|measured@25|far5 and "
                        "always-cloud/32BI_N1|measured@25|cad50|far5. StudyCTRL1-episodes' report "
                        "described this as a 1-s grid; it is the 0.25-s grid with a 0.5-s cloud "
                        "call cadence (cad50), which is the SAME cadence this row uses."),
        by_scale={})
    for lbl, cx in (("raw_committed", ctx), ("calibrated_crossfit", ctx_cal),
                    ("calibrated_one_map", ctx_one)):
        seen, mdev, Ddev, Ld = B.dev_seen_all(cx, st)
        mc = int(round(cad / cx["step"]))
        _d, Lc = B.latencies(st, *arm)
        Dc = B.steps_ceil(Lc, cx["step"])
        ac = {c: B.held_stream(cx["arrs"][arm][c], cx["meta"][c]["G"], mc, Dc)
              for c in cx["clips"]}
        pd_, pc_ = eng.point(seen), eng.point(ac)
        rows = {}
        for trig in (0.05, 0.10, 0.20, 0.40):
            r = B.run_escalation(cx, arm[0], arm[1], st, cad, far, trig, cell["k"], cell["q"],
                                 cell["lmax"], cell["cooldown"])
            pe = eng.point(r["streams"])
            h = cell["horizon"]
            den = pc_[h] - pd_[h]
            rows["%.2f" % trig] = dict(
                escalation_ap_h0=float(pe[h]), device_only_ap_h0=float(pd_[h]),
                always_cloud_ap_h0=float(pc_[h]),
                capture=float((pe[h] - pd_[h]) / den) if abs(den) > 1e-15 else None,
                invocations=int(sum(r["inv"].values())),
                ap_by_horizon={str(k): float(v) for k, v in pe.items()},
                primary_mean_0515=float(np.mean([pe[hh] for hh in CM.PRIMARY_HORIZONS])),
                capture_primary=float(
                    (np.mean([pe[hh] for hh in CM.PRIMARY_HORIZONS])
                     - np.mean([pd_[hh] for hh in CM.PRIMARY_HORIZONS]))
                    / (np.mean([pc_[hh] for hh in CM.PRIMARY_HORIZONS])
                       - np.mean([pd_[hh] for hh in CM.PRIMARY_HORIZONS]))))
        out["by_scale"][lbl] = dict(
            device_only_ap={str(k): float(v) for k, v in pd_.items()},
            always_cloud_ap={str(k): float(v) for k, v in pc_.items()},
            by_trigger_rate=rows)
    out["committed_vs_reproduced"] = {
        t: dict(committed=E9B_CELL["committed_capture"][t],
                reproduced_raw=out["by_scale"]["raw_committed"]["by_trigger_rate"][
                    "%.2f" % float(t)]["capture"],
                calibrated=out["by_scale"]["calibrated_crossfit"]["by_trigger_rate"][
                    "%.2f" % float(t)]["capture"],
                calibrated_one_map=out["by_scale"]["calibrated_one_map"]["by_trigger_rate"][
                    "%.2f" % float(t)]["capture"])
        for t in ("0.05", "0.10", "0.20", "0.40")}
    out["note"] = (
        "StudyE9b's alarm, dismiss and trigger thresholds are score QUANTILES of the pooled "
        "negative instants, so under ONE per-tier affine map with a > 0 a quantile maps to the "
        "transformed quantile and every decision, every episode and every invocation count is "
        "identical: only the delivered VALUES move onto a common scale. Under the CROSS-FITTED "
        "calibration that is no longer true, because the pooled negatives carry five different "
        "maps, so a pooled quantile is not the image of the raw quantile and the decisions move "
        "too. The invocation counts for all three scales are reported so this can be checked "
        "rather than asserted, and the one-map row is the clean statement of what the calibration "
        "alone does to the measured capture.")
    return out


# ---------------------------------------------------------------- E9b against random
def e9b_vs_random(ctx, sched, cal, fits, chA, kind: str) -> Dict[str, Any]:
    """StudyE9b's escalation cell beside a RANDOM arm at the same realized cloud work, under the
    primary calibration, with the paired difference in captured fraction and its CI.

    THE BUDGET AXES ARE NOT THE SAME AXIS and that is reported rather than papered over.
    StudyE9b's 5 / 10 / 20 / 40 % is a TRIGGER RATE, a quantile of the device's score on negative
    instants. This row's 5 / 10 / 20 / 40 % is a CALL FRACTION, total cloud calls over decision
    instants (B1). The two differ by about 2x, so each E9b cell is matched to the random arm whose
    REALIZED CALL FRACTION is closest, which is the comparison that holds cloud work fixed, and
    both numbers are printed so the residual mismatch is visible. One cell (trigger 40 %, realized
    call fraction 0.6060) has no comparator in the pre-registered budget grid and is reported with
    none rather than against a mismatched one.

    The pairing is exact: StudyE9b's own ApEngine and this row's are both built from
    `numpy.random.default_rng(SEED)` over the same positive and negative clip lists, and their
    resample index matrices are asserted identical, so a difference may be taken resample by
    resample across the two.
    """
    import study_e9b_dense as B
    import study_e9_episodes as E9
    allc = list(ctx["clips"])
    sub_all = CB.sub_for(ctx, allc)
    maps = cal["by_fold"][kind]
    asg = {k: int(v) for k, v in cal["assignment"].items()}
    cx = CAL.crossfit_ctx(ctx, maps, asg)
    cx["tau"] = E9.fit_thresholds(cx["arrs"], cx["meta"], cx["clips"], cx["fold"])
    eng = ctx["eng"]
    mine = CM.engine(sub_all)
    assert np.array_equal(eng.PI, mine.PI) and np.array_equal(eng.M, mine.M), (
        "the two ApEngine instances do not share their resamples; a paired difference across them "
        "would not be valid")
    H = CM.PRIMARY_HORIZONS

    def boot_primary(streams):
        full, boot = eng.full(streams)
        return (float(np.mean([full[h]["ap"] for h in H])),
                np.mean([boot[h] for h in H], axis=0))

    cell = E9B_CELL
    st, cad, far = cell["setting"], cell["cadence_s"], cell["far"]
    arm = tuple(cell["resolver"])
    seen, _m, _D, _Ld = B.dev_seen_all(cx, st)
    mc = int(round(cad / cx["step"]))
    _d, Lc = B.latencies(st, *arm)
    Dc = B.steps_ceil(Lc, cx["step"])
    ac = {c: B.held_stream(cx["arrs"][arm][c], cx["meta"][c]["G"], mc, Dc) for c in cx["clips"]}
    p_dev, b_dev = boot_primary(seen)
    p_cl, b_cl = boot_primary(ac)
    den_pt = p_cl - p_dev
    den_b = b_cl - b_dev
    ok = np.abs(den_b) > 1e-12
    n_inst = CB.n_instants(C.Runner(ctx, sched), allc)

    # the random arm at each pre-registered budget, from the fitted settings, on the same scale
    Rf = {f: C.Runner(CAL.calibrated_ctx(ctx, maps[str(f)]), sched) for f in range(N_FOLDS)}
    fi = FD.folds()
    rnd = {}
    for Bb in BUDGETS:
        streams, epi = {}, {}
        for f in range(N_FOLDS):
            held = fi["fold"][str(f)]["clips"]
            a = CB.held_arms(Rf[f], chA, fits[str(f)], held, Bb)
            streams.update(a["streams"]["random-escalation"])
            epi.update(a["episodes"]["random-escalation"])
        pt, bt = boot_primary(streams)
        cf = CB.call_fraction(Rf[0], epi, None, allc)
        rnd[str(Bb)] = dict(point=pt, boot=bt, call_fraction=cf,
                            capture=float((pt - p_dev) / den_pt))

    out: Dict[str, Any] = dict(
        calibration_kind=kind, cell=dict(cell, resolver="%s_N%d" % arm),
        references=dict(device_only_primary=p_dev, always_cloud_primary=p_cl, gap=den_pt,
                        note=("StudyE9b's own device-only and always-cloud/32BI_N1 cad50 streams, "
                              "which this row reproduces bit-identically on the raw scale")),
        total_decision_instants=n_inst,
        random_arm_by_budget={k: dict(primary_ap=v["point"], capture=v["capture"],
                                      realized_call_fraction=v["call_fraction"])
                              for k, v in rnd.items()},
        by_trigger_rate={})
    for trig in (0.05, 0.10, 0.20, 0.40):
        r = B.run_escalation(cx, arm[0], arm[1], st, cad, far, trig, cell["k"], cell["q"],
                             cell["lmax"], cell["cooldown"])
        pt, bt = boot_primary(r["streams"])
        inv = int(sum(r["inv"].values()))
        cf = inv / n_inst
        cap_pt = float((pt - p_dev) / den_pt)
        cap_b = (bt[ok] - b_dev[ok]) / den_b[ok]
        best = min(rnd, key=lambda k: abs(rnd[k]["call_fraction"] - cf))
        matched = best if abs(rnd[best]["call_fraction"] - cf) <= 0.15 else None
        row = dict(trigger_rate=trig, invocations=inv, realized_call_fraction=cf,
                   escalation_primary_ap=pt, escalation_capture=cap_pt,
                   escalation_capture_ci=[float(np.percentile(cap_b, 2.5)),
                                          float(np.percentile(cap_b, 97.5))],
                   matched_random_budget=(float(matched) if matched else None),
                   matched_random_realized_call_fraction=(rnd[matched]["call_fraction"]
                                                          if matched else None),
                   budget_axis_note=("StudyE9b's trigger rate is a quantile on negatives, not a "
                                     "call fraction; the match is on realized cloud work"))
        if matched is None:
            row["random_capture"] = None
            row["difference_vs_random"] = None
            row["unmatched_reason"] = (
                "no pre-registered budget has a realized call fraction within 0.15 of %.4f; the "
                "grid stops at 40 %%, whose random arm realizes %.4f" % (cf, rnd["0.4"][
                    "call_fraction"]))
        else:
            d = cap_b - (rnd[matched]["boot"][ok] - b_dev[ok]) / den_b[ok]
            lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
            sd = float(np.std(d, ddof=1))
            row["random_capture"] = rnd[matched]["capture"]
            row["difference_vs_random"] = dict(
                difference=cap_pt - rnd[matched]["capture"], ci=[lo, hi],
                excludes_zero=bool(lo > 0 or hi < 0), bootstrap_sd=sd,
                ci_half_width=float((hi - lo) / 2.0),
                mde_80pct_power_alpha05=float(CM.Z_SUM_80 * sd),
                excludes_above_10_points=bool(hi <= CM.RULE2_BAND),
                rule2_power_label=("real negative" if hi <= CM.RULE2_BAND
                                   else "inconclusive (underpowered)"))
        out["by_trigger_rate"]["%.2f" % trig] = row
    return out


# ---------------------------------------------------------------- sanity checks
def sanity(ctx, sched, cal, per, cross, R_one, chA, kind: str) -> Dict[str, Any]:
    allc = list(ctx["clips"])
    sub_all = CB.sub_for(ctx, allc)
    R_raw = C.Runner(ctx, sched)
    eng = CM.engine(sub_all)

    def refs(Rx):
        return dict(
            challenge_device_only=float(chA.point(Rx.device_only(allc))["mAP"]),
            challenge_always_cloud=float(chA.point(Rx.always_cloud(allc))["mAP"]),
            streaming_device_only={str(h): float(v)
                                   for h, v in eng.point(Rx.device_only(allc)).items()},
            streaming_always_cloud={str(h): float(v)
                                    for h, v in eng.point(Rx.always_cloud(allc)).items()})
    r_raw, r_one, r_cross = refs(R_raw), refs(R_one), refs(cross)
    e9b = json.loads((ROOT / "results/dashcam/study_e9b/e9b_study1_results.json").read_text())
    e9b_dev = {k: float(v["ap"]) for k, v in
               e9b["baselines"]["device-only|measured@25|far5"]["ap"].items()}
    e9b_cloud = {k: float(v["ap"]) for k, v in
                 e9b["baselines"]["always-cloud/32BI_N1|measured@25|cad50|far5"]["ap"].items()}

    def dmax(a, b):
        return max(abs(a[k] - b[k]) for k in a if k in b)

    a = dict(
        what_must_match=(
            "always-cloud and device-only deliver scores from ONE tier only, and a single per-tier "
            "monotone map cannot reorder values within a tier, so their challenge mAP must equal "
            "StudyE9c's committed 0.5675307471627266 and 0.4776042449177038 and their streaming "
            "AP must equal StudyE9b's committed device-only|measured@25|far5 and "
            "always-cloud/32BI_N1|measured@25|cad50|far5 at every horizon."),
        single_map=dict(
            challenge=dict(device_only=r_one["challenge_device_only"],
                           always_cloud=r_one["challenge_always_cloud"],
                           committed_device_only=COMMITTED_CHALLENGE["device_only"],
                           committed_always_cloud=COMMITTED_CHALLENGE["always_cloud"],
                           diff_device=r_one["challenge_device_only"]
                           - COMMITTED_CHALLENGE["device_only"],
                           diff_cloud=r_one["challenge_always_cloud"]
                           - COMMITTED_CHALLENGE["always_cloud"]),
            streaming=dict(device_only=r_one["streaming_device_only"],
                           always_cloud=r_one["streaming_always_cloud"],
                           committed_device_only=e9b_dev, committed_always_cloud=e9b_cloud,
                           max_abs_diff_device=dmax(r_one["streaming_device_only"], e9b_dev),
                           max_abs_diff_cloud=dmax(r_one["streaming_always_cloud"], e9b_cloud)),
            pass_=bool(abs(r_one["challenge_device_only"]
                           - COMMITTED_CHALLENGE["device_only"]) < 1e-15
                       and abs(r_one["challenge_always_cloud"]
                               - COMMITTED_CHALLENGE["always_cloud"]) < 1e-15
                       and dmax(r_one["streaming_device_only"], e9b_dev) < 1e-15
                       and dmax(r_one["streaming_always_cloud"], e9b_cloud) < 1e-15)),
        cross_fitted=dict(
            challenge=dict(device_only=r_cross["challenge_device_only"],
                           always_cloud=r_cross["challenge_always_cloud"],
                           diff_device=r_cross["challenge_device_only"]
                           - COMMITTED_CHALLENGE["device_only"],
                           diff_cloud=r_cross["challenge_always_cloud"]
                           - COMMITTED_CHALLENGE["always_cloud"]),
            streaming=dict(device_only=r_cross["streaming_device_only"],
                           always_cloud=r_cross["streaming_always_cloud"],
                           max_abs_diff_device=dmax(r_cross["streaming_device_only"], e9b_dev),
                           max_abs_diff_cloud=dmax(r_cross["streaming_always_cloud"], e9b_cloud)),
            pass_=bool(abs(r_cross["challenge_device_only"]
                           - COMMITTED_CHALLENGE["device_only"]) < 1e-15
                       and abs(r_cross["challenge_always_cloud"]
                               - COMMITTED_CHALLENGE["always_cloud"]) < 1e-15)),
        raw_reproduction=dict(
            challenge=dict(device_only=r_raw["challenge_device_only"],
                           always_cloud=r_raw["challenge_always_cloud"],
                           diff_device=r_raw["challenge_device_only"]
                           - COMMITTED_CHALLENGE["device_only"],
                           diff_cloud=r_raw["challenge_always_cloud"]
                           - COMMITTED_CHALLENGE["always_cloud"]),
            streaming_max_abs_diff=dict(
                device=dmax(r_raw["streaming_device_only"], e9b_dev),
                cloud=dmax(r_raw["streaming_always_cloud"], e9b_cloud))),
        explanation=(
            ("under d3dev there is ONE map per tier for every clip and every fold, so the "
             "cross-fitted and the single-map contexts are the same object and the invariance "
             "holds EXACTLY in both: the committed references reproduce to machine zero and "
             "sanity check (a) passes as written.")
            if kind == CAL.KIND_D3DEV else
            ("the invariance holds EXACTLY for one map per tier and CANNOT hold for the "
             "cross-fitted application, because five folds carry five different affine maps and "
             "both metrics rank ACROSS clips: a value from fold 0 and a value from fold 1 are no "
             "longer on one scale. This is a property of cross-fitting a calibration under a "
             "cross-clip rank metric, not of the calibration, and it is reported with its size "
             "rather than absorbed.")))

    # gate (b): the positives-only oracle against device-only on challenge mAP
    gate = {}
    for lbl, Rx in (("raw", R_raw), ("calibrated_crossfit", cross), ("calibrated_one_map", R_one)):
        ep = CB.oracle_episodes(Rx, chA, allc, 0)
        ep_a = CB.oracle_episodes_all(Rx, chA, allc, 0)
        gate[lbl] = dict(
            oracle_positives_only=float(chA.point(CB.arm_stream(Rx, allc, ep))["mAP"]),
            oracle_every_crop=float(chA.point(CB.arm_stream(Rx, allc, ep_a))["mAP"]),
            device_only=float(chA.point(Rx.device_only(allc))["mAP"]),
            always_cloud=float(chA.point(Rx.always_cloud(allc))["mAP"]))
        gate[lbl]["oracle_at_or_above_device_only"] = bool(
            gate[lbl]["oracle_positives_only"] >= gate[lbl]["device_only"] - 1e-12)
        gate[lbl]["margin"] = (gate[lbl]["oracle_positives_only"] - gate[lbl]["device_only"])

    # gate (c): no held-out clip in any fit
    fi = FD.folds()
    leak = []
    for f in range(N_FOLDS):
        te = FD.train_eval(f)
        ov = sorted(set(te["train"]) & set(te["held"]))
        m = cal["by_fold"][kind]["%d" % f][CAL.tier_key(C.DEVICE)]
        leak.append(dict(fold=f, n_train=len(te["train"]), n_held=len(te["held"]),
                         overlap=len(ov),
                         calibration_fitted_on_n_clips=m["n_clips_fitted_on"],
                         calibration_overlap_with_the_300=(
                             m["d3_sample"]["overlap_with_evaluation_clips"]
                             if kind == CAL.KIND_D3DEV else None)))
    assert all(x["overlap"] == 0 for x in leak)
    if kind == CAL.KIND_D3DEV:
        # the d3dev map is fitted on a DISJOINT split, so it is not fitted on the 240 training
        # clips and must not be; the leak-free condition is that none of the 300 enters it
        assert all(x["calibration_overlap_with_the_300"] == 0 for x in leak)
        leak_note = ("every tunable is fitted on exactly the 240 training clips of its fold and "
                     "train / held-out overlap is 0 in all 5 folds; the CALIBRATION is one map "
                     "per tier fitted on the 601 StudyD3 Nexar DEV clips, of which 0 are among "
                     "the 300 evaluation clips, which is strictly stronger than cross-fitting")
    else:
        assert all(x["calibration_fitted_on_n_clips"] == x["n_train"] for x in leak)
        leak_note = ("every calibration and every tunable is fitted on exactly the 240 training "
                     "clips of its fold; train and held-out overlap is 0 in all 5 folds")

    return dict(check_a_references_unchanged=a,
                check_b_positives_only_oracle=dict(
                    requirement=("the positives-only oracle must score at or above device-only on "
                                 "challenge mAP; if it does not, STOP and report"),
                    per_scale=gate,
                    pass_=bool(gate["calibrated_crossfit"]["oracle_at_or_above_device_only"]),
                    pass_on_one_map=bool(
                        gate["calibrated_one_map"]["oracle_at_or_above_device_only"])),
                check_c_no_leakage=dict(per_fold=leak, pass_=True, asserted=leak_note),
                check_metric_engine=CM.assert_matches_metrics_module(
                    sub_all, cross.device_only(allc)))


# ---------------------------------------------------------------- CLI
def main() -> int:
    import argparse
    from _provenance import stamp
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=("calibrate", "fit", "fit2", "mechanism", "pool", "sens", "e9b",
                             "load", "e9brandom", "all"))
    ap.add_argument("--kind", default="platt", choices=list(CAL.ALL_KINDS))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t_all = time.time()
    ctx, sched = C.context()
    allc = list(ctx["clips"])
    chA = C.challenge_for(CB.sub_for(ctx, allc))
    fi = FD.folds()
    print("folds: %s" % {f: fi["fold"][str(f)]["n"] for f in range(N_FOLDS)}, flush=True)
    print("background cadences: %s" % ", ".join(
        "%.0f s costs %.4f" % (cs, 2.0 / round(cs / STEP)) for cs in BG_CADENCES_S), flush=True)

    cal_file = OUT / "ctrl1c_calibration.json"
    if a.stage in ("calibrate", "all"):
        t = time.time()
        cal = build_calibration(ctx, sched)
        cal["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage calibrate", model=None,
                                   device="cpu", n=300, args=None)
        cal_file.write_text(json.dumps(cal, indent=1, default=float))
        for kind in cal["kinds"]:
            for f in range(N_FOLDS):
                m = cal["by_fold"][kind][str(f)]
                if kind == "isotonic":
                    print("  %-13s fold %d: blocks dev %d cloud %d"
                          % (kind, f, m[CAL.tier_key(C.DEVICE)]["n_blocks"],
                             m[CAL.tier_key(C.CLOUD)]["n_blocks"]), flush=True)
                else:
                    print("  %-13s fold %d: dev a %+.6f b %+.4f | cloud a %+.6f b %+.4f"
                          % (kind, f, m[CAL.tier_key(C.DEVICE)]["a"],
                             m[CAL.tier_key(C.DEVICE)]["b"], m[CAL.tier_key(C.CLOUD)]["a"],
                             m[CAL.tier_key(C.CLOUD)]["b"]), flush=True)
        print("calibrate: %.0f s; wrote %s" % (time.time() - t, cal_file), flush=True)

    cal = json.loads(cal_file.read_text())
    kind = a.kind
    per, cross, R_one = runners(ctx, sched, cal, kind)
    fits_file = OUT / ("ctrl1c_fits_%s.json" % kind)

    if a.stage in ("fit", "all"):
        t = time.time()
        fits = {}
        for f in range(N_FOLDS):
            te = FD.train_eval(f)
            tf = time.time()
            fits[str(f)] = fit_fold(per[f], chA, te["train"], f)
            print("fold %d fitted on %d clips in %.0f s" % (f, len(te["train"]),
                                                            time.time() - tf), flush=True)
            for B in BUDGETS:
                cb = fits[str(f)]["controller"][str(B)]
                cl = fits[str(f)]["cloud_initiated"][str(B)]["chosen"]
                print("   budget %3.0f %%: theta %7.4f W_c %.1f delta %.2f n_c %d K_c %d %-5s "
                      "frac %.4f ap %.5f | oracle lead %3d | cloud %s"
                      % (100 * B, cb["theta"], cb["w_c"], cb["delta"], cb["n_c"], cb["k_c"],
                         cb["mode"], cb["train_call_fraction"], cb["train_streaming_ap"],
                         fits[str(f)]["oracle"][str(B)]["lead_calls"],
                         ("c=%.0f s tau %.3f%s" % (cl["cadence_s"], cl["tau"],
                                                   " DEGENERATE-TRIGGER"
                                                   if cl["trigger_degenerate"] else ""))
                         if cl else "INFEASIBLE"), flush=True)
        obj = dict(fits=fits, folds=fi["rule"], budgets=list(BUDGETS), calibration_kind=kind,
                   budget_metric="call fraction (B1), unchanged from StudyCTRL1b",
                   objective=("maximize TRAINING-fold STREAMING AP (mean over 0.5 / 1.0 / 1.5 s) "
                              "of escalation-only at a fixed call-fraction budget (C2)"),
                   grid=dict(W_c=list(C.GRID_W_C), delta=list(C.GRID_DELTA),
                             n_c=list(C.GRID_N_C), K_c=list(C.GRID_K_C),
                             instability_mode=list(C.GRID_MODE),
                             background_cadence_s=list(BG_CADENCES_S)),
                   schedule=sched)
        obj["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage fit", model=None,
                                   device="cpu", n=300, args=None)
        fits_file.write_text(json.dumps(obj, indent=1, default=float))
        print("fit: %.0f s; wrote %s" % (time.time() - t, fits_file), flush=True)

    needs_fits = a.stage in ("fit2", "mechanism", "pool", "sens", "e9brandom", "all")
    if needs_fits and not fits_file.exists():
        print("no fits for kind %r yet; run --stage fit first" % kind, flush=True)
        return 1
    obj_all = json.loads(fits_file.read_text()) if fits_file.exists() else dict(fits={})
    fits = obj_all["fits"]

    if a.stage in ("fit2", "all"):
        t = time.time()
        for f in range(N_FOLDS):
            te = FD.train_eval(f)
            fl = CB.fit_learned(per[f], chA, te["train"], f, fits[str(f)]["controller"])
            fits[str(f)]["learned"] = fl
            fits[str(f)]["context_trickle"] = fit_context_trickle(
                per[f], te["train"], fl, fits[str(f)]["controller"])
            top = sorted(fl["importances"]["gbt"].items(), key=lambda kv: -kv[1])[:3]
            print("fold %d learned: GBT r2 %.4f, logistic AUC %.4f, top %s, context %s (%.4f)"
                  % (f, fl["fit_quality"]["gbt_train_r2"],
                     fl["fit_quality"]["logistic_train_auc"],
                     [(k, round(v, 3)) for k, v in top], fl["context"]["feature"],
                     fl["context"]["gbt_importance"]), flush=True)
            for B in BUDGETS:
                ct = fits[str(f)]["context_trickle"][str(B)]["chosen"]
                print("   budget %3.0f %%: ceiling theta %+.5f | context trickle %s"
                      % (100 * B, fl["thresholds"][str(B)]["ceiling-gbt"]["theta"],
                         ("c=%.0f s tau %.3f frac %.4f%s"
                          % (ct["cadence_s"], ct["tau"], ct["train_call_fraction"],
                             " DEGENERATE-TRIGGER" if ct["trigger_degenerate"] else ""))
                         if ct else "INFEASIBLE"), flush=True)
        obj_all["fits"] = fits
        obj_all["features"] = dict(used=list(LN.FEATURES), not_available=LN.NOT_AVAILABLE)
        obj_all["_provenance_fit2"] = stamp(script="ctrl1c_crossfit.py --stage fit2", model=None,
                                            device="cpu", n=300, args=None)
        fits_file.write_text(json.dumps(obj_all, indent=1, default=float))
        print("fit2: %.0f s; wrote %s" % (time.time() - t, fits_file), flush=True)
        fits = json.loads(fits_file.read_text())["fits"]

    mech_file = OUT / ("ctrl1c_mechanism_%s.json" % kind)
    if a.stage in ("mechanism", "all"):
        t = time.time()
        mech = mechanism_ctrl1c(ctx, sched, cal, per, cross, R_one, fits, chA, kind)
        te = FD.train_eval(0)
        mech["ctrl1b_protocol"] = dict(
            note=("StudyCTRL1b's own Steps 1 to 5 for the arms themselves, re-run UNCHANGED on "
                  "the calibrated scale, so that the arms' links are verified in this row too and "
                  "not inherited"),
            new_arms=CB.mechanism_new_arms(per[0], chA, fits["0"], te["train"]),
            learned_arms=(CB.mechanism_learned_arms(per[0], chA, fits["0"], te["train"])
                          if "learned" in fits["0"] else None))
        mech["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage mechanism", model=None,
                                    device="cpu", n=len(te["train"]), args=None)
        mech_file.write_text(json.dumps(mech, indent=1, default=float))
        for l in mech["step2_links"]:
            print("  LINK %-22s %-46s varies=%s" % (l["change"], l["link"][:46], l["varies"]),
                  flush=True)
        for B in BUDGETS:
            r = mech["step4_controls"]["affine_invariance_of_the_device_filter"]["per_budget"][
                str(B)]
            print("  affine invariance %3.0f %%: episodes identical %s" % (100 * B,
                                                                          r["episodes_identical"]),
                  flush=True)
        print("mechanism: %.0f s; wrote %s" % (time.time() - t, mech_file), flush=True)

    if a.stage in ("pool", "all"):
        assert mech_file.exists(), ("mechanism verification must be recorded BEFORE the pooled "
                                    "numbers are written")
        t = time.time()
        res = pool(ctx, sched, cal, per, cross, R_one, fits, chA, kind, full=True)
        res["sanity"] = sanity(ctx, sched, cal, per, cross, R_one, chA, kind)
        res["fold_rule"] = fi["rule"]
        res["supersedes"] = ("StudyCTRL1b-crossfit's capture table is SUPERSEDED FOR COMPARISON by "
                             "this one, not deleted: it is kept in results/dashcam/ctrl1b/ and "
                             "reports/study_ctrl1b_crossfit.md, and its defects are named there "
                             "and here")
        res["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage pool", model=None,
                                   device="cpu", n=300, args=None)
        (OUT / ("ctrl1c_pooled_%s.json" % kind)).write_text(json.dumps(res, indent=1,
                                                                       default=float))
        for B in BUDGETS:
            cell = res["by_budget"][str(B)]
            print("budget %3.0f %% (streaming gap %.5f, challenge gap %.4f)"
                  % (100 * B, cell["references"]["gap_streaming"],
                     cell["references"]["gap_challenge"]), flush=True)
            for r in cell["capture_table"]:
                print("   %-22s ap %.5f cap %7.1f %% [%6.1f, %6.1f] beats-random %-5s | mAP "
                      "%.4f cap %7.1f %% | frac %.4f"
                      % (r["arm"], r["streaming_ap"], 100 * (r["streaming_capture"] or 0),
                         100 * (r["streaming_capture_ci"] or [0, 0])[0],
                         100 * (r["streaming_capture_ci"] or [0, 0])[1],
                         r["beats_random_streaming"], r["challenge_mAP"],
                         100 * (r["challenge_capture"] or 0), r["call_fraction"]), flush=True)
        s = res["sanity"]
        print("SANITY a single-map pass=%s cross-fitted pass=%s; b oracle pass=%s (margin %+.4f) "
              "one-map %s; c leakage pass=%s"
              % (s["check_a_references_unchanged"]["single_map"]["pass_"],
                 s["check_a_references_unchanged"]["cross_fitted"]["pass_"],
                 s["check_b_positives_only_oracle"]["pass_"],
                 s["check_b_positives_only_oracle"]["per_scale"]["calibrated_crossfit"]["margin"],
                 s["check_b_positives_only_oracle"]["pass_on_one_map"],
                 s["check_c_no_leakage"]["pass_"]), flush=True)
        print("pool: %.0f s" % (time.time() - t), flush=True)

    if a.stage in ("sens",):
        t = time.time()
        res = pool(ctx, sched, cal, per, cross, R_one, fits, chA, kind, full=False)
        res["sanity"] = sanity(ctx, sched, cal, per, cross, R_one, chA, kind)
        res["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage sens", model=None,
                                   device="cpu", n=300, args=None)
        (OUT / ("ctrl1c_pooled_%s.json" % kind)).write_text(json.dumps(res, indent=1,
                                                                       default=float))
        print("sens %s: %.0f s" % (kind, time.time() - t), flush=True)

    if a.stage in ("e9b", "all"):
        t = time.time()
        r = e9b_recheck(ctx, sched, cal, kind)
        r["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage e9b", model=None,
                                 device="cpu", n=300, args=None)
        (OUT / ("ctrl1c_e9b_recheck_%s.json" % kind)).write_text(json.dumps(r, indent=1,
                                                                            default=float))
        for k, v in r["committed_vs_reproduced"].items():
            print("  E9b trig %s: committed %.4f, reproduced raw %.4f, calibrated %.4f"
                  % (k, v["committed"], v["reproduced_raw"], v["calibrated"]), flush=True)
        print("e9b: %.0f s" % (time.time() - t), flush=True)

    if a.stage in ("e9brandom", "all"):
        t = time.time()
        r = e9b_vs_random(ctx, sched, cal, fits, chA, kind)
        r["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage e9brandom", model=None,
                                 device="cpu", n=300, args=None)
        (OUT / ("ctrl1c_e9b_vs_random_%s.json" % kind)).write_text(json.dumps(r, indent=1,
                                                                              default=float))
        for k, v in r["by_trigger_rate"].items():
            if v["difference_vs_random"] is None:
                print("  E9b trig %s: capture %+.1f %% [%+.1f, %+.1f], realized frac %.4f, NO "
                      "MATCHED RANDOM ARM" % (k, 100 * v["escalation_capture"],
                                              100 * v["escalation_capture_ci"][0],
                                              100 * v["escalation_capture_ci"][1],
                                              v["realized_call_fraction"]), flush=True)
            else:
                d = v["difference_vs_random"]
                print("  E9b trig %s: capture %+.1f %% vs random %+.1f %% (budget %.0f %%, frac "
                      "%.4f vs %.4f); difference %+.1f %% [%+.1f, %+.1f] excl0 %s %s"
                      % (k, 100 * v["escalation_capture"], 100 * v["random_capture"],
                         100 * v["matched_random_budget"], v["realized_call_fraction"],
                         v["matched_random_realized_call_fraction"], 100 * d["difference"],
                         100 * d["ci"][0], 100 * d["ci"][1], d["excludes_zero"],
                         d["rule2_power_label"]), flush=True)
        print("e9brandom: %.0f s" % (time.time() - t), flush=True)

    if a.stage in ("load", "all"):
        lc = load_column()
        lc["_provenance"] = stamp(script="ctrl1c_crossfit.py --stage load", model=None,
                                  device="cpu", n=None, args=None)
        (OUT / "ctrl1c_load_column.json").write_text(json.dumps(lc, indent=1, default=float))
        for row in lc["rows"]:
            print("  budget %3.0f %%: %.2f calls/s/device -> %.1f devices per H100 (%.1f with the "
                  "admission stall)" % (100 * row["budget"], row["calls_per_second_per_device"],
                                        row["devices_step_only"],
                                        row["devices_with_admission_stall"]), flush=True)

    print("TOTAL %.0f s" % (time.time() - t_all), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
