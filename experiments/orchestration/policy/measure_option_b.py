#!/usr/bin/env python3
"""StudyLIVE2-perf Option B: the fallback's fidelity, divergence, speed and closed-loop effect.

M-B1 T0 criteria on the fallback, FIT trials only, side by side with the full frozen model.
M-B2 Shadow divergence on the committed fixtures at 8 / 32 / 64 / 128 devices.
M-B3 Speed, closed_form against rollout, Option 0 on, same method as perf_speed_option0.json.
M-B4 Closed-loop effect on the fixtures. FIXTURE REPLAY, NOT A LIVE RESULT.

CPU only, committed fixtures, no GPU and no live run. The fallback is OFF everywhere by default;
this script sets `sh_cost` on its own arm objects and nothing else. NO HOLDOUT IS TOUCHED: M-B1
loads the FIT split only, and the load factor has no fitted parameter so there is nothing to
cross-fit.

M-B2, M-B3 and M-B4 run with mu ESTIMATED (`mu="ewma"`), not at its PLACEHOLDER zero. That is
deliberate and it matters: the pre-registered prediction is about the BACKLOG term, and with
mu = 0 that term is silent in the rollout and in the closed form alike, so a divergence study at
mu = 0 could not see the thing it is about. Spec 13 says no evaluation may run with mu = 0.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ORCH = HERE.parent
ROOT = ORCH.parents[1]
sys.path = [q for q in sys.path if q and Path(q).resolve() != HERE]
for _p in (str(ORCH), str(ORCH / "live2"), str(ORCH / "live2" / "fleet"),
           str(ORCH / "live2" / "scorer"), str(ORCH / "live"), str(ORCH / "baselines"),
           str(ORCH / "sim"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT = ROOT / "results/orchestration/live2/coord/perf"


def _pct(xs: Sequence[float], p: float) -> Optional[float]:
    v = sorted(xs)
    return round(v[min(int(p * len(v)), len(v) - 1)], 9) if v else None


def _dist(xs: Sequence[float]) -> Dict[str, Any]:
    v = sorted(xs)
    if not v:
        return dict(n=0)
    return dict(n=len(v), median=round(statistics.median(v), 9), p10=_pct(v, 0.10),
                p90=_pct(v, 0.90), min=round(v[0], 9), max=round(v[-1], 9))


def _stamp(script: str, n: int, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from _provenance import stamp
    d = stamp(script=script, model="none", device="flash_cpu", n=n, args=None)
    if extra:
        d.update(extra)
    return d


# ---------------------------------------------------------------- the shadow run
def _shadow(n_devices: int, window_s: float, seed: int = 1, h: float = 1.0,
            mu: str = "ewma") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    import fix_checks as FX
    holder: Dict[str, Any] = {}
    real = FX._arm

    def arm(*a, **kw):
        m = real(*a, **kw)
        m.co.sh_cost = "shadow"
        holder["arm"] = m
        return m

    FX._arm = arm
    try:
        res = FX._cell(n_dashcam=n_devices // 2, n_robot=n_devices - n_devices // 2,
                       window_s=window_s, seed=seed, h=h, mu=mu)
    finally:
        FX._arm = real
    return list(holder["arm"].co.sh_shadow), res


def _tercile_edges(xs: Sequence[float]) -> Tuple[float, float]:
    v = sorted(xs)
    if not v:
        return (0.0, 0.0)
    return (v[len(v) // 3], v[2 * len(v) // 3])


def _split(rows: Sequence[Dict[str, Any]], key: str) -> Dict[str, Any]:
    vals = [float(r[key]) for r in rows]
    lo, hi = _tercile_edges(vals)
    buckets: Dict[str, List[Dict[str, Any]]] = {"T1_low": [], "T2_mid": [], "T3_high": []}
    for r in rows:
        v = float(r[key])
        buckets["T1_low" if v <= lo else ("T2_mid" if v <= hi else "T3_high")].append(r)
    return dict(edges=dict(lo=lo, hi=hi),
                buckets={k: _summarise(v) for k, v in buckets.items()})


def _summarise(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return dict(n=0)
    d = [r["delta_j_closed_form"] - r["delta_j_rollout"] for r in rows]
    over = sum(1 for r in rows if r["admit_closed_form"] and not r["admit_rollout"])
    under = sum(1 for r in rows if r["admit_rollout"] and not r["admit_closed_form"])
    exact = sum(1 for x in d if x == 0.0)
    return dict(n=len(rows), n_exact_match=exact,
                exact_match_fraction=round(exact / len(rows), 6),
                sign_disagreements=over + under,
                sign_disagreement_rate=round((over + under) / len(rows), 6),
                over_admissions=over, over_admission_rate=round(over / len(rows), 6),
                under_admissions=under, under_admission_rate=round(under / len(rows), 6),
                admits_closed_form=sum(1 for r in rows if r["admit_closed_form"]),
                admits_rollout=sum(1 for r in rows if r["admit_rollout"]),
                delta_j_difference=_dist(d),
                load_factor=_dist([r["load_factor"] for r in rows]))


def m_b2(sizes: Sequence[int], window_s: float, seed: int, h: float) -> Dict[str, Any]:
    by_size: Dict[str, Any] = {}
    allrows: List[Dict[str, Any]] = []
    for n in sizes:
        rows, res = _shadow(n, window_s, seed, h)
        for r in rows:
            r["_size"] = n
        allrows += rows
        by_size[str(n)] = dict(
            overall=_summarise(rows),
            by_backlog_tercile_queued_tokens=_split(rows, "backlog_queued_tokens"),
            by_backlog_tercile_running_requests=_split(rows, "backlog_running_requests"),
            decision_latency_ms=res.get("decision_latency_ms"),
            mu_seen=sorted({round(float(r["terms"]["mu"]), 6) for r in rows})[:6])
    pooled = _summarise(allrows)
    over_by_size = {k: v["overall"]["over_admission_rate"] for k, v in by_size.items()}
    med_by_terc = {
        k: {b: (v["by_backlog_tercile_queued_tokens"]["buckets"][b]
                .get("delta_j_difference", {}).get("median"))
            for b in ("T1_low", "T2_mid", "T3_high")}
        for k, v in by_size.items()}
    over_by_terc = {
        k: {b: (v["by_backlog_tercile_queued_tokens"]["buckets"][b]
                .get("over_admission_rate"))
            for b in ("T1_low", "T2_mid", "T3_high")}
        for k, v in by_size.items()}
    return dict(check="option_b_m_b2_shadow_divergence", is_measurement=False,
                label="dry-run committed fixtures, mu estimated (ewma); not a live result",
                window_s=window_s, seed=seed, H_s=h, sizes=list(sizes),
                pooled=pooled, by_size=by_size,
                prediction_inputs=dict(over_admission_rate_by_size=over_by_size,
                                       over_admission_rate_by_backlog_tercile=over_by_terc,
                                       delta_j_difference_median_by_backlog_tercile=med_by_terc),
                _provenance=_stamp("measure_option_b.py::m_b2", len(allrows)))


# ---------------------------------------------------------------- M-B3 speed
def m_b3(sizes: Sequence[int], window_s: float, seed: int, h: float) -> Dict[str, Any]:
    import fix_checks as FX
    rows = []
    for n in sizes:
        for mode in ("rollout", "closed_form"):
            holder: Dict[str, Any] = {}
            real = FX._arm

            def arm(*a, **kw):
                m = real(*a, **kw)
                m.co.sh_cost = mode
                holder["arm"] = m
                return m

            FX._arm = arm
            try:
                res = FX._cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=window_s,
                               seed=seed, h=h, mu="ewma")
            finally:
                FX._arm = real
            rows.append(dict(n_devices=n, sh_cost=mode,
                             decision_latency_ms=res.get("decision_latency_ms"),
                             n_decisions=res.get("n_decisions"),
                             n_requests=res.get("n_requests"),
                             cpu_s=res.get("cpu_s"), wall_s=res.get("wall_measured_s"),
                             sh_closed_form_calls=holder["arm"].co.sh_closed_form_calls,
                             scoring_calls=res.get("scoring_calls")))
    return dict(check="option_b_m_b3_speed", is_measurement=False,
                label="dry-run committed fixtures, Option 0 on, mu estimated",
                window_s=window_s, seed=seed, H_s=h, rows=rows,
                _provenance=_stamp("measure_option_b.py::m_b3", len(rows)))


# ---------------------------------------------------------------- M-B4 closed loop
def m_b4(sizes: Sequence[int], window_s: float, seed: int, h: float) -> Dict[str, Any]:
    import fix_checks as FX
    import schema as SC
    rows = []
    for n in sizes:
        per: Dict[str, Any] = {}
        for mode in ("rollout", "closed_form"):
            holder: Dict[str, Any] = {}
            real = FX._arm

            def arm(*a, **kw):
                m = real(*a, **kw)
                m.co.sh_cost = mode
                holder["arm"] = m
                return m

            FX._arm = arm
            try:
                res = FX._cell(n_dashcam=n // 2, n_robot=n - n // 2, window_s=window_s,
                               seed=seed, h=h, mu="ewma")
            finally:
                FX._arm = real
            decs = [json.loads(l) for l in open(res["decision_log"])]
            a = holder["arm"]
            st = dict(a.stats)
            per[mode] = dict(
                n_decisions=res.get("n_decisions"), n_requests=res.get("n_requests"),
                sh_escalated=st.get("sh_escalated"), sh_admitted=st.get("sh_admitted"),
                sh_declined=st.get("sh_declined"),
                released=sum(1 for d in decs if d["kind"] in ("release_monitor",
                                                              "release_recall")),
                kinds={k: sum(1 for d in decs if d["kind"] == k)
                       for k in sorted({d["kind"] for d in decs})},
                n_monitor_answers=res.get("n_monitor_answers"),
                n_recall_answers=res.get("n_recall_answers"),
                n_on_time=res.get("n_on_time"),
                # NO fixture-level J is reported, and the reason is stated rather than a zero
                # printed: a dry run produces no scored J, the decision log carries no per-row
                # delta_j field to sum, and inventing a proxy would be a number with no
                # definition behind it. The closest quantities the fixture DOES define are the
                # on-time count and the admitted / released / answered counts, all above.
                fixture_J=dict(
                    available=False,
                    reason="a dry-run fixture produces no scored J; the scorer needs a measured "
                           "run, and the decision log has no per-decision J to sum",
                    on_time_fraction=(round((res.get("n_on_time") or 0)
                                            / max(res.get("n_requests") or 1, 1), 6))))
        rows.append(dict(n_devices=n, rollout=per["rollout"], closed_form=per["closed_form"],
                         sh_admitted_delta=((per["closed_form"]["sh_admitted"] or 0)
                                            - (per["rollout"]["sh_admitted"] or 0)),
                         released_delta=(per["closed_form"]["released"]
                                         - per["rollout"]["released"]),
                         on_time_delta=((per["closed_form"]["n_on_time"] or 0)
                                        - (per["rollout"]["n_on_time"] or 0))))
    return dict(check="option_b_m_b4_closed_loop", is_measurement=False,
                label="FIXTURE REPLAY, NOT A LIVE RESULT; never a round-1 number",
                window_s=window_s, seed=seed, H_s=h, rows=rows,
                _provenance=_stamp("measure_option_b.py::m_b4", len(rows)))


# ---------------------------------------------------------------- M-B1 T0 on the fallback
def m_b1() -> Dict[str, Any]:
    """Criteria (i) and (ii) on SH-admission imposed delay (TTFT metric), FIT trials only.

    SCOPE, stated because most of T0 does not apply to this fallback. The closed form prices ONE
    quantity: the delay an admission imposes on the requests it overlaps. So criteria (i) and
    (ii) are run on exactly that quantity, with the COMMITTED tolerances and the COMMITTED
    ranking rule (`run_t0.delay_pass`, `run_t0.RANK_RATIO`, `run_t0.MIN_FRACTION`), against the
    same measured trials the full model is scored on. Criteria (iii) and (iv) DO NOT APPLY and
    are reported as such with the reason rather than scored on something they do not describe.
    """
    from policy import score_t0b as S
    from policy import trace_replay as tr
    from policy import eng1d_replay as e1d
    from policy.eng1_engine import make_sim
    from policy.run_t0 import MIN_FRACTION, RANK_RATIO, delay_pass
    from policy.eng1_engine_fast import Eng1Engine, Pol4Terms, StepModel
    from policy.engine import Request

    step = StepModel.load()
    eng = Eng1Engine(step=step, gpu_kv_tokens=62944, host_kv_tokens=1_000_000, profiles=None,
                     pol4=Pol4Terms.load_for_model("pol4"))
    sim = make_sim(engine_model="pol4")

    partc = [t for t in tr.load_part_c_trials() if not t.holdout]
    e1d_trials, e1d_audit = e1d.load_trials("fit")
    assert e1d_audit["split"] == "fit"
    def _action_tokens(t):
        a = (t.arms["with"].action or [None])[0]
        return int(a.get("prompt_tokens") or 0) if a else None

    # THE SCOPE THAT MATTERS, and it is narrow. The fallback is only ever applied to an SH
    # admission: one 378-token single-frame episode call. Every committed trial injects an
    # action of its own size, and the distribution is nothing like that: Part C FIT runs
    # 378 to 13,275 tokens with a median of 11,058, and ENG1d FIT runs 10,925 to 13,273 with
    # NOT ONE trial at or below 600. So the whole-group numbers below score the closed form far
    # outside the regime it is used in, and the SH-SIZED subset is the only comparison that
    # speaks to the fallback as built. All three are reported; the subset is the one to read.
    sh_sized = [t for t in partc if (_action_tokens(t) or 0) <= 600]
    groups = [("ENG1/ENG1c Part C FIT, SH-SIZED ACTIONS ONLY (<= 600 prompt tokens)", sh_sized),
              ("ENG1/ENG1c Part C FIT, all actions (378 to 13,275 tokens; OUT OF SCOPE for the "
               "fallback, reported for completeness)", partc),
              ("ENG1d FIT (every action 10,925 tokens or more; NO SH-SIZED TRIAL EXISTS)",
               list(e1d_trials))]

    out = []
    for name, trials in groups:
        rows = []
        for t in trials:
            m = S._measured_sum(t, "without", "ttft")
            if not m or m["n_matched"] <= 0:
                continue
            pr = S._predicted_sum(t, sim, "ttft")
            # the closed form's own prediction of the SAME quantity: the action's service time,
            # inflated by the frozen step model's occupancy ratio, imposed on each background
            # request the action overlaps
            act = (t.arms["with"].action or [None])[0]
            if act is None:
                continue
            tok = int(act.get("prompt_tokens") or 0)
            cached = int(act.get("cached_tokens") or 0)
            bg = [r for r in t.arms["with"].background if r.get("kind") in tr.COMPARED_KINDS]
            # the action's SERVICE TIME from the frozen engine, which is what the closed form
            # uses: not one step of the step model, which is a fraction of a chunked prefill
            s_a = float(eng.predict(Request(kind="rc_piece", device="d", tokens=tok, frames=0,
                                            readiness=("COLD" if cached == 0 else "HOST-WARM"),
                                            meta=dict(cached_tokens=cached)),
                                    concurrent=0).service_s)
            # occupancy at the moment of injection, for the load factor: the background
            # requests already in service when the action arrives
            t_inj = float(getattr(t, "t_inj_rel", 0.0) or 0.0)
            arr = [float(r.get("arrival_rel") or 0.0) for r in bg]
            r_d = sum(1 for x in arr if t_inj - s_a <= x <= t_inj)
            r_p = sum(1 for x in arr if t_inj - s_a <= x <= t_inj)
            ctx = sum(int(r.get("prompt_tokens") or 0) for r, x in zip(bg, arr)
                      if t_inj - s_a <= x <= t_inj)
            loaded = float(step.step_ms(tok, 0, r_d, r_p, ctx))
            solo = float(step.step_ms(tok, 0, 0, 0, 0))
            lf = (loaded / solo) if solo > 0 else 1.0
            # THE CLOSED FORM'S OWN ANSWER on this quantity: a single serial server, so each
            # background request that arrives while the action holds the server inherits the
            # RESIDUAL of the action's inflated service time, and nothing else is delayed
            shift = lf * s_a
            cf_delay = sum(max(0.0, shift - (x - t_inj)) for x in arr if t_inj < x <= t_inj + shift)
            rows.append(dict(key=t.key(), cell=t.cell(), load=t.load, action=t.action,
                             n_matched=m["n_matched"], measured_delay_s=m["total_s"],
                             full_model_delay_s=pr["total_s"], closed_form_delay_s=cf_delay,
                             load_factor=lf, action_tokens=tok,
                             full_model=delay_pass(pr["total_s"], m["total_s"]),
                             closed_form=delay_pass(cf_delay, m["total_s"])))
        res = dict(group=name, n_trials_scored=len(rows),
                   load_factor=_dist([r["load_factor"] for r in rows]),
                   action_prompt_tokens=_dist([float(r["action_tokens"]) for r in rows]),
                   # is the over-prediction the load factor, or the serial-shift assumption
                   # underneath it? This is the same criterion (i) with LF forced to 1.
                   closed_form_criterion_i_with_lf_1=(lambda rr: dict(
                       n=len(rr), n_passed=sum(1 for x in rr if x["passed"]),
                       fraction=(round(sum(1 for x in rr if x["passed"]) / len(rr), 6)
                                 if rr else None),
                       ratio=_dist([x["ratio"] for x in rr if x["ratio"] is not None])))(
                       [delay_pass(r["closed_form_delay_s"] / r["load_factor"]
                                   if r["load_factor"] else r["closed_form_delay_s"],
                                   r["measured_delay_s"]) for r in rows]))
        for who in ("full_model", "closed_form"):
            ok = [r for r in rows if r[who]["passed"]]
            frac = (len(ok) / len(rows)) if rows else 0.0
            res["%s_criterion_i" % who] = dict(
                n=len(rows), n_passed=len(ok), fraction=round(frac, 6),
                spec_bar=MIN_FRACTION, meets_spec_bar=bool(frac >= MIN_FRACTION),
                ratio=_dist([r[who]["ratio"] for r in rows if r[who]["ratio"] is not None]))
            # criterion (ii): the same pairwise ranking rule, on cell medians
            med_m: Dict[str, List[float]] = {}
            med_x: Dict[str, List[float]] = {}
            for r in rows:
                med_m.setdefault(r["cell"], []).append(r["measured_delay_s"])
                med_x.setdefault(r["cell"], []).append(
                    r["closed_form_delay_s"] if who == "closed_form" else r["full_model_delay_s"])
            mm = {c: statistics.median(v) for c, v in med_m.items()}
            mx = {c: statistics.median(v) for c, v in med_x.items()}
            pairs, inc, agree = [], 0, 0
            for cond in sorted({c.rsplit("|", 1)[0] for c in mm}):
                acts = sorted(c.rsplit("|", 1)[1] for c in mm if c.rsplit("|", 1)[0] == cond)
                for i in range(len(acts)):
                    for j in range(i + 1, len(acts)):
                        a, b = "%s|%s" % (cond, acts[i]), "%s|%s" % (cond, acts[j])
                        ma, mb = mm[a], mm[b]
                        lo, hi = min(abs(ma), abs(mb)), max(abs(ma), abs(mb))
                        if lo <= 0 or hi / lo <= RANK_RATIO:
                            pairs.append(dict(condition=cond, included=False))
                            continue
                        ag = bool((ma > mb) == (mx[a] > mx[b]))
                        inc += 1
                        agree += int(ag)
                        pairs.append(dict(condition=cond, included=True, agree=ag))
            res["%s_criterion_ii" % who] = dict(
                n_pairs_total=len(pairs), n_pairs_included=inc, n_agree=agree,
                fraction=(round(agree / inc, 6) if inc else None), spec_bar=MIN_FRACTION,
                meets_spec_bar=(bool(inc and agree / inc >= MIN_FRACTION) if inc else None))
        out.append(res)
    return dict(
        check="option_b_m_b1_t0_on_the_fallback", is_measurement=False,
        split="FIT ONLY; no HOLDOUT of any study was opened", groups=out,
        criterion_iii_completion_time=dict(
            applies=False,
            reason="the closed form predicts no completion time. It prices the delay an "
                   "admission imposes on overlapping requests and nothing else, so a "
                   "completion-time median relative error would be scoring it on a quantity it "
                   "does not produce."),
        criterion_iv_prefix_loss_class=dict(
            applies=False,
            reason="the closed form omits the KV pool and the A6.2 prefix-risk term outright "
                   "(declared in advance, pre-registration B.4 item 2), so it has no prefix-loss "
                   "class to classify."),
        note="acceptance is not declared here: the numbers are reported against the spec's "
             "pre-registered bars and against the full frozen model, and the decision is the "
             "user's after the H100 pilot",
        _provenance=_stamp("measure_option_b.py::m_b1", sum(g["n_trials_scored"] for g in out)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("m_b1", "m_b2", "m_b3", "m_b4", "all"))
    ap.add_argument("--sizes", default="8,32,64,128")
    ap.add_argument("--window-s", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--h", type=float, default=1.0)
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",")]
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"m_b1": lambda: m_b1(),
            "m_b2": lambda: m_b2(sizes, a.window_s, a.seed, a.h),
            "m_b3": lambda: m_b3(sizes, a.window_s, a.seed, a.h),
            "m_b4": lambda: m_b4(sizes, a.window_s, a.seed, a.h)}
    todo = list(jobs) if a.what == "all" else [a.what]
    for name in todo:
        res = jobs[name]()
        p = OUT / ("perf_optionB_%s.json" % name)
        p.write_text(json.dumps(res, indent=1, default=str) + "\n")
        print("wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
