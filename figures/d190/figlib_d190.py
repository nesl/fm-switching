#!/usr/bin/env python3
"""Shared style and arm registry for the D190 off-critical-path figures.

Colour-blind-safe by construction: colours are drawn from the Okabe-Ito and Tol qualitative
palettes, and every arm also carries a distinct MARKER and (for lines) a distinct DASH so identity
never rests on colour alone. The same arm takes the same colour, marker and order in every figure.
No em dashes in any emitted text.
"""
from __future__ import annotations

import csv
import os

# Deterministic output: fix the PDF CreationDate (matplotlib reads SOURCE_DATE_EPOCH) so a
# regenerate with unchanged data produces byte-identical files and the D190 poll does not create
# no-op commits. The value is an arbitrary fixed epoch, not a real build time.
os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSV = os.path.join(REPO, "reports/figures/frontier_data.csv")
FIGDIR = os.path.join(REPO, "figures/d190")

# Okabe-Ito + two Tol teals, all CVD-safe.
C = {
    "black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73",
    "blue": "#0072B2", "vermilion": "#D55E00", "purple": "#CC79A7", "grey": "#9A9A9A",
    "teal": "#44AA99", "sand": "#DDCC77",
}

# arm_family -> style. cls groups arms for legends and for the F1 "one family" labelling.
ARMS = {
    "base":             dict(color=C["blue"],      marker="o", ls="-",  label="base (noc3)",        cls="joint",   order=0),
    "joint-c3":         dict(color=C["sky"],       marker="s", ls="-",  label="joint (with C3)",    cls="joint",   order=1),
    "rules":            dict(color=C["purple"],    marker="v", ls="--", label="rules",              cls="ladder",  order=2),
    "v5-rules-old":     dict(color=C["purple"],    marker="p", ls=":",  label="rules (v5 old)",     cls="ladder",  order=3),
    "state":            dict(color=C["teal"],      marker="<", ls="--", label="state (plain)",      cls="ladder",  order=4),
    "state-uo":         dict(color=C["green"],     marker="D", ls="-",  label="state-uo (rung2)",   cls="ladder",  order=5),
    "state-uo-c5attr":  dict(color=C["vermilion"], marker="P", ls="-.", label="state-uo +C5",       cls="c5",      order=6),
    "fair-c5attr":      dict(color=C["vermilion"], marker="X", ls="-.", label="fair +C5",           cls="c5",      order=7),
    "fair-c5attr-gain0":dict(color=C["vermilion"], marker="*", ls="-.", label="fair +C5 gain0",     cls="c5",      order=8),
    "shares":           dict(color=C["orange"],    marker="h", ls="-",  label="state-shares",       cls="shares",  order=9),
    "shares-r1":        dict(color=C["orange"],    marker="H", ls="--", label="state-shares r1",    cls="shares",  order=10),
    "shares-r2":        dict(color=C["sand"],      marker="8", ls="--", label="state-shares r2",    cls="shares",  order=11),
}
# every baseline family shares one neutral style; markers separate them where several are shown.
BASELINES = ["edf", "llf", "b7-edf-feasibility", "always-cloud-fcfs", "mooncake",
             "attentionstore-prefetch", "lmcache", "kvflow-prefetch", "simplestream",
             "streamscout", "querystream-proactive", "eco-llm", "confidence-cascade",
             "warm-all-lru", "r3-streaming"]
BASELINE_MARKERS = ["o", "s", "^", "v", "D", "P", "X", "*", "h", "<", ">", "p", "d", "H", "8"]

C5_FAMILY = {"state-uo-c5attr", "fair-c5attr", "fair-c5attr-gain0"}


def style(fam, i_baseline=0):
    """Stable style per family. Baselines get a marker and order fixed by their position in the
    BASELINES list, so the result does not depend on plotting order or on hash randomisation.
    The i_baseline argument is kept for call-site compatibility and ignored.
    """
    if fam in ARMS:
        return dict(ARMS[fam])
    idx = BASELINES.index(fam) if fam in BASELINES else len(BASELINES)
    mk = BASELINE_MARKERS[idx % len(BASELINE_MARKERS)]
    return dict(color=C["grey"], marker=mk, ls=":", label=fam, cls="baseline", order=100 + idx)


def rcparams():
    plt.rcParams.update({
        "figure.dpi": 200, "savefig.dpi": 200,
        "font.size": 9.5, "axes.titlesize": 10.5, "axes.labelsize": 9.5,
        "legend.fontsize": 7.6, "xtick.labelsize": 8.2, "ytick.labelsize": 8.2,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "savefig.bbox": "tight", "figure.autolayout": False,
    })


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(memory=None, scorable_only=True):
    """Rows as dicts with numeric fields coerced. memory in {'1x','0.5x',None}."""
    out = []
    for r in csv.DictReader(open(CSV)):
        if scorable_only and r["scorable"] != "True":
            continue
        if memory is not None and r["memory"] != memory:
            continue
        rr = dict(r)
        for k in ("seed", "robot_pool_n", "robot_on_time", "robot_by_deadline_n",
                  "ss_pool_n", "alert_n_instants", "alert_on_time", "late_alert_frames",
                  "n_episodes"):
            rr[k] = _num(r.get(k))
        for k in ("robot_on_time_frac", "retention_rung2_gain_over_base", "robot_by_deadline_acc",
                  "device_only_robot_floor", "assist_within2s_pooled", "assist_perdev_min",
                  "alert_mean_per_episode_attain", "alert_frac_episodes_ge_0p25",
                  "alert_pooled_attain"):
            rr[k] = _num(r.get(k))
        out.append(rr)
    return out


def by_family(rows):
    d = {}
    for r in rows:
        d.setdefault(r["arm_family"], []).append(r)
    return d


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def save(fig, figid):
    rcparams  # noqa  (ensure referenced)
    png = os.path.join(FIGDIR, figid + ".png")
    pdf = os.path.join(FIGDIR, figid + ".pdf")
    fig.savefig(png, metadata={"Software": None})
    fig.savefig(pdf, metadata={"Creator": None, "Producer": None})
    plt.close(fig)
    return png, pdf
