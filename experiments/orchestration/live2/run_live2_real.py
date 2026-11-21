#!/usr/bin/env python3
"""One REAL-SERVER live2 cell per invocation, every input a flag. CPU side only.

StudyLIVE2-harness, fix (c). This is `experiments/orchestration/study_live2_pilot.py` turned into
a committed runner: the pilot's behaviour is kept (the same trace generation, the same arm and
coordinator construction as `run_live2_cell.py`, the same header fields, the real-time
`FleetEmulator` through `bridge.EmulatorBridge`, the same run_meta annotation, then
`scorer/score.py`), with three differences, all of them the harness fix this row is about:

  1. THE COORDINATOR RUNS IN ITS OWN PROCESS by default (`procsplit.py`), so the emulator's
     clock, and therefore the lateness this run is judged by, is measured in a process that does
     no HTTP. `--no-split` keeps the pilot's single-process wiring for comparison.
  2. The HTTP is one async streaming client and the frame base64 is computed once
     (`asyncbackend.py`, `framecache.py`).
  3. The emulator ticks the coordinator on the WALL CLOCK while it waits, which is what actually
     fixed the pilot's lateness; see the StudyLIVE2-harness report section.

The pilot's own adapters are kept and still recorded: `--frames-root` is a directory resolved as
`frames_root / frame_ref` (a tree of symlinks named by frame_ref is how the pilot built it), the
bridge carries `--server-kind` so the emulator's run_meta records what served the run, and a run
with no `--server` sends nothing (the device-only arm).

STARTING THE ENGINE IS NOT THIS SCRIPT'S JOB unless `--start-server` is given: the flag exists so
the H100 can keep the pilot's restart-per-run behaviour, and it imports the H100-only modules
lazily so this file stays runnable on flash. Without it, `--server URL` points at a server the
caller already started.

NOTHING HERE IS A MEASUREMENT BY ITSELF: `is_measurement` is False in every header this writes,
and a run against anything but a real engine carries that `server_kind`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
# HERE / "hybrid": hybrid_arm.py imports its sibling value_reader as a top-level module (flash 5d7c084), which fails
# unless the package directory itself is on the path (every run died at `import hybrid` at 16:37 on 2026-11-20).
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)



def _instrument_placement(st):
    """Output-only: total enact_placement's per-call counts (offloaded / kept_warm / evicted / resident), which cstate
    returns and discards, so a run records whether --kv-capacity-enforced ever evicted anything. No decision reads it."""
    tot = {"calls": 0}
    orig = st.enact_placement
    def wrapped(now):
        c = orig(now)
        tot["calls"] += 1
        for k, v in (c or {}).items():
            tot[k] = tot.get(k, 0) + int(v)
        return c
    st.enact_placement = wrapped
    return tot


def _memory_pressure(st, tot):
    p = dict(getattr(st, "pressure", None) or {})
    p.pop("_open", None)
    p["intervals_n"] = len(p.get("intervals") or [])
    p["intervals"] = (p.get("intervals") or [])[:200]
    return dict(kv_capacity_enforced=bool(getattr(st, "kv_capacity_enforced", False)),
                gpu_kv_tokens=int(getattr(st, "gpu_kv_tokens", 0) or 0), pressure=p, enact_placement_totals=tot)


def build_parser() -> argparse.ArgumentParser:
    # B3: the --robot-deadline-s default and the trace-name anchor are READ from data_sources, so
    # there is one definition of each. `main` overwrites `_DS.ROBOT_DEADLINE_S` with the parsed
    # value, and this function runs BEFORE that assignment, so the default it reads is the
    # module's own committed 3.0 and never a value a previous parse left behind.
    import data_sources as _DS
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", required=True)
    ap.add_argument("--out", required=True, help="the run directory for this ONE cell")
    ap.add_argument("--trace-dir", default=None,
                    help="an existing trace; generated under --work when absent")
    ap.add_argument("--work", default=None, help="where generated traces are kept")
    ap.add_argument("--n-devices", type=int, default=8)
    ap.add_argument("--ratio", default="50:50")
    ap.add_argument("--ss-question-set", default="ss1", choices=["ss1", "ss2"],
                    help="D143: single-shot devices draw from StudySS1 (default) or the EVAL part of the committed StudySS2 "
                         "30/70 split (RefSpatial + RealWorldQA); recorded in the header and the trace directory name")
    ap.add_argument("--robot-question-set", default="eval", choices=["eval", "lh_req"],
                    help="D142 / D143 A: robots draw from EVAL (default) or EVAL LH-REQ questions only; recorded in the "
                         "header and in the trace directory name")
    ap.add_argument("--robot-deadline-s", type=float, default=_DS.ROBOT_DEADLINE_S,
                    help="D147 / B3: the robot (long-horizon) deadline L, written into every robot question of the "
                         "trace and used by the scorer. The DEFAULT IS NOW 3.0 (single-shot + 1 s, from the use case); "
                         "5.0 was the historical starting value (D71) and is one point of the D147 sweep. Any value "
                         "other than the 5.0 TRACE NAME ANCHOR gets its own trace directory (_L<value>) and is "
                         "recorded in the header, so a 3 s run is tagged _L3 whether it was passed or defaulted")
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--mode", default="A", choices=("A", "B"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--frame-manifest", default=None)
    ap.add_argument("--dashcam-format", default="oneframe", choices=("oneframe", "epg"),
                    help="D153: 'epg' sends every dashcam query, device and cloud, as the append-only episode "
                         "context of D148 (EP-G as StudySH-EP ran it); 'oneframe' is the committed StudyD3 body and "
                         "the default. It is a property of the TRACE, so a different format gets its own trace "
                         "directory and its own fairness digest, and the coordinator reads it off the trace")
    ap.add_argument("--dashcam-min-frames", type=int, default=3,
                    help="D153's minimum-frame floor: instants before an episode's Nth frame are not decision "
                         "instants for ANY arm, device or cloud, and are excluded by not being emitted at all. "
                         "epg only; the user may raise it to 6")
    ap.add_argument("--frames-root", default=None)
    ap.add_argument("--server", default=None, help="OpenAI-compatible base URL; omit to send nothing")
    ap.add_argument("--server-kind", default="vllm")
    ap.add_argument("--model", default="32BI")
    ap.add_argument("--gpu-kv-tokens", type=int, default=62944)
    ap.add_argument("--host-tier-gib", type=float, default=27.0)
    ap.add_argument("--host-tier-tokens", type=int, default=None)
    ap.add_argument("--calibration", default=None)
    ap.add_argument("--cost-model", default="pol4")
    ap.add_argument("--h-s", type=float, default=0.5)
    ap.add_argument("--mu-mode", default="ewma")
    ap.add_argument("--mu-fixed", type=float, default=None)
    ap.add_argument("--impl", default="fast")
    ap.add_argument("--cap-k", type=int, default=None)
    ap.add_argument("--decision-period-s", type=float, default=0.1)
    ap.add_argument("--gpu-budget-s", type=float, default=None)
    ap.add_argument("--drain-s", type=float, default=20.0)
    ap.add_argument("--tick-s", type=float, default=None)
    ap.add_argument("--self-tick-s", type=float, default=0.005)
    ap.add_argument("--http-limit", type=int, default=16384)
    ap.add_argument("--cache-cap-bytes", type=int, default=None)
    ap.add_argument("--no-split", dest="split", action="store_false",
                    help="the pilot's single-process wiring, for comparison only")
    ap.add_argument("--no-warm-cache", dest="warm_cache", action="store_false")
    ap.add_argument("--server-extra-flags", default=None,
                    help="D130 tuned-engine: extra vLLM flags, only '--long-prefill-token-threshold 1024' accepted")
    ap.add_argument("--scheduling-policy", default="fcfs", choices=("fcfs", "priority"),
                    help="vllm-priority wiring: start the server with --scheduling-policy priority and "
                         "send each request's priority; default fcfs (the round-1 server)")
    ap.add_argument("--kv-capacity-enforced", action="store_true",
                    help="D133 PA-4 / overnight plan: set CoordState.kv_capacity_enforced (enforce gpu_kv_tokens as a "
                         "capacity for every arm); off by default, recorded in the header")
    ap.add_argument("--c-inflight", type=int, default=None,
                    help="D114 sensitivity: set the EDF-family arm's own c_inflight on the constructed "
                         "instance (the factory passes no arguments to these arms); default = the arm's 4")
    ap.add_argument("--forward-at", default="first", choices=("first", "end"),
                    help="addendum: forward answers at the first content token (ruling Option 1) or at stream end")
    ap.add_argument("--no-forward-on-completion", dest="forward_on_completion",
                    action="store_false",
                    help="StudyLIVE2-harness addendum off: answers wait for the decision thread")
    ap.add_argument("--no-score", dest="score", action="store_false")
    ap.add_argument("--memory-setting", default=None)
    ap.add_argument("--label", default="")
    ap.add_argument("--start-server", action="store_true",
                    help="H100 only: restart the round-1 server for this cell, as the pilot did")
    ap.set_defaults(split=True, warm_cache=True, score=True, forward_on_completion=True)
    return ap


def _arm_kwargs(a) -> Dict[str, Any]:
    if a.arm != "policy-core":
        return {}
    return dict(cost_model=a.cost_model, h_s=a.h_s, mu_mode=a.mu_mode, mu_fixed=a.mu_fixed,
                impl=a.impl, cap_k=a.cap_k)


def _trace(a, work: Path) -> Path:
    import data_sources as _DS
    import trace as TR
    if a.trace_dir:
        return Path(a.trace_dir)
    # The cache key must carry every generator input that changes the trace. The defaults keep the historical name
    # (so committed runs' traces are reused unchanged); any other ratio or robot question set gets its own directory,
    # otherwise a 40:40:20 or LH-REQ run would silently reuse a 50:50 EVAL trace.
    extra = "" if (a.ratio == "50:50" and a.robot_question_set == "eval" and a.ss_question_set == "ss1") else \
        f"_r{a.ratio.replace(':', '-')}_{a.robot_question_set}_{a.ss_question_set}"
    # D147: a different L is a different trace. The comparison is against the 5.0 TRACE NAME
    # ANCHOR and NOT against the argparse default, which B3 has moved to 3.0. Tying it to the
    # default would silently give the un-suffixed name a second meaning: committed un-suffixed
    # cells are 5 s, so a defaulted 3 s run must be tagged _L3 exactly as an explicit one is, and
    # a 5 s run must stay un-suffixed. Committed _L3 and un-suffixed cells both stay addressable,
    # which is what the H100's driver and the offline re-scorer key off.
    if float(a.robot_deadline_s) != _DS.TRACE_NAME_ANCHOR_DEADLINE_S:
        extra += f"_L{float(a.robot_deadline_s):g}"
    if a.dashcam_format != "oneframe":          # D153: a different dashcam format is a different workload
        extra += f"_{a.dashcam_format}"
        if int(a.dashcam_min_frames) != 3:
            extra += f"f{int(a.dashcam_min_frames)}"
    tdir = work / "traces" / f"seed{a.seed}_n{a.n_devices}_{int(a.run_s)}s_{a.mode}{extra}"
    if not (tdir / "trace.jsonl").exists():
        TR.write_trace(tdir, TR.generate_trace(
            a.seed, a.n_devices, a.ratio, a.run_s, a.mode,
            frame_manifest=(Path(a.frame_manifest) if a.frame_manifest else None),
            **({} if a.robot_question_set == "eval" else dict(robot_question_set=a.robot_question_set)),
            **({} if a.ss_question_set == "ss1" else dict(ss_question_set=a.ss_question_set)),
            **({} if a.dashcam_format == "oneframe"
               else dict(dashcam_format=a.dashcam_format,
                         dashcam_min_frames=int(a.dashcam_min_frames)))))
    return tdir


def run(a) -> Dict[str, Any]:
    import arms as A
    import cachekeys as CK
    import calib as CALIB
    import cstate as CS
    import emulator as EM
    import run_live2_cell as RC

    rdir = Path(a.out)
    rdir.mkdir(parents=True, exist_ok=True)
    work = Path(a.work) if a.work else (rdir.parent / "work")
    work.mkdir(parents=True, exist_ok=True)
    tdir = _trace(a, work)
    tmeta = json.loads((tdir / "trace_meta.json").read_text())
    htok = int(a.host_tier_tokens or RC.host_tokens(a.host_tier_gib))
    sends = bool(a.server)

    # StudyLIVE2-harness addendum (2), from flash's branch: a real-server run refuses to start
    # with a frame it cannot send (checked BEFORE the server starts, so nothing is half-run)
    import preflight as PF
    frames_report = PF.require_frames(tdir, (Path(a.frames_root) if a.frames_root else None),
                                      a.server_kind if sends else "device-only-no-server")
    (rdir / "frames_preflight.json").write_text(
        json.dumps(frames_report, indent=1, default=str) + "\n")

    srv = None
    sinfo: Optional[Dict[str, Any]] = None
    # D115: 1 s host-load sampler over the whole run (server start to server stop)
    import hostload as HL
    hl = HL.HostLoadSampler(rdir / "host_load.jsonl.gz").start()
    if a.start_server:
        srv, sinfo = _start_server(a)

    import hybrid  # noqa: F401  (registers the hybrid-* arms; D138)
    arm = A.make_arm(a.arm, **_arm_kwargs(a))
    if a.c_inflight is not None:
        if not hasattr(arm, "c_inflight"):
            raise SystemExit(f"--c-inflight given but arm {a.arm} has no c_inflight")
        arm.c_inflight = int(a.c_inflight)
    conf = dict(gpu_kv_tokens=a.gpu_kv_tokens, host_tier_gib=a.host_tier_gib,
                host_tier_tokens=htok, targets=CS.TARGETS)
    if sends:                                    # vllm-priority refuses an undeclared server mode
        conf.update(server_scheduling_policy=a.scheduling_policy, has_backend=True)
    cal: Dict[str, Any] = {}
    knots = None
    if a.calibration:
        cal = CALIB.load_map(Path(a.calibration))
        CALIB.require_runnable(cal, a.server_kind)
        knots = CALIB.write_knots(cal, rdir / "calibration_knots.json")
        if a.arm == "policy-core":
            conf["calibration_knots_path"] = knots
    arm.live2_configure(**conf)

    header = dict(
        label=a.label or "StudyLIVE2 real-server cell", git_commit=RC.git_commit(),
        arm=arm.name, arm_version=getattr(arm, "arm_version", None),
        flags=(arm.flags.as_dict() if hasattr(arm, "flags") else {}),
        gpu_kv_tokens=a.gpu_kv_tokens, host_tier_gib=a.host_tier_gib, host_tier_tokens=htok,
        cost_model=(a.cost_model if a.arm == "policy-core" else None),
        calibration_file=(str(a.calibration) if a.calibration else None),
        calibration_label=cal.get("label"),
        fairness_digest=tmeta.get(f"fairness_digest_{a.mode}"),
        live1_trace_digest=tmeta.get("live1_trace_digest"),
        seed=a.seed, targets=CS.TARGETS, upload_mode=a.mode, robot_question_set=a.robot_question_set, ss_question_set=a.ss_question_set,
        robot_deadline_s=float(a.robot_deadline_s),
        mu_mode=(a.mu_mode if a.arm == "policy-core" else None),
        H=(a.h_s if a.arm == "policy-core" else None),
        decision_period_s=a.decision_period_s, ratio=a.ratio, n_devices=a.n_devices,
        run_s=a.run_s, memory_setting=RC.memory_setting(a.host_tier_gib, a.memory_setting),
        server=sinfo, server_url=(a.server or "none"), server_kind=a.server_kind,
        frames_preflight=frames_report, git_working_tree=_tree_state(),
        c_inflight=getattr(arm, "c_inflight", None),
        scheduling_policy=(a.scheduling_policy if sends else None),
        server_extra_flags=(a.server_extra_flags if sends else None),
        c_inflight_set_by_runner=(a.c_inflight is not None),
        kv_capacity_enforced=bool(a.kv_capacity_enforced),
        dashcam_format=tmeta.get("dashcam_format", "oneframe"),
        dashcam_min_frames=tmeta.get("dashcam_min_frames"),
        epg_cap_frames=tmeta.get("epg_cap_frames"),
        epg_refresh_rule=tmeta.get("epg_refresh_rule"),
        model=a.model, split_processes=bool(a.split), is_measurement=False)
    (rdir / "header.json").write_text(json.dumps(header, indent=1, default=str) + "\n")

    cfg = dict(run_dir=str(rdir), arm=a.arm, arm_kwargs=_arm_kwargs(a), mode=a.mode,
               run_s=a.run_s, drain_s=a.drain_s, decision_period_s=a.decision_period_s,
               gpu_kv_tokens=a.gpu_kv_tokens, host_tier_gib=a.host_tier_gib,
               host_tier_tokens=htok, seed=a.seed,
               run_tag=CK.run_tag(a.seed, a.arm), frames_root=a.frames_root,
               server_url=a.server, model=a.model,
               strip_hints=(a.server_kind != "fake"), defer_images=True,
               calibration_knots_path=(str(knots) if knots else None),
               gpu_budget_s=a.gpu_budget_s, http_limit=a.http_limit,
               cache_cap_bytes=a.cache_cap_bytes, self_tick_s=a.self_tick_s,
               forward_on_completion=bool(a.forward_on_completion),
               c_inflight=a.c_inflight, kv_capacity_enforced=bool(a.kv_capacity_enforced),
               scheduling_policy=(a.scheduling_policy if sends else None),
               forward_at_first_token=(a.forward_at == "first"))

    err = None
    em = None
    t0 = time.time()
    if a.split:
        import harness_fixture as HF
        import procsplit as PS
        if a.warm_cache and a.frames_root:
            cfg["warm_refs"] = HF.refs_in_trace(tdir)
        sr = PS.SplitRun(cfg, kind=a.server_kind)
        br = sr.__enter__()
        try:
            em = _emulator(EM, tdir, br, a)
            em.lateness.detail = []          # per-action kind, for the addendum's instrumentation
            em.run(rdir)
        except Exception as e:                                        # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        finally:
            sr.__exit__()
        res = dict(br.stats())
    else:
        res, err = _inprocess(a, tdir, rdir, cfg, htok, arm, EM)
    wall = time.time() - t0
    if srv is not None:
        srv.stop()
    host_load = hl.stop()

    rm = (json.loads((rdir / "run_meta.json").read_text())
          if (rdir / "run_meta.json").exists() else {})
    rm.update(memory_setting=RC.memory_setting(a.host_tier_gib, a.memory_setting),
              split_processes=bool(a.split), label=header["label"], git_commit=header["git_commit"])
    # StudyLIVE2-harness addendum (instrumentation): lateness per action kind, and the gap from
    # each cloud answer's response-stream end to its forwarding (child) and receipt (emulator).
    if a.split and em is not None and em.lateness.detail is not None:
        rm["lateness_by_kind"] = _by_kind(em.lateness.detail)
        _write_detail(rdir, em.lateness.detail)
    rm["completion_to_forward_ms"] = res.get("completion_to_forward_ms")
    rm["completion_to_emulator_ms"] = res.get("completion_to_emulator_ms")
    rm["forward_on_completion"] = bool(a.split and a.forward_on_completion)
    rm["submit_delay_ms"] = res.get("submit_delay_ms")          # epoch start -> submit call
    rm["decision_time"] = res.get("decision_time")              # D115: wall, CPU, ratio, candidates
    rm["host_load"] = host_load                                  # D115: 1 s sampler percentiles
    rm["submit_delay_total_ms"] = (res.get("backend") or {}).get("submit_delay_total_ms")  # epoch nominal t -> wire
    rm["wire_extra_delay_ms"] = (res.get("backend") or {}).get("wire_extra_delay_ms")
    rm["decision_latency_ms"] = res.get("decision_latency_ms")
    rm["forward_at"] = a.forward_at if (a.split and a.forward_on_completion) else "decision-thread"
    rm["first_token_to_forward_ms"] = res.get("first_token_to_forward_ms")
    rm["first_line_to_first_content_ms"] = (res.get("backend") or {}).get("first_line_to_first_content_ms")
    rm["forwarding"] = {k: (res.get("bridge") or {}).get(k) for k in
                        ("n_forwarded_on_completion", "n_skipped_forwarded", "n_forward_mismatch",
                         "n_recall_first_token", "n_recall_letter_differs", "recall_letter_diffs",
                         "n_monitor_score_differs")}
    rm["callback_errors"] = (res.get("backend") or {}).get("n_callback_errors")
    (rdir / "run_meta.json").write_text(json.dumps(rm, indent=2, sort_keys=True) + "\n")
    (rdir / "coordinator_result.json").write_text(
        json.dumps(res, indent=1, default=str) + "\n")
    out = dict(arm=a.arm, n_devices=a.n_devices, mode=a.mode, run_s=a.run_s, seed=a.seed,
               split=bool(a.split), err=err, wall_s=round(wall, 3),
               run_dir=str(rdir), trace_dir=str(tdir),
               lateness=rm.get("lateness"), run_valid=rm.get("run_valid"),
               digests_equal=rm.get("digests_equal"),
               n_requests=res.get("n_requests"), n_errors=res.get("n_errors"),
               server_kind=a.server_kind, is_measurement=False)
    if a.score and a.calibration:
        out["score"] = _score(tdir, rdir, Path(a.calibration), a.arm)
    (rdir / "cell.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return out


def _tree_state() -> Dict[str, Any]:
    """HEAD plus whether, and how, the working tree differs from it (a run's exact code)."""
    import hashlib
    import subprocess
    def g(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout
    diff = g("diff", "HEAD", "--", "experiments")
    return dict(head=g("rev-parse", "HEAD").strip(), dirty=bool(diff),
                diff_sha256=(hashlib.sha256(diff.encode()).hexdigest() if diff else None),
                dirty_files=sorted({l[6:] for l in diff.splitlines() if l.startswith("+++ b/")}))


def _by_kind(detail) -> Dict[str, Any]:
    from collections import defaultdict
    g: Dict[str, list] = defaultdict(list)
    for _due, what, ms in detail:
        g[str(what)].append(float(ms))
    out = {}
    for k, v in sorted(g.items()):
        v.sort()
        def q(p, v=v):
            return round(v[min(len(v) - 1, int(p * len(v)))], 4)
        out[k] = dict(n=len(v), p50_ms=q(0.5), p90_ms=q(0.9), p99_ms=q(0.99), max_ms=round(v[-1], 4),
                      n_over_50ms=sum(1 for x in v if x > 50.0))
    return out


def _write_detail(rdir: Path, detail) -> None:
    import gzip
    with gzip.open(rdir / "lateness_detail.jsonl.gz", "wt") as f:
        for due, what, ms in detail:
            f.write(json.dumps(dict(due_t=due, kind=what, lateness_ms=ms)) + "\n")


def _emulator(EM, tdir: Path, br, a):
    kw = {}
    if a.tick_s is not None:
        kw["tick_s"] = a.tick_s
    return EM.FleetEmulator(tdir, br, a.mode, realtime=True, drain_s=a.drain_s, **kw)


def _inprocess(a, tdir: Path, rdir: Path, cfg, htok, arm, EM):
    """The pilot's single-process wiring, kept for comparison (`--no-split`)."""
    import framecache as FC
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    cache = FC.FrameCache(Path(a.frames_root)) if a.frames_root else None
    be = None
    if a.server:
        from asyncbackend import AsyncLive2Backend
        be = AsyncLive2Backend(a.server, model=a.model,
                               strip_hints=(a.server_kind != "fake"), cache=cache,
                               limit=a.http_limit)
    logs = Logs(rdir).open()
    co = Live2Coordinator(arm, be, [], gpu_kv_tokens=a.gpu_kv_tokens,
                          host_tier_gib=a.host_tier_gib, host_tier_tokens=htok,
                          upload_mode=a.mode, window_s=a.run_s, drain_s=a.drain_s,
                          decision_period_s=a.decision_period_s, seed=a.seed, logs=logs,
                          run_tag=cfg["run_tag"],
                          frames_root=(Path(a.frames_root) if a.frames_root else None),
                          frame_cache=cache, defer_images=True,
                          dry_run=not bool(a.server), gpu_budget_s=a.gpu_budget_s,
                          targets=cfg.get("targets"))
    co.st.kv_capacity_enforced = bool(a.kv_capacity_enforced)
    _mp_tot = _instrument_placement(co.st)
    br = EmulatorBridge(co)
    br.kind = a.server_kind
    import time as _t
    cpu0 = _t.process_time()
    t0 = _t.time()
    err = None
    try:
        _emulator(EM, tdir, br, a).run(rdir)
    except Exception as e:                                            # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    res = co._result(cpu0, _t.time() - t0)
    res["memory_pressure"] = _memory_pressure(co.st, _mp_tot)          # output only (split mode: procsplit)
    co.write_decision_times(rdir / "decision_time.jsonl.gz")          # D115
    logs.close()
    if be is not None:
        res["backend"] = be.metrics() if hasattr(be, "metrics") else None
        be.close()
    return res, err


def _score(tdir: Path, rdir: Path, cal: Path, arm: str) -> Dict[str, Any]:
    import score as SC
    try:
        import data_sources as _DS
        return dict(ok=True, score=SC.score_run(tdir, rdir, cal, arm, L_rob_grid=(float(_DS.ROBOT_DEADLINE_S),)))
    except Exception as e:                                            # noqa: BLE001
        return dict(ok=False, error=f"{type(e).__name__}: {e}")


def _start_server(a):
    """The pilot's restart-per-run, imported lazily because it is H100-only."""
    sys.path.insert(0, str(REPO / "experiments/orchestration"))
    import study_live2_pilot as P
    srv, sinfo, _M = P.start_server(a.host_tier_gib, scheduling_policy=a.scheduling_policy,
                                    extra_flags=(a.server_extra_flags.split() if a.server_extra_flags else None))
    return srv, sinfo


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    # D147: set the robot deadline ONCE, before any module reads it: trace generation reads DS.ROBOT_DEADLINE_S at call
    # time and the scorer binds it at import (it is imported lazily, after this line).
    import data_sources as _DS
    _DS.ROBOT_DEADLINE_S = float(a.robot_deadline_s)
    out = run(a)
    print(json.dumps(out, indent=1, default=str))
    return 0 if not out.get("err") else 1


if __name__ == "__main__":
    raise SystemExit(main())
