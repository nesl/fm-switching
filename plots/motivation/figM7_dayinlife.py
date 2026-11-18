"""M7 Day in the life.

One robot question, served three ways, against a fleet of 20 dashcams monitored on
the cloud. (a) the fraction of the 20 dashcams missing their 0.916 s deadline per 0.5 s
bin, around the question; one line per action (one go, 2,048 pieces, 1,024 pieces) and
a thin grey no-question control at zero. (b) the robot's own answer time per action,
with a dashed line at the robot's 5 s target (D71).

Message: one robot question in one go disrupts the whole fleet; small pieces remove
that but push the robot past its own deadline; no fixed shape serves both.

Source (read-only): results/motivation/mot1/mot1_figdata.json (representative
repetition 3, the repetition whose one-go extra-miss count is the median of the 5;
never the HOLDOUT or the failed first design). Report reproduced:
reports/study_mot1_dayinlife.md section 6 (extra missed 57 / 24 / 0; robot TTFT from
the question 3.47 / 5.90 / 6.79 s; N = 20, deadline 0.916 s, question at 20 s).
Caching: prefix caching ON; the robot's history is a cold ~11k rebuild in every run;
the dashcam monitoring requests are the live 25 percent-per-device service share.
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
d = json.load(open(F.ROOT / "results/motivation/mot1/mot1_figdata.json"))

bin_s = d["bin_s"]; q_at = d["question_at_s"]
frac = d["frac_streams_missing_per_bin"]
t = np.arange(len(frac["ONE-GO"])) * bin_s - q_at           # time relative to the question
acts = [("ONE-GO", "one go", F.C_ONEGO), ("P2048", "2,048 pieces", F.C_PIECE2048),
        ("P1024", "1,024 pieces", F.C_PIECE1024)]
extra = {a: d["summary"][a]["extra_missed"]["median"] for a, _, _ in acts}
rob_med = {a: d["summary"][a]["robot_ttft_s"]["median"] for a, _, _ in acts}
rob_rep = {a: d["summary"][a]["robot_ttft_s"]["per_rep"] for a, _, _ in acts}
TARGET = 5.0   # robot answer-time target, D71

fig = plt.figure(figsize=(F.COL1, 2.15))
gs = fig.add_gridspec(1, 3, wspace=0.62, width_ratios=[1.15, 1.15, 1])
axa = fig.add_subplot(gs[0, :2])
axb = fig.add_subplot(gs[0, 2])

# window: about 10 s before to 15 s after
lo, hi = -10, 15
m = (t >= lo) & (t <= hi)
# no-question control (thin grey at 0)
axa.step(t[m], np.array(frac["NONE"])[m], where="mid", color=F.C_WITHOUT, lw=0.8,
         label="no question")
for key, lab, c in acts:
    axa.step(t[m], np.array(frac[key])[m], where="mid", color=c, lw=1.3, label=lab)
axa.axvline(0, color="black", lw=0.8, ls=":")
axa.set_xlabel("Time around question (s)")
axa.set_ylabel("Fraction of 20 dashcams\nmissing deadline")
axa.set_xlim(lo, hi); axa.set_ylim(-0.03, 1.15)
# legend in the empty right half of the window
axa.legend(loc="center right", handlelength=1.0, labelspacing=0.3, fontsize=6.0,
           borderaxespad=0.3)
# "question" marker label, upper-left of the line
axa.text(-0.6, 1.08, "question", ha="right", fontsize=6.2, color="black")
# extra-missed annotations in the empty upper-left, coloured by action
axa.text(lo + 0.4, 1.02, "extra missed:", fontsize=6.2, va="top")
axa.text(lo + 0.4, 0.90, f"{extra['ONE-GO']}", fontsize=7, va="top", color=F.C_ONEGO, fontweight="bold")
axa.text(lo + 2.6, 0.90, f"{extra['P2048']}", fontsize=7, va="top", color=F.C_PIECE2048, fontweight="bold")
axa.text(lo + 4.4, 0.90, f"{extra['P1024']}", fontsize=7, va="top", color=F.C_PIECE1024, fontweight="bold")
axa.text(0.02, 0.97, "(a)", transform=axa.transAxes, fontsize=8, va="top", fontweight="bold")

# (b) robot answer time per action
xb = np.arange(3)
for i, (key, lab, c) in enumerate(acts):
    med = rob_med[key]; reps = rob_rep[key]
    axb.bar(i, med, 0.66, color=c, edgecolor="white", linewidth=0.4)
    axb.errorbar(i, med, yerr=[[med - min(reps)], [max(reps) - med]], fmt="none",
                 ecolor="black", elinewidth=0.7, capsize=1.8)
axb.axhline(TARGET, ls="--", lw=0.9, color="black")
axb.text(2.4, TARGET + 0.12, "5 s target", ha="right", va="bottom", fontsize=6.2)
axb.set_xticks(xb)
axb.set_xticklabels(["one\ngo", "2048\npc", "1024\npc"], fontsize=6.3)
axb.set_ylabel("Robot answer time (s)")
axb.set_ylim(0, 8)
axb.text(0.05, 0.97, "(b)", transform=axb.transAxes, fontsize=8, va="top", fontweight="bold")

pdf, png = F.save(fig, "figM7_dayinlife")

payload = {
    "figure": "M7",
    "message": "One robot question in one go disrupts the whole fleet; small pieces remove that but push the robot past its own deadline; no fixed shape serves both.",
    "source_file": "results/motivation/mot1/mot1_figdata.json (representative repetition 3)",
    "representative_rep": d["representative_rep"],
    "representative_rule": d["representative_rule"],
    "N_dashcams": d["N"], "deadline_s": d["deadline_s"], "bin_s": bin_s, "question_at_s": q_at,
    "panel_a_extra_missed_median": extra,
    "panel_b_robot_ttft_s": {a: {"median": round(rob_med[a], 3), "per_rep": rob_rep[a],
                                 "min": min(rob_rep[a]), "max": max(rob_rep[a])} for a, _, _ in acts},
    "robot_target_s": TARGET,
    "report": "reports/study_mot1_dayinlife.md section 6",
    "report_values": {"extra_missed": {"ONE-GO": 57, "P2048": 24, "P1024": 0},
                      "robot_ttft_from_question": {"ONE-GO": 3.47, "P2048": 5.90, "P1024": 6.79},
                      "N": 20, "deadline_s": 0.916, "question_at_s": 20},
    "checks": {
        "extra_onego": extra["ONE-GO"] == 57, "extra_2048": extra["P2048"] == 24, "extra_1024": extra["P1024"] == 0,
        "robot_onego": F.ratio(rob_med["ONE-GO"], 3.47), "robot_2048": F.ratio(rob_med["P2048"], 5.90),
        "robot_1024": F.ratio(rob_med["P1024"], 6.79),
        "rep_is_3": d["representative_rep"] == 3, "N_is_20": d["N"] == 20},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM7_dayinlife", payload))
print("M7 done. extra", extra, "robot_med", {a: round(rob_med[a], 2) for a, _, _ in acts},
      "rep", d["representative_rep"])
