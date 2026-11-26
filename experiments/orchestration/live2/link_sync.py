#!/usr/bin/env python3
"""link_sync: the policy side of POST-OUTAGE SYNC (switch `live2_link_sync`, DEFAULT OFF).

WHAT IT IS. After a reconnect the device's buffered backlog is HELD at the device (the emulator's
`link_sync_hold`) and goes up only when this controller asks for it (`sync_pull`, via
`arm.link_sync_out`, read once per epoch by `coordinator._link_sync_flush`). Live frames upload
first. The controller also decides, for a question that arrives before its device has caught up,
question-first / wait / device. It wraps the arm's own `decide` and changes only (a) the release
queue and (b) the recall actions of such questions; with no outage it never acts.

TWO MODES, ONE MACHINERY (user ruling 5). "ours" releases by priority (form iv: marginal on-time
gain per decision period minus the current-queue harm, deficit-weighted); "fifo" releases at the
reconnect, one device at a time, in reconnect order, with no gain or harm term. The naive-recovery
control is "fifo" on an arm built with deficit gain 0 (D226). Everything else is shared code.

SERIAL CATCH-UP (a design choice not in the ruling, FLAGGED): at most ONE device is released at a
time, the next after the previous one's estimated arrival. Without a shared bottleneck the release
order could not matter (each robot has its own 13.6 Mbps uplink). It is the stand-in for the
saturation guard on background sync and it is the same for both modes.

TIE-BREAK (`tiebreak`): under D177 the gain of a catch-up is exactly 0, so "hold" (LITERAL, the
gate arm) never releases early; "free" releases a device whenever the current-queue harm is
exactly 0 (a catch-up that costs nothing in the currency), most urgent expected question first.
"free" is a design choice not in the ruling and is a separate arm.
THE CURRENCY (user ruling D281). MAIN arm, `currency="acc"`: value = P(on time) x accuracy, with
COMMITTED accuracies only (`oracle_fair_table.json`): full evidence `recall|cloud|WITH_HISTORY`
0.568799 (n 12660), evidence-missing `recall|cloud|WITHOUT_HISTORY` 0.212222 (n 3011), device
option `recall|device|NA` 0.257732 (n 970; flash's choice, flagged). QUESTION-FIRST accuracy =
(1 - m) * 0.568799 + m * 0.212222 with m = the device's MISSING SECONDS / its HISTORY SECONDS, read
by the policy from the link record (offline interval) and the session's history span (the cloud's
believed history plus the held backlog, at the D2 stride of 2 s per frame). WAIT = the catch-up
time plus the later P(on time), then 0.568799.
*** STATED MODELLING ASSUMPTION: accuracy interpolates LINEARLY in the missing share between the
two committed values, and those values are POOLED over all recall questions, not measured on
outage-affected ones. *** It is recorded in `link_sync_value_model` in the counters.
ABLATION, `currency="d177"`: on-time only. D177 values an option at w * P(on-time cloud answer) and
does not read accuracy, so a catch-up is worth exactly 0 and the arm is EXPECTED NEVER TO RELEASE
EARLY (`plan_sync` cannot choose WAIT either). That expectation is part of the result.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import data_sources as DS
import links as LK

SYNC_SWITCH = "live2_link_sync"
MODES = ("ours", "fifo")
CURRENCIES = ("acc", "d177")
PRIOR_GAP_S = 30.0               # robot question gap prior (the rq30 re-ask mean) before any estimate
DECISION_PERIOD_S = 0.1
ROBOT_DEADLINE_S = 3.0           # D147, committed

_ORACLE = Path(__file__).resolve().parents[3] / "results/orchestration/live2/oracle/oracle_fair_table.json"


def _oracle(key: str) -> Tuple[float, int, int]:
    d = json.loads(_ORACLE.read_text())["table"][key]
    return float(d["acc"]), int(d["n"]), int(d["k"])


ACC_QF, _N, _K = _oracle("recall|cloud|WITH_HISTORY")
ACC_NO_EVIDENCE, _N2, _K2 = _oracle("recall|cloud|WITHOUT_HISTORY")
ACC_DEVICE, _N3, _K3 = _oracle("recall|device|NA")
D2_STRIDE_S = DS.D2_STRIDE_S
VALUE_MODEL = ("STATED MODELLING ASSUMPTION (D281): question-first accuracy = (1-m)*%.6f + m*%.6f, "
               "m = missing seconds / history seconds read from the link record and the session "
               "history span; accuracy interpolates LINEARLY in m between two committed values that "
               "are POOLED over all recall questions, not measured on outage-affected ones. Committed "
               "rows (oracle_fair_table.json): recall|cloud|WITH_HISTORY %.6f (n %d, k %d); "
               "recall|cloud|WITHOUT_HISTORY %.6f (n %d, k %d); device option recall|device|NA %.6f "
               "(n %d, k %d), flash's choice, flagged."
               % (ACC_QF, ACC_NO_EVIDENCE, ACC_QF, _N, _K, ACC_NO_EVIDENCE, _N2, _K2, ACC_DEVICE,
                  _N3, _K3))


def missing_share(offline_s: float, believed_tokens: int, backlog_tokens: int) -> float:
    """m = the device's missing seconds / its history seconds (D281). Missing seconds is the
    offline interval from the link record; history seconds is the session's history span at the D2
    stride, from the cloud's believed history plus the held backlog (the 31-token header excluded)."""
    full = max(int(believed_tokens) + int(backlog_tokens) - DS.D2_HEADER_TOK, 1)
    hist_s = full / float(DS.D2_TOK_PER_IMG) * D2_STRIDE_S
    return max(0.0, min(1.0, float(offline_s) / hist_s))


class SyncSwitchError(RuntimeError):
    pass


def arm_enables(arm: Any) -> Optional[str]:
    """The sync mode for THIS INSTANCE or None. Instance-dict only; a class-level value raises."""
    own = vars(arm)
    if SYNC_SWITCH not in own:
        for klass in type(arm).__mro__:
            if klass.__dict__.get(SYNC_SWITCH):
                raise SyncSwitchError("%s is set as a CLASS attribute of %s" % (SYNC_SWITCH,
                                                                                klass.__name__))
        return None
    v = own[SYNC_SWITCH]
    if v not in MODES:
        raise SyncSwitchError("%s must be one of %s, got %r" % (SYNC_SWITCH, MODES, v))
    return v


def arm_controls_sync(arm: Any) -> bool:
    return arm_enables(arm) is not None


class Controller:
    def __init__(self, arm: Any, mode: str, currency: str, tiebreak: str = "hold") -> None:
        self.arm, self.mode, self.currency, self.tiebreak = arm, mode, currency, tiebreak
        self.spec = LK.LinkSpec()
        self.tr: Dict[str, Dict[str, Any]] = {}
        self.c: Dict[str, Any] = {k: 0 for k in (
            "link_sync_epochs", "link_sync_reconnects_seen", "link_sync_releases",
            "link_sync_holds_serial", "link_sync_holds_harm", "link_sync_questions_before_catchup",
            "link_sync_plan_calls", "link_sync_choice_QUESTION_FIRST", "link_sync_choice_WAIT",
            "link_sync_choice_LEAVE_TO_DEVICE", "link_sync_acc_choice_QUESTION_FIRST",
            "link_sync_acc_choice_WAIT", "link_sync_acc_choice_DEVICE",
            "link_sync_acted_defer", "link_sync_acted_device", "link_sync_forced_release",
            "link_sync_plan_errors", "link_sync_harm_nonzero", "link_sync_gain_positive")}
        self.c["link_sync_value_model"] = VALUE_MODEL
        self.c["link_sync_mode"] = mode
        self.c["link_sync_currency"] = currency
        self.c["link_sync_tiebreak"] = tiebreak
        self.log: List[Dict[str, Any]] = []

    # ---- helpers ------------------------------------------------------------------------------
    def _roster(self) -> Dict[str, Any]:
        return getattr(getattr(self.arm, "_rules", None), "_roster", None) or {}

    def _gap(self, d: str) -> Tuple[float, bool]:
        g = (getattr(getattr(self.arm, "_rules", None), "_gap_ewma", None) or {}).get(d)
        return (float(g), True) if g else (PRIOR_GAP_S, False)

    def _next_q(self, d: str, now: float) -> float:
        """The policy's own CAUSAL next-question estimate (D11/D48): last seen question plus the
        EWMA gap, never earlier than now, and now + the prior gap with no estimate."""
        last = (getattr(getattr(self.arm, "_rules", None), "_last_q_t", None) or {}).get(d)
        gap, has = self._gap(d)
        return max(now, (float(last) + gap) if (has and last is not None) else now + gap)

    def _weight(self, d: str) -> float:
        try:
            return float(self.arm._planner_w_source.weight(d))
        except Exception:                                                  # noqa: BLE001
            return 1.0

    def _catch_up_s(self, frames: int) -> float:
        upload = LK.serialise_s(int(frames * DS.E10A_SEMBER_Q88_D2_MEDIAN_B), self.spec.uplink_mbps)
        return LK.pull_s(self.spec.rtt_ms) + upload + (self.spec.rtt_ms / 1000.0) / 2.0

    def _p(self, tokens: int, slack_s: float) -> float:
        import cf_cost as CC                                               # noqa: PLC0415
        cf = self.arm._cf_engine()
        pred = CC.predict(cf.model, int(tokens), 0, 0, 0)
        return float(CC.p_on_time(cf.residuals, pred.engine_s, float(slack_s) - CC.LINK_RTT_S))

    # ---- the epoch ----------------------------------------------------------------------------
    def step(self, obs: Any, act: Any) -> Any:
        self.c["link_sync_epochs"] += 1
        now = float(obs.now_s)
        self._track(obs, now)
        if self.tr:
            act = self._questions(obs, act, now)
            self._release(obs, now)
        return act

    def _track(self, obs: Any, now: float) -> None:
        for lk in obs.device_links:
            d = lk.device_id
            if (lk.connected and lk.back_online_at is not None and lk.backlog_frames > 0
                    and d not in self.tr):
                self.tr[d] = dict(reconnect=float(lk.back_online_at), frames=int(lk.backlog_frames),
                                  offline_s=float(lk.back_online_at - lk.offline_since),
                                  tokens=int(lk.backlog_tokens), state="pending", est_done=None,
                                  requested_at=None, seen_at=now)
                self.c["link_sync_reconnects_seen"] += 1
                pend = sorted(x for x, r in self.tr.items() if r["state"] == "pending")
                self.log.append(dict(ev="reconnect_seen", t=now, device_id=d,
                                     reconnect=lk.back_online_at, backlog_frames=lk.backlog_frames,
                                     backlog_tokens=lk.backlog_tokens,
                                     next_q_estimates={x: round(self._next_q(x, now), 3)
                                                       for x in pend},
                                     gap_has_estimate={x: self._gap(x)[1] for x in pend}))

    def _caught_up(self, d: str, now: float) -> bool:
        r = self.tr.get(d)
        if r is None or r["state"] == "done":
            return True
        if r["state"] == "catching_up" and now >= r["est_done"]:
            r["state"] = "done"
            self.log.append(dict(ev="caught_up_est", t=now, device_id=d))
            return True
        return False

    def _dev_session(self, obs: Any, d: str) -> Optional[str]:
        sd = self._roster().get("session_device") or {}
        live = set(obs.live_sessions)
        cands = sorted(s for s, dv in sd.items() if dv == d and s in live)
        return cands[-1] if cands else None

    # ---- questions that arrive before catch-up -----------------------------------------------
    def _questions(self, obs: Any, act: Any, now: float) -> Any:
        sd = self._roster().get("session_device") or {}
        for q in obs.recall:
            d = sd.get(q.session_id)
            if d is None or d not in self.tr or self._caught_up(d, now):
                continue
            r = self.tr[d]
            self.c["link_sync_questions_before_catchup"] += 1
            rem_tokens = r["tokens"]
            believed = int(q.readiness_tokens)
            full = believed + rem_tokens
            if r["state"] == "catching_up":
                catch = max(r["est_done"] - now, 0.0)
            else:
                catch = self._catch_up_s(r["frames"])
            dl_s = float(q.deadline_s) - now
            chosen, plan_choice = None, None
            try:
                dec = self.arm._cf_engine().plan_sync(
                    decision_id="link_q:" + str(q.query_id), device_id=d, now_s=now,
                    deadline_abs_s=float(q.deadline_s), pre_outage_tokens=believed,
                    recent_frame_tokens=0, full_tokens=full, catch_up_s=catch,
                    acc_question_first=ACC_QF, question_id=q.question_id, kind="robot")
                plan_choice = dec.chosen
                self.c["link_sync_plan_calls"] += 1
                self.c["link_sync_choice_" + plan_choice] += 1
            except Exception as e:                                         # noqa: BLE001
                self.c["link_sync_plan_errors"] += 1
                plan_choice = "ERROR:" + type(e).__name__
            p_qf = self._p(believed, dl_s)
            p_w = self._p(full, dl_s - catch)
            m = missing_share(r["offline_s"], believed, rem_tokens)
            w = self._weight(d)
            acc_qf_m = (1.0 - m) * ACC_QF + m * ACC_NO_EVIDENCE
            v_qf = w * p_qf * acc_qf_m
            v_w = w * p_w * ACC_QF
            try:
                import cf_objective as CO                                  # noqa: PLC0415
                p_dev = float(CO.p_device_on_time(dl_s, CO.device_wait_s(
                    kind="robot", question_id=q.question_id)))
            except Exception:                                              # noqa: BLE001
                p_dev = 1.0
            v_dev = w * p_dev * ACC_DEVICE
            best = max((v_qf, "QUESTION_FIRST"), (v_w, "WAIT"), (v_dev, "DEVICE"))
            acc_choice = best[1]
            self.c["link_sync_acc_choice_" + acc_choice] += 1
            chosen = ({"QUESTION_FIRST": "QUESTION_FIRST", "WAIT": "WAIT", "DEVICE": "LEAVE_TO_DEVICE"}[acc_choice]
                      if self.currency == "acc" else (plan_choice or "QUESTION_FIRST"))
            self.log.append(dict(ev="question", t=now, device_id=d, query_id=q.query_id,
                                 believed_tokens=believed, backlog_tokens=rem_tokens,
                                 deadline_in_s=round(dl_s, 3), catch_up_s=round(catch, 3),
                                 plan_sync_choice=plan_choice, acc_choice=acc_choice,
                                 m=round(m, 4), qf_accuracy_modelled=round(acc_qf_m, 6),
                                 v_qf=round(v_qf, 6), v_wait=round(v_w, 6), v_device=round(v_dev, 6),
                                 p_qf=round(p_qf, 4),
                                 p_wait=round(p_w, 4), chosen=chosen,
                                 qf_accuracy_provisional=ACC_QF))
            if chosen == "WAIT":
                self._force_release(d, now)
                self._set_recall(act, q.query_id, "DEFER", defer_s=round(catch + 0.05, 3))
                self.c["link_sync_acted_defer"] += 1
            elif chosen == "LEAVE_TO_DEVICE":
                self._set_recall(act, q.query_id, "DEVICE")
                self.c["link_sync_acted_device"] += 1
        return act

    @staticmethod
    def _set_recall(act: Any, query_id: str, decision: str, defer_s: Optional[float] = None) -> None:
        from interface import RecallAction                                  # noqa: PLC0415
        for ra in act.recalls:
            if ra.query_id == query_id:
                ra.decision, ra.defer_s = decision, defer_s
                return
        act.recalls.append(RecallAction(query_id=query_id, decision=decision, defer_s=defer_s))

    def _issue(self, d: str, now: float, why: str, **extra: Any) -> None:
        r = self.tr[d]
        r["state"], r["requested_at"] = "catching_up", now
        r["est_done"] = now + self._catch_up_s(r["frames"])
        self.arm.link_sync_out.append((d, 0))
        self.c["link_sync_releases"] += 1
        self.log.append(dict(ev="release", t=now, device_id=d, why=why, est_done=round(r["est_done"], 3),
                             reconnect=r["reconnect"], order_index=self.c["link_sync_releases"],
                             **extra))

    def _force_release(self, d: str, now: float) -> None:
        if self.tr[d]["state"] == "pending":
            self.c["link_sync_forced_release"] += 1
            self._issue(d, now, "question_wait")

    # ---- background release -------------------------------------------------------------------
    def _release(self, obs: Any, now: float) -> None:
        pend = [d for d, r in self.tr.items() if r["state"] == "pending"]
        if not pend:
            return
        busy = [d for d, r in self.tr.items() if r["state"] == "catching_up" and now < r["est_done"]]
        if busy:
            self.c["link_sync_holds_serial"] += 1
            return
        if self.mode == "fifo":
            d = sorted(pend, key=lambda x: (self.tr[x]["reconnect"], x))[0]
            self._issue(d, now, "fifo")
            return
        scored = []
        for d in pend:
            r = self.tr[d]
            gap, _has = self._gap(d)
            p_ev = missing_share(r["offline_s"], self._believed(obs, d), r["tokens"])
            w = self._weight(d)
            p_qf = self._p(max(self._believed(obs, d), 1), ROBOT_DEADLINE_S)
            if self.currency == "acc":
                gain = (w * (1.0 / gap) * DECISION_PERIOD_S * p_qf * p_ev * (ACC_QF - ACC_NO_EVIDENCE))
            else:
                gain = 0.0
            sid = self._dev_session(obs, d)
            harm = 0.0
            if sid is not None:
                try:
                    harm = float(self.arm._harm_warm(obs, sid, int(r["tokens"])))
                except Exception:                                          # noqa: BLE001
                    harm = 0.0
            if harm > 0:
                self.c["link_sync_harm_nonzero"] += 1
            if gain > 0:
                self.c["link_sync_gain_positive"] += 1
            scored.append((gain - harm, gain, harm, self._next_q(d, now), d))
        scored.sort(key=lambda x: (-x[0], x[3], x[4]))
        net, gain, harm, nq, d = scored[0]
        if net > 0.0 or (net == 0.0 and (gain > 0.0 or self.tiebreak == "free")):
            self._issue(d, now, "priority", net=round(net, 9), gain=round(gain, 9),
                        harm=round(harm, 9), next_q_est=round(nq, 3),
                        pending_order=[x[4] for x in scored])
        else:
            self.c["link_sync_holds_harm"] += 1

    def _believed(self, obs: Any, d: str) -> int:
        sid = self._dev_session(obs, d)
        if sid is None:
            return 0
        return int((self._roster().get("est_tokens_by_session") or {}).get(sid, 0))


def install(arm: Any, mode: str, currency: str = "acc", tiebreak: str = "hold") -> None:
    if mode not in MODES or currency not in CURRENCIES:
        raise SyncSwitchError("bad mode/currency %r/%r" % (mode, currency))
    object.__setattr__(arm, SYNC_SWITCH, mode)
    arm.link_sync_out = []
    arm.link_sync = Controller(arm, mode, currency, tiebreak)
    inner = arm.decide

    def decide(obs):
        act = inner(obs)
        return arm.link_sync.step(obs, act)
    arm.decide = decide
    if arm_enables(arm) != mode:                                           # pragma: no cover
        raise SyncSwitchError("link sync did not take on the instance")
