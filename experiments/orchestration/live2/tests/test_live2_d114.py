#!/usr/bin/env python3
"""D114: the EDF family releases from the head of the EDF order up to `c_inflight`.

User ruling 2026-11-18. The old rule released exactly ONE unit per 100 ms period across
monitoring and recall COMBINED (`first = order[0]`), a ceiling of 10 releases per second against
10.82 dashcam instants per second offered on the seed-10 trace, so the backlog was permanent by
construction and robot questions starved behind the nearer instant deadlines.

`c_inflight = 4` is StudyD7b Part A's smallest concurrency at which the 32B reaches 100 % GPU
utilisation. In-flight means submitted and not yet completed across all kinds, which is exactly
`obs.cloud.running_by_class`.
"""
from __future__ import annotations

import collections
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib"),
           str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                        # noqa: E402
import interface as I                                                   # noqa: E402
from test_live2_history_size import _run, _trace                        # noqa: E402

NET = I.NetworkState(connected=True, uplink_bps=13.6e6, rtt_s=0.05)
RELEASE_KINDS = ("release_monitor", "release_recall", "release_piece", "release_whole")


def _obs(n_streams: int, in_flight: int, now: float = 100.0) -> I.Observation:
    """`n_streams` monitoring instants pending, `in_flight` requests already out.

    The instants are given STRICTLY INCREASING deadlines through the D100 roster hook, so the
    deadline order is unambiguous and "in deadline order" is a real assertion rather than a
    tie broken by item_id.
    """
    streams = tuple(I.EpisodicStream(stream_id="cam%02d" % i, delivered_scores=(),
                                     delivered_times_s=(), cadence_s=0.5, frame_count=1,
                                     on_cloud=False, network=NET)
                    for i in range(n_streams))
    cloud = I.CloudState(queued_by_class=dict(recall=0, episodic=0),
                         running_by_class=dict(recall=in_flight, episodic=0),
                         gpu_kv_fraction=0.0, host_kv_fraction=0.0, gpu_warm_sessions=(),
                         host_warm_sessions=(), latency_estimate_s={})
    return I.Observation(now_s=now, epoch="tick", streams=streams, recall=(), cloud=cloud,
                         budget_remaining_gpu_s=1e9)


def _roster(n_streams: int, now: float = 100.0) -> dict:
    return {"sh_instant": {"cam%02d" % i: {"t_capture": now - 0.4 + 0.001 * i,
                                           "deadline_abs": now + 0.1 + 0.001 * i}
                           for i in range(n_streams)}}


def _released_streams(arm, obs) -> list:
    return [s.stream_id for s in arm.decide(obs).streams if s.mode == "cloud"]


class TestTheReleaseCount(unittest.TestCase):
    """Requirement 1 of the ruling, the three stated cells."""

    def _arm(self, n_streams, now=100.0):
        arm = A.Pi0Edf()
        arm.live2_roster(_roster(n_streams, now))
        arm._targets = {"dashcam": {"L_s": 0.5}}
        return arm

    def test_ten_pending_and_nothing_in_flight_releases_exactly_four(self):
        arm = self._arm(10)
        got = _released_streams(arm, _obs(10, 0))
        self.assertEqual(len(got), 4, "c_inflight=4 with 0 in flight must release 4, got %r" % got)

    def test_they_are_the_four_earliest_deadlines(self):
        arm = self._arm(10)
        got = _released_streams(arm, _obs(10, 0))
        self.assertEqual(sorted(got), ["cam00", "cam01", "cam02", "cam03"],
                         "the prefix must be the earliest deadlines, got %r" % got)

    def test_three_in_flight_releases_exactly_one(self):
        arm = self._arm(10)
        got = _released_streams(arm, _obs(10, 3))
        self.assertEqual(len(got), 1, "4 - 3 = 1 release, got %r" % got)
        self.assertEqual(got, ["cam00"], "and it must be the earliest deadline")

    def test_four_in_flight_releases_nothing(self):
        arm = self._arm(10)
        self.assertEqual(_released_streams(arm, _obs(10, 4)), [])

    def test_more_than_four_in_flight_releases_nothing_rather_than_going_negative(self):
        arm = self._arm(10)
        self.assertEqual(_released_streams(arm, _obs(10, 9)), [])
        self.assertEqual(arm._release_budget(_obs(10, 9)), 0)

    def test_in_flight_is_counted_across_all_kinds(self):
        """The ruling says across all kinds, so the two classes must both be charged."""
        arm = self._arm(10)
        o = _obs(10, 0)
        split = I.CloudState(queued_by_class=dict(recall=0, episodic=0),
                             running_by_class=dict(recall=2, episodic=1),
                             gpu_kv_fraction=0.0, host_kv_fraction=0.0, gpu_warm_sessions=(),
                             host_warm_sessions=(), latency_estimate_s={})
        o2 = I.Observation(now_s=o.now_s, epoch="tick", streams=o.streams, recall=(),
                           cloud=split, budget_remaining_gpu_s=1e9)
        self.assertEqual(arm._release_budget(o2), 1, "recall 2 + episodic 1 must charge 3 slots")

    def test_fewer_pending_than_the_budget_releases_only_what_is_pending(self):
        arm = self._arm(2)
        self.assertEqual(len(_released_streams(arm, _obs(2, 0))), 2)

    def test_the_old_one_per_epoch_rule_is_gone(self):
        self.assertFalse(A.Pi0Edf().releases_one_per_epoch)

    def test_c_inflight_is_a_parameter_and_reaches_the_run_header(self):
        self.assertEqual(A.Pi0Edf().c_inflight, 4)
        self.assertEqual(A.Pi0Edf().live2_describe()["c_inflight"], 4)
        arm = A.Pi0Edf(c_inflight=2)
        arm.live2_roster(_roster(10))
        arm._targets = {"dashcam": {"L_s": 0.5}}
        self.assertEqual(len(_released_streams(arm, _obs(10, 0))), 2)
        self.assertEqual(arm.live2_describe()["c_inflight"], 2)
        with self.assertRaises(ValueError):
            A.Pi0Edf(c_inflight=0)

    def test_the_piece_arms_carry_the_same_rule(self):
        for pt in (1024, 2048):
            arm = A.Pi0Edf(piece_tokens=pt)
            arm.live2_roster(_roster(10))
            arm._targets = {"dashcam": {"L_s": 0.5}}
            self.assertEqual(len(_released_streams(arm, _obs(10, 0))), 4, "edf-piece%d" % pt)
            self.assertEqual(arm.piece_tokens, pt, "piece size must be unchanged")


class TestTheCeilingIsGoneOnTheRealTrace(unittest.TestCase):
    """Requirements 2 and 3, on the seed-10 12-device fleet replay."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        tdir = _trace(d)
        co, _ = _run(tdir, d / "run", "edf")
        cls.rows = [json.loads(l) for l in open(d / "run" / "decision.jsonl")]
        per = collections.Counter()
        for r in cls.rows:
            if r["kind"] in RELEASE_KINDS:
                per[round(r["t"], 4)] += 1
        cls.per_period = sorted(per.values())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_more_than_one_unit_is_released_in_some_period(self):
        self.assertGreater(max(self.per_period), 1,
                           "the 10/s ceiling is still in place: max releases per period is 1")

    def test_no_period_exceeds_c_inflight(self):
        self.assertLessEqual(max(self.per_period), 4,
                             "a period released more than c_inflight=4 units")


if __name__ == "__main__":
    unittest.main(verbosity=2)
