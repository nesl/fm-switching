#!/usr/bin/env python3
"""StudyLIVE2-coord, Part 4: the tests that need a server. CPU only, the EXISTING CPU stub.

The server is `experiments/orchestration/live/fake_server.py`, unchanged. It is a test fixture:
it checks that an arm's actions are legal, that the loop enacts them and that a request reaches
an OpenAI-compatible endpoint and comes back. NOTHING IT PRODUCES IS A MEASUREMENT, and in
particular it reports no `prompt_tokens_details.cached_tokens`, so D81's WARM / COLD tag is
`None` on a stub run by construction rather than being guessed (see `backend.cached_tokens_of`).
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
ROOT = LIVE2.parents[2]
for _p in (str(LIVE2), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cachekeys as CK                                                # noqa: E402
import schema as SC                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from backend import Live2Backend                                      # noqa: E402
from coordinator import Live2Coordinator, Logs                        # noqa: E402
import fake_server as FS                                              # noqa: E402

from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK, _arm         # noqa: E402

WINDOW = 12.0


def _live(name, out, *, mode="A", window=WINDOW, speed=1.0, trace=None, frames=None):
    tr = trace or T.synthetic(n_dashcam=1, n_robot=1, duration_s=window, seed=1,
                              upload_mode=mode, frames_dir=frames)
    T.require_fake_server(tr, "fake")
    a = _arm(name)
    logs = Logs(Path(out)).open()
    with FS.serve(0) as url:
        be = Live2Backend(url, workers=16)
        resp = T.pull_responder(tr.get("frames_by_instant") or {}) if mode == "B" else None
        co = Live2Coordinator(a, be, tr["events"], gpu_kv_tokens=GPU_KV,
                              host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                              upload_mode=mode, window_s=window, drain_s=5.0, seed=1,
                              logs=logs, run_tag=CK.run_tag(1, name), speed=speed,
                              frames_root=(Path(frames) if frames else None), on_pull=resp)
        res = co.run()
        sent = list(be.sent)
        be.close()
    logs.close()
    return a, co, res, sent


class TestFakeServer(unittest.TestCase):
    def test_requests_reach_the_stub_and_come_back(self):
        with tempfile.TemporaryDirectory() as d:
            _a, _co, res, sent = _live("always-cloud-fcfs", Path(d))
            reqs = SC.read_jsonl(Path(d) / "request.jsonl")
        self.assertEqual(res["n_errors"], 0, res["first_errors"])
        self.assertGreater(len(reqs), 0)
        self.assertEqual(len(sent), res["n_requests"])
        for r in reqs:
            self.assertEqual(r["http_status"], 200)
            self.assertIsNotNone(r["t_first_token"])
            # the stub reports no cached_tokens, so the cache path is UNKNOWN, not COLD
            self.assertIsNone(r["cache_path"])

    def test_the_cache_isolation_fields_are_sent(self):
        """D84: the test is on the BODIES that went out, not on the coordinator's intent."""
        with tempfile.TemporaryDirectory() as d:
            _a, _co, _res, sent = _live("always-cloud-fcfs", Path(d))
        self.assertGreater(len(sent), 0)
        salts, uuids = {}, {}
        for s in sent:
            self.assertTrue(s["cache_salt"])
            self.assertTrue(s["mm_uuids"])
            salts.setdefault(s["device_id"], set()).add(s["cache_salt"])
            for u in s["mm_uuids"]:
                uuids.setdefault((s["device_id"], u.rsplit("|", 1)[-1]), set()).add(u)
        CK.check_isolation(salts, uuids)

    def test_mode_b_pulls_before_the_frame_exists(self):
        with tempfile.TemporaryDirectory() as d:
            _a, co, res, _sent = _live("always-cloud-fcfs", Path(d), mode="B")
        self.assertGreater(res["n_pulls"], 0)
        self.assertGreater(res["n_requests"], 0)
        for p in co.pulls:
            self.assertEqual(p["kind"], "pull_request")

    def test_the_policy_core_runs_live(self):
        with tempfile.TemporaryDirectory() as d:
            _a, _co, res, _sent = _live("policy-core", Path(d))
            decs = SC.read_jsonl(Path(d) / "decision.jsonl")
        self.assertEqual(res["n_errors"], 0, res["first_errors"])
        self.assertEqual(res["h_s"], 1.0)
        for x in decs:
            self.assertEqual(x["cost_model_id"], "pol4")
            self.assertEqual(x["H"], 1.0)
            self.assertEqual(x["mu"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
