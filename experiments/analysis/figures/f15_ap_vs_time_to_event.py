#!/usr/bin/env python3
"""Paper Figure 15: Nexar AP versus time-to-event, cloud versus device (StudyEARLY1). OFFLINE, committed data.

Source: reports/figures/early1_results.json (StudyEARLY1, committed 2026-11-23; pipeline: experiments/analysis/early1/early1.py).
F15.csv holds only a gap pointer row; the series are read from the committed EARLY1 results. Proxy: the device series is the
Qwen3-VL-4B model and the cloud series the Qwen3-VL-32B model on the SAME 300 Nexar validation clips (150 positive, 150
negative), split ALL, AP at t = 0.5 .. 3.0 s before the event; 95 percent bootstrap CI over source videos (2000 resamples).
Format epg-2fps (StudySH-EP, the 2 fps episodic format the cloud sees in the workload). These are MODEL-level
measurements, not system arms, so they carry no DEV/OLD arm status; the figure is marked as a committed model-level
measurement and not as FINAL (a reviewer should not read it as a COVEX result).
usage: python3 -I f15_ap_vs_time_to_event.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

SRC = "reports/figures/early1_results.json"
FMT = "epg-2fps (StudySH-EP)"
ONE = "one-frame (StudyD14b, N=1)"


def main():
    d = json.loads((P.REPO / SRC).read_text())
    hs = d["horizons"]
    res = {}
    for fmt in (FMT, ONE):
        sp = d["formats"][fmt]["splits"]["ALL"]["by_model"]
        res[fmt] = {m: ([sp[m]["ap"][str(h)]["ap"] for h in hs], [sp[m]["ap"][str(h)]["ci"] for h in hs])
                    for m in ("4B", "32B")}
        res[fmt]["base"] = d["formats"][fmt]["splits"]["ALL"]["base_rate_by_horizon"]
    cloud_col, dev_col = P.COLORS["stateful"], P.COLORS["device"]

    def build(fig, mode):
        ax = fig.add_axes([0.14, 0.18, 0.83, 0.76])
        P.style_axes(ax, xgrid=False)
        ax.yaxis.grid(True, color=P.COLORS["grid"], lw=0.4)
        for fmt, ls, mk in ((FMT, "-", "o"), (ONE, (0, (3, 1.5)), "s")):
            for m, col, lab in (("32B", cloud_col, "cloud 32B"), ("4B", dev_col, "device 4B")):
                ap, ci = res[fmt][m]
                if fmt == FMT:
                    ax.fill_between(hs, [c[0] for c in ci], [c[1] for c in ci], color=col, alpha=0.15, lw=0)
                ax.plot(hs, ap, color=col, lw=1.1 if fmt == FMT else 0.8, ls=ls, marker=mk, ms=3,
                        mfc=col if fmt == FMT else "white", mew=0.7,
                        label=f"{lab}, " + ("2 fps episode" if fmt == FMT else "one frame"))
        ax.axhline(0.5, color=P.COLORS["tag"], lw=0.5, ls=":")
        ax.set_xlabel("time to event (s)", fontsize=P.FS_AXLABEL)
        ax.set_ylabel("Nexar AP", fontsize=P.FS_AXLABEL)
        ax.set_xticks(hs)
        ax.set_ylim(0, 0.9)
        ax.legend(loc="upper right", fontsize=P.FS_TEXT - 0.5, frameon=False, handlelength=2.2, labelspacing=0.25)

    caption = ("Crash-anticipation average precision (Nexar, 300 validation clips) versus time to event for the cloud model "
               "(Qwen3-VL-32B) and the on-device model (Qwen3-VL-4B), model-level measurement from StudyEARLY1 with 95 percent "
               "bootstrap bands over source videos for the 2 fps episodic format; the one-frame format is dashed. Dotted line "
               "is the chance level (0.5 for the 2 fps format). Cloud delivery latency (median 0.69 s) is not charged here.")
    rows = [{"status": "committed model-level measurement (not a system arm; no DEV/OLD)", "arm": f"{m} ({fmt})",
             "seed": "n/a (bootstrap seed 0)", "run_dir": SRC, "run_commit": "committed-study (StudyEARLY1)",
             "pipeline_sha": "n/a", "split": "ALL", "horizons_s": hs, "ap": res[fmt][m][0], "ap_ci95": res[fmt][m][1]}
            for fmt in (FMT, ONE) for m in ("4B", "32B")]
    P.save_figure(build, "F15_ap_vs_time_to_event", P.SINGLE_IN, 2.5, [], rows, caption, None)
    cap = P.OUTDIR / "F15_ap_vs_time_to_event.caption.txt"
    cap.write_text("[PLACEHOLDER: committed model-level measurement, StudyEARLY1; no COVEX data, not FINAL] " + caption + "\n")
    j = json.loads((P.OUTDIR / "F15_ap_vs_time_to_event.rows.json").read_text())
    j["status_tag"] = "committed model-level measurement (no OLD/DEV arm plotted); F15.csv itself is a gap pointer row"
    (P.OUTDIR / "F15_ap_vs_time_to_event.rows.json").write_text(json.dumps(j, indent=1))
    P.compile_preview("F15_ap_vs_time_to_event", caption)
    print({m: [round(x, 3) for x in res[FMT][m][0]] for m in ("4B", "32B")})


if __name__ == "__main__":
    main()
