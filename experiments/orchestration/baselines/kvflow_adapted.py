#!/usr/bin/env python3
"""KVFlow (arXiv:2507.07400), ADAPTED behind our policy interface. Case D. P1.

Decision logic = `reconstructed/kvflow.py`, unchanged. Mapping in cards/kvflow.md.

**THE PAPER'S SIGNAL IS NOT CAUSALLY AVAILABLE, and the addendum says so: "adapt its
reuse-priority principle to client sessions using only causal signals (no future workflow
knowledge)".** KVFlow reads steps-to-execution from a KNOWN agentic workflow graph. We have no
graph: when a client session next asks is precisely what a scheduler may not know. So the
adapted policy ESTIMATES steps-to-execution from each session's OWN observed inter-arrival
history - an exponentially-weighted mean gap, turned into "expected seconds until the next
arrival" - and feeds that estimate into the paper's eviction and prefetch rules unchanged.

This is a principle adaptation, NOT a reproduction: KVFlow's advantage over LRU comes from exact
future knowledge, and the causal estimate is strictly weaker.

CPU only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent / "reconstructed"))

import costs as C
from interface import (Action, Observation, Policy, RecallAction, SessionAction,
                       StreamAction, materialize)
from kvflow import KVNode, evict, prefetch  # noqa: E402


class KVFlowAdapted(Policy):
    name = "kvflow"
    case = "D"
    experiments = ("B-recall",)
    paper = "Pan et al., KVFlow: Efficient Prefix Caching for Accelerating LLM-Based Multi-Agent Workflows, arXiv:2507.07400"
    decides = ("session_action", "recall_decision")
    defaults_used = ("episodic_mode", "cadence_s", "frame_count", "representation", "order")

    def __init__(self, gpu_capacity_tokens: int = 60000, prefetch_horizon_s: float = 5.0,
                 alpha: float = 0.3) -> None:
        self.cap = int(gpu_capacity_tokens)
        self.horizon_s = float(prefetch_horizon_s)
        self.alpha = float(alpha)
        self._last: Dict[str, float] = {}
        self._gap: Dict[str, float] = {}

    def reset(self, seed: int = 0) -> None:
        self._last.clear()
        self._gap.clear()

    def _observe(self, obs: Observation) -> None:
        for q in obs.recall:
            t0 = self._last.get(q.session_id)
            if t0 is not None:
                g = obs.now_s - t0
                self._gap[q.session_id] = (self.alpha * g
                                           + (1 - self.alpha) * self._gap.get(q.session_id, g))
            self._last[q.session_id] = obs.now_s

    def _steps_to_execution(self, sid: str, now_s: float) -> float:
        """The causal estimate standing in for the paper's workflow lookup: expected seconds
        until this session's next arrival, from its own observed inter-arrival history."""
        g = self._gap.get(sid)
        if g is None:
            return float("inf")              # never seen twice: assume far from reuse
        last = self._last.get(sid, now_s)
        return max(g - (now_s - last), 0.0)

    def decide(self, obs: Observation) -> Action:
        self._observe(obs)
        tokens: Dict[str, int] = {}
        for q in obs.recall:
            tokens[q.session_id] = max(tokens.get(q.session_id, 0), q.readiness_tokens)
        for sid in list(obs.cloud.gpu_warm_sessions) + list(obs.cloud.host_warm_sessions):
            tokens.setdefault(sid, 11000)
        nodes = [KVNode(sid, tok, sid in obs.cloud.gpu_warm_sessions,
                        self._steps_to_execution(sid, obs.now_s))
                 for sid, tok in sorted(tokens.items())]
        after = evict(nodes, self.cap)
        pull = set(prefetch(after, self.horizon_s, slots=2))
        sess = []
        for n in after:
            keep = n.resident or n.node_id in pull
            if keep and not n.resident:
                # the paper's PREFETCH: this session's state does not exist on the GPU yet and
                # KVFlow pulls it in ahead of the predicted arrival. Amendment 2026-11-12: that
                # is MATERIALIZE, monolithic, because KVFlow prefetches a whole prefix.
                sess.append(materialize(n.node_id, tokens.get(n.node_id, 11000),
                                        slice_tokens=None))
            else:
                sess.append(SessionAction(n.node_id,
                                          "KEEP_GPU_WARM" if keep else "OFFLOAD_TO_HOST"))
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            sessions=sess)
