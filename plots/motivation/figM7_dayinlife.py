"""M7 Day in the life (revision 4): one trade-off panel in the style of M3a.

One point per action served against a fleet of 20 dashcams monitored on the cloud,
with one robot question needing its ~11k-token history:
  x = the robot's own answer time from the question (s)
  y = extra dashcam deadlines missed over the no-question control (count)
Median over the 5 paired Part B repetitions, with min-to-max whiskers in both
directions. A dashed vertical line marks the robot's 5 s deadline; the shaded box is
the only good region (robot on time and the fleet unharmed). Only the host-warm recall
lands in it: one go harms the fleet, and the pieces only trade the harm for a late robot.

Message: only a warm history answers the robot on time and leaves the fleet unharmed;
a cold history in one go harms the fleet, and cutting it into pieces only trades that
harm for a late robot.

Sources (read-only): results/motivation/mot1/mot1_requests.jsonl.gz (raw per-instant
records, Part B runs A2BR1..A2BR5, each action paired to its own-repetition NONE control)
for the extra-missed counts, and results/motivation/mot1/mot1_figdata_amend2.json for the
robot answer times. Report: reports/study_mot1_dayinlife.md sections 10.2 and 10.3 (extra
missed median 59 / 28 / 0 / 0; robot TTFT from the question 3.56 / 6.10 / 6.87 / 0.69 s;
HOST in 5 of 5 for host-warm; Part A tight host flushed COLD in 5 of 5). N = 20, deadline
0.916 s, question at 20 s.
Caching: prefix caching ON; one go and the pieces rebuild the ~11k history from cold,
host-warm is a host reload (measured on the host tier in 5 of 5 Part B runs); the dashcams
run the live one-request-per-two-seconds (66 % of the one-frame peak) service load.
The cumulative-over-time computation of the old panel (a) is retained in the JSON record.
"""
import gzip
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import figstyle as F

F.apply_style()
ROOT = F.ROOT
DL = 0.916          # dashcam deadline, submit-to-last-token, server side
Q_AT = 20.0         # the robot question lands at t0 + 20 s in every run
REPS = range(1, 6)

acts = [("ONE-GO", "one go", F.C_ONEGO, F.MARK["onego"]),
        ("P2048", "2,048 pieces", F.C_PIECE2048, F.MARK["piece2048"]),
        ("P1024", "1,024 pieces", F.C_PIECE1024, F.MARK["piece1024"]),
        ("HOST-WARM", "host-warm", F.C_HOSTWARM, F.MARK["hostwarm"])]

# ---- extra missed from the raw per-instant records (also the time series) --
miss = {}            # (rep, action) -> sorted array of miss deadline-times vs question
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

grid = np.arange(-2.0, 15.0001, 0.05)      # kept only for the JSON record


def cum(times):
    return np.searchsorted(times, grid, side="right") if len(times) else np.zeros_like(grid, dtype=int)


extra = {}           # action -> per-rep final counts + median/min/max; plus time series
timeseries = {}
for a, _, _, _ in acts:
    stack = []
    for rep in REPS:
        e = cum(miss.get((rep, a), np.array([]))) - cum(miss.get((rep, "NONE"), np.array([])))
        stack.append(e)
    M = np.array(stack)
    finals = [int(x) for x in M[:, -1]]
    extra[a] = dict(median=float(np.median(finals)), lo=min(finals), hi=max(finals), per_rep=finals)
    # retain the cumulative-over-time computation (downsampled to 0.25 s) for the record
    step = 5                                # 0.05 s grid -> 0.25 s
    timeseries[a] = dict(t=[round(float(x), 2) for x in grid[::step]],
                         median=[int(x) for x in np.median(M, axis=0)[::step]],
                         min=[int(x) for x in M.min(0)[::step]],
                         max=[int(x) for x in M.max(0)[::step]])

# ---- robot answer time per action, from the figure data --------------------
fd = json.load(open(ROOT / "results/motivation/mot1/mot1_figdata_amend2.json"))
rob = {}
for a, _, _, _ in acts:
    reps = fd["robot_ttft_s"][a]["per_rep"]
    rob[a] = dict(median=float(np.median(reps)), lo=float(min(reps)), hi=float(max(reps)), per_rep=reps)
TARGET = 5.0         # robot answer-time deadline, D71

partA = fd["partA_tight_host"]["runs"]
k_flushed = sum(1 for r in partA if r["measured_tier"] != "HOST")

# ---- figure: one panel, M3a style ------------------------------------------
fig, ax = plt.subplots(figsize=(F.COL1, 2.15))
XLO, XHI, YLO, YHI = 0.0, 8.7, -4.0, 80.0

# the only good region: robot on time (x < 5) and fleet unharmed (y near 0)
ax.add_patch(Rectangle((XLO, 0), TARGET - XLO, 3.0, facecolor=F.OI["grey"], alpha=0.16,
                       edgecolor="none", zorder=0))
ax.text(2.5, 1.5, "robot on time,\nfleet unharmed", ha="center", va="center",
        fontsize=5.6, color="#555555", zorder=1)
ax.axvline(TARGET, color="black", lw=0.9, ls="--")
ax.text(4.86, 40, "robot deadline", rotation=90, ha="right", va="center", fontsize=6.2)

for a, lab, c, mk in acts:
    x, y = rob[a]["median"], extra[a]["median"]
    ax.errorbar(x, y, xerr=[[x - rob[a]["lo"]], [rob[a]["hi"] - x]],
                yerr=[[y - extra[a]["lo"]], [extra[a]["hi"] - y]],
                fmt=mk, color=c, ecolor=c, elinewidth=0.8, capsize=2,
                markersize=6, markeredgecolor="white", markeredgewidth=0.5, zorder=3)

# direct point labels (no legend box)
lab_pos = {"ONE-GO": (3.56, 77, "center", "bottom"),
           "P2048": (6.10, 44, "center", "bottom"),
           "P1024": (6.87, 6.5, "center", "bottom"),
           "HOST-WARM": (0.69, -2.6, "center", "top")}
for a, lab, c, mk in acts:
    px, py, ha, va = lab_pos[a]
    ax.text(px, py, lab, color=c, fontsize=6.2, fontweight="bold", ha=ha, va=va, zorder=4)

ax.set_xlabel("Robot answer time from question (s)")
ax.set_ylabel("Extra missed dashcam deadlines")
ax.set_xlim(XLO, XHI)
ax.set_ylim(YLO, YHI)

pdf, png = F.save(fig, "figM7_dayinlife")

# ---- JSON record -----------------------------------------------------------
payload = {
    "figure": "M7",
    "revision": 4,
    "message": "Only a warm history answers the robot on time and leaves the fleet unharmed; a cold history in one go harms the fleet, and cutting it into pieces only trades the harm for a late robot.",
    "design": "amendment 2 Part B only (roomy 256 GiB host, five actions, one paired set); single trade-off panel in the M3a style (x = robot answer time, y = extra missed deadlines); the old time-series panel is removed but its computation is kept below.",
    "sources": {
        "extra_missed_raw": "results/motivation/mot1/mot1_requests.jsonl.gz (kind=monitor, label A2BR1..A2BR5; each action paired to its own-repetition NONE control)",
        "robot_ttft": "results/motivation/mot1/mot1_figdata_amend2.json robot_ttft_s per_rep",
    },
    "N_dashcams": fd["N"], "deadline_s": fd["deadline_s"], "question_at_s": Q_AT,
    "robot_deadline_s": TARGET,
    "palette": {"cold / one go": "#D55E00", "host-warm": "#009E73", "GPU-warm": "#E69F00",
                "2,048-token pieces": "#56B4E9", "1,024-token pieces": "#0072B2"},
    "point_definition": "x = median robot answer time from the question, y = median extra missed dashcam deadlines (action minus paired NONE), each over the 5 Part B repetitions; whiskers = min to max over the repetitions in both directions.",
    "points": {a: {"robot_ttft_s": {"median": round(rob[a]["median"], 4), "min": round(rob[a]["lo"], 4),
                                    "max": round(rob[a]["hi"], 4), "per_rep": rob[a]["per_rep"]},
                   "extra_missed": {"median": int(extra[a]["median"]), "min": extra[a]["lo"],
                                    "max": extra[a]["hi"], "per_rep": extra[a]["per_rep"]}}
               for a, _, _, _ in acts},
    "timeseries_for_record": {
        "definition": "cumulative extra missed deadlines vs time since the question (t = t_submit + 0.916 - (t0 + 20)); median/min/max over 5 reps, downsampled to 0.25 s. Computed but no longer plotted.",
        "series": timeseries},
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
        "extra_onego": int(extra["ONE-GO"]["median"]) == 59,
        "extra_2048": int(extra["P2048"]["median"]) == 28,
        "extra_1024": int(extra["P1024"]["median"]) == 0,
        "extra_hostwarm": int(extra["HOST-WARM"]["median"]) == 0,
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
print("M7 rev4 done. points",
      {a: (round(rob[a]["median"], 2), int(extra[a]["median"])) for a, _, _, _ in acts},
      "hostwarm", [t["tier"] for t in fd["hostwarm_measured_tiers"]], "partA_flushed", k_flushed)
