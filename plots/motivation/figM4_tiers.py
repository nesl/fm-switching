"""M4 Storage tiers (revision 1): the three readiness tiers of the problem setting,
GPU-warm / host / cold. Disk is NOT a tier yet (design log D78, Q12), so it is not
shown here; StudyENG1f's disk data is kept for a separate later figure.

(a) the job's restore TTFT at the 11,184-token history for GPU-warm / host / cold,
    all from StudyENG1 Part D conc 1 (same study, same history): 0.10 / 0.17 / 2.74 s
    (spec v4 section 5.3). Medians with p10-p90 spread.
(b) delay imposed on other requests under load for the same three states, from the
    one study that measured all three under one load, StudyENG1c Part D (by tier at
    arrival, mono action, host-full capped servers). GPU-warm and host impose about
    0 s; cold imposes about 14 s.
(c) capacity: number of 11,184-token histories each tier holds under the round-1
    capacities (D76): GPU pool 62,944 tokens, host beyond the GPU pool at 27 GiB
    (47,648 tokens) and 256 GiB (985,632 tokens), cold unbounded.

Sources (read-only): results/cost/study_eng1/eng1_partD_requests_h100nvl.jsonl,
results/cost/study_eng1/eng1_results.json (D.conc1),
results/cost/study_eng1c/eng1c_results.json (D.trials), and the committed cap table
in reports/study_eng1c_hostfull.md section 1.
Caching: (a) cold = image bytes, no KV; host = KV on host tier; GPU-warm = KV resident
on the GPU. (b) same states measured as the injected job's tier at arrival under a
background load.
"""
import json, statistics
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
ROOT = F.ROOT

# ---- (a) restore TTFT by tier, ENG1 Part D conc 1 --------------------------
d1 = [json.loads(l) for l in open(ROOT / "results/cost/study_eng1/eng1_partD_requests_h100nvl.jsonl")]
probe = [r for r in d1 if r.get("kind") == "query" and r.get("conc") == 1 and r.get("role") is None and r.get("ttft_s")]
a = {}
for st in ["gpu", "host", "cold"]:
    v = np.array([r["ttft_s"] for r in probe if r.get("state") == st])
    a[st] = dict(n=len(v), median=float(np.median(v)), p10=float(np.percentile(v, 10)),
                 p90=float(np.percentile(v, 90)))

# ---- (b) imposed delay under load by tier, ENG1c Part D (mono, capped) ------
D = json.load(open(ROOT / "results/cost/study_eng1c/eng1c_results.json"))["D"]["trials"]
capped = [r for r in D if r["cap"] in (27, 38, 60) and r["variant"] == "mono"]
b = {}
for st in ["gpu", "host", "cold"]:
    v = np.array([r["imposed_s"] for r in capped if r["tier"] == st])
    lo, hi = F.boot_ci(v, stat=np.median, n=2000, seed=0)
    b[st] = dict(n=len(v), median=float(np.median(v)), ci=(lo, hi),
                 lo=float(np.min(v)), hi=float(np.max(v)))

# ---- (c) capacity: 11,184-token histories per tier -------------------------
HIST = 11184
GPU_POOL = 62944
HOST27_BEYOND = 47648      # 27 GiB: 110,592 host tokens - 62,944 GPU pool
HOST256_BEYOND = 985632    # 256 GiB: 1,048,576 - 62,944
cap = {
    "GPU pool": GPU_POOL / HIST,
    "host +27 GiB": HOST27_BEYOND / HIST,
    "host +256 GiB": HOST256_BEYOND / HIST,
}

# ---- figure ----------------------------------------------------------------
fig = plt.figure(figsize=(F.COL2, 2.1))
gs = fig.add_gridspec(1, 3, wspace=0.42, width_ratios=[1, 1, 1.25])
axa, axb, axc = (fig.add_subplot(gs[0, i]) for i in range(3))
col = {"gpu": F.C_GPUWARM, "host": F.C_HOST, "cold": F.C_COLD}
hatch = {"gpu": F.HATCH["gpuwarm"], "host": F.HATCH["host"], "cold": F.HATCH["cold"]}
labels = {"gpu": "GPU\nwarm", "host": "host", "cold": "cold"}
order = ["gpu", "host", "cold"]

# (a)
for i, st in enumerate(order):
    m = a[st]["median"]
    axa.bar(i, m, 0.62, color=col[st], hatch=hatch[st], edgecolor="white", linewidth=0.4)
    axa.errorbar(i, m, yerr=[[m - a[st]["p10"]], [a[st]["p90"] - m]], fmt="none",
                 ecolor="black", elinewidth=0.7, capsize=1.8)
    axa.text(i, m + 0.06, f"{m:.2f}", ha="center", va="bottom", fontsize=6.5)
axa.set_xticks(range(3)); axa.set_xticklabels([labels[s] for s in order])
axa.set_ylabel("Restore TTFT at 11k (s)")
axa.set_ylim(0, 3.1)
axa.text(0.02, 0.96, "(a)", transform=axa.transAxes, fontsize=8, va="top", fontweight="bold")

# (b)
for i, st in enumerate(order):
    m = b[st]["median"]
    axb.bar(i, m, 0.62, color=col[st], hatch=hatch[st], edgecolor="white", linewidth=0.4)
    axb.errorbar(i, m, yerr=[[max(m - b[st]["ci"][0], 0)], [max(b[st]["ci"][1] - m, 0)]],
                 fmt="none", ecolor="black", elinewidth=0.7, capsize=1.8)
    tag = f"{m:.1f}" if m > 1 else "~0"
    axb.text(i, m + 0.4, tag, ha="center", va="bottom", fontsize=6.5)
axb.set_xticks(range(3)); axb.set_xticklabels([labels[s] for s in order])
axb.set_ylabel("Delay imposed on\nothers under load (s)")
axb.set_ylim(0, 17)
axb.text(0.02, 0.96, "(b)", transform=axb.transAxes, fontsize=8, va="top", fontweight="bold")

# (c) capacity, log y; cold unbounded as an up-arrow
cx = list(cap.keys())
cv = [cap[k] for k in cx]
ccol = [F.C_GPUWARM, F.C_HOST, F.C_HOST]
chatch = [F.HATCH["gpuwarm"], F.HATCH["host"], F.HATCH["host"]]
for i, (k, v) in enumerate(zip(cx, cv)):
    axc.bar(i, v, 0.6, color=ccol[i], hatch=chatch[i], edgecolor="white", linewidth=0.4)
    axc.text(i, v * 1.12, f"{v:.0f}", ha="center", va="bottom", fontsize=6.5)
# cold unbounded
axc.annotate("", xy=(3, 300), xytext=(3, 30),
             arrowprops=dict(arrowstyle="->", lw=1.2, color=F.C_COLD))
axc.text(3, 4, "cold:\nunbounded", ha="center", va="center", fontsize=6.4, color=F.C_COLD)
axc.set_yscale("log")
axc.set_ylim(1, 500)
axc.set_xticks(range(4))
axc.set_xticklabels(["GPU\npool", "host\n+27G", "host\n+256G", "cold"])
axc.set_ylabel("11k histories held (log)")
axc.text(0.02, 0.96, "(c)", transform=axc.transAxes, fontsize=8, va="top", fontweight="bold")

pdf, png = F.save(fig, "figM4_tiers")

payload = {
    "figure": "M4",
    "message": "Faster tiers are far cheaper for everyone but hold only a handful of histories; cold is unbounded but slow and disruptive.",
    "note": "Disk is NOT a tier yet (design log D78, Q12); the disk panel of the prior version was removed. StudyENG1f disk data kept for a later figure.",
    "panel_a": {
        "source": "results/cost/study_eng1/eng1_partD_requests_h100nvl.jsonl (kind=query, conc=1, role=None); results/cost/study_eng1/eng1_results.json D.conc1",
        "restore_ttft_11k_s": {s: {"n": a[s]["n"], "median": round(a[s]["median"], 5),
                                   "p10": round(a[s]["p10"], 4), "p90": round(a[s]["p90"], 4)} for s in order},
        "report": "spec v4 section 5.3 / reports/study_eng1_steptime.md Part D (0.10 / 0.17 / 2.74 s)",
        "report_values": {"gpu": 0.10, "host": 0.17, "cold": 2.74},
        "checks": {"gpu": F.ratio(a["gpu"]["median"], 0.10), "host": F.ratio(a["host"]["median"], 0.17),
                   "cold": F.ratio(a["cold"]["median"], 2.74)}},
    "panel_b": {
        "source": "results/cost/study_eng1c/eng1c_results.json D.trials (variant=mono, caps 27/38/60, by tier at arrival)",
        "error_bars": "95% bootstrap CI of the median, 2000 resamples seed 0, unit = trial",
        "imposed_under_load_s": {s: {"n": b[s]["n"], "median": round(b[s]["median"], 3),
                                     "ci": [round(x, 3) for x in b[s]["ci"]]} for s in order},
        "report": "reports/study_eng1c_hostfull.md section 6 (cold mono imposed 14.0-16.5 s; host-warm ~0 s; GPU-warm imposed -0.3 to 0.2 s)",
        "report_values": {"cold_mono": "14.0-16.5", "host": "~0", "gpu": "-0.3 to 0.2"},
        "checks": {"cold_in_range": 14.0 <= b["cold"]["median"] <= 16.5,
                   "gpu_near_zero": -0.3 <= b["gpu"]["median"] <= 0.2,
                   "host_near_zero": abs(b["host"]["median"]) < 1.0,
                   "all_three_measured_under_load": all(b[s]["n"] > 0 for s in order)}},
    "panel_c": {
        "history_tokens": HIST,
        "arithmetic": {
            "GPU pool": {"tokens": GPU_POOL, "histories": round(cap["GPU pool"], 2),
                         "calc": f"{GPU_POOL}/{HIST}", "note": "working space for in-flight requests reduces this in practice"},
            "host +27 GiB beyond GPU pool": {"tokens": HOST27_BEYOND, "histories": round(cap["host +27 GiB"], 2),
                                             "calc": f"(110592-62944)/{HIST} = {HOST27_BEYOND}/{HIST}"},
            "host +256 GiB beyond GPU pool": {"tokens": HOST256_BEYOND, "histories": round(cap["host +256 GiB"], 2),
                                              "calc": f"(1048576-62944)/{HIST} = {HOST256_BEYOND}/{HIST}"},
            "cold": "unbounded"},
        "report": "reports/study_eng1c_hostfull.md section 1 cap table (GPU pool 62,944; 27 GiB beyond 47,648; 256 GiB beyond 985,632); D76 round-1 capacities",
        "checks": {"gpu_hist": F.ratio(cap["GPU pool"], 62944 / 11184),
                   "host27_hist": F.ratio(cap["host +27 GiB"], 47648 / 11184),
                   "host256_hist": F.ratio(cap["host +256 GiB"], 985632 / 11184)}},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM4_tiers", payload))
print("M4 done. (a)", {s: round(a[s]["median"], 3) for s in order},
      "(b)", {s: round(b[s]["median"], 3) for s in order},
      "(c)", {k: round(v, 2) for k, v in cap.items()})
