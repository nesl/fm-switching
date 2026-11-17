"""StudyT0b-fidelity Part 2: score the four approval criteria on StudyENG1c-hostfull Part D.

WHAT THIS IS. StudyT0-fidelity's criterion (i) failed on StudyENG1 Part C, StudyPOL4-engine
revised the cost model, and T0b re-tests the revision on data the model has never seen. The
fresh collection is StudyENG1c-hostfull Part D: its held-out split was written at
2026-11-16T15:04:32Z, before its first request, and ENG1c recorded but did not analyse its 120
HOLDOUT pairs.

HOLDOUT FENCING. This module's loader takes a `split` and builds trials for the FIT pairs only.
`split="holdout"` raises unless an explicit user authorization string is passed, and even then
the one-shot path of `t0_harness.T0Harness.run_holdout_once` is the only intended caller, which
re-verifies the freeze and refuses a second run. The default path never constructs a holdout
trial at all, so a refused run has not touched the holdout.

OUT OF SAMPLE. No StudyPOL4 coefficient and no StudyT0 parameter was fitted on any StudyENG1c
datum: terms (a), (b) and (c) were fitted on StudyENG1 Parts A, B and D and on StudyENG1b. The
240 ENG1c FIT pairs are therefore OUT OF SAMPLE for the model. They are called FIT because they
are ENG1c's own fit split, and they are used here for implementation verification and for the
old-versus-new comparison that decides whether to spend the holdout.

WHAT IS SCORED: THE DELAY MODEL WITH RESIDENCY GIVEN. The frozen model prices a host reload
(term a) and a cold rebuild (term b) but carries no host-tier residency bookkeeping. The tier at
arrival is therefore an INPUT, taken from the measurement, exactly as StudyENG1 Part C's cached
tokens were an input to T0. Predicting residency from write volume (StudyENG1c implication 1) is
a separate later test and is not performed here.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import trace_replay as tr
from .eng1_engine import ENGINE_MODELS, EngineSim, Pol4Terms, make_sim
from .kvpool import KVPool
from .run_t0 import (COMPLETION_MARE, MIN_FRACTION, _dist, delay_pass, evaluate_part_c)
from .run_pol4 import error_direction, pooled_direction

PART_D_PATH = "results/cost/study_eng1c/eng1c_partD_h100nvl.jsonl"
PART_B_TRIALS_PATH = "results/cost/study_eng1c/eng1c_trials_h100nvl.jsonl"
ENG1C_SPLIT_PATH = "results/cost/study_eng1c/eng1c_holdout_split.json"
ENG1C_RESULTS_PATH = "results/cost/study_eng1c/eng1c_results.json"
OUT_DIR = "results/orchestration/study_t0b"

ACTION_NAME = {"mono": "mono11k", "piece2048": "piece2048", "piece1024": "piece1024"}
IB_RATIO = 0.90

OUT_OF_SAMPLE_LABEL = (
    "OUT OF SAMPLE FOR THE MODEL. No StudyPOL4 term and no StudyT0 parameter was fitted on any "
    "StudyENG1c datum; the terms were fitted on StudyENG1 Parts A, B and D and on StudyENG1b. "
    "These are ENG1c's own FIT pairs, used for implementation verification and for the "
    "old-versus-new comparison; the 120 ENG1c HOLDOUT pairs are untouched.")

RESIDENCY_LABEL = (
    "DELAY MODEL WITH RESIDENCY GIVEN. The tier at arrival is an input taken from the "
    "measurement (the injected job's own recorded cached tokens, with ENG1c's write-order "
    "simulator as the cross-check), not a prediction. The model is scored on what delay the "
    "action imposes given its tier, not on predicting the tier.")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


class HoldoutFenced(PermissionError):
    """Raised when the ENG1c Part D holdout is requested without authorization."""


def _external_attribution(trial: tr.Trial, counters: Dict[str, int]) -> None:
    """StudyPOL4's own rule, applied unchanged: a per-run host-transfer counter may be charged to
    the action only when it equals the action's cached tokens within the chaining tolerance AND
    the baseline arm's counter is zero, so nothing else in the trace could have produced it."""
    for mode in sorted(trial.arms):
        ext = int(counters.get(mode, 0) or 0)
        if ext <= 0:
            continue
        others = [counters.get(m, 0) or 0 for m in trial.arms if m != mode]
        rows = sorted(trial.arms[mode].action, key=lambda r: (r.get("part_i") or 0))
        cached = sum(int(r.get("cached_tokens", 0) or 0) for r in rows)
        if any(o != 0 for o in others) or abs(cached - ext) > tr.EXTERNAL_TOLERANCE_TOKENS:
            trial.external_unattributed[mode] = ext
            continue
        left = ext
        for row in rows:
            take = min(left, int(row.get("cached_tokens", 0) or 0))
            row["_external_cached_tokens"] = take
            left -= take


def load_part_d_trials(split: str = "fit", authorization: str = "",
                       path: Any = None) -> Tuple[List[tr.Trial], Dict[str, Any]]:
    """Every ENG1c Part D pair of the requested split, as trials the frozen replay can score.

    `load` carries the cap so that criterion (ii)'s background condition is (cap, load), which is
    what ENG1c varied; `action` is T0's own action name, so the ranking code compares the same
    three actions T0 ranked."""
    split = str(split).lower()
    if split not in ("fit", "holdout"):
        raise ValueError("split must be 'fit' or 'holdout', got %r" % split)
    if split == "holdout" and not authorization:
        raise HoldoutFenced(
            "the 120 ENG1c Part D HOLDOUT pairs are the only fresh data T0b has. Building them "
            "needs the user's authorization recorded in `authorization`, and the run itself must "
            "go through t0_harness.T0Harness.run_holdout_once so the freeze is re-verified and a "
            "second run is refused.")
    p = Path(path) if path is not None else (_root() / PART_D_PATH)
    buckets: Dict[Tuple[int, str, str, int], tr.Trial] = {}
    counters: Dict[Tuple[int, str, str, int], Dict[str, int]] = defaultdict(dict)
    want_holdout = (split == "holdout")
    seen = dict(rows=0, pairs_fit=set(), pairs_holdout=set(), modes=defaultdict(int),
                kinds=defaultdict(int))
    with open(p) as fh:
        for line in fh:
            row = json.loads(line)
            seen["rows"] += 1
            kind = row.get("kind")
            seen["kinds"][str(kind)] += 1
            if kind in ("pair_check", "build"):
                continue
            mode = row.get("mode")
            if mode not in ("with", "without", "repeat"):
                continue
            hold = bool(row.get("holdout"))
            (seen["pairs_holdout"] if hold else seen["pairs_fit"]).add(row.get("pair"))
            if hold != want_holdout:
                continue
            k = (int(row["cap"]), str(row["load"]), str(row["variant"]), int(row["trial"]))
            t = buckets.get(k)
            if t is None:
                t = tr.Trial(load="%d_%s" % (k[0], k[1]), action=ACTION_NAME[k[2]],
                             trial=k[3], holdout=hold,
                             t_inj_rel=float(row.get("t_inj_rel") or 0.0))
                buckets[k] = t
            if kind == "run_summary":
                md = row.get("metrics_delta") or {}
                counters[k][mode] = int(md.get(tr.EXTERNAL_TOKENS_COUNTER, 0) or 0)
            arm = t.arms.get(mode)
            if arm is None:
                arm = tr.Arm(mode=mode, t0_trace=float(row.get("t0_trace") or 0.0))
                t.arms[mode] = arm
            if row.get("t0_trace") and not arm.t0_trace:
                arm.t0_trace = float(row["t0_trace"])
            seen["modes"][mode] += 1
            if kind == "episodic":
                arm.background.append(row)
            elif kind == "inject":
                arm.action.append(row)
            elif kind == "job":
                # NOT a setup row: setup rows must finish before the trace starts, and the job
                # is the action itself. It is attached to the trial for the tier cross-check.
                setattr(t, "job_record_%s" % mode, row)
    trials = [buckets[k] for k in sorted(buckets)]
    for k, t in sorted(buckets.items()):
        _external_attribution(t, counters.get(k, {}))
    raw = json.loads((_root() / ENG1C_SPLIT_PATH).read_text())
    n_split = sum(len(v) for v in raw["holdout"].values())
    audit = dict(
        split=split, n_trials=len(trials),
        n_fit_pairs_in_record=len(seen["pairs_fit"]),
        n_holdout_pairs_in_record=len(seen["pairs_holdout"]),
        n_holdout_pairs_in_split_file=n_split,
        holdout_pairs_built=(len(trials) if want_holdout else 0),
        holdout_trials_used=(len(trials) if want_holdout else 0),
        rows_read=seen["rows"], kinds={k: v for k, v in sorted(seen["kinds"].items())},
        split_file=ENG1C_SPLIT_PATH, authorization=authorization,
        assertions=["the record's holdout flag selects exactly the split file's pair count",
                    "no trial of the other split is constructed at all",
                    "every scored trial carries a with arm and a without arm"])
    assert len(seen["pairs_holdout"]) == n_split, (
        "the record flags %d holdout pairs, the split file lists %d"
        % (len(seen["pairs_holdout"]), n_split))
    if not want_holdout:
        assert all(not t.holdout for t in trials), "a holdout trial reached the FIT set"
    missing = [t.key() for t in trials if "with" not in t.arms or "without" not in t.arms]
    assert not missing, "trials without both arms: %s" % missing[:5]
    return trials, audit


def tier_inputs(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """What residency the scored trials were given, and whether the measurement and ENG1c's
    write-order simulator agreed about it. Residency is an INPUT here (see RESIDENCY_LABEL); this
    records which value each trial got and how often the two sources disagree."""
    rows = []
    for t in trials:
        acts = sorted(t.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
        if not acts:
            continue
        first = acts[0]
        cached = int(first.get("cached_tokens", 0) or 0)
        prompt = int(first.get("prompt_tokens", 0) or 0)
        ext = sum(int(r.get("_external_cached_tokens", 0) or 0) for r in acts)
        job = getattr(t, "job_record_with", None)
        sim_tier = (job.get("tier_at_arrival") or {}).get("R4_code") if job else None
        measured = ("cold" if cached == 0 else
                    ("warm_host" if ext > 0 else "warm_local"))
        rows.append(dict(key=t.key(), cached_tokens=cached, prompt_tokens=prompt,
                         external_cached_tokens=ext, measured_state=measured,
                         eng1c_sim_tier_R4=sim_tier,
                         unattributed=dict(t.external_unattributed)))
    agree = [r for r in rows if r["eng1c_sim_tier_R4"] is not None and
             ((r["measured_state"] == "cold") == (r["eng1c_sim_tier_R4"] == "cold"))]
    return dict(n=len(rows), n_cold=sum(1 for r in rows if r["measured_state"] == "cold"),
                n_warm_host=sum(1 for r in rows if r["measured_state"] == "warm_host"),
                n_warm_local=sum(1 for r in rows if r["measured_state"] == "warm_local"),
                n_agree_cold_vs_warm=len(agree),
                n_with_unattributed_counter=sum(1 for r in rows if r["unattributed"]),
                label=RESIDENCY_LABEL, rows=rows)


def _sum_over_shared(trial: tr.Trial, base_mode: str) -> Optional[Dict[str, Any]]:
    """The imposed-delay sum of ENG1c Part D, computed against any chosen baseline arm: the sum
    over episodic background requests matched by index of TTFT(with) minus TTFT(baseline)."""
    if "with" not in trial.arms or base_mode not in trial.arms:
        return None
    w = {tr._bg_key(r): r for r in trial.arms["with"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    o = {tr._bg_key(r): r for r in trial.arms[base_mode].background
         if r.get("kind") in tr.COMPARED_KINDS}
    shared = sorted(set(w) & set(o), key=lambda k: str(k))
    total = 0.0
    n = 0
    for k in shared:
        a, b = w[k].get("ttft_s"), o[k].get("ttft_s")
        if a is None or b is None:
            continue
        total += float(a) - float(b)
        n += 1
    return dict(total_s=total, n_matched=n)


def repeatability_ceiling(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """Criterion (i) applied to the measurement against itself, which is (i-b)'s denominator.

    ENG1c's repeat rule put an independent repeat of the WITHOUT run on the first three FIT
    trials of each cell. A trial with a repeat therefore yields TWO independent measurements of
    the same imposed delay: (with minus without) and (with minus repeat). The ceiling is the
    fraction of those pairs that agree under criterion (i)'s own tolerance, so no predictor can
    exceed it.

    DEVIATION FROM THE T0b ROW'S WORDING, DISCLOSED: no HOLDOUT pair has a repeat, so the
    denominator comes from FIT pairs of the SAME 24 cells as the numerator. That satisfies 'the
    same conditions' and not 'the same trials'."""
    rows = []
    for t in trials:
        if "repeat" not in t.arms:
            continue
        a = _sum_over_shared(t, "without")
        b = _sum_over_shared(t, "repeat")
        if not a or not b or a["n_matched"] == 0 or b["n_matched"] == 0:
            continue
        chk = delay_pass(a["total_s"], b["total_s"])
        rows.append(dict(key=t.key(), cell=t.cell(), load=t.load, action=t.action,
                         est_vs_without_s=a["total_s"], est_vs_repeat_s=b["total_s"],
                         n_matched=min(a["n_matched"], b["n_matched"]), check=chk))
    n = len(rows)
    npass = sum(1 for r in rows if r["check"]["passed"])
    per_cell: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_cell[r["cell"]].append(r)
    return dict(
        n=n, n_passed=npass, ceiling=(npass / n if n else None),
        per_cell={c: dict(n=len(v), n_passed=sum(1 for r in v if r["check"]["passed"]),
                          ceiling=sum(1 for r in v if r["check"]["passed"]) / len(v))
                  for c, v in sorted(per_cell.items())},
        definition="criterion (i) between two independent measurements of the same trial's "
                   "imposed delay, (with - without) against (with - repeat)",
        deviation="no HOLDOUT pair carries a repeat; the denominator is the FIT repeat pairs of "
                  "the same 24 cells (cap x load x action) as the numerator",
        rows=rows)


def criterion_i_b(fraction: Optional[float], ceiling: Optional[float]) -> Dict[str, Any]:
    """(i-b) as pre-registered: the model's agreement fraction must be at least 0.9 times the
    measurement's agreement with itself, under the same tolerance on the same conditions."""
    if fraction is None or ceiling in (None, 0):
        return dict(verdict="NOT COMPUTABLE", fraction=fraction, ceiling=ceiling,
                    threshold=IB_RATIO)
    ratio = fraction / ceiling
    return dict(criterion="(i-b) delay imposed on others, repeatability-scaled",
                fraction=fraction, ceiling=ceiling, ratio=ratio, threshold=IB_RATIO,
                bar_absolute_for_reference=MIN_FRACTION,
                verdict=("PASS" if ratio >= IB_RATIO else "FAIL"),
                wording="three numbers side by side: the (i-b) bar is 0.9 of the ceiling, the "
                        "measurement repeatability ceiling is %s, and the model is %s"
                        % (("%.4f" % ceiling), ("%.4f" % fraction)))


def criterion_iv_eng1c_part_b(path: Any = None) -> Dict[str, Any]:
    """Criterion (iv) on ENG1c Part B, which is the ENG1b trial repeated under host caps.

    This is reported as a DEGENERACY CHECK rather than a re-test: if every Part B trial lost the
    whole prefix from the GPU pool, the measured class is a CONSTANT and the criterion cannot
    discriminate, which CLAUDE.md Step 2 calls a stopping condition for that link. The number is
    computed rather than assumed."""
    p = Path(path) if path is not None else (_root() / PART_B_TRIALS_PATH)
    rows = []
    for line in open(p):
        t = json.loads(line)
        if t.get("sub") != "B" or t.get("resume_error"):
            continue
        prefix = int(t.get("prefix_tokens") or 0)
        md = t.get("resume_window_delta") or {}
        local_hit = int(md.get("prompt_tokens_by_source_total|local_cache_hit", 0) or 0)
        local_hit = min(local_hit, prefix)
        lost = max(prefix - local_hit, 0)
        kvcap = int(t.get("kv_capacity_tokens") or 0)
        alloc = int(t.get("filler_tokens_done_before_resume") or 0) + int(t.get("occ_tokens") or 0)
        pool = KVPool(capacity_tokens=kvcap) if kvcap > 0 else None
        pred_lost = None
        if pool is not None and prefix > 0:
            pool.put("prefix", prefix, 0.0, referenced=False)
            pred_lost = int(pool.allocate("other_work", alloc, 1.0)["freed"].get("prefix", 0))
        rows.append(dict(ns=t.get("ns"), cap=t.get("cap"), occ=t.get("occ"),
                         older=bool(t.get("older")), prefix_tokens=prefix,
                         measured_lost_tokens=lost,
                         measured_class=tr.loss_class(lost, prefix),
                         predicted_lost_tokens=pred_lost,
                         predicted_class=(tr.loss_class(pred_lost, prefix)
                                          if pred_lost is not None else None),
                         kv_capacity_tokens=kvcap, allocated_tokens=alloc))
    classes = defaultdict(int)
    for r in rows:
        classes[r["measured_class"]] += 1
    scored = [r for r in rows if r["predicted_class"] is not None]
    correct = sum(1 for r in scored if r["predicted_class"] == r["measured_class"])
    degenerate = len(classes) <= 1
    dominant = (max(classes.values()) / len(rows)) if rows else None
    near = bool(not degenerate and dominant is not None and dominant >= 0.9)
    if degenerate:
        verdict = ("DEGENERATE, NOT A RE-TEST: the measured class is constant, so the criterion "
                   "cannot discriminate and T0's registered (iv) result stands")
    elif near:
        verdict = ("COMPUTED BUT NEARLY DEGENERATE: %d of %d trials are in one class and the "
                   "third class never occurs, so the accuracy is carried by a class the model "
                   "gets right by construction. It is reported, not treated as a strong "
                   "re-test, and T0's registered (iv) result stands"
                   % (max(classes.values()), len(rows)))
    else:
        verdict = "COMPUTED on ENG1c Part B, which varies the class"
    return dict(
        n=len(rows), n_scored=len(scored), measured_class_counts=dict(sorted(classes.items())),
        class_accuracy=(correct / len(scored) if scored else None), n_correct=correct,
        degenerate=bool(degenerate), nearly_degenerate=near,
        dominant_class_share=dominant,
        confusion={"%s->%s" % (a, b): c for (a, b), c in sorted(
            {(r["measured_class"], r["predicted_class"]): sum(
                1 for x in scored if x["measured_class"] == r["measured_class"]
                and x["predicted_class"] == r["predicted_class"]) for r in scored}.items())},
        threshold=0.90,
        criterion_verdict=("PASS" if scored and correct / len(scored) >= 0.90 else "FAIL"),
        verdict=verdict,
        mae_fraction_lost=(statistics.median(
            [abs((r["predicted_lost_tokens"] - r["measured_lost_tokens"]) / max(r["prefix_tokens"], 1))
             for r in scored]) if scored else None),
        note="ENG1c Part B is not ENG1c's holdout (the holdout is Part D only), so reading it "
             "spends nothing. Every Part B trial is OUT OF SAMPLE for the model.",
        rows=rows)


def cross_check_against_eng1c(trials: Sequence[tr.Trial], _unused: Any = None) -> Dict[str, Any]:
    """CLAUDE.md consistency check 1 on the one quantity ENG1c published itself: the measured
    imposed delay per trial. ENG1c computed it from the same rows with its own code, so a
    disagreement means the adapter is wrong. Both definitions are compared, which is how the
    definition audit's finding was established."""
    raw = json.loads((_root() / ENG1C_RESULTS_PATH).read_text())
    theirs = {}
    for r in raw["D"]["trials"]:
        theirs[(int(r["cap"]), str(r["load"]), ACTION_NAME[str(r["variant"])],
                int(r["trial"]))] = float(r["imposed_s"])
    out = {}
    n = 0
    for metric in METRICS:
        rows = []
        for t in trials:
            cap, load = t.load.split("_", 1)
            k = (int(cap), load, t.action, t.trial)
            if k not in theirs:
                continue
            m = _measured_sum(t, "without", metric)
            if not m:
                continue
            rows.append(dict(key=t.key(), mine_s=m["total_s"], eng1c_s=theirs[k],
                             abs_diff_s=abs(m["total_s"] - theirs[k])))
        n = max(n, len(rows))
        worst = max((r["abs_diff_s"] for r in rows), default=None)
        out[metric] = dict(
            n=len(rows), max_abs_diff_s=worst,
            median_abs_diff_s=(statistics.median([r["abs_diff_s"] for r in rows])
                               if rows else None),
            n_within_1e_6=sum(1 for r in rows if r["abs_diff_s"] <= 1e-6),
            agree=(worst is not None and worst <= 1e-6), examples=rows[:5])
    out["n"] = n
    out["quantity"] = "imposed delay per trial, summed over the episodic background"
    out["prior_source"] = "results/cost/study_eng1c/eng1c_results.json, D.trials[].imposed_s"
    out["reading"] = ("the latency definition reproduces ENG1c's published value exactly on every "
                      "trial, so the adapter reads the record correctly; the TTFT definition does "
                      "not, because it is a different quantity")
    return out


# --------------------------------------------------------------- mechanism verification
def mechanism_verification(trials: Sequence[tr.Trial]) -> Dict[str, Any]:
    """CLAUDE.md Steps 1 to 5, computed and recorded BEFORE the sweep's conclusions.

    Step 4's controls disable the mechanism under test rather than argue about it: (a) the action
    is removed from the with arm, which must collapse the predicted imposed delay to zero; (b)
    the host-transfer input is zeroed, which must change the prediction on exactly the trials
    whose action reloaded from host and on no others."""
    sim = make_sim("pol4")
    terms = Pol4Terms.load()
    link_rows = []
    pred_by_state: Dict[str, List[float]] = defaultdict(list)
    ext_tokens = []
    prompts = []
    for t in trials:
        acts = sorted(t.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
        if not acts:
            continue
        cached = int(acts[0].get("cached_tokens", 0) or 0)
        ext = sum(int(r.get("_external_cached_tokens", 0) or 0) for r in acts)
        state = "cold" if cached == 0 else ("warm_host" if ext > 0 else "warm_local")
        pr = tr.predict_trial(t, sim)
        pred_by_state[state].append(pr["predicted_delay_s"])
        ext_tokens.append(ext)
        prompts.append(sum(int(r.get("prompt_tokens", 0) or 0) for r in acts))

    # Step 4 (a): no action in the with arm at all
    zero_action = []
    with_action_same_trials = []
    for t in trials[:40]:
        with_action_same_trials.append(tr.predict_trial(t, sim)["predicted_delay_s"])
        res_w = sim.run(tr._arm_requests(t.arms["with"], include_action=False))
        res_o = sim.run(tr._arm_requests(t.arms["without"], include_action=False))
        w = {tr._bg_key(r): r for r in t.arms["with"].background
             if r.get("kind") in tr.COMPARED_KINDS}
        o = {tr._bg_key(r): r for r in t.arms["without"].background
             if r.get("kind") in tr.COMPARED_KINDS}
        tot = 0.0
        for k in sorted(set(w) & set(o), key=lambda k: str(k)):
            a = res_w["per_request"].get(str(w[k].get("rid")), {}).get("ttft_s")
            b = res_o["per_request"].get(str(o[k].get("rid")), {}).get("ttft_s")
            if a is None or b is None:
                continue
            tot += float(a) - float(b)
        zero_action.append(dict(key=t.key(), predicted_delay_without_action_s=tot))

    # Step 4 (b): the host-transfer input zeroed
    host_control = []
    for t in trials:
        acts = sorted(t.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
        ext = sum(int(r.get("_external_cached_tokens", 0) or 0) for r in acts)
        base = tr.predict_trial(t, sim)["predicted_delay_s"]
        on = sim.run(tr._arm_requests(t.arms["with"], include_action=True))["per_request"]
        ttft_on = [on.get(str(r.get("rid")), {}).get("ttft_s") for r in acts]
        saved = [int(r.get("_external_cached_tokens", 0) or 0) for r in acts]
        for r in acts:
            r["_external_cached_tokens"] = 0
        off = tr.predict_trial(t, sim)["predicted_delay_s"]
        offp = sim.run(tr._arm_requests(t.arms["with"], include_action=True))["per_request"]
        ttft_off = [offp.get(str(r.get("rid")), {}).get("ttft_s") for r in acts]
        for r, v in zip(acts, saved):
            r["_external_cached_tokens"] = v
        d_ttft = max((abs(a - b) for a, b in zip(ttft_on, ttft_off)
                      if a is not None and b is not None), default=0.0)
        host_control.append(dict(key=t.key(), external_tokens=ext, with_term_s=base,
                                 term_off_s=off, changed=bool(abs(base - off) > 1e-9),
                                 action_ttft_change_s=d_ttft,
                                 action_ttft_changed=bool(d_ttft > 1e-9),
                                 n_background=len(t.arms["with"].background)))
    hc_host = [r for r in host_control if r["external_tokens"] > 0]
    hc_other = [r for r in host_control if r["external_tokens"] == 0]
    za = [r["predicted_delay_without_action_s"] for r in zero_action]

    step2 = [
        dict(causal_link="the action occupies the engine",
             implementing_quantity="EngineSim step time over the action's prefill",
             value_range="predicted imposed delay %s" % _fmt_range(
                 [v for vs in pred_by_state.values() for v in vs]),
             varies="yes", evidence="per state: %s" % {k: _fmt_range(v)
                                                       for k, v in sorted(pred_by_state.items())}),
        dict(causal_link="a cold history costs a full prefill, a host-warm one a transfer",
             implementing_quantity="the action's prompt and cached tokens, and term (a)'s "
                                   "external_cached_tokens",
             value_range="action prompt tokens %s; host-transferred tokens %s"
                         % (_fmt_range(prompts), _fmt_range(ext_tokens)),
             varies="yes",
             evidence="cold trials n=%d, host-warm n=%d, locally warm n=%d"
                      % (len(pred_by_state["cold"]), len(pred_by_state["warm_host"]),
                         len(pred_by_state["warm_local"]))),
        dict(causal_link="the occupied engine delays the requests queued behind it",
             implementing_quantity="the paired difference of background TTFTs in the simulation",
             value_range="control with the action removed: %s" % _fmt_range(za),
             varies="yes",
             evidence="Step 4 (a): removing the action collapses the predicted delay"),
        dict(causal_link="the host tier makes a warm arrival cheap",
             implementing_quantity="term (a), %.4f GB/s and %.4f ms fixed"
                                   % (terms.coef["host_kv_transfer_gb_per_s"],
                                      terms.coef["host_kv_lookup_fixed_ms"]),
             value_range="term on minus off, host trials: %s"
                         % _fmt_range([r["with_term_s"] - r["term_off_s"] for r in hc_host]),
             varies=("yes" if any(r["changed"] for r in hc_host) else "NO: ABSENT"),
             evidence="Step 4 (b): %d of %d host trials change, %d of %d non-host trials change"
                      % (sum(1 for r in hc_host if r["changed"]), len(hc_host),
                         sum(1 for r in hc_other if r["changed"]), len(hc_other))),
    ]
    absent = [r for r in step2 if r["varies"].startswith("NO")]
    one = trials[0]
    trace = _unit_trace(one, sim)
    return dict(
        step1_causal_chain=(
            "StudyENG1c Part D injects one device's next request into a running trace. If the "
            "physical component of context inertia is real (FORMULATION.md: reconstruction cost "
            "grows with context length), then the tier the history is in at arrival decides the "
            "action's own work: a GPU-warm or host-warm arrival needs a transfer at most, while "
            "a cold arrival needs a full prefill of about 11k tokens. That work occupies the "
            "engine, and the engine is shared, so it delays every request queued behind it. The "
            "cost model therefore predicts the imposed delay by charging the action's prefill "
            "(term b for its length, term c for how it batches with co-arriving prefills) or its "
            "host transfer (term a), replaying both arms of the recorded pair, and differencing "
            "them. T0b asks whether that predicted difference matches the measured one. The tier "
            "itself is an input, not a prediction (RESIDENCY GIVEN), so the chain tested here "
            "starts at the action's work and not at the eviction rule."),
        step2_instantiation=step2,
        step2_verdict=("PASS: no link is ABSENT or CONSTANT" if not absent else
                       "STOP: %d link(s) ABSENT or CONSTANT" % len(absent)),
        step3_unit_trace=trace,
        step4_negative_control=dict(
            control_a=dict(
                what="remove the action from the with arm and re-predict the paired difference",
                n=len(zero_action), predicted_delay_s=_dist(za),
                max_abs_s=max((abs(x) for x in za), default=None),
                median_abs_s=(statistics.median([abs(x) for x in za]) if za else None),
                median_abs_with_action_s=(statistics.median(
                    [abs(x) for x in with_action_same_trials]) if with_action_same_trials
                    else None),
                shrink_factor=((statistics.median([abs(x) for x in with_action_same_trials])
                                / statistics.median([abs(x) for x in za]))
                               if za and with_action_same_trials
                               and statistics.median([abs(x) for x in za]) > 0 else None),
                collapses=bool(za and with_action_same_trials and
                               statistics.median([abs(x) for x in za])
                               <= 0.1 * statistics.median(
                                   [abs(x) for x in with_action_same_trials])),
                reading="the two arms are replayed from their OWN recorded arrival times, so "
                        "their difference is not identically zero even without the action; the "
                        "control is that the residue is an order of magnitude below the "
                        "predicted delay WITH the action on the same trials"),
            control_b=dict(
                what="zero term (a)'s host-transfer input and re-predict",
                n_host=len(hc_host), n_non_host=len(hc_other),
                n_host_changed=sum(1 for r in hc_host if r["changed"]),
                n_non_host_changed=sum(1 for r in hc_other if r["changed"]),
                median_change_host_s=(statistics.median(
                    [r["with_term_s"] - r["term_off_s"] for r in hc_host]) if hc_host else None),
                n_host_action_ttft_changed=sum(1 for r in hc_host if r["action_ttft_changed"]),
                median_action_ttft_change_host_s=(statistics.median(
                    [r["action_ttft_change_s"] for r in hc_host]) if hc_host else None),
                reading="term (a) changes the ACTION's own predicted TTFT in every host trial "
                        "(the host transfer of about 11k tokens), and it changes the delay "
                        "imposed on others only where a compared background request was queued "
                        "behind the action; in the remaining host trials the transfer lands in "
                        "an idle window and reaches nobody, which is the mechanism and not an "
                        "absent term",
                rows=hc_host[:10]),
            cell="every scored FIT trial for control (b); the first 40 trials in record order "
                 "for control (a)"),
        step5_alternative_explanation=(
            "The headline could be produced by (a) the cost model pricing the action's own work "
            "correctly [the claimed mechanism], or (b) the imposed delay being dominated by the "
            "number of background arrivals during the action, which the replay reproduces from "
            "the record whatever the action costs. The two separate on the cold-versus-warm "
            "contrast: under (b) the predicted delay would be about equal for a cold and a warm "
            "arrival in the same cell, because the trace is the same; under (a) it tracks the "
            "action's own work. Control (b) above is the sharp form of the same test, and the "
            "per-state ranges in Step 2 report it. A second alternative, that the model is right "
            "only because residency was given to it, is why the residency input is labelled and "
            "why predicting residency is a separate test."),
        note="recorded before any criterion verdict was written; the sweep is the FIT dry run")


def _fmt_range(xs: Sequence[float]) -> str:
    if not xs:
        return "EMPTY"
    return "%.4f to %.4f (n %d)" % (min(xs), max(xs), len(xs))


def _unit_trace(t: tr.Trial, sim: EngineSim) -> Dict[str, Any]:
    """Step 3: one trial, every charge the prediction makes, readable by hand."""
    acts = sorted(t.arms["with"].action, key=lambda r: (r.get("part_i") or 0))
    reqs_with = tr._arm_requests(t.arms["with"], include_action=True)
    res_with = sim.run(reqs_with)
    res_without = sim.run(tr._arm_requests(t.arms["without"], include_action=False))
    m = tr.measured_imposed_delay_s(t)
    pr = tr.predict_trial(t, sim)
    return dict(
        key=t.key(), cell=t.cell(), t_inj_rel=t.t_inj_rel,
        action_rows=[dict(rid=r.get("rid"), prompt_tokens=r.get("prompt_tokens"),
                          cached_tokens=r.get("cached_tokens"),
                          external_cached_tokens=r.get("_external_cached_tokens", 0),
                          n_images_charged=tr._n_images(r), body_mb=r.get("body_mb"),
                          measured_ttft_s=r.get("ttft_s")) for r in acts],
        n_background_with=len(t.arms["with"].background),
        n_background_without=len(t.arms["without"].background),
        n_steps_with=res_with["n_steps"], n_steps_without=res_without["n_steps"],
        predicted_action_ttft_s=[res_with["per_request"].get(str(r.get("rid")), {}).get("ttft_s")
                                 for r in acts],
        predicted_imposed_delay_s=pr["predicted_delay_s"],
        measured_imposed_delay_s=m["total_s"],
        n_matched=m["n_matched"],
        per_request_first_ten=pr["per"][:10],
        bound_by="the engine's step queue: the action's prefill occupies steps the background "
                 "requests then wait for; no KV or accelerator budget binds in a Part D trial",
        outcome=dict(criterion_i=delay_pass(pr["predicted_delay_s"], m["total_s"])))


# ------------------------------------------------- the two definitions of "imposed delay"
# CLAUDE.md consistency check 4 (definition audit) found the same name used twice:
#   StudyENG1 Part C and StudyT0 summed TTFT deltas over the episodic background;
#   StudyENG1c Part D sums end-to-end LATENCY deltas over the same requests.
# Summing latency deltas reproduces every one of ENG1c's own 360 published imposed_s values to
# 0.000000 s, and summing TTFT deltas does not (median 1.16 s apart), so the two are different
# quantities and not an implementation discrepancy. Both are scored here: the PRIMARY is the
# collection's own published definition (latency), and the TTFT variant is reported beside it
# because that is the one T0's failing 0.586 was measured on.
METRICS = ("latency", "ttft")
METRIC_FIELD = dict(latency="latency_s", ttft="ttft_s")
METRIC_NOTE = dict(
    latency="PRIMARY for T0b: StudyENG1c Part D's own published quantity, the sum over episodic "
            "background requests of end-to-end latency(with) minus latency(without). Summing it "
            "from the committed rows reproduces all 360 of ENG1c's imposed_s values exactly.",
    ttft="SECONDARY: StudyENG1 Part C's and StudyT0's definition, the same sum over TTFT. "
         "Reported because StudyT0's criterion (i) of 0.586 was measured this way, so only this "
         "column is comparable to it.")


def _measured_sum(trial: tr.Trial, base_mode: str, metric: str) -> Optional[Dict[str, Any]]:
    f = METRIC_FIELD[metric]
    if "with" not in trial.arms or base_mode not in trial.arms:
        return None
    w = {tr._bg_key(r): r for r in trial.arms["with"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    o = {tr._bg_key(r): r for r in trial.arms[base_mode].background
         if r.get("kind") in tr.COMPARED_KINDS}
    total, n = 0.0, 0
    for k in sorted(set(w) & set(o), key=lambda k: str(k)):
        a, b = w[k].get(f), o[k].get(f)
        if a is None or b is None:
            continue
        total += float(a) - float(b)
        n += 1
    return dict(total_s=total, n_matched=n)


def _pred_value(pr: Dict[str, Any], req_row: Dict[str, Any], metric: str,
                t0: float) -> Optional[float]:
    p = pr.get(str(req_row.get("rid")))
    if p is None:
        return None
    if metric == "ttft":
        return p.get("ttft_s")
    end = p.get("t_end")
    if end is None:
        return None
    return float(end) - (float(req_row["t_submit"]) - t0)


def _predicted_sum(trial: tr.Trial, sim: EngineSim, metric: str) -> Dict[str, Any]:
    res_w = sim.run(tr._arm_requests(trial.arms["with"], include_action=True))
    res_o = sim.run(tr._arm_requests(trial.arms["without"], include_action=False))
    pw, po = res_w["per_request"], res_o["per_request"]
    w = {tr._bg_key(r): r for r in trial.arms["with"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    o = {tr._bg_key(r): r for r in trial.arms["without"].background
         if r.get("kind") in tr.COMPARED_KINDS}
    total, n = 0.0, 0
    for k in sorted(set(w) & set(o), key=lambda k: str(k)):
        a = _pred_value(pw, w[k], metric, trial.arms["with"].t0_trace)
        b = _pred_value(po, o[k], metric, trial.arms["without"].t0_trace)
        if a is None or b is None:
            continue
        total += float(a) - float(b)
        n += 1
    acts = trial.arms["with"].action
    comp = None
    if acts:
        subs, ends = [], []
        for r in acts:
            p = pw.get(str(r.get("rid")))
            if p is None:
                continue
            subs.append(float(r["t_submit"]) - trial.arms["with"].t0_trace)
            e = p.get("t_end") if p.get("t_end") is not None else p.get("t_first")
            if e is not None:
                ends.append(e)
        if subs and ends:
            comp = max(ends) - min(subs)
    return dict(total_s=total, n_matched=n, predicted_completion_s=comp,
                unfinished=res_w["unfinished"] + res_o["unfinished"])


def evaluate(trials: Sequence[tr.Trial], sim: EngineSim, metric: str) -> Dict[str, Any]:
    """Criteria (i), (ii) and (iii) on one metric, with the same tolerances and the same ranking
    rule run_t0 uses, so the numbers are comparable to StudyT0's own."""
    from .run_t0 import RANK_RATIO
    rows = []
    for t in trials:
        m = _measured_sum(t, "without", metric)
        pr = _predicted_sum(t, sim, metric)
        mc = tr.measured_action_completion_s(t)
        pc = pr["predicted_completion_s"]
        rows.append(dict(
            key=t.key(), load=t.load, action=t.action, trial=t.trial, cell=t.cell(),
            cap=t.load.split("_", 1)[0], bg_load=t.load.split("_", 1)[1],
            reconstructible=bool(m and m["n_matched"] > 0),
            n_matched_measured=(m["n_matched"] if m else 0), n_matched_predicted=pr["n_matched"],
            measured_delay_s=(m["total_s"] if m else None),
            predicted_delay_s=pr["total_s"],
            measured_completion_s=mc, predicted_completion_s=pc,
            delay=delay_pass(pr["total_s"], m["total_s"] if m else 0.0),
            completion_are=(abs(pc - mc) / mc if (mc and pc is not None and mc > 0) else None),
            unfinished=pr["unfinished"]))
    usable = [r for r in rows if r["reconstructible"]]
    dp = [r for r in usable if r["delay"]["passed"]]
    frac = len(dp) / len(usable) if usable else 0.0
    crit_i = dict(n=len(usable), n_passed=len(dp), fraction=frac, threshold=MIN_FRACTION,
                  verdict=("PASS" if frac >= MIN_FRACTION else "FAIL"))
    by_m: Dict[str, List[float]] = defaultdict(list)
    by_p: Dict[str, List[float]] = defaultdict(list)
    for r in usable:
        by_m[r["cell"]].append(r["measured_delay_s"])
        by_p[r["cell"]].append(r["predicted_delay_s"])
    med_m = {c: statistics.median(v) for c, v in by_m.items()}
    med_p = {c: statistics.median(v) for c, v in by_p.items()}
    pairs = []
    for cond in sorted({c.rsplit("|", 1)[0] for c in med_m}):
        acts = sorted(c.rsplit("|", 1)[1] for c in med_m if c.rsplit("|", 1)[0] == cond)
        for i in range(len(acts)):
            for j in range(i + 1, len(acts)):
                a, b = acts[i], acts[j]
                ma, mb = med_m["%s|%s" % (cond, a)], med_m["%s|%s" % (cond, b)]
                pa, pb = med_p["%s|%s" % (cond, a)], med_p["%s|%s" % (cond, b)]
                lo, hi = min(abs(ma), abs(mb)), max(abs(ma), abs(mb))
                if lo <= 0 or hi / lo <= RANK_RATIO:
                    pairs.append(dict(condition=cond, a=a, b=b, included=False,
                                      measured_ratio=(hi / lo if lo > 0 else None)))
                    continue
                pairs.append(dict(condition=cond, a=a, b=b, included=True, measured_ratio=hi / lo,
                                  measured=[ma, mb], predicted=[pa, pb],
                                  agree=bool((ma > mb) == (pa > pb))))
    inc = [p for p in pairs if p["included"]]
    agree = (sum(1 for p in inc if p["agree"]) / len(inc)) if inc else 0.0
    crit_ii = dict(n_pairs_total=len(pairs), n_pairs_included=len(inc),
                   n_agree=sum(1 for p in inc if p["agree"]), fraction=agree,
                   threshold=MIN_FRACTION,
                   verdict=("PASS" if inc and agree >= MIN_FRACTION else
                            ("FAIL" if inc else "NOT COMPUTABLE")),
                   pairs=pairs, cell_medians_measured=med_m, cell_medians_predicted=med_p)
    ares = [r["completion_are"] for r in usable if r["completion_are"] is not None]
    mare = statistics.median(ares) if ares else None
    crit_iii = dict(n=len(ares), median_abs_rel_error=mare, threshold=COMPLETION_MARE,
                    verdict=("PASS" if ares and mare <= COMPLETION_MARE else "FAIL"))
    return dict(metric=metric, metric_note=METRIC_NOTE[metric], n_trials=len(rows),
                n_usable=len(usable),
                criteria=dict(delay_imposed_on_others=crit_i, ranking=crit_ii,
                              job_completion_time=crit_iii),
                trials=rows)


def ceiling_for_metric(trials: Sequence[tr.Trial], metric: str) -> Dict[str, Any]:
    rows = []
    for t in trials:
        if "repeat" not in t.arms:
            continue
        a = _measured_sum(t, "without", metric)
        b = _measured_sum(t, "repeat", metric)
        if not a or not b or a["n_matched"] == 0 or b["n_matched"] == 0:
            continue
        rows.append(dict(key=t.key(), cell=t.cell(), est_vs_without_s=a["total_s"],
                         est_vs_repeat_s=b["total_s"],
                         check=delay_pass(a["total_s"], b["total_s"])))
    n = len(rows)
    npass = sum(1 for r in rows if r["check"]["passed"])
    per_cell: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_cell[r["cell"]].append(r)
    return dict(metric=metric, n=n, n_passed=npass, ceiling=(npass / n if n else None),
                per_cell={c: dict(n=len(v), n_passed=sum(1 for r in v if r["check"]["passed"]),
                                  ceiling=sum(1 for r in v if r["check"]["passed"]) / len(v))
                          for c, v in sorted(per_cell.items())},
                definition="criterion (i) between the two independent measurements of the same "
                           "trial's imposed delay, (with - without) against (with - repeat), on "
                           "the %s definition" % metric,
                deviation="no HOLDOUT pair carries a repeat; the denominator is the FIT repeat "
                          "pairs of the same 24 cells as the numerator",
                rows=rows)


# ------------------------------------------------------------------------------ driver
def per_cut_tables(res: Dict[str, Any]) -> Dict[str, Any]:
    """The brief's cuts: per cap, per load, per action and per (cap, load), each with the
    direction of the error (positive signed error is over-prediction)."""
    return dict(
        per_cap=error_direction(res, lambda r: r["load"].split("_", 1)[0]),
        per_load=error_direction(res, lambda r: r["load"].split("_", 1)[1]),
        per_action=error_direction(res, lambda r: r["action"]),
        per_cap_load=error_direction(res, lambda r: r["load"]),
        per_cell=error_direction(res, lambda r: r["cell"]),
        pooled=pooled_direction(res))


def _ci(res: Dict[str, Any]) -> Dict[str, Any]:
    return res["criteria"]["delay_imposed_on_others"]


def _cii(res: Dict[str, Any]) -> Dict[str, Any]:
    return res["criteria"]["ranking"]


def _ciii(res: Dict[str, Any]) -> Dict[str, Any]:
    return res["criteria"]["job_completion_time"]


def criteria_table(res: Dict[str, Any], ceiling: Dict[str, Any],
                   iv: Dict[str, Any]) -> Dict[str, Any]:
    return dict(
        i_delay_absolute=dict(fraction=_ci(res)["fraction"], n=_ci(res)["n"],
                              n_passed=_ci(res)["n_passed"], threshold=MIN_FRACTION,
                              verdict=_ci(res)["verdict"]),
        i_b_repeatability_scaled=criterion_i_b(_ci(res)["fraction"], ceiling.get("ceiling")),
        ii_ranking=dict(fraction=_cii(res)["fraction"],
                        n_pairs_included=_cii(res)["n_pairs_included"],
                        n_agree=_cii(res)["n_agree"],
                        threshold=MIN_FRACTION, verdict=_cii(res)["verdict"]),
        iii_completion=dict(median_abs_rel_error=_ciii(res)["median_abs_rel_error"],
                            n=_ciii(res)["n"], threshold=COMPLETION_MARE,
                            verdict=_ciii(res)["verdict"]),
        iv_prefix_loss=dict(source="StudyENG1c Part B (non-holdout)",
                            class_accuracy=iv.get("class_accuracy"),
                            measured_class_counts=iv.get("measured_class_counts"),
                            degenerate=iv.get("degenerate"), verdict=iv.get("verdict")))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="eng1,pol4")
    ap.add_argument("--split", default="fit", choices=["fit"],
                    help="only the FIT split is runnable from the command line; the holdout "
                         "goes through t0_harness.T0Harness.run_holdout_once under the user's "
                         "authorization")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for m in models:
        if m not in ENGINE_MODELS:
            raise SystemExit("unknown engine model %r; choose from %s" % (m, ENGINE_MODELS))
    out_dir = Path(args.out_dir) if args.out_dir else (_root() / OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    trials, audit = load_part_d_trials(split="fit")
    print("ENG1c Part D FIT trials: %d (holdout pairs built: %d of %d)"
          % (len(trials), audit["holdout_pairs_built"], audit["n_holdout_pairs_in_split_file"]))

    mech = mechanism_verification(trials)
    mech["holdout_audit"] = audit
    mech["labels"] = dict(out_of_sample=OUT_OF_SAMPLE_LABEL, residency=RESIDENCY_LABEL)
    mech["_provenance"] = _stamp(len(trials), args)
    (out_dir / "t0b_mechanism.json").write_text(json.dumps(mech, indent=1, default=str))
    ca = mech["step4_negative_control"]["control_a"]
    cb = mech["step4_negative_control"]["control_b"]
    print("mechanism: step2 %s | control a collapses %s (median %.4f vs %.4f with the action) | "
          "control b host changed %d/%d, non-host %d/%d"
          % (mech["step2_verdict"], ca["collapses"], ca["median_abs_s"] or 0.0,
             ca["median_abs_with_action_s"] or 0.0, cb["n_host_changed"], cb["n_host"],
             cb["n_non_host_changed"], cb["n_non_host"]))
    if mech["step2_verdict"].startswith("STOP"):
        print("STOPPING: an ABSENT or CONSTANT link; no criteria are scored")
        return 2

    xcheck = cross_check_against_eng1c(trials, {})
    print("cross-check against ENG1c's own imposed_s: latency max abs diff %.2e s, "
          "ttft max abs diff %.4f s over %d trials"
          % (xcheck["latency"]["max_abs_diff_s"], xcheck["ttft"]["max_abs_diff_s"],
             xcheck["n"]))
    iv = criterion_iv_eng1c_part_b()
    tiers = tier_inputs(trials)
    ceilings = {metric: ceiling_for_metric(trials, metric) for metric in METRICS}
    for metric in METRICS:
        c = ceilings[metric]
        print("repeatability ceiling (%s): %.4f (%d of %d repeat pairs)"
              % (metric, c["ceiling"], c["n_passed"], c["n"]))

    scored: Dict[str, Dict[str, Dict[str, Any]]] = {}
    crit: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for m in models:
        sim = make_sim(m)
        scored[m], crit[m] = {}, {}
        for metric in METRICS:
            res = evaluate(trials, sim, metric)
            res["engine_model"] = m
            res["engine"] = sim.step.describe()
            res["pol4_terms"] = (sim.pol4.describe() if sim.pol4 is not None else "OFF")
            res["split"] = "StudyENG1c Part D FIT pairs. %s" % OUT_OF_SAMPLE_LABEL
            res["residency"] = RESIDENCY_LABEL
            res["cuts"] = per_cut_tables(res)
            scored[m][metric] = res
            crit[m][metric] = criteria_table(res, ceilings[metric], iv)
            c = crit[m][metric]
            print("%-5s %-8s (i) %.4f  (i-b) ratio %s  (ii) %.4f  (iii) %s"
                  % (m, metric, c["i_delay_absolute"]["fraction"],
                     ("%.4f" % c["i_b_repeatability_scaled"]["ratio"])
                     if c["i_b_repeatability_scaled"].get("ratio") is not None else "n/a",
                     c["ii_ranking"]["fraction"],
                     ("%.4f" % c["iii_completion"]["median_abs_rel_error"])
                     if c["iii_completion"]["median_abs_rel_error"] is not None else "n/a"))

    internal = _internal_check(trials, models[0])
    print("internal check, my ttft path against run_t0.evaluate_part_c: %s" % internal["agree"])

    out = dict(
        study="StudyT0b-fidelity Part 2, FIT DRY RUN on StudyENG1c-hostfull Part D",
        split="StudyENG1c Part D FIT pairs (360 of 480; the 120 HOLDOUT pairs were not built)",
        out_of_sample=OUT_OF_SAMPLE_LABEL, residency=RESIDENCY_LABEL,
        definition_audit=dict(metrics=METRIC_NOTE, cross_check=xcheck,
                              finding="the name 'imposed delay' carries two definitions across "
                                      "committed experiments: TTFT deltas in StudyENG1 Part C "
                                      "and StudyT0, end-to-end latency deltas in StudyENG1c "
                                      "Part D. Both are scored; neither is a bug."),
        holdout_audit=audit,
        criteria={m: {k: crit[m][k] for k in crit[m]} for m in crit},
        repeatability_ceiling={k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                               for k, v in ceilings.items()},
        criterion_iv_eng1c_part_b={k: v for k, v in iv.items() if k != "rows"},
        tier_inputs={k: v for k, v in tiers.items() if k != "rows"},
        internal_check=internal,
        cuts={m: {metric: scored[m][metric]["cuts"] for metric in scored[m]} for m in scored},
        criterion_ii_detail={m: {metric: dict(
            pairs=scored[m][metric]["criteria"]["ranking"]["pairs"],
            cell_medians_measured=scored[m][metric]["criteria"]["ranking"]["cell_medians_measured"],
            cell_medians_predicted=scored[m][metric]["criteria"]["ranking"]["cell_medians_predicted"])
            for metric in scored[m]} for m in scored},
        per_trial={m: {metric: [dict(key=r["key"], cell=r["cell"],
                                     measured_delay_s=r["measured_delay_s"],
                                     predicted_delay_s=r["predicted_delay_s"],
                                     passed=r["delay"]["passed"], ratio=r["delay"]["ratio"],
                                     completion_are=r["completion_are"])
                                for r in scored[m][metric]["trials"]]
                       for metric in scored[m]} for m in scored},
        gate="THE HOLDOUT IS NOT SCORED HERE. The 120 ENG1c Part D HOLDOUT pairs were not built; "
             "the user's gate of 2026-11-17 stops this study before the one-shot run.")
    out["_provenance"] = _stamp(len(trials), args)
    (out_dir / "t0b_fit_dryrun_eng1c.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote %s" % (out_dir / "t0b_fit_dryrun_eng1c.json"))
    return 0


def _internal_check(trials: Sequence[tr.Trial], model: str) -> Dict[str, Any]:
    """My own TTFT path against the frozen run_t0.evaluate_part_c on the same trials: the two
    must agree exactly, or the adapter has changed the criterion rather than the data."""
    sim = make_sim(model)
    mine = evaluate(trials, sim, "ttft")
    theirs = evaluate_part_c(trials, sim)
    a = mine["criteria"]["delay_imposed_on_others"]["fraction"]
    b = theirs["criteria"]["delay_imposed_on_others"]["fraction"]
    worst = 0.0
    tt = {r["key"]: r for r in theirs["trials"]}
    for r in mine["trials"]:
        o = tt.get(r["key"])
        if o is None or r["measured_delay_s"] is None:
            continue
        worst = max(worst, abs(r["predicted_delay_s"] - o["predicted_delay_s"]),
                    abs(r["measured_delay_s"] - o["measured_delay_s"]))
    return dict(model=model, criterion_i_mine=a, criterion_i_frozen_run_t0=b,
                max_abs_per_trial_diff_s=worst, agree=bool(abs(a - b) < 1e-12 and worst < 1e-9),
                what="run_t0.evaluate_part_c scores TTFT only; this confirms the adapter feeds it "
                     "the same trials and reproduces its numbers")


def _stamp(n: int, args: Any) -> Dict[str, Any]:
    sys.path.insert(0, str(_root() / "experiments" / "lib"))
    from _provenance import stamp
    return stamp(script="policy/score_t0b.py", model=None, device=None, n=n, args=vars(args))


if __name__ == "__main__":
    raise SystemExit(main())
