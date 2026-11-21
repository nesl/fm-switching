#!/usr/bin/env python3
"""Shared infrastructure for the paper figure pipeline (CPU only, committed data only).

Every figure script imports this module so that palette, arm colours, arm order,
statistics (Wilson interval, question-clustered bootstrap) and output handling are
identical across figures. The rules this module enforces come from the figure task:

- Palette is manuscript Figure 1: blue #1f5594 (queries and answers),
  green #14705f (evidence and KV), purple #7b4b8a (devices and control),
  risk #b8641a (risk). Neutrals are greys.
- Same arm colours and the same arm order in every figure (ARMS below).
- Colourblind safety: blue and purple collapse under red-green CVD
  (CIELAB dE 5.2 under deuteranopia and protanopia, measured). Any figure that
  draws blue and purple as distinct series MUST also separate them by linestyle,
  marker or hatch. The ARMS and TIER styles below carry that secondary encoding,
  so identity never rests on hue alone.
- Robot accuracy intervals are clustered by question (CLUSTER = question id).
- No em dashes anywhere in captions or figure text.
- Each figure writes PNG and PDF to figures/paper/ plus a caption file naming its
  claim, its source files and each source file's git hash.
- Evaluation figures are watermarked PILOT until the repeat-trace cells exist.

This module performs no inference and reads no GPU. It only reads committed files.
"""
from __future__ import annotations

import json
import math
import subprocess
import warnings
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "figures" / "paper"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# palette (manuscript Figure 1)
# ---------------------------------------------------------------------------
BLUE = "#1f5594"    # queries and answers
GREEN = "#14705f"   # evidence and KV
PURPLE = "#7b4b8a"  # devices and control
RISK = "#b8641a"    # risk

INK = "#222222"
MUTED = "#666666"
GRID = "#d7d7d7"
GREY = "#8a8a8a"
LIGHT_GREY = "#bdbdbd"


def tint(hex_color: str, frac: float) -> str:
    """Mix a colour toward white by frac in [0,1] (0 keeps it, 1 is white)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = round(r + (255 - r) * frac)
    g = round(g + (255 - g) * frac)
    b = round(b + (255 - b) * frac)
    return f"#{r:02x}{g:02x}{b:02x}"


def shade(hex_color: str, frac: float) -> str:
    """Mix a colour toward black by frac in [0,1]."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return f"#{round(r*(1-frac)):02x}{round(g*(1-frac)):02x}{round(b*(1-frac)):02x}"


# ---------------------------------------------------------------------------
# arm registry: colour, order, and the secondary encoding (linestyle, marker,
# hatch) that keeps blue and purple separable under CVD. One entry per arm; the
# same colour and the same order are used in every figure. Keys are the canonical
# arm names; ALIASES maps the cell/file spellings onto them.
# ---------------------------------------------------------------------------
class Arm:
    def __init__(self, key, label, color, order, ls="-", marker="o", hatch=""):
        self.key = key
        self.label = label
        self.color = color
        self.order = order
        self.ls = ls
        self.marker = marker
        self.hatch = hatch

    def line_kw(self, **extra):
        kw = dict(color=self.color, linestyle=self.ls, marker=self.marker,
                  markersize=5.5, linewidth=2.0, label=self.label)
        kw.update(extra)
        return kw

    def bar_kw(self, **extra):
        kw = dict(color=self.color, hatch=self.hatch, edgecolor="white",
                  linewidth=0.8, label=self.label)
        kw.update(extra)
        return kw


# Proposed policy first (hero, blue, solid). Then warming baseline (green),
# cascade-routing (purple, dashdot + triangle so it stays distinct from blue
# under CVD), eco-llm (risk/orange), then static baselines in grey. Order is the
# legend and plotting order in every figure.
ARMS = {
    "hybrid-F-lhreq-noc3": Arm("hybrid-F-lhreq-noc3", "joint (ours)", BLUE, 0, "-", "o"),
    "warm-all-lru":        Arm("warm-all-lru", "warm-all + LRU", GREEN, 1, "--", "s", "///"),
    "cascade-routing":     Arm("cascade-routing", "cascade-routing", PURPLE, 2, "-.", "^", "xxx"),
    "eco-llm":             Arm("eco-llm", "eco-llm", RISK, 3, ":", "D", "..."),
    "always-local":        Arm("always-local", "always-local", GREY, 4, "-", "v", ""),
    "always-cloud":        Arm("always-cloud", "always-cloud", shade(GREY, 0.35), 5, "--", "P", "\\\\"),
    "no-warm":             Arm("no-warm", "no warming", LIGHT_GREY, 6, ":", "x", ""),
}

ALIASES = {
    "hybrid-F-lhreq-noc3": "hybrid-F-lhreq-noc3",
    "hybrid-f-lhreq-noc3": "hybrid-F-lhreq-noc3",
    "hybrid-F-lhreq": "hybrid-F-lhreq-noc3",
    "hybrid-f-lhreq": "hybrid-F-lhreq-noc3",
    "warm-all-lru": "warm-all-lru",
    "warm-all": "warm-all-lru",
    "cascade-routing": "cascade-routing",
    "eco-llm": "eco-llm",
    "always-local": "always-local",
    "always-cloud": "always-cloud",
    "no-warm": "no-warm",
}


def arm(name: str) -> Arm:
    key = ALIASES.get(name, ALIASES.get(name.lower(), name))
    return ARMS[key]


def arms_in_order(names):
    """Return the given arm names as Arm objects in the registry order."""
    objs = []
    for n in names:
        try:
            objs.append(arm(n))
        except KeyError:
            continue
    return sorted(set(objs), key=lambda a: a.order)


# ---------------------------------------------------------------------------
# tier and representation styling (for M1, M3, M7, M8). Device is purple
# (devices and control); cloud is blue (queries and answers). They are a tight
# CVD pair, so device carries a hatch / marker and cloud does not. Representation
# is shown by tint: recent window is the lighter tint, rich/full history is full
# saturation.
# ---------------------------------------------------------------------------
TIER = {
    "device": dict(color=PURPLE, marker="s", hatch="///", label="device (Orin 4B)"),
    "cloud":  dict(color=BLUE, marker="o", hatch="", label="cloud (32B)"),
}
REP_TINT = {"recent": 0.45, "rich": 0.0, "full": 0.0, "d2": 0.0}


def rep_color(tier_key: str, rep: str) -> str:
    base = TIER[tier_key]["color"]
    return tint(base, REP_TINT.get(rep.lower(), 0.0))


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.959963985):
    """Wilson 95% interval. Returns (p_hat, lo, hi). n==0 gives (nan,0,1)."""
    if n == 0:
        return float("nan"), 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, centre - half), min(1.0, centre + half)


def cluster_bootstrap_ci(items, cluster_key, value_key, nboot=2000, seed=0,
                         agg=np.mean):
    """Bootstrap a mean clustered by cluster_key (question id for robot).

    items: list of dicts. Resamples clusters with replacement, each cluster
    contributing all its rows. Returns (point, lo, hi) at 95 percent.
    """
    rng = np.random.default_rng(seed)
    by = {}
    for it in items:
        by.setdefault(it[cluster_key], []).append(float(it[value_key]))
    clusters = list(by.values())
    if not clusters:
        return float("nan"), float("nan"), float("nan")
    flat = [v for c in clusters for v in c]
    point = float(agg(flat))
    n = len(clusters)
    boots = []
    idx = np.arange(n)
    for _ in range(nboot):
        pick = rng.choice(idx, size=n, replace=True)
        vals = [v for j in pick for v in clusters[j]]
        boots.append(agg(vals))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def pctl(xs, q):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.percentile(xs, q)) if xs else float("nan")


# ---------------------------------------------------------------------------
# page style
# ---------------------------------------------------------------------------
DPI = 300
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "xtick.color": INK,
    "ytick.color": INK,
    "text.color": INK,
    "grid.color": GRID,
    "grid.linewidth": 0.7,
    "legend.frameon": False,
    "legend.fontsize": 9.5,
    "figure.dpi": DPI,
})


def new_fig(w=6.6, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.grid(True, axis="y", zorder=0)
    ax.set_axisbelow(True)
    return fig, ax


def watermark_pilot(ax_or_fig):
    """Stamp a diagonal PILOT watermark across the axes."""
    target = ax_or_fig
    if hasattr(target, "axes") and not hasattr(target, "transAxes"):
        target = target.axes[0]
    target.text(0.5, 0.5, "PILOT", transform=target.transAxes,
                fontsize=58, color="#000000", alpha=0.08, rotation=30,
                ha="center", va="center", zorder=5, fontweight="bold")


# ---------------------------------------------------------------------------
# provenance and output
# ---------------------------------------------------------------------------
def git_hash(path) -> str:
    """Last commit sha (short) that touched path, or 'UNTRACKED'."""
    p = Path(path)
    rel = p.relative_to(REPO) if p.is_absolute() else p
    try:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)],
                                 cwd=REPO, capture_output=True, text=True)
        if tracked.returncode != 0:
            return "UNTRACKED"
        out = subprocess.run(["git", "log", "-1", "--format=%h", "--", str(rel)],
                             cwd=REPO, capture_output=True, text=True)
        return out.stdout.strip() or "NO-COMMIT"
    except Exception as e:  # pragma: no cover
        return f"ERR:{e}"[:40]


def _assert_no_emdash(text: str, where: str):
    for ch in ("—", "–"):
        if ch in text:
            raise ValueError(f"em/en dash in {where}; use a plain hyphen or rephrase")


def save(fig, figid: str, pilot: bool = False):
    if pilot:
        watermark_pilot(fig)
    fig.savefig(OUT_DIR / f"{figid}.png", dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{figid}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  saved figures/paper/{figid}.png + .pdf" + ("  [PILOT]" if pilot else ""))


def write_caption(figid: str, claim: str, sources, pilot: bool = False,
                  notes: str = ""):
    """Write figures/paper/<figid>.caption.txt: one claim, source files + hashes."""
    _assert_no_emdash(claim, f"{figid} claim")
    _assert_no_emdash(notes, f"{figid} notes")
    lines = [f"{figid}", "", "CLAIM:", claim.strip(), "", "SOURCES (committed):"]
    for s in sources:
        lines.append(f"  {s}  @ {git_hash(s)}")
    if pilot:
        lines += ["", "STATUS: PILOT. Drawn from the EP-G pilot cells; to be re-run "
                  "on the repeat-trace cells. Numbers are provisional."]
    if notes:
        lines += ["", "NOTES:", notes.strip()]
    lines.append("")
    txt = "\n".join(lines)
    _assert_no_emdash(txt, f"{figid} caption")
    (OUT_DIR / f"{figid}.caption.txt").write_text(txt)
    print(f"  wrote figures/paper/{figid}.caption.txt")


def load_json(path):
    return json.loads((REPO / path).read_text()) if not Path(path).is_absolute() \
        else json.loads(Path(path).read_text())


def load_jsonl(path):
    p = REPO / path if not Path(path).is_absolute() else Path(path)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
