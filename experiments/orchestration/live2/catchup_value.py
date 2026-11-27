#!/usr/bin/env python3
"""VALUE GATE FOR CATCH-UP PREFILL (group C S2; switch `live2_catchup_prefill_value`, arm
`covex-v6-fair-final-cand-tl-sync`). DEV BUILD, DEFAULT OFF on every arm. User ruling D327/D328.

WHAT IT REPLACES. The paced and busy-x gates of the catch-up family (`catchup_prefill`: the JIT
horizon, the ask credit, the C5 cap, the C2 epoch row, and the busy-x single-shot / dashcam /
global-window tests) are NOT applied in this mode. In their place a robot's catch-up slice is
RELEASED only when its NET VALUE is positive:

    gain = w_dev x N_exp x (p_on(warm) - p_on(cold)) x (ACC_QF - ACC_DEVICE)
    harm = (the harm B's own load-aware estimator prices for the requests the catch-up sits in
            front of) converted to the same units
    release iff gain - harm > 0              ("ours" form, link_sync._release: net > 0, ties by
                                              next-question time; order is (-net, next_q, sid))

GAIN (every quantity committed; none introduced).
  w_dev   the live deficit weight (`arm._cup_w_of`, `arms_v6cfr3._weight_of`, floored at 1.0).
  N_exp   `future_horizon.expected_questions(HORIZON_WARM_CAP_S, the rules arm's gap EWMA)`: the
          SAME function step 3's FUTURE calls (cf_forfeit re-exports it), so sync and the
          counterfactual agree on a robot's future.
  p_on    `cf_cost.p_on_time(residuals, engine_s, slack)` with `engine_s` from `cf_cost.predict` and
          slack = the 3 s robot deadline (arms_v6state.ROBOT_DEADLINE_S, D147): cold = the next
          question finds the session's unbuilt tail as uncached tokens; warm = it finds none.
  ACC_QF - ACC_DEVICE   oracle_fair_table.json `recall|cloud|WITH_HISTORY` (0.568799) minus
          `recall|device|NA` (0.257732) = 0.311067 (link_sync.ACC_QF / ACC_DEVICE). A late cloud
          answer falls back to the device answer, so the value of an on-time cloud answer is the
          cloud-over-device gap, the FAIR valuation the oracle and B's margin use.

HARM. B's load-aware first-token estimator `la_arrival_admission.loadaware_est(u, queued)` =
`d162_price.first_token_s` (INTERCEPT_S + PER_UNCACHED_S u + PER_QUEUE_S queued_ahead, d162_price.py:90):
  - the added work is the session's unbuilt tail `u` tokens (what completing the catch-up adds
    ahead of the other requests);
  - the queue ahead is `la_arrival_admission.queued_ahead(obs)` (in-flight uncached tokens, the
    register B itself reads); `d249_queue_visibility` is NOT set: est_loadaware replaces it;
  - PENDING AND IN-FLIGHT harm: the requests already queued (the recall rows `_queued_behind`
    returns with the d249 flag off, plus the in-flight deadline rows `_d249_rows(force=True)`), each
    priced by `cf_protect_defer.harm_on_time` -> `cf_objective.harm_warm_from_queue_delay` (the
    committed D162 queued-ahead delay on each row's own P(on time));
  - EXPECTED-ARRIVAL harm: the questions EXPECTED TO ARRIVE while the work is served, per other
    device (robot and single-shot; the dashcam is priced through its in-flight rows only, because no
    dashcam arrival row exists), over the window `future_horizon.arrival_window` = min(est_loadaware,
    HORIZON_WARM_CAP_S): the queue wait is counted ONCE (est_loadaware already sums it with the
    service time, the D328 addendum), at each device's gap-EWMA rate (the same rate N_exp uses).
UNITS. `harm_on_time` returns D177 on-time answers (sum_j w_j x (p_before - p_after)). The gain
above is in accuracy units, so each harmed row's on-time loss is converted by ITS OWN type's
cloud-over-device gap, the same logic as the gain: recall rows by ACC_QF - ACC_DEVICE;
single-shot rows by `single_shot|cloud|COLD` minus `single_shot|device|NA` (oracle_fair_table.json,
0.621881 - 0.547985 = 0.073896); DASHCAM (`alert`) rows contribute NO harm term (D330 item 3: no
committed accuracy gap exists, no uncommitted unit is used; dashcam stays with C5). Both
nets (accuracy units, on-time units) are recorded on every row; the gate reads the accuracy one.

S1 (reduced to what S2 needs): the per-session pending backlog tokens (window backlog minus the part
that has arrived) and the offline window (`back_online_at - offline_since`) are recorded on each
decision row; the gate itself reads the unbuilt tail.

READ SITE: `catchup_prefill.candidates` (value branch) and `catchup_prefill.order`. The decision it
changes is the MATERIALIZE list, as for the rest of the family.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

VALUE_VERSION = "catchup-value-1.1"
VLOG_CAP = 4000


def _gaps() -> Dict[str, float]:
    import link_sync as LS
    ss_c, _n1, _k1 = LS._oracle("single_shot|cloud|COLD")
    ss_d, _n2, _k2 = LS._oracle("single_shot|device|NA")
    return {"recall": float(LS.ACC_QF) - float(LS.ACC_DEVICE),
            "assistance": float(ss_c) - float(ss_d)}


def observe_questions(arm: Any, obs: Any, roster: Dict[str, Any]) -> None:
    """Per device, the last question seen (its session, prompt tokens, deadline duration, type): what
    an EXPECTED arrival of that device would look like. Read-only bookkeeping, as step 3's
    `_cf3_observe`; runs only when the value mode is on."""
    cu = arm._cu_state
    sdev = roster.get("session_device") or {}
    ss_types = getattr(arm, "_ss_types", None) or frozenset()
    for qy in (getattr(obs, "recall", None) or ()):
        did = sdev.get(str(qy.session_id))
        if did is None:
            continue
        cu.lastq[str(did)] = {
            "session_id": str(qy.session_id), "tokens": int(qy.readiness_tokens),
            "slack_s": float(qy.deadline_s) - float(qy.arrival_s),
            "qtype": ("assistance" if str(getattr(qy, "category", "")) in ss_types else "recall")}


def _others(outer: Any, arm: Any, obs: Any, sid: str, did: str, roster: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The requests the catch-up would sit in front of: pending recall rows and in-flight deadline
    rows, own device excluded, each with its type. DASHCAM (`alert`) rows are EXCLUDED (D330 item 3):
    they contribute no harm term and stay with C5, as in step 3's HARM (`_cf3_admit` keeps only
    qtype recall/assistance)."""
    devs = roster.get("devices") or {}
    sdev = roster.get("session_device") or {}
    rows: List[Dict[str, Any]] = []
    have = set()
    for r in outer._queued_behind(obs, sid, True):
        d2 = str(r.get("device_id", ""))
        if d2 == str(did):
            continue
        t = "recall" if str((devs.get(d2) or {}).get("type")) == "robot" else "assistance"
        rows.append(dict(r, qtype=t))
        have.add(str(r.get("req_id")))
    for r in outer._d249_rows(obs, sid, force=True):
        if str(r.get("req_id")) in have or str(r.get("device_id")) == str(did):
            continue
        t = str(r.get("d249_qtype") or "")
        t = {"assistance": "assistance", "alert": "alert", "recall": "recall"}.get(
            t, "recall" if str((devs.get(str(r.get("device_id")), {}) or {}).get("type")) == "robot" else "assistance")
        if t == "alert":
            continue
        rows.append(dict(r, qtype=t))
    return rows


def evaluate(arm: Any, obs: Any, roster: Dict[str, Any], sid: str, did: str, tail: int,
             win: Tuple[int, int, str], est_now: int) -> Dict[str, Any]:
    """The net value of releasing a catch-up slice for session `sid` now. Never raises: any failure
    is a counted HOLD (a catch-up that cannot be priced is not released)."""
    import cf_cost as CC
    import cf_protect_defer as PD
    import d162_price as DP
    import future_horizon as FH
    import la_arrival_admission as LAA
    import link_sync as LS
    import arms_v6state as V6S
    cu = arm._cu_state
    outer = arm._cu_outer
    out: Dict[str, Any] = {"sid": sid, "device_id": did, "tail": int(tail), "release": False,
                           "gate": None, "version": VALUE_VERSION}
    gap = (getattr(arm, "_gap_ewma", None) or {}).get(did)
    n_exp = FH.expected_questions(float(CC.HORIZON_WARM_CAP_S), gap)
    if n_exp is None:
        out["gate"] = "no_question_estimate"
        return out
    cf = outer._cf_engine()
    res = cf.residuals
    p_on = (lambda e, s: float(CC.p_on_time(res, e, s)))
    w_of = arm._cup_w_of
    w = float(w_of(did))
    fut = FH.forfeited_future(
        w_r=w, u_cold=int(tail), u_warm=0, slack_next_s=float(V6S.ROBOT_DEADLINE_S),
        p_on_time=p_on, engine_s_of=lambda n: float(CC.predict(cf.model, int(n), 0, 0, 0).engine_s),
        n_expected=float(n_exp))
    g_robot = float(LS.ACC_QF) - float(LS.ACC_DEVICE)
    gain_ot = float(fut["future_gain"])
    gain_acc = gain_ot * g_robot
    # ---- harm: B's own estimator, over the window est_loadaware itself defines -----------------
    u = int(tail)
    ahead = int(LAA.queued_ahead(obs))
    service = float(DP.first_token_s(u, 0))
    est_la = float(LAA.loadaware_est(u, ahead))
    wait = est_la - service
    window = FH.arrival_window(service_s=service, wait_s=wait, cap_s=float(CC.HORIZON_WARM_CAP_S),
                               mode="queue_service")
    others = _others(outer, arm, obs, sid, did, roster)
    h_pend = PD.harm_on_time(u, others, p_on_time=p_on, w_of=w_of)
    builtmap = roster.get("built_tokens_by_session") or {}
    devs_arr = []
    for d2, info in cu.lastq.items():
        if d2 == str(did):
            continue
        devs_arr.append({"device_id": d2, "qtype": info["qtype"],
                         "gap_s": (getattr(arm, "_gap_ewma", None) or {}).get(d2),
                         "u_tokens": max(int(info["tokens"]) - int(builtmap.get(info["session_id"], 0) or 0), 0),
                         "slack_s": info["slack_s"]})
    ar = FH.arrival_rows(devs_arr, ahead_tokens=ahead, window_s=window, est_of=LAA.loadaware_est)
    h_arr = PD.harm_on_time(u, ar["rows"], p_on_time=p_on,
                            w_of=lambda dv: float(w_of(dv)) * float(ar["n_by_dev"].get(str(dv), 0.0)))
    gaps = _gaps()
    by_type: Dict[str, float] = {}
    for hh in (h_pend, h_arr):
        for t, v in (hh.get("harm_by_type") or {}).items():
            by_type[t] = by_type.get(t, 0.0) + float(v)
    harm_ot = float(h_pend["harm"]) + float(h_arr["harm"])
    harm_acc = 0.0
    for t, v in by_type.items():
        harm_acc += float(v) * float(gaps[t])
    net_acc = gain_acc - harm_acc
    net_ot = gain_ot - harm_ot
    lk = (cu.link.get(sid) or {})
    out.update({
        "w": w, "n_expected": float(n_exp), "p_on_cold": fut["p_on_cold"], "p_on_warm": fut["p_on_warm"],
        "gain_ot": gain_ot, "gain_acc": gain_acc, "harm_ot": harm_ot, "harm_acc": harm_acc,
        "harm_pending_ot": float(h_pend["harm"]), "harm_arrival_ot": float(h_arr["harm"]),
        "harm_by_type_ot": {k: round(v, 9) for k, v in sorted(by_type.items())},
        "window_s": float(window), "service_s": service, "est_loadaware_s": est_la,
        "queue_wait_s": wait, "queued_ahead": ahead, "n_other_rows": len(others),
        "n_arrival_rows": len(ar["rows"]), "n_expected_arrivals": float(ar["n_expected_total"]),
        "net_acc": net_acc, "net_ot": net_ot,
        "pending_backlog_tokens": int(max(int(win[1]) - max(int(est_now) - int(win[0]), 0), 0)),
        "offline_s": lk.get("offline_s"), "release": bool(net_acc > 0.0),
        "gate": "released" if net_acc > 0.0 else "held_net_not_positive"})
    return out


def record(arm: Any, d: Dict[str, Any], now_s: float) -> None:
    st = arm.stats
    st["catchup_value_evals"] += 1
    g = str(d.get("gate"))
    st["catchup_value_" + g] += 1                      # gate 'released' IS the release counter
    cu = arm._cu_state
    if len(cu.vlog) < VLOG_CAP:
        row = {"t": round(float(now_s), 4)}
        for k, v in d.items():
            row[k] = round(v, 6) if isinstance(v, float) else v
        cu.vlog.append(row)
