"""The v3 scheduling policy (research/POLICY_SPEC_v3.md) as a library.

StudyPOL2-build. CPU only: this package computes decisions, it does not run a model, a server or
an engine. Every conditional mechanism of spec 7.0 is behind a flag that DEFAULTS OFF, the engine
model is pluggable so M1's measurement can replace the placeholder without touching the policy,
and every parameter default carries its provenance in `params.PROVENANCE`.

Read `spec_map.SPEC_MAP` for the section-to-code table and `spec_map.AMBIGUITIES` for every place
the spec left a choice, with the choice taken and why.
"""
from .flags import Flags
from .params import Params, PROVENANCE
from .profiles import Profiles, load_profiles
from .engine import EngineModel, PlaceholderEngine, Request
from .state import (Device, Link, HistoryBelief, Episode, Job, PendingItem, Fleet, Opportunity,
                    TIERS, colder)
from .utility import u_sh_cloud, u_sh_device, u_ss, u_rc, gain
from .demand import Demand
from .telemetry import ResidencyBelief, TelemetrySnapshot
from .continuation import classify, continuation_value, FEASIBLE, PRIORITY, INFEASIBLE
from .readiness import state_value, tier_assignment, state_actions
from .kvpool import KVPool, PrefixEntry, eng1b_long_gap_curve, survival_p_loss, prefix_id_for
from .tiers import (HostPool, TieredStore, lru_rule, largest_first_rule,
                    p_host_from_occupancy, P_HOST_WITH_ROOM, EVICTION_RULE_ASSUMPTION)
from .calibration import (TierCalibration, MonotoneMap, CalibrationMissing, CalibrationInvalid,
                          require_calibrated, rank_across_tiers, upgrade_decision,
                          identity_for_tests)
from .controller import DeviceController, ControllerState
from .rollout import Rollout, RolloutResult, delta_j
from .coordinator import Coordinator, Decision

__all__ = [
    "Flags", "Params", "PROVENANCE", "Profiles", "load_profiles", "EngineModel",
    "PlaceholderEngine", "Request", "Device", "Link", "HistoryBelief", "Episode", "Job",
    "PendingItem", "Fleet", "Opportunity", "TIERS", "colder", "u_sh_cloud", "u_sh_device",
    "u_ss", "u_rc", "gain", "Demand", "ResidencyBelief", "TelemetrySnapshot", "classify",
    "continuation_value", "FEASIBLE", "PRIORITY", "INFEASIBLE", "state_value",
    "tier_assignment", "state_actions", "DeviceController", "ControllerState", "Rollout",
    "RolloutResult", "delta_j", "Coordinator", "Decision",
    "KVPool", "PrefixEntry", "eng1b_long_gap_curve", "survival_p_loss", "prefix_id_for",
    "HostPool", "TieredStore", "lru_rule", "largest_first_rule", "p_host_from_occupancy",
    "P_HOST_WITH_ROOM", "EVICTION_RULE_ASSUMPTION", "TierCalibration", "MonotoneMap",
    "CalibrationMissing", "CalibrationInvalid", "require_calibrated", "rank_across_tiers",
    "upgrade_decision", "identity_for_tests",
]
