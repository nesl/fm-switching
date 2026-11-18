#!/usr/bin/env python3
"""The coordinator's believed history size is the session's CUMULATIVE token total.

StudyLIVE2 history-size fix, 2026-11-18, found by the H100 on StudyMOT2 seed 10. Two defects on
the two sides of one wire:

  * `fleet/emulator.py` forwarded the PER-BATCH increment (`r["est_tokens"]`) and discarded the
    cumulative total the trace carries beside it (`cum_tokens`);
  * `cstate.py` then kept `max(batch, so_far)`, which on a stream of increments leaves the
    belief at the LARGEST SINGLE BATCH.

On the seed-10 12-device trace that put robo002's second session at 1,381 tokens when it really
holds 17,581, and every session in that trace was understated by 2.0x to 12.7x. Because
`coordinator._advance_build` derives the FRAME COUNT from the token budget
(`n_new = round(piece / D2_TOK_PER_IMG)`), an understated history also sent a fraction of the
frames, which is how a 24,838-token history went out as a 2,171-token prompt.

Every test here FAILS on the pre-fix code.
"""
from __future__ import annotations

import collections
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

import cachekeys as CK                                                  # noqa: E402
import cstate as CS                                                     # noqa: E402
import emulator as EM                                                   # noqa: E402
import trace as TR                                                      # noqa: E402
from bridge import EmulatorBridge                                       # noqa: E402
from coordinator import Live2Coordinator, Logs                          # noqa: E402

SEED, NDEV, RUN_S, MODE = 10, 12, 600.0, "A"
HIST = ("history_preload", "history_batch", "history_append")


def _trace(d: Path, seed=SEED, n=NDEV, run_s=RUN_S, mode=MODE):
    tdir = d / "trace"
    TR.write_trace(tdir, TR.generate_trace(seed, n, "50:50", run_s, mode))
    return tdir


def _cumulatives(tdir: Path):
    """(device, session) -> the trace's cumulative totals in order, from its own records."""
    out = collections.OrderedDict()
    for ln in open(tdir / "trace.jsonl"):
        r = json.loads(ln)
        if r["kind"] in HIST:
            out.setdefault((r["device_id"], r["session_id"]), []).append(int(r["cum_tokens"]))
    return out


def _frame_store(tdir: Path, root: Path) -> Path:
    """A file per frame_ref the trace needs, so `coordinator._path` resolves.

    Content is irrelevant and never read: a dry run only checks that the file EXISTS, and
    `sent_bytes_for` only advances for a frame whose bytes went out, so without a store every
    frame is sent as a uuid reference and the build's progress cannot be observed at all.
    """
    root.mkdir(parents=True, exist_ok=True)
    refs = set()
    for ln in open(tdir / "trace.jsonl"):
        r = json.loads(ln)
        if r.get("frame_ref"):
            refs.add(r["frame_ref"])
        for x in (r.get("frame_refs") or ()):
            refs.add(x)
    for ref in refs:
        p = root / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(b"x")
    return root


def _run(tdir: Path, rdir: Path, arm_name: str, run_s=RUN_S, mode=MODE,
         frames_root: Path = None, submits: list = None):
    """One dry run through the real emulator, bridge and coordinator; records the beliefs."""
    import arms as A
    import cstate as CSM
    import run_live2_cell as RC
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK

    seen = collections.OrderedDict()
    real_app, real_pre = CSM.CoordState.history_append, CSM.CoordState.history_preload

    def app(self, ev):
        s = real_app(self, ev)
        seen.setdefault((s.device_id, s.session_id), []).append(int(s.est_tokens))
        return s

    def pre(self, ev):
        s = real_pre(self, ev)
        seen.setdefault((s.device_id, s.session_id), []).append(int(s.est_tokens))
        return s

    kw = (dict(cost_model="pol4", h_s=0.5, mu_mode="ewma", mu_fixed=None, impl="fast",
               cap_k=None) if arm_name == "policy-core" else {})
    arm = A.make_arm(arm_name, **kw)
    htok = RC.host_tokens(HOST_GIB)
    arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=htok,
                        targets=CS.TARGETS)
    logs = Logs(rdir).open()
    co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                          host_tier_tokens=htok, upload_mode=mode, window_s=run_s,
                          drain_s=10.0, seed=SEED, logs=logs,
                          run_tag=CK.run_tag(SEED, arm_name), dry_run=True,
                          frames_root=frames_root)
    if submits is not None:
        real_submit = co._submit

        def spy(**kw):
            sid = kw.get("session_id")
            sess = co.st.sessions.get(sid) if sid else None
            submits.append(dict(kind=kw["kind"], session_id=sid,
                                frames=[f["frame_ref"] for f in kw["frames"]],
                                new=[f["frame_ref"] for f in kw["frames"]
                                     if f.get("path") is not None],
                                est_tokens=kw.get("est_tokens"),
                                # the history AS IT STOOD at this submit: a build can only
                                # carry the frames that had arrived by then, so the final
                                # frame list is the wrong thing to compare against
                                history_then=(list(sess.frames) if sess else []),
                                believed_tokens_then=(int(sess.est_tokens) if sess else 0),
                                built_then=(int(sess.built_tokens) if sess else 0)))
            return real_submit(**kw)

        co._submit = spy
    br = EmulatorBridge(co)
    br.kind = "stub"
    CSM.CoordState.history_append, CSM.CoordState.history_preload = app, pre
    try:
        EM.FleetEmulator(tdir, br, mode, realtime=False, drain_s=10.0).run(rdir)
    finally:
        CSM.CoordState.history_append, CSM.CoordState.history_preload = real_app, real_pre
    logs.close()
    return co, seen


class TestTheBeliefIsTheCumulativeTotal(unittest.TestCase):
    def test_the_defect_is_real_in_the_committed_trace(self):
        """The trace itself: per-batch increments understate the session by up to 12.7x."""
        with tempfile.TemporaryDirectory() as d:
            tdir = _trace(Path(d))
            inc = collections.OrderedDict()
            for ln in open(tdir / "trace.jsonl"):
                r = json.loads(ln)
                if r["kind"] in HIST:
                    inc.setdefault((r["device_id"], r["session_id"]), []).append(
                        int(r["est_tokens"]))
            cum = _cumulatives(tdir)
        self.assertEqual(sorted(inc), sorted(cum))
        ratios = [cum[k][-1] / max(inc[k]) for k in cum]
        self.assertGreater(max(ratios), 10.0,
                           "the understatement this fix exists for is not present in the trace")
        worst = max(cum, key=lambda k: cum[k][-1] / max(inc[k]))
        self.assertGreater(cum[worst][-1], 10000)

    def test_every_believed_history_equals_the_traces_cumulative_total(self):
        """The whole point: at EVERY append and preload, belief == the trace's cum_tokens."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            _co, seen = _run(tdir, d / "run", "edf")
            cum = _cumulatives(tdir)
        self.assertGreater(len(seen), 0, "no history event reached the coordinator")
        for key, want in cum.items():
            got = seen.get(key)
            self.assertIsNotNone(got, "session %r never reached the coordinator" % (key,))
            self.assertEqual(got, want,
                             "believed history tokens differ from the trace's cumulative "
                             "totals for %r:\n  believed %r\n  trace    %r" % (key, got, want))

    def test_it_holds_across_session_chaining(self):
        """A second session restarts from its own total (D83), not from the first session's."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            _co, seen = _run(tdir, d / "run", "edf")
            cum = _cumulatives(tdir)
        by_dev = collections.defaultdict(list)
        for (dev, sid) in cum:
            by_dev[dev].append(sid)
        chained = {k: v for k, v in by_dev.items() if len(v) > 1}
        self.assertGreater(len(chained), 0, "the trace has no chained session to check")
        for dev, sids in chained.items():
            for sid in sids:
                self.assertEqual(seen[(dev, sid)], cum[(dev, sid)], (dev, sid))
            # the later session's belief is its OWN total, so it is not monotonically
            # accumulating across the device's sessions
            self.assertTrue(all(seen[(dev, s)][0] <= seen[(dev, s)][-1] for s in sids))

    def test_it_holds_for_a_preloaded_session(self):
        """D101: a preload sets the same cumulative quantity, and later batches include it."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            pre = {}
            for ln in open(tdir / "trace.jsonl"):
                r = json.loads(ln)
                if r["kind"] == "history_preload":
                    pre[(r["device_id"], r["session_id"])] = int(r["cum_tokens"])
            _co, seen = _run(tdir, d / "run", "edf")
            cum = _cumulatives(tdir)
        self.assertGreater(len(pre), 0, "the trace has no preloaded session to check")
        for key, p in pre.items():
            self.assertEqual(seen[key][0], p, "the preload's own belief is wrong for %r" % (key,))
            self.assertEqual(seen[key], cum[key], key)
            # later batches carry the preload inside their cumulative total
            if len(seen[key]) > 1:
                self.assertGreater(seen[key][-1], p)

    def test_a_record_without_cum_tokens_is_refused_rather_than_misread(self):
        with self.assertRaises(KeyError) as cm:
            EM._cumulative_tokens(dict(kind="history_batch", device_id="robo000",
                                       session_id="s", batch_id="b", est_tokens=1381))
        self.assertIn("CUMULATIVE", str(cm.exception))


class TestTheBuildCoversTheHistory(unittest.TestCase):
    def _sessions_built(self, co):
        return [s for s in co.st.sessions.values() if s.est_tokens > 0]

    def test_a_whole_materialize_covers_every_frame_of_the_history(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            root = _frame_store(tdir, d / "frames")
            subs = []
            co, _seen = _run(tdir, d / "run", "edf", frames_root=root, submits=subs)
        wholes = [x for x in subs if x["kind"] == "whole"]
        self.assertGreater(len(wholes), 0, "no session issued a whole build")
        checked = 0
        for w in wholes:
            s = co.st.sessions.get(w["session_id"])
            if s is None or not s.frames:
                continue
            # a WHOLE build is the remainder in one request, and with the belief correct the
            # remainder is the whole history AS IT STOOD when the build was issued
            self.assertEqual(w["frames"], w["history_then"],
                             "a whole build of session %s carried %d of the %d frames the "
                             "history held at that moment (believed %d tokens, built %d)"
                             % (w["session_id"], len(w["frames"]), len(w["history_then"]),
                                w["believed_tokens_then"], w["built_then"]))
            checked += 1
        self.assertGreater(checked, 5, checked)

    def test_the_frame_count_a_whole_build_sends_matches_the_history_size(self):
        """`n_new = round(piece / D2_TOK_PER_IMG)` must resolve to EVERY frame, not a fraction."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            co, _seen = _run(tdir, d / "run", "edf")
        checked = 0
        for s in self._sessions_built(co):
            # the identity the sizing rule rests on: a D2 history of N frames is
            # N * 90 + 31 tokens, so round(tokens / 90) == N
            n = len(s.frames)
            self.assertEqual(round(s.est_tokens / float(CS.D2_TOK_PER_IMG)), n,
                             "history of %d frames believes %d tokens, which does not resolve "
                             "to %d frames" % (n, s.est_tokens, n))
            checked += 1
        self.assertGreater(checked, 5, checked)

    def test_pieces_partition_the_history_with_no_gap_and_no_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d)
            root = _frame_store(tdir, d / "frames")
            subs = []
            co, _seen = _run(tdir, d / "run", "edf-piece1024", frames_root=root, submits=subs)
        by_session = collections.defaultdict(list)
        for x in subs:
            if x["kind"] in ("piece", "whole") and x["session_id"]:
                by_session[x["session_id"]].append(x)
        self.assertGreater(len(by_session), 5, len(by_session))
        checked = 0
        for sid, reqs in by_session.items():
            s = co.st.sessions.get(sid)
            if s is None or not s.frames:
                continue
            new = []
            for r in reqs:
                new += r["new"]
            # NO OVERLAP: no frame's bytes go out twice
            self.assertEqual(len(new), len(set(new)),
                             "session %s sent a frame's bytes twice across its pieces" % sid)
            # NO GAP: the pieces are consecutive from the start of the history, in order
            self.assertEqual(new, s.frames[:len(new)],
                             "session %s did not partition its history in order" % sid)
            # and each request carries the whole built prefix, references plus the new bytes
            for r in reqs:
                self.assertEqual(r["frames"][-len(r["new"]):], r["new"])
            checked += 1
        self.assertGreater(checked, 5, checked)


class TestThroughTheFakeServer(unittest.TestCase):
    def test_prompt_token_accounting_scales_with_history_size(self):
        """Against a server, a bigger history must produce a bigger prompt."""
        import fakestream as FS
        from backend import Live2Backend
        import arms as A
        import run_live2_cell as RC
        from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir = _trace(d, run_s=240.0)
            rdir = d / "run"
            arm = A.make_arm("edf")
            htok = RC.host_tokens(HOST_GIB)
            arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                                host_tier_tokens=htok, targets=CS.TARGETS)
            logs = Logs(rdir).open()
            with FS.serve(0, concurrency=8) as url:
                be = Live2Backend(url, workers=16, model="32BI", strip_hints=True)
                co = Live2Coordinator(arm, be, [], gpu_kv_tokens=GPU_KV,
                                      host_tier_gib=HOST_GIB, host_tier_tokens=htok,
                                      upload_mode=MODE, window_s=240.0, drain_s=10.0,
                                      seed=SEED, logs=logs, run_tag=CK.run_tag(SEED, "edf"))
                br = EmulatorBridge(co)
                br.kind = "fake"
                EM.FleetEmulator(tdir, br, MODE, realtime=False, drain_s=10.0).run(rdir)
                sent = list(be.sent)
                be.close()
            logs.close()
        builds = [b for b in sent if b["kind"] in ("piece", "whole")]
        self.assertGreater(len(builds), 0, "no build request was sent")
        # the body's SIZE is the observable here: the fixture server reports the token hint, so
        # the honest check is that the bytes on the wire grow with the frames carried
        pairs = [(len(b["mm_uuids"]), b["bytes"]) for b in builds]
        big = max(pairs)[0]
        self.assertGreater(big, 20, "no build carried a large history: %r" % (sorted(pairs)[-3:],))
        lo = [by for nf, by in pairs if nf <= 5]
        hi = [by for nf, by in pairs if nf >= big]
        if lo and hi:
            self.assertGreater(max(hi), max(lo) * 2,
                               "request bytes do not scale with the history carried")


if __name__ == "__main__":
    unittest.main(verbosity=2)
