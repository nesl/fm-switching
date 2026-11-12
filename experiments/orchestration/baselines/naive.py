#!/usr/bin/env python3
"""The seven naive baselines, implemented directly behind the policy interface.

StudyB-baselines. CPU only. No performance claim is made and these are never compared with one
another here.

All seven decide the full action space except where noted; whatever they leave undecided is
filled by `interface.DEFAULTS`, identically for every baseline.
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Optional, Sequence

import numpy as np

from interface import (DEFAULTS, Action, Observation, Policy, RecallAction, SessionAction,
                       StreamAction)


# ---------------------------------------------------------------- 1. device-only
class DeviceOnly(Policy):
    """Everything local. The cloud is never called, so the cloud action space is unused rather
    than defaulted."""

    name = "device-only"
    case = "naive"
    experiments = ('A-episodic', 'C-mixed')
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ()

    def decide(self, obs: Observation) -> Action:
        return Action(
            streams=[StreamAction(s.stream_id, "local") for s in obs.streams],
            recall=[RecallAction(q.query_id, "DEVICE") for q in obs.recall],
            sessions=[SessionAction(sid, "EVICT") for sid in obs.cloud.gpu_warm_sessions],
        )


# ---------------------------------------------------------------- 2. always-cloud FCFS
class AlwaysCloudFCFS(Policy):
    """Every stream on the cloud at the default cadence and frame count, every recall served on
    the cloud immediately at whatever readiness it happens to have, FCFS order, default engine.
    This is the vLLM-default arm: no admission, no ordering, no state management beyond the
    default host offload."""

    name = "always-cloud-fcfs"
    case = "naive"
    experiments = ('A-episodic', 'B-recall', 'C-mixed')
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order",
                     "engine_config")

    def decide(self, obs: Observation) -> Action:
        return Action(
            streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
            recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall],
            order="FCFS",
            engine_config="default",
        )


# ---------------------------------------------------------------- 3. random admission
class RandomAdmission(Policy):
    """Admit a fraction `budget_fraction` of streams and of recall queries uniformly at random.

    The matched budget is the point of this baseline, so the fraction is a constructor argument
    and the harness sets it to whatever share the policy under test realised. Reported as a mean
    over `n_seeds` seeds (the harness runs it once per seed; `reset(seed)` selects the stream)."""

    name = "random-admission"
    case = "naive"
    experiments = ('A-episodic', 'C-mixed')
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")
    n_seeds = 20

    def __init__(self, budget_fraction: float = 0.5, n_seeds: int = 20) -> None:
        self.budget_fraction = float(budget_fraction)
        self.n_seeds = int(n_seeds)
        self._rng = np.random.default_rng(0)

    def reset(self, seed: int = 0) -> None:
        self._rng = np.random.default_rng([12345, seed])

    def decide(self, obs: Observation) -> Action:
        b = self.budget_fraction
        return Action(
            streams=[StreamAction(s.stream_id,
                                  "cloud" if self._rng.random() < b else "local")
                     for s in obs.streams],
            recall=[RecallAction(q.query_id,
                                 "CLOUD" if self._rng.random() < b else "DEVICE")
                    for q in obs.recall],
        )


# ---------------------------------------------------------------- 4. round robin
class RoundRobin(Policy):
    """Equal cloud share per stream: at every epoch exactly `k` streams hold the cloud slot, and
    the slot rotates, so over a replay each stream gets the same share. `k` is set from the
    matched budget by the harness."""

    name = "round-robin"
    case = "naive"
    experiments = ('A-episodic',)
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")

    def __init__(self, n_cloud_slots: int = 1) -> None:
        self.k = int(n_cloud_slots)
        self._cursor = 0

    def reset(self, seed: int = 0) -> None:
        self._cursor = 0

    def decide(self, obs: Observation) -> Action:
        ids = [s.stream_id for s in obs.streams]
        chosen = set()
        if ids:
            for j in range(min(self.k, len(ids))):
                chosen.add(ids[(self._cursor + j) % len(ids)])
            self._cursor = (self._cursor + max(self.k, 1)) % len(ids)
        qids = [q.query_id for q in obs.recall]
        # recall queries round-robin on the same cursor so the share is equal across both classes
        radm = set(qids[:self.k]) if qids else set()
        return Action(
            streams=[StreamAction(i, "cloud" if i in chosen else "local") for i in ids],
            recall=[RecallAction(q, "CLOUD" if q in radm else "DEVICE") for q in qids],
        )


# ---------------------------------------------------------------- 5. static partition
class StaticPartition(Policy):
    """A fixed cloud share per query class, decided offline and never adapted.

    `stream_share` is the fraction of streams pinned to the cloud (chosen by stream id order, so
    the partition is stable); `class_share` maps a recall category to the fraction of its queries
    served on the cloud, applied by a stable hash of the query id so the same query always lands
    the same way. Shares come from the development split, never from evaluation data."""

    name = "static-partition"
    case = "naive"
    experiments = ('A-episodic', 'C-mixed')
    decides = ("episodic_mode", "recall_decision")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action", "order")

    def __init__(self, stream_share: float = 0.5,
                 class_share: Optional[Dict[str, float]] = None,
                 default_class_share: float = 0.5) -> None:
        self.stream_share = float(stream_share)
        self.class_share = dict(class_share or {})
        self.default_class_share = float(default_class_share)

    @staticmethod
    def _unit_hash(key: str) -> float:
        import zlib
        return (zlib.crc32(key.encode()) % (1 << 30)) / float(1 << 30)

    def decide(self, obs: Observation) -> Action:
        ids = sorted(s.stream_id for s in obs.streams)
        n_cloud = int(round(self.stream_share * len(ids)))
        cloud = set(ids[:n_cloud])
        rec = []
        for q in obs.recall:
            share = self.class_share.get(q.category, self.default_class_share)
            rec.append(RecallAction(q.query_id,
                                    "CLOUD" if self._unit_hash(q.query_id) < share else "DEVICE"))
        return Action(
            streams=[StreamAction(s.stream_id,
                                  "cloud" if s.stream_id in cloud else "local")
                     for s in obs.streams],
            recall=rec,
        )


# ---------------------------------------------------------------- 6. EDF
class EDFServiceTime(Policy):
    """Earliest-deadline-first over recall queries, with admission by service-time estimate.

    A query is admitted to the cloud only if the estimated service time at its current readiness
    fits in its remaining slack; otherwise it is served on the device. Among admitted queries the
    order is by deadline (the `order` field carries "EDF" so the harness sorts that way).
    Service-time estimates come from `costs.recall_ttft_s`, i.e. the measured StudyRH5 curves at
    the query's own readiness and token count — never a label and never a future arrival.

    Streams: EDF has nothing to say about a standing query with no deadline, so streams take the
    documented default (cloud at c = 0.5 s, N = 1) when the budget allows and local otherwise.
    """

    name = "edf-service-time"
    case = "naive"
    experiments = ('C-mixed',)
    decides = ("recall_decision", "order")
    defaults_used = ("cadence_s", "frame_count", "representation", "session_action",
                     "episodic_mode")

    def __init__(self, safety_factor: float = 1.0) -> None:
        self.safety = float(safety_factor)

    def decide(self, obs: Observation) -> Action:
        import costs as C
        rec: List[RecallAction] = []
        for q in sorted(obs.recall, key=lambda x: x.deadline_s):
            est = C.recall_ttft_s(max(q.readiness_tokens, 1), q.readiness) * self.safety
            fits = est <= q.slack_s(obs.now_s)
            rec.append(RecallAction(q.query_id, "CLOUD" if fits else "DEVICE"))
        mode = "cloud" if obs.budget_remaining_gpu_s > 0 else "local"
        return Action(
            streams=[StreamAction(s.stream_id, mode) for s in obs.streams],
            recall=rec,
            order="EDF",
        )


# ---------------------------------------------------------------- 7. hindsight oracle
class HindsightOracle(Policy):
    """UPPER BOUND, NOT A POLICY. It reads the future.

    The interface forbids future information in the observation, and this class does not break
    that: the harness injects the realised trace through the constructor, out of band, and the
    class declares `reads_future = True`. The smoke harness therefore EXCLUDES it from the
    causality check and the report must never present it as a deployable baseline.

    `plan` maps (epoch_index) -> Action, precomputed by the harness from the whole replay.
    """

    name = "hindsight-oracle"
    case = "naive"
    experiments = ('A-episodic', 'B-recall', 'C-mixed')
    reads_future = True
    decides = ("all",)
    defaults_used = ()

    def __init__(self, plan: Optional[Sequence[Action]] = None) -> None:
        self.plan = list(plan or [])
        self._i = 0

    def reset(self, seed: int = 0) -> None:
        self._i = 0

    def decide(self, obs: Observation) -> Action:
        if self._i < len(self.plan):
            a = self.plan[self._i]
            self._i += 1
            # the plan may name entities that have since departed; keep only live ones
            sids = {s.stream_id for s in obs.streams}
            qids = {q.query_id for q in obs.recall}
            return Action(
                streams=[s for s in a.streams if s.stream_id in sids],
                recall=[r for r in a.recall if r.query_id in qids],
                sessions=list(a.sessions), engine_config=a.engine_config, order=a.order)
        self._i += 1
        return Action(streams=[StreamAction(s.stream_id, "cloud") for s in obs.streams],
                      recall=[RecallAction(q.query_id, "CLOUD") for q in obs.recall])


NAIVE_POLICIES = {
    "device-only": DeviceOnly,
    "always-cloud-fcfs": AlwaysCloudFCFS,
    "random-admission": RandomAdmission,
    "round-robin": RoundRobin,
    "static-partition": StaticPartition,
    "edf-service-time": EDFServiceTime,
    "hindsight-oracle": HindsightOracle,
}
