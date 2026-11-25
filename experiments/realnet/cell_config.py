#!/usr/bin/env python3
"""One cell as a single declarative object, so a run is reproducible from an artifact.

StudyREAL-NET support module.

WHY. Before this, a cell was assembled from CLI flags across three commands on three hosts:
reproducible only if someone transcribed them correctly, and impossible to point a D92
pre-registration row at. A cell config names everything that defines the cell -- trace,
device-to-host assignment, network profile per host, run length, seed, output -- and the
loader RESOLVES it (filling in measured floors, shaping offsets and feasibility) so the
resolved form can be stamped into `run_meta.json` alongside the results.

THE DATASET AND THE NETWORK ARE BOTH SEAMS. `trace_dir` and `frames_root` select the dataset;
`profile` per host selects the network. Neither requires a code change, and `profiles_file`
can point at a JSON file of extra profiles so a new link model needs no edit to
`mnwifi_profiles.py` either.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mnwifi_profiles as MP  # noqa: E402

REQUIRED = ("name", "trace_dir", "devices", "run_s")

# The paper's grid recipe, as the H100 driver applies it. Every token is a TRACE-GENERATION
# input, baked into the trace directory name by run_live2_real.py::_trace (lines 216-236), not
# a run-time label:
#
#   _L3    D147: --robot-deadline-s 3.0. The trace name anchor is 5.0, so 3.0 is suffixed _L3.
#   _epg   D153: --dashcam-format epg (EPG_ARGS), append-only EP-G episodes, and D156 (2) adds
#          --robot-upload per-frame, which suffixes _perframe.
#   _rq30  D159 (C) / D161: --robot-reask-mean-s 30 (RQ30_ARGS), suffixing _rq30.
#
# So the cell tag `_L3_epg_rq30` corresponds to the trace directory
# `..._L3_epg_perframe_rq30`: the driver's tag and the trace name differ by the _perframe
# token that _epg implies. baseline_matrix_table.py:548 states plainly that `_L3_epg` and
# `_L3_epg_rq30` cells are DIFFERENT WORKLOADS, so a realnet cell that declares an emulated
# comparator must match the comparator's recipe exactly, not approximately.
RECIPE_FLAGS = {
    "robot_deadline_s": 3.0,
    "dashcam_format": "epg",
    "robot_upload": "per-frame",
    "robot_reask_mean_s": 30.0,
}
RECIPE_TRACE_SUFFIX = "_L3_epg_perframe_rq30"


class ConfigError(Exception):
    """A cell config that cannot be resolved. Raised rather than defaulted."""


def load(path: Path) -> Dict[str, Any]:
    """Read a cell config and resolve it. Raises on anything ambiguous."""
    path = Path(path)
    cfg = json.loads(path.read_text())
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ConfigError("%s is missing required keys: %s" % (path, missing))

    # Extra profiles from a file, so a new link model needs no code edit.
    pf = cfg.get("profiles_file")
    if pf:
        pfp = (path.parent / pf) if not Path(pf).is_absolute() else Path(pf)
        if not pfp.exists():
            raise ConfigError("profiles_file %s does not exist" % pfp)
        extra = json.loads(pfp.read_text())
        for name, spec in (extra.get("profiles") or {}).items():
            MP.PROFILES[name] = spec
        for host, floor in (extra.get("floors") or {}).items():
            MP.FLOOR_RT_MS[host] = floor
        for host, mtu in (extra.get("mtu") or {}).items():
            MP.MTU[host] = int(mtu)

    trace = Path(cfg["trace_dir"])
    if not trace.is_absolute():
        trace = (path.parent / trace).resolve()
    if not (trace / "trace_meta.json").exists():
        hint = ""
        if RECIPE_TRACE_SUFFIX in trace.name:
            hint = (
                "\n\n    This is the PAPER RECIPE trace, and it is deliberately not committed: "
                "the repo holds only its device_answers.jsonl.gz and dashcam_instants.jsonl.gz. "
                "run_live2_real.py::_trace regenerates it on demand (the existence check at "
                "`if not (tdir / \"trace.jsonl\").exists()`), and generating it needs the JPEG "
                "frame manifest at /home/pragya/data/live2/jpeg/combined_manifest.jsonl, which "
                "lives on the H100.\n    So this cell can only be resolved where that manifest "
                "is reachable. It is NOT a config error: it is the cell correctly refusing to "
                "run against a workload it cannot reproduce.")
        raise ConfigError("trace_dir %s holds no trace_meta.json%s" % (trace, hint))
    meta = json.loads((trace / "trace_meta.json").read_text())

    # F5: the cell's run_s must match the trace's, or the cell is partial.
    trace_run_s = meta.get("run_s")
    if trace_run_s is not None and abs(float(trace_run_s) - float(cfg["run_s"])) > 1e-6:
        if not cfg.get("allow_short_run"):
            raise ConfigError(
                "run_s %.3f disagrees with the trace's run_s %.3f; a short run silently "
                "truncates the cell. Set \"allow_short_run\": true to accept a PARTIAL cell."
                % (float(cfg["run_s"]), float(trace_run_s)))

    devices: List[Dict[str, Any]] = []
    for d in cfg["devices"]:
        if "device_id" not in d or "host" not in d:
            raise ConfigError("each device needs device_id and host: %r" % d)
        host = d["host"]
        prof = d.get("profile", cfg.get("profile", "unshaped"))
        if prof not in MP.PROFILES:
            raise ConfigError("unknown profile %r (have %s)"
                              % (prof, sorted(MP.PROFILES)))
        if host not in MP.FLOOR_RT_MS:
            raise ConfigError(
                "no measured floor for host %r; a shaping offset cannot be computed without "
                "one. Add it to the profiles_file rather than guessing." % host)
        f = MP.feasible(prof, host)
        if not f["feasible"] and prof != "unshaped":
            raise ConfigError(
                "host %r cannot represent profile %r: floor p99 %.3f ms exceeds target "
                "%.3f ms" % (host, prof, f["floor_p99_ms"], f["target_rtt_ms"]))
        devices.append(dict(device_id=d["device_id"], host=host, role=d.get("role", "real"),
                            profile=prof, iface=d.get("iface", "eth0"),
                            shaping=f, mnwifi=MP.mnwifi_params(prof, host)))

    # GATE: recipe and digest parity against a declared emulated comparator.
    comparator = cfg.get("comparator")
    recipe = dict(RECIPE_FLAGS) if cfg.get("recipe") == "L3_epg_rq30" else cfg.get("recipe")
    parity: Dict[str, Any] = dict(declared_comparator=comparator, recipe=recipe)
    if comparator:
        want_digest = comparator.get("fairness_digest")
        want_trace = comparator.get("trace_dir")
        got_digest = meta.get("fairness_digest")
        parity["comparator_fairness_digest"] = want_digest
        parity["cell_fairness_digest"] = got_digest
        if want_digest and got_digest and want_digest != got_digest:
            raise ConfigError(
                "FAIRNESS DIGEST MISMATCH: this cell's trace carries %s but the declared "
                "comparator %r carries %s. The two are not the same workload, so the cells "
                "are not comparable (D96 (2), D209 parity). Point trace_dir at the "
                "comparator's own trace."
                % (str(got_digest)[:16], comparator.get("cell", "?"), str(want_digest)[:16]))
        if want_trace and RECIPE_TRACE_SUFFIX in str(want_trace) \
                and RECIPE_TRACE_SUFFIX not in str(trace):
            raise ConfigError(
                "RECIPE MISMATCH: the comparator's trace is %r (recipe %s) but this cell's "
                "trace is %r, which carries no %s. _L3_epg_rq30 and the un-suffixed trace are "
                "DIFFERENT WORKLOADS (baseline_matrix_table.py:548): different robot deadline "
                "(3.0 vs 5.0 s), dashcam format (EP-G vs one-frame), upload contract "
                "(per-frame vs batch-30s) and question volume (rq30 vs none)."
                % (str(want_trace).rsplit("/", 1)[-1], RECIPE_TRACE_SUFFIX,
                   str(trace).rsplit("/", 1)[-1], RECIPE_TRACE_SUFFIX))
    if recipe:
        # A declared recipe must agree with the trace it points at, where the trace records it.
        for k, want in recipe.items():
            got = meta.get(k)
            if got is None:
                continue                      # the trace does not record this knob
            if isinstance(want, (int, float)) and not isinstance(want, bool):
                bad = abs(float(got) - float(want)) > 1e-9
            else:
                bad = (got != want)
            if bad:
                raise ConfigError(
                    "RECIPE MISMATCH on %s: cell declares %r but the trace records %r"
                    % (k, want, got))

    resolved = dict(
        name=cfg["name"],
        description=cfg.get("description"),
        config_path=str(path),
        trace_dir=str(trace),
        trace_meta=dict(run_s=meta.get("run_s"), n_devices=meta.get("n_devices"),
                        mode=meta.get("mode"), ratio=meta.get("ratio"),
                        fairness_digest=meta.get("fairness_digest"),
                        dashcam_deadline_s=meta.get("dashcam_deadline_s"),
                        robot_deadline_s=meta.get("robot_deadline_s")),
        frames_root=cfg.get("frames_root"),
        synthetic_frames=bool(cfg.get("synthetic_frames", False)),
        run_s=float(cfg["run_s"]),
        allow_short_run=bool(cfg.get("allow_short_run", False)),
        seed=cfg.get("seed", 0),
        tick_s=float(cfg.get("tick_s", 0.010)),
        drain_s=float(cfg.get("drain_s", 5.0)),
        server=cfg.get("server", {"host": "127.0.0.1", "port": 47900}),
        coordinator=cfg.get("coordinator", "stub"),
        mode=cfg.get("mode", "A"),
        out_dir=cfg.get("out_dir"),
        devices=devices,
        n_real=sum(1 for d in devices if d["role"] == "real"),
        n_emulated=sum(1 for d in devices if d["role"] == "emulated"),
        parity=parity,
    )

    if resolved["mode"] == "B":
        raise ConfigError(
            "mode B (pull) is not implemented: no monitor_offer is sent, so no pull_request "
            "could be answered and the cell would carry no frames")
    if resolved["synthetic_frames"]:
        resolved["measurement_warning"] = (
            "synthetic_frames=true: the wire carries bytes of the recorded LENGTH but not the "
            "real images. Valid for transport tests, NOT a measured cell.")
    return resolved


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Resolve and validate a cell config")
    ap.add_argument("config")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = load(Path(a.config))
    except ConfigError as e:
        print("INVALID CELL CONFIG: %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2, sort_keys=True))
        return 0
    print("cell        %s" % r["name"])
    print("trace       %s" % r["trace_dir"])
    print("run_s       %.1f  (trace %s)" % (r["run_s"], r["trace_meta"]["run_s"]))
    print("devices     %d real + %d emulated" % (r["n_real"], r["n_emulated"]))
    if r.get("measurement_warning"):
        print("WARNING     %s" % r["measurement_warning"])
    print("")
    print("%-10s %-9s %-9s %-16s %9s %9s" % ("device", "host", "role", "profile",
                                             "add_ms", "feasible"))
    for d in r["devices"]:
        print("%-10s %-9s %-9s %-16s %9.3f %9s"
              % (d["device_id"], d["host"], d["role"], d["profile"],
                 d["shaping"].get("add_rtt_ms") or 0.0, d["shaping"]["feasible"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
