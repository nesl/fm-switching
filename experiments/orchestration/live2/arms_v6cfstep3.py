#!/usr/bin/env python3
"""STEP 3 ARM, REBUILT ON F0 (D327/D331): `covex-v6-fair-final-cand-tl-sync-cf` (F1) = F0 + protect-and-defer +
forfeit-valued admission + the deficit-rotated resident set. See `cf_forfeit.py` for the rule and its units.

F0 is `covex-v6-fair-final-cand-tl-sync` = rung 3 + P (engine_resync + pb_wire_tokens +
pb_host_engine_model) + 0b + B + the touch-latch fix (`pb_touch_guard`) + the S2 value-gated catch-up
prefill (`catchup_prefill` + `catchup_value`). The question-priority uplink `_qp` is a CELL TAG, not an
arm property, and is passed to this arm exactly as to F0. The N_exp / FUTURE helpers are the ones in
`future_horizon.py`, shared with the S2 gate (D328): sync and the counterfactual agree on a robot's future.

COMPOSITION (MRO): `V6CandCF(_ProtectDeferMixin, _Step3Mixin, V6FairFinal)`.
    _Step3Mixin.decide runs INSIDE `_ProtectDeferMixin.decide` (super), so an admission this step
    makes is then seen by rung 4's protect-and-defer REQUEST leg, which may still defer it when an
    alert episode is active and the harm crosses the committed bar. Request deferral
    (`cf_request_defer`) is NOT part of this arm: it fired 54 times with 0 rescues (D232).

EVERY SWITCH DEFAULT OFF. With both step-3 switches off the mixin returns `super().decide(obs)`
untouched. The protect-and-defer switch is the committed one (`live2_cf_protect_defer`).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d162_price as DP                                                        # noqa: E402
import cf_cost as CC                                                           # noqa: E402
import cf_forfeit as CF                                                        # noqa: E402
import cf_protect_defer as PD                                                  # noqa: E402
import la_arrival_admission as LAA                                             # noqa: E402
import context_limit as CL                                                     # noqa: E402
import arms_v6cf as VCF                                                        # noqa: E402

STEP3_VERSION = "covex-v6-cand-tl-sync-cf-1.0"
CAND_CF = "covex-v6-fair-final-cand-tl-sync-cf"
MAX_CF_ROWS = 6000


class _Step3Mixin:
    """The two step-3 channels, as post-processing of the base action (the pattern the committed
    protect-and-defer mixin uses). Mixed in BEHIND `_ProtectDeferMixin`."""

    def __init__(self, name: str, *, cf_forfeit_admit: bool = False,
                 cf_resident_set: bool = False, cf_future_mode: str = "horizon",
                 cf_harm_arrivals: bool = False, cf_window_mode: str = "queue_service",
                 cf_s2_netting: bool = False, cf_claim_scope: str = "window", **kw: Any) -> None:
        super().__init__(name=name, **kw)
        if cf_claim_scope not in ("window", "piece"):
            raise ValueError("cf_claim_scope must be 'window' or 'piece'")
        self.cf3_claim_scope = str(cf_claim_scope)
        if cf_window_mode not in CF.WINDOW_MODES:
            raise ValueError("cf_window_mode must be one of %r" % (CF.WINDOW_MODES,))
        self.cf3_window_mode = str(cf_window_mode)
        if cf_future_mode not in ("horizon", "next", "zero"):
            raise ValueError("cf_future_mode must be 'horizon', 'next' or 'zero'")
        self.cf3_future_mode = str(cf_future_mode)
        object.__setattr__(self, CF.ADMIT_SWITCH, bool(cf_forfeit_admit))
        object.__setattr__(self, CF.RESIDENT_SWITCH, bool(cf_resident_set))
        object.__setattr__(self, CF.HARM_ARRIVALS_SWITCH, bool(cf_harm_arrivals))
        object.__setattr__(self, CF.NET_SWITCH, bool(cf_s2_netting))
        self._cf3_dev: Dict[str, Dict[str, Any]] = {}
        self.cf3_rows: List[Dict[str, Any]] = []
        self._cf3_host_tokens: Optional[float] = None
        self._cf3_set_key: Any = None
        self._cf3_set: Optional[Dict[str, Any]] = None
        self.arm_version = STEP3_VERSION

    def live2_configure(self, **kw: Any) -> None:
        if "host_tier_tokens" in kw:
            self._cf3_host_tokens = float(kw["host_tier_tokens"])
        super().live2_configure(**kw)

    # ---- the resident set ------------------------------------------------------------------
    def _cf3_capacity(self, obs: Any, robot_belief_tokens: float) -> Optional[float]:
        pool = getattr(self, "_pd_gpu_kv_tokens", None)
        if pool is None or self._cf3_host_tokens is None:
            return None
        frac = float(getattr(obs.cloud, "gpu_kv_fraction", 0.0) or 0.0)
        not_robot = max(frac * float(pool) - float(robot_belief_tokens), 0.0)
        return max(float(pool) + float(self._cf3_host_tokens) - not_robot, 0.0)

    def _cf3_resident(self, obs: Any) -> Optional[Dict[str, Any]]:
        key = (float(obs.now_s), int(len(obs.recall or ())))
        if self._cf3_set_key == key:
            return self._cf3_set
        self._cf3_set_key = key
        roster = getattr(self._rules, "_roster", None) or {}
        sdev = roster.get("session_device") or {}
        devs = roster.get("devices") or {}
        est = roster.get("est_tokens_by_session") or {}
        built = roster.get("built_tokens_by_session") or {}
        cands: List[Dict[str, Any]] = []
        for sid, did in sdev.items():
            if str((devs.get(did) or {}).get("type")) != "robot":
                continue
            nq = self._p_question(str(did), float(obs.now_s))
            if not nq["has_estimate"]:
                continue
            # ACTIVE only: the last question is inside the committed warm horizon. A session that has
            # not asked for longer than HORIZON_WARM_CAP_S is not a candidate (its predicted next
            # time clamps to NOW, which would rank a dead session first).
            last_q = (getattr(self._rules, "_last_q_t", None) or {}).get(str(did))
            if last_q is None or float(obs.now_s) - float(last_q) > float(CC.HORIZON_WARM_CAP_S):
                self.stats["cf3_resident_stale_session"] += 1
                continue
            tok = int(est.get(sid, 0) or 0)
            if tok <= 0:
                continue
            cands.append({"session_id": str(sid), "device_id": str(did), "tokens": tok,
                          "w": float(self._pd_w_of(str(did))),
                          "next_q_s": float(nq["next_question_s"])})
        rb = float(sum(int(built.get(str(s), 0) or 0) for s in (obs.cloud.gpu_warm_sessions or ())
                       if str(s) in sdev
                       and str((devs.get(sdev.get(str(s))) or {}).get("type")) == "robot"))
        cap = self._cf3_capacity(obs, rb)
        if cap is None:
            self.stats["cf3_resident_no_capacity"] += 1
            self._cf3_set = None
            return None
        rs = CF.resident_set(cands, cap)
        rs["member_set"] = frozenset(rs["members"])
        rs["excluded_set"] = frozenset(rs["excluded"])
        st = self.stats
        st["cf3_resident_epochs"] += 1
        st["cf3_resident_members_sum"] += len(rs["members"])
        st["cf3_resident_excluded_sum"] += len(rs["excluded"])
        if rs["excluded"]:
            st["cf3_resident_epochs_with_excluded"] += 1
        prev = self.__dict__.get("_cf3_prev_members")
        if prev is not None and prev != rs["member_set"]:
            st["cf3_resident_rotations"] += 1
        self.__dict__["_cf3_prev_members"] = rs["member_set"]
        self._cf3_set = rs
        return rs

    # ---- the decision ----------------------------------------------------------------------
    def decide(self, obs: Any) -> Any:
        act = super().decide(obs)
        admit_on, res_on = CF.admit_enabled(self), CF.resident_enabled(self)
        if not (admit_on or res_on):
            return act
        self._cf3_observe(obs)
        rs = self._cf3_resident(obs)
        if res_on and rs is not None:
            self._cf3_filter_touches(act, rs)
        if admit_on:
            self._cf3_admit(obs, act, rs if res_on else None)
        return act

    def _cf3_filter_touches(self, act: Any, rs: Dict[str, Any]) -> None:
        keep: List[Any] = []
        dropped = 0
        for sa in list(act.sessions or ()):
            if str(getattr(sa, "action", "")) == "KEEP_GPU_WARM" \
                    and str(sa.session_id) in rs["excluded_set"]:
                dropped += 1
                continue
            keep.append(sa)
        if dropped:
            act.sessions = keep
            self.stats["cf3_touch_dropped_outside_set"] += dropped

    def _cf3_la_row(self, query_id: str) -> Optional[Dict[str, Any]]:
        base = getattr(getattr(self, "_rules", None), "_base", None) or getattr(self, "_rules", None)
        rows = base.__dict__.get("_la_dec_rows") if base is not None else None
        for r in reversed(rows or ()):
            if r.get("query_id") == query_id:
                return r
        return None

    def _cf3_observe(self, obs: Any) -> None:
        """Per device, the last question seen (its session, prompt tokens, deadline duration, type):
        what an EXPECTED arrival of that device would look like. Read-only bookkeeping."""
        roster = getattr(self._rules, "_roster", None) or {}
        sdev = roster.get("session_device") or {}
        ss_types = getattr(self._rules, "_ss_types", None) or frozenset()
        for qy in (obs.recall or ()):
            did = sdev.get(str(qy.session_id))
            if did is None:
                continue
            self._cf3_dev[str(did)] = {
                "session_id": str(qy.session_id), "tokens": int(qy.readiness_tokens),
                "slack_s": float(qy.deadline_s) - float(qy.arrival_s),
                "qtype": ("assistance" if str(getattr(qy, "category", "")) in ss_types else "recall")}

    def _cf3_arrival_harm(self, obs: Any, did: str, u: int, est_la: float, w_of: Any,
                          p_on: Any) -> Dict[str, Any]:
        roster = getattr(self._rules, "_roster", None) or {}
        built = roster.get("built_tokens_by_session") or {}
        gaps = getattr(self._rules, "_gap_ewma", None) or {}
        ahead = LAA.queued_ahead(obs)
        service = float(DP.first_token_s(int(u), 0))
        wait = float(DP.first_token_s(int(u), int(ahead))) - service
        window = CF.arrival_window(service_s=service, wait_s=wait,
                                   cap_s=float(CC.HORIZON_WARM_CAP_S), mode=self.cf3_window_mode)
        devs = []
        for d2, info in self._cf3_dev.items():
            if d2 == str(did):
                continue
            devs.append({"device_id": d2, "qtype": info["qtype"], "gap_s": gaps.get(d2),
                         "u_tokens": max(int(info["tokens"]) - int(built.get(info["session_id"], 0) or 0), 0),
                         "slack_s": info["slack_s"]})
        ar = CF.arrival_rows(devs, ahead_tokens=ahead, window_s=window,
                             est_of=LAA.loadaware_est)
        h = PD.harm_on_time(u, ar["rows"], p_on_time=p_on,
                            w_of=lambda dv: float(w_of(dv)) * float(ar["n_by_dev"].get(str(dv), 0.0)))
        h["n_expected_total"] = ar["n_expected_total"]
        h["window_s"] = ar["window_s"]
        h["queue_wait_s"] = wait
        h["service_s"] = service
        h["n_arrival_rows"] = len(ar["rows"])
        return h

    def _cf3_s2_claim(self, obs: Any, did: str, scope: str):
        """D333 extended netting: (held, since) for S2's claim on device `did`'s future."""
        import catchup_prefill as CU
        rules = getattr(self, "_rules", None)
        if rules is None or getattr(rules, "_cu_state", None) is None:
            return False, None
        return CU.s2_claim(rules, obs, did, scope)

    def _cf3_f1_window(self, obs: Any, u: int) -> float:
        """The admitted request's own D324 window (est_loadaware, capped at the horizon): the span in
        which F1 holds the robot's future. The same function the arrival HARM uses."""
        ahead = LAA.queued_ahead(obs)
        service = float(DP.first_token_s(int(u), 0))
        wait = float(DP.first_token_s(int(u), int(ahead))) - service
        return float(CF.arrival_window(service_s=service, wait_s=wait,
                                       cap_s=float(CC.HORIZON_WARM_CAP_S), mode=self.cf3_window_mode))

    def _cf3_net_claim(self, obs: Any, act: Any, ra: Any, d: Dict[str, Any], did: str, sid: str,
                       harm: Dict[str, Any], harm_arr: Optional[Dict[str, Any]]) -> bool:
        """D331 NETTING: F1's counterfactual admission and S2's catch-up release must not both act on
        the same robot in the same epoch. Called when the admission rule would ADMIT. Returns True
        when the ADMISSION is suppressed (S2's release has the higher net); when the admission has the
        higher net, S2's MATERIALIZE action for that robot is removed from the plan and logged as
        suppressed. With the switch OFF it only COUNTS and LOGS the coincidence (both execute: the
        un-netted behaviour). Every quantity committed: no constant."""
        cu = getattr(getattr(self, "_rules", None), "_cu_state", None)
        self.stats["cf3_net_checked"] += 1                  # an admission reached the claim
        if cu is None or getattr(cu, "rel_t", None) is None or float(cu.rel_t) != float(obs.now_s):
            return False
        self.stats["cf3_net_s2_epoch_open"] += 1            # S2 released some robot in this very epoch
        s2 = None
        for sid2, (net2, did2) in (cu.rel or {}).items():
            if str(did2) == str(did):
                s2 = (str(sid2), float(net2))
                break
        if s2 is None:
            return False
        import catchup_value as CV
        import link_sync as LS
        gaps = CV._gaps()
        g_robot = float(LS.ACC_QF) - float(LS.ACC_DEVICE)
        by_type: Dict[str, float] = {}
        for hh in (harm, harm_arr):
            for k, v in ((hh or {}).get("harm_by_type") or {}).items():
                by_type[k] = by_type.get(k, 0.0) + float(v)
        harm_acc = sum(float(v) * float(gaps[k]) for k, v in by_type.items())
        adm_acc = (float(d["own_gain"]) + float(d["future_gain"]) - float(d["bar"])) * g_robot - harm_acc
        st = self.stats
        st["cf3_net_coincide"] += 1
        net_on = CF.net_enabled(self)
        win = CF.net_winner(adm_acc, s2[1])
        row = {"event": "net_claim", "t": round(float(obs.now_s), 4), "device_id": str(did),
               "session_id": sid, "query_id": str(ra.query_id), "s2_session_id": s2[0],
               "adm_net_acc": round(adm_acc, 6), "s2_net_acc": round(s2[1], 6), "harm_acc": round(harm_acc, 6),
               "netting_on": bool(net_on), "winner": win,
               "executed": (("both" if not net_on else ("admit" if win == "admit" else "s2"))),
               "suppressed": (None if not net_on else ("s2_release" if win == "admit" else "admission"))}
        if len(self.cf3_rows) < MAX_CF_ROWS:
            self.cf3_rows.append(row)
        if not net_on:
            st["cf3_net_both_executed"] += 1
            return False
        if win == "admit":
            before = len(act.sessions or ())
            act.sessions = [sa for sa in (act.sessions or ())
                            if not (str(getattr(sa, "session_id", "")) == s2[0]
                                    and str(getattr(sa, "action", "")) == "MATERIALIZE")]
            st["cf3_net_s2_suppressed"] += 1
            st["cf3_net_s2_actions_removed"] += before - len(act.sessions)
            if float(cu.first_rel.get(s2[0], -1.0)) == float(obs.now_s):
                cu.first_rel.pop(s2[0], None)                # the release did not execute: no S2 claim
            if float(cu.rel_dev.get(str(did), -1.0)) == float(obs.now_s):
                cu.rel_dev.pop(str(did), None)
            return False
        st["cf3_net_admission_suppressed"] += 1
        return True

    def _cf3_admit(self, obs: Any, act: Any, rs: Optional[Dict[str, Any]]) -> None:
        roster = getattr(self._rules, "_roster", None) or {}
        sdev = roster.get("session_device") or {}
        devs = roster.get("devices") or {}
        st = self.stats
        arrivals_on = CF.harm_arrivals_enabled(self)
        cf = self._cf_engine()
        res = cf.residuals
        for ra in list(act.recall or ()):
            if str(getattr(ra, "decision", "")) != "REJECT":
                continue
            qy = next((q for q in (obs.recall or ()) if str(q.query_id) == str(ra.query_id)), None)
            if qy is None:
                continue
            sid = str(qy.session_id)
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            if int(getattr(qy, "readiness_tokens", 0) or 0) > CL.limit_tokens():
                st["cf3_skip_over_limit"] += 1
                continue
            row = self._cf3_la_row(str(ra.query_id))
            if row is None:
                st["cf3_skip_no_la_row"] += 1
                continue
            st["cf3_considered"] += 1
            u = int(row["uncached_u"])
            est_la, qs = float(row["est_loadaware_s"]), float(row["slack_s"])
            w_r = float(self._pd_w_of(str(did)))
            nq = self._p_question(str(did), float(obs.now_s))
            dt = (float(nq["next_question_s"]) - float(obs.now_s)) if nq["has_estimate"] else None
            p_on = (lambda e, s: float(CC.p_on_time(res, e, s)))
            # old HARM: other pending ROBOT questions. D320 HARM: pending robot and single-shot
            # questions PLUS the questions expected to arrive while this request is served.
            others = [r for r in self._pd_others(obs, sid)
                      if r["qtype"] in (("recall", "assistance") if arrivals_on else ("recall",))]
            harm = PD.harm_on_time(u, others, p_on_time=p_on, w_of=self._pd_w_of)
            harm_pending = float(harm["harm"])
            harm_arr = None
            if arrivals_on:
                harm_arr = self._cf3_arrival_harm(obs, str(did), u, est_la, self._pd_w_of, p_on)
                harm = dict(harm, harm=harm_pending + float(harm_arr["harm"]))
            bar = PD.bar(self._pd_w_of, str(did), harmed_device_ids=[str(r["device_id"]) for r in others],
                         reading=self._pd_bar_reading)
            p_self = float(CC.p_on_time(res, est_la, qs))
            fut = None
            if dt is not None and dt <= float(CC.HORIZON_WARM_CAP_S):
                l_next = float(qy.deadline_s) - float(qy.arrival_s)
                gap = (getattr(self._rules, "_gap_ewma", None) or {}).get(str(did))
                # 'zero' is the Step 4 negative control (the future term forced to 0 at its source,
                # everything else live): it must collapse to the arm without the admission.
                n_exp = (CF.expected_questions(float(CC.HORIZON_WARM_CAP_S), gap)
                         if self.cf3_future_mode == "horizon"
                         else (0.0 if self.cf3_future_mode == "zero" else 1.0))
                fut = CF.forfeited_future(
                    w_r=w_r, u_cold=u, u_warm=0, slack_next_s=l_next,
                    p_on_time=lambda e, s: float(CC.p_on_time(res, e, s)),
                    engine_s_of=lambda n: float(CC.predict(cf.model, int(n), 0, 0, 0).engine_s),
                    n_expected=(1.0 if n_exp is None else float(n_exp)))
            in_set = True if rs is None else (sid in rs["member_set"])
            # D333 EXTENDED NETTING: S2's claim on this robot's future, opened in an EARLIER epoch and
            # not yet completed, bars F1 from crediting it (a same-epoch release goes to the joint
            # evaluation `_cf3_net_claim`). Both claim scopes are measured; `cf3_claim_scope` rules.
            net_on = CF.net_enabled(self)
            held_w, since_w = self._cf3_s2_claim(obs, str(did), "window")
            held_p, since_p = self._cf3_s2_claim(obs, str(did), "piece")
            held, since = (held_w, since_w) if self.cf3_claim_scope == "window" else (held_p, since_p)
            claim_block = CF.s2_claim_blocks(net_on, held, since, float(obs.now_s))
            d_free = CF.admit_decision(
                in_resident_set=in_set, has_estimate=bool(nq["has_estimate"]), dt_next_s=dt,
                horizon_cap_s=float(CC.HORIZON_WARM_CAP_S), w_r=w_r, p_self=p_self,
                harm=float(harm["harm"]), bar_value=float(bar["bar"]), future=fut)
            would = d_free["action"] == CF.ADMIT
            if would and held_w and since_w is not None and float(since_w) < float(obs.now_s):
                st["cf3_claim_diag_window_would_block"] += 1
            if would and held_p and since_p is not None and float(since_p) < float(obs.now_s):
                st["cf3_claim_diag_piece_would_block"] += 1
            if claim_block:
                d = CF.admit_decision(
                    in_resident_set=in_set, has_estimate=bool(nq["has_estimate"]), dt_next_s=dt,
                    horizon_cap_s=float(CC.HORIZON_WARM_CAP_S), w_r=w_r, p_self=p_self,
                    harm=float(harm["harm"]), bar_value=float(bar["bar"]), future=None)
                if d["gate"] == "future_not_priced":
                    d["gate"] = "future_claimed_by_s2"
                st["cf3_claim_s2_held_epochs"] += 1
                if would:
                    st["cf3_claim_blocked_admission"] += 1
                    if len(self.cf3_rows) < MAX_CF_ROWS:
                        self.cf3_rows.append({
                            "event": "claim_block", "t": round(float(obs.now_s), 4), "device_id": str(did),
                            "session_id": sid, "query_id": str(ra.query_id), "scope": self.cf3_claim_scope,
                            "s2_claim_since": round(float(since), 4), "would_net": round(float(d_free["net"]), 6),
                            "bar": round(float(d_free["bar"]), 6)})
            else:
                d = d_free
            st["cf3_gate_" + str(d["gate"]).split(":")[0]] += 1
            if len(self.cf3_rows) < MAX_CF_ROWS:
                self.cf3_rows.append({
                    "t": round(float(obs.now_s), 4), "query_id": str(ra.query_id), "session_id": sid,
                    "device_id": str(did), "u": u, "est_la": round(est_la, 6),
                    "slack_s": round(qs, 6), "action": d["action"], "gate": d["gate"],
                    "in_resident_set": bool(in_set), "dt_next_s": dt, "w_r": w_r,
                    "p_self": round(p_self, 6), "harm": round(float(harm["harm"]), 6),
                    "n_harm_rows": int(harm["n_others_considered"]),
                    "harm_pending": round(harm_pending, 6),
                    "harm_arrival": (None if harm_arr is None else round(float(harm_arr["harm"]), 6)),
                    "n_expected_arrivals": (None if harm_arr is None
                                            else round(float(harm_arr["n_expected_total"]), 4)),
                    "arrival_window_s": (None if harm_arr is None else round(float(harm_arr["window_s"]), 4)),
                    "queue_wait_s": (None if harm_arr is None else round(float(harm_arr["queue_wait_s"]), 4)),
                    "service_s": (None if harm_arr is None else round(float(harm_arr["service_s"]), 4)),
                    "bar": round(float(bar["bar"]), 6),
                    "future_gain": round(float(d.get("future_gain", 0.0)), 6),
                    "n_expected": (None if fut is None else round(fut["n_expected"], 4)),
                    "net": (None if "net" not in d else round(float(d["net"]), 6)),
                    "p_on_cold": (None if fut is None else round(fut["p_on_cold"], 6)),
                    "p_on_warm": (None if fut is None else round(fut["p_on_warm"], 6))})
            if d["action"] == CF.ADMIT and self._cf3_net_claim(obs, act, ra, d, str(did), sid, harm, harm_arr):
                continue
            if d["action"] == CF.ADMIT:
                ra.decision = "CLOUD"
                ra.defer_s = None
                st["cf3_admitted"] += 1
                cu_ = getattr(getattr(self, "_rules", None), "_cu_state", None)
                if net_on and cu_ is not None:
                    w_ = self._cf3_f1_window(obs, u)
                    cu_.f1_claim[str(did)] = (float(obs.now_s), float(obs.now_s) + w_)
                    st["cf3_claim_f1_opened"] += 1
                    if len(self.cf3_rows) < MAX_CF_ROWS:
                        self.cf3_rows.append({"event": "f1_claim_open", "t": round(float(obs.now_s), 4),
                                              "device_id": str(did), "session_id": sid,
                                              "until": round(float(obs.now_s) + w_, 4), "window_s": round(w_, 4)})

    def cf3_report(self) -> Dict[str, Any]:
        return {"version": STEP3_VERSION, "forfeit": CF.as_dict(),
                "admit_on": CF.admit_enabled(self), "resident_on": CF.resident_enabled(self),
                "n_rows": len(self.cf3_rows)}


def _build_class() -> Any:
    import arms_final_ladder as FL                                         # noqa: PLC0415
    return type("V6CandCF", (VCF._ProtectDeferMixin, _Step3Mixin, FL.V6FairFinal),
                {"_pd_base_key": "c5attr",
                 "__doc__": "the candidate plus protect-and-defer plus the two step-3 channels"})


def make_cand_cf(name: str = CAND_CF, *, cf_forfeit_admit: bool = True,
                 cf_resident_set: bool = True, protect_defer: bool = True,
                 cf_future_mode: str = "horizon", cf_harm_arrivals: bool = True,
                 cf_window_mode: str = "queue_service", cf_s2_netting: bool = True,
                 cf_claim_scope: str = "window", **kw: Any) -> Any:
    """F0 switches (P engine_resync + wire + host model, 0b, B, touch guard, S2 value-gated catch-up) via the ONE ladder builder,
    over the step-3 class, then the committed live weight wiring rung 4 uses for `w_d`."""
    import arms_final_ladder as FL                                         # noqa: PLC0415
    import arms_v6cfr3 as R4                                               # noqa: PLC0415
    cls = _build_class()
    arm = FL.make_rung3(name, predictive_belief=True, book_belief=True, la_arrival=True,
                        engine_resync=True, pb_wire_tokens=True, pb_host_engine_model=True,
                        pb_touch_guard=True, catchup_prefill=True, catchup_value=True,
                        _cls=cls, _cls_kw=dict(protect_defer=protect_defer,
                                               cf_forfeit_admit=cf_forfeit_admit,
                                               cf_resident_set=cf_resident_set,
                                               cf_future_mode=cf_future_mode,
                                               cf_harm_arrivals=cf_harm_arrivals,
                                               cf_window_mode=cf_window_mode,
                                               cf_s2_netting=cf_s2_netting,
                                               cf_claim_scope=cf_claim_scope), **kw)
    arm._pd_w_of = lambda did, _a=arm: R4._weight_of(_a, did)
    arm._pd_w_source = R4.W_SOURCE_LIVE
    if CF.admit_enabled(arm) is not bool(cf_forfeit_admit) or \
            CF.harm_arrivals_enabled(arm) is not bool(cf_harm_arrivals) or \
            CF.resident_enabled(arm) is not bool(cf_resident_set):         # pragma: no cover
        raise FL.LadderSwitchError("the step-3 switches did not take on the instance")
    return arm


ARMS_STEP3: Dict[str, Any] = {
    CAND_CF: (lambda **kw: make_cand_cf(CAND_CF, **kw)),
    # one-factor attribution arms (each component alone; protect-and-defer stays with all three)
    CAND_CF + "-a": (lambda **kw: make_cand_cf(CAND_CF + "-a", cf_resident_set=False, **kw)),
    CAND_CF + "-r": (lambda **kw: make_cand_cf(CAND_CF + "-r", cf_forfeit_admit=False,
                                                cf_harm_arrivals=False, **kw)),
    CAND_CF + "-pd": (lambda **kw: make_cand_cf(CAND_CF + "-pd", cf_forfeit_admit=False,
                                                cf_resident_set=False, cf_harm_arrivals=False, **kw)),
    # all three OFF: must equal covex-v6-fair-final-cand-tl-sync (F0) digest for digest
    CAND_CF + "-off": (lambda **kw: make_cand_cf(CAND_CF + "-off", cf_forfeit_admit=False,
                                                 cf_resident_set=False, protect_defer=False,
                                                 cf_harm_arrivals=False, **kw)),
    # Step 4 negative control: admission live, future term forced to zero
    # D320 attribution: the OLD HARM (pending robot questions only) kept, everything else as the full arm
    CAND_CF + "-h0": (lambda **kw: make_cand_cf(CAND_CF + "-h0", cf_harm_arrivals=False, **kw)),
    # D324: the D320 window (service time only) kept for reproducibility
    # D331 attribution: the un-netted F1 (admission and S2 release may both act on a robot in one epoch;
    # the coincidences are only COUNTED and LOGGED)
    CAND_CF + "-nonet": (lambda **kw: make_cand_cf(CAND_CF + "-nonet", cf_s2_netting=False, **kw)),
    # D333 attribution: the claim held only while the released catch-up request is in flight
    CAND_CF + "-claimpiece": (lambda **kw: make_cand_cf(CAND_CF + "-claimpiece", cf_claim_scope="piece", **kw)),
    CAND_CF + "-w0": (lambda **kw: make_cand_cf(CAND_CF + "-w0", cf_window_mode="service", **kw)),
    CAND_CF + "-a0": (lambda **kw: make_cand_cf(CAND_CF + "-a0", cf_resident_set=False,
                                                cf_future_mode="zero", **kw)),
}


def register() -> List[str]:
    import arms as A
    clash = [n for n in ARMS_STEP3 if n in A.ARMS]
    if clash:                                                              # pragma: no cover
        raise RuntimeError("step-3 arms would REPLACE registered arm(s) %r" % (clash,))
    A.ARMS.update(ARMS_STEP3)
    return sorted(ARMS_STEP3)
