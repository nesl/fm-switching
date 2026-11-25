#!/usr/bin/env python3
"""StudyORACLE stage 2: dashcam episode max-over-subsets valuation (CPU, no images).

The LP values single queries, but a dashcam episode's correctness depends on WHICH instants carry a
cloud answer, and serving a bad instant can LOWER the episode value, so episode value is not
monotone in the served set. Per the pre-reg (fix 1) each episode e enters the LP as one unit worth
gain_e = v_e^max - v_e^dev for work w_e, where:
  v_e^dev = episode value with ALL instants DEVICE (served set empty);
  v_e^max = MAX over every subset S of served (cloud) instants of v_e(S);
  w_e     = MIN work over every IMPROVING subset S (v_e(S) > v_e^dev) of the W_q of instants in S.

Episode correctness v_e(S) (standing-crossing model, dashcam_episodic / D197):
  each instant i has a device score d_i (threshold th_dev) and a cloud score c_i (threshold
  th_cloud); with cloud served on S, instant i CROSSES iff (c_i >= th_cloud if i in S else
  d_i >= th_dev). The episode raises its alert at the FIRST crossing in time order.
  - CRASH episode (has a pre-event instant, ref = time_of_event): CORRECT iff the first crossing
    occurs at pts < ref (a true, in-time detection).
  - NO-CRASH episode: CORRECT iff NO instant crosses (no false alarm).
  v_e(S) is 1 if correct else 0 (HINDSIGHT actual; FAIR uses per-tier episode-threshold expected
  correctness, wired in the live-data stage; the MACHINERY here is identical, only the scores and
  the 0/1-vs-expected value differ).

Enumeration is EXACT but small: only DECISIVE instants (where cloud crossing != device crossing) can
change v_e, so subsets are enumerated over decisive instants only (the pre-reg's "decisive instants
are few"). This file is the machinery plus a unit test on hand-built episodes; it is applied to the
live episodes in the next stage.
"""
from __future__ import annotations
import itertools
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Instant:
    pts: float           # clip time (for ordering and the pre-event test)
    d_score: float       # device (4BI) standing score
    c_score: float       # cloud (32BI) standing score
    work: float          # W_q tokens to serve this instant on the cloud


@dataclass
class Episode:
    eid: str
    instants: List[Instant]
    is_crash: bool
    ref: Optional[float]           # time_of_event (crash only)
    th_dev: float
    th_cloud: float


def _crosses(inst: Instant, served: bool, th_dev: float, th_cloud: float) -> bool:
    return (inst.c_score >= th_cloud) if served else (inst.d_score >= th_dev)


def episode_correct(ep: Episode, served_set: frozenset) -> int:
    """1 if the episode is correct with cloud served on served_set, else 0."""
    first_cross_pts = None
    for inst in sorted(ep.instants, key=lambda x: x.pts):
        if _crosses(inst, id(inst) in served_set, ep.th_dev, ep.th_cloud):
            first_cross_pts = inst.pts
            break
    if ep.is_crash:
        return 1 if (first_cross_pts is not None and ep.ref is not None
                     and first_cross_pts < ep.ref) else 0
    else:
        return 1 if first_cross_pts is None else 0


def max_over_subsets(ep: Episode):
    """Return v_dev, v_max, gain, w (min improving-subset work), and the enumeration size."""
    # decisive instants: cloud crossing != device crossing (only these can change v_e)
    decisive = [i for i in ep.instants
                if (i.c_score >= ep.th_cloud) != (i.d_score >= ep.th_dev)]
    v_dev = episode_correct(ep, frozenset())
    v_max = v_dev
    best_w = None
    # enumerate subsets of decisive instants (served = cloud on that instant)
    for r in range(len(decisive) + 1):
        for combo in itertools.combinations(decisive, r):
            S = frozenset(id(i) for i in combo)
            v = episode_correct(ep, S)
            if v > v_max:
                v_max = v
            if v > v_dev:
                w = sum(i.work for i in combo)
                if best_w is None or w < best_w:
                    best_w = w
    gain = v_max - v_dev
    # if no subset improves, gain is 0 and there is no work to spend
    w = best_w if (gain > 0 and best_w is not None) else 0.0
    return {"v_dev": v_dev, "v_max": v_max, "gain": gain, "w": w,
            "n_decisive": len(decisive), "n_subsets": 2 ** len(decisive)}


def _unit_test():
    ok = True
    TD, TC = 0.5, 0.5   # thresholds
    # Episode A: CRASH, ref=10. Device never crosses before event (all d<0.5), cloud crosses at a
    # pre-event instant (c>=0.5). Device-only MISSES (v_dev=0); serving that one cloud instant
    # DETECTS in time (v_max=1); gain=1, w = that instant's work.
    a = Episode("A", [Instant(2, 0.1, 0.9, 100), Instant(5, 0.2, 0.2, 100),
                      Instant(12, 0.1, 0.1, 100)], is_crash=True, ref=10, th_dev=TD, th_cloud=TC)
    ra = max_over_subsets(a)
    print("A crash-rescue:", ra, "expect v_dev=0 v_max=1 gain=1 w=100")
    ok &= ra == {"v_dev": 0, "v_max": 1, "gain": 1, "w": 100.0, "n_decisive": 1, "n_subsets": 2}
    # Episode B: NO-CRASH. Device does not cross (no false alarm) -> v_dev=1 (correct). Cloud WOULD
    # cross on one instant (c>=0.5) -> serving it causes a FALSE ALARM, lowering value. So v_max
    # stays 1 (do not serve), gain=0, w=0. Proves non-monotonicity is handled.
    b = Episode("B", [Instant(2, 0.1, 0.9, 100), Instant(5, 0.2, 0.3, 100)],
                is_crash=False, ref=None, th_dev=TD, th_cloud=TC)
    rb = max_over_subsets(b)
    print("B nocrash-no-serve:", rb, "expect v_dev=1 v_max=1 gain=0 w=0")
    ok &= rb["v_dev"] == 1 and rb["v_max"] == 1 and rb["gain"] == 0 and rb["w"] == 0.0
    # Episode C: NO-CRASH where DEVICE false-alarms (d>=0.5) but CLOUD does not (c<0.5). Device-only
    # is WRONG (v_dev=0, false alarm); serving cloud on that instant SUPPRESSES the alarm -> v_max=1,
    # gain=1, w = that instant's work. Serving fixes a device false alarm.
    c = Episode("C", [Instant(2, 0.9, 0.1, 50), Instant(5, 0.2, 0.2, 50)],
                is_crash=False, ref=None, th_dev=TD, th_cloud=TC)
    rc = max_over_subsets(c)
    print("C nocrash-suppress:", rc, "expect v_dev=0 v_max=1 gain=1 w=50")
    ok &= rc["v_dev"] == 0 and rc["v_max"] == 1 and rc["gain"] == 1 and rc["w"] == 50.0
    # Episode D: min-work improving subset. CRASH ref=10; two pre-event cloud-only crossings, works
    # 30 and 70. Either alone detects -> min improving work is 30, not 100.
    d = Episode("D", [Instant(2, 0.1, 0.9, 70), Instant(4, 0.1, 0.9, 30),
                      Instant(12, 0.1, 0.1, 50)], is_crash=True, ref=10, th_dev=TD, th_cloud=TC)
    rd = max_over_subsets(d)
    print("D min-work:", rd, "expect v_dev=0 v_max=1 gain=1 w=30")
    ok &= rd["v_dev"] == 0 and rd["v_max"] == 1 and rd["gain"] == 1 and rd["w"] == 30.0
    # Episode E: already correct device-only crash (device crosses pre-event) -> gain 0, serving
    # cannot improve beyond 1.
    e = Episode("E", [Instant(3, 0.9, 0.9, 100), Instant(12, 0.1, 0.1, 100)],
                is_crash=True, ref=10, th_dev=TD, th_cloud=TC)
    re = max_over_subsets(e)
    print("E already-correct:", re, "expect v_dev=1 v_max=1 gain=0 w=0")
    ok &= re["v_dev"] == 1 and re["v_max"] == 1 and re["gain"] == 0 and re["w"] == 0.0
    print("DASHCAM MAX-OVER-SUBSETS UNIT TEST:", "PASS" if ok else "*** FAIL ***")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _unit_test() else 1)
