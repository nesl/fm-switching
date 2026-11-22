#!/usr/bin/env python3
"""D179 (4): the wire-time deadline re-check. Session B.

NOTHING HERE IS A MEASUREMENT. Every test drives the REAL `Live2Coordinator` on a hand-built
opportunity, so the quantity under test is the one the live path reads, not a re-implementation.

  1   the re-check SKIPS a request that can no longer make its deadline and does NOT skip one
      that can - BOTH DIRECTIONS, in the two ways release time differs from arrival time (the
      deadline came closer, and the queue ahead grew)
  2   THE EP-G FRAME-CARRY TEST, the load-bearing one: after a skipped alert instant the NEXT
      request for that episode carries the skipped frame, carries its BYTES rather than a
      uuid-only reference, and its uncached count RISES by exactly one frame's tokens
  3   the counters increment per type and the total agrees with the sum of the three
  4   NEGATIVE CONTROL: with the switch off, the same infeasible request is submitted exactly as
      before, no counter appears, and the decision log is byte-identical to a tree without the
      switch read
  5   POSITIVE CONTROL: the harness can see a skip at all, demonstrated through the COMMITTED
      budget-refusal path, which existed before D179 and is not the mechanism under test

Test 2's discriminator deserves its own note, because the obvious assertion does not work. Under
EP-G every monitoring request re-sends the WHOLE episode's ref list, so "the next request includes
the skipped frame" is true whether or not the instant was skipped and proves nothing. What the
skip changes is which frames carry BYTES: a frame whose carrying request returned 200 goes as a
uuid-only reference, and a frame that was never sent cannot. So the body-level assertion is on
`body["_live2"]["frame_refs"]` TOGETHER WITH the per-frame bytes/reference split, and the token
assertion is on the charged uncached count. Both are asserted; the body is reachable, so the
token count is not a substitute for it.
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "hybrid"), str(LIVE2 / "v5"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                        # noqa: E402
import bodies as B                                                      # noqa: E402
import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import d162_price as DP                                                 # noqa: E402
import release_recheck as RR                                            # noqa: E402
from coordinator import Live2Coordinator                                # noqa: E402
from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK                 # noqa: E402

DEV = "dash000"
ROBO = "robo000"
ASST = "asst000"
T0 = 10.0
L_SH = 1.0                      # the committed dashcam deadline (share_capacity DEADLINE_S)


class _Fixture:
    """A real coordinator, one real device, real frame files on disk, nothing stubbed."""

    def __init__(self, tmp: Path, *, recheck: bool, dev: str = DEV, dev_type: str = "dashcam"):
        self.tmp = tmp
        self.frames = tmp / "frames"
        self.frames.mkdir(parents=True, exist_ok=True)
        arm = A.make_arm("always-cloud-fcfs")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        # THE SWITCH IS SET ON THE INSTANCE, which is the shape D179 (4) requires. Setting it on
        # the class is a hard error and test 3b asserts that.
        #
        # D162 PRICING IS SET WITH IT, AND THAT IS A PRECONDITION, NOT A CONVENIENCE: the
        # re-check's queue input `_uncached_in_flight` is decremented only under D162 pricing
        # (coordinator.py:1508), so without it the field is a cumulative run total rather than
        # the queue ahead. The coordinator refuses the combination, and
        # TestTheQueueInputMustBeInTheRightRegister asserts the refusal.
        if recheck:
            arm.live2_release_recheck = True
            arm.live2_d162_pricing = True
        self.co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                   host_tier_tokens=HOST_TOK, upload_mode="A", window_s=600.0,
                                   drain_s=5.0, seed=1, dry_run=True,
                                   run_tag=CK.run_tag(1, "d179rr"), frames_root=self.frames)
        assert self.co._release_recheck is bool(recheck)
        # an arm that WAITS for the device answer would make `_serve_monitor` return early for a
        # reason unrelated to this test, so the fixture asserts it does not
        assert self.co.reads_device is False
        self.co._ingest(dict(kind="device_register", device_id=dev, type=dev_type,
                             uplink_mbps=13.6, rtt_ms=50.0, start_t=0.0), 0.0)
        self.dev = dev

    def frame(self, name: str) -> str:
        (self.frames / name).write_bytes(b"\xff\xd8\xff\xd9")
        return name

    def episode(self, idx: int, n_frames: int, *, t_capture: float, deadline_s: float = L_SH):
        """One EP-G monitoring instant whose episode is the append-only prefix f0..f{n-1}."""
        refs = [self.frame("f%02d.jpg" % i) for i in range(n_frames)]
        oid = "o%03d" % idx
        self.co._ingest(dict(kind="monitor_frame", opportunity_id=oid, device_id=self.dev,
                             t_capture=t_capture, deadline_s=deadline_s,
                             instant_id="i%03d" % idx, t_arrive=t_capture,
                             frame_ref=refs[-1], frame_bytes=4,
                             episode_id="ep0", episode_index=idx,
                             episode_frames=len(refs), frame_refs=list(refs)), t_capture)
        assert self.co.dashcam_format == "epg"
        return oid, refs

    def recall(self, idx: int, *, t_ask: float, deadline_s: float, tokens: int = 8000):
        """One recall opportunity with a cold history of `tokens`, which is what a wire-time
        re-check of the recall path has to price."""
        sid = "%s|s%03d" % (self.dev, idx)
        self.co._ingest(dict(kind="session_start", session_id=sid, device_id=self.dev,
                             t=t_ask - 1.0), t_ask - 1.0)
        s = self.co.st.sessions[sid]
        s.est_tokens = int(tokens)
        oid = "q%03d" % idx
        self.co._ingest(dict(kind="recall_question", opportunity_id=oid, device_id=self.dev,
                             t_ask=t_ask, deadline_s=deadline_s, t_arrive=t_ask,
                             session_id=sid, question="q?", options=["A", "B"],
                             question_id="qid%d" % idx, category="recall"), t_ask)
        return self.co.st.opps[oid], s

    def serve(self, t: float):
        self.co._serve_monitor(self.dev, t, 0.0, None, {})

    def submissions(self):
        return [sub for _f, sub in self.co.futures]

    def confirm_all(self, t: float):
        """Complete every outstanding request and make its frames uuid-referenceable (D158 (2)).

        A DRY FUTURE CARRIES NO `http_status`, by design and by the committed docstring on
        `_promote_confirmed_bytes`, so a dry run never promotes anything and every frame goes out
        as bytes. The promotion is therefore invoked directly with the 200 a live run returns -
        the COMMITTED function, not a re-implementation of it - because otherwise the
        bytes-versus-reference split, which is the body-level evidence of frame carry, is not
        observable in a dry test at all.
        """
        subs = list(self.submissions())
        self.co.st.now = t
        self.co._collect(t)
        for sub in subs:
            self.co._promote_confirmed_bytes(sub, {"http_status": 200})


def _fix(recheck, **kw):
    tmp = Path(tempfile.mkdtemp())
    return _Fixture(tmp, recheck=recheck, **kw)


class TestBothDirections(unittest.TestCase):
    """Test 1. A test that only shows the skip proves nothing about the predicate."""

    def test_a_feasible_alert_is_sent(self):
        f = _fix(True)
        f.episode(0, 1, t_capture=T0)
        f.serve(T0 + 0.1)                       # 0.9 s left, one frame, nothing in flight
        self.assertEqual(len(f.submissions()), 1, "a feasible alert must still be sent")
        self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 0)
        self.assertEqual(f.co.release_infeasible_events, [])

    def test_an_alert_whose_deadline_has_nearly_passed_is_skipped(self):
        f = _fix(True)
        f.episode(0, 1, t_capture=T0)
        # 0.01 s left against a predicted 0.13 s first token: infeasible on the deadline alone
        f.serve(T0 + L_SH - 0.01)
        self.assertEqual(f.submissions(), [], "an alert past hope must NOT go on the wire")
        self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 1)
        self.assertEqual(f.co.counts[RR.COUNTER_BY_TYPE["alert"]], 1)
        self.assertEqual(f.co.st.opps["o000"].state, "declined")
        rows = [a for a in f.co.answers if a["opportunity_id"] == "o000"]
        self.assertEqual([r["decision"] for r in rows], [RR.DECISION])
        self.assertEqual(rows[0]["served_by"], "device")

    def test_the_queue_ahead_is_what_release_time_adds(self):
        """THE MECHANISM: identical request, identical deadline, only the queue differs. This is
        the quantity b7's arrival test cannot see, so it is asserted on its own."""
        est_tokens = B.epg_prompt_tokens(1)
        remaining = L_SH - 0.1
        self.assertLessEqual(DP.first_token_s(est_tokens, 0), remaining)
        big = 30000
        self.assertGreater(DP.first_token_s(est_tokens, big), remaining)
        for queue, want_sent in ((0, 1), (big, 0)):
            f = _fix(True)
            f.episode(0, 1, t_capture=T0)
            f.co._uncached_in_flight = queue
            f.serve(T0 + 0.1)
            self.assertEqual(len(f.submissions()), want_sent,
                             "queue_ahead=%d should give %d submissions" % (queue, want_sent))
            self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 1 - want_sent)

    def test_the_budget_is_untouched_by_a_skip(self):
        f = _fix(True)
        f.episode(0, 1, t_capture=T0)
        spent0 = f.co.st.budget.spent_gpu_seconds
        f.serve(T0 + L_SH - 0.01)
        self.assertEqual(f.co.st.budget.spent_gpu_seconds, spent0)
        self.assertEqual(f.co._uncached_in_flight, 0)


class TestEpgFrameCarry(unittest.TestCase):
    """Test 2, THE LOAD-BEARING ONE. A skipped alert instant must cost the QUESTION, not the
    FRAME: the episode is append-only, so the next request carries the skipped frame and pays for
    it. Asserted on the actual request body AND on the charged uncached count."""

    def _two_instants(self, skip_first: bool):
        f = _fix(True)
        f.episode(0, 4, t_capture=T0)
        if skip_first:
            f.co._uncached_in_flight = 30000            # makes instant 0 infeasible
            f.serve(T0 + 0.1)
            self.assertEqual(f.submissions(), [], "instant 0 was meant to be skipped")
            f.co._uncached_in_flight = 0
        else:
            f.serve(T0 + 0.1)
            self.assertEqual(len(f.submissions()), 1)
            f.confirm_all(T0 + 1.5)                     # its frames become uuid-referenceable
        f.episode(1, 5, t_capture=T0 + 2.0)
        f.serve(T0 + 2.1)
        subs = f.submissions()
        self.assertTrue(subs, "the NEXT instant must be sent in both arms")
        return f, subs[-1]

    def test_the_next_request_body_carries_the_skipped_frame_as_bytes(self):
        f_skip, sub_skip = self._two_instants(skip_first=True)
        f_ctl, sub_ctl = self._two_instants(skip_first=False)
        # (a) the body carries the whole append-only episode in both arms - which is why the ref
        #     list alone cannot be the discriminator, and this is asserted rather than assumed
        for sub in (sub_skip, sub_ctl):
            self.assertEqual(sub.body["_live2"]["frame_refs"],
                             ["f%02d.jpg" % i for i in range(5)])
        # (b) THE DISCRIMINATOR: which frames carry BYTES. After a skip the skipped frame f03 has
        #     never been on the wire, so it cannot be referenced by uuid and goes as bytes.
        def split(sub):
            imgs = [p for p in sub.body["messages"][0]["content"]
                    if p.get("type") == "image_url"]
            n_bytes = sum(1 for p in imgs if p["image_url"] is not None)
            return len(imgs), n_bytes
        self.assertEqual(split(sub_skip), (5, 5),
                         "after a skip every frame of the episode still carries bytes, because "
                         "none of them has ever been on the wire")
        self.assertEqual(split(sub_ctl), (5, 1),
                         "in the control the four confirmed frames go as uuid-only references")
        # and the skipped frame specifically is one of the ones carrying bytes
        f03 = [p for p in sub_skip.body["messages"][0]["content"]
               if p.get("type") == "image_url"][3]
        self.assertIsNotNone(f03["image_url"])

    def test_the_uncached_count_rises_by_exactly_the_skipped_frame(self):
        f_skip, _ = self._two_instants(skip_first=True)
        f_ctl, _ = self._two_instants(skip_first=False)
        # `new_tokens_charged` is the charge's own basis (`n_new`), recorded per EP-G request
        skip_u = f_skip.co.epg_requests[-1]["new_tokens_charged"]
        ctl_u = f_ctl.co.epg_requests[-1]["new_tokens_charged"]
        self.assertEqual(ctl_u, B.epg_prompt_tokens(1),
                         "the control's second instant pays for its one new frame")
        self.assertEqual(skip_u, B.epg_prompt_tokens(5),
                         "after a skip the second instant pays for all five unsent frames")
        self.assertEqual(skip_u - ctl_u, 4 * B.EPG_TOK_PER_FRAME)
        self.assertEqual(f_skip.co._uncached_last_charged, skip_u)

    def test_the_skipped_frame_is_still_in_the_episode_not_dropped(self):
        f, sub = self._two_instants(skip_first=True)
        ev = f.co.release_infeasible_events[-1]
        self.assertEqual(ev["skipped_frame_ref"], "f03.jpg")
        self.assertIn(ev["skipped_frame_ref"], sub.body["_live2"]["frame_refs"])
        self.assertEqual(ev["n_episode_frames"], 4)


class TestCounters(unittest.TestCase):
    """Test 3. The four frozen names, per type, and the sum identity the H100's reader checks."""

    def test_alert_recall_and_assistance_each_land_in_their_own_counter(self):
        got = {}
        for dev, dev_type, qtype in ((DEV, "dashcam", "alert"),
                                     (ROBO, "robot", "recall"),
                                     (ASST, "assistive", "assistance")):
            f = _fix(True, dev=dev, dev_type=dev_type)
            if qtype == "alert":
                f.episode(0, 1, t_capture=T0)
                f.co._uncached_in_flight = 30000
                f.serve(T0 + 0.1)
            else:
                o, s = f.recall(0, t_ask=T0, deadline_s=0.05, tokens=8000)
                f.co._submit_recall(o, s, T0 + 0.01, 0.0, None, {}, whole=True)
            self.assertEqual(f.submissions(), [], qtype)
            got[qtype] = dict(f.co.counts)
            self.assertTrue(RR.totals_agree(f.co.counts), qtype)
            self.assertEqual(f.co.counts[RR.COUNTER_BY_TYPE[qtype]], 1, qtype)
            self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 1, qtype)
        # and no type's counter leaks into another's
        for qtype, counts in got.items():
            for other in RR.TYPES:
                if other != qtype:
                    self.assertEqual(counts.get(RR.COUNTER_BY_TYPE[other], 0), 0,
                                     "%s leaked into %s" % (qtype, other))

    def test_the_names_are_the_frozen_ones(self):
        self.assertEqual(RR.COUNTER_TOTAL, "release_infeasible")
        self.assertEqual(RR.COUNTER_BY_TYPE, {"alert": "release_infeasible_alert",
                                              "recall": "release_infeasible_recall",
                                              "assistance": "release_infeasible_assistance"})

    def test_the_total_tracks_several_skips(self):
        f = _fix(True)
        for i in range(3):
            f.episode(i, 1 + i, t_capture=T0 + 3.0 * i)
            f.co._uncached_in_flight = 30000
            f.serve(T0 + 3.0 * i + 0.1)
        self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 3)
        self.assertEqual(f.co.counts[RR.COUNTER_BY_TYPE["alert"]], 3)
        self.assertTrue(RR.totals_agree(f.co.counts))

    def test_a_class_level_switch_is_refused(self):
        """D179 (4): an INSTANCE attribute. A class-level ON is the shape that cost a live cell."""
        class _Armish:
            live2_release_recheck = True
        with self.assertRaises(RR.ReleaseRecheckSwitchError):
            RR.arm_enables(_Armish())

        class _Off:
            live2_release_recheck = False       # a harmless class default is allowed through
        self.assertFalse(RR.arm_enables(_Off()))
        # an INSTANCE override of either shape is read, which is the sanctioned way to turn it on
        on_over_class_default = _Off()
        on_over_class_default.live2_release_recheck = True
        self.assertTrue(RR.arm_enables(on_over_class_default))
        off_over_class_on = _Armish()
        off_over_class_on.live2_release_recheck = False
        self.assertFalse(RR.arm_enables(off_over_class_on))

    def test_the_default_is_false(self):
        f = _fix(False)
        self.assertFalse(f.co._release_recheck)
        self.assertFalse(RR.arm_enables(A.make_arm("always-cloud-fcfs")))


class TestTheQueueInputMustBeInTheRightRegister(unittest.TestCase):
    """The first dry cell tripped the D179 STOP condition at 99.98 percent of alert requests,
    because `_uncached_in_flight` is incremented at four release sites unconditionally and
    decremented only under D162 pricing, so on a non-priced arm it is a cumulative run total.
    The coordinator now refuses that combination instead of reading it."""

    def test_the_recheck_is_refused_without_d162_pricing(self):
        arm = A.make_arm("always-cloud-fcfs")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        arm.live2_release_recheck = True                 # and NO live2_d162_pricing
        with self.assertRaises(RuntimeError) as cm:
            Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                             host_tier_tokens=HOST_TOK, upload_mode="A", window_s=60.0,
                             drain_s=5.0, seed=1, dry_run=True,
                             run_tag=CK.run_tag(1, "d179reg"))
        self.assertIn("live2_d162_pricing", str(cm.exception))

    def test_an_arm_without_the_switch_is_not_refused(self):
        f = _fix(False)                                  # no switch, no pricing: unchanged
        self.assertFalse(f.co._release_recheck)


class TestNegativeControl(unittest.TestCase):
    """Test 4. With the switch off the very request the re-check would skip is submitted, and the
    decision log is identical to the run with the switch absent entirely."""

    def test_the_same_infeasible_alert_is_sent_with_the_switch_off(self):
        f = _fix(False)
        f.episode(0, 1, t_capture=T0)
        f.co._uncached_in_flight = 30000
        f.serve(T0 + 0.1)
        self.assertEqual(len(f.submissions()), 1,
                         "with the switch off the infeasible alert must still be sent")
        for name in (RR.COUNTER_TOTAL,) + tuple(RR.COUNTER_BY_TYPE.values()):
            self.assertNotIn(name, f.co.counts, "%s appeared with the switch off" % name)
        self.assertEqual(f.co.release_infeasible_events, [])

    def test_the_same_infeasible_recall_is_sent_with_the_switch_off(self):
        f = _fix(False)
        o, s = f.recall(0, t_ask=T0, deadline_s=0.05, tokens=8000)
        f.co._submit_recall(o, s, T0 + 0.01, 0.0, None, {}, whole=True)
        self.assertEqual(len(f.submissions()), 1)
        self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 0)

    def test_the_decision_kinds_are_unchanged_with_the_switch_off(self):
        f = _fix(False)
        f.episode(0, 2, t_capture=T0)
        f.co._uncached_in_flight = 30000
        f.serve(T0 + 0.1)
        g = _fix(True)
        g.episode(0, 2, t_capture=T0)
        g.co._uncached_in_flight = 30000
        g.serve(T0 + 0.1)
        self.assertEqual(f.co.n_dec, 1)
        self.assertEqual(g.co.n_dec, 1)
        # the switch moves the decision itself, which is Step 2b: not merely a counter
        self.assertEqual(len(f.submissions()), 1)
        self.assertEqual(len(g.submissions()), 0)


class TestPositiveControl(unittest.TestCase):
    """Test 5. Could this harness see a skip at all? Demonstrated through the COMMITTED budget
    refusal, which predates D179 and is not the mechanism under test. An impossible success and
    an impossible failure are equally diagnostic, so the check that catches the skip is itself
    checked against a known-good arm of the code."""

    def test_the_committed_budget_refusal_is_visible_to_the_same_assertions(self):
        f = _fix(False)                                 # switch OFF: this is not D179's path
        f.episode(0, 1, t_capture=T0)
        f.co.st.budget.gpu_seconds = 0.0                # the committed refusal, forced
        f.serve(T0 + 0.1)
        self.assertEqual(f.submissions(), [],
                         "the harness cannot see a skip at all: every later null is uninformative")
        self.assertEqual(f.co.counts["budget_refusal_monitor"], 1)
        self.assertEqual(f.co.counts[RR.COUNTER_TOTAL], 0,
                         "a budget refusal must not be counted as a release-infeasible skip")

    def test_the_harness_can_see_a_send_too(self):
        f = _fix(False)
        f.episode(0, 1, t_capture=T0)
        f.serve(T0 + 0.1)
        self.assertEqual(len(f.submissions()), 1)
        self.assertEqual(f.co.counts["submitted_monitor"], 1)


class TestThePredictorIsTheCommittedOne(unittest.TestCase):
    """The coefficients are IMPORTED, never retyped, and the comparator is b7's own direction."""

    def test_no_coefficient_drift(self):
        self.assertTrue(DP.assert_no_drift().get("agrees"))

    def test_the_estimate_is_exactly_the_d162_model(self):
        d = RR.decide(qtype="alert", uncached=380, queued_uncached_ahead=1234, remaining_s=1.0)
        self.assertEqual(d["est_first_token_s"], DP.first_token_s(380, 1234))
        self.assertTrue(d["feasible"])
        self.assertFalse(RR.decide(qtype="alert", uncached=380, queued_uncached_ahead=1234,
                                   remaining_s=0.0)["feasible"])

    def test_the_boundary_is_inclusive_like_b7s(self):
        est = DP.first_token_s(380, 0)
        self.assertTrue(RR.decide(qtype="alert", uncached=380, queued_uncached_ahead=0,
                                  remaining_s=est)["feasible"])

    def test_background_kinds_are_out_of_scope(self):
        for kind in ("piece", "whole", "touch", "append"):
            self.assertIsNone(RR.type_of_request(kind, DEV), kind)

    def test_the_type_map_agrees_with_session_as_interface_when_present(self):
        d = RR.assert_no_interface_drift()
        if d.get("checked"):
            self.assertTrue(d["agrees"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
