#!/usr/bin/env python3
"""StudyLIVE2-coord, Part 4: the flash tests. CPU only, fake server or no server at all.

NOTHING ANY OF THESE TESTS PRODUCES IS A MEASUREMENT.

  a  schema round-trip; every arm emits only legal actions
  b  fairness: one frozen trace, identical opportunity-stream digest for every arm
  c  scrub enforced; an arm declaring reads_future is refused
  d  device-only submits zero requests; always-cloud one per opportunity
  e  determinism: same trace, arm and seed give an identical decision log
  f  cache-isolation fields on every request (D84)
  g  DEFER honoured: a deferred item is not submitted before defer_s (D90)
  h  the INTERIM-map refusal works (D86)
  chain  a prefix-chained rebuild at StudyENG1's 11,184-token history completes piece by piece
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                      # noqa: E402
import cachekeys as CK                                                # noqa: E402
import calib as CALIB                                                 # noqa: E402
import cstate as CS                                                   # noqa: E402
import schema as SC                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from coordinator import Live2Coordinator, Logs                        # noqa: E402
from interface import Action, Observation, Policy, RecallAction        # noqa: E402

GPU_KV = 62_944
HOST_GIB = 27.0
HOST_TOK = 48_000
WINDOW = 60.0


def _trace(seed=1, mode="A", nd=2, nr=2, duration=WINDOW, frames=None):
    return T.synthetic(n_dashcam=nd, n_robot=nr, duration_s=duration, seed=seed,
                       upload_mode=mode, frames_dir=frames)


def _arm(name):
    kw = dict(h_s=1.0) if name == "policy-core" else {}
    a = A.make_arm(name, **kw)
    cfg = dict(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
               targets=CS.TARGETS)
    if name == "policy-core":
        d = Path(tempfile.mkdtemp())
        cfg["calibration_knots_path"] = CALIB.write_knots(CALIB.load_map(), d / "k.json")
    a.live2_configure(**cfg)
    return a


def _run(name, trace, out, *, seed=1, mode="A", window=WINDOW, frames=None, dry=True):
    a = _arm(name)
    logs = Logs(Path(out)).open()
    resp = T.pull_responder(trace.get("frames_by_instant") or {}) if mode == "B" else None
    co = Live2Coordinator(a, None, trace["events"], gpu_kv_tokens=GPU_KV,
                          host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, upload_mode=mode,
                          window_s=window, drain_s=10.0, seed=seed, logs=logs,
                          run_tag=CK.run_tag(seed, name), dry_run=dry,
                          frames_root=(Path(frames) if frames else None), on_pull=resp)
    res = co.run()
    logs.close()
    return a, co, res


class TestA_SchemaAndLegality(unittest.TestCase):
    def test_schema_round_trip(self):
        for kind, fields in SC.FIELDS.items():
            kw = {f: _sample(f) for f in fields}
            ev = SC.make(kind, **kw)
            obj = SC.parse(ev)
            self.assertEqual(SC.to_wire(obj), ev)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            recs = [SC.make(k, **{f: _sample(f) for f in fs}) for k, fs in SC.FIELDS.items()]
            SC.write_jsonl(p, recs)
            self.assertEqual(SC.read_jsonl(p), recs)

    def test_header_round_trip(self):
        h = SC.RunHeader(git_commit="x", arm="edf", arm_version="v", flags={},
                         gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                         cost_model_id="pol4", cost_model_hash="h", calibration_file="f",
                         calibration_label="INTERIM", fairness_digest="d" * 64,
                         live1_trace_digest="l" * 32, trace_label="SYNTHETIC",
                         seed=1, targets=CS.TARGETS, upload_mode="A", mu_mode="none",
                         mu_value=0.0, H=1.0, tick_s=0.1, decision_period_s=0.1,
                         gpu_budget_s=60.0, memory_setting="tight", ratio="50:50", mode="A",
                         server_url="u", server_kind="fake")
        with tempfile.TemporaryDirectory() as d:
            p = SC.write_header(Path(d) / "header.json", h)
            back = SC.read_header(p)
            self.assertEqual(back.fairness_digest, "d" * 64)
            self.assertEqual(back.live1_trace_digest, "l" * 32)

    def test_every_arm_emits_only_legal_actions(self):
        tr = _trace()
        with tempfile.TemporaryDirectory() as d:
            for name in A.ARM_NAMES:
                a, co, res = _run(name, tr, Path(d) / name)
                self.assertEqual(res["n_errors"], 0, name)
                self.assertGreater(res["n_decisions"] + res["n_requests"], 0, name)


class TestB_Fairness(unittest.TestCase):
    def test_the_canonical_fairness_digest_is_identical_for_every_arm(self):
        """D96 part 2: the canonical digest is the fleet's ORDER-INDEPENDENT sha256 over sorted
        event tuples, 64 hex characters, covering device_register, session_start, session_end,
        history_append, recall_question and monitor_frame in push mode (monitor_offer in pull
        mode, where the frames depend on the arm's own pulls and so cannot be an invariant)."""
        tr = _trace()
        self.assertEqual(len(tr["fairness_digest"]), 64)
        import random as _r
        ev = list(tr["events"])
        _r.shuffle(ev)
        self.assertEqual(T.fairness_digest(ev, "A"), tr["fairness_digest"],
                         "the fairness digest is not order-independent")
        pull = _trace(mode="B")
        self.assertNotIn("monitor_frame", T.fairness_kinds("B"))
        self.assertIn("monitor_offer", T.fairness_kinds("B"))
        self.assertEqual(len(pull["fairness_digest"]), 64)
        seen = set()
        with tempfile.TemporaryDirectory() as d:
            for name in A.ARM_NAMES:
                _a, co, _res = _run(name, tr, Path(d) / name)
                seen.add(_opp_digest(co))
        self.assertEqual(len(seen), 1, f"arms saw different opportunity streams: {seen}")

    def test_the_fairness_digest_equals_the_fleets_canonical_one(self):
        """D96 makes the FLEET's definition canonical, so this asserts byte equality with
        `fleet/trace.py::fairness_digest` on the same stream, in BOTH modes. If the fleet
        changes its row shape this test fails rather than two digests silently diverging."""
        sys.path.insert(0, str(LIVE2 / "fleet"))
        import trace as FT                                           # noqa: E402
        tr = _trace(duration=90.0)
        # D101: the stream carries a history_preload too, so the row shape of the NEW event is
        # cross-checked against the fleet's and not only the six older kinds.
        ev = list(tr["events"]) + [SC.make("history_preload", device_id="r0",
                                           session_id="r0/s0", frame_refs=["f1", "f2"],
                                           est_tokens=5000, t=0.0)]
        self.assertIn("history_preload", T.fairness_kinds("A"))
        recs = [_fleet_record(e) for e in ev]
        recs = [r for r in recs if r is not None]
        self.assertEqual(T.fairness_digest(ev, "A"), FT.fairness_digest(recs, "A"))
        # In PULL mode the wire stream carries monitor_offer where push carries monitor_frame,
        # so the pull side is built from the pull trace; the fleet record is the same
        # `monitor_opportunity` either way and the digest differs only in the label.
        pull = list(_trace(duration=90.0, mode="B")["events"]) + [ev[-1]]
        precs = [r for r in (_fleet_record(e) for e in pull) if r is not None]
        self.assertEqual(T.fairness_digest(pull, "B"), FT.fairness_digest(precs, "B"))

    def test_identical_opportunity_stream_digest(self):
        """The per-arm check on the stream the coordinator actually built."""
        tr = _trace()
        seen = set()
        with tempfile.TemporaryDirectory() as d:
            for name in A.ARM_NAMES:
                _a, co, _res = _run(name, tr, Path(d) / name)
                seen.add(_opp_digest(co))
        self.assertEqual(len(seen), 1, f"arms saw different opportunity streams: {seen}")

    def test_digest_changes_with_the_stream(self):
        self.assertNotEqual(_trace(seed=1)["fairness_digest"], _trace(seed=2)["fairness_digest"])


class _FutureReader(Policy):
    name = "future-reader"
    case = "naive"
    reads_future = True

    def decide(self, obs):
        return Action()


class TestC_Scrub(unittest.TestCase):
    def test_reads_future_is_refused(self):
        tr = _trace(duration=20.0)
        with self.assertRaises(RuntimeError):
            Live2Coordinator(_FutureReader(), None, tr["events"], gpu_kv_tokens=GPU_KV,
                             host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, window_s=20.0,
                             dry_run=True).run()

    def test_scrub_runs_on_every_observation(self):
        st = CS.CoordState(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                           host_tier_tokens=HOST_TOK)
        st.register(dict(device_id="dash000", type="dashcam", uplink_mbps=13.6, rtt_ms=44.0,
                         start_t=0.0), "salt")
        obs = st.observation(0.0, "tick")
        from interface import scrub
        self.assertIs(scrub(obs), obs)
        for f in ("label", "y_true", "ground_truth", "oracle"):
            self.assertFalse(hasattr(obs, f))


class TestD_RequestCounts(unittest.TestCase):
    def test_device_only_sends_nothing(self):
        tr = _trace()
        with tempfile.TemporaryDirectory() as d:
            _a, _co, res = _run("device-only", tr, Path(d))
        self.assertEqual(res["n_requests"], 0)

    def test_always_cloud_one_request_per_opportunity(self):
        tr = _trace()
        with tempfile.TemporaryDirectory() as d:
            _a, co, res = _run("always-cloud-fcfs", tr, Path(d))
        n_opp = sum(1 for o in co.st.opps.values())
        self.assertEqual(res["n_requests"], n_opp,
                         f"{res['n_requests']} requests for {n_opp} opportunities")


class TestE_Determinism(unittest.TestCase):
    """Determinism is checked in `--dry-run`, which sends no HTTP and runs on a virtual clock.
    Under real HTTP the completion times are not reproducible, so a bit-identical decision log
    is not expected there; the wall-clock-derived field `decision_latency_ms` is excluded here
    for the same reason."""

    WALL = ("decision_latency_ms",)

    def test_same_trace_arm_seed_gives_the_same_decision_log(self):
        tr = _trace()
        for name in ("edf", "edf-piece2048", "b9", "policy-core"):
            with tempfile.TemporaryDirectory() as d:
                _run(name, tr, Path(d) / "r1")
                _run(name, tr, Path(d) / "r2")
                a = _strip(SC.read_jsonl(Path(d) / "r1" / "decision.jsonl"), self.WALL)
                b = _strip(SC.read_jsonl(Path(d) / "r2" / "decision.jsonl"), self.WALL)
                self.assertEqual(a, b, name)

    def test_a_different_seed_changes_the_trace(self):
        self.assertNotEqual(_trace(seed=1)["fairness_digest"], _trace(seed=3)["fairness_digest"])


class TestF_CacheIsolation(unittest.TestCase):
    """D84, verified on the bodies the coordinator actually built."""

    def test_every_request_carries_a_salt_and_a_uuid_per_frame(self):
        tr = _trace(frames=None)
        with tempfile.TemporaryDirectory() as d:
            a = _arm("always-cloud-fcfs")
            logs = Logs(Path(d)).open()
            co = Live2Coordinator(a, None, tr["events"], gpu_kv_tokens=GPU_KV,
                                 host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                                 window_s=WINDOW, drain_s=5.0, seed=1, logs=logs,
                                 run_tag=CK.run_tag(1, "always-cloud-fcfs"), dry_run=True)
            co.run()
            logs.close()
            reqs = SC.read_jsonl(Path(d) / "request.jsonl")
        self.assertGreater(len(reqs), 0)
        salts, uuids = {}, {}
        for r in reqs:
            self.assertTrue(r["cache_salt"], r)
            self.assertTrue(r["mm_uuids"], r)
            salts.setdefault(r["device_id"], set()).add(r["cache_salt"])
            for u in r["mm_uuids"]:
                uuids.setdefault((r["device_id"], u.rsplit("|", 1)[-1]), set()).add(u)
        out = CK.check_isolation(salts, uuids)
        self.assertGreaterEqual(out["n_distinct_salts"], 2)

    def test_the_same_device_keeps_one_uuid_per_frame_across_resends(self):
        tag = CK.run_tag(1, "x")
        u1 = CK.mm_uuid(tag, "rob000", "rob000/s0/play0", "f1.jpg")
        u2 = CK.mm_uuid(tag, "rob000", "rob000/s0/play0", "f1.jpg")
        u3 = CK.mm_uuid(tag, "rob001", "rob001/s0/play0", "f1.jpg")
        self.assertEqual(u1, u2)
        self.assertNotEqual(u1, u3)
        self.assertNotEqual(CK.cache_salt(tag, "rob000"), CK.cache_salt(tag, "rob001"))

    def test_the_wire_body_carries_the_fields(self):
        import bodies as B
        body = B.build_body(kind="recall", device_id="rob000", session_id="s0",
                            run_tag="tag", salt="SALT", header="h",
                            frames=[dict(frame_ref="a.jpg", path=None),
                                    dict(frame_ref="b.jpg", path=None)],
                            question="q?", options=["A"], est_tokens=100)
        self.assertEqual(body["cache_salt"], "SALT")
        parts = body["messages"][0]["content"]
        imgs = [p for p in parts if p.get("type") == "image_url"]
        self.assertEqual(len(imgs), 2)
        for p in imgs:
            self.assertTrue(p["uuid"])
            self.assertIsNone(p["image_url"])          # a uuid-only reference (StudyRH7)
        wire = B.strip_internal(body)
        self.assertNotIn("_live2", wire)
        self.assertIn("cache_salt", wire)


class _Deferrer(Policy):
    """Defers every query by DEFER_S, then takes it. Used to prove the run loop honours DEFER
    for an arm that emits it, which D90 requires of the loop and not of B9."""

    name = "deferrer"
    case = "naive"
    DEFER_S = 2.0

    def reset(self, seed=0):
        self.seen = {}

    def decide(self, obs: Observation) -> Action:
        rec = []
        for q in obs.recall:
            if q.query_id not in self.seen:
                self.seen[q.query_id] = obs.now_s
                rec.append(RecallAction(q.query_id, "DEFER", defer_s=self.DEFER_S))
            else:
                rec.append(RecallAction(q.query_id, "CLOUD", representation="D2"))
        return Action(recall=rec)


class TestG_Defer(unittest.TestCase):
    def test_a_deferred_item_is_not_submitted_before_defer_s(self):
        tr = _trace(duration=120.0)
        with tempfile.TemporaryDirectory() as d:
            arm = _Deferrer()
            logs = Logs(Path(d)).open()
            co = Live2Coordinator(arm, None, tr["events"], gpu_kv_tokens=GPU_KV,
                                  host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                                  window_s=120.0, drain_s=10.0, seed=1, logs=logs,
                                  dry_run=True)
            co.run()
            logs.close()
            decs = SC.read_jsonl(Path(d) / "decision.jsonl")
            reqs = SC.read_jsonl(Path(d) / "request.jsonl")
        deferred = {dd["opportunity_ids"][0]: dd["t"] for dd in decs if dd["kind"] == "defer"}
        self.assertGreater(len(deferred), 0, "the arm never deferred, so nothing was tested")
        by_dec = {dd["decision_id"]: dd for dd in decs}
        n_checked = 0
        for r in reqs:
            dd = by_dec.get(r["decision_id"]) or {}
            if dd.get("kind") != "release_recall":
                continue
            oid = dd["opportunity_ids"][0]
            if oid in deferred:
                self.assertGreaterEqual(r["t_submit"] + 1e-9,
                                        deferred[oid] + _Deferrer.DEFER_S,
                                        f"{oid} submitted before its defer_s elapsed")
                n_checked += 1
        self.assertGreater(n_checked, 0, "no deferred item was ever submitted")


class TestChaining(unittest.TestCase):
    """The prefix-chained rebuild at a REALISTIC history size, which the synthetic trace's
    short sessions do not reach: StudyENG1's 11,184-token D2 history (spec 5.3)."""

    TOK = 11_184

    def _session(self, co, est_tokens):
        co.st.register(dict(device_id="rob000", type="robot", uplink_mbps=13.6, rtt_ms=44.0,
                            start_t=0.0), "salt")
        co.st.session_start(dict(device_id="rob000", session_id="s0", t=0.0))
        n = est_tokens // CS.D2_TOK_PER_IMG
        co.st.history_append(dict(device_id="rob000", session_id="s0", batch_id="b0",
                                  t_arrive=0.0, frame_refs=[f"f{i}" for i in range(n)],
                                  est_tokens=est_tokens))
        return co.st.sessions["s0"]

    def _co(self):
        tr = _trace(duration=20.0)
        return Live2Coordinator(_arm("edf"), None, tr["events"], gpu_kv_tokens=GPU_KV,
                                host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                                window_s=20.0, dry_run=True)

    def test_a_1024_token_chain_completes_one_piece_at_a_time(self):
        co = self._co()
        s = self._session(co, self.TOK)
        seen = []
        for k in range(200):
            rid = co._advance_build(s, self.TOK, 1024, 0.1 * k, 0.0, {}, {})
            if rid is None:
                break
            b = co.builds[rid]
            seen.append(b["piece_tokens"])
            s.built_tokens += b["piece_tokens"]            # the completion the engine reports
        self.assertEqual(sum(seen), self.TOK, seen)
        self.assertEqual(len(seen), 11, seen)              # 10 x 1024 + a 944-token tail
        self.assertTrue(all(p <= 1024 for p in seen))

    def test_whole_is_one_request(self):
        co = self._co()
        s = self._session(co, self.TOK)
        rid = co._advance_build(s, self.TOK, None, 0.0, 0.0, {}, {})
        self.assertEqual(co.builds[rid]["piece_tokens"], self.TOK)

    def test_later_pieces_reference_the_already_sent_frames_rather_than_resending_bytes(self):
        co = self._co()
        s = self._session(co, self.TOK)
        co._advance_build(s, self.TOK, 1024, 0.0, 0.0, {}, {})
        s.built_tokens += 1024
        rid = co._advance_build(s, self.TOK, 1024, 0.1, 0.0, {}, {})
        body = next(sub.body for _f, sub in co.futures if sub.request_id == rid)
        parts = [p for p in body["messages"][0]["content"] if p.get("type") == "image_url"]
        refs = [p for p in parts if p["image_url"] is None]
        self.assertGreater(len(refs), 0, "the second piece re-sent every frame's bytes")
        self.assertEqual(body["_live2"]["n_new_frames"], len(parts) - len(refs))


class TestEmulatorBridge(unittest.TestCase):
    """The live2 coordinator driven through the FLEET EMULATOR's own Protocol
    (`fleet/emulator.py:76-78`), which is how the live run is wired."""

    def _bridge(self, mode="A"):
        from bridge import EmulatorBridge
        tr = _trace(duration=60.0, mode=mode)
        co = Live2Coordinator(_arm("always-cloud-fcfs"), None, [], gpu_kv_tokens=GPU_KV,
                              host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                              upload_mode=mode, window_s=60.0, dry_run=True)
        return EmulatorBridge(co), tr

    def test_it_satisfies_the_protocol_and_answers_events(self):
        br, tr = self._bridge()
        replies = []
        for e in tr["events"]:
            replies += list(br.on_event(e, T._sched(e)))
        for k in range(0, 70):
            replies += list(br.tick(float(k)))
        kinds = {r["kind"] for r in replies}
        self.assertTrue(hasattr(br, "on_event") and hasattr(br, "tick"))
        self.assertIn("cloud_answer", kinds, replies[:3])
        self.assertGreater(br.n_events, 0)
        for r in replies:
            SC.parse(r)                                   # every reply is on-schema
        self.assertEqual(br.describe()["arm"], "always-cloud-fcfs")

    def test_pull_mode_replies_with_pull_requests(self):
        br, tr = self._bridge(mode="B")
        replies = []
        for e in tr["events"]:
            replies += list(br.on_event(e, T._sched(e)))
        self.assertIn("pull_request", {r["kind"] for r in replies})

    def test_an_off_schema_event_is_refused_at_the_bridge(self):
        br, _tr = self._bridge()
        with self.assertRaises((ValueError, KeyError)):
            br.on_event(dict(kind="monitor_frame", device_id="dash000"), 0.0)


class TestH_CalibrationRefusal(unittest.TestCase):
    def test_interim_map_is_refused_on_a_real_server(self):
        m = CALIB.load_map()
        self.assertEqual(m["label"], "INTERIM")
        CALIB.require_runnable(m, "fake")
        with self.assertRaises(CALIB.CalibrationRefused):
            CALIB.require_runnable(m, "vllm")

    def test_a_final_map_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "final.json"
            p.write_text(json.dumps(dict(a=0.1, b=1.0, label="FINAL", fit_sample="dense",
                                         compare={"h100_32b": dict(a=0.12, b=1.8)})))
            m = CALIB.load_map(p)
            self.assertEqual(m["label"], "FINAL")
            CALIB.require_runnable(m, "vllm")

    def test_synthetic_trace_is_refused_on_a_real_server(self):
        tr = _trace(duration=20.0)
        T.require_fake_server(tr, "fake")
        with self.assertRaises(T.SyntheticTraceRefused):
            T.require_fake_server(tr, "vllm")


def _fleet_record(e):
    """The same event in the FLEET's internal record shape, so the two canonical digest
    implementations can be compared on one stream."""
    k = e["kind"]
    if k == "device_register":
        return dict(kind=k, device_id=e["device_id"], start_t=e["start_t"])
    if k in ("session_start", "session_end"):
        return dict(kind=k, device_id=e["device_id"], t=e["t"], session_id=e["session_id"])
    if k == "history_preload":
        return dict(kind="history_preload", device_id=e["device_id"], t=e["t"],
                    session_id=e["session_id"], est_tokens=e["est_tokens"])
    if k == "history_append":
        return dict(kind="history_batch", device_id=e["device_id"], t=e["t_arrive"],
                    batch_id=e["batch_id"], est_tokens=e["est_tokens"])
    if k == "recall_question":
        return dict(kind=k, device_id=e["device_id"], t=e["t_ask"],
                    opportunity_id=e["opportunity_id"], session_id=e["session_id"],
                    deadline_s=e["deadline_s"])
    if k in ("monitor_frame", "monitor_offer"):
        return dict(kind="monitor_opportunity", device_id=e["device_id"], t=e["t_capture"],
                    opportunity_id=e["opportunity_id"], deadline_s=e["deadline_s"])
    return None


def _opp_digest(co) -> str:
    """The opportunity stream the coordinator actually built for this arm. Under mode B the
    FRAMES each arm pulls differ by design (D69); the instants and questions may not."""
    import hashlib
    h = hashlib.sha256()
    for oid in co.st.order:
        o = co.st.opps[oid]
        h.update(repr((o.kind, o.device_id, o.opp_id, round(o.t_event, 4),
                       round(o.deadline_s, 4))).encode())
    return h.hexdigest()[:32]


def _strip(rows, drop):
    return [{k: v for k, v in r.items() if k not in drop} for r in rows]


def _sample(field: str):
    if field in ("device_id",):
        return "dash000"
    if field in ("session_id",):
        return "rob000/s0/play0"
    if field in ("instant_id", "question_id", "batch_id"):
        return "id0"
    if field == "opportunity_id":
        return "dash000|i00000"
    if field in ("type",):
        return "dashcam"
    if field in ("frame_refs",):
        return ["a.jpg", "b.jpg"]
    if field in ("options",):
        return ["A", "B"]
    if field in ("question",):
        return "q?"
    if field in ("frame_ref",):
        return "a.jpg"
    if field in ("payload",):
        return {"answer": "A"}
    if field in ("frame_bytes", "est_tokens"):
        return 100
    return 1.0


if __name__ == "__main__":
    unittest.main(verbosity=2)
