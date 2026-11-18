#!/usr/bin/env python3
"""Run ONE live round-1 cell: one arm, one trace, one server. CPU only in this file.

StudyLIVE2-coord. Every run writes a HEADER carrying the git commit, the arm and its version,
every flag value, the capacities, the cost-model id and hash, the calibration file and its
label, the trace digest and label, the seed and the targets (reproducibility rule), plus the
three JSONL log streams and the predicted-versus-actual join (D63).

REFUSALS, before anything is submitted:
  * a calibration map labelled INTERIM against a non-stub server (D86);
  * a SYNTHETIC trace against a non-stub server;
  * an arm declaring `reads_future` (fairness rule 5).

NOTHING FROM A FAKE-SERVER RUN IS A MEASUREMENT: `is_measurement` is false in the header and in
the result.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/orchestration/live"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms as A                                                      # noqa: E402
import cachekeys as CK                                                # noqa: E402
import calib as CALIB                                                 # noqa: E402
import cstate as CS                                                   # noqa: E402
import joiner as J                                                    # noqa: E402
import schema as SC                                                   # noqa: E402
import traces as T                                                    # noqa: E402
from backend import Live2Backend                                      # noqa: E402
from coordinator import DEFAULT_TICK_S, Live2Coordinator, Logs        # noqa: E402

DEFAULT_OUT = ROOT / "results/orchestration/live2/coord"
# D76: the values round 1 runs at, named so a reproduction can pass them explicitly. They are
# INPUTS (D56), never defaults: the CLI requires both.
H100NVL_KV_POOL_TOKENS = 62_944
HOST_TIGHT_GIB = 27.0
HOST_ROOMY_GIB = 256.0
# StudyENG1b: 256 GiB of host offload held about 986k tokens beyond the GPU pool, and 27 GiB
# about 48k (D76). The bytes-per-token that implies is carried explicitly so the conversion is
# visible rather than hidden in a constant.
HOST_BYTES_PER_TOKEN = 256 * 1024 ** 3 / (986_000 + H100NVL_KV_POOL_TOKENS)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:                                                 # noqa: BLE001
        return "unknown"


def cost_model_hash(engine_model: str) -> str:
    """The md5 of every file whose exact bytes decide a prediction, as StudyPOL4 froze them."""
    try:
        from policy.freeze_t0b import FROZEN_FILES
    except Exception:                                                 # noqa: BLE001
        FROZEN_FILES = ["experiments/orchestration/policy/eng1_engine.py"]
    h = hashlib.md5()
    h.update(engine_model.encode())
    for rel in FROZEN_FILES:
        p = ROOT / rel
        if p.exists():
            h.update(hashlib.md5(p.read_bytes()).hexdigest().encode())
    return h.hexdigest()


def host_tokens(host_tier_gib: float) -> int:
    return int(host_tier_gib * 1024 ** 3 / HOST_BYTES_PER_TOKEN)


def build(args) -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if args.arm == "policy-core":
        kw = dict(cost_model=args.cost_model, h_s=args.h, mu_mode=args.mu_mode,
                  mu_fixed=args.mu_fixed)
    arm = A.make_arm(args.arm, **kw)
    cal = CALIB.load_map(args.calibration)
    CALIB.require_runnable(cal, args.server_kind)
    out = Path(args.out) / f"{args.arm}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    knots = CALIB.write_knots(cal, out / "calibration_knots.json")
    htok = args.host_tier_tokens or host_tokens(args.host_tier_gib)
    cfg = dict(gpu_kv_tokens=args.gpu_kv_tokens, host_tier_gib=args.host_tier_gib,
               host_tier_tokens=htok, targets=CS.TARGETS)
    if args.arm == "policy-core":
        cfg["calibration_knots_path"] = knots
    arm.live2_configure(**cfg)
    if args.trace:
        tr = T.load(args.trace)
    else:
        tr = T.synthetic(n_dashcam=args.n_dashcam, n_robot=args.n_robot,
                         duration_s=args.window_s, seed=args.seed,
                         upload_mode=args.upload_mode,
                         frames_dir=(Path(args.frames_dir) if args.frames_dir else None))
    T.require_fake_server(tr, args.server_kind)
    return dict(arm=arm, trace=tr, out=out, cal=cal, knots=knots, host_tier_tokens=htok)


def run(args) -> Dict[str, Any]:
    b = build(args)
    arm, tr, out = b["arm"], b["trace"], b["out"]
    run_tag = CK.run_tag(args.seed, args.arm)
    logs = Logs(out).open()
    backend = None
    if not args.dry_run and getattr(arm, "sends_requests", True):
        backend = Live2Backend(args.server, workers=args.workers, model=args.model,
                               strip_hints=(args.server_kind != "fake"))
    responder = (T.pull_responder(tr.get("frames_by_instant") or {})
                 if args.upload_mode == "B" else None)
    co = Live2Coordinator(
        arm, backend, tr["events"], gpu_kv_tokens=args.gpu_kv_tokens,
        host_tier_gib=args.host_tier_gib, host_tier_tokens=b["host_tier_tokens"],
        upload_mode=args.upload_mode, window_s=args.window_s, drain_s=args.drain_s,
        tick_s=args.tick_s, seed=args.seed, speed=args.speed, logs=logs, run_tag=run_tag,
        frames_root=(Path(args.frames_dir) if args.frames_dir else None),
        dry_run=args.dry_run, targets=CS.TARGETS, on_pull=responder)
    header = SC.RunHeader(
        git_commit=git_commit(), arm=arm.name,
        arm_version=getattr(arm, "arm_version", "unversioned"),
        flags=(arm.flags.as_dict() if hasattr(arm, "flags") else {}),
        gpu_kv_tokens=args.gpu_kv_tokens, host_tier_gib=args.host_tier_gib,
        host_tier_tokens=b["host_tier_tokens"],
        cost_model_id=(arm.engine.model_name() if hasattr(arm, "engine") else "none"),
        cost_model_hash=(cost_model_hash(args.cost_model) if hasattr(arm, "engine") else "none"),
        calibration_file=str(b["cal"]["path"]), calibration_label=str(b["cal"]["label"]),
        fairness_digest=tr["fairness_digest"],
        live1_trace_digest=tr.get("live1_trace_digest"),
        trace_label=tr["label"], seed=args.seed,
        targets=CS.TARGETS, upload_mode=args.upload_mode, mu_mode=args.mu_mode,
        mu_value=(float(arm.params.mu) if hasattr(arm, "params") else None),
        H=(float(arm.params.H) if hasattr(arm, "params") else None),
        tick_s=co.tick_s, server_url=(args.server if backend is not None else "none"),
        model=args.model,
        server_kind=args.server_kind, is_measurement=False,
        placeholders=(arm.placeholder_table() if hasattr(arm, "placeholder_table") else []),
        note=("NOT A MEASUREMENT: %s server, trace label %s. Arms without a planning horizon "
              "tick at %.3f s." % (args.server_kind, tr["label"], DEFAULT_TICK_S)))
    SC.write_header(out / "header.json", header)
    try:
        res = co.run()
    finally:
        logs.close()
        if backend is not None:
            backend.close()
    res["fairness_digest"] = tr["fairness_digest"]
    res["live1_trace_digest"] = tr.get("live1_trace_digest")
    res["trace_label"] = tr["label"]
    res["calibration_label"] = b["cal"]["label"]
    if hasattr(arm, "placeholder_table"):
        res["placeholders"] = arm.placeholder_table()
    if backend is not None:
        res["sent_bodies"] = len(backend.sent)
        (out / "sent_bodies.json").write_text(json.dumps(backend.sent, indent=1) + "\n")
    SC.write_jsonl(out / "cloud_answer.jsonl", co.cloud_answers)
    if co.pulls:
        SC.write_jsonl(out / "pull_request.jsonl", co.pulls)
    joined = J.join(out)
    J.write(out, joined)
    res["predicted_vs_actual"] = dict(n_rows=len(joined["rows"]), by_mix=joined["by_mix"])
    from _provenance import stamp
    res["_provenance"] = stamp(script="run_live2_cell.py", model="none",
                               device="flash_cpu", n=res["n_requests"], seed=args.seed,
                               args=args)
    (out / "result.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str)
                                     + "\n")
    return res


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=list(A.ARM_NAMES))
    ap.add_argument("--label", default="flash")
    ap.add_argument("--server", default="http://127.0.0.1:8077")
    ap.add_argument("--server-kind", default="fake", choices=("fake", "vllm"))
    ap.add_argument("--gpu-kv-tokens", type=int, required=True,
                    help="D56: an INPUT. Round 1 runs at %d on the H100."
                         % H100NVL_KV_POOL_TOKENS)
    ap.add_argument("--host-tier-gib", type=float, required=True,
                    help="D56, D76: an INPUT. Round 1 runs TIGHT %.0f and ROOMY %.0f."
                         % (HOST_TIGHT_GIB, HOST_ROOMY_GIB))
    ap.add_argument("--host-tier-tokens", type=int, default=0,
                    help="override the GiB to token conversion")
    ap.add_argument("--cost-model", default="pol4",
                    help="D74: pol4 is frozen and the default; pluggable")
    ap.add_argument("--calibration", default=None,
                    help="D86: the map file path is an INPUT")
    ap.add_argument("--mu-mode", default="none", choices=("none", "ewma", "fixed"))
    ap.add_argument("--mu-fixed", type=float, default=None)
    ap.add_argument("--h", type=float, default=1.0, help="planning horizon, swept at 0.5 and 1.0")
    ap.add_argument("--upload-mode", default="A", choices=("A", "B"))
    ap.add_argument("--window-s", type=float, default=180.0)
    ap.add_argument("--drain-s", type=float, default=20.0)
    ap.add_argument("--tick-s", type=float, default=None)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--model", default="fake-32BI",
                    help="the served model id; a real run passes the vLLM model name")
    ap.add_argument("--n-dashcam", type=int, default=2)
    ap.add_argument("--n-robot", type=int, default=2)
    ap.add_argument("--trace", default=None, help="a fleet trace JSONL; omit for SYNTHETIC")
    ap.add_argument("--frames-dir", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="no HTTP at all: the loop runs on a virtual clock with the committed "
                         "cost curve as the service time. A legality and determinism test, "
                         "never a measurement.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    return ap


def main(argv: Optional[list] = None) -> int:
    args = parser().parse_args(argv)
    res = run(args)
    print(json.dumps({k: v for k, v in res.items() if k != "placeholders"}, indent=1,
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
