"""StudyPOL6-chain Part A: the pol6 module's flags and terms, and the StudyENG1e loader stub."""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policy import diagnose_pol6_gap as dg
from policy import eng1e_replay as e1e
from policy.eng1_engine import SimRequest, frontend_service_s as pol4_fe
from policy.pol6_engine import (AWAITING_ENG1E, INHERITED_COEF_NAMES, SCHEDULER_HOOKS,
                                Pol6Config, Pol6Terms, apply_piece_gaps)


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


# --------------------------------------------------------------------- pol6 is not the model
class TestPol6IsNotAdopted(unittest.TestCase):
    def test_pol6_is_not_adopted_and_every_flag_is_off_by_default(self):
        t = Pol6Terms.load()
        self.assertFalse(t.adopted())
        self.assertFalse(t.config.any_on())
        self.assertFalse(t.config.piece_gap_scheduling)
        self.assertFalse(t.config.step_granularity)
        self.assertFalse(t.config.in_step_merge)

    def test_the_terms_file_states_zero_holdout_trials_and_carries_no_fitted_coefficient(self):
        raw = json.loads((_root() / "results/orchestration/study_pol6/pol6_terms.json")
                         .read_text())
        self.assertEqual(raw["holdout_trials_used"], 0)
        self.assertEqual(raw["coef"], {},
                         "Part A fitted nothing; a coefficient here would anticipate Part B")

    def test_a_terms_file_with_a_fitted_coefficient_is_refused(self):
        raw = json.loads((_root() / "results/orchestration/study_pol6/pol6_terms.json")
                         .read_text())
        raw["coef"] = {"invented_term": 1.0}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh)
            p = fh.name
        with self.assertRaises(ValueError):
            Pol6Terms.load(path=p)

    def test_the_front_end_coefficients_are_inherited_from_pol5_not_copied(self):
        t = Pol6Terms.load()
        declared = t.raw["inherits"]["coefficients"]
        for name in INHERITED_COEF_NAMES:
            self.assertIn(name, declared)
        self.assertIn("pol5_terms.json", t.pol5.path)

    def test_no_fitted_number_is_typed_into_the_pol6_module(self):
        """Every number pol6 uses must come from a file. The structural literals 0 and 1 are
        exempt: StudyPOL5 records two REJECTED rules as the switch values 0.0, which are not
        fitted quantities, and a module cannot avoid writing 0 and 1."""
        src = (_root() / "experiments/orchestration/policy/pol6_engine.py").read_text()
        t = Pol6Terms.load()
        lits = {float(n.value) for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                and not isinstance(n.value, bool)}
        fitted = {n: v for n, v in t.pol5.coef.items() if float(v) not in (0.0, 1.0)}
        self.assertTrue(fitted)
        for name, val in fitted.items():
            self.assertNotIn(float(val), lits,
                             "coefficient %s is typed into pol6_engine.py" % name)


# --------------------------------------------------------------------- the flags themselves
class TestFlags(unittest.TestCase):
    def test_both_unmeasured_rules_are_recorded_as_awaiting_eng1e_and_are_not_implemented(self):
        for name in ("step_granularity", "in_step_merge"):
            self.assertIn(name, SCHEDULER_HOOKS)
            self.assertIn("NOT IMPLEMENTED", SCHEDULER_HOOKS[name])
        self.assertTrue(AWAITING_ENG1E)
        for text in AWAITING_ENG1E.values():
            self.assertIn("ENG1e", text.replace("StudyENG1e", "ENG1e"))

    def test_the_gap_rule_is_implemented_but_off_and_records_why(self):
        self.assertIn("IMPLEMENTED", SCHEDULER_HOOKS["piece_gap_scheduling"])
        self.assertIn("OFF BY DEFAULT", SCHEDULER_HOOKS["piece_gap_scheduling"])

    def test_turning_on_a_rule_with_no_measured_parameter_raises(self):
        t = Pol6Terms.load().with_config(piece_gap_scheduling=True, step_granularity=True)
        with self.assertRaises(NotImplementedError):
            apply_piece_gaps([self._req("a", 0.0)], t)

    @staticmethod
    def _req(rid: str, t_submit: float, body_mb: float = 0.011, n_images: int = 11,
             tag: str = "action") -> SimRequest:
        return SimRequest(rid=rid, t_submit=t_submit, prompt_tokens=1024, cached_tokens=0,
                          body_mb=body_mb, n_images=n_images, out_tokens=1, tag=tag)

    def test_with_the_flag_off_the_chain_is_returned_unchanged(self):
        t = Pol6Terms.load()
        reqs = [self._req("p0", 0.0), self._req("p1", 1.0), self._req("bg", 0.5, tag="background")]
        self.assertEqual([r.t_submit for r in apply_piece_gaps(reqs, t)],
                         [r.t_submit for r in reqs])

    def test_with_the_flag_on_the_first_piece_never_moves_and_later_pieces_shift_cumulatively(self):
        t = Pol6Terms.load().with_config(piece_gap_scheduling=True)
        reqs = [self._req("p0", 0.0), self._req("p1", 1.0), self._req("p2", 2.0)]
        out = {r.rid: r.t_submit for r in apply_piece_gaps(reqs, t)}
        shift = t.gap_shift_s(0.011, 11)
        self.assertAlmostEqual(out["p0"], 0.0, places=9)
        self.assertAlmostEqual(out["p1"], 1.0 + shift, places=9)
        self.assertAlmostEqual(out["p2"], 2.0 + 2 * shift, places=9)

    def test_background_requests_are_never_re_timed(self):
        t = Pol6Terms.load().with_config(piece_gap_scheduling=True)
        reqs = [self._req("p0", 0.0), self._req("p1", 1.0),
                self._req("bg", 0.5, tag="background")]
        out = {r.rid: r.t_submit for r in apply_piece_gaps(reqs, t)}
        self.assertAlmostEqual(out["bg"], 0.5, places=9)

    def test_the_gap_shift_is_signed_and_positive_on_the_measured_piece_bodies(self):
        """Part A: a chained piece is a tiny body with many images, where pol4 charges 29.8 ms
        and the image-aware term charges 58.2 ms (piece1024) and 95.4 ms (piece2048)."""
        t = Pol6Terms.load()
        self.assertGreater(t.gap_shift_s(0.011, 11), 0.0)
        self.assertGreater(t.gap_shift_s(0.0132, 23), t.gap_shift_s(0.011, 11))
        # and it is NOT clamped: a large low-image body is the other direction
        self.assertLess(t.gap_shift_s(22.76, 1), 0.0)

    def test_the_image_aware_window_overshoots_the_measured_piece_window(self):
        """Why the flag is off: turning it on would over-state the gap, not fix it. Measured
        median windows are 34.9 ms (piece1024) and 44.1 ms (piece2048)."""
        t = Pol6Terms.load()
        self.assertGreater(t.piece_front_end_s(0.011, 11), 0.0349)
        self.assertGreater(t.piece_front_end_s(0.0132, 23), 0.0441)
        self.assertLess(pol4_fe(0.011, False), 0.0349)


# --------------------------------------------------------------------- Part A's verdict on record
class TestPartAVerdictIsRecorded(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((_root() / "results/orchestration/study_pol6/pol6_terms.json")
                              .read_text())
        self.v = self.raw["partA_verdict"]

    def test_the_gap_hypothesis_is_recorded_as_contradicted_as_an_explanation(self):
        self.assertIn("CONTRADICTED", self.v["verdict"])

    def test_the_gaps_are_recorded_as_real_even_though_they_do_not_explain_the_error(self):
        g = self.v["gaps_are_real"]
        self.assertGreater(g["n_gaps"], 1000)
        self.assertGreater(g["gap_s_median"], 0.0)
        self.assertEqual(g["n_gaps_with_any_step"], g["n_gaps_with_other_work"])

    def test_the_busy_position_carries_most_of_the_over_prediction(self):
        pos = self.v["where_the_over_prediction_is"]["by_position_of_the_background_first_token"]
        self.assertGreater(pos["busy"]["over_s"], pos["gap"]["over_s"])
        self.assertGreater(pos["busy"]["over_s"],
                           0.75 * sum(p["over_s"] for p in pos.values()))

    def test_the_error_is_in_the_with_arm_not_the_without_arm(self):
        pos = self.v["where_the_over_prediction_is"]["by_position_of_the_background_first_token"]
        self.assertGreater(abs(pos["busy"]["err_with_s"]), 10 * abs(pos["busy"]["err_without_s"]))

    def test_mono_is_the_negative_control_and_has_the_mechanism_absent(self):
        mc = self.v["leading_alternative"]["negative_control_mono11k"]
        self.assertEqual(mc["other_prefill_tokens_in_piece_steps_median"], 0.0)
        self.assertEqual(mc["max_ctx_req_in_piece_steps_median"], 1.0)
        self.assertEqual(mc["steps_per_piece_measured_median"],
                         mc["steps_per_piece_pol4_median"])
        self.assertEqual(mc["measured_gap_total_s_median"], 0.0)
        self.assertLess(mc["imposed_delay_ratio_ttft_median"], 1.2)

    def test_the_chained_actions_have_the_mechanism_present(self):
        for k in ("fit_evidence_piece1024", "fit_evidence_piece2048"):
            e = self.v["leading_alternative"][k]
            self.assertGreater(e["steps_per_piece_measured_median"],
                               e["steps_per_piece_pol4_median"])
            self.assertGreater(e["other_prefill_tokens_in_piece_steps_median"], 0)
            self.assertGreater(e["imposed_delay_ratio_ttft_median"], 1.5)

    def test_pol4_already_reproduces_most_of_the_measured_gap(self):
        for k in ("fit_evidence_piece1024", "fit_evidence_piece2048"):
            e = self.v["leading_alternative"][k]
            share = e["pol4_gap_total_s_median"] / e["measured_gap_total_s_median"]
            self.assertGreater(share, 0.5, "pol4 is not treating the chain as contiguous")

    def test_pol4_gets_the_chain_span_right(self):
        for k in ("fit_evidence_piece1024", "fit_evidence_piece2048"):
            e = self.v["leading_alternative"][k]
            r = e["pol4_chain_span_s_median"] / e["measured_chain_span_s_median"]
            self.assertLess(abs(r - 1.0), 0.05)


# --------------------------------------------------------------------- the diagnosis is FIT only
class TestDiagnosisIsFitOnly(unittest.TestCase):
    def test_the_recorded_run_used_zero_holdout_trials(self):
        d = json.loads((_root() / "results/orchestration/study_pol6/pol6_partA_gap.json")
                       .read_text())
        self.assertEqual(d["holdout_audit"]["split"], "fit")
        self.assertEqual(d["holdout_audit"]["holdout_trials_used"], 0)
        self.assertIn("DERIVED", d["label"])
        self.assertIn("FIT", d["label"])

    def test_the_step_duration_is_the_consecutive_time_difference_not_elapsed_ms(self):
        """`elapsed_ms` is not the step's wall duration: on a monolithic 11k prefill its median
        is 0.03 ms. The regression this guards against produced a 3e-05 s median step."""
        src = (_root() / "experiments/orchestration/policy/diagnose_pol6_gap.py").read_text()
        self.assertIn("def dur(self, i: int)", src)
        self.assertIn("self.t[i] - self.t[i - 1]", src)
        d = json.loads((_root() / "results/orchestration/study_pol6/pol6_partA_gap.json")
                       .read_text())
        med = d["chained"]["by_action"]["piece1024"]["step_dur_median_s"]["median"]
        self.assertGreater(med, 0.01)


# --------------------------------------------------------------------- the ENG1e loader stub
SYNTH = [
    # trial t1: the action "a0" prefills over TWO steps and shares the second with "bg1".
    dict(trial="t1", step=0, t=100.0, dur_s=0.10, holdout=False,
         members=[dict(rid="a0", new_tokens=600, images=6)]),
    dict(trial="t1", step=1, t=100.1, dur_s=0.09, holdout=False,
         members=[dict(rid="a0", new_tokens=424, images=5),
                  dict(rid="bg1", new_tokens=378, images=4)]),
    dict(trial="t1", step=2, t=100.2, dur_s=0.02, holdout=False,
         members=[dict(rid="a0", new_tokens=0, decoding=True),
                  dict(rid="bg1", new_tokens=0, decoding=True)]),
    # one HOLDOUT step, which must never be constructed on a fit read.
    dict(trial="h1", step=0, t=200.0, dur_s=0.10, holdout=True,
         members=[dict(rid="ha0", new_tokens=1024, images=11)]),
]


class TestEng1eLoader(unittest.TestCase):
    def test_the_required_fields_are_declared_before_the_schema_is_committed(self):
        self.assertEqual(e1e.REQUIRED_STEP_FIELDS, ("t", "step", "members"))
        self.assertEqual(e1e.REQUIRED_MEMBER_FIELDS, ("rid", "new_tokens"))

    def test_eng1e_is_not_committed_yet_so_the_default_path_refuses_to_guess(self):
        self.assertFalse(e1e.eng1e_is_committed())
        with self.assertRaises(e1e.SchemaNotCommitted):
            e1e.load_membership()

    def test_the_holdout_is_refused_without_authorization(self):
        with self.assertRaises(e1e.HoldoutFenced):
            e1e.parse_rows(SYNTH, split="holdout")

    def test_a_fit_read_constructs_no_holdout_step(self):
        steps, audit = e1e.parse_rows(SYNTH, split="fit")
        self.assertEqual(audit["n_holdout_rows"], 1)
        self.assertEqual(audit["holdout_steps_built"], 0)
        self.assertEqual(len(steps), 3)
        self.assertTrue(all(not s.holdout for s in steps))
        self.assertNotIn("ha0", {str(m["rid"]) for s in steps for m in s.members})

    def test_an_authorized_holdout_read_returns_only_holdout_steps(self):
        steps, audit = e1e.parse_rows(SYNTH, split="holdout", authorization="test only")
        self.assertEqual(len(steps), 1)
        self.assertTrue(all(s.holdout for s in steps))
        self.assertEqual(audit["authorization"], "test only")

    def test_a_row_missing_a_required_field_is_refused(self):
        bad = [dict(trial="t1", t=1.0, holdout=False,
                    members=[dict(rid="a0", new_tokens=1)])]
        with self.assertRaises(ValueError):
            e1e.parse_rows(bad, split="fit")
        worse = [dict(trial="t1", step=0, t=1.0, holdout=False, members=[dict(rid="a0")])]
        with self.assertRaises(ValueError):
            e1e.parse_rows(worse, split="fit")

    def test_steps_per_request_is_measured_not_derived(self):
        steps, _ = e1e.parse_rows(SYNTH, split="fit")
        self.assertEqual(e1e.steps_per_request(steps), {"a0": 2, "bg1": 1})

    def test_the_merge_rate_counts_only_steps_the_action_prefilled_in(self):
        steps, _ = e1e.parse_rows(SYNTH, split="fit")
        m = e1e.merge_rate(steps, ["a0"])
        self.assertEqual(m["n_action_steps"], 2)
        self.assertEqual(m["n_shared_steps"], 1)
        self.assertAlmostEqual(m["shared_fraction"], 0.5)
        self.assertEqual(m["other_prefill_tokens"], 378)
        self.assertTrue(m["measured"])

    def test_other_prefill_tokens_is_per_step_and_excludes_decodes(self):
        steps, _ = e1e.parse_rows(SYNTH, split="fit")
        by_step = {s.step: s for s in steps}
        self.assertEqual(by_step[0].other_prefill_tokens("a0"), 0)
        self.assertEqual(by_step[1].other_prefill_tokens("a0"), 378)
        self.assertEqual(by_step[2].n_prefilling(), 0)
        self.assertEqual(len(by_step[2].decoding()), 2)

    def test_a_jsonl_file_round_trips_through_the_loader(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            for r in SYNTH:
                fh.write(json.dumps(r) + "\n")
            p = fh.name
        steps, audit = e1e.load_membership(split="fit", path=p)
        self.assertEqual(len(steps), 3)
        self.assertEqual(audit["source"], p)
        with self.assertRaises(e1e.HoldoutFenced):
            e1e.load_membership(split="holdout", path=p)


# --------------------------------------------------------------------- the freeze is intact
class TestFrozenFilesUntouched(unittest.TestCase):
    def test_every_t0b_freeze_md5_still_matches(self):
        import hashlib
        root = _root()
        raw = json.loads((root / "results/orchestration/study_t0b/t0b_freeze.json").read_text())
        bad = []
        for rel, want in sorted(raw["files"].items()):
            got = hashlib.md5((root / rel).read_bytes()).hexdigest()
            if got != want:
                bad.append((rel, want, got))
        self.assertEqual(bad, [], "StudyPOL6 must not touch a file in the T0b freeze")
        self.assertEqual(len(raw["files"]), 12)


if __name__ == "__main__":
    unittest.main()
