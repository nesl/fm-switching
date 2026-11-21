#!/usr/bin/env python3
"""M7: StudySH-EP. 32B vs 4B sudden-hazard detection, and warm vs cold episode cost.

Two panels, one claim: the cloud 32B detects better than the device 4B at every
episode condition and extra frames do not close the gap (the device does not
improve past one-frame C1 and degrades at the two highest frame-count conditions);
and the cost of episode context is paid on the cold path only, so warming makes
episode context nearly as cheap as one frame.

CPU only. Committed data only: results/dashcam/study_sh_ep/sh_ep_results.json.
StudySH-EP is a clean study; its EP-G arm is the shep2 EP-G run and is distinct
from the live2 EP-G cells used by the evaluation figures, so no family mixing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np
import matplotlib.pyplot as plt

SRC = "results/dashcam/study_sh_ep/sh_ep_results.json"
FIGID = "M7_shep_detection_and_cost"
CONDS = ["C1", "C3", "C6", "EP-B", "EP-G"]


def main():
    d = F.load_json(SRC)
    arms = d["arms"]
    cost = d["cost"]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.4, 4.3))
    for ax in (axA, axB):
        ax.grid(True, axis="y", color=F.GRID, linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # Panel A: detection mAP, device 4BI vs cloud 32BI, per condition, with CIs.
    x = np.arange(len(CONDS))
    bw = 0.38
    for off, tierkey, model in [(-bw / 2, "device", "4BI"), (bw / 2, "cloud", "32BI")]:
        col = F.TIER[tierkey]["color"]
        hatch = F.TIER[tierkey]["hatch"]
        vals, los, his = [], [], []
        for c in CONDS:
            m = arms[f"{model}|{c}"]["mAP"]
            vals.append(m["value"]); los.append(m["value"] - m["ci"][0]); his.append(m["ci"][1] - m["value"])
        axA.bar(x + off, vals, width=bw, color=col, hatch=hatch, edgecolor="white",
                linewidth=0.9, zorder=3, label=F.TIER[tierkey]["label"].replace("Orin 4B", "4B").replace("32B", "32B"))
        axA.errorbar(x + off, vals, yerr=[los, his], fmt="none", ecolor=F.INK,
                     elinewidth=1.2, capsize=3, zorder=4)
    axA.set_xticks(x); axA.set_xticklabels(CONDS)
    axA.set_ylabel("sudden-hazard detection mAP")
    axA.set_xlabel("episode condition")
    axA.set_ylim(0, 0.8)
    axA.axvspan(-0.5, 0.5, color=F.BLUE, alpha=0.05, zorder=0)
    axA.legend(loc="upper right", ncol=1)
    axA.set_title("32B detects better; frames do not help the 4B", fontsize=10.5, pad=6)

    # Panel B: device 4BI cold vs warm TTFT p50 per condition.
    valc = [cost[f"4BI|{c}"]["ttft_cold_s"]["p50"] for c in CONDS]
    valw = [cost[f"4BI|{c}"].get("ttft_warm_s") for c in CONDS]
    valw = [(w["p50"] if w else None) for w in valw]
    for off, series, col, lab, hatch in [
            (-bw / 2, valc, F.RISK, "cold (first build)", "..."),
            (bw / 2, valw, F.GREEN, "warm (reuse built history)", "")]:
        xs = [xi + off for xi, v in zip(x, series) if v is not None]
        ys = [v for v in series if v is not None]
        axB.bar(xs, ys, width=bw, color=col, hatch=hatch, edgecolor="white",
                linewidth=0.9, zorder=3, label=lab)
        for xi, v in zip(xs, ys):
            axB.text(xi, v + 0.03, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=F.INK)
    axB.axhline(valc[0], color=F.GREY, linewidth=1.1, linestyle=":", zorder=2)
    axB.text(0.35, 1.5, f"dotted line: one-frame C1 cold ({valc[0]:.2f} s)", ha="left",
             va="center", fontsize=8.5, color=F.MUTED)
    axB.set_xticks(x); axB.set_xticklabels(CONDS)
    axB.set_ylabel("device 4B first-token latency p50 (s)")
    axB.set_xlabel("episode condition")
    axB.set_ylim(0, 2.05)
    axB.legend(loc="upper left", ncol=1)
    axB.set_title("Episode context costs the device cold, not warm", fontsize=10.5, pad=6)

    F.save(fig, FIGID, pilot=False)

    g = d["h1_gap"]
    claim = (
        "At every episode condition the cloud 32B detects sudden hazards better than the "
        f"device 4B: the mAP gap runs {g['C1']['gap']*100:.1f} to {g['C6']['gap']*100:.1f} pp "
        "and every 95 percent CI is above zero. Adding frames does not close the gap: the device "
        f"4B does not improve beyond the one-frame C1 condition (mAP {arms['4BI|C1']['mAP']['value']:.3f}) "
        f"and falls at the two highest frame-count conditions C6 ({arms['4BI|C6']['mAP']['value']:.3f}) "
        f"and EP-G ({arms['4BI|EP-G']['mAP']['value']:.3f}). The cost of episode context is paid on "
        f"the cold path only: full-history EP-G context costs the device {cost['4BI|EP-G']['ttft_cold_s']['p50']:.2f} s "
        f"cold at first-token p50 but {cost['4BI|EP-G']['ttft_warm_s']['p50']:.2f} s warm, close to the "
        f"{cost['4BI|C1']['ttft_cold_s']['p50']:.2f} s one-frame cost."
    )
    notes = (
        "Device is Qwen3-VL-4B-Instruct on the Orin; cloud is 32B-Instruct on an H100; cross-stack "
        "by deployment design with per-request input identity verified (deployment_pair: 0 prompt-token, "
        "header or frame-sha mismatches). Detection mAP CIs are the study's clip bootstrap. Panel B shows "
        "TTFT p50 only (no CI in the committed cost block). C1 is one frame so it has no warm reuse path. "
        "Conditions: C1 one frame, C3/C6 clip windows, EP-B/EP-G append-only episodes. Device is purple and "
        "cloud is blue in separate paired bars and labelled, so the blue/purple pair is never hue-alone; "
        "cold is risk-orange and warm is KV-green. StudySH-EP is CLOSED with a one-frame C1 verdict; this "
        "figure shows why (episodes do not help detection and their cost is a cold-start cost)."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=False, notes=notes)


if __name__ == "__main__":
    main()
