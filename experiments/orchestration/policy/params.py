"""Spec 9: every parameter, its default and WHERE THE DEFAULT COMES FROM.

A default here is one of three things, and `PROVENANCE` says which for every field:
  COMMITTED      a measured value from a committed study, cited;
  DEV-FITTED     fitted on DEV by a committed study, cited;
  PLACEHOLDER    no committed value exists; the field must be swept or supplied, and the policy
                 refuses to treat it as evidence (`Params.placeholders()` lists them).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional, Tuple

# D56: both warm-tier sizes are INPUTS. These are the values StudyENG1 and StudyENG1b ran at on
# h100nvl, kept as named constants so a reproduction can pass them explicitly. They are NOT
# defaults: `Params` leaves both capacities at 0, which refuses rather than guessing.
H100NVL_KV_POOL_TOKENS = 62_944          # StudyENG1 section 1.2 and StudyENG1b section 3
HOST_OFFLOAD_GIB_ENG1B = 256             # StudyENG1b: --kv-offloading-size 256, native backend


@dataclass
class Params:
    H: float = 0.75
    H_s: float = 10.0
    T_k: Dict[str, float] = field(default_factory=lambda: {"SH": 0.5})
    E_k: Dict[str, int] = field(default_factory=lambda: {"SH": 10})
    W_k: Dict[str, int] = field(default_factory=lambda: {"SH": 3})
    L_k: Dict[str, float] = field(default_factory=lambda: {"SH": 1.5, "SS": 2.0, "RC": 10.0})
    q_k: Dict[str, float] = field(default_factory=lambda: {"SH": 0.0, "SS": 0.0, "RC": 0.0})
    p_k: Dict[str, float] = field(default_factory=lambda: {"SH": 0.9, "SS": 0.9, "RC": 0.9})
    omega: Dict[str, float] = field(default_factory=lambda: {"SH": 1.0, "RC": 0.42463109124188936,
                                                             "SS": None})
    feasibility_threshold: float = 0.5
    mu: float = 0.0
    mu_ewma_alpha: float = 0.1
    belief_conservatism: float = 0.5
    piece_sizes_tokens: Tuple[int, ...] = (1024, 2048)
    allow_whole_job_piece: bool = True
    theta_k: Dict[str, float] = field(default_factory=lambda: {"SH": 2.0})
    beta: float = 0.0
    W_c: float = 3.0
    delta: float = 1.5
    n_c: int = 3
    K_c: int = 2
    K_e: int = 2
    instability_mode: str = "var"
    H_up: float = 5.0
    theta_up: float = 0.5
    N_sum: int = 0
    gpu_kv_capacity_tokens: int = 0
    host_kv_capacity_tokens: int = 0
    question_first_history_bytes: int = 1_000_000
    kv_pool_model: bool = True
    p_host: Optional[float] = None
    host_eviction_rule: str = "lru"
    tier_calibration: Optional[Any] = None
    mu_estimator: str = "none"
    survival_curve: Optional[Any] = None
    prefix_loss_replan_threshold: float = 0.5
    decision_latency_s: Optional[float] = None
    continuation_resolution_s: float = 0.25
    episode_cadence_grid_s: float = 0.25

    def p_host_for(self, host_pool: Any = None, evicted_tokens: int = 0,
                   prefix_id: Optional[str] = None, t: float = 0.0) -> Dict[str, Any]:
        """D56: P_host is a FUNCTION OF HOST OCCUPANCY, not a constant.

        `p_host` is now an OPTIONAL OVERRIDE. None, the default, means 'derive it', and the
        derivation is `tiers.p_host_from_occupancy`: StudyENG1b's measured 0.999 when the host
        tier has room for the evicted blocks, and the fraction the host eviction rule keeps when
        it does not. A float pins it, which is what a sweep or a reproduction of the POL2
        behaviour (0.0, the conservative extreme) does."""
        from .tiers import p_host_from_occupancy
        if self.p_host is not None:
            return dict(p_host=float(self.p_host), basis="pinned by Params.p_host",
                        measured=False, host_occupancy_fraction=None,
                        source="supplied by the caller or the sweep")
        return p_host_from_occupancy(host_pool, evicted_tokens, prefix_id=prefix_id, t=t)

    def host_eviction_callable(self) -> Any:
        from . import tiers
        rules = {"lru": tiers.lru_rule, "largest_first": tiers.largest_first_rule}
        if self.host_eviction_rule not in rules:
            raise ValueError("unknown host eviction rule %r; known: %s"
                             % (self.host_eviction_rule, sorted(rules)))
        return rules[self.host_eviction_rule]

    def placeholders(self) -> List[str]:
        return [k for k, v in PROVENANCE.items() if v["kind"] == "PLACEHOLDER"
                and k in asdict(self)]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


PROVENANCE: Dict[str, Dict[str, str]] = {
    "H": dict(kind="PLACEHOLDER", note="spec 9 says 0.5-1 s and SWEPT; 0.75 s is the midpoint "
                                       "and carries no evidence of its own"),
    "H_s": dict(kind="PLACEHOLDER", note="spec 9 says seconds and swept; 10 s chosen as the "
                                         "order of the committed recall inter-arrival p50 "
                                         "(68.0 s) divided by a small factor, and must be swept"),
    "T_k": dict(kind="DEV-FITTED", note="SH cadence 0.5 s; StudyCTRL1-episodes and "
                                        "StudyCTRL1b-crossfit ran the controller at this cadence"),
    "E_k": dict(kind="DEV-FITTED", note="10 calls per episode, StudyCTRL1-episodes"),
    "W_k": dict(kind="PLACEHOLDER", note="merge window in frames; merging is OFF and its "
                                         "enabling condition is not met, so this is unused"),
    "L_k": dict(kind="PLACEHOLDER", note="application parameters, spec 9 says swept; the SH "
                                         "value is the longest challenge horizon and the RC "
                                         "value is SLICE1 Part B's reporting deadline, neither "
                                         "is an application requirement"),
    "q_k": dict(kind="PLACEHOLDER", note="quality floors are application parameters; 0.0 means "
                                         "unconstrained and must be swept"),
    "p_k": dict(kind="PLACEHOLDER", note="attainment targets are application parameters"),
    "omega": dict(kind="DEV-FITTED", note="StudyPROF1-dev class_weights_omega, omega_SH = 1 and "
                                          "omega_RC = 0.4246, marked a PROPOSAL awaiting user "
                                          "approval; omega_SS is None because no committed SS "
                                          "accuracy pair exists, and the policy raises if an SS "
                                          "opportunity is scored while it is None"),
    "feasibility_threshold": dict(kind="PLACEHOLDER", note="spec 7.3 and 9 say DEV and swept; no "
                                                           "committed DEV value exists"),
    "mu": dict(kind="PLACEHOLDER", note="GPU backlog price in utility per GPU-second; spec 3.5 "
                                        "and 8 use it but give no update rule, see "
                                        "spec_map.AMBIGUITIES A3"),
    "mu_ewma_alpha": dict(kind="PLACEHOLDER", note="smoothing of the mu update, our choice"),
    "belief_conservatism": dict(kind="PLACEHOLDER", note="spec 9 says fixed and reported; 0.5 "
                                                         "puts half the ambiguous mass on the "
                                                         "colder tier"),
    "piece_sizes_tokens": dict(kind="COMMITTED", note="SLICE1 Parts A-D measured 1,024 and "
                                                      "2,048-token prefix-chained pieces"),
    "allow_whole_job_piece": dict(kind="COMMITTED", note="spec 7.4 says measured sizes plus "
                                                         "whole-job"),
    "theta_k": dict(kind="DEV-FITTED", note="the controller threshold is solved per budget by "
                                            "StudyCTRL1b-crossfit on training folds; 2.0 is a "
                                            "neutral starting value only"),
    "beta": dict(kind="PLACEHOLDER", note="escalation price coefficient; the price flag is OFF "
                                          "and beta has no committed DEV calibration, so it is "
                                          "held at 0"),
    "W_c": dict(kind="DEV-FITTED", note="StudyCTRL1-episodes grid, seconds of device samples"),
    "delta": dict(kind="DEV-FITTED", note="StudyCTRL1-episodes grid, rise lag in seconds"),
    "n_c": dict(kind="DEV-FITTED", note="StudyCTRL1-episodes grid, instability window"),
    "K_c": dict(kind="DEV-FITTED", note="StudyCTRL1-episodes grid, below-threshold samples that "
                                        "close an episode"),
    "K_e": dict(kind="PLACEHOLDER", note="cloud-side episode end after K_e negative DeltaJ "
                                         "calls; spec 7.7 names it and gives no value"),
    "instability_mode": dict(kind="DEV-FITTED", note="StudyCTRL1-episodes A2: var or flips, "
                                                     "chosen on DEV"),
    "H_up": dict(kind="PLACEHOLDER", note="upload trigger horizon; predictive upload is OFF"),
    "theta_up": dict(kind="PLACEHOLDER", note="upload trigger threshold; predictive upload is OFF"),
    "N_sum": dict(kind="PLACEHOLDER", note="summary refresh trigger; summaries are OFF"),
    "gpu_kv_capacity_tokens": dict(
        kind="PLACEHOLDER",
        note="D56: an INPUT, not the H100's value. 0 means 'not supplied' and the tier "
             "assignment refuses to run until a capacity is given, because a wrong capacity "
             "silently changes every allocation. The value StudyENG1 and StudyENG1b ran at is "
             "H100NVL_KV_POOL_TOKENS = 62,944 and is available as a named constant for a "
             "reproduction, never as a default"),
    "host_kv_capacity_tokens": dict(
        kind="PLACEHOLDER",
        note="D56: an INPUT and BOUNDED. 0 means 'not supplied'. The host tier is always "
             "available per spec 1.1 (D29), but its SIZE is a deployment fact and the bound is "
             "what makes P_host a function of occupancy rather than a constant. StudyENG1b ran "
             "with 256 GiB of offload, which is HOST_OFFLOAD_GIB_ENG1B"),
    "kv_pool_model": dict(
        kind="COMMITTED",
        note="addendum A6 makes the KV-pool model part of the core, so it is ON. The switch "
             "exists because A6's own acceptance test requires showing that with ZERO pressure "
             "the A6 terms vanish and the results equal the pre-A6 path"),
    "p_host": dict(
        kind="COMMITTED",
        note="A6.1's P_host, the probability that evicted blocks are recoverable from the host "
             "tier. NO LONGER A CONSTANT (D56, 2026-11-16): the default is None, meaning DERIVE "
             "IT FROM HOST OCCUPANCY through Params.p_host_for and tiers.p_host_from_occupancy. "
             "StudyENG1b measured the with-room value: 853,936 of 854,898 evicted prefix tokens "
             "returned as external host hits on the KV-HOST server, P_host = 0.999, because the "
             "offloading connector writes every built block through to host as it is computed. "
             "With no host tier configured it is 0.0, which is StudyENG1b's E0 server by "
             "construction. With a FULL host tier the host eviction rule decides what survives, "
             "and that part carries the rule's ASSUMPTION label. A float pins the value, which "
             "is how a sweep, or the old conservative 0.0, is expressed"),
    "host_eviction_rule": dict(
        kind="PLACEHOLDER",
        note="ASSUMPTION, labelled as such in tiers.EVICTION_RULE_ASSUMPTION and in the report. "
             "The default is LRU. StudyENG1 Part D found vLLM 0.31.0 exposes eviction only as "
             "sampled lifetime and idle histograms and no counter for cached-but-unreferenced "
             "blocks, so the host tier's eviction order was never observed. StudyENG1c is the "
             "measurement that replaces it; the rule is a pluggable callable"),
    "tier_calibration": dict(
        kind="PLACEHOLDER",
        note="D57's per-tier monotone map from a raw score to a probability, LOADED FROM A FILE "
             "and fitted on DEV by StudyCTRL1c, which has not delivered it. None means NOT "
             "SUPPLIED, and calibration.require_calibrated then RAISES on any comparison, "
             "ranking, upgrade or gain estimate that mixes tiers, rather than silently "
             "comparing two different scales. StudyCTRL1b measured that the two tiers' raw "
             "scores are on different scales (ambiguity A12), which is why the failure is loud"),
    "mu_estimator": dict(
        kind="PLACEHOLDER",
        note="WHICH estimator updates mu, chosen EXPLICITLY rather than by default. 'none' is "
             "the default and holds mu at its PLACEHOLDER 0, so the backlog channel is silent "
             "and says so. 'ewma_marginal_utility' is the rule POL2 ambiguity A3 describes, an "
             "EWMA of the realized marginal utility per GPU-second of the last released item "
             "floored at zero. Spec 8 says only 'update mu' and spec 9 does not list mu at all, "
             "so the spec does NOT determine the estimator; reports/study_pol3_update.md writes "
             "out the options and their consequences instead of choosing one silently"),
    "survival_curve": dict(
        kind="PLACEHOLDER",
        note="A6.2's beyond-horizon extension of P_loss, assigned to M5. None means NO CURVE "
             "EXISTS; the beyond-horizon part of a gap then contributes nothing and every "
             "result that depended on it carries beyond_horizon_unmeasured"),
    "prefix_loss_replan_threshold": dict(
        kind="PLACEHOLDER",
        note="A6.4 says to re-plan on loss that is observed OR believed likely; 'likely' needs a "
             "number and the spec gives none, so 0.5 is used and swept"),
    "question_first_history_bytes": dict(
        kind="PLACEHOLDER",
        note="the unsent-history size above which an RC query MAY take the question-first path "
             "(addendum A2 as revised). No committed study sets it; 1 MB is about three "
             "StudyD4 frames at the committed 354,902 B and must be swept"),
    "decision_latency_s": dict(
        kind="COMMITTED",
        note="the coordinator's own decision latency, charged ONLY on the question-first path "
             "and irrelevant on the complete path. Measured by this row's own M4 and read back "
             "from results/orchestration/pol2/pol2_m4_decision_time.json. "
             "Resolved from this row's M4 measurement when the file is present; None means "
             "UNMEASURED and the question-first path then refuses to quote a delivered delay "
             "rather than quoting one that omits it"),
    "continuation_resolution_s": dict(kind="PLACEHOLDER", note="spec 9 says set by M4; 0.25 s is "
                                                               "the committed decision grid"),
    "episode_cadence_grid_s": dict(kind="COMMITTED", note="StudyD14b 0.25-s decision grid"),
}
