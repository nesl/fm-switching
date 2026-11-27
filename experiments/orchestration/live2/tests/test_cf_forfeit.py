#!/usr/bin/env python3
"""Unit tests for step 3 (cf_forfeit.py and arms_v6cfstep3.py). CPU only, no engine.
Run: python -I test_cf_forfeit.py
"""
import sys
import unittest
from pathlib import Path

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import cf_forfeit as CF  # noqa: E402


class _A:
    pass


class SwitchTests(unittest.TestCase):
    def test_default_off_and_strict(self):
        a = _A()
        self.assertFalse(CF.admit_enabled(a))
        self.assertFalse(CF.resident_enabled(a))
        object.__setattr__(a, CF.ADMIT_SWITCH, True)
        self.assertTrue(CF.admit_enabled(a))
        object.__setattr__(a, CF.RESIDENT_SWITCH, 1)
        with self.assertRaises(CF.CfForfeitSwitchError):
            CF.resident_enabled(a)

    def test_class_level_switch_raises(self):
        class B:
            live2_cf_forfeit_admit = True
        with self.assertRaises(CF.CfForfeitSwitchError):
            CF.admit_enabled(B())


class ResidentSetTests(unittest.TestCase):
    def _c(self, sid, w, nq, tok):
        return dict(session_id=sid, device_id=sid, tokens=tok, w=w, next_q_s=nq)

    def test_fits_and_order(self):
        cands = [self._c("a", 1.0, 5, 40), self._c("b", 2.0, 9, 40), self._c("c", 1.0, 3, 40)]
        rs = CF.resident_set(cands, 80)
        self.assertEqual(rs["order"], ["b", "c", "a"])
        self.assertEqual(rs["members"], ["b", "c"])
        self.assertEqual(rs["excluded"], ["a"])
        self.assertLessEqual(rs["used_tokens"], 80)

    def test_rotates_with_deficit(self):
        base = [self._c("a", 1.0, 5, 40), self._c("b", 1.0, 9, 40), self._c("c", 1.0, 3, 40)]
        r0 = CF.resident_set(base, 80)["members"]
        base[1]["w"] = 3.0
        r1 = CF.resident_set(base, 80)["members"]
        self.assertNotEqual(set(r0), set(r1))
        self.assertIn("b", r1)

    def test_skip_then_smaller_fits(self):
        cands = [self._c("big", 3.0, 1, 90), self._c("s1", 1.0, 2, 30)]
        self.assertEqual(CF.resident_set(cands, 100)["members"], ["big"])
        cands = [self._c("big", 3.0, 1, 120), self._c("s1", 1.0, 2, 30)]
        rs = CF.resident_set(cands, 100)
        self.assertEqual(rs["members"], ["s1"])
        self.assertEqual(rs["excluded"], ["big"])

    def test_total_order_is_deterministic(self):
        cands = [self._c("b", 1.0, 5, 10), self._c("a", 1.0, 5, 10)]
        self.assertEqual(CF.resident_set(cands, 100)["order"], ["a", "b"])


class FutureTests(unittest.TestCase):
    P = staticmethod(lambda e, s: 1.0 if e <= s else 0.0)
    E = staticmethod(lambda u: 0.001 * u)

    def test_gain_scales_with_weight_and_count(self):
        f1 = CF.forfeited_future(w_r=1.0, u_cold=5000, u_warm=0, slack_next_s=3.0, p_on_time=self.P,
                                 engine_s_of=self.E)
        f2 = CF.forfeited_future(w_r=2.0, u_cold=5000, u_warm=0, slack_next_s=3.0, p_on_time=self.P,
                                 engine_s_of=self.E, n_expected=3.0)
        self.assertEqual(f1["future_gain"], 1.0)
        self.assertEqual(f2["future_gain"], 6.0)

    def test_no_gain_when_cold_is_already_on_time(self):
        f = CF.forfeited_future(w_r=1.0, u_cold=100, u_warm=0, slack_next_s=3.0, p_on_time=self.P,
                                engine_s_of=self.E)
        self.assertEqual(f["future_gain"], 0.0)

    def test_expected_questions(self):
        self.assertEqual(CF.expected_questions(120.0, 30.0), 4.0)
        self.assertIsNone(CF.expected_questions(120.0, None))
        self.assertIsNone(CF.expected_questions(120.0, 0.0))


class DecisionTests(unittest.TestCase):
    def _fut(self, g):
        return {"future_gain": g}

    def _d(self, **o):
        kw = dict(in_resident_set=True, has_estimate=True, dt_next_s=10.0, horizon_cap_s=120.0,
                  w_r=1.0, p_self=0.1, harm=0.0, bar_value=0.658, future=self._fut(1.0))
        kw.update(o)
        return CF.admit_decision(**kw)

    def test_admit(self):
        d = self._d()
        self.assertEqual(d["action"], CF.ADMIT)
        self.assertAlmostEqual(d["net"], 1.1)

    def test_each_gate(self):
        self.assertEqual(self._d(has_estimate=False)["gate"], "no_question_estimate")
        self.assertEqual(self._d(dt_next_s=121.0)["gate"], "next_question_beyond_horizon")
        self.assertEqual(self._d(in_resident_set=False)["gate"], "not_in_resident_set")
        self.assertEqual(self._d(future=None)["gate"], "future_not_priced")
        self.assertEqual(self._d(future=self._fut(0.0))["gate"], "no_future_gain")
        self.assertEqual(self._d(future=self._fut(0.5), p_self=0.0)["gate"], "net_does_not_exceed_the_bar")

    def test_harm_vetoes(self):
        self.assertEqual(self._d(harm=5.0)["action"], CF.KEEP_REJECT)

    def test_weight_cancels_in_bar_ratio(self):
        a = self._d(w_r=1.0, p_self=0.2, future=self._fut(0.5), bar_value=0.658)
        b = self._d(w_r=2.0, p_self=0.2, future=self._fut(1.0), bar_value=1.316)
        self.assertEqual(a["action"], b["action"])


class ArrivalHarmTests(unittest.TestCase):
    """D320: HARM prices the questions expected to ARRIVE while the admitted request is served."""

    @staticmethod
    def _p(e, s):
        return 1.0 if e <= s else 0.0

    def _devs(self, n, gap=5.0):
        return [dict(device_id="d%d" % i, qtype="recall", gap_s=gap, u_tokens=2000, slack_s=3.0)
                for i in range(n)]

    def _harm(self, devs, window, u=16000):
        import cf_protect_defer as PD
        ar = CF.arrival_rows(devs, ahead_tokens=0, window_s=window, est_of=lambda u_, q_: 1.0)
        h = PD.harm_on_time(u, ar["rows"], p_on_time=self._p,
                            w_of=lambda dv: 1.0 * ar["n_by_dev"].get(str(dv), 0.0))
        return h, ar

    def test_rows_and_expected_counts(self):
        devs = self._devs(3) + [dict(device_id="nogap", qtype="recall", gap_s=None, u_tokens=1, slack_s=3.0)]
        ar = CF.arrival_rows(devs, ahead_tokens=0, window_s=4.0, est_of=lambda u_, q_: 1.0)
        self.assertEqual(len(ar["rows"]), 3)
        self.assertAlmostEqual(ar["n_expected_total"], 3 * 0.8)
        self.assertNotIn("nogap", ar["n_by_dev"])

    def test_full_queue_harm_blocks_a_large_future(self):
        h, ar = self._harm(self._devs(10), window=4.0)
        self.assertAlmostEqual(h["harm"], 8.0)
        d = CF.admit_decision(in_resident_set=True, has_estimate=True, dt_next_s=10.0, horizon_cap_s=120.0,
                              w_r=1.0, p_self=0.1, harm=h["harm"], bar_value=0.658,
                              future={"future_gain": 3.0})
        self.assertEqual(d["action"], CF.KEEP_REJECT)
        self.assertEqual(d["gate"], "net_does_not_exceed_the_bar")

    def test_light_load_does_not_block(self):
        h, _ = self._harm(self._devs(1), window=4.0)
        self.assertAlmostEqual(h["harm"], 0.8)
        d = CF.admit_decision(in_resident_set=True, has_estimate=True, dt_next_s=10.0, horizon_cap_s=120.0,
                              w_r=1.0, p_self=0.1, harm=h["harm"], bar_value=0.658,
                              future={"future_gain": 3.0})
        self.assertEqual(d["action"], CF.ADMIT)

    def test_no_arrivals_no_window_no_harm(self):
        h, _ = self._harm(self._devs(5), window=0.0)
        self.assertEqual(h["harm"], 0.0)

    def test_switch_strict_default_off(self):
        a = _A()
        self.assertFalse(CF.harm_arrivals_enabled(a))
        object.__setattr__(a, CF.HARM_ARRIVALS_SWITCH, 1)
        with self.assertRaises(CF.CfForfeitSwitchError):
            CF.harm_arrivals_enabled(a)


class WindowTests(unittest.TestCase):
    """D324: the arrival window is the queue wait plus the service time, capped at the horizon."""

    def _parts(self, u, ahead):
        import d162_price as DP
        svc = DP.first_token_s(u, 0)
        return svc, DP.first_token_s(u, ahead) - svc

    def test_empty_queue_reduces_to_service_time(self):
        svc, wait = self._parts(10000, 0)
        self.assertAlmostEqual(wait, 0.0)
        a = CF.arrival_window(service_s=svc, wait_s=wait, cap_s=120.0, mode="queue_service")
        b = CF.arrival_window(service_s=svc, wait_s=wait, cap_s=120.0, mode="service")
        self.assertAlmostEqual(a, b)

    def test_nonempty_queue_lengthens_the_window(self):
        svc, wait = self._parts(10000, 30000)
        self.assertGreater(wait, 0.0)
        a = CF.arrival_window(service_s=svc, wait_s=wait, cap_s=120.0, mode="queue_service")
        b = CF.arrival_window(service_s=svc, wait_s=wait, cap_s=120.0, mode="service")
        self.assertGreater(a, b)
        self.assertAlmostEqual(a - b, wait)
        import d162_price as DP
        self.assertAlmostEqual(a, DP.first_token_s(10000, 30000))   # = B's est_loadaware

    def test_cap_and_bad_mode(self):
        self.assertEqual(CF.arrival_window(service_s=100.0, wait_s=100.0, cap_s=120.0), 120.0)
        with self.assertRaises(ValueError):
            CF.arrival_window(service_s=1.0, wait_s=1.0, cap_s=120.0, mode="full")

    def test_longer_window_means_more_expected_arrivals_and_harm(self):
        import cf_protect_defer as PD
        devs = [dict(device_id="d%d" % i, qtype="recall", gap_s=5.0, u_tokens=2000, slack_s=3.0)
                for i in range(4)]
        p = lambda e, s: 1.0 if e <= s else 0.0
        out = []
        for win in (2.0, 6.0):
            ar = CF.arrival_rows(devs, ahead_tokens=0, window_s=win, est_of=lambda u_, q_: 1.0)
            h = PD.harm_on_time(16000, ar["rows"], p_on_time=p,
                                w_of=lambda dv: ar["n_by_dev"].get(str(dv), 0.0))
            out.append(h["harm"])
        self.assertGreater(out[1], out[0])


class ArmWiringTests(unittest.TestCase):
    def test_arm_builds_switches_read_back_and_off_arm(self):
        import arms as A
        import arms_final_ladder as FL
        import arms_v6cfr3 as R4
        import arms_v6c5 as C5
        import arms_v6shares as SH
        import arms_v6state as ST
        import arms_v6cf as VCF
        for m in (ST, C5, SH, VCF):
            m.register()
        R4.register()
        FL.register()
        arm = A.make_arm("covex-v6-fair-final-cand-tl-sync-cf")
        self.assertTrue(CF.admit_enabled(arm) and CF.resident_enabled(arm))
        off = A.make_arm("covex-v6-fair-final-cand-tl-sync-cf-off")
        self.assertFalse(CF.admit_enabled(off) or CF.resident_enabled(off))
        h0 = A.make_arm("covex-v6-fair-final-cand-tl-sync-cf-h0")
        self.assertTrue(CF.admit_enabled(h0) and CF.resident_enabled(h0))
        self.assertFalse(CF.harm_arrivals_enabled(h0))
        self.assertTrue(CF.harm_arrivals_enabled(arm))
        self.assertFalse(CF.harm_arrivals_enabled(off))
        w0 = A.make_arm("covex-v6-fair-final-cand-tl-sync-cf-w0")
        self.assertEqual(w0.cf3_window_mode, "service")
        self.assertEqual(arm.cf3_window_mode, "queue_service")
        self.assertTrue(CF.harm_arrivals_enabled(w0))
        plain = A.make_arm("covex-v6-fair-final-cand")
        self.assertFalse(CF.admit_enabled(plain) or CF.resident_enabled(plain))


if __name__ == "__main__":
    unittest.main()
