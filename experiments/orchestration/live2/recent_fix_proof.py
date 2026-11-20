#!/usr/bin/env python3
"""Proof for the RECENT-send fix (user ruling 2026-11-20), one DRY cell: an arm choosing RECENT sends exactly the RECENT
window it is charged for. Run with no server up.

Cell: hybrid-F-lhreq, three-type 40:40:20, LH-REQ robots, SS2 pool, 16 devices, seed 0, 1200 s, enforcement on (the cell
with the most RECENT releases). For every recall submission the request log gives the image uuids actually attached to
the body (one per frame), the tokens charged (est_tokens), and the decision gives the representation. Pass iff:
  RECENT: frames sent == k = ceil(session frames x charged tokens / history tokens), at least 1, and charged <= 467;
  D2 (or none): frames sent == every frame of the session (byte-identical behaviour to before the fix).
Writes results/orchestration/live2/frozen_test/recent_fix_proof.json.
"""
import json
import math
import sys
import tempfile
from pathlib import Path

L = Path(__file__).resolve().parent
R = L.parents[2]
for p in (L, L / "fleet", L / "tests", R / "experiments/orchestration/baselines", R / "experiments/orchestration/sim",
          R / "experiments/lib"):
    sys.path.insert(0, str(p))
import arms as A, cachekeys as CK, cstate as CS, emulator as EM, trace as TR, hybrid  # noqa: E401,F401
from bridge import EmulatorBridge
from coordinator import Live2Coordinator, Logs
from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK


def main(arm="hybrid-F-lhreq", seed=0, n=16, run_s=1200.0):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        TR.write_trace(d / "t", TR.generate_trace(seed, n, "40:40:20", run_s, "A", robot_question_set="lh_req",
                                                  ss_question_set="ss2"))
        a = A.make_arm(arm)
        a.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        logs = Logs(d / "r").open()
        co = Live2Coordinator(a, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                              upload_mode="A", window_s=run_s, drain_s=5.0, seed=seed, logs=logs,
                              run_tag=CK.run_tag(seed, "x"), dry_run=True)
        co.st.kv_capacity_enforced = True
        sizes = {}                                        # (session_id) -> (frames, est_tokens) at each recall submit
        orig = co._submit_recall

        def spy(o, s, t, dt_ms, preds, mix, whole):
            rq = getattr(o, "requested_representation", None)
            sizes[o.opp_id] = (len(s.frames), int(s.est_tokens), str(rq or "D2").upper(),
                               int(s.tokens_for_representation(rq)))
            return orig(o, s, t, dt_ms, preds, mix, whole)
        co._submit_recall = spy
        br = EmulatorBridge(co)
        br.kind = "stub"
        EM.FleetEmulator(d / "t", br, "A", realtime=False, drain_s=5.0).run(d / "r")
        logs.close()
        reqs = [json.loads(x) for x in open(d / "r" / "request.jsonl")]
    rows, bad = [], []
    for r in reqs:
        op = r.get("opportunity_id")
        if op not in sizes:
            continue
        frames_all, hist, rep, charged = sizes[op]
        sent = len(r.get("mm_uuids") or [])
        if rep == "RECENT":
            want = max(1, min(frames_all, math.ceil(frames_all * charged / max(hist, 1)))) if charged else None
            ok = (want is not None and sent == want and charged <= CS.RECENT_WINDOW_TOKENS)
        else:
            want = frames_all
            ok = (sent == want)
        rows.append(dict(opportunity_id=op, representation=rep, session_frames=frames_all, history_tokens=hist,
                         tokens_charged=charged, frames_sent=sent, frames_expected=want, ok=ok))
        if not ok:
            bad.append(rows[-1])
    rec = [x for x in rows if x["representation"] == "RECENT"]
    res = dict(cell=f"{arm} n{n} s{seed} {int(run_s)} s three-type lh_req ss2 dry", recalls=len(rows),
               recent_releases=len(rec), recent_examples=rec[:5], failures=bad[:10], n_failures=len(bad),
               passed=(len(bad) == 0 and len(rec) > 0))
    out = R / "results/orchestration/live2/frozen_test/recent_fix_proof.json"
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("cell", "recalls", "recent_releases", "n_failures", "passed")}))
    for x in rec[:5]:
        print(x)


if __name__ == "__main__":
    main()
