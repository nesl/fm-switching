#!/usr/bin/env python3
"""D118: the two stronger baselines, `llf` and `vllm-priority`. BUILT AND IN NO RUN.

User decision 2026-11-18. They answer what the D114 replay invites a reviewer to ask: use
least-laxity rather than EDF and drop what can no longer make it, and isn't this just vLLM with
priority scheduling.

The laxity ordering test is the point of `llf`: at 17,581 tokens cold a recall's S_hat is about
4.48 s against a 5 s deadline, so its laxity is about 0.52 s, while a dashcam instant one second
out has S_hat 0.1422 s and laxity about 0.86 s. LLF releases the rebuild FIRST where EDF releases
the instant.
"""
from __future__ import annotations

import sys
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
import costs as C                                                       # noqa: E402
import interface as I                                                   # noqa: E402

NET = I.NetworkState(connected=True, uplink_bps=13.6e6, rtt_s=0.05)
NOW = 100.0
BIG = 17581          # robo002|s001's true cumulative history, from the history-size fix


def _stream(sid: str = "cam00") -> I.EpisodicStream:
    return I.EpisodicStream(stream_id=sid, delivered_scores=(), delivered_times_s=(),
                            cadence_s=0.5, frame_count=1, on_cloud=False, network=NET)


def _recall(qid: str, tokens: int, readiness: str, deadline_abs: float,
            session: str = "robo002|s001") -> I.RecallQuery:
    ev = (I.EvidenceItem("D2", "gpu" if readiness == "GPU-WARM" else "device", tokens,
                         tokens * 4),)
    return I.RecallQuery(query_id=qid, session_id=session, category="recall", arrival_s=NOW - 0.1,
                         deadline_s=deadline_abs, evidence=ev, readiness=readiness,
                         readiness_tokens=tokens)


def _obs(streams, recall, in_flight: int = 0) -> I.Observation:
    cloud = I.CloudState(queued_by_class=dict(recall=0, episodic=0),
                         running_by_class=dict(recall=in_flight, episodic=0),
                         gpu_kv_fraction=0.0, host_kv_fraction=0.0, gpu_warm_sessions=(),
                         host_warm_sessions=(), latency_estimate_s={})
    return I.Observation(now_s=NOW, epoch="tick", streams=tuple(streams), recall=tuple(recall),
                         cloud=cloud, budget_remaining_gpu_s=1e9)


def _arm(cls=A.LlfArm, **kw):
    a = cls(**kw) if kw else cls()
    a._targets = {"dashcam": {"L_s": 1.0}}
    return a


def _roster(ids, deadline_abs):
    return {"sh_instant": {i: {"t_capture": NOW - 0.4, "deadline_abs": deadline_abs}
                           for i in ids}}


class TestLlfLaxityOrdering(unittest.TestCase):
    """The reviewer's question: does least-laxity actually reorder against EDF?"""

    def test_a_long_cold_recall_beats_an_earlier_deadline_instant(self):
        arm = _arm()
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        act = arm.decide(_obs([_stream()], [q],
                      in_flight=A.Pi0Edf.C_INFLIGHT_DEFAULT - 1))  # exactly ONE slot
        on = [s.stream_id for s in act.streams if s.mode == "cloud"]
        took = [r.query_id for r in act.recall if r.decision == "CLOUD"]
        self.assertEqual(took, ["q1"], "the cold rebuild must take the only slot under LLF")
        self.assertEqual(on, [], "the instant must NOT be released, though its deadline is nearer")

    def test_edf_makes_the_opposite_choice_on_the_same_input(self):
        """The contrast is the whole point, so it is asserted rather than described."""
        arm = _arm(A.Pi0Edf)
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        act = arm.decide(_obs([_stream()], [q],
                      in_flight=A.Pi0Edf.C_INFLIGHT_DEFAULT - 1))  # exactly ONE slot
        on = [s.stream_id for s in act.streams if s.mode == "cloud"]
        self.assertEqual(on, ["cam00"], "EDF must pick the nearer deadline, which is the instant")

    def test_the_laxities_are_the_registered_numbers(self):
        arm = _arm()
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        items = {p.item_id: p for p in arm._pending_items(_obs([_stream()], [q]))}
        s_rc = arm.s_hat_s(items["rc:q1"])
        s_mon = arm.s_hat_s(items["mon:cam00"])
        self.assertAlmostEqual(s_mon, 0.1422, places=4)
        self.assertAlmostEqual(s_rc, C.recall_ttft_s(BIG, "COLD")
                               + C.recall_ttft_s(BIG, "GPU-WARM"), places=9)
        self.assertLess(arm.laxity_s(items["rc:q1"], NOW),
                        arm.laxity_s(items["mon:cam00"], NOW))

    def test_a_warm_recall_is_priced_by_its_committed_reload_curve(self):
        arm = _arm()
        for readiness in ("GPU-WARM", "HOST-WARM"):
            q = _recall("q1", BIG, readiness, NOW + 5.0)
            p = {x.item_id: x for x in arm._pending_items(_obs([], [q]))}["rc:q1"]
            self.assertAlmostEqual(arm.s_hat_s(p), C.recall_ttft_s(BIG, readiness), places=9,
                                   msg=readiness)

    def test_the_cold_estimate_does_not_double_count_the_prefill(self):
        """`recall_ttft_s(t, COLD)` IS the prefill, so a COLD answer term would charge it twice."""
        arm = _arm()
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        p = {x.item_id: x for x in arm._pending_items(_obs([], [q]))}["rc:q1"]
        # The nearest COMMITTED size to 17,581 is 11k, so the committed rate is 4,500 tok/s,
        # not the 28k row's 3,800. Asserted against the table rather than a guess.
        rate = C.COLD_PREFILL_TOK_S[C._nearest_size(BIG)]
        self.assertEqual(rate, 4500.0)
        self.assertAlmostEqual(C.recall_ttft_s(BIG, "COLD"), BIG / rate, places=9)
        self.assertLess(arm.s_hat_s(p), 2 * C.recall_ttft_s(BIG, "COLD"))


class TestLlfSkipRule(unittest.TestCase):
    def test_a_negative_laxity_unit_is_skipped_and_counted(self):
        arm = _arm()
        # 0.2 s left for a 4.48 s job: laxity is far below zero.
        q = _recall("q1", BIG, "COLD", NOW + 0.2)
        act = arm.decide(_obs([], [q]))
        modes = [r.decision for r in act.recall]
        self.assertEqual(modes, ["DEVICE"], "a hopeless unit falls to the device")
        self.assertEqual(arm.stats["skipped_total"], 1)
        self.assertEqual(arm.stats["skips_by_kind"], {"rc_piece": 1})

    def test_a_skipped_instant_is_counted_under_its_own_kind(self):
        arm = _arm()
        arm.live2_roster(_roster(["cam00"], NOW - 1.0))     # deadline already past
        act = arm.decide(_obs([_stream()], []))
        self.assertEqual([s.mode for s in act.streams], ["local"])
        self.assertEqual(arm.stats["skips_by_kind"], {"episode_call": 1})

    def test_a_feasible_unit_is_not_skipped(self):
        arm = _arm()
        q = _recall("q1", BIG, "GPU-WARM", NOW + 5.0)
        act = arm.decide(_obs([], [q]))
        self.assertEqual([r.decision for r in act.recall], ["CLOUD"])
        self.assertEqual(arm.stats["skipped_total"], 0)

    def test_a_skipped_unit_does_not_consume_a_release_slot(self):
        arm = _arm()
        arm.live2_roster(_roster(["cam00"], NOW - 1.0))
        q = _recall("q1", BIG, "GPU-WARM", NOW + 5.0)
        act = arm.decide(_obs([_stream()], [q],
                      in_flight=A.Pi0Edf.C_INFLIGHT_DEFAULT - 1))  # exactly ONE slot
        self.assertEqual([r.decision for r in act.recall], ["CLOUD"],
                         "the one slot must go to the feasible unit, not be eaten by the skip")


class TestLlfKeepsTheD114Bound(unittest.TestCase):
    def _many(self, n, in_flight):
        arm = _arm()
        ids = ["cam%02d" % i for i in range(n)]
        arm.live2_roster({"sh_instant": {i: {"t_capture": NOW - 0.4,
                                             "deadline_abs": NOW + 1.0 + 0.001 * k}
                                         for k, i in enumerate(ids)}})
        act = arm.decide(_obs([_stream(i) for i in ids], [], in_flight=in_flight))
        return [s.stream_id for s in act.streams if s.mode == "cloud"]

    # D128 moved the DEFAULT bound from 4 to 8, and `LlfArm` subclasses `Pi0Edf` so it INHERITED
    # that change. These cells are written against the committed default, with the bound of 4
    # kept under explicit parameterised coverage below. The D118 rule, that llf keeps the D114
    # release bound, is what is being tested and it is unchanged.
    C = A.Pi0Edf.C_INFLIGHT_DEFAULT

    def test_nothing_in_flight_releases_exactly_c_inflight(self):
        self.assertEqual(len(self._many(12, 0)), self.C)

    def test_one_short_of_the_bound_releases_exactly_one(self):
        self.assertEqual(len(self._many(12, self.C - 1)), 1)

    def test_at_the_bound_releases_nothing(self):
        self.assertEqual(self._many(12, self.C), [])

    def test_the_old_bound_of_four_is_still_reachable_by_parameter(self):
        arm = A.make_arm("llf", c_inflight=4)
        self.assertEqual(arm.c_inflight, 4)
        self.assertEqual(arm.live2_describe()["c_inflight"], 4)
        self.assertEqual(arm.stats["c_inflight"], 4)

    def test_c_inflight_reaches_the_run_header(self):
        self.assertEqual(A.make_arm("llf").live2_describe()["c_inflight"], self.C)
        self.assertEqual(A.make_arm("llf").stats["c_inflight"], self.C)


class TestLlfUsesCommittedCurvesOnly(unittest.TestCase):
    def test_s_hat_reads_the_committed_costs_module_and_not_the_policy(self):
        """D74: the policy's cost model, engine model and rollout must never price a baseline."""
        import inspect
        src = inspect.getsource(A.LlfArm.s_hat_s)
        self.assertIn("import costs as C", src)
        for banned in ("eng1", "Eng1Engine", "profiles", "pol4", "Rollout", "rollout",
                       "cost_model", "state_value"):
            self.assertNotIn(banned, src, "s_hat must not reach for %r" % banned)
        self.assertEqual(A.make_arm("llf").stats["s_hat_source"], "baselines/costs.py")

    def test_the_curves_it_uses_carry_committed_provenance(self):
        self.assertIn("StudyRH5", C.SOURCES["RECALL_TTFT_S"])
        self.assertIn("StudyD7", C.SOURCES["CLOUD_TTFT"])


class TestVllmPriority(unittest.TestCase):
    def _arm(self, mode="priority", has_backend=False):
        a = A.make_arm("vllm-priority")
        a.live2_configure(gpu_kv_tokens=1, host_tier_gib=1.0, host_tier_tokens=1,
                          targets={"dashcam": {"L_s": 1.0}},
                          server_scheduling_policy=mode, has_backend=has_backend)
        return a

    def test_every_action_carries_an_integer_priority_equal_to_its_deadline(self):
        arm = self._arm()
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        act = arm.decide(_obs([_stream()], [q]))
        pri = act.notes["priority_ms"]
        self.assertEqual(pri["mon:cam00"], int(round((NOW + 1.0) * 1000)))
        self.assertEqual(pri["rc:q1"], int(round((NOW + 5.0) * 1000)))
        for v in pri.values():
            self.assertIsInstance(v, int)
        self.assertEqual(act.order, "ENGINE-PRIORITY")

    def test_lower_value_is_the_nearer_deadline(self):
        arm = self._arm()
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        q = _recall("q1", BIG, "COLD", NOW + 5.0)
        pri = arm.decide(_obs([_stream()], [q])).notes["priority_ms"]
        self.assertLess(pri["mon:cam00"], pri["rc:q1"])

    def test_release_is_identical_to_always_cloud_fcfs(self):
        arm = self._arm()
        plain = A.make_arm("always-cloud-fcfs")
        arm.live2_roster(_roster(["cam00", "cam01"], NOW + 1.0))
        obs = _obs([_stream("cam00"), _stream("cam01")], [_recall("q1", BIG, "COLD", NOW + 5.0)])
        a, b = arm.decide(obs), plain.decide(obs)
        self.assertEqual([(s.stream_id, s.mode) for s in a.streams],
                         [(s.stream_id, s.mode) for s in b.streams])
        self.assertEqual([(r.query_id, r.decision) for r in a.recall],
                         [(r.query_id, r.decision) for r in b.recall])

    def test_it_refuses_to_run_when_the_server_is_declared_fcfs(self):
        arm = self._arm(mode="fcfs")
        with self.assertRaises(RuntimeError) as cm:
            arm.decide(_obs([_stream()], []))
        self.assertIn("priority", str(cm.exception))

    def test_it_refuses_when_a_backend_is_attached_but_nothing_is_declared(self):
        arm = self._arm(mode=None, has_backend=True)
        with self.assertRaises(RuntimeError):
            arm.decide(_obs([_stream()], []))

    def test_an_undeclared_dry_run_proceeds_but_is_stamped(self):
        arm = self._arm(mode=None, has_backend=False)
        arm.live2_roster(_roster(["cam00"], NOW + 1.0))
        arm.decide(_obs([_stream()], []))
        self.assertTrue(arm.stats["server_mode_undeclared"])
        self.assertIsNone(arm.live2_describe()["server_scheduling_policy"])

    def test_the_declared_mode_reaches_the_run_header(self):
        self.assertEqual(self._arm().live2_describe()["server_scheduling_policy"], "priority")
        self.assertEqual(self._arm().live2_describe()["requires_server_mode"], "priority")


class TestNeitherArmIsInTheRoundOneList(unittest.TestCase):
    """D118: built and in NO run until the user decides."""

    def test_the_round_one_list_still_has_eight_arms(self):
        self.assertEqual(len(A.ROUND1_ARM_NAMES), 8)
        for n in ("llf", "vllm-priority"):
            self.assertNotIn(n, A.ROUND1_ARM_NAMES)

    def test_both_are_buildable(self):
        for n in ("llf", "vllm-priority"):
            self.assertIn(n, A.ARM_NAMES)
            self.assertIsNotNone(A.make_arm(n))

    def test_the_scorer_still_names_exactly_seven_gpu_baselines(self):
        sys.path.insert(0, str(LIVE2 / "scorer"))
        import score as SC
        self.assertEqual(len(SC.GPU_BASELINES), 7)
        for n in ("llf", "vllm-priority"):
            self.assertNotIn(n, SC.GPU_BASELINES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
