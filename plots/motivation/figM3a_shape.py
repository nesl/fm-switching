"""M3a Shape trade-off.

One point per rebuild shape (one go / 2,048-token pieces / 1,024-token pieces):
x = the job's own TTFT (s), y = total delay imposed on others (s, log). Medians
with 95% bootstrap CI bars in both directions (unit resampled = trial).

Source: StudyENG1c-hostfull Part D, cold-tier arrivals on the host-full (capped)
servers (27, 38, 60 GiB), both loads. results/cost/study_eng1c/eng1c_results.json
(D.trials). Report reproduced: reports/study_eng1c_hostfull.md section 6 and
verdict D (cold mono ~14 s; pieces ~6 s / ~3 s at +0.7 to +1.1 s job TTFT; pieces
impose about 4 to 5x less than a monolithic rebuild).
Caching: prefix caching ON; the host tier is full (write-through, ongoing LRU
eviction); every cold arrival is a fresh rebuild (0 cached-token mismatches).
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
D = json.load(open(F.ROOT / "results/cost/study_eng1c/eng1c_results.json"))["D"]["trials"]

shapes = [("mono", "one go", F.C_ONEGO, F.MARK["onego"]),
          ("piece2048", "2,048 pieces", F.C_PIECE2048, F.MARK["piece2048"]),
          ("piece1024", "1,024 pieces", F.C_PIECE1024, F.MARK["piece1024"])]

pts = {}
for key, label, color, marker in shapes:
    sel = [r for r in D if r["variant"] == key and r["cap"] in (27, 38, 60) and r["tier"] == "cold"]
    ttft = np.array([r["job_ttft"] for r in sel])
    imp = np.array([r["imposed_s"] for r in sel])
    mt = float(np.median(ttft)); mi = float(np.median(imp))
    tlo, thi = F.boot_ci(ttft, stat=np.median, n=2000, seed=0)
    ilo, ihi = F.boot_ci(imp, stat=np.median, n=2000, seed=0)
    pts[key] = dict(label=label, color=color, marker=marker, n=len(sel),
                    ttft=mt, imp=mi, ttft_ci=(tlo, thi), imp_ci=(ilo, ihi))

fig, ax = plt.subplots(figsize=(F.COL1, 2.15))
for key, label, color, marker in shapes:
    p = pts[key]
    ax.errorbar(p["ttft"], p["imp"],
                xerr=[[p["ttft"] - p["ttft_ci"][0]], [p["ttft_ci"][1] - p["ttft"]]],
                yerr=[[p["imp"] - p["imp_ci"][0]], [p["imp_ci"][1] - p["imp"]]],
                fmt=marker, color=color, ecolor=color, elinewidth=0.8, capsize=2,
                markersize=6, markeredgecolor="white", markeredgewidth=0.5, label=label)
ax.set_yscale("log")
from matplotlib.ticker import FixedLocator, FixedFormatter, NullLocator
ax.yaxis.set_major_locator(FixedLocator([3, 6, 10, 20]))
ax.yaxis.set_major_formatter(FixedFormatter(["3", "6", "10", "20"]))
ax.yaxis.set_minor_locator(NullLocator())
ax.set_xlabel("Job's own TTFT (s)")
ax.set_ylabel("Delay imposed on others (s, log)")
ax.set_xlim(2.0, 3.7)
ax.set_ylim(2.3, 22)
ax.legend(loc="upper right", handlelength=0.8, labelspacing=0.3)

red = pts["mono"]["imp"] / pts["piece1024"]["imp"]
dttft = pts["piece1024"]["ttft"] - pts["mono"]["ttft"]
# arrow from mono to 1024 shape
ax.annotate("", xy=(pts["piece1024"]["ttft"], pts["piece1024"]["imp"]),
            xytext=(pts["mono"]["ttft"], pts["mono"]["imp"]),
            arrowprops=dict(arrowstyle="->", lw=0.7, color="black", alpha=0.6))
ax.annotate(f"{red:.1f}x less delay", (2.75, 7.2), fontsize=6.8, fontweight="bold")
ax.annotate(f"for +{dttft:.1f} s TTFT", (2.9, 3.7), fontsize=6.8)

pdf, png = F.save(fig, "figM3a_shape")

payload = {
    "figure": "M3a",
    "message": "Rebuilding a cold history as small pieces instead of one request cuts the delay it imposes on others several-fold, for about one extra second of the job's own TTFT.",
    "subset": "StudyENG1c Part D, cold-tier arrivals, capped (host-full) servers 27/38/60 GiB, both loads",
    "error_bars": "95% bootstrap CI of the median, 2000 resamples seed 0, unit = trial",
    "points": {k: {"n": pts[k]["n"], "job_ttft_median_s": round(pts[k]["ttft"], 3),
                   "imposed_median_s": round(pts[k]["imp"], 3),
                   "ttft_ci": [round(x, 3) for x in pts[k]["ttft_ci"]],
                   "imposed_ci": [round(x, 3) for x in pts[k]["imp_ci"]]} for k in pts},
    "reduction_factor_mono_over_1024": round(red, 2),
    "ttft_cost_mono_to_1024_s": round(dttft, 3),
    "report": "reports/study_eng1c_hostfull.md section 6, verdict D, implication 5",
    "report_values": {"cold_job_ttft_mono": "2.24-2.32", "cold_job_ttft_2048": "2.8-3.0",
                      "cold_job_ttft_1024": "3.3-3.4", "cold_imposed_mono": "14.0-16.5",
                      "cold_imposed_2048": "3.8-6.2", "cold_imposed_1024": "2.9-3.6",
                      "reduction_factor": "4 to 5x", "ttft_cost": "+0.7 to +1.1 s"},
    "checks": {
        "mono_ttft_in_range": 2.24 <= pts["mono"]["ttft"] <= 2.32,
        "piece2048_ttft_in_range": 2.8 <= pts["piece2048"]["ttft"] <= 3.0,
        "piece1024_ttft_in_range": 3.3 <= pts["piece1024"]["ttft"] <= 3.4,
        "mono_imp_in_range": 14.0 <= pts["mono"]["imp"] <= 16.5,
        "piece2048_imp_in_range": 3.8 <= pts["piece2048"]["imp"] <= 6.2,
        "piece1024_imp_in_range": 2.9 <= pts["piece1024"]["imp"] <= 3.6,
        "reduction_in_4to5": 4.0 <= red <= 5.0, "ttft_cost_in_range": 0.7 <= round(dttft, 1) <= 1.1},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM3a_shape", payload))
print("M3a done.", {k: (round(pts[k]["ttft"], 3), round(pts[k]["imp"], 3), pts[k]["n"]) for k in pts},
      "reduction", round(red, 2), "ttft_cost", round(dttft, 3))
