#!/usr/bin/env python3
"""Unit tests for the link_ line (link_events, link_sync, E1). CPU only. Run: python test_link_events.py

Covers: DeviceLink/Observation validation and scrub, the link table's refusals, the wire kinds'
lockstep between schema.py and fleet/events.py, the E1 placement refusals, the emulator's backlog
counts, held-backlog token conservation (believed total == capture total after a full release and
less by exactly the held tokens while held), class-level switch refusals, and the read site.
"""
import sys
import unittest
from pathlib import Path

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L.parent / "baselines", L.parent / "sim"):
    sys.path.insert(0, str(p))

import interface as I                                                      # noqa: E402
import schema as SC                                                        # noqa: E402
import events as EV                                                        # noqa: E402
import cstate as CS                                                        # noqa: E402
import link_read as LR                                                     # noqa: E402
import link_sync as LS                                                     # noqa: E402


def _obs(links, now=100.0):
    cloud = I.CloudState({}, {}, 0.0, 0.0, (), (), {})
    return I.Observation(now_s=now, epoch="connectivity_change", streams=(), recall=(), cloud=cloud,
                         budget_remaining_gpu_s=0.0, device_links=tuple(links))


class TestObservation(unittest.TestCase):
    def test_valid_and_scrub(self):
        o = _obs([I.DeviceLink("r1", False, offline_since=50.0),
                  I.DeviceLink("r2", True, 10.0, 20.0, 60, 5400)])
        I.scrub(o)

    def test_future_instant_refused(self):
        with self.assertRaises(ValueError):
            _obs([I.DeviceLink("r1", True, 10.0, 120.0, 1, 90)], now=100.0)

    def test_offline_with_end_or_backlog_refused(self):
        with self.assertRaises(ValueError):
            _obs([I.DeviceLink("r1", False, 10.0, 20.0)])
        with self.assertRaises(ValueError):
            _obs([I.DeviceLink("r1", False, 10.0, None, 3, 270)])
        with self.assertRaises(ValueError):
            _obs([I.DeviceLink("r1", False, None)])

    def test_default_empty(self):
        self.assertEqual(_obs([]).device_links, ())


class TestLinkTable(unittest.TestCase):
    def _st(self, on=True):
        st = CS.CoordState(gpu_kv_tokens=1000, host_tier_gib=1.0, host_tier_tokens=1000)
        st.link_events = on
        st.register(dict(device_id="r1", type="robot", uplink_mbps=13.6, rtt_ms=44.0, start_t=0.0), "s")
        return st

    def test_off_refuses(self):
        st = self._st(on=False)
        with self.assertRaises(RuntimeError):
            st.link_event(EV.make_link(device_id="r1", t=1.0, connected=False, offline_since=1.0,
                                       back_online_at=None, backlog_frames=0, backlog_tokens=0))

    def test_sequence_and_refusals(self):
        st = self._st()
        self.assertTrue(st.links["r1"].connected)
        down = EV.make_link(device_id="r1", t=5.0, connected=False, offline_since=5.0,
                            back_online_at=None, backlog_frames=0, backlog_tokens=0)
        st.link_event(down)
        with self.assertRaises(ValueError):
            st.link_event(down)                                    # already offline
        up = EV.make_link(device_id="r1", t=9.0, connected=True, offline_since=5.0,
                          back_online_at=9.0, backlog_frames=60, backlog_tokens=5400)
        lk = st.link_event(up)
        self.assertEqual((lk.offline_since, lk.back_online_at, lk.backlog_tokens), (5.0, 9.0, 5400))
        with self.assertRaises(ValueError):
            st.link_event(up)                                      # reconnect with no outage open
        bad = EV.make_link(device_id="r1", t=20.0, connected=False, offline_since=20.0,
                           back_online_at=None, backlog_frames=3, backlog_tokens=0)
        with self.assertRaises(ValueError):
            st.link_event(bad)                                     # a start carries no backlog
        with self.assertRaises(KeyError):
            st.link_event(dict(up, device_id="nope"))


class TestSchemaLockstep(unittest.TestCase):
    def test_link_fields_agree(self):
        self.assertEqual({k: tuple(v) for k, v in SC.LINK_FIELDS.items()}, EV.LINK_FIELDS)
        EV.check_link_against_schema()

    def test_committed_fields_untouched(self):
        self.assertNotIn("connectivity", SC.FIELDS)
        self.assertNotIn("connectivity", EV.FIELDS)

    def test_parse_and_make(self):
        e = EV.make_link(device_id="r1", t=1.0, connected=True, offline_since=0.0,
                         back_online_at=1.0, backlog_frames=1, backlog_tokens=90)
        SC.parse(e)
        with self.assertRaises(ValueError):
            EV.make_link(device_id="r1", t=1.0)
        with self.assertRaises(ValueError):
            SC.parse(dict(e, extra=1))


class TestSwitches(unittest.TestCase):
    class _A:
        decide = staticmethod(lambda obs: "act")

    def test_class_level_refused(self):
        class A(self._A):
            live2_link_read = True
        with self.assertRaises(LR.LinkReadSwitchError):
            LR.arm_enables(A())
        class B(self._A):
            live2_link_sync = "ours"
        with self.assertRaises(LS.SyncSwitchError):
            LS.arm_enables(B())

    def test_default_off(self):
        self.assertFalse(LR.arm_enables(self._A()))
        self.assertIsNone(LS.arm_enables(self._A()))

    def test_read_site_counts(self):
        a = self._A()
        LR.install(a)
        o = _obs([I.DeviceLink("r1", False, offline_since=50.0), I.DeviceLink("r2", True, 10.0, 20.0, 60, 5400)])
        self.assertEqual(a.decide(o), "act")
        c = a.link_counters
        self.assertEqual((c["link_epochs_read"], c["link_offline_epochs"], c["link_reconnects_seen"],
                          c["link_backlog_frames_seen"]), (1, 1, 1, 60))

    def test_missing_share(self):
        # 120 s offline, 5400 backlog tokens + 20000 believed: history 25369/90*2 s
        m = LS.missing_share(120.0, 20000, 5400)
        self.assertAlmostEqual(m, 120.0 / ((25400 - 31) / 90.0 * 2.0), places=9)
        self.assertEqual(LS.missing_share(1e9, 10, 10), 1.0)
        self.assertEqual(LS.missing_share(0.0, 10, 10), 0.0)

    def test_committed_rows(self):
        self.assertAlmostEqual(LS.ACC_NO_EVIDENCE, 0.212222, places=6)
        self.assertAlmostEqual(LS.ACC_DEVICE, 0.257732, places=6)
        self.assertIn("STATED MODELLING ASSUMPTION", LS.VALUE_MODEL)

    def test_provisional_value_is_the_committed_row(self):
        self.assertAlmostEqual(LS.ACC_QF, 0.568799, places=6)
        self.assertIn("recall|cloud|WITH_HISTORY", LS.VALUE_MODEL)


class TestPlacement(unittest.TestCase):
    def test_evidence_refusals(self):
        import trace as TR
        kw = dict(outage_robots_k=1, outage_duration_s=120.0, outage_placement="evidence")
        with self.assertRaises(ValueError):
            TR.generate_trace(4, 16, "3:11:2", 300.0, "A", **kw)
        with self.assertRaises(ValueError):
            TR.generate_trace(4, 16, "3:11:2", 300.0, "A", outage_robots_k=1, outage_duration_s=120.0,
                              outage_placement="centre", outage_t0_s=50.0)
        with self.assertRaises(ValueError):
            TR.generate_trace(4, 16, "3:11:2", 300.0, "A", outage_t0_s=290.0, **kw)

    def test_evidence_nested_and_equal_to_centre_victims(self):
        import trace as TR
        a = {}
        for k in (1, 3, 5):
            b = TR.generate_trace(4, 16, "3:11:2", 600.0, "A", outage_robots_k=k, outage_duration_s=120.0,
                                  outage_placement="evidence", outage_t0_s=200.0)
            a[k] = b["meta"]["outage"]
        self.assertTrue(set(a[1]["robots"]) <= set(a[3]["robots"]) <= set(a[5]["robots"]))
        self.assertEqual({a[k]["t_start"] for k in a}, {200.0})
        c = TR.generate_trace(4, 16, "3:11:2", 600.0, "A", outage_robots_k=3, outage_duration_s=120.0,
                              outage_placement="centre")["meta"]["outage"]
        self.assertEqual(c["robots"], a[3]["robots"])
        self.assertEqual(a[3]["t0_explicit"], 200.0)


class TestEmulatorBacklog(unittest.TestCase):
    """One dry cell per case (about 12 s each)."""
    @classmethod
    def setUpClass(cls):
        import test_hybrid as TH
        cls.TH = TH
        cls.wl = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
                      dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0,
                      outage_robots_k=3, outage_duration_s=120.0, outage_placement="evidence",
                      outage_t0_s=100.0, link_events=True, link_sync=True)

    def _run(self, arm):
        self.TH.dry(arm, 4, 16, 300.0, **self.wl)
        return self.TH.dry.last

    def test_counts_and_conservation(self):
        for arm, released in (("covex-v6-fair-final-q-sync-ctl", True), ("covex-v6-fair-final-q-sync-d177", False)):
            last = self._run(arm)
            em, co = last["em"], last["co"]
            o = em.meta["outage"]
            self.assertEqual(em.n_link_events, 2 * len(o["robots"]))
            for rid in o["robots"]:
                per = o["deferred_per_robot"][rid]
                self.assertEqual(sum(m["frames"] for m in per["deferred"]), per["frames"])
                self.assertEqual(co.st.links[rid].backlog_frames, per["frames"])
                self.assertEqual(co.st.links[rid].backlog_tokens, per["frames"] * 90)
            any_held = 0
            for sid, s in co.st.sessions.items():
                if s.device_id not in o["robots"]:
                    continue
                cum = em._latest_cum.get(sid)
                if cum is None:
                    continue
                held = sum(m["own_tokens"] for m in em._held_by_sess.get(sid, ())
                           if m["batch_id"] not in em._released and m["cum_tokens"] <= cum)
                self.assertEqual(s.est_tokens, cum - held)
                if released:
                    self.assertEqual(held, 0)
                    self.assertEqual(s.est_tokens, cum)
                else:
                    any_held += held
            if not released:
                self.assertGreater(any_held, 0, "nothing held in a never-releasing arm")


if __name__ == "__main__":
    unittest.main(verbosity=1)
