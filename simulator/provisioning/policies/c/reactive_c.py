"""ReactiveC: no provisioning. Engine handles cold materialization on demand."""
from __future__ import annotations


class ReactiveC:
    name = "reactive"
    is_joint = False
    is_oracle = False

    def reset(self): pass

    def decide_c(self, sessions, prov_state, reachable_nodes, epoch, vf, nodes,
                 serving_distribution, current_regimes, tau, infeasibility_map):
        return []
