"""Spec 7.0: core versus conditional mechanisms. Every conditional flag DEFAULTS OFF (D38)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Any, Dict


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

    ENABLING_CONDITION: Dict[str, str] = None

    def with_(self, **kw: bool) -> "Flags":
        return replace(self, **kw)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("ENABLING_CONDITION", None)
        return d

    def any_on(self) -> bool:
        return any(self.as_dict().values())


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
