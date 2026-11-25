#!/usr/bin/env python3
"""D190 one-shot regenerate: rebuild the frontier table then redraw F1 to F5.

Idempotent and CPU only. Run this after new rq30 cells land (the D190 poll re-runs exactly this).
It writes only reports/figures/frontier_data.csv, reports/figures/frontier_data_README.md and
figures/d190/F*.{png,pdf}. It never touches results/ or research/.

    python3 -I figures/d190/run_all.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script):
    print(f"=== {script} ===")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script)],
                       cwd=os.path.abspath(os.path.join(HERE, "..", "..")))
    if r.returncode != 0:
        raise SystemExit(f"{script} failed with {r.returncode}")


if __name__ == "__main__":
    run("build_frontier.py")
    # IMAGE RENDERING SWITCHED OFF (user ruling 2026-11-24, DO NOT PLOT). The pipeline writes data
    # only (CSV, JSON, README); it no longer renders F1 to F5 .png/.pdf. Set D190_RENDER_IMAGES=1
    # to re-enable, only after the user says "plot".
    if os.environ.get("D190_RENDER_IMAGES") == "1":
        run("make_figures.py")
    else:
        print("make_figures.py SKIPPED: image rendering is OFF (DO NOT PLOT); "
              "set D190_RENDER_IMAGES=1 to re-enable after approval")
    print("D190 regenerate complete (data only)")
