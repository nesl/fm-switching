"""
Topology: node definitions and mobility model.

MobilityModel wraps markov_network.py from the legacy simulator (simulator/)
for per-epoch connectivity traces. Each epoch = 30 seconds.

prefill_slowdown assumptions (vs A6000 reference):
  cloud (A6000):    1.0  — measured reference
  edge (RTX3090Ti): 1.5  — estimated from phase-1 RTX3090Ti cold-prefill ratio
                           (e.g. L=8k: 2028ms vs 1369ms ≈ 1.48x, rounded 1.5)
  device (Jetson):  6.0  — estimated; E23 pending; Jetson SDPA prefill ~6x slower
                           at comparable L from inertia_profile measurements
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# Access legacy markov_network from simulator/
_SIM_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SIM_DIR))
from markov_network import sample_trace  # noqa: E402


@dataclass
class Node:
    node_id: str
    capacity_gb: float      # GPU memory usable for KV after model residency
    prefill_slowdown: float = 1.0   # multiplier vs a6000 reference


DEFAULT_NODES: Dict[str, Node] = {
    "device": Node("device", capacity_gb=4.0,  prefill_slowdown=6.0),
    "edge":   Node("edge",   capacity_gb=9.0,  prefill_slowdown=1.5),
    "cloud":  Node("cloud",  capacity_gb=34.0, prefill_slowdown=1.0),
}

# Map mobility_level → markov_network profile
_MOBILITY_PROFILE = {
    "static":      "campus",   # low handoff entropy, high P(good)
    "predictable": "urban",
    "moderate":    "indoor",
    "high":        "harsh",
}

EPOCH_SECONDS = 30


class MobilityModel:
    """
    Per-epoch connectivity model for one edge node.
    Device is always reachable. Cloud is always reachable. Edge uses Markov trace.
    Candidate nodes at epoch t = {device, cloud} ∪ {edge if edge_connected[t]}.
    """

    def __init__(self, mobility_level: str, n_epochs: int, seed: int = 0,
                 nodes: Dict[str, Node] = None):
        if mobility_level not in _MOBILITY_PROFILE:
            raise ValueError(f"Unknown mobility level: {mobility_level}. "
                             f"Choose from {list(_MOBILITY_PROFILE)}")
        self.mobility_level = mobility_level
        self.n_epochs = n_epochs
        self.nodes = nodes or DEFAULT_NODES
        profile = _MOBILITY_PROFILE[mobility_level]
        # Generate trace at 1 sample/second; we advance EPOCH_SECONDS per epoch
        n_seconds = n_epochs * EPOCH_SECONDS + EPOCH_SECONDS
        raw = sample_trace(profile, n_seconds=n_seconds, seed=seed)
        # Subsample: one sample per epoch (take every EPOCH_SECONDS-th second)
        self._edge_connected: List[bool] = []
        for ep in range(n_epochs + 1):
            t = ep * EPOCH_SECONDS
            t = min(t, len(raw) - 1)
            self._edge_connected.append(bool(raw[t]["connected"]))

    def reachable_nodes(self, epoch: int) -> List[str]:
        """Return list of node_ids reachable at this epoch."""
        reachable = ["device", "cloud"]
        if "edge" in self.nodes and self._edge_connected[epoch]:
            reachable.append("edge")
        return [n for n in reachable if n in self.nodes]

    def next_reachable_nodes(self, epoch: int) -> List[str]:
        """Peek one epoch ahead (oracle parity: given to all policies)."""
        return self.reachable_nodes(min(epoch + 1, self.n_epochs))

    def edge_connected(self, epoch: int) -> bool:
        return self._edge_connected[min(epoch, len(self._edge_connected) - 1)]
