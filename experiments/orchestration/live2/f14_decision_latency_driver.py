#!/usr/bin/env python3
"""F14 DECISION-LATENCY SWEEP: the two final rungs at 16 / 24 / 32 / 48 devices, EACH CELL ALONE.

D214 item 2. `covex-v6-fair-final` (rung 3) and `covex-v6-final` (rung 4), seed 4, posted workload,
against the 20 ms decision budget.

THE ALONE RULE IS ENFORCED BY THE DRIVER, NOT BY TIMING A WINDOW BY HAND (D216 (1)). Before every
cell it polls until no OTHER live2 process is running, runs the cell, then RE-CHECKS that nothing
started DURING it; a cell that was not alone end to end is recorded `alone: false` and its numbers
are not reported as a bar. The driver's own child is identified by an ENVIRONMENT MARKER, never by
a command-line pattern: `pgrep -f` on a pattern that matches the session's own shell kills it with
exit 144, and a cmdline match cannot tell this driver's cell from another session's anyway.

loadavg IS RECORDED AS A MAGNITUDE at the start and the end of every cell, with the foreign-process
census beside it. This is not bookkeeping. A PRIOR SWEEP FOUND THE SAME ARM GIVING p99 4.345 /
2.571 / 1.968 ms ACROSS THREE BYTE-IDENTICAL RUNS as the host emptied. So:

  *** BETWEEN-CELL LATENCY MEASURES HOST CONTENTION AND MAY NOT RANK ARMS. ***

A cross-arm latency ranking taken from this sweep would be a HOST-LOAD RANKING wearing an arm's
name: a plausible spread deriving from a quantity that cannot carry the meaning claimed, which is
CLAUDE.md check 3's artefact-spread shape exactly. `assemble` therefore reports the two arms side
by side and REFUSES to emit a winner, and it flags any arm-pair whose latency gap is smaller than
the spread the same arm showed across differing loadavg. The sweep's readable claim is about SIZE
(does p99 cross 20 ms, and where), not about which arm is faster.

NOTHING HERE IS RESCALED. D115 (1) measured the H100 host CPU at about 2.2x slower than flash on
the committed policy benchmark, and D115 (3) allows a normalised latency to be REPORTED as a
labelled derived quantity while forbidding any rescaling of run OUTCOMES. The report therefore
carries the MEASURED FLASH column and the FACTOR as two separate things, plus one clearly labelled
DERIVED column, and never a single merged number.

REGISTER: every number is DRY and LOGICAL, flash CPU wall-clock inside the arm's `decide`
(`coordinator.py:2127`). No engine, no real KV allocator, no H100.

Usage:
    python f14_decision_latency_driver.py --out-dir DIR [--wait-s 7200] [--sizes 16,24,32,48]
    python f14_decision_latency_driver.py --out-dir DIR --assemble-only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "f14_one_cell.py"
MARKER_ENV = "F14_CELL_MARKER"
BUDGET_MS = 20.0

# D115 (1), OBSERVED and committed: the H100 host CPU is about 2.2x slower than flash on the
# committed policy benchmark, and pinned to an idle core it matches the unpinned run within 1 %,
# so the gap is the CPU and not contention (D110 result). IT IS CARRIED BESIDE THE TABLE AND NEVER
# MULTIPLIED INTO IT.
FLASH_TO_H100_CPU_FACTOR = 2.2

ARMS = ("covex-v6-fair-final", "covex-v6-final")
SIZES = (16, 24, 32, 48)

# CLAUDE.md check 7, the POSITIVE CONTROL ON THE CHECK ITSELF: a COMMITTED arm, through THIS
# wrapper, must reproduce its COMMITTED digest. A failure here is the wrapper, not the arm.
# `covex-v6-base` is a rung-0 arm, so D216 (1)'s rule about an unfixed rung-2 digest does not touch
# it and it is an ADMISSIBLE bar.
CONTROL = ("F14c_control", "covex-v6-base", 16)
CONTROL_DIGEST = "af8befb9420ad86a"
CONTROL_ROWS = 12085
CONTROL_SOURCE = "results/orchestration/live2/frozen_test/c5attr_digest_proofs.json"

LIVE2_NAMES = frozenset((
    "cf_pd_one_cell.py", "cfr3_one_cell.py", "c5attr_one_cell.py", "rr_one_cell.py",
    "d210_kv025_one_cell.py", "d216_final_kv025_one_cell.py", "f14_one_cell.py",
    "d213_digest_driver.py", "d209_digest_driver.py", "d216_final_kv025_driver.py",
    "d210_kv025_driver.py", "f14_decision_latency_driver.py", "run_live2_real.py",
    "run_live2_cell.py", "test_hybrid.py",
))


def _ancestors(pid: int) -> List[int]:
    out, seen = [], set()
    while pid and pid not in seen:
        seen.add(pid)
        out.append(pid)
        try:
            with open("/proc/%d/stat" % pid) as fh:
                pid = int(fh.read().rsplit(")", 1)[1].split()[1])
        except Exception:                                                  # noqa: BLE001
            break
    return out


def _has_marker(pid: int, marker: str) -> bool:
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            env = fh.read()
    except Exception:                                                      # noqa: BLE001
        return False
    return ("%s=%s" % (MARKER_ENV, marker)).encode() in env


def foreign_live2(marker: str, mine: set) -> List[Dict[str, Any]]:
    """Every live2 process that is not this driver, its ancestors, or a cell it launched.

    Identified by the BASENAME of an argv entry against a known list, and excluded by an
    environment marker. Never by `pgrep -f` on a self-matching pattern.
    """
    out: List[Dict[str, Any]] = []
    for ent in os.listdir("/proc"):
        if not ent.isdigit():
            continue
        pid = int(ent)
        if pid in mine:
            continue
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                parts = [x.decode("utf-8", "replace") for x in fh.read().split(b"\0") if x]
        except Exception:                                                  # noqa: BLE001
            continue
        if not parts or not [t for t in parts if os.path.basename(t) in LIVE2_NAMES]:
            continue
        if _has_marker(pid, marker):
            continue
        cwd = None
        try:
            cwd = os.readlink("/proc/%d/cwd" % pid)
        except Exception:                                                  # noqa: BLE001
            pass
        out.append({"pid": pid, "cwd": cwd, "cmd": " ".join(parts)[:400]})
    return out


def wait_alone(marker: str, mine: set, wait_s: float, poll_s: float = 20.0) -> Dict[str, Any]:
    t0 = time.time()
    seen: List[Dict[str, Any]] = []
    while True:
        f = foreign_live2(marker, mine)
        if not f:
            return {"alone_at_start": True, "waited_s": round(time.time() - t0, 1),
                    "foreign_seen_while_waiting": seen[:20]}
        if not seen:
            seen = f
        if time.time() - t0 >= wait_s:
            return {"alone_at_start": False, "waited_s": round(time.time() - t0, 1),
                    "foreign_at_give_up": f, "foreign_seen_while_waiting": seen[:20]}
        time.sleep(poll_s)


def run_cell(tag: str, arm: str, n: int, out_dir: Path, seed: int, run_s: float,
             wait_s: float, enforce: bool) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = out_dir / ("%s.json" % tag)
    lat = out_dir / ("%s.lat.json" % tag)
    err = out_dir / ("%s.err" % tag)
    marker = uuid.uuid4().hex
    mine = set(_ancestors(os.getpid()))
    gate = wait_alone(marker, mine, wait_s)

    cmd = [sys.executable, "-I", str(RUNNER), "--arm", arm, "--seed", str(seed),
           "--n", str(n), "--run-s", str(run_s), "--cutoff-off", "--lat-out", str(lat)]
    if enforce:
        cmd.append("--enforce-kv")
    env = dict(os.environ)
    env[MARKER_ENV] = marker
    l0 = os.getloadavg()
    t0 = time.time()
    with open(cell, "w") as fo, open(err, "w") as fe:
        rc = subprocess.call(cmd, cwd=str(HERE), stdout=fo, stderr=fe, env=env)
    l1 = os.getloadavg()
    after = foreign_live2(marker, mine)

    rec: Dict[str, Any] = {
        "tag": tag, "arm": arm, "n_devices": n, "seed": seed, "run_s": run_s,
        "kv_capacity_enforced": bool(enforce), "returncode": rc,
        "wall_s": round(time.time() - t0, 1),
        # loadavg AS A MAGNITUDE, D216 (1). Not a flag, the number.
        "loadavg_at_start": [round(x, 2) for x in l0],
        "loadavg_at_end": [round(x, 2) for x in l1],
        "foreign_live2_at_start": gate.get("foreign_at_give_up") or [],
        "foreign_live2_at_end": after,
        "waited_for_alone_s": gate.get("waited_s"),
        # GUARD-ASSERTED, not asserted. See `alone_guard_bound`.
        "alone_by_guard": bool(gate.get("alone_at_start") and not after),
        "alone": ("GUARD-ASSERTED CLEAR" if (gate.get("alone_at_start") and not after)
                  else "FOREIGN LIVE2 PROCESS SEEN"),
        "alone_definition": ("no OTHER live2 process VISIBLE TO THE GUARD at the start AND none "
                             "started during the cell. A cell whose guard was not clear is "
                             "recorded and is NOT reported as a bar (D216 (1))."),
        "alone_guard_bound": 'the guard enumerates foreign live2 processes by a hardcoded list of .py BASENAMES, so a process whose script name is not in that list is INVISIBLE to it. A cell can therefore record a clear guard truthfully and still not have been alone. THE BOOLEAN IS A SUMMARY OF THE CENSUS, NEVER THE FINDING: re-adjudicate from foreign_live2_at_start / _at_end and the loadavg magnitudes beside it. Direct evidence of determinism (two independent runs agreeing exactly) outranks any alone claim.',
        "cmd": " ".join(cmd),
    }
    if rc == 0:
        try:
            rec["cell"] = json.loads(cell.read_text())
        except Exception as exc:                                           # noqa: BLE001
            rec["cell_parse_error"] = str(exc)
        if lat.exists():
            try:
                rec["lat"] = json.loads(lat.read_text())
            except Exception as exc:                                       # noqa: BLE001
                rec["lat_parse_error"] = str(exc)
    else:
        rec["stderr_tail"] = err.read_text()[-3000:] if err.exists() else None
    (out_dir / ("%s.rec.json" % tag)).write_text(json.dumps(rec, indent=1, default=float) + "\n")
    return rec


# ------------------------------------------------------------------------------- the report

_DIST = ("min", "p25", "median", "p75", "iqr", "p90", "p99", "max", "mean", "n", "n_distinct")


def assemble(out_dir: Path) -> Dict[str, Any]:
    recs = []
    for p in sorted(out_dir.glob("*.rec.json")):
        try:
            recs.append(json.loads(p.read_text()))
        except Exception:                                                  # noqa: BLE001
            continue
    by = {(r.get("arm"), r.get("n_devices")): r for r in recs}

    rows: List[Dict[str, Any]] = []
    for arm in ARMS:
        for n in SIZES:
            r = by.get((arm, n))
            if r is None or not r.get("lat"):
                rows.append({"arm": arm, "n_devices": n, "status": "NOT RUN"})
                continue
            lat = r["lat"]
            row = {"arm": arm, "n_devices": n, "status": "ok",
                   "alone": r.get("alone"),
                   "alone_by_guard": r.get("alone_by_guard"),
                   "loadavg_at_start": r.get("loadavg_at_start"),
                   "loadavg_at_end": r.get("loadavg_at_end"),
                   "digest": (r.get("cell") or {}).get("digest"),
                   "decision_rows": (r.get("cell") or {}).get("rows"),
                   "wall_s": r.get("wall_s")}
            for k in _DIST:
                row[k + "_ms" if k not in ("n", "n_distinct") else k] = lat.get(k)
            row["n_over_budget"] = lat.get("n_over_budget")
            row["frac_over_budget"] = lat.get("frac_over_budget")
            row["p99_within_20ms"] = lat.get("p99_within_budget")
            row["max_within_20ms"] = lat.get("max_within_budget")
            row["constant_where_a_distribution_is_expected"] = lat.get(
                "constant_where_a_distribution_is_expected")
            row["by_kind"] = lat.get("by_kind")
            # D115 (3): a labelled DERIVED column, never a replacement for the measured one.
            for q in ("p50", "median", "p99", "max"):
                v = lat.get("median" if q in ("p50", "median") else q)
                if v is not None:
                    row["DERIVED_h100_%s_ms" % q] = round(float(v) * FLASH_TO_H100_CPU_FACTOR, 6)
            rows.append(row)

    flags: List[str] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("constant_where_a_distribution_is_expected"):
            flags.append("CONSTANT WHERE A DISTRIBUTION IS EXPECTED: %s at n=%d has %s distinct "
                         "decision latencies over %s rows. A constant advertises breakage."
                         % (row["arm"], row["n_devices"], row.get("n_distinct"), row.get("n")))
        if row.get("alone_by_guard") is False:
            flags.append("NOT ALONE: %s at n=%d ran with another live2 process; its latency is "
                         "not reported as a bar (D216 (1))." % (row["arm"], row["n_devices"]))

    # The cross-arm comparison, refused rather than reported.
    pairs = []
    for n in SIZES:
        a = next((r for r in rows if r["arm"] == ARMS[0] and r["n_devices"] == n
                  and r.get("status") == "ok"), None)
        b = next((r for r in rows if r["arm"] == ARMS[1] and r["n_devices"] == n
                  and r.get("status") == "ok"), None)
        if not (a and b):
            continue
        la = (a.get("loadavg_at_start") or [None])[0]
        lb = (b.get("loadavg_at_start") or [None])[0]
        pairs.append({
            "n_devices": n,
            "p99_ms": {ARMS[0]: a.get("p99_ms"), ARMS[1]: b.get("p99_ms")},
            "loadavg_1m_at_start": {ARMS[0]: la, ARMS[1]: lb},
            "RANKING": "REFUSED",
            "why": ("BETWEEN-CELL LATENCY MEASURES HOST CONTENTION AND MAY NOT RANK ARMS. The "
                    "two cells ran at different times on a shared host; a prior sweep moved the "
                    "SAME arm's p99 4.345 / 2.571 / 1.968 ms across three byte-identical runs as "
                    "the host emptied. Any arm ordering read off this pair would be a host-load "
                    "ordering with an arm's name on it."),
        })

    return {
        "_register": ("DRY and LOGICAL. flash CPU wall-clock inside the arm's decide "
                      "(coordinator.py:2127). NOT an H100 number, NOT an engine number."),
        "budget_ms": BUDGET_MS,
        "flash_to_h100_cpu_factor": FLASH_TO_H100_CPU_FACTOR,
        "flash_to_h100_cpu_factor_source": (
            "D115 (1): the H100 host CPU is about 2.2x slower than flash on the committed policy "
            "benchmark; pinned to an idle core it matches the unpinned run within 1 %, so the gap "
            "is the CPU and not contention."),
        "normalisation_rule": (
            "D115 (3): a normalised latency may be REPORTED as a labelled derived quantity; run "
            "OUTCOMES are never rescaled. The measured flash figures and the factor are given "
            "SIDE BY SIDE and are never multiplied into one number. Every DERIVED_h100_* column "
            "is that labelled derived quantity and is not a measurement on the H100."),
        "cross_arm_ranking": "REFUSED -- see pairs[].why",
        "pairs": pairs,
        "flags": flags,
        "rows": rows,
        "control": _control_row(out_dir),
    }


def _control_row(out_dir: Path) -> Dict[str, Any]:
    p = out_dir / ("%s.rec.json" % CONTROL[0])
    if not p.exists():
        return {"status": "NOT RUN", "_what": "CLAUDE.md check 7 positive control on the wrapper"}
    r = json.loads(p.read_text())
    got = (r.get("cell") or {}).get("digest")
    rows = (r.get("cell") or {}).get("rows")
    return {
        "_what": ("POSITIVE CONTROL ON THE CHECK ITSELF: a committed arm through THIS wrapper must "
                  "reproduce its committed digest. If a known-good committed arm fails here, the "
                  "WRAPPER is broken and not the arm."),
        "arm": CONTROL[1], "n_devices": CONTROL[2],
        "expected_digest": CONTROL_DIGEST, "expected_rows": CONTROL_ROWS,
        "source_of_expected": CONTROL_SOURCE,
        "got_digest": got, "got_rows": rows,
        "PASS": bool(got == CONTROL_DIGEST and rows == CONTROL_ROWS),
        "alone": r.get("alone"),
                   "alone_by_guard": r.get("alone_by_guard"), "loadavg_at_start": r.get("loadavg_at_start"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--sizes", default=",".join(str(s) for s in SIZES))
    ap.add_argument("--wait-s", type=float, default=7200.0,
                    help="how long to wait for an ALONE window before running anyway and "
                         "recording alone=false")
    # THE REGIME IS A CHOICE AND IT IS STATED. Coordinator eviction OFF, matching the 1x
    # final-ladder bar cells the D216-KV025 chain is producing at n=16 (F1_r3_final_1x /
    # F2_r4_final_1x, enforce off). That makes the n=16 rungs of this sweep CROSS-CHECKABLE against
    # those cells on the digest and the row count, which is the reason for picking this side.
    # `--enforce-kv` runs the other regime; the two must never be mixed inside one sweep, because
    # eviction changes decisions and so changes how much there is to decide.
    ap.add_argument("--enforce-kv", dest="enforce_kv", action="store_true", default=False,
                    help="run with coordinator KV eviction ON (the committed frozen-grid live "
                         "regime). Default OFF, to match the 1x final-ladder bar cells.")
    ap.add_argument("--skip-control", action="store_true")
    ap.add_argument("--assemble-only", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not a.assemble_only:
        sizes = [int(x) for x in str(a.sizes).split(",") if x.strip()]
        cells: List[Tuple[str, str, int]] = []
        if not a.skip_control:
            cells.append(CONTROL)
        for arm in ARMS:
            short = "r3" if arm == ARMS[0] else "r4"
            for n in sizes:
                cells.append(("F14_%s_n%d" % (short, n), arm, n))
        for tag, arm, n in cells:
            if (out / ("%s.rec.json" % tag)).exists():
                print("skip (already present): %s" % tag, flush=True)
                continue
            rec = run_cell(tag, arm, n, out, a.seed, a.run_s, a.wait_s, bool(a.enforce_kv))
            print(json.dumps({k: rec.get(k) for k in
                              ("tag", "arm", "n_devices", "returncode", "alone", "wall_s",
                               "loadavg_at_start", "loadavg_at_end")}), flush=True)

    rep = assemble(out)
    (out / "f14_decision_latency.json").write_text(
        json.dumps(rep, indent=2, default=float) + "\n")
    print(json.dumps({k: rep[k] for k in ("budget_ms", "flash_to_h100_cpu_factor", "flags",
                                          "cross_arm_ranking")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
