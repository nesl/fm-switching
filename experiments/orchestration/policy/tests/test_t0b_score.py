"""StudyT0b Part 2: the ENG1c Part D adapter, the holdout fence and the two definitions."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from policy import score_t0b as st
from policy import trace_replay as tr
from policy.eng1_engine import make_sim


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


class TestHoldoutFence(unittest.TestCase):
    def test_the_holdout_split_cannot_be_built_without_authorization(self):
        with self.assertRaises(st.HoldoutFenced):
            st.load_part_d_trials(split="holdout")

    def test_an_unknown_split_is_refused(self):
        with self.assertRaises(ValueError):
            st.load_part_d_trials(split="eval")

    def test_the_fit_load_builds_no_holdout_trial_and_says_so(self):
        trials, audit = st.load_part_d_trials(split="fit")
        self.assertEqual(audit["holdout_trials_used"], 0)
        self.assertEqual(audit["holdout_pairs_built"], 0)
        self.assertTrue(all(not t.holdout for t in trials))

    def test_the_record_flags_exactly_the_split_files_holdout_pairs(self):
        _, audit = st.load_part_d_trials(split="fit")
        self.assertEqual(audit["n_holdout_pairs_in_record"],
                         audit["n_holdout_pairs_in_split_file"])
        self.assertEqual(audit["n_holdout_pairs_in_split_file"], 120)

    def test_the_fit_set_is_the_rest_of_the_population(self):
        trials, audit = st.load_part_d_trials(split="fit")
        self.assertEqual(len(trials), 360)
        self.assertEqual(audit["n_fit_pairs_in_record"], 360)


class TestAdapterAgainstEng1c(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trials, cls.audit = st.load_part_d_trials(split="fit")

    def test_the_latency_definition_reproduces_eng1cs_published_imposed_delay(self):
        x = st.cross_check_against_eng1c(self.trials)
        self.assertTrue(x["latency"]["agree"], x["latency"])
        self.assertLessEqual(x["latency"]["max_abs_diff_s"], 1e-6)

    def test_the_ttft_definition_is_a_different_quantity_and_is_labelled(self):
        x = st.cross_check_against_eng1c(self.trials)
        self.assertFalse(x["ttft"]["agree"])
        self.assertGreater(x["ttft"]["max_abs_diff_s"], 0.1)
        self.assertIn("different quantity", x["reading"])

    def test_every_trial_has_both_arms_and_one_action(self):
        for t in self.trials:
            self.assertIn("with", t.arms)
            self.assertIn("without", t.arms)
            self.assertTrue(t.arms["with"].action, t.key())
            self.assertFalse(t.arms["without"].action, t.key())

    def test_the_ranking_condition_is_cap_and_load_not_cap_alone(self):
        conds = {t.load for t in self.trials}
        self.assertEqual(len(conds), 8)
        self.assertTrue(all("_" in c for c in conds))
        cells = {t.cell() for t in self.trials}
        self.assertEqual(len(cells), 24)

    def test_the_action_names_are_t0s_own_so_the_ranking_is_comparable(self):
        self.assertEqual({t.action for t in self.trials},
                         {"mono11k", "piece2048", "piece1024"})

    def test_no_job_row_is_treated_as_a_setup_row(self):
        for t in self.trials:
            for arm in t.arms.values():
                self.assertEqual(arm.setup, [])


class TestCeilingAndCriterionIB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trials, _ = st.load_part_d_trials(split="fit")

    def test_the_ceiling_uses_three_repeat_pairs_per_cell(self):
        c = st.ceiling_for_metric(self.trials, "latency")
        self.assertEqual(c["n"], 72)
        self.assertEqual(len(c["per_cell"]), 24)
        self.assertTrue(all(v["n"] == 3 for v in c["per_cell"].values()))

    def test_the_ceiling_is_a_measurement_against_itself(self):
        c = st.ceiling_for_metric(self.trials, "latency")
        self.assertIn("with - repeat", c["definition"])
        self.assertIn("same 24 cells", c["deviation"])

    def test_criterion_i_b_is_a_ratio_to_the_ceiling(self):
        r = st.criterion_i_b(0.45, 0.90)
        self.assertAlmostEqual(r["ratio"], 0.5)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(st.criterion_i_b(0.81, 0.90)["verdict"], "PASS")

    def test_criterion_i_b_reports_the_three_numbers_side_by_side(self):
        r = st.criterion_i_b(0.55, 0.8889)
        self.assertIn("0.8889", r["wording"])
        self.assertIn("0.5500", r["wording"])

    def test_a_missing_ceiling_is_not_computable_rather_than_a_pass(self):
        self.assertEqual(st.criterion_i_b(0.9, None)["verdict"], "NOT COMPUTABLE")
        self.assertEqual(st.criterion_i_b(0.9, 0)["verdict"], "NOT COMPUTABLE")


class TestResidencyIsAnInput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trials, _ = st.load_part_d_trials(split="fit")

    def test_the_tier_input_is_recorded_and_labelled(self):
        ti = st.tier_inputs(self.trials)
        self.assertEqual(ti["n"], 360)
        self.assertIn("RESIDENCY GIVEN", ti["label"])
        self.assertEqual(ti["n_cold"] + ti["n_warm_host"] + ti["n_warm_local"], ti["n"])
        self.assertGreater(ti["n_cold"], 0)
        self.assertGreater(ti["n_warm_host"], 0)

    def test_the_host_transfer_input_is_only_charged_where_the_counter_is_attributable(self):
        charged = 0
        for t in self.trials:
            for r in t.arms["with"].action:
                if int(r.get("_external_cached_tokens", 0) or 0) > 0:
                    charged += 1
                    self.assertLessEqual(int(r["_external_cached_tokens"]),
                                         int(r["cached_tokens"]))
        self.assertGreater(charged, 0)


class TestCriterionIVDegeneracy(unittest.TestCase):
    def test_eng1c_part_b_is_nearly_degenerate_and_says_so(self):
        iv = st.criterion_iv_eng1c_part_b()
        self.assertFalse(iv["degenerate"])
        self.assertTrue(iv["nearly_degenerate"])
        self.assertGreaterEqual(iv["dominant_class_share"], 0.9)
        self.assertNotIn("partial", iv["measured_class_counts"])
        self.assertIn("NEARLY DEGENERATE", iv["verdict"])
        self.assertEqual(iv["criterion_verdict"], "PASS")

    def test_the_class_accuracy_is_computed_over_every_part_b_trial(self):
        iv = st.criterion_iv_eng1c_part_b()
        self.assertEqual(iv["n"], iv["n_scored"])
        self.assertGreater(iv["n"], 300)


class TestMyPathMatchesTheFrozenOne(unittest.TestCase):
    def test_the_ttft_path_reproduces_run_t0s_own_scoring(self):
        trials, _ = st.load_part_d_trials(split="fit")
        chk = st._internal_check(trials[:60], "pol4")
        self.assertTrue(chk["agree"], chk)


if __name__ == "__main__":
    unittest.main()
