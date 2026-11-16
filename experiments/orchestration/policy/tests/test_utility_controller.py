import math
import unittest

from policy.controller import DeviceController
from policy.profiles import MissingEvidence
from policy.utility import gain, t_ready_s, u_rc, u_sh_cloud, u_sh_device
from policy.tests._fixtures import PF, device


class TestUtility(unittest.TestCase):
    def test_interpolation_hits_the_grid_exactly(self):
        for d, u in PF.u_sh_grid(1):
            self.assertAlmostEqual(u_sh_cloud(PF, d)[0], u, places=12)

    def test_no_extrapolation_past_the_last_measured_delay(self):
        last = PF.u_sh_grid(1)[-1]
        u, inrange = u_sh_cloud(PF, last[0] + 5.0)
        self.assertAlmostEqual(u, last[1], places=12)
        self.assertFalse(inrange, "a delay beyond the measured grid must be flagged")

    def test_interpolated_value_stays_inside_the_grid_range(self):
        grid = PF.u_sh_grid(1)
        lo = min(u for _, u in grid)
        hi = max(u for _, u in grid)
        for i in range(0, 61):
            u = u_sh_cloud(PF, i * 0.05)[0]
            self.assertGreaterEqual(u + 1e-12, lo)
            self.assertLessEqual(u - 1e-12, hi)

    def test_m_greater_than_one_is_refused_unless_merging_is_on(self):
        with self.assertRaises(MissingEvidence):
            u_sh_cloud(PF, 0.5, m_frames=3)
        self.assertGreater(u_sh_cloud(PF, 0.5, m_frames=3, allow_m_gt_1=True)[0], 0.0)

    def test_gain_is_zero_at_the_device_and_can_be_negative(self):
        ud = u_sh_device(PF)
        self.assertAlmostEqual(gain(PF, "SH", ud, ud), 0.0, places=12)
        far = u_sh_cloud(PF, 3.0)[0]
        self.assertLess(gain(PF, "SH", far, ud), 0.0,
                        "a stale cloud answer must be allowed to score negative (D39)")

    def test_u_ss_refuses(self):
        from policy.utility import u_ss
        with self.assertRaises(MissingEvidence):
            u_ss(PF, 0.1, 2.0)

    def test_t_ready_is_ordered_by_tier(self):
        d = device()
        totals = {}
        for tier in ("GPU", "HOST", "STORED"):
            totals[tier] = t_ready_s(PF, "RICH", tier, 11_000, 0.0, 0, d.link)["total"]
        self.assertLess(totals["GPU"], totals["HOST"])
        self.assertLess(totals["HOST"], totals["STORED"])

    def test_u_rc_falls_back_to_the_device_past_the_deadline(self):
        d = device()
        cloud = u_rc(PF, "counting_objects_events", "RICH", 1.0, 0.0, d.link, 10.0)
        late = u_rc(PF, "counting_objects_events", "RICH", 100.0, 0.0, d.link, 10.0)
        self.assertTrue(cloud[1])
        self.assertFalse(late[1])
        self.assertAlmostEqual(late[0], PF.rc_accuracy("counting_objects_events", "D2", "device"),
                               places=12)


class TestController(unittest.TestCase):
    def _run(self, scores, **kw):
        c = DeviceController(w_c=3.0, delta=1.5, n_c=3, k_c=2, theta=1.5, cadence_s=0.75, **kw)
        return [c.step(s, 0.75 * i) for i, s in enumerate(scores)]

    def test_a_flat_window_cannot_escalate(self):
        out = self._run([-11.0] * 12)
        self.assertTrue(all(o["signal"] is None for o in out[1:]))
        self.assertTrue(all(o["action"] == "none" for o in out))

    def test_no_absolute_confidence_scale_invariance(self):
        """Spec 7.7 forbids absolute confidence: an affine rescaling of the whole score stream
        must leave every signal unchanged in the variance reading."""
        import random
        rng = random.Random(0)
        base = [rng.gauss(-12, 0.8) for _ in range(30)]
        a = self._run(base, mode="var")
        for slope, offset in ((2.0, 0.0), (1.0, +7.0), (0.5, -3.0)):
            b = self._run([slope * x + offset for x in base], mode="var")
            for x, y in zip(a, b):
                if x["signal"] is None:
                    self.assertIsNone(y["signal"])
                else:
                    self.assertAlmostEqual(x["signal"], y["signal"], places=9)
                self.assertEqual(x["action"], y["action"])

    def test_episode_closes_after_k_c_quiet_samples(self):
        scores = [-12, -11.9, -12.1, -8.0, -8.1, -12.0, -12.1, -12.0]
        acts = [o["action"] for o in self._run(scores)]
        self.assertIn("escalate", acts)
        self.assertIn("close", acts)

    def test_episode_is_bounded_by_e_k(self):
        c = DeviceController(w_c=3.0, delta=1.5, n_c=3, k_c=99, theta=0.5, cadence_s=0.75, e_k=4)
        rising = [-12 + 0.5 * i for i in range(20)]
        calls = 0
        for i, s in enumerate(rising):
            o = c.step(s, 0.75 * i)
            calls = max(calls, o["calls"])
        self.assertLessEqual(calls, 4)

    def test_price_term_only_moves_the_threshold_when_enabled(self):
        c = DeviceController(w_c=3.0, delta=1.5, n_c=3, k_c=2, theta=1.5, beta=2.0)
        self.assertEqual(c.threshold(price=3.0, price_enabled=False), 1.5)
        self.assertEqual(c.threshold(price=3.0, price_enabled=True), 7.5)
