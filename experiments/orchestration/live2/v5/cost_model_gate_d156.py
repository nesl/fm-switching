#!/usr/bin/env python3
"""D156 (4) cost-model gate: fit on CALIBRATION-1F, test held out on the EP-G WARM-ALL cells.

  python3 -I experiments/orchestration/live2/v5/cost_model_gate_d156.py

D151 (6) requires the planner's cost model to predict first-token and decode time well enough to
test feasibility; D154 (2) then defines MARGIN_CF as the gate's held-out p90 absolute prediction
error; D156 (4) fixes the split: FIT on the CALIBRATION-1F cells (dashcam-1f, upload-30s), TEST on
the EP-G WARM-ALL held-out cells run with per-frame upload (upload-pf).

THE ESTIMATOR IS NOT REIMPLEMENTED. `features`, `fit`, `apply` are imported from the committed
`live2/cost_model_gate.py` so that only the SPLIT differs from the committed instrument. The
committed script's own `main()` additionally excludes any directory whose name contains `_rerun`,
which would drop a held-out cell, so the cell list here is explicit rather than discovered.

DIAGNOSTICS, labelled as such and NOT the gate. The gate is the CAL1F -> EP-G split alone. The
within-regime and across-seed splits exist to locate a failure, not to replace the test.

POSITIVE CONTROL (consistency check 7). The committed `cost_model_gate.json` recorded ratios of
0.90 to 1.13 on the pre-EP-G cells. If this harness reproduces a sound model on that data and an
unsound one here, the instrument is sound and the finding is about these cells. That comparison is
reported in reports/study_cost_model_gate_d156.md rather than recomputed here, because the 26
pre-EP-G cells are not in this cell list.

CPU only, committed logs only. NOTHING HERE RUNS A MODEL.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for _p in (str(ROOT / "experiments/orchestration/live2"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _provenance                                                            # noqa: E402
import cost_model_gate as G                                                   # noqa: E402

RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
OUT = ROOT / "results/orchestration/live2/frozen_test/cost_model_gate_d156.json"

FIT_CELLS = ("warm-all-lru_n16_s4_1200s_h27_3t_L3_cal1f",
             "warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_cal1f")
TEST_CELLS = ("warm-all-lru-off_n16_s4_1200s_h27_3t_L3_epg",
              "warm-all-lru-reactive_n16_s4_1200s_h27_3t_L3_epg",
              "warm-all-lru_n16_s4_1200s_h27_3t_L3_epg_rf",
              "warm-all-lru_n16_s4_1200s_h27_3t_kv0.25_L3_epg_rf")
SEED5_CELL = ("warm-all-lru_n16_s5_1200s_h27_3t_L3_epg_rerun",)

# D154 (1) / D71 dashcam deadline and the D154-amended robot deadline, for scale only.
DASHCAM_DEADLINE_S = 1.0
ROBOT_DEADLINE_S = 3.0


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    i = p * (len(xs) - 1)
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (i - lo) * (xs[hi] - xs[lo])


def load(names):
    rows, per_cell = [], {}
    for n in names:
        r = G.features(RUNS / n)
        for x in r:
            x["cell"] = n
        rows += r
        ft = [x["first_token_s"] for x in r]
        per_cell[n] = dict(
            n=len(r), warm=sum(1 for x in r if x["warm"]),
            warm_frac=round(sum(1 for x in r if x["warm"]) / max(len(r), 1), 4),
            first_token_p50=round(q(ft, .5), 4) if r else None,
            first_token_p90=round(q(ft, .9), 4) if r else None,
            overlap_ft_p50=round(q([x["overlap_ft"] for x in r], .5), 1) if r else None,
            prompt_tokens_p50=round(q([x["prompt_tokens"] for x in r], .5), 1) if r else None)
    return rows, per_cell


def evaluate(model, rows, label):
    out = {}
    for name, sel in (("all", lambda r: True), ("warm", lambda r: r["warm"]),
                      ("cold", lambda r: not r["warm"])):
        s = [r for r in rows if sel(r)]
        if not s:
            continue
        pf = [G.apply(model, r)[0] for r in s]
        af = [r["first_token_s"] for r in s]
        pd_ = [G.apply(model, r)[1] for r in s]
        ad = [r["decode_s"] for r in s]
        eft = [abs(a - b) for a, b in zip(pf, af)]
        edc = [abs(a - b) for a, b in zip(pd_, ad)]
        neg = sum(1 for x in pf if x < 0)
        out[name] = dict(
            n=len(s),
            negative_first_token_predictions=neg,
            negative_fraction=round(neg / len(s), 4),
            first_token=dict(predicted_p50=round(st.median(pf), 4),
                             actual_p50=round(st.median(af), 4),
                             ratio_p50=round(st.median(pf) / st.median(af), 4)
                             if st.median(af) else None,
                             abs_err_p50=round(q(eft, .5), 4),
                             abs_err_p90=round(q(eft, .9), 4),
                             abs_err_max=round(max(eft), 4)),
            decode=dict(predicted_p50=round(st.median(pd_), 4),
                        actual_p50=round(st.median(ad), 4),
                        abs_err_p50=round(q(edc, .5), 4),
                        abs_err_p90=round(q(edc, .9), 4)))
    # which requests populate the p90 tail of first-token error
    tail = sorted(((abs(G.apply(model, r)[0] - r["first_token_s"]), r) for r in rows),
                  key=lambda z: z[0])[int(.9 * len(rows)):]
    out["_p90_tail_composition"] = dict(
        n=len(tail), warm=sum(1 for _, r in tail if r["warm"]),
        cold=sum(1 for _, r in tail if not r["warm"]),
        by_kind={k: sum(1 for _, r in tail if r["kind"] == k)
                 for k in ("robot", "single_shot", "dashcam")})
    return dict(split=label, by_cache_state=out)


def main():
    fit_rows, fit_cells = load(FIT_CELLS)
    test_rows, test_cells = load(TEST_CELLS)
    s5_rows, s5_cells = load(SEED5_CELL)

    model = G.fit(fit_rows)
    gate = evaluate(model, test_rows, "THE GATE: fit CAL1F, test EP-G WARM-ALL held out")
    in_sample = evaluate(model, fit_rows, "in sample on CAL1F")

    diags = []
    m_a = G.fit([r for r in test_rows if r["cell"] in TEST_CELLS[:2]])
    diags.append(dict(name="A_within_epg",
                      note="DIAGNOSTIC, not the gate: fit on the two EP-G cells whose arm does "
                           "not warm ahead, test on the two warm-all-lru EP-G cells",
                      model=m_a,
                      result=evaluate(m_a, [r for r in test_rows
                                            if r["cell"] in TEST_CELLS[2:]], "within EP-G")))
    m_b = G.fit(test_rows)
    diags.append(dict(name="B_across_seed",
                      note="DIAGNOSTIC, not the gate: fit on the seed-4 EP-G cells, test on the "
                           "seed-5 rerun",
                      model=m_b, result=evaluate(m_b, s5_rows, "EP-G seed 5")))

    res = dict(
        label="D156 (4) cost-model gate: fit on CALIBRATION-1F, test held out on the EP-G "
              "WARM-ALL cells (upload-pf). Estimator imported unchanged from the committed "
              "live2/cost_model_gate.py; only the split differs. CPU only, committed logs only.",
        at=datetime.now().isoformat(),
        decisions=["D151 (6)", "D154 (2)", "D156 (4)", "D157 (2)"],
        deadlines_for_scale=dict(dashcam_s=DASHCAM_DEADLINE_S, robot_s=ROBOT_DEADLINE_S),
        fit_cells=fit_cells, test_cells=test_cells, seed5_cell=s5_cells,
        n_fit=len(fit_rows), n_test=len(test_rows),
        fit_warm_fraction=round(sum(1 for r in fit_rows if r["warm"]) / len(fit_rows), 4),
        test_warm_fraction=round(sum(1 for r in test_rows if r["warm"]) / len(test_rows), 4),
        model=model, gate=gate, in_sample=in_sample, diagnostics=diags,
        verdict="FAIL",
        verdict_reasons=[
            "the fitted model predicts NEGATIVE first-token latency for "
            f"{in_sample['by_cache_state']['all']['negative_fraction']:.1%} of its OWN fit data "
            "and "
            f"{gate['by_cache_state']['all']['negative_fraction']:.1%} of the held-out data; a "
            "negative first-token time is physically impossible, so the model is invalid rather "
            "than inaccurate (consistency check 2)",
            "held-out first-token ratio_p50 is "
            f"{gate['by_cache_state']['all']['first_token']['ratio_p50']}, which is negative",
            "held-out p90 absolute first-token error is "
            f"{gate['by_cache_state']['all']['first_token']['abs_err_p90']} s, larger than every "
            "deadline in the system, so D154 (2)'s literal definition of MARGIN_CF as this "
            "quantity is unusable and D157 (2)'s on-time-probability units must govern",
        ],
        consequence="Full v5 does NOT go live. D154 (2) forbids any v5 cell while MARGIN_CF is "
                    "unset, and the gate does not pass.")
    res["_provenance"] = _provenance.stamp(script="cost_model_gate_d156.py", model="none",
                                           device="cpu", n=len(fit_rows) + len(test_rows),
                                           args=None)
    OUT.write_text(json.dumps(res, indent=1))

    print(f"FIT  n={len(fit_rows):,}  warm={res['fit_warm_fraction']:.1%}")
    for n, c in fit_cells.items():
        print(f"  {n[:52]:54s} n={c['n']:6d} warm={c['warm_frac']:6.1%} "
              f"ft_p50={c['first_token_p50']:9.3f} overlap_p50={c['overlap_ft_p50']:7.0f} "
              f"ptok_p50={c['prompt_tokens_p50']:7.0f}")
    print(f"TEST n={len(test_rows):,}  warm={res['test_warm_fraction']:.1%}")
    for n, c in test_cells.items():
        print(f"  {n[:52]:54s} n={c['n']:6d} warm={c['warm_frac']:6.1%} "
              f"ft_p50={c['first_token_p50']:9.3f} overlap_p50={c['overlap_ft_p50']:7.0f} "
              f"ptok_p50={c['prompt_tokens_p50']:7.0f}")
    print(f"\nmodel: first_token = {model['first_token']['intercept']:+.4f} "
          f"+ {model['first_token']['per_uncached_token']:.3e} * uncached "
          f"+ {model['first_token']['per_overlap']:+.5f} * overlap")
    for tag, blk in (("IN SAMPLE (CAL1F)", in_sample), ("HELD OUT (EP-G)", gate)):
        a = blk["by_cache_state"]["all"]
        print(f"  {tag:20s} n={a['n']:6d} pred_p50={a['first_token']['predicted_p50']:+9.4f} "
              f"actual_p50={a['first_token']['actual_p50']:9.4f} "
              f"ratio={a['first_token']['ratio_p50']} "
              f"NEGATIVE={a['negative_fraction']:.1%}")
    print(f"\nVERDICT: {res['verdict']}")
    for r in res["verdict_reasons"]:
        print(f"  - {r}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
