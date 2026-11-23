#!/usr/bin/env python3
"""D192 one-shot regenerate: build episodic_scores.csv then the two plots and the validation file.

Idempotent, CPU only, read-only on all inputs. Writes only reports/figures/episodic_scores.csv,
reports/figures/episodic_scores_README.md, reports/figures/episodic_{per_type,detection_vs_gpu}.*,
and reports/figures/d192_validation.json. The D192 poll re-runs exactly this when new cells land.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script):
    print(f"=== {script} ===")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script)],
                       cwd=os.path.abspath(os.path.join(HERE, "..", "..", "..")))
    if r.returncode != 0:
        raise SystemExit(f"{script} failed with {r.returncode}")


if __name__ == "__main__":
    run("build_episodic.py")
    run("make_episodic_plots.py")
    print("D192 regenerate complete")
