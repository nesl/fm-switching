"""Shared style for the StudyFIG1-motivation paper figures (M1-M6).

MobiSys / ACM sigconf single-column width is 3.33 in; double column 7.0 in.
Vector PDF with Type-42 (TrueType) fonts embedded, no Type-3; 300-dpi PNG.
Okabe-Ito colour-blind-safe palette. The same colour means the same thing in
every figure, and every series is also distinguished by marker or hatch so the
figure survives greyscale / colour-blind rendering. No em dashes anywhere.
"""
import json
import pathlib
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIGDIR = ROOT / "figures" / "motivation"
FIGDIR.mkdir(parents=True, exist_ok=True)

# ---- Okabe-Ito palette -----------------------------------------------------
OI = {
    "black": "#000000",
    "orange": "#E69F00",
    "skyblue": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
    "grey": "#999999",
}

# Fixed semantic colours (documented in reports/study_fig1_motivation.md).
# Family A, device vs cloud (M1 only):
C_DEVICE = OI["blue"]
C_CLOUD = OI["vermillion"]
# Family B, rebuild shape (M3a, M3b, M5):
C_ONEGO = OI["vermillion"]      # one-go / mono / cold rebuild
C_PIECE2048 = OI["skyblue"]
C_PIECE1024 = OI["green"]
C_PIECES = OI["green"]          # pieces as one class (M5)
# Family C, readiness tier (M4, M5):
C_COLD = OI["vermillion"]       # a cold rebuild is the one-go/mono action
C_HOST = OI["green"]
C_DISK = OI["blue"]
C_GPUWARM = OI["orange"]
C_WARM = OI["orange"]           # reload / warm as one class (M5)
# Interference, with vs without (M2):
C_WITHOUT = OI["grey"]
C_WITH = OI["vermillion"]
# M3b served-content legend (local to that panel):
C_SERVED_ACTION = OI["blue"]
C_SERVED_BG = OI["orange"]
C_SERVED_BOTH = OI["purple"]
# Single-series workload (M6):
C_WORKLOAD = OI["blue"]

MARK = {
    "onego": "o", "piece2048": "s", "piece1024": "^", "pieces": "s",
    "cold": "o", "host": "^", "disk": "s", "gpuwarm": "D", "warm": "D",
    "device": "o", "cloud": "s",
}
HATCH = {
    "onego": "//", "piece2048": "..", "piece1024": "xx", "pieces": "..",
    "cold": "//", "host": "xx", "disk": "..", "gpuwarm": "",
    "device": "", "cloud": "//",
}

COL1 = 3.33   # single column width (in)
COL2 = 7.0    # double column width (in)


def apply_style():
    plt.rcParams.update({
        "pdf.fonttype": 42,          # embed TrueType, no Type-3
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "font.size": 8,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.0,
        "grid.linewidth": 0.4,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 120,
    })


def boot_ci(values, stat=np.mean, n=2000, seed=0, alpha=0.05):
    """95% bootstrap CI, resampling the items (the unit). Returns (lo, hi)."""
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (np.nan, np.nan)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    reps = np.array([stat(v[i]) for i in idx])
    return float(np.quantile(reps, alpha / 2)), float(np.quantile(reps, 1 - alpha / 2))


def boot_ci_diff(a, b, stat=np.mean, n=2000, seed=0, alpha=0.05):
    """95% bootstrap CI for stat(a)-stat(b) with PAIRED resampling when len equal,
    else independent resampling. Returns (point, lo, hi)."""
    rng = np.random.default_rng(seed)
    a = np.asarray(a, float); b = np.asarray(b, float)
    point = stat(a) - stat(b)
    if len(a) == len(b):
        idx = rng.integers(0, len(a), size=(n, len(a)))
        reps = np.array([stat(a[i]) - stat(b[i]) for i in idx])
    else:
        ia = rng.integers(0, len(a), size=(n, len(a)))
        ib = rng.integers(0, len(b), size=(n, len(b)))
        reps = np.array([stat(a[i]) - stat(b[j]) for i, j in zip(ia, ib)])
    return float(point), float(np.quantile(reps, alpha / 2)), float(np.quantile(reps, 1 - alpha / 2))


def save(fig, name):
    """Save <name>.pdf (vector) and <name>.png (300 dpi)."""
    pdf = FIGDIR / f"{name}.pdf"
    png = FIGDIR / f"{name}.png"
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(png, bbox_inches="tight", pad_inches=0.02, dpi=300)
    plt.close(fig)
    return str(pdf), str(png)


def dump_json(name, payload):
    p = FIGDIR / f"{name}.json"
    with open(p, "w") as f:
        json.dump(payload, f, indent=2)
    return str(p)


def ratio(this, report):
    try:
        return round(float(this) / float(report), 4) if report else None
    except Exception:
        return None
