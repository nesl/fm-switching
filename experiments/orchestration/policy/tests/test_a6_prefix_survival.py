import unittest

from policy.continuation import INFEASIBLE, classify, expected_remaining_work, restore_costs_s
from policy.kvpool import KVPool, prefix_id_for, survival_p_loss
from policy.readiness import assert_single_counting, prefix_items
from policy.rollout import delta_j
from policy.state import PendingItem
from policy.telemetry import TelemetrySnapshot
from policy.tests._fixtures import PF, coordinator, engine, fleet, job, params, piece_item


def with_job(f, pieces_total=6, pieces_done=3, tokens=2048, deadline=10.0):
    j = job(deadline=deadline, pieces=pieces_total, done=pieces_done)
    j.tokens_per_piece = tokens
    f.jobs[j.job_id] = j
    return j


class TestKVPool(unittest.TestCase):
    def test_unreferenced_blocks_are_freed_first_and_referenced_ones_are_not(self):
        p = KVPool(capacity_tokens=10_000)
        p.put("cold", 4_000, 0.0, referenced=False)
        p.put("held", 4_000, 1.0, referenced=True)
        freed = p.make_room(6_000, 2.0)
        self.assertIn("cold", freed)
        self.assertNotIn("held", freed)

    def test_free_order_is_unreferenced_then_least_recently_used(self):
        p = KVPool(capacity_tokens=10_000)
        p.put("old", 1_000, 0.0, referenced=False)
        p.put("new", 1_000, 5.0, referenced=False)
        p.put("held", 1_000, 1.0, referenced=True)
        self.assertEqual(p.free_order(), ["old", "new", "held"])

    def test_p_loss_is_the_evicted_fraction_and_rises_with_demand(self):
        p = KVPool(capacity_tokens=10_000)
        p.put(prefix_id_for("j0"), 4_000, 0.0, referenced=False)
        p.put("other", 4_000, 0.0, referenced=False)
        low = p.predict_loss(prefix_id_for("j0"), 500, 1.0)["p_loss"]
        high = p.predict_loss(prefix_id_for("j0"), 9_000, 1.0)["p_loss"]
        self.assertEqual(low, 0.0)
        self.assertGreater(high, low)
        self.assertLessEqual(high, 1.0)

    def test_no_survival_curve_means_no_invented_number(self):
        s = survival_p_loss(None, 30.0)
        self.assertEqual(s["p_loss"], 0.0)
        self.assertFalse(s["available"])
        self.assertIn("M5", s["note"])
        self.assertEqual(survival_p_loss(lambda g: 0.4, 30.0)["p_loss"], 0.4)


class TestExpectedRemainingWork(unittest.TestCase):
    def test_formula_matches_a6_term_by_term(self):
        e = engine()
        j = job(pieces=6, done=3)
        j.tokens_per_piece = 2048
        built = j.pieces_done * j.tokens_per_piece
        w_reload, w_rebuild = restore_costs_s(built, PF)
        for p_loss, p_host in ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (1.0, 0.25)):
            rw = expected_remaining_work(j, e, PF, p_loss=p_loss, p_host=p_host,
                                         prefix_tokens=built)
            self.assertAlmostEqual(
                rw.extra_s, p_loss * (p_host * w_reload + (1 - p_host) * w_rebuild), places=12)
            self.assertAlmostEqual(rw.total_s, rw.w_left_s + rw.extra_s, places=12)

    def test_a_reload_is_cheaper_than_a_rebuild_so_p_host_lowers_the_cost(self):
        e = engine()
        j = job(pieces=6, done=3)
        j.tokens_per_piece = 2048
        hot = expected_remaining_work(j, e, PF, p_loss=1.0, p_host=1.0).extra_s
        cold = expected_remaining_work(j, e, PF, p_loss=1.0, p_host=0.0).extra_s
        self.assertLess(hot, cold)

    def test_probabilities_are_validated(self):
        e = engine()
        for bad in ((1.5, 0.0), (0.0, -0.1)):
            with self.assertRaises(ValueError):
                expected_remaining_work(job(), e, PF, p_loss=bad[0], p_host=bad[1])

    def test_feasibility_can_flip_on_the_restore_work(self):
        e = engine()
        j = job(deadline=3.0, pieces=4, done=2)
        j.tokens_per_piece = 2048
        safe = classify(j, 0.0, e, 0.0, 0.5, extra_work_s=0.0)
        at_risk = classify(j, 0.0, e, 0.0, 0.5, extra_work_s=100.0)
        self.assertNotEqual(safe, INFEASIBLE)
        self.assertEqual(at_risk, INFEASIBLE)


class TestA6InTheRollout(unittest.TestCase):
    """Tests (iii) and (iv) of the brief."""

    def _loaded(self, capacity, n_rivals=6, rival_tokens=4000, mu=1.0):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=capacity, mu=mu))
        f = fleet(1)
        j = with_job(f)
        f.pending.append(piece_item(iid="next", tokens=j.tokens_per_piece, job_id=j.job_id,
                                    deadline=j.deadline))
        for i in range(n_rivals):
            f.pending.append(piece_item(iid="rival%d" % i, tokens=rival_tokens,
                                        job_id="rival%d" % i, deadline=9.0))
        return co, f, j

    def test_iii_high_kv_pressure_makes_deferring_a_piece_worse(self):
        co, f, j = self._loaded(capacity=12_000)
        on = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        co.params.kv_pool_model = False
        off = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        self.assertLess(on, off,
                        "under KV pressure, deferring must score lower with the pool model on")

    def test_iii_needs_a_non_zero_gpu_price_to_reach_delta_j(self):
        """A6's restore work reaches DeltaJ through spec 5.3's backlog price. mu is a
        PLACEHOLDER at 0, and with mu = 0 that channel is silent by construction; this pins the
        fact rather than leaving it to be discovered later."""
        co, f, j = self._loaded(capacity=12_000, mu=0.0)
        on = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        co.params.kv_pool_model = False
        off = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        self.assertAlmostEqual(on, off, places=12)

    def test_iv_with_zero_pressure_the_a6_terms_vanish(self):
        co, f, j = self._loaded(capacity=100_000_000, n_rivals=0)
        r_on = co.rollout.run(f)
        on = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        for info in r_on.detail["prefix_risk"].values():
            self.assertEqual(info["p_loss"], 0.0)
            self.assertEqual(info["extra_work_s"], 0.0)
        co.params.kv_pool_model = False
        off = delta_j(co.rollout, f, dict(kind="defer", item_id="next"))["delta_j"]
        self.assertAlmostEqual(on, off, places=12,
                               msg="with P_loss = 0 the A6 path must equal the pre-A6 path")

    def test_the_pool_is_reported_on_every_rollout(self):
        co, f, j = self._loaded(capacity=12_000)
        r = co.rollout.run(f)
        self.assertIn("capacity_tokens", r.kv)
        self.assertIn("free_order", r.kv)
        self.assertGreater(len(r.detail["prefix_risk"]), 0)

    def test_beyond_horizon_is_flagged_unmeasured_rather_than_filled_in(self):
        co, f, j = self._loaded(capacity=12_000)
        r = co.rollout.run(f)
        info = list(r.detail["prefix_risk"].values())[0]
        self.assertFalse(info["beyond_horizon"]["available"])
        self.assertTrue(info["beyond_horizon_unmeasured"])

    def test_a_supplied_survival_curve_is_used(self):
        co, f, j = self._loaded(capacity=100_000_000, n_rivals=0)
        co.params.survival_curve = lambda g: 0.9
        r = co.rollout.run(f)
        info = list(r.detail["prefix_risk"].values())[0]
        self.assertAlmostEqual(info["p_loss"], 0.9, places=12)
        self.assertGreater(info["extra_work_s"], 0.0)
        self.assertFalse(info["beyond_horizon_unmeasured"])


class TestA6Replanning(unittest.TestCase):
    """Test (v) of the brief."""

    def _co(self, capacity=12_000, rivals=0, rival_tokens=4000):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=capacity))
        f = fleet(1)
        j = with_job(f)
        it = piece_item(iid="next", tokens=j.tokens_per_piece, job_id=j.job_id,
                        deadline=j.deadline)
        f.pending.append(it)
        for i in range(rivals):
            f.pending.append(piece_item(iid="rival%d" % i, tokens=rival_tokens,
                                        job_id="rival%d" % i, deadline=9.0))
        return co, f, j, it

    def test_v_observed_loss_triggers_replanning_and_adds_restore_work(self):
        co, f, j, it = self._co(capacity=100_000_000)
        before = j.pieces_total
        tel = TelemetrySnapshot(local_hits=0, external_hits=0, evictions=3)
        out = co.verify_prefix_before_release(f, it, telemetry=tel)
        self.assertTrue(out["observed_loss"])
        self.assertTrue(out["replanned"])
        self.assertEqual(j.pieces_total, before + 1)
        restore = [p for p in f.pending if p.meta.get("a6_restore")]
        self.assertEqual(len(restore), 1)
        self.assertGreater(restore[0].meta["restore_work_s"], 0.0)
        self.assertEqual(restore[0].tokens, j.pieces_done * j.tokens_per_piece)
        self.assertEqual(len(co.prefix_loss_events), 1)
        self.assertIn("OBSERVED", co.prefix_loss_events[0]["requested_continuation_vs_"
                                                           "observed_loss"])

    def test_likely_loss_also_triggers_replanning(self):
        co, f, j, it = self._co(capacity=8_000, rivals=3)
        out = co.verify_prefix_before_release(f, it)
        self.assertGreaterEqual(out["p_loss"], co.params.prefix_loss_replan_threshold)
        self.assertTrue(out["replanned"])
        self.assertTrue(co.prefix_loss_events)

    def test_a_safe_prefix_is_not_replanned(self):
        co, f, j, it = self._co(capacity=100_000_000)
        out = co.verify_prefix_before_release(f, it)
        self.assertEqual(out["p_loss"], 0.0)
        self.assertFalse(out["replanned"])
        self.assertEqual(co.prefix_loss_events, [])

    def test_the_release_loop_replans_instead_of_releasing_a_lost_prefix(self):
        co, f, j, it = self._co(capacity=8_000, rivals=3)
        out = co._release_loop(f)
        self.assertTrue(any(d.kind == "prefix_loss" for d in out))
        self.assertTrue(any(p.meta.get("a6_restore") for p in f.pending))


class TestA6MemoryDecision(unittest.TestCase):
    """Test (vi) of the brief, plus A6.3's no-pin rule."""

    def test_vi_continuation_and_state_value_never_count_the_same_question(self):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=12_000))
        f = fleet(1)
        j = with_job(f)
        r = co.rollout.run(f)
        cont = r.detail["terminal"]["continuation"]
        sv = r.detail["terminal"]["state_value"]
        assert_single_counting(cont, sv)
        self.assertTrue(cont and sv, "A6.3 values the prefix BOTH ways, once each")
        self.assertEqual({tuple(x["counts_question"]) for x in cont},
                         {("job", j.job_id)})
        self.assertEqual({tuple(x["counts_question"]) for x in sv}, {("future", "RICH")})

    def test_the_assertion_actually_fires_on_a_double_count(self):
        with self.assertRaises(AssertionError):
            assert_single_counting([dict(counts_question=("job", "j0"))],
                                   [dict(counts_question=("job", "j0"))])

    def test_an_in_progress_prefix_becomes_a_memory_item_valued_once_each_way(self):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=12_000))
        f = fleet(1)
        j = with_job(f)
        r = co.rollout.run(f)
        risk = dict(r.detail["prefix_risk"])
        var = co.rollout.continuation_value_at_risk(f, j.job_id)
        risk[j.job_id]["continuation_value_at_risk"] = var["value_at_risk"]
        items = prefix_items(f, risk, r.detail["terminal"]["state_value"])
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertAlmostEqual(it["value"],
                               it["continuation_value_at_risk"] + it["state_value_future"],
                               places=12)
        self.assertFalse(it["pinned"], "no code path may assume a prefix is pinned")
        self.assertNotEqual(it["counts_question"], it["state_counts"])

    def test_value_at_risk_is_zero_when_nothing_is_built(self):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=12_000))
        f = fleet(1)
        j = with_job(f, pieces_done=0)
        var = co.rollout.continuation_value_at_risk(f, j.job_id)
        self.assertEqual(var["built_prefix_tokens"], 0)
        self.assertEqual(var["restore_work_s"], 0.0)
        self.assertAlmostEqual(var["value_at_risk"], 0.0, places=12)


class TestA6PieceSizing(unittest.TestCase):
    def test_piece_sizing_accounts_for_the_gaps_a_size_implies(self):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=12_000))
        f = fleet(1)
        j = with_job(f, pieces_total=8, pieces_done=0, tokens=1024)
        out = co.choose_piece_size(f, j)
        self.assertIn("chosen", out)
        sizes = {r["size_tokens"]: r for r in out["candidates"]}
        self.assertIn(1024, sizes)
        self.assertIn(2048, sizes)
        self.assertGreater(sizes[1024]["gaps"], sizes[2048]["gaps"])
        for r in out["candidates"]:
            self.assertAlmostEqual(r["expected_total_s"],
                                   r["work_s"] + r["expected_restore_s"], places=12)

    def test_whole_job_is_a_candidate_and_has_no_gaps(self):
        co = coordinator(p=params(H=1.0, gpu_kv_capacity_tokens=12_000))
        f = fleet(1)
        j = with_job(f, pieces_total=4, pieces_done=0, tokens=2048)
        out = co.choose_piece_size(f, j)
        whole = [r for r in out["candidates"] if r["n_pieces"] == 1]
        self.assertTrue(whole)
        self.assertEqual(whole[0]["gaps"], 0)
        self.assertEqual(whole[0]["expected_restore_s"], 0.0)
