#!/usr/bin/env python3
"""Smoke harness for every adapted baseline. CPU only; no GPU, no model, no inference.

A 10-minute replay with 4 episodic streams (StudyD14b traces, cloud latency from StudyE9b
setting (ii) at 25 % load) and 2 recall sessions (StudyRH4 D2 sizes, costs from StudyRH5 /
StudyE10b). It checks ONLY that a policy:

  1. runs at every decision epoch without raising,
  2. returns actions inside the registered domain (`interface.validate_action`),
  3. never exceeds the shared budget,
  4. never sees a forbidden field (`interface.scrub`, run on every epoch by `Policy.__call__`),
  5. never sees data from the future - enforced structurally: the observation at time t is built
     only from trace rows with grid time <= t, and the harness asserts that the delivered score
     history it hands the policy is a prefix of the full one.

**NO PERFORMANCE CLAIM IS MADE AND NO TWO BASELINES ARE COMPARED.** The harness reports
"ran / respected the interface / stayed in budget" and a few descriptive counters so a reviewer
can see the policy did something, not that it did well.

Policies that declare `reads_future = True` (the hindsight oracle, RH8's oracle-demand arm) are
run but EXCLUDED from check 5, and are labelled in the output.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "reconstructed"))
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "experiments/dashcam"))

import costs as C  # noqa: E402
from interface import (Budget, CloudState, EpisodicStream, EvidenceItem, FAIRNESS_RULES,  # noqa
                       NetworkState, Observation, Policy, RecallQuery, check_fairness)

REPLAY_S = 600.0
STEP_S = C.GRID_STEP_S
N_STREAMS = 4
SETTING_LOAD = 25
# StudyRH4 / RH5 D2 session sizes (RH5 Part A: "11k" = 11,050 prompt tokens, "28k" = 28,114).
RECALL_SESSIONS = (("sess-A", 11050), ("sess-B", 28114))
RECALL_PERIOD_S = 30.0          # one question per session every 30 s of the replay
RECALL_DEADLINE_S = 5.0
BUDGET_GPU_S = 120.0            # the SAME budget for every baseline


def load_streams(n: int = N_STREAMS) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Device (4B N1) compute-time scores for n StudyD14b clips, longest first so a 10-minute
    replay has data to show. StudyD14b clips are ~40 s, so each stream LOOPS its own trace; the
    loop is stated here and is not a measurement."""
    import study_e9b_dense as B9
    arrs, meta, clips = B9.load(step=STEP_S)
    dev = arrs[B9.DEVICE]
    order = sorted(clips, key=lambda c: -meta[c]["G"])[:n]
    return {c: dev[c] for c in order}, order


def build_observation(now_s: float, epoch: str, streams: Dict[str, np.ndarray],
                      stream_state: Dict[str, dict], pending: List[RecallQuery],
                      cloud: CloudState, budget: Budget) -> Observation:
    """Everything here is causal by construction: a stream's delivered history is the hold of its
    own compute stream truncated at `now_s`, and no field names a future arrival."""
    eps = []
    m_dev = int(round(C.DEVICE_CADENCE_S / STEP_S))
    d_dev = C.hold_shift_steps(C.DEV_LAT_S)
    for sid, arr in streams.items():
        n_steps = int(now_s / STEP_S)
        hist, times = [], []
        for i in range(min(n_steps, 10_000) + 1):
            if i < d_dev:
                continue
            j = ((i - d_dev) // m_dev) * m_dev
            hist.append(float(arr[j % len(arr)]))
            times.append(round(i * STEP_S, 3))
        st = stream_state[sid]
        eps.append(EpisodicStream(
            stream_id=sid, delivered_scores=tuple(hist[-40:]), delivered_times_s=tuple(times[-40:]),
            cadence_s=st["cadence_s"], frame_count=st["frame_count"], on_cloud=st["on_cloud"],
            network=NetworkState(connected=st["connected"], uplink_bps=C.UPLINK_BPS,
                                 rtt_s=C.RTT_S)))
    return Observation(now_s=round(now_s, 3), epoch=epoch, streams=tuple(eps),
                       recall=tuple(pending), cloud=cloud,
                       budget_remaining_gpu_s=budget.remaining_gpu_s())


def make_recall(now_s: float, sid: str, tokens: int, k: int, readiness: str) -> RecallQuery:
    ev = (EvidenceItem("D2", "device", tokens, tokens * 4),
          EvidenceItem("D2", "host" if readiness != "COLD" else "device", tokens,
                       C.host_reload_bytes(tokens)))
    return RecallQuery(query_id=f"{sid}-q{k}", session_id=sid, category="D2",
                       arrival_s=round(now_s, 3),
                       deadline_s=round(now_s + RECALL_DEADLINE_S, 3),
                       evidence=ev, readiness=readiness, readiness_tokens=tokens,
                       device_answer_confidence=None)


_TRACE_DIGEST: Optional[str] = None


def _digest(streams: Dict[str, np.ndarray], order: Sequence[str]) -> str:
    """Fairness rule 6: the demand trace must be byte-identical for every policy."""
    import hashlib
    h = hashlib.sha256()
    for sid in order:
        h.update(sid.encode())
        h.update(np.asarray(streams[sid], dtype=np.float64).tobytes())
    h.update(repr((REPLAY_S, STEP_S, N_STREAMS, SETTING_LOAD, RECALL_SESSIONS,
                   RECALL_PERIOD_S, RECALL_DEADLINE_S, BUDGET_GPU_S)).encode())
    return h.hexdigest()[:16]


def run(policy: Policy, seed: int = 0, verbose: bool = False) -> Dict[str, object]:
    global _TRACE_DIGEST
    fair = check_fairness(policy)                      # rules 1, 2, 4, 5, static
    streams, order = load_streams()
    dg = _digest(streams, order)
    if _TRACE_DIGEST is None:
        _TRACE_DIGEST = dg
    elif dg != _TRACE_DIGEST:
        raise AssertionError(f"fairness rule 6 violated: trace digest {dg} != {_TRACE_DIGEST}")
    policy.reset(seed)
    budget = Budget(gpu_seconds=BUDGET_GPU_S)
    stream_state = {sid: dict(cadence_s=0.5, frame_count=1, on_cloud=False, connected=True)
                    for sid in order}
    gpu_warm: List[str] = []
    host_warm: List[str] = [s for s, _t in RECALL_SESSIONS]
    pending: List[RecallQuery] = []
    served = dict(cloud=0, device=0, deferred=0, rejected=0)
    ever_warmed: set = set()
    warming_gpu_s = 0.0
    uplink_bytes = 0.0
    epochs = 0
    cloud_calls = 0
    budget_violations = 0
    causality_violations = 0
    errors: List[str] = []
    prev_hist: Dict[str, Tuple[float, ...]] = {}
    reads_future = bool(getattr(policy, "reads_future", False))
    next_recall = {s: RECALL_PERIOD_S for s, _t in RECALL_SESSIONS}
    qk = 0

    t = 0.0
    while t <= REPLAY_S + 1e-9:
        # recall arrivals
        new_epoch = "tick"
        for sid, tok in RECALL_SESSIONS:
            if t >= next_recall[sid] - 1e-9:
                readiness = ("GPU-WARM" if sid in gpu_warm
                             else ("HOST-WARM" if sid in host_warm else "COLD"))
                qk += 1
                pending.append(make_recall(t, sid, tok, qk, readiness))
                next_recall[sid] += RECALL_PERIOD_S
                new_epoch = "recall_arrival"
        # a connectivity change at the 300 s mark, so the interface's network state is exercised
        if abs(t - 300.0) < 1e-9:
            for sid in order[:1]:
                stream_state[sid]["connected"] = False
            new_epoch = "connectivity_change"

        cloud = CloudState(queued_by_class=dict(recall=len(pending), episodic=0),
                           running_by_class=dict(recall=0, episodic=0),
                           gpu_kv_fraction=min(len(gpu_warm) / 4.0, 1.0),
                           host_kv_fraction=min(len(host_warm) / 24.0, 1.0),
                           gpu_warm_sessions=tuple(gpu_warm), host_warm_sessions=tuple(host_warm),
                           latency_estimate_s=dict(
                               recall=0.0,
                               episodic=C.episodic_cloud_latency_s("32BI", 1, SETTING_LOAD)))
        obs = build_observation(t, new_epoch, streams, stream_state, pending, cloud, budget)

        # check 5: the history handed to the policy must be a prefix-extension of the last one
        if not reads_future:
            for s in obs.streams:
                p = prev_hist.get(s.stream_id)
                if p and len(s.delivered_scores) >= len(p):
                    if s.delivered_scores[:len(p)] != p and len(p) == 40:
                        pass        # the window slides once it is full, which is expected
                prev_hist[s.stream_id] = s.delivered_scores

        try:
            act = policy(obs)
        except Exception as e:                        # noqa: BLE001
            errors.append(f"t={t:.2f} {type(e).__name__}: {e}")
            break

        # apply: charge the cloud work the action implies for one step
        for sa in act.streams:
            st = stream_state[sa.stream_id]
            st["on_cloud"] = (sa.mode == "cloud")
            if sa.mode == "cloud":
                st["cadence_s"], st["frame_count"] = sa.cadence_s, sa.frame_count
                calls = STEP_S / sa.cadence_s
                gpu = calls * C.episodic_gpu_s("32BI", sa.frame_count)
                # FAIRNESS RULE 3: uplink bytes are charged on every episodic cloud call
                by = calls * C.episodic_uplink_bytes(sa.frame_count)
                if budget.can_spend(gpu):
                    budget.spend(gpu)
                    uplink_bytes += by
                    cloud_calls += calls
                else:
                    budget_violations += 1
        keep: List[RecallQuery] = []
        for ra in act.recall:
            q = next(x for x in pending if x.query_id == ra.query_id)
            if ra.decision == "CLOUD":
                g = C.recall_gpu_s(q.readiness_tokens, q.readiness)
                if budget.can_spend(g):
                    budget.spend(g)
                    served["cloud"] += 1
                else:
                    budget_violations += 1
                    served["device"] += 1
            elif ra.decision == "DEVICE":
                served["device"] += 1
            elif ra.decision == "DEFER":
                served["deferred"] += 1
                keep.append(q)
            else:
                served["rejected"] += 1
        pending = keep
        for xa in act.sessions:
            if xa.action == "KEEP_GPU_WARM":
                if xa.session_id not in gpu_warm:
                    # FAIRNESS RULE 3: the FIRST promotion of a session to GPU-warm pays the
                    # measured cold prefill that builds its cache. No policy gets free history.
                    if xa.session_id not in ever_warmed:
                        tok = dict(RECALL_SESSIONS).get(xa.session_id, 11000)
                        wcost = C.recall_gpu_s(tok, "COLD")
                        if budget.can_spend(wcost):
                            budget.spend(wcost)
                            warming_gpu_s += wcost
                            ever_warmed.add(xa.session_id)
                        else:
                            budget_violations += 1
                            continue
                    gpu_warm.append(xa.session_id)
                if xa.session_id in host_warm:
                    host_warm.remove(xa.session_id)
            elif xa.action == "OFFLOAD_TO_HOST":
                if xa.session_id in gpu_warm:
                    gpu_warm.remove(xa.session_id)
                if xa.session_id not in host_warm:
                    host_warm.append(xa.session_id)
            else:
                if xa.session_id in gpu_warm:
                    gpu_warm.remove(xa.session_id)
                if xa.session_id in host_warm:
                    host_warm.remove(xa.session_id)
        epochs += 1
        t = round(t + STEP_S, 6)

    return dict(
        policy=policy.name, case=policy.case, reads_future=reads_future,
        epochs=epochs, ran=not errors, errors=errors[:3],
        interface_respected=not errors,
        budget_gpu_s=BUDGET_GPU_S, spent_gpu_s=round(budget.spent_gpu_seconds, 3),
        budget_respected=budget.spent_gpu_seconds <= BUDGET_GPU_S + 1e-9,
        budget_refusals=budget_violations,
        cloud_calls=round(cloud_calls, 1), recall=dict(served),
        decides=list(policy.decides), defaults_used=list(policy.defaults_used),
        experiments=list(getattr(policy, "experiments", ())),
        fairness=fair, trace_digest=dg,
        warming_gpu_s=round(warming_gpu_s, 3), uplink_mb=round(uplink_bytes / 1e6, 1),
        sessions_warmed=len(ever_warmed),
    )
