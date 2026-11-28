#!/usr/bin/env python3
"""Shared style for the paper figure set (D334). Every experiments/analysis/figures/fNN_*.py imports this.

OFFLINE, CPU only. Provides: colours, sizes, baseline display names and \\cite keys, class membership (D336),
DATA STATUS rules (FINAL / DEV / OLD / NO DATA), a PGF writer that makes right-aligned labels independent of
citation width, a LaTeX preview compiler (acmart sigconf wrapper, stub bibliography), and provenance/caption writers.

Status vocabulary (never FINAL until the frozen arm on the evaluation seeds exists):
  DEV   today's candidate arms (covex-v6-fair-final-cand-tl, covex-v6-fair-final-cand-tl-sync) and the baselines
        on dev seeds 4-7, when their figdata row is status valid.
  OLD   everything else used as COVEX (the rung 3 covex-v6-fair-final stand-in, earlier rungs, superseded
        candidates), and any row whose figdata status is provisional or superseded.
  NO DATA   the figure has no plotted rows; the axes are drawn with a centred "NO DATA YET: ..." tag.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
OUTDIR = REPO / "figures/paper"
PREVIEW = OUTDIR / "preview"

# ---- sizes (inches) and type ----
SINGLE_IN = 3.33
DOUBLE_IN = 7.0
FS_TEXT = 7.0        # tick, value and legend text
FS_AXLABEL = 7.5     # axis labels

# ---- colours (D334). Device-only purple is a PLACEHOLDER until the user supplies the Figure 3 purple. ----
COLORS = {
    "covex": "#285B91",
    "stateful": "#7A7A7A",
    "stateless": "#C8C8C8",
    "device": "#7A4E9C",   # PLACEHOLDER purple, flagged
    "ink": "#1A1A1A",
    "grid": "#E6E6E6",
    "tag": "#8C8C8C",
}
DEVICE_PURPLE_NOTE = "device-only purple #7A4E9C is a PLACEHOLDER until the user supplies the exact Figure 3 purple"

# ---- arms ----
COVEX_RUNG3 = "covex-v6-fair-final"          # OLD stand-in for COVEX (rung 3)
COVEX_DEV = {"covex-v6-fair-final-cand-tl": "COVEX (dev)",
             "covex-v6-fair-final-cand-tl-sync": "COVEX + S2 (dev)"}
DEVICE = "device-only"

# arm -> (display name, class, \cite key or None). Class per D336 (stateful: KVFlow, LMCache, AttentionStore,
# Mooncake, Warm-all LRU; stateless: the rest). Display names match figures/paper/F01_intro_teaser.
BASELINES = {
    "streamscout": ("StreamScout", "stateless", "streamscout2026"),
    "simplestream": ("SimpleStream", "stateless", "simplestream2026"),
    "llf": ("LLF", "stateless", "mok1983llf"),
    "eco-llm": ("ECO-LLM", "stateless", "ecollm2025"),
    "mooncake": ("Mooncake", "stateful", "mooncake2025"),
    "b7-edf-feasibility": ("EDF + feasibility", "stateless", "liu1973edf"),
    "edf": ("EDF", "stateless", "liu1973edf"),
    "kvflow-prefetch": ("KVFlow", "stateful", "kvflow2025"),
    "always-cloud-fcfs": ("Always-cloud FCFS", "stateless", None),
    "querystream-proactive": ("QueryStream", "stateless", "querystream2026"),
    "attentionstore-prefetch": ("AttentionStore", "stateful", "cachedattention2024"),
    "lmcache": ("LMCache", "stateful", "lmcache2025"),
    "warm-all-lru": ("Warm-all LRU", "stateful", None),
    "confidence-cascade": ("Confidence cascade", "stateless", "chen2024frugalgpt"),
    "device-only": ("On-device only", "device", None),
}
BASELINE_ARMS = [a for a in BASELINES if a != DEVICE]


def display(arm: str) -> str:
    return BASELINES[arm][0] if arm in BASELINES else arm


def arm_class(arm: str) -> str:
    if arm == COVEX_RUNG3 or arm in COVEX_DEV:
        return "covex"
    return BASELINES[arm][1] if arm in BASELINES else "covex"


def cite_key(arm: str):
    return BASELINES[arm][2] if arm in BASELINES else None


def tex_name(arm: str, bold: bool = False) -> str:
    """LaTeX label for an arm, with its \\cite key when it has one (resolves in the paper's bibliography)."""
    name = display(arm) if arm in BASELINES else (COVEX_DEV.get(arm) or "COVEX (old: rung 3)")
    if arm in BASELINES:
        name = name
    key = cite_key(arm)
    body = name if key is None else f"{name}~\\cite{{{key}}}"
    return r"\textbf{" + body + "}" if bold else body


def arm_status(arm: str, row_status: str = "valid") -> str:
    """DEV / OLD per the rules above. row_status is the figdata status column."""
    if row_status in ("provisional", "superseded-by-final", "gap"):
        return "OLD"
    if arm in COVEX_DEV:
        return "DEV"
    if arm == COVEX_RUNG3:
        return "OLD"
    if arm in BASELINES:
        return "DEV"
    return "OLD"


def status_tag(statuses) -> str | None:
    """Corner tag for a figure: OLD DATA if any plotted series is OLD, else DEV DATA, else None (FINAL)."""
    s = set(statuses)
    if "OLD" in s:
        return "OLD DATA"
    if "DEV" in s:
        return "DEV DATA"
    return None


def legend_label(arm: str) -> str:
    """Legend text with status, e.g. 'COVEX (old: rung 3)' or 'COVEX (dev)'."""
    if arm in COVEX_DEV:
        return COVEX_DEV[arm]
    if arm == COVEX_RUNG3:
        return "COVEX (old: rung 3)"
    return display(arm)


# ---- matplotlib setup ----
def rc_setup():
    from matplotlib import rcParams
    rcParams.update({"pgf.texsystem": "pdflatex", "pgf.rcfonts": False, "text.usetex": False,
                     "font.size": FS_TEXT, "pdf.fonttype": 42, "ps.fonttype": 42,
                     "axes.edgecolor": COLORS["ink"], "text.color": COLORS["ink"]})


def new_figure(width_in: float, height_in: float, mode: str):
    """mode 'pgf' or 'agg'. Returns (fig, canvas-attached figure)."""
    from matplotlib.figure import Figure
    if mode == "pgf":
        from matplotlib.backends.backend_pgf import FigureCanvasPgf as Canvas
    else:
        from matplotlib.backends.backend_agg import FigureCanvasAgg as Canvas
    fig = Figure(figsize=(width_in, height_in))
    Canvas(fig)
    return fig


def style_axes(ax, xgrid: bool = True):
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if xgrid:
        ax.xaxis.grid(True, color=COLORS["grid"], lw=0.4)
    ax.tick_params(axis="both", length=0, labelsize=FS_TEXT, colors=COLORS["ink"])


def add_status_tag(fig, statuses, mode: str):
    """Small grey corner tag: OLD DATA / DEV DATA; nothing for FINAL."""
    tag = status_tag(statuses)
    if tag:
        fig.text(0.99, 0.985, tag, ha="right", va="top", fontsize=5.5, color=COLORS["tag"])
    return tag


def no_data(fig, need: str):
    """Empty plot with the axes frame and a centred NO DATA tag."""
    ax = fig.add_axes([0.12, 0.18, 0.84, 0.72])
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.5, 0.5, f"NO DATA YET: {need}", ha="center", va="center", fontsize=FS_TEXT, color=COLORS["tag"],
             wrap=True)
    return ax


def fix_pgf_right_labels(path: Path) -> int:
    """Turn every right-anchored \\pgftext into a zero-width right-aligned box at the same left point.
    The pgf 'right' anchor placed citation labels at different edges in Overleaf; this does not depend on it."""
    src = Path(path).read_text()
    src, n = re.subn(r"\\pgftext\[x=([\d.]+in),y=([\d.]+in),right,\]\{(.*)\}%",
                     lambda m: "\\pgftext[x=%s,y=%s,left,]{\\makebox[0pt][r]{%s}}%%" % (m.group(1), m.group(2), m.group(3)),
                     src)
    Path(path).write_text(src)
    return n


def save_figure(build, stem: str, width_in: float, height_in: float, statuses, rows, caption_body: str,
                extra=None):
    """build(fig, mode) draws into fig. Writes FNN.pgf (fixed-edge labels), FNN.png (agg, 300 dpi),
    FNN.caption.txt (status-prefixed caption), FNN.rows.json (provenance). Returns the caption text."""
    rc_setup()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fig = new_figure(width_in, height_in, "pgf")
    build(fig, "pgf")
    tag = status_tag(statuses)
    if tag:
        add_status_tag(fig, statuses, "pgf")
    pgf = OUTDIR / f"{stem}.pgf"
    fig.savefig(pgf)
    fix_pgf_right_labels(pgf)
    fig2 = new_figure(width_in, height_in, "agg")
    build(fig2, "agg")
    if tag:
        add_status_tag(fig2, statuses, "agg")
    fig2.savefig(OUTDIR / f"{stem}.png", dpi=300)
    prefix = f"[PLACEHOLDER: {tag or 'FINAL'}{', ' + extra if extra else ''}] "
    caption = prefix + caption_body
    (OUTDIR / f"{stem}.caption.txt").write_text(caption + "\n")
    write_rows(stem, rows, statuses, extra)
    return caption


def git_sha() -> str:
    return subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_rows(stem: str, rows, statuses, extra=None):
    """Provenance JSON: every plotted row with its status, arm, seed, run_dir, run_commit, pipeline sha."""
    out = {"figure": stem, "git_sha": git_sha(), "status_tag": status_tag(statuses) or "FINAL",
           "device_color_note": DEVICE_PURPLE_NOTE, "extra": extra, "rows": rows}
    (OUTDIR / f"{stem}.rows.json").write_text(json.dumps(out, indent=1, default=str))


# ---- LaTeX preview (acmart sigconf, stub bibliography) ----
STUB_BIB = "\n".join(
    f"@misc{{{k}, title={{{k}}}, author={{Stub}}, year={{2026}}, note={{stub}}}}"
    for k in ["streamscout2026", "simplestream2026", "querystream2026", "ecollm2025", "mooncake2025",
              "kvflow2025", "lmcache2025", "cachedattention2024", "liu1973edf", "mok1983llf",
              "chen2024frugalgpt"]
) + "\n"

PREVIEW_TEX = r"""\documentclass[sigconf]{acmart}
\usepackage{pgf}
\usepackage[T1]{fontenc}
\usepackage{libertine}
\settopmatter{printacmref=false}
\pagestyle{empty}
\begin{document}
{\fontfamily{LinuxBiolinumT}\selectfont
\begin{figure}[t]
  \centering
  \input{%(pgf)s}
  \caption{%(caption)s}
  \label{fig:%(stem)s}
\end{figure}
}
\bibliographystyle{ACM-Reference-Format}
\bibliography{refs_stub}
\end{document}
"""


def compile_preview(stem: str, caption_tex: str) -> Path:
    """Compile PREVIEW/<stem>.pdf from the PGF through the acmart wrapper. Needs pdflatex and bibtex on PATH."""
    PREVIEW.mkdir(parents=True, exist_ok=True)
    (PREVIEW / "refs_stub.bib").write_text(STUB_BIB)
    tex = PREVIEW_TEX % {"pgf": f"../{stem}.pgf", "caption": caption_tex, "stem": stem}
    (PREVIEW / f"{stem}_preview.tex").write_text(tex)
    for cmd in (["pdflatex", "-interaction=nonstopmode", f"{stem}_preview.tex"],
                ["bibtex", f"{stem}_preview"],
                ["pdflatex", "-interaction=nonstopmode", f"{stem}_preview.tex"],
                ["pdflatex", "-interaction=nonstopmode", f"{stem}_preview.tex"]):
        subprocess.run(cmd, cwd=PREVIEW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    pdf = PREVIEW / f"{stem}_preview.pdf"
    if not pdf.exists():
        raise RuntimeError(f"preview did not compile: see {PREVIEW / (stem + '_preview.log')}")
    return pdf
