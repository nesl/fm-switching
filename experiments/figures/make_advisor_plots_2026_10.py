#!/usr/bin/env python3
"""
Advisor plots for FM-switching, 2026-10-23.

CPU-only, no GPU, no new inference. Reads committed result files only and writes
PDF + PNG per slide to figures/advisor_2026_10_23/, plus numbers.md listing every
plotted number with its source file and the report value it should match.

Every number here is computed from the result files. Report values are quoted for
cross-checking only and are never substituted for a computed value.
"""

import json
import gzip
import math
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "figures" / "advisor_2026_10_23"
OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO / "experiments" / "sember"))
sys.path.insert(0, str(REPO / "experiments" / "erqa"))

# S-EMBER CIs: the same video-clustered bootstrap used by the result being replicated.
from study_o_q4_analyze import clustered_bootstrap, did_with_ci  # noqa: E402
import r4_analyse as R4  # noqa: E402

NBOOT = 2000
SEED = 0

# ── palette (IBM colorblind-safe), matching make_advisor_plots.py ─────────────
C = dict(
    blue="#648FFF",
    violet="#785EF0",
    red="#DC267F",
    orange="#FE6100",
    yellow="#FFB000",
    green="#117733",
    teal="#44AA99",
    grey="#999999",
    light_grey="#CCCCCC",
    dark="#222222",
)

DEVICE_C = C["blue"]
CLOUD_C = C["red"]

SLIDE_SIZE = (10, 6)
DPI = 300
FONT_LABEL = 14
FONT_TICK = 12
FONT_ANNOT = 11

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.labelsize": FONT_LABEL,
    "xtick.labelsize": FONT_TICK,
    "ytick.labelsize": FONT_TICK,
    "figure.dpi": DPI,
})


def save(fig, stem):
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {stem}.pdf + {stem}.png")


# ─────────────────────────────────────────────────────────────────────────────
# numbers registry
# ─────────────────────────────────────────────────────────────────────────────
NUMBERS = []
MISMATCHES = []
NOTES = []
TOL_PP = 0.1


def rec(slide, quantity, value, source, report=None, report_value=None,
        unit="pp", tol=TOL_PP, note=""):
    """Record one plotted number and cross-check it against its report value."""
    status = "—"
    delta = ""
    if report_value is not None and value is not None:
        d = value - report_value
        delta = f"{d:+.2f}"
        if abs(d) > tol:
            status = "**MISMATCH**"
            MISMATCHES.append((slide, quantity, value, report_value, d, report, note))
        else:
            status = "match"
    NUMBERS.append(dict(slide=slide, quantity=quantity, value=value, unit=unit,
                        source=source, report=report or "—",
                        report_value=report_value, delta=delta, status=status,
                        note=note))
    return value


def note(slide, text):
    NOTES.append((slide, text))


# ─────────────────────────────────────────────────────────────────────────────
# statistics
# ─────────────────────────────────────────────────────────────────────────────
def wilson(k, n, z=1.959963985):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def acc(ok):
    ok = np.asarray(ok, bool)
    return 100.0 * ok.mean() if len(ok) else float("nan")


def sember_diff(a, b, vids, nboot=NBOOT, seed=SEED):
    """b - a in pp, video-clustered bootstrap CI (S-EMBER convention)."""
    a = np.asarray(a, bool)
    b = np.asarray(b, bool)
    vids = np.asarray(vids)

    def fn(idx):
        return float(b[idx].mean() - a[idx].mean())

    obs = fn(np.arange(len(a)))
    boot = clustered_bootstrap(vids, fn, nboot=nboot, seed=seed)
    boot = boot[np.isfinite(boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return 100 * obs, 100 * lo, 100 * hi, 100 * float(boot.std(ddof=1))


def paired_diff(a, b, nboot=NBOOT, seed=SEED):
    """b - a in pp, paired question-level bootstrap (ERQA / MV-RoboBench)."""
    a = np.asarray(a, bool)
    b = np.asarray(b, bool)
    n = len(a)
    rng = np.random.default_rng(seed)
    obs = float(b.mean() - a.mean())
    boot = np.empty(nboot)
    for i in range(nboot):
        idx = rng.integers(0, n, n)
        boot[i] = b[idx].mean() - a[idx].mean()
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return 100 * obs, 100 * lo, 100 * hi, 100 * float(boot.std(ddof=1))


def mcnemar_counts(a, b):
    """b over a: (b_count, c_count) = (a wrong & b right, a right & b wrong)."""
    a = np.asarray(a, bool)
    b = np.asarray(b, bool)
    return int((~a & b).sum()), int((a & ~b).sum())


# ─────────────────────────────────────────────────────────────────────────────
# loaders
# ─────────────────────────────────────────────────────────────────────────────
def jl(path):
    p = REPO / path
    op = gzip.open if str(p).endswith(".gz") else open
    with op(p, "rt") as f:
        return [json.loads(line) for line in f]


def js(path):
    return json.load(open(REPO / path))


_CACHE = {}


def cached(key, fn):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


# --- device tier (A6000, llama.cpp F16) --------------------------------------
def device_cell(cell):
    """accuracy_C*.jsonl keyed by question_id."""
    return cached(f"dev_{cell}", lambda: {
        r["question_id"]: r for r in jl(f"results/device/accuracy_{cell}.jsonl")})


# --- cloud S-EMBER (H100, vLLM) ----------------------------------------------
def sember_cloud(study, path):
    def _load():
        out = defaultdict(dict)
        for r in jl(path):
            if r["mode"] != "batched":
                continue
            out[r["cell"]][r["question_id"]] = r
        return dict(out)
    return cached(f"cloud_{study}", _load)


def r1():
    return sember_cloud("r1", "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")


def rh1():
    return sember_cloud("rh1", "results/sember/study_rh1/study_rh1_requests_h100nvl.jsonl.gz")


def rh3():
    return sember_cloud("rh3", "results/sember/study_rh3/study_rh3_requests_h100nvl.jsonl.gz")


def rh4():
    return sember_cloud("rh4", "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz")


# --- Orin device latency (llama.cpp F16 / Q8_0) -------------------------------
def orin_latency(tag):
    return cached(f"orin_{tag}", lambda: jl(f"results/device/latency_sember_{tag}.jsonl"))


def orin_tokens(tag):
    return cached(f"orintok_{tag}", lambda: jl(f"results/device/tokens_{tag}.jsonl.gz"))


# --- ERQA / MV-RoboBench ------------------------------------------------------
def r4_rows(workload, arm):
    """Device 4B signal rows (A6000, HF sdpa). OOM rows excluded, as r4_analyse does."""
    def _load():
        rows = jl(f"results/erqa/r4_signals/r4_{workload}_{arm}.jsonl")
        return [r for r in rows if not r.get("oom")]
    return cached(f"r4_{workload}_{arm}", _load)


def study_r_arm(arm):
    """ERQA 32B (h100nvl, HF flash_attention_2) keyed by question_id."""
    return cached(f"sr_{arm}", lambda: {
        t["question_id"]: t
        for t in jl("results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl")
        if t["arm"] == arm})


def study_s2_arm(arm):
    """MV-RoboBench 32B (h100nvl, HF flash_attention_2) keyed by path."""
    return cached(f"ss2_{arm}", lambda: {
        t["path"]: t
        for t in jl("results/erqa/study_s2/study_s2_trials_h100nvl_fa2.jsonl")
        if t["arm"] == arm})


def study_q_arm(arm):
    """ERQA 8B (A6000, HF sdpa) keyed by question_id. arm D = 8B-I, arm C = 8B-T."""
    return cached(f"sq_{arm}", lambda: {
        t["question_id"]: t
        for t in jl("results/erqa/study_q/study_q_trials.jsonl")
        if t["arm"] == arm and t.get("pass_index", 1) in (None, 1)})


# ─────────────────────────────────────────────────────────────────────────────
# alignment helpers
# ─────────────────────────────────────────────────────────────────────────────
def common_ids(*dicts):
    ids = set(dicts[0])
    for d in dicts[1:]:
        ids &= set(d)
    return sorted(ids)


def oks(d, ids):
    return np.array([bool(d[i]["correct"]) for i in ids], bool)


def vids_of(d, ids):
    return np.array([d[i]["video_id"] for i in ids])


def preds(d, ids, key):
    return np.array([d[i].get(key) for i in ids], dtype=object)


def erqa_ok(d, ids):
    return np.array([bool(d[i]["correct"]) for i in ids], bool)


# ─────────────────────────────────────────────────────────────────────────────
# forest-plot helper: paired differences with CIs
# ─────────────────────────────────────────────────────────────────────────────
def forest(ax, rows, xlabel, title=None, colors=None):
    """rows: list of (label, diff, lo, hi). Drawn top-to-bottom."""
    ys = np.arange(len(rows))[::-1]
    for y, (lab, d, lo, hi) in zip(ys, rows):
        col = (colors or {}).get(lab, C["dark"])
        excl = (lo > 0) or (hi < 0)
        ax.plot([lo, hi], [y, y], color=col, lw=2.4,
                solid_capstyle="round", alpha=1.0 if excl else 0.55)
        ax.plot([d], [y], "o", color=col, ms=9 if excl else 7,
                mfc=col if excl else "white", mew=2, zorder=3)
    ax.axvline(0, color=C["grey"], lw=1, ls="--", zorder=0)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=FONT_ANNOT)
    ax.set_xlabel(xlabel)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    if title:
        ax.set_title(title, fontsize=FONT_LABEL, fontweight="bold", loc="left")


def table_axes(ax, col_labels, rows, col_widths=None, header_color=C["dark"],
               fontsize=10, row_colors=None):
    """Render a simple text table on a bare axes."""
    ax.axis("off")
    ncol = len(col_labels)
    w = col_widths or [1.0 / ncol] * ncol
    xs = np.cumsum([0] + list(w))[:-1]
    nrow = len(rows)
    ytop = 1.0
    dy = 1.0 / (nrow + 1.6)
    for ci, (x, lab) in enumerate(zip(xs, col_labels)):
        ha = "left" if ci == 0 else "center"
        ax.text(x if ci == 0 else x + w[ci] / 2, ytop, lab, ha=ha, va="bottom",
                fontsize=fontsize, fontweight="bold", color=header_color)
    ax.plot([0, 1], [ytop - 0.12 * dy, ytop - 0.12 * dy], color=C["light_grey"], lw=1)
    for ri, row in enumerate(rows):
        y = ytop - (ri + 1) * dy
        col = (row_colors or {}).get(ri, C["dark"])
        for ci, (x, cell) in enumerate(zip(xs, row)):
            ha = "left" if ci == 0 else "center"
            ax.text(x if ci == 0 else x + w[ci] / 2, y, str(cell), ha=ha, va="center",
                    fontsize=fontsize, color=col)
    ax.set_xlim(0, 1)
    ax.set_ylim(ytop - (nrow + 1) * dy, ytop + 1.2 * dy)


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 1 — does the cloud model improve accuracy?
# ─────────────────────────────────────────────────────────────────────────────
def slide1():
    print("S1 device vs cloud")
    S = "S1"
    table_rows = []
    forest_rows = []

    # ---------- S-EMBER, n = 845 ----------
    C1, C3 = device_cell("C1"), device_cell("C3")
    K = r1()
    ids = common_ids(C1, C3, K["K1"], K["K2"])
    vids = vids_of(C1, ids)
    d_i, d_t = oks(C1, ids), oks(C3, ids)
    c_i, c_t = oks(K["K1"], ids), oks(K["K2"], ids)

    for lab, ok, src, rep, repv in [
        ("S-EMBER  device 4B-I (A6000 llama.cpp F16, DEV-RECENT)", d_i,
         "results/device/accuracy_C1.jsonl", "device_tier_accuracy_llamacpp.md §A", 31.5),
        ("S-EMBER  device 4B-T (A6000 llama.cpp F16, DEV-RECENT)", d_t,
         "results/device/accuracy_C3.jsonl", "device_tier_accuracy_llamacpp.md §A", 33.4),
        ("S-EMBER  cloud 32B-I RICH, K1 (H100 vLLM)", c_i,
         "study_r1_requests_h100nvl.jsonl.gz cell=K1", "study_r1_cloud32b_sember.md §Accuracy", 39.53),
        ("S-EMBER  cloud 32B-T RICH, K2 (H100 vLLM)", c_t,
         "study_r1_requests_h100nvl.jsonl.gz cell=K2", "study_r1_cloud32b_sember.md §Accuracy", 33.85),
    ]:
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(ok))
        rec(S, f"accuracy — {lab}", round(a, 2), src, rep, repv)
        table_rows.append((lab, len(ok), f"{a:.1f}", f"[{lo:.1f}, {hi:.1f}]"))

    for lab, a_, b_, rep, repv in [
        ("S-EMBER  32B-I RICH − 4B-I DEV-RECENT", d_i, c_i,
         "study_r1_cloud32b_sember.md CLOUD HELPS (vs StudyO 4B-I; different device run)", None),
        ("S-EMBER  32B-T RICH − 4B-T DEV-RECENT", d_t, c_t, None, None),
    ]:
        diff, lo, hi, se = sember_diff(a_, b_, vids)
        rec(S, f"paired diff — {lab}", round(diff, 2),
            "accuracy_C*.jsonl + study_r1_requests_h100nvl.jsonl.gz", rep, repv)
        rec(S, f"paired diff CI — {lab}", None, "video-clustered bootstrap 2000 seed 0",
            note=f"[{lo:+.2f}, {hi:+.2f}] SE {se:.2f}")
        forest_rows.append((lab, diff, lo, hi))

    # ---------- S-EMBER, Orin 120-question sample ----------
    o_i = {r["question_id"]: r for r in orin_latency("8bi_f16_F16")}
    o_t = {r["question_id"]: r for r in orin_latency("8bt_f16_F16")}
    ids120 = common_ids(o_i, o_t, C1, C3, K["K1"])
    v120 = vids_of(C1, ids120)
    s120 = {
        "8B-I (Orin llama.cpp F16)": np.array([bool(o_i[i]["correct"]) for i in ids120]),
        "8B-T (Orin llama.cpp F16)": np.array([bool(o_t[i]["correct"]) for i in ids120]),
        "4B-I (A6000 llama.cpp F16)": oks(C1, ids120),
        "4B-T (A6000 llama.cpp F16)": oks(C3, ids120),
        "32B-I RICH K1 (H100 vLLM)": oks(K["K1"], ids120),
    }
    rep120 = {"8B-I (Orin llama.cpp F16)": 35.0, "8B-T (Orin llama.cpp F16)": 37.0,
              "4B-I (A6000 llama.cpp F16)": 31.7, "4B-T (A6000 llama.cpp F16)": 36.7}
    rows120 = []
    for lab, ok in s120.items():
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(ok))
        rec(S, f"accuracy n=120 — {lab}", round(a, 2),
            "latency_sember_8b*_f16_F16.jsonl / accuracy_C{1,3}.jsonl / R1 K1",
            "device_latency_sember.md (8B, rounded to 1%) · device_tier_accuracy_llamacpp.md §E (4B)",
            rep120.get(lab), tol=0.6 if lab.startswith("8B") else TOL_PP,
            note="report rounds 8B accuracy to whole %" if lab.startswith("8B") else "")
        rows120.append((lab, len(ok), f"{a:.1f}", f"[{lo:.1f}, {hi:.1f}]"))

    d120, l120, h120, _ = sember_diff(s120["4B-I (A6000 llama.cpp F16)"],
                                      s120["32B-I RICH K1 (H100 vLLM)"], v120)
    rec(S, "paired diff n=120 — 32B-I K1 − 4B-I DEV-RECENT", round(d120, 2),
        "R1 K1 + accuracy_C1.jsonl", note=f"[{l120:+.2f}, {h120:+.2f}]")
    d8, l8, h8, _ = sember_diff(s120["4B-I (A6000 llama.cpp F16)"],
                                s120["8B-I (Orin llama.cpp F16)"], v120)
    rec(S, "paired diff n=120 — 8B-I (Orin) − 4B-I (A6000)", round(d8, 2),
        "latency_sember_8bi + accuracy_C1.jsonl",
        note=f"[{l8:+.2f}, {h8:+.2f}]; different hosts, same DEV-RECENT construction")

    # ---------- ERQA, n = 400 ----------
    erqa_rows, erqa_forest = erqa_panel(S, table_rows, forest_rows)
    # ---------- MV-RoboBench, n = 401 ----------
    mv_rows, mv_forest = mvrobo_panel(S, table_rows, forest_rows)

    # ---------- figure ----------
    sep = ("— the Orin's own 120-question S-EMBER sample, every row on the same questions —",
           "", "", "")
    all_rows = table_rows + [sep] + rows120
    fig = plt.figure(figsize=(17.5, 9.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.18, 1.0], hspace=0.22)
    ax_t = fig.add_subplot(gs[0])
    table_axes(
        ax_t,
        ["cell  (model · construction · backend · hardware)", "n", "acc %", "Wilson 95%"],
        all_rows,
        col_widths=[0.62, 0.08, 0.12, 0.18], fontsize=9.6,
        row_colors={i: (C["grey"] if r is sep else
                        (CLOUD_C if "32B" in r[0] else DEVICE_C))
                    for i, r in enumerate(all_rows)},
    )
    ax_t.set_title("Device (Orin-class 4B/8B) vs cloud (H100 32B) — accuracy per workload\n"
                   "upper block n = 845 / 400 / 401; lower block = the Orin's 120-question "
                   "S-EMBER sample only",
                   fontsize=FONT_LABEL, fontweight="bold", loc="left")

    ax_f = fig.add_subplot(gs[1])
    allf = forest_rows
    forest(ax_f, allf, "cloud − device  (pp, paired)",
           title="Paired differences, cloud minus device  "
                 "(S-EMBER: video-clustered bootstrap 2,000 / seed 0;  "
                 "ERQA & MV-RoboBench: paired question-level bootstrap 2,000 / seed 0)",
           colors={r[0]: CLOUD_C for r in allf})
    ax_f.text(0.995, 0.02, "filled marker = 95% CI excludes 0", transform=ax_f.transAxes,
              ha="right", va="bottom", fontsize=9, color=C["grey"], style="italic")
    save(fig, "s1_device_vs_cloud_accuracy")


def erqa_panel(S, table_rows, forest_rows):
    """ERQA rows for slide 1. Device 4B/8B = A6000 HF sdpa; cloud 32B = H100 HF fa2."""
    di = r4_rows("erqa", "instruct")
    dt = r4_rows("erqa", "thinking")
    di_d = {r["qid"]: r for r in di}
    dt_d = {r["qid"]: r for r in dt}
    cC, cD = study_r_arm("C"), study_r_arm("D")
    q8i, q8t = study_q_arm("D"), study_q_arm("C")
    ids = common_ids(di_d, dt_d, cC, cD, q8i, q8t)

    series = [
        ("ERQA  device 4B-I (A6000 HF sdpa)", erqa_ok(di_d, ids),
         "results/erqa/r4_signals/r4_erqa_instruct.jsonl", "r4_device_signals_prep.md §Escalation", 42.0),
        ("ERQA  device 4B-T (A6000 HF sdpa)", erqa_ok(dt_d, ids),
         "results/erqa/r4_signals/r4_erqa_thinking.jsonl", "r4_device_signals_prep.md §Escalation", 45.0),
        ("ERQA  device 8B-I, StudyQ arm D (A6000 HF sdpa)", erqa_ok(q8i, ids),
         "results/erqa/study_q/study_q_trials.jsonl arm=D", "study_q_retry_vs_scale_erqa.md", 42.5),
        ("ERQA  device 8B-T, StudyQ arm C (A6000 HF sdpa)", erqa_ok(q8t, ids),
         "results/erqa/study_q/study_q_trials.jsonl arm=C", "study_q_retry_vs_scale_erqa.md", 43.5),
        ("ERQA  cloud 32B-I, StudyR arm C (H100 HF fa2)", erqa_ok(cC, ids),
         "study_r_trials_h100nvl_fa2.jsonl arm=C", "study_r_device_vs_cloud.md §Flash-attn", 46.8),
        ("ERQA  cloud 32B-T, StudyR arm D (H100 HF fa2)", erqa_ok(cD, ids),
         "study_r_trials_h100nvl_fa2.jsonl arm=D", "study_r_device_vs_cloud.md §Flash-attn", 48.8),
    ]
    vals = {}
    for lab, ok, src, rep, repv in series:
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(ok))
        rec(S, f"accuracy — {lab}", round(a, 2), src, rep, repv)
        table_rows.append((lab, len(ok), f"{a:.1f}", f"[{lo:.1f}, {hi:.1f}]"))
        vals[lab] = ok
    note(S, "ERQA 8B **is** available (StudyQ arms D = 8B-Instruct and C = 8B-Thinking, "
            "A6000 HF sdpa) and is included. MV-RoboBench has no 8B arm in the repository.")

    for lab, a_, b_ in [
        ("ERQA  32B-I (fa2) − 4B-I (sdpa)", vals[series[0][0]], vals[series[4][0]]),
        ("ERQA  32B-T (fa2) − 4B-T (sdpa)", vals[series[1][0]], vals[series[5][0]]),
    ]:
        diff, lo, hi, se = paired_diff(a_, b_)
        rec(S, f"paired diff — {lab}", round(diff, 2),
            "r4_signals + study_r_trials_h100nvl_fa2.jsonl",
            note=f"[{lo:+.2f}, {hi:+.2f}] SE {se:.2f}; BACKEND-MISMATCHED (device sdpa vs cloud fa2), "
                 "as study_r_device_vs_cloud.md labels it")
        forest_rows.append((lab, diff, lo, hi))
    return None, None


def mvrobo_panel(S, table_rows, forest_rows):
    """MV-RoboBench rows for slide 1."""
    di = {r["qid"]: r for r in r4_rows("mvrobo", "instruct")}
    dt = {r["qid"]: r for r in r4_rows("mvrobo", "thinking")}
    cC, cD = study_s2_arm("C"), study_s2_arm("D")
    ids = common_ids(di, dt, cC, cD)

    series = [
        ("MV-RoboBench  device 4B-I (A6000 HF sdpa)", erqa_ok(di, ids),
         "results/erqa/r4_signals/r4_mvrobo_instruct.jsonl", "r4_device_signals_prep.md §Escalation", 36.9),
        ("MV-RoboBench  device 4B-T (A6000 HF sdpa)", erqa_ok(dt, ids),
         "results/erqa/r4_signals/r4_mvrobo_thinking.jsonl", "r4_device_signals_prep.md §Escalation", 43.6),
        ("MV-RoboBench  cloud 32B-I, StudyS2 arm C (H100 HF fa2)", erqa_ok(cC, ids),
         "study_s2_trials_h100nvl_fa2.jsonl arm=C", "study_s2_mvrobobench_32b.md §Flash-attn", 48.1),
        ("MV-RoboBench  cloud 32B-T, StudyS2 arm D (H100 HF fa2)", erqa_ok(cD, ids),
         "study_s2_trials_h100nvl_fa2.jsonl arm=D", "study_s2_mvrobobench_32b.md §Flash-attn", 43.9),
    ]
    vals = {}
    for lab, ok, src, rep, repv in series:
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(ok))
        rec(S, f"accuracy — {lab}", round(a, 2), src, rep, repv)
        table_rows.append((lab, len(ok), f"{a:.1f}", f"[{lo:.1f}, {hi:.1f}]"))
        vals[lab] = ok

    for lab, a_, b_ in [
        ("MV-RoboBench  32B-I (fa2) − 4B-I (sdpa)", vals[series[0][0]], vals[series[2][0]]),
        ("MV-RoboBench  32B-T (fa2) − 4B-T (sdpa)", vals[series[1][0]], vals[series[3][0]]),
    ]:
        diff, lo, hi, se = paired_diff(a_, b_)
        rec(S, f"paired diff — {lab}", round(diff, 2),
            "r4_signals + study_s2_trials_h100nvl_fa2.jsonl",
            note=f"[{lo:+.2f}, {hi:+.2f}] SE {se:.2f}; BACKEND-MISMATCHED (device sdpa vs cloud fa2)")
        forest_rows.append((lab, diff, lo, hi))
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 2 — does longer reasoning help?
# ─────────────────────────────────────────────────────────────────────────────
def slide2():
    print("S2 thinking minus instruct")
    S = "S2"
    diffs, lengths, changed = [], [], []

    # device 4B, S-EMBER (A6000 llama.cpp F16, DEV-RECENT)
    C1, C3 = device_cell("C1"), device_cell("C3")
    ids = common_ids(C1, C3)
    vids = vids_of(C1, ids)
    a, b = oks(C1, ids), oks(C3, ids)
    d, lo, hi, _ = sember_diff(a, b, vids)
    rec(S, "S-EMBER device 4B  T−I (C3−C1, DEV-RECENT, A6000 llama.cpp F16), all 845",
        round(d, 2), "accuracy_C1.jsonl, accuracy_C3.jsonl",
        note=f"[{lo:+.2f}, {hi:+.2f}]; plotted value. The report's contrast is on qt>120 "
             "(recorded on the next line)")
    qt = np.array([float(C1[i]["question_time"]) for i in ids])
    m = qt > 120
    dq, lq, hq, _ = sember_diff(a[m], b[m], vids[m])
    rec(S, "S-EMBER device 4B  T−I (C3−C1), qt>120 n=678 — report cross-check", round(dq, 2),
        "accuracy_C1.jsonl, accuracy_C3.jsonl", "device_tier_accuracy_llamacpp.md §D", 1.77,
        note=f"CI here [{lq:+.2f}, {hq:+.2f}] vs report [-1.44, +4.89]: point estimate exact, "
             "CI differs by <0.2 pp (see numbers.md notes)")
    diffs.append(("S-EMBER  device 4B (A6000 llama.cpp F16)", d, lo, hi, "device"))
    p1 = preds(C1, ids, "predicted_letter")
    p3 = preds(C3, ids, "predicted_letter")
    ch = 100.0 * float((p1 != p3).mean())
    rec(S, "S-EMBER device 4B  answers changed by thinking (letter changed)", round(ch, 2),
        "accuracy_C1/C3 predicted_letter", unit="%")
    bb, cc = mcnemar_counts(a, b)
    rec(S, "S-EMBER device 4B  discordant correctness b+c", bb + cc,
        "accuracy_C1/C3 correct", unit="questions", note=f"b={bb} c={cc} of n={len(ids)}")
    changed.append(("S-EMBER  device 4B", ch, len(ids), "device"))
    lengths.append(("S-EMBER  device 4B-T\n(A6000 llama.cpp F16)",
                    float(np.median([C3[i]["n_think_tokens"] or 0 for i in ids])),
                    float(np.median([C3[i]["latency_ms"] for i in ids])) / 1000.0, "device"))

    # cloud 32B, S-EMBER (H100 vLLM): K2 − K1
    K = r1()
    idsk = common_ids(K["K1"], K["K2"])
    vk = vids_of(K["K1"], idsk)
    ak, bk = oks(K["K1"], idsk), oks(K["K2"], idsk)
    d, lo, hi, _ = sember_diff(ak, bk, vk)
    rec(S, "S-EMBER cloud 32B  T−I (K2−K1, RICH, H100 vLLM)", round(d, 2),
        "study_r1_requests_h100nvl.jsonl.gz K1,K2",
        "study_r1_cloud32b_sember.md §Accuracy (33.85 − 39.53)", 33.85 - 39.53,
        note=f"[{lo:+.2f}, {hi:+.2f}]; K2 uses model-card VL sampling, K1 is greedy")
    diffs.append(("S-EMBER  cloud 32B (H100 vLLM)", d, lo, hi, "cloud"))
    pk1 = preds(K["K1"], idsk, "pred")
    pk2 = preds(K["K2"], idsk, "pred")
    ch = 100.0 * float((pk1 != pk2).mean())
    rec(S, "S-EMBER cloud 32B  answers changed by thinking (letter changed)", round(ch, 2),
        "study_r1 K1/K2 pred", unit="%")
    bb, cc = mcnemar_counts(ak, bk)
    rec(S, "S-EMBER cloud 32B  discordant correctness b+c", bb + cc,
        "study_r1 K1/K2 correct", unit="questions", note=f"b={bb} c={cc} of n={len(idsk)}")
    changed.append(("S-EMBER  cloud 32B", ch, len(idsk), "cloud"))
    lengths.append(("S-EMBER  cloud 32B-T K2\n(H100 vLLM)",
                    float(np.median([K["K2"][i]["completion_tokens"] for i in idsk])),
                    float(np.median([K["K2"][i]["latency_s"] for i in idsk])), "cloud"))
    note(S, "The R1 K2 request records store `completion_tokens` but no think-token count, "
            "so the 'median reasoning tokens' bar for cloud 32B-T on S-EMBER is completion "
            "tokens (139). study_r1_cloud32b_sember.md reports think tokens median 135 and "
            "completion tokens median 139 for the same cell — the bar is the latter, and it "
            "is the only Thinking arm in this figure not measured as think tokens.")

    # ERQA
    di = {r["qid"]: r for r in r4_rows("erqa", "instruct")}
    dt = {r["qid"]: r for r in r4_rows("erqa", "thinking")}
    ide = common_ids(di, dt)
    d, lo, hi, _ = paired_diff(erqa_ok(di, ide), erqa_ok(dt, ide))
    rec(S, "ERQA device 4B  T−I (A6000 HF sdpa)", round(d, 2),
        "r4_erqa_instruct.jsonl, r4_erqa_thinking.jsonl",
        "r4_device_signals_prep.md §Escalation (45.0 − 42.0)", 3.0, note=f"[{lo:+.2f}, {hi:+.2f}]")
    diffs.append(("ERQA  device 4B (A6000 HF sdpa)", d, lo, hi, "device"))
    ch = 100.0 * float((preds(di, ide, "predicted_letter") != preds(dt, ide, "predicted_letter")).mean())
    rec(S, "ERQA device 4B  answers changed by thinking (letter changed)", round(ch, 2),
        "r4_erqa_* predicted_letter", unit="%")
    bb, cc = mcnemar_counts(erqa_ok(di, ide), erqa_ok(dt, ide))
    rec(S, "ERQA device 4B  discordant correctness b+c", bb + cc, "r4_erqa_* correct",
        unit="questions", note=f"b={bb} c={cc} of n={len(ide)}")
    changed.append(("ERQA  device 4B", ch, len(ide), "device"))
    lengths.append(("ERQA  device 4B-T\n(A6000 HF sdpa)",
                    float(np.median([dt[i]["n_think_tokens"] or 0 for i in ide])),
                    float(np.median([dt[i]["lat_ms"] for i in ide])) / 1000.0, "device"))

    cC, cD = study_r_arm("C"), study_r_arm("D")
    idc = common_ids(cC, cD)
    d, lo, hi, _ = paired_diff(erqa_ok(cC, idc), erqa_ok(cD, idc))
    rec(S, "ERQA cloud 32B  D−C (H100 HF fa2)", round(d, 2),
        "study_r_trials_h100nvl_fa2.jsonl", "study_r_device_vs_cloud.md §Flash-attn (D−C overall)",
        2.0, tol=0.3, note=f"[{lo:+.2f}, {hi:+.2f}]; report quotes +2.0 pp to 1 dp")
    diffs.append(("ERQA  cloud 32B (H100 HF fa2)", d, lo, hi, "cloud"))
    ch = 100.0 * float((preds(cC, idc, "predicted_letter") != preds(cD, idc, "predicted_letter")).mean())
    rec(S, "ERQA cloud 32B  answers changed by thinking (letter changed)", round(ch, 2),
        "study_r fa2 predicted_letter", unit="%",
        note="plotted value; the report's '~22% of answers changed' is the b+c discordance below")
    bb, cc = mcnemar_counts(erqa_ok(cC, idc), erqa_ok(cD, idc))
    rec(S, "ERQA cloud 32B  discordant correctness b+c", bb + cc, "study_r fa2 correct",
        "study_r_device_vs_cloud.md §Flash-attn (b=48 c=40, '~22% overall')", 88.0,
        unit="questions", note=f"b={bb} c={cc} of n={len(idc)} = {100*(bb+cc)/len(idc):.1f}%")
    changed.append(("ERQA  cloud 32B", ch, len(idc), "cloud"))
    lengths.append(("ERQA  cloud 32B-T arm D\n(H100 HF fa2)",
                    float(np.median([cD[i]["n_think_tokens"] or 0 for i in idc])),
                    float(np.median([cD[i]["total_latency_ms"] for i in idc])) / 1000.0, "cloud"))

    # MV-RoboBench
    mi = {r["qid"]: r for r in r4_rows("mvrobo", "instruct")}
    mt = {r["qid"]: r for r in r4_rows("mvrobo", "thinking")}
    idm = common_ids(mi, mt)
    d, lo, hi, _ = paired_diff(erqa_ok(mi, idm), erqa_ok(mt, idm))
    rec(S, "MV-RoboBench device 4B  T−I (A6000 HF sdpa)", round(d, 2),
        "r4_mvrobo_instruct.jsonl, r4_mvrobo_thinking.jsonl",
        "r4_device_signals_prep.md §Escalation (43.6 − 36.9)", 6.7, note=f"[{lo:+.2f}, {hi:+.2f}]")
    diffs.append(("MV-RoboBench  device 4B (A6000 HF sdpa)", d, lo, hi, "device"))
    ch = 100.0 * float((preds(mi, idm, "predicted_letter") != preds(mt, idm, "predicted_letter")).mean())
    rec(S, "MV-RoboBench device 4B  answers changed by thinking (letter changed)", round(ch, 2),
        "r4_mvrobo_* predicted_letter", unit="%")
    bb, cc = mcnemar_counts(erqa_ok(mi, idm), erqa_ok(mt, idm))
    rec(S, "MV-RoboBench device 4B  discordant correctness b+c", bb + cc, "r4_mvrobo_* correct",
        unit="questions", note=f"b={bb} c={cc} of n={len(idm)}")
    changed.append(("MV-RoboBench  device 4B", ch, len(idm), "device"))
    lengths.append(("MV-RoboBench  device 4B-T\n(A6000 HF sdpa)",
                    float(np.median([mt[i]["n_think_tokens"] or 0 for i in idm])),
                    float(np.median([mt[i]["lat_ms"] for i in idm])) / 1000.0, "device"))

    sC, sD = study_s2_arm("C"), study_s2_arm("D")
    ids2 = common_ids(sC, sD)
    d, lo, hi, _ = paired_diff(erqa_ok(sC, ids2), erqa_ok(sD, ids2))
    rec(S, "MV-RoboBench cloud 32B  D−C (H100 HF fa2)", round(d, 2),
        "study_s2_trials_h100nvl_fa2.jsonl", "study_s2_mvrobobench_32b.md §Flash-attn (net_rescue)",
        -4.24, note=f"[{lo:+.2f}, {hi:+.2f}]")
    diffs.append(("MV-RoboBench  cloud 32B (H100 HF fa2)", d, lo, hi, "cloud"))
    ch = 100.0 * float((preds(sC, ids2, "pred") != preds(sD, ids2, "pred")).mean())
    rec(S, "MV-RoboBench cloud 32B  answers changed by thinking (letter changed)", round(ch, 2),
        "study_s2 fa2 pred", unit="%",
        note="plotted value; the report's 'answers changed by thinking 123 (30.7%)' is b+c below")
    bb, cc = mcnemar_counts(erqa_ok(sC, ids2), erqa_ok(sD, ids2))
    rec(S, "MV-RoboBench cloud 32B  discordant correctness b+c", bb + cc, "study_s2 fa2 correct",
        "study_s2_mvrobobench_32b.md §Flash-attn (b=53 c=70 → 123, '30.7%')", 123.0,
        unit="questions", note=f"b={bb} c={cc} of n={len(ids2)} = {100*(bb+cc)/len(ids2):.1f}%")
    changed.append(("MV-RoboBench  cloud 32B", ch, len(ids2), "cloud"))
    lengths.append(("MV-RoboBench  cloud 32B-T arm D\n(H100 HF fa2)",
                    float(np.median([sD[i]["n_think_tokens"] or 0 for i in ids2])),
                    float(np.median([sD[i]["total_latency_ms"] for i in ids2])) / 1000.0, "cloud"))

    for lab, tt, lt, tier in lengths:
        rec(S, f"median reasoning tokens — {lab}".replace("\n", " "), round(tt, 1), "per-trial records", unit="tok")
        rec(S, f"median latency — {lab}".replace("\n", " "), round(lt, 2), "per-trial records", unit="s")

    # ---------- figure ----------
    fig = plt.figure(figsize=(18, 7.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.35, 1.0, 0.85], wspace=0.55)

    ax1 = fig.add_subplot(gs[0])
    forest(ax1, [(l, d, lo, hi) for l, d, lo, hi, _ in diffs],
           "Thinking − Instruct  (pp, paired)",
           title="A.  Thinking minus Instruct, same tier and workload",
           colors={l: (DEVICE_C if t == "device" else CLOUD_C) for l, _, _, _, t in diffs})
    ax1.text(0.995, 0.02, "filled marker = 95% CI excludes 0",
             transform=ax1.transAxes, ha="right", va="bottom",
             fontsize=9, color=C["grey"], style="italic")

    ax2 = fig.add_subplot(gs[1])
    ys = np.arange(len(lengths))[::-1]
    cols = [DEVICE_C if t == "device" else CLOUD_C for *_, t in lengths]
    ax2.barh(ys, [l[1] for l in lengths], color=cols, height=0.6)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([l[0] for l in lengths], fontsize=8.5)
    ax2.set_xscale("log")
    ax2.set_xlabel("median reasoning tokens  (log)")
    ax2.set_title("B.  Cost of the Thinking arm", fontsize=FONT_LABEL,
                  fontweight="bold", loc="left")
    for y, l in zip(ys, lengths):
        ax2.text(l[1] * 1.12, y, f"{l[1]:,.0f} tok · {l[2]:.1f} s med",
                 va="center", fontsize=8.6, color=C["dark"])
    ax2.set_xlim(right=max(l[1] for l in lengths) * 9)

    ax3 = fig.add_subplot(gs[2])
    ys = np.arange(len(changed))[::-1]
    cols = [DEVICE_C if t == "device" else CLOUD_C for *_, t in changed]
    ax3.barh(ys, [c[1] for c in changed], color=cols, height=0.6)
    ax3.set_yticks(ys)
    ax3.set_yticklabels([f"{c[0]}  (n={c[2]})" for c in changed], fontsize=8.5)
    ax3.set_xlabel("% of answers changed")
    ax3.set_title("C.  Thinking reshuffles answers", fontsize=FONT_LABEL,
                  fontweight="bold", loc="left")
    for y, c in zip(ys, changed):
        ax3.text(c[1] + 1.2, y, f"{c[1]:.0f}%", va="center", fontsize=9, color=C["dark"])
    ax3.set_xlim(0, max(c[1] for c in changed) * 1.28)

    fig.suptitle("Does longer reasoning help?  Thinking vs Instruct at each tier "
                 "(device = Orin-class 4B, cloud = H100 32B)",
                 fontsize=15, fontweight="bold", x=0.012, ha="left", y=1.005)
    save(fig, "s2_thinking_vs_instruct")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 3 — model capability vs historical evidence
# ─────────────────────────────────────────────────────────────────────────────
def _did_block(S, label, lo_ok, hi_ok, covered, vids, n_note, src, rep=None, repv=None):
    """(hi - lo) within each evidence stratum, plus the DiD with clustered CI."""
    miss = ~covered
    cells = {}
    for stratum, m in (("evidence NOT covered by RECENT", miss), ("evidence covered by RECENT", covered)):
        a, b = 100 * lo_ok[m].mean(), 100 * hi_ok[m].mean()
        cells[stratum] = (int(m.sum()), a, b, b - a)
        rec(S, f"{label} — {stratum}: RECENT-like", round(a, 2), src)
        rec(S, f"{label} — {stratum}: RICH-like", round(b, 2), src)
        rec(S, f"{label} — {stratum}: diff", round(b - a, 2), src)
    obs, lo, hi, se = did_with_ci(lo_ok, hi_ok, covered, vids, nboot=NBOOT, seed=SEED)
    obs, lo, hi, se = 100 * obs, 100 * lo, 100 * hi, 100 * se
    rec(S, f"{label} — DiD (miss − cover)", round(obs, 2), src, rep, repv,
        note=f"[{lo:+.2f}, {hi:+.2f}] SE {se:.2f}; {n_note}")
    return cells, (obs, lo, hi)


def slide3():
    print("S3 capability vs historical evidence")
    S = "S3"
    dev_blocks, cloud_blocks, dids = [], [], []

    # ---- device: C1 vs C2 (4B-I) and C3 vs C4 (4B-T), qt > 120 ----
    for lab, lo_cell, hi_cell, repv in [
        ("device 4B-I  DEV-RECENT → DEV-RICH\n(A6000 llama.cpp F16)", "C1", "C2", 22.28),
        ("device 4B-T  DEV-RECENT → DEV-RICH\n(A6000 llama.cpp F16)", "C3", "C4", 19.56),
    ]:
        L, H = device_cell(lo_cell), device_cell(hi_cell)
        ids = common_ids(L, H)
        qt = np.array([float(L[i]["question_time"]) for i in ids])
        m = qt > 120
        ids = [i for i, keep in zip(ids, m) if keep]
        lo_ok, hi_ok = oks(L, ids), oks(H, ids)
        covered = np.array([bool(L[i]["evidence_covered"]) for i in ids])
        vids = vids_of(L, ids)
        cells, did = _did_block(
            S, lab.replace("\n", " "), lo_ok, hi_ok, covered, vids,
            f"qt>120 denominator, n={len(ids)}",
            f"results/device/accuracy_{lo_cell}.jsonl, accuracy_{hi_cell}.jsonl",
            "device_tier_accuracy_llamacpp.md §B", repv)
        dev_blocks.append((lab, cells, len(ids)))
        dids.append((lab.replace("\n", " "), *did, "device"))

    # ---- cloud: K3 → K1 (R1) and K3 → D2 (RH4) ----
    K = r1()
    ids = common_ids(K["K1"], K["K3"])
    lo_ok, hi_ok = oks(K["K3"], ids), oks(K["K1"], ids)
    covered = np.array([bool(K["K3"][i]["evidence_covered"]) for i in ids])
    vids = vids_of(K["K3"], ids)
    cells, did = _did_block(
        S, "cloud 32B-I  K3 RECENT → K1 RICH", lo_ok, hi_ok, covered, vids,
        f"all {len(ids)}", "study_r1_requests_h100nvl.jsonl.gz K1,K3",
        "study_r1_cloud32b_sember.md HISTORY GATES THE CLOUD", 18.46)
    cloud_blocks.append(("cloud 32B-I  K3 RECENT → K1 RICH\n(H100 vLLM)", cells, len(ids)))
    dids.append(("cloud 32B-I  K3 RECENT → K1 RICH (H100 vLLM)", *did, "cloud"))

    D = rh4()["D2"]
    D = {k: v for k, v in D.items() if v["error"] is None}
    ids = common_ids(K["K3"], D)
    lo_ok, hi_ok = oks(K["K3"], ids), oks(D, ids)
    covered = np.array([bool(K["K3"][i]["evidence_covered"]) for i in ids])
    vids = vids_of(K["K3"], ids)
    cells, did = _did_block(
        S, "cloud 32B-I  K3 RECENT → D2 fixed-stride", lo_ok, hi_ok, covered, vids,
        f"paired {len(ids)} (6 over-context D2 questions excluded)",
        "study_r1 K3 + study_rh4_requests_h100nvl.jsonl.gz D2",
        "study_rh4_fixed_stride.md Contrasts (D2 − K3 DiD)", 24.09)
    cloud_blocks.append(("cloud 32B-I  K3 RECENT → D2 stride-2 s\n(H100 vLLM, append-only)", cells, len(ids)))
    dids.append(("cloud 32B-I  K3 RECENT → D2 stride-2 s (H100 vLLM)", *did, "cloud"))

    # ---- figure ----
    fig = plt.figure(figsize=(16, 10.5))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.62], hspace=0.42, wspace=0.18)

    for col, (blocks, tier, tcol) in enumerate(
            [(dev_blocks, "Device tier (Orin-class 4B)", DEVICE_C),
             (cloud_blocks, "Cloud tier (H100 32B)", CLOUD_C)]):
        ax = fig.add_subplot(gs[0, col])
        labels, xs = [], []
        x = 0
        for lab, cells, n in blocks:
            for stratum, (sn, a, b, d) in cells.items():
                short = "evidence MISS" if "NOT" in stratum else "evidence COVER"
                ax.bar(x - 0.19, a, width=0.36, color=C["grey"], zorder=2)
                ax.bar(x + 0.19, b, width=0.36, color=tcol, zorder=2)
                ax.annotate("", xy=(x + 0.19, b), xytext=(x - 0.19, a),
                            arrowprops=dict(arrowstyle="->", color=C["dark"], lw=1.3,
                                            shrinkA=2, shrinkB=2), zorder=4)
                ax.text(x, max(a, b) + 2.0, f"{d:+.1f}", ha="center", fontsize=10,
                        fontweight="bold", color=C["dark"])
                labels.append(f"{short}\nn={sn}")
                xs.append(x)
                x += 1
            x += 0.6
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("accuracy (%)")
        ax.set_ylim(0, 64)
        ax.set_title(tier, fontsize=FONT_LABEL, fontweight="bold", loc="left")
        for i, (lab, cells, n) in enumerate(blocks):
            ax.text(i * 2.6 + 0.5, 56.5, lab, ha="center", fontsize=9,
                    color=tcol, fontweight="bold")
        ax.legend(handles=[mpatches.Patch(color=C["grey"], label="recent-window history"),
                           mpatches.Patch(color=tcol, label="whole-session history")],
                  fontsize=9.5, frameon=False, loc="upper center",
                  bbox_to_anchor=(0.5, -0.12), ncol=2)

    axd = fig.add_subplot(gs[1, :])
    forest(axd, [(l, d, lo, hi) for l, d, lo, hi, _ in dids],
           "difference-in-differences:  (whole-session − recent) on MISS  minus  the same on COVER   (pp)",
           title="Capability only pays when the recent window missed the evidence  "
                 "(video-clustered bootstrap, 2,000 resamples, seed 0)",
           colors={l: (DEVICE_C if t == "device" else CLOUD_C) for l, _, _, _, t in dids})
    axd.text(0.995, 0.03, "filled marker = 95% CI excludes 0", transform=axd.transAxes,
             ha="right", va="bottom", fontsize=9, color=C["grey"], style="italic")

    fig.suptitle("Model capability vs historical evidence — split by whether the recent "
                 "window covered the answer's evidence\n"
                 "device panel uses the pre-registered qt > 120 s denominator "
                 "(n = 678); cloud panels use all questions",
                 fontsize=14.5, fontweight="bold", x=0.012, ha="left", y=1.02)
    save(fig, "s3_capability_vs_evidence")


# AUROC values as printed in reports/r4_device_signals_prep.md §AUROC, for cross-checking.
# option_mass for MV-RoboBench/4B-Thinking is referenced in that report's prose but is absent
# from its table, so it has no report value here.
REPORT_AUROC = {
    ("erqa", "instruct"): {"neg_entropy_bits": 0.5734, "max_option_prob": 0.5709,
                           "margin_norm": 0.5703, "option_mass": 0.5171},
    ("erqa", "thinking"): {"neg_hesitation_wait": 0.6229, "neg_hesitation_total": 0.6155,
                           "neg_think_tokens": 0.6002, "max_option_prob": 0.5666,
                           "neg_entropy_bits": 0.5645, "margin_norm": 0.5644,
                           "neg_letter_changes": 0.5640, "option_mass": 0.5020},
    ("mvrobo", "instruct"): {"option_mass": 0.6145, "neg_entropy_bits": 0.5913,
                             "max_option_prob": 0.5902, "margin_norm": 0.5885},
    ("mvrobo", "thinking"): {"margin_norm": 0.6021, "max_option_prob": 0.6012,
                             "neg_entropy_bits": 0.6010, "neg_hesitation_wait": 0.5814,
                             "neg_hesitation_total": 0.5698, "neg_think_tokens": 0.5421,
                             "neg_letter_changes": 0.5070},
}


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 4 — can we predict when to escalate?
# ─────────────────────────────────────────────────────────────────────────────
def esc_grid(n, step=1):
    ks = np.arange(0, n + 1, step)
    if ks[-1] != n:
        ks = np.append(ks, n)
    return ks


def curve_from_order(order, dev_ok, cloud_ok, ks):
    """Accuracy when the first k items of `order` are escalated."""
    dev_ok = np.asarray(dev_ok, bool)
    cloud_ok = np.asarray(cloud_ok, bool)
    # gains accumulate in ESCALATION order, not index order
    gain = cloud_ok[order].astype(int) - dev_ok[order].astype(int)
    cum = np.concatenate([[0.0], np.cumsum(gain)])
    base = dev_ok.sum()
    return 100.0 * (base + cum[ks]) / len(dev_ok)


def random_curve(dev_ok, cloud_ok, ks, draws=200, seed=SEED):
    """Mean accuracy over `draws` random escalation sets at each k."""
    dev_ok = np.asarray(dev_ok, bool)
    cloud_ok = np.asarray(cloud_ok, bool)
    n = len(dev_ok)
    rng = np.random.default_rng(seed)
    acc_sum = np.zeros(len(ks))
    for _ in range(draws):
        order = rng.permutation(n)
        acc_sum += curve_from_order(order, dev_ok, cloud_ok, ks)
    return acc_sum / draws


def oracle_order(dev_ok, cloud_ok):
    """Escalate device-wrong & cloud-right first (r4_analyse's rule)."""
    helps = np.asarray(cloud_ok, bool).astype(int) - np.asarray(dev_ok, bool).astype(int)
    return np.argsort(-helps, kind="mergesort")


def oracle_reaches_cloud(dev_ok, cloud_ok):
    """Smallest escalated fraction at which the perfect oracle reaches always-cloud accuracy."""
    n = len(dev_ok)
    ks = np.arange(0, n + 1)
    cur = curve_from_order(oracle_order(dev_ok, cloud_ok), dev_ok, cloud_ok, ks)
    target = 100.0 * np.asarray(cloud_ok, bool).mean()
    hit = np.nonzero(cur >= target - 1e-9)[0]
    return (float(hit[0]) / n) if len(hit) else float("nan")


def _esc_panel(ax, title, dev_ok, cloud_ok, signals, subtitle):
    n = len(dev_ok)
    ks = esc_grid(n, max(1, n // 200))
    e = ks / n
    base = 100.0 * dev_ok.mean()
    cloudacc = 100.0 * cloud_ok.mean()

    ax.axhline(base, color=DEVICE_C, lw=1.4, ls=":", zorder=1)
    ax.axhline(cloudacc, color=CLOUD_C, lw=1.4, ls=":", zorder=1)
    ax.text(0.015, base, " always-local", color=DEVICE_C, fontsize=8.5,
            va="bottom", ha="left", fontweight="bold")
    ax.text(0.985, cloudacc, "always-cloud ", color=CLOUD_C, fontsize=8.5,
            va="bottom", ha="right", fontweight="bold")

    rnd = random_curve(dev_ok, cloud_ok, ks)
    ax.plot(e, rnd, color=C["dark"], lw=2.2, ls="--", label="random (mean of 200 draws)", zorder=3)
    orc = curve_from_order(oracle_order(dev_ok, cloud_ok), dev_ok, cloud_ok, ks)
    ax.plot(e, orc, color=C["green"], lw=2.4, label="perfect oracle", zorder=3)

    pal = [C["blue"], C["violet"], C["orange"], C["yellow"], C["teal"],
           C["red"], C["grey"], "#AA4499"]
    sig_curves = {}
    for i, (name, conf) in enumerate(signals.items()):
        order = np.argsort(conf, kind="mergesort")  # least confident first
        cur = curve_from_order(order, dev_ok, cloud_ok, ks)
        sig_curves[name] = (cur, pal[i % len(pal)])
        ax.plot(e, cur, color=pal[i % len(pal)], lw=1.5, alpha=0.95, label=name, zorder=2)

    # inset: every signal against random on the same escalation budget
    if sig_curves:
        ins = ax.inset_axes([0.085, 0.50, 0.40, 0.33])
        for name, (cur, col) in sig_curves.items():
            ins.plot(e, cur - rnd, color=col, lw=1.1)
        ins.axhline(0, color=C["dark"], lw=1.1, ls="--")
        ins.set_xlim(0, 1)
        ins.tick_params(labelsize=6.5, length=2)
        ins.set_title("signal − random (pp)", fontsize=7.2, color=C["dark"], pad=2)
        for sp in ("top", "right"):
            ins.spines[sp].set_visible(False)

    ax.set_xlim(0, 1)
    ax.set_xlabel("fraction escalated to cloud")
    ax.set_ylabel("accuracy (%)")
    ax.set_title(f"{title}\n{subtitle}", fontsize=10.5, fontweight="bold", loc="left")
    return base, cloudacc


def slide4():
    print("S4 escalation")
    S = "S4"
    auroc_blocks = []

    fig = plt.figure(figsize=(16, 21))
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 1.5], hspace=0.42, wspace=0.22)

    # ---------- S-EMBER: device C1 / C3 → cloud K1 ----------
    K = r1()
    C1, C3 = device_cell("C1"), device_cell("C3")
    for col, (cell, name) in enumerate([("C1", "4B-Instruct"), ("C3", "4B-Thinking")]):
        D = device_cell(cell)
        ids = common_ids(D, K["K1"], K["K3"])
        dev_ok = oks(D, ids)
        cloud_ok = oks(K["K1"], ids)
        miss = ~np.array([bool(K["K3"][i]["evidence_covered"]) for i in ids])
        n = len(ids)

        ax = fig.add_subplot(gs[0, col])
        base, cloudacc = _esc_panel(
            ax, f"S-EMBER — device {name} → cloud 32B-I RICH (K1)",
            dev_ok, cloud_ok, {},
            f"device A6000 llama.cpp F16 · cloud H100 vLLM · n={n}")

        # evidence oracle: escalate exactly the questions RECENT misses
        order = np.concatenate([np.nonzero(miss)[0], np.nonzero(~miss)[0]])
        k = int(miss.sum())
        ev_acc = float(curve_from_order(order, dev_ok, cloud_ok, np.array([k]))[0])
        ax.plot([k / n], [ev_acc], marker="D", ms=10, color=C["orange"],
                mec="white", mew=1.4, zorder=5,
                label=f"evidence oracle (escalate the {k} RECENT-miss questions)")
        ax.annotate(f"evidence oracle: escalate exactly the {k} questions\n"
                    f"the RECENT window misses  →  {ev_acc:.1f}%",
                    xy=(k / n, ev_acc), xytext=(0.17, 0.30), textcoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color=C["orange"], lw=1.4),
                    fontsize=8.8, color=C["orange"], fontweight="bold")
        rec(S, f"S-EMBER {name} — always-local accuracy", round(base, 2),
            f"results/device/accuracy_{cell}.jsonl")
        rec(S, f"S-EMBER {name} — always-cloud (K1) accuracy", round(cloudacc, 2),
            "study_r1 K1")
        rec(S, f"S-EMBER {name} — evidence-oracle accuracy at e={k/n:.3f}", round(ev_acc, 2),
            "study_r1 K3 evidence_covered + K1",
            note=f"escalates the {k} questions the RECENT window misses")
        f_hit = oracle_reaches_cloud(dev_ok, cloud_ok)
        rec(S, f"S-EMBER {name} — fraction escalated where the perfect oracle first "
               "reaches always-cloud accuracy", round(f_hit, 4), "computed", unit="fraction")

    # ---------- ERQA / MV-RoboBench: cloud = arm C (32B-Instruct) ----------
    rng = np.random.default_rng(SEED)   # same stream order as r4_analyse.main()
    row = 1
    for workload, cloud_map, cloud_label, cloud_file in [
        ("erqa", study_r_arm("C"), "StudyR arm C (32B-Instruct, H100 HF fa2)",
         "study_r_trials_h100nvl_fa2.jsonl"),
        ("mvrobo", study_s2_arm("C"), "StudyS2 arm C (32B-Instruct, H100 HF fa2)",
         "study_s2_trials_h100nvl_fa2.jsonl"),
    ]:
        wl_name = "ERQA" if workload == "erqa" else "MV-RoboBench"
        for col, arm in enumerate(("instruct", "thinking")):
            rows = r4_rows(workload, arm)
            dev_ok_all = np.array([bool(r["correct"]) for r in rows], bool)
            sigs_all = R4.signals_for(rows, arm)

            # AUROC + CI, in r4_analyse's own order so the rng stream matches the report
            block = []
            for nm, sv in sigs_all.items():
                a = R4.auroc(sv, dev_ok_all)
                ci = R4.boot_ci(lambda idx, sv=sv: R4.auroc(sv[idx], dev_ok_all[idx]),
                                len(rows), rng)
                block.append((nm, a, ci))
                repv = REPORT_AUROC[(workload, arm)].get(nm)
                rec(S, f"AUROC {wl_name}/4B-{arm} — {nm}", round(a, 4),
                    f"results/erqa/r4_signals/r4_{workload}_{arm}.jsonl",
                    "r4_device_signals_prep.md §AUROC", repv, unit="AUROC", tol=0.00005,
                    note=f"95% CI [{ci[0]:.4f}, {ci[1]:.4f}]" + (
                        "" if repv is not None else
                        "; not listed in the report's table (its prose refers to it)"))

            paired = [(r, cloud_map[r["qid"]]) for r in rows if r["qid"] in cloud_map]
            pr = [x[0] for x in paired]
            cloud_ok = np.array([bool(x[1]["correct"]) for x in paired], bool)
            dev_ok = np.array([bool(r["correct"]) for r in pr], bool)
            sigs = R4.signals_for(pr, arm)
            n = len(pr)

            ax = fig.add_subplot(gs[row, col])
            base, cloudacc = _esc_panel(
                ax, f"{wl_name} — device 4B-{arm.capitalize()} → cloud 32B-I (arm C)",
                dev_ok, cloud_ok, sigs,
                f"device A6000 HF sdpa · cloud H100 HF fa2 · n={n}")
            # legend is shared at figure level (see below)

            # keep the rng stream aligned with r4_analyse (escalation draws)
            best = max(sigs.items(), key=lambda kv: (R4.auroc(kv[1], dev_ok)
                                                     if np.isfinite(R4.auroc(kv[1], dev_ok)) else 0))
            esc = R4.escalation(best[1], dev_ok, cloud_ok, rng)
            for r_ in esc:
                rec(S, f"{wl_name}/4B-{arm} escalation @e={r_['e']} — signal "
                       f"'{best[0]}' (cloud = arm C)", round(100 * r_["signal"], 2),
                    f"r4_{workload}_{arm}.jsonl + {cloud_file} arm=C",
                    note=f"random {100*r_['random']:.1f}, oracle {100*r_['oracle']:.1f}, "
                         f"gap closed {r_['closed']:.3f}; the report's table uses arm D "
                         "(32B-Thinking) as cloud, so its values differ by design")
            f_hit = oracle_reaches_cloud(dev_ok, cloud_ok)
            rec(S, f"{wl_name}/4B-{arm} — fraction escalated where the perfect oracle first "
                   "reaches always-cloud accuracy", round(f_hit, 4), "computed", unit="fraction")
            rec(S, f"{wl_name}/4B-{arm} — always-local accuracy", round(base, 2),
                f"r4_{workload}_{arm}.jsonl")
            rec(S, f"{wl_name}/4B-{arm} — always-cloud (arm C) accuracy", round(cloudacc, 2),
                cloud_file)
            auroc_blocks.append((f"{wl_name} / 4B-{arm.capitalize()}  (n={len(rows)})",
                                 block, f_hit, base, cloudacc))
        row += 1

    # ---------- AUROC table ----------
    ax = fig.add_subplot(gs[3, :])
    ax.axis("off")
    lines = []
    for title, block, f_hit, base, cloudacc in auroc_blocks:
        lines.append((f"{title}", "", "", ""))
        for nm, a, ci in sorted(block, key=lambda t: -t[1]):
            lines.append((f"    {nm}", f"{a:.4f}", f"[{ci[0]:.4f}, {ci[1]:.4f}]", ""))
        lines.append(("    always-local / always-cloud (arm C)",
                      f"{base:.1f}% / {cloudacc:.1f}%", "",
                      f"perfect oracle reaches always-cloud at e = {f_hit:.3f}"))
    table_axes(ax, ["signal  (higher = more confident)", "AUROC for device correctness",
                    "95% CI", "oracle crossing"],
               lines, col_widths=[0.40, 0.17, 0.19, 0.24], fontsize=8.4,
               row_colors={i: (C["dark"] if r[0].startswith("    ") else CLOUD_C)
                           for i, r in enumerate(lines)})
    ax.set_title("AUROC of each device-side confidence signal for device correctness  "
                 "(Mann-Whitney U, tie-corrected; 2,000-resample question bootstrap, seed 0)",
                 fontsize=12, fontweight="bold", loc="left")

    SIG_NAMES = ["neg_entropy_bits", "margin_norm", "max_option_prob", "option_mass",
                 "neg_think_tokens", "neg_hesitation_total", "neg_hesitation_wait",
                 "neg_letter_changes"]
    pal = [C["blue"], C["violet"], C["orange"], C["yellow"], C["teal"],
           C["red"], C["grey"], "#AA4499"]
    handles = [Line2D([], [], color=C["dark"], lw=2.2, ls="--",
                      label="random (mean of 200 draws)"),
               Line2D([], [], color=C["green"], lw=2.4, label="perfect oracle"),
               Line2D([], [], color=C["orange"], marker="D", ls="none", ms=9,
                      label="evidence oracle (S-EMBER only)")]
    handles += [Line2D([], [], color=pal[i], lw=1.6, label=n)
                for i, n in enumerate(SIG_NAMES)]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.962),
               ncol=6, fontsize=9.2, frameon=False,
               title="device-side confidence signals (ERQA / MV-RoboBench panels); "
                     "signals are ordered least-confident-first",
               title_fontsize=9.2)
    fig.suptitle(
        "Can we predict when to escalate?  Accuracy vs fraction escalated from "
        "device (Orin-class 4B) to cloud (H100 32B)\n"
        "ERQA and MV-RoboBench cloud tier is 32B-Instruct (arm C), not the "
        "32B-Thinking arm D used in reports/r4_device_signals_prep.md",
        fontsize=14.5, fontweight="bold", x=0.012, ha="left", y=0.995)
    fig.text(0.012, 0.055,
             "Footnote: the perfect oracle escalates exactly the questions the device gets wrong "
             "and the cloud gets right. On 4–5 option multiple choice both tiers\n"
             "also agree by chance, so the oracle counts chance-correct cloud answers as "
             "recoverable and overstates the headroom a real trigger could reach.",
             fontsize=10, color=C["dark"], style="italic", va="top")
    save(fig, "s4_escalation")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 5 — what does local reasoning cost?
# ─────────────────────────────────────────────────────────────────────────────
ORIN_CFGS = [
    ("4bi_f16_F16", "4B-Instruct F16", False),
    ("4bt_f16_F16", "4B-Thinking F16", True),
    ("8bi_f16_F16", "8B-Instruct F16", False),
    ("8bt_f16_F16", "8B-Thinking F16", True),
    ("4bt_q8_Q8_0", "4B-Thinking Q8_0", True),
]
ORIN_REPORT = {   # device_latency_sember.md, median values
    "4bi_f16_F16": dict(ttft=17.0, total=17.1, think=0, dec=None),
    "4bt_f16_F16": dict(ttft=17.2, total=38.3, think=342, dec=16.2),
    "8bi_f16_F16": dict(ttft=28.3, total=28.4, think=0, dec=None),
    "8bt_f16_F16": dict(ttft=28.4, total=59.3, think=318, dec=10.0),
    "4bt_q8_Q8_0": dict(ttft=18.1, total=37.2, think=470, dec=22.0),
}


def decode_rate_from_tokens(tag):
    """Decode tok/s per question from the per-token timestamp arrays."""
    out = []
    for r in orin_tokens(tag):
        ts = [t[0] for t in r["tokens"]]
        if len(ts) >= 3 and ts[-1] > ts[0]:
            out.append((len(ts) - 1) / (ts[-1] - ts[0]))
    return np.array(out)


def slide5():
    print("S5 local reasoning cost")
    S = "S5"
    data = {}
    for tag, label, thinking in ORIN_CFGS:
        rows = orin_latency(tag)
        rep = ORIN_REPORT[tag]
        ttft = np.array([r["ttft_s"] for r in rows], float)
        tot = np.array([r["total_latency_s"] for r in rows], float)
        think = np.array([r["n_think_tokens"] or 0 for r in rows], float)
        dec = decode_rate_from_tokens(tag)
        data[tag] = dict(label=label, thinking=thinking, n=len(rows),
                         ttft=ttft, total=tot, think=think, dec=dec)
        src = f"results/device/latency_sember_{tag}.jsonl"
        rec(S, f"{label} (Orin llama.cpp) — TTFT median", round(float(np.median(ttft)), 2),
            src, "device_latency_sember.md", rep["ttft"], unit="s", tol=0.06,
            note=f"p90 {np.percentile(ttft,90):.2f} s, n={len(rows)}")
        rec(S, f"{label} (Orin llama.cpp) — total latency median",
            round(float(np.median(tot)), 2), src, "device_latency_sember.md", rep["total"],
            unit="s", tol=0.06, note=f"p90 {np.percentile(tot,90):.2f} s")
        if thinking:
            rec(S, f"{label} (Orin llama.cpp) — reasoning tokens median",
                round(float(np.median(think)), 1), src, "device_latency_sember.md",
                float(rep["think"]), unit="tok", tol=0.6,
                note=f"p90 {np.percentile(think,90):.0f} tok")
            rec(S, f"{label} (Orin llama.cpp) — decode tok/s median (from per-token timestamps)",
                round(float(np.median(dec)), 2), f"results/device/tokens_{tag}.jsonl.gz",
                "device_latency_sember.md", rep["dec"], unit="tok/s", tol=0.4)

    # cloud reference band: RH5 Part A at 11k
    pa = jl("results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz")
    band = {}
    for lab, cfg, state, repv in [("GPU-warm (GPU-only)", "gpu", "GPU-WARM", 0.382),
                                  ("Host-warm (GPU+host)", "host", "HOST-WARM", 0.459),
                                  ("Cold re-prefill (GPU-only)", "gpu", "COLD", 2.445)]:
        v = np.array([r["ttft_s"] for r in pa
                      if r["size"] == "11k" and r["cfg"] == cfg and r["state"] == state], float)
        band[lab] = (float(np.median(v)), float(v.min()), float(v.max()), len(v))
        rec(S, f"cloud reference, H100 32B TTFT at 11k — {lab}", round(float(np.median(v)), 3),
            "results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz",
            "study_rh5_host_offload.md Part A", repv, unit="s", tol=0.002,
            note=f"[{v.min():.3f}, {v.max():.3f}], n={len(v)}; TTFT only, no network")

    # ---------- figure ----------
    fig = plt.figure(figsize=(17, 10))
    gs = fig.add_gridspec(2, 2, hspace=0.42, wspace=0.22)
    tags = [t for t, _, _ in ORIN_CFGS]
    labs = [data[t]["label"] for t in tags]
    cols = [C["blue"] if "4B" in l else C["violet"] for l in labs]

    ax = fig.add_subplot(gs[0, 0])
    bp = ax.boxplot([data[t]["ttft"] for t in tags], vert=True, widths=0.55,
                    patch_artist=True, showfliers=False)
    for b, c_ in zip(bp["boxes"], cols):
        b.set(facecolor=c_, alpha=0.75, edgecolor=C["dark"])
    for med in bp["medians"]:
        med.set(color=C["dark"], lw=2)
    for lab, (m, lo, hi, nn) in band.items():
        ax.axhline(m, color=C["red"], lw=1.3,
                   ls="-" if "Cold" in lab else ("--" if "Host" in lab else ":"))
        ax.text(0.62, m * 1.07, f"H100 32B cloud — {lab}: {m:.2f} s", color=C["red"],
                fontsize=8.2, va="bottom", ha="left")
    ax.set_xticks(range(1, len(tags) + 1))
    ax.set_xticklabels(labs, fontsize=9, rotation=18, ha="right")
    ax.set_ylabel("TTFT (s)")
    ax.set_yscale("log")
    ax.set_title("A.  Time to first token — Jetson AGX Orin, llama.cpp\n"
                 "red lines: H100 32B vLLM at an 11k-token history, TTFT only, no network",
                 fontsize=11.5, fontweight="bold", loc="left")

    ax = fig.add_subplot(gs[0, 1])
    bp = ax.boxplot([data[t]["total"] for t in tags], vert=True, widths=0.55,
                    patch_artist=True, showfliers=True,
                    flierprops=dict(marker=".", ms=3, mfc=C["grey"], mec="none"))
    for b, c_ in zip(bp["boxes"], cols):
        b.set(facecolor=c_, alpha=0.75, edgecolor=C["dark"])
    for med in bp["medians"]:
        med.set(color=C["dark"], lw=2)
    ax.set_xticks(range(1, len(tags) + 1))
    ax.set_xticklabels(labs, fontsize=9, rotation=18, ha="right")
    ax.set_ylabel("full-response latency (s)")
    ax.set_yscale("log")
    ax.set_title("B.  Full response latency (log) — Orin llama.cpp\n"
                 "Instruct is prefill-bound; Thinking adds a long, heavy tail",
                 fontsize=11.5, fontweight="bold", loc="left")

    ax = fig.add_subplot(gs[1, 0])
    tt = [t for t in tags if data[t]["thinking"]]
    bp = ax.boxplot([data[t]["think"] for t in tt], vert=True, widths=0.45,
                    patch_artist=True, showfliers=True,
                    flierprops=dict(marker=".", ms=3, mfc=C["grey"], mec="none"))
    for b in bp["boxes"]:
        b.set(facecolor=C["orange"], alpha=0.7, edgecolor=C["dark"])
    for med in bp["medians"]:
        med.set(color=C["dark"], lw=2)
    ax.set_xticks(range(1, len(tt) + 1))
    ax.set_xticklabels([data[t]["label"] for t in tt], fontsize=9.5)
    ax.set_ylabel("reasoning tokens")
    ax.set_yscale("log")
    ax.set_title("C.  Reasoning-token distribution per Thinking model (Orin llama.cpp)",
                 fontsize=11.5, fontweight="bold", loc="left")

    ax = fig.add_subplot(gs[1, 1])
    bp = ax.boxplot([data[t]["dec"] for t in tt], vert=True, widths=0.45,
                    patch_artist=True, showfliers=False)
    for b in bp["boxes"]:
        b.set(facecolor=C["teal"], alpha=0.8, edgecolor=C["dark"])
    for med in bp["medians"]:
        med.set(color=C["dark"], lw=2)
    for i, t in enumerate(tt, start=1):
        ax.text(i, float(np.median(data[t]["dec"])) + 0.9,
                f"{np.median(data[t]['dec']):.1f}", ha="center", fontsize=9.5,
                fontweight="bold", color=C["dark"])
    ax.set_xticks(range(1, len(tt) + 1))
    ax.set_xticklabels([data[t]["label"] for t in tt], fontsize=9.5)
    ax.set_ylabel("decode tok/s")
    ax.set_ylim(top=max(float(np.median(data[t]["dec"])) for t in tt) * 1.12)
    ax.set_title("D.  Decode throughput from the per-token timestamp arrays "
                 "(tokens_*.jsonl.gz)", fontsize=11.5, fontweight="bold", loc="left")

    fig.suptitle("What does local reasoning cost?  Jetson AGX Orin, llama.cpp, "
                 "DEV-RECENT 37-frame inputs (~12.4k tokens), 120-question sample "
                 "(Q8_0: 40)", fontsize=14.5, fontweight="bold", x=0.012, ha="left", y=1.0)
    save(fig, "s5_local_reasoning_cost")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 6 — accurate history at what cost?
# ─────────────────────────────────────────────────────────────────────────────
APPEND_ONLY = {   # from the decision tables in study_rh3_warmable_representations.md / study_rh4_fixed_stride.md
    "K1": "no", "K3": "no", "H1a": "no", "H1b": "no", "H1c": "no",
    "A": "yes", "B": "only <=256 s", "C": "no", "D1": "yes", "D2": "yes",
}
# (mean history tokens, accuracy, report, denominator) as printed in the owning report.
# StudyRH4's results table is already on the paired n = 839 set used here, so it is the
# matching reference for every cell it lists; H1a/H1b/C and H1c are only reported on 845.
REPORT_S6 = {
    "K1": (12124, 39.81, "study_rh4_fixed_stride.md Results", 839),
    "K3": (12112, 38.62, "study_rh4_fixed_stride.md Results", 839),
    "H1a": (6062, 32.54, "study_rh3_warmable_representations.md", 845),
    "H1b": (3048, 30.06, "study_rh3_warmable_representations.md", 845),
    "H1c": (None, 38.70, "study_rh1_history_ladder.md", 845),
    "A": (5533, 30.51, "study_rh4_fixed_stride.md Results", 839),
    "B": (12583, 40.52, "study_rh4_fixed_stride.md Results", 839),
    "C": (12725, 39.88, "study_rh3_warmable_representations.md", 845),
    "D1": (8188, 36.83, "study_rh4_fixed_stride.md Results", 839),
    "D2": (11325, 39.57, "study_rh4_fixed_stride.md Results", 839),
}


def slide6():
    print("S6 accuracy vs history cost")
    S = "S6"
    cells = {}
    cells.update({k: v for k, v in r1().items() if k in ("K1", "K3")})
    cells.update(rh1())
    cells.update(rh3())
    cells.update({k: {q: r for q, r in v.items() if r["error"] is None}
                  for k, v in rh4().items()})
    order = ["K1", "K3", "H1a", "H1b", "H1c", "A", "B", "C", "D1", "D2"]
    ids = common_ids(*[cells[k] for k in order])
    note(S, f"All ten cells are scored on the same paired set of n={len(ids)} questions "
            "(the intersection with no HTTP-400 over-context error), so one scatter uses one "
            "denominator. Each report scores its own cells on its own denominator "
            "(RH1/RH3 on 845, RH4 on its paired 839), so the per-cell accuracies below differ "
            "slightly from the report values; both are listed.")

    # "history tokens" in RH3/RH4 = prompt tokens minus the question text. RH3 commits the
    # mean text length (no per-question value exists), and a mean of differences is the
    # difference of means, so the cell means are exact up to the 845-vs-839 shift in text mean.
    text_mean = float(js("results/sember/study_rh3/study_rh3_results_h100nvl.json")
                      ["text_only_tokens_mean"])
    rec(S, "mean question-text tokens subtracted to get history tokens", round(text_mean, 2),
        "study_rh3_results_h100nvl.json text_only_tokens_mean",
        "study_rh3_warmable_representations.md", None, unit="tok",
        note="committed over 845; per-question text lengths are not stored")

    pts = []
    for k in order:
        ok = oks(cells[k], ids)
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(ok))
        tok = float(np.mean([cells[k][i]["prompt_tokens"] for i in ids])) - text_mean
        rtok, racc, rsrc, rden = REPORT_S6[k]
        rec(S, f"cell {k} — accuracy on the common paired set (n={len(ids)})", round(a, 2),
            "R1 / RH1 / RH3 / RH4 request records", rsrc, racc,
            tol=TOL_PP if rden == 839 else 1.5,
            note="" if rden == 839 else
                 f"the report scores this cell on {rden}; tolerance widened to 1.5 pp "
                 "for the denominator difference")
        rec(S, f"cell {k} — mean history tokens on the common paired set", round(tok, 0),
            "prompt_tokens − mean question-text tokens", rsrc,
            float(rtok) if rtok else None, unit="tok", tol=2 if rden == 839 else 40,
            note="H1c has no mean-token value in its report; RH1's parity gate puts its "
                 "prompts at K1's on 845/845" if k == "H1c" else "")
        pts.append((k, tok, a, lo, hi, APPEND_ONLY[k]))

    rh3_p0 = js("results/sember/study_rh3/study_rh3_part0_h100nvl.json")
    ext_frac = float(np.mean([r["ext_cached_frac"] for r in rh3_p0["rows"]]))
    rec(S, "RH3 Part 0 — mean reusable fraction when the video is extended", round(100 * ext_frac, 2),
        "study_rh3_part0_h100nvl.json", "study_rh3_warmable_representations.md Part 0", 0.0,
        unit="%", note="uniform re-spacing rewrites the prefix: nothing is reused")
    rh4_p0 = js("results/sember/study_rh4/study_rh4_part0_h100nvl.json")
    reuse = np.array([r["cached_over_first_prompt"] for r in rh4_p0["rows"]], float)
    rec(S, "RH4 Part 0 — reusable fraction after a 30 s append (min over 5 questions)",
        round(100 * float(reuse.min()), 2), "study_rh4_part0_h100nvl.json",
        "study_rh4_fixed_stride.md Part 0 (99.2-99.5% on 5/5)", 99.2, unit="%", tol=0.4,
        note=f"range {100*reuse.min():.1f}-{100*min(reuse.max(),1.0):.1f}% over 5 questions")

    fig, ax = plt.subplots(figsize=(13.5, 8.5))
    shape = {"yes": "o", "no": "s", "only <=256 s": "^"}
    fill = {"yes": C["green"], "no": C["grey"], "only <=256 s": C["yellow"]}
    for k, tok, a, lo, hi, ap in pts:
        ax.errorbar(tok, a, yerr=[[a - lo], [hi - a]], fmt="none",
                    ecolor=C["light_grey"], elinewidth=1.6, capsize=3, zorder=1)
        ax.plot(tok, a, shape[ap], ms=13, color=fill[ap], mec=C["dark"], mew=1.3, zorder=3)
        off = {"K1": (-30, 9), "K3": (-14, -24), "H1c": (34, -2), "B": (-10, 14),
               "C": (30, -6), "D2": (-4, 14)}.get(k, (0, 13))
        ax.annotate(k, (tok, a), textcoords="offset points", xytext=off,
                    ha="center", fontsize=11, fontweight="bold", color=C["dark"])
    ax.set_xlabel("mean history tokens per escalation  (prompt tokens − question text)")
    ax.set_ylabel("accuracy (%)   with Wilson 95% CI")
    ax.set_title("Accurate history at what cost?  Cloud 32B-Instruct (H100 vLLM) on S-EMBER\n"
                 f"all cells scored on the same paired n = {len(ids)}; marker shape = can the "
                 "history be appended to without rewriting the cached prefix",
                 fontsize=13, fontweight="bold", loc="left")
    ax.legend(handles=[
        Line2D([], [], marker="o", ls="none", ms=11, color=C["green"], mec=C["dark"],
               label="append-only: yes"),
        Line2D([], [], marker="^", ls="none", ms=11, color=C["yellow"], mec=C["dark"],
               label="append-only: only while the session is ≤ 256 s"),
        Line2D([], [], marker="s", ls="none", ms=11, color=C["grey"], mec=C["dark"],
               label="append-only: no"),
    ], fontsize=10.5, frameon=False, loc="lower right")
    ax.text(0.015, 0.965,
            "RH3 Part 0: extending the video reuses 0 tokens — uniform re-spacing rewrites "
            "almost every frame\n"
            f"RH4 Part 0: appending 30 s to the fixed-stride history reuses "
            f"≥ {100*reuse.min():.1f}% of the earlier prompt on 5/5 questions",
            transform=ax.transAxes, fontsize=10, va="top", color=C["dark"],
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=C["light_grey"]))
    save(fig, "s6_accuracy_vs_history_cost")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 7 — cost of keeping cloud history ready (RH5 Part A)
# ─────────────────────────────────────────────────────────────────────────────
PARTA_STATES = [
    ("GPU-WARM (GPU-only)", "gpu", "GPU-WARM", C["blue"], {"11k": 0.382, "28k": 0.874}),
    ("GPU-WARM (GPU+host)", "host", "GPU-WARM", C["teal"], {"11k": 0.415, "28k": 0.873}),
    ("HOST-WARM (GPU+host)", "host", "HOST-WARM", C["orange"], {"11k": 0.459, "28k": 1.001}),
    ("COLD re-prefill (GPU-only)", "gpu", "COLD", C["red"], {"11k": 2.445, "28k": 7.367}),
]


def slide7():
    print("S7 warm-state reload cost")
    S = "S7"
    pa = jl("results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz")
    sizes = ["11k", "28k"]
    vals = {}
    for lab, cfg, state, col, reps in PARTA_STATES:
        for sz in sizes:
            v = np.array([r["ttft_s"] for r in pa
                          if r["size"] == sz and r["cfg"] == cfg and r["state"] == state], float)
            vals[(lab, sz)] = v
            rec(S, f"RH5 Part A TTFT median — {lab}, {sz}", round(float(np.median(v)), 3),
                "results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz",
                "study_rh5_host_offload.md Part A", reps[sz], unit="s", tol=0.002,
                note=f"[{v.min():.3f}, {v.max():.3f}] over n={len(v)} requests")
    for sz in sizes:
        hw = float(np.median(vals[("HOST-WARM (GPU+host)", sz)]))
        cold = float(np.median(vals[("COLD re-prefill (GPU-only)", sz)]))
        rec(S, f"host reload vs cold re-prefill speed-up, {sz}", round(cold / hw, 2),
            "study_rh5_partA_h100nvl.jsonl.gz", "study_rh5_host_offload.md Part A",
            5.3 if sz == "11k" else 7.4, unit="x", tol=0.06)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.4), sharey=True)
    for ax, sz in zip(axes, sizes):
        for i, (lab, cfg, state, col, reps) in enumerate(PARTA_STATES):
            v = vals[(lab, sz)]
            m = float(np.median(v))
            ax.bar(i, m, width=0.6, color=col, alpha=0.9, zorder=2)
            ax.errorbar(i, m, yerr=[[m - v.min()], [v.max() - m]], fmt="none",
                        ecolor=C["dark"], elinewidth=1.5, capsize=5, zorder=3)
            ax.text(i, v.max() * 1.10, f"{m:.3f} s", ha="center", fontsize=10,
                    fontweight="bold", color=C["dark"])
        ax.set_xticks(range(len(PARTA_STATES)))
        ax.set_xticklabels([p[0].replace(" (", "\n(") for p in PARTA_STATES], fontsize=9)
        ax.set_yscale("log")
        ax.set_title(f"{sz}-token history   (n = {len(vals[(PARTA_STATES[0][0], sz)])} "
                     "requests per bar)", fontsize=12.5, fontweight="bold", loc="left")
    axes[0].set_ylabel("TTFT (s)   median, bars span min–max")
    fig.suptitle("Cost of keeping a cloud history ready — StudyRH5 Part A, "
                 "H100 32B (Qwen3-VL-32B-Instruct, vLLM, bf16 KV)\n"
                 "one request at a time, D2 fixed-stride history; host tier = vLLM native "
                 "OffloadingConnector, 256 GiB pinned; TTFT only, no network",
                 fontsize=13.5, fontweight="bold", x=0.012, ha="left", y=1.03)
    save(fig, "s7_warm_state_reload_cost")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 8 — many devices sharing the cloud (RH5 Part B, RH2 overlay)
# ─────────────────────────────────────────────────────────────────────────────
def slide8():
    print("S8 fleet sharing the cloud")
    S = "S8"
    rh5 = js("results/cost/study_rh5/study_rh5_results_h100nvl.json")["cells"]
    rh2 = js("results/cost/study_rh2/study_rh2_results_h100nvl.json")["cells"]
    Ds = [4, 8, 16, 24]
    REP = {("GPU", "median"): {4: 0.53, 8: 95.6, 16: 802.0, 24: 1520.0},
           ("HOST", "median"): {4: 0.54, 8: 0.52, 16: 0.60, 24: 0.81},
           ("GPU", "p99"): {4: 1.37, 8: 238.0, 16: 1904.0, 24: 3144.0},
           ("HOST", "p99"): {4: 0.98, 8: 1.15, 16: 1.78, 24: 2.00},
           ("GPU", "hit"): {4: 0.96, 8: 0.72, 16: 0.38, 24: 0.24},
           ("HOST", "hit"): {4: 0.96, 8: 0.97, 16: 0.97, 24: 0.97}}
    series = {}
    for key, label, col in [("GPU", "GPU-only KV", CLOUD_C), ("HOST", "GPU + 256 GiB host KV", C["teal"])]:
        med, p99, hit = [], [], []
        for D in Ds:
            c = rh5[f"RH5_{key}_D{D}"]
            m, p = c["ttft_s"]["median"], c["ttft_s"]["p99"]
            h = c["esc_hit_token_weighted"]
            med.append(m); p99.append(p); hit.append(h)
            tol = {"median": 0.6, "p99": 0.6, "hit": 0.006}
            rec(S, f"RH5 Part B {label} D={D} — warm escalation TTFT median", round(m, 3),
                "study_rh5_results_h100nvl.json", "study_rh5_host_offload.md Part B",
                REP[(key, "median")][D], unit="s", tol=max(tol["median"], abs(REP[(key, "median")][D]) * 0.01))
            rec(S, f"RH5 Part B {label} D={D} — warm escalation TTFT p99", round(p, 3),
                "study_rh5_results_h100nvl.json", "study_rh5_host_offload.md Part B",
                REP[(key, "p99")][D], unit="s", tol=max(0.6, abs(REP[(key, "p99")][D]) * 0.01))
            rec(S, f"RH5 Part B {label} D={D} — escalation token hit rate", round(h, 4),
                "study_rh5_results_h100nvl.json", "study_rh5_host_offload.md Part B",
                REP[(key, "hit")][D], unit="fraction", tol=0.006)
        series[label] = (med, p99, hit, col)

    rh2_D = [8, 12, 16, 24]
    rh2_med = [rh2[f"RH2_WARM_D{D}_r100"]["warm"]["ttft_s"]["median"] for D in rh2_D]
    rh2_p99 = [rh2[f"RH2_WARM_D{D}_r100"]["warm"]["ttft_s"]["p99"] for D in rh2_D]
    rh2_hit = [rh2[f"RH2_WARM_D{D}_r100"]["warm"]["hit_token_weighted"] for D in rh2_D]
    rec(S, "RH2 overlay (A-format history, GPU-only) D=16 — warm escalation TTFT median",
        round(rh2_med[2], 3), "study_rh2_results_h100nvl.json",
        "study_rh5_host_offload.md (RH2's A-format knee: 7.9 s at D=16)", 7.9, unit="s", tol=0.01)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.6))
    ax = axes[0]
    for label, (med, p99, hit, col) in series.items():
        ax.plot(Ds, med, "-o", color=col, lw=2.4, ms=8, label=f"{label} — median")
        ax.plot(Ds, p99, "--s", color=col, lw=1.6, ms=6, alpha=0.75, label=f"{label} — p99")
    ax.plot(rh2_D, rh2_med, "-.D", color=C["grey"], lw=1.8, ms=6,
            label="StudyRH2 A-format history, GPU-only — median")
    ax.axhspan(0, 1.5, color=C["green"], alpha=0.10, zorder=0)
    ax.text(24, 1.42, "pre-registered bound: median ≤ 1.5 s  ", fontsize=8.6,
            color=C["green"], va="top", ha="right", fontweight="bold")
    ax.set_yscale("log")
    ax.set_xlabel("D — warm devices sharing the GPU")
    ax.set_ylabel("warm escalation TTFT (s, log)")
    ax.set_xticks(sorted(set(Ds + rh2_D)))
    ax.set_title("A.  Warm escalation latency vs fleet size", fontsize=12.5,
                 fontweight="bold", loc="left")
    ax.legend(fontsize=8.6, frameon=False, loc="upper left")

    ax = axes[1]
    for label, (med, p99, hit, col) in series.items():
        ax.plot(Ds, hit, "-o", color=col, lw=2.4, ms=8, label=label)
    ax.plot(rh2_D, rh2_hit, "-.D", color=C["grey"], lw=1.8, ms=6,
            label="StudyRH2 A-format history, GPU-only")
    ax.set_xlabel("D — warm devices sharing the GPU")
    ax.set_ylabel("escalation token hit rate (token-weighted)")
    ax.set_ylim(0, 1.05)
    ax.set_xticks(sorted(set(Ds + rh2_D)))
    ax.set_title("B.  Why: the prefix the escalation can reuse", fontsize=12.5,
                 fontweight="bold", loc="left")
    ax.legend(fontsize=8.8, frameon=False, loc="lower left")

    fig.suptitle("Many devices sharing one cloud GPU — StudyRH5 Part B, H100 32B "
                 "(vLLM), D2 fixed-stride histories, 15-min window, escalation rate 1.0\n"
                 "dashed grey = StudyRH2, a DIFFERENT history format (A: 1 fps, 160×128, "
                 "≈4.7k tokens) on GPU-only KV — shown as a reference, not a matched condition",
                 fontsize=13, fontweight="bold", x=0.012, ha="left", y=1.04)
    save(fig, "s8_fleet_sharing_cloud")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 9 (backup) — RH6: where the offload configuration breaks
# ─────────────────────────────────────────────────────────────────────────────
def slide9():
    print("S9 RH6 ingestion knee")
    S = "S9"
    cells = js("results/cost/study_rh6/study_rh6_results_h100nvl.json")["cells"]
    Ds = [32, 48, 64, 96]
    REP_MED = {32: 0.56, 48: 654.45, 64: 1114.08, 96: 1722.41}
    REP_P99 = {32: 1.91, 48: 881.40, 64: 1528.17, 96: 2425.95}
    med, p99 = [], []
    for D in Ds:
        c = cells[f"RH6_A_D{D}"]
        m, p = c["esc_ttft_s"]["median"], c["esc_ttft_s"]["p99"]
        med.append(m); p99.append(p)
        rec(S, f"RH6 Part A D={D} (256 GiB host) — warm escalation TTFT median", round(m, 2),
            "study_rh6_results_h100nvl.json", "study_rh6_offload_knee_levers.md Per-cell metrics",
            REP_MED[D], unit="s", tol=max(0.02, REP_MED[D] * 0.005))
        rec(S, f"RH6 Part A D={D} — warm escalation TTFT p99", round(p, 2),
            "study_rh6_results_h100nvl.json", "study_rh6_offload_knee_levers.md",
            REP_P99[D], unit="s", tol=max(0.02, REP_P99[D] * 0.005))
    cC = cells["RH6_C_D48"]
    c_med, c_p99 = cC["esc_ttft_s"]["median"], cC["esc_ttft_s"]["p99"]
    rec(S, "RH6 Part C D=48 (64 GiB host) — warm escalation TTFT median", round(c_med, 2),
        "study_rh6_results_h100nvl.json", "study_rh6_offload_knee_levers.md Part C",
        3363.97, unit="s", tol=1.0)
    rec(S, "RH6 Part C D=48 (64 GiB host) — warm miss fraction", round(cC["warm_miss_frac"], 4),
        "study_rh6_results_h100nvl.json", "study_rh6_offload_knee_levers.md Part C (88%)",
        0.88, unit="fraction", tol=0.01)

    qbars = []
    for D in (32, 48):
        d = cells[f"RH6_A_D{D}"]["diagnostics"]
        up = d["upstream_of_engine_window"]["median"]
        eng = d["engine_queue_window"]["median"]
        gpu = d["gpu_util_window"]["median"]
        qbars.append((D, up, eng, gpu))
        rec(S, f"RH6 A D={D} — median queue upstream of the engine (API server)", round(up, 1),
            "study_rh6_results_h100nvl.json diagnostics",
            "study_rh6_offload_knee_levers.md Diagnostics",
            1.0 if D == 32 else 1301.0, unit="requests", tol=0.6)
        rec(S, f"RH6 A D={D} — median engine queue (running + waiting)", round(eng, 1),
            "study_rh6_results_h100nvl.json diagnostics",
            "study_rh6_offload_knee_levers.md Diagnostics", 0.0, unit="requests", tol=0.6)
        rec(S, f"RH6 A D={D} — median GPU SM utilisation in window", round(gpu, 1),
            "study_rh6_results_h100nvl.json diagnostics",
            "study_rh6_offload_knee_levers.md Diagnostics",
            58.0 if D == 32 else 0.0, unit="%", tol=0.6)

    fig, axes = plt.subplots(1, 2, figsize=(15, 6.6))
    ax = axes[0]
    ax.plot(Ds, med, "-o", color=C["teal"], lw=2.4, ms=9, label="median (256 GiB host buffer)")
    ax.plot(Ds, p99, "--s", color=C["teal"], lw=1.6, ms=7, alpha=0.75, label="p99 (256 GiB)")
    ax.plot([48], [c_med], marker="X", ms=16, color=C["red"], ls="none",
            label="Part C: 64 GiB host buffer, median")
    ax.plot([48], [c_p99], marker="x", ms=13, mew=3, color=C["red"], ls="none",
            label="Part C: 64 GiB host buffer, p99")
    ax.annotate("D* = 48", xy=(48, med[1]), xytext=(55, med[1] * 0.18),
                arrowprops=dict(arrowstyle="->", color=C["dark"], lw=1.5),
                fontsize=12, fontweight="bold", color=C["dark"])
    ax.axhspan(0, 1.5, color=C["green"], alpha=0.10, zorder=0)
    ax.set_yscale("log")
    ax.set_xlabel("D — warm devices sharing the GPU")
    ax.set_ylabel("warm escalation TTFT (s, log)")
    ax.set_xticks(Ds)
    ax.set_title("A.  The offload configuration's own knee", fontsize=12.5,
                 fontweight="bold", loc="left")
    ax.legend(fontsize=9, frameon=False, loc="lower right")

    ax = axes[1]
    x = np.arange(len(qbars))
    ax.bar(x - 0.2, [q[1] for q in qbars], width=0.38, color=C["orange"],
           label="queued upstream of the engine (accepted by the API server)")
    ax.bar(x + 0.2, [q[2] for q in qbars], width=0.38, color=C["blue"],
           label="queued in the engine (running + waiting)")
    for i, q in enumerate(qbars):
        ax.text(i - 0.2, max(q[1], 0.6) * 1.3, f"{q[1]:,.0f}", ha="center",
                fontsize=11, fontweight="bold", color=C["dark"])
        ax.text(i + 0.2, 0.08, f"{q[2]:,.0f}", ha="center", va="bottom",
                fontsize=11, fontweight="bold", color=C["blue"])
        ax.text(i, 0.016, f"GPU SM util {q[3]:.0f}%", ha="center", fontsize=10,
                color=C["dark"], style="italic")
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set_ylim(0, 4000)
    ax.set_xticks(x)
    ax.set_xticklabels([f"D = {q[0]}" for q in qbars], fontsize=12)
    ax.set_ylabel("in-window median queue depth (requests, symlog)")
    ax.set_title("B.  Where the backlog sits at the knee", fontsize=12.5,
                 fontweight="bold", loc="left")
    ax.legend(fontsize=9, frameon=False, loc="upper left", bbox_to_anchor=(0.0, 0.88))

    fig.suptitle("Backup — StudyRH6: the knee of the GPU+host configuration is an API "
                 "ingestion bottleneck (protocol), not GPU\n"
                 "H100 32B, vLLM, D2 fixed-stride histories; at D* = 48 the GPU is idle and "
                 "the engine queue is empty while 1,301 requests wait in the API server",
                 fontsize=13, fontweight="bold", x=0.012, ha="left", y=1.04)
    save(fig, "s9_rh6_ingestion_knee")


# ─────────────────────────────────────────────────────────────────────────────
# numbers.md
# ─────────────────────────────────────────────────────────────────────────────
SLIDE_TITLES = {
    "S1": ("s1_device_vs_cloud_accuracy", "Does the cloud model improve accuracy?"),
    "S2": ("s2_thinking_vs_instruct", "Does longer reasoning help?"),
    "S3": ("s3_capability_vs_evidence", "Model capability vs historical evidence"),
    "S4": ("s4_escalation", "Can we predict when to escalate?"),
    "S5": ("s5_local_reasoning_cost", "What does local reasoning cost?"),
    "S6": ("s6_accuracy_vs_history_cost", "Accurate history at what cost?"),
    "S7": ("s7_warm_state_reload_cost", "Cost of keeping cloud history ready"),
    "S8": ("s8_fleet_sharing_cloud", "Many devices sharing the cloud"),
    "S9": ("s9_rh6_ingestion_knee", "Backup — RH6 offload knee"),
}


def fmt_val(n):
    v = n["value"]
    if v is None:
        return "—"
    u = n["unit"]
    if u == "pp":
        return f"{v:+.2f} pp" if "diff" in n["quantity"] or "DiD" in n["quantity"] else f"{v:.2f}"
    if u in ("%",):
        return f"{v:.2f}%"
    if u == "s":
        return f"{v:.3f} s" if abs(v) < 10 else f"{v:,.2f} s"
    if u == "tok":
        return f"{v:,.0f}"
    if u == "x":
        return f"{v:.2f}x"
    if u in ("AUROC", "fraction"):
        return f"{v:.4f}"
    if u == "requests":
        return f"{v:,.1f}"
    return f"{v}"


def md_escape(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def write_numbers():
    import subprocess
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                             capture_output=True, text=True).stdout.strip()[:12]
    except Exception:
        sha = "unknown"

    L = []
    L.append("# Advisor plots — plotted numbers and their sources (2026-10-23)\n")
    L.append(f"Generated by `experiments/figures/make_advisor_plots_2026_10.py` at commit "
             f"`{sha}`. CPU only; no GPU was used and no inference was run.\n")
    L.append("Every value in this file is **computed from the committed result files**. "
             "The *report* column names the committed report the value should match, and "
             "*report value* is the figure printed there. A difference larger than the "
             "stated tolerance (0.1 pp by default) is flagged as a MISMATCH and is listed "
             "below rather than silently reconciled.\n")
    L.append("Confidence intervals: S-EMBER uses the video-clustered bootstrap imported "
             "from `experiments/sember/study_o_q4_analyze.py` (2,000 resamples, seed 0); "
             "ERQA and MV-RoboBench use a paired question-level bootstrap (2,000 resamples, "
             "seed 0). AUROC CIs reuse `experiments/erqa/r4_analyse.py`'s own `auroc` and "
             "`boot_ci` and consume the random stream in that script's order, so they "
             "reproduce its published intervals digit for digit.\n")

    L.append("## Mismatches\n")
    if MISMATCHES:
        L.append("| slide | quantity | computed | report | Δ | report source |")
        L.append("|---|---|---|---|---|---|")
        for sl, q, v, rv, d, rp, nt in MISMATCHES:
            L.append(f"| {sl} | {md_escape(q)} | {v} | {rv} | {d:+.3f} | {md_escape(rp)} |")
        L.append("")
    else:
        L.append("**None.** Every plotted quantity that has a committed report value "
                 "reproduces it within tolerance.\n")

    if NOTES:
        L.append("## Notes on denominators and definitions\n")
        for sl, t in NOTES:
            L.append(f"- **{sl}** — {t}")
        L.append("")

    L.append("## Deliberate differences from the reports\n")
    L.append("These are specified differences, not discrepancies:\n")
    L.append("- **S4 cloud tier.** The escalation curves and the oracle crossings for ERQA "
             "and MV-RoboBench use **arm C (32B-Instruct)** as the cloud tier, as specified "
             "for this deck. `reports/r4_device_signals_prep.md` uses **arm D "
             "(32B-Thinking)**, so its escalation table (gap-closed −0.261 on ERQA/Instruct, "
             "etc.) is not the same quantity and is not cross-checked here. The AUROCs are "
             "device-side only and so are unaffected — all 23 reproduce exactly.")
    L.append("- **S2 reshuffling.** `% of answers changed by thinking` is plotted as the "
             "fraction of questions whose predicted letter changed. The S2 and R reports use "
             "the phrase \"answers changed by thinking\" for the McNemar discordance b+c "
             "(correctness flips), a smaller quantity. Both are recorded; the b+c rows are "
             "the ones cross-checked.")
    L.append("- **S6 denominator.** All ten history cells are scored on one common paired "
             "set so a single scatter is internally consistent. StudyRH4's table uses the "
             "same paired set and matches exactly; H1a, H1b, C and H1c are only published on "
             "845, so those four rows carry a widened tolerance and are labelled.")
    L.append("- **S3 denominators.** The device panel uses the pre-registered `qt > 120 s` "
             "subset (n = 678) as `reports/device_tier_accuracy_llamacpp.md` does; the cloud "
             "panels use the denominators of R1 and RH4. Each panel states its own n.\n")

    L.append("## Backend and hardware labels used on the panels\n")
    L.append("| label | meaning |")
    L.append("|---|---|")
    for a, b in [
        ("A6000 llama.cpp F16", "flash / RTX A6000 GPU 1, llama.cpp c0fd786, GGUF F16, DEV-RECENT or DEV-RICH image inputs"),
        ("Orin llama.cpp F16", "Jetson AGX Orin 64 GB, llama.cpp c0fd786 (sm_87), GGUF F16, DEV-RECENT image inputs"),
        ("A6000 HF sdpa", "flash / RTX A6000, HuggingFace transformers, attn_implementation = sdpa"),
        ("H100 HF fa2", "sn4622120321 GPU 3, HuggingFace transformers, flash_attention_2, bf16"),
        ("H100 vLLM", "sn4622120321 GPU 3, vLLM 0.31.0+cu129, bf16 weights and KV, prefix caching as stated per study"),
    ]:
        L.append(f"| {a} | {b} |")
    L.append("")

    for sl in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]:
        rows = [n for n in NUMBERS if n["slide"] == sl]
        if not rows:
            continue
        stem, title = SLIDE_TITLES[sl]
        L.append(f"## {sl} — {title}\n")
        L.append(f"Files: `{stem}.pdf`, `{stem}.png`\n")
        L.append("| quantity | value | source file | report | report value | Δ | check |")
        L.append("|---|---|---|---|---|---|---|")
        for n in rows:
            rv = "—" if n["report_value"] is None else f"{n['report_value']}"
            q = md_escape(n["quantity"])
            if n["note"]:
                q += f"<br><sub>{md_escape(n['note'])}</sub>"
            L.append(f"| {q} | {fmt_val(n)} | `{md_escape(n['source'])}` | "
                     f"{md_escape(n['report'])} | {rv} | {n['delta'] or '—'} | {n['status']} |")
        L.append("")

    (OUT_DIR / "numbers.md").write_text("\n".join(L) + "\n")
    print(f"  wrote numbers.md ({len(NUMBERS)} values, {len(MISMATCHES)} mismatches)")


def main():
    print(f"writing to {OUT_DIR}")
    slide1()
    slide2()
    slide3()
    slide4()
    slide5()
    slide6()
    slide7()
    slide8()
    slide9()
    write_numbers()
    total = sum(f.stat().st_size for f in OUT_DIR.iterdir() if f.is_file())
    print(f"\n{len(list(OUT_DIR.iterdir()))} files, {total/1e6:.1f} MB total")
    if MISMATCHES:
        print(f"\n{len(MISMATCHES)} MISMATCH(es) — see numbers.md")
        for sl, q, v, rv, d, rp, nt in MISMATCHES:
            print(f"  [{sl}] {q}: computed {v} vs report {rv} ({d:+.3f})")
    else:
        print("\nno mismatches: every cross-checked value reproduces its report")


if __name__ == "__main__":
    main()
