"""Cascade routing - Dekoninck, Baader and Vechev, ICML 2025 (arXiv:2410.10347).

See `cards/cascade_routing.md`. The paper's contribution is that ROUTING (choose one model per
query) and CASCADING (run increasingly larger models until the answer is good enough) are special
cases of one strategy, and that the unified rule is optimal under its formulation. It is therefore
NOT a duplicate of `cascade_adapted.py` (FrugalGPT + AutoMix), which has a fixed order and can
never skip the small model, nor of `routellm_adapted.py` / `hybrid_llm_adapted.py`, which route
once and can never escalate. This arm can do both.

The decision rule, faithful: at each step, over every SUPERMODEL (ordered model set) containing the
models already run, pick the one maximising expected quality minus lambda times expected cost; if
it adds no unrun model, stop, otherwise run the cheapest unrun model in it.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction, StreamAction,
                       DEFAULTS)

# Ex-ante quality priors. COMMITTED StudyR1 cells, not invented for this arm:
#   32B-I x RICH = 0.3953 (K1), 32B-I x RECENT = 0.3834 (K3), device 4B-I x RECENT = 0.3278.
# The paper's ex-ante estimator is a trained classifier; we substitute committed priors and the
# card states the consequence, that this tests the SELECTION RULE and not the estimator.
Q_CLOUD_RICH = 0.3953
Q_CLOUD_RECENT = 0.3834
Q_DEVICE = 0.3278

LAMBDA_BASE = 0.02          # quality units per GPU-second at full budget
LAMBDA_SQUEEZE = 8.0        # how hard lambda rises as the budget depletes


class CascadeRoutingAdapted(Policy):
    """Cascade routing over our two-model set: device 4B-I and cloud 32B."""

    name = "cascade-routing"
    case = "D"
    experiments = ("C-mixed",)
    decides = ("recall_decision", "representation", "episodic_mode")
    defaults_used = ("cadence_s", "frame_count", "defer_s", "session_action", "order",
                     "engine_config")
    # The POST-HOC update the paper requires. This is a LIVE channel, verified before the arm was
    # written: declared at interface.py:370, read at coordinator.py:171, passed into
    # cstate.observation(...); the field reaches only arms that declare it.
    reads_device_answer = True

    def __init__(self, lambda_base: float = LAMBDA_BASE,
                 squeeze: float = LAMBDA_SQUEEZE) -> None:
        self.lambda_base = float(lambda_base)
        self.squeeze = float(squeeze)
        self.stats: Dict[str, Any] = dict(
            arm=self.name, route_cloud_direct=0, route_device_stop=0,
            cascade_started=0, cascade_escalated=0, cascade_stopped_posthoc=0,
            cloud_infeasible=0)

    def reset(self, seed: int = 0) -> None:
        for k in list(self.stats):
            if isinstance(self.stats[k], int):
                self.stats[k] = 0

    # ---- lambda: "set so the expected cost budget B is met", read against the live budget
    def _lmbda(self, obs: Observation) -> float:
        total = max(float(getattr(obs, "budget_total_gpu_s", 0.0) or 0.0), 1e-9)
        left = max(float(getattr(obs, "budget_remaining_gpu_s", 0.0) or 0.0), 0.0)
        frac_spent = 1.0 - min(left / total, 1.0) if total > 1e-9 else 0.0
        return self.lambda_base * (1.0 + self.squeeze * frac_spent)

    @staticmethod
    def _cloud_cost_and_latency(q, rep: str) -> Tuple[float, float]:
        tok = max(int(q.readiness_tokens), 1)
        if rep == "RECENT":
            tok = max(min(467, tok), 1)          # the committed RECENT window
        return C.recall_gpu_s(tok, q.readiness), C.recall_ttft_s(tok, q.readiness)

    def decide(self, obs: Observation) -> Action:
        lam = self._lmbda(obs)
        rec: List[RecallAction] = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            rec.append(self._one(q, obs, lam))
        streams = [StreamAction(s.stream_id, DEFAULTS["episodic_mode"])
                   for s in obs.streams if s.network.connected]
        return Action(streams=streams, recall=rec, sessions=[],
                      notes=dict(rule="cascade routing: argmax over supermodels of "
                                      "quality - lambda * cost, stop when nothing unrun is added",
                                 lambda_now=round(lam, 5)))

    def _one(self, q, obs: Observation, lam: float) -> RecallAction:
        slack = max(q.slack_s(obs.now_s), 0.0)
        conf = getattr(q, "device_answer_confidence", None)

        # value of each cloud representation, excluding any that cannot land inside the deadline
        opts: Dict[str, Tuple[float, float]] = {}
        for rep, qual in (("RICH", Q_CLOUD_RICH), ("RECENT", Q_CLOUD_RECENT)):
            cost, lat = self._cloud_cost_and_latency(q, rep)
            if lat <= slack:
                opts[rep] = (qual, cost)
        if not opts:
            self.stats["cloud_infeasible"] += 1
            return RecallAction(q.query_id, "DEVICE")

        best_rep = max(opts, key=lambda r: opts[r][0] - lam * opts[r][1])
        q_cloud, c_cloud = opts[best_rep]

        if conf is not None:
            # ---- POST-HOC step. The device has answered; its confidence updates the estimate of
            # what escalating is still worth. A confident device answer lowers the marginal gain.
            q_dev_post = Q_DEVICE + (1.0 - Q_DEVICE) * float(conf)
            gain = q_cloud - q_dev_post
            if gain - lam * c_cloud > 0.0:
                self.stats["cascade_escalated"] += 1
                return RecallAction(q.query_id, "CLOUD", representation=best_rep)
            self.stats["cascade_stopped_posthoc"] += 1
            return RecallAction(q.query_id, "DEVICE")

        # ---- EX-ANTE step over the three supermodels.
        v_device = Q_DEVICE - lam * 0.0
        v_cloud = q_cloud - lam * c_cloud
        # {device, cloud}: quality of the best member, cost of both, and it buys the post-hoc look
        v_both = max(Q_DEVICE, q_cloud) - lam * c_cloud
        best = max((v_device, "device"), (v_cloud, "cloud"), (v_both, "both"))[1]
        if best == "cloud":
            self.stats["route_cloud_direct"] += 1
            return RecallAction(q.query_id, "CLOUD", representation=best_rep)
        if best == "device":
            self.stats["route_device_stop"] += 1
            return RecallAction(q.query_id, "DEVICE")
        self.stats["cascade_started"] += 1          # run the cheapest unrun model: the device
        return RecallAction(q.query_id, "DEVICE")
