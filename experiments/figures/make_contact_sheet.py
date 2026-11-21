#!/usr/bin/env python3
"""Contact sheet: all paper figures (M1-M8 motivation, E1-E8 evaluation) on one page.

CPU only. Reads the already-rendered figures/paper/*.png and lays them out in a grid,
each labelled with its id and one-line role. Evaluation figures are marked PILOT in the
label as well as in their own watermark. Reproducible: re-run after any figure changes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

OUT = F.OUT_DIR
FIGS = [
    ("M1_lhreq_accuracy_by_tier_rep", "M1  LH-REQ accuracy by tier x rep"),
    ("M2_ttft_vs_history_cold_warm", "M2  first-token vs history, cold/warm"),
    ("M3_accuracy_vs_latency", "M3  accuracy vs latency"),
    ("M4_imposed_delay_by_rebuild_shape", "M4  delay imposed, rebuild shape"),
    ("M5_warmall_vs_policy_epg", "M5  warm-all vs policy on EP-G"),
    ("M6_warmstate_kv_pool", "M6  KV pool vs history (warm-state sim)"),
    ("M7_shep_detection_and_cost", "M7  SH-EP detection and cost"),
    ("M8_ss2_accuracy_gap_by_dataset", "M8  SS2 accuracy gap per dataset"),
    ("E1_headline_by_workload", "E1  per-workload headline  [PILOT]"),
    ("E2_ablation_ladder", "E2  ablation ladder  [PILOT]"),
    ("E3_mechanism_over_time", "E3  mechanism over time  [PILOT]"),
    ("E4_capacity_knee", "E4  capacity knee  [PILOT]"),
    ("E5_memory_sweep", "E5  memory sweep  [PILOT]"),
    ("E6_deadline_sweep", "E6  deadline sweep  [PILOT]"),
    ("E7_per_device_attainment", "E7  per-device attainment  [PILOT]"),
    ("E8_decision_latency", "E8  decision latency  [PILOT]"),
]
NCOL, NROW = 4, 4


def main():
    fig, axes = plt.subplots(NROW, NCOL, figsize=(16, 11.5))
    for ax, (fid, label) in zip(axes.flat, FIGS):
        p = OUT / f"{fid}.png"
        if p.exists():
            ax.imshow(mpimg.imread(p))
        else:
            ax.text(0.5, 0.5, f"{fid}\n(missing)", ha="center", va="center",
                    transform=ax.transAxes, color=F.MUTED)
        ax.set_title(label, fontsize=10, color=F.INK, pad=4,
                     fontweight=("bold" if label.startswith("M") else "normal"))
        ax.axis("off")
    for ax in list(axes.flat)[len(FIGS):]:
        ax.axis("off")
    fig.suptitle("FM-switching paper figures  -  motivation (M1-M8) and evaluation (E1-E8, PILOT)",
                 fontsize=14, color=F.INK, y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(OUT / "contact_sheet.png", dpi=140, bbox_inches="tight")
    fig.savefig(OUT / "contact_sheet.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote figures/paper/contact_sheet.png + .pdf")

    (OUT / "contact_sheet.caption.txt").write_text(
        "contact_sheet\n\nCLAIM:\nOne-page index of the 16 paper figures: motivation M1-M8 "
        "(drawn from committed data) and evaluation E1-E8 (PILOT, drawn from the EP-G pilot cells "
        "and to be re-run on the repeat-trace cells). Each thumbnail links to its own script and "
        "caption file under experiments/figures/ and figures/paper/.\n\n"
        "SOURCES (committed): the per-figure source files listed in each figure's own caption.\n")


if __name__ == "__main__":
    main()
