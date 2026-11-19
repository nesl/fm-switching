"""Spec 7.0: core versus conditional mechanisms. Every conditional flag DEFAULTS OFF (D38)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Any, Dict


# Spec 7.0's CONDITIONAL MECHANISMS, which D66 requires to be off for a round-1 core run. A
# D122 v1.1 DEFECT FIX is not a conditional mechanism, so it is deliberately not in this tuple:
# `any_on` still reports every flag, and `conditional_any_on` is what the D66 guard asks.
SPEC_7_0_CONDITIONAL = ("escalation_price", "phase_assignment", "merging", "summaries",
                        "predictive_upload", "conditional_recall_rate", "sampled_scenarios",
                        "closed_form_fallback")


@dataclass(frozen=True)
class Flags:
    escalation_price: bool = False
    phase_assignment: bool = False
    merging: bool = False
    summaries: bool = False
    predictive_upload: bool = False
    conditional_recall_rate: bool = False
    sampled_scenarios: bool = False
    closed_form_fallback: bool = False
    # D122 v1.1 fix A3. Spec 7.3 promotes a job that would become infeasible within the next
    # interval to the PRIORITY class, and `coordinator._update_jobs` does set
    # `job.feasibility = PRIORITY`. But the rollout valued every job with `priority=False` hard
    # coded, so the label could not change the value it was assigned for. With this flag the
    # job's OWN class is passed through. DEFAULT OFF (D38).
    honour_job_priority: bool = False
    # D122 v1.1. The D98-equivalent tail for RECALL: an rc_piece that cannot start inside the
    # horizon is simulated through to the answer's predicted delivery, so a rebuild's payoff is
    # not worth zero merely because it lands after t0 + H, and the question is credited at its
    # OWN deadline exactly as D98 credits an SH instant. DEFAULT OFF.
    rc_tail: bool = False
    # D122 v1.1. `HistoryBelief.staleness_s` is read in production and was written nowhere, so it
    # sat at 0.0 while feeding `utility.t_ready_s`, where it becomes catch-up frames. This writes
    # it from coordinator state. DEFAULT OFF.
    write_staleness: bool = False
    # D122 v1.1 F3. `continuation_schedule` places a job's pieces at
    # `cursor = t + (0.0 if priority else competing_s)`, and its own docstring calls competing_s
    # "the engine-seconds of other work pi_0 would serve before this job's pieces", yet every
    # production caller passed 0.0, so the schedule assumed the job had the engine to itself.
    # That one zero pinned p_finish at 1, made PRIORITY unreachable from `classify` and left A3
    # inert. This derives it from the rollout's own state. DEFAULT OFF.
    realistic_competing: bool = False
    # D122 v1.1, user item 1: the two causes inside `rc_tail`, independently toggleable so the
    # SH side effect can be attributed. (a) the shared tail cursor, which simulates an rc_piece
    # beyond H and lets `_rc_utility` see its progress; (b) the RC rows `_rc_opportunities`
    # appends, which enter `_z_term`'s sum for EVERY candidate. `rc_tail` stays the master, so
    # `rc_tail` alone turns both on and is byte-identical to the build before this split.
    rc_tail_cursor: bool = False
    rc_tail_zrows: bool = False
    # D122 v1.1 F4 (spec Phat): p_finish stops being a 0/1 indicator and becomes
    # P(predicted finish <= D_r) under the cost model's MEASURED completion-time error,
    # calibrated from committed FIT-only residuals. DEFAULT OFF.
    prob_p_finish: bool = False

    def tail_cursor_on(self) -> bool:
        return bool(self.rc_tail or self.rc_tail_cursor)

    def tail_zrows_on(self) -> bool:
        return bool(self.rc_tail or self.rc_tail_zrows)

    ENABLING_CONDITION: Dict[str, str] = None

    def with_(self, **kw: bool) -> "Flags":
        return replace(self, **kw)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("ENABLING_CONDITION", None)
        return d

    def any_on(self) -> bool:
        return any(self.as_dict().values())

    def conditional_any_on(self) -> bool:
        """D66's check: spec 7.0's conditional mechanisms only, not the v1.1 defect fixes."""
        return any(bool(getattr(self, n)) for n in SPEC_7_0_CONDITIONAL)


CONDITIONAL = {
    "escalation_price": dict(
        spec="7.7",
        enabling_condition="beta calibrated on DEV so a higher price suppresses the "
                           "lowest-benefit escalations first; evaluated separately from admission",
        status="NOT MET: no committed DEV calibration of beta exists"),
    "phase_assignment": dict(
        spec="7.8",
        enabling_condition="predicted clustering gain exceeds the capture-time shift cost",
        status="NOT MET: requires M1's step model to predict clustering gain"),
    "merging": dict(
        spec="7.9",
        enabling_condition="M3 shows merged-call utility exceeds the device's at the delays "
                           "involved",
        status="NOT MET AND WEAKENED: StudyFRAMES1 and StudyCTRL1b found no measurable m = 3 "
               "benefit on held-out clips and a negative point estimate once m = 3 pays its own "
               "upload; the DEV-positive m = 3 entries in profiles_dev.json are marked "
               "DEV-OPTIMISTIC and must not be used to enable this"),
    "summaries": dict(
        spec="7.10",
        enabling_condition="DEV quality competitive for some question types and refresh cost "
                           "measured",
        status="NOT MET: StudyF2 inconclusive; no committed SUMMARY recall table"),
    "predictive_upload": dict(
        spec="7.11",
        enabling_condition="improves time-to-ready over on-demand upload under measured links",
        status="NOT MET: no measured bandwidth series exists (StudyPROF1-dev link_model marks "
               "bandwidth an ASSUMPTION), so the comparison cannot be made"),
    "conditional_recall_rate": dict(
        spec="6.4",
        enabling_condition="DEV data shows recall questions concentrate around episodes",
        status="NOT COMPUTABLE: StudyPROF1-dev found no committed trace carrying escalations and "
               "recall questions on one stream, so the conservative default applies and the rate "
               "is not used"),
    "sampled_scenarios": dict(
        spec="5.1",
        enabling_condition="T0 and M4 show sampling is affordable and more faithful than the "
                           "expected-value rollout",
        status="NOT MET: T0 has not been run"),
    "closed_form_fallback": dict(
        spec="5.5",
        enabling_condition="the fallback itself passes T0",
        status="NOT MET: T0 has not been run"),
}

Flags.ENABLING_CONDITION = CONDITIONAL
