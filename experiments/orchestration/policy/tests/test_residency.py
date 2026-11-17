"""StudyRES1-residency: the bookkeeping model, its policy switch and the holdout fence."""
from __future__ import annotations

import sys
import unittest
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from policy.residency import (CLASSES, GPU_POOL_TOKENS_H100NVL, POLICIES, Req, ResidencyModel,
                              TOKENS_PER_BLOCK, Tier, host_tokens_for_cap, n_chunks, replay)
import run_res1 as R


def mk(rid, t, prompt, hid=None, hist=0, writes=None, reuse=False, **kw):
    return Req(rid=rid, t_submit=float(t), t_end=float(t) + 0.1, prompt_tokens=prompt,
               hid=hid, hist_tokens=hist, writes_hid=(writes or hid or rid), reuse=reuse, **kw)


class TestItReadsNothingMeasured(unittest.TestCase):
    def test_the_request_record_has_no_field_for_a_measured_counter(self):
        names = {f.name for f in fields(Req)}
        for forbidden in ("cached_tokens", "m_local", "m_external", "m_compute",
                          "external_cached_tokens", "local_cache_hit", "ttft_s", "latency_s"):
            self.assertNotIn(forbidden, names)

    def test_the_module_source_mentions_no_measured_counter_name(self):
        src = (Path(__file__).resolve().parents[1] / "residency.py").read_text()
        for forbidden in ("cached_tokens", "local_cache_hit", "external_kv_transfer",
                          "m_external", "m_local"):
            self.assertNotIn(forbidden, src, forbidden)


class TestTier(unittest.TestCase):
    def test_the_tail_is_evicted_first_within_a_history(self):
        t = Tier(capacity_tokens=5 * TOKENS_PER_BLOCK)
        t.store("h", range(5))
        t.store("other", [0])
        t.evict_to_capacity()
        self.assertIn(("h", 0), t)
        self.assertNotIn(("h", 4), t)

    def test_capacity_is_respected(self):
        t = Tier(capacity_tokens=10 * TOKENS_PER_BLOCK)
        t.store("h", range(50))
        t.evict_to_capacity()
        self.assertLessEqual(t.tokens(), t.capacity_tokens)

    def test_a_refresh_makes_a_history_survive_other_work(self):
        t = Tier(capacity_tokens=4 * TOKENS_PER_BLOCK)
        t.store("a", range(2))
        t.store("b", range(2))
        t.touch("a", range(2))
        t.store("c", range(2))
        t.evict_to_capacity()
        self.assertIn(("a", 0), t)
        self.assertNotIn(("b", 1), t)

    def test_leading_run_counts_only_contiguous_chunks(self):
        t = Tier(capacity_tokens=100 * TOKENS_PER_BLOCK)
        t.store("h", [0, 1, 3])
        self.assertEqual(t.leading_run("h", 0, 4), 2)
        self.assertEqual(t.leading_run("h", 3, 4), 1)


class TestCapacities(unittest.TestCase):
    def test_host_capacity_is_four_thousand_ninety_six_tokens_per_gib(self):
        self.assertEqual(host_tokens_for_cap(27), 110592)
        self.assertEqual(host_tokens_for_cap(256), 1048576)

    def test_a_twelve_gib_host_is_smaller_than_the_gpu_pool(self):
        self.assertLess(host_tokens_for_cap(12), GPU_POOL_TOKENS_H100NVL)


class TestPredictionClasses(unittest.TestCase):
    def setUp(self):
        self.m = ResidencyModel(cap_gib=27, policy="rule")

    def test_a_fresh_history_is_cold(self):
        p = self.m.predict(mk("q", 1, 11024, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "COLD")

    def test_a_history_still_on_gpu_is_gpu_warm(self):
        b = mk("b", 1, 11024)
        b.writes_hid = "h"
        self.m.complete(b, self.m.predict(b))
        p = self.m.predict(mk("q", 2, 11164, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "GPU")
        self.assertEqual(p.host_chunks, 0)

    def test_a_history_evicted_from_gpu_but_held_on_host_is_host_warm(self):
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        for i in range(6):
            f = mk("f%d" % i, 2 + i, 11024)
            self.m.complete(f, self.m.predict(f))
        p = self.m.predict(mk("q", 20, 11164, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "HOST")
        self.assertGreater(p.host_chunks, 0)

    def test_enough_other_work_makes_it_cold_again(self):
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        for i in range(40):
            f = mk("f%d" % i, 2 + i, 11024)
            self.m.complete(f, self.m.predict(f))
        p = self.m.predict(mk("q", 100, 11164, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "COLD")

    def test_a_history_whose_middle_is_gone_is_partial_with_a_host_fraction(self):
        """GPU holds the head, host holds the next stretch, and the rest is gone: the engine
        serves what it can from each tier in order and recomputes the tail."""
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        n = n_chunks(11024)
        self.m.host.drop_history("h", n)
        self.m.gpu.drop_history("h", n)
        self.m.gpu.store("h", range(0, 200))
        self.m.host.store("h", range(200, 400))
        p = self.m.predict(mk("q", 5, 11164, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "PARTIAL")
        self.assertEqual(p.gpu_chunks, 200)
        self.assertEqual(p.host_chunks, 200)
        self.assertAlmostEqual(p.host_fraction, 200 * TOKENS_PER_BLOCK / 11024.0, places=6)

    def test_a_half_evicted_history_whose_head_aged_out_is_lost_entirely(self):
        """StudyENG1c Part A's PM case: the touch left the GPU-served head unrefreshed on host,
        so when the GPU loses the head the prefix lookup fails at chunk 0 and the whole history
        is gone although its tail is still on host."""
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        n = n_chunks(11024)
        self.m.host.drop_history("h", n)
        self.m.gpu.drop_history("h", n)
        self.m.host.store("h", range(300, n))
        p = self.m.predict(mk("q", 5, 11164, hid="h", hist=11024, reuse=True))
        self.assertEqual(p.cls, "COLD")
        self.assertEqual(p.host_chunks, 0)

    def test_a_block_aligned_prompt_takes_the_host_load_path(self):
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        p = self.m.predict(mk("touch", 2, 11024, hid="h", hist=11024, reuse=True))
        self.assertTrue(p.forced_last_block)
        self.assertTrue(p.host_path)
        self.assertEqual(p.cls, "HOST")

    def test_a_prompt_one_token_past_the_history_avoids_the_host_path(self):
        b = mk("b", 1, 11024, writes="h")
        self.m.complete(b, self.m.predict(b))
        p = self.m.predict(mk("touch", 2, 11025, hid="h", hist=11024, reuse=True))
        self.assertFalse(p.forced_last_block)
        self.assertEqual(p.cls, "GPU")

    def test_every_predicted_class_is_one_of_the_four(self):
        p = self.m.predict(mk("q", 1, 11024, hid="h", hist=11024, reuse=True))
        self.assertIn(p.cls, CLASSES)


class TestPolicySwitch(unittest.TestCase):
    def _stream(self, n_fillers=20):
        """A build, a touch that is served wholly from GPU, then enough other work to evict the
        history from the GPU pool but less than the host cap since the touch."""
        reqs = [mk("build", 1, 11024, writes="h")]
        reqs.append(mk("touch", 2, 11025, hid="h", hist=11024, writes="h", reuse=True))
        for i in range(n_fillers):
            reqs.append(mk("f%d" % i, 10 + i, 11024))
        reqs.append(mk("probe", 200, 11025, hid="h", hist=11024, writes="h", reuse=True))
        return reqs

    def test_the_rule_keeps_a_wholly_gpu_served_history_on_host(self):
        """20 fillers write 220,480 tokens: past the 62,944-token GPU pool, inside the
        245,760-token host cap at 60 GiB."""
        rows = replay(self._stream(20), cap_gib=60, policy="rule")
        self.assertEqual(rows[-1]["predicted_class"], "HOST")

    def test_enough_writes_past_the_host_cap_lose_it_even_under_the_rule(self):
        self.assertEqual(replay(self._stream(25), cap_gib=60,
                                policy="rule")[-1]["predicted_class"], "COLD")

    def _stream_touch_in_the_middle(self, before=11, after=11):
        """The touch happens AFTER some other work, so that a refresh makes the history younger
        than those earlier writes. That is the only arrangement in which a refresh policy and a
        store-time policy can disagree."""
        reqs = [mk("build", 1, 11024, writes="h")]
        for i in range(before):
            reqs.append(mk("pre%d" % i, 5 + i, 11024))
        reqs.append(mk("touch", 100, 11025, hid="h", hist=11024, writes="h", reuse=True))
        for i in range(after):
            reqs.append(mk("post%d" % i, 200 + i, 11024))
        reqs.append(mk("probe", 500, 11025, hid="h", hist=11024, writes="h", reuse=True))
        return reqs

    def test_fifo_loses_it_because_the_touch_never_refreshes(self):
        """Total stored is 11 + 11 + 1 histories of about 11k tokens, which overruns the
        245,760-token cap at 60 GiB. Under the rule the touch made the history younger than the
        11 earlier writes, so those go first and it survives on host; under FIFO its store time
        is still the oldest, so it is the one that goes."""
        rule = replay(self._stream_touch_in_the_middle(), cap_gib=60,
                      policy="rule")[-1]["predicted_class"]
        fifo = replay(self._stream_touch_in_the_middle(), cap_gib=60,
                      policy="fifo")[-1]["predicted_class"]
        self.assertEqual(rule, "HOST")
        self.assertNotEqual(fifo, "HOST")

    def test_every_policy_runs_and_produces_one_row_per_reuse_request(self):
        for p in POLICIES:
            rows = replay(self._stream(), cap_gib=27, policy=p)
            self.assertEqual(len(rows), 2, p)

    def test_occupancy_only_ignores_recency_entirely(self):
        rows = replay(self._stream(), cap_gib=256, policy="occupancy")
        self.assertEqual(rows[-1]["predicted_class"], "HOST")

    def test_the_policy_name_is_validated(self):
        with self.assertRaises(ValueError):
            ResidencyModel(cap_gib=27, policy="whatever")


class TestMeasuredGroundTruth(unittest.TestCase):
    def test_cold_is_a_hit_of_at_most_one_block(self):
        self.assertEqual(R.measured_class(11024, 0, 0.0, True)["cls"], "COLD")
        self.assertEqual(R.measured_class(11024, 16, 0.0, True)["cls"], "COLD")

    def test_the_forced_last_block_still_counts_as_warm(self):
        m = R.measured_class(2114, 2096, 0.0, True)
        self.assertEqual(m["cls"], "GPU")

    def test_host_needs_more_than_one_block_from_host(self):
        self.assertEqual(R.measured_class(11024, 11008, 11008.0, True)["cls"], "HOST")
        self.assertEqual(R.measured_class(11024, 11008, 0.0, True)["cls"], "GPU")

    def test_partial_is_determinable_without_a_counter(self):
        m = R.measured_class(11024, 5000, None, False)
        self.assertEqual(m["cls"], "PARTIAL")
        self.assertTrue(m["determined"])
        self.assertIsNone(m["host_fraction"])

    def test_a_warm_request_without_an_attributable_counter_is_undetermined(self):
        m = R.measured_class(11024, 11008, None, False)
        self.assertIsNone(m["cls"])
        self.assertFalse(m["determined"])
        self.assertIn("no counter window", m["reason"])

    def test_the_two_class_state_is_known_even_when_the_tier_is_not(self):
        self.assertEqual(R.measured_2class(dict(determined=False, measured=None)), "WARM")
        self.assertEqual(R.measured_2class(dict(determined=True, measured="COLD")), "COLD")
        self.assertEqual(R.measured_2class(dict(determined=True, measured="HOST")), "WARM")


class TestHoldoutFence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = R.measured_truth()
        cls.streams, cls.audit = R.build_streams()

    def test_no_holdout_request_has_a_measured_class(self):
        holdout = {r.rid for v in self.streams.values() for r in v if r.holdout}
        self.assertGreater(len(holdout), 0)
        self.assertEqual(sorted(set(self.truth) & holdout), [])

    def test_holdout_requests_are_still_replayed_for_capacity(self):
        n = sum(1 for v in self.streams.values() for r in v if r.holdout)
        self.assertGreater(n, 1000)

    def test_no_holdout_request_reaches_a_scored_row(self):
        rows = R.joined(self.streams, self.truth, "rule")
        holdout = {r.rid for v in self.streams.values() for r in v if r.holdout}
        self.assertEqual([r["rid"] for r in rows if r["rid"] in holdout], [])

    def test_the_part_d_truth_builder_refuses_holdout_runs(self):
        t = R.truth_part_d(fence_holdout=True)
        rows = R._rows("D")
        holdout_rids = {str(r["rid"]) for r in rows
                        if r["kind"] == "inject" and r.get("holdout")}
        self.assertGreater(len(holdout_rids), 0)
        self.assertEqual(sorted(holdout_rids & set(t)), [])


class TestStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.streams, cls.audit = R.build_streams()

    def test_each_server_segment_has_one_capacity(self):
        for label, v in self.audit["per_server"].items():
            self.assertIn(v["cap_gib"], (12.0, 27.0, 38.0, 60.0, 256.0), label)

    def test_part_e_has_no_reuse_request(self):
        self.assertEqual(self.audit["per_part"]["E"]["n_reuse"], 0)

    def test_the_reuse_counts_match_the_record(self):
        self.assertEqual(self.audit["per_part"]["A"]["n_reuse"], 235)
        self.assertEqual(self.audit["per_part"]["B"]["n_reuse"], 1550)
        self.assertEqual(self.audit["per_part"]["C"]["n_reuse"], 510)


if __name__ == "__main__":
    unittest.main()
