"""D138 P1: the chooser's three required proofs and its cost report.

1. OFF-SWITCH. `enabled=False` returns the handed-in default BY IDENTITY and runs zero rollouts.
   This is a single switch gating the whole change, not a reconstruction of prior behaviour.
2. DEVIATION. The chooser must be shown to deviate from the default at least once, by candidate
   kind, BEFORE any comparison is reported. A chooser that always returns the default passes every
   correctness test perfectly.
3. COST. Rollouts per call and latency per call at 10, 12, 16 and 32 devices, which is the range
   where this could become the binding cost.
"""
from __future__ import annotations
import json, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent), str(HERE.parent.parent / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import chooser as CH
from tests import _fixtures as FX
from state import Job, PendingItem


def _fleet_with_work(n_devices: int, n_jobs: int = 6):
    f = FX.fleet(n_devices=n_devices, t=0.0)
    for i in range(min(n_jobs, n_devices)):
        did = sorted(f.devices)[i]
        j = FX.job(did=did, deadline=5.0, pieces=4, done=0)
        f.jobs[j.job_id] = j
        for k in range(2):
            f.pending.append(FX.piece_item(did=did, t=0.0, iid="pc_%d_%d" % (i, k),
                                           deadline=5.0))
    return f


def _candidates(f):
    """One robot question's options, each carrying its own rollout kwargs and its own span.

    The chooser never interprets these; the component proposing them does.
    """
    ids = [p.item_id for p in f.pending]
    first = ids[:1]
    rest = ids[1:3]
    return [
        CH.Candidate(kind="default_defer", rollout_kwargs={}, deadline_s=5.0),
        CH.Candidate(kind="warm", rollout_kwargs=dict(release_now=tuple(first)), deadline_s=5.0),
        CH.Candidate(kind="pieces", rollout_kwargs=dict(release_now=tuple(first + rest)),
                     deadline_s=5.0),
        CH.Candidate(kind="decline", rollout_kwargs=dict(drop=tuple(first)), deadline_s=5.0),
        CH.Candidate(kind="rebuild_now", rollout_kwargs=dict(exclude=tuple(rest)), deadline_s=5.0),
    ]


def off_switch_proof(trials: int = 200):
    ch = CH.Chooser(enabled=False)
    f = _fleet_with_work(8)
    cands = _candidates(f)
    st = CH.ChooserState(rollout=FX.rollout(), fleet=f, now_s=0.0)
    identical = 0
    for i in range(trials):
        d = cands[i % len(cands)]
        got = ch.choose(cands, st, default=d)
        if got is d:
            identical += 1
    return dict(trials=trials, returned_default_by_identity=identical,
                rollouts_run=ch.stats["rollouts"],
                verdict=("PASS: default returned by identity on every trial, zero rollouts"
                         if identical == trials and ch.stats["rollouts"] == 0 else "FAIL"))


def cell(n_devices: int, delta: float = 0.0, calls: int = 12):
    ch = CH.Chooser(enabled=True, delta=delta)
    ro = FX.rollout()
    out = []
    for c in range(calls):
        f = _fleet_with_work(n_devices)
        st = CH.ChooserState(rollout=ro, fleet=f, now_s=0.0)
        cands = _candidates(f)
        chosen = ch.choose(cands, st, default=cands[0])
        out.append(chosen.kind)
    lat = ch.stats["latency_ms_per_call"]
    rpc = ch.stats["rollouts_per_call"]
    return dict(n_devices=n_devices, calls=ch.stats["calls"],
                rollouts_total=ch.stats["rollouts"],
                rollouts_per_call=dict(min=min(rpc), median=statistics.median(rpc), max=max(rpc)),
                latency_ms_per_call=dict(min=round(min(lat), 3),
                                         median=round(statistics.median(lat), 3),
                                         max=round(max(lat), 3),
                                         mean=round(statistics.fmean(lat), 3)),
                deviations=ch.stats["deviations"], defaults_kept=ch.stats["defaults_kept"],
                deviations_by_kind=dict(ch.stats["deviations_by_kind"]),
                chosen_kinds={k: out.count(k) for k in sorted(set(out))})


if __name__ == "__main__":
    rep = dict(off_switch=off_switch_proof(), cells=[])
    print(json.dumps(rep["off_switch"]), flush=True)
    for n in (10, 12, 16, 32):
        c = cell(n)
        rep["cells"].append(c)
        print(json.dumps(c), flush=True)
    rep["deviation_proof"] = dict(
        total_deviations=sum(c["deviations"] for c in rep["cells"]),
        by_kind={k: sum(c["deviations_by_kind"].get(k, 0) for c in rep["cells"])
                 for k in sorted({k for c in rep["cells"] for k in c["deviations_by_kind"]})})
    out = HERE.parent.parent.parent / "results/orchestration/live2/chooser/chooser_probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out, "w"), indent=1)
    print("wrote", out, flush=True)
