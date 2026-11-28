#!/usr/bin/env python3
"""Paper Figure 17: real deployment. NO real-deployment data exists (reports/figdata/F17.csv has 0 rows; READINESS.md:
"F17: placeholder, no real-deployment data exists"). This script draws the empty axes, labels and legend with a centred
"NO DATA YET: real-deployment data". It reads nothing. Axis semantics are provisional (on-time rate against time in the
deployment); they change when the deployment protocol is fixed. usage: python3 -I f17_real_deployment.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402


def main():
    def build(fig, mode):
        ax = fig.add_axes([0.14, 0.17, 0.83, 0.7])
        P.style_axes(ax, xgrid=False)
        ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xticks([0, 0.5, 1])
        ax.set_xticklabels(["", "", ""])
        ax.set_xlabel("deployment time (provisional axis)", fontsize=P.FS_AXLABEL)
        ax.set_ylabel("on-time rate (provisional axis)", fontsize=P.FS_AXLABEL)
        from matplotlib.lines import Line2D
        h = [Line2D([0], [0], color=P.COLORS["covex"], lw=1.2), Line2D([0], [0], color=P.COLORS["stateful"], lw=1.2),
             Line2D([0], [0], color=P.COLORS["stateless"], lw=1.2)]
        ax.legend(h, ["COVEX", "stateful baseline", "stateless baseline"], loc="upper left", fontsize=P.FS_TEXT,
                  frameon=False, ncol=1, columnspacing=0.9, handlelength=1.4, borderaxespad=0.1)
        fig.text(0.555, 0.5, "NO DATA YET: real-deployment data", ha="center", va="center", fontsize=P.FS_TEXT,
                 color=P.COLORS["tag"])

    caption = "Real deployment. No real-deployment data exists yet; the panel shows empty axes and legend only."
    P.save_figure(build, "F17_real_deployment", P.SINGLE_IN, 2.4, [], [], caption, "NO DATA: no real-deployment data exists")
    import json
    j = json.loads((P.OUTDIR / "F17_real_deployment.rows.json").read_text())
    j["status_tag"] = "NO DATA"
    (P.OUTDIR / "F17_real_deployment.rows.json").write_text(json.dumps(j, indent=1))
    (P.OUTDIR / "F17_real_deployment.caption.txt").write_text("[PLACEHOLDER: NO DATA, no real-deployment data exists] " + caption + "\n")
    P.compile_preview("F17_real_deployment", caption)


if __name__ == "__main__":
    main()
