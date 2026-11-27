#!/usr/bin/env python3
"""Unit tests for the D319 touch guard that reads P (live2_pb_touch_guard). CPU only.
Run: python -I test_touch_p_guard.py
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

L = Path(__file__).resolve().parents[1]
for p in (L / "hybrid", L, L / "fleet", L / "v5", L / "tests", L / ".." / "baselines", L / ".." / "sim"):
    sys.path.insert(0, str(p))

import predictive_belief as PB  # noqa: E402
import touch_policy as TP  # noqa: E402

BLOCK = PB.BLOCK


def _p(gpu_blocks=64, host_blocks=64):
    return PB.PredictiveBelief(gpu_blocks, host_blocks, offload_controls=True, prefill_s_per_token=None,
                               engine_resync=True, host_engine_model=True)


def _build(p, key, tokens, t=0.0, rid="r1"):
    p.observe_send(rid, key, tokens, t, 0, robot=True)
    p.observe_completion(rid, 0, t + 1.0, prompt_tokens=tokens)


class TSwitch(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(PB.touch_guard_enables(NS()))

    def test_instance_on(self):
        a = NS()
        object.__setattr__(a, PB.TOUCH_GUARD_SWITCH, True)
        self.assertTrue(PB.touch_guard_enables(a))

    def test_class_attribute_raises(self):
        class K:
            pass
        setattr(K, PB.TOUCH_GUARD_SWITCH, True)
        with self.assertRaises(PB.PredictiveBeliefSwitchError):
            PB.touch_guard_enables(K())

    def test_non_bool_raises(self):
        a = NS()
        object.__setattr__(a, PB.TOUCH_GUARD_SWITCH, 1)
        with self.assertRaises(PB.PredictiveBeliefSwitchError):
            PB.touch_guard_enables(a)


class TTierSplit(unittest.TestCase):
    def test_empty_chain(self):
        self.assertEqual(_p().tier_split("s1", 1600), (0.0, 0.0))

    def test_gpu_resident(self):
        p = _p()
        _build(p, "s1", 1600)
        g, h = p.tier_split("s1", 1600)
        self.assertGreaterEqual(g, 0.95)
        self.assertEqual(h, 0.0)

    def test_pure_read_changes_no_stat(self):
        p = _p()
        _build(p, "s1", 1600)
        before = dict(p.stats)
        p.tier_split("s1", 1600)
        self.assertEqual(before, p.stats)

    def test_host_only_after_gpu_eviction(self):
        p = _p(gpu_blocks=110, host_blocks=400)
        _build(p, "s1", 1600, 0.0, "r1")                # 100 blocks, then free
        _build(p, "s2", 1600, 10.0, "r2")               # pressure: evicts s1's GPU blocks to host
        g, h = p.tier_split("s1", 1600)
        self.assertLess(g, 0.95)
        self.assertGreater(g + h, 0.0)

    def test_evicted_everywhere(self):
        p = _p(gpu_blocks=110, host_blocks=10)
        _build(p, "s1", 1600, 0.0, "r1")
        _build(p, "s2", 1600, 10.0, "r2")
        _build(p, "s3", 1600, 20.0, "r3")
        g, h = p.tier_split("s1", 1600)
        self.assertLess(g + h, 0.95)


class TGuardDecision(unittest.TestCase):
    """The decision the coordinator takes: D150 cold + P belief -> mixed_touch_guard."""

    def _decide(self, g, h):
        pbel = {"gpu": g, "host": h, "cold": max(0.0, 1.0 - g - h)}
        return TP.mixed_touch_guard(pbel)[0]

    def test_pure_gpu_allowed(self):
        self.assertTrue(self._decide(1.0, 0.0))

    def test_pure_host_allowed(self):
        self.assertTrue(self._decide(0.0, 1.0))

    def test_mixed_refused(self):
        self.assertFalse(self._decide(0.5, 0.5))

    def test_partial_refused(self):
        self.assertFalse(self._decide(0.4, 0.0))

    def test_evicted_refused(self):
        self.assertFalse(self._decide(0.0, 0.0))


class TCoordinator(unittest.TestCase):
    """Positive controls on the real coordinator method `_submit_touch` (dry coordinator)."""

    @classmethod
    def setUpClass(cls):
        import test_hybrid as TH
        import coordinator as CO
        import arms_final_ladder as FL
        os.environ.setdefault("DRY_PATHS", "1")
        try:
            FL.register()
        except Exception:
            pass
        cls.TH, cls.CO = TH, CO
        W = dict(ratio="3:11:2", robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                 robot_upload="per-frame", robot_reask_mean_s=30.0)
        TH.dry("covex-v6-fair-final-cand-tl", 4, 16, 20.0, **W)
        cls.co = TH.dry.last["co"]

    def _s(self, key, belief):
        return NS(session_id=key, belief=belief, built_tokens=1600, confirmed_bytes_for=[1],
                  device_id="robo000", last_touch_s=0.0)

    def _try(self, s):
        c0 = dict(self.co.counts)
        try:
            self.co._submit_touch(s, 30.0, 0.0, None, None)
        except Exception:
            pass
        return {k: self.co.counts[k] - c0.get(k, 0) for k in self.co.counts
                if self.co.counts[k] != c0.get(k, 0)}

    def test_cold_but_host_resident_is_touched(self):
        co = self.co
        co._pb = _p()
        _build(co._pb, "synth|a", 1600)
        d = self._try(self._s("synth|a", {"gpu": 0.0, "host": 0.0, "cold": 1.0}))
        self.assertEqual(d.get("touch_guard_p_consulted"), 1)
        self.assertEqual(d.get("touch_guard_p_allowed"), 1)
        self.assertNotIn("touch_refused_guard", d)
        # past every gate: the price was spent and the code reached the touch decision log (the dry
        # coordinator's log file is closed, so the call raises exactly there and nowhere earlier)
        self.assertGreater(d.get("touch_price_milli_sum", 0), 0)

    def test_cold_and_truly_evicted_stays_refused(self):
        co = self.co
        co._pb = _p()
        d = self._try(self._s("synth|none", {"gpu": 0.0, "host": 0.0, "cold": 1.0}))
        self.assertEqual(d.get("touch_guard_p_consulted"), 1)
        self.assertEqual(d.get("touch_guard_p_kept_cold"), 1)
        self.assertEqual(d.get("touch_refused_guard"), 1)

    def test_warm_session_never_consults_p(self):
        co = self.co
        co._pb = _p()
        d = self._try(self._s("synth|w", {"gpu": 1.0, "host": 0.0, "cold": 0.0}))
        self.assertNotIn("touch_guard_p_consulted", d)

    def test_switch_off_arm_never_consults_p(self):
        co = self.co
        saved = co._pb_touch_guard
        co._pb_touch_guard = False
        try:
            co._pb = _p()
            _build(co._pb, "synth|b", 1600)
            d = self._try(self._s("synth|b", {"gpu": 0.0, "host": 0.0, "cold": 1.0}))
            self.assertNotIn("touch_guard_p_consulted", d)
            self.assertEqual(d.get("touch_refused_guard"), 1)
        finally:
            co._pb_touch_guard = saved


if __name__ == "__main__":
    unittest.main(verbosity=1)
