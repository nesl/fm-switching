"""M1 Cloud value (two panels).

(a) S-EMBER recall accuracy: device (4B, RECENT window) vs cloud (32B, RICH
    history), split by whether the evidence lies inside or outside the device's
    120 s window (StudyR1's own evidence_covered split).
(b) Monitoring challenge mAP: device-only vs always-cloud (StudyCTRL1b).

Committed sources, read-only:
  results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz   (K1 = 32B-I RICH)
  results/sember/study_o/study_o_q4_trials_fa2.jsonl           (4B-I RECENT)
  results/dashcam/ctrl1b/ctrl1b_crossfit.json
Reports reproduced: reports/study_r1_cloud32b_sember.md (Accuracy table),
                    reports/study_ctrl1b_crossfit.md (sections 3, 3.1).
Caching: StudyR1 accuracy rows prefix caching OFF (batched); CTRL1b is CPU-only
replay of committed traces (no caching involved).
"""
import json, gzip
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
ROOT = F.ROOT

# ---------------- Panel (a) data: StudyR1 accuracy split -------------------
r1 = [json.loads(l) for l in gzip.open(
    ROOT / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "rt")]
acc = [r for r in r1 if r["mode"] == "batched"]
# per-question evidence coverage from the RECENT construction (report: StudyO field)
covered = {r["question_id"]: r["evidence_covered"] for r in acc if r["construction"] == "RECENT"}
k1 = [r for r in acc if r["cell"] == "K1"]                      # 32B-I RICH (cloud)

o = [json.loads(l) for l in open(ROOT / "results/sember/study_o/study_o_q4_trials_fa2.jsonl")]
o4 = [r for r in o if r["model_arm"] == "4B-I" and r["state_arm"] == "RECENT"]  # device

def split_correct(rows):
    out = {True: [], False: []}
    for r in rows:
        c = covered.get(r["question_id"])
        if c is None:
            continue
        out[c].append(1 if r["correct"] else 0)
    return out

cloud = split_correct(k1)
device = split_correct(o4)

# groups: outside window (covered==False, misses), inside window (covered==True)
groups = [("Evidence outside\nwindow", False), ("Evidence inside\nwindow", True)]
prov_a = {}
dev_acc, dev_ci, clo_acc, clo_ci, gains, ns = [], [], [], [], [], []
for label, cov in groups:
    dv = device[cov]; cl = cloud[cov]
    da = 100 * np.mean(dv); ca = 100 * np.mean(cl)
    dlo, dhi = F.boot_ci(np.array(dv) * 100, n=2000, seed=0)
    clo_lo, clo_hi = F.boot_ci(np.array(cl) * 100, n=2000, seed=0)
    dev_acc.append(da); clo_acc.append(ca)
    dev_ci.append((dlo, dhi)); clo_ci.append((clo_lo, clo_hi))
    # gain as the difference of the rounded bar heights (what the reader reads,
    # and what the report's accuracy table implies: 42.3-20.6, 39.2-34.4)
    gains.append(round(ca, 1) - round(da, 1)); ns.append((len(dv), len(cl)))
    prov_a[label.replace("\n", " ")] = {
        "n_questions": len(dv),
        "device_4B_RECENT_acc_pct": round(da, 1),
        "cloud_32B_RICH_acc_pct": round(ca, 1),
        "gain_pp": round(ca, 1) - round(da, 1),
    }

# ---------------- Panel (b) data: StudyCTRL1b mAP ---------------------------
cb = json.load(open(ROOT / "results/dashcam/ctrl1b/ctrl1b_crossfit.json"))
b20 = cb["by_budget"]["0.2"]
mdev = b20["challenge_mAP"]["device-only"]
mcloud = b20["challenge_mAP"]["always-cloud"]
mdev_ci = b20["challenge_mAP_ci"]["device-only"]
mcloud_ci = b20["challenge_mAP_ci"]["always-cloud"]
gap = b20["paired_differences"]["always-cloud minus device-only"]["difference"]
gap_ci = b20["paired_differences"]["always-cloud minus device-only"]["ci"]

# ---------------- Figure ----------------------------------------------------
fig = plt.figure(figsize=(F.COL1, 2.0))
gs = fig.add_gridspec(1, 3, wspace=0.65)
axa = fig.add_subplot(gs[0, :2])
axb = fig.add_subplot(gs[0, 2])

x = np.arange(len(groups)); w = 0.36
for i in range(len(groups)):
    axa.bar(x[i] - w / 2, dev_acc[i], w, color=F.C_DEVICE, hatch=F.HATCH["device"],
            edgecolor="white", linewidth=0.4, label="Device 4B (recent)" if i == 0 else None)
    axa.bar(x[i] + w / 2, clo_acc[i], w, color=F.C_CLOUD, hatch=F.HATCH["cloud"],
            edgecolor="white", linewidth=0.4, label="Cloud 32B (full)" if i == 0 else None)
    axa.errorbar(x[i] - w / 2, dev_acc[i], yerr=[[dev_acc[i] - dev_ci[i][0]], [dev_ci[i][1] - dev_acc[i]]],
                 fmt="none", ecolor="black", elinewidth=0.7, capsize=1.6)
    axa.errorbar(x[i] + w / 2, clo_acc[i], yerr=[[clo_acc[i] - clo_ci[i][0]], [clo_ci[i][1] - clo_acc[i]]],
                 fmt="none", ecolor="black", elinewidth=0.7, capsize=1.6)
    # gain annotation just above the taller error bar of the group
    ytop = max(clo_ci[i][1], dev_ci[i][1])
    axa.annotate(f"+{gains[i]:.1f} pp", (x[i], ytop + 1.2), ha="center", va="bottom",
                 fontsize=7, fontweight="bold",
                 color=(F.C_CLOUD if gains[i] > 10 else "black"))
axa.set_xticks(x); axa.set_xticklabels([g[0] for g in groups])
axa.set_ylabel("Recall accuracy (%)")
axa.set_ylim(0, 58)
axa.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, handlelength=1.0,
           columnspacing=1.0, borderaxespad=0.0, fontsize=6.6)
axa.text(0.015, 0.03, "(a)", transform=axa.transAxes, fontsize=8, va="bottom", fontweight="bold")

# panel b
xb = np.arange(2)
axb.bar(0, mdev, 0.6, color=F.C_DEVICE, hatch=F.HATCH["device"], edgecolor="white", linewidth=0.4)
axb.bar(1, mcloud, 0.6, color=F.C_CLOUD, hatch=F.HATCH["cloud"], edgecolor="white", linewidth=0.4)
axb.errorbar(0, mdev, yerr=[[mdev - mdev_ci[0]], [mdev_ci[1] - mdev]], fmt="none", ecolor="black", elinewidth=0.7, capsize=1.6)
axb.errorbar(1, mcloud, yerr=[[mcloud - mcloud_ci[0]], [mcloud_ci[1] - mcloud]], fmt="none", ecolor="black", elinewidth=0.7, capsize=1.6)
axb.set_xticks(xb); axb.set_xticklabels(["device", "cloud"])
axb.set_ylabel("Challenge mAP")
axb.set_ylim(0, 0.78)
axb.annotate(f"+{gap:.3f}", (0.5, mcloud_ci[1] + 0.015), ha="center", va="bottom",
             fontsize=7, fontweight="bold", color=F.C_CLOUD)
axb.text(0.04, 0.03, "(b)", transform=axb.transAxes, fontsize=8, va="bottom", fontweight="bold")

pdf, png = F.save(fig, "figM1_cloud_value")

# ---------------- provenance JSON ------------------------------------------
payload = {
    "figure": "M1",
    "message": "The cloud helps most when the evidence has fallen out of the device's recent window; on the monitoring task the cloud tier is also more accurate.",
    "panel_a": {
        "source_file": "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz (K1=32B-I RICH), results/sember/study_o/study_o_q4_trials_fa2.jsonl (4B-I RECENT)",
        "split": "StudyR1 evidence_covered from the RECENT construction; outside=False (misses), inside=True (covers)",
        "error_bars": "95% bootstrap CI, 2000 resamples seed 0, unit = question",
        "values": prov_a,
        "report": "reports/study_r1_cloud32b_sember.md Accuracy table",
        "report_values": {
            "cloud_32B_RICH_misses_pct": 42.3, "cloud_32B_RICH_covers_pct": 39.2,
            "device_4B_RECENT_misses_pct": 20.6, "device_4B_RECENT_covers_pct": 34.4,
            "n_misses": 97, "n_covers": 748},
        "checks": {
            "cloud_misses_ratio": F.ratio(prov_a["Evidence outside window"]["cloud_32B_RICH_acc_pct"], 42.3),
            "cloud_covers_ratio": F.ratio(prov_a["Evidence inside window"]["cloud_32B_RICH_acc_pct"], 39.2),
            "device_misses_ratio": F.ratio(prov_a["Evidence outside window"]["device_4B_RECENT_acc_pct"], 20.6),
            "device_covers_ratio": F.ratio(prov_a["Evidence inside window"]["device_4B_RECENT_acc_pct"], 34.4),
            "n_misses_match": ns[0] == (97, 97), "n_covers_match": ns[1] == (748, 748)},
    },
    "panel_b": {
        "source_file": "results/dashcam/ctrl1b/ctrl1b_crossfit.json (by_budget 0.2, cross-fitted, all 300 clips held out)",
        "error_bars": "committed 95% CI, 2000 paired clip resamples seed 0",
        "device_only_mAP": mdev, "always_cloud_mAP": mcloud,
        "device_only_ci": mdev_ci, "always_cloud_ci": mcloud_ci,
        "gap": gap, "gap_ci": gap_ci,
        "report": "reports/study_ctrl1b_crossfit.md sections 3, 3.1",
        "report_values": {"device_only": 0.4776, "always_cloud": 0.5675,
                          "gap": 0.0899, "gap_ci": [0.0357, 0.1497]},
        "checks": {"device_ratio": F.ratio(mdev, 0.4776), "cloud_ratio": F.ratio(mcloud, 0.5675),
                   "gap_ratio": F.ratio(gap, 0.0899)},
    },
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM1_cloud_value", payload))
print("M1 done:", prov_a, "| mAP dev/cloud", round(mdev, 4), round(mcloud, 4), "gap", round(gap, 4))
