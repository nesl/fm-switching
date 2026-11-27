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
    ap.add_argument("--robot-reask-mean-s", type=float, default=0.0,
                    help="D159 (C) / D161: per robot device a Poisson re-ask process with this "
                         "mean interval in seconds, drawing uniformly from that session's "
                         "questions already asked. 0.0 (the default) emits no re-asks and leaves "
                         "the trace byte-identical to the committed one.")
    ap.add_argument("--robot-upload", default="batch-30s", choices=("batch-30s", "per-frame"),
                    help="D154 (4) / D150 SYNC (1): 'per-frame' uploads every robot history frame AS CAPTURED, one "
                         "request per frame, for ALL arms; 'batch-30s' is D68's fixed 30-s batch and the committed "
                         "default (earlier cells are labelled upload-30s). It is a property of the TRACE, so a "
                         "per-frame cell gets its own trace directory, its own fairness digest and its own run tag")
    # D242 item A: the correlated multi-robot outage. ALL THREE DEFAULT OFF/ZERO, so the default
    # path is the committed one and the trace directory keeps its committed name.
    ap.add_argument("--outage-robots-k", type=int, default=0,
                    help="D242 A: how many robots lose the uplink TOGETHER; 0 is off")
    ap.add_argument("--outage-duration-s", type=float, default=0.0,
                    help="D242 A: the outage window D in seconds; 0 is off")
    ap.add_argument("--outage-seed-offset", type=int, default=0,
                    help="D242 A: offsets the dedicated outage RNG stream only")
    # D266 item 2: the placement rule. DEFAULTS TO THE COMMITTED BAND DRAW, so a run that does not
    # name it is the run the committed cells made.
    ap.add_argument("--outage-placement", default="band", choices=("band", "centre", "evidence"),
                    help="D266 item 2: 'centre' fixes the window at the centre of the committed "
                         "band and nests the victims across k; 'band' is the committed D242 draw; "
                         "E1 'evidence' takes the window start from --outage-t0-s (required)")
    ap.add_argument("--outage-t0-s", type=float, default=None,
                    help="E1: explicit outage start, required by and only valid with "
                         "--outage-placement evidence; same value for every k at a seed")
    ap.add_argument("--outage-t0-derivation", default="",
                    help="E1: free text recorded in the trace meta (how t0 was chosen)")
    # PER-DEVICE UPLINK RATE (D75 default 13.6 Mbps for every device). DEFAULT None = unchanged.
    ap.add_argument("--robot-uplink-mbps", type=float, default=None,
                    help="uplink rate in Mbps for EVERY robot device (ids robo*), for the WHOLE run, "
                         "independent of any outage; every other device keeps the D75 default 13.6. "
                         "At n16 _c3-11-2 the 11 robots equal the k=11 outage victim set. It is an "
                         "emulator setting and does NOT enter the trace directory name. None = off")
    ap.add_argument("--uplink-question-priority", action="store_true",
                    help="question text (class 0) is served ahead of history and monitor frames "
                         "(class 1) on every device uplink queue, non-preemptive (default OFF)")
    # link_events switch: DEFAULT OFF. On, the emulator emits `connectivity` events from the
    # trace's outage meta and the coordinator keeps a per-device link table published as
    # `Observation.device_links`. Meaningless without an outage (no events then, byte-identical).
    ap.add_argument("--link-events", action="store_true",
                    help="emit and apply connectivity events (default OFF)")
    # link_sync switch: DEFAULT OFF. Needs --link-events. On, an arm that DECLARES sync control
    # (link_sync.arm_controls_sync) runs with the device backlog held until it sends `sync_pull`;
    # any other arm in the same run is unaffected (auto-release, the committed FIFO behaviour).
    ap.add_argument("--link-sync", action="store_true",
                    help="hold the post-outage backlog for a sync-controlling arm (default OFF)")
    # D273 (1): what happens to the frames. DEFAULTS TO THE COMMITTED BUFFERED RE-TIMING, so a run
    # that does not name it is the run the committed cells made.
    ap.add_argument("--outage-semantics", default="buffered", choices=("buffered", "true"),
                    help="D273 (1): 'true' loses the in-window frames to the cloud and leaves the "
                         "device's own history complete; 'buffered' is the committed D242 "
                         "re-timing and the default")
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
    # D216 (2) / D222 (1) g / D227 (E3): the engine /metrics scrape. OFF by default, because
    # turning it on for every cell that has a server is a DEPLOYMENT-DEFAULT change and only the
    # user rules those (D187: held or unproved code defaults OFF; the committed StudyD222-PASS1
    # pre-registration states "class default OFF"). A cell asks for it explicitly. The class
    # default in asyncbackend is already False; this line is what overrode it.
    ap.add_argument("--metrics-scrape", dest="metrics_scrape", action="store_true", default=False,
                    help="scrape the engine's /metrics in the background and publish the "
                         "allow-listed engine keys into the observation (D216 (2), D227)")
    ap.add_argument("--no-metrics-scrape", dest="metrics_scrape", action="store_false",
                    help="switch the /metrics scrape off; cell.json then records state "
                         "never_scraped and marks the engine-metric quantities untrusted")
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


_SWITCH_KEYS = ("live2_predictive_belief", "live2_pb_engine_resync", "live2_book_belief_uncached",
                "live2_la_arrival_admission", "live2_value_aware_admission", "live2_catchup_prefill",
                "live2_pb_wire_tokens", "live2_pb_host_engine_model")
_SWITCH_KEYS_ON_ONLY = ("live2_catchup_prefill_paced", "live2_catchup_prefill_busyx", "live2_pb_touch_guard",
                         "live2_catchup_prefill_value",
                         # step 3 on F0 (D331): header record only; ON-only, so every other arm is unchanged
                         "live2_cf_protect_defer", "live2_cf_forfeit_admit", "live2_cf_resident_set",
                         "live2_cf_harm_arrivals", "live2_cf_s2_netting")


def _switch_record(arm) -> Dict[str, bool]:
    """The arm-scoped switch values as the instance dicts hold them (the arm, its _rules and
    _rules._base: catch-up prefill lives on _rules); an absent key is off. Empty unless at least
    one is on, so the header and cell JSON of every other arm are unchanged."""
    insts = [arm]
    rules = getattr(arm, "_rules", None)
    if rules is not None:
        insts += [rules, getattr(rules, "_base", None)]
    owns = [vars(o) for o in insts if o is not None]
    rec = {k: any(bool(own.get(k, False)) for own in owns) for k in _SWITCH_KEYS}
    for k in _SWITCH_KEYS_ON_ONLY:
        if any(bool(own.get(k, False)) for own in owns):
            rec[k] = True
    return rec if any(rec.values()) else {}


def _arm_kwargs(a) -> Dict[str, Any]:
    if a.arm != "policy-core":
        return {}
    return dict(cost_model=a.cost_model, h_s=a.h_s, mu_mode=a.mu_mode, mu_fixed=a.mu_fixed,
                impl=a.impl, cap_k=a.cap_k)


def _check_link_args(a) -> None:
    if a.outage_placement == "evidence" and a.outage_t0_s is None:
        raise SystemExit("--outage-placement evidence requires --outage-t0-s; refused")
    if a.outage_placement != "evidence" and a.outage_t0_s is not None:
        raise SystemExit("--outage-t0-s is only valid with --outage-placement evidence; refused")


def _trace(a, work: Path) -> Path:
    _check_link_args(a)
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
    if a.robot_upload != "batch-30s":           # D154 (4): a different upload contract is a different workload
        extra += "_perframe"
    # D159 (C) / D161: a different question volume is a different workload, and the directory MUST
    # differ or `if not (tdir / "trace.jsonl").exists()` would silently reuse the non-re-ask trace.
    if float(a.robot_reask_mean_s) > 0.0:
        extra += "_rq%g" % float(a.robot_reask_mean_s)
    # D242 item A: an outage is a different trace, and the directory MUST differ or the
    # `trace.jsonl` existence check below would silently reuse the no-outage trace. The
    # seed offset enters the name only when it is non-zero, so a k/D cell at offset 0 keeps
    # one name. Outages off adds nothing, which is what keeps every committed name addressable.
    if int(a.outage_robots_k) > 0 and float(a.outage_duration_s) > 0.0:
        extra += "_outk%dd%g" % (int(a.outage_robots_k), float(a.outage_duration_s))
        if int(a.outage_seed_offset) != 0:
            extra += "o%d" % int(a.outage_seed_offset)
        # D266 item 2, and it is the ONE failure here that would silently produce wrong cells
        # rather than refusing: THE PLACEMENT RULE IS PART OF THE CACHE KEY. Before this line the
        # directory name carried seed, n, run_s, mode, ratio, question sets, L, epg, perframe, rq
        # and outk<K>d<D> AND NOTHING ABOUT THE PLACEMENT, while the regeneration test below is
        # only `if not (tdir / "trace.jsonl").exists()`. So the first `centre` cell run at a
        # (seed, n, ratio, k, D) that already has a `band` trace on disk would have SERVED THE OLD
        # PLACEMENT - old victims, old window - and every gate would have passed, because the
        # driver's assertion and the trace_meta it reads cover only k and D, and both of those are
        # correct in the stale meta. The default rule adds nothing to the name, which is what
        # keeps every committed trace addressable.
        if a.outage_placement != "band":
            extra += "p%s" % str(a.outage_placement)
        # E1: the explicit t0 is part of the cache key as well as the rule, or a trace built at
        # another t0 would be served.
        if a.outage_placement == "evidence":
            extra += "t%g" % float(a.outage_t0_s)
        # link_events: the trace META then carries the deferred-batch marks, so it is a different
        # trace directory (a marks-less trace served to a link cell would hold nothing back).
        if a.link_events:
            extra += "_lnk"
        # D273 (1), and the hazard is identical to the placement one above: a BUFFERED trace served
        # from the directory cache to a TRUE-outage cell would pass every gate, because k, D and
        # the placement are all correct in the stale meta. The default adds nothing to the name.
        if a.outage_semantics != "buffered":
            extra += "s%s" % str(a.outage_semantics)
    tdir = work / "traces" / f"seed{a.seed}_n{a.n_devices}_{int(a.run_s)}s_{a.mode}{extra}"
    if not (tdir / "trace.jsonl").exists():
        TR.write_trace(tdir, TR.generate_trace(
            a.seed, a.n_devices, a.ratio, a.run_s, a.mode,
            frame_manifest=(Path(a.frame_manifest) if a.frame_manifest else None),
            **({} if a.robot_question_set == "eval" else dict(robot_question_set=a.robot_question_set)),
            **({} if a.ss_question_set == "ss1" else dict(ss_question_set=a.ss_question_set)),
            **({} if a.dashcam_format == "oneframe"
               else dict(dashcam_format=a.dashcam_format,
                         dashcam_min_frames=int(a.dashcam_min_frames))),
            **({} if a.robot_upload == "batch-30s" else dict(robot_upload=a.robot_upload)),
            **({} if float(a.robot_reask_mean_s) <= 0.0
               else dict(robot_reask_mean_s=float(a.robot_reask_mean_s))),
            # D242 item A: passed only when ON, for the same reason as every switch above: the
            # defaulted call must be the call the committed traces were built with.
            **({} if not (int(a.outage_robots_k) > 0 and float(a.outage_duration_s) > 0.0)
               else dict(outage_robots_k=int(a.outage_robots_k),
                         outage_duration_s=float(a.outage_duration_s),
                         outage_seed_offset=int(a.outage_seed_offset),
                         # passed only when it is NOT the default, for the same reason as every
                         # switch above: the defaulted call must be the call the committed traces
                         # were built with, argument for argument.
                         **({} if a.outage_placement == "band"
                            else dict(outage_placement=str(a.outage_placement))),
                         **({} if not a.link_events else dict(outage_link_marks=True)),
                         **({} if a.outage_placement != "evidence"
                            else dict(outage_t0_s=float(a.outage_t0_s),
                                      outage_t0_derivation=str(a.outage_t0_derivation))),
                         **({} if a.outage_semantics == "buffered"
                            else dict(outage_semantics=str(a.outage_semantics)))))))
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
    # THE ARM IS BUILT BEFORE THE SERVER IS STARTED. It used to be the other way round, so a bad
    # arm name crashed AFTER the server was up, the server was left orphaned at ppid 1, and the
    # next cell waited forever for a GPU that nothing would release. That cost three idle minutes
    # on GPU 2 on 2026-11-21 when `covex-v6-state` did not resolve. Nothing here touches the
    # server: `_arm_kwargs` reads only the parsed command line, and `live2_configure` still runs
    # further down, after `sends` and `sinfo` exist. So the cheap, failure-prone step now happens
    # first, and the expensive, resource-holding one second.
    import hybrid  # noqa: F401  (registers the hybrid-* arms; D138)
    arm = A.make_arm(a.arm, **_arm_kwargs(a))
    import link_sync as LS                                                 # noqa: PLC0415
    a._sync_on = bool(a.link_sync and LS.arm_controls_sync(arm))
    if a.link_sync and not a.link_events:
        raise SystemExit("--link-sync requires --link-events; refused")
    if LS.arm_controls_sync(arm) and not a.link_sync:
        raise SystemExit("arm %s controls post-outage sync and needs --link-sync (and "
                         "--link-events) in the launch arguments; refused" % a.arm)
    if a.c_inflight is not None:
        if not hasattr(arm, "c_inflight"):
            raise SystemExit(f"--c-inflight given but arm {a.arm} has no c_inflight")
        arm.c_inflight = int(a.c_inflight)

    if a.start_server:
        srv, sinfo = _start_server(a)
        # AND A BACKSTOP, because ordering only fixes the failure we have already seen. Anything
        # that raises between here and the normal stop below would orphan the server just the
        # same. `atexit` fires on a normal exit, on SystemExit and on an unhandled exception,
        # which covers every one of those; it cannot cover SIGKILL, and nothing in-process can.
        # Guarded by a flag so the normal stop is not repeated.
        import atexit

        def _stop_if_still_running(_s=srv):
            try:
                if not getattr(_s, "_live2_stopped", False):
                    _s.stop()
            except Exception:                                          # noqa: BLE001
                pass

        atexit.register(_stop_if_still_running)
    # D223 (2) / D56: THE CONTEXT LIMIT IS AN INPUT, READ ONCE HERE, BEFORE ANY DECISION IS MADE.
    # Three sources in order, and the first two are the server's own statement of what it serves:
    #
    #   1. a server THIS PROCESS STARTED: its argv, `sinfo["command"]`. Authoritative. At the real
    #      0.5x condition that argv carries `--max-model-len` TWICE (the pinned 32768 at index 7
    #      and the extra-flag 31472 at index 39) and the parse takes the LAST, as argparse does.
    #   2. a server started elsewhere and attached to with `--server`: the declared extra flags
    #      are then the only statement of its launch, so they are read if they carry a limit.
    #   3. no server at all (a dry cell): the model snapshot's own position limit, recorded under
    #      its own source string so no artefact can present it as an engine's answer.
    #
    # It FAILS LOUD, never defaults, when a server IS configured and its limit cannot be read:
    # a run that assumes its limit has not tested its over-limit rule.
    import context_limit as CL
    if sinfo is not None:
        CL.configure_from_server_argv(sinfo.get("command"),
                                      where="the started server's argv (header.json server.command)")
    elif sends:
        if CL.configure_from_extra_flags(a.server_extra_flags) is None:
            raise SystemExit(
                "--server was given without --start-server and --server-extra-flags carries no "
                "--max-model-len, so this run cannot read the engine's configured context limit: "
                "STOP (D223 (2)). Pass the limit in --server-extra-flags, or start the server "
                "here with --start-server so its argv can be read.")
    else:
        CL.configure_arch_default()
    limit_state = CL.state()
    print("D223 (2) context limit: %d tokens, source=%s"
          % (limit_state["context_limit_tokens"], limit_state["source"]), flush=True)

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

    sw_rec = _switch_record(arm)
    header = dict(
        # D154 (4): the contract is appended to the CELL LABEL as well as to the run tag, so a
        # per-frame cell announces itself in every artefact that carries a label.
        label=((a.label or "StudyLIVE2 real-server cell")
               + ("" if a.robot_upload == "batch-30s" else " [robot-upload=per-frame]")),
        git_commit=RC.git_commit(),
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
        context_limit=limit_state,          # D223 (2): every cell says what limit it ran under
        c_inflight_set_by_runner=(a.c_inflight is not None),
        kv_capacity_enforced=bool(a.kv_capacity_enforced),
        # D227: the cell says whether it scraped, in its header as well as in its metrics_health,
        # so provenance survives even if the backend block is lost. `and sends` because a cell with
        # no server cannot scrape and must not claim it tried.
        metrics_scrape=bool(a.metrics_scrape and sends),
        robot_upload=tmeta.get("robot_upload", "batch-30s"),
        robot_upload_rule=tmeta.get("robot_upload_rule"),
        dashcam_format=tmeta.get("dashcam_format", "oneframe"),
        dashcam_min_frames=tmeta.get("dashcam_min_frames"),
        epg_cap_frames=tmeta.get("epg_cap_frames"),
        epg_refresh_rule=tmeta.get("epg_refresh_rule"),
        model=a.model, split_processes=bool(a.split), is_measurement=False,
        # D266 item 2: the RESOLVED trace directory, so a validator never has to glob for it, and
        # the outage exactly as the generator recorded it, so the cell carries its own victims,
        # window and placement rule without a second file being located first.
        trace_dir=str(tdir),
        outage=tmeta.get("outage"),
        outage_placement=((tmeta.get("outage") or {}).get("placement")
                          if tmeta.get("outage") else None),
        outage_semantics=((tmeta.get("outage") or {}).get("semantics")
                          if tmeta.get("outage") else None),
        # link_events: present in the header ONLY when on, so an off header is the old header.
        **({} if not a.link_events else dict(link_events=True)),
        **({} if a.robot_uplink_mbps is None else dict(robot_uplink_mbps=float(a.robot_uplink_mbps))),
        **({} if not a.uplink_question_priority else dict(uplink_question_priority=True)),
        **({} if not getattr(a, "_sync_on", False) else dict(link_sync=True)),
        **({} if not sw_rec else dict(switches=sw_rec)))
    (rdir / "header.json").write_text(json.dumps(header, indent=1, default=str) + "\n")

    cfg = dict(run_dir=str(rdir), arm=a.arm, arm_kwargs=_arm_kwargs(a), mode=a.mode,
               run_s=a.run_s, drain_s=a.drain_s, decision_period_s=a.decision_period_s,
               gpu_kv_tokens=a.gpu_kv_tokens, host_tier_gib=a.host_tier_gib,
               host_tier_tokens=htok, seed=a.seed,
               # D154 (4): the run tag carries the upload contract, so a per-frame cell can never be
               # mistaken for a committed upload-30s one and never shares an engine-side cache entry with it.
               run_tag=CK.run_tag(a.seed, a.arm,
                                  label=("live2" if a.robot_upload == "batch-30s" else "live2perframe")),
               frames_root=a.frames_root,
               server_url=a.server, model=a.model,
               strip_hints=(a.server_kind != "fake"), defer_images=True,
               calibration_knots_path=(str(knots) if knots else None),
               gpu_budget_s=a.gpu_budget_s, http_limit=a.http_limit,
               cache_cap_bytes=a.cache_cap_bytes, self_tick_s=a.self_tick_s,
               forward_on_completion=bool(a.forward_on_completion),
               c_inflight=a.c_inflight, kv_capacity_enforced=bool(a.kv_capacity_enforced),
               metrics_scrape=bool(a.metrics_scrape),
               **({} if not a.link_events else dict(link_events=True)),
               **({} if not a._sync_on else dict(link_sync=True)),
               scheduling_policy=(a.scheduling_policy if sends else None),
               forward_at_first_token=(a.forward_at == "first"),
               # D223 (2): the limit read above travels to the coordinator PROCESS, which is where
               # the decisions are made in split mode. Resolved number plus the argv it came from.
               context_limit_tokens=int(limit_state["context_limit_tokens"]),
               context_limit_source=str(limit_state["source"]))

    err = None
    em = None
    t0 = time.time()
    if a.split:
        import harness_fixture as HF
        import procsplit as PS
        if a.warm_cache and a.frames_root:
            cfg["warm_refs"] = HF.refs_in_trace(tdir)
        # Torn-tree guard, the RUNNER-ONLY half (source_agreement.py): a runner that builds a cfg
        # without the context limit while a server is configured refuses here, before launch. This
        # is the half the runner/child overlap cannot see (run_live2_real.py is runner-only).
        if cfg.get("server_url") not in (None, "none") and cfg.get("context_limit_tokens") is None:
            raise SystemExit("PRE-FLIGHT: a server is configured but the cfg carries no "
                             "context_limit_tokens: STOP (D223 (2), torn-tree guard)")
        import source_agreement as SA
        cfg["source_runner"] = SA.loaded_repo_files()   # hashed immediately before the launch
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
        # The child writes its own coordinator_result.json BEFORE sending it. If the result never
        # arrived, say WHICH failure it was, and never overwrite the child's file with the parent's
        # five wire counters (which is how 31 committed cells lost their counts).
        if "n_requests" in res:
            res["result_status"] = "received"
        elif (rdir / "coordinator_result.json").exists():
            res = dict(json.loads((rdir / "coordinator_result.json").read_text()), **res)
            res["result_status"] = "parent_closed_before_result"
        else:
            res["result_status"] = "child_never_sent_result"
        sa = res.get("source_agreement") or {}
        if str(sa.get("verdict", "")).startswith("INVALID"):
            err = err or f"TornTree: torn_lazy_import {sa.get('torn_lazy_import')}"
    else:
        res, err = _inprocess(a, tdir, rdir, cfg, htok, arm, EM)
    wall = time.time() - t0
    if srv is not None:
        srv.stop()
        srv._live2_stopped = True          # tell the atexit backstop this one is already down
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
               robot_upload=header["robot_upload"],
               split=bool(a.split), err=err, wall_s=round(wall, 3),
               run_dir=str(rdir), trace_dir=str(tdir),
               lateness=rm.get("lateness"), run_valid=rm.get("run_valid"),
               digests_equal=rm.get("digests_equal"),
               n_requests=res.get("n_requests"), n_errors=res.get("n_errors"),
               server_kind=a.server_kind, is_measurement=False)
    # D226 (3), fail loud: the request log is complete only if (a) it has one row per submitted
    # request and (b) every outcome's cloud_payload.request_id resolves to a row (abandoned rows
    # included). Either failing sets request_log_complete = false and flags the cell.
    out["request_log_reconciled"] = _reconcile_delivered(rdir)
    out["request_log"] = rl = _request_log_check(rdir, res.get("n_requests"))
    if not rl["request_log_complete"]:
        out["flag"] = "REQUEST_LOG_INCOMPLETE"
        print(f"*** REQUEST_LOG_INCOMPLETE: {json.dumps(rl)}", file=sys.stderr, flush=True)
    if a.split:
        out["result_status"] = res.get("result_status")
        if res.get("result_status") != "received":
            out["flag_result"] = "COORDINATOR_RESULT_MISSING: " + str(res.get("result_status"))
            print(f"*** {out['flag_result']}", file=sys.stderr, flush=True)
        out["source_agreement"] = sa = res.get("source_agreement")
        if sa:
            # header.json records what state the cell actually ran in, so the guard's outcome goes
            # there too (written at start, extended here).
            hp = rdir / "header.json"
            hd = json.loads(hp.read_text()) if hp.exists() else {}
            hd["source_agreement"] = sa
            hd["result_status"] = res.get("result_status")
            hp.write_text(json.dumps(hd, indent=1, default=str) + "\n")
            if sa.get("verdict") != "OK":
                print(f"*** SOURCE AGREEMENT {sa.get('verdict')}: moved_after_import="
                      f"{sa.get('moved_after_import')} torn_lazy_import={sa.get('torn_lazy_import')}",
                      file=sys.stderr, flush=True)
    if a.score and a.calibration:
        out["score"] = _score(tdir, rdir, Path(a.calibration), a.arm)
    # D227 (E3): EVERY cell.json carries this, a dry cell's included, because "the field is
    # absent" is exactly the ambiguity the ruling exists to remove. `MT.cell_metrics_health`
    # derives the three states from the backend block and names the quantities a reader may not
    # trust; it never invents a state the counters do not support.
    import metrics_trust as MT
    out["metrics_health"] = MT.cell_metrics_health(res, dry_run=not bool(a.server))
    if sw_rec:
        out["switches"] = sw_rec
    (rdir / "cell.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return out


def _reconcile_delivered(rdir: Path) -> Dict[str, Any]:
    """User ruling 2026-11-24 (rung 3 kv0.5r s4, r10175): a request whose answer was DELIVERED must
    never be left without a row or with an `abandoned` one. The child writes real first-token rows
    for answers it forwarded; this is the backstop for any it could not see. For every outcome with a
    delivered cloud answer whose request id has no row, or only an abandoned row, a row is written
    FROM THE OUTCOME with row_source "completed_row_reconstructed": http_status 200, marked
    http_status_inferred (a delivered answer means the stream returned 200), t_first_token from the
    outcome's t_cloud_done, token fields None. Counted, never silent."""
    rq, oc = rdir / "request.jsonl", rdir / "outcomes.jsonl"
    if not rq.exists() or not oc.exists():
        return dict(checked=False, reason="request.jsonl or outcomes.jsonl absent")
    rows = [json.loads(l) for l in rq.read_text().splitlines() if l.strip()]
    by_id = {r.get("request_id"): i for i, r in enumerate(rows)}
    n_added = n_replaced = 0
    ids = []
    with open(oc) as fh:
        for line in fh:
            if not line.strip():
                continue
            o = json.loads(line)
            cp = o.get("cloud_payload")
            rid = cp.get("request_id") if isinstance(cp, dict) else None
            if rid is None or o.get("t_delivered") is None:
                continue
            i = by_id.get(rid)
            if i is not None and not rows[i].get("abandoned"):
                continue
            row = dict(rows[i]) if i is not None else dict(request_id=rid)
            row.update(device_id=row.get("device_id") or o.get("device_id"),
                       opportunity_id=row.get("opportunity_id") or o.get("opportunity_id"),
                       session_id=row.get("session_id") or o.get("session_id"),
                       t_first_token=o.get("t_cloud_done"), http_status=200,
                       http_status_inferred=True, abandoned=False,
                       row_source="completed_row_reconstructed")
            if i is None:
                rows.append(row)
                by_id[rid] = len(rows) - 1
                n_added += 1
            else:
                rows[i] = row
                n_replaced += 1
            ids.append(rid)
    if n_added or n_replaced:
        rq.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        print(f"*** REQUEST LOG RECONSTRUCTED from outcomes: {n_added} added, {n_replaced} "
              f"abandoned rows replaced: {ids[:10]}", file=sys.stderr, flush=True)
    return dict(checked=True, reconstructed_added=n_added, abandoned_replaced=n_replaced,
                reconstructed_ids_first=ids[:10])


def _request_log_check(rdir: Path, n_requests: Any) -> Dict[str, Any]:
    """D226 (3): count request.jsonl rows (and abandoned ones) against the submitted count, and
    resolve every outcome's cloud request id against those rows. Reads only this cell's files."""
    ids, n_rows, n_abandoned, abandoned_ids, sources = set(), 0, 0, set(), {}
    rq = rdir / "request.jsonl"
    if rq.exists():
        with open(rq) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                n_rows += 1
                n_abandoned += bool(r.get("abandoned"))
                if r.get("abandoned"):
                    abandoned_ids.add(r.get("request_id"))
                k = str(r.get("row_source") or "completed")
                sources[k] = sources.get(k, 0) + 1
                ids.add(r.get("request_id"))
    n_ref, unresolved, delivered_abandoned = 0, [], []
    oc = rdir / "outcomes.jsonl"
    if oc.exists():
        with open(oc) as fh:
            for line in fh:
                if not line.strip():
                    continue
                o = json.loads(line)
                cp = o.get("cloud_payload")
                rid = cp.get("request_id") if isinstance(cp, dict) else None
                if rid is None:
                    continue
                n_ref += 1
                if rid not in ids:
                    unresolved.append(rid)
                elif rid in abandoned_ids and o.get("t_delivered") is not None:
                    delivered_abandoned.append(rid)
    rows_match = n_requests is not None and n_rows == int(n_requests)
    return dict(n_requests=n_requests, request_rows=n_rows, request_rows_abandoned=n_abandoned,
                rows_match_submitted=bool(rows_match), outcome_request_ids=n_ref,
                outcome_request_ids_unresolved=len(unresolved),
                unresolved_first=unresolved[:10], row_sources=sources,
                delivered_resolving_to_abandoned=len(delivered_abandoned),
                delivered_abandoned_first=delivered_abandoned[:10],
                request_log_complete=bool(rows_match and not unresolved and not delivered_abandoned
                                          and rq.exists()))


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
    if a.link_events:
        kw["link_events"] = True
    if getattr(a, "_sync_on", False):
        kw["link_sync_hold"] = True
    if getattr(a, "uplink_question_priority", False):
        kw["uplink_question_priority"] = True
    if a.robot_uplink_mbps is not None:
        import links as LK
        rate = float(a.robot_uplink_mbps)
        if not rate > 0.0:
            raise SystemExit("--robot-uplink-mbps must be > 0; refused")
        robots = sorted({str(r.get("device_id")) for r in map(json.loads, open(Path(tdir) / "trace.jsonl"))
                         if str(r.get("device_id", "")).startswith("robo")})
        if not robots:
            raise SystemExit("--robot-uplink-mbps given but the trace holds no robo* device; refused")
        kw["link_by_device"] = {d: LK.LinkSpec(uplink_mbps=rate) for d in robots}
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
        # D216 (2): arm-scoped nowhere, CELL-scoped here. Set on the INSTANCE, so a class default
        # can never turn the scrape on for a cell that did not ask for it.
        be.metrics_scrape = bool(a.metrics_scrape)
    logs = Logs(rdir).open()
    co = Live2Coordinator(arm, be, [], gpu_kv_tokens=a.gpu_kv_tokens,
                          host_tier_gib=a.host_tier_gib, host_tier_tokens=htok,
                          upload_mode=a.mode, window_s=a.run_s, drain_s=a.drain_s,
                          decision_period_s=a.decision_period_s, seed=a.seed, logs=logs,
                          run_tag=cfg["run_tag"],
                          frames_root=(Path(a.frames_root) if a.frames_root else None),
                          frame_cache=cache, defer_images=True,
                          dry_run=not bool(a.server), gpu_budget_s=a.gpu_budget_s,
                          targets=cfg.get("targets"),
                          link_events=bool(a.link_events),
                          link_sync=bool(getattr(a, "_sync_on", False)))
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
    co.write_link_log(rdir)
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
