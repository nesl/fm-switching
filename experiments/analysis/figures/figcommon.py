"""Helpers shared by the fNN_*.py figure scripts (loaders, labels, provenance rows). Written by the figure scripts'
author because paperstyle.py (not edited) lacks them. OFFLINE, CPU only."""
from __future__ import annotations
import re
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as ps  # noqa: E402

FIGDATA = ps.REPO / "reports/figdata"
INK = ps.COLORS["ink"]
CLASS_COLOR = {"covex": ps.COLORS["covex"], "stateful": ps.COLORS["stateful"],
               "stateless": ps.COLORS["stateless"], "device": ps.COLORS["device"]}
DEFAULT_COVEX = ps.COVEX_RUNG3


def plain(s: str) -> str:
    """Plain-text label for the agg preview: drop LaTeX commands and citations."""
    s = re.sub(r"~?\\cite\{[^}]*\}", "", s)
    return s.replace("\\textbf{", "").replace("}", "").replace("~", " ").replace("$\\times$", "x")


def label(arm: str, mode: str, bold: bool = False) -> str:
    return ps.tex_name(arm, bold) if mode == "pgf" else plain(ps.tex_name(arm, bold))


def cls(arm: str) -> str:
    return "device" if arm == ps.DEVICE else ps.arm_class(arm)


def color(arm: str) -> str:
    return CLASS_COLOR[cls(arm)]


def load(name: str, standard: bool = True) -> pd.DataFrame:
    d = pd.read_csv(FIGDATA / name)
    if standard:
        d = d[(d.cond_memory == "1x") & (d.cond_n_devices == 16)]
    return d


def prov_rows(df: pd.DataFrame, extra_cols=()):
    """One provenance dict per distinct (arm, seed) cell used."""
    out = []
    for (arm, seed), g in df.groupby(["arm", "seed"], sort=True):
        r = g.iloc[0]
        d = {"status": ps.arm_status(arm, r["status"]), "figdata_status": r["status"], "arm": arm, "seed": str(seed),
             "run_dir": r["run_dir"], "run_commit": r["run_commit"], "pipeline_sha": r["pipeline_sha"]}
        for c in extra_cols:
            d[c] = r[c]
        out.append(d)
    return out


def row_statuses(rows):
    return [r["status"] for r in rows]


def right_labels(ax, ys, labels, bold_flags, fs=ps.FS_TEXT, x=-0.02):
    """Right-aligned labels at a fixed x (the pgf fix turns these into fixed-edge boxes)."""
    for y, lab, b in zip(ys, labels, bold_flags):
        ax.text(x, y, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=fs, color=INK,
                fontweight="bold" if b else "normal", clip_on=False)


def finish(stem: str, caption_tex_extra: str = ""):
    """Compile the preview PDF and copy it to figures/paper/<stem>.pdf. Returns the pdf path."""
    import shutil
    cap = (ps.OUTDIR / f"{stem}.caption.txt").read_text().strip()
    cap_tex = cap.replace("[", "{[}", 1).replace("%", r"\%")
    pdf = ps.compile_preview(stem, cap_tex)
    shutil.copy(pdf, ps.OUTDIR / f"{stem}.pdf")
    return pdf


def set_no_data_status(stem: str):
    """For NO DATA figures: caption prefix and rows.json status say NO DATA, not FINAL."""
    import json
    c = ps.OUTDIR / f"{stem}.caption.txt"
    c.write_text(c.read_text().replace("[PLACEHOLDER: FINAL", "[PLACEHOLDER: NO DATA", 1))
    j = ps.OUTDIR / f"{stem}.rows.json"
    d = json.loads(j.read_text())
    d["status_tag"] = "NO DATA"
    j.write_text(json.dumps(d, indent=1))
