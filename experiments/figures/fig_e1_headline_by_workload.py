#!/usr/bin/env python3
"""E1 (PILOT): per-workload headline vs baselines, with CIs.

Claim: the joint policy serves the most robot recalls and the most SS opportunities
within deadline, beating the EDF-feasibility baseline on SS beyond its CI, while every
arm meets the dashcam target, so the binding workloads are robot and SS and the policy
is best on both.

CPU only. Committed EP-G pilot headline frozen_headline_n16_4seed.json (seeds 0,4,5,6;
on-time rule: delivered within deadline by HTTP 200, robot 5 s, SS 2 s, dashcam 1 s).
Intervals are the committed paired bootstrap ci95. WATERMARKED PILOT: these are the
pilot cells, to be re-run on the repeat-trace cells.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figlib as F
import numpy as np

SRC = "results/orchestration/live2/frozen_test/frozen_headline_n16_4seed.json"
FIGID = "E1_headline_by_workload"
ARM_ORDER = ["hybrid-F-lhreq", "hybrid-F6-lhreq", "mooncake", "eco-llm", "b7-edf-feasibility"]


def main():
    d = F.load_json(SRC)
    rows = {r["arm"]: r for r in d["rows"]}
    # positive control: b7 is the baseline, its own minus-b7 deltas must be exactly 0.
    b7 = rows["b7-edf-feasibility"]
    assert b7["robot_minus_b7_ci95"] == [0.0, 0.0] and b7["ss_minus_b7_ci95"] == [0.0, 0.0], \
        "control FAIL: b7 is not its own baseline"

    workloads = [
        ("robot within 5 s", "robot_feasible_on_time", "robot_ci95", "robot_feasible_n"),
        ("SS within 2 s", "ss_on_time", "ss_ci95", "ss_n"),
    ]
    arms = [a for a in ARM_ORDER if a in rows]

    fig, ax = F.new_fig(8.2, 4.6)
    ngroup = len(workloads) + 1  # +1 for dashcam
    gw = 0.82
    bw = gw / len(arms)
    xg = np.arange(ngroup)

    for ai, a in enumerate(arms):
        A = F.arm(a)
        off = -gw / 2 + bw * (ai + 0.5)
        vals, los, his = [], [], []
        for _, vk, ck, nk in workloads:
            r = rows[a]
            vals.append(r[vk]); los.append(r[vk] - r[ck][0]); his.append(r[ck][1] - r[vk])
        # dashcam: fraction of runs meeting, from "N of M"
        dm = rows[a]["dashcam_all_meet_runs"]
        dfrac = (dm if isinstance(dm, (int, float)) else int(str(dm).split()[0]) / int(str(dm).split()[-1]))
        vals.append(dfrac); los.append(0.0); his.append(0.0)
        ax.bar(xg + off, vals, width=bw * 0.92, color=A.color, hatch=A.hatch,
               edgecolor="white", linewidth=0.6, zorder=3, label=A.label)
        ax.errorbar(xg[:2] + off, vals[:2], yerr=[los[:2], his[:2]], fmt="none",
                    ecolor=F.INK, elinewidth=1.0, capsize=2.5, zorder=4)

    ax.set_xticks(xg)
    ax.set_xticklabels(["robot\nwithin 5 s", "SS\nwithin 2 s", "dashcam\n(4/4 runs)"])
    ax.set_ylabel("fraction meeting target")
    ax.set_ylim(0, 1.12)
    ax.set_yticks(np.arange(0, 1.01, 0.25))
    ax.set_yticklabels([f"{int(v*100)}%" for v in np.arange(0, 1.01, 0.25)])
    ax.axhline(1.0, color=F.GRID, lw=0.8, zorder=1)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=5, fontsize=8.6,
              columnspacing=1.2, handletextpad=0.5)
    ax.set_title("Joint policy leads on robot and SS; all arms meet dashcam",
                 fontsize=10.8, pad=8)
    F.save(fig, FIGID, pilot=True)

    h = rows["hybrid-F-lhreq"]
    claim = (
        f"The joint policy serves {h['robot_feasible_on_time']*100:.0f}% of robot recalls within 5 s and "
        f"{h['ss_on_time']*100:.0f}% of SS opportunities within 2 s, the highest of the five arms on both. "
        f"Its SS service beats the EDF-feasibility baseline b7 by a paired "
        f"{h['ss_minus_b7_ci95'][0]*100:.1f} to {h['ss_minus_b7_ci95'][1]*100:.1f} pp (CI excludes 0); its "
        f"robot gain over b7 is {h['robot_minus_b7_ci95'][0]*100:.1f} to {h['robot_minus_b7_ci95'][1]*100:.1f} pp "
        "(CI includes 0). Every arm meets the dashcam target in all 4 runs, so robot and SS are the binding "
        "workloads and the policy is best on both."
    )
    notes = (
        "EP-G PILOT cells, frozen_headline_n16_4seed.json, 16 devices, seeds 0, 4, 5, 6 (seed 0 is the pilot "
        "seed, so this headline is pilot-stage and watermarked PILOT; the reported run uses seeds 1-3 and does "
        "not exist yet). On-time rule: delivered within the deadline by an HTTP 200 (robot 5 s, SS 2 s, dashcam "
        "1 s). Error bars on robot and SS are the committed paired bootstrap ci95; dashcam is fraction of runs "
        "meeting the per-device target and carries no opportunity-level CI. Positive control: b7's own minus-b7 "
        "deltas are exactly 0, confirming it is the baseline. Arm colours and order are the shared registry; "
        "the joint policy is query-blue. Clean EP-G family only."
    )
    F.write_caption(FIGID, claim, [SRC], pilot=True, notes=notes)


if __name__ == "__main__":
    main()
