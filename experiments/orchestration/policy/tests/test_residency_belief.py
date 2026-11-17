"""StudyPOL5-engine Part 3: the residency belief, its boundary rule and its wiring."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policy.residency import TOKENS_PER_BLOCK, host_tokens_for_cap
from policy.residency_belief import (BLOCK_ROUNDING_FIX, BOUNDARY_MARGIN_FRACTION,
                                     MARGIN_SOURCE, RES1_ACCOUNTING_ERROR_TOKENS,
                                     RES1_BLOCK_ROUNDING_TOKENS, ResidencyBelief,
                                     blocks_written, boundary_margin_tokens)
from policy.rollout import Rollout
from policy.coordinator import Coordinator


def _root() -> Path:
    return Path(__file__).resolve().parents[4]


class TestTheMarginComesFromMeasuredQuantities(unittest.TestCase):
    def test_the_margin_is_res1s_accounting_error_plus_block_rounding(self):
        expected = (RES1_ACCOUNTING_ERROR_TOKENS + RES1_BLOCK_ROUNDING_TOKENS) / 245760.0
        self.assertAlmostEqual(BOUNDARY_MARGIN_FRACTION, expected, places=12)
        self.assertIn("3,064", MARGIN_SOURCE)
        self.assertIn("816", MARGIN_SOURCE)
        self.assertIn("1.37 per cent", MARGIN_SOURCE)

    def test_the_margin_scales_with_the_cap_rather_than_being_a_constant(self):
        small = boundary_margin_tokens(host_tokens_for_cap(27))
        big = boundary_margin_tokens(host_tokens_for_cap(256))
        self.assertLess(small, big)
        self.assertAlmostEqual(big / float(host_tokens_for_cap(256)),
                               small / float(host_tokens_for_cap(27)), places=4)

    def test_the_margin_at_sixty_gib_is_about_four_thousand_tokens(self):
        m = boundary_margin_tokens(host_tokens_for_cap(60))
        self.assertGreater(m, 3000)
        self.assertLess(m, 5000)


class TestTheBoundaryRule(unittest.TestCase):
    def setUp(self):
        self.b = ResidencyBelief(cap_gib=60)
        self.cap = self.b.host_capacity_tokens()
        self.margin = boundary_margin_tokens(self.cap)

    def test_well_inside_the_cap_the_history_is_host_warm_with_no_split(self):
        r = self.b.belief("h", written_since_refresh=0)
        self.assertEqual(r["p_host"], 1.0)
        self.assertFalse(r["boundary"])
        self.assertTrue(r["measured"])

    def test_well_past_the_cap_the_history_is_cold_with_no_split(self):
        r = self.b.belief("h", written_since_refresh=self.cap + self.margin + 1)
        self.assertEqual(r["p_host"], 0.0)
        self.assertEqual(r["p_cold"], 1.0)
        self.assertFalse(r["boundary"])

    def test_inside_the_margin_the_belief_splits_and_says_possibly_cold(self):
        r = self.b.belief("h", written_since_refresh=self.cap)
        self.assertTrue(r["boundary"])
        self.assertAlmostEqual(r["p_host"], 0.5, places=6)
        self.assertAlmostEqual(r["p_host"] + r["p_cold"], 1.0, places=12)
        self.assertIn("POSSIBLY COLD", r["basis"])
        self.assertFalse(r["measured"])

    def test_the_split_is_monotone_across_the_boundary(self):
        xs = [self.cap - self.margin, self.cap - self.margin // 2, self.cap,
              self.cap + self.margin // 2, self.cap + self.margin]
        ps = [self.b.belief("h", written_since_refresh=x)["p_host"] for x in xs]
        self.assertEqual(ps, sorted(ps, reverse=True))
        self.assertAlmostEqual(ps[0], 1.0, places=6)
        self.assertAlmostEqual(ps[-1], 0.0, places=6)

    def test_no_host_tier_means_nothing_survives(self):
        r = ResidencyBelief(cap_gib=0).belief("h", written_since_refresh=0)
        self.assertEqual(r["p_host"], 0.0)
        self.assertEqual(r["p_cold"], 1.0)


class TestTheBlockRoundingFix(unittest.TestCase):
    def test_a_trailing_partial_block_is_not_charged(self):
        self.assertEqual(blocks_written(378), 23)
        self.assertEqual(blocks_written(16), 1)
        self.assertEqual(blocks_written(15), 0)

    def test_the_fix_is_disclosed_and_says_res1_was_not_rescored(self):
        self.assertIn("DISCLOSED", BLOCK_ROUNDING_FIX)
        self.assertIn("NOT", BLOCK_ROUNDING_FIX)
        self.assertIn("fitting on TEST", BLOCK_ROUNDING_FIX)

    def test_the_write_stream_ages_other_histories_and_not_the_refreshed_one(self):
        b = ResidencyBelief(cap_gib=27)
        b.note_build("a", 11024)
        b.note_build("c", 11024)
        self.assertEqual(b.written_since_refresh["c"], 0)
        self.assertGreater(b.written_since_refresh["a"], 0)
        b.note_refresh("a")
        self.assertEqual(b.written_since_refresh["a"], 0)


class TestItIsADropInForParams(unittest.TestCase):
    def test_it_returns_the_keys_the_controller_reads(self):
        r = ResidencyBelief(cap_gib=60).p_host_for(None, 1000, prefix_id="h")
        for k in ("p_host", "basis", "measured", "host_occupancy_fraction"):
            self.assertIn(k, r)
        self.assertIsInstance(r["p_host"], float)

    def test_it_says_when_the_write_stream_was_not_fed_to_it(self):
        r = ResidencyBelief(cap_gib=60).p_host_for(None, 1000, prefix_id="never_seen")
        self.assertFalse(r["write_stream_tracked"])
        self.assertIn("occupancy stood in for it", r["basis"])

    def test_it_names_what_it_replaces(self):
        r = ResidencyBelief(cap_gib=60).p_host_for(None, 0, prefix_id="h")
        self.assertIn("EVICTION_RULE_ASSUMPTION", r["replaces"])


class TestWiring(unittest.TestCase):
    def test_the_rollout_defaults_to_the_old_path(self):
        self.assertIsNone(Rollout.__dataclass_fields__["residency_belief"].default)

    def test_the_coordinator_passes_the_belief_to_its_rollout(self):
        self.assertIn("residency_belief", Coordinator.__dataclass_fields__)

    def test_no_frozen_file_was_modified(self):
        frozen = json.loads((_root() / "results/orchestration/study_t0b/t0b_freeze.json").read_text())
        for rel, md5 in frozen["files"].items():
            got = hashlib.md5((_root() / rel).read_bytes()).hexdigest()
            self.assertEqual(got, md5, rel)

    def test_the_belief_is_not_inside_a_frozen_file(self):
        frozen = json.loads((_root() / "results/orchestration/study_t0b/t0b_freeze.json").read_text())
        self.assertNotIn("experiments/orchestration/policy/residency_belief.py", frozen["files"])
        self.assertNotIn("experiments/orchestration/policy/rollout.py", frozen["files"])
        self.assertNotIn("experiments/orchestration/policy/coordinator.py", frozen["files"])


if __name__ == "__main__":
    unittest.main()
