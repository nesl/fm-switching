#!/usr/bin/env python3
"""D249 UNIT PROOFS: the harm and pricing arithmetic, the unit guard, and the two hazards.

Run:  python3 -I d249_queue_unit_proofs.py [--out FILE]

Every number below is computed from the committed sources (`d162_price`, the cost-model gates,
`cf_objective`, `cf_margin`), never from a literal written here, except where a literal is the
EXPECTED value being checked against.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_cost as CC                                                           # noqa: E402
import cf_margin as CM                                                         # noqa: E402
import cf_objective as CO                                                      # noqa: E402
import d162_price as DP                                                        # noqa: E402
import d249_queue_visibility as QV                                             # noqa: E402

RESULTS: List[Dict[str, Any]] = []


def check(name: str, ok: bool, detail: Any) -> None:
    RESULTS.append({"test": name, "PASS": bool(ok), "detail": detail})


def t_unit_guard() -> None:
    """The guard accepts per_queue_token, refuses per_overlap, and refuses drift."""
    model = CC.load_gate_model()
    got = QV.assert_queue_unit(DP.PER_QUEUE_S, model)
    check("guard accepts the committed per_queue_token",
          got == 0.0001535807289338535,
          {"coefficient_s_per_token": got, "source": DP.SOURCE})

    raised = None
    try:
        QV.assert_queue_unit(float(model["first_token"]["per_overlap"]), model)
    except QV.D249UnitError as e:
        raised = str(e)[:160]
    check("guard REFUSES cf_cost per_overlap in the per-token slot", raised is not None,
          {"per_overlap_s_per_request": float(model["first_token"]["per_overlap"]),
           "raised": raised})

    raised2 = None
    try:
        QV.assert_queue_unit(DP.PER_QUEUE_S * 1.01, model)
    except QV.D249UnitError as e:
        raised2 = str(e)[:120]
    check("guard REFUSES a drifted coefficient", raised2 is not None, {"raised": raised2})

    factor = float(model["first_token"]["per_overlap"]) / DP.PER_QUEUE_S
    check("the measured unit factor is 247.46", abs(factor - 247.4582) < 1e-3,
          {"per_overlap/per_queue_token": factor,
           "what_it_means": ("a token count passed into overlap_ft is wrong by this factor AND "
                             "in the wrong unit; it once predicted 165.6 s against 0.818 s "
                             "observed")})


def t_queue_delay() -> None:
    """`queue_delay_s` is seconds per TOKEN, monotone, and zero at zero."""
    d0 = QV.queue_delay_s(0)
    d15 = QV.queue_delay_s(15)
    d168 = QV.queue_delay_s(168)
    d11586 = QV.queue_delay_s(11586)
    d75634 = QV.queue_delay_s(75634)
    check("zero tokens is zero seconds", d0 == 0.0, {"s": d0})
    check("a touch (15 uncached tokens) costs 2.30 ms", abs(d15 - 0.002303711) < 1e-9,
          {"s": d15, "ms": round(d15 * 1000.0, 4),
           "note": "the mispricing the D245 estimate names: 2.30 ms of harm to others"})
    check("monotone non-decreasing in tokens", d0 <= d15 <= d168 <= d11586 <= d75634,
          {"0": d0, "15": d15, "168_p50_measured": d168,
           "11586_p90_measured": d11586, "75634_max_measured": d75634})
    # what the SAME counts would have produced through the WRONG argument, for the record
    model = CC.load_gate_model()
    po = float(model["first_token"]["per_overlap"])
    check("the wrong unit would be absurd and is unreachable from this path",
          po * 11586 > 400.0,
          {"per_overlap_times_11586_s": round(po * 11586, 1),
           "per_queue_token_times_11586_s": round(d11586, 4),
           "ratio": round((po * 11586) / d11586, 2)})


def t_overlap_stays_zero() -> None:
    """STATIC: every `CC.predict` call in the state planner still passes overlap_ft = 0.

    The hard zero is load-bearing (`study_fix102_prepared.md` section 5.2). This test fails if a
    future edit puts anything but a literal 0 in the third and fourth arguments.
    """
    src = (HERE / "arms_v6state.py").read_text()
    calls: List[str] = []
    for m in re.finditer(r"CC\.predict\(", src):
        i, depth = m.end(), 1
        while i < len(src) and depth:
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        calls.append(" ".join(src[m.end():i - 1].split()))
    bad = [c for c in calls if not re.search(r",\s*0,\s*0\s*$", c.strip())]
    check("all CC.predict calls in arms_v6state keep overlap_ft = overlap_decode = 0",
          not bad, {"n_calls": len(calls), "calls": [c.strip() for c in calls], "bad": bad})


def t_harm_sign_and_rows() -> None:
    """THE HAZARD-2 DIRECTION, measured rather than asserted.

    `harm_warm` DECREASES as a row's own predicted service rises, because a request already
    predicted slow has less `p_on_time` left to lose. So a build that makes the rows' own
    `engine_s` include the queue ahead of them makes HOLD_BACK CHEAPER TO REFUSE and TOUCH MORE
    attractive. A result that reads "the planner now paces against contention" must be checked
    against this table before it is believed.
    """
    res = CC.load_residuals()
    p = lambda eng, slack: CC.p_on_time(res, eng, slack)                       # noqa: E731
    rows_at = {}
    for extra_q in (0, 168, 1108, 11586):
        eng = 1.2535 + QV.queue_delay_s(extra_q)
        row = [{"req_id": "x", "device_id": "dash000", "engine_s": eng, "slack_s": 0.9,
                "p_device_on_time": 1.0, "weight": 1.0}]
        h = CO.harm_warm_from_queue_delay(2000, row, p_on_time=p,
                                          acc_cloud=1.0, acc_device=0.0)
        rows_at[extra_q] = {"row_engine_s": round(eng, 6), "harm": round(h.total, 9),
                            "n_affected": h.n_affected, "delta_t_s": round(h.delta_t_s, 6)}
    harms = [rows_at[k]["harm"] for k in (0, 168, 1108, 11586)]
    check("harm_warm is NON-INCREASING as the queue ahead of the row grows (hazard 2)",
          all(harms[i] >= harms[i + 1] for i in range(len(harms) - 1)),
          {"by_queued_ahead_tokens": rows_at,
           "direction": ("more contention -> LESS harm per row -> HOLD_BACK cheaper to refuse "
                         "-> MORE touching, which D236 measured costing 383 dashcam on-time "
                         "instants")})

    # and the other direction: MORE ROWS is MORE harm, which is what the new source adds
    base = {"req_id": "x", "device_id": "dash000", "engine_s": 1.2535, "slack_s": 0.9,
            "p_device_on_time": 1.0, "weight": 1.0}
    by_n = {}
    for n in (0, 1, 2, 4, 8):
        rs = [dict(base, req_id="r%d" % i) for i in range(n)]
        h = CO.harm_warm_from_queue_delay(2000, rs, p_on_time=p, acc_cloud=1.0, acc_device=0.0)
        by_n[n] = round(h.total, 9)
    check("harm_warm grows with the NUMBER of rows, which is what the new source supplies",
          all(by_n[a] <= by_n[b] for a, b in ((0, 1), (1, 2), (2, 4), (4, 8))),
          {"harm_by_n_rows": by_n,
           "measured_row_counts_in_this_cell": "{0: 2253, 1: 11010, 2: 13736, 3: 14660, 4: 11526, "
                                               "5: 5662, 6: 1777, 7: 228, 8: 13, 9: 37, 10: 18}"})

    # THE CAP IS COUNTED, not silent
    big = CO.harm_warm_from_queue_delay(10 ** 6, [dict(base)], p_on_time=p,
                                        acc_cloud=1.0, acc_device=0.0)
    check("a warm beyond the healthy-regime bound is CAPPED and says so", big.capped,
          {"delta_t_s": big.delta_t_s, "bound_s": CO.HEALTHY_FIRST_TOKEN_BOUND_S})


def t_p_warm_cold_monotone() -> None:
    """The warm/cold pair is non-increasing in queued-ahead tokens, and unchanged at zero."""
    import arms as A                                                           # noqa: PLC0415
    arm = A.make_arm("covex-v6-fair-final-q")
    base = arm._p_warm_cold(8000, 4000, 0)
    rows = {0: base}
    for q in (168, 1108, 11586, 75634):
        rows[q] = arm._p_warm_cold(8000, 4000, q)
    off = A.make_arm("covex-v6-fair-final")._p_warm_cold(8000, 4000)
    check("at zero queued-ahead tokens the pair is EXACTLY the committed rung-3 pair",
          base == off, {"d249_arm_at_zero": base, "rung3": off})
    ws = [rows[q]["warm"] for q in (0, 168, 1108, 11586, 75634)]
    cs = [rows[q]["cold"] for q in (0, 168, 1108, 11586, 75634)]
    check("p(on time) is non-increasing in queued-ahead tokens",
          all(ws[i] >= ws[i + 1] for i in range(len(ws) - 1))
          and all(cs[i] >= cs[i + 1] for i in range(len(cs) - 1)),
          {"by_queued_ahead_tokens": {str(k): {kk: round(vv, 6) for kk, vv in v.items()}
                                      for k, v in rows.items()}})


def t_switch() -> None:
    """The switch is arm-scoped, default off, and a class-level ON raises."""
    import arms as A                                                           # noqa: PLC0415
    off = A.make_arm("covex-v6-fair-final")
    on = A.make_arm("covex-v6-fair-final-q")
    check("default OFF on rung 3", QV.arm_enables(off) is False, {"arm": off.name})
    check("ON on covex-v6-fair-final-q", QV.arm_enables(on) is True, {"arm": on.name})

    class _Bad:
        pass
    setattr(_Bad, QV.D249_SWITCH, True)
    raised = None
    try:
        QV.arm_enables(_Bad())
    except QV.D249SwitchError as e:
        raised = str(e)[:120]
    check("a truthy CLASS attribute RAISES", raised is not None, {"raised": raised})

    # the publisher and the consumer read the SAME attribute on the SAME object
    check("one attribute serves publisher and consumer",
          QV.arm_enables(on) and on._d249_on(),
          {"coordinator_reader": "d249_queue_visibility.arm_enables(arm)",
           "planner_reader": "arms_v6state.V6StateArm._d249_on"})


def t_margin() -> None:
    """D249's "MARGIN_CF (0.6582)" against the two constants in the code.

    NOT RECALIBRATED HERE (the ruling says recalibration comes after the build and its method is
    reported before it is applied). This test records what the planner's bar ALREADY is.
    """
    m_cf = float(CM.MARGIN_CF)
    on_time = CO.attainment_margin(m_cf)
    check("MARGIN_CF is 0.16456 in correctness units", abs(m_cf - 0.16456) < 1e-12, {"v": m_cf})
    check("the planner's bar is already MARGIN_CF_ON_TIME = 0.65824",
          abs(on_time - 0.65824) < 1e-5,
          {"attainment_margin(MARGIN_CF)": on_time,
           "A_D2_DEV": float(getattr(CO, "A_D2_DEV", 0.25)),
           "read_site": ("v5/cf_planner.py::Counterfactual._margin, which wraps "
                         "cf_margin.resolve_margin in cf_objective.attainment_margin, so "
                         "plan_state compares delta against 0.65824 x w_d TODAY"),
           "ruling_reading": ("D249 writes MARGIN_CF (0.6582); 0.6582 is the value of "
                              "MARGIN_CF_ON_TIME and the bar the planner already applies, so "
                              "this build changes NO margin")})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    for fn in (t_unit_guard, t_queue_delay, t_overlap_stays_zero, t_harm_sign_and_rows,
               t_p_warm_cold_monotone, t_switch, t_margin):
        try:
            fn()
        except Exception as e:                                                 # noqa: BLE001
            import traceback
            check(fn.__name__ + " RAISED", False,
                  {"error": repr(e), "tb": traceback.format_exc()[-800:]})
    n = len(RESULTS)
    bad = [r for r in RESULTS if not r["PASS"]]
    out = {"_what": "D249 unit proofs: harm and pricing arithmetic plus the unit guard",
           "n_tests": n, "n_failed": len(bad),
           "VERDICT": "PASS" if not bad else "FAIL: %s" % [r["test"] for r in bad],
           "tests": RESULTS}
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"n_tests": n, "n_failed": len(bad), "VERDICT": out["VERDICT"],
                      "failed": [r["test"] for r in bad]}, indent=1))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
