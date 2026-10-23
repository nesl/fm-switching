#!/usr/bin/env python3
"""
Advisor story deck for FM-switching, 2026-10-23.

CPU-only, no GPU, no new inference. Loaders and statistics helpers are imported
from make_advisor_plots_2026_10.py; this script only chooses what to show.

One plot per slide, 16:9, at most four bars or lines per panel. Writes PDF + PNG
per slide to figures/advisor_2026_10_23/story/, plus story_numbers.md (every
plotted number with its source file and the report value it must match) and
slides_text.md (the text-only slides, with numbers filled from the registry).
"""

import sys
import textwrap
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_advisor_plots_2026_10 as M  # noqa: E402
from make_advisor_plots_2026_10 import (  # noqa: E402
    acc, common_ids, curve_from_order, device_cell, erqa_ok, jl, md_escape,
    oks, oracle_order, orin_latency, paired_diff, preds, r1, r4_rows,
    random_curve, sember_diff, study_q_arm, study_r_arm, vids_of, wilson,
    ORIN_REPORT, R4, NBOOT, SEED,
)

OUT = REPO / "figures" / "advisor_2026_10_23" / "story"
OUT.mkdir(parents=True, exist_ok=True)

DEVICE = "#648FFF"      # device = blue
CLOUD = "#DC267F"       # cloud = magenta
CLOUD_LT = "#F5A0C6"    # cloud, recent-window history
RANDOM = "#222222"      # random = black dashed
ORACLE = "#117733"      # oracle = green
GREY = "#8C8C8C"
DARK = "#1A1A1A"

FIGSIZE = (16, 9)
DPI = 120               # 1920 x 1080

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 17,
    "axes.labelsize": 18,
    "axes.titlesize": 19,
    "xtick.labelsize": 16,
    "ytick.labelsize": 16,
    "legend.fontsize": 16,
})

VALS = {}


def rec(key, slide, quantity, value, source, report=None, report_value=None,
        unit="pp", tol=0.1, note=""):
    """Record into the shared registry and keep the value under a short key."""
    M.rec(slide, quantity, value, source, report, report_value, unit, tol, note)
    if key:
        VALS[key] = value
    return value


def finish(fig, stem, source_line, title):
    fig.suptitle(title, fontsize=25 if len(title) <= 58 else 21,
                 fontweight="bold", x=0.035, ha="left", y=0.962)
    wrapped = "\n".join(textwrap.wrap(" ".join(source_line.split()), width=168))
    fig.text(0.035, 0.018, wrapped, fontsize=12, color=GREY, ha="left", va="bottom")
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.png", dpi=DPI)
    plt.close(fig)
    print(f"  saved {stem}.pdf + {stem}.png")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 2 — a larger cloud model is more accurate, and faster
# ─────────────────────────────────────────────────────────────────────────────
ORIN_TAGS = [("4bi_f16_F16", "4B-I", 34.2), ("4bt_f16_F16", "4B-T", 33.3),
             ("8bi_f16_F16", "8B-I", 35.0), ("8bt_f16_F16", "8B-T", 37.0)]

# label placement around each scatter point, chosen so labels and error bars do not collide
T2_LABEL_SIDE = {"4B-I": "above", "8B-I": "below", "4B-T": "above", "8B-T": "below"}

# RH5 Part A, 11k-token history, TTFT only, no network (study_rh5_host_offload.md Part A).
RH5_A_11K = [("GPU-WARM", "gpu", 0.382), ("COLD", "gpu", 2.445)]


def slide2():
    print("story 2 — device vs cloud accuracy and latency")
    S = "T2"
    K = r1()["K1"]
    orin = {tag: {r["question_id"]: r for r in orin_latency(tag)} for tag, _, _ in ORIN_TAGS}
    ids = common_ids(*orin.values(), K)
    n = len(ids)
    rec(None, S, "S-EMBER question block — n", n,
        "results/device/latency_sember_*_f16_F16.jsonl ∩ study_r1 K1", unit="questions",
        note="the Orin's own 120-question sample; every point below is on these questions")

    pts = []
    for tag, lab, repv in ORIN_TAGS:
        d = orin[tag]
        ok = np.array([bool(d[i]["correct"]) for i in ids], bool)
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), n)
        lat = float(np.median([d[i]["total_latency_s"] for i in ids]))
        rec(f"t2_acc_{lab}", S, f"S-EMBER accuracy — device {lab} (Jetson Orin llama.cpp F16)",
            round(a, 2), f"results/device/latency_sember_{tag}.jsonl",
            "device_latency_sember.md §Secondary accuracy", repv,
            tol=0.6 if lab.startswith("8B") else 0.1,
            note="report rounds the 8B figures to whole %" if lab.startswith("8B") else "")
        rec(f"t2_lat_{lab}", S, f"S-EMBER median full-response latency — device {lab} "
            "(Jetson Orin llama.cpp F16)", round(lat, 2),
            f"results/device/latency_sember_{tag}.jsonl", "device_latency_sember.md",
            ORIN_REPORT[tag]["total"], unit="s", tol=0.1,
            note=f"Wilson 95% [{lo:.1f}, {hi:.1f}] on accuracy")
        pts.append((lab, lat, a, lo, hi))

    ok_c = np.array([bool(K[i]["correct"]) for i in ids], bool)
    a_c = acc(ok_c)
    lo_c, hi_c = wilson(int(ok_c.sum()), n)
    rec("t2_acc_32B-I", S, "S-EMBER accuracy — cloud 32B-I RICH, R1 K1 (H100 vLLM)",
        round(a_c, 2), "study_r1_requests_h100nvl.jsonl.gz cell=K1 mode=batched",
        "study_r1_cloud32b_sember.md §Accuracy (39.53% on all 845)", None,
        note=f"on this 120-question block only; Wilson 95% [{lo_c:.1f}, {hi_c:.1f}]")

    single = [r for r in jl("results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
              if r["cell"] == "K1" and r["mode"] == "single"]
    lat_c = float(np.median([r["latency_s"] for r in single]))
    rec("t2_lat_32B-I", S, "S-EMBER sequential single-request latency — cloud 32B-I K1 "
        "(H100 vLLM, mode=single, n=50, prefix caching off)", round(lat_c, 2),
        "study_r1_requests_h100nvl.jsonl.gz cell=K1 mode=single",
        "study_r1_cloud32b_sember.md §Clean single-request latency (K1 total median)",
        4.28, unit="s", tol=0.02,
        note="first 50 questions, one request at a time; includes HTTP transfer of the PNG "
             "frames, so it is NOT the no-network TTFT plotted as the bar")

    pa = jl("results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz")
    bar = {}
    for state, cfg, repv in RH5_A_11K:
        v = np.array([r["ttft_s"] for r in pa
                      if r["size"] == "11k" and r["cfg"] == cfg and r["state"] == state], float)
        m = float(np.median(v))
        bar[state] = m
        rec(f"t2_ttft_{state}", S, f"RH5 Part A TTFT median, 11k history — {state} "
            "(H100 vLLM, GPU-only server, no network)", round(m, 3),
            "results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz",
            "study_rh5_host_offload.md Part A", repv, unit="s", tol=0.002,
            note=f"min–max [{v.min():.3f}, {v.max():.3f}] over n={len(v)}")

    # ---- ERQA panel ----
    di = {r["qid"]: r for r in r4_rows("erqa", "instruct")}
    q8 = study_q_arm("D")
    cC = study_r_arm("C")
    eids = common_ids(di, q8, cC)
    erqa = []
    for lab, d, src, rep, repv, tier in [
        ("4B-I\ndevice", di, "results/erqa/r4_signals/r4_erqa_instruct.jsonl",
         "r4_device_signals_prep.md §Escalation", 42.0, DEVICE),
        ("8B-I\ndevice", q8, "results/erqa/study_q/study_q_trials.jsonl arm=D",
         "study_q_retry_vs_scale_erqa.md", 42.5, DEVICE),
        ("32B-I\ncloud", cC, "results/erqa/study_r/study_r_trials_h100nvl_fa2.jsonl arm=C",
         "study_r_device_vs_cloud.md §Flash-attn", 46.8, CLOUD),
    ]:
        ok = erqa_ok(d, eids)
        a = acc(ok)
        lo, hi = wilson(int(ok.sum()), len(eids))
        key = "t2_erqa_" + lab.split("\n")[0]
        rec(key, S, f"ERQA accuracy — {lab.replace(chr(10), ' ')}", round(a, 2), src, rep, repv,
            note=f"Wilson 95% [{lo:.1f}, {hi:.1f}], n={len(eids)}")
        erqa.append((lab, a, lo, hi, tier))
    rec("t2_erqa_n", S, "ERQA — n", len(eids), "common question_ids across the three arms",
        unit="questions")
    M.note(S, "ERQA device arms are A6000 HF sdpa and the cloud arm is H100 HF fa2, so the "
              "ERQA device↔cloud gap is BACKEND-MISMATCHED, exactly as "
              "reports/study_r_device_vs_cloud.md labels it. ERQA device latency was never "
              "measured, so only S-EMBER carries a latency axis.")

    # ---- figure ----
    fig = plt.figure(figsize=FIGSIZE)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.95, 1.0], wspace=0.26,
                          left=0.065, right=0.975, top=0.845, bottom=0.185)

    ax = fig.add_subplot(gs[0])
    for lab, lat, a, lo, hi in pts:
        ax.errorbar(lat, a, yerr=[[a - lo], [hi - a]], fmt="o", ms=13, color=DEVICE,
                    ecolor=DEVICE, elinewidth=2, capsize=5, zorder=3)
        above = T2_LABEL_SIDE[lab] == "above"
        ax.annotate(lab, (lat, hi if above else lo), textcoords="offset points",
                    xytext=(0, 9 if above else -9), ha="center",
                    va="bottom" if above else "top",
                    fontsize=17, fontweight="bold", color=DEVICE)
    ax.plot([bar["GPU-WARM"], bar["COLD"]], [a_c, a_c], color=CLOUD, lw=7,
            solid_capstyle="butt", alpha=0.45, zorder=2)
    ax.errorbar(lat_c, a_c, yerr=[[a_c - lo_c], [hi_c - a_c]], fmt="o", ms=13, color=CLOUD,
                ecolor=CLOUD, elinewidth=2, capsize=5, zorder=4)
    ax.annotate("32B-I", (lat_c, a_c), textcoords="offset points", xytext=(0, 17),
                ha="center", fontsize=17, fontweight="bold", color=CLOUD)
    ax.annotate(f"TTFT, no network:\n{bar['GPU-WARM']:.2f} s warm → {bar['COLD']:.2f} s cold",
                xy=((bar["GPU-WARM"] * bar["COLD"]) ** 0.5, a_c),
                textcoords="offset points", xytext=(0, 42), ha="center",
                fontsize=15, color=CLOUD,
                arrowprops=dict(arrowstyle="->", color=CLOUD, lw=1.6))
    ax.annotate(f"one request at a time,\nwith frame upload: {lat_c:.2f} s",
                xy=(lat_c, a_c - (a_c - lo_c) - 0.4), textcoords="offset points",
                xytext=(0, -52), ha="center", fontsize=15, color=CLOUD,
                arrowprops=dict(arrowstyle="->", color=CLOUD, lw=1.6))
    ax.set_xscale("log")
    ax.set_xlim(0.28, 95)
    ax.set_xticks([0.5, 1, 2, 5, 10, 20, 50])
    ax.set_xticklabels(["0.5", "1", "2", "5", "10", "20", "50"])
    ax.set_xlabel("median full-response latency (s, log)")
    ax.set_ylabel("S-EMBER accuracy (%)")
    ax.set_ylim(22, 58)
    ax.set_title(f"S-EMBER, the same {n} questions for every point", fontsize=19, loc="left")
    ax.legend(handles=[Line2D([], [], color=DEVICE, marker="o", ls="none", ms=11,
                              label="device (Jetson Orin)"),
                       Line2D([], [], color=CLOUD, marker="o", ls="none", ms=11,
                              label="cloud (H100)")],
              frameon=False, loc="lower left")

    ax2 = fig.add_subplot(gs[1])
    xs = np.arange(len(erqa))
    ax2.bar(xs, [e[1] for e in erqa], width=0.6, color=[e[4] for e in erqa], zorder=2)
    ax2.errorbar(xs, [e[1] for e in erqa],
                 yerr=[[e[1] - e[2] for e in erqa], [e[3] - e[1] for e in erqa]],
                 fmt="none", ecolor=DARK, elinewidth=2, capsize=6, zorder=3)
    for x, e in zip(xs, erqa):
        ax2.text(x, e[3] + 1.0, f"{e[1]:.1f}", ha="center", fontsize=17, fontweight="bold")
    ax2.set_xticks(xs)
    ax2.set_xticklabels([e[0] for e in erqa])
    ax2.set_ylabel("ERQA accuracy (%)")
    ax2.set_ylim(0, 60)
    ax2.set_title(f"ERQA, {len(eids)} questions", fontsize=19, loc="left")
    ax2.text(0.5, 0.985, "accuracy only;\ndevice latency not measured on ERQA",
             transform=ax2.transAxes, ha="center", va="top", fontsize=14, color=GREY,
             style="italic")

    finish(fig, "t2_cloud_accuracy_and_latency",
           f"S-EMBER: device = Jetson AGX Orin, llama.cpp F16, DEV-RECENT 37-frame inputs, "
           f"n={n};  cloud = H100 NVL, Qwen3-VL-32B-Instruct, vLLM, RICH history (R1 K1), "
           f"single-request latency n=50;  TTFT bar = StudyRH5 Part A, 11k history, no network.   "
           f"ERQA: device 4B/8B = A6000 HF sdpa, cloud 32B = H100 HF fa2, n={len(eids)} "
           f"(backend-mismatched).  Error bars: Wilson 95%.",
           "A larger cloud model is more accurate — and faster")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 3 — size and history
# ─────────────────────────────────────────────────────────────────────────────
def slide3():
    print("story 3 — size and history")
    S = "T3"
    K = r1()
    C1 = device_cell("C1")
    ids = common_ids(C1, K["K1"], K["K3"])
    covered = np.array([bool(K["K3"][i]["evidence_covered"]) for i in ids])
    vids = vids_of(C1, ids)
    dev = oks(C1, ids)
    rec_ = oks(K["K3"], ids)
    full = oks(K["K1"], ids)
    rec(None, S, "S-EMBER — n", len(ids), "accuracy_C1.jsonl ∩ study_r1 K1,K3",
        unit="questions")

    REP = {
        ("miss", "K3"): 24.7, ("miss", "K1"): 42.3,
        ("cover", "K3"): 40.1, ("cover", "K1"): 39.2,
    }
    groups = []
    for gname, mask, title in [("miss", ~covered, "evidence NOT covered\nby the recent window"),
                               ("cover", covered, "evidence covered\nby the recent window")]:
        ns = int(mask.sum())
        rec(f"t3_n_{gname}", S, f"S-EMBER {gname} stratum — n", ns,
            "study_r1 K3 evidence_covered", unit="questions")
        bars = []
        for blab, arr, src, repv, col in [
            ("device 4B-I\n(recent window)", dev, "results/device/accuracy_C1.jsonl", None, DEVICE),
            ("cloud 32B-I\n(recent window)", rec_, "study_r1 K3", REP[(gname, "K3")], CLOUD_LT),
            ("cloud 32B-I\n(full history)", full, "study_r1 K1", REP[(gname, "K1")], CLOUD),
        ]:
            a = 100.0 * float(arr[mask].mean())
            key = f"t3_{gname}_" + ("dev" if "device" in blab else
                                    ("k3" if "recent" in blab else "k1"))
            rec(key, S, f"S-EMBER {gname} stratum — {blab.replace(chr(10), ' ')} accuracy",
                round(a, 2), src,
                "study_r1_cloud32b_sember.md §Accuracy" if repv is not None else None, repv,
                tol=0.1, note="device arm is A6000 llama.cpp F16 DEV-RECENT; the R1 report's "
                              "4B-I × RECENT row is a different (HF fa2) run"
                              if repv is None else "")
            bars.append((blab, a, col))
        d_size, lo_s, hi_s, _ = sember_diff(dev[mask], rec_[mask], vids[mask])
        d_hist, lo_h, hi_h, _ = sember_diff(rec_[mask], full[mask], vids[mask])
        rec(f"t3_{gname}_size", S, f"S-EMBER {gname} stratum — model size "
            "(cloud 32B-I recent − device 4B-I recent)", round(d_size, 2),
            "accuracy_C1.jsonl + study_r1 K3",
            note=f"[{lo_s:+.2f}, {hi_s:+.2f}]; video-clustered bootstrap 2,000 seed 0; "
                 "BACKEND-MISMATCHED (device llama.cpp F16 vs cloud vLLM)")
        rec(f"t3_{gname}_hist", S, f"S-EMBER {gname} stratum — history "
            "(cloud 32B-I full − cloud 32B-I recent, K1 − K3)", round(d_hist, 2),
            "study_r1 K1, K3",
            "study_r1_cloud32b_sember.md HISTORY GATES THE CLOUD",
            17.53 if gname == "miss" else -0.94,
            note=f"[{lo_h:+.2f}, {hi_h:+.2f}]; video-clustered bootstrap 2,000 seed 0")
        VALS[f"t3_{gname}_hist_ci"] = (lo_h, hi_h)
        VALS[f"t3_{gname}_size_ci"] = (lo_s, hi_s)
        groups.append((title, ns, bars, (d_size, lo_s, hi_s), (d_hist, lo_h, hi_h)))

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.075, right=0.97, top=0.82, bottom=0.27)
    width = 0.62
    centres = []
    for gi, (title, ns, bars, size, hist) in enumerate(groups):
        x0 = gi * 4.4
        xs = [x0, x0 + 1.0, x0 + 2.0]
        for x, (blab, a, col) in zip(xs, bars):
            ax.bar(x, a, width=width, color=col, zorder=2)
            ax.text(x, a + 1.1, f"{a:.1f}", ha="center", fontsize=17, fontweight="bold")
        top = max(b[1] for b in bars)
        for (xa, xb), (d, lo, hi), name, yoff in [
                ((xs[0], xs[1]), size, "model size", 8.0),
                ((xs[1], xs[2]), hist, "history", 23.0)]:
            y = top + yoff
            ax.annotate("", xy=(xb, y), xytext=(xa, y),
                        arrowprops=dict(arrowstyle="->", color=DARK, lw=2.2))
            ax.text((xa + xb) / 2, y + 2.4,
                    f"{name}\n{d:+.1f} pp  [{lo:+.1f}, {hi:+.1f}]",
                    ha="center", fontsize=16, fontweight="bold", color=DARK,
                    linespacing=1.3)
        centres.append((x0 + 1.0, f"{title}\n(n = {ns})"))
        for x, (blab, a, col) in zip(xs, bars):
            ax.text(x, -3.2, blab, ha="center", va="top", fontsize=15, color=DARK)
    ax.set_xticks([c[0] for c in centres])
    ax.set_xticklabels([c[1] for c in centres], fontsize=18, fontweight="bold")
    ax.tick_params(axis="x", length=0, pad=72)
    ax.set_ylabel("S-EMBER accuracy (%)")
    ax.set_ylim(0, 78)
    ax.set_xlim(-0.9, 7.0)
    finish(fig, "t3_size_and_history",
           f"S-EMBER, {len(ids)} questions, split by the recent window's evidence coverage "
           f"(study_r1 K3 `evidence_covered`).  Device = A6000 llama.cpp F16, DEV-RECENT "
           f"(accuracy_C1); cloud = H100 NVL, Qwen3-VL-32B-Instruct, vLLM, RECENT (K3) and "
           f"RICH (K1).  Device↔cloud arrow is backend-mismatched.  "
           f"CIs: video-clustered bootstrap, 2,000 resamples, seed 0.",
           "The cloud helps for two reasons: model size, and history the device has pruned")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 4 — thinking does not buy accuracy
# ─────────────────────────────────────────────────────────────────────────────
def slide4():
    print("story 4 — thinking vs instruct")
    S = "T4"
    rows = []

    C1, C3 = device_cell("C1"), device_cell("C3")
    ids = common_ids(C1, C3)
    vids = vids_of(C1, ids)
    a, b = oks(C1, ids), oks(C3, ids)
    d, lo, hi, _ = sember_diff(a, b, vids)
    rec("t4_sember_dev", S, "S-EMBER device 4B — Thinking − Instruct (C3 − C1), all 845",
        round(d, 2), "results/device/accuracy_C1.jsonl, accuracy_C3.jsonl",
        note=f"[{lo:+.2f}, {hi:+.2f}]; the report's contrast is the qt>120 subset, recorded next")
    qt = np.array([float(C1[i]["question_time"]) for i in ids])
    m = qt > 120
    dq, lq, hq, _ = sember_diff(a[m], b[m], vids[m])
    rec(None, S, "S-EMBER device 4B — T − I, qt>120 (n=678), report cross-check", round(dq, 2),
        "accuracy_C1.jsonl, accuracy_C3.jsonl", "device_tier_accuracy_llamacpp.md §D", 1.77,
        note=f"CI here [{lq:+.2f}, {hq:+.2f}] vs the report's [-1.44, +4.89]; point estimate exact")
    lt_i = float(np.median([C1[i]["latency_ms"] for i in ids])) / 1000
    lt_t = float(np.median([C3[i]["latency_ms"] for i in ids])) / 1000
    ch = 100.0 * float((preds(C1, ids, "predicted_letter") != preds(C3, ids, "predicted_letter")).mean())
    rows.append(("S-EMBER · device 4B\n(A6000 llama.cpp F16)", d, lo, hi, lt_t / lt_i, ch,
                 len(ids), DEVICE, "t4_sember_dev"))

    K = r1()
    idk = common_ids(K["K1"], K["K2"])
    vk = vids_of(K["K1"], idk)
    ak, bk = oks(K["K1"], idk), oks(K["K2"], idk)
    d, lo, hi, _ = sember_diff(ak, bk, vk)
    rec("t4_sember_cloud", S, "S-EMBER cloud 32B — Thinking − Instruct (K2 − K1)", round(d, 2),
        "study_r1_requests_h100nvl.jsonl.gz K1, K2",
        "study_r1_cloud32b_sember.md §Accuracy (33.85 − 39.53)", 33.85 - 39.53,
        note=f"[{lo:+.2f}, {hi:+.2f}]; K2 uses model-card VL sampling, K1 is greedy")
    lt_i = float(np.median([K["K1"][i]["latency_s"] for i in idk]))
    lt_t = float(np.median([K["K2"][i]["latency_s"] for i in idk]))
    ch = 100.0 * float((preds(K["K1"], idk, "pred") != preds(K["K2"], idk, "pred")).mean())
    rows.append(("S-EMBER · cloud 32B\n(H100 vLLM)", d, lo, hi, lt_t / lt_i, ch,
                 len(idk), CLOUD, "t4_sember_cloud"))

    di = {r["qid"]: r for r in r4_rows("erqa", "instruct")}
    dt = {r["qid"]: r for r in r4_rows("erqa", "thinking")}
    ide = common_ids(di, dt)
    d, lo, hi, _ = paired_diff(erqa_ok(di, ide), erqa_ok(dt, ide))
    rec("t4_erqa_dev", S, "ERQA device 4B — Thinking − Instruct", round(d, 2),
        "r4_erqa_instruct.jsonl, r4_erqa_thinking.jsonl",
        "r4_device_signals_prep.md §Escalation (45.0 − 42.0)", 3.0,
        note=f"[{lo:+.2f}, {hi:+.2f}]; paired question bootstrap 2,000 seed 0")
    lt_i = float(np.median([di[i]["lat_ms"] for i in ide])) / 1000
    lt_t = float(np.median([dt[i]["lat_ms"] for i in ide])) / 1000
    ch = 100.0 * float((preds(di, ide, "predicted_letter") != preds(dt, ide, "predicted_letter")).mean())
    rows.append(("ERQA · device 4B\n(A6000 HF sdpa)", d, lo, hi, lt_t / lt_i, ch,
                 len(ide), DEVICE, "t4_erqa_dev"))

    cC, cD = study_r_arm("C"), study_r_arm("D")
    idc = common_ids(cC, cD)
    d, lo, hi, _ = paired_diff(erqa_ok(cC, idc), erqa_ok(cD, idc))
    rec("t4_erqa_cloud", S, "ERQA cloud 32B — Thinking − Instruct (arm D − arm C)", round(d, 2),
        "study_r_trials_h100nvl_fa2.jsonl",
        "study_r_device_vs_cloud.md §Flash-attn (D − C overall)", 2.0, tol=0.3,
        note=f"[{lo:+.2f}, {hi:+.2f}]; the report quotes +2.0 pp to one decimal place")
    lt_i = float(np.median([cC[i]["total_latency_ms"] for i in idc])) / 1000
    lt_t = float(np.median([cD[i]["total_latency_ms"] for i in idc])) / 1000
    ch = 100.0 * float((preds(cC, idc, "predicted_letter") != preds(cD, idc, "predicted_letter")).mean())
    rows.append(("ERQA · cloud 32B\n(H100 HF fa2)", d, lo, hi, lt_t / lt_i, ch,
                 len(idc), CLOUD, "t4_erqa_cloud"))

    M.note(S, "The S-EMBER latency multiple is measured on **batched** runs (R1 cells ran at "
              "concurrency 8 on the cloud side), so 1.7x understates what one 32B Thinking "
              "request costs on its own: K2's median completion length is 139 tokens against "
              "K1's 2. The ERQA multiples are single-request. The device S-EMBER row is the "
              "A6000 accuracy mirror; on the Jetson Orin itself the same contrast is "
              "38.31 s / 17.07 s = 2.2x (see the first slide).")
    for lab, d, lo, hi, mult, ch, n, col, key in rows:
        short = lab.replace("\n", " ")
        rec(key + "_x", S, f"{short} — Thinking ÷ Instruct median latency", round(mult, 2),
            "per-trial latency records", unit="x",
            note="S-EMBER rows are batched wall-clock (R1 ran at concurrency 8); ERQA rows "
                 "are single-request" if "S-EMBER" in short else "single-request")
        rec(key + "_ch", S, f"{short} — % of answers whose letter changed", round(ch, 2),
            "per-trial predicted letters", unit="%",
            note="the S2 and R reports use the phrase 'answers changed by thinking' for the "
                 "McNemar discordance b+c, a different and smaller quantity")

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.215, right=0.70, top=0.82, bottom=0.16)
    ys = np.arange(len(rows))[::-1]
    for y, (lab, d, lo, hi, mult, ch, n, col, key) in zip(ys, rows):
        excl = (lo > 0) or (hi < 0)
        ax.plot([lo, hi], [y, y], color=col, lw=4, solid_capstyle="round")
        ax.plot([d], [y], "o", ms=15, color=col, mfc=col if excl else "white", mew=3, zorder=3)
        ax.text(1.035, y, f"{mult:.1f}× the latency\n{ch:.0f}% of answers changed",
                transform=ax.get_yaxis_transform(), va="center", fontsize=16, color=DARK)
    ax.axvline(0, color=GREY, lw=1.6, ls="--", zorder=0)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{r[0]}\nn = {r[6]}" for r in rows], fontsize=16)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("Thinking − Instruct accuracy (pp, paired, 95% CI)")
    ax.set_xlim(-10, 9)
    ax.text(0.0, 1.03, "open marker = 95% CI includes 0", transform=ax.transAxes,
            fontsize=15, color=GREY, style="italic")
    finish(fig, "t4_thinking_vs_instruct",
           "S-EMBER rows: video-clustered bootstrap, 2,000 resamples, seed 0 "
           "(device = A6000 llama.cpp F16 DEV-RECENT; cloud = H100 vLLM RICH).   "
           "ERQA rows: paired question-level bootstrap, 2,000 resamples, seed 0 "
           "(device = A6000 HF sdpa; cloud = H100 HF fa2).   "
           "Latency multiples are medians on the same stack as the row.",
           "More thinking does not buy accuracy at either tier")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 5 — device-side signals
# ─────────────────────────────────────────────────────────────────────────────
def r4_erqa_stream():
    """Replay r4_analyse.main()'s random stream for ERQA so its CIs reproduce exactly."""
    rng = np.random.default_rng(SEED)
    cC = study_r_arm("C")
    out = {}
    for arm in ("instruct", "thinking"):
        rows = r4_rows("erqa", arm)
        dev_all = np.array([bool(r["correct"]) for r in rows], bool)
        sigs_all = R4.signals_for(rows, arm)
        aurocs = {}
        for nm, sv in sigs_all.items():
            a = R4.auroc(sv, dev_all)
            ci = R4.boot_ci(lambda idx, sv=sv: R4.auroc(sv[idx], dev_all[idx]), len(rows), rng)
            aurocs[nm] = (a, ci)
        paired = [(r, cC[r["qid"]]) for r in rows if r["qid"] in cC]
        pr = [x[0] for x in paired]
        dev_ok = np.array([bool(r["correct"]) for r in pr], bool)
        cloud_ok = np.array([bool(x[1]["correct"]) for x in paired], bool)
        sigs = R4.signals_for(pr, arm)
        best = max(sigs.items(), key=lambda kv: (R4.auroc(kv[1], dev_ok)
                                                 if np.isfinite(R4.auroc(kv[1], dev_ok)) else 0))
        esc = R4.escalation(best[1], dev_ok, cloud_ok, rng)
        out[arm] = dict(aurocs=aurocs, dev_ok=dev_ok, cloud_ok=cloud_ok, sigs=sigs,
                        best=best[0], esc=esc, n=len(pr), n_all=len(rows))
    return out


def slide5():
    print("story 5 — device-side signals")
    S = "T5"
    st = r4_erqa_stream()
    T, I = st["thinking"], st["instruct"]

    SIG = "neg_hesitation_wait"
    a_sig, ci_sig = T["aurocs"][SIG]
    rec("t5_auroc", S, f"ERQA 4B-Thinking — AUROC of {SIG} for device correctness",
        round(a_sig, 4), "results/erqa/r4_signals/r4_erqa_thinking.jsonl",
        "r4_device_signals_prep.md §AUROC", 0.6229, unit="AUROC", tol=0.00005,
        note=f"95% CI [{ci_sig[0]:.4f}, {ci_sig[1]:.4f}], n={T['n_all']}; computed with "
             "r4_analyse.auroc / boot_ci on that script's own random stream")
    VALS["t5_auroc_ci"] = ci_sig

    dev_ok, cloud_ok = T["dev_ok"], T["cloud_ok"]
    n = len(dev_ok)
    ks = np.arange(0, n + 1)
    e = ks / n
    base = 100.0 * dev_ok.mean()
    cl = 100.0 * cloud_ok.mean()
    rec("t5_local", S, "ERQA 4B-Thinking → 32B-I — always-local accuracy", round(base, 2),
        "r4_erqa_thinking.jsonl", unit="%", note=f"paired n={n}")
    rec("t5_cloud", S, "ERQA 4B-Thinking → 32B-I — always-cloud accuracy (StudyR arm C)",
        round(cl, 2), "study_r_trials_h100nvl_fa2.jsonl arm=C", unit="%")

    conf = T["sigs"][SIG]
    sig_curve = curve_from_order(np.argsort(conf, kind="mergesort"), dev_ok, cloud_ok, ks)
    rnd = random_curve(dev_ok, cloud_ok, ks)
    orc = curve_from_order(oracle_order(dev_ok, cloud_ok), dev_ok, cloud_ok, ks)
    k20 = int(round(0.2 * n))
    rec(None, S, f"ERQA 4B-Thinking — accuracy escalating the least-confident 20% by {SIG}",
        round(float(sig_curve[k20]), 2), "r4_erqa_thinking.jsonl + study_r arm C", unit="%",
        note=f"random {rnd[k20]:.2f}%, perfect oracle {orc[k20]:.2f}%")

    e20 = [r for r in I["esc"] if r["e"] == 0.2][0]
    rec("t5_i_sig", S, f"ERQA 4B-Instruct — accuracy escalating the least-confident 20% by "
        f"{I['best']}", round(100 * e20["signal"], 2),
        "r4_erqa_instruct.jsonl + study_r_trials_h100nvl_fa2.jsonl arm=C", unit="%",
        note=f"paired n={I['n']}; the report's escalation table uses arm D (32B-Thinking) as "
             "the cloud tier, so its values are a different quantity")
    rec("t5_i_rand", S, "ERQA 4B-Instruct — accuracy escalating a random 20%",
        round(100 * e20["random"], 2), "mean of 200 random draws", unit="%",
        note=f"perfect oracle {100*e20['oracle']:.2f}%, gap closed {e20['closed']:.3f}")
    VALS["t5_i_signal_name"] = I["best"]

    fig = plt.figure(figsize=FIGSIZE)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.075, right=0.975, top=0.845, bottom=0.215)
    ax.plot([0, 1], [base, base], color=DEVICE, lw=2, ls=":", zorder=1)
    ax.plot([0, 1], [cl, cl], color=CLOUD, lw=2, ls=":", zorder=1)
    ax.text(1.015, base, f"always-local\n{base:.1f}%", color=DEVICE, fontsize=16,
            fontweight="bold", va="center", ha="left")
    ax.text(1.015, cl, f"always-cloud\n{cl:.1f}%", color=CLOUD, fontsize=16,
            fontweight="bold", va="center", ha="left")
    ax.plot(e, orc, color=ORACLE, lw=3, label="perfect oracle", zorder=3)
    ax.plot(e, rnd, color=RANDOM, lw=2.6, ls="--", label="random (mean of 200 draws)", zorder=3)
    ax.plot(e, sig_curve, color=DEVICE, lw=3, label=f"best signal: {SIG}", zorder=4)
    ax.set_xlim(0, 1.17)
    ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_xlabel("fraction of questions escalated to the cloud")
    ax.set_ylabel("ERQA accuracy (%)")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.015, 0.60))
    ax.text(0.26, 0.97,
            f"Best signal AUROC {a_sig:.2f} [{ci_sig[0]:.2f}, {ci_sig[1]:.2f}] "
            f"for device correctness.\n"
            f"With 4B-Instruct, escalating the least-confident 20% by {I['best']}\n"
            f"gives {100*e20['signal']:.1f}% vs random {100*e20['random']:.1f}%.",
            transform=ax.transAxes, va="top", ha="left", fontsize=17,
            bbox=dict(boxstyle="round,pad=0.55", fc="white", ec=GREY, lw=1.2))
    ax.text(0.0, -0.165,
            "Perfect oracle is an upper bound; on 4-option multiple choice it counts chance "
            "agreement as recoverable.",
            transform=ax.transAxes, fontsize=14, color=GREY, style="italic")
    finish(fig, "t5_device_signals",
           f"ERQA, device 4B-Thinking (A6000 HF sdpa, r4_erqa_thinking.jsonl) → cloud "
           f"32B-Instruct (H100 HF fa2, StudyR arm C), paired n={n}.  Backend-mismatched.  "
           f"Signal order is least-confident-first; AUROC from experiments/erqa/r4_analyse.py "
           f"(2,000-resample question bootstrap, seed 0).",
           "Device-side signals do not yet tell us when to escalate")


# ─────────────────────────────────────────────────────────────────────────────
# SLIDE 6 — escalation cost vs fleet size
# ─────────────────────────────────────────────────────────────────────────────
HOSTC = "#FE6100"
COLDC = "#6A6A6A"
PARTA_11K = [("in GPU memory\n(GPU-warm)", "gpu", "GPU-WARM", CLOUD, 0.382),
             ("in host memory\n(host-warm)", "host", "HOST-WARM", HOSTC, 0.459),
             ("rebuilt from scratch\n(cold re-prefill)", "gpu", "COLD", COLDC, 2.445)]


def slide6():
    print("story 6 — escalation cost vs fleet size")
    S = "T6"
    pa = jl("results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz")
    bars = []
    for lab, cfg, state, col, repv in PARTA_11K:
        v = np.array([r["ttft_s"] for r in pa
                      if r["size"] == "11k" and r["cfg"] == cfg and r["state"] == state], float)
        m = float(np.median(v))
        rec(f"t6_{state}", S, f"RH5 Part A TTFT median, 11k history — {state}", round(m, 3),
            "results/cost/study_rh5/study_rh5_partA_h100nvl.jsonl.gz",
            "study_rh5_host_offload.md Part A", repv, unit="s", tol=0.002,
            note=f"min–max [{v.min():.3f}, {v.max():.3f}] over n={len(v)} requests")
        bars.append((lab, m, v.min(), v.max(), col, len(v)))

    rh5 = M.js("results/cost/study_rh5/study_rh5_results_h100nvl.json")["cells"]
    Ds = [4, 8, 16, 24]
    REP = {"GPU": {4: 0.53, 8: 95.6, 16: 802.0, 24: 1520.0},
           "HOST": {4: 0.54, 8: 0.52, 16: 0.60, 24: 0.81}}
    series = {}
    for key, label, col in [("GPU", "GPU memory only", CLOUD),
                            ("HOST", "GPU + 256 GiB host memory", HOSTC)]:
        med = []
        for D in Ds:
            m = rh5[f"RH5_{key}_D{D}"]["ttft_s"]["median"]
            med.append(m)
            rec(f"t6_{key}_D{D}", S, f"RH5 Part B {label} — warm escalation TTFT median at D={D}",
                round(m, 3), "results/cost/study_rh5/study_rh5_results_h100nvl.json",
                "study_rh5_host_offload.md Part B", REP[key][D], unit="s",
                tol=max(0.6, abs(REP[key][D]) * 0.01))
        series[label] = (med, col)

    p0 = M.js("results/sember/study_rh4/study_rh4_part0_h100nvl.json")["rows"]
    cold = [r for r in p0 if r["first"]["cached_tokens"] < 0.01 * r["first"]["prompt_tokens"]]
    reuse = [r["cached_over_first_prompt"] for r in cold]
    rec("t6_rh4_reuse", S, "RH4 Part 0 — cached tokens on the appended request ÷ the earlier "
        "prompt (cold FIRST rows only)", round(100 * float(np.median(reuse)), 2),
        "results/sember/study_rh4/study_rh4_part0_h100nvl.json",
        "study_rh4_fixed_stride.md (99.2–99.5% on 5/5)", None, unit="%",
        note=f"min–max [{100*min(reuse):.2f}, {100*max(reuse):.2f}] over {len(cold)} of "
             f"{len(p0)} rows; the other rows had a warm FIRST, giving a ratio above 1")
    p3 = M.js("results/sember/study_rh3/study_rh3_part0_h100nvl.json")["rows"]
    f3 = [r["ext_cached_frac"] for r in p3]
    rec("t6_rh3_reuse", S, "RH3 Part 0 — cached fraction when a single-video history is "
        "extended by 10 frames", round(100 * float(np.max(f3)), 2),
        "results/sember/study_rh3/study_rh3_part0_h100nvl.json",
        "study_rh4_fixed_stride.md ('reused 0 tokens')", 0.0, unit="%",
        note=f"max over all {len(f3)} rows; every row is exactly 0")
    rec("t6_d2_k1", S, "RH4 — D2 fixed-stride minus K1 one-video accuracy (paired n=839)",
        -0.24, "study_rh4_fixed_stride.md Decision table",
        "study_rh4_fixed_stride.md Decision table", -0.24,
        note="quoted from the report, not recomputed here: the full-accuracy claim in the "
             "caption comes from StudyRH4's own paired contrast [-2.80, +2.41]")

    fig = plt.figure(figsize=FIGSIZE)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.25], wspace=0.24,
                          left=0.072, right=0.975, top=0.835, bottom=0.275)

    ax = fig.add_subplot(gs[0])
    xs = np.arange(len(bars))
    for x, (lab, m, vmin, vmax, col, nreq) in zip(xs, bars):
        ax.bar(x, m, width=0.6, color=col, zorder=2)
        ax.errorbar(x, m, yerr=[[m - vmin], [vmax - m]], fmt="none", ecolor=DARK,
                    elinewidth=2, capsize=7, zorder=3)
        ax.text(x, vmax * 1.16, f"{m:.2f} s", ha="center", fontsize=17, fontweight="bold")
    ax.set_xticks(xs)
    ax.set_xticklabels([b[0] for b in bars], fontsize=15)
    ax.set_yscale("log")
    ax.set_ylim(0.22, 7)
    ax.set_yticks([0.3, 0.5, 1, 2, 5])
    ax.set_yticklabels(["0.3", "0.5", "1", "2", "5"])
    ax.set_ylabel("escalation TTFT (s, log)\nmedian, bars span min–max")
    ax.set_title(f"Where the history sits  (11k tokens, n={bars[0][5]} per bar)",
                 fontsize=19, loc="left")

    ax = fig.add_subplot(gs[1])
    for label, (med, col) in series.items():
        ax.plot(Ds, med, "-o", color=col, lw=3, ms=11, label=label)
    for D, m in zip(Ds, series["GPU memory only"][0]):
        if m > 10:
            ax.annotate(f"{m:,.0f} s", (D, m), textcoords="offset points", xytext=(0, 13),
                        ha="center", fontsize=15, color=CLOUD, fontweight="bold")
    ax.annotate(f"{series['GPU + 256 GiB host memory'][0][-1]:.2f} s",
                (24, series['GPU + 256 GiB host memory'][0][-1]),
                textcoords="offset points", xytext=(0, -28), ha="center", fontsize=15,
                color=HOSTC, fontweight="bold")
    ax.set_yscale("log")
    ax.set_xticks(Ds)
    ax.set_xlabel("D — devices kept warm on one GPU")
    ax.set_ylabel("warm escalation TTFT (s, log), median")
    ax.set_title("How many devices the cloud keeps ready", fontsize=19, loc="left")
    ax.set_ylim(top=6e3)
    ax.legend(frameon=False, loc="upper left", fontsize=15, bbox_to_anchor=(0.0, 0.88))

    fig.text(0.072, 0.145,
             f"History format: fixed-stride images keep full accuracy "
             f"(D2 − K1 = {VALS['t6_d2_k1']:+.2f} pp) and reuse "
             f"{VALS['t6_rh4_reuse']:.0f}% of cached\n"
             f"state per update (RH4); a single-video history reuses "
             f"{VALS['t6_rh3_reuse']:.0f}% (RH3).",
             fontsize=17, color=DARK, ha="left", va="top")
    finish(fig, "t6_escalation_cost_vs_fleet",
           "Left: StudyRH5 Part A, H100 NVL, Qwen3-VL-32B-Instruct, vLLM bf16 KV, D2 "
           "fixed-stride history, one request at a time, TTFT only, no network; host tier = "
           "vLLM OffloadingConnector, 256 GiB pinned.   "
           "Right: StudyRH5 Part B, same stack, 15-min window, escalation rate 1.0.",
           "Escalation cost depends on how many devices the cloud keeps ready")


# ─────────────────────────────────────────────────────────────────────────────
# outputs
# ─────────────────────────────────────────────────────────────────────────────
STORY_SLIDES = {
    "T2": ("t2_cloud_accuracy_and_latency",
           "A larger cloud model is more accurate — and faster"),
    "T3": ("t3_size_and_history",
           "The cloud helps for two reasons: model size, and history the device has pruned"),
    "T4": ("t4_thinking_vs_instruct", "More thinking does not buy accuracy at either tier"),
    "T5": ("t5_device_signals", "Device-side signals do not yet tell us when to escalate"),
    "T6": ("t6_escalation_cost_vs_fleet",
           "Escalation cost depends on how many devices the cloud keeps ready"),
}


def write_numbers():
    import subprocess
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()[:12] or "unknown"
    mine = [n for n in M.NUMBERS if n["slide"] in STORY_SLIDES]
    mism = [m for m in M.MISMATCHES if m[0] in STORY_SLIDES]

    L = ["# Advisor story deck — plotted numbers and their sources (2026-10-23)\n"]
    L.append(f"Generated by `experiments/figures/make_advisor_story_2026_10.py` at commit "
             f"`{sha}`. CPU only; no GPU was used and no inference was run. Loaders and "
             f"statistics helpers are imported from `make_advisor_plots_2026_10.py`.\n")
    L.append("Every value is **computed from the committed result files** unless its source "
             "column names a report. The *report value* column is the figure printed in that "
             "report; a difference larger than the stated tolerance (0.1 pp by default) is "
             "flagged as a MISMATCH below and is never silently reconciled.\n")
    L.append("Confidence intervals: S-EMBER rows use the video-clustered bootstrap from "
             "`experiments/sember/study_o_q4_analyze.py` (2,000 resamples, seed 0); ERQA rows "
             "use a paired question-level bootstrap (2,000 resamples, seed 0); AUROC CIs reuse "
             "`experiments/erqa/r4_analyse.py`'s `auroc` and `boot_ci` and consume its random "
             "stream in that script's order.\n")

    L.append("## Mismatches\n")
    if mism:
        L.append("| slide | quantity | computed | report value | Δ | report |")
        L.append("|---|---|---|---|---|---|")
        for sl, q, v, rv, d, rp, nt in mism:
            L.append(f"| {sl} | {md_escape(q)} | {v} | {rv} | {d:+.3f} | {md_escape(rp)} |")
        L.append("")
    else:
        L.append("**None.** Every plotted quantity with a committed report value reproduces "
                 "it within tolerance.\n")

    notes = [(s, t) for s, t in M.NOTES if s in STORY_SLIDES]
    if notes:
        L.append("## Notes\n")
        for s, t in notes:
            L.append(f"- **{s}** — {t}")
        L.append("")

    L.append("## Backend and hardware labels\n")
    L.append("| label | meaning |")
    L.append("|---|---|")
    for a, b in [
        ("device (Jetson Orin)", "Jetson AGX Orin 64 GB, llama.cpp c0fd786 (sm_87), GGUF F16, "
                                 "DEV-RECENT 37-frame image inputs"),
        ("A6000 llama.cpp F16", "flash / RTX A6000 GPU 1, llama.cpp c0fd786, GGUF F16 — the "
                                "accuracy mirror of the Orin construction"),
        ("A6000 HF sdpa", "flash / RTX A6000, HuggingFace transformers, attn_implementation=sdpa"),
        ("cloud (H100) vLLM", "sn4622120321 GPU 3, Qwen3-VL-32B-Instruct, vLLM 0.31.0+cu129, bf16"),
        ("cloud (H100) HF fa2", "sn4622120321 GPU 3, HuggingFace transformers, "
                                "flash_attention_2, bf16"),
    ]:
        L.append(f"| {a} | {b} |")
    L.append("")

    for sl in STORY_SLIDES:
        rows = [n for n in mine if n["slide"] == sl]
        if not rows:
            continue
        stem, title = STORY_SLIDES[sl]
        L.append(f"## {sl} — {title}\n")
        L.append(f"Files: `{stem}.pdf`, `{stem}.png`\n")
        L.append("| quantity | value | source file | report | report value | Δ | check |")
        L.append("|---|---|---|---|---|---|---|")
        for n in rows:
            rv = "—" if n["report_value"] is None else f"{n['report_value']}"
            q = md_escape(n["quantity"])
            if n["note"]:
                q += f"<br><sub>{md_escape(n['note'])}</sub>"
            L.append(f"| {q} | {M.fmt_val(n)} | `{md_escape(n['source'])}` | "
                     f"{md_escape(n['report'])} | {rv} | {n['delta'] or '—'} | {n['status']} |")
        L.append("")

    (OUT / "story_numbers.md").write_text("\n".join(L) + "\n")
    print(f"  wrote story_numbers.md ({len(mine)} values, {len(mism)} mismatches)")
    return mism


def write_slides_text():
    V = VALS
    ci5 = V["t5_auroc_ci"]
    L = ["# Advisor story deck — text-only slides (2026-10-23)\n"]
    L.append("Every number below is taken from `story_numbers.md`, which computes it from the "
             "committed result files. Nothing here is typed in by hand.\n")

    L.append("## Slide 1 — Three questions\n")
    L.append("1. **Does the larger model help, and at what latency?**  \n"
             "   Device (Jetson Orin) 4B/8B against cloud (H100) 32B, on the same questions.")
    L.append("2. **Do token-level signals tell us when to escalate?**  \n"
             "   Can the device itself decide which questions to send up?")
    L.append("3. **What happens when many devices share the cloud?**  \n"
             "   What limits how many warm sessions one GPU can hold.\n")

    L.append("## Slide 7 — Takeaways and next steps\n")
    L.append("### Takeaways\n")
    L.append(f"1. **The 32B cloud model helps, and it is faster.** On the Orin's S-EMBER "
             f"block the cloud reaches {V['t2_acc_32B-I']:.1f}% against "
             f"{V['t2_acc_8B-T']:.1f}% for the best on-device arm (8B-Thinking), and it "
             f"answers in {V['t2_lat_32B-I']:.1f} s sequentially — against "
             f"{V['t2_lat_8B-T']:.1f} s on the device. With the history already in GPU "
             f"memory the cloud's TTFT is {V['t2_ttft_GPU-WARM']:.2f} s.")
    L.append(f"2. **Its value is model size *plus* history.** Where the recent window misses "
             f"the evidence (n = {V['t3_n_miss']}), moving to the cloud's recent-window "
             f"prompt is worth {V['t3_miss_size']:+.1f} pp and the full history a further "
             f"{V['t3_miss_hist']:+.1f} pp "
             f"[{V['t3_miss_hist_ci'][0]:+.1f}, {V['t3_miss_hist_ci'][1]:+.1f}]. Where the "
             f"window already covers it (n = {V['t3_n_cover']}), the history is worth "
             f"{V['t3_cover_hist']:+.1f} pp "
             f"[{V['t3_cover_hist_ci'][0]:+.1f}, {V['t3_cover_hist_ci'][1]:+.1f}] — nothing.")
    L.append(f"3. **Device signals do not yet find where escalation helps.** The best "
             f"thinking-trace signal reaches AUROC {V['t5_auroc']:.2f} "
             f"[{ci5[0]:.2f}, {ci5[1]:.2f}] for device correctness. Escalating the "
             f"least-confident 20% of ERQA questions from 4B-Instruct gives "
             f"{V['t5_i_sig']:.1f}% against {V['t5_i_rand']:.1f}% for a random 20%.")
    L.append(f"4. **Cloud *state*, not cloud compute, limits escalation.** Keeping histories "
             f"in GPU memory alone, median warm escalation TTFT goes from "
             f"{V['t6_GPU_D4']:.2f} s at D=4 to {V['t6_GPU_D24']:,.0f} s at D=24. With 256 "
             f"GiB of host memory behind the GPU the same D=24 is "
             f"{V['t6_HOST_D24']:.2f} s. Paging a history back from host memory costs "
             f"{V['t6_HOST-WARM']:.2f} s against {V['t6_COLD']:.2f} s to rebuild it.")
    L.append(f"   Thinking is not a lever at either tier: Thinking − Instruct is "
             f"{V['t4_sember_dev']:+.1f} pp on-device and {V['t4_sember_cloud']:+.1f} pp in "
             f"the cloud on S-EMBER, and {V['t4_erqa_dev']:+.1f} / "
             f"{V['t4_erqa_cloud']:+.1f} pp on ERQA, at "
             f"{V['t4_sember_dev_x']:.1f}× the device latency on the A6000 mirror and "
             f"{V['t2_lat_4B-T'] / V['t2_lat_4B-I']:.1f}× on the Orin itself.\n")
    L.append("### Next steps\n")
    L.append("- **Trigger study on a held-out split**, including a cloud-side history check: "
             "the device asks, the cloud decides whether its own history adds anything before "
             "it spends a full 32B pass.")
    L.append("- **End-to-end evaluation with strong baselines**: always-local, always-cloud, "
             "random escalation at a matched rate, and an oracle bound, under one latency "
             "budget.")
    L.append("- **Mobility and network**: every latency here is local HTTP or TTFT with no "
             "network. Reachability and handover change which tier is even available.\n")
    L.append("### Asks\n")
    L.append("- **Which deadline regime should we design for?** The device answers in "
             f"{V['t2_lat_4B-I']:.0f}–{V['t2_lat_8B-T']:.0f} s; a warm cloud answers in "
             f"about {V['t2_ttft_GPU-WARM']:.1f} s plus network. Those are different products.")
    L.append("- **Are S-EMBER and ERQA enough?** S-EMBER carries the history mechanism; ERQA "
             "carries the signals. Neither is a robot-deployment workload.\n")

    (OUT / "slides_text.md").write_text("\n".join(L) + "\n")
    print("  wrote slides_text.md")


def main():
    print(f"writing to {OUT}")
    slide2()
    slide3()
    slide4()
    slide5()
    slide6()
    mism = write_numbers()
    write_slides_text()
    files = sorted(f for f in OUT.iterdir() if f.is_file())
    total = sum(f.stat().st_size for f in files)
    print(f"\n{len(files)} files, {total/1e6:.2f} MB total")
    if mism:
        print(f"\n{len(mism)} MISMATCH(es):")
        for sl, q, v, rv, d, rp, nt in mism:
            print(f"  [{sl}] {q}: computed {v} vs report {rv} ({d:+.3f})")
    else:
        print("\nno mismatches: every cross-checked value reproduces its report")


if __name__ == "__main__":
    main()
