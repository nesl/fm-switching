"""
ReactiveThresholdPolicy — the reactive baseline / "never worse than reactive"
comparison point.

Purely reactive: no forecasting, no pre-warming, no overlap. Each cycle it
monitors the *current* state and triggers a migration only after a monitored
metric crosses a threshold (memory pressure → cloud; disconnect → edge; heavy
context on edge → strip to stateless). Because it emits the standard
MIGRATE_TO_CLOUD / MIGRATE_TO_EDGE actions, the switch pays the FULL inertia
cost at switch time via the orchestrator's standard migration path
(cost_model.migration_cost_s) — there is no overlap or pre-fill to hide it.
This is exactly the behavior of policies.ReactiveThreshold, which the call
sites fall back to when this module is absent
(see multi_seed_validation.py:246), so we subclass it to guarantee identical
semantics and reuse its decision logic and thresholds rather than reinventing
them.

The thresholds are exposed as constructor parameters (defaulting to the base
class values) so the baseline's trigger point can be swept without editing the
shared policies.py.
"""

from policies import ReactiveThreshold


class ReactiveThresholdPolicy(ReactiveThreshold):
    name = "ReactiveThreshold"

    def __init__(self, mem_thresh=None, ctx_thresh=None, hysteresis_s=None):
        # Default to the base-class constants; override only if provided.
        if mem_thresh is not None:
            self.MEM_THRESH = mem_thresh
        if ctx_thresh is not None:
            self.CTX_THRESH = ctx_thresh
        if hysteresis_s is not None:
            self.HYSTERESIS_S = hysteresis_s

    def reset(self):
        # Stateless across episodes (all reactive state lives in SimState,
        # tracked by the orchestrator). Defined so run_episode's reset() hook
        # is a clean no-op.
        pass

    # decide(state) is inherited verbatim from policies.ReactiveThreshold.
