#!/usr/bin/env python3
"""StudyLIVE2-fix2: the scored bodies, the committed extraction, and the two encode parsers.

CPU only, no GPU, nothing measured. Run with

  PYTHONPATH=experiments/orchestration/live2 python3 -m unittest discover -s .../tests

The point of this module is that NOTHING here states the committed request form in its own
words: every expected value is read out of the committed study script or the committed manifest,
so a test passing means the live body IS the committed body, not that it matches a copy of it.
"""
from __future__ import annotations

import ast
import base64
import gzip
import hashlib
import io
import json
import math
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(LIVE2 / "fleet"), str(LIVE2 / "scorer"), str(LIVE2 / "data"),
           str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/sim"), str(ROOT / "experiments/lib"),
           str(ROOT / "experiments/sember"),
           str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bodies as B                                                      # noqa: E402
import cachekeys as CK                                                  # noqa: E402
import scores as S2                                                     # noqa: E402
import schema as SCH                                                    # noqa: E402
import traces as T                                                      # noqa: E402
from backend import Live2Backend                                        # noqa: E402
from coordinator import Live2Coordinator, Logs                          # noqa: E402

D3 = ROOT / "experiments/dashcam/d3_infer_vllm.py"
R1_MANIFEST = ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
SEMBER_MCQ = ROOT / "results/sember/study_h/data/sember_mcq.jsonl"

# The ONLY differences the live bodies are allowed to have from the committed ones.
SH_EXEMPTIONS = (
    "image bytes and media type (round 1 sends the stored JPEGs, D70/D91)",
    "the D84 cache keys: top-level cache_salt and the per-image client uuid",
    "stream / stream_options: live2 times the first token, as StudyORIN1-dense and StudyD15 do",
)


def _committed_d3_body():
    """StudyD3's own `body()` and `grey_header()`, executed out of the committed script.

    The grey path is used because it builds the same content shape from bytes in hand, with no
    frame-store read, so this test runs on flash where the frame pools do not exist.
    """
    src = ast.parse(D3.read_text(), filename=str(D3))
    want_f = {"body", "grey_header"}
    want_c = {"QUERY", "GEN"}
    body = [n for n in src.body
            if (isinstance(n, ast.FunctionDef) and n.name in want_f)
            or (isinstance(n, ast.Assign)
                and {t.id for t in n.targets if isinstance(t, ast.Name)} & want_c)]
    got_f = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    if got_f != want_f:
        raise AssertionError(f"d3_infer_vllm.py no longer defines {sorted(want_f)}: {got_f}")
    ns = {"base64": base64, "hashlib": hashlib, "Path": Path, "math": math}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(D3), "exec"), ns)   # noqa: S102
    return ns


def _normalise(body):
    """Strip exactly the declared exemptions, leaving everything else to be compared."""
    out = json.loads(json.dumps(body))
    out.pop("cache_salt", None)
    out.pop("stream", None)
    out.pop("stream_options", None)
    for part in out["messages"][0]["content"]:
        if part.get("type") != "image_url":
            continue
        part.pop("uuid", None)
        part["image_url"] = "<IMAGE BYTES>"
    return out


class TestTheShBodyIsTheCommittedOne(unittest.TestCase):
    def setUp(self):
        self.ns = _committed_d3_body()
        png = io.BytesIO()
        from PIL import Image
        Image.new("RGB", (8, 8), (128, 128, 128)).save(png, format="PNG")
        self.grey = png.getvalue()

    def _live_body(self):
        return B.build_body(kind="monitor", device_id="dash000", session_id=None,
                            run_tag="rt", salt="dash000|rt", header="ignored by the contract",
                            frames=[dict(frame_ref="01040.mp4|t0003.00", path=None)],
                            question=None, options=(), max_tokens=4, est_tokens=378)

    def test_the_question_and_generation_parameters_come_from_the_committed_script(self):
        self.assertEqual(B.SH_QUERY, self.ns["QUERY"])
        self.assertEqual(B.SH_GEN, self.ns["GEN"])
        self.assertEqual(B.SH_HEADER, self.ns["grey_header"](1))

    def test_the_body_is_byte_identical_under_the_declared_exemptions(self):
        committed, _h, _hdr = self.ns["body"]({"request_id": "x"}, "32BI", grey=self.grey, n=1)
        live = B.strip_internal(self._live_body(), strip_hints=True)
        a = json.dumps(_normalise(committed), sort_keys=True)
        b = json.dumps(_normalise(live), sort_keys=True)
        self.assertEqual(a, b)

    def test_the_exemptions_are_exactly_the_three_declared_ones(self):
        committed, _h, _hdr = self.ns["body"]({"request_id": "x"}, "32BI", grey=self.grey, n=1)
        live = B.strip_internal(self._live_body(), strip_hints=True)
        extra = set(live) - set(committed)
        missing = set(committed) - set(live)
        self.assertEqual(extra, {"cache_salt", "stream_options"})
        self.assertEqual(missing, set())
        self.assertFalse(committed["stream"])
        self.assertTrue(live["stream"])
        img = [p for p in live["messages"][0]["content"] if p.get("type") == "image_url"]
        self.assertEqual(len(img), 1)
        self.assertIn("uuid", img[0])
        self.assertEqual(len(SH_EXEMPTIONS), 3)

    def test_one_frame_per_call_is_enforced(self):
        with self.assertRaises(ValueError):
            B.build_body(kind="monitor", device_id="d", session_id=None, run_tag="rt", salt="s",
                         header="h", frames=[dict(frame_ref="a", path=None),
                                             dict(frame_ref="b", path=None)],
                         question=None, options=(), max_tokens=4)

    def test_a_caller_may_not_substitute_the_question(self):
        with self.assertRaises(ValueError):
            B.build_body(kind="monitor", device_id="d", session_id=None, run_tag="rt", salt="s",
                         header="h", frames=[dict(frame_ref="a", path=None)],
                         question="is anything happening?", options=(), max_tokens=4)


class TestTheCommittedExtraction(unittest.TestCase):
    def test_the_extractor_is_the_committed_function_itself(self):
        src = ast.parse(D3.read_text(), filename=str(D3))
        fn = [n for n in src.body if isinstance(n, ast.FunctionDef) and n.name == "yes_no"]
        self.assertEqual(len(fn), 1)
        self.assertEqual(S2.yes_no.__name__, "yes_no")
        self.assertEqual(S2.yes_no.__code__.co_consts, compile(
            ast.Module(body=fn, type_ignores=[]), str(D3), "exec").co_consts[0].co_consts)

    def test_the_score_is_the_log_of_p_yes(self):
        lp = [{"top_logprobs": [{"token": "Yes", "logprob": -0.5},
                                {"token": " No", "logprob": -1.5}]}]
        p, y, n = S2.yes_no(lp)
        got = S2.sh_score(lp)
        self.assertAlmostEqual(got["p_yes"], p)
        self.assertAlmostEqual(got["cloud_score"], math.log(p))
        self.assertAlmostEqual(p, y / (y + n))

    def test_neither_yes_nor_no_is_unknown_not_a_number(self):
        lp = [{"top_logprobs": [{"token": "Maybe", "logprob": -0.1}]}]
        got = S2.sh_score(lp)
        self.assertIsNone(got["cloud_score"])
        self.assertTrue(got["neither"])
        self.assertIsNone(S2.sh_score(None)["cloud_score"])

    def test_the_first_token_is_taken_out_of_a_stream(self):
        chunks = [dict(logprobs={"content": []}),
                  dict(logprobs={"content": [{"top_logprobs": [{"token": "Yes",
                                                                "logprob": -0.2}]}]}),
                  dict(logprobs={"content": [{"top_logprobs": [{"token": "No",
                                                                "logprob": -0.3}]}]})]
        first = S2.first_token_logprobs(chunks)
        self.assertEqual(first[0]["top_logprobs"][0]["token"], "Yes")
        self.assertIsNone(S2.first_token_logprobs([]))


class TestTheRecallBodyIsStudyR1s(unittest.TestCase):
    def test_the_question_text_matches_every_committed_r1_row(self):
        mcq = {}
        with open(SEMBER_MCQ) as fh:
            for ln in fh:
                r = json.loads(ln)
                opts = r["options"]
                if isinstance(opts, str):
                    opts = ast.literal_eval(opts)
                mcq[r["question_id"]] = (r["question"], list(opts))
        n = 0
        for ln in gzip.open(R1_MANIFEST, "rt"):
            r = json.loads(ln)
            if r["question_id"] not in mcq:
                continue
            q, opts = mcq[r["question_id"]]
            self.assertEqual(B.recall_question_text(q, opts), r["text"],
                             f"question text differs on {r['question_id']}")
            n += 1
        self.assertEqual(n, 1690, f"{n} committed R1 rows were compared, expected 1690")

    def test_the_generation_parameters_are_studyr1_cell_k1(self):
        cells = S2.committed_constant(S2.R1_SCRIPT, "CELLS")
        self.assertEqual(cells["K1"][0], "32BI")
        want = dict(cells["K1"][2], seed=S2.committed_constant(S2.R1_SCRIPT, "SEED"))
        self.assertEqual(B.RECALL_GEN, want)

    def test_the_live_recall_body_carries_that_text_and_those_parameters(self):
        body = B.build_body(kind="recall", device_id="robo000", session_id="s|p0",
                            run_tag="rt", salt="robo000|rt", header="D2 history",
                            frames=[dict(frame_ref="s|f000002.00", path=None)],
                            question="Where did I leave the mug?",
                            options=["A. kitchen", "B. hall"], max_tokens=4)
        txt = [p["text"] for p in body["messages"][0]["content"] if p.get("type") == "text"]
        self.assertEqual(txt[-1], B.recall_question_text("Where did I leave the mug?",
                                                         ["A. kitchen", "B. hall"]))
        for k, v in B.RECALL_GEN.items():
            self.assertEqual(body[k], v)

    def test_the_answer_parser_is_studyr1s(self):
        self.assertEqual(S2.recall_letter("The answer is B.")["cloud_letter"], "B")
        self.assertEqual(S2.recall_letter("no letter here")["cloud_letter"], "X")
        self.assertEqual(S2.recall_letter("A then later D")["cloud_letter"], "D")


# ---------------------------------------------------------------- a scoring fake server
class _ScoringHandler(BaseHTTPRequestHandler):
    """An OpenAI-compatible stub that answers with logprobs, which the LIVE1 stub does not.

    It is a TEST FIXTURE: the token it returns is fixed and no number it produces may enter a
    measured result. `server_kind` stays "fake" in every run that uses it.
    """
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):                                              # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        letter = "Yes" if body.get("logprobs") else "B"
        lp = {"content": [{"token": letter, "logprob": -0.2,
                           "top_logprobs": [{"token": "Yes", "logprob": -0.2},
                                            {"token": "No", "logprob": -1.8}]}]}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for i, piece in enumerate((letter, "")):
            ch = dict(id="scored", object="chat.completion.chunk",
                      choices=[dict(index=0, delta=dict(content=piece),
                                    logprobs=(lp if i == 0 else None),
                                    finish_reason=None if i == 0 else "stop")],
                      usage=(dict(prompt_tokens=int(body.get("fm_tokens") or 1),
                                  completion_tokens=1) if i else None))
            self.wfile.write(("data: " + json.dumps(ch) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class _Serve:
    def __enter__(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _ScoringHandler)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        return "http://127.0.0.1:%d" % self.srv.server_address[1]

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()


def _run_scored(out: Path, window: float = 12.0):
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK, _arm
    tr = T.synthetic(n_dashcam=1, n_robot=1, duration_s=window, seed=1, upload_mode="A")
    T.require_fake_server(tr, "fake")
    logs = Logs(Path(out)).open()
    with _Serve() as url:
        be = Live2Backend(url, workers=8)
        co = Live2Coordinator(_arm("always-cloud-fcfs"), be, tr["events"], gpu_kv_tokens=GPU_KV,
                              host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                              upload_mode="A", window_s=window, drain_s=5.0, seed=1,
                              logs=logs, run_tag=CK.run_tag(1, "fix2"))
        res = co.run()
        be.close()
    logs.close()
    return co, res


class TestTheCoordinatorRecordsTheScore(unittest.TestCase):
    def test_every_monitor_answer_carries_a_cloud_score(self):
        with tempfile.TemporaryDirectory() as d:
            co, res = _run_scored(Path(d))
        self.assertEqual(res["n_errors"], 0, res.get("first_errors"))
        mon = [a for a in co.cloud_answers if a["payload"]["kind"] == "monitor"]
        self.assertGreater(len(mon), 0)
        for a in mon:
            cs = a["payload"]["cloud_score"]
            self.assertIsNotNone(cs)
            self.assertLess(cs, 0.0)
            self.assertAlmostEqual(cs, math.log(a["payload"]["p_yes"]))

    def test_every_recall_answer_carries_a_letter(self):
        with tempfile.TemporaryDirectory() as d:
            co, _res = _run_scored(Path(d))
        rec = [a for a in co.cloud_answers if a["payload"]["kind"] == "recall"]
        for a in rec:
            self.assertIn(a["payload"]["cloud_letter"], tuple("ABCDEX"))
            self.assertIsNone(a["payload"]["cloud_score"])

    def test_a_dry_run_records_no_score_rather_than_a_fabricated_one(self):
        from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK, _arm
        tr = T.synthetic(n_dashcam=1, n_robot=1, duration_s=12.0, seed=1, upload_mode="A")
        co = Live2Coordinator(_arm("always-cloud-fcfs"), None, tr["events"],
                              gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                              host_tier_tokens=HOST_TOK, upload_mode="A", window_s=12.0,
                              drain_s=5.0, seed=1, dry_run=True,
                              run_tag=CK.run_tag(1, "fix2dry"))
        co.run()
        self.assertGreater(len(co.cloud_answers), 0)
        for a in co.cloud_answers:
            self.assertIsNone(a["payload"]["cloud_score"])


class TestTheScorerComputesApFromCoordinatorScores(unittest.TestCase):
    """END TO END: a real-pool trace, the real coordinator, the committed extractor, the scorer.

    Every `cloud_score` the scorer reads here was produced by `Live2Coordinator._score_of` out of
    the logprobs the fixture server returned. Nothing in this test writes a score.
    """

    def test_ap_is_computed_and_no_instant_is_missing_a_score(self):
        import data_sources as DS
        import emulator as EM
        import score as SCORE
        import trace as TR
        from bridge import EmulatorBridge
        from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK, _arm
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            tdir, rdir = d / "trace", d / "run"
            TR.write_trace(tdir, TR.generate_trace(11, 8, "25:75", 600.0, "A"))
            rdir.mkdir(parents=True, exist_ok=True)
            logs = Logs(rdir).open()
            with _Serve() as url:
                be = Live2Backend(url, workers=8)
                co = Live2Coordinator(_arm("always-cloud-fcfs"), be, [], gpu_kv_tokens=GPU_KV,
                                      host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                                      upload_mode="A", window_s=600.0, drain_s=5.0, seed=11,
                                      logs=logs, run_tag=CK.run_tag(11, "fix2e2e"))
                em = EM.FleetEmulator(tdir, EmulatorBridge(co), "A", realtime=False)
                em.run(rdir)
            logs.close()
            scored = [o for o in em.outcomes.values()
                      if o.kind == "monitor" and (o.cloud_payload or {}).get("cloud_score")
                      is not None]
            self.assertGreater(len(scored), 0, "the run served no scored SH instant")
            lo = SCORE.load(tdir, rdir)
            dv = SCORE.dashcam_value(lo, DS.calibration())
        self.assertEqual(dv["n_missing_cloud_score"], 0, dv.get("refused"))
        self.assertIsNotNone(dv["ap"], dv.get("refused"))
        for v in dv["ap"].values():
            self.assertTrue(0.0 <= v <= 1.0, dv["ap"])


class TestTheStubPassesAScoreThrough(unittest.TestCase):
    def test_the_stub_coordinator_no_longer_hands_the_scorer_a_none(self):
        import emulator as EM
        stub = EM.StubCoordinator()
        ev = dict(kind="monitor_frame", device_id="dash000", opportunity_id="dash000|t0001.00",
                  instant_id="dash000|t0001.00", t_capture=1.0, deadline_s=0.5)
        (out,) = stub.on_event(ev, 1.0)
        self.assertTrue(out["payload"]["stub"])
        self.assertIsNotNone(out["payload"]["cloud_score"])
        self.assertTrue(-14.0 <= out["payload"]["cloud_score"] < 0.0)
        stub2 = EM.StubCoordinator()
        (out2,) = stub2.on_event(ev, 1.0)
        self.assertEqual(out["payload"]["cloud_score"], out2["payload"]["cloud_score"])

    def test_the_stub_score_can_be_switched_off(self):
        import emulator as EM
        stub = EM.StubCoordinator(stub_scores=False)
        ev = dict(kind="monitor_frame", device_id="dash000", opportunity_id="o1",
                  instant_id="o1", t_capture=1.0, deadline_s=0.5)
        (out,) = stub.on_event(ev, 1.0)
        self.assertIsNone(out["payload"]["cloud_score"])


class TestTheEncodeParsers(unittest.TestCase):
    def _png(self, size=(768, 432)):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, (90, 120, 150)).save(buf, format="PNG")
        return buf.getvalue()

    def test_the_nexar_parser_reads_the_clip_pts_layout_and_checks_the_sha(self):
        import encode_jpeg as E
        png = self._png()
        sha = hashlib.sha256(png).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "store" / "01040").mkdir(parents=True)
            (d / "store" / "01040" / "0003000.png").write_bytes(png)
            man = d / "man.jsonl.gz"
            with gzip.open(man, "wt") as fh:
                for t in (3.0, 3.25):
                    fh.write(json.dumps(dict(n=1, file_name="01040.mp4", t=t,
                                             frame_keys=["0003000"],
                                             small_sha256=[sha])) + "\n")
                fh.write(json.dumps(dict(n=3, file_name="01040.mp4", t=3.0,
                                         frame_keys=["0003000"],
                                         small_sha256=[sha])) + "\n")
            old = E.D14B_MANIFEST
            try:
                E.D14B_MANIFEST = man
                got = list(E.iter_nexar(d / "store"))
                # the N = 3 row is not a round-1 instant and must not be stored
                self.assertEqual([r for r, _ in got],
                                 ["01040.mp4|t0003.00", "01040.mp4|t0003.25"])
                self.assertTrue(all(b == png for _, b in got))
                bad = d / "man_bad.jsonl.gz"
                with gzip.open(bad, "wt") as fh:
                    fh.write(json.dumps(dict(n=1, file_name="01040.mp4", t=3.0,
                                             frame_keys=["0003000"],
                                             small_sha256=["0" * 64])) + "\n")
                E.D14B_MANIFEST = bad
                with self.assertRaises(SystemExit):
                    list(E.iter_nexar(d / "store"))
            finally:
                E.D14B_MANIFEST = old

    def test_the_nexar_frame_ref_is_the_one_the_trace_puts_on_the_wire(self):
        import encode_jpeg as E
        self.assertEqual(f"{'01040.mp4'}|t{3.0:07.2f}", "01040.mp4|t0003.00")
        src = (ROOT / "experiments/orchestration/live2/fleet/trace.py").read_text()
        self.assertIn('f"{clip}|t{t_local:07.2f}"', src)
        self.assertIn('f"{sid}|f{x:08.2f}"', src)
        self.assertEqual(E.D2_STRIDE_S, 2.0)
        self.assertEqual(E.D2_SIZE_HW, (352, 256))

    def test_the_sember_d2_parser_uses_the_committed_loader_and_stride(self):
        import data_sources as DS
        import encode_jpeg as E
        import study_rh3_inputs as B3
        sid = sorted(DS.eval_sessions())[0]
        last_q = max(q.t_ask for q in DS.eval_sessions()[sid].questions)
        png = self._png((640, 480))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / sid
            root.mkdir(parents=True)
            frames = []
            for t in (0.0, 1.0, 2.0, 4.0, last_q + 100.0):
                name = f"{t:.2f}.png"
                (root / name).write_bytes(png)
                frames.append([t, name])
            (root / "index.json").write_text(json.dumps(dict(frames=frames)))
            old_frames, old_sessions = B3.FRAMES, DS.eval_sessions
            try:
                one = {sid: DS.eval_sessions()[sid]}
                DS.eval_sessions = lambda: one
                got = list(E.iter_sember_d2(Path(d)))
            finally:
                B3.FRAMES, DS.eval_sessions = old_frames, old_sessions
        refs = [r for r, _ in got]
        # the 2-s stride only, nothing past the last question, and the committed ref format
        self.assertEqual(refs, [f"{sid}|f{0.0:08.2f}", f"{sid}|f{2.0:08.2f}",
                                f"{sid}|f{4.0:08.2f}"])
        # the committed loader's own orientation rule decides the size, not this test
        h, w = B3.orient(E.D2_SIZE_HW, 640, 480)
        self.assertEqual({im.size for _, im in got}, {(w, h)})
        jb = E.jpeg_bytes_from_image(got[0][1], E.SEMBER_QUALITY)
        self.assertEqual(jb[:2], b"\xff\xd8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
