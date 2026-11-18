"""M7 Day in the life (revision 3, amendment 2 Part B, roomy 256 GiB host).

One robot question served four ways against a fleet of 20 dashcams monitored on the
cloud. (a) the CUMULATIVE count of extra missed dashcam deadlines (the action's misses
minus the paired no-question NONE control's, counted per instant at its 0.916 s
deadline), versus time since the robot's question; one curve per action (one go, 2,048
pieces, 1,024 pieces, host-warm), thick line = median over the 5 repetitions at each
time, light band = min to max over the repetitions, each curve tagged at its right end
with its final median count. (b) the robot's own answer time per action, bar = median,
whiskers = min to max over the 5 repetitions, dashed line at the robot's 5 s deadline
(D71).

Message: with a cold history, one go disrupts the fleet and small pieces make the robot
late; a warm history avoids both.

Source (read-only): results/motivation/mot1/mot1_requests.jsonl.gz (raw per-instant
records, Part B runs labelled A2BR1..A2BR5, each action paired to its own-repetition
NONE control) and results/motivation/mot1/mot1_figdata_amend2.json (per-repetition robot
TTFT and the summary medians). Report reproduced: reports/study_mot1_dayinlife.md
section 10.3 (extra missed median 59 / 28 / 0 / 0; robot TTFT from the question 3.56 /
6.10 / 6.87 / 0.69 s; N = 20, deadline 0.916 s, question at 20 s, HOST in 5 of 5 for
host-warm) and section 10.2 (Part A tight host).
Caching: prefix caching ON; the 256 GiB host holds the warmed history so host-warm is a
host reload (measured HOST in 5 of 5), while one go and the pieces rebuild from cold; the
dashcam monitoring is the live one-request-per-2 s-per-stream service load.
"""
import gzip
import json
import numpy as np
import matplotlib.pyplot as plt
import figstyle as F

F.apply_style()
ROOT = F.ROOT
DL = 0.916          # dashcam deadline, submit-to-last-token, server side
Q_AT = 20.0         # the robot question lands at t0 + 20 s in every run
REPS = range(1, 6)

# ---- (a) cumulative extra missed from the raw per-instant records ----------
# For each Part B run, collect each missed monitor instant's deadline time relative
# to the robot question (t_submit + 0.916 - (t0 + 20)).
miss = {}            # (rep, action) -> sorted array of miss deadline-times
with gzip.open(ROOT / "results/motivation/mot1/mot1_requests.jsonl.gz", "rt") as fh:
    for line in fh:
        r = json.loads(line)
        if r["kind"] != "monitor" or not r["label"].startswith("A2BR"):
            continue
        key = (r["rep"], r["action"])
        missed = (r["error"] is not None) or (r["e2e_s"] is None) or (r["e2e_s"] > DL)
        if missed:
            miss.setdefault(key, []).append(r["t_submit"] + DL - (r["t0"] + Q_AT))
miss = {k: np.array(sorted(v)) for k, v in miss.items()}

XLO, XHI = -2.0, 15.0
grid = np.arange(XLO, XHI + 1e-9, 0.05)
acts = [("ONE-GO", "one go", F.C_ONEGO, "-"),
        ("P2048", "2,048 pieces", F.C_PIECE2048, "--"),
        ("P1024", "1,024 pieces", F.C_PIECE1024, ":"),
        ("HOST-WARM", "host-warm", F.C_WARM, "-.")]


def cum(times):
    return np.searchsorted(times, grid, side="right") if len(times) else np.zeros_like(grid, dtype=int)


curve = {}           # action -> (median, lo, hi) over reps, and final median
for a, _, _, _ in acts:
    stack = []
    for rep in REPS:
        extra = cum(miss.get((rep, a), np.array([]))) - cum(miss.get((rep, "NONE"), np.array([])))
        stack.append(extra)
    M = np.array(stack)
    curve[a] = dict(median=np.median(M, axis=0), lo=M.min(0), hi=M.max(0),
                    final_median=float(np.median(M[:, -1])),
                    final_per_rep=[int(x) for x in M[:, -1]])

# ---- (b) robot answer time per action, from the figure data ----------------
fd = json.load(open(ROOT / "results/motivation/mot1/mot1_figdata_amend2.json"))
rob = {}
for a, _, _, _ in acts:
    reps = fd["robot_ttft_s"][a]["per_rep"]
    rob[a] = dict(median=float(np.median(reps)), lo=float(min(reps)), hi=float(max(reps)),
                  per_rep=reps)
TARGET = 5.0         # robot answer-time deadline, D71

# Part A tight-host flush count (caption block, not a plotted line)
partA = fd["partA_tight_host"]["runs"]
k_flushed = sum(1 for r in partA if r["measured_tier"] != "HOST")

# ---- figure ----------------------------------------------------------------
fig = plt.figure(figsize=(F.COL1, 2.2))
gs = fig.add_gridspec(1, 2, wspace=0.52, width_ratios=[1.22, 1.25])
axa = fig.add_subplot(gs[0, 0])
axb = fig.add_subplot(gs[0, 1])

# (a) cumulative curves: band, then median step, with direct curve labels
XR = 16.0                                   # right edge, leaving room for end counts
for a, lab, c, ls in acts:
    cv = curve[a]
    axa.fill_between(grid, cv["lo"], cv["hi"], step="post", color=c, alpha=0.16, linewidth=0)
for a, lab, c, ls in acts:
    cv = curve[a]
    axa.step(grid, cv["median"], where="post", color=c, lw=1.6, ls=ls)
axa.axvline(0, color="black", lw=0.8, ls=":")
axa.text(-0.4, 40, "question", fontsize=6.2, color="black", rotation=90, va="center", ha="right")
axa.set_xlabel("Time since robot question (s)")
axa.set_ylabel("Cumulative extra\nmissed deadlines")
axa.set_xlim(XLO, XR)
axa.set_ylim(-4, 82)
axa.set_xticks([0, 5, 10, 15])
# direct curve labels (name riding the plateau) + final median count at the right end.
# The 1,024-pieces and host-warm curves coincide at y = 0; both lines are kept, but their
# two end labels are replaced by one neutral-grey label just above the zero line.
name_pos = {"ONE-GO": (9.0, 63), "P2048": (6.2, 32)}
cnt_y = {"ONE-GO": 59, "P2048": 28}
for a, lab, c, ls in acts:
    if a not in name_pos:
        continue
    axa.text(*name_pos[a], lab, fontsize=5.8, color=c, va="center", ha="left", fontweight="bold")
    axa.text(15.4, cnt_y[a], f"{int(curve[a]['final_median'])}", fontsize=6.6, color=c,
             va="center", ha="left", fontweight="bold")
axa.text(15.6, 4.0, "1,024 pieces, host-warm: 0", fontsize=5.6, color="#404040",
         va="center", ha="right", fontweight="bold")
axa.text(0.02, 0.97, "(a)", transform=axa.transAxes, fontsize=8, va="top", fontweight="bold")

# (b) robot answer time per action
xb = np.arange(len(acts))
for i, (a, lab, c, ls) in enumerate(acts):
    m = rob[a]["median"]
    axb.bar(i, m, 0.68, color=c, edgecolor="white", linewidth=0.4)
    axb.errorbar(i, m, yerr=[[m - rob[a]["lo"]], [rob[a]["hi"] - m]], fmt="none",
                 ecolor="black", elinewidth=0.7, capsize=1.8)
axb.axhline(TARGET, ls="--", lw=0.9, color="black")
axb.text(-0.55, TARGET + 0.15, "robot deadline 5 s", ha="left", va="bottom", fontsize=5.8)
axb.set_xticks(xb)
axb.set_xticklabels(["one\ngo", "2,048\npieces", "1,024\npieces", "host-\nwarm"], fontsize=4.9)
axb.set_ylabel("Robot answer time (s)")
axb.set_ylim(0, 9)
axb.set_xlim(-0.65, len(acts) - 0.35)
axb.text(0.04, 0.97, "(b)", transform=axb.transAxes, fontsize=8, va="top", fontweight="bold")

pdf, png = F.save(fig, "figM7_dayinlife")

# ---- JSON record -----------------------------------------------------------
payload = {
    "figure": "M7",
    "revision": 3,
    "message": "With a cold history, one go disrupts the fleet and small pieces make the robot late; a warm history avoids both.",
    "design": "amendment 2 Part B only (roomy 256 GiB host, all five actions, one consistent paired set); panel (a) computed from the raw per-instant records, not from the 0.5 s bin fractions.",
    "sources": {
        "panel_a_raw": "results/motivation/mot1/mot1_requests.jsonl.gz (kind=monitor, label A2BR1..A2BR5; each action paired to its own-repetition NONE control)",
        "panel_b": "results/motivation/mot1/mot1_figdata_amend2.json robot_ttft_s per_rep",
    },
    "N_dashcams": fd["N"], "deadline_s": fd["deadline_s"], "question_at_s": Q_AT,
    "panel_a_definition": "cumulative (action missed instants minus paired NONE missed instants) ordered by each instant's deadline time = t_submit + 0.916 - (t0 + 20); thick line = median over 5 reps at each time, band = min to max over reps",
    "panel_a_final_extra_missed": {a: {"median": int(curve[a]["final_median"]),
                                       "per_rep": curve[a]["final_per_rep"],
                                       "min": int(min(curve[a]["final_per_rep"])),
                                       "max": int(max(curve[a]["final_per_rep"]))} for a, _, _, _ in acts},
    "panel_b_robot_ttft_s": {a: {"median": round(rob[a]["median"], 4), "per_rep": rob[a]["per_rep"],
                                 "min": round(rob[a]["lo"], 4), "max": round(rob[a]["hi"], 4)} for a, _, _, _ in acts},
    "robot_deadline_s": TARGET,
    "hostwarm_measured_tier_partB": [t["tier"] for t in fd["hostwarm_measured_tiers"]],
    "partA_tight_host": {"measured_tier": [r["measured_tier"] for r in partA],
                         "k_flushed_of_5": k_flushed,
                         "caption_sentence": f"With tight host memory (27 GiB), the warmed history had been flushed by question time in {k_flushed} of 5 runs."},
    "report": "reports/study_mot1_dayinlife.md sections 10.2 and 10.3",
    "report_values": {"extra_missed_median": {"ONE-GO": 59, "P2048": 28, "P1024": 0, "HOST-WARM": 0},
                      "robot_ttft_from_question": {"ONE-GO": 3.56, "P2048": 6.10, "P1024": 6.87, "HOST-WARM": 0.69},
                      "N": 20, "deadline_s": 0.916, "question_at_s": 20,
                      "hostwarm_tier": "HOST in 5 of 5", "partA_flushed": "COLD in 5 of 5"},
    "checks": {
        "extra_onego": int(curve["ONE-GO"]["final_median"]) == 59,
        "extra_2048": int(curve["P2048"]["final_median"]) == 28,
        "extra_1024": int(curve["P1024"]["final_median"]) == 0,
        "extra_hostwarm": int(curve["HOST-WARM"]["final_median"]) == 0,
        "robot_onego": F.ratio(rob["ONE-GO"]["median"], 3.56),
        "robot_2048": F.ratio(rob["P2048"]["median"], 6.10),
        "robot_1024": F.ratio(rob["P1024"]["median"], 6.87),
        "robot_hostwarm": F.ratio(rob["HOST-WARM"]["median"], 0.69),
        "hostwarm_all_HOST": all(t["tier"] == "HOST" for t in fd["hostwarm_measured_tiers"]),
        "partA_all_flushed": k_flushed == 5,
        "N_is_20": fd["N"] == 20},
    "outputs": {"pdf": pdf, "png": png},
}
print(F.dump_json("figM7_dayinlife", payload))
print("M7 rev3 done. extra_median",
      {a: int(curve[a]["final_median"]) for a, _, _, _ in acts},
      "robot_median", {a: round(rob[a]["median"], 2) for a, _, _, _ in acts},
      "hostwarm_tiers", [t["tier"] for t in fd["hostwarm_measured_tiers"]],
      "partA_flushed", k_flushed)
