#!/usr/bin/env python3
"""StudySIM1d-validate. CPU ONLY; no GPU, no model server, no inference.

Three parts, run in order.

  PART A  ARM AUDIT. Why several StudySIM1c-scoped arms look degenerate. One representative cell
          (balanced mix, F = 4, deadline 5 s, seed 0) per arm, fully instrumented: every action
          counted by request class, and the first five episodic and first five recall decisions
          traced with the inputs the arm read, the rule it computed, the action, and why the
          alternative lost. Each arm is then classified FAITHFUL / ADAPTER BUG / SCOPE
          INTERACTION. NOTHING here changes what an arm decides: a change of that kind is listed
          as a PROPOSED CHANGE for the user, which is the pre-registered stopping condition.

  PART B  MODE-INDEPENDENT OVERLAP COST. StudySIM1b found a 0.05-0.07 s penalty on an episodic
          request whose service overlaps an in-flight warm recall request, THE SAME SIZE in
          KV-GPU and KV-HOST cells, and did not model it because its own pre-registered rule
          required the effect to be host-specific. This part fits it on cells that are in NO
          StudySIM1 gate cell, adds it as an OFF-by-default engine option, and re-runs the gate.

  PART C  OUT-OF-SAMPLE VALIDATION against StudySLICE1 Part B, which was measured LIVE on the
          H100 and which the simulator has never seen. No parameter is fitted or changed using
          any Part B number.

Nothing in this file writes to git.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (HERE, ROOT / "experiments/lib", ROOT / "experiments/dashcam",
          ROOT / "experiments/orchestration/baselines",
          ROOT / "experiments/orchestration/baselines/smoke",
          ROOT / "experiments/orchestration/baselines/reconstructed"):
    sys.path.insert(0, str(p))

OUT = ROOT / "results/orchestration/sim1d"

# The one representative cell the audit traces, fixed before any run.
AUDIT_CELL = dict(mix="balanced", fleet=4, deadline_s=5.0, seed=0)

# The arms the specification names, in its own order. "B9-noHost" is the label StudySIM1c gives
# B9-best-of-breed when the harness's availability flag disables its host-offload component.
AUDIT_ARMS = [
    "B9-noHost",
    "videostorm/maxmin", "videostorm/maxsum", "covstream", "hybrid-llm", "simplestream",
    "streamscout",
    "B7-edf-feasibility", "thinking-qwenvl-atdm",
    "kvflow", "preble", "rh8-demand-aware-causal",
    "B10-blocking-aware-admission", "B11-naive-slicing",
    "B3-best-static", "tuned-engine", "always-cloud-fcfs",
]


# ================================================================ Part A: the tracer
class Traced:
    """A transparent proxy around a policy that records every decision it makes.

    It is NOT a Policy subclass on purpose: `check_fairness` and the harness read a policy's
    declarations with `getattr`, and subclassing would shadow the wrapped policy's class
    attributes with the base class's defaults. Delegation keeps the arm's own declarations.
    """

    def __init__(self, pol, explain: Optional[Callable] = None, keep: int = 5,
                 probe: Optional[Callable] = None, probe_every: int = 100) -> None:
        self.pol = pol
        self.explain = explain
        self.keep = int(keep)
        self.probe = probe
        self.probe_every = int(probe_every)
        self._probe_acc: Dict[str, List[float]] = defaultdict(list)
        self.name = pol.name
        self.epochs = 0
        self.stream_actions = Counter()        # mode -> n
        self.recall_actions = Counter()        # decision -> n
        self.session_actions = Counter()       # action -> n
        self.slice_requests = 0
        self.episodic_chain: List[Dict] = []
        self.recall_chain: List[Dict] = []
        self._ep_seen = 0
        self._rc_seen = 0

    def __getattr__(self, k):                  # every declaration the harness reads
        return getattr(self.pol, k)

    def reset(self, seed: int = 0) -> None:
        self.pol.reset(seed)

    def __call__(self, obs):
        act = self.pol(obs)
        self.epochs += 1
        if self.probe is not None and (self.epochs - 1) % self.probe_every == 0:
            try:
                for k, v in self.probe(self.pol, obs, act).items():
                    self._probe_acc[k].append(float(v))
            except Exception as e:                                    # noqa: BLE001
                self._probe_acc[f"probe_failed:{type(e).__name__}: {e}"].append(1.0)
        why = None
        for sa in act.streams:
            self.stream_actions[sa.mode] += 1
            if self._ep_seen < self.keep:
                if why is None and self.explain is not None:
                    why = self._safe_explain(obs, act)
                self.episodic_chain.append(dict(
                    epoch=self.epochs, now_s=obs.now_s, stream_id=sa.stream_id, action=sa.mode,
                    cadence_s=sa.cadence_s, frame_count=sa.frame_count,
                    inputs=_stream_inputs(obs, sa.stream_id), why=(why or {}).get(sa.stream_id)
                    if isinstance(why, dict) else why))
                self._ep_seen += 1
        for ra in act.recall:
            self.recall_actions[ra.decision] += 1
            if self._rc_seen < self.keep:
                if why is None and self.explain is not None:
                    why = self._safe_explain(obs, act)
                self.recall_chain.append(dict(
                    epoch=self.epochs, now_s=obs.now_s, query_id=ra.query_id,
                    action=ra.decision, representation=ra.representation, defer_s=ra.defer_s,
                    inputs=_recall_inputs(obs, ra.query_id),
                    why=(why or {}).get(ra.query_id) if isinstance(why, dict) else why))
                self._rc_seen += 1
        for xa in act.sessions:
            self.session_actions[xa.action] += 1
            if xa.action == "MATERIALIZE" and xa.slice_tokens:
                self.slice_requests += 1
        return act

    def _safe_explain(self, obs, act):
        try:
            return self.explain(self.pol, obs, act)
        except Exception as e:                                        # noqa: BLE001
            return {"explainer_failed": f"{type(e).__name__}: {e}"}

    def probe_summary(self) -> Dict:
        out = {}
        for k, v in sorted(self._probe_acc.items()):
            a = np.asarray(v, dtype=float)
            out[k] = dict(n=int(a.size), mean=float(a.mean()), min=float(a.min()),
                          max=float(a.max()), n_true=int((a > 0.5).sum()))
        return out

    def summary(self) -> Dict:
        return dict(arm=self.name, epochs=self.epochs, probes=self.probe_summary(),
                    stream_actions=dict(self.stream_actions),
                    recall_actions=dict(self.recall_actions),
                    session_actions=dict(self.session_actions),
                    slice_materializations=self.slice_requests,
                    first_episodic_decisions=self.episodic_chain,
                    first_recall_decisions=self.recall_chain)


def _stream_inputs(obs, sid: str) -> Dict:
    s = next((x for x in obs.streams if x.stream_id == sid), None)
    if s is None:
        return {}
    return dict(n_delivered_scores=len(s.delivered_scores),
                latest_score=(None if s.latest_score() is None else round(s.latest_score(), 4)),
                cadence_s=s.cadence_s, frame_count=s.frame_count, on_cloud=s.on_cloud,
                connected=s.network.connected,
                budget_remaining_gpu_s=round(obs.budget_remaining_gpu_s, 2),
                gpu_kv_fraction=round(obs.cloud.gpu_kv_fraction, 4),
                queued=dict(obs.cloud.queued_by_class), running=dict(obs.cloud.running_by_class))


def _recall_inputs(obs, qid: str) -> Dict:
    q = next((x for x in obs.recall if x.query_id == qid), None)
    if q is None:
        return {}
    return dict(session_id=q.session_id, category=q.category, readiness=q.readiness,
                readiness_tokens=q.readiness_tokens,
                evidence=[(e.representation, e.tier, e.tokens) for e in q.evidence],
                distinct_representations=sorted({e.representation for e in q.evidence}),
                device_answer_confidence=q.device_answer_confidence,
                slack_s=round(q.slack_s(obs.now_s), 3),
                gpu_warm_sessions=list(obs.cloud.gpu_warm_sessions),
                queued=dict(obs.cloud.queued_by_class), running=dict(obs.cloud.running_by_class),
                gpu_kv_fraction=round(obs.cloud.gpu_kv_fraction, 4),
                budget_remaining_gpu_s=round(obs.budget_remaining_gpu_s, 2))


# ---------------------------------------------------------------- arm-specific explainers
def _ex_videostorm(pol, obs, act) -> Dict:
    import videostorm as V
    by = {r["name"]: r for r in pol._rows}
    qs = []
    for s in obs.streams:
        q = pol._query(s.stream_id)
        cur = (f"cloud/32BI_N{s.frame_count}@{s.cadence_s}" if s.on_cloud else "local")
        q.lag_s = by.get(cur, pol._rows[0])["lag_s"]
        qs.append(q)
    cap = max(obs.budget_remaining_gpu_s / max(pol.horizon_s, 1e-9), 0.0)
    alloc = (V.allocate_maxmin if pol.objective == "maxmin" else V.allocate_maxsum)(
        qs, cap, pol.horizon_s, pol.delta)
    out = {}
    for s in obs.streams:
        a, cfg = alloc[s.stream_id]
        row = by[cfg.name]
        out[s.stream_id] = dict(
            rule=("Eq. 4 allocation over the measured profile; a stream goes to the cloud iff "
                  "a_k > 0 AND the chosen configuration is a cloud one"),
            capacity_R_gpu_s_per_s=round(cap, 4), objective=pol.objective,
            allocation_a_k=round(float(a), 6), chosen_config=cfg.name,
            chosen_mode=row["mode"], chosen_quality=round(row["quality"], 5),
            chosen_demand_gpu_s_per_s=round(row["demand_gpu_s_per_s"], 5),
            cloud_options={r["name"]: dict(quality=round(r["quality"], 5),
                                           demand=round(r["demand_gpu_s_per_s"], 5))
                           for r in pol._rows},
            alternative_rejected=("a cloud configuration: rejected because the chosen one is "
                                  "local or a_k <= 0" if row["mode"] == "local"
                                  else "local: rejected because a cloud config won"))
    return out


def _ex_literal_local(pol, obs, act) -> Dict:
    """covstream / simplestream / streamscout: the adapter emits a literal 'local' for every
    stream, with no rule computed from the observation at all."""
    return {s.stream_id: dict(
        rule="the adapter emits StreamAction(stream_id, 'local') unconditionally",
        computed_from_observation=False,
        docstring_says=("episodic streams take the documented default"
                        if pol.name in ("simplestream", "streamscout") else
                        "the cloud keeps the structure resident; that is the whole design"),
        documented_default="DEFAULTS['episodic_mode'] = 'cloud'",
        declares_decides_episodic_mode=("episodic_mode" in getattr(pol, "decides", ())),
        alternative_rejected="cloud: never evaluated; no branch exists")
        for s in obs.streams}


def _ex_hybrid(pol, obs, act) -> Dict:
    import hybrid_llm_adapted as H
    out = {}
    for s in obs.streams:
        x = np.asarray([H._features(s)], dtype=float)
        route = bool(pol.router.route(x, pol.threshold)[0])
        p = None
        p = float(pol.router.predict(x)[0])
        out[s.stream_id] = dict(
            rule="send to the SMALL model (keep local) when p_w(x) >= threshold (Eq. 1-4)",
            variant=pol.variant, threshold=pol.threshold, t_star=getattr(pol, "t_star", None),
            features=[round(v, 5) for v in x[0].tolist()],
            p_w=(None if p is None else round(p, 5)),
            keep_local=route, connected=s.network.connected,
            n_dev_rows=pol.n_dev,
            alternative_rejected=("cloud: p_w >= threshold, so the router predicts the device is "
                                 "as good as the cloud" if route else "local"))
    return out


def _ex_thinking(pol, obs, act) -> Dict:
    from thinking_qwenvl import atdm
    out = {}
    for q in obs.recall:
        rho = min(len({e.representation for e in q.evidence}) / 3.0, 1.0)
        conf = (float(q.device_answer_confidence)
                if q.device_answer_confidence is not None else rho)
        d = atdm(rho, conf, pol.pt, pol.ct)
        out[q.query_id] = dict(
            rule="ATDM answers when progress rho and confidence both clear their thresholds",
            rho=round(rho, 5), confidence=round(conf, 5),
            progress_threshold=pol.pt, confidence_threshold=pol.ct,
            answer_now=bool(d.answer_now), reason=d.reason,
            rho_numerator=sorted({e.representation for e in q.evidence}),
            rho_note=("rho = |distinct representations in the evidence inventory| / 3; the "
                      "harness builds every inventory from TWO EvidenceItems that both carry "
                      "representation 'D2', so the numerator is 1 in every query of every cell"),
            alternative_rejected=("CLOUD: rejected because rho or confidence is below threshold"
                                  if not d.answer_now else "DEFER"))
    for s in obs.streams:
        v = s.latest_score()
        conf = 0.0 if v is None else max(min((v + 12.0) / 12.0, 1.0), 0.0)
        rho = min(len(s.delivered_scores) / 20.0, 1.0)
        d = atdm(rho, conf, pol.pt, pol.ct)
        out[s.stream_id] = dict(
            rule="the same ATDM test on the stream's own delivered history",
            rho=round(rho, 5), confidence=round(conf, 5), latest_score=v,
            progress_threshold=pol.pt, confidence_threshold=pol.ct,
            answer_now=bool(d.answer_now), reason=d.reason,
            alternative_rejected=("cloud: rejected because the ATDM test did not fire"
                                  if not d.answer_now else "local"))
    return out


def _ex_b7(pol, obs, act) -> Dict:
    import costs as C
    out = {}
    for q in obs.recall:
        est = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
        slack = q.slack_s(obs.now_s)
        out[q.query_id] = dict(
            rule="EDF + feasibility: CLOUD if est <= slack, DEFER if est <= slack + defer_s, "
                 "else REJECT",
            predicted_service_s=round(est, 4), slack_s=round(slack, 4), defer_s=pol.defer_s,
            readiness=q.readiness, readiness_tokens=q.readiness_tokens,
            branch=("CLOUD" if est <= slack else
                    ("DEFER" if est <= slack + pol.defer_s else "REJECT")),
            note=("the estimate is the ISOLATED service time from costs.recall_ttft_s; it "
                  "carries no queueing term, so it cannot see what the engine is doing"),
            alternative_rejected="CLOUD: rejected because the isolated estimate already "
                                 "exceeds the slack")
    return out


def _ex_preble(pol, obs, act) -> Dict:
    lp = pol._load_pressure(obs)
    AFF = {"GPU-WARM": 1.0, "HOST-WARM": 0.5, "COLD": 0.0}
    out = {}
    for q in obs.recall:
        aff = AFF.get(q.readiness, 0.0)
        out[q.query_id] = dict(
            rule="score = affinity - load_weight * load_pressure; shed COLD work to the device "
                 "while load_pressure > max_load_pressure",
            load_pressure=round(lp, 4), max_load_pressure=pol.max_load_pressure,
            affinity=aff, readiness=q.readiness,
            score=round(aff - pol.load_weight * lp, 4),
            branch=("DEVICE" if (lp > pol.max_load_pressure and aff <= 0.0) else "CLOUD"),
            load_pressure_terms=dict(gpu_kv_fraction=round(obs.cloud.gpu_kv_fraction, 4),
                                     queued_plus_running=sum(obs.cloud.queued_by_class.values())
                                     + sum(obs.cloud.running_by_class.values())),
            alternative_rejected="DEVICE: rejected because load pressure is below the threshold "
                                 "or the session is cache-resident")
    return out


def _ex_kvflow(pol, obs, act) -> Dict:
    out = {}
    for q in obs.recall:
        out[q.query_id] = dict(
            rule="KVFlow's reuse-aware eviction and prefetch over a CAUSAL steps-to-execution "
                 "estimate; the recall decision itself is always CLOUD",
            steps_to_execution_s=pol._steps_to_execution(q.session_id, obs.now_s),
            ewma_gap_s=pol._gap.get(q.session_id), readiness=q.readiness,
            prefetch_horizon_s=pol.horizon_s, gpu_capacity_tokens=pol.cap,
            alternative_rejected="DEVICE / DEFER: this adapter never emits them")
    for s in obs.streams:
        out[s.stream_id] = dict(rule="episodic mode is not decided by KVFlow; the adapter emits "
                                     "'cloud' for every stream",
                                declares_default_used=("episodic_mode"
                                                       in getattr(pol, "defaults_used", ())),
                                documented_default="cloud")
    return out


def _ex_rh8(pol, obs, act) -> Dict:
    sessions = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                      | {q.session_id for q in obs.recall})
    k = max(int(round(pol.high_frac * len(sessions))), 0)
    ranked = sorted(sessions, key=lambda s: -pol._count.get(s, 0.0))
    out = {}
    for q in obs.recall:
        out[q.query_id] = dict(
            rule="RH8 keeps the top HIGH_FRAC of sessions warm, ranked by a decayed count of "
                 "their own past arrivals; the recall decision is always CLOUD",
            n_sessions=len(sessions), high_frac=pol.high_frac, warm_slots_k=k,
            decayed_count=round(pol._count.get(q.session_id, 0.0), 4),
            rank=(ranked.index(q.session_id) if q.session_id in ranked else None),
            kept_warm=bool(q.session_id in set(ranked[:k])), readiness=q.readiness,
            alternative_rejected="DEVICE / DEFER: this adapter never emits them")
    return out


def _ex_b10(pol, obs, act) -> Dict:
    import costs as C
    on_cloud = [s for s in obs.streams if s.network.connected]
    out = {}
    for q in obs.recall:
        T = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness)
        slack = q.slack_s(obs.now_s)
        affected = [s for s in on_cloud if s.cadence_s <= T]
        worst = min((pol._tolerable_hold_s(s) for s in affected), default=float("inf"))
        out[q.query_id] = dict(
            rule="DEFER a recall whose non-preemptive engine time T exceeds the affected "
                 "streams' StudyE9d d*, UNLESS its slack is exhausted (slack <= T)",
            predicted_engine_time_T_s=round(T, 4), slack_s=round(slack, 4),
            n_streams_connected=len(on_cloud),
            n_affected=len(affected),
            affected_cadences_s=sorted({s.cadence_s for s in affected}),
            worst_d_star_s=(None if math.isinf(worst) else round(worst, 4)),
            branch=("CLOUD (slack exhausted)" if slack <= T else
                    ("DEFER" if T >= worst else "CLOUD")),
            readiness=q.readiness,
            materializes=bool(q.readiness == "COLD" and (slack <= T or T < worst)),
            alternative_rejected=("DEFER: rejected because the deadline is not sacrificed to a "
                                  "stream" if slack <= T else
                                  "CLOUD: rejected because T >= d* for an affected stream"))
    return out


def _ex_b11(pol, obs, act) -> Dict:
    known = sorted(set(obs.cloud.gpu_warm_sessions) | set(obs.cloud.host_warm_sessions)
                   | {q.session_id for q in obs.recall})
    out = {}
    for q in obs.recall:
        out[q.query_id] = dict(
            rule="every materialization is chained in FIXED 2,048-token slices, FCFS, with no "
                 "awareness of episodic timing; the recall decision is always CLOUD",
            slice_tokens=pol.slice_tokens, engine_config=pol.engine,
            session_is_gpu_warm=bool(q.session_id in obs.cloud.gpu_warm_sessions),
            emits=("KEEP_GPU_WARM" if q.session_id in obs.cloud.gpu_warm_sessions
                   else "MATERIALIZE(slice_tokens=%d)" % pol.slice_tokens),
            n_known_sessions=len(known),
            alternative_rejected="DEVICE / DEFER: this arm never emits them")
    return out


def _ex_b9(pol, obs, act) -> Dict:
    """B9's four independent components and the fixed precedence between them, step by step."""
    lp = pol._load_pressure(obs)
    ii = pol._component_ii(obs)
    n = max(len(obs.streams), 1)
    after_i = {}
    for sid, row in ii.items():
        after_i[sid] = (pol._component_i_stream(row, obs, n) if row["mode"] == "cloud" else row)
    left0 = max(obs.budget_remaining_gpu_s, 0.0)
    out = {}
    import costs as C
    for s in obs.streams:
        rho = min(len(s.delivered_scores) / 20.0, 1.0)
        gate = (rho >= pol.readiness_threshold) and s.network.connected
        out[s.stream_id] = dict(
            precedence="(ii) decides the rate, (i) may only DOWNGRADE it, (iii) admits",
            component_ii_readiness_rho=round(rho, 5),
            component_ii_readiness_threshold=pol.readiness_threshold,
            component_ii_gate_passed=bool(gate),
            component_ii_capacity_R=round(max(obs.budget_remaining_gpu_s
                                              / max(pol.horizon_s, 1e-9), 0.0), 4),
            component_ii_choice=ii[s.stream_id]["name"],
            component_ii_mode=ii[s.stream_id]["mode"],
            component_i_choice=after_i[s.stream_id]["name"],
            component_i_mode=after_i[s.stream_id]["mode"],
            component_i_downgraded=bool(after_i[s.stream_id]["name"]
                                        != ii[s.stream_id]["name"]),
            component_i_per_stream_budget_gpu_s=round(left0 / n, 4),
            component_iii_budget_left_gpu_s=round(left0, 2),
            load_pressure=round(lp, 4),
            local_quality=round(pol.local["quality"], 5),
            chosen_quality=round(after_i[s.stream_id]["quality"], 5),
            alternative_rejected=(
                "cloud: rejected by component (ii)'s R3 readiness gate" if not gate else
                ("cloud: rejected by component (i)'s ECO-LLM SLO downgrade to a local "
                 "configuration" if after_i[s.stream_id]["mode"] == "local"
                 else "local: a cloud configuration survived both components")))
    for q in obs.recall:
        rep, cost = pol._component_i_recall(q, obs)
        aff = {"GPU-WARM": 1.0, "HOST-WARM": 0.5, "COLD": 0.0}[q.readiness]
        out[q.query_id] = dict(
            component_i_representation=rep, component_i_cost_gpu_s=round(cost, 4),
            component_iv_affinity=aff, component_iv_max_load_pressure=pol.max_load_pressure,
            load_pressure=round(lp, 4), readiness=q.readiness,
            rule="(i) chooses the representation, (iii) may REFUSE on budget, (iv) may REFUSE "
                 "on cache affinity under load",
            alternative_rejected="CLOUD: refused by (iii) on budget or by (iv) on affinity")
    return out


def _ex_trivial_cloud(pol, obs, act) -> Dict:
    return {s.stream_id: dict(
        rule="this arm puts every stream on the cloud at the documented default cadence and "
             "frame count",
        documented_default_cadence_s=0.5, documented_default_frame_count=1,
        connected=s.network.connected,
        alternative_rejected="local: this arm has no branch that selects it")
        for s in obs.streams}


EXPLAINERS: Dict[str, Callable] = {
    "videostorm/maxmin": _ex_videostorm, "videostorm/maxsum": _ex_videostorm,
    "covstream": _ex_literal_local, "simplestream": _ex_literal_local,
    "streamscout": _ex_literal_local,
    "hybrid-llm": _ex_hybrid, "thinking-qwenvl-atdm": _ex_thinking,
    "B7-edf-feasibility": _ex_b7, "preble": _ex_preble, "kvflow": _ex_kvflow,
    "rh8-demand-aware-causal": _ex_rh8,
    "B10-blocking-aware-admission": _ex_b10, "B11-naive-slicing": _ex_b11,
    "B9-noHost": _ex_b9,
    "B3-best-static": _ex_trivial_cloud, "tuned-engine": _ex_trivial_cloud,
    "always-cloud-fcfs": _ex_trivial_cloud,
}


# ---------------------------------------------------------------- whole-run probes
# The first five decisions show the rule; these show whether the rule's inputs EVER move over the
# whole replay, which is what separates "the gate has not fired yet" from "the gate cannot fire".
def _pr_videostorm(pol, obs, act) -> Dict:
    import videostorm as V
    by = {r["name"]: r for r in pol._rows}
    qs = []
    for s in obs.streams:
        q = pol._query(s.stream_id)
        cur = (f"cloud/32BI_N{s.frame_count}@{s.cadence_s}" if s.on_cloud else "local")
        q.lag_s = by.get(cur, pol._rows[0])["lag_s"]
        qs.append(q)
    cap = max(obs.budget_remaining_gpu_s / max(pol.horizon_s, 1e-9), 0.0)
    alloc = (V.allocate_maxmin if pol.objective == "maxmin" else V.allocate_maxsum)(
        qs, cap, pol.horizon_s, pol.delta)
    n_cloud = sum(1 for sid in alloc if by[alloc[sid][1].name]["mode"] == "cloud")
    s0 = obs.streams[0]
    q0 = pol._query(s0.stream_id)
    q0.lag_s = by["local"]["lag_s"]
    cloud_row = by["cloud/32BI_N1@0.5"]
    u_local = V.utility(q0, by["local"]["quality"],
                        V.predict_lag(q0, 0.0, V.Config("local", by["local"]["quality"], 0.0),
                                      pol.horizon_s))
    ccfg = V.Config(cloud_row["name"], cloud_row["quality"], cloud_row["demand_gpu_s_per_s"])
    u_cloud0 = V.utility(q0, cloud_row["quality"], V.predict_lag(q0, 0.0, ccfg, pol.horizon_s))
    return dict(capacity_R=cap, n_streams_allocated_cloud=n_cloud,
                utility_local=u_local, utility_cloud_at_alloc0=u_cloud0,
                quality_gap_cloud_minus_local=cloud_row["quality"] - by["local"]["quality"],
                predicted_lag_cloud_at_alloc0_s=V.predict_lag(q0, 0.0, ccfg, pol.horizon_s),
                lag_max_s=q0.lag_max_s)


def _pr_b9(pol, obs, act) -> Dict:
    ii = pol._component_ii(obs)
    n = max(len(obs.streams), 1)
    n_gate = 0
    for s in obs.streams:
        rho = min(len(s.delivered_scores) / 20.0, 1.0)
        n_gate += int((rho >= pol.readiness_threshold) and s.network.connected)
    n_ii_cloud = sum(1 for v in ii.values() if v["mode"] == "cloud")
    after = {sid: (pol._component_i_stream(r, obs, n) if r["mode"] == "cloud" else r)
             for sid, r in ii.items()}
    n_i_cloud = sum(1 for v in after.values() if v["mode"] == "cloud")
    n_final_cloud = sum(1 for sa in act.streams if sa.mode == "cloud")
    # the same Eq. 1-2 arithmetic the standalone VideoStorm arm runs, inside B9's component (ii)
    import videostorm as V
    s0 = obs.streams[0]
    q0 = V.Query(qid=s0.stream_id,
                 profile=[V.Config(r["name"], r["quality"], max(r["demand_gpu_s_per_s"], 0.0))
                          for r in pol.rows],
                 u_base=0.0, alpha_q=1.0, alpha_min_q=0.0, alpha_l=1.0, lag_max_s=0.5,
                 lag_s=pol.local["lag_s"])
    crow = pol.by["cloud/32BI_N1@0.5"]
    ccfg = V.Config(crow["name"], crow["quality"], crow["demand_gpu_s_per_s"])
    lcfg = V.Config("local", pol.local["quality"], 0.0)
    return dict(ii_utility_local=V.utility(q0, pol.local["quality"],
                                           V.predict_lag(q0, 0.0, lcfg, pol.horizon_s)),
                ii_utility_cloud_at_alloc0=V.utility(
                    q0, crow["quality"], V.predict_lag(q0, 0.0, ccfg, pol.horizon_s)),
                ii_predicted_lag_cloud_s=V.predict_lag(q0, 0.0, ccfg, pol.horizon_s),
                ii_quality_gap=crow["quality"] - pol.local["quality"],
                n_streams=len(obs.streams), n_passed_readiness_gate=n_gate,
                n_cloud_after_component_ii=n_ii_cloud,
                n_cloud_after_component_i=n_i_cloud,
                n_cloud_final=n_final_cloud,
                mean_rho=float(np.mean([min(len(s.delivered_scores) / 20.0, 1.0)
                                        for s in obs.streams])) if obs.streams else 0.0,
                load_pressure=pol._load_pressure(obs))


def _pr_hybrid(pol, obs, act) -> Dict:
    import hybrid_llm_adapted as H
    ps = [float(pol.router.predict(np.asarray([H._features(s)], dtype=float))[0])
          for s in obs.streams]
    return dict(mean_p_w=float(np.mean(ps)) if ps else 0.0,
                max_p_w=float(np.max(ps)) if ps else 0.0,
                threshold=pol.threshold,
                n_below_threshold=sum(1 for p in ps if p < pol.threshold),
                n_cloud_final=sum(1 for sa in act.streams if sa.mode == "cloud"))


def _pr_thinking(pol, obs, act) -> Dict:
    rhos = [min(len({e.representation for e in q.evidence}) / 3.0, 1.0) for q in obs.recall]
    srho = [min(len(s.delivered_scores) / 20.0, 1.0) for s in obs.streams]
    sconf = []
    for s in obs.streams:
        v = s.latest_score()
        sconf.append(0.0 if v is None else max(min((v + 12.0) / 12.0, 1.0), 0.0))
    return dict(mean_recall_rho=float(np.mean(rhos)) if rhos else 0.0,
                max_recall_rho=float(np.max(rhos)) if rhos else 0.0,
                progress_threshold=pol.pt,
                mean_stream_rho=float(np.mean(srho)) if srho else 0.0,
                mean_stream_conf=float(np.mean(sconf)) if sconf else 0.0,
                n_recall_pending=len(obs.recall),
                n_cloud_final=sum(1 for sa in act.streams if sa.mode == "cloud"))


def _pr_preble(pol, obs, act) -> Dict:
    return dict(load_pressure=pol._load_pressure(obs),
                max_load_pressure=pol.max_load_pressure,
                gpu_kv_fraction=obs.cloud.gpu_kv_fraction,
                queued_plus_running=sum(obs.cloud.queued_by_class.values())
                + sum(obs.cloud.running_by_class.values()),
                n_recall_pending=len(obs.recall))


def _pr_b10(pol, obs, act) -> Dict:
    import costs as C
    n_def = sum(1 for ra in act.recall if ra.decision == "DEFER")
    Ts, ds = [], []
    on_cloud = [s for s in obs.streams if s.network.connected]
    for q in obs.recall:
        Ts.append(C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness))
        aff = [s for s in on_cloud if s.cadence_s <= Ts[-1]]
        ds.append(min((pol._tolerable_hold_s(s) for s in aff), default=float("inf")))
    ds = [x for x in ds if not math.isinf(x)]
    return dict(n_recall_pending=len(obs.recall), n_defer=n_def,
                mean_T_s=float(np.mean(Ts)) if Ts else 0.0,
                mean_d_star_s=float(np.mean(ds)) if ds else -1.0,
                n_d_star_finite=len(ds))


def _pr_b7(pol, obs, act) -> Dict:
    import costs as C
    est = [C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness) for q in obs.recall]
    sl = [q.slack_s(obs.now_s) for q in obs.recall]
    return dict(n_recall_pending=len(obs.recall),
                mean_est_s=float(np.mean(est)) if est else 0.0,
                mean_slack_s=float(np.mean(sl)) if sl else 0.0,
                n_reject=sum(1 for ra in act.recall if ra.decision == "REJECT"),
                n_defer=sum(1 for ra in act.recall if ra.decision == "DEFER"))


PROBES: Dict[str, Callable] = {
    "videostorm/maxmin": _pr_videostorm, "videostorm/maxsum": _pr_videostorm,
    "B9-noHost": _pr_b9, "hybrid-llm": _pr_hybrid, "thinking-qwenvl-atdm": _pr_thinking,
    "preble": _pr_preble, "B10-blocking-aware-admission": _pr_b10, "B7-edf-feasibility": _pr_b7,
}


# ---------------------------------------------------------------- engine-level overlap counting
def _overlap_stats(eng) -> Dict:
    """How many episodic requests shared the engine with a recall-class request, and for how
    long. This is what the 4-decimal agreement question needs: the arms agree because the
    overlapping population is tiny, not because the admission rules do nothing."""
    RECALL_KINDS = ("cold", "slice", "append", "escalation", "host_reload")
    rec = [(r.visible_s, r.done_s, r.kind) for r in eng.done
           if r.kind in RECALL_KINDS and r.done_s is not None]
    rec.sort(key=lambda x: (x[0], x[1]))
    ep = [(r.visible_s, r.done_s) for r in eng.done
          if r.kind == "episodic" and r.done_s is not None]
    starts = np.array([x[0] for x in rec]) if rec else np.zeros(0)
    ends = np.array([x[1] for x in rec]) if rec else np.zeros(0)
    n_ov = 0
    for a, b in ep:
        if rec and np.any((starts <= b) & (ends >= a)):
            n_ov += 1
    busy = float(sum(b - a for a, b, _k in rec))
    return dict(n_episodic_done=len(ep), n_recall_class_done=len(rec),
                n_recall_by_kind=dict(Counter(k for _a, _b, k in rec)),
                n_episodic_overlapping_recall=n_ov,
                fraction_episodic_overlapping=(n_ov / len(ep) if ep else None),
                recall_busy_window_s=round(busy, 3),
                engine_clock_s=round(eng.clock, 3),
                recall_busy_fraction_of_run=round(busy / max(eng.clock, 1e-9), 5))


def part_a() -> Dict:
    """Trace every audited arm on the one representative cell and classify it."""
    import run as R
    import workload as W
    tr = W.build_trace(AUDIT_CELL["mix"], AUDIT_CELL["fleet"], AUDIT_CELL["deadline_s"],
                       AUDIT_CELL["seed"])
    arms = {label: p for label, p in R._arms()}
    missing = [a for a in AUDIT_ARMS if a not in arms]
    rows = []
    for label in AUDIT_ARMS:
        if label not in arms:
            continue
        pol = arms[label]
        tp = Traced(pol, EXPLAINERS.get(label), probe=PROBES.get(label))
        import engine as E
        made: List[Any] = []
        real_engine = E.Engine

        class _Capturing(real_engine):                                # noqa: D401
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                made.append(self)

        R.E.Engine = _Capturing
        try:
            res = R.run_cell(tr, tp, seed=AUDIT_CELL["seed"])
        finally:
            R.E.Engine = real_engine
        row = tp.summary()
        row["engine_overlap"] = _overlap_stats(made[-1]) if made else None
        row.update(label=label,
                   challenge_mAP=res["challenge_mAP"],
                   recall_n=res["recall"]["n"],
                   recall_timely_accuracy=res["recall"]["timely_accuracy"],
                   recall_starvation=res["recall"].get("starvation"),
                   episodic_submitted=res["episodic"]["submitted"],
                   episodic_completed=res["episodic"]["completed"],
                   episodic_ttft_p50=res["episodic"]["ttft_p50"],
                   episodic_ttft_p99=res["episodic"]["ttft_p99"],
                   decisions=res["decisions"], engine=res["engine"],
                   gpu_s=res["gpu_s"], gpu_s_budget=res["gpu_s_budget"],
                   trace_digest=res["trace_digest"])
        rows.append(row)
        print("  %-30s mAP %.4f  ep_sub %5d  recall n=%-4s timely %-6s  modes %s" % (
            label, res["challenge_mAP"], res["episodic"]["submitted"],
            res["recall"]["n"],
            ("%.3f" % res["recall"]["timely_accuracy"])
            if res["recall"]["timely_accuracy"] is not None else "-",
            dict(tp.stream_actions)), flush=True)
    # The specification's representative cell is at deadline 5 s, where several of the reported
    # symptoms do not appear. The committed StudySIM1c cells say where they DO appear, and one
    # symptom-bearing cell is traced as well so the mechanism is shown and not inferred.
    sym = _symptom_cells(R, W, arms)
    return dict(
        label="StudySIM1d-validate PART A: arm audit on one representative cell",
        cell=dict(AUDIT_CELL, trace_digest=tr.digest, length_s=tr.length_s,
                  n_streams=tr.n_streams, n_sessions=tr.n_sessions),
        arms=rows, missing_arms=missing,
        symptom_location=_symptom_location(), symptom_cell_traces=sym,
        agreement_in_committed_sim1c=_agreement_table())


SYMPTOM_CELL = dict(mix="balanced", fleet=4, deadline_s=2.0, seed=0)
SYMPTOM_ARMS = ["B7-edf-feasibility", "kvflow", "preble", "rh8-demand-aware-causal",
                "thinking-qwenvl-atdm", "always-cloud-fcfs"]


def _symptom_cells(R, W, arms) -> Dict:
    tr = W.build_trace(SYMPTOM_CELL["mix"], SYMPTOM_CELL["fleet"], SYMPTOM_CELL["deadline_s"],
                       SYMPTOM_CELL["seed"])
    out = []
    for label in SYMPTOM_ARMS:
        if label not in arms:
            continue
        tp = Traced(arms[label], EXPLAINERS.get(label), probe=PROBES.get(label))
        res = R.run_cell(tr, tp, seed=SYMPTOM_CELL["seed"])
        out.append(dict(label=label, challenge_mAP=res["challenge_mAP"],
                        recall=res["recall"], decisions=res["decisions"],
                        recall_actions=dict(tp.recall_actions),
                        stream_actions=dict(tp.stream_actions),
                        probes=tp.probe_summary(),
                        first_recall_decisions=tp.recall_chain))
        print("  [symptom d=2s] %-28s mAP %.4f timely %-7s starved %s" % (
            label, res["challenge_mAP"],
            ("%.4f" % res["recall"]["timely_accuracy"])
            if res["recall"]["timely_accuracy"] is not None else "-",
            res["recall"].get("starved_fraction")), flush=True)
    return dict(cell=dict(SYMPTOM_CELL, trace_digest=tr.digest), arms=out)


def _sim1c_rows() -> List[Dict]:
    import csv
    p = ROOT / "results/orchestration/sim1c/sim1c_cells.csv"
    with p.open() as f:
        return list(csv.DictReader(f))


def _symptom_location() -> Dict:
    """Where in the committed StudySIM1c sweep each reported symptom actually occurs."""
    rows = _sim1c_rows()
    out = {}
    for arm in ("B7-edf-feasibility", "thinking-qwenvl-atdm", "kvflow", "preble",
                "rh8-demand-aware-causal"):
        rs = [r for r in rows if r["arm"] == arm]
        bad = [r for r in rs if float(r["timely_accuracy"]) <= 0.010]
        out[arm] = dict(
            n_cells=len(rs),
            timely_min=min(float(r["timely_accuracy"]) for r in rs),
            timely_max=max(float(r["timely_accuracy"]) for r in rs),
            n_cells_at_or_below_0p010=len(bad),
            deadlines_of_those_cells=sorted({r["deadline_s"] for r in bad}),
            mixes_of_those_cells=sorted({r["mix"] for r in bad}),
            fleets_of_those_cells=sorted({int(r["fleet"]) for r in bad}),
            starved_fraction_of_those_cells=sorted({round(float(r["starved_fraction"]), 4)
                                                    for r in bad}))
    return out


AGREEING = ("B10-blocking-aware-admission", "B11-naive-slicing", "B3-best-static",
            "tuned-engine", "always-cloud-fcfs")


def _agreement_table() -> Dict:
    """How close the five arms the specification names actually are, cell by cell, in the
    committed StudySIM1c sweep."""
    rows = _sim1c_rows()
    by = defaultdict(dict)
    for r in rows:
        if r["arm"] in AGREEING:
            by[(r["mix"], int(r["fleet"]), float(r["deadline_s"]))][r["arm"]] = r
    cells, n4 = [], 0
    for key, d in sorted(by.items()):
        if len(d) < len(AGREEING):
            continue
        maps = [float(v["challenge_mAP"]) for v in d.values()]
        tim = [float(v["timely_accuracy"]) for v in d.values()]
        spread_map = max(maps) - min(maps)
        spread_tim = max(tim) - min(tim)
        n4 += int(spread_map < 5e-5)
        cells.append(dict(mix=key[0], fleet=key[1], deadline_s=key[2],
                          mAP_spread=round(spread_map, 8),
                          timely_spread=round(spread_tim, 8),
                          agree_to_4dp=bool(spread_map < 5e-5),
                          mAP_by_arm={k: round(float(v["challenge_mAP"]), 6)
                                      for k, v in sorted(d.items())}))
    return dict(arms=list(AGREEING), n_cells=len(cells), n_cells_agreeing_to_4dp=n4,
                max_mAP_spread=max((c["mAP_spread"] for c in cells), default=None),
                max_timely_spread=max((c["timely_spread"] for c in cells), default=None),
                cells=cells)


# ================================================================ Part B
# ---------------------------------------------------------------- B1: what is IN the gate
# StudySIM1's gate is `calibrate.REF_P99` (29 cells), `calibrate.REF_CAPACITY` (16 ladders, each
# of which runs EVERY level of its N's ladder bottom-up) and `calibrate.REF_P50` (8 cells). A
# measured cell counts as IN THE GATE if its (kv mode, k, r) matches one of the eight gate
# CONDITIONS and it was measured at the engine configuration the gate reproduces, which is
# vLLM 0.31.0 defaults: StudyE10c's E0, StudyE10e's P0 and every StudyE10b cell. Anything else
# is held out. The rule is deliberately CONSERVATIVE: it marks a cell in-gate on the condition
# alone, without checking whether that exact level was reached before a ladder stopped.
GATE_CONDITION_KEYS = {
    ("KVGPU", 0, 0.0): "C0", ("KVGPU", 0, 0.05): "C1-r05", ("KVGPU", 0, 0.1): "C1-r10",
    ("KVGPU", 4, 0.0): "KVGPU-k4", ("KVGPU", 8, 0.0): "KVGPU-k8",
    ("KVHOST", 8, 0.0): "KVHOST-k8", ("KVHOST", 16, 0.0): "KVHOST-k16",
    ("KVHOST", 8, 0.1): "C4",
}
GATE_CONFIGS = {"E0", "P0", None}          # None = StudyE10b, which ran 0.31.0 defaults


def _cell_key(rs: List[Dict]) -> Tuple[str, int, float, int, int, Optional[str]]:
    r0 = rs[0]
    kv = next((r.get("kv") for r in rs if r.get("kv")), None)
    k = int(next((r.get("k") for r in rs if r.get("k") is not None), 0) or 0)
    r_ = float(next((r.get("r") for r in rs if r.get("r") is not None), 0.0) or 0.0)
    n = int(r0.get("N") or r0.get("n") or 1)
    lvl = int(round(100 * float(r0.get("frac") or 0.0)))
    name = r0["cell"]
    cfg = None
    parts = name.split("_")
    if name.startswith("E10C_") or name.startswith("E10E_"):
        cfg = parts[1]
    return kv, k, r_, n, lvl, cfg


def _cells_by_study() -> Dict[str, Dict[str, List[Dict]]]:
    import sim1b_hosttax as S
    out = {}
    for st in ("e10b", "e10c", "e10e"):
        by = defaultdict(list)
        for r in S.load(st):
            by[r["cell"]].append(r)
        out[st] = dict(by)
    return out


def gate_inventory() -> Dict:
    """Part B.1: exactly which committed cells are in StudySIM1's gate, and which are not."""
    sys.path.insert(0, str(HERE))
    import calibrate as C
    studies = _cells_by_study()
    in_gate, held = [], []
    for st, by in sorted(studies.items()):
        for cell, rs in sorted(by.items()):
            kv, k, r_, n, lvl, cfg = _cell_key(rs)
            cond = GATE_CONDITION_KEYS.get((kv, k, round(r_, 3)))
            is_gate = bool(cond is not None and cfg in GATE_CONFIGS)
            row = dict(study=st, cell=cell, kv=kv, k=k, r=r_, n_frames=n, level_pct=lvl,
                       engine_config=cfg, gate_condition=cond, n_records=len(rs),
                       reason=("condition %s at the gate's engine configuration" % cond
                               if is_gate else
                               ("engine configuration %s is not the one the gate reproduces"
                                % cfg if cond is not None else
                                "(kv, k, r) = (%s, %d, %g) is not one of the gate's eight "
                                "conditions" % (kv, k, r_))))
            (in_gate if is_gate else held).append(row)
    return dict(
        rule="a committed cell is IN StudySIM1's gate iff its (kv, k, r) is one of the eight "
             "calibrate.CONDITIONS and it was measured at vLLM 0.31.0 defaults (StudyE10c E0, "
             "StudyE10e P0, every StudyE10b cell); everything else is HELD OUT",
        gate_conditions={f"{a}|k{b}|r{c}": v for (a, b, c), v in GATE_CONDITION_KEYS.items()},
        gate_reference_counts=dict(p99_cells=len(C.REF_P99), capacity_ladders=len(C.REF_CAPACITY),
                                   p50_cells=len(C.REF_P50)),
        gate_ladder_levels={str(k): list(v) for k, v in C.LADDER.items()},
        n_in_gate=len(in_gate), n_held_out=len(held),
        in_gate=in_gate, held_out=held)


# ---------------------------------------------------------------- B3: PRE-REGISTERED form
OVERLAP_FORMS = {
    "a_blocking_per_step": (
        "a per-step cost added to every engine step that contains a warm recall request's "
        "prefill, charged to ALL requests in that step. It is ENGINE TIME, so queueing "
        "AMPLIFIES it and the OVERLAP-minus-CLEAR difference must GROW with load."),
    "b_nonblocking_per_request": (
        "a fixed added delay per episodic request per concurrent in-flight warm request, "
        "charged off the engine's critical path. It is NOT engine time, so queueing does not "
        "amplify it and the OVERLAP-minus-CLEAR difference must be FLAT or FALL with load."),
}
OVERLAP_DECISION_RULE = (
    "Pre-registered before the fit, and it is StudySIM1b's own test: regress the per-cell "
    "OVERLAP-minus-CLEAR median difference on the cell's load fraction across the HELD-OUT "
    "cells. A slope significantly GREATER than zero (bootstrap CI excluding 0) selects form "
    "(a), blocking. A slope whose CI includes zero, or which is negative, selects form (b), "
    "non-blocking. The magnitude is then taken from the held-out cells only: the OLS "
    "coefficient on the number of concurrent in-flight warm requests, with load as a covariate.")
WARM_KINDS_MEASURED = ("recall_append", "recall_escalation", "recall_warmup")


def part_b_fit() -> Dict:
    """Part B.1-B.3: the gate inventory, the held-out data, the pre-registered form, the fit."""
    import sim1b_hosttax as S
    inv = gate_inventory()
    held_names = {(r["study"], r["cell"]) for r in inv["held_out"]}
    studies = _cells_by_study()

    cells, pooled = [], []
    for st, by in sorted(studies.items()):
        for cell, rs in sorted(by.items()):
            if (st, cell) not in held_names:
                continue
            kv, k, r_, n, lvl, cfg = _cell_key(rs)
            if k <= 0:
                continue                      # no warm session, so no overlap to measure
            lab, exc = S.label_cell(rs)
            if not lab:
                continue
            ov = [x["ttft_s"] for x in lab if x["overlap"]]
            cl = [x["ttft_s"] for x in lab if not x["overlap"]]
            row = dict(study=st, cell=cell, kv=kv, k=k, r=r_, n_frames=n, level_pct=lvl,
                       engine_config=cfg, n=len(lab), n_overlap=len(ov), n_clear=len(cl),
                       excluded_cold_overlap=exc,
                       mean_n_concurrent=float(np.mean([x["n_concurrent"] for x in lab
                                                        if x["overlap"]])) if ov else None)
            if len(ov) >= 20 and len(cl) >= 20:
                row["overlap_p50_s"] = float(np.percentile(ov, 50))
                row["clear_p50_s"] = float(np.percentile(cl, 50))
                row["diff_p50_s"] = S.boot_diff(cl, ov)
            cells.append(row)
            for x in lab:
                x["study"], x["level_pct"], x["engine_config"] = st, lvl, cfg
            pooled += lab

    usable = [c for c in cells if "diff_p50_s" in c]
    # ---- the pre-registered load test
    x = np.array([c["level_pct"] / 100.0 for c in usable])
    y = np.array([c["diff_p50_s"]["point"] for c in usable])
    rng = np.random.default_rng(0)
    slopes = []
    for _ in range(2000):
        idx = rng.integers(0, len(x), len(x))
        if np.ptp(x[idx]) < 1e-9:
            continue
        slopes.append(float(np.polyfit(x[idx], y[idx], 1)[0]))
    slope = float(np.polyfit(x, y, 1)[0]) if np.ptp(x) > 1e-9 else 0.0
    ci = [float(np.percentile(slopes, 2.5)), float(np.percentile(slopes, 97.5))]
    grows = bool(ci[0] > 0.0)
    form = "a_blocking_per_step" if grows else "b_nonblocking_per_request"

    # ---- magnitude, from the held-out requests only
    X = np.column_stack([np.ones(len(pooled)),
                         np.array([float(p["n_concurrent"]) for p in pooled]),
                         np.array([p["frac"] for p in pooled])])
    yy = np.array([p["ttft_s"] for p in pooled])
    names = ["intercept", "n_concurrent", "load_fraction"]
    beta, *_ = np.linalg.lstsq(X, yy, rcond=None)
    bs = np.empty((500, X.shape[1]))
    rng = np.random.default_rng(0)
    for i in range(500):
        idx = rng.integers(0, len(yy), len(yy))
        bs[i], *_ = np.linalg.lstsq(X[idx], yy[idx], rcond=None)
    resid = yy - X @ beta
    coefs = {nm: dict(beta=float(b), ci=[float(np.percentile(bs[:, j], 2.5)),
                                         float(np.percentile(bs[:, j], 97.5))])
             for j, (nm, b) in enumerate(zip(names, beta))}

    by_load = defaultdict(list)
    for c in usable:
        by_load[c["level_pct"]].append(c["diff_p50_s"]["point"])

    # ---- is the effect the same size in both KV modes, on HELD-OUT data?
    by_mode = {}
    for mode in ("KVGPU", "KVHOST"):
        sel = [c for c in usable if c["kv"] == mode]
        if sel:
            v = [c["diff_p50_s"]["point"] for c in sel]
            by_mode[mode] = dict(n_cells=len(sel), median_diff_s=float(np.median(v)),
                                 min_diff_s=float(np.min(v)), max_diff_s=float(np.max(v)),
                                 cells=[c["cell"] for c in sel])
    # ---- the collapse diagnostic: the pre-registered per-request coefficient is dominated by
    # the cells where a warm miss re-prefills the whole history, which the model ALREADY has.
    calm = [p for p in pooled if p["ttft_s"] < 5.0]
    Xc = np.column_stack([np.ones(len(calm)),
                          np.array([float(p["n_concurrent"]) for p in calm]),
                          np.array([p["frac"] for p in calm])])
    yc = np.array([p["ttft_s"] for p in calm])
    bc, *_ = np.linalg.lstsq(Xc, yc, rcond=None)
    collapse_cells = sorted({p["cell"] for p in pooled if p["ttft_s"] >= 5.0})

    # ---- THE REGISTERED MAGNITUDE for form (a). A per-step blocking cost is read at the
    # LOWEST load on the ladder, where queueing amplification is smallest and the measured
    # difference is therefore closest to the raw step cost. Every value comes from a held-out
    # cell; no gate cell is used and no other constant is touched.
    lowest = min(by_load)
    step_cost = float(np.median(by_load[lowest]))

    return dict(
        label="StudySIM1d PART B: the mode-independent overlap cost, fitted on HELD-OUT cells",
        gate_inventory=inv,
        candidate_rule="held out = every committed k > 0 cell that is not in the gate: "
                       "StudyE10b's KV-GPU k = 2 and k = 16 ladders, its KV-GPU k = 8 r = 0.1 "
                       "cells, and StudyE10c's KV-HOST C2 / C3 / C4 cells at engine "
                       "configurations E1, E2 and E4",
        pre_registered_forms=OVERLAP_FORMS, decision_rule=OVERLAP_DECISION_RULE,
        cells=cells, n_cells_usable=len(usable),
        n_requests_pooled=len(pooled),
        load_test=dict(slope_s_per_unit_load=slope, ci=ci, grows_with_load=grows,
                       diff_by_load_pct={str(k): [round(x, 5) for x in v]
                                         for k, v in sorted(by_load.items())},
                       verdict=("form (a), blocking: the OVERLAP penalty grows with load"
                                if grows else
                                "form (b), non-blocking: the OVERLAP penalty does not grow "
                                "with load, so it is not engine time")),
        chosen_form=form,
        regression=dict(model="ttft_s ~ 1 + n_concurrent + load_fraction, OLS over every "
                              "held-out episodic request not overlapping a cold recall; CIs "
                              "from 500 bootstrap refits",
                        n=len(yy), r2=float(1.0 - resid.var() / yy.var()), coefficients=coefs),
        mode_split=dict(
            question="is the effect the same size in KV-GPU and KV-HOST on HELD-OUT data?",
            by_kv_mode=by_mode),
        collapse_diagnostic=dict(
            issue="the pre-registered per-request coefficient is computed over every held-out "
                  "request, and the held-out set contains the KV-GPU k = 16 and k = 8 r = 0.1 "
                  "cells, where a warm miss re-prefills the WHOLE history. Those re-prefills "
                  "are long AND concurrent, so the coefficient on n_concurrent absorbs a "
                  "mechanism the model already has (StudyE10b's collapse chain), and it returns "
                  "%.3f s per concurrent request against a measured OVERLAP-minus-CLEAR "
                  "difference of 0.032-0.088 s. It is reported, and it is NOT the registered "
                  "value." % float(coefs["n_concurrent"]["beta"]),
            collapse_cells=collapse_cells,
            n_requests_above_5s=len(pooled) - len(calm),
            coefficients_excluding_requests_above_5s=dict(
                zip(names, [float(b) for b in bc])),
            n_calm=len(calm)),
        registered_value=dict(
            overlap_step_cost_s=step_cost,
            rule="form (a) is a PER-STEP cost, so its magnitude is read as the median per-cell "
                 "OVERLAP-minus-CLEAR difference at the LOWEST load on the ladder (%d %%), "
                 "where queueing amplification is smallest; the per-request coefficient the "
                 "decision rule names is reported above but is not usable for a per-step form "
                 "and is contaminated by the collapse cells" % lowest,
            from_cells=[c["cell"] for c in usable if c["level_pct"] == lowest],
            n_cells=len(by_load[lowest]),
            values_s=[round(v, 5) for v in sorted(by_load[lowest])],
            lowest_load_pct=lowest),
        overlap_cost_s=float(coefs["n_concurrent"]["beta"]),
        overlap_cost_ci=coefs["n_concurrent"]["ci"],
        no_gate_cell_used=True)


# ---------------------------------------------------------------- B4-B6: the gate and controls
def part_b_gate() -> Dict:
    """Part B.4-B.6: SIM1's gate run ONCE per configuration, the negative controls, and the
    N = 3 diagnosis. Same cells, seeds, bars and collapse rule; no gate cell set any value."""
    sys.path.insert(0, str(HERE))
    import calibrate as C
    import engine as E
    import sim1b_hosttax as S

    fit = json.loads((OUT / "sim1d_part_b_fit.json").read_text())
    ov = float(fit["registered_value"]["overlap_step_cost_s"])
    hm = E.HOST_MODE_COST_S
    if abs(ov - E.OVERLAP_STEP_COST_S) > 1e-9:
        raise AssertionError("the registered value and engine.OVERLAP_STEP_COST_S disagree: "
                             f"{ov} vs {E.OVERLAP_STEP_COST_S}")

    runs = {}
    for label, kw in (("off", {}),
                      ("mode_cost_only", dict(host_mode_cost_s=hm)),
                      ("overlap_only", dict(overlap_step_cost_s=ov)),
                      ("both", dict(host_mode_cost_s=hm, overlap_step_cost_s=ov))):
        print("=== gate:", label, kw, flush=True)
        runs[label] = S.run_gate(label, **kw)

    # ---- negative control 1: the overlap cost at 0 must reproduce StudySIM1b exactly
    prev = json.loads((ROOT / "results/orchestration/sim1b/sim1b_gate.json").read_text())
    ctl = {}
    for ours, theirs in (("off", "off"), ("mode_cost_only", "mode_cost_on")):
        mism = []
        a = {(c["condition"], c["n_frames"], c["level_pct"]): c for c in runs[ours]["cells"]}
        for c in prev["runs"][theirs]["cells"]:
            k = (c["condition"], c["n_frames"], c["level_pct"])
            x, y = c["sim_p99_s"], a[k]["sim_p99_s"]
            same = (x == y) or (x is None and y is None) or (
                isinstance(x, float) and isinstance(y, float)
                and math.isinf(x) and math.isinf(y))
            if not same:
                mism.append(dict(cell="%s N%d %d%%" % k, sim1b=x, sim1d=y))
        ctl["control_1_%s_reproduces_sim1b_%s" % (ours, theirs)] = dict(
            rule="with the overlap cost at 0 the gate must reproduce StudySIM1b cell for cell, "
                 "bit-exactly",
            n_cells=len(prev["runs"][theirs]["cells"]), n_mismatch=len(mism),
            mismatches=mism, pass_=bool(not mism))

    # ---- negative control 2: with no warm sessions, every cell must be unchanged
    nowarm = [c for c in runs["off"]["cells"] if C.CONDITIONS[c["condition"]][1] == 0]
    on = {(c["condition"], c["n_frames"], c["level_pct"]): c
          for c in runs["overlap_only"]["cells"]}
    bad = []
    for c in nowarm:
        k = (c["condition"], c["n_frames"], c["level_pct"])
        if c["sim_p99_s"] != on[k]["sim_p99_s"]:
            bad.append(dict(cell="%s N%d %d%%" % k, off=c["sim_p99_s"], on=on[k]["sim_p99_s"]))
    ctl["control_2_no_warm_sessions_unchanged"] = dict(
        rule="the cost is charged only on a step carrying a WARM recall prefill, so every cell "
             "with k = 0 warm sessions (C0, C1-r05, C1-r10) must be bit-identical with the "
             "option ON",
        n_cells=len(nowarm), n_changed=len(bad), changed=bad, pass_=bool(not bad))

    # ---- the N = 3 diagnosis (DIAGNOSE, do not fix)
    diag = _n3_diagnosis(C, E, runs["both"])

    best = max(runs, key=lambda k: (runs[k]["p99_fraction_agree"]
                                    + runs[k]["ladders_fraction_agree"]))
    return dict(
        label="StudySIM1d PART B gate: StudySIM1's calibration gate, unchanged, with the "
              "host mode cost and the mode-independent overlap cost OFF, each alone, and both",
        host_mode_cost_s=hm, overlap_step_cost_s=ov,
        no_gate_cell_used_to_set_any_value=True,
        runs=runs, controls=ctl, n3_diagnosis=diag,
        summary={k: dict(GATE=v["GATE"], p99="%d/%d" % (v["p99_cells_agree"],
                                                        v["p99_cells_total"]),
                         capacity="%d/%d" % (v["ladders_agree"], v["ladders_total"]))
                 for k, v in runs.items()},
        best_configuration=best)


def _n3_diagnosis(C, E, run) -> Dict:
    """What in the model makes N = 3 queue more than the measurement. DIAGNOSIS ONLY: nothing
    here is changed, and the fix the diagnosis points at needs a measurement we do not have."""
    from collections import Counter as _C
    rows = []
    for cond, n, lvl in (("C0", 1, 10), ("C0", 3, 10), ("C0", 1, 25), ("C0", 3, 25),
                         ("C0", 1, 40), ("C0", 3, 35), ("C0", 1, 50), ("C0", 3, 50)):
        kv, k, r = C.CONDITIONS[cond]
        eng = E.Engine(config="P0", kv_mode=kv)
        total = C.DISCARD_S + C.WINDOW_S
        rate = C.PEAK_REQ_S[n] * lvl / 100.0
        rng = np.random.default_rng(0)
        t, i = 0.0, 0
        while True:
            t += rng.exponential(1.0 / rate)
            if t >= total:
                break
            eng.submit(E.episodic_request(f"ep{i}", t, n))
            i += 1
        eng.run_until(total + 300)
        eng.drain()
        ep = [x for x in eng.done if x.kind == "episodic"
              and C.DISCARD_S <= x.arrival_s < total]
        done_at = _C(round(x.done_s, 9) for x in ep)
        share = np.array([done_at[round(x.done_s, 9)] for x in ep], dtype=float)
        tt = np.array([x.ttft_s() for x in ep])
        hi = tt >= np.percentile(tt, 99)
        tok = {1: 378, 3: 1062}[n]
        quantum = tok / E.RATE_EPISODIC_TOK_S
        p50, p99 = float(np.percentile(tt, 50)), float(np.percentile(tt, 99))
        meas99 = C.REF_P99.get((cond, n, lvl), (None, ""))[0]
        meas50 = C.REF_P50.get((cond, n, lvl), (None, ""))[0]
        rows.append(dict(
            condition=cond, n_frames=n, level_pct=lvl, n_episodic=len(ep),
            prompt_tokens=tok, queueing_quantum_s=round(quantum, 5),
            sim_p50_s=round(p50, 4), sim_p99_s=round(p99, 4),
            measured_p50_s=meas50, measured_p99_s=meas99,
            sim_p99_minus_p50_s=round(p99 - p50, 4),
            measured_p99_minus_sim_p50_s=(None if meas99 is None
                                          else round(meas99 - p50, 4)),
            tail_in_quanta_sim=round((p99 - p50) / quantum, 3),
            tail_in_quanta_measured=(None if meas99 is None
                                     else round((meas99 - p50) / quantum, 3)),
            fraction_sharing_a_step=round(float((share > 1).mean()), 4),
            mean_requests_per_finishing_step=round(float(share.mean()), 4),
            mean_share_of_the_p99_requests=round(float(share[hi].mean()), 3),
            max_requests_per_step_at_budget=round(E.MAX_NUM_BATCHED_TOKENS / float(tok), 2)))
    n3 = [c for c in run["cells"] if c["n_frames"] == 3 and c["ratio"] is not None
          and not math.isinf(c["ratio"])]
    n1 = [c for c in run["cells"] if c["n_frames"] == 1 and c["ratio"] is not None
          and not math.isinf(c["ratio"])]
    over3 = [c for c in n3 if not c["agree"] and c["ratio"] > 1]
    return dict(
        question="what in the model makes N = 3 queue more than the measurement?",
        ratio_by_n_frames=dict(
            N1=dict(n=len(n1), median_sim_over_measured=float(np.median([c["ratio"]
                                                                         for c in n1])),
                    n_disagree=sum(1 for c in n1 if not c["agree"])),
            N3=dict(n=len(n3), median_sim_over_measured=float(np.median([c["ratio"]
                                                                         for c in n3])),
                    n_disagree=sum(1 for c in n3 if not c["agree"]),
                    n_disagree_by_over_prediction=len(over3),
                    over_predicted_cells=["%s N%d %d%% ratio %.2f"
                                          % (c["condition"], c["n_frames"], c["level_pct"],
                                             c["ratio"]) for c in over3])),
        cells=rows,
        mechanism=(
            "IT IS NOT THE QUEUE, IT IS THE QUEUEING QUANTUM. The model's p50 is right at both "
            "N: 0.264 s simulated at N = 3 against StudyE10c's measured 0.25-0.30 s, and 0.144 s "
            "at N = 1 against its 0.14-0.15 s. What differs is what a request pays when it is "
            "NOT admitted at the start of a step. In this model a step's duration is the SERIAL "
            "SUM of the compute of every request in it, so a request that arrives mid-step waits "
            "one whole quantum of prompt_tokens / 5,708 tok/s: 0.066 s at N = 1 and 0.186 s at "
            "N = 3, 2.8x more. The measurement does not behave that way. At C0 N = 3 10 %, where "
            "the simulator records NO step sharing at all, the simulated tail above the median "
            "is 0.173 s - 0.93 of one quantum - while the measured tail above the same median is "
            "0.096 s, about HALF a quantum. A waiting request in the real engine is therefore "
            "released part way through the running prefill, which is what vLLM's V1 scheduler "
            "does: with an 8,192-token step budget it admits up to 7 requests of 1,062 tokens "
            "into ONE forward pass, and that pass is SUB-LINEAR in its tokens because a single "
            "1,062-token prefill does not saturate the GPU. The model has no sub-linear batching "
            "term, so it over-charges every concurrent prefill by the sharer's own compute time. "
            "At N = 1 that error is 0.066 s and stays inside the +/-25 % band of a 0.45 s budget; "
            "at N = 3 it is 0.186 s against a budget only 2.7x larger, so the N = 3 cells fall "
            "outside it. This is an ABSENT link in the sense of CLAUDE.md Step 2, not a "
            "mis-set constant: StudyD7 and StudyD7b measured PER-REQUEST peaks (15.10 req/s at "
            "378 tokens and 5.38 req/s at 1,062), and nothing committed measures BATCHED prefill "
            "throughput at either N. Correcting it would need that measurement, which this study "
            "does not have, so it is diagnosed and left alone."),
        limits_of_this_diagnosis=(
            "Two things the table shows that the mechanism above does not fully explain. First, "
            "the same over-charge is present at N = 1: the simulated tail is 1.10 / 2.15 / 4.14 "
            "/ 4.73 quanta at 10 / 25 / 40 / 50 % against a measured 1.09 / 1.92 / 3.61 / 4.32, "
            "so the model is 1 to 15 % long there too - it is only in SECONDS that N = 3 leaves "
            "the band. Second, the sign REVERSES at C0 N = 3 50 %, where the simulated tail is "
            "3.48 quanta against a measured 4.27, so at the top of the N = 3 ladder the model "
            "under-queues instead. A single missing sub-linear batching term does not produce a "
            "sign reversal, so at least one further effect is present at high N = 3 load and is "
            "not identified here."),
        what_would_fix_it=(
            "a committed measurement of prefill wall time against batch token count on the same "
            "server - for example StudyE10c's E0 configuration driven at a fixed concurrency of "
            "1, 2, 4 and 8 simultaneous N = 1 and N = 3 prefills - which would give the engine a "
            "measured step-time curve instead of a linear one"),
        not_fixed=True)


# ================================================================ Part C
CONFIGS_C = {
    "sim1_baseline_all_off": {},
    "host_mode_cost_on": dict(host_mode_cost_s=None),
    "host_mode_plus_overlap_on": dict(host_mode_cost_s=None, overlap_step_cost_s=None),
}


def _measured() -> Dict:
    return json.loads((ROOT / "results/cost/study_slice1/slice1_live_results.json").read_text())


def _cap_idx(level: Optional[int], ladder=None) -> int:
    """Part B's own index, on PART B'S FULL LADDER: 0 means 'below the ladder', otherwise 1 plus
    the level's position in (10, 20, 25, 30, 40). C0 was measured only at 25 and 40 %, but its
    index is still taken on the full ladder, which is how Part B records it (40 % -> 5)."""
    import sim1d_slice as _S
    return 0 if level is None else (list(_S.LADDER).index(level) + 1)


def mechanism_verification_part_c(S) -> Dict:
    """CLAUDE.md Steps 1-5, recorded BEFORE Part C's sweep runs."""
    prof = S.part_a_profile()
    # Step 3: one traced cold recall under P4, slice by slice.
    traced = S.run_cell("C1a", "P4", 25, seed_level_index=0, trace=True)
    t3 = (traced["traces"] or [None])[0]
    # Step 4: the negative control. Slicing and gap alignment are the mechanisms under test, so
    # with no episodic traffic in the way (C0's r = 0 has no cold recall at all, so the control
    # is run instead by removing the GAP, i.e. by comparing P4 against P3_2048, which is P4
    # without the slack guard, and P3_2048 against P1, which is the same chain with no alignment)
    ctl = {}
    for pol in ("P1", "P3_2048", "P4"):
        c = S.cell_median("C1a", pol, 25)
        ctl[pol] = dict(p99_s=c["p99_s"], meets_budget=c["meets_budget"],
                        t_answer_p50=c["t_answer_p50"], frac_10s=c["frac_10s"])
    disabled = {}
    for pol in ("P3_2048", "P4"):
        c = S.cell_median("C1a", pol, 25, cold_rate_tok_s=None)
        disabled[pol] = c["p99_s"]
    return dict(
        step1_causal_chain=(
            "research/FORMULATION.md scopes Context Inertia as a PHYSICAL cost that grows with "
            "context length, and StudyE10c section 6 / StudyE10d located its mechanism in this "
            "engine: a cold history prefill is ONE non-preemptive unit, so an episodic request "
            "arriving during it is not scheduled until the step that produces the cold "
            "request's first token. The chain Part C tests is: (1) if the materialization is "
            "split into prefix-chained slices then the longest non-preemptive unit falls from "
            "the whole history to one slice (StudySLICE1 Part A measured exactly this: 2.06 s "
            "-> 0.39 s at 2,048 tokens); (2) if the longest unit is shorter than the gap "
            "between episodic calls, an episodic request waits at most one slice instead of a "
            "whole prefill; (3) if slices are additionally dispatched only into gaps, the wait "
            "falls again; so (4) episodic p99 stays inside the 0.45 s budget at a higher "
            "arrival rate, which is capacity. Part C asks whether the simulator reproduces (4) "
            "on a measurement it has never seen."),
        step2_links=[
            dict(link="(1) slicing shortens the longest non-preemptive unit",
                 quantity="the per-part compute_tokens the orchestrator submits",
                 value_or_range="monolithic %d tokens in one request; %d parts of <= %d tokens "
                                "at n = 2,048 and %d parts at n = 1,024"
                                % (prof["prompt_tokens"],
                                   len(S.build_parts("P4", prof)),
                                   max(p.new_tokens for p in S.build_parts("P4", prof)),
                                   len(S.build_parts("P3_1024", prof))),
                 varies="YES, by policy", evidence="build_parts, Part A's own chain geometry"),
            dict(link="(2) an episodic request waits at most one unit",
                 quantity="episodic TTFT p99 in the cell",
                 value_or_range="P1 %.3f s vs P3_2048 %.3f s at C1a 25 %%"
                                % (ctl["P1"]["p99_s"], ctl["P3_2048"]["p99_s"]),
                 varies="YES", evidence="the Step 4 control rows below"),
            dict(link="(3) gap dispatch shortens it further",
                 quantity="episodic TTFT p99 with the gap guard on",
                 value_or_range="P3_2048 %.3f s vs P4 %.3f s"
                                % (ctl["P3_2048"]["p99_s"], ctl["P4"]["p99_s"]),
                 varies="YES" if abs(ctl["P3_2048"]["p99_s"] - ctl["P4"]["p99_s"]) > 1e-6
                        else "NO - at this cell the guard never fires",
                 evidence="the released_by counters in each cell"),
            dict(link="(4) capacity rises",
                 quantity="the highest ladder level meeting p99 <= 0.45 s",
                 value_or_range="computed in the sweep below",
                 varies="measured against Part B", evidence="the per-configuration tables"),
            dict(link="the recall still answers in time",
                 quantity="time to answer and the fraction within 10 s",
                 value_or_range="P1 %.2f s / %.2f; P4 %.2f s / %.2f"
                                % (ctl["P1"]["t_answer_p50"], ctl["P1"]["frac_10s"],
                                   ctl["P4"]["t_answer_p50"], ctl["P4"]["frac_10s"]),
                 varies="YES", evidence="the same cells")],
        step3_traced_cold_recall=t3,
        step3_note="one cold recall under P4 at C1a 25 %, slice by slice: the release reason, "
                   "the slack start the guard compared against, the engine window, and every "
                   "episodic request whose engine window it overlapped. Hand-checkable: a slice "
                   "released 'gap' has next_episodic_due_s - now_s > pred_s, and one released "
                   "'slack' has now_s >= slack_start_s.",
        step4_negative_control=dict(
            rule="disable the mechanism under test and the result must collapse. Slicing IS the "
                 "mechanism, so P1 (the same admission queue with ONE monolithic unit) is the "
                 "disabled arm and P3_2048 / P4 are the enabled ones.",
            cells=ctl,
            mechanism_present=bool(ctl["P1"]["p99_s"] > 1.5 * ctl["P3_2048"]["p99_s"]),
            p99_with_slicing_disabled=ctl["P1"]["p99_s"],
            p99_with_slicing_enabled=ctl["P3_2048"]["p99_s"],
            extra=disabled),
        step5_alternative_explanation=(
            "The headline 'P4 restores capacity' could also be produced by (b) P4 simply "
            "DELAYING the cold recall until the episodic traffic has drained, which any "
            "admission policy that waits long enough would do, rather than by slicing. The data "
            "separate them: P2 is exactly that policy - monolithic, held until its slack runs "
            "out - and it does NOT restore capacity in the measurement (< 10 % at C1a) while "
            "its answers slide to a 9.8 s median; P4 restores capacity AND answers at a 3.4-8.2 "
            "s median. A second alternative, (c) that the chain is simply CHEAPER, is excluded "
            "by Part A: chain / monolithic engine time is 0.990-1.093, so the chain costs the "
            "same or slightly more. If P4 and P2 had the same capacity the experiment could not "
            "distinguish them, and that is reported per configuration."))


def part_c() -> Dict:
    import engine as E
    import sim1d_slice as S
    meas = _measured()
    fit = json.loads((OUT / "sim1d_part_b_fit.json").read_text())
    ovc = float(fit["registered_value"]["overlap_step_cost_s"])

    print("=== Part C mechanism verification (before the sweep)", flush=True)
    mv = mechanism_verification_part_c(S)

    configs = {
        "sim1_baseline_all_off": {},
        "host_mode_cost_on": dict(host_mode_cost_s=E.HOST_MODE_COST_S),
        "host_mode_plus_overlap_on": dict(host_mode_cost_s=E.HOST_MODE_COST_S,
                                          overlap_step_cost_s=ovc),
    }
    out_cfg = {}
    for cname, kw in configs.items():
        print("=== Part C configuration:", cname, kw, flush=True)
        pairs, cells = [], []
        for cond in ("C1a", "C1b", "C4", "C0"):
            pols = S.POLICIES if cond != "C0" else ("P0",)
            levels = S.LADDER if cond != "C0" else S.C0_LEVELS
            for pol in pols:
                cap, p99 = S.capacity(cond, pol, levels=levels, **kw)
                m = meas.get("table", {}).get(cond, {}).get(pol)
                det = S.cell_median(cond, pol, levels[0], **kw)
                mi = None if m is None else m["capacity_idx"]
                si = _cap_idx(cap)
                pairs.append(dict(
                    condition=cond, policy=pol,
                    sim_capacity_pct=cap, sim_capacity_idx=si,
                    measured_capacity=(None if m is None else m["capacity"]),
                    measured_capacity_idx=mi,
                    within_one_level=(None if mi is None else bool(abs(si - mi) <= 1)),
                    exact=(None if mi is None else bool(si == mi)),
                    sim_p99_by_level={str(k): v for k, v in p99.items()},
                    sim_t_answer_p50=det["t_answer_p50"], sim_t_answer_p90=det["t_answer_p90"],
                    sim_frac_10s=det["frac_10s"], sim_frac_5s=det["frac_5s"],
                    sim_unanswered=det["unanswered"], sim_cold_n=det["cold_n"],
                    measured_t_answer_p50=(None if m is None else m.get("t_answer_p50")),
                    measured_t_answer_p90=(None if m is None else m.get("t_answer_p90")),
                    measured_frac_10s=(None if m is None else m.get("frac_10s")),
                    measured_frac_5s=(None if m is None else m.get("frac_5s")),
                    measured_unanswered=(None if m is None else m.get("unanswered"))))
                for lvl, v in p99.items():
                    mc = None if m is None else next((c for c in m["cells"]
                                                      if abs(c["frac"] * 100 - lvl) < 1e-6), None)
                    cells.append(dict(condition=cond, policy=pol, level_pct=lvl,
                                      sim_p99_s=v,
                                      measured_p99_s=(None if mc is None else mc["p99"]),
                                      measured_p50_s=(None if mc is None else mc["p50"]),
                                      measured_p90_s=(None if mc is None else mc["p90"]),
                                      ratio=(None if (mc is None or not mc["p99"] or v is None
                                                      or math.isinf(v)) else v / mc["p99"])))
                print("   %-4s %-9s sim %-6s meas %-8s" % (
                    cond, pol, str(cap), None if m is None else m["capacity"]), flush=True)

        comparable = [p for p in pairs if p["within_one_level"] is not None]
        n_ok = sum(1 for p in comparable if p["within_one_level"])
        frac = n_ok / max(len(comparable), 1)
        # the C1a ordering check: P4 highest; P3_1024 above P0, P1 and P2
        c1a = {p["policy"]: p["sim_capacity_idx"] for p in pairs if p["condition"] == "C1a"}
        ord_p4 = bool(c1a.get("P4", -1) >= max(v for k, v in c1a.items() if k != "P4"))
        ord_p3 = bool(all(c1a.get("P3_1024", -1) > c1a.get(k, 99) for k in ("P0", "P1", "P2")))
        p4 = next(p for p in pairs if p["condition"] == "C1a" and p["policy"] == "P4")
        p4_ok = bool(abs(p4["sim_capacity_idx"] - _cap_idx(30)) <= 1)
        out_cfg[cname] = dict(
            options=kw, pairs=pairs, cells=cells,
            n_comparable_pairs=len(comparable), n_within_one_level=n_ok,
            fraction_within_one_level=frac,
            check_capacity_80pct=bool(frac >= 0.80),
            check_c1a_ordering=dict(p4_highest=ord_p4,
                                    p3_1024_above_p0_p1_p2=ord_p3,
                                    pass_=bool(ord_p4 and ord_p3),
                                    sim_c1a_capacity_idx=c1a),
            check_p4_c1a_within_one_level_of_30pct=p4_ok,
            PASS=bool(frac >= 0.80 and ord_p4 and ord_p3 and p4_ok))
        print("   -> capacity %d/%d (%.0f %%), ordering p4=%s p3=%s, p4@C1a %s  => %s" % (
            n_ok, len(comparable), 100 * frac, ord_p4, ord_p3, p4_ok,
            "PASS" if out_cfg[cname]["PASS"] else "FAIL"), flush=True)

    # declared sensitivity: the cold prefill rate. The simulator's own constant (StudyRH5's
    # 4,500 tok/s at 11k) is PRIMARY; StudySLICE1 PART A's measured monolithic rate is the
    # sensitivity. Neither comes from Part B.
    prof = S.part_a_profile()
    sens = {}
    for lab, rt in (("simulator RATE_COLD_BY_SIZE 11k = %.0f tok/s"
                     % E.RATE_COLD_BY_SIZE[11050], None),
                    ("StudySLICE1 Part A monolithic rate = %.0f tok/s"
                     % prof["mono_rate_tok_s"], prof["mono_rate_tok_s"])):
        rows = []
        for pol in S.POLICIES:
            cap, _p = S.capacity("C1a", pol, cold_rate_tok_s=rt)
            m = meas["table"]["C1a"][pol]
            rows.append(dict(policy=pol, sim_capacity_pct=cap,
                             measured_capacity=m["capacity"],
                             within_one_level=bool(abs(_cap_idx(cap)
                                                       - m["capacity_idx"]) <= 1)))
        sens[lab] = rows

    return dict(
        label="StudySIM1d PART C: the simulator against StudySLICE1 Part B, held out",
        mirrored_from=S.MIRRORED_FROM,
        part_a_profile=prof,
        no_part_b_number_used_to_set_a_parameter=True,
        pre_registered_pass=(
            "per configuration: the capacity level matches Part B within one ladder level in "
            ">= 80 % of (condition, policy) pairs, AND the C1a ordering matches (P4 highest; "
            "P3_1024 above P0, P1 and P2), AND P4's C1a capacity is within one level of the "
            "measured 30 %"),
        mechanism_verification=mv,
        configurations=out_cfg,
        cold_rate_sensitivity=dict(
            rule="the cold prefill rate is the one workload constant where two committed "
                 "measurements disagree: StudyRH5 Part A's 4,500 tok/s at 11k (the simulator's "
                 "own constant, PRIMARY) and StudySLICE1 Part A's 5,375 tok/s on this server. "
                 "Both are held-in; neither is a Part B number.",
            rows=sens),
        p5_entry_point=dict(
            where="experiments/orchestration/sim/sim1d_slice.py",
            how="add 'P5' to POLICIES, give build_parts a P5 branch (warm appends deferred and "
                "coalesced) and add a P5 case to _release_time (escalations gap-aligned). "
                "Nothing else changes: run_cell, cell_median and capacity are policy-agnostic, "
                "and part_c() iterates S.POLICIES.",
            not_implemented_now=True,
            reason="StudySLICE1 Part C is still running on the H100; implementing P5 before its "
                   "ground truth exists would make it an in-sample arm"))


# ================================================================ entry point
def _write(name: str, obj: Dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "experiments/lib"))
    from _provenance import stamp
    obj["_provenance"] = stamp(script=f"sim1d_validate.py --{name}", model=None, device="cpu",
                               n=len(obj.get("arms", obj.get("cells", []))), args=None)
    p = OUT / f"sim1d_{name}.json"
    p.write_text(json.dumps(obj, indent=1, default=str))
    print("wrote", p)
    return p


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--part-a", action="store_true")
    ap.add_argument("--part-b-fit", action="store_true")
    ap.add_argument("--part-b-gate", action="store_true")
    ap.add_argument("--part-c", action="store_true")
    a = ap.parse_args()
    if a.part_a:
        _write("part_a", part_a())
        return 0
    if a.part_b_fit:
        _write("part_b_fit", part_b_fit())
        return 0
    if a.part_b_gate:
        _write("part_b_gate", part_b_gate())
        return 0
    if a.part_c:
        _write("part_c", part_c())
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
