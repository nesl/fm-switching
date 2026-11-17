"""StudyPOL3-update: one test per change, named after the decision it pins.

D56 (three tiers, both warm tiers bounded, evidence never deleted, P_host from occupancy),
D57 (per-tier score calibration with a loud failure), StudyENG1b (mechanistic prefix loss, tail
first, and the staircase kept out of the in-horizon path), and spec 8's mu estimator made an
explicit choice rather than a silent default.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from policy.tests._fixtures import (PF, coordinator, engine, fleet, job, params, piece_item,
                                    rollout)
from policy import calibration, kvpool, tiers
from policy.calibration import (CalibrationInvalid, CalibrationMissing, MonotoneMap,
                                TierCalibration, identity_for_tests, rank_across_tiers,
                                upgrade_decision)
from policy.kvpool import KVPool
from policy.params import H100NVL_KV_POOL_TOKENS, PROVENANCE, Params
from policy.readiness import tier_assignment
from policy.tiers import HostPool, TieredStore, largest_first_rule, p_host_from_occupancy


class TestD56BoundedHost(unittest.TestCase):
    def test_the_host_tier_is_bounded_and_refuses_what_does_not_fit(self):
        h = HostPool(capacity_tokens=1000)
        r = h.accept("a", 400, t=0.0)
        self.assertEqual(r["accepted_tokens"], 400)
        r = h.accept("b", 900, t=1.0)
        # 600 free, so 600 of the 900 fit once LRU has freed what it can
        self.assertEqual(h.occupancy(), 1000)
        self.assertLessEqual(r["accepted_tokens"], 900)
        self.assertGreater(sum(r["evicted"].values()) + r["accepted_tokens"], 0)

    def test_eviction_from_the_host_tier_is_a_demotion_not_a_deletion(self):
        h = HostPool(capacity_tokens=1000)
        h.accept("old", 1000, t=0.0)
        h.accept("new", 600, t=1.0)
        self.assertEqual(h.demoted_to_cold.get("old"), 600)
        self.assertEqual(h.tokens_of("old"), 400)
        self.assertEqual(h.tokens_of("new"), 600)

    def test_the_default_host_rule_is_lru_and_is_labelled_an_assumption(self):
        h = HostPool(capacity_tokens=1000)
        self.assertEqual(h.rule_name, "lru")
        self.assertIn("ASSUMPTION", h.eviction_rule_status())
        self.assertIn("StudyENG1c", h.eviction_rule_status())
        self.assertIn("ASSUMPTION", PROVENANCE["host_eviction_rule"]["note"])

    def test_the_host_rule_is_pluggable(self):
        h = HostPool(capacity_tokens=1000, eviction_rule=largest_first_rule,
                     rule_name="largest_first")
        h.accept("small", 200, t=0.0)
        h.accept("big", 800, t=1.0)
        h.accept("x", 300, t=2.0)
        self.assertEqual(h.demoted_to_cold.get("big"), 300)
        self.assertIsNone(h.demoted_to_cold.get("small"))

    def test_a_prefix_that_leaves_both_warm_tiers_is_cold_and_not_lost(self):
        pool = KVPool(capacity_tokens=4000)
        pool.put("p", 4000, 0.0, referenced=False)
        store = TieredStore(gpu=pool, host=HostPool(capacity_tokens=1000))
        pool.allocate("arrival", 4000, 1.0, store=store)
        self.assertEqual(store.host.tokens_of("p"), 1000)
        self.assertEqual(store.cold_tokens.get("p"), 3000)
        self.assertEqual(store.host.tokens_of("p") + store.cold_tokens["p"], 4000)
        self.assertEqual(store.tier_of("p"), "HOST")

    def test_the_gpu_pool_size_is_an_input_and_the_h100_value_is_only_a_named_constant(self):
        p = Params()
        self.assertEqual(p.gpu_kv_capacity_tokens, 0)
        self.assertEqual(p.host_kv_capacity_tokens, 0)
        self.assertEqual(H100NVL_KV_POOL_TOKENS, 62_944)
        self.assertIn("INPUT", PROVENANCE["gpu_kv_capacity_tokens"]["note"])


class TestD56PHostByOccupancy(unittest.TestCase):
    def test_p_host_is_no_longer_a_constant_placeholder(self):
        self.assertIsNone(Params().p_host)
        self.assertEqual(PROVENANCE["p_host"]["kind"], "COMMITTED")

    def test_with_room_it_is_the_eng1b_measurement(self):
        h = HostPool(capacity_tokens=100_000)
        r = p_host_from_occupancy(h, 10_000)
        self.assertAlmostEqual(r["p_host"], tiers.P_HOST_WITH_ROOM)
        self.assertTrue(r["measured"])
        self.assertIn("StudyENG1b", r["source"])

    def test_with_no_host_tier_it_is_zero_which_is_the_e0_server(self):
        r = p_host_from_occupancy(None, 10_000)
        self.assertEqual(r["p_host"], 0.0)
        self.assertIn("E0", r["basis"])

    def test_a_full_host_tier_lowers_it_and_flags_the_rule(self):
        h = HostPool(capacity_tokens=1000)
        h.accept("resident", 1000, t=0.0)
        r = p_host_from_occupancy(h, 10_000, prefix_id="evicted", t=1.0)
        self.assertLess(r["p_host"], tiers.P_HOST_WITH_ROOM)
        self.assertFalse(r["measured"])
        self.assertIn("ASSUMPTION", r["rule_status"])

    def test_a_full_host_tier_under_lru_pushes_the_cost_onto_the_incumbents(self):
        """The consequence of LRU, stated rather than assumed: freshly evicted blocks are the
        most recently used, so on a FULL host tier the rule admits them and demotes incumbents to
        cold. P_host for these blocks therefore stays at the measured value, the result is flagged
        unmeasured because the rule decided it, and the cost appears as cold tokens elsewhere."""
        full = HostPool(capacity_tokens=10_000)
        full.accept("incumbent", 10_000, t=0.0)
        r = p_host_from_occupancy(full, 5_000, prefix_id="evicted", t=1.0)
        self.assertAlmostEqual(r["p_host"], tiers.P_HOST_WITH_ROOM)
        self.assertFalse(r["measured"])
        self.assertAlmostEqual(r["fraction_kept"], 1.0)
        store = TieredStore(gpu=KVPool(capacity_tokens=1), host=full)
        store.demote_from_gpu({"evicted": 5_000}, 1.0)
        self.assertEqual(full.demoted_to_cold.get("incumbent"), 5_000)

    def test_it_falls_below_the_measured_value_only_when_the_blocks_do_not_fit_at_all(self):
        small = HostPool(capacity_tokens=1_000)
        fits = p_host_from_occupancy(small, 500)["p_host"]
        does_not = p_host_from_occupancy(small, 10_000, prefix_id="e", t=1.0)["p_host"]
        self.assertAlmostEqual(fits, tiers.P_HOST_WITH_ROOM)
        self.assertLess(does_not, fits)

    def test_a_float_still_pins_it_for_a_sweep(self):
        p = params(p_host=0.0)
        self.assertEqual(p.p_host_for(HostPool(capacity_tokens=10_000), 100)["p_host"], 0.0)

    def test_the_rollout_reads_p_host_from_the_bounded_host_tier(self):
        ro = rollout(p=params(gpu_kv_capacity_tokens=12_000, host_kv_capacity_tokens=1_000_000))
        f = fleet()
        f.jobs["j0"] = job(pieces=4, done=2)
        f.pending.append(piece_item(iid="rival", job_id="rival0", tokens=11_000))
        res = ro.run(f)
        risk = res.detail["prefix_risk"]
        self.assertIn("j0", risk)
        self.assertIn("p_host", risk["j0"])
        self.assertIn("basis", risk["j0"]["p_host"])

    def test_the_rollout_prices_the_resume_queue_from_its_own_timeline(self):
        ro = rollout(p=params(gpu_kv_capacity_tokens=12_000, host_kv_capacity_tokens=1_000_000))
        f = fleet()
        f.jobs["j0"] = job(pieces=4, done=2)
        f.pending.append(piece_item(iid="rival", job_id="rival0", tokens=11_000))
        risk = ro.run(f).detail["prefix_risk"]["j0"]
        self.assertIn("resume_queue_s", risk)
        self.assertGreaterEqual(risk["resume_queue_s"], 0.0)


class TestD57Calibration(unittest.TestCase):
    def test_a_cross_tier_comparison_with_no_calibration_raises(self):
        with self.assertRaises(CalibrationMissing):
            calibration.require_calibrated(None, ["device", "cloud"], "a test")

    def test_a_cross_tier_comparison_under_identity_maps_raises(self):
        with self.assertRaises(CalibrationMissing):
            calibration.require_calibrated(TierCalibration(), ["device", "cloud"], "a test")

    def test_a_single_tier_comparison_needs_no_calibration(self):
        calibration.require_calibrated(None, ["cloud", "cloud"], "a test")
        calibration.require_calibrated(TierCalibration(), ["cloud"], "a test")

    def test_tests_may_opt_in_explicitly_and_nothing_else_may(self):
        cal = identity_for_tests()
        self.assertTrue(cal.allow_identity_mixed_tier)
        calibration.require_calibrated(cal, ["device", "cloud"], "a test")
        self.assertIn("NOT A CALIBRATION", cal.source_file)

    def test_a_non_monotone_map_is_refused(self):
        with self.assertRaises(CalibrationInvalid):
            MonotoneMap(tier="cloud", knots=[(0.0, 0.5), (1.0, 0.2)])
        with self.assertRaises(CalibrationInvalid):
            MonotoneMap(tier="cloud", knots=[(1.0, 0.2), (1.0, 0.3)])
        with self.assertRaises(CalibrationInvalid):
            MonotoneMap(tier="cloud", knots=[(0.0, 0.0), (1.0, 1.4)])

    def test_a_loaded_map_is_applied_and_is_not_extrapolated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cal.json"
            p.write_text(json.dumps(dict(tiers=dict(
                device=dict(knots=[[0.0, 0.1], [1.0, 0.5]], source="DEV, StudyCTRL1c"),
                cloud=dict(knots=[[0.0, 0.3], [1.0, 0.9]], source="DEV, StudyCTRL1c")))))
            cal = calibration.load(p)
        self.assertAlmostEqual(cal.to_probability("device", 0.5)["probability"], 0.3)
        out = cal.to_probability("cloud", 5.0)
        self.assertAlmostEqual(out["probability"], 0.9)
        self.assertFalse(out["within_measured_range"])

    def test_an_empty_map_in_the_file_is_refused_rather_than_read_as_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cal.json"
            p.write_text(json.dumps(dict(tiers=dict(device=dict(knots=[])))))
            with self.assertRaises(CalibrationInvalid):
                calibration.load(p)

    def test_ranking_across_tiers_maps_first_and_can_reverse_the_raw_order(self):
        cal = TierCalibration(maps=dict(
            device=MonotoneMap("device", [(0.0, 0.0), (10.0, 0.2)], "DEV"),
            cloud=MonotoneMap("cloud", [(0.0, 0.0), (1.0, 0.9)], "DEV")))
        rows = rank_across_tiers(cal, [dict(id="d", tier="device", raw=9.0),
                                       dict(id="c", tier="cloud", raw=0.9)], "a test")
        self.assertEqual(rows[0]["id"], "c")

    def test_the_cloud_upgrades_the_device_answer_only_on_the_calibrated_scale(self):
        cal = TierCalibration(maps=dict(
            device=MonotoneMap("device", [(0.0, 0.0), (10.0, 0.9)], "DEV"),
            cloud=MonotoneMap("cloud", [(0.0, 0.0), (1.0, 0.4)], "DEV")))
        r = upgrade_decision(cal, dict(tier="cloud", raw=1.0), dict(tier="device", raw=10.0))
        self.assertFalse(r["upgrade"])
        with self.assertRaises(CalibrationMissing):
            upgrade_decision(None, dict(tier="cloud", raw=1.0), dict(tier="device", raw=0.0))

    def test_the_coordinator_exposes_the_guarded_upgrade(self):
        co = coordinator()
        with self.assertRaises(CalibrationMissing):
            co.upgrade_device_answer(dict(tier="cloud", raw=1.0), dict(tier="device", raw=0.0))
        co.params.tier_calibration = identity_for_tests()
        self.assertTrue(co.upgrade_device_answer(dict(tier="cloud", raw=1.0),
                                                 dict(tier="device", raw=0.0))["upgrade"])

    def test_tier_assignment_refuses_an_uncalibrated_cross_tier_score(self):
        cands = [dict(device="d0", rep="RICH", tokens=1000, value=1.0, score_tier="device"),
                 dict(device="d1", rep="RICH", tokens=1000, value=2.0, score_tier="cloud")]
        with self.assertRaises(CalibrationMissing):
            tier_assignment(cands, 10_000, 10_000)
        out = tier_assignment(cands, 10_000, 10_000, calibration=identity_for_tests())
        self.assertEqual(len(out["gpu"]), 2)


class TestD56TierAssignmentBounded(unittest.TestCase):
    def test_what_fits_neither_warm_tier_is_cold_and_cold_is_an_alias_of_denied(self):
        cands = [dict(device="d0", rep="RICH", tokens=900, value=9.0),
                 dict(device="d1", rep="RICH", tokens=900, value=8.0),
                 dict(device="d2", rep="RICH", tokens=900, value=7.0)]
        out = tier_assignment(cands, 1000, 1000)
        self.assertEqual(len(out["gpu"]), 1)
        self.assertEqual(len(out["host"]), 1)
        self.assertEqual(len(out["cold"]), 1)
        self.assertIs(out["cold"], out["denied"])

    def test_a_host_tier_that_is_already_occupied_has_less_room(self):
        cands = [dict(device="d0", rep="RICH", tokens=900, value=9.0),
                 dict(device="d1", rep="RICH", tokens=900, value=8.0)]
        free = tier_assignment(cands, 1000, 1000, host_occupied_tokens=0)
        full = tier_assignment(cands, 1000, 1000, host_occupied_tokens=950)
        self.assertEqual(len(free["cold"]), 0)
        self.assertEqual(len(full["cold"]), 1)

    def test_a_zero_capacity_still_refuses(self):
        with self.assertRaises(ValueError):
            tier_assignment([dict(tokens=1, value=1.0)], 0, 10)


class TestEng1bMechanisticPrefixLoss(unittest.TestCase):
    def test_nothing_is_lost_below_the_free_pool_and_loss_starts_exactly_at_it(self):
        cap, prefix = H100NVL_KV_POOL_TOKENS, 10_389
        free = cap - prefix
        for alloc, expect_loss in ((free - 1, False), (free, False), (free + 1, True)):
            pool = KVPool(capacity_tokens=cap)
            pool.put("p", prefix, 0.0, referenced=False)
            res = pool.allocate("other", alloc, 1.0)
            self.assertEqual(bool(res["freed"].get("p", 0)), expect_loss,
                             "allocation %d of a %d-token free pool" % (alloc, free))

    def test_a_partial_loss_keeps_the_leading_tokens(self):
        cap, prefix = 20_000, 10_000
        pool = KVPool(capacity_tokens=cap)
        pool.put("p", prefix, 0.0, referenced=False)
        pool.allocate("other", 13_000, 1.0)
        e = pool.entries["p"]
        self.assertEqual(e.head_tokens(), 7_000)
        self.assertEqual(e.lost_tail_tokens(), 3_000)
        self.assertEqual(e.built_tokens, prefix)

    def test_a_referenced_prefix_is_never_freed(self):
        pool = KVPool(capacity_tokens=10_000)
        pool.put("held", 9_000, 0.0, referenced=True)
        pool.allocate("other", 9_000, 1.0)
        self.assertEqual(pool.entries["held"].tokens, 9_000)

    def test_re_referencing_a_warm_context_pushes_it_behind_the_deferred_prefix(self):
        """StudyENG1b's W25 mechanism: the warm sessions re-reference their own contexts during
        the gap, which moves those blocks behind the prefix in the free queue without allocating
        anything new, and the prefix is then the first thing freed."""
        pool = KVPool(capacity_tokens=30_000)
        pool.put("prefix", 10_000, 0.0, referenced=False)
        pool.put("warm", 10_000, 1.0, referenced=False)
        self.assertEqual(pool.free_order()[0], "prefix")
        pool.reference("warm", 2.0, held=True)
        pool.reference("warm", 2.5, held=False)
        self.assertEqual(pool.free_order()[0], "prefix")
        pool.reference("prefix", 3.0, held=True)
        pool.reference("prefix", 3.5, held=False)
        self.assertEqual(pool.free_order()[0], "warm")

    def test_predict_loss_reads_no_fitted_curve(self):
        src = Path(kvpool.__file__).read_text()
        body = src.split("def predict_loss", 1)[1].split("\n    def ", 1)[0]
        for name in ("ENG1B_STAIRCASE", "eng1b_long_gap_curve", "survival_p_loss"):
            self.assertNotIn(name, body,
                             "predict_loss must stay mechanistic; %s is a fitted curve" % name)

    def test_the_measured_staircase_exists_only_as_the_long_gap_fallback(self):
        self.assertEqual(kvpool.eng1b_long_gap_curve(0.9), 0.0)
        self.assertAlmostEqual(kvpool.eng1b_long_gap_curve(1.10), 0.33)
        self.assertAlmostEqual(kvpool.eng1b_long_gap_curve(1.25), 0.60)
        self.assertEqual(kvpool.eng1b_long_gap_curve(1.6), 1.0)
        self.assertIn("LONG-GAP FALLBACK ONLY", kvpool.ENG1B_STAIRCASE_SOURCE)
        self.assertIsNone(Params().survival_curve)

    def test_the_staircase_is_monotone(self):
        xs = [i / 20.0 for i in range(0, 40)]
        ys = [kvpool.eng1b_long_gap_curve(x) for x in xs]
        self.assertEqual(ys, sorted(ys))


class TestMuEstimatorIsAnExplicitChoice(unittest.TestCase):
    def test_the_default_estimator_does_nothing_and_says_why(self):
        co = coordinator()
        self.assertEqual(co.params.mu_estimator, "none")
        f = fleet()
        f.in_flight.append(piece_item(iid="inflight"))
        co._last_delta_j = 5.0
        co._update_mu(f)
        self.assertEqual(co.params.mu, 0.0)
        self.assertIn("DOES NOT DETERMINE", co.mu_note.upper())

    def test_the_ewma_estimator_is_selectable(self):
        co = coordinator(p=params(mu_estimator="ewma_marginal_utility"))
        f = fleet()
        f.in_flight.append(piece_item(iid="inflight"))
        co._last_delta_j = 5.0
        co._update_mu(f)
        self.assertGreater(co.params.mu, 0.0)

    def test_an_unknown_estimator_raises_rather_than_falling_back(self):
        co = coordinator(p=params(mu_estimator="whatever"))
        f = fleet()
        f.in_flight.append(piece_item(iid="inflight"))
        with self.assertRaises(ValueError):
            co._update_mu(f)

    def test_mu_is_still_a_declared_placeholder(self):
        self.assertEqual(PROVENANCE["mu"]["kind"], "PLACEHOLDER")
        self.assertEqual(PROVENANCE["mu_estimator"]["kind"], "PLACEHOLDER")
        self.assertIn("mu_estimator", Params().placeholders())


if __name__ == "__main__":
    unittest.main()
