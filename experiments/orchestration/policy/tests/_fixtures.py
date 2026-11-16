"""Fixtures the tests share. No randomness: every object here is deterministic."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "experiments/orchestration"))

from policy import (Coordinator, Demand, Device, Flags, HistoryBelief, Link, Params,
                    PlaceholderEngine, Rollout, Fleet, Job, PendingItem, load_profiles)

PF = load_profiles()


def params(**kw) -> Params:
    p = Params()
    p.gpu_kv_capacity_tokens = 200_000
    p.host_kv_capacity_tokens = 2_000_000
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def device(did: str = "d0", size_tokens: int = 11_000, staleness_s: float = 0.0,
           tier: str = "STORED") -> Device:
    link = Link(bandwidth_bytes_s=PF.uplink_bytes_per_s(), rtt_s=PF.rtt_s())
    probs = {"GPU": 0.0, "HOST": 0.0, "STORED": 0.0}
    probs[tier] = 1.0
    d = Device(device_id=did, link=link,
               history={"RICH": HistoryBelief(rep="RICH", size_tokens=size_tokens, probs=probs,
                                              staleness_s=staleness_s)},
               qtype="counting_objects_events")
    d.demand = Demand().prior_from_profiles(PF)
    return d


def fleet(n_devices: int = 1, t: float = 0.0) -> Fleet:
    f = Fleet(t=t)
    for i in range(n_devices):
        f.add_device(device("d%d" % i))
    return f


def engine(pf=PF) -> PlaceholderEngine:
    return PlaceholderEngine(profiles=pf, gpu_kv_tokens=200_000, host_kv_tokens=2_000_000)


def rollout(flags: Flags = None, p: Params = None) -> Rollout:
    return Rollout(PF, p or params(), flags or Flags(), engine())


def coordinator(flags: Flags = None, p: Params = None) -> Coordinator:
    pp = p or params()
    ff = flags or Flags()
    return Coordinator(PF, pp, ff, engine(), Rollout(PF, pp, ff, engine()))


def call_item(did: str = "d0", t: float = 0.0, iid: str = "call0") -> PendingItem:
    return PendingItem(item_id=iid, kind="episode_call", device=did, due_at=t, frames=1)


def piece_item(did: str = "d0", t: float = 0.0, iid: str = "p0", deadline: float = 10.0,
               tokens: int = 2048, job_id: str = "j0") -> PendingItem:
    return PendingItem(item_id=iid, kind="rc_piece", device=did, due_at=t, deadline=deadline,
                       tokens=tokens, job_id=job_id)


def job(did: str = "d0", deadline: float = 10.0, pieces: int = 4, done: int = 0) -> Job:
    return Job(job_id="j0", device=did, qtype="counting_objects_events", rep="RICH",
               deadline=deadline, admitted_at=0.0, pieces_total=pieces, pieces_done=done,
               tokens_per_piece=2048)
