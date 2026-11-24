"""User ruling 2026-11-24, writer fix proof: ONE split-mode cell on the fake streaming server, CPU only.

Asserts (the ruling's two conditions, plus the guard records):
  A. request.jsonl rows == submitted requests (n_requests from the child's own result);
  B. every DELIVERED outcome (t_delivered set) resolves to a NON-abandoned row;
and reports the row_source tally, so the end cases are shown to have OCCURRED (not just passed):
  - "abandoned": in flight at finish with no delivered answer (forced by concurrency 2);
  - "first_token_forwarded_stream_unfinished": delivered at first token, stream still open at
    finish (forced by fakestream tail_s, the r10175 case).
Usage: split_proof.py <tree root> <out json>
"""
import json
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
L2 = root / "experiments/orchestration/live2"
for p in (L2, L2 / "fleet", L2 / "tests", L2 / "scorer", root / "experiments/orchestration/live",
          root / "experiments/orchestration/baselines", root / "experiments/orchestration/sim",
          root / "experiments/lib"):
    sys.path.insert(0, str(p))

import emulator as EM            # noqa: E402
import fakestream as FS          # noqa: E402
import procsplit as PS           # noqa: E402
import run_live2_real as RR      # noqa: E402
import source_agreement as SA    # noqa: E402
import trace as TR               # noqa: E402
from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK  # noqa: E402

def main() -> None:
    out = {}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        tdir, rdir = d / "trace", d / "run"
        TR.write_trace(tdir, TR.generate_trace(5, 4, "50:50", 30.0, "A"))
        with FS.serve(0, concurrency=2, tail_s=8.0) as url:
            cfg = dict(run_dir=str(rdir), arm="edf", arm_kwargs={}, mode="A", run_s=30.0,
                       drain_s=2.0, decision_period_s=0.1, gpu_kv_tokens=GPU_KV,
                       host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK, seed=5, run_tag="wp",
                       frames_root=None, server_url=url, strip_hints=False, defer_images=True,
                       self_tick_s=0.005, scheduling_policy=None,
                       context_limit_tokens=32768, context_limit_source="split_proof (fake server)")
            cfg["source_runner"] = SA.loaded_repo_files()
            err = None
            try:
                with PS.SplitRun(cfg, kind="fake") as remote:
                    EM.FleetEmulator(tdir, remote, "A", realtime=True, drain_s=2.0).run(rdir)
            except Exception as e:                                        # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
        res = json.loads((rdir / "coordinator_result.json").read_text())
        rec = RR._reconcile_delivered(rdir)
        rl = RR._request_log_check(rdir, res.get("n_requests"))
        sa = res.get("source_agreement") or {}
        out = dict(err=err, n_requests=res.get("n_requests"),
                   counts={k: v for k, v in (res.get("counts") or {}).items()
                           if k.startswith(("request", "requests_"))},
                   reconciled=rec, request_log=rl,
                   source_agreement={k: sa.get(k) for k in (
                       "verdict", "overlap_n", "runner_only_n", "child_only_at_start_n",
                       "child_only_late_n", "start_files_n", "start_hash_wall_s",
                       "end_hash_wall_s", "torn_lazy_import", "moved_after_import")})
        src = rl.get("row_sources") or {}
        out["A_rows_equal_submitted"] = bool(rl.get("rows_match_submitted"))
        out["B_no_delivered_on_abandoned"] = (rl.get("delivered_resolving_to_abandoned") == 0
                                              and rl.get("outcome_request_ids_unresolved") == 0)
        out["end_cases_occurred"] = dict(abandoned=src.get("abandoned", 0),
                                         first_token_unfinished=src.get(
                                             "first_token_forwarded_stream_unfinished", 0))
        out["verdict"] = ("PASS" if out["A_rows_equal_submitted"] and out["B_no_delivered_on_abandoned"]
                          and err is None and sa.get("verdict") == "OK" else "FAIL")
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(dict(verdict=out["verdict"], A=out["A_rows_equal_submitted"],
                          B=out["B_no_delivered_on_abandoned"], cases=out["end_cases_occurred"],
                          n_requests=out["n_requests"], err=err)))


if __name__ == "__main__":
    main()
