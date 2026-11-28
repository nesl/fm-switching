"""Helpers shared by f05..f11 only (the shared paperstyle.py is not edited). OFFLINE, CPU only, read-only on cells.

Provides: committed-scorer access (figdata.cell_core on one run dir), figdata CSV loading, arm labels/colours/markers
(PGF labels carry the \\cite key, the PNG gets plain names), right-aligned y labels, and finish() which writes the
paperstyle outputs, compiles the acmart preview, copies the preview PDF to figures/paper/<stem>.pdf and renders the
preview page PNG (150 dpi) under figures/paper/preview/.
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paperstyle as ps  # noqa: E402

os.environ["PATH"] = os.path.expanduser("~/texlive/2026/bin/aarch64-linux") + ":" + os.environ.get("PATH", "")
REPO = ps.REPO
FIGDATA = REPO / "reports/figdata"
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
INK = ps.COLORS["ink"]

# Development-ladder arms that are not paper baselines (display names; all OLD unless in ps.COVEX_DEV).
LADDER_NAMES = {
    "base": "rung 0 base", "rules": "rung 1 rules", "state-uo-c5attr": "rung 2 state",
    "fair-c5attr": "rung 3 fair", "fair-c5attr-rr": "rung 3 fair + rr",
    "covex-v6-fair-final": "COVEX (old: rung 3)",
}


def load_csv(name):
    return list(csv.DictReader(open(FIGDATA / f"{name}.csv")))


def fnum(x):
    return None if x in ("", None) else float(x)


def status_of(arm, row_status="valid"):
    return ps.arm_status(arm, row_status)


def name(arm, mode, bold=False):
    """Axis/legend name. PGF: baseline names carry \\cite; PNG: plain."""
    if arm in ps.BASELINES:
        return ps.tex_name(arm, bold) if mode == "pgf" else ps.display(arm)
    if arm in ps.COVEX_DEV or arm == ps.COVEX_RUNG3:
        return ps.legend_label(arm)
    return LADDER_NAMES.get(arm, arm)


def color(arm):
    if arm in ps.COVEX_DEV or arm == ps.COVEX_RUNG3:
        return ps.COLORS["covex"]
    if arm == ps.DEVICE:
        return ps.COLORS["device"]
    if arm in ps.BASELINES:
        return ps.COLORS[ps.BASELINES[arm][1]]
    return "#6F8FB5"   # non-COVEX development-ladder arms (rungs 0-3): lighter blue, OLD


def right_labels(ax, ys, labels, bold=None, fs=ps.FS_TEXT, x=-0.02):
    """Right-aligned labels in axes-x coordinates (save_figure turns the PGF right anchor into a fixed box)."""
    tr = ax.get_yaxis_transform()
    for i, (y, lab) in enumerate(zip(ys, labels)):
        ax.text(x, y, lab, transform=tr, ha="right", va="center", fontsize=fs, color=INK)


def score_cell(run_dir):
    """Committed scorer (figdata.cell_core -> canon) on one run dir. Returns metrics plus provenance."""
    sys.path.insert(0, str(REPO / "experiments/analysis/figdata"))
    import figdata as F  # noqa: PLC0415
    path = str(Path(run_dir) if Path(run_dir).is_absolute() else RUNS / run_dir)
    m = F.cell_core({"path": path})
    m = {k: v for k, v in m.items() if not k.startswith("_")}
    m["run_dir"] = os.path.relpath(path, REPO)
    m["run_commit"] = F.run_commit(path)
    m["pipeline_sha"] = F.PIPELINE_SHA
    return m


def finish(stem, build, width, height, statuses, rows, body, extra):
    """Write all outputs for one figure and compile + render the preview."""
    caption = ps.save_figure(build, stem, width, height, statuses, rows, body, extra=extra)
    ps.compile_preview(stem, caption)
    shutil.copy(ps.PREVIEW / f"{stem}_preview.pdf", ps.OUTDIR / f"{stem}.pdf")
    subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", str(ps.PREVIEW / f"{stem}_preview.pdf"),
                    str(ps.PREVIEW / f"{stem}_preview_page")], check=True)
    sz = (ps.OUTDIR / f"{stem}.png").stat().st_size
    assert sz < 5_000_000, sz
    return caption
