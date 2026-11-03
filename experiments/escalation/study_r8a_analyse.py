#!/usr/bin/env python3
"""StudyR8a figures. Reads results/escalation/study_r8a/study_r8a_results.json only."""
import json, sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
TAG = sys.argv[1] if len(sys.argv) > 1 else ""
RES = ROOT / f"results/escalation/study_r8a/study_r8a_results{TAG}.json"
FIG = ROOT / "figures/escalation"
FIG.mkdir(parents=True, exist_ok=True)

BLUE, MAG, GREEN, GREY, ORANGE = "#648FFF", "#DC267F", "#117733", "#8C8C8C", "#FE6100"
plt.rcParams.update({"font.family": "sans-serif", "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 12,
                     "axes.labelsize": 13, "legend.fontsize": 10})

FAMILY = [("query+prefix_hand", BLUE, "o", "query+prefix (hand)"),
          ("query+prefix_tfidf", MAG, "s", "query+prefix (tf-idf)"),
          ("query+prefix_emb", ORANGE, "^", "query+prefix (embed)"),
          ("query+prefix_unc", GREEN, "D", "query+prefix (uncertainty)"),
          ("length_only", GREY, "x", "length only")]


def main():
    d = json.load(open(RES))
    for wl, r in d["results"].items():
        b = r["part2"]["_baselines"]["e0.2"]
        fig, ax = plt.subplots(figsize=(7.4, 5.0))
        for fi, (pre, col, mk, lab) in enumerate(FAMILY):
            pts = []
            for key, row in r["part2"].items():
                if key == "_baselines" or not key.startswith(pre + "_k"):
                    continue
                best = max(row[f"e0.2_{x}"]["acc"] for x in ("by_gain", "by_failure"))
                pts.append((row["latency_s"], best, row["k"]))
            if not pts:
                continue
            pts.sort()
            ax.plot([p[0] for p in pts], [p[1] for p in pts], mk + "-", color=col,
                    ms=7, lw=1.6, label=lab, alpha=0.9)
            for x, y, k in pts:
                if k == 400:
                    ax.annotate(f"k={k}", (x, y), textcoords="offset points",
                                xytext=(0, 8 if fi % 2 == 0 else -16), ha="center",
                                fontsize=9, color=col)
        q = max(r["part2"]["query_only"][f"e0.2_{x}"]["acc"] for x in ("by_gain", "by_failure"))
        ax.plot([0], [q], "*", color="black", ms=16, label="query only (0 s)", zorder=5)
        for y, c, lab in [(b["always_local"], BLUE, "always-local"),
                          (b["always_cloud"], MAG, "always-cloud"),
                          (b["random"], "black", "random at e=0.2")]:
            ax.axhline(y, color=c, lw=1.2, ls=":" if lab != "random at e=0.2" else "--")
            left = lab == "random at e=0.2"
            ax.text(0.30 if left else 0.995, y, lab + " ",
                    transform=ax.get_yaxis_transform(),
                    ha="right", va="bottom", fontsize=9, color=c)
        ax.set_xlabel("decision latency (s)")
        ax.set_ylabel("accuracy at e = 0.2 (%)")
        ax.set_title(f"{wl.upper()}  n={r['n']}", fontsize=13, loc="left", pad=26)
        ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.01, 0.97), ncol=2)
        fig.tight_layout()
        fig.savefig(FIG / f"r8a_utility_{wl}{TAG}.png", dpi=200)
        plt.close(fig)
        print(f"  wrote r8a_utility_{wl}.png")

        # AUROC against k, device-incorrect and (S-EMBER) evidence outside the window
        tgts = ["device_incorrect"] + (["evidence_outside_window"]
                                       if "evidence_outside_window" in r["part1"]["query_only"]
                                       else [])
        fig, axes = plt.subplots(1, len(tgts), figsize=(6.2 * len(tgts), 4.6), squeeze=False)
        for ax, tgt in zip(axes[0], tgts):
            for pre, col, mk, lab in FAMILY:
                xs, ys, los, his = [], [], [], []
                for key, row in r["part1"].items():
                    if not key.startswith(pre + "_k") or row["k"] in (None, "full"):
                        continue
                    xs.append(row["k"]); ys.append(row[tgt]["auroc"])
                    los.append(row[tgt]["ci"][0]); his.append(row[tgt]["ci"][1])
                if not xs:
                    continue
                o = np.argsort(xs)
                xs = np.array(xs)[o]; ys = np.array(ys)[o]
                los = np.array(los)[o]; his = np.array(his)[o]
                ax.plot(xs, ys, mk + "-", color=col, ms=6, lw=1.6, label=lab)
                ax.fill_between(xs, los, his, color=col, alpha=0.10)
            qa = r["part1"]["query_only"][tgt]["auroc"]
            ax.axhline(qa, color="black", lw=1.4, ls="--")
            ax.text(0.01, qa, f" query only {qa:.3f}", transform=ax.get_yaxis_transform(),
                    va="bottom", fontsize=9)
            ax.axhline(0.5, color=GREY, lw=1, ls=":")
            ax.set_xlabel("prefix length k (tokens)")
            ax.set_ylabel("held-out AUROC")
            ax.set_title(tgt.replace("_", " "), fontsize=12, loc="left")
            ax.legend(frameon=False, fontsize=9)
        fig.suptitle(f"{wl.upper()}  n={r['n']}", fontsize=13, x=0.01, ha="left")
        fig.tight_layout()
        fig.savefig(FIG / f"r8a_auroc_{wl}{TAG}.png", dpi=200)
        plt.close(fig)
        print(f"  wrote r8a_auroc_{wl}.png")

    # rescue matrix
    rm = d["results"]["sember"].get("part3_rescue_matrix")
    if rm:
        c = rm["counts"]
        keys = ["history_rescuable_either", "capability_rescuable", "both_needed", "none"]
        labs = ["history\nrescuable", "capability\nrescuable", "both\nneeded", "neither"]
        fig, ax = plt.subplots(figsize=(6.4, 4.4))
        ax.bar(range(len(keys)), [c[k] for k in keys],
               color=[GREEN, BLUE, ORANGE, GREY], width=0.6)
        for i, k in enumerate(keys):
            ax.text(i, c[k] + 3, str(c[k]), ha="center", fontsize=12, fontweight="bold")
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels(labs)
        ax.set_ylabel("questions")
        ax.set_title(f"S-EMBER: what would rescue the {c['device_fails']} device failures",
                     fontsize=12, loc="left")
        fig.tight_layout()
        fig.savefig(FIG / f"r8a_rescue_matrix{TAG}.png", dpi=200)
        plt.close(fig)
        print("  wrote r8a_rescue_matrix.png")


if __name__ == "__main__":
    main()
