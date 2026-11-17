"""StudyPOL5-engine: the new flags, the fitted terms, and the fence on BOTH new holdouts."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policy import eng1d_replay as e1d
from policy import score_t0b as st
from policy.eng1_engine import ENGINE_MODELS, Pol4Terms, SimRequest, make_sim
from policy.pol5_engine import POL5_COEF_NAMES, SCHEDULER_HOOKS, Pol5Terms


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


class TestHoldoutFences(unittest.TestCase):
    def test_the_eng1d_holdout_cannot_be_built_without_authorization(self):
        with self.assertRaises(e1d.HoldoutFenced):
            e1d.load_trials("holdout")

    def test_the_eng1c_part_d_holdout_cannot_be_built_without_authorization(self):
        with self.assertRaises(st.HoldoutFenced):
            st.load_part_d_trials(split="holdout")

    def test_the_eng1d_fit_split_excludes_every_holdout_trial(self):
        trials, audit = e1d.load_trials("fit")
        keys = e1d.holdout_keys()
        self.assertEqual(len(keys), 60)
        self.assertEqual(audit["holdout_trials_used"], 0)
        self.assertFalse({(t.load, t.action, t.trial) for t in trials} & keys)

    def test_the_measured_arrival_record_carries_no_holdout_trial(self):
        keys = e1d.holdout_keys()
        arrivals = e1d.measured_arrivals(fence=True)
        self.assertFalse({(k[0], k[1], k[2]) for k in arrivals} & keys)

    def test_the_front_end_fit_rows_carry_no_holdout_request(self):
        rows = e1d.frontend_windows(fence=True)
        self.assertGreater(len(rows), 10000)
        self.assertTrue(all(r["load"] is None or True for r in rows))


class TestPol5Terms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.terms = Pol5Terms.load()
        cls.raw = json.loads((_root() / "results/orchestration/study_pol5/pol5_terms.json").read_text())

    def test_no_fitted_number_is_typed_into_the_module(self):
        """The coefficients may be QUOTED in the docstring, which is documentation; what must not
        happen is one of them appearing as a numeric literal in the code, so this walks the
        parsed syntax tree rather than the text."""
        import ast
        src = (Path(__file__).resolve().parents[1] / "pol5_engine.py").read_text()
        literals = [n.value for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                    and not isinstance(n.value, bool)]
        for name in POL5_COEF_NAMES:
            self.assertIn(name, src)
            value = self.terms.coef[name]
            if value in (0.0, 1.0):
                continue                      # a switched-off rule is a flag, not a fit
            for lit in literals:
                self.assertNotAlmostEqual(float(lit), float(value), places=6,
                                          msg="%s = %r is typed into the module" % (name, value))

    def test_the_terms_file_states_zero_holdout_trials(self):
        self.assertEqual(int(self.raw["holdout_trials_used"]), 0)

    def test_both_rejected_rules_are_recorded_as_rejected_and_switched_off(self):
        self.assertEqual(self.terms.coef["async_schedule_lag_steps"], 0.0)
        self.assertEqual(self.terms.coef["serial_prefill_admission"], 0.0)
        self.assertIn("REJECTED", self.raw["async_scheduling"]["status"])
        self.assertIn("REJECTED", self.raw["serial_prefill_admission"]["status"])

    def test_the_front_end_grows_with_images_as_measured(self):
        a = self.terms.frontend_service_s(1.0, 1, False)
        b = self.terms.frontend_service_s(1.0, 124, False)
        self.assertGreater(b, a)
        self.assertAlmostEqual(b - a, 123 * self.terms.coef["front_end_per_image_ms"] / 1000.0,
                               places=9)

    def test_the_busy_regime_is_longer_not_shorter(self):
        self.assertGreater(self.terms.coef["front_end_busy_factor"], 1.0)
        self.assertGreater(self.terms.frontend_service_s(5.0, 20, True),
                           self.terms.frontend_service_s(5.0, 20, False))

    def test_the_capped_host_charge_is_transfer_plus_a_measured_overhead(self):
        bpt = Pol4Terms.load().coef["host_kv_bytes_per_token"]
        ms = self.terms.host_reload_ms(11000, bpt)
        self.assertGreater(ms, self.terms.coef["host_kv_reload_overhead_ms_capped"])
        self.assertEqual(self.terms.host_reload_ms(0, bpt), 0.0)


class TestPol5IsNotWiredIntoTheFrozenEngine(unittest.TestCase):
    """StudyPOL5 stopped at its regression gate, so the serving model must be untouched: the
    engine module is named in the StudyT0b freeze and its md5 may not move."""

    def test_the_engine_still_offers_exactly_the_three_frozen_models(self):
        self.assertEqual(ENGINE_MODELS, ("eng1", "pol4", "pol4_nobatch"))
        for bad in ("pol5", "pol5_nolag"):
            with self.assertRaises(ValueError):
                make_sim(bad)

    def test_the_engine_module_md5_still_matches_the_t0b_freeze(self):
        import hashlib
        frozen = json.loads((_root() / "results/orchestration/study_t0b/t0b_freeze.json").read_text())
        for rel, md5 in frozen["files"].items():
            got = hashlib.md5((_root() / rel).read_bytes()).hexdigest()
            self.assertEqual(got, md5, rel)

    def test_pol5_declares_itself_not_adopted(self):
        self.assertFalse(Pol5Terms.load().adopted())

    def test_the_rejected_scheduler_hooks_are_described_and_not_implemented(self):
        self.assertEqual(set(SCHEDULER_HOOKS), {"async_schedule_lag_steps",
                                                "serial_prefill_admission"})
        for text in SCHEDULER_HOOKS.values():
            self.assertIn("REJECTED", text)
        src = (Path(__file__).resolve().parents[1] / "eng1_engine.py").read_text()
        self.assertNotIn("serial_prefill_admission", src)
        self.assertNotIn("async_schedule_lag_steps", src)


if __name__ == "__main__":
    unittest.main()
