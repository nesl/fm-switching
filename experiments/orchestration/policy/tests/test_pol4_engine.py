"""StudyPOL4-engine: tests for the three new engine-model terms and the flag that selects them.

These do not evaluate T0b. They check that each new term is read from the committed JSON and not
typed into the module, that each one is neutral exactly where the measurement says it should be,
that each reproduces the StudyENG1 measurement it was fitted on, that the OLD model is still
reachable and still bit-identical, and that the spent Part C HOLDOUT triples are excluded by an
assertion rather than by convention.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from policy import trace_replay as tr
from policy.eng1_engine import (CHUNK_TOKENS, ENGINE_MODELS, Eng1Engine, EngineSim, POL4_COEF_NAMES,
                                Pol4Terms, SimRequest, StepModel, make_sim)
from policy.engine import Request

_TRIALS = None


def _fit_trials():
    """The Part C FIT trials, loaded once: the record is 43 MB."""
    global _TRIALS
    if _TRIALS is None:
        from policy.run_pol4 import split_fit_trials
        _TRIALS = split_fit_trials()
    return _TRIALS


class TestTermProvenance(unittest.TestCase):
    def test_the_terms_are_loaded_and_state_that_no_holdout_trial_entered_them(self):
        t = Pol4Terms.load()
        self.assertEqual(int(t.raw["holdout_trials_used"]), 0)
        self.assertIn("exclude", t.raw["holdout_exclusion"])
        for name in POL4_COEF_NAMES:
            self.assertIn(name, t.coef)

    def test_a_terms_file_that_does_not_state_zero_holdout_use_is_refused(self):
        raw = json.loads(Path(Pol4Terms.load().path).read_text())
        raw["holdout_trials_used"] = 3
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                Pol4Terms.load(p)

    def test_a_terms_file_missing_a_coefficient_is_refused(self):
        raw = json.loads(Path(Pol4Terms.load().path).read_text())
        raw["coef"].pop("host_kv_transfer_gb_per_s")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                Pol4Terms.load(p)

    def test_no_fitted_pol4_number_is_typed_into_the_module(self):
        """The StudyT0-fidelity contract, extended rather than replaced: every coefficient of
        every term must come from a committed JSON."""
        from policy import eng1_engine
        src = Path(eng1_engine.__file__).read_text()
        terms = Pol4Terms.load()
        for name, value in terms.coef.items():
            self.assertNotIn('"%s" = ' % name, src)
            if name == "host_kv_bytes_per_token":
                continue          # 262144 is 256 KiB, a block size, and is still not typed here
            for digits in (6, 4):
                needle = ("%%.%df" % digits) % value
                if needle.rstrip("0").rstrip(".") in ("0", "1", "-0"):
                    continue
                self.assertNotIn(needle, src,
                                 "fitted value %s of %s must be read from the JSON" % (needle,
                                                                                        name))

    def test_the_step_model_itself_was_not_refitted(self):
        sm = StepModel.load()
        self.assertIn("Part C (incl. HOLDOUT) not used", sm.raw["fit_data"])
        self.assertEqual(sm.raw["n"], 5974)


class TestFlagSelectsTheModel(unittest.TestCase):
    def test_the_three_configurations_exist_and_differ(self):
        self.assertEqual(ENGINE_MODELS, ("eng1", "pol4", "pol4_nobatch"))
        self.assertIsNone(make_sim("eng1").pol4)
        self.assertIsNotNone(make_sim("pol4").pol4)
        self.assertEqual(make_sim("pol4_nobatch").pol4.coef["batch_prefill_gain_exponent"], 0.0)
        self.assertNotEqual(make_sim("pol4").pol4.coef["batch_prefill_gain_exponent"], 0.0)
        self.assertEqual([make_sim(m).model_name() for m in ENGINE_MODELS], list(ENGINE_MODELS))

    def test_an_unknown_flag_is_refused(self):
        for bad in ("pol5", "", "POL4", "new"):
            with self.assertRaises(ValueError):
                make_sim(bad)
        with self.assertRaises(ValueError):
            Eng1Engine.load(engine_model="pol5")
        with self.assertRaises(ValueError):
            Pol4Terms.load_for_model("pol5")

    def test_the_old_model_is_bit_identical_to_the_frozen_one(self):
        """`pol4=None` must take exactly the code path StudyT0-fidelity tested, and a NEUTRAL
        probe must be indistinguishable from it."""
        reqs = [SimRequest(rid="a", t_submit=0.0, prompt_tokens=378, n_images=1, body_mb=0.44,
                           out_tokens=2),
                SimRequest(rid="b", t_submit=0.01, prompt_tokens=11_043, n_images=122,
                           body_mb=21.88, out_tokens=2),
                SimRequest(rid="c", t_submit=0.02, prompt_tokens=378, n_images=1, body_mb=0.44,
                           out_tokens=2)]
        old = EngineSim(step=StepModel.load()).run(reqs)
        neutral = EngineSim(step=StepModel.load(), pol4=Pol4Terms.for_probe()).run(reqs)
        for rid in ("a", "b", "c"):
            self.assertAlmostEqual(old["per_request"][rid]["ttft_s"],
                                   neutral["per_request"][rid]["ttft_s"], places=12)
        self.assertEqual(old["n_steps"], neutral["n_steps"])
        self.assertTrue(all(not s["pol4"] for s in old["steps"]))

    def test_a_probe_rejects_an_unknown_coefficient(self):
        with self.assertRaises(KeyError):
            Pol4Terms.for_probe(not_a_coefficient=1.0)


class TestTermAHostKvTransfer(unittest.TestCase):
    def test_it_is_zero_without_external_tokens_and_linear_in_them(self):
        t = Pol4Terms.load()
        self.assertEqual(t.host_reload_ms(0), 0.0)
        self.assertEqual(t.host_reload_ms(-5), 0.0)
        a, b = t.host_reload_ms(5_000), t.host_reload_ms(10_000)
        fixed = t.coef["host_kv_lookup_fixed_ms"]
        self.assertAlmostEqual((b - fixed) / (a - fixed), 2.0, places=9)

    def test_it_reproduces_the_part_d_measured_transfer_time(self):
        """StudyENG1 Part D, concurrency-1 host queries: the engine's own
        kv_offload_load_time_total is 57.4 ms at about 10,968 external tokens."""
        ms = Pol4Terms.load().host_reload_ms(10_968)
        self.assertLess(abs(ms / 57.367 - 1.0), 0.5, "predicted %.2f ms against 57.37 ms" % ms)

    def test_a_reload_delays_the_reloading_request_and_a_co_scheduled_one(self):
        reqs = [SimRequest(rid="reload", t_submit=0.0, prompt_tokens=11_098,
                           cached_tokens=11_008, external_cached_tokens=11_008, body_mb=0.02,
                           n_images=1, out_tokens=2),
                SimRequest(rid="other", t_submit=0.03, prompt_tokens=378, n_images=1,
                           body_mb=0.44, out_tokens=2)]
        gpu = [SimRequest(rid=r.rid, t_submit=r.t_submit, prompt_tokens=r.prompt_tokens,
                          cached_tokens=r.cached_tokens, body_mb=r.body_mb,
                          n_images=r.n_images, out_tokens=r.out_tokens) for r in reqs]
        sim = make_sim("pol4")
        hot = sim.run(reqs)["per_request"]
        cold = sim.run(gpu)["per_request"]
        self.assertGreater(hot["reload"]["ttft_s"], cold["reload"]["ttft_s"])
        self.assertGreater(hot["other"]["ttft_s"], cold["other"]["ttft_s"],
                           "the reload must reach a co-scheduled request through step occupancy")
        # and the old model charges nothing at all, which is the gap StudyT0 found
        old = EngineSim(step=StepModel.load()).run(reqs)["per_request"]
        self.assertAlmostEqual(old["reload"]["ttft_s"],
                               EngineSim(step=StepModel.load()).run(gpu)["per_request"]
                               ["reload"]["ttft_s"], places=12)

    def test_external_tokens_can_never_exceed_cached_tokens(self):
        r = SimRequest(rid="x", t_submit=0.0, prompt_tokens=500, cached_tokens=100,
                       external_cached_tokens=10_000)
        self.assertEqual(r.external_tokens(), 100)

    def test_the_policy_facing_engine_charges_it_too(self):
        eng_old = Eng1Engine.load(engine_model="eng1")
        eng_new = Eng1Engine.load(engine_model="pol4")
        req = Request(kind="rc_piece", device="d0", tokens=90, frames=1, readiness="HOST-WARM",
                      meta=dict(cached_tokens=11_008, external_cached_tokens=11_008))
        self.assertGreater(eng_new.predict(req, concurrent=0).first_token_s,
                           eng_old.predict(req, concurrent=0).first_token_s)
        self.assertIn("host-KV reload", eng_new.predict(req, concurrent=0).basis)


class TestTermBLongColdPrefill(unittest.TestCase):
    def test_it_is_exactly_neutral_at_or_below_one_step(self):
        t = Pol4Terms.load()
        for n in (0, 1, 378, 2048, 8192):
            self.assertEqual(t.long_prefill_scale(n, CHUNK_TOKENS), 1.0)
        self.assertNotEqual(t.long_prefill_scale(8193, CHUNK_TOKENS), 1.0)

    def test_it_reduces_the_monolithic_11k_block_and_rises_with_size(self):
        t = Pol4Terms.load()
        s11 = t.long_prefill_scale(11_127, CHUNK_TOKENS)
        s28 = t.long_prefill_scale(28_035, CHUNK_TOKENS)
        self.assertLess(s11, 1.0)
        self.assertGreater(s28, s11)

    def test_the_monolithic_11k_solo_ttft_moves_toward_the_measurement(self):
        """StudyENG1 Part B solo mono11k on E0: 2.673 s. The old model predicts 2.977 s."""
        kw = dict(prompt_tokens=11_127, cached_tokens=0, body_mb=28.0065, n_images=124,
                  out_tokens=2)
        old = EngineSim(step=StepModel.load()).run(
            [SimRequest(rid="x", t_submit=0.0, **kw)])["per_request"]["x"]["ttft_s"]
        new = make_sim("pol4").run(
            [SimRequest(rid="x", t_submit=0.0, **kw)])["per_request"]["x"]["ttft_s"]
        self.assertGreater(old, 2.673)
        self.assertLess(abs(new - 2.673), abs(old - 2.673))

    def test_it_does_not_touch_a_single_step_piece(self):
        kw = dict(prompt_tokens=13_094, cached_tokens=11_008, body_mb=5.3006, n_images=23,
                  out_tokens=1)
        old = EngineSim(step=StepModel.load()).run(
            [SimRequest(rid="x", t_submit=0.0, **kw)])["per_request"]["x"]["ttft_s"]
        new = EngineSim(step=StepModel.load(),
                        pol4=Pol4Terms.for_probe(
                            long_prefill_scale_intercept=Pol4Terms.load().coef
                            ["long_prefill_scale_intercept"],
                            long_prefill_scale_per_1k_tokens=Pol4Terms.load().coef
                            ["long_prefill_scale_per_1k_tokens"])).run(
            [SimRequest(rid="x", t_submit=0.0, **kw)])["per_request"]["x"]["ttft_s"]
        self.assertAlmostEqual(old, new, places=12)


class TestTermCSubLinearBatching(unittest.TestCase):
    def test_it_is_exactly_neutral_for_a_single_prefill(self):
        t = Pol4Terms.load()
        self.assertEqual(t.batch_prefill_gain(0), 1.0)
        self.assertEqual(t.batch_prefill_gain(1), 1.0)
        self.assertNotEqual(t.batch_prefill_gain(2), 1.0)

    def test_a_zero_exponent_is_the_old_model(self):
        p = Pol4Terms.for_probe(batch_prefill_gain_exponent=0.0)
        for m in (1, 2, 4, 8, 16):
            self.assertEqual(p.batch_prefill_gain(m), 1.0)

    def test_the_fitted_sign_is_recorded_as_a_penalty_not_a_gain(self):
        """StudyPOL4's finding, asserted so it cannot be silently reversed: fitted on StudyENG1
        Part A A1's own batching ratio, the exponent is NEGATIVE, i.e. a small penalty, and the
        old model already reproduced the published anchors."""
        raw = Pol4Terms.load().raw["sub_linear_batching"]
        self.assertLess(raw["batch_prefill_gain_exponent"], 0.0)
        a = raw["reproduced_published_anchors"]
        self.assertLess(abs(a["N=1"]["ratio_t16_over_16t1"] / 0.510 - 1.0), 0.01)
        self.assertLess(abs(a["N=3"]["ratio_t16_over_16t1"] / 0.731 - 1.0), 0.01)
        implied = raw["implied_ratio_t16_over_16t1"]["N=1|k=16"]
        self.assertLess(abs(implied["old_over_measured"] - 1.0), 0.05)

    def test_it_is_monotone_in_the_number_of_prefills(self):
        t = Pol4Terms.load()
        vals = [t.batch_prefill_gain(m) for m in (2, 4, 8, 16)]
        self.assertEqual(vals, sorted(vals))

    def test_it_changes_a_shared_step_and_only_a_shared_step(self):
        probe = Pol4Terms.for_probe(
            batch_prefill_gain_exponent=Pol4Terms.load().coef["batch_prefill_gain_exponent"])
        solo = [SimRequest(rid="a", t_submit=0.0, prompt_tokens=378, n_images=1, body_mb=0.44,
                           out_tokens=2)]
        self.assertAlmostEqual(EngineSim(step=StepModel.load()).run(solo)["per_request"]["a"]
                               ["ttft_s"],
                               EngineSim(step=StepModel.load(), pol4=probe).run(solo)
                               ["per_request"]["a"]["ttft_s"], places=12)
        many = [SimRequest(rid="r%d" % i, t_submit=0.0, prompt_tokens=378, n_images=1,
                           body_mb=0.44, out_tokens=2) for i in range(8)]
        a = EngineSim(step=StepModel.load()).run(many)
        b = EngineSim(step=StepModel.load(), pol4=probe).run(many)
        self.assertNotAlmostEqual(max(v["ttft_s"] for v in a["per_request"].values()),
                                  max(v["ttft_s"] for v in b["per_request"].values()), places=6)
        self.assertTrue(any("batch_prefill_gain" in s["pol4"] for s in b["steps"]))


class TestHoldoutIsExcluded(unittest.TestCase):
    def test_the_split_is_loaded_only_to_exclude_and_the_exclusion_is_asserted(self):
        fit, audit = _fit_trials()
        self.assertEqual(audit["holdout_trials_used"], 0)
        self.assertEqual(audit["n_fit_scored"], 406)
        self.assertEqual(audit["n_holdout_excluded"], 174)
        self.assertEqual(audit["n_holdout_in_split_file"], 174)
        self.assertEqual(len(fit), 406)
        self.assertFalse(any(t.holdout for t in fit))

    def test_a_leaked_holdout_trial_would_raise(self):
        from policy.run_pol4 import split_fit_trials
        import policy.run_pol4 as rp
        trials = tr.load_part_c_trials()
        for t in trials:
            if t.holdout:
                t.holdout = False
                break
        orig = tr.load_part_c_trials
        tr.load_part_c_trials = lambda *a, **k: trials
        try:
            with self.assertRaises(AssertionError):
                split_fit_trials()
        finally:
            tr.load_part_c_trials = orig


class TestExternalTokenAttribution(unittest.TestCase):
    def test_only_the_hostreload_action_is_charged_and_w25_is_left_unattributed(self):
        fit, _ = _fit_trials()
        charged = {}
        unattributed = {}
        for t in fit:
            for mode in ("with", "without"):
                for r in t.arms[mode].action:
                    if int(r.get("_external_cached_tokens", 0) or 0) > 0:
                        charged.setdefault(t.action, 0)
                        charged[t.action] += 1
                        self.assertEqual(mode, "with")
                        self.assertLessEqual(int(r["_external_cached_tokens"]),
                                             int(r["cached_tokens"]))
            for mode in t.external_unattributed:
                unattributed.setdefault(t.load, 0)
                unattributed[t.load] += 1
        self.assertEqual(sorted(charged), ["hostreload"])
        self.assertEqual(charged["hostreload"], 56)
        self.assertEqual(sorted(unattributed), ["W25"],
                         "only the W25 cells carry host hits the record cannot attribute")

    def test_the_charged_count_matches_the_action_s_cached_tokens(self):
        fit, _ = _fit_trials()
        n = 0
        for t in fit:
            if t.action != "hostreload":
                continue
            for r in t.arms["with"].action:
                ext = int(r.get("_external_cached_tokens", 0) or 0)
                self.assertLessEqual(abs(ext - int(r["cached_tokens"])),
                                     tr.EXTERNAL_TOLERANCE_TOKENS)
                n += 1
        self.assertEqual(n, 56)


if __name__ == "__main__":
    unittest.main()
