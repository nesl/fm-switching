#!/usr/bin/env python3
"""StudyCTRL1b-crossfit: StudyCTRL1-episodes and StudyFRAMES1 re-run with 5-fold cross-fitting on
all 300 StudyD14b clips, with an oracle trigger and a cloud-initiated trigger added. CPU only; no
GPU, no model server, no inference. Every score is a committed StudyD14b trace.

Pre-registered in `research/EXPERIMENTS.md` (StudyCTRL1b-crossfit) before anything was computed,
including the fold rule (`d14b_folds.py`), the budget metric and the objective.

WHY. StudyCTRL1 fitted on 90 clips and reported on 210, and the 210-clip subset could not resolve
the always-cloud minus device-only gap it measured against. Cross-fitting keeps the no-peeking
property and scores every one of the 300 clips held out, so the pooled metric carries the power of
the whole set. The 90/210 results are kept in the report as SUPERSEDED, not deleted.

THE BUDGET METRIC IS NEW AND IS NOT StudyCTRL1'S (B1 below). StudyCTRL1 charged an arm the
fraction of device-time with an OPEN EPISODE. That cannot price the cloud-initiated arm, whose
background samples occupy no episode at all. So the pre-registered budget here is

    budget = total cloud calls / total decision instants on the 0.5-s cadence

which charges a background sample and an episode follow-up call the same, since each is one cloud
call. StudyCTRL1's open-time fraction is computed and reported beside it for every arm.

DECISIONS THE BRIEF AND THE SPEC LEAVE OPEN, each recorded here and in the report rather than
silently taken. A1-A5 of `ctrl1_controller.py` still hold and are not restated.

  (B1) The budget metric, above. Both metrics are reported for every arm at every budget.

  (B2) The ORACLE TRIGGER is non-causal by construction: it places calls so that a cloud answer
       is delivered exactly at each challenge crop instant of each POSITIVE clip, and never calls
       on a negative clip. Its budget knob is a LEAD EXTENSION: L extra calls at the same 0.5-s
       cadence before the first needed call, L solved on the training folds to hit the budget.

  (B2b) THE BRIEF'S TWO REQUIREMENTS FOR THE ORACLE CANNOT BOTH HOLD, and this is measured, not
       argued. "Escalate exactly over the challenge-horizon windows before each positive event"
       and "an upper bound on any trigger at that budget" are incompatible, because the challenge
       metric is a RANK metric over one crop per clip and the two tiers' scores live on different
       scales: over all 300 clips the 32B's score is a median 3.25 log units BELOW the 4B's at the
       crop instants. Replacing the score on positives only therefore drags the positives DOWN
       the ranking and the positives-only oracle scores BELOW device-only. Both readings are
       therefore computed and reported:
         `oracle-trigger`      the brief's literal arm, positives only;
         `oracle-timing-bound` the same placement on EVERY clip's crop instant, positive and
                               negative alike, which is the arm that actually bounds timing.
       Nothing is hidden by this: the positives-only number is reported as the headline the brief
       asked for, and the artifact behind it is the most consequential finding of the row.

  (B2c) The oracle's metric value is EXACTLY INVARIANT to the lead extension, because the crop
       instant is served by the same call whatever the lead, and the challenge metric reads no
       other instant. The budget matching is therefore cosmetic for the oracle and is reported as
       a CONSTANT link in the mechanism verification rather than passed off as a swept knob.

  (B3) The CLOUD-INITIATED arm's episode-close rule is not given in the brief. The cloud decides
       with the only thing it has, its own delivered scores: an episode closes when K_c
       consecutive episode-call scores whose read time has passed fall at or below the threshold,
       or after E_k calls. K_c is taken from the escalation-only arm chosen at the same budget on
       the same training folds rather than tuned separately, so the two arms differ in trigger
       and not in episode length policy.

  (B4) Background sampling is NOT charged while an episode is open, because the episode already
       samples the same stream at a faster cadence. Charging both would price the arm for work it
       does not do.

  (B5) Causality of the cloud-initiated trigger is enforced: a background sample captured at
       instant i is read by the cloud dc grid steps later, so its episode can only open at the
       first decision instant at or after i + dc.

  (B7) The threshold searches for the absolute-confidence and cloud-initiated arms bisect over
       [-30, 0.5] log units, not over the narrower range StudyCTRL1 used for the device score.
       The 32B's scores run lower than the 4B's (p05 -23.0 against -18.25), so the narrower range
       could not reach the 40 % budget at all and would have reported a budget the arm never
       spent. The range is a search bound, not a model parameter, and every arm's REALIZED budget
       is reported next to its target.

  (B8) The PREDICTABILITY-CEILING target is the SIGNED per-instant cloud gain: (the cloud's
       score at the instant minus the device's displayed score), times +1 on a positive clip and
       -1 on a negative one. The sign is what turns a score difference into a utility, and this
       row's own central finding forces it: the two tiers' scores are on different scales, so an
       unsigned target would teach the model to escalate wherever the cloud's score is merely
       lower. The models never see the label or the sign; recovering it from features is the
       predictability question. Three feature families the brief asks for are NOT COMPUTABLE here
       and are listed with their reasons in `ctrl1b_learned.NOT_AVAILABLE`: no visual feature
       (the frame store is absent from this machine), no ego speed (it does not exist in the
       committed Nexar table), and elapsed time is excluded by decision because it would leak the
       dataset's event placement. The ceiling is therefore a ceiling on SCORE-DYNAMICS-AND-CONTEXT
       predictability, which is said wherever the number appears.

  (B9) The CONTEXT-MODULATED TRICKLE's context signal is the strongest NON-SCORE feature by the
       training folds' own boosted-tree importance, with its threshold at 0.5 for a BINARY
       feature and at the training-fold MEDIAN for a continuous one; neither is fitted to the
       outcome. The median alone was the first rule and it DEGENERATES on a one-hot feature whose
       category covers more than half the rows, since the median is then 1.0 and the strict test
       never fires; mechanism verification Step 2 caught that as a CONSTANT link before any
       pooled number existed, and the rule was corrected rather than the arm being reported
       degenerate. Every available non-score feature is CLIP-LEVEL
       Nexar metadata, so the modulation is per clip rather than per instant; with the frame store
       present it would be a per-instant visual signal instead.

  (B6) StudyFRAMES1 HAS NO TUNABLE in its matched-delay form, so cross-fitting it would be
       identical to pooling. Two things are therefore reported: the pooled all-300 curve with
       per-fold values (which is a power gain, not a bias removal), and a genuine cross-fitted
       object, CHOOSE-N: pick the better N per delay on the 4 training folds and apply that choice
       to the held-out fold. That is the thing a DEV-fitted profile table would actually do, and
       it is the direct test of whether the DEV frame bonus transfers.
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
import ctrl1b_learned as LN                               # noqa: E402
import d14b_folds as FD                                   # noqa: E402
import d14b_split as SP                                   # noqa: E402
import metrics as M                                       # noqa: E402

OUT = ROOT / "results/dashcam/ctrl1b"
STEP = C.STEP
T0 = C.T0
BUDGETS = C.BUDGETS
E_K = C.E_K
NB, SEED = C.NB, C.SEED
BG_CADENCES_S = (1.0, 2.0, 4.0)
TOL = 0.0025
N_FOLDS = FD.N_FOLDS

ARMS_ORDER = ("device-only", "always-cloud", "escalation-only", "oracle-trigger",
              "oracle-timing-bound", "cloud-initiated", "context-trickle", "ceiling-gbt",
              "ceiling-logistic", "absolute-confidence", "random-escalation")

# the brief's names for the arms, used in the capture-fraction table
ARM_LABEL = {"escalation-only": "device filter (spec 7.7)",
             "cloud-initiated": "cloud trickle",
             "context-trickle": "context-modulated trickle",
             "ceiling-gbt": "predictability ceiling, boosted trees (LEARNED)",
             "ceiling-logistic": "predictability ceiling, logistic (LEARNED)",
             "oracle-trigger": "oracle trigger, positives only (NON-CAUSAL)",
             "oracle-timing-bound": "oracle timing bound, every crop (NON-CAUSAL)",
             "absolute-confidence": "absolute-confidence trigger",
             "random-escalation": "random escalation"}


# ---------------------------------------------------------------- subsets and budget metrics
def sub_for(ctx, clips: Sequence[str]) -> Dict[str, Any]:
    """A metric context restricted to a clip list. Only the positive and negative lists move, so
    the committed crop geometry is untouched (see d14b_split.subset_ctx)."""
    keep = set(clips)
    s = dict(ctx)
    s["pos"] = [c for c in ctx["pos"] if c in keep]
    s["neg"] = [c for c in ctx["neg"] if c in keep]
    s["scored_clips"] = [c for c in ctx["clips"] if c in keep]
    s["pos_pts"] = sum(ctx["meta"][c]["G"] for c in s["pos"])
    s["neg_pts"] = sum(ctx["meta"][c]["G"] for c in s["neg"])
    s["hours_pos"] = s["pos_pts"] * ctx["step"] / 3600.0
    s["hours_neg"] = s["neg_pts"] * ctx["step"] / 3600.0
    s["hours_all"] = s["hours_pos"] + s["hours_neg"]
    return s


def n_instants(R, clips: Sequence[str]) -> int:
    ts = R.sched["call_cadence_steps"]
    return sum(len(range(0, R.ctx["meta"][c]["G"], ts)) for c in clips)


def n_calls(epi: Dict[str, List[Dict[str, Any]]], bg: Optional[Dict[str, List[int]]],
            clips: Sequence[str]) -> int:
    t = sum(len(e["calls"]) for c in clips for e in epi.get(c, []))
    if bg:
        t += sum(len(bg.get(c, [])) for c in clips)
    return t


def call_fraction(R, epi, bg, clips: Sequence[str]) -> float:
    d = n_instants(R, clips)
    return n_calls(epi, bg, clips) / d if d else 0.0


def open_fraction(R, epi, clips: Sequence[str]) -> float:
    on = tot = 0
    for c in clips:
        G = R.ctx["meta"][c]["G"]
        on += int(C.open_mask(epi.get(c, []), G).sum())
        tot += G
    return on / tot if tot else 0.0


def label_correlation(R, epi, bg, clips: Sequence[str]) -> Dict[str, Any]:
    """How much of an arm's spending lands on POSITIVE clips. The two tiers' scores are on
    different scales, so an arm whose calls are label-correlated biases the rank metric whatever
    its timing is; this is the statistic that measures that exposure."""
    ts = R.sched["call_cadence_steps"]
    out = {}
    for lab in ("positive", "negative"):
        cs = [c for c in clips if R.ctx["meta"][c]["label"] == lab]
        inst = sum(len(range(0, R.ctx["meta"][c]["G"], ts)) for c in cs)
        out[lab] = dict(n_clips=len(cs), n_calls=n_calls(epi, bg, cs),
                        call_fraction=(n_calls(epi, bg, cs) / inst if inst else None))
    a, b = out["positive"]["call_fraction"], out["negative"]["call_fraction"]
    out["positive_over_negative_rate_ratio"] = (a / b if (a is not None and b) else None)
    return out


def arm_stream(R, clips: Sequence[str], epi, bg=None) -> Dict[str, np.ndarray]:
    """One sample-and-hold over the union of device deliveries, episode-call deliveries and
    background-sample deliveries (ctrl1_controller A4). A background sample is a cloud call and
    its answer is displayed exactly like any other."""
    out = {}
    for c in clips:
        cap, read, val = R.S[c]
        G = R.ctx["meta"][c]["G"]
        eps = list(epi.get(c, []))
        if bg:
            eps = eps + [dict(calls=[i]) for i in bg.get(c, [])]
        out[c] = C.mixed_stream(cap, read, val, R.ctx["arrs"][C.CLOUD][c], eps, G,
                                R.sched["cloud_shift_steps"])
    return out


def solve_down(fn, target: float, lo: float, hi: float, iters: int = 24) -> Tuple[float, float]:
    """Bisection on a monotone-DECREASING fraction (higher threshold, fewer calls)."""
    f_lo, f_hi = fn(lo), fn(hi)
    if f_lo < target:
        return lo, f_lo
    if f_hi > target:
        return hi, f_hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f = fn(mid)
        if f > target:
            lo, f_lo = mid, f
        else:
            hi, f_hi = mid, f
        if hi - lo < 1e-6:
            break
    return (hi, f_hi) if abs(f_hi - target) < abs(f_lo - target) else (lo, f_lo)


# ---------------------------------------------------------------- the oracle trigger (B2)
def oracle_calls(R, chA, clip: str, lead: int) -> List[int]:
    """Call capture instants that land a cloud delivery ON each challenge crop instant of a
    positive clip, plus `lead` earlier calls at the same cadence. Negative clips get nothing."""
    if R.ctx["meta"][clip]["label"] != "positive":
        return []
    ts = R.sched["call_cadence_steps"]
    dc = R.sched["cloud_shift_steps"]
    G = R.ctx["meta"][clip]["G"]
    need = []
    for h in chA.incl[clip]:
        i = chA.pos_idx[(clip, h)]
        cap = i - dc
        if cap < 0:
            continue
        need.append(int((cap // ts) * ts))
    if not need:
        return []
    first = min(need)
    ext = [first - k * ts for k in range(1, lead + 1) if first - k * ts >= 0]
    return sorted({j for j in need + ext if 0 <= j < G})


def oracle_calls_all(R, chA, clip: str, lead: int) -> List[int]:
    """The SECOND reading of the brief's oracle (B2b): serve the crop instant of EVERY clip,
    positive and negative alike, since the metric's crop geometry is what an oracle knows. This
    is the arm that is actually an upper bound on timing; the positives-only reading above is not,
    for the reason recorded in B2b."""
    import study_e9d_delay as D
    ts = R.sched["call_cadence_steps"]
    dc = R.sched["cloud_shift_steps"]
    G = R.ctx["meta"][clip]["G"]
    if R.ctx["meta"][clip]["label"] == "positive":
        idx = [chA.pos_idx[(clip, h)] for h in chA.incl[clip]]
    else:
        idx = [chA.neg_idx[(clip, h)] for h in D.CHAL_H]
    need = [int(((i - dc) // ts) * ts) for i in idx if i - dc >= 0]
    if not need:
        return []
    first = min(need)
    ext = [first - k * ts for k in range(1, lead + 1) if first - k * ts >= 0]
    return sorted({j for j in need + ext if 0 <= j < G})


def _eps_from_calls(R, clips, callfn) -> Dict[str, List[Dict[str, Any]]]:
    dc = R.sched["cloud_shift_steps"]
    out = {}
    for c in clips:
        calls = callfn(c)
        if not calls:
            out[c] = []
            continue
        G = R.ctx["meta"][c]["G"]
        out[c] = [dict(open_i=calls[0], calls=calls, close_i=int(min(G - 1, calls[-1] + dc)))]
    return out


def oracle_episodes(R, chA, clips: Sequence[str], lead: int
                    ) -> Dict[str, List[Dict[str, Any]]]:
    return _eps_from_calls(R, clips, lambda c: oracle_calls(R, chA, c, lead))


def oracle_episodes_all(R, chA, clips: Sequence[str], lead: int
                        ) -> Dict[str, List[Dict[str, Any]]]:
    return _eps_from_calls(R, clips, lambda c: oracle_calls_all(R, chA, c, lead))


# ---------------------------------------------------------------- the cloud-initiated trigger
def cloud_initiated(R, clips: Sequence[str], cstep, tau: float, k_c: int, e_k: int = E_K
                    ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[int]]]:
    """Background 32B sampling every `cstep` grid steps; an episode at the 0.5-s cadence opens
    when a background sample's own score passes tau, read dc steps after its capture (B5). The
    episode closes on K_c consecutive below-tau call scores whose read time has passed, or after
    e_k calls (B3). Background sampling pauses while an episode is open (B4)."""
    ts = R.sched["call_cadence_steps"]
    dc = R.sched["cloud_shift_steps"]
    epi: Dict[str, List[Dict[str, Any]]] = {}
    bg: Dict[str, List[int]] = {}
    for c in clips:
        G = R.ctx["meta"][c]["G"]
        arr = R.ctx["arrs"][C.CLOUD][c]
        cs = int(cstep[c]) if isinstance(cstep, dict) else int(cstep)
        eps: List[Dict[str, Any]] = []
        samples: List[int] = []
        open_ep = None
        pending: Optional[int] = None
        below = 0
        ptr = 0
        for i in range(0, G, ts):
            if open_ep is None:
                if pending is not None and i >= pending:
                    open_ep = dict(open_i=int(i), calls=[int(i)])
                    pending, below, ptr = None, 0, 0
                else:
                    if i % cs == 0:
                        samples.append(int(i))
                        if pending is None and float(arr[i]) > tau:
                            pending = int(math.ceil((i + dc) / ts) * ts)
                    continue
            if open_ep is not None:
                last = open_ep["calls"][-1]
                if i - last >= ts and len(open_ep["calls"]) < e_k:
                    open_ep["calls"].append(int(i))
                while ptr < len(open_ep["calls"]) and open_ep["calls"][ptr] + dc <= i:
                    s = float(arr[open_ep["calls"][ptr]])
                    below = below + 1 if s <= tau else 0
                    ptr += 1
                if len(open_ep["calls"]) >= e_k or below >= k_c:
                    open_ep["close_i"] = int(min(G - 1, open_ep["calls"][-1] + dc))
                    eps.append(open_ep)
                    open_ep = None
                    below, ptr = 0, 0
        if open_ep is not None:
            open_ep["close_i"] = int(min(G - 1, open_ep["calls"][-1] + dc))
            eps.append(open_ep)
        epi[c] = eps
        bg[c] = samples
    return epi, bg


def bg_floor(R, cstep: int) -> float:
    """The budget a background cadence costs before any episode: one call every cstep steps
    against one decision instant every ts steps."""
    return R.sched["call_cadence_steps"] / cstep


# ---------------------------------------------------------------- per-fold training fits
def fit_fold(R, chA, train: Sequence[str], fold: int) -> Dict[str, Any]:
    """Every tunable, chosen on the 4 training folds only. The objective is the pre-registered
    one: maximize training challenge mAP of escalation-only at a fixed budget, where the budget is
    the call fraction (B1)."""
    ch_tr = C.challenge_for(sub_for(R.ctx, train))
    rows: List[Dict[str, Any]] = []
    for w_c in C.GRID_W_C:
        for delta in C.GRID_DELTA:
            for n_c in C.GRID_N_C:
                for mode in C.GRID_MODE:
                    key = (w_c, delta, n_c, mode)
                    for k_c in C.GRID_K_C:
                        def frac(th, key=key, k_c=k_c):
                            return call_fraction(R, R.episodes_all(train, key, th, k_c), None,
                                                 train)
                        for B in BUDGETS:
                            th, f = solve_down(frac, B, -2.0, 12.0, iters=22)
                            epi = R.episodes_all(train, key, th, k_c)
                            m = float(ch_tr.point(arm_stream(R, train, epi))["mAP"])
                            rows.append(dict(w_c=w_c, delta=delta, n_c=n_c, mode=mode, k_c=k_c,
                                             budget=B, theta=th, train_call_fraction=f,
                                             train_mAP=m, hit_budget=bool(abs(f - B) <= TOL)))
    best = {}
    for B in BUDGETS:
        cand = [r for r in rows if r["budget"] == B and r["hit_budget"]]
        if not cand:
            cand = [r for r in rows if r["budget"] == B]
            cand.sort(key=lambda r: abs(r["train_call_fraction"] - B))
            keep = abs(cand[0]["train_call_fraction"] - B) + 1e-9
            cand = [r for r in cand if abs(r["train_call_fraction"] - B) <= keep]
        cand.sort(key=lambda r: -r["train_mAP"])
        best[str(B)] = cand[0]

    absolute, random_cfg, oracle, cloud = {}, {}, {}, {}
    for B in BUDGETS:
        cb = best[str(B)]
        k_c = cb["k_c"]

        def fa(t, k_c=k_c):
            return call_fraction(R, R.abs_episodes_all(train, t, k_c), None, train)
        tau, fv = solve_down(fa, B, -30.0, 0.5, iters=34)
        absolute[str(B)] = dict(tau=tau, train_call_fraction=fv, k_c=k_c,
                                hit_budget=bool(abs(fv - B) <= TOL))

        epi_b = R.episodes_all(train, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]),
                               cb["theta"], k_c)
        calls = [len(e["calls"]) for c in train for e in epi_b[c]]
        n_call = max(1, int(round(float(np.median(calls)))) if calls else 1)
        lo, hi = 0.0, 1.0
        for _ in range(28):
            mid = 0.5 * (lo + hi)
            if call_fraction(R, R.random_episodes_all(train, mid, n_call), None, train) < B:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        p = 0.5 * (lo + hi)
        random_cfg[str(B)] = dict(
            p_open=p, calls_per_episode=n_call, seed=SEED,
            train_call_fraction=call_fraction(R, R.random_episodes_all(train, p, n_call), None,
                                              train))

        def fit_lead(fn):
            cands = []
            for L in range(0, 400):
                ep = fn(R, chA, train, L)
                f = call_fraction(R, ep, None, train)
                cands.append((abs(f - B), L, f))
                if f > B + 0.5:
                    break
            cands.sort()
            _, L, f = cands[0]
            return dict(lead_calls=L, lead_s=L * R.sched["call_cadence_steps"] * STEP,
                        train_call_fraction=f, hit_budget=bool(abs(f - B) <= TOL),
                        non_causal=True)
        oracle[str(B)] = fit_lead(oracle_episodes)
        oracle[str(B)]["timing_bound"] = fit_lead(oracle_episodes_all)

        feas = []
        for cs in BG_CADENCES_S:
            cstep = int(round(cs / STEP))
            floor = bg_floor(R, cstep)
            if floor > B + TOL:
                feas.append(dict(cadence_s=cs, background_floor=floor, feasible=False,
                                 reason="background sampling alone exceeds the budget"))
                continue

            def fc(t, cstep=cstep, k_c=k_c):
                e, b = cloud_initiated(R, train, cstep, t, k_c)
                return call_fraction(R, e, b, train)
            t_, f_ = solve_down(fc, B, -30.0, 0.5, iters=30)
            e, b = cloud_initiated(R, train, cstep, t_, k_c)
            m = float(ch_tr.point(arm_stream(R, train, e, b))["mAP"])
            feas.append(dict(cadence_s=cs, background_floor=floor, feasible=True, tau=t_,
                             train_call_fraction=f_, train_mAP=m, k_c=k_c,
                             hit_budget=bool(abs(f_ - B) <= TOL),
                             n_episodes=sum(len(v) for v in e.values()),
                             n_background=sum(len(v) for v in b.values())))
        ok = [x for x in feas if x["feasible"]]
        ok.sort(key=lambda x: -x["train_mAP"])
        cloud[str(B)] = dict(
            candidates=feas, chosen=(ok[0] if ok else None),
            infeasible_reason=(None if ok else
                               "no background cadence in {1, 2, 4} s fits this budget: the "
                               "cheapest, 4 s, already costs %.4f of the decision instants"
                               % bg_floor(R, int(round(max(BG_CADENCES_S) / STEP)))))
    return dict(fold=fold, n_train=len(train), controller=best, absolute=absolute,
                random=random_cfg, oracle=oracle, cloud_initiated=cloud,
                train_references=dict(
                    device_only=float(ch_tr.point(R.device_only(train))["mAP"]),
                    always_cloud=float(ch_tr.point(R.always_cloud(train))["mAP"])))


# ---------------------------------------------------------------- held-out arm construction
def held_arms(R, chA, fit: Dict[str, Any], held: Sequence[str], B: float) -> Dict[str, Any]:
    """The arms on one held-out fold, under settings fitted without it."""
    cb = fit["controller"][str(B)]
    key = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
    k_c = cb["k_c"]
    epi = R.episodes_all(held, key, cb["theta"], k_c)
    epi_abs = R.abs_episodes_all(held, fit["absolute"][str(B)]["tau"], k_c)
    rc = fit["random"][str(B)]
    epi_rnd = R.random_episodes_all(held, rc["p_open"], rc["calls_per_episode"])
    epi_or = oracle_episodes(R, chA, held, fit["oracle"][str(B)]["lead_calls"])
    epi_ob = oracle_episodes_all(R, chA, held,
                                 fit["oracle"][str(B)]["timing_bound"]["lead_calls"])
    ch = fit["cloud_initiated"][str(B)]["chosen"]
    if ch is None:
        epi_cl, bg_cl = {c: [] for c in held}, {c: [] for c in held}
    else:
        epi_cl, bg_cl = cloud_initiated(R, held, int(round(ch["cadence_s"] / STEP)), ch["tau"],
                                        ch["k_c"])
    fl = fit.get("learned")
    if fl is None:
        epi_g = epi_l = {c: [] for c in held}
        epi_ct, bg_ct = {c: [] for c in held}, {c: [] for c in held}
    else:
        sig = learned_held(R, fl, held, B)
        thr = fl["thresholds"][str(B)]
        epi_g = episodes_from_signal(R, held, sig["gbt"], thr["ceiling-gbt"]["theta"],
                                     thr["ceiling-gbt"]["k_c"])
        epi_l = episodes_from_signal(R, held, sig["logistic"],
                                     thr["ceiling-logistic"]["theta"],
                                     thr["ceiling-logistic"]["k_c"])
        ct = fit.get("context_trickle", {}).get(str(B), {}).get("chosen")
        if ct is None:
            epi_ct, bg_ct = {c: [] for c in held}, {c: [] for c in held}
        else:
            per = context_cstep(R, held, fl, int(round(ct["cadence_s"] / STEP)))
            epi_ct, bg_ct = cloud_initiated(R, held, per, ct["tau"], ct["k_c"])
    return dict(
        episodes={"escalation-only": epi, "absolute-confidence": epi_abs,
                  "random-escalation": epi_rnd, "oracle-trigger": epi_or,
                  "oracle-timing-bound": epi_ob, "cloud-initiated": epi_cl,
                  "context-trickle": epi_ct, "ceiling-gbt": epi_g,
                  "ceiling-logistic": epi_l},
        background={"cloud-initiated": bg_cl, "context-trickle": bg_ct},
        cloud_feasible=(ch is not None),
        streams={
            "device-only": R.device_only(held),
            "always-cloud": R.always_cloud(held),
            "escalation-only": arm_stream(R, held, epi),
            "oracle-trigger": arm_stream(R, held, epi_or),
            "oracle-timing-bound": arm_stream(R, held, epi_ob),
            "cloud-initiated": arm_stream(R, held, epi_cl, bg_cl),
            "context-trickle": arm_stream(R, held, epi_ct, bg_ct),
            "ceiling-gbt": arm_stream(R, held, epi_g),
            "ceiling-logistic": arm_stream(R, held, epi_l),
            "absolute-confidence": arm_stream(R, held, epi_abs),
            "random-escalation": arm_stream(R, held, epi_rnd)})


def budget_report(R, arms: Dict[str, Any], clips: Sequence[str]) -> Dict[str, Any]:
    out = {}
    for a, epi in arms["episodes"].items():
        bg = arms["background"].get(a)
        out[a] = dict(call_fraction=call_fraction(R, epi, bg, clips),
                      open_time_fraction=open_fraction(R, epi, clips),
                      n_calls=n_calls(epi, bg, clips),
                      n_background=(sum(len(v) for v in bg.values()) if bg else 0),
                      n_episodes=sum(len(v) for v in epi.values()))
    out["always-cloud"] = dict(call_fraction=1.0, open_time_fraction=1.0,
                               n_calls=n_instants(R, clips), n_background=0, n_episodes=0)
    out["device-only"] = dict(call_fraction=0.0, open_time_fraction=0.0, n_calls=0,
                              n_background=0, n_episodes=0)
    return out


# ---------------------------------------------------------------- mechanism verification
def mechanism_new_arms(R, chA, fit: Dict[str, Any], train: Sequence[str]) -> Dict[str, Any]:
    """CLAUDE.md mechanism verification Steps 1-5 for the TWO NEW ARMS, on TRAINING folds only and
    BEFORE any pooled held-out number is written. The unit is one episode on one clip."""
    ch_tr = C.challenge_for(sub_for(R.ctx, train))
    sub = sub_for(R.ctx, train)
    pos, neg = sub["pos"], sub["neg"]
    ts = R.sched["call_cadence_steps"]
    dc = R.sched["cloud_shift_steps"]
    m_dev = float(ch_tr.point(R.device_only(train))["mAP"])
    m_cloud = float(ch_tr.point(R.always_cloud(train))["mAP"])

    chain_oracle = (
        "If a cloud answer delivered AT a challenge crop instant carries a better-separating "
        "score than the device's own held sample at that instant (StudyE9c measured the pooled "
        "separation: 32B 0.5675 against 4B 0.4776 over all 300 clips), then placing calls so "
        "that each positive clip's crop instants are served by a cloud delivery, and spending "
        "nothing on negatives, must capture at least as much of the always-cloud minus "
        "device-only gap as any causal trigger at the same budget. The oracle therefore bounds "
        "TIMING: whatever remains uncaptured at a given budget cannot be recovered by a better "
        "trigger, only by a better cloud answer or by more budget.")
    chain_cloud = (
        "If the cloud's own 32B score at a background cadence c carries the approach of an event "
        "(the same signal StudyD14b measured on the 4B, on a stronger model), then background "
        "sampling at cadence c detects it, an episode opened at the 0.5-s cadence covers the crop "
        "instants that follow, and the delivered 32B scores replace the device's at those "
        "instants, raising challenge mAP. The cost is paid twice over, in background samples and "
        "in episode calls, so the arm is only worth it if the detection is sharp enough that the "
        "episodes land where they matter.")
    links: List[Dict[str, Any]] = []

    # --- oracle L1: the calls do land a delivery on the crop instants
    served = tot = 0
    for c in pos:
        calls = set(oracle_calls(R, chA, c, 0))
        for h in chA.incl[c]:
            i = chA.pos_idx[(c, h)]
            tot += 1
            if (i - dc) // ts * ts in calls and i - dc >= 0:
                served += 1
    cb = fit["controller"][str(BUDGETS[1])]
    epi_esc = R.episodes_all(train, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]), cb["theta"],
                             cb["k_c"])
    esc_served = 0
    for c in pos:
        mask = C.open_mask(epi_esc[c], R.ctx["meta"][c]["G"])
        for h in chA.incl[c]:
            if mask[chA.pos_idx[(c, h)]]:
                esc_served += 1
    links.append(dict(
        arm="oracle-trigger", link="oracle placement -> a cloud delivery at the crop instant",
        quantity="fraction of scored positive-clip crop instants served by a cloud delivery",
        value=dict(oracle=served / tot if tot else None, n_crop_instants=tot,
                   escalation_only_at_10pct=esc_served / tot if tot else None),
        varies=bool(tot and served / tot > (esc_served / tot) + 1e-9),
        evidence="the oracle serves every crop instant it is defined on, the fitted controller a "
                 "minority of them, so the quantity separates the arms"))

    # --- oracle L2: the lead extension is the budget knob
    curve = []
    for L in (0, 2, 8, 32, 128):
        ep = oracle_episodes(R, chA, train, L)
        curve.append(dict(lead_calls=L, call_fraction=call_fraction(R, ep, None, train),
                          open_time_fraction=open_fraction(R, ep, train),
                          train_mAP=float(ch_tr.point(arm_stream(R, train, ep))["mAP"])))
    spread = max(x["train_mAP"] for x in curve) - min(x["train_mAP"] for x in curve)
    links.append(dict(
        arm="oracle-trigger", link="lead extension -> budget -> metric",
        quantity="call fraction and training mAP as the lead grows", value=curve,
        varies=bool(curve[-1]["call_fraction"] > curve[0]["call_fraction"] + 1e-9),
        metric_varies=bool(spread > 1e-9), metric_spread=float(spread),
        status=("CONSTANT in the metric" if spread <= 1e-9 else "varies"),
        evidence=("the call fraction rises monotonically with the lead, but the metric is "
                  "EXACTLY CONSTANT across it (spread %.2e): the crop instant is served by the "
                  "same call whatever the lead and the challenge metric reads no other instant. "
                  "Per CLAUDE.md a CONSTANT link cannot carry a claim, so the oracle is reported "
                  "as ONE number rather than as a budget curve, and the budget matching the "
                  "brief asks for is recorded as cosmetic (B2c)." % spread)))

    # --- oracle L3: THE quantity the whole bound depends on
    d_pos, d_neg = [], []
    for c in pos:
        for h in chA.incl[c]:
            i = chA.pos_idx[(c, h)]
            if i - dc < 0:
                continue
            cap = (i - dc) // ts * ts
            d_pos.append(float(R.ctx["arrs"][C.CLOUD][c][cap]) - float(R.dev[c][i]))
    import study_e9d_delay as D
    dropped = 0
    for c in neg:
        for h in D.CHAL_H:
            i = chA.neg_idx[(c, h)]
            cap = max(0, (i - dc) // ts * ts)
            v = float(R.ctx["arrs"][C.CLOUD][c][cap]) - float(R.dev[c][i])
            if abs(v) > 1e6:
                dropped += 1          # the device stream holds its -1e9 sentinel before its
                continue              # first delivery; those crops carry no comparison
            d_neg.append(v)
    links.append(dict(
        arm="oracle-trigger", link="cloud answer -> a better score AT the crop instant",
        quantity="cloud score at the serving call minus the device's displayed score, at the "
                 "crop instants of training positives",
        value=dict(n=len(d_pos), mean=float(np.mean(d_pos)) if d_pos else None,
                   p50=float(np.median(d_pos)) if d_pos else None,
                   fraction_positive=float(np.mean(np.asarray(d_pos) > 0)) if d_pos else None,
                   n_negative_crops=len(d_neg),
                   mean_on_negatives=float(np.mean(d_neg)) if d_neg else None,
                   p50_on_negatives=float(np.median(d_neg)) if d_neg else None,
                   n_crops_dropped_sentinel=dropped),
        varies=bool(d_pos and abs(float(np.mean(d_pos))) > 1e-9),
        evidence="the cloud's score at the instant the oracle serves differs from the device's, "
                 "so perfect timing has something to deliver; its SIGN is what decides whether "
                 "the bound is above or below device-only"))

    # --- the calibration link both new arms depend on
    allc_t = list(train)
    cl = np.concatenate([R.ctx["arrs"][C.CLOUD][c] for c in allc_t])
    de = np.concatenate([R.ctx["arrs"][C.DEVICE][c] for c in allc_t])
    links.append(dict(
        arm="both new arms", link="tier score scale -> rank metric",
        quantity="raw log P(Yes) percentiles of the two tiers over the training clips",
        value=dict(cloud_p05=float(np.percentile(cl, 5)), cloud_p50=float(np.percentile(cl, 50)),
                   cloud_p95=float(np.percentile(cl, 95)), device_p05=float(np.percentile(de, 5)),
                   device_p50=float(np.percentile(de, 50)),
                   device_p95=float(np.percentile(de, 95)),
                   median_offset_cloud_minus_device=float(np.percentile(cl, 50)
                                                          - np.percentile(de, 50))),
        varies=True,
        evidence=("the two tiers are NOT on a common scale, so any arm whose calls are "
                  "label-correlated moves the rank metric through the scale offset alone. This "
                  "link is the reason the oracle has two readings (B2b) and it bears directly on "
                  "spec 4.1: u_SH must be a calibrated utility, not a raw tier score.")))

    # --- cloud-initiated L1: background samples trigger at all
    cl = fit["cloud_initiated"]
    chosen_cl = {str(B): cl[str(B)]["chosen"] for B in BUDGETS}
    feasible_budgets = [B for B in BUDGETS if chosen_cl[str(B)] is not None]
    tcurve = []
    if feasible_budgets:
        cstep = int(round(chosen_cl[str(feasible_budgets[0])]["cadence_s"] / STEP))
        k_c = chosen_cl[str(feasible_budgets[0])]["k_c"]
        for tau in (-8.0, -4.0, -2.0, -1.0, -0.5):
            e, b = cloud_initiated(R, train, cstep, tau, k_c)
            tcurve.append(dict(tau=tau, n_episodes=sum(len(v) for v in e.values()),
                               n_background=sum(len(v) for v in b.values()),
                               call_fraction=call_fraction(R, e, b, train)))
    links.append(dict(
        arm="cloud-initiated", link="background cloud score -> episode trigger",
        quantity="episodes and total calls as tau moves, at the chosen cadence",
        value=tcurve, varies=bool(len(tcurve) > 1 and
                                  tcurve[0]["n_episodes"] != tcurve[-1]["n_episodes"]),
        evidence=("the trigger count falls as tau rises, so the threshold is a live knob"
                  if tcurve else "NO FEASIBLE CADENCE AT ANY BUDGET: see the infeasibility note")))

    # --- cloud-initiated L2: an episode is open at the crop instants, and the metric moves
    byb = {}
    for B in BUDGETS:
        ch_b = chosen_cl[str(B)]
        if ch_b is None:
            byb[str(B)] = None
            continue
        e, b = cloud_initiated(R, train, int(round(ch_b["cadence_s"] / STEP)), ch_b["tau"],
                               ch_b["k_c"])
        hit = tot2 = 0
        for c in pos:
            mask = C.open_mask(e[c], R.ctx["meta"][c]["G"])
            for h in chA.incl[c]:
                tot2 += 1
                if mask[chA.pos_idx[(c, h)]]:
                    hit += 1
        byb[str(B)] = dict(fraction_crops_in_open_episode=(hit / tot2 if tot2 else None),
                           train_mAP=float(ch_tr.point(arm_stream(R, train, e, b))["mAP"]),
                           device_only=m_dev, always_cloud=m_cloud)
    links.append(dict(
        arm="cloud-initiated", link="episode -> displayed score -> challenge mAP",
        quantity="fraction of positive crop instants inside an open episode, and training mAP, "
                 "by budget", value=byb,
        varies=bool(len({json.dumps(v, sort_keys=True, default=float)
                         for v in byb.values()}) > 1),
        evidence="both move with the budget where the arm is feasible"))

    # --- Step 3: one traced episode of each new arm
    trace = {}
    for c in pos:
        calls = oracle_calls(R, chA, c, fit["oracle"][str(BUDGETS[1])]["lead_calls"])
        if not calls:
            continue
        st = arm_stream(R, [c], oracle_episodes(R, chA, [c],
                                                fit["oracle"][str(BUDGETS[1])]["lead_calls"]))[c]
        trace["oracle-trigger"] = dict(
            clip=c, label="positive", event_s=R.ctx["meta"][c]["event"],
            budget=BUDGETS[1], lead_calls=fit["oracle"][str(BUDGETS[1])]["lead_calls"],
            crops=[dict(horizon_s=h, crop_index=int(chA.pos_idx[(c, h)]),
                        crop_time_s=T0 + chA.pos_idx[(c, h)] * STEP,
                        serving_call_capture_index=int((chA.pos_idx[(c, h)] - dc) // ts * ts),
                        device_displayed=float(R.dev[c][chA.pos_idx[(c, h)]]),
                        oracle_displayed=float(st[chA.pos_idx[(c, h)]]),
                        cloud_at_serving_capture=float(
                            R.ctx["arrs"][C.CLOUD][c][(chA.pos_idx[(c, h)] - dc) // ts * ts]))
                   for h in chA.incl[c] if chA.pos_idx[(c, h)] - dc >= 0],
            n_calls=len(calls), call_times_s=[round(T0 + i * STEP, 3) for i in calls[:12]],
            arithmetic=("each crop instant i is served by the call captured at the largest "
                        "decision instant at or below i - %d grid steps, so its answer is "
                        "readable exactly at or just before i; the lead calls precede the first "
                        "needed call at the 0.5-s cadence" % dc))
        break
    if feasible_budgets:
        B = feasible_budgets[0]
        ch_b = chosen_cl[str(B)]
        cstep = int(round(ch_b["cadence_s"] / STEP))
        for c in pos:
            e, b = cloud_initiated(R, [c], cstep, ch_b["tau"], ch_b["k_c"])
            if not e[c]:
                continue
            x = e[c][0]
            arr = R.ctx["arrs"][C.CLOUD][c]
            fired = [i for i in b[c] if float(arr[i]) > ch_b["tau"] and i + dc <= x["open_i"]]
            st = arm_stream(R, [c], e, b)[c]
            trace["cloud-initiated"] = dict(
                clip=c, label="positive", event_s=R.ctx["meta"][c]["event"], budget=B,
                background_cadence_s=ch_b["cadence_s"], tau=ch_b["tau"], k_c=ch_b["k_c"],
                triggering_sample=dict(
                    capture_index=(fired[-1] if fired else None),
                    capture_time_s=(T0 + fired[-1] * STEP if fired else None),
                    score=(float(arr[fired[-1]]) if fired else None),
                    readable_time_s=(T0 + (fired[-1] + dc) * STEP if fired else None)),
                episode=dict(open_index=x["open_i"], open_time_s=T0 + x["open_i"] * STEP,
                             call_times_s=[round(T0 + i * STEP, 3) for i in x["calls"]],
                             call_scores=[float(arr[i]) for i in x["calls"]],
                             close_index=x["close_i"], close_time_s=T0 + x["close_i"] * STEP,
                             n_calls=len(x["calls"])),
                n_background_samples=len(b[c]),
                displayed_at_crops=[dict(horizon_s=h, crop_index=int(chA.pos_idx[(c, h)]),
                                         device_only=float(R.dev[c][chA.pos_idx[(c, h)]]),
                                         cloud_initiated=float(st[chA.pos_idx[(c, h)]]))
                                    for h in chA.incl[c]],
                arithmetic=("the background sample captured at the listed instant is readable "
                            "%d grid steps later; the episode opens at the first decision "
                            "instant at or after that read time and calls every %d steps; it "
                            "closes after %d consecutive read-back call scores at or below tau"
                            % (dc, ts, ch_b["k_c"])))
            break

    # --- Step 4: negative controls for the new arms
    controls = {}
    saved = R.ctx["arrs"][C.CLOUD]
    rows = []
    for B in BUDGETS:
        ep = oracle_episodes(R, chA, train, fit["oracle"][str(B)]["lead_calls"])
        live = float(ch_tr.point(arm_stream(R, train, ep))["mAP"])
        try:
            R.ctx["arrs"][C.CLOUD] = R.ctx["arrs"][C.DEVICE]
            same = float(ch_tr.point(arm_stream(R, train, ep))["mAP"])
        finally:
            R.ctx["arrs"][C.CLOUD] = saved
        rows.append(dict(budget=B, oracle=live, control_device_scores_through_cloud_path=same,
                         device_only=m_dev, total_gain=live - m_dev,
                         gain_from_path_freshness=same - m_dev,
                         gain_from_cloud_score_quality=live - same))
    rows_b = []
    for B in BUDGETS:
        ep_p = oracle_episodes(R, chA, train, fit["oracle"][str(B)]["lead_calls"])
        ep_a = oracle_episodes_all(R, chA, train,
                                   fit["oracle"][str(B)]["timing_bound"]["lead_calls"])
        rows_b.append(dict(
            budget=B,
            oracle_positives_only=float(ch_tr.point(arm_stream(R, train, ep_p))["mAP"]),
            oracle_every_crop=float(ch_tr.point(arm_stream(R, train, ep_a))["mAP"]),
            device_only=m_dev, always_cloud=m_cloud,
            label_correlation_positives_only=label_correlation(R, ep_p, None, train),
            label_correlation_every_crop=label_correlation(R, ep_a, None, train)))
    controls["oracle_label_correlation"] = dict(
        control=("the SAME perfect timing applied to every clip's crop instant instead of to the "
                 "positives only, which holds the timing fixed and removes the label "
                 "correlation of the spending"),
        per_budget=rows_b,
        reading=("if the positives-only oracle sits below device-only while the every-crop "
                 "oracle sits above it, the metric is responding to WHICH clips were escalated "
                 "and not to when; the two tiers' scores are on different scales, so a "
                 "label-correlated escalation pattern biases a rank metric by itself. That is "
                 "the mechanism this control isolates and it is the row's headline."))
    controls["oracle_no_cloud_advantage"] = dict(
        control=("the cloud score is replaced by the DEVICE's own score while the oracle's call "
                 "pattern is unchanged, so perfect timing buys the cloud PATH and nothing else"),
        per_budget=rows,
        reading=("if the oracle's gain survives this control, perfect timing is worth no more "
                 "than fresher delivery of the device's own score, which would mean the cloud's "
                 "answer quality, not the trigger, is the binding resource"))
    rows2 = []
    for B in BUDGETS:
        ch_b = chosen_cl[str(B)]
        if ch_b is None:
            rows2.append(dict(budget=B, feasible=False))
            continue
        cstep = int(round(ch_b["cadence_s"] / STEP))
        e, b = cloud_initiated(R, train, cstep, ch_b["tau"], ch_b["k_c"])
        live = float(ch_tr.point(arm_stream(R, train, e, b))["mAP"])
        e0, b0 = cloud_initiated(R, train, cstep, 1e9, ch_b["k_c"])
        bg_only = float(ch_tr.point(arm_stream(R, train, e0, b0))["mAP"])
        rows2.append(dict(budget=B, cloud_initiated=live, background_only_no_trigger=bg_only,
                          device_only=m_dev, gain_from_episodes=live - bg_only,
                          gain_from_background_alone=bg_only - m_dev,
                          background_only_call_fraction=call_fraction(R, e0, b0, train)))
    controls["cloud_initiated_trigger_disabled"] = dict(
        control=("tau is set to +infinity so no episode ever opens: the arm becomes background "
                 "sampling alone at the same cadence, which is the mechanism-off condition for "
                 "the TRIGGER while holding the sampling fixed"),
        per_budget=rows2,
        reading=("the difference between the two rows is everything the cloud-initiated TRIGGER "
                 "contributes; the background-only row is what the cadence alone buys and is "
                 "charged at a lower budget, which is stated with the number"))

    return dict(
        step1_causal_chain=dict(oracle_trigger=chain_oracle, cloud_initiated=chain_cloud),
        step2_links=links, step3_trace=trace, step4_controls=controls,
        step4_cell=dict(side="TRAINING folds of fold 0", clips=len(train),
                        budgets=list(BUDGETS), setting=C.SETTING),
        step5_alternative=(
            "For the ORACLE the competing explanation is the same one StudyCTRL1 could not rule "
            "out: that any cloud call at all helps because the cloud PATH is fresher than the "
            "device's 0.75-s held samples, not because the call is well placed. The control in "
            "Step 4 separates them directly by running the oracle's own call pattern with the "
            "device's own scores. For the CLOUD-INITIATED arm the competing explanation is that "
            "its benefit is entirely the background sampling, which upgrades the display every c "
            "seconds whether or not an episode ever opens; the trigger-disabled control "
            "separates those two. A third explanation covers both arms and cannot be separated "
            "within this study: the challenge metric reads ONE crop per clip, so an arm that "
            "happens to deliver a cloud score at that one instant is credited with the whole "
            "clip, and 300 clips carry 300 such instants. That is a property of the committed "
            "metric, not of the arms, and it is why the oracle is reported as a bound on timing "
            "rather than as an achievable policy."))


def mechanism_learned_arms(R, chA, fit: Dict[str, Any], train: Sequence[str]) -> Dict[str, Any]:
    """Steps 1-5 for arms (d) and (e), on TRAINING folds only and before any pooled number."""
    fl = fit["learned"]
    w = fl["window"]
    ch_tr = C.challenge_for(sub_for(R.ctx, train))
    sub = sub_for(R.ctx, train)
    m_dev = float(ch_tr.point(R.device_only(train))["mAP"])
    m_cloud = float(ch_tr.point(R.always_cloud(train))["mAP"])
    X, y, sp = learned_matrix(R, train, w["w_c"], w["delta"], w["n_c"])
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    g, l = rebuild_models(fl)
    pg, pl = g.predict(X), l.predict(X)
    links = []
    links.append(dict(
        arm="ceiling", link="device-observable features -> the per-instant cloud gain",
        quantity="training-fold fit of the signed gain target (B8)",
        value=dict(n_rows=int(ok.sum()), gbt_r2=LN.r2(y[ok], pg[ok]),
                   logistic_auc=LN.auc((y[ok] > 0).astype(float), pl[ok]),
                   target_mean=float(y[ok].mean()), target_sd=float(y[ok].std()),
                   fraction_positive_gain=float(np.mean(y[ok] > 0))),
        varies=bool(np.std(pg[ok]) > 1e-9),
        evidence="the prediction varies across instants and tracks the target to the stated r2; "
                 "a flat prediction would make the arm identical to random at the same budget"))
    curve = []
    sig = learned_signal(pg, sp, train)
    lo = float(np.nanmin(np.concatenate([sig[c] for c in train if len(sig[c])])))
    hi = float(np.nanmax(np.concatenate([sig[c] for c in train if len(sig[c])])))
    for frac_th in (0.1, 0.3, 0.5, 0.7, 0.9):
        th = lo + frac_th * (hi - lo)
        e = episodes_from_signal(R, train, sig, th, fl["thresholds"][str(BUDGETS[1])][
            "ceiling-gbt"]["k_c"])
        curve.append(dict(theta=th, call_fraction=call_fraction(R, e, None, train),
                          train_mAP=float(ch_tr.point(arm_stream(R, train, e))["mAP"])))
    links.append(dict(arm="ceiling", link="predicted gain -> episodes -> challenge mAP",
                      quantity="call fraction and training mAP as the learned threshold moves",
                      value=curve,
                      varies=bool(curve[0]["call_fraction"] > curve[-1]["call_fraction"] + 1e-9),
                      evidence="the threshold is a live budget knob and the metric moves with it"))
    ctx = fl["context"]
    per4 = context_cstep(R, train, fl, 16)
    links.append(dict(
        arm="context-trickle", link="context signal -> background cadence",
        quantity="clips whose cadence is halved by the chosen context feature",
        value=dict(feature=ctx["feature"], threshold=ctx["threshold"],
                   n_clips_modulated=int(sum(1 for c in train if per4[c] != 16)),
                   n_clips=len(train), gbt_importance=ctx["gbt_importance"],
                   all_context_importance_zero=ctx["all_context_importance_zero"]),
        varies=bool(0 < sum(1 for c in train if per4[c] != 16) < len(train)),
        evidence="the modulation fires on a proper subset of the clips, so the arm differs from "
                 "arm (b) at both cadences"))

    # Step 4: the decisive control for a LEARNED arm is a permuted target
    rng = np.random.default_rng(SEED)
    yp = y[ok].copy()
    rng.shuffle(yp)
    gp = LN.GBT().fit(X[ok], yp)
    Xa, _ya, spa = X, y, sp
    pgp = gp.predict(Xa)
    sigp = learned_signal(pgp, spa, train)
    rows = []
    for B in BUDGETS:
        k_c = fl["thresholds"][str(B)]["ceiling-gbt"]["k_c"]
        th_real = fl["thresholds"][str(B)]["ceiling-gbt"]["theta"]
        e_real = episodes_from_signal(R, train, sig, th_real, k_c)
        lo_p = float(np.nanmin(np.concatenate([sigp[c] for c in train if len(sigp[c])])))
        hi_p = float(np.nanmax(np.concatenate([sigp[c] for c in train if len(sigp[c])])))

        def frac(x, sigp=sigp, k_c=k_c):
            return call_fraction(R, episodes_from_signal(R, train, sigp, x, k_c), None, train)
        th_p, f_p = solve_down(frac, B, lo_p - 1e-6, hi_p + 1e-6, iters=26)
        e_perm = episodes_from_signal(R, train, sigp, th_p, k_c)
        rows.append(dict(
            budget=B,
            ceiling_real=float(ch_tr.point(arm_stream(R, train, e_real))["mAP"]),
            ceiling_permuted_target=float(ch_tr.point(arm_stream(R, train, e_perm))["mAP"]),
            permuted_call_fraction=f_p, device_only=m_dev, always_cloud=m_cloud,
            permuted_train_r2=LN.r2(yp, gp.predict(X[ok]))))
    return dict(
        step1_causal_chain=dict(
            ceiling=("If the per-instant cloud gain is predictable from features a device already "
                     "has, then a model fitted on the training folds predicts it on the held-out "
                     "fold, escalating at the instants of highest predicted gain captures more "
                     "of the always-cloud minus device-only gap than a rule that does not look "
                     "at those features, and the capture fraction it reaches is a CEILING on what "
                     "any trigger built from the same features could reach."),
            context_trickle=("If a cheap context signal marks streams whose cloud gain is higher, "
                             "then spending the same budget at a doubled background cadence on "
                             "those streams and the base cadence elsewhere captures more of the "
                             "gap than a uniform cadence does.")),
        step2_links=links,
        step3_trace=dict(
            ceiling_top_features_gbt=sorted(fl["importances"]["gbt"].items(),
                                            key=lambda kv: -kv[1])[:8],
            ceiling_top_features_logistic=sorted(fl["importances"]["logistic"].items(),
                                                 key=lambda kv: -kv[1])[:8],
            features_not_available=fl["features_not_available"],
            arithmetic=("the GBT importance is the share of total squared-error reduction per "
                        "feature over all stumps; the logistic importance is the absolute "
                        "standardized coefficient")),
        step4_controls=dict(permuted_target=dict(
            control=("the SAME model class and the SAME budget, fitted on a PERMUTED target "
                     "(seed 0), which destroys the feature-to-gain relation and nothing else"),
            per_budget=rows,
            reading=("if the real ceiling does not beat the permuted-target ceiling, the features "
                     "carry no usable signal and the arm is random escalation with extra steps"))),
        step4_cell=dict(side="TRAINING folds of fold 0", clips=len(train),
                        budgets=list(BUDGETS)),
        step5_alternative=(
            "The ceiling's apparent gain could come from (a) the features genuinely predicting "
            "where the cloud helps [the claimed mechanism], or (b) the arm simply spending its "
            "budget in a different TEXTURE, for instance in many short episodes rather than few "
            "long ones, which changes freshness without any targeting. The permuted-target "
            "control separates these: it keeps the model class, the episode machinery and the "
            "budget and removes only the signal. The random-escalation arm at the same budget is "
            "the second comparator. A third explanation cannot be separated here and is stated "
            "with the number: the ceiling is fitted on a target DEFINED using the clip label's "
            "sign (B8), so it is an upper bound available to an oracle-signed objective and not "
            "a deployable policy, which is why the brief labels it a ceiling."))


# ---------------------------------------------------------------- pooled held-out evaluation
def pool(R, chA, fits: Dict[str, Any], folds_info: Dict[str, Any]) -> Dict[str, Any]:
    """Every clip scored under settings fitted WITHOUT it, then the five held-out folds pooled
    into one 300-clip evaluation with paired clip-bootstrap CIs."""
    allc = list(R.ctx["clips"])
    sub_all = sub_for(R.ctx, allc)
    pos, neg = sub_all["pos"], sub_all["neg"]
    out: Dict[str, Any] = dict(by_budget={}, per_fold={}, negative_control={})
    held_by_fold = {f: folds_info["fold"][str(f)]["clips"] for f in range(N_FOLDS)}

    for B in BUDGETS:
        streams: Dict[str, Dict[str, np.ndarray]] = {a: {} for a in ARMS_ORDER}
        epi_pool: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        bg_pool: Dict[str, Dict[str, List[int]]] = {}
        feas = {}
        for f in range(N_FOLDS):
            held = held_by_fold[f]
            arms = held_arms(R, chA, fits[str(f)], held, B)
            feas[str(f)] = arms["cloud_feasible"]
            for a in ARMS_ORDER:
                streams[a].update(arms["streams"][a])
            for a, e in arms["episodes"].items():
                epi_pool.setdefault(a, {}).update(e)
            for a, b in arms["background"].items():
                bg_pool.setdefault(a, {}).update(b)
        boot, per = C.paired_multi(chA, streams, pos, neg)
        budgets_realized = {}
        for a in ARMS_ORDER:
            if a in ("device-only", "always-cloud"):
                budgets_realized[a] = dict(
                    call_fraction=(0.0 if a == "device-only" else 1.0),
                    open_time_fraction=(0.0 if a == "device-only" else 1.0))
                continue
            budgets_realized[a] = dict(
                call_fraction=call_fraction(R, epi_pool[a], bg_pool.get(a), allc),
                open_time_fraction=open_fraction(R, epi_pool[a], allc),
                label_correlation=label_correlation(R, epi_pool[a], bg_pool.get(a), allc),
                n_calls=n_calls(epi_pool[a], bg_pool.get(a), allc),
                n_background=(sum(len(v) for v in bg_pool[a].values())
                              if a in bg_pool else 0))
        stats = {a: C.episode_stats(R, epi_pool[a], allc, chA, pos, neg)
                 for a in epi_pool}
        gaps = {a: C.gap_fraction(per, boot["point"], a)
                for a in ARMS_ORDER if a not in ("device-only", "always-cloud")}
        diffs = {}
        for a in ARMS_ORDER:
            if a == "device-only":
                continue
            diffs["%s minus device-only" % a] = C._diff(per, boot["point"], a, "device-only")
        for a in ARMS_ORDER:
            if a in ("device-only", "random-escalation"):
                continue
            diffs["%s minus random-escalation" % a] = C._diff(per, boot["point"], a,
                                                              "random-escalation")
        for a in ("ceiling-gbt", "ceiling-logistic", "context-trickle", "cloud-initiated"):
            diffs["%s minus escalation-only" % a] = C._diff(per, boot["point"], a,
                                                            "escalation-only")
        diffs["oracle-timing-bound minus oracle-trigger"] = C._diff(
            per, boot["point"], "oracle-timing-bound", "oracle-trigger")
        diffs["oracle-trigger minus escalation-only"] = C._diff(per, boot["point"],
                                                                "oracle-trigger",
                                                                "escalation-only")
        capture_table = []
        for a in ARMS_ORDER:
            if a in ("device-only", "always-cloud"):
                continue
            g = gaps.get(a)
            capture_table.append(dict(
                arm=a, label=ARM_LABEL.get(a, a),
                capture_fraction=(g["value"] if g else None),
                ci=(g["ci"] if g else None),
                challenge_mAP=boot["point"][a],
                call_fraction=budgets_realized[a]["call_fraction"],
                open_time_fraction=budgets_realized[a]["open_time_fraction"],
                positive_over_negative_call_rate=budgets_realized[a]["label_correlation"][
                    "positive_over_negative_rate_ratio"],
                learned=bool(a.startswith("ceiling")),
                non_causal=bool(a.startswith("oracle"))))
        out["by_budget"][str(B)] = dict(
            capture_fraction_table=capture_table,
            target_budget=B, realized=budgets_realized,
            cloud_initiated_feasible_by_fold=feas,
            challenge_mAP=boot["point"], challenge_mAP_ci=boot["ci"],
            streaming_ap={a: {str(h): v for h, v in M.streaming_ap(sub_all, s).items()}
                          for a, s in streams.items()},
            gap_fraction_captured=gaps, paired_differences=diffs,
            episode_stats=stats,
            settings_by_fold={str(f): dict(
                controller=fits[str(f)]["controller"][str(B)],
                absolute=fits[str(f)]["absolute"][str(B)],
                random=fits[str(f)]["random"][str(B)],
                oracle=fits[str(f)]["oracle"][str(B)],
                cloud_initiated=fits[str(f)]["cloud_initiated"][str(B)]["chosen"],
                cloud_initiated_infeasible=fits[str(f)]["cloud_initiated"][str(B)][
                    "infeasible_reason"],
                learned_thresholds=fits[str(f)].get("learned", {}).get("thresholds", {})
                .get(str(B)),
                context_trickle=fits[str(f)].get("context_trickle", {}).get(str(B), {})
                .get("chosen"),
                context_feature=fits[str(f)].get("learned", {}).get("context"))
                for f in range(N_FOLDS)})

        # per fold, the same arms scored on that fold alone (point values only)
        for f in range(N_FOLDS):
            held = held_by_fold[f]
            ch_f = C.challenge_for(sub_for(R.ctx, held))
            row = {a: float(ch_f.point({c: streams[a][c] for c in held})["mAP"])
                   for a in ARMS_ORDER}
            out["per_fold"].setdefault(str(f), {})[str(B)] = row

        # the freshness-versus-score-quality control, recomputed on HELD-OUT clips
        saved = R.ctx["arrs"][C.CLOUD]
        ctrl_streams = {}
        try:
            R.ctx["arrs"][C.CLOUD] = R.ctx["arrs"][C.DEVICE]
            for f in range(N_FOLDS):
                held = held_by_fold[f]
                a2 = held_arms(R, chA, fits[str(f)], held, B)
                ctrl_streams.update(a2["streams"]["escalation-only"])
        finally:
            R.ctx["arrs"][C.CLOUD] = saved
        live = boot["point"]["escalation-only"]
        m_dev = boot["point"]["device-only"]
        same = float(chA.point(ctrl_streams)["mAP"])
        out["negative_control"][str(B)] = dict(
            escalation_only=live, control_device_scores_through_cloud_path=same,
            device_only=m_dev, total_gain=live - m_dev,
            gain_from_path_freshness=same - m_dev,
            gain_from_cloud_score_quality=live - same,
            share_from_cloud_score_quality=((live - same) / (live - m_dev)
                                            if abs(live - m_dev) > 1e-9 else None))
    out["references_pooled"] = dict(
        device_only=float(chA.point(R.device_only(allc))["mAP"]),
        always_cloud=float(chA.point(R.always_cloud(allc))["mAP"]),
        committed_studye9c=dict(always_cloud=0.5675307471627267,
                                device_only=0.47760424491770376))
    out["budget_metric"] = ("total cloud calls divided by total decision instants on the 0.5-s "
                            "cadence (B1); StudyCTRL1's open-episode-time fraction is reported "
                            "beside it as open_time_fraction")
    return out


# ---------------------------------------------------------------- StudyFRAMES1 re-run (B6)
def frames_crossfit(R, chA, folds_info: Dict[str, Any]) -> Dict[str, Any]:
    import frames1_utility as FU
    ctx = R.ctx
    allc = list(ctx["clips"])
    sub_all = sub_for(ctx, allc)
    held_by_fold = {f: folds_info["fold"][str(f)]["clips"] for f in range(N_FOLDS)}
    res: Dict[str, Any] = dict(
        label=("StudyFRAMES1 re-run on all 300 clips: the pooled matched-delay curve (no "
               "tunable, so pooling is the whole gain) and a genuine cross-fitted CHOOSE-N "
               "object (B6)."),
        cadence_s=FU.PRIMARY_CADENCE_S, total_delays_s=list(FU.TOTAL_DELAYS_S),
        arms={}, pooled_gain_vs_delay={}, per_fold_gain_vs_delay={}, choose_n={},
        own_latency={})
    for (m, n) in FU.ARMS:
        L, sh = FU.arm_latency(ctx, m, n)
        res["arms"]["%s_N%d" % (m, n)] = dict(measured_latency_s=L, hold_shift_steps=sh)

    for tier in ("32BI", "4BI"):
        for d in FU.TOTAL_DELAYS_S:
            sh = int(round(d / STEP))
            a = FU.delivered(ctx, tier, 3, FU.PRIMARY_CADENCE_S, sh, allc)
            b = FU.delivered(ctx, tier, 1, FU.PRIMARY_CADENCE_S, sh, allc)
            res["pooled_gain_vs_delay"]["%s|D%.2f" % (tier, d)] = dict(
                tier=tier, total_delay_s=d, n_clips=300,
                **FU.paired_gain(chA, a, b, sub_all["pos"], sub_all["neg"]))
            for f in range(N_FOLDS):
                held = held_by_fold[f]
                ch_f = C.challenge_for(sub_for(ctx, held))
                res["per_fold_gain_vs_delay"]["%s|D%.2f|f%d" % (tier, d, f)] = dict(
                    tier=tier, total_delay_s=d, fold=f,
                    mAP_N3=float(ch_f.point({c: a[c] for c in held})["mAP"]),
                    mAP_N1=float(ch_f.point({c: b[c] for c in held})["mAP"]))

        # CHOOSE-N: the choice is made on the 4 training folds and applied to the held-out fold
        for d in FU.TOTAL_DELAYS_S:
            sh = int(round(d / STEP))
            a = FU.delivered(ctx, tier, 3, FU.PRIMARY_CADENCE_S, sh, allc)
            b = FU.delivered(ctx, tier, 1, FU.PRIMARY_CADENCE_S, sh, allc)
            picked, chosen_stream = {}, {}
            for f in range(N_FOLDS):
                held = held_by_fold[f]
                train = [c for c in allc if c not in set(held)]
                ch_t = C.challenge_for(sub_for(ctx, train))
                g = (float(ch_t.point({c: a[c] for c in train})["mAP"])
                     - float(ch_t.point({c: b[c] for c in train})["mAP"]))
                pick = 3 if g > 0 else 1
                picked[str(f)] = dict(train_gain_N3_minus_N1=g, chosen_N=pick)
                src = a if pick == 3 else b
                chosen_stream.update({c: src[c] for c in held})
            res["choose_n"]["%s|D%.2f" % (tier, d)] = dict(
                tier=tier, total_delay_s=d, per_fold=picked,
                n_folds_choosing_N3=sum(1 for v in picked.values() if v["chosen_N"] == 3),
                **FU.paired_gain(chA, chosen_stream, b, sub_all["pos"], sub_all["neg"]))

    for tier in ("32BI", "4BI"):
        sh3 = res["arms"]["%s_N3" % tier]["hold_shift_steps"]
        sh1 = res["arms"]["%s_N1" % tier]["hold_shift_steps"]
        if sh3 is None:
            res["own_latency"][tier] = dict(
                available=False,
                reason=("no committed serving latency for %s N = 3 (StudyD7 / D7b measured the "
                        "4B at N = 1 only); nothing is estimated" % tier))
            continue
        a = FU.delivered(ctx, tier, 3, FU.PRIMARY_CADENCE_S, sh3, allc)
        b = FU.delivered(ctx, tier, 1, FU.PRIMARY_CADENCE_S, sh1, allc)
        res["own_latency"][tier] = dict(
            n3_hold_shift_s=sh3 * STEP, n1_hold_shift_s=sh1 * STEP, n_clips=300,
            **FU.paired_gain(chA, a, b, sub_all["pos"], sub_all["neg"]))
    res["superseded"] = ("StudyFRAMES1's 90/210 numbers are kept in "
                         "results/dashcam/frames1/frames1_results.json and in "
                         "reports/study_frames1.md and are superseded by the pooled 300-clip "
                         "values here, not deleted")
    return res


# ---------------------------------------------------------------- workload traces
def workload(R, chA, fits, folds_info) -> Dict[str, Any]:
    allc = list(R.ctx["clips"])
    ts = R.sched["call_cadence_steps"]
    dc = R.sched["cloud_shift_steps"]
    per_clip = {c: dict(label=R.ctx["meta"][c]["label"], event_s=R.ctx["meta"][c]["event"],
                        duration_s=R.ctx["meta"][c]["dur"], grid_points=R.ctx["meta"][c]["G"],
                        fold=None,
                        eligible_opportunities_s=[round(T0 + i * STEP, 3)
                                                  for i in range(0, R.ctx["meta"][c]["G"], ts)],
                        arms={}) for c in allc}
    for f in range(N_FOLDS):
        for c in folds_info["fold"][str(f)]["clips"]:
            per_clip[c]["fold"] = f
    for B in BUDGETS:
        for f in range(N_FOLDS):
            held = folds_info["fold"][str(f)]["clips"]
            arms = held_arms(R, chA, fits[str(f)], held, B)
            for a, epi in arms["episodes"].items():
                for c in held:
                    per_clip[c]["arms"].setdefault(a, {})[str(B)] = dict(
                        episodes=[dict(open_s=round(T0 + e["open_i"] * STEP, 3),
                                       close_s=round(T0 + e["close_i"] * STEP, 3),
                                       call_times_s=[round(T0 + i * STEP, 3)
                                                     for i in e["calls"]],
                                       delivery_times_s=[round(T0 + (i + dc) * STEP, 3)
                                                         for i in e["calls"]],
                                       n_calls=len(e["calls"])) for e in epi[c]],
                        background_sample_times_s=[
                            round(T0 + i * STEP, 3)
                            for i in arms["background"].get(a, {}).get(c, [])])
    return dict(
        note=("held-out escalation, episode call and background sample times for all 300 clips "
              "at each budget, under settings fitted on the other four folds. Times are seconds "
              "into the clip (the trace starts at t = 3.0 s). Cloud answers are readable "
              "%d grid steps after their call under StudyE9b setting (ii) with ZERO contention, "
              "which a live run replaces with its own measured TTFTs." % dc),
        call_cadence_s=C.T_K, max_calls_per_episode=E_K, setting=C.SETTING,
        cloud_shift_steps=dc, grid_step_s=STEP, t0_s=T0, budgets=list(BUDGETS),
        arms=list(ARMS_ORDER), clips=per_clip)


# ---------------------------------------------------------------- consistency, check 1
def consistency(R, chA) -> Dict[str, Any]:
    allc = list(R.ctx["clips"])
    cloud = float(chA.point(R.always_cloud(allc))["mAP"])
    dev = float(chA.point(R.device_only(allc))["mAP"])
    ref_c, ref_d = 0.5675307471627267, 0.47760424491770376
    import frames1_utility as FU
    lat = {("%s_N%d" % (m, n)): FU.arm_latency(R.ctx, m, n)[0] for (m, n) in FU.ARMS}
    return dict(
        check1_all300=dict(
            always_cloud=cloud, device_only=dev, committed_always_cloud=ref_c,
            committed_device_only=ref_d, diff_cloud=cloud - ref_c, diff_device=dev - ref_d,
            agree=bool(abs(cloud - ref_c) < 1e-12 and abs(dev - ref_d) < 1e-12),
            note=("the pooled design scores all 300 clips, so this is a DIRECT comparison with "
                  "StudyE9c's committed references rather than the subset recomputation "
                  "StudyCTRL1 had to make")),
        check2_rates=dict(
            arm_latencies_s=lat, uplink_mbit_s=13.6, rtt_s=0.044,
            device_cadence_s=R.sched["dev_cadence_steps"] * STEP,
            device_latency_s=R.sched["dev_latency_s"],
            cloud_latency_s=R.sched["cloud_latency_s"],
            call_cadence_s=C.T_K,
            note="nothing is timed in this row; every latency is a committed constant"),
        check4_definitions=dict(
            challenge_metric="study_e9d_delay.Challenge, horizons 0.5 / 1.0 / 1.5 s, one crop "
                             "per clip, unweighted mean of per-horizon AP",
            ap="study_e9d_delay.ap_fast (sklearn is absent in this environment and a raising "
               "stub is installed by metrics._ensure_sklearn_importable before the import)",
            delivery="study_e9b_dense held_stream / study_e9d_delay.cloud_delivered, setting "
                     "(ii) measured@25",
            budget="call fraction (B1), NOT StudyCTRL1's open-episode-time fraction; both are "
                   "reported for every arm",
            fold_rule=FD.folds()["rule"]))


# ---------------------------------------------------------------- CLI
def main() -> int:
    import argparse
    from _provenance import stamp
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=("fit", "fit2", "mechanism", "pool", "frames", "workload", "all"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ctx, sched = C.context()
    R = C.Runner(ctx, sched)
    chA = C.challenge_for(sub_for(ctx, list(ctx["clips"])))
    fi = FD.folds()
    print("folds: %s" % {f: fi["fold"][str(f)]["n"] for f in range(N_FOLDS)})
    print("schedule: device cadence %d steps shift %d; cloud shift %d steps; call cadence %d"
          % (sched["dev_cadence_steps"], sched["dev_shift_steps"], sched["cloud_shift_steps"],
             sched["call_cadence_steps"]))
    for cs in BG_CADENCES_S:
        print("  background cadence %.1f s costs %.4f of the decision instants"
              % (cs, bg_floor(R, int(round(cs / STEP)))))

    fits_file = OUT / "ctrl1b_fits.json"
    if a.stage in ("fit", "all"):
        t0 = time.time()
        fits = {}
        for f in range(N_FOLDS):
            te = FD.train_eval(f)
            tf = time.time()
            fits[str(f)] = fit_fold(R, chA, te["train"], f)
            print("fold %d fitted on %d clips in %.0f s" % (f, len(te["train"]),
                                                            time.time() - tf))
            for B in BUDGETS:
                cb = fits[str(f)]["controller"][str(B)]
                cl = fits[str(f)]["cloud_initiated"][str(B)]["chosen"]
                print("   budget %3.0f %%: theta %7.4f W_c %.1f delta %.2f n_c %d K_c %d %-5s "
                      "train frac %.4f mAP %.4f | oracle lead %3d | cloud %s"
                      % (100 * B, cb["theta"], cb["w_c"], cb["delta"], cb["n_c"], cb["k_c"],
                         cb["mode"], cb["train_call_fraction"], cb["train_mAP"],
                         fits[str(f)]["oracle"][str(B)]["lead_calls"],
                         ("c=%.0f s tau %.3f" % (cl["cadence_s"], cl["tau"])) if cl
                         else "INFEASIBLE"))
        obj = dict(fits=fits, folds=fi["rule"], budgets=list(BUDGETS),
                   budget_metric="call fraction (B1)",
                   objective=("maximize TRAINING-fold challenge mAP of escalation-only at a "
                              "fixed call-fraction budget; pre-registered"),
                   grid=dict(W_c=list(C.GRID_W_C), delta=list(C.GRID_DELTA),
                             n_c=list(C.GRID_N_C), K_c=list(C.GRID_K_C),
                             instability_mode=list(C.GRID_MODE),
                             background_cadence_s=list(BG_CADENCES_S)),
                   schedule=sched)
        obj["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage fit", model=None,
                                   device="cpu", n=300, args=None)
        fits_file.write_text(json.dumps(obj, indent=1, default=float))
        print("fit: %.0f s total; wrote %s" % (time.time() - t0, fits_file))

    obj_all = json.loads(fits_file.read_text())
    fits = obj_all["fits"]

    if a.stage in ("fit2", "all"):
        t0 = time.time()
        for f in range(N_FOLDS):
            te = FD.train_eval(f)
            tf = time.time()
            fl = fit_learned(R, chA, te["train"], f, fits[str(f)]["controller"])
            fits[str(f)]["learned"] = fl
            fits[str(f)]["context_trickle"] = fit_context_trickle(
                R, chA, te["train"], fl, fits[str(f)]["controller"],
                fits[str(f)]["cloud_initiated"])
            top = sorted(fl["importances"]["gbt"].items(), key=lambda kv: -kv[1])[:3]
            print("fold %d learned in %.0f s: GBT train r2 %.4f, logistic train AUC %.4f, top "
                  "features %s, context feature %s (importance %.4f)"
                  % (f, time.time() - tf, fl["fit_quality"]["gbt_train_r2"],
                     fl["fit_quality"]["logistic_train_auc"],
                     [(k, round(v, 3)) for k, v in top], fl["context"]["feature"],
                     fl["context"]["gbt_importance"]))
            for B in BUDGETS:
                ct = fits[str(f)]["context_trickle"][str(B)]["chosen"]
                print("   budget %3.0f %%: ceiling theta %+.4f frac %.4f | context trickle %s"
                      % (100 * B, fl["thresholds"][str(B)]["ceiling-gbt"]["theta"],
                         fl["thresholds"][str(B)]["ceiling-gbt"]["train_call_fraction"],
                         ("c=%.0f s tau %.3f frac %.4f" % (ct["cadence_s"], ct["tau"],
                                                           ct["train_call_fraction"]))
                         if ct else "INFEASIBLE"))
        obj_all["fits"] = fits
        obj_all["features"] = dict(used=list(LN.FEATURES),
                                   not_available=LN.NOT_AVAILABLE)
        obj_all["_provenance_fit2"] = stamp(script="ctrl1b_crossfit.py --stage fit2", model=None,
                                            device="cpu", n=300, args=None)
        fits_file.write_text(json.dumps(obj_all, indent=1, default=float))
        print("fit2: %.0f s total; wrote %s" % (time.time() - t0, fits_file))
        fits = json.loads(fits_file.read_text())["fits"]

    if a.stage in ("mechanism", "all"):
        te = FD.train_eval(0)
        mech = mechanism_new_arms(R, chA, fits["0"], te["train"])
        if "learned" in fits["0"]:
            mech["learned_arms"] = mechanism_learned_arms(R, chA, fits["0"], te["train"])
            for l in mech["learned_arms"]["step2_links"]:
                print("  LINK %-14s %-48s varies=%s" % (l["arm"], l["link"][:48], l["varies"]))
            for r in mech["learned_arms"]["step4_controls"]["permuted_target"]["per_budget"]:
                print("  ceiling control %3.0f %%: real %.4f, permuted target %.4f, device-only "
                      "%.4f" % (100 * r["budget"], r["ceiling_real"],
                                r["ceiling_permuted_target"], r["device_only"]))
        mech["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage mechanism", model=None,
                                    device="cpu", n=len(te["train"]), args=None)
        (OUT / "ctrl1b_mechanism.json").write_text(json.dumps(mech, indent=1, default=float))
        for l in mech["step2_links"]:
            print("  LINK %-14s %-48s varies=%s" % (l["arm"], l["link"][:48], l["varies"]))
        for r in mech["step4_controls"]["oracle_no_cloud_advantage"]["per_budget"]:
            print("  oracle control %3.0f %%: oracle %.4f, device scores through the cloud path "
                  "%.4f, device-only %.4f" % (100 * r["budget"], r["oracle"],
                                              r["control_device_scores_through_cloud_path"],
                                              r["device_only"]))
        for r in mech["step4_controls"]["cloud_initiated_trigger_disabled"]["per_budget"]:
            if not r.get("feasible", True):
                print("  cloud control %3.0f %%: INFEASIBLE" % (100 * r["budget"]))
            else:
                print("  cloud control %3.0f %%: with trigger %.4f, background only %.4f "
                      "(episodes worth %+.4f)" % (100 * r["budget"], r["cloud_initiated"],
                                                  r["background_only_no_trigger"],
                                                  r["gain_from_episodes"]))
        print("wrote", OUT / "ctrl1b_mechanism.json")

    if a.stage in ("pool", "all"):
        assert (OUT / "ctrl1b_mechanism.json").exists(), (
            "mechanism verification must be recorded BEFORE the pooled numbers are written")
        t0 = time.time()
        res = pool(R, chA, fits, fi)
        res["fold_rule"] = fi["rule"]
        res["superseded"] = ("StudyCTRL1-episodes' 90/210 results are kept in "
                             "results/dashcam/ctrl1/ and reports/study_ctrl1_episodes.md and are "
                             "superseded by these pooled 300-clip values, not deleted")
        res["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage pool", model=None,
                                   device="cpu", n=300, args=None)
        (OUT / "ctrl1b_crossfit.json").write_text(json.dumps(res, indent=1, default=float))
        for B in BUDGETS:
            r = res["by_budget"][str(B)]
            print("budget %3.0f %%" % (100 * B))
            for arm in ARMS_ORDER:
                g = r["gap_fraction_captured"].get(arm)
                print("   %-20s mAP %.4f  call frac %.4f  %s"
                      % (arm, r["challenge_mAP"][arm], r["realized"][arm]["call_fraction"],
                         ("gap %.1f %% [%.1f, %.1f]"
                          % (100 * g["value"], 100 * g["ci"][0], 100 * g["ci"][1]))
                         if g and g["value"] is not None else ""))
        con = consistency(R, chA)
        con["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage pool", model=None,
                                   device="cpu", n=300, args=None)
        (OUT / "ctrl1b_consistency.json").write_text(json.dumps(con, indent=1, default=float))
        print("pool: %.0f s; check 1 agree=%s (cloud %+.2e, device %+.2e)"
              % (time.time() - t0, con["check1_all300"]["agree"],
                 con["check1_all300"]["diff_cloud"], con["check1_all300"]["diff_device"]))
        print("wrote", OUT / "ctrl1b_crossfit.json")

    if a.stage in ("frames", "all"):
        t0 = time.time()
        fr = frames_crossfit(R, chA, fi)
        fr["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage frames", model=None,
                                  device="cpu", n=300, args=None)
        (OUT / "frames1b_crossfit.json").write_text(json.dumps(fr, indent=1, default=float))
        for tier in ("32BI", "4BI"):
            row = []
            for d in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
                g = fr["pooled_gain_vs_delay"]["%s|D%.2f" % (tier, d)]
                row.append("d=%.1f %+.4f%s" % (d, g["gain"], "*" if g["excludes_zero"] else ""))
            print("  %s pooled N3 minus N1: %s" % (tier, "  ".join(row)))
            cn = fr["choose_n"]["%s|D0.00" % tier]
            print("     choose-N at d=0: %d of 5 folds picked N=3, held-out gain %+.4f "
                  "[%+.4f, %+.4f]" % (cn["n_folds_choosing_N3"], cn["gain"], cn["ci"][0],
                                      cn["ci"][1]))
        print("frames: %.0f s; wrote %s" % (time.time() - t0, OUT / "frames1b_crossfit.json"))

    if a.stage in ("workload", "all"):
        wl = workload(R, chA, fits, fi)
        wl["_provenance"] = stamp(script="ctrl1b_crossfit.py --stage workload", model=None,
                                  device="cpu", n=300, args=None)
        (OUT / "ctrl1b_workload_traces.json").write_text(json.dumps(wl, indent=1, default=float))
        print("workload traces: %d clips, %d arms; wrote %s"
              % (len(wl["clips"]), len(wl["arms"]), OUT / "ctrl1b_workload_traces.json"))
    return 0




# ---------------------------------------------------------------- arms (d) and (e)
def learned_matrix(R, clips: Sequence[str], w_c: float, delta: float, n_c: int
                   ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Tuple[int, int]]]:
    """Features and the signed per-instant gain target (B8), one row per device sample."""
    import csv
    rows = {r["file_name"]: r for r in SP.clip_rows()}
    Xs, ys, span = [], [], {}
    at = 0
    for c in clips:
        _cap, read, val = R.S[c]
        if not len(read):
            span[c] = (at, at)
            continue
        X = LN.clip_features(val, read, w_c, delta, n_c, R.cad_s, rows[c])
        y = LN.clip_target(R.ctx["arrs"][C.CLOUD][c], R.dev[c], read,
                           R.ctx["meta"][c]["label"])
        Xs.append(X)
        ys.append(y)
        span[c] = (at, at + len(y))
        at += len(y)
    return (np.vstack(Xs) if Xs else np.zeros((0, len(LN.FEATURES)))), \
           (np.concatenate(ys) if ys else np.zeros(0)), span


def learned_signal(pred: np.ndarray, span: Dict[str, Tuple[int, int]],
                   clips: Sequence[str]) -> Dict[str, np.ndarray]:
    return {c: pred[span[c][0]:span[c][1]] for c in clips}


def episodes_from_signal(R, clips: Sequence[str], sig: Dict[str, np.ndarray], theta: float,
                         k_c: int) -> Dict[str, List[Dict[str, Any]]]:
    """The learned score is dropped into the SAME episode machinery as every other arm, so the
    accounting cannot differ between arms."""
    out = {}
    for c in clips:
        G = R.ctx["meta"][c]["G"]
        s = sig[c]
        out[c] = C.run_episodes(s if len(s) else np.full(max(len(R.S[c][1]), 1), np.nan),
                                R.S[c][1], G, theta, k_c, R.sched["call_cadence_steps"], E_K,
                                R.sched["cloud_shift_steps"])
    return out


def fit_learned(R, chA, train: Sequence[str], fold: int, controller: Dict[str, Any]
                ) -> Dict[str, Any]:
    """Arms (d) and (e), fitted on the TRAINING folds only.

    The feature window (W_c, delta, n_c) is the one the controller search already chose on these
    same training folds at the 10 % budget, so the ceiling reads the same signals the device
    filter does and the comparison is about the DECISION RULE, not about the window."""
    base = controller[str(BUDGETS[1])]
    w_c, delta, n_c = base["w_c"], base["delta"], base["n_c"]
    Xtr, ytr, sp_tr = learned_matrix(R, train, w_c, delta, n_c)
    ok = np.isfinite(ytr) & np.all(np.isfinite(Xtr), axis=1)
    gbt = LN.GBT().fit(Xtr[ok], ytr[ok])
    lg = LN.Logistic().fit(Xtr[ok], (ytr[ok] > 0).astype(float))
    p_gbt_tr = gbt.predict(Xtr)
    p_lg_tr = lg.predict(Xtr)
    imp_gbt = gbt.importances()
    imp_lg = lg.importances()

    out: Dict[str, Any] = dict(
        fold=fold, window=dict(w_c=w_c, delta=delta, n_c=n_c, source="the controller's own "
                               "training-fold choice at the 10 % budget"),
        features=list(LN.FEATURES), features_not_available=LN.NOT_AVAILABLE,
        n_train_rows=int(ok.sum()),
        target=("signed per-instant cloud gain (B8): (cloud score at the instant minus the "
                "device's displayed score) x (+1 on positives, -1 on negatives)"),
        fit_quality=dict(
            gbt_train_r2=LN.r2(ytr[ok], p_gbt_tr[ok]),
            logistic_train_auc=LN.auc((ytr[ok] > 0).astype(float), p_lg_tr[ok]),
            n_trees=len(gbt.trees), base=gbt.base),
        importances=dict(gbt=imp_gbt, logistic=imp_lg),
        model=dict(gbt=dict(base=float(gbt.base), lr=float(gbt.lr),
                            trees=[dict(feature=int(t.feature), threshold=float(t.threshold),
                                        left=float(t.left), right=float(t.right),
                                        gain=float(t.gain)) for t in gbt.trees],
                            n_trees_total=len(gbt.trees)),
                   logistic=dict(w=[float(x) for x in lg.w], b=float(lg.b),
                                 mu=[float(x) for x in lg.mu],
                                 sd=[float(x) for x in lg.sd],
                                 by_feature=dict(zip(LN.FEATURES,
                                                     [float(x) for x in lg.w])))),
        thresholds={}, context={})

    sig_gbt = learned_signal(p_gbt_tr, sp_tr, train)
    sig_lg = learned_signal(p_lg_tr, sp_tr, train)
    for B in BUDGETS:
        th = {}
        for name, sig in (("ceiling-gbt", sig_gbt), ("ceiling-logistic", sig_lg)):
            lo = float(np.nanmin(np.concatenate([sig[c] for c in train if len(sig[c])])))
            hi = float(np.nanmax(np.concatenate([sig[c] for c in train if len(sig[c])])))

            def frac(x, sig=sig):
                return call_fraction(R, episodes_from_signal(R, train, sig, x, base["k_c"]),
                                     None, train)
            tsel, f = solve_down(frac, B, lo - 1e-6, hi + 1e-6, iters=30)
            th[name] = dict(theta=tsel, train_call_fraction=f, k_c=base["k_c"],
                            hit_budget=bool(abs(f - B) <= TOL))
        out["thresholds"][str(B)] = th

    # ---- arm (e): the strongest NON-SCORE feature, chosen on the training folds only
    ctx_rank = sorted(((f, imp_gbt.get(f, 0.0)) for f in LN.CONTEXT_FEATURES),
                      key=lambda kv: -kv[1])
    ctx_rank_lg = sorted(((f, imp_lg.get(f, 0.0)) for f in LN.CONTEXT_FEATURES),
                         key=lambda kv: -kv[1])
    chosen_feat = ctx_rank[0][0] if ctx_rank[0][1] > 0 else ctx_rank_lg[0][0]
    jcol = LN.FEATURES.index(chosen_feat)
    col = Xtr[ok][:, jcol] if ok.any() else np.zeros(1)
    binary = bool(np.all(np.isin(np.unique(col), (0.0, 1.0))))
    thr = 0.5 if binary else float(np.median(col))
    out["context"] = dict(
        feature=chosen_feat, threshold=thr,
        threshold_rule=("0.5 for a BINARY feature, the training-fold MEDIAN for a continuous "
                        "one; neither is fitted to the outcome. The median alone DEGENERATES on "
                        "a one-hot feature whose category covers more than half the rows (its "
                        "median is then 1.0 and the test v > threshold never fires), which the "
                        "mechanism verification caught as a CONSTANT link before any pooled "
                        "number was written; see the report's section on arm (e)"),
        threshold_is_binary_rule=binary,
        gbt_importance=imp_gbt.get(chosen_feat, 0.0),
        logistic_importance=imp_lg.get(chosen_feat, 0.0),
        ranking_gbt=ctx_rank[:5], ranking_logistic=ctx_rank_lg[:5],
        all_context_importance_zero=bool(ctx_rank[0][1] <= 0.0),
        note=("every available non-score feature is CLIP-LEVEL Nexar metadata, because no "
              "per-instant visual feature is computable on this machine, so the modulation is "
              "per clip rather than per instant"))
    return out


def rebuild_models(fit_l: Dict[str, Any]) -> Tuple[Any, Any]:
    """Reconstruct the two fitted models from the fits JSON, so the pooling stage never refits."""
    g = LN.GBT()
    g.base = float(fit_l["model"]["gbt"]["base"])
    g.lr = float(fit_l["model"]["gbt"]["lr"])
    g.trees = [LN.Stump(int(r["feature"]), float(r["threshold"]), float(r["left"]),
                        float(r["right"]), float(r["gain"]))
               for r in fit_l["model"]["gbt"]["trees"]]
    l = LN.Logistic()
    l.w = np.asarray(fit_l["model"]["logistic"]["w"], dtype=float)
    l.b = float(fit_l["model"]["logistic"]["b"])
    l.mu = np.asarray(fit_l["model"]["logistic"]["mu"], dtype=float)
    l.sd = np.asarray(fit_l["model"]["logistic"]["sd"], dtype=float)
    return g, l


def learned_held(R, fit_l: Dict[str, Any], held: Sequence[str], B: float
                 ) -> Dict[str, Dict[str, np.ndarray]]:
    w = fit_l["window"]
    X, _y, sp = learned_matrix(R, held, w["w_c"], w["delta"], w["n_c"])
    g, l = rebuild_models(fit_l)
    return dict(gbt=learned_signal(g.predict(X), sp, held),
                logistic=learned_signal(l.predict(X), sp, held))


def context_cstep(R, clips: Sequence[str], fit_l: Dict[str, Any], cstep: int) -> Dict[str, int]:
    """Arm (e): halve the background cadence on the clips whose context signal is above its
    training-fold threshold."""
    import csv
    rows = {r["file_name"]: r for r in SP.clip_rows()}
    feat, thr = fit_l["context"]["feature"], fit_l["context"]["threshold"]
    out = {}
    for c in clips:
        v = _context_value(rows[c], feat)
        out[c] = max(2, cstep // 2) if v > thr else cstep
    return out


def _context_value(row: Dict[str, str], feat: str) -> float:
    for s in LN.SCENES:
        if feat == "scene_" + s.lower().replace("-", "_"):
            return 1.0 if row.get("scene") == s else 0.0
    for s in LN.LIGHTS:
        if feat == "light_" + s.lower():
            return 1.0 if row.get("light") == s else 0.0
    for s in LN.WEATHERS:
        if feat == "weather_" + s.lower():
            return 1.0 if row.get("weather") == s else 0.0
    raise KeyError("context feature %r is not a clip-level feature" % feat)


def fit_context_trickle(R, chA, train: Sequence[str], fit_l: Dict[str, Any],
                        controller: Dict[str, Any], cloud: Dict[str, Any]) -> Dict[str, Any]:
    """Arm (e) keeps arm (b)'s base cadence and threshold search, with the per-clip cadence
    doubling applied before tau is solved, so the budget still binds."""
    ch_tr = C.challenge_for(sub_for(R.ctx, train))
    out = {}
    for B in BUDGETS:
        k_c = controller[str(B)]["k_c"]
        picked = None
        for cs in BG_CADENCES_S:
            cstep = int(round(cs / STEP))
            per = context_cstep(R, train, fit_l, cstep)
            floor = np.mean([R.sched["call_cadence_steps"] / per[c] for c in train])
            if floor > B + TOL:
                continue

            def fc(x, per=per, k_c=k_c):
                e, b = cloud_initiated(R, train, per, x, k_c)
                return call_fraction(R, e, b, train)
            tsel, f = solve_down(fc, B, -30.0, 0.5, iters=30)
            e, b = cloud_initiated(R, train, per, tsel, k_c)
            m = float(ch_tr.point(arm_stream(R, train, e, b))["mAP"])
            cand = dict(cadence_s=cs, tau=tsel, k_c=k_c, train_call_fraction=f, train_mAP=m,
                        mean_background_floor=float(floor),
                        n_clips_modulated=int(sum(1 for c in train
                                                  if per[c] != cstep)),
                        hit_budget=bool(abs(f - B) <= TOL))
            if picked is None or cand["train_mAP"] > picked["train_mAP"]:
                picked = cand
        out[str(B)] = dict(chosen=picked,
                           infeasible_reason=(None if picked else
                                              "no background cadence in {1, 2, 4} s fits this "
                                              "budget once the context modulation is applied"))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
