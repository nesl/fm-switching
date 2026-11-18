#!/usr/bin/env python3
"""StudyLIVE2-harness: the wire is unchanged, and the clock is driven in real time.

CPU only, nothing measured. Two things have to be true for this row to be a harness fix and not
a change of the experiment:

  1. the BYTES the coordinator sends are the bytes it sent before (the frame cache, the deferred
     image assembly and the fast serializer are all tested against the committed path);
  2. a run whose coordinator sits in another process presents the same events, carries the same
     fairness digest, and - with the child's self-ticking off, so both runs are a function of one
     clock - takes the same decisions line for line.

The third thing, that the fix actually fixes the lateness, is not a unit test: it is the
measured grid in `harness_checks.py`, reported in `reports/study_live2_coord.md`.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib"),
           str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import asyncbackend as AB                                              # noqa: E402
import bodies as B                                                     # noqa: E402
import framecache as FC                                                # noqa: E402
import harness_fixture as HF                                           # noqa: E402

BODY_KW = dict(device_id="dash000", session_id="s|p0", run_tag="rt", salt="dash000|rt",
               header="D2 history")


def _store(d: Path, n: int = 3):
    """A few frames with the committed byte lengths, and the refs for them."""
    sizes = HF.manifest_bytes()
    refs = list(sizes)[:n]
    HF.build_store(d, refs, sizes)
    return refs, sizes


def _shapes(refs, store: Path):
    """One body per kind the coordinator sends, mixing sent bytes with uuid references."""
    frames = [dict(frame_ref=r, path=(store / r)) for r in refs]
    frames[-1] = dict(frame_ref=refs[-1], path=None)          # an already-sent frame
    yield "monitor", dict(kind="monitor", frames=frames[:1], question=None, options=(),
                          max_tokens=4, **BODY_KW)
    yield "recall", dict(kind="recall", frames=frames, question="Where did I leave the mug?",
                         options=["A. kitchen", "B. hall"], max_tokens=4, **BODY_KW)
    yield "piece", dict(kind="piece", frames=frames, question=None, options=(),
                        max_tokens=1, est_tokens=9000, **BODY_KW)
    yield "append", dict(kind="append", frames=frames, question=None, options=(),
                         max_tokens=1, est_tokens=3091, **BODY_KW)


class TestTheWireIsUnchanged(unittest.TestCase):
    def test_the_cache_returns_what_the_committed_encoder_returned(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            refs, _sizes = _store(d)
            cache = FC.FrameCache(d)
            for ref in refs:
                self.assertEqual(cache.data_url(ref), B._data_url(d / ref))
            # a second read is a hit and returns the identical string
            self.assertEqual(cache.data_url(refs[0]), B._data_url(d / refs[0]))
            self.assertGreater(cache.stats()["hits"], 0)

    def test_a_deferred_body_materializes_to_the_immediate_body(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            refs, _ = _store(d)
            cache = FC.FrameCache(d)
            for name, kw in _shapes(refs, d):
                now = B.build_body(**kw)
                later = B.materialize(B.build_body(defer_images=True, **kw), cache)
                self.assertEqual(json.dumps(now, sort_keys=True),
                                 json.dumps(later, sort_keys=True), name)

    def test_a_deferred_body_is_never_sent_unmaterialized(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            refs, _ = _store(d)
            body = B.build_body(defer_images=True, **dict(
                kind="monitor", frames=[dict(frame_ref=refs[0], path=(Path(d) / refs[0]))],
                question=None, options=(), max_tokens=4, **BODY_KW))
            self.assertFalse(B.is_materialized(body))
            self.assertIn(B.DEFERRED, json.dumps(body))
            B.materialize(body, FC.FrameCache(d))
            self.assertTrue(B.is_materialized(body))
            self.assertNotIn(B.DEFERRED, json.dumps(body))

    def test_a_deferred_part_whose_frame_vanished_raises(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            body = B.build_body(defer_images=True, **dict(
                kind="monitor", frames=[dict(frame_ref="gone.jpg", path=(Path(d) / "gone.jpg"))],
                question=None, options=(), max_tokens=4, **BODY_KW))
            with self.assertRaises(FileNotFoundError):
                B.materialize(body, FC.FrameCache(d))

    def test_the_fast_serializer_is_json(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            refs, _ = _store(d)
            cache = FC.FrameCache(d)
            for name, kw in _shapes(refs, d):
                body = B.materialize(B.build_body(defer_images=True, **kw), cache)
                wire = B.strip_internal(body, strip_hints=True)
                fast = AB.wire_bytes(wire)
                self.assertEqual(json.loads(fast), json.loads(json.dumps(wire)), name)

    def test_the_serializer_falls_back_when_a_url_would_need_escaping(self):
        body = dict(model="32BI", messages=[dict(role="user", content=[
            {"type": "image_url", "image_url": {"url": 'da"ta\\x'}, "uuid": "u1"}])])
        self.assertEqual(json.loads(AB.wire_bytes(body)),
                         json.loads(json.dumps(body)))


class TestTheFixtureStore(unittest.TestCase):
    def test_every_fixture_frame_has_its_committed_byte_length(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sizes = HF.manifest_bytes()
            refs = list(sizes)[:6]
            info = HF.build_store(d, refs, sizes)
            self.assertEqual(info["n_frames"], 6)
            self.assertEqual(info["n_missing"], 0)
            for ref in refs:
                self.assertEqual((d / ref).stat().st_size, sizes[ref], ref)

    def test_the_byte_counts_come_from_the_committed_manifests(self):
        sizes = HF.manifest_bytes()
        n = 0
        for name in HF.NAMES:
            for ln in gzip.open(HF.MANIFESTS / f"{name}_manifest.jsonl.gz", "rt"):
                r = json.loads(ln)
                self.assertEqual(sizes[r["frame_ref"]], int(r["bytes"]))
                n += 1
        self.assertEqual(n, len(sizes))
        self.assertEqual(n, 74156)

    def test_the_fixture_is_reproducible_from_the_frame_ref(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            sizes = HF.manifest_bytes()
            refs = list(sizes)[:3]
            HF.build_store(Path(a), refs, sizes)
            HF.build_store(Path(b), refs, sizes)
            for ref in refs:
                self.assertEqual((Path(a) / ref).read_bytes(), (Path(b) / ref).read_bytes())


class TestTheRealTimeTick(unittest.TestCase):
    """The step-1 finding, as a test: a coordinator is driven while the loop WAITS."""

    def test_a_waiting_loop_still_ticks_the_coordinator(self):
        import emulator as EM
        import trace as TR

        class Counting:
            kind = "stub"

            def __init__(self):
                self.ticks = []
                self.events = 0

            def on_event(self, event, t):
                self.events += 1
                return ()

            def tick(self, t):
                self.ticks.append(t)
                return ()

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = d / "trace"
            TR.write_trace(tdir, TR.generate_trace(1, 4, "50:50", 6.0, "A"))
            co = Counting()
            em = EM.FleetEmulator(tdir, co, "A", realtime=True, drain_s=1.0)
            em.run(d / "run")
            lat = em.lateness.stats()
        # the window is 6 s and the tick is 10 ms, so a loop that only ticked when an action
        # popped would produce far fewer than this
        self.assertGreater(len(co.ticks), 300, len(co.ticks))
        self.assertEqual(co.ticks, sorted(co.ticks), "ticks must be monotonic")
        self.assertLess(lat["p99_ms"], 50.0, lat)

    def test_a_non_realtime_run_still_ticks_exactly_as_before(self):
        import emulator as EM
        import trace as TR

        class Counting:
            kind = "stub"

            def __init__(self):
                self.ticks = []

            def on_event(self, event, t):
                return ()

            def tick(self, t):
                self.ticks.append(t)
                return ()

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = d / "trace"
            TR.write_trace(tdir, TR.generate_trace(1, 4, "50:50", 6.0, "A"))
            co = Counting()
            em = EM.FleetEmulator(tdir, co, "A", realtime=False, drain_s=1.0)
            em.run(d / "run")
        # a non-real-time run has no wall clock to wait on, so the ticks are the old catch-up
        # grid: one per tick_s up to the last action, and nothing else
        self.assertEqual(co.ticks, sorted(co.ticks))
        step = em.tick_s
        self.assertTrue(all(abs(b - a - step) < 1e-9 for a, b in zip(co.ticks, co.ticks[1:])),
                        "the non-real-time tick grid is no longer uniform")


class TestTheProcessSplit(unittest.TestCase):
    def test_a_split_run_decides_exactly_as_an_in_process_run(self):
        import emulator as EM
        import procsplit as PS
        import trace as TR
        from bridge import EmulatorBridge
        from coordinator import Live2Coordinator, Logs
        from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK, _arm
        import arms as A

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = d / "trace"
            TR.write_trace(tdir, TR.generate_trace(3, 4, "50:50", 30.0, "A"))

            r1 = d / "inproc"
            logs = Logs(r1).open()
            co = Live2Coordinator(_arm("edf"), None, [], gpu_kv_tokens=GPU_KV,
                                  host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                                  upload_mode="A", window_s=30.0, drain_s=5.0, seed=3,
                                  logs=logs, run_tag="rt", dry_run=True)
            br = EmulatorBridge(co)
            br.kind = "stub"
            EM.FleetEmulator(tdir, br, "A", realtime=False, drain_s=5.0).run(r1)
            logs.close()

            r2 = d / "split"
            cfg = dict(run_dir=str(r2), arm="edf", arm_kwargs={}, mode="A", run_s=30.0,
                       drain_s=5.0, decision_period_s=0.1, gpu_kv_tokens=GPU_KV,
                       host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, seed=3,
                       run_tag="rt", frames_root=None, server_url=None,
                       defer_images=True, self_tick_s=0.0)
            with PS.SplitRun(cfg, kind="stub") as remote:
                EM.FleetEmulator(tdir, remote, "A", realtime=False, drain_s=5.0).run(r2)

            m1 = json.loads((r1 / "run_meta.json").read_text())
            m2 = json.loads((r2 / "run_meta.json").read_text())
            self.assertEqual(m1["fairness_digest"], m2["fairness_digest"])
            self.assertEqual(m1["trace_fairness_digest"], m2["trace_fairness_digest"])
            self.assertTrue(m2["digests_equal"])
            o1 = sorted(json.loads(l)["opportunity_id"]
                        for l in open(r1 / "outcomes.jsonl"))
            o2 = sorted(json.loads(l)["opportunity_id"]
                        for l in open(r2 / "outcomes.jsonl"))
            self.assertEqual(o1, o2)
            d1 = [json.loads(l) for l in open(r1 / "decision.jsonl")]
            d2 = [json.loads(l) for l in open(r2 / "decision.jsonl")]
            strip = ("decision_latency_ms",)
            self.assertEqual([{k: v for k, v in x.items() if k not in strip} for x in d1],
                             [{k: v for k, v in x.items() if k not in strip} for x in d2],
                             "the split run took different decisions")

    def test_the_socket_path_stays_inside_the_af_unix_limit(self):
        import procsplit as PS
        p = PS.SplitRun._short_sock()
        self.assertLess(len(p.encode()), 100, p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
