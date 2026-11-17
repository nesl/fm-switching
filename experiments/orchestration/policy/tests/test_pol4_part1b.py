"""StudyPOL4-engine Part 1b: tests for the attribution, the base check and the blocking
estimator."""
from __future__ import annotations

import unittest

from policy import trace_replay as tr
from policy.analyze_pol4_1b import (QUERY_IMAGE_TOKENS, _boot_ci, admission_check,
                                    blocking_under_load, compared_set_check, front_end_share,
                                    merged_step_duration, single_request_base)
from policy.eng1_engine import StepModel, make_sim
from policy.run_pol4 import split_fit_trials

_TRIALS = None


def _fit_trials():
    global _TRIALS
    if _TRIALS is None:
        _TRIALS, _ = split_fit_trials()
    return _TRIALS


def _synthetic(n_trials: int, action: str = "synth"):
    """Trials whose blocking fraction is known by construction: an action that holds the engine
    until t = 1.0 and two arrivals at t = 0.5 (rho 0.6) and t = 0.8 (rho 0.5)."""
    out = []
    for i in range(n_trials):
        arms = {}
        for mode, t_with in (("with", True), ("without", False)):
            bg = [
                dict(kind="episodic", idx=0, rid="%s-%d-bg0" % (mode, i), arrival_rel=0.5,
                     t_submit=0.5, ttft_s=(0.4 if t_with else 0.1), t_first=0.9),
                dict(kind="episodic", idx=1, rid="%s-%d-bg1" % (mode, i), arrival_rel=0.8,
                     t_submit=0.8, ttft_s=(0.2 if t_with else 0.1), t_first=1.0),
            ]
            arm = tr.Arm(mode=mode, t0_trace=0.0)
            arm.background.extend(bg)
            if t_with:
                arm.action.append(dict(kind="inject", rid="act-%d" % i, t_submit=0.0,
                                       t_first=1.0, t_end=1.0, ttft_s=1.0))
            arms[mode] = arm
        out.append(tr.Trial(load="L", action=action, trial=i, holdout=False, t_inj_rel=0.0,
                            arms=arms))
    return out


class TestBlockingEstimator(unittest.TestCase):
    def test_it_recovers_a_known_blocking_fraction(self):
        res = blocking_under_load(_synthetic(20))
        cut = res["per_cut"]["L|synth"]
        self.assertEqual(cut["n_trials"], 20)
        self.assertEqual(cut["n_arrivals"], 40)
        # per trial the two arrivals give 0.3/0.5 = 0.6 and 0.1/0.2 = 0.5, median 0.55
        self.assertAlmostEqual(cut["rho_trial_median"], 0.55, places=9)
        self.assertTrue(cut["identified"])

    def test_an_arrival_outside_the_action_window_is_not_counted(self):
        trials = _synthetic(12)
        for t in trials:
            for arm in t.arms.values():
                for r in arm.background:
                    r["arrival_rel"] = 5.0          # after the action finished
        res = blocking_under_load(trials)
        self.assertNotIn("L|synth", res["per_cut"])

    def test_a_thin_cut_is_not_declared_identified(self):
        res = blocking_under_load(_synthetic(3))
        self.assertFalse(res["per_cut"]["L|synth"]["identified"])

    def test_the_identifiability_criterion_is_stated_with_its_thresholds(self):
        c = blocking_under_load(_synthetic(12))["criterion"]
        self.assertEqual((c["min_arrivals"], c["min_trials"], c["max_ci_half_width"]),
                         (30, 10, 0.25))

    def test_the_bootstrap_ci_brackets_the_median(self):
        ci = _boot_ci([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        self.assertLessEqual(ci["lo"], ci["median"])
        self.assertGreaterEqual(ci["hi"], ci["median"])

    def test_it_is_not_added_to_the_model(self):
        self.assertIn("NOT ADDED", blocking_under_load(_synthetic(12))["not_added"])


class TestBurst4Attribution(unittest.TestCase):
    def test_the_two_shares_add_to_the_predicted_imposed_delay(self):
        sim = make_sim(engine_model="eng1")
        t = [x for x in _fit_trials() if x.action == "burst4"][0]
        rw = sim.run(tr._arm_requests(t.arms["with"], include_action=True))["per_request"]
        ro = sim.run(tr._arm_requests(t.arms["without"], include_action=False))["per_request"]
        fe = eng = 0.0
        for a, b in [(w, o) for w, o in zip(*[[r for r in sorted(
                [x for x in arm.background if x.get("kind") == "episodic"],
                key=lambda r: str(tr._bg_key(r)))] for arm in (t.arms["with"],
                                                               t.arms["without"])])]:
            x, y = rw.get(str(a.get("rid"))), ro.get(str(b.get("rid")))
            if not x or not y or x["ttft_s"] is None or y["ttft_s"] is None:
                continue
            fe += (x["t_added"] - (x["t_first"] - x["ttft_s"])) - (
                y["t_added"] - (y["t_first"] - y["ttft_s"]))
            eng += (x["t_first"] - x["t_added"]) - (y["t_first"] - y["t_added"])
        self.assertAlmostEqual(fe + eng, tr.predict_trial(t, sim)["predicted_delay_s"],
                               places=9)

    def test_the_front_end_is_not_the_burst4_channel(self):
        r = front_end_share(_fit_trials(), "eng1")["per_action"]["burst4"]
        self.assertGreater(r["med_over_prediction_s"], 0.05)
        # below a tenth of a millisecond, and below 1 % of the over-prediction it would have to
        # explain
        self.assertLess(abs(r["front_end_share_p50_s"]), 1e-4)
        self.assertLess(abs(r["front_end_share_of_over_prediction"]), 0.01)

    def test_the_compared_request_set_is_balanced_and_does_not_explain_it(self):
        r = compared_set_check(_fit_trials())["per_action"]["burst4"]
        self.assertEqual(r["unbalanced_trials"], 0)
        self.assertEqual(r["n_with_p50"], r["n_without_p50"])
        self.assertLess(abs(r["med_ratio_episodic"] / r["med_ratio_superset"] - 1.0), 0.05)

    def test_the_admission_terms_charge_the_burst_nothing_so_they_cannot_double_count_it(self):
        r = admission_check(_fit_trials(), StepModel.load())["per_action"]["burst4"]
        self.assertAlmostEqual(r["admission_charged_to_the_action_ms_p50"], 0.0, places=9)
        self.assertAlmostEqual(r["med_over_prediction_s"],
                               r["med_over_prediction_admission_off_s"], places=6)

    def test_the_merged_step_is_over_charged_and_the_term_reduces_it(self):
        old = merged_step_duration(_fit_trials(), "eng1")["per_action"]["burst4"]
        new = merged_step_duration(_fit_trials(), "pol4")["per_action"]["burst4"]
        self.assertGreater(old["ratio_p50"], 1.0)
        self.assertLess(new["ratio_p50"], old["ratio_p50"])
        self.assertEqual(old["measured_shared_span_s"]["p50"],
                         new["measured_shared_span_s"]["p50"])


class TestSingleRequestBase(unittest.TestCase):
    def test_the_query_image_token_count_is_the_one_the_record_implies(self):
        r = single_request_base(StepModel.load())
        for cell in r["a1_k1"].values():
            self.assertAlmostEqual(cell["implied_query_image_tokens"], QUERY_IMAGE_TOKENS,
                                   places=6)

    def test_the_frame_count_convention_is_what_produced_the_0_804_figure(self):
        r = single_request_base(StepModel.load())["a1_k1"]["N=1"]
        self.assertLess(abs(r["as_frames"]["ratio"] - 0.804), 0.01)
        self.assertLess(abs(r["as_encoder_units"]["ratio"] - 1.0), 0.01)

    def test_no_term_is_added_for_the_base(self):
        self.assertEqual(single_request_base(StepModel.load())["verdict"], "no term")


if __name__ == "__main__":
    unittest.main()
