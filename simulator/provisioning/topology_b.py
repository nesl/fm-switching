"""
E24b topology: 3 edge nodes (rtx3090ti-class) + 1 cloud (a6000-class).

Each edge runs an independent Markov connectivity trace.
Serving node = lowest-index connected edge, else cloud.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_SIM_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SIM_DIR))
from markov_network import sample_trace  # noqa: E402

EPOCH_SECONDS = 30

# rtx3090ti full-KV is infeasible at L >= 49152 (OOM confirmed E22)
# Maximum feasible L for full KV on edge nodes:
EDGE_MAX_L_FULL = 32768

_MOBILITY_PROFILE = {
    "static":      "campus",
    "predictable": "urban",
    "moderate":    "indoor",
    "high":        "harsh",
}


@dataclass
class NodeB:
    node_id: str
    capacity_gb: float
    prefill_slowdown: float = 1.0
    tier: str = "cloud"                    # "edge" or "cloud"
    max_L_feasible_full: Optional[int] = None   # None = no OOM limit


def make_nodes_b(edge_cap_gb: float, cloud_cap_gb: float) -> Dict[str, NodeB]:
    nodes: Dict[str, NodeB] = {}
    for i in range(3):
        nodes[f"edge{i}"] = NodeB(
            node_id=f"edge{i}",
            capacity_gb=edge_cap_gb,
            prefill_slowdown=1.5,
            tier="edge",
            max_L_feasible_full=EDGE_MAX_L_FULL,
        )
    nodes["cloud"] = NodeB(
        node_id="cloud",
        capacity_gb=cloud_cap_gb,
        prefill_slowdown=1.0,
        tier="cloud",
        max_L_feasible_full=None,
    )
    return nodes


class MobilityModel3Edge:
    """
    3 independent Markov traces for edge0/1/2; cloud always reachable.
    Seeds: edge_i uses base_seed + i*1000 to ensure independence.
    """

    def __init__(self, mobility_level: str, n_epochs: int, seed: int = 0):
        if mobility_level not in _MOBILITY_PROFILE:
            raise ValueError(f"Unknown mobility level: {mobility_level}")
        self.mobility_level = mobility_level
        self.n_epochs = n_epochs
        profile = _MOBILITY_PROFILE[mobility_level]
        n_seconds = n_epochs * EPOCH_SECONDS + EPOCH_SECONDS + 1

        self._edge_connected: List[List[bool]] = []
        for i in range(3):
            raw = sample_trace(profile, n_seconds=n_seconds, seed=seed + i * 1000)
            trace = []
            for ep in range(n_epochs + 1):
                t = min(ep * EPOCH_SECONDS, len(raw) - 1)
                trace.append(bool(raw[t]["connected"]))
            self._edge_connected.append(trace)

    def reachable_nodes(self, epoch: int) -> List[str]:
        ep = min(epoch, self.n_epochs)
        nodes = ["cloud"]
        for i in range(3):
            if self._edge_connected[i][ep]:
                nodes.append(f"edge{i}")
        return nodes

    def serving_node(self, epoch: int) -> str:
        """Lowest-index connected edge, else cloud."""
        ep = min(epoch, self.n_epochs)
        for i in range(3):
            if self._edge_connected[i][ep]:
                return f"edge{i}"
        return "cloud"

    def next_serving_node(self, epoch: int) -> str:
        return self.serving_node(min(epoch + 1, self.n_epochs))

    def reachable_next_2(self, epoch: int) -> List[str]:
        """Union of nodes reachable at epoch+1 and epoch+2."""
        reached = {"cloud"}
        for delta in (1, 2):
            ep = min(epoch + delta, self.n_epochs)
            for i in range(3):
                if self._edge_connected[i][ep]:
                    reached.add(f"edge{i}")
        return list(reached)
