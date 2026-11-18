#!/usr/bin/env python3
"""StudyLIVE2-pilot (round 1, block 0): runner glue around flash's UNCHANGED live2 code. PILOT, NOT A ROUND-1 RESULT.

Per run: restart the round-1 server (the LIVE2-pre Part 2 command: ENG1c KV-HOST flags with host 27 GiB, or 256 GiB for
the roomy check; ENG1 stat-logger plugin as there), generate the fleet trace (fleet/trace.py, seed 0, 50 : 50, mode A,
per-frame bytes from the Part-1 manifests), build the arm and the live2 coordinator exactly as run_live2_cell.py does
(FINAL calibration, cost model pol4, mu EWMA, H = 0.5 s, decision period 100 ms, GPU budget default, targets D71 / D82),
drive it from the real-time fleet emulator through bridge.EmulatorBridge (as live2/tests/test_live2_fix2.py's end-to-end
test wires it), stop the server, then score with scorer/score.py.

Adapters (implementation only, recorded in the report): (1) `frames_root` is a directory of symlinks named by frame_ref
(the coordinator resolves frames_root / frame_ref) pointing at the Part-1 stored JPEGs; (2) the bridge instance carries
kind = "vllm" so the emulator's run_meta records a real server, and run_meta is annotated with the header's memory
setting after the run, so the scorer reads the run as what it is; (3) device-only sends no request and is run without a
server.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
L2 = HERE / "live2"
for p in (L2, L2 / "fleet", L2 / "scorer", HERE / "live", HERE / "baselines", REPO / "experiments/lib", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

OUT = REPO / "results/orchestration/live2/pilot"
WORK = Path.home() / "data/live2/pilot"
STORE = Path.home() / "data/live2/jpeg"
FRAMES = Path.home() / "data/live2/frames_by_ref"
MANIFEST = STORE / "combined_manifest.jsonl"
CAL = REPO / "results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json"
GPU_KV, HOST_TIGHT, HOST_ROOMY = 62944, 27.0, 256.0
SEED, RATIO, MODE = 0, "50:50", "A"
LABEL = "PILOT, NOT A ROUND-1 RESULT"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "pilot.log", "a") as f:
        f.write(line + "\n")


def prep():
    """Symlinks named by frame_ref and one plain manifest for the trace generator (read-only on the stores)."""
    FRAMES.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(MANIFEST, "w") as man:
        for name in ("nexar_q90", "sember_d2_q88"):
            for ln in open(STORE / name / "manifest.jsonl"):
                r = json.loads(ln)
                man.write(json.dumps(dict(frame_ref=r["frame_ref"], bytes=r["bytes"], sha256=r["sha256"])) + "\n")
                link = FRAMES / r["frame_ref"]
                if not link.exists():
                    os.symlink(r["path"], link)
                n += 1
    log(f"prep: {n} frame symlinks under {FRAMES}; manifest {MANIFEST}")


def start_server(host_gib):
    sys.path.insert(0, str(REPO / "experiments/cost"))
    import study_live2_pre as LP
    import study_eng1_steptime as M
    X, E, F = M.X, M.E, M.F
    X.META_PATH = OUT / "pilot_servers_meta.json"
    X.CURRENT = REPO / "logs/live2_pilot_current.json"
    M.G.X.META_PATH = X.META_PATH
    E.MON = OUT / "pilot_monitor.jsonl"
    snap = E.snapshot("pre_start")
    if snap["ours_outside_job"] or snap["foreign_on_gpu"]:
        raise SystemExit(f"GPU 2 not exclusive: {snap['foreign_on_gpu']} {snap['ours_outside_job']}: STOP")
    F.require_idle()
    ref = next(x["flags"] for x in json.loads(LP.ENG1C_META.read_text())["servers"] if x["label"] == "DE_c38")
    flags = M.E.COMMON + ["--kv-offloading-backend", "native", "--kv-offloading-size", f"{host_gib:g}"] + \
        M.D.LOGFLAGS + ["--enable-logging-iteration-details"]
    diff = [(a, b) for a, b in zip(ref, flags) if a != b]
    if diff != [("38", f"{host_gib:g}")] or len(ref) != len(flags):
        raise SystemExit(f"flag diff vs DE_c38 {diff}: STOP")
    os.environ["PYTHONPATH"] = str(M.PLUGIN_DIR)
    os.environ["ENG1_STATLOG_PATH"] = str(WORK / f"statlog_{int(time.time())}.jsonl")
    t0 = time.time()
    srv = X.Server("32BI", flags)
    info = srv.start()
    os.environ.pop("PYTHONPATH", None)
    if info.get("kv_cache_tokens") != GPU_KV:
        srv.stop()
        raise SystemExit(f"GPU pool {info.get('kv_cache_tokens')}: STOP")
    return srv, dict(command=info.get("server_cmd"), flag_diff=diff, restart_started=t0, up_at=time.time(),
                     startup_s=info.get("startup_s"), log=str(srv.logpath), host_gib=host_gib), M


def run_cell(arm_name, n_dev, run_s, host_gib=HOST_TIGHT, tag="", drain_s=20.0):
    import arms as A
    import cachekeys as CK
    import calib as CALIB
    import cstate as CS
    import schema as SC
    import trace as TR
    import emulator as EM
    import run_live2_cell as RC
    from backend import Live2Backend
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    label = f"{arm_name}_n{n_dev}_{'roomy' if host_gib == HOST_ROOMY else 'tight'}{tag}"
    tdir, rdir = WORK / "traces" / f"n{n_dev}_{int(run_s)}s", OUT / "runs" / label
    if not (tdir / "trace.jsonl").exists():
        TR.write_trace(tdir, TR.generate_trace(SEED, n_dev, RATIO, run_s, MODE, frame_manifest=MANIFEST))
    rdir.mkdir(parents=True, exist_ok=True)
    sends = arm_name != "device-only"
    srv, sinfo, M = (start_server(host_gib) if sends else (None, None, None))
    kw = {}
    if arm_name == "policy-core":
        kw = dict(cost_model="pol4", h_s=0.5, mu_mode="ewma", mu_fixed=None, impl="fast", cap_k=None)
    arm = A.make_arm(arm_name, **kw)
    cal = CALIB.load_map(CAL)
    CALIB.require_runnable(cal, "vllm")
    knots = CALIB.write_knots(cal, rdir / "calibration_knots.json")
    htok = RC.host_tokens(host_gib)
    cfg = dict(gpu_kv_tokens=GPU_KV, host_tier_gib=host_gib, host_tier_tokens=htok, targets=CS.TARGETS)
    if arm_name == "policy-core":
        cfg["calibration_knots_path"] = knots
    arm.live2_configure(**cfg)
    logs = Logs(rdir).open()
    be = Live2Backend("http://127.0.0.1:8031", workers=64, model="32BI", strip_hints=True) if sends else None
    co = Live2Coordinator(arm, be, [], gpu_kv_tokens=GPU_KV, host_tier_gib=host_gib, host_tier_tokens=htok,
                          upload_mode=MODE, window_s=run_s, drain_s=drain_s, decision_period_s=0.1,
                          gpu_budget_s=None, seed=SEED, logs=logs, run_tag=CK.run_tag(SEED, arm_name),
                          frames_root=FRAMES, dry_run=not sends, targets=CS.TARGETS)
    br = EmulatorBridge(co)
    br.kind = "vllm" if sends else "device-only-no-server"
    tr = json.loads((tdir / "trace_meta.json").read_text())
    header = dict(label=LABEL, git_commit=RC.git_commit(), arm=arm.name, arm_version=getattr(arm, "arm_version", None),
                  flags=(arm.flags.as_dict() if hasattr(arm, "flags") else {}), gpu_kv_tokens=GPU_KV,
                  host_tier_gib=host_gib, host_tier_tokens=htok, cost_model="pol4" if arm_name == "policy-core" else None,
                  calibration_file=str(CAL), calibration_label=cal["label"], fairness_digest=tr.get(f"fairness_digest_{MODE}"),
                  seed=SEED, targets=CS.TARGETS, upload_mode=MODE, mu_mode="ewma" if arm_name == "policy-core" else None,
                  H=0.5 if arm_name == "policy-core" else None, decision_period_s=0.1, ratio=RATIO, n_devices=n_dev,
                  run_s=run_s, memory_setting=RC.memory_setting(host_gib), server=sinfo, is_measurement=False)
    (rdir / "header.json").write_text(json.dumps(header, indent=1, default=str) + "\n")
    cpu0 = time.process_time()
    t0 = time.time()
    em = EM.FleetEmulator(tdir, br, MODE, realtime=True)
    err = None
    try:
        meta = em.run(rdir)
    except Exception as e:  # noqa: BLE001  (a digest mismatch raises after writing run_meta)
        err = f"{type(e).__name__}: {e}"
        meta = json.loads((rdir / "run_meta.json").read_text()) if (rdir / "run_meta.json").exists() else {}
    wall = time.time() - t0
    res = co._result(cpu0, wall)
    logs.close()
    sent = list(be.sent) if be is not None else []
    if be is not None:
        be.close()
    if srv is not None:
        srv.stop()
    rm = json.loads((rdir / "run_meta.json").read_text()) if (rdir / "run_meta.json").exists() else {}
    rm.update(memory_setting=RC.memory_setting(host_gib), pilot_label=LABEL)
    (rdir / "run_meta.json").write_text(json.dumps(rm, indent=2, sort_keys=True) + "\n")
    (rdir / "coordinator_result.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    (rdir / "sent_bodies_summary.json").write_text(json.dumps(dict(
        n=len(sent), all_have_salt=all((b.get("body") or b).get("cache_salt") for b in sent) if sent else None),
        default=str) + "\n")
    return dict(label=label, arm=arm_name, n=n_dev, run_s=run_s, host_gib=host_gib, rdir=str(rdir), tdir=str(tdir),
                err=err, run_meta=rm, coord=res, n_sent=len(sent), sent=sent, server=sinfo, wall_s=wall)


def score(cell):
    import score as SC
    try:
        s = SC.score_run(Path(cell["tdir"]), Path(cell["rdir"]), CAL, cell["arm"])
        return dict(ok=True, score=s)
    except Exception as e:  # noqa: BLE001
        return dict(ok=False, error=f"{type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("prep", "step1", "cell"))
    ap.add_argument("--arm")
    ap.add_argument("--n", type=int)
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--host-gib", type=float, default=HOST_TIGHT)
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if a.what == "prep":
        prep()
    elif a.what == "cell":
        c = run_cell(a.arm, a.n, a.run_s, a.host_gib)
        s = score(c)
        out = dict(c, sent=None, score=s)
        with open(OUT / "pilot_runs.jsonl", "a") as f:
            f.write(json.dumps(out, default=str) + "\n")
        log(f"cell {c['label']}: err {c['err']} valid {c['run_meta'].get('run_valid')} lateness p99 "
            f"{(c['run_meta'].get('lateness') or {}).get('p99_ms')} digests_equal {c['run_meta'].get('digests_equal')} "
            f"requests {c['coord'].get('n_requests')} errors {c['coord'].get('n_errors')} scored {s.get('ok')} "
            f"{'' if s.get('ok') else s.get('error')}")


if __name__ == "__main__":
    main()
