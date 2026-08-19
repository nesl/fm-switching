"""Reactive policy: no pre-provisioning. Serves cold on demand."""

from .base import BasePolicy


class ReactivePolicy(BasePolicy):
    @property
    def name(self) -> str:
        return "reactive"

    def reset(self):
        pass

    def decide(self, sessions, prov_state, reachable_nodes, epoch,
               cost_model, nodes, next_serving_nodes, future_regimes):
        return []
