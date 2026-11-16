"""Spec 6: state value for FUTURE questions, greedy tier assignment and the state actions.

Spec 5.3's one rule is enforced here by construction: `state_value` values FUTURE questions only
and takes an `exclude_job` argument so the question already carried by a continuation value is not
counted twice.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .state import TIERS, Device, colder


@dataclass
class StateAction:
    kind: str                     # PROMOTE_RELOAD | PROMOTE_REBUILD | DEMOTE | CATCH_UP |
    device: str                   # REFRESH_SUMMARY | REQUEST_UPLOAD
    rep: str
    target_tier: Optional[str]
    tokens: int
    conditional: bool = False
    spec: str = "6.2"


def _u_rc_from_tier(pf, qtype: str, rep: str, tier: str, size_tokens: int, staleness_s: float,
                    link, deadline_s: float, t_queue: float = 0.0) -> float:
    from .utility import t_ready_s, u_rc
    if tier == "DEVICE":
        return pf.rc_accuracy(qtype, "D2", "device")
    tr = t_ready_s(pf, rep, tier, size_tokens, staleness_s, 0, link)
    return u_rc(pf, qtype, rep, tr["total"], t_queue, link, deadline_s)[0]


def state_value(pf, device: Device, rep: str, demand, h_s: float, qtype: str, link,
                deadline_s: float, omega_rc: float, in_episode: bool = False,
                exclude_job: Optional[str] = None, credit_allowed: bool = True) -> Dict[str, Any]:
    """Spec 6.1, with addendum A6.3's single-counting rule made explicit.

    This value is for FUTURE ARRIVALS only: it is P(a question arrives within H_s) times the gain
    readiness buys THAT question. The question a job is already serving is valued by the job's
    continuation value (5.4) and never here, so the two can both be counted for the same prefix
    without double counting, which is exactly what A6.3 asks for. `exclude_job` records which
    in-progress job this prefix is already carrying, so the assertion can check it."""
    b = device.history[rep]
    p_need = demand.p_need_within(rep, h_s, in_episode)
    here = b.expected({t: _u_rc_from_tier(pf, qtype, rep, t, b.size_tokens, b.staleness_s, link,
                                          deadline_s) for t in TIERS})
    nxt = b.expected({t: _u_rc_from_tier(pf, qtype, rep, colder(t), b.size_tokens, b.staleness_s,
                                         link, deadline_s) for t in TIERS})
    dev = pf.rc_accuracy(qtype, "D2", "device")
    value = p_need * omega_rc * (here - max(nxt, dev))
    if not credit_allowed:
        value = 0.0
    return dict(value=float(value), p_need=float(p_need), u_here=float(here),
                u_next_colder=float(nxt), u_device=float(dev), rep=rep,
                excluded_job=exclude_job, credit_allowed=bool(credit_allowed),
                counts="future arrivals only (A6.3); the in-progress question is valued by the "
                       "job's continuation value",
                conditional_rate_used=bool(in_episode and demand.conditional_rate_enabled))


def assert_single_counting(continuation_rows: Sequence[Dict[str, Any]],
                           state_rows: Sequence[Dict[str, Any]]) -> None:
    """A6.3 with v3 5.3: no question may be counted twice.

    A continuation row carries ("job", job_id); a state-value row carries ("future", rep). The
    two label spaces are disjoint by construction, and this asserts it rather than trusting it,
    because the rule is the one thing A6.3 says must hold when a prefix is valued in the memory
    decision."""
    c = {tuple(r["counts_question"]) for r in continuation_rows if "counts_question" in r}
    s = {tuple(r["counts_question"]) for r in state_rows if "counts_question" in r}
    overlap = c & s
    if overlap:
        raise AssertionError("A6.3 single counting violated for %s" % sorted(overlap))
    for r in state_rows:
        if r.get("excluded_job") is not None:
            key = ("job", r["excluded_job"])
            if key in s:
                raise AssertionError("state value counted the in-progress question %s" % (key,))


def prefix_items(fleet, risk: Dict[str, Any], state_rows: Sequence[Dict[str, Any]]
                 ) -> List[Dict[str, Any]]:
    """A6.3: an in-progress job's built prefix becomes an item in the memory decision, valued at
    its CONTINUATION VALUE AT RISK (the drop in ContValue if it is lost) plus its STATE VALUE for
    future questions, counted once each.

    No code path may assume a prefix is pinned: this only changes how the prefix is VALUED, and
    the value acts through scheduling choices (finishing sooner, larger pieces, not releasing
    competing KV-heavy work), never through a pin."""
    out: List[Dict[str, Any]] = []
    by_rep = {}
    for r in state_rows:
        by_rep[(r.get("device"), r.get("rep"))] = r
    for jid, info in (risk or {}).items():
        job = fleet.jobs.get(jid)
        if job is None:
            continue
        sv = by_rep.get((job.device, job.rep), {})
        out.append(dict(
            kind="in_progress_prefix", job_id=jid, device=job.device, rep=job.rep,
            tokens=int(info.get("built_prefix_tokens", 0)),
            continuation_value_at_risk=float(info.get("continuation_value_at_risk", 0.0)),
            state_value_future=float(sv.get("value", 0.0)),
            value=float(info.get("continuation_value_at_risk", 0.0)) + float(sv.get("value", 0.0)),
            counts_question=("job", jid), state_counts=("future", job.rep),
            pinned=False,
            note="valued once as the job's own question at risk and once as readiness for future "
                 "questions (A6.3); the prefix is NOT pinned"))
    return out


def tier_assignment(candidates: Sequence[Dict[str, Any]], gpu_capacity_tokens: int,
                    host_capacity_tokens: int) -> Dict[str, Any]:
    """Spec 6.3: greedy promotion by state-value gain PER BYTE of the scarce tier, within
    capacity. nu_tier is the gain per byte of the last promotion into a full tier.

    A capacity of 0 means 'not supplied' and raises, because a silently wrong capacity changes
    every allocation (see params.PROVENANCE)."""
    if gpu_capacity_tokens <= 0 or host_capacity_tokens <= 0:
        raise ValueError("GPU and host KV capacities must be supplied (tokens > 0); "
                         "params.Params leaves them at 0 deliberately")
    ranked = sorted(candidates, key=lambda c: -(c["value"] / max(c["tokens"], 1)))
    gpu_used = host_used = 0
    gpu, host, denied = [], [], []
    nu = {"GPU": 0.0, "HOST": 0.0}
    for c in ranked:
        dens = c["value"] / max(c["tokens"], 1)
        if gpu_used + c["tokens"] <= gpu_capacity_tokens and c["value"] > 0:
            gpu.append(c)
            gpu_used += c["tokens"]
            nu["GPU"] = dens
        elif host_used + c["tokens"] <= host_capacity_tokens and c["value"] > 0:
            host.append(c)
            host_used += c["tokens"]
            nu["HOST"] = dens
        else:
            denied.append(c)
    return dict(gpu=gpu, host=host, denied=denied, gpu_tokens_used=gpu_used,
                host_tokens_used=host_used, nu_tier=nu,
                note="an approximation of a multiple-choice knapsack (spec 6.3); the evaluation "
                     "compares it against a stronger offline allocation on recorded traces")


def state_actions(device: Device, rep: str, flags, target: Optional[str] = None
                  ) -> List[StateAction]:
    """Spec 6.2's table, with the conditional rows gated by their flags."""
    b = device.history[rep]
    cur = b.most_likely()
    out: List[StateAction] = []
    if cur == "HOST":
        out.append(StateAction("PROMOTE_RELOAD", device.device_id, rep, "GPU", b.size_tokens))
    if cur == "STORED":
        out.append(StateAction("PROMOTE_REBUILD", device.device_id, rep, "GPU", b.size_tokens))
    if cur == "GPU":
        out.append(StateAction("DEMOTE", device.device_id, rep, "HOST", b.size_tokens))
    if b.staleness_s > 0:
        out.append(StateAction("CATCH_UP", device.device_id, rep, cur, b.size_tokens))
    if flags.summaries:
        out.append(StateAction("REFRESH_SUMMARY", device.device_id, rep, cur, b.size_tokens,
                               conditional=True, spec="7.10"))
    if flags.predictive_upload and b.unsent_frames > 0:
        out.append(StateAction("REQUEST_UPLOAD", device.device_id, rep, cur, b.size_tokens,
                               conditional=True, spec="7.11"))
    if target is not None:
        out = [a for a in out if a.target_tier == target]
    return out
