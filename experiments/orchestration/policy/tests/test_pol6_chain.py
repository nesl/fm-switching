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

    def test_the_default_path_refuses_to_guess_whether_or_not_eng1e_is_committed(self):
        # StudyENG1e landed on origin/main after this test was written, so the uncommitted
        # branch is exercised against an empty root instead of the repo's own state.
        with tempfile.TemporaryDirectory() as empty:
            self.assertFalse(e1e.eng1e_is_committed(Path(empty)))
        self.assertTrue(e1e.eng1e_is_committed())
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


# --------------------------------------------------------------------- the merge addendum
class TestMergeAddendum(unittest.TestCase):
    """StudyPOL6 Part A section 11: pol4 DOES merge background prefills into a piece's step, more
    often than the engine does. These pin the corrected claim so the wrong one cannot return."""

    def setUp(self):
        self.d = json.loads(
            (_root() / "results/orchestration/study_pol6/pol6_partA_merge_addendum.json")
            .read_text())

    def test_pol4_merges_on_most_chained_piece_steps(self):
        by = self.d["eng1c_chained"]["by_action"]
        self.assertGreater(by["piece1024"]["shared_fraction"], 0.5)
        self.assertGreater(by["piece2048"]["shared_fraction"], 0.6)

    def test_pol4_merges_more_often_than_the_engine_does(self):
        """The engine's derived figures from the Part A diagnosis: 8 of 20 piece1024 steps and
        5.5 of 11.5 piece2048 steps carry other prefill tokens."""
        a = json.loads((_root() / "results/orchestration/study_pol6/pol6_partA_gap.json")
                       .read_text())["chained"]["by_action"]
        by = self.d["eng1c_chained"]["by_action"]
        for act in ("piece1024", "piece2048"):
            engine = (a[act]["n_piece_steps_other_prefill"]["median"]
                      / a[act]["n_piece_steps"]["median"])
            self.assertGreater(by[act]["shared_fraction"], engine)

    def test_pol4_admits_a_wider_batch_than_the_engine_was_ever_seen_to(self):
        a = json.loads((_root() / "results/orchestration/study_pol6/pol6_partA_gap.json")
                       .read_text())["chained"]["by_action"]
        by = self.d["eng1c_chained"]["by_action"]
        for act in ("piece1024", "piece2048"):
            self.assertGreater(by[act]["max_prefilling_in_an_action_step"],
                               a[act]["max_ctx_req_in_piece_steps"]["median"])

    def test_the_addendum_read_no_holdout_of_either_collection(self):
        self.assertEqual(self.d["holdout_audit"]["eng1c"]["split"], "fit")
        self.assertEqual(self.d["holdout_audit"]["eng1c"]["holdout_trials_used"], 0)
        self.assertEqual(self.d["holdout_audit"]["eng1d"]["split"], "fit")

    def test_the_superseded_wording_is_kept_rather_than_erased(self):
        raw = json.loads((_root() / "results/orchestration/study_pol6/pol6_terms.json")
                         .read_text())
        la = raw["partA_verdict"]["leading_alternative"]
        self.assertIn("never be merged", la["statement_erratum"]["was"])
        self.assertNotIn("never be merged", la["statement"])
        self.assertIn("H-overmerge", la["name"])
        self.assertIn("ERRATUM", raw["partA_verdict"]["erratum"])

    def test_the_wrong_claim_is_not_left_uncorrected_anywhere(self):
        for rel in ("reports/study_pol6_chain.md",
                    "experiments/orchestration/policy/pol6_engine.py"):
            text = (_root() / rel).read_text()
            if "never lets a background prefill" in text or "never be merged" in text:
                self.assertIn("ERRATUM", text, "%s states the wrong claim unmarked" % rel)

    def test_the_eng1d_input_is_reported_separately_and_differs(self):
        """ENG1d's bytes-carrying mono11k never merges in pol4 either, so the two inputs are not
        interchangeable and the ENG1c-versus-ENG1d puzzle is a real one."""
        self.assertEqual(self.d["eng1d"]["by_action"]["mono11k"]["shared_fraction"], 0.0)
        self.assertLess(self.d["eng1d"]["by_action"]["piece1024"]["shared_fraction"],
                        self.d["eng1c_chained"]["by_action"]["piece1024"]["shared_fraction"])


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


ENG1E_SCRATCH = Path("/tmp/claude-1001/-home-pragya-Desktop-FM-switching/"
                     "8ab3f7e8-2a5d-4e65-8ff9-c6ae1f12519b/scratchpad/eng1e_b80b3b9")
PARTB_SCORE = "results/orchestration/study_pol6/pol6_partB_fit_score.json"
PARTB_DIAG = "results/orchestration/study_pol6/pol6_partB_diagnosis.json"


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


class TestPartBCommittedSchema(unittest.TestCase):
    """StudyENG1e's schema is fixed by its report section 1.1; the adapter must follow it."""

    ROW = dict(i=7, t0=100.0, el=50.0, t1=100.06, ts=99.5, tr=99.9,
               r=[["chatcmpl-abc-0011aabb", 1024, "p", 0, 11],
                  ["chatcmpl-bg9-0022ccdd", 1, "d", 378, 0]])

    def test_the_committed_field_list_is_recorded_so_a_rename_is_caught(self):
        self.assertEqual(e1e.COMMITTED_STEP_FIELDS, ("i", "t0", "el", "t1", "ts", "tr", "r"))
        self.assertEqual(e1e.COMMITTED_MEMBER_POSITIONS[0], "rid")

    def test_a_row_missing_a_committed_field_is_refused_not_guessed(self):
        bad = {k: v for k, v in self.ROW.items() if k != "ts"}
        with self.assertRaises(ValueError):
            e1e.adapt_step_row(bad)

    def test_step_end_is_t0_plus_el_and_start_is_dispatch_or_the_previous_end(self):
        """The report measured a mono first step whose el was 0.025 ms after a 1.64 s
        execute_model call, so el alone does NOT bound a step. Same trap as Part A's
        elapsed_ms."""
        a = e1e.adapt_step_row(self.ROW)
        self.assertAlmostEqual(a["t_end"], 100.0 + 0.050, places=9)
        self.assertAlmostEqual(a["t"], 99.5, places=9)          # ts, no previous step
        b = e1e.adapt_step_row(self.ROW, prev_end=99.8)
        self.assertAlmostEqual(b["t"], 99.8, places=9)          # clipped to the previous end
        self.assertGreater(a["dur_s"], b["dur_s"])

    def test_the_phase_flag_separates_prefill_from_decode(self):
        a = e1e.adapt_step_row(self.ROW)
        pre = [m for m in a["members"] if not m["decoding"]]
        dec = [m for m in a["members"] if m["decoding"]]
        self.assertEqual(len(pre), 1)
        self.assertEqual(len(dec), 1)
        self.assertEqual(pre[0]["new_tokens"], 1024)
        self.assertEqual(pre[0]["enc_inputs"], 11)


@unittest.skipUnless(ENG1E_SCRATCH.exists(), "StudyENG1e inputs not extracted")
class TestPartBHoldoutFenceOnTheRealSplit(unittest.TestCase):
    """The fence must hold on the COMMITTED split file, not only on a synthetic example."""

    def setUp(self):
        self._old = e1e.ENG1E_ROOT
        e1e.ENG1E_ROOT = ENG1E_SCRATCH

    def tearDown(self):
        e1e.ENG1E_ROOT = self._old

    def test_the_real_split_reserves_five_trials_per_cell(self):
        sp = e1e.holdout_split()
        self.assertEqual(sp["n_cells"], 12)
        self.assertEqual(sp["n_holdout_trials"], 60)
        self.assertTrue(all(len(v) == 5 for v in sp["holdout"].values()))

    def test_loading_the_holdout_without_authorization_raises(self):
        with self.assertRaises(e1e.HoldoutFenced):
            e1e.load_eng1e_trials("holdout")

    def test_the_fit_load_builds_no_holdout_trial_and_matches_the_split_file(self):
        trials, audit = e1e.load_eng1e_trials("fit")
        self.assertEqual(audit["holdout_trials_built"], 0)
        self.assertFalse(any(t.holdout for t in trials))
        self.assertEqual(audit["n_holdout_trials_in_record"],
                         audit["n_holdout_trials_in_split_file"])
        self.assertEqual(len(trials), 360)


class TestPartBLeavesPol6Unadopted(unittest.TestCase):
    """The regression gate fired, so nothing may be frozen or switched on."""

    def test_the_terms_file_still_carries_no_fitted_coefficient(self):
        raw = json.loads((_repo() / "results/orchestration/study_pol6/pol6_terms.json")
                         .read_text())
        self.assertEqual(raw["coef"], {})
        self.assertEqual(int(raw["holdout_trials_used"]), 0)

    def test_the_measured_window_is_recorded_as_rejected_not_as_a_coefficient(self):
        raw = json.loads((_repo() / "results/orchestration/study_pol6/pol6_terms.json")
                         .read_text())
        w = raw["partB"]["measured_handover_window"]
        self.assertIn("REJECTED", w["status"])
        self.assertTrue(w["piece_handover_s"])

    def test_every_flag_including_the_new_one_is_off_by_default(self):
        c = Pol6Config()
        self.assertFalse(c.any_on())
        self.assertFalse(c.measured_handover)

    def test_the_new_flag_is_counted_as_on_when_set(self):
        self.assertTrue(Pol6Config(measured_handover=True).any_on())


@unittest.skipUnless((Path(__file__).resolve().parents[4] / PARTB_SCORE).exists(),
                     "Part B score not produced")
class TestPartBRegressionStop(unittest.TestCase):

    def setUp(self):
        self.d = json.loads((_repo() / PARTB_SCORE).read_text())

    def test_the_regression_stop_is_recorded_as_fired(self):
        self.assertTrue(self.d["regression_stop"]["fired"])
        self.assertIn("NOT frozen", self.d["regression_stop"]["consequence"])

    def test_it_fired_on_criterion_iii_and_not_on_ranking(self):
        g = self.d["regression_stop"]["detail"]["latency"]
        self.assertTrue(g["criterion_iii"]["worse"])
        self.assertFalse(g["criterion_ii"]["worse"])

    def test_criterion_i_improved_which_is_why_the_term_is_recorded_at_all(self):
        a = self.d["models"]["pol4"]["latency"]["criterion_i"]["fraction"]
        b = self.d["models"]["pol6"]["latency"]["criterion_i"]["fraction"]
        self.assertGreater(b, a)

    def test_no_holdout_trial_was_scored(self):
        self.assertEqual(self.d["loader_audit"]["holdout_trials_built"], 0)
        self.assertEqual(self.d["loader_audit"]["split"], "fit")


@unittest.skipUnless((Path(__file__).resolve().parents[4] / PARTB_DIAG).exists(),
                     "Part B diagnosis not produced")
class TestPartBDiagnosisSupersedesPartA(unittest.TestCase):

    def setUp(self):
        self.d = json.loads((_repo() / PARTB_DIAG).read_text())

    def test_the_engine_runs_every_piece_in_one_step_and_pol4_already_does(self):
        """Part A derived 1.75 and 1.92 steps per piece by subtraction. It is 1.0, measured."""
        chains = [v for v in self.d["per_cell"].values() if v["action"] != "mono"]
        self.assertEqual(len(chains), 16)
        for v in chains:
            self.assertEqual(v["a_step_granularity"]["measured_median"], 1.0)
            self.assertEqual(v["a_step_granularity"]["measured_max"], 1.0)
            self.assertEqual(v["a_step_granularity"]["pol4_median"], 1.0)

    def test_part_a_s_derived_merge_figure_is_marked_superseded(self):
        self.assertIn("SUPERSEDED", self.d["eng1c_vs_eng1d"]["part_a_claim_status"])

    def test_the_structural_rule_is_recorded_as_rejected_on_fit(self):
        r = self.d["rejected_rule"]
        self.assertEqual(r["verdict"], "REJECTED ON FIT")
        self.assertGreater(r["result_on_fit"]["chain_ratio_with_rule"],
                           r["result_on_fit"]["chain_ratio_pol4"])

    def test_none_of_the_three_candidates_is_the_driver(self):
        w = self.d["which_drives_it"]
        for k in ("a_step_granularity", "b_in_step_merging", "c_encoder_budget"):
            self.assertTrue(w[k].startswith("NOT the driver"))
        self.assertIn("HAND-OVER WINDOW", w["what_is"])

    def test_the_mode_difference_is_the_front_end_and_not_the_scheduling(self):
        mc = self.d["mode_comparison"]
        self.assertEqual(mc["steps_per_piece"]["B"]["median"], 1.0)
        self.assertEqual(mc["steps_per_piece"]["A"]["median"], 1.0)
        self.assertGreater(mc["handover_window_s"]["A"]["median"],
                           mc["handover_window_s"]["B"]["median"])


if __name__ == "__main__":
    unittest.main()
