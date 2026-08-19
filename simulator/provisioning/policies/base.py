"""Base policy interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ProvisioningDecision:
    session_id: int
    node_id: str
    fidelity: str
    action: str   # "materialize" | "refresh" | "store" | "evict" | "noop"


class BasePolicy:
    """All policies implement this interface."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    def reset(self):
        """Reset any internal state between simulation runs."""

    def decide(self, sessions: dict, prov_state, reachable_nodes: List[str],
               epoch: int, cost_model, nodes: dict,
               next_serving_nodes: dict, future_regimes: dict) -> List[ProvisioningDecision]:
        """
        Return a list of ProvisioningDecisions.

        Args:
            sessions: {session_id: SessionState}
            prov_state: ProvisioningState
            reachable_nodes: list of node_ids reachable this epoch
            epoch: current epoch index
            cost_model: CostModel instance
            nodes: {node_id: Node}
            next_serving_nodes: {session_id: node_id} — oracle-parity: actual next serving node
            future_regimes: {session_id: regime} — oracle-parity: same as current (regime fixed)
        """
        return []
