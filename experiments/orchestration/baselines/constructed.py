#!/usr/bin/env python3
"""The constructed baselines (case "constructed"): B3, B4, B6, B7, B8 and B9.

StudyB-baselines addendum §3. These are ours, not adaptations of a paper, and they exist to give
the scheduler honest competition at every level of sophistication. **B9 is the primary
competitor** and is deliberately made as strong as the suite allows: it gets the SAME trained
estimators, the SAME measured cost curves and the SAME host-offload facilities our scheduler will
get, and every component choice is documented in `cards/constructed.md`.

All six obey fairness rules 1-6 and are checked by `interface.check_fairness`.

CPU only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
import devsplit as DS
import profiles as P
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction,
                       materialize)


# ================================================================ B3
class B3BestStatic(Policy):
    """B3: the best STATIC configuration per workload scenario, chosen on training data.

    One configuration is fixed for the whole replay - no adaptation at all. Which one is chosen
    depends on the declared scenario, and the choice is made on the DEVELOPMENT split by taking
    the configuration with the highest measured quality whose demand fits the scenario's budget.
    This is the "you did not need a scheduler" baseline.
    """

    name = "B3-best-static"
    case = "constructed"
    experiments = ("A-episodic", "B-recall", "C-mixed")
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision", "representation")
    defaults_used = ("session_action", "order", "engine_config")

    def __init__(self, scenario_budget_gpu_s_per_s: float = 0.2,
                 setting: str = "measured@25") -> None:
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        afford = [r for r in self.rows if r["demand_gpu_s_per_s"] <= scenario_budget_gpu_s_per_s]
        self.choice = max(afford or self.rows, key=lambda r: r["quality"])
        self.scenario_budget = float(scenario_budget_gpu_s_per_s)

    def decide(self, obs: Observation) -> Action:
        r = self.choice
        acts = [StreamAction(s.stream_id, "local" if (r["mode"] == "local"
                                                      or not s.network.connected) else "cloud",
                             None if r["mode"] == "local" else r["cadence_s"],
                             None if r["mode"] == "local" else r["frame_count"])
                for s in obs.streams]
        return Action(streams=acts,
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall])


# ================================================================ B4
class B4QueryTypeRouting(Policy):
    """B4: route by QUERY TYPE, with a calibrated rule per type.

    - single-shot        -> the cheapest FEASIBLE tier (device if it can answer in time)
    - short-horizon      -> local, with a fixed escalation rule (the StudyE9 threshold)
    - long-horizon       -> cloud history (the richest representation the session holds)

    The type is read from the query's category, which is observable; the escalation threshold is
    the development-split `tau_trigger`, not an evaluation-fitted one.
    """

    name = "B4-query-type-routing"
    case = "constructed"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "recall_decision", "representation")
    defaults_used = ("cadence_s", "frame_count", "session_action", "order")
    LONG = ("D2", "RICH", "long", "long-horizon")
    SHORT = ("RECENT", "short", "short-horizon")

    def __init__(self, trigger_rate: float = 0.20) -> None:
        sc, lab = DS.load(arms=(("4BI", 1),))
        neg = np.array([v for c, per in sc[("4BI", 1)].items() if lab[c] == "negative"
                        for v in per.values()])
        self.tau = float(np.quantile(neg, 1.0 - float(trigger_rate)))

    def decide(self, obs: Observation) -> Action:
        rec: List[RecallAction] = []
        for q in obs.recall:
            cat = str(q.category)
            have = {e.representation for e in q.evidence}
            if cat in self.LONG or "D2" in have:
                rep = "RICH" if "RICH" in have else ("D2" if "D2" in have else "RECENT")
                rec.append(RecallAction(q.query_id, "CLOUD", representation=rep))
            elif cat in self.SHORT:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            else:
                # single-shot: cheapest feasible tier
                est = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
                rec.append(RecallAction(q.query_id, "DEVICE") if est > q.slack_s(obs.now_s)
                           else RecallAction(q.query_id, "CLOUD", representation="RECENT"))
        acts = []
        for s in obs.streams:
            v = s.latest_score()
            esc = v is not None and v >= self.tau and s.network.connected
            acts.append(StreamAction(s.stream_id, "cloud" if esc else "local"))
        return Action(streams=acts, recall=rec)


# ================================================================ B6
class B6LatencyAwareRouting(Policy):
    """B6: highest estimated QUALITY subject to the predicted deadline.

    For each pending query, enumerate the (tier, representation) options the session actually
    holds, drop those whose predicted service time exceeds the remaining slack, and take the
    highest-quality survivor. For streams, take the highest-quality configuration whose delivery
    hold shift fits the episodic deadline.
    """

    name = "B6-latency-aware-routing"
    case = "constructed"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision", "representation")
    defaults_used = ("session_action", "order")
    REP_Q = {"RECENT": 0.6, "D2": 1.0, "RICH": 1.0}
    REP_SCALE = {"RECENT": 0.35, "D2": 1.0, "RICH": 1.0}

    def __init__(self, setting: str = "measured@25", episodic_deadline_s: float = 0.75) -> None:
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        self.ep_deadline = float(episodic_deadline_s)

    def decide(self, obs: Observation) -> Action:
        feas = [r for r in self.rows if r["lag_s"] <= self.ep_deadline] or self.rows
        best = max(feas, key=lambda r: r["quality"])
        acts = [StreamAction(s.stream_id,
                             "local" if (best["mode"] == "local" or not s.network.connected)
                             else "cloud",
                             None if best["mode"] == "local" else best["cadence_s"],
                             None if best["mode"] == "local" else best["frame_count"])
                for s in obs.streams]
        rec = []
        for q in obs.recall:
            have = {e.representation for e in q.evidence} or {"RECENT"}
            opts = []
            for rep in have:
                tok = max(int(q.readiness_tokens * self.REP_SCALE.get(rep, 1.0)), 1)
                if C.recall_ttft_s(tok, q.readiness) <= q.slack_s(obs.now_s):
                    opts.append((self.REP_Q.get(rep, 0.6), rep))
            if opts:
                rec.append(RecallAction(q.query_id, "CLOUD", representation=max(opts)[1]))
            else:
                rec.append(RecallAction(q.query_id, "DEVICE"))
        return Action(streams=acts, recall=rec)


# ================================================================ B7
class B7EDFFeasibility(Policy):
    """B7: EDF plus feasibility admission - defer or reject work predicted to miss (Clockwork-style).

    Unlike `naive.EDFServiceTime`, which falls back to the device, B7 uses the full action space:
    it DEFERS work that could still make its deadline after a wait, and REJECTS work that cannot
    make it at all.
    """

    name = "B7-edf-feasibility"
    case = "constructed"
    experiments = ("C-mixed",)
    decides = ("recall_decision", "defer_s", "order")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation",
                     "session_action")

    def __init__(self, defer_s: float = 0.5) -> None:
        self.defer_s = float(defer_s)

    def decide(self, obs: Observation) -> Action:
        rec = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            est = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
            slack = q.slack_s(obs.now_s)
            if est <= slack:
                rec.append(RecallAction(q.query_id, "CLOUD"))
            elif est <= slack + self.defer_s:
                rec.append(RecallAction(q.query_id, "DEFER", defer_s=self.defer_s))
            else:
                rec.append(RecallAction(q.query_id, "REJECT"))
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=rec, order="EDF")


# ================================================================ B8
class B8UtilityPerGPUSecond(Policy):
    """B8: admit by expected incremental utility per estimated GPU-second.

    Every candidate piece of cloud work - a stream configuration or a recall query - is scored by
    (expected utility gain) / (estimated GPU-seconds), and work is admitted in that order while
    the budget lasts. This is the classic ratio rule, and it is the baseline a cost-aware
    scheduler must beat.
    """

    name = "B8-utility-per-gpu-second"
    case = "constructed"
    experiments = ("A-episodic", "C-mixed")
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision")
    defaults_used = ("representation", "session_action", "order")
    REP_Q = {"RECENT": 0.6, "D2": 1.0, "RICH": 1.0}

    def __init__(self, setting: str = "measured@25", horizon_s: float = 10.0) -> None:
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        self.local_q = next(r["quality"] for r in self.rows if r["mode"] == "local")
        self.horizon_s = float(horizon_s)

    def decide(self, obs: Observation) -> Action:
        cands: List[Tuple[float, str, object]] = []
        for s in obs.streams:
            if not s.network.connected:
                continue
            for r in self.rows:
                if r["mode"] != "cloud":
                    continue
                gain = r["quality"] - self.local_q
                cost = r["demand_gpu_s_per_s"] * C.GRID_STEP_S
                if cost > 0 and gain > 0:
                    cands.append((gain / cost, "stream", (s.stream_id, r)))
        for q in obs.recall:
            cost = C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)
            gain = self.REP_Q.get("D2", 1.0) - 0.3        # cloud over a device answer
            if cost > 0:
                cands.append((gain / cost, "recall", q))
        cands.sort(key=lambda t: -t[0])
        left = max(obs.budget_remaining_gpu_s, 0.0)
        chosen_streams: Dict[str, object] = {}
        chosen_recall: Dict[str, bool] = {}
        for _ratio, kind, payload in cands:
            if kind == "stream":
                sid, r = payload
                if sid in chosen_streams:
                    continue
                cost = r["demand_gpu_s_per_s"] * C.GRID_STEP_S
                if cost <= left:
                    chosen_streams[sid] = r
                    left -= cost
            else:
                q = payload
                if q.query_id in chosen_recall:
                    continue
                cost = C.recall_gpu_s(max(q.readiness_tokens, 1), q.readiness)
                if cost <= left and cost <= q.slack_s(obs.now_s):
                    chosen_recall[q.query_id] = True
                    left -= cost
        acts = []
        for s in obs.streams:
            r = chosen_streams.get(s.stream_id)
            acts.append(StreamAction(s.stream_id, "cloud", r["cadence_s"], r["frame_count"])
                        if r else StreamAction(s.stream_id, "local"))
        rec = [RecallAction(q.query_id, "CLOUD" if chosen_recall.get(q.query_id) else "DEVICE")
               for q in obs.recall]
        return Action(streams=acts, recall=rec)


# ================================================================ B9
class B9BestOfBreed(Policy):
    """B9: the independent best-of-breed controller. **THE PRIMARY COMPETITOR.**

    Four modern mechanisms run INDEPENDENTLY on the same physical resources, each given the same
    trained estimators, the same measured cost curves and the same host-offload facilities our
    scheduler will get:

      (i)   model / evidence routing          - ECO-LLM-style joint (tier, representation,
                                                cadence, N) selection under SLOs, over the
                                                MEASURED profile (`profiles`, StudyE9b / E9c,
                                                StudyRH5).
      (ii)  streaming readiness + rate        - VideoStorm-style MaxMin rate allocation across
                                                streams (Eq. 4), gated by an R3-Streaming-style
                                                readiness test so a stream that cannot yet
                                                contribute does not consume cloud work.
      (iii) SLO-aware cloud scheduling        - utility-per-GPU-second admission (B8's ratio
                                                rule) with EDF ordering among the admitted.
      (iv)  modern KV management              - host offload, Preble-style cache-affinity
                                                admission, and KVFlow-style reuse-aware eviction
                                                driven by the CAUSAL inter-arrival estimate.

    **The point of B9 is that the four are INDEPENDENT.** Each optimises its own objective from
    the shared observation and none sees another's choice; where two would touch the same field,
    a FIXED, DOCUMENTED precedence resolves it rather than a joint optimisation:

        episodic mode / cadence / N : (ii) decides the rate, (i) may only DOWNGRADE it to a
                                      cheaper configuration if (i)'s SLO check fails
        recall tier / representation: (i) chooses, (iii) may REFUSE on budget, (iv) may REFUSE on
                                      cache affinity under load
        session placement           : (iv) alone
        order                       : (iii) alone

    That precedence is the thing a jointly-optimising scheduler is supposed to beat; it is stated
    here and in `cards/constructed.md` so the comparison is honest.
    """

    name = "B9-best-of-breed"
    case = "constructed"
    experiments = ("C-mixed",)
    decides = ("episodic_mode", "cadence_s", "frame_count", "recall_decision", "representation",
               "session_action", "order")
    defaults_used = ("engine_config",)
    REP_Q = {"RECENT": 0.6, "D2": 1.0, "RICH": 1.0}
    REP_SCALE = {"RECENT": 0.35, "D2": 1.0, "RICH": 1.0}

    def __init__(self, setting: str = "measured@25", horizon_s: float = 10.0,
                 gpu_warm_slots: int = 4, readiness_threshold: float = 0.35,
                 max_load_pressure: float = 0.9, alpha: float = 0.3) -> None:
        import ecollm as E
        import videostorm as V
        self._E, self._V = E, V
        self.setting, self.horizon_s = setting, float(horizon_s)
        self.gpu_warm_slots = int(gpu_warm_slots)
        self.readiness_threshold = float(readiness_threshold)
        self.max_load_pressure = float(max_load_pressure)
        self.alpha = float(alpha)
        self.rows = P.stream_profile(setting=setting, horizon=0.5, quality="streaming")
        self.by = {r["name"]: r for r in self.rows}
        self.local = next(r for r in self.rows if r["mode"] == "local")
        # (iv)'s causal reuse estimate
        self._last: Dict[str, float] = {}
        self._gap: Dict[str, float] = {}

    def reset(self, seed: int = 0) -> None:
        self._last.clear()
        self._gap.clear()

    # ---- component (ii): VideoStorm MaxMin rate allocation + R3 readiness gate
    def _component_ii(self, obs: Observation) -> Dict[str, dict]:
        V = self._V
        ready = {}
        for s in obs.streams:
            n = len(s.delivered_scores)
            rho = min(n / 20.0, 1.0)
            ready[s.stream_id] = (rho >= self.readiness_threshold) and s.network.connected
        live = [s for s in obs.streams if ready[s.stream_id]]
        out = {s.stream_id: self.local for s in obs.streams}
        if not live:
            return out
        qs = []
        for s in live:
            qs.append(V.Query(
                qid=s.stream_id,
                profile=[V.Config(r["name"], r["quality"], max(r["demand_gpu_s_per_s"], 0.0))
                         for r in self.rows],
                u_base=0.0, alpha_q=1.0, alpha_min_q=0.0, alpha_l=1.0, lag_max_s=0.5,
                lag_s=self.by.get(f"cloud/32BI_N{s.frame_count}@{s.cadence_s}",
                                  self.local)["lag_s"]))
        cap = max(obs.budget_remaining_gpu_s / max(self.horizon_s, 1e-9), 0.0)
        alloc = V.allocate_maxmin(qs, cap, self.horizon_s, 0.01)
        for s in live:
            a, cfg = alloc[s.stream_id]
            out[s.stream_id] = self.by[cfg.name] if a > 0 else self.local
        return out

    # ---- component (i): ECO-LLM joint selection, as an SLO check that may only DOWNGRADE
    def _component_i_stream(self, row: dict, obs: Observation, n_streams: int) -> dict:
        E = self._E
        per = max(obs.budget_remaining_gpu_s, 0.0) / max(n_streams, 1)
        pts = E.explore([dict(name=r["name"]) for r in self.rows],
                        lambda c: (self.by[c["name"]]["quality"],
                                   self.by[c["name"]]["demand_gpu_s_per_s"] * self.horizon_s,
                                   self.by[c["name"]]["lag_s"]))
        pick, _f = E.select(pts, E.SLO(max_cost_gpu_s=per))
        cand = self.by[dict(pick.knobs)["name"]]
        # precedence: (i) may only make (ii)'s choice CHEAPER, never richer
        if cand["demand_gpu_s_per_s"] < row["demand_gpu_s_per_s"]:
            return cand
        return row

    def _component_i_recall(self, q, obs: Observation) -> Tuple[str, float]:
        E = self._E
        have = {e.representation for e in q.evidence} or {"RECENT"}
        space, tab = [], {}
        for rep in sorted(have):
            tok = max(int(q.readiness_tokens * self.REP_SCALE.get(rep, 1.0)), 1)
            tab[rep] = (self.REP_Q.get(rep, 0.6), C.recall_gpu_s(tok, q.readiness),
                        C.recall_ttft_s(tok, q.readiness))
            space.append(dict(rep=rep))
        pts = E.explore(space, lambda c: tab[c["rep"]])
        pick, _f = E.select(pts, E.SLO(max_latency_s=max(q.slack_s(obs.now_s), 0.0)))
        rep = dict(pick.knobs)["rep"]
        return rep, tab[rep][1]

    # ---- component (iv): causal reuse estimate for eviction and affinity
    def _observe(self, obs: Observation) -> None:
        for q in obs.recall:
            t0 = self._last.get(q.session_id)
            if t0 is not None:
                g = obs.now_s - t0
                self._gap[q.session_id] = (self.alpha * g
                                           + (1 - self.alpha) * self._gap.get(q.session_id, g))
            self._last[q.session_id] = obs.now_s

    def _reuse_eta(self, sid: str, now_s: float) -> float:
        g = self._gap.get(sid)
        if g is None:
            return float("inf")
        return max(g - (now_s - self._last.get(sid, now_s)), 0.0)

    @staticmethod
    def _load_pressure(obs: Observation) -> float:
        n = sum(obs.cloud.queued_by_class.values()) + sum(obs.cloud.running_by_class.values())
        return max(obs.cloud.gpu_kv_fraction, min(n / 8.0, 1.0))

    def decide(self, obs: Observation) -> Action:
        self._observe(obs)
        lp = self._load_pressure(obs)

        # (ii) then (i): rate allocation, SLO-downgraded
        chosen = self._component_ii(obs)
        n = max(len(obs.streams), 1)
        for sid in list(chosen):
            if chosen[sid]["mode"] == "cloud":
                chosen[sid] = self._component_i_stream(chosen[sid], obs, n)

        # (iii) utility-per-GPU-second admission over everything, EDF among admitted recall
        left = max(obs.budget_remaining_gpu_s, 0.0)
        ratios = []
        for sid, r in chosen.items():
            if r["mode"] != "cloud":
                continue
            cost = r["demand_gpu_s_per_s"] * C.GRID_STEP_S
            gain = r["quality"] - self.local["quality"]
            ratios.append((gain / cost if cost > 0 else 0.0, "stream", sid, cost))
        recall_plan: Dict[str, Tuple[str, str, float]] = {}
        for q in obs.recall:
            rep, cost = self._component_i_recall(q, obs)
            gain = self.REP_Q.get(rep, 0.6) - 0.3
            ratios.append((gain / cost if cost > 0 else 0.0, "recall", q.query_id, cost))
            recall_plan[q.query_id] = (rep, q.session_id, cost)
        ratios.sort(key=lambda t: -t[0])
        admit_stream, admit_recall = set(), set()
        for _ratio, kind, key, cost in ratios:
            if cost <= left:
                (admit_stream if kind == "stream" else admit_recall).add(key)
                left -= cost

        acts = []
        for s in obs.streams:
            r = chosen[s.stream_id]
            ok = r["mode"] == "cloud" and s.stream_id in admit_stream and s.network.connected
            acts.append(StreamAction(s.stream_id, "cloud", r["cadence_s"], r["frame_count"])
                        if ok else StreamAction(s.stream_id, "local"))

        # (iv) cache-affinity refusal under load, then placement by reuse ETA
        rec = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            rep, _sid, _c = recall_plan[q.query_id]
            affinity = {"GPU-WARM": 1.0, "HOST-WARM": 0.5, "COLD": 0.0}[q.readiness]
            if q.query_id not in admit_recall:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            elif lp > self.max_load_pressure and affinity <= 0.0:
                rec.append(RecallAction(q.query_id, "DEVICE"))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD", representation=rep))
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        warm = sorted(known, key=lambda s: self._reuse_eta(s, obs.now_s))[:self.gpu_warm_slots]
        sess = [SessionAction(s, "KEEP_GPU_WARM" if s in warm else "OFFLOAD_TO_HOST")
                for s in known]
        return Action(streams=acts, recall=rec, sessions=sess, order="EDF",
                      notes=dict(components="i=ECO-LLM-style, ii=VideoStorm+R3, "
                                            "iii=utility-per-GPU-s+EDF, iv=Preble+KVFlow-causal",
                                 independent=True, load_pressure=round(lp, 3)))


# ================================================================ B10
class B10BlockingAwareAdmission(Policy):
    """B10: blocking-aware admission, WITHOUT slicing.

    StudyB-baselines amendment (2026-11-12) item (c). The mechanism it tests is the one
    StudyE10c / E10d / E10e located and StudyE9d priced:

      * a cloud recall request runs as ONE non-preemptive unit on the shared replica, and every
        episodic request arriving during it is held until its first token (StudyE10c section 6,
        StudyE10d: the LM prefill is the unsplittable unit; StudyE10e: capping the per-step
        tokens cuts the hold by 19-30 % and does not remove it);
      * a held episodic score is delivered late, and StudyE9d measured exactly what lateness
        costs - V(d), with d* the added delay at which a cloud stream falls to the device's own
        value.

    So B10 admits a recall query only when the hold it would impose does not push an episodic
    stream past the step where its value falls. Concretely, for each pending query:

      T        = predicted non-preemptive engine time = `costs.recall_ttft_s(tokens, readiness)`
      affected = cloud streams with at least one call due inside T (cadence <= T)
      d*       = `profiles.d_star_s(arm, cadence)` from StudyE9d's curve
      DEFER if T >= d* for any affected stream, UNLESS the query's deadline slack is exhausted
      (slack <= T), in which case it is ADMITTED - a deadline is not sacrificed to a stream.

    Everything else: EDF order; recall served at whatever readiness the session actually has
    (COLD, HOST-WARM or GPU-WARM, never upgraded for free); KV management is B9's component (iv)
    - the causal inter-arrival estimate ranks sessions for the GPU-warm slots.

    **No slicing.** B10 builds state monolithically (`slice_tokens = None`), which is what every
    pre-amendment baseline can express, and declares that restriction: whether slicing helps is
    the property under test, and B11 is its ablation.
    """

    name = "B10-blocking-aware-admission"
    case = "constructed"
    experiments = ("C-mixed",)
    decides = ("recall_decision", "defer_s", "session_action", "order")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation",
                     "engine_config")
    restricts_action_space = "slice_tokens = None (one monolithic prefill)"
    restriction_reason = ("B10 exists to test blocking-AWARE ADMISSION without slicing, so that "
                          "the admission rule and the slicing mechanism can be attributed "
                          "separately; B11 is the slicing-without-scheduling ablation and the "
                          "monolithic restriction is the property under test (fairness rule 4).")

    def __init__(self, defer_quantum_s: float = 0.25, gpu_warm_slots: int = 4,
                 quality: str = "challenge", horizon: float = 0.0, alpha: float = 0.3) -> None:
        self.defer_q = float(defer_quantum_s)
        self.gpu_warm_slots = int(gpu_warm_slots)
        self.quality, self.horizon = quality, float(horizon)
        self.alpha = float(alpha)
        self._last: Dict[str, float] = {}
        self._gap: Dict[str, float] = {}

    def reset(self, seed: int = 0) -> None:
        self._last.clear()
        self._gap.clear()

    # ---- B9 component (iv), verbatim: the CAUSAL reuse estimate
    def _observe(self, obs: Observation) -> None:
        for q in obs.recall:
            t0 = self._last.get(q.session_id)
            if t0 is not None:
                g = obs.now_s - t0
                self._gap[q.session_id] = (self.alpha * g
                                           + (1 - self.alpha) * self._gap.get(q.session_id, g))
            self._last[q.session_id] = obs.now_s

    def _reuse_eta(self, sid: str, now_s: float) -> float:
        g = self._gap.get(sid)
        if g is None:
            return float("inf")
        return max(g - (now_s - self._last.get(sid, now_s)), 0.0)

    def _tolerable_hold_s(self, s) -> float:
        """How much added delivery delay this stream can take before it stops being worth calling
        - StudyE9d's d*. A stream the policy would not put on the cloud anyway tolerates any hold,
        and `None` (no crossing inside StudyE9d's 3-s grid) is read as its 3-s maximum."""
        arm = f"32BI_N{s.frame_count}"
        try:
            d = P.d_star_s(arm, s.cadence_s, self.quality, self.horizon)
        except KeyError:
            return float("inf")
        return float(P.DELAYS_S[-1]) if d is None else float(d)

    def decide(self, obs: Observation) -> Action:
        self._observe(obs)
        # B10 does not decide placement: it relies on DEFAULTS["episodic_mode"] = "cloud", so
        # every connected stream is a cloud stream and is affected by a hold. Reading
        # `s.on_cloud` instead would silently exempt every stream in a replay where the harness
        # has not yet put one on the cloud, and the admission rule would never fire.
        on_cloud = [s for s in obs.streams if s.network.connected]
        rec: List[RecallAction] = []
        sess_build: List[SessionAction] = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):          # EDF
            T = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
            slack = q.slack_s(obs.now_s)
            affected = [s for s in on_cloud if s.cadence_s <= T]
            worst = min((self._tolerable_hold_s(s) for s in affected), default=float("inf"))
            if slack <= T:
                # the deadline is about to be missed: a deadline is not sacrificed to a stream
                rec.append(RecallAction(q.query_id, "CLOUD"))
                if q.readiness == "COLD":
                    sess_build.append(materialize(q.session_id, max(q.readiness_tokens, 1),
                                                  slice_tokens=None))
            elif T >= worst:
                rec.append(RecallAction(q.query_id, "DEFER",
                                        defer_s=min(self.defer_q, max(slack - T, 0.0))))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD"))
                if q.readiness == "COLD":
                    sess_build.append(materialize(q.session_id, max(q.readiness_tokens, 1),
                                                  slice_tokens=None))
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        building = {a.session_id for a in sess_build}
        warm = sorted(known, key=lambda s: self._reuse_eta(s, obs.now_s))[:self.gpu_warm_slots]
        sess = list(sess_build) + [
            SessionAction(s, "KEEP_GPU_WARM" if s in warm else "OFFLOAD_TO_HOST")
            for s in known if s not in building]
        return Action(streams=[], recall=rec, sessions=sess, order="EDF",
                      notes=dict(rule="defer a recall whose non-preemptive engine time exceeds "
                                      "the affected streams' StudyE9d d*, unless its slack is "
                                      "exhausted", slicing=False))


# ================================================================ B11
class B11NaiveSlicing(Policy):
    """B11: naive slicing - the ablation of slicing WITHOUT scheduling.

    StudyB-baselines amendment (2026-11-12) item (c). Every materialization is chained in FIXED
    2,048-token slices, FCFS, with NO awareness of episodic timing; everything else is the
    tuned-engine always-cloud baseline (StudyE10e's P1, the engine the user chose on 2026-11-12).

    It exists so that any gain from slicing can be separated from any gain from scheduling: B10
    schedules without slicing, B11 slices without scheduling, and a policy that beats both does
    something neither mechanism does alone.

    **The per-slice overhead is NOT a measured quantity.** StudySIM1 sweeps it over
    {0.02, 0.05, 0.1, 0.2, 0.47} s and every result involving B11 is labelled parametric until
    StudySLICE1 measures it. 2,048 tokens is StudyE10c's E2 step budget, chosen because it is a
    documented vLLM 0.31.0 value rather than a tuned one.
    """

    name = "B11-naive-slicing"
    case = "constructed"
    experiments = ("B-recall", "C-mixed")
    decides = ("recall_decision", "session_action", "engine_config")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation", "order")
    SLICE_TOKENS = 2048          # StudyE10c's E2 step budget, a documented vLLM 0.31.0 value

    def __init__(self, slice_tokens: int = SLICE_TOKENS) -> None:
        import tuned_engine as TE
        self.slice_tokens = int(slice_tokens)
        self.engine = TE.TUNED

    def decide(self, obs: Observation) -> Action:
        known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                       | {q.session_id for q in obs.recall})
        tok = {q.session_id: q.readiness_tokens for q in obs.recall}
        sess = [(SessionAction(s, "KEEP_GPU_WARM") if s in obs.cloud.gpu_warm_sessions
                 else materialize(s, max(tok.get(s, 11000), 1),
                                  slice_tokens=self.slice_tokens)) for s in known]
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
                      sessions=sess, order="FCFS", engine_config=self.engine,
                      notes=dict(slicing=True, slice_tokens=self.slice_tokens,
                                 per_slice_overhead="UNMEASURED - StudySIM1 sweeps it"))


CONSTRUCTED = {
    "B3-best-static": B3BestStatic,
    "B4-query-type-routing": B4QueryTypeRouting,
    "B6-latency-aware-routing": B6LatencyAwareRouting,
    "B7-edf-feasibility": B7EDFFeasibility,
    "B8-utility-per-gpu-second": B8UtilityPerGPUSecond,
    "B9-best-of-breed": B9BestOfBreed,
    "B10-blocking-aware-admission": B10BlockingAwareAdmission,
    "B11-naive-slicing": B11NaiveSlicing,
}
