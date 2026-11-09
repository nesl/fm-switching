#!/usr/bin/env python3
"""StudyB2 status file writer: results/benchmarks/study_b2_status.md (run every 30 min by b2_status_loop.sh).
Stage / next-step notes come from logs/b2_stage.txt (maintained by hand at stage changes). Row counts are read from the
rows files (skipped while a latency step runs, so the isolation check sees no work of ours). Disk floor 20 GB: below it
the status file says so and logs/b2_disk_floor.log gets a line.
"""
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b2_common as C2  # noqa: E402

ROOT = C2.REPO_ROOT
CHAIN_LOG = ROOT / "logs/dseries_chain.log"
QUEUE = ROOT / "logs/b2_queue.txt"
DONE = ROOT / "logs/dseries_done"
OUT = ROOT / "results/benchmarks/study_b2_status.md"
FLOOR_GB = 20.0
PLANNED = {"ovo_rtv": 15486, "streaming_bench": 6700, "herbench": 28901}


def chain_state():
    lines = CHAIN_LOG.read_text(errors="replace").splitlines()[-20000:] if CHAIN_LOG.exists() else []
    cur = None
    for l in lines:
        m = re.match(r"=== DS (\S+ \S+) START (\S+):", l)
        if m:
            cur = (m.group(2), m.group(1))
        if re.match(r"=== DS \S+ \S+ END rc=", l):
            cur = None
    flags = [l for l in lines if re.search(r"FOREIGN|HALT|JOB FAILED|STOP|still failed|repeat control", l)][-6:]
    prog = [l for l in lines if l.startswith("[") and ("B2 " in l)][-3:]
    return cur, flags, prog


def queue_state():
    steps = []
    if QUEUE.exists():
        for l in QUEUE.read_text().splitlines():
            if l.strip() and not l.startswith("#"):
                name = l.split()[0]
                mk = DONE / name
                steps.append((name, mk.read_text().strip()[:40] if mk.exists() else "pending"))
    return steps


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    free = shutil.disk_usage("/home/pragya/data").free / 2**30  # GiB, as df -h
    stage = (ROOT / "logs/b2_stage.txt").read_text().strip() if (ROOT / "logs/b2_stage.txt").exists() else "?"
    cur, flags, prog = chain_state()
    steps = queue_state()
    latency_running = bool(cur and "latency" in cur[0].lower())
    rows_tbl = []
    for ds, planned in PLANNED.items():
        d = ROOT / f"results/benchmarks/study_b2_{ds}"
        for arm in C2.MODELS:
            if latency_running:
                break
            parts = C2.row_parts(d, f"b2_rows_{arm}")
            if not parts:
                continue
            ok = C2.latest_ok(C2.read_rows(d, f"b2_rows_{arm}"))
            main = sum(1 for k in ok if k[0] == "main")
            grey = sum(1 for k in ok if k[0] == "grey")
            mb = sum(p.stat().st_size for p in parts) / 1e6
            rows_tbl.append(f"| {ds} | {arm} | {main} / {planned - 200} | {grey} / 200 | "
                            f"{100 * (main + grey) / planned:.1f} % | {len(parts)} file(s), {mb:.1f} MB |")
    halt = C2.HALT.read_text().strip() if C2.HALT.exists() else None
    if free < FLOOR_GB:
        with open(ROOT / "logs/b2_disk_floor.log", "a") as f:
            f.write(f"{now} free {free:.1f} GB < {FLOOR_GB} GB\n")
    pending = [n for n, s in steps if s == "pending"]
    md = [f"# StudyB2-h100 status", "", f"Updated: {now} (written every 30 min by `experiments/benchmarks/b2_status.py`).", "",
          f"- **Stage:** {stage}",
          f"- **Running step:** {cur[0] + ' (since ' + cur[1] + ')' if cur else 'none'}",
          f"- **Next step:** {next((n for n in pending if not cur or n != cur[0]), '— (queue empty; see stage note)')}",
          f"- **Disk free (data disk):** {free:.1f} GiB (floor {FLOOR_GB:.0f} GiB{' — BELOW FLOOR' if free < FLOOR_GB else ''})",
          f"- **HALT:** {halt or 'none'}", "",
          "## Coverage (error-free rows)", ""]
    if latency_running:
        md += ["(row counts skipped while the latency sample runs, so it sees no work of ours)", ""]
    elif rows_tbl:
        md += ["| dataset | arm | main | grey | coverage | files |", "|---|---|---|---|---|---|"] + rows_tbl + [""]
    else:
        md += ["(no B2 rows yet)", ""]
    md += ["## Queue", "", "| step | state |", "|---|---|"] + [f"| {n} | {s} |" for n, s in steps] + [""]
    md += ["## Latest progress lines", ""] + [f"- `{l[:200]}`" for l in prog] + [""]
    md += ["## Latest stops / flags", ""] + ([f"- `{l[:220]}`" for l in flags] or ["- none"]) + [""]
    OUT.write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
