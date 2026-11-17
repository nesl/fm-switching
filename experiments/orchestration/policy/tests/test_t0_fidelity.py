"""StudyT0-fidelity: tests for the measured engine model, the replay and the one-shot fence.

These do not evaluate T0. They check that the engine model reproduces StudyENG1's own committed
solo measurements, that no coefficient is hard-coded in the module, that a trial is reconstructed
from the record the way the measurement defined it, and that the one-shot holdout mode cannot be
run twice, without authorization, or against an edited model.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from policy import trace_replay as tr
from policy.eng1_engine import (CHUNK_TOKENS, Eng1Engine, EngineSim, SimRequest, StepModel,
                                TOKENS_PER_FRAME, frontend_service_s)
from policy.engine import Request
from policy.t0_harness import (FreezeViolation, FrozenState, HoldoutRefused, T0Harness, md5_of)


def _sim() -> EngineSim:
    return EngineSim(step=StepModel.load())


class TestStepModelProvenance(unittest.TestCase):
    def test_the_model_is_loaded_and_states_its_fit_data(self):
        sm = StepModel.load()
        self.assertIn("HOLDOUT", sm.raw["fit_data"])
        self.assertIn("Part A", sm.raw["fit_data"])
        self.assertGreater(sm.raw["n"], 5000)

    def test_no_coefficient_is_hard_coded_in_the_module(self):
        from policy import eng1_engine
        src = Path(eng1_engine.__file__).read_text()
        for name in StepModel.load().coef:
            self.assertNotIn('"%s"' % name + " =", src)
        for value in ("28.69", "0.07403", "8.6218", "18.148"):
            self.assertNotIn(value, src,
                             "a fitted coefficient must be read from the JSON, not typed here")

    def test_a_model_file_without_stated_provenance_is_refused(self):
        raw = json.loads(Path(StepModel.load().path).read_text())
        raw.pop("fit_data")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json"
            p.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                StepModel.load(p)


class TestSoloCrossChecks(unittest.TestCase):
    """StudyENG1's own solo measurements. The tolerance is the 2x of CLAUDE.md's consistency
    check, not a tuned window: these are cross-checks, not a fit."""

    def _ttft(self, **kw) -> float:
        r = SimRequest(rid="x", t_submit=0.0, **kw)
        return _sim().run([r])["per_request"]["x"]["ttft_s"]

    def test_monolithic_11k(self):
        p = self._ttft(prompt_tokens=11_043, cached_tokens=0, body_mb=21.8755, n_images=122,
                       out_tokens=2)
        self.assertLess(abs(p / 2.673 - 1.0), 0.5, "predicted %.3f vs measured 2.673 s" % p)

    def test_piece_2048_on_an_11k_prefix(self):
        p = self._ttft(prompt_tokens=13_094, cached_tokens=11_008, body_mb=5.3006, n_images=23,
                       out_tokens=1)
        self.assertLess(abs(p / 0.564 - 1.0), 0.5, "predicted %.3f vs measured 0.564 s" % p)

    def test_episodic_n1(self):
        p = self._ttft(prompt_tokens=378, cached_tokens=0, body_mb=0.4433, n_images=1,
                       out_tokens=2)
        self.assertLess(abs(p / 0.138 - 1.0), 0.5, "predicted %.4f vs measured 0.135 to "
                                                   "0.141 s" % p)

    def test_the_front_end_has_two_measured_regimes_and_the_busy_one_is_cheaper(self):
        self.assertAlmostEqual(frontend_service_s(0.0, False), 0.0296)
        self.assertAlmostEqual(frontend_service_s(0.0, True), 0.0069)
        self.assertLess(frontend_service_s(1.0, True), frontend_service_s(1.0, False))


class TestSchedulingStructure(unittest.TestCase):
    def test_a_long_prefill_holds_the_partial_slot_alone(self):
        big = SimRequest(rid="big", t_submit=0.0, prompt_tokens=20_000, body_mb=0.0,
                         n_images=0, out_tokens=1)
        small = SimRequest(rid="small", t_submit=0.0, prompt_tokens=100, body_mb=0.0,
                           n_images=0, out_tokens=1)
        res = _sim().run([big, small])
        for s in res["steps"]:
            if "big" in s["prefilling"]:
                self.assertEqual(s["prefilling"], ["big"])
        self.assertGreater(res["per_request"]["small"]["ttft_s"],
                           res["per_request"]["big"]["ttft_s"] * 0.5)

    def test_short_prefills_share_one_step(self):
        reqs = [SimRequest(rid="r%d" % i, t_submit=0.0, prompt_tokens=378, body_mb=0.0,
                           n_images=1, out_tokens=1) for i in range(4)]
        res = _sim().run(reqs)
        batched = [s for s in res["steps"] if len(s["prefilling"]) > 1]
        self.assertTrue(batched, "four 378-token prefills must share a step (H-step)")

    def test_the_batch_never_exceeds_the_step_token_budget(self):
        reqs = [SimRequest(rid="r%d" % i, t_submit=0.0, prompt_tokens=3000, body_mb=0.0,
                           n_images=0, out_tokens=1) for i in range(6)]
        for s in _sim().run(reqs)["steps"]:
            self.assertLessEqual(s["new_tokens"], CHUNK_TOKENS)

    def test_the_engine_protocol_flags_an_extrapolated_prefill(self):
        e = Eng1Engine.load()
        ok = e.predict(Request(kind="rc_piece", device="d", tokens=2048), concurrent=0)
        big = e.predict(Request(kind="rc_piece", device="d", tokens=30_000), concurrent=0)
        self.assertTrue(ok.in_sample)
        self.assertFalse(big.in_sample)
        self.assertIn("NOT IN SAMPLE", big.basis)


class TestTraceReplay(unittest.TestCase):
    def test_a_frame_is_90_tokens_which_is_the_committed_definition(self):
        self.assertEqual(TOKENS_PER_FRAME, 90)

    def test_the_loss_classes_use_the_eng1b_tolerance(self):
        self.assertEqual(tr.loss_class(0, 10_000), "none")
        self.assertEqual(tr.loss_class(32, 10_000), "none")
        self.assertEqual(tr.loss_class(5_000, 10_000), "partial")
        self.assertEqual(tr.loss_class(10_000, 10_000), "total")
        self.assertEqual(tr.loss_class(9_980, 10_000), "total")

    def test_the_eng1b_prediction_is_pool_bookkeeping_only(self):
        trial = dict(prefix=10_389, alloc_before_sched=33_902)
        r = tr.predict_eng1b_trial(trial, 62_944)
        self.assertEqual(r["predicted_lost_tokens"], 0)
        self.assertEqual(r["predicted_class"], "none")
        self.assertEqual(r["free_pool_tokens"], 62_944 - 10_389)
        trial2 = dict(prefix=10_389, alloc_before_sched=62_944)
        r2 = tr.predict_eng1b_trial(trial2, 62_944)
        self.assertEqual(r2["predicted_lost_tokens"], 10_389)
        self.assertEqual(r2["predicted_class"], "total")


class TestComparedRequestSet(unittest.TestCase):
    """The definition CLAUDE.md's consistency check 1 caught: StudyENG1 section 9's published
    per-cell table sums over the EPISODIC background stream only. In the W25 cells the warm
    sessions run and occupy the engine but are not in the sum."""

    def test_the_compared_set_is_the_episodic_stream(self):
        self.assertEqual(tuple(tr.COMPARED_KINDS), ("episodic",))
        self.assertIn("warm_append", tr.BACKGROUND_KINDS)

    def test_the_w25_cells_reproduce_the_published_medians(self):
        import statistics
        trials = [t for t in tr.load_part_c_trials()
                  if not t.holdout and t.load == "W25" and t.action == "mono11k"]
        self.assertEqual(len(trials), 14)
        med = statistics.median([tr.measured_imposed_delay_s(t)["total_s"] for t in trials])
        self.assertAlmostEqual(med, 16.9, places=1,
                               msg="StudyENG1 section 9 publishes 16.9 s for W25 mono11k")
        med_all = statistics.median([tr.measured_imposed_delay_s(t, tr.BACKGROUND_KINDS)
                                     ["total_s"] for t in trials])
        self.assertGreater(med_all, 20.0,
                           "including the warm sessions must NOT reproduce the published value, "
                           "which is why the compared set is a stated definition")


class TestSecondaryRescoreGuard(unittest.TestCase):
    """The secondary criterion (ii) re-score must prove it is re-scoring the SAME frozen
    predictions, and must refuse rather than quietly produce a number if it cannot."""

    def test_it_refuses_when_it_cannot_reproduce_the_registered_values(self):
        import json as _json
        import tempfile as _tf
        from policy.run_t0 import holdout_secondary_criterion_ii
        trials = [t for t in tr.load_part_c_trials() if t.holdout][:3]
        self.assertEqual(len(trials), 3)
        doctored = dict(trials=[dict(key=t.key(), predicted_delay_s=-999.0,
                                     measured_delay_s=-999.0) for t in trials])
        with _tf.TemporaryDirectory() as d:
            p = Path(d) / "registered.json"
            p.write_text(_json.dumps(doctored))
            with self.assertRaises(RuntimeError):
                holdout_secondary_criterion_ii(trials, _sim(), p)

    def test_it_refuses_when_a_trial_is_absent_from_the_registered_file(self):
        import json as _json
        import tempfile as _tf
        from policy.run_t0 import holdout_secondary_criterion_ii
        trials = [t for t in tr.load_part_c_trials() if t.holdout][:2]
        with _tf.TemporaryDirectory() as d:
            p = Path(d) / "registered.json"
            p.write_text(_json.dumps(dict(trials=[])))
            with self.assertRaises(RuntimeError):
                holdout_secondary_criterion_ii(trials, _sim(), p)


class TestOneShotFence(unittest.TestCase):
    def _frozen(self, d: Path) -> FrozenState:
        root = Path(__file__).resolve().parents[4]
        return FrozenState.freeze(root, ["results/cost/study_eng1/eng1_step_model.json"],
                                  note="test")

    def test_the_default_run_still_refuses_a_holdout_split(self):
        with self.assertRaises(HoldoutRefused):
            T0Harness().run(dict(split="holdout", cases=[]))
        with self.assertRaises(HoldoutRefused):
            T0Harness().run(dict(split="something-new", cases=[]))

    def test_the_one_shot_run_needs_an_authorization(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with self.assertRaises(HoldoutRefused):
                T0Harness().run_holdout_once(self._frozen(d), d / "r.json", d / "l.log",
                                             lambda: dict(ok=True))

    def test_the_one_shot_run_refuses_a_second_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = self._frozen(d)
            out = T0Harness().run_holdout_once(f, d / "r.json", d / "l.log",
                                               lambda: dict(ok=True), authorization="a test")
            self.assertTrue((d / "r.json").exists())
            self.assertIn("_one_shot", out)
            self.assertEqual(len((d / "l.log").read_text().strip().splitlines()), 1)
            with self.assertRaises(HoldoutRefused):
                T0Harness().run_holdout_once(f, d / "r.json", d / "l.log",
                                             lambda: dict(ok=True), authorization="a test")

    def test_the_one_shot_run_refuses_an_edited_model(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = self._frozen(d)
            f.files["results/cost/study_eng1/eng1_step_model.json"] = "0" * 32
            with self.assertRaises(FreezeViolation):
                T0Harness().run_holdout_once(f, d / "r.json", d / "l.log",
                                             lambda: dict(ok=True), authorization="a test")
            self.assertFalse((d / "r.json").exists())

    def test_a_refused_run_never_calls_the_computation(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            f = self._frozen(d)
            f.files["results/cost/study_eng1/eng1_step_model.json"] = "0" * 32
            with self.assertRaises(FreezeViolation):
                T0Harness().run_holdout_once(f, d / "r.json", d / "l.log",
                                             lambda: calls.append(1) or dict(),
                                             authorization="a test")
        self.assertEqual(calls, [])

    def test_the_freeze_records_a_real_md5_and_the_git_head(self):
        with tempfile.TemporaryDirectory() as d:
            f = self._frozen(Path(d))
        root = Path(__file__).resolve().parents[4]
        rel = "results/cost/study_eng1/eng1_step_model.json"
        self.assertEqual(f.files[rel], md5_of(root / rel))
        self.assertEqual(len(f.git["head"]), 40)
        self.assertTrue(f.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
