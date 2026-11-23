#!/usr/bin/env python3
"""Mechanism tests for cf_protect_defer: the switch, the bar, the harm arithmetic, the SIGN.

pytest is not installed in `fmtk`, so this is a plain script with an explicit pass/fail summary
and a NON-ZERO EXIT on failure. It runs no cell and touches no harness: every quantity is driven
to a chosen value, which is the only register in which "a higher w_d defers more" can be checked
as arithmetic rather than hoped for from a log.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_protect_defer as PD                                                  # noqa: E402
import d162_price as DP                                                        # noqa: E402

RESULTS: List[Dict[str, Any]] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    RESULTS.append({"check": name, "pass": bool(ok), "detail": detail})


# A hand-written on-time curve, so every number below can be checked by hand: the answer is on
# time iff the slack covers the predicted service, with a linear ramp over the last second.
def p_lin(engine_s: float, slack_s: float) -> float:
    if slack_s <= engine_s:
        return 0.0
    return min((slack_s - engine_s) / 1.0, 1.0)


def others(n_alert: int = 3, slack: float = 1.0, engine: float = 0.14,
           dev_on_time: float = 1.0) -> List[Dict[str, Any]]:
    return [{"req_id": "a%d" % i, "device_id": "dash%03d" % i, "session_id": None,
             "qtype": "alert", "engine_s": engine, "slack_s": slack,
             "p_device_on_time": dev_on_time} for i in range(n_alert)]


class _Pred:
    """A ServicePrediction stand-in: `cf_cost.latest_safe_start` reads these two fields only."""

    def __init__(self, total_s: float) -> None:
        self.total_s = float(total_s)
        self.total_prefill_only_s = float(total_s)


def t_switch() -> None:
    class Plain:
        pass

    class ClassOn:
        live2_cf_protect_defer = True

    class ClassOff:
        live2_cf_protect_defer = False

    p = Plain()
    check("switch default is False on an arm that declares nothing", PD.arm_enables(p) is False)
    o = Plain()
    setattr(o, PD.SWITCH_ATTR, True)
    check("switch True on the INSTANCE reads True", PD.arm_enables(o) is True)
    raised = False
    try:
        PD.arm_enables(ClassOn())
    except PD.ProtectDeferSwitchError:
        raised = True
    check("a truthy CLASS attribute RAISES", raised)
    check("a False class attribute is allowed through as False",
          PD.arm_enables(ClassOff()) is False)


def t_margin() -> None:
    import cf_margin as CM
    import cf_objective as CO
    check("MARGIN_CF_ON_TIME is derived, not retyped",
          abs(PD.MARGIN_CF_ON_TIME - float(CM.MARGIN_CF) / CO.A_D2_DEV) < 1e-15,
          {"value": PD.MARGIN_CF_ON_TIME, "margin_cf": CM.MARGIN_CF, "a_d2_dev": CO.A_D2_DEV})
    check("MARGIN_CF_ON_TIME rounds to D177 (3)'s 0.6582",
          round(PD.MARGIN_CF_ON_TIME, 4) == 0.6582)
    b = PD.bar(PD.default_w_of, "robo001")
    check("bar at w = 1 is exactly MARGIN_CF_ON_TIME", b["bar"] == PD.MARGIN_CF_ON_TIME, b)


def t_harm_arithmetic() -> None:
    # Three alert instants, each with 1.0 s of slack and 0.14 s of predicted service, so each is
    # on time with p = min((1.0 - 0.14)/1, 1) = 0.86 before the rebuild.
    u = 2048
    dt = DP.PER_QUEUE_S * u                        # 0.0001535807289338535 * 2048
    h = PD.harm_on_time(u, others(3), p_on_time=p_lin)
    expect_dt = 0.0001535807289338535 * 2048
    p_b = p_lin(0.14, 1.0)
    p_a = p_lin(0.14, 1.0 - dt)
    expect = 3.0 * (p_b - p_a)                     # w = 1 on every row
    check("delta first token = PER_QUEUE_S x u, imported not retyped",
          abs(h["delta_first_token_s"] - expect_dt) < 1e-12,
          {"got": h["delta_first_token_s"], "expect": expect_dt,
           "per_queue_s": h["per_queue_s"], "source": h["price_source"]})
    check("harm = sum_j w_j x (p_before - p_after), by hand",
          abs(h["harm"] - expect) < 1e-12,
          {"got": h["harm"], "expect": expect, "p_before": p_b, "p_after": p_a})
    check("harm is in on-time units (cf_objective.ON_TIME_UNITS)", h["on_time_units"] is True)
    check("harm rises with u", PD.harm_on_time(4096, others(3), p_on_time=p_lin)["harm"]
          > h["harm"])
    check("harm rises with the number of others harmed",
          PD.harm_on_time(u, others(6), p_on_time=p_lin)["harm"] > h["harm"])
    # D175 (1): a request that cannot be delivered either way loses nothing.
    h0 = PD.harm_on_time(u, others(3, slack=0.05), p_on_time=p_lin)
    check("a request already past delivering loses nothing (D175 (1))", h0["harm"] == 0.0, h0)
    # The device-discount reading, and what it does to an alert row.
    check("under the device-discounted reading an alert row whose device answer is on time "
          "contributes ZERO harm", h["harm_device_discounted"] == 0.0,
          {"on_time_cloud": h["harm"], "device_discounted": h["harm_device_discounted"]})
    hd = PD.harm_on_time(u, others(3, dev_on_time=0.0), p_on_time=p_lin)
    # 1e-8, not 1e-12: `cf_objective.harm_warm_from_queue_delay` rounds each row's `value_lost`
    # to 9 decimals, and the discounted figure is summed from those rows while `harm` is the
    # unrounded total. The two therefore agree to about 1e-9 and no closer, by construction.
    check("and the same rows with NO device answer lose everything",
          abs(hd["harm_device_discounted"] - hd["harm"]) < 1e-8,
          {"discounted": hd["harm_device_discounted"], "harm": hd["harm"]})


def _decide(w_alert: float, w_recall: float, *, reading: str = "decider",
            u: int = 20000, harm_scale: float = 1.0,
            margin_scale: float = 1.0) -> Dict[str, Any]:
    def w_of(did: str) -> float:
        return w_alert if str(did).startswith("dash") else w_recall
    return PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=True,
                     n_alert_pending=3, u_rebuild=u, free_kv_tokens=5000.0,
                     victim={"session_id": "s9", "device_id": "robo009",
                             "next_question_in_s": 4.0, "warm_tokens": 7000},
                     others=others(3), deadline_abs_s=40.0, pred=_Pred(3.0),
                     chunk_tokens=2048, p_on_time=p_lin, w_of=w_of,
                     w_source="synthetic test weights", bar_reading=reading,
                     harm_scale=harm_scale, margin_scale=margin_scale)


def t_sign() -> None:
    # Pick a harm that sits just above the bar at w = 1, then move each weight separately.
    base = _decide(1.0, 1.0)
    check("the test cell fires at w = 1 (so both directions are observable)",
          base["action"] != "BASE", {"harm": base["harm_value"], "bar": base["bar_value"],
                                     "action": base["action"]})
    hi_alert = _decide(2.0, 1.0)
    check("RULED reading: a lagging ALERT type (w_j up) defers MORE - harm rises, bar fixed",
          hi_alert["harm_value"] > base["harm_value"]
          and hi_alert["bar_value"] == base["bar_value"]
          and hi_alert["action"] != "BASE",
          {"harm": [base["harm_value"], hi_alert["harm_value"]],
           "bar": [base["bar_value"], hi_alert["bar_value"]]})
    # a recall device far behind its own target: the bar rises, so its rebuild is deferred less
    hi_rec = _decide(1.0, 50.0)
    check("RULED reading: a lagging RECALL device (w_R up) defers LESS - bar rises, harm fixed",
          hi_rec["bar_value"] > base["bar_value"]
          and hi_rec["harm_value"] == base["harm_value"]
          and hi_rec["action"] == "BASE",
          {"harm": [base["harm_value"], hi_rec["harm_value"]],
           "bar": [base["bar_value"], hi_rec["bar_value"]], "action": hi_rec["action"]})
    # THE WRONG READING, and what it actually does, which is not what it looks like it would do.
    # Putting the HARMED type's weight on the bar does not reverse the direction: it CANCELS it.
    # Every harm row carries that same weight, so harm and bar scale together and the ratio that
    # decides is unchanged - CLAUDE.md Rule 2's `cancelled by geometry`, which is the shape that
    # yields a believable null rather than a crash, because the counter moves and the decision
    # does not.
    ratio_ruled = [_decide(w, 1.0)["harm_value"] / _decide(w, 1.0)["bar_value"]
                   for w in (1.0, 2.0, 50.0)]
    ratio_wrong = [_decide(w, 1.0, reading="max_harmed")["harm_value"]
                   / _decide(w, 1.0, reading="max_harmed")["bar_value"]
                   for w in (1.0, 2.0, 50.0)]
    check("RULED reading: the harm-to-bar ratio RISES with the harmed type's weight",
          ratio_ruled[0] < ratio_ruled[1] < ratio_ruled[2], ratio_ruled)
    check("WRONG reading (harmed weight on the bar): the ratio is CONSTANT, so the deficit "
          "weight is INERT - cancelled by geometry, not reversed",
          max(ratio_wrong) - min(ratio_wrong) < 1e-9, ratio_wrong)
    # and under the wrong reading the DECIDER's own deficit is ignored entirely, so a lagging
    # recall device loses the protection the ruled bar gives it
    wr_lo = _decide(1.0, 1.0, reading="max_harmed")
    wr_hi = _decide(1.0, 50.0, reading="max_harmed")
    check("WRONG reading: raising the DECIDER's weight changes neither bar nor action, so a "
          "lagging recall device's rebuild is deferred exactly as readily",
          wr_hi["bar_value"] == wr_lo["bar_value"] and wr_hi["action"] == wr_lo["action"],
          {"bar": [wr_lo["bar_value"], wr_hi["bar_value"]],
           "action": [wr_lo["action"], wr_hi["action"]],
           "ruled_for_contrast": [_decide(1.0, 1.0)["action"], _decide(1.0, 50.0)["action"]]})
    check("the bar records WHICH device its weight came from",
          base["bar_detail"]["bar_weight_source"] == "robo001"
          and wr_hi["bar_detail"]["bar_weight_source"].startswith("dash"),
          {"ruled": base["bar_detail"]["bar_weight_source"],
           "wrong": wr_hi["bar_detail"]["bar_weight_source"]})


def t_controls() -> None:
    z = _decide(1.0, 1.0, harm_scale=0.0)
    check("NEGATIVE CONTROL 1: harm forced to zero never defers",
          z["harm_value"] == 0.0 and z["action"] == "BASE", {"gate": z["gate"]})
    big = _decide(1.0, 1.0, margin_scale=1e9)
    check("NEGATIVE CONTROL 2: an enormous bar never defers, and it scales THE BAR ALONE",
          big["action"] == "BASE" and big["bar_value"] > 1e8
          and big["harm_value"] == _decide(1.0, 1.0)["harm_value"],
          {"gate": big["gate"], "bar": big["bar_value"], "harm": big["harm_value"]})
    # THE BROKEN FORM, kept as a check so the cancellation cannot come back unnoticed: scaling the
    # WEIGHT instead scales harm and bar together and the control does not collapse.
    wrong = _decide(1e9, 1e9)
    check("the BROKEN form of control 2 (scaling the weight) does NOT collapse, which is why it "
          "is not the control",
          wrong["action"] != "BASE" and wrong["harm_value"] > 1e8,
          {"action": wrong["action"], "harm": wrong["harm_value"], "bar": wrong["bar_value"]})


def t_gates() -> None:
    g = PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=False,
                  n_alert_pending=0, u_rebuild=20000, free_kv_tokens=0.0,
                  victim={"session_id": "s9", "device_id": "robo009",
                          "next_question_in_s": 4.0, "warm_tokens": 7000},
                  others=others(3), deadline_abs_s=40.0, pred=_Pred(3.0),
                  chunk_tokens=2048, p_on_time=p_lin)
    check("no active alert episode is a gate, before any harm is computed",
          g["action"] == "BASE" and g["gate"] == "no_active_alert_episode" and "harm" not in g)
    f = PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=True,
                  n_alert_pending=3, u_rebuild=100, free_kv_tokens=50000.0,
                  victim={"session_id": "s9", "device_id": "robo009",
                          "next_question_in_s": 4.0, "warm_tokens": 7000},
                  others=others(3), deadline_abs_s=40.0, pred=_Pred(3.0),
                  chunk_tokens=2048, p_on_time=p_lin)
    check("a rebuild that fits the free pool evicts nobody and is a gate",
          f["gate"] == "rebuild_fits_without_evicting")
    nv = PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=True,
                   n_alert_pending=3, u_rebuild=20000, free_kv_tokens=0.0, victim=None,
                   others=others(3), deadline_abs_s=40.0, pred=_Pred(3.0),
                   chunk_tokens=2048, p_on_time=p_lin)
    check("no victim with a question in the horizon is a gate",
          nv["gate"] == "no_victim_with_a_question_in_the_horizon")


def t_latest_safe_start() -> None:
    check("a FITTED kappa was found", PD.KAPPA_INFO["calibrated"] is True,
          {"kappa": PD.KAPPA, "source": PD.KAPPA_INFO["source"]})
    lss = PD.latest_safe_start(10.0, 40.0, _Pred(3.0))
    want = 40.0 - PD.KAPPA * 3.0
    check("latest start = deadline - kappa x predicted service, by hand",
          abs(lss["latest_start_s"] - want) < 1e-6,
          {"got": lss["latest_start_s"], "expect": want, "kappa": PD.KAPPA})
    check("deferral_s = latest start - now", abs(lss["deferral_s"] - (want - 10.0)) < 1e-6)
    # must-start-now: the deadline is one service away, so there is nothing to defer and the
    # compound must take the CHUNK channel instead
    near = PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=True,
                     n_alert_pending=3, u_rebuild=20000, free_kv_tokens=0.0,
                     victim={"session_id": "s9", "device_id": "robo009",
                             "next_question_in_s": 4.0, "warm_tokens": 7000},
                     others=others(3), deadline_abs_s=10.5, pred=_Pred(3.0),
                     chunk_tokens=2048, p_on_time=p_lin)
    check("when the latest safe start has passed the compound SENDS LESS instead of deferring",
          near["action"] == "PROTECT_AND_CHUNK"
          and near["chunk_tokens"] in PD.SLICE_LADDER
          and near["chunk_tokens"] < 20000,
          {"action": near["action"], "gate": near["gate"],
           "chunk_tokens": near.get("chunk_tokens"), "ladder": near.get("slice_ladder_tried")})
    check("the slice chosen is the LARGEST rung whose harm is at or below the bar, so its size "
          "is a consequence of the bar and not a knob",
          near["harm_if_chunked"]["harm"] <= near["bar_value"]
          and near["harm_if_chunked"]["harm"] < near["harm"]["harm"]
          and all(r["harm"] > near["bar_value"]
                  for r in near["slice_ladder_tried"][:-1]),
          {"chunked": near["harm_if_chunked"]["harm"], "whole": near["harm"]["harm"],
           "bar": near["bar_value"], "ladder": near["slice_ladder_tried"]})


def t_request_has_no_slice_channel() -> None:
    req = PD.decide(decider_device_id="robo001", now_s=10.0, alert_active=True,
                    n_alert_pending=3, u_rebuild=20000, free_kv_tokens=0.0,
                    victim={"session_id": "s9", "device_id": "robo009",
                            "next_question_in_s": 4.0, "warm_tokens": 7000},
                    others=others(3), deadline_abs_s=10.5, pred=_Pred(3.0),
                    chunk_tokens=None, p_on_time=p_lin)
    check("a REQUEST leg (chunk_tokens None) past its latest safe start is UNEXPRESSIBLE, never "
          "a silent chunk: a query is one prompt",
          req["action"] == "BASE"
          and req["gate"].startswith("wanted_to_act_but_a_request_has_no_slice_channel"),
          {"action": req["action"], "gate": req["gate"], "crosses_bar": req["crosses_bar"]})
    check("and it still records that it crossed the bar, so the loss is counted and not hidden",
          req["crosses_bar"] is True and req["harm_value"] > req["bar_value"],
          {"harm": req["harm_value"], "bar": req["bar_value"]})


def t_trace() -> None:
    d = _decide(1.0, 1.0)
    lines = PD.trace_lines(d)
    check("the trace is produced and names every term",
          all(any(k in ln for ln in lines) for k in
              ("HARM =", "BAR =", "TEST: harm", "LATEST SAFE START", "ACTION:")),
          {"n_lines": len(lines)})
    return lines


def main() -> int:
    t_switch()
    t_margin()
    t_harm_arithmetic()
    t_sign()
    t_controls()
    t_gates()
    t_latest_safe_start()
    t_request_has_no_slice_channel()
    lines = t_trace()
    n_bad = sum(1 for r in RESULTS if not r["pass"])
    print("\n".join(lines))
    print()
    for r in RESULTS:
        print("%s  %s" % ("PASS" if r["pass"] else "FAIL", r["check"]))
        if not r["pass"]:
            print("      detail: %s" % json.dumps(r["detail"], default=str))
    print("\n%d checks, %d passed, %d FAILED" % (len(RESULTS), len(RESULTS) - n_bad, n_bad))
    sys.path.insert(0, str(HERE.parents[2] / "experiments/lib"))
    try:
        from _provenance import stamp
        prov = stamp(script="cf_pd_tests.py", model="n/a (unit arithmetic, CPU)", device="flash")
    except Exception as exc:                                                   # noqa: BLE001
        prov = {"git_commit": "unavailable", "why": str(exc)}
    out = HERE.parents[2] / "results/orchestration/live2/frozen_test/cf_pd_mechanism_tests.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_what": "cf_protect_defer mechanism tests: switch, bar, harm arithmetic, the SIGN, the "
                 "two negative controls, the gates, the latest safe start",
        "_register": "unit arithmetic on driven inputs; NO cell, NO harness, NO engine",
        "all_pass": n_bad == 0, "n_checks": len(RESULTS), "n_failed": n_bad,
        "checks": RESULTS, "traced_decision": lines,
        "mechanism": PD.as_dict(), "_provenance": prov}, indent=1, default=str))
    print("wrote %s" % out)
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
