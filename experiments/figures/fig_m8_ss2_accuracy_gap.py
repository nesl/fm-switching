#!/usr/bin/env python3
"""M8: StudySS2. Device 4B vs cloud 32B single-shot accuracy gap per dataset.

Claim: the cloud 32B beats the device 4B on both spatial datasets, and the gap is
much larger on spatial reasoning (RefSpatial, point-in-mask) than on general visual
QA (RealWorldQA), so the value of escalating to the cloud is task dependent.

CPU only. Committed data only: the two StudySS2 compare files, using the `clean`
block (below-floor exclusions applied) per each file's own denominators rule.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np
import matplotlib.pyplot as plt

SRCS = {
    "RefSpatial": "results/casestudy/study_ss2/refspatial_compare.json",
    "RealWorldQA": "results/casestudy/study_ss2/realworldqa_compare.json",
}
RESCORE = "results/casestudy/study_ss2/refspatial_rescore.json"
FIGID = "M8_ss2_accuracy_gap_by_dataset"


def main():
    data = {name: F.load_json(p)["clean"] for name, p in SRCS.items()}

    fig, ax = F.new_fig(6.8, 4.3)
    datasets = list(SRCS.keys())
    x = np.arange(len(datasets))
    bw = 0.36
    for off, tierkey, field in [(-bw / 2, "device", "device_accuracy"),
                                (bw / 2, "cloud", "cloud_accuracy")]:
        col = F.TIER[tierkey]["color"]
        hatch = F.TIER[tierkey]["hatch"]
        vals = [data[ds][field]["mean"] for ds in datasets]
        los = [data[ds][field]["mean"] - data[ds][field]["ci95"][0] for ds in datasets]
        his = [data[ds][field]["ci95"][1] - data[ds][field]["mean"] for ds in datasets]
        lab = "device (Orin 4B)" if tierkey == "device" else "cloud (32B)"
        ax.bar(x + off, vals, width=bw, color=col, hatch=hatch, edgecolor="white",
               linewidth=0.9, zorder=3, label=lab)
        ax.errorbar(x + off, vals, yerr=[los, his], fmt="none", ecolor=F.INK,
                    elinewidth=1.3, capsize=4, zorder=4)
        for xi, v in zip(x + off, vals):
            ax.text(xi, v - 0.02, f"{v*100:.0f}%", ha="center", va="top",
                    fontsize=9.5, color="white", fontweight="bold")

    # paired-delta annotation per dataset
    for xi, ds in zip(x, datasets):
        pd = data[ds]["paired_difference"]
        dlt = pd["delta_cloud_minus_device"]
        lo, hi = pd["ci95"]
        top = max(data[ds]["cloud_accuracy"]["ci95"][1], data[ds]["device_accuracy"]["ci95"][1])
        ax.annotate(f"gap +{dlt*100:.1f} pp\n[{lo*100:.1f}, {hi*100:.1f}]",
                    xy=(xi, top + 0.03), ha="center", va="bottom", fontsize=8.5,
                    color=F.INK)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{ds}\n(n={data[ds]['device_accuracy']['n']})" for ds in datasets])
    ax.set_ylabel("single-shot accuracy")
    ax.set_ylim(0, 0.88)
    ax.set_yticks(np.arange(0, 0.81, 0.2))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 0.81, 0.2)])
    ax.legend(loc="upper left", ncol=1)
    ax.set_title("Cloud beats device on both; the gap is task dependent",
                 fontsize=11, pad=8)
    F.save(fig, FIGID, pilot=False)

    rs = F.load_json(RESCORE)
    rf, rw = data["RefSpatial"], data["RealWorldQA"]
    claim = (
        "On StudySS2, the cloud 32B beats the device 4B on both datasets. The gap is much "
        f"larger on RefSpatial spatial reasoning, where cloud {rf['cloud_accuracy']['mean']*100:.1f}% "
        f"beats device {rf['device_accuracy']['mean']*100:.1f}% by a paired "
        f"{rf['paired_difference']['delta_cloud_minus_device']*100:.1f} pp "
        f"(95% CI [{rf['paired_difference']['ci95'][0]*100:.1f}, {rf['paired_difference']['ci95'][1]*100:.1f}]), "
        f"than on RealWorldQA general visual QA, where cloud {rw['cloud_accuracy']['mean']*100:.1f}% beats "
        f"device {rw['device_accuracy']['mean']*100:.1f}% by {rw['paired_difference']['delta_cloud_minus_device']*100:.1f} pp "
        f"(95% CI [{rw['paired_difference']['ci95'][0]*100:.1f}, {rw['paired_difference']['ci95'][1]*100:.1f}]). "
        "The value of escalating to the cloud therefore depends on the task."
    )
    notes = (
        "Numbers are each compare file's `clean` block (n=277 RefSpatial, n=765 RealWorldQA), which "
        "excludes only the below-min-pixel set per the file's two-denominators rule; CIs are the committed "
        "paired bootstrap. Device is Qwen3-VL-4B on the Orin, cloud is 32B. Committed refinement, flagged "
        f"not re-plotted: the RefSpatial cloud rescore (refspatial_rescore.json) moves the paired gap from "
        f"+{rs['delta']['old']*100:.1f} pp to +{rs['delta']['new']*100:.1f} pp via the fixed point parser on "
        f"the cloud side, with 0 device rows moved (control passed), which only widens the RefSpatial gap; "
        "the headline direction and ordering are unchanged. Device purple and cloud blue sit in separate "
        "labelled dataset groups, so the pair is never distinguished by hue alone."
    )
    F.write_caption(FIGID, claim, [SRCS["RefSpatial"], SRCS["RealWorldQA"], RESCORE],
                    pilot=False, notes=notes)


if __name__ == "__main__":
    main()
