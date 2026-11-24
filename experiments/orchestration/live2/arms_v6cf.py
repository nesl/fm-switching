#!/usr/bin/env python3
"""covex-v6-cf-pd: the REQUEST and STATE counterfactual decisions and spec v6 section 7's
PROTECT-AND-DEFER compound, over EITHER rung-2 base, behind one switch, default off.

WHAT IS HERE AND WHAT IS NOT. Section 7 names three compounds and three decision kinds. This
module builds ONE compound - protect and defer - on TWO decision kinds:

    STATE leg    a background rebuild (a MATERIALIZE the base asked for this epoch) is HELD BACK
                 to its latest safe start, or sent as ONE CHUNK when its latest safe start is
                 already here, and the victim history is TOUCHED in the same decision.
    REQUEST leg  a pending recall query the base admitted CLOUD on a cold or partial history is
                 DEFERRED to its latest safe start (spec v6 section 7's request row), and the
                 victim history is TOUCHED in the same decision.

`keep-ready set`, `admit with protected victim` and `plan_sync` are NOT built. The mechanism -
the harm, the bar, the latest safe start and the decision - is `cf_protect_defer.py`; this file
is the arm that wires it to the harness and enacts it. Nothing in cf_* is reimplemented.

THE BASE IS A PARAMETER AND IS NOT HARDWIRED, because which rung-2 base exists is a CONTINGENCY
the user's addendum 9 item A fixes and this session does not know the outcome of:

    rung 2 will be EITHER covex-v6-state-shares (if it passes all three D179 (6) checks)
                     OR covex-v6-state-uo-c5attr (if shares fails any, as a logged override
                        of the D181 rule).

So BOTH variants are registered, `covex-v6-cf-pd-shares` and `covex-v6-cf-pd-c5attr`, each a
subclass of its own base built at registration time by `_class_for`; the bare name
`covex-v6-cf-pd` RAISES and names the contingency, for the reason `arm_names_v6.py` rule 3 gives:
a name that silently resolved to one of the two would run every cell and pass every proof while
containing a base nobody chose. HOW THE CHOICE IS MADE AT CELL TIME: the main session reads the
three D179 (6) pre-registered checks off the posted shares cells against the rule already
committed in `reports/study_c5_selection_rule.md`, and posts the matching variant's name. This
module makes no such choice and posts no cell list.

THE SWITCH is `live2_cf_protect_defer`, an arm-scoped INSTANCE attribute, default FALSE, and a
truthy CLASS attribute RAISES (`cf_protect_defer.arm_enables`, the established pattern of
`release_recheck.arm_enables` and `share_admission.arm_enables`). It is set on every object the
decide path can bind `self` to, for the reason `arms_v6shares.py` records: `V5Rules2Arm.__call__`
runs `HybridArm.__call__(self, obs)` with `self` being the wrapper and `V5Rules2Arm.decide` then
calls `self._base.decide`, so a reader that runs against the inner object sees the attribute only
if the attribute is there.

THE DEFICIT WEIGHT IS INJECTED AND IS NOT BUILT HERE. covex-v6-fair (another session, item B1 of
the same addendum) owns `w = 1 + 2.0 x shortfall` floored at 1. This arm takes `w_of` as a
callable and defaults it to the constant 1.0, so the component works and is testable before that
lands; `w_source` travels with every number, so a figure computed at the default can never be
read as a figure computed against live deficits.

WHERE THIS ARM IS REGISTERED, AND THE ONE THING IT CANNOT DO FOR ITSELF. `register()` puts the
names in live2's registry. The HARNESS process does not import this module: `run_live2_real.py`
imports `arms` and `hybrid` and nothing else, so for a LIVE cell two lines must be added to
`arms.py` beside the other v6 families, exactly as `arms_v6state`, `arms_v6fair`, `arms_v6c5` and
`arms_v6shares` are:

    from arms_v6cf import V6CF_ARMS                                     # noqa: E402
    ARMS.update(V6CF_ARMS)

`arms.py` is a shared file with another session's uncommitted edits in it at this commit, so this
session does NOT edit it: the two lines are reported for the main session to merge, and every
proof here calls `register()` itself, which is what the one-cell runners already do.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "v5"), str(HERE / "fleet"), str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cf_cost as CC                                                           # noqa: E402
import cf_objective as CO                                                      # noqa: E402
import cf_protect_defer as PD                                                  # noqa: E402
from interface import Action, Observation, SessionAction                        # noqa: E402

V6CF_VERSION = "covex-v6-cf-pd-1.0"

# D152 (3) / D170: the engine's context limit. A request above it is REJECTED by the base and
# cannot be harmed by a queue delay, so it is not an `others` row.
#
# D223 (2): READ AT DECISION TIME, from the one module that holds the run's limit. What stood here
# was `from hybrid.hybrid_arm import CONTEXT_LIMIT_TOKENS` behind a bare `except Exception` that
# retyped `32768`, and it had both faults the ruling names: a VALUE bound at import, which no
# run-start read could reach, and a silent fallback that would have made a 0.5x cell plan against
# 32,768 while the engine served 31,472. `arms_v6cfr3.py` reads `VCF.CONTEXT_LIMIT_TOKENS`, so the
# live module attribute is kept here too and resolves through the same one call.
import context_limit as CL                                                     # noqa: E402


def __getattr__(name):
    if name == "CONTEXT_LIMIT_TOKENS":
        return CL.limit_tokens()
    raise AttributeError(name)

# The two candidate rung-2 bases of the addendum 9 item A contingency.
BASES: Dict[str, Dict[str, str]] = {
    "shares": {"module": "arms_v6shares", "cls": "V6StateSharesArm",
               "base_arm": "covex-v6-state-shares",
               "why": "D179 share admission plus deadline-aware release re-check"},
    "c5attr": {"module": "arms_v6c5", "cls": "V6StateUoC5AttrArm",
               "base_arm": "covex-v6-state-uo-c5attr",
               "why": "the C5 attribution rule, the logged-override fallback if shares fails"},
}
CONTINGENCY = (
    "addendum 9 item A, 2026-11-22: rung 2 is EITHER covex-v6-state-shares (if it passes all "
    "three D179 (6) checks) OR covex-v6-state-uo-c5attr (if shares fails any, as a logged "
    "override of the D181 rule). The selection rule is committed in "
    "reports/study_c5_selection_rule.md and is read off the posted shares cells at cell time.")


class BaseNotChosen(RuntimeError):
    """The bare rung-4 name was asked for while the rung-2 base is still a contingency."""


class _ProtectDeferMixin:
    """The one added channel. Mixed in FRONT of a rung-2 base, so `super()` is that base."""

    def __init__(self, name: str, *,
                 protect_defer: bool = True,
                 device_answers: bool = False,
                 w_of: Optional[Callable[[str], float]] = None,
                 w_source: Optional[str] = None,
                 bar_reading: str = PD.WEIGHT_ON_BAR_DEFAULT,
                 control_harm_zero: bool = False,
                 control_margin_huge: bool = False,
                 **kw: Any) -> None:
        super().__init__(name=name, **kw)
        self.arm_version = V6CF_VERSION
        self.pd_base_key = str(getattr(type(self), "_pd_base_key", "?"))
        self._pd_w_of = w_of or PD.default_w_of
        self._pd_w_source = w_source or (PD.W_SOURCE_DEFAULT if w_of is None else
                                         "injected callable supplied by the caller")
        if bar_reading not in PD.WEIGHT_ON_BAR_READINGS:
            raise ValueError("unknown bar reading %r" % (bar_reading,))
        self._pd_bar_reading = str(bar_reading)
        # CLAUDE.md Step 4. Both controls are NAMED ARMS, so the control is a cell and not a code
        # edit, which is the arms_v6shares precedent.
        self._pd_control_harm_zero = bool(control_harm_zero)
        self._pd_control_margin_huge = bool(control_margin_huge)
        self.pd_harms: List[float] = []
        self.pd_decisions: List[Dict[str, Any]] = []
        self.pd_trace_kept: Optional[Dict[str, Any]] = None
        self.pd_trace_crossed: Optional[Dict[str, Any]] = None
        # D218 (1), the addendum of 2026-11-23: the PREDICTED TRADE of every denial, recorded AT
        # the denial. UNCAPPED, unlike `pd_decisions`: a denial is a characteristic decision and
        # there are tens of them, so none of them is dropped to a cap.
        self.pd_device_trades: List[Dict[str, Any]] = []
        self._pd_trace_device: Optional[Dict[str, Any]] = None
        self._pd_gpu_kv_tokens: Optional[float] = None
        self._pd_rows_key: Any = None
        self._pd_rows: List[Dict[str, Any]] = []
        for obj in self._pd_targets():
            setattr(obj, PD.SWITCH_ATTR, bool(protect_defer))
            # The third request candidate is a SEPARATE switch on the same chain of objects, for
            # the same reason: `V5Rules2Arm.decide` calls `self._base.decide`, so a reader that
            # runs against the inner object sees the attribute only if the attribute is there.
            setattr(obj, PD.DEVICE_ANSWERS_SWITCH_ATTR, bool(device_answers))

    # ---- the switch, on every object the decide path can bind `self` to -----------------------
    def _pd_targets(self) -> List[Any]:
        out: List[Any] = []
        o: Any = self
        seen = set()
        while o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append(o)
            o = o.__dict__.get("_rules") or o.__dict__.get("_base")
        return out

    def pd_switch_report(self) -> Dict[str, Any]:
        """What the switch reads as on EVERY object of the chain, and with what type. A single
        getattr on the wrapper is the check that passes while the inner object decides
        differently."""
        return {"attr": PD.SWITCH_ATTR,
                "chain": [{"class": type(o).__name__,
                           "declared_on_instance": PD.SWITCH_ATTR in vars(o),
                           "value": vars(o).get(PD.SWITCH_ATTR),
                           "type": type(vars(o).get(PD.SWITCH_ATTR)).__name__}
                          for o in self._pd_targets()],
                "arm_enables": PD.arm_enables(self),
                # D218 (1): the SECOND switch, read back the same way and on the same chain. A
                # single getattr on the wrapper is the check that passes while the inner object
                # decides differently, and that applies to this switch exactly as to the first.
                "device_answers": {
                    "attr": PD.DEVICE_ANSWERS_SWITCH_ATTR,
                    "chain": [{"class": type(o).__name__,
                               "declared_on_instance": (
                                   PD.DEVICE_ANSWERS_SWITCH_ATTR in vars(o)),
                               "value": vars(o).get(PD.DEVICE_ANSWERS_SWITCH_ATTR),
                               "type": type(vars(o).get(
                                   PD.DEVICE_ANSWERS_SWITCH_ATTR)).__name__}
                              for o in self._pd_targets()],
                    "arm_enables": PD.device_answers_enabled(self)}}

    # ---- the one input the scrubbed Observation does not carry --------------------------------
    def live2_configure(self, **kw: Any) -> None:
        # The GPU KV pool size is a configured INPUT (D56: capacities are inputs, not constants).
        # Captured here rather than retyped, so the eviction test cannot drift from the cell.
        if "gpu_kv_tokens" in kw:
            self._pd_gpu_kv_tokens = float(kw["gpu_kv_tokens"])
        super().live2_configure(**kw)

    # ---- the harm population -----------------------------------------------------------------
    def _pd_others(self, obs: Observation, exclude_session: str) -> List[Dict[str, Any]]:
        """Every PENDING DEADLINE REQUEST of another device, as a harm row.

        THE THREE DEADLINE TYPES OF SPEC v6 SECTION 2, and both of the two sources the arm has:

          alert        one row per alert device with a pending instant, from the roster's
                       `sh_instant` (the coordinator's own choice of the instant it will act on,
                       with that instant's ABSOLUTE deadline). Its token count is NOT observable,
                       so the service time is predicted from the MEASURED median uncached tokens
                       of an EP-G dashcam request; `cf_protect_defer.PROXIES` states the proxy and
                       what it is and is not valid for.
          recall and   one row per query in `obs.recall` of another session, at ITS OWN
          assistance   readiness tokens and its own absolute deadline.

        An over-limit query is EXCLUDED: the base REJECTS it, so it never reaches the engine and a
        queue delay cannot cost it anything (D175 (1): only a DELIVERED cloud answer replaces the
        device's, and a refused request never does).

        Built ONCE PER EPOCH and filtered per rebuild, like rung 2's `_queued_behind`, because the
        pending set does not change inside one decision period.
        """
        # KEYED ON THE DECISION PERIOD, NOT ON `id(obs)`. Rung 2's `_queued_behind` caches under
        # `id(obs)` - a MEMORY ADDRESS - which CPython reuses, so a new Observation landing where
        # the last one was leaves the previous epoch's rows in the cache. That makes a rung-2
        # arm's decisions depend on allocation history, and it is the best candidate this session
        # found for the documented open defect "dry decisions do not reproduce across runs"
        # (measured: `cf_pd_one_cell.py --diag-epoch-cache-key`). The file is another session's,
        # so the finding is reported rather than fixed; this cache does not repeat the pattern.
        key = (float(obs.now_s), int(len(obs.recall or ())))
        if self._pd_rows_key != key:
            self._pd_rows_key = key
            cf = self._cf_engine()
            roster = getattr(self._rules, "_roster", None) or {}
            devs = roster.get("devices") or {}
            sdev = roster.get("session_device") or {}
            built = roster.get("built_tokens_by_session") or {}
            ss_types = getattr(self._rules, "_ss_types", None) or frozenset()
            rows: List[Dict[str, Any]] = []
            for did, inst in (roster.get("sh_instant") or {}).items():
                if str((devs.get(did) or {}).get("type")) != "dashcam":
                    continue
                pr = CC.predict(cf.model, int(PD.ALERT_UNCACHED_TOKENS), 0, 0, 0)
                rows.append({"req_id": str(inst.get("opportunity_id")), "device_id": str(did),
                             "session_id": None, "qtype": "alert",
                             # D222 (1) item 1: the row's own UNCACHED PROMPT tokens, published so
                             # the question-deferral leg can sum the queued-ahead WORK instead of
                             # passing a literal zero. For an alert it is the measured EP-G median
                             # (`cf_protect_defer.PROXIES`), the same number this row's engine_s is
                             # already predicted from, so no new quantity enters here.
                             "u_tokens": int(PD.ALERT_UNCACHED_TOKENS),
                             "engine_s": float(pr.engine_s),
                             "slack_s": (float(inst.get("deadline_abs", obs.now_s))
                                         - float(obs.now_s)),
                             # the measured EP-G append first token is inside the 1 s deadline at
                             # every episode position (v5/cf_objective.py DeviceLatency note)
                             "p_device_on_time": 1.0})
            for qy in (obs.recall or ()):
                tok = int(getattr(qy, "readiness_tokens", 0) or 0)
                if tok > CL.limit_tokens():
                    self.stats["pd_other_skipped_over_limit"] += 1
                    continue
                unc = max(tok - int(built.get(str(qy.session_id), 0) or 0), 0)
                pr = CC.predict(cf.model, unc, 0, 0, 0)
                qtype = ("assistance" if str(getattr(qy, "category", "")) in ss_types
                         else "recall")
                slack = float(qy.deadline_s) - float(obs.now_s)
                rows.append({"req_id": str(qy.query_id),
                             "device_id": str(sdev.get(str(qy.session_id), "")),
                             "session_id": str(qy.session_id), "qtype": qtype,
                             # D222 (1) item 1: the SAME `unc` this row's engine_s is predicted
                             # from, published rather than recomputed, so the queued-ahead work
                             # and the row's own price can never disagree.
                             "u_tokens": int(unc),
                             "engine_s": float(pr.engine_s), "slack_s": slack,
                             "p_device_on_time": float(CO.p_device_on_time(
                                 max(slack, 0.0),
                                 kind=("single_shot" if qtype == "assistance" else "robot"),
                                 question_id=getattr(qy, "question_id", None)))})
            self._pd_rows = rows
        return [r for r in self._pd_rows if r["session_id"] != str(exclude_session)]

    def _pd_victim(self, obs: Observation, exclude_session: str) -> Optional[Dict[str, Any]]:
        """H: the warm recall history R's allocation would evict before ITS expected question.

        The earliest expected question wins, because that is the one an eviction destroys first.
        The question estimate is the rules arm's own causal EWMA (D11, D48), through rung 2's
        `_p_question`, KEYED BY DEVICE - keying it on the session returns a miss for every
        session, which is the defect `arms_v6state.py` records.
        """
        roster = getattr(self._rules, "_roster", None) or {}
        devs = roster.get("devices") or {}
        sdev = roster.get("session_device") or {}
        built = roster.get("built_tokens_by_session") or {}
        best: Optional[Dict[str, Any]] = None
        for sid in (obs.cloud.gpu_warm_sessions or ()):
            if str(sid) == str(exclude_session):
                continue
            did = sdev.get(str(sid))
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            q = self._p_question(str(did), float(obs.now_s))
            if not q["has_estimate"]:
                continue
            dt = float(q["next_question_s"]) - float(obs.now_s)
            if dt > PD.STATE_HORIZON_S:
                continue
            cand = {"session_id": str(sid), "device_id": str(did),
                    "next_question_in_s": dt, "p_question": float(q["p_question"]),
                    "warm_tokens": int(built.get(str(sid), 0) or 0)}
            if best is None or cand["next_question_in_s"] < best["next_question_in_s"]:
                best = cand
        return best

    def _pd_free_kv(self, obs: Observation) -> float:
        """Free GPU KV tokens, from the ENGINE METRIC and the RESIDENCY BELIEF, whichever is
        tighter.

        THIS IS NOT BELT AND BRACES, IT IS THE ONLY WAY THE GATE IS REACHABLE AT ALL, and the
        measurement that says so is in this component's own proofs. `obs.cloud.gpu_kv_fraction`
        is the engine's KV-usage gauge. CORRECTED 2026-11-23: this line previously said
        `vllm:gpu_cache_usage_perc` READ OFF THE LIVE SERVER. BOTH HALVES WERE WRONG. This engine
        emits `vllm:kv_cache_usage_perc` and NO `vllm:gpu_cache_usage_perc` (H100 probe,
        frozen_test/engine_probe_hit26/) - BUT THAT DOES NOT MAKE A READ KEYED ON THE OLDER NAME
        WRONG, AND THIS NOTE WAS INCOMPLETE UNTIL 2026-11-24: the scrape path reads EITHER spelling
        (`live/adapter.py:204` `KV_KEYS`) and REPUBLISHES under `vllm:gpu_cache_usage_perc`
        (`:205` `KV_CANONICAL_KEY`, aliasing counted by `n_kv_key_aliased`) precisely so that no
        reader has to change. So `cstate.py`'s read of the canonical name is CORRECT BY DESIGN and
        MUST NOT BE 'FIXED'. The first version of this correction stated the engine fact without the
        aliasing, which would lead a reader to change a correct read - the same incompleteness, in the
        opposite direction, as the wording it replaced; and it was NOT read off the live server either, because
        live2 NEVER SCRAPED /metrics AT ALL - `AsyncLive2Backend` is not an `HttpBackend` subclass
        and contains no `/metrics` string, so the field was IDENTICALLY 0.0 in LIVE cells too, not
        only dry ones. D216 (2) adds the scrape; until its wiring lands this gate reads 0.0 live. In a DRY cell
        there is no server, `self.metrics` is empty and the field is IDENTICALLY 0.0, measured:
        free_kv_min = free_kv_max = 62,944 over 77 decisions on a 300 s dry cell. A gate whose
        input is a constant cannot test anything (CLAUDE.md Step 2), and a null from it would be
        UNEXERCISED and not a negative.

        The residency BELIEF is the second source spec v6 section 3 names for exactly this input
        ("coordinator bookkeeping corrected by engine telemetry", D44, D47, D150), and it is
        available dry: `obs.cloud.gpu_warm_sessions` is the believed-GPU set (`cstate.py:619`,
        the argmax of each session's belief) and `built_tokens_by_session` is how much of each
        history the cloud has built. So occupancy is estimated both ways and the LARGER is taken,
        which is the pessimistic one and therefore the one that does not let a rebuild through on
        a missing signal. `pd_kv_bound_by_*` records which bound, every decision.

        WHAT IT STILL UNDERSTATES, stated rather than left to be discovered: alert episode
        contexts occupy the same pool and are not recall sessions, so they are not in
        `built_tokens_by_session` and this estimate does not count them. The engine metric does
        count them, and live it is the one that will bind.
        """
        pool = self._pd_gpu_kv_tokens
        if pool is None:
            self.stats["pd_no_kv_pool_configured"] += 1
            return 0.0
        frac = float(getattr(obs.cloud, "gpu_kv_fraction", 0.0) or 0.0)
        occ_metric = frac * float(pool)
        built = (getattr(self._rules, "_roster", None) or {}).get(
            "built_tokens_by_session") or {}
        occ_belief = float(sum(int(built.get(str(s), 0) or 0)
                               for s in (obs.cloud.gpu_warm_sessions or ())))
        if occ_belief >= occ_metric:
            self.stats["pd_kv_bound_by_belief"] += 1
        else:
            self.stats["pd_kv_bound_by_engine_metric"] += 1
        return max(float(pool) - max(occ_metric, occ_belief), 0.0)

    # ---- the decision ------------------------------------------------------------------------
    # Step 4, second direction. It scales THE BAR AND ONLY THE BAR. The first version scaled the
    # deficit WEIGHT instead and was broken: every harm row carries that same weight, so harm and
    # bar scaled together, the ratio was unchanged and the control reproduced the treatment's
    # digest exactly with 17 deferrals at a bar of 6.6e8. See cf_protect_defer.bar's docstring.
    MARGIN_CONTROL_SCALE = 1e9

    def _pd_one(self, obs: Observation, *, kind: str, decider_device_id: str,
                session_id: str, u_rebuild: int, deadline_abs_s: Optional[float],
                chunk_tokens: Optional[int],
                query_id: Optional[str] = None) -> Dict[str, Any]:
        cf = self._cf_engine()
        others = self._pd_others(obs, session_id)
        victim = self._pd_victim(obs, session_id)
        pred = CC.predict(cf.model, int(u_rebuild), 0, 0, 0)
        res = cf.residuals
        n_alert = sum(1 for r in others if r["qtype"] == "alert")
        d = PD.decide(decider_device_id=str(decider_device_id), now_s=float(obs.now_s),
                      alert_active=bool(n_alert > 0), n_alert_pending=n_alert,
                      u_rebuild=int(u_rebuild), free_kv_tokens=self._pd_free_kv(obs),
                      victim=victim, others=others,
                      deadline_abs_s=deadline_abs_s, pred=pred,
                      chunk_tokens=chunk_tokens,
                      p_on_time=(lambda eng, slack: float(CC.p_on_time(res, eng, slack))),
                      w_of=self._pd_w_of,
                      w_source=self._pd_w_source, bar_reading=self._pd_bar_reading,
                      # Step 4, first direction: the mechanism under test is the HARM, so the
                      # control sets it to zero AT ITS SOURCE rather than switching the component
                      # off. 1.0 on every scorable path.
                      harm_scale=(0.0 if self._pd_control_harm_zero else 1.0),
                      margin_scale=(self.MARGIN_CONTROL_SCALE
                                    if self._pd_control_margin_huge else 1.0),
                      # D218 (1). The read of the second switch, at the point it changes a
                      # decision rather than where it is set.
                      device_answers=PD.device_answers_enabled(self))
        d["kind"] = kind
        d["session_id"] = str(session_id)
        d["query_id"] = (str(query_id) if query_id is not None else None)
        d["controls"] = {"harm_zero": self._pd_control_harm_zero,
                         "margin_huge": self._pd_control_margin_huge}
        self._pd_record(d)
        return d

    def _pd_record(self, d: Dict[str, Any]) -> None:
        st = self.stats
        st["pd_decisions"] += 1
        st["pd_decisions_" + str(d.get("kind"))] += 1
        st["pd_gate_" + str(d.get("gate"))] += 1
        # The EVICTION gate's own two inputs, always, because "the gate was never reached" and
        # "the gate was reached and the pool was always roomy" are different diagnoses and only
        # the distributions tell them apart.
        u, fk = int(d.get("u_rebuild", 0)), float(d.get("free_kv_tokens", 0.0))
        st["pd_u_max"] = max(int(st.get("pd_u_max", 0)), u)
        st["pd_u_sum"] += u
        st["pd_free_kv_min"] = min(int(st.get("pd_free_kv_min", 10 ** 9)), int(fk))
        st["pd_free_kv_max"] = max(int(st.get("pd_free_kv_max", 0)), int(fk))
        st["pd_free_kv_sum"] += int(fk)
        if d.get("victim"):
            st["pd_victim_found"] += 1
        # a compact per-decision record, capped, so the harm distribution and the gate mix can be
        # re-derived from one cell without keeping every harm row
        if len(self.pd_decisions) < 4000:
            self.pd_decisions.append({
                "t": d.get("now_s"), "kind": d.get("kind"), "gate": d.get("gate"),
                "action": d.get("action"), "u": u, "free_kv": fk,
                "harm": d.get("harm_value"), "bar": d.get("bar_value"),
                "crosses_bar": d.get("crosses_bar"),
                "deferral_s": d.get("deferral_s"), "chunk_tokens": d.get("chunk_tokens"),
                "n_alert_pending": d.get("n_alert_pending")})
        if "harm_value" in d:
            h = float(d["harm_value"])
            self.pd_harms.append(h)
            st["pd_harm_n"] += 1
            st["pd_harm_micro_sum"] += int(round(h * 1e6))
            st["pd_harm_micro_max"] = max(int(st.get("pd_harm_micro_max", 0)),
                                          int(round(h * 1e6)))
            if h <= 0.0:
                st["pd_harm_zero"] += 1
            for lo in (0.0, 0.01, 0.1, PD.MARGIN_CF_ON_TIME, 1.0, 2.0, 5.0):
                if h > lo:
                    st["pd_harm_gt_%s" % ("%g" % lo).replace(".", "p")] += 1
            if d.get("crosses_bar"):
                st["pd_harm_over_bar"] += 1
        # The one traced unit (CLAUDE.md Step 3): the FIRST decision that ACTED, kept whole. The
        # first decision that CROSSED THE BAR is kept separately, because when no decision acts
        # that is the informative unit and a trace of a decision that never reached the harm
        # would say nothing about the mechanism.
        if self.pd_trace_kept is None and str(d.get("action")) != "BASE":
            self.pd_trace_kept = d
        if self.pd_trace_crossed is None and bool(d.get("crosses_bar")):
            self.pd_trace_crossed = d
        # D218 (1) addendum: the per-denial trade, recorded AT the denial. The record is kept for
        # the decision that FIRED; a declined trade is counted by its gate and is not a denial.
        tr = d.get("device_answers_trade")
        if tr is not None and str(d.get("action")) == "DEVICE_ANSWERS":
            self.pd_device_trades.append({
                "t": d.get("now_s"), "kind": d.get("kind"),
                "decider_device_id": d.get("decider_device_id"),
                "session_id": d.get("session_id"),
                "query_id": d.get("query_id"),
                "u_rebuild": d.get("u_rebuild"),
                "free_kv_tokens": d.get("free_kv_tokens"),
                "n_alert_pending": d.get("n_alert_pending"),
                "victim_session_id": (d.get("victim") or {}).get("session_id"),
                "trade": tr})
            if self._pd_trace_device is None:
                self._pd_trace_device = d

    def decide(self, obs: Observation) -> Action:
        act = super().decide(obs)
        if not PD.arm_enables(self):
            return act
        g = self._rules.guard_state(obs)
        if g["active"]:
            # Spec v6 section 7, "healthy regime only": if the guard is active the counterfactual
            # defers to it. The same obligation rung 2 and v5-full carry.
            self.stats["pd_deferred_to_guard_epochs"] += 1
            return act
        roster = getattr(self._rules, "_roster", None) or {}
        sdev = roster.get("session_device") or {}
        devs = roster.get("devices") or {}
        built = roster.get("built_tokens_by_session") or {}
        chunk = getattr(self._rules, "chunk_tokens", None) or \
            getattr(self._rules, "slice_tokens", None)
        protect: Dict[str, Dict[str, Any]] = {}
        drop: set = set()
        chunk_now: Dict[str, int] = {}
        # ---- STATE leg: the rebuilds the base asked for this epoch ---------------------------
        for sa in list(act.sessions or ()):
            if str(getattr(sa, "action", "")) != "MATERIALIZE":
                continue
            sid = str(sa.session_id)
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            u = max(int(getattr(sa, "target_tokens", 0) or 0)
                    - int(built.get(sid, 0) or 0), 0)
            if getattr(sa, "slice_tokens", None) is not None:
                u = min(u, int(sa.slice_tokens))
            nxt = self._p_question(str(did), float(obs.now_s))
            d = self._pd_one(obs, kind="state", decider_device_id=str(did), session_id=sid,
                             u_rebuild=u,
                             deadline_abs_s=(float(nxt["next_question_s"])
                                             if nxt["has_estimate"] else None),
                             chunk_tokens=(int(chunk) if chunk else None))
            if d["action"] == "PROTECT_AND_DEFER":
                drop.add(sid)
                self.stats["pd_state_defers"] += 1
            elif d["action"] == "PROTECT_AND_CHUNK":
                chunk_now[sid] = int(d["chunk_tokens"])
                self.stats["pd_state_chunks"] += 1
            else:
                continue
            v = d.get("victim") or {}
            if v.get("session_id"):
                protect[str(v["session_id"])] = v
        # ---- REQUEST leg: a cold admission the base made this epoch --------------------------
        for ra in list(act.recall or ()):
            if str(getattr(ra, "decision", "")) != "CLOUD":
                continue
            qy = next((q for q in (obs.recall or ()) if str(q.query_id) == str(ra.query_id)), None)
            if qy is None:
                continue
            sid = str(qy.session_id)
            did = sdev.get(sid)
            if did is None or str((devs.get(did) or {}).get("type")) != "robot":
                continue
            u = max(int(getattr(qy, "readiness_tokens", 0) or 0)
                    - int(built.get(sid, 0) or 0), 0)
            d = self._pd_one(obs, kind="request", decider_device_id=str(did), session_id=sid,
                             u_rebuild=u, deadline_abs_s=float(qy.deadline_s),
                             # a request has no chunk channel: a query is one prompt
                             chunk_tokens=None,
                             query_id=str(ra.query_id))
            if d["action"] == "DEVICE_ANSWERS":
                # D218 (1). THE THIRD CHANNEL, and the one the measured 27 decisions needed.
                # `DEVICE` is a registered value of `interface.RECALL_ACTIONS` and is READ at
                # `coordinator.py:863`, which declines the opportunity and records the device as
                # the answerer, so this is a channel the harness carries rather than a field
                # written and never read. `representation` is left as the base set it: the
                # coordinator's DEVICE branch does not read it, and `validate_action` constrains
                # the representation only on a CLOUD decision.
                #
                # THE VICTIM IS NOT PROTECTED ON THIS BRANCH, deliberately and stated rather
                # than left to be noticed. The deviation is that the rebuild never happens, so
                # there is nothing left to evict H and a KEEP_GPU_WARM would be a SECOND
                # mechanism riding on the ruled one. D218 (1) rules the device deviation and
                # nothing else.
                ra.decision = "DEVICE"
                self.stats["pd_request_device_answers"] += 1
                continue
            if d["action"] != "PROTECT_AND_DEFER":
                if d.get("device_answers_trade") is not None:
                    # the channel EXISTS and the trade was declined: a decision, not an absent
                    # channel, and it is counted as neither of the other two
                    self.stats["pd_request_device_declined"] += 1
                elif d.get("crosses_bar"):
                    # the harm cleared the bar and no channel of THIS compound could express the
                    # deviation; counted, never silently dropped
                    self.stats["pd_request_crossed_bar_unexpressible"] += 1
                    if d.get("device_answers_unpriceable"):
                        self.stats["pd_request_device_no_p_self"] += 1
                continue
            # THE CHANNEL. `defer_s` is READ at coordinator.py:785 (`o.defer_until = t +
            # defer_s`), which is what withholds the opportunity until the latest safe start and
            # then re-decides it (amendment 2, D90). `representation` is left exactly as the base
            # set it: the DEFER branch returns before the submit path, and the opportunity is
            # decided afresh when it is re-offered.
            ra.decision = "DEFER"
            ra.defer_s = float(d["deferral_s"])
            self.stats["pd_request_defers"] += 1
            v = d.get("victim") or {}
            if v.get("session_id"):
                protect[str(v["session_id"])] = v
        # ---- enactment -----------------------------------------------------------------------
        if drop:
            act.sessions = [sa for sa in (act.sessions or ())
                            if not (str(sa.session_id) in drop
                                    and str(getattr(sa, "action", "")) == "MATERIALIZE")]
        for sa in (act.sessions or ()):
            if str(getattr(sa, "action", "")) == "MATERIALIZE" and str(sa.session_id) in chunk_now:
                sa.slice_tokens = int(chunk_now[str(sa.session_id)])
        taken = {str(sa.session_id) for sa in (act.sessions or ())}
        extra: List[Any] = []
        for sid in protect:
            if sid in taken:
                self.stats["pd_protect_unexpressible_session_busy"] += 1
                continue
            extra.append(SessionAction(session_id=sid, action="KEEP_GPU_WARM"))
            self.stats["pd_protects"] += 1
        if extra:
            act.sessions = list(act.sessions or ()) + extra
        return act

    # ---- reporting ---------------------------------------------------------------------------
    def pd_harm_distribution(self) -> Dict[str, Any]:
        v = sorted(float(x) for x in self.pd_harms)
        if not v:
            return {"n": 0, "note": "no decision reached the harm computation"}
        def q(p: float) -> float:
            return v[min(int(p * (len(v) - 1)), len(v) - 1)]
        return {"n": len(v), "min": v[0], "p25": q(0.25), "median": q(0.5), "p75": q(0.75),
                "p90": q(0.9), "max": v[-1],
                "n_zero": sum(1 for x in v if x <= 0.0),
                "n_distinct": len(set(round(x, 9) for x in v)),
                "bar_at_w1": PD.MARGIN_CF_ON_TIME,
                "n_over_bar_at_w1": sum(1 for x in v if x > PD.MARGIN_CF_ON_TIME)}

    def pd_device_trade_report(self) -> Dict[str, Any]:
        """D218 (1) addendum: every denial's PREDICTED TRADE, plus the totals.

        THE EXPLICIT ZERO IS THE POINT OF THE FIXED TYPE LIST. A type that never appears among the
        devices saved is a finding about WHERE the mechanism acts, so all three types are present
        in every total with a value of 0.0 rather than omitted.
        """
        tr = [dict(x) for x in self.pd_device_trades]
        tot = {t: 0.0 for t in PD.HARM_TYPES}
        moved = {t: 0 for t in PD.HARM_TYPES}
        own = saved = net = 0.0
        resid = 0.0
        outside: Dict[str, float] = {}
        for x in tr:
            t = x.get("trade") or {}
            for k in PD.HARM_TYPES:
                tot[k] += float((t.get("saved_on_time_answers_by_type") or {}).get(k, 0.0))
                moved[k] += int((t.get("n_moved_by_type") or {}).get(k, 0))
            for k, v in (t.get("types_outside_the_declared_three") or {}).items():
                outside[k] = outside.get(k, 0.0) + float(v)
            own += float(t.get("own_lost_weighted_p_on_time", 0.0))
            saved += float(t.get("saved_total", 0.0))
            net += float(t.get("net", 0.0))
            resid = max(resid, abs(float(
                t.get("by_type_sum_residual_against_unscaled", 0.0))))
        holds = all(bool(x.get("trade", {}).get("by_type_sum_holds", True)) for x in tr)
        return {
            "_register": ("PREDICTED at decision time from the committed D162 price and the "
                          "committed on-time curve, NOT observed: a dry cell has no engine, so "
                          "no denial's realised outcome exists to be measured."),
            "_units": ("counts of expected on-time cloud answers, each device weighted by its "
                       "per-device w_d (D191 (2)); no division by the number served"),
            "n_denials": len(tr),
            "totals": {
                "own_lost_weighted_p_on_time": own,
                "saved_on_time_answers_by_type": tot,
                "saved_total": saved,
                "net": net,
                "n_requests_moved_by_type": moved,
                "types_outside_the_declared_three": outside,
                "types_with_zero_saved": sorted(k for k, v in tot.items() if v == 0.0),
            },
            "by_type_sum_identity": {
                "claim": ("the by-type breakdown sums to the harm term compared against the bar, "
                          "because harm_by_type accumulates the same rows whose value_lost sums "
                          "to the total, and harm_scale is 1.0 on every scorable path"),
                "worst_abs_residual_over_denials": resid,
                "residual_cause": ("cf_objective rounds each harm row's value_lost to 9 decimals "
                                   "while accumulating the total unrounded; the per-denial "
                                   "tolerance is 5e-10 x n_harm_rows and travels with each "
                                   "record"),
                "holds": bool(holds),
            },
            "per_denial": tr,
        }

    def live2_describe(self) -> Dict[str, Any]:
        d = dict(super().live2_describe())
        d.update(arm=self.name, arm_version=V6CF_VERSION,
                 covex_v6_cf=dict(
                     compound="protect and defer (spec v6 section 7, D165 (D))",
                     decision_kinds=["request", "state"],
                     device_answers=dict(
                         enabled=PD.device_answers_enabled(self),
                         attr=PD.DEVICE_ANSWERS_SWITCH_ATTR,
                         candidate=("spec v6 section 7's THIRD request candidate, 'leave to the "
                                    "device', built under D218 (1)"),
                         rule=PD.DEVICE_ANSWERS_RULE,
                         sign_source=PD.DEVICE_ANSWERS_SIGN_SOURCE,
                         n_denials=len(self.pd_device_trades)),
                     not_built=["keep-ready set", "admit with protected victim", "plan_sync"],
                     base=dict(BASES[self.pd_base_key], key=self.pd_base_key),
                     contingency=CONTINGENCY,
                     switch=self.pd_switch_report(),
                     mechanism="experiments/orchestration/live2/cf_protect_defer.py",
                     margin=dict(value=PD.MARGIN_CF_ON_TIME,
                                 source=PD.MARGIN_CF_ON_TIME_SOURCE),
                     bar_reading=self._pd_bar_reading,
                     w_source=self._pd_w_source,
                     kappa=PD.KAPPA_INFO,
                     controls=dict(harm_zero=self._pd_control_harm_zero,
                                   margin_huge=self._pd_control_margin_huge),
                     harm_distribution=self.pd_harm_distribution()))
        return d


_CLASS_CACHE: Dict[str, Any] = {}


def _class_for(base_key: str) -> Any:
    """Build the arm class over one of the two candidate bases, at registration time."""
    if base_key in _CLASS_CACHE:
        return _CLASS_CACHE[base_key]
    spec = BASES[base_key]
    base = getattr(importlib.import_module(spec["module"]), spec["cls"])
    cls = type("V6CfProtectDefer_" + base_key, (_ProtectDeferMixin, base),
               {"_pd_base_key": base_key,
                "__doc__": "protect-and-defer over %s (%s)" % (spec["base_arm"], spec["why"])})
    _CLASS_CACHE[base_key] = cls
    return cls


def _not_chosen(**_kw: Any) -> Any:
    raise BaseNotChosen(
        "covex-v6-cf-pd names a rung-4 arm whose RUNG-2 BASE is still a contingency, so it must "
        "not resolve to either candidate. %s Ask for covex-v6-cf-pd-shares or "
        "covex-v6-cf-pd-c5attr by name." % CONTINGENCY)


def _arms() -> Dict[str, Any]:
    out: Dict[str, Any] = {"covex-v6-cf-pd": _not_chosen}
    for key in BASES:
        n = "covex-v6-cf-pd-" + key
        out[n] = (lambda _k=key, _n=n, **kw: _class_for(_k)(name=_n, **kw))
        # CLAUDE.md Step 4, as NAMED ARMS so each control is a cell and not a code edit.
        out[n + "-off"] = (lambda _k=key, _n=n, **kw: _class_for(_k)(
            name=_n + "-off", protect_defer=False, **kw))
        out[n + "-harmzero"] = (lambda _k=key, _n=n, **kw: _class_for(_k)(
            name=_n + "-harmzero", control_harm_zero=True, **kw))
        out[n + "-bigmargin"] = (lambda _k=key, _n=n, **kw: _class_for(_k)(
            name=_n + "-bigmargin", control_margin_huge=True, **kw))
        # the WRONG weight-on-bar reading, reachable only so the sign reversal can be measured
        out[n + "-barmaxharmed"] = (lambda _k=key, _n=n, **kw: _class_for(_k)(
            name=_n + "-barmaxharmed", bar_reading="max_harmed", **kw))
    return out


V6CF_ARMS: Dict[str, Any] = _arms()

# ---------------------------------------------------------------------------------------------
# D232 (2): `covex-v6-final-nqd` AND THE DEVICE_ANSWERS FAMILY, ON THE NORMAL IMPORT PATH.
#
# `run_live2_real.py` imports `arms` and `hybrid` and nothing else, and reaches the arm through
# `arms.make_arm`. `arms.py` already does `from arms_v6cf import V6CF_ARMS; ARMS.update(...)`, so
# a key added here exists in the harness's process. A name registered only in
# `arms_v6cf_device.register()` does not, and a posted cell list would die at launch - the same
# registration gap that made eleven `covex-v6-cf-pd` arms invisible and that D208 fixed for the
# final ladder with exactly this lazy shape.
#
# THE FACTORIES ARE LAZY because `arms_v6cf_device` imports THIS module, so a module-level import
# of it here would be a circular import and would fail. The import happens inside each factory at
# CALL time. Nothing is imported at registration time.
DEVICE_ANSWERS_LAZY_NAMES = (
    # D232 (2), the reshaped rung 4 and its bars
    "covex-v6-final-nqd",
    "covex-v6-final-nqd-off",
    "covex-v6-final-nqd-daoff",
    "covex-v6-final-nqd-harm0",
    "covex-v6-final-nqd-margin-huge",
    # D218 (1), kept so its dry proofs reproduce
    "covex-v6-final-da",
    "covex-v6-final-da-off",
    "covex-v6-final-da-harm0",
    "covex-v6-final-da-margin-huge",
)


def _device_answers_lazy() -> Dict[str, Any]:
    """One lazy factory per DEVICE_ANSWERS arm, each importing its module at CALL time."""
    out: Dict[str, Any] = {}
    for _n in DEVICE_ANSWERS_LAZY_NAMES:
        def _f(_name: str = _n, **kw: Any) -> Any:
            import arms_v6cf_device as _DA                                 # noqa: PLC0415
            return _DA.ARMS[_name](**kw)
        # marked so `arms_v6cf_device.register()` can tell its own shim from a real collision: a
        # name already in `arms.ARMS` is normally a refusal, and this one is not a collision.
        _f.is_device_answers_lazy_shim = True                              # type: ignore[attr-defined]
        _f.shim_for = _n                                                   # type: ignore[attr-defined]
        out[_n] = _f
    return out


for _k, _v in _device_answers_lazy().items():
    if _k in V6CF_ARMS:                                                    # pragma: no cover
        raise RuntimeError("the DEVICE_ANSWERS family would shadow an arms_v6cf name: %r" % (_k,))
    V6CF_ARMS[_k] = _v


def register() -> None:
    import arms as A
    A.ARMS.update(V6CF_ARMS)


def as_dict() -> Dict[str, Any]:
    return {"version": V6CF_VERSION, "arms": sorted(V6CF_ARMS),
            "bases": BASES, "contingency": CONTINGENCY,
            "mechanism": PD.as_dict(),
            "arms_py_lines_needed": ["from arms_v6cf import V6CF_ARMS", "ARMS.update(V6CF_ARMS)"]}


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=1))
