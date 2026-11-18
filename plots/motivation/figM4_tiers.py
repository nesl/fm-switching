"""M4 Storage tiers (3 panels, double column).

(a) restore TTFT at 11k for cold / host / disk.
(b) delay imposed on others at P40 (log s) for the same three states.
(c) per-load restore TTFT for 1, 2, 4 simultaneous disk loads, unloaded, with a
    dashed line at the cold solo median.

Source: StudyENG1f-disk Parts 1-3 (FIT only), results/cost/study_eng1f/eng1f_results.json.
Report reproduced: reports/study_eng1f_disk.md sections 5, 6, 7.
Caching: cold = image bytes, no KV anywhere; host-warm = KV on host tier; disk =
KV on the local NVMe disk tier (O_DIRECT, page cache verified empty by fincore).
All TTFTs are solo unloaded except panel (b), which is the delay imposed on
concurrent background traffic at load P40.
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
d = json.load(open(F.ROOT / "results/cost/study_eng1f/eng1f_results.json"))

# ---- data ------------------------------------------------------------------
states = ["cold", "host", "disk"]
colors = {"cold": F.C_COLD, "host": F.C_HOST, "disk": F.C_DISK}
hatches = {"cold": F.HATCH["cold"], "host": F.HATCH["host"], "disk": F.HATCH["disk"]}

# (a) restore TTFT 11k
a = {s: d["part1"][f"11k|{s}"]["ttft_s"] for s in states}
# (b) imposed delay P40
b = {s: d["part2_P40"][s]["imposed_lat_s"] for s in states}
# (c) concurrent disk loads
c = {k: d["part3"][f"unloaded|{k}"]["per_load_ttft_s"] for k in ["k1", "k2", "k4"]}
cold_solo = d["part1"]["11k|cold"]["ttft_s"]["median"]

fig = plt.figure(figsize=(F.COL2, 2.05))
gs = fig.add_gridspec(1, 3, wspace=0.42, width_ratios=[1, 1, 1.15])
axa, axb, axc = (fig.add_subplot(gs[0, i]) for i in range(3))

# ---- (a) restore TTFT ------------------------------------------------------
x = np.arange(3)
for i, s in enumerate(states):
    m = a[s]["median"]
    axa.bar(i, m, 0.62, color=colors[s], hatch=hatches[s], edgecolor="white", linewidth=0.4)
    axa.errorbar(i, m, yerr=[[m - a[s]["p10"]], [a[s]["p90"] - m]], fmt="none",
                 ecolor="black", elinewidth=0.7, capsize=1.8)
    axa.text(i, m + 0.06, f"{m:.2f}", ha="center", va="bottom", fontsize=6.5)
axa.set_xticks(x); axa.set_xticklabels(["cold", "host", "disk"])
axa.set_ylabel("Restore TTFT at 11k (s)")
axa.set_ylim(0, 3.1)
disk_frac = a["disk"]["median"] / a["cold"]["median"]
axa.annotate(f"disk {disk_frac:.2f}x cold", (2, a["disk"]["median"]), xytext=(1.6, 2.1),
             ha="center", va="center", fontsize=6.5,
             arrowprops=dict(arrowstyle="->", lw=0.6, color="black"))
axa.set_title("(a)", loc="left", fontsize=8)

# ---- (b) imposed delay (log) ----------------------------------------------
FLOOR = 0.03
for i, s in enumerate(states):
    m = b[s]["median"]
    axb.bar(i, max(m, FLOOR), 0.62, bottom=0, color=colors[s], hatch=hatches[s],
            edgecolor="white", linewidth=0.4)
    hi = b[s]["p90"]
    if hi > m:
        axb.errorbar(i, m, yerr=[[0], [hi - m]], fmt="none", ecolor="black", elinewidth=0.7, capsize=1.8)
    axb.text(i, max(m, FLOOR) * 1.25, f"{m:.2f}", ha="center", va="bottom", fontsize=6.5)
axb.set_yscale("log")
axb.set_ylim(FLOOR, 90)
axb.set_xticks(x); axb.set_xticklabels(["cold", "host", "disk"])
axb.set_ylabel("Delay imposed on\nothers at P40 (s, log)")
fold = b["cold"]["median"] / b["disk"]["median"]
axb.annotate(f"cold imposes\n{fold:.0f}x more", (1.5, 4.0), ha="center", va="center",
             fontsize=6.6, fontweight="bold", color=F.C_COLD)
axb.set_title("(b)", loc="left", fontsize=8)

# ---- (c) concurrent disk loads --------------------------------------------
ks = [1, 2, 4]
med = [c["k1"]["median"], c["k2"]["median"], c["k4"]["median"]]
p10 = [c["k1"]["p10"], c["k2"]["p10"], c["k4"]["p10"]]
p90 = [c["k1"]["p90"], c["k2"]["p90"], c["k4"]["p90"]]
yerr = [[m - lo for m, lo in zip(med, p10)], [hi - m for m, hi in zip(med, p90)]]
axc.errorbar(ks, med, yerr=yerr, fmt="-o", color=F.C_DISK, ecolor="black",
             elinewidth=0.7, capsize=2, markersize=3.5, markerfacecolor=F.C_DISK,
             markeredgecolor="white", markeredgewidth=0.4)
axc.axhline(cold_solo, ls="--", lw=0.8, color=F.C_COLD)
axc.text(1.05, cold_solo + 0.08, f"cold solo recompute {cold_solo:.2f} s",
         fontsize=6.3, color=F.C_COLD, va="bottom")
axc.set_xticks(ks); axc.set_xlabel("simultaneous disk loads")
axc.set_ylabel("Per-load restore TTFT (s)")
axc.set_ylim(0, 4.0)
axc.annotate("4 at once slower\nthan one recompute", (4, med[2]), xytext=(2.3, 3.6),
             ha="center", fontsize=6.3,
             arrowprops=dict(arrowstyle="->", lw=0.6))
axc.set_title("(c)", loc="left", fontsize=8)

pdf, png = F.save(fig, "figM4_tiers")

payload = {
    "figure": "M4",
    "message": "A host- or disk-warm restore is far cheaper than a cold rebuild and imposes almost nothing on others, but concurrent disk restores serialize on disk bandwidth.",
    "source_file": "results/cost/study_eng1f/eng1f_results.json (Parts 1-3, FIT only)",
    "report": "reports/study_eng1f_disk.md sections 5 (Part 1), 6 (Part 2), 7 (Part 3)",
    "panel_a_restore_ttft_11k_s": {s: {"median": a[s]["median"], "p10": a[s]["p10"], "p90": a[s]["p90"]} for s in states},
    "panel_a_report": {"cold": 2.687, "host": 0.203, "disk": 1.149},
    "panel_b_imposed_P40_s": {s: {"median": b[s]["median"], "p10": b[s]["p10"], "p90": b[s]["p90"], "ci95": b[s]["ci95"]} for s in states},
    "panel_b_report": {"cold": 36.54, "host": 0.14, "disk": 0.10},
    "panel_c_per_load_ttft_s": {k: {"median": c[k]["median"], "p10": c[k]["p10"], "p90": c[k]["p90"]} for k in c},
    "panel_c_report": {"k1": 1.121, "k2": 1.858, "k4": 3.530, "cold_solo_dashed": 2.687},
    "annotations": {"restore_11k_disk_over_cold_frac": round(disk_frac, 2),
                    "restore_11k_disk_over_cold_report": 0.43,
                    "imposed_cold_over_disk": round(fold, 0)},
    "checks": {
        "a_cold": F.ratio(a["cold"]["median"], 2.687), "a_host": F.ratio(a["host"]["median"], 0.203),
        "a_disk": F.ratio(a["disk"]["median"], 1.149),
        "b_cold": F.ratio(b["cold"]["median"], 36.54), "b_host": F.ratio(b["host"]["median"], 0.14),
        "b_disk": F.ratio(b["disk"]["median"], 0.10),
        "c_k1": F.ratio(c["k1"]["median"], 1.121), "c_k2": F.ratio(c["k2"]["median"], 1.858),
        "c_k4": F.ratio(c["k4"]["median"], 3.530), "c_dashed": F.ratio(cold_solo, 2.687)},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM4_tiers", payload))
print("M4 done. a:", {s: round(a[s]['median'], 3) for s in states},
      "b:", {s: round(b[s]['median'], 2) for s in states},
      "c:", [round(m, 3) for m in med], "cold_solo", round(cold_solo, 3))
