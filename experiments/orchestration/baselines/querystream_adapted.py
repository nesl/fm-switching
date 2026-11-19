"""QueryStream (ICLR 2026) - the PROACTIVE RESPONSE half only.

See `cards/querystream.md`. The pre-check required by D134 split this method in two and the halves
go opposite ways:

  * Query-Aware Differential Pruning (QDP) chooses WHICH EVIDENCE to send. Its channel is live
    since Part A, but its SIGNAL is absent: QDP prunes on semantic relevance and temporal novelty,
    and `RecallQuery` exposes no token- or frame-level relevance at all. The only query-side
    feature is `category`, which two independent routes have shown is noise and harmful to act on.
    Channel live, signal absent. NOT PORTED, and not merely pending.

  * Proactive Response chooses WHEN to answer rather than answering on a fixed schedule. Its
    signal IS available, and it is ported here.

What this arm decides in our setting: for each robot question, whether the evidence in hand is
already enough to answer, or whether to DEFER and let the stream supply more first - while never
deferring past the point where the answer can still land inside its deadline.
"""
from __future__ import annotations
from typing import Any, Dict, List

import costs as C
from interface import (Action, Observation, Policy, RecallAction, StreamAction, DEFAULTS)

DEFER_QUANTUM_S = 0.25          # one decision period; the smallest wait that can change anything
SETTLE_FRAC = 0.02              # evidence has "settled" when it grew by less than this
                                # fraction over one decision period


class QueryStreamProactiveAdapted(Policy):
    """QueryStream's proactive-response rule, without QDP."""

    name = "querystream-proactive"
    case = "D"
    experiments = ("B-recall",)
    decides = ("recall_decision", "defer_s", "episodic_mode")
    # NOTE: `representation` is deliberately NOT decided. Choosing evidence is QDP's job and QDP is
    # not ported, so this arm leaves representation unset and is CHEAP-INJECTED on the two-axis
    # rule: comparable with RECENT-effective arms, entitled to no credit for the discount.
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order",
                     "engine_config")

    def __init__(self, defer_quantum_s: float = DEFER_QUANTUM_S,
                 settle_frac: float = SETTLE_FRAC) -> None:
        self.defer_q = float(defer_quantum_s)
        self.settle_frac = float(settle_frac)
        self._seen: Dict[str, int] = {}
        self.stats: Dict[str, Any] = dict(
            arm=self.name, answered_now=0, deferred_for_evidence=0,
            answered_on_deadline_pressure=0, no_wait_possible=0)

    def reset(self, seed: int = 0) -> None:
        self._seen.clear()
        for k, v in list(self.stats.items()):
            if isinstance(v, int):
                self.stats[k] = 0

    @staticmethod
    def _service_s(q) -> float:
        return float(C.recall_ttft_s(max(int(q.readiness_tokens), 1), q.readiness))

    def _evidence_is_sufficient(self, q, now_s: float) -> bool:
        """Has the evidence stopped improving materially, or is the session already warm?

        The paper's signal is a query-token relevance score over the frame stream, which our
        observation does not expose. ADAPTATION, declared on the card.

        A FIRST VERSION OF THIS PROXY WAS INERT AND IS RECORDED HERE RATHER THAN QUIETLY REPLACED.
        It compared `max(e.tokens for e in q.evidence)` against `readiness_tokens`. That can never
        fire: `cstate` always offers a D2 evidence item whose size IS the whole believed history,
        so the ratio is always 1.0 and every query reads as sufficient. The arm produced zero
        DEFER decisions and was byte-identical to b7 on decision kinds. The inventory describes
        what COULD be sent, not what has arrived.

        This version uses the quantity that actually moves as the stream runs: the session's
        believed history, `readiness_tokens`. Proactive response waits while the evidence is still
        growing and answers once it has settled - or once the deadline forces it. A warm session is
        sufficient by definition, its history being in hand.
        """
        if str(q.readiness).upper() in ("GPU-WARM", "HOST-WARM"):
            return True
        tok = max(int(q.readiness_tokens), 1)
        prev = self._seen.get(q.session_id)
        self._seen[q.session_id] = tok
        if prev is None:
            return False                       # first sight: let one more quantum of stream land
        growth = (tok - prev) / max(prev, 1)
        return growth < self.settle_frac

    def decide(self, obs: Observation) -> Action:
        rec: List[RecallAction] = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            slack = max(q.slack_s(obs.now_s), 0.0)
            svc = self._service_s(q)
            if self._evidence_is_sufficient(q, obs.now_s):
                rec.append(RecallAction(q.query_id, "CLOUD"))
                self.stats["answered_now"] += 1
                continue
            # Would waiting one more quantum still leave room to answer inside the deadline?
            if svc + self.defer_q <= slack:
                rec.append(RecallAction(q.query_id, "DEFER", defer_s=self.defer_q))
                self.stats["deferred_for_evidence"] += 1
            else:
                # Deadline pressure overrides the wait: answer with what is in hand.
                rec.append(RecallAction(q.query_id, "CLOUD"))
                self.stats["answered_on_deadline_pressure"] += 1
                if svc > slack:
                    self.stats["no_wait_possible"] += 1
        streams = [StreamAction(s.stream_id, DEFAULTS["episodic_mode"])
                   for s in obs.streams if s.network.connected]
        return Action(streams=streams, recall=rec, sessions=[],
                      notes=dict(rule="QueryStream proactive response: answer when the evidence "
                                      "suffices, otherwise wait, but never past the deadline",
                                 qdp_ported=False,
                                 qdp_reason="channel live since Part A, signal absent: no "
                                            "token- or frame-level relevance in RecallQuery"))
