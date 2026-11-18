"""M5 Predictability.

Predicted (x) vs measured (y) delay imposed on others, log-log, with the y = x
line. Points are the held-back pairs of StudyT0b's one-shot (the StudyENG1c Part D
and StudyENG1d holdouts), scored exactly as T0b scored them, coloured by action
(one go / pieces / reload-warm). Annotates the ranking agreement and the chain
over-prediction factor as reported.

Sources (read-only):
  results/orchestration/study_t0b/t0b_holdout_eng1c.json
  results/orchestration/study_t0b/t0b_holdout_eng1d.json
Report reproduced: reports/study_t0b_fidelity.md section 8A (one-shot): ranking
(ii) 0.9500 (ENG1c) / 1.0000 (ENG1d); over-prediction concentrated in chained
piece rebuilds (predicted/measured median ratios 1.5 to 1.9x).
Caching: these are a CPU-only replay of the frozen cost model against committed
H100 measurements; no inference and no caching in the scoring itself. Tier at
arrival (cold vs warm) is the measurement's own recorded residency.
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
ROOT = F.ROOT
FLOOR = 0.02   # log-axis floor; warm/near-zero delays are clamped here (noted)

ec = json.load(open(ROOT / "results/orchestration/study_t0b/t0b_holdout_eng1c.json"))
ed = json.load(open(ROOT / "results/orchestration/study_t0b/t0b_holdout_eng1d.json"))

# tier per ENG1c holdout trial (reload-warm vs cold rebuild)
tier = {r["key"]: r["measured_state"] for r in ec["residency"]["rows"]}


def action_cat(cell, key, warmable):
    if warmable and tier.get(key, "cold") != "cold":
        return "warm"
    return "onego" if "mono11k" in cell else "pieces"


points = []   # (pred, meas, cat, source)
for d, src, warmable in [(ec, "ENG1c", True), (ed, "ENG1d", False)]:
    for t in d["latency"]["per_trial"]:
        points.append((t["predicted_delay_s"], t["measured_delay_s"],
                       action_cat(t["cell"], t["key"], warmable), src))

cats = {"onego": ("one go", F.C_ONEGO, F.MARK["onego"]),
        "pieces": ("pieces", F.C_PIECES, F.MARK["pieces"]),
        "warm": ("reload / warm", F.C_WARM, F.MARK["warm"])}

fig, ax = plt.subplots(figsize=(F.COL1, 2.6))
lim_lo, lim_hi = FLOOR, 100
ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], ls="--", lw=0.8, color="black", alpha=0.6, zorder=1)
for cat, (label, color, marker) in cats.items():
    xs = [max(p, FLOOR) for p, m, c, s in points if c == cat]
    ys = [max(m, FLOOR) for p, m, c, s in points if c == cat]
    ax.scatter(xs, ys, s=14, color=color, marker=marker, edgecolor="white",
               linewidth=0.3, alpha=0.85, label=label, zorder=3)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlim(lim_lo, lim_hi); ax.set_ylim(lim_lo, lim_hi)
ax.set_xlabel("Predicted delay imposed on others (s, log)")
ax.set_ylabel("Measured delay (s, log)")
ax.set_aspect("equal")
ax.legend(loc="lower right", handlelength=0.8, labelspacing=0.3)
ax.text(0.05, 0.93, "y = x", transform=ax.transAxes, fontsize=6.5, rotation=0, color="black")

# ---- reported quantities ---------------------------------------------------
rank_ec = ec["latency"]["ranking"]["pairs"]
rank_ed = ed["latency"]["ranking"]["pairs"]
ec_agree = sum(1 for p in rank_ec if p.get("included") and p.get("agree"))
ec_incl = sum(1 for p in rank_ec if p.get("included"))
ed_agree = sum(1 for p in rank_ed if p.get("included") and p.get("agree"))
ed_incl = sum(1 for p in rank_ed if p.get("included"))

# chain over-prediction, per piece size on the ENG1c holdout (report section 8A.1):
# predicted median / measured median.
def size_ratio(size):
    m = [t["measured_delay_s"] for t in ec["latency"]["per_trial"] if size in t["cell"]]
    p = [t["predicted_delay_s"] for t in ec["latency"]["per_trial"] if size in t["cell"]]
    return float(np.median(p)) / float(np.median(m))

r2048 = size_ratio("piece2048"); r1024 = size_ratio("piece1024")
lo, hi = min(r2048, r1024), max(r2048, r1024)

ax.annotate(f"ranking {ec_agree}/{ec_incl} (ENG1c), {ed_agree}/{ed_incl} (ENG1d)",
            (0.03, 0.80), xycoords="axes fraction", fontsize=6.2, va="top")
ax.annotate(f"chains over-predicted {lo:.1f}-{hi:.1f}x", (0.03, 0.72),
            xycoords="axes fraction", fontsize=6.2, va="top", color=F.C_PIECES)

pdf, png = F.save(fig, "figM5_predictability")

from collections import Counter
catcount = Counter(c for _, _, c, _ in points)
payload = {
    "figure": "M5",
    "message": "The cost model tracks the measured imposed delay and ranks actions correctly, but systematically over-predicts the delay of chained piece rebuilds (points above y=x).",
    "n_points": len(points), "category_counts": dict(catcount),
    "floor_s": FLOOR, "floor_note": "warm / near-zero (and the few negative) delays clamped to the log-axis floor",
    "sources": ["results/orchestration/study_t0b/t0b_holdout_eng1c.json (120 pairs)",
                "results/orchestration/study_t0b/t0b_holdout_eng1d.json (60 pairs)"],
    "ranking_agreement": {"ENG1c": f"{ec_agree}/{ec_incl}", "ENG1d": f"{ed_agree}/{ed_incl}",
                          "ENG1c_fraction": round(ec_agree / ec_incl, 4), "ENG1d_fraction": round(ed_agree / ed_incl, 4)},
    "chain_overprediction_eng1c_holdout": {"piece2048": round(r2048, 3), "piece1024": round(r1024, 3)},
    "report": "reports/study_t0b_fidelity.md section 8A.1",
    "report_values": {"ranking_ENG1c": 0.9500, "ranking_ENG1d": 1.0000,
                      "holdout_piece2048_meas_med": 5.267, "holdout_piece2048_pred_med": 7.780,
                      "holdout_piece1024_meas_med": 2.804, "holdout_piece1024_pred_med": 5.290,
                      "holdout_piece2048_ratio": round(7.780 / 5.267, 3),
                      "holdout_piece1024_ratio": round(5.290 / 2.804, 3),
                      "POL5_chain_overprediction": "1.6 to 1.8x"},
    "checks": {"ranking_ENG1c": F.ratio(round(ec_agree / ec_incl, 4), 0.9500),
               "ranking_ENG1d": F.ratio(round(ed_agree / ed_incl, 4), 1.0000),
               "piece2048_ratio_vs_report": F.ratio(r2048, 7.780 / 5.267),
               "piece1024_ratio_vs_report": F.ratio(r1024, 5.290 / 2.804)},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM5_predictability", payload))
print("M5 done. points", len(points), catcount, "rank", f"{ec_agree}/{ec_incl}", f"{ed_agree}/{ed_incl}",
      "chain 2048/1024", round(r2048, 3), round(r1024, 3))
