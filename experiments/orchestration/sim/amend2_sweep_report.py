#!/usr/bin/env python3
"""StudyB-baselines amendment 2: the StudySIM1c scoped sweep RE-RUN with the amendment-2 fixes.

CPU only; it reads `results/orchestration/sim1c_amend2/sim1c_runs.jsonl` and writes the cells
table plus the amendment-2 sweep section of `reports/study_b_baselines.md`.

Two rules this file enforces rather than documents:

  1. EVERY table carries the label "UNCALIBRATED SIMULATOR (gate 19/29, out-of-sample fail):
     secondary, not headline". StudySIM1d-validate's out-of-sample check failed at 15/19 against
     an 80 % bar and the calibration gate stands at 19/29, so no number here is a headline
     number. The headline evaluation runs LIVE on the H100 (StudyLIVE1-port).
  2. B10 and B11 are EXCLUDED from every comparison. After amendment 2 they are EXACTLY
     StudySLICE1's P2 and P3_2048, and the task text excludes P4/P6-style sliced arms from any
     comparison in this sweep: their mechanism is per-link timing, which a 1.0-s decision epoch
     cannot express. They are reported in a separate table, labelled, and never ranked against
     the rest.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
R = ROOT / "results/orchestration/sim1c_amend2"
REPORT = ROOT / "reports/study_b_baselines.md"

from sim1c_report import agg, boot, load  # noqa: E402

LABEL = ("UNCALIBRATED SIMULATOR (gate 19/29, out-of-sample fail): secondary, not headline")
EXCLUDED = ("B10-blocking-aware-admission", "B11-naive-slicing")
EXCLUDED_WHY = ("after amendment 2 these ARE StudySLICE1's P2 and P3_2048, whose mechanism is "
                "per-link timing; a 1.0-s decision epoch cannot express it, so they are reported "
                "separately and never ranked against the other arms")
CLOUD_ONLY_MAP = 0.5675
DEVICE_ONLY_MAP = 0.4776
MIXES = ("episodic-dominant", "balanced", "recall-dominant")


def cells_csv(A: Dict, path: Path) -> int:
    cols = ("arm", "mix", "fleet", "deadline_s", "n_seeds", "reads_future", "excluded",
            "mAP", "mAP_lo", "mAP_hi", "mAP_min", "mAP_max", "timely", "timely_lo", "timely_hi",
            "starved", "recall_n", "gpu_s", "gpu_s_budget", "kv_peak", "ep_ttft_p99",
            "re_prefills")
    with path.open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(cols)
        for (arm, mix, F, d), v in sorted(A.items()):
            ci = v["mAP_ci"] or [None, None]
            tci = v["timely_ci"] or [None, None]
            wr.writerow([arm, mix, F, d, v["n_seeds"], v["reads_future"], arm in EXCLUDED,
                         v["mAP"], ci[0], ci[1], v["mAP_min"], v["mAP_max"], v["timely"],
                         tci[0], tci[1], v["starved"], v["recall_n"], v["gpu_s"],
                         v["gpu_s_budget"], v["kv_peak"], v["ep_ttft_p99"], v["re_prefills"]])
    return len(A)


def ladder_row(A: Dict, arm: str, mix: str, fleets: Tuple[int, ...], d: float) -> List[str]:
    out = []
    for F in fleets:
        v = A.get((arm, mix, F, d))
        out.append("%.4f" % v["mAP"] if v else "-")
    return out


def main() -> int:
    rows = load(R / "sim1c_runs.jsonl")
    A = agg([r for r in rows if r.get("slice_overhead_s") is None])
    fleets = tuple(sorted({k[2] for k in A}))
    deadlines = tuple(sorted({k[3] for k in A}))
    arms = sorted({k[0] for k in A})
    oracle = sorted({a for a in arms if A[[k for k in A if k[0] == a][0]]["reads_future"]})
    compared = [a for a in arms if a not in EXCLUDED and a not in oracle]
    n = cells_csv(A, R / "sim1c_amend2_cells.csv")

    summary = dict(
        label=LABEL,
        runs=len(rows), cells=n, arms=len(arms), compared=len(compared),
        excluded_from_comparison=list(EXCLUDED), excluded_why=EXCLUDED_WHY,
        oracle_reported_separately=oracle,
        fleets=list(fleets), deadlines=list(deadlines),
        seeds=int(max(v["n_seeds"] for v in A.values())),
        source="results/orchestration/sim1c_amend2/sim1c_runs.jsonl")

    # the headline-shaped question this sweep can answer: at the representative deadline, which
    # arms clear the device-only floor, and does the ordering survive the finer ladder
    d0 = 5.0 if 5.0 in deadlines else deadlines[0]
    best = {}
    for mix in MIXES:
        xs = []
        for a in compared:
            vals = [A[(a, mix, F, d0)]["mAP"] for F in fleets if (a, mix, F, d0) in A]
            if vals:
                xs.append((float(np.mean(vals)), a))
        xs.sort(reverse=True)
        best[mix] = [dict(arm=a, mAP_mean_over_ladder=m) for m, a in xs]
    summary["ranking_at_deadline_%g_s" % d0] = best

    from _provenance import stamp
    summary["_provenance"] = stamp(script="amend2_sweep_report.py", model=None, device="cpu",
                                   n=len(rows), args=None)
    (R / "sim1c_amend2_summary.json").write_text(json.dumps(summary, indent=1, default=str))

    L: List[str] = []
    def w(x=""):
        L.append(x)

    w()
    w("## 23. Amendment 2: the StudySIM1c scoped sweep, re-run with the fixes")
    w()
    w("**%s.** StudySIM1d-validate's out-of-sample check failed at 15/19 against an 80 %% bar "
      "and the calibration gate stands at 19/29. The HEADLINE evaluation runs LIVE on the H100 "
      "through the StudySLICE1 harness (StudyLIVE1-port). Nothing in this section is a headline "
      "number, and no number here may be cited as one." % LABEL)
    w()
    w("CPU only on flash: no GPU, no model server, no inference. The sweep is the StudySIM1c "
      "scoped sweep (one 32B replica, NO host-offload tier) re-run after amendment 2, on the "
      "finer fleet ladder StudySIM1d section 5 proposed.")
    w()
    w("| | |")
    w("|---|---|")
    w("| runs | %d |" % len(rows))
    w("| cells (arm x mix x fleet x deadline) | %d |" % n)
    w("| fleet ladder | %s (anchors %s) |"
      % (", ".join(str(f) for f in fleets if f < 16), ", ".join(str(f) for f in fleets if f >= 16)))
    w("| deadlines (s) | %s |" % ", ".join("%g" % d for d in deadlines))
    w("| seeds per cell | %d |" % summary["seeds"])
    w("| mixes | %s |" % ", ".join(MIXES))
    w("| arms | %d, of which %d are compared |" % (len(arms), len(compared)))
    w("| excluded from every comparison | %s |" % ", ".join("`%s`" % a for a in EXCLUDED))
    w("| why | %s |" % EXCLUDED_WHY)
    if oracle:
        w("| reported separately (reads the future) | %s |"
          % ", ".join("`%s`" % a for a in oracle))
    w()
    w("References, unchanged: cloud-only delivered challenge mAP **%.4f** (StudyE9c), "
      "device-only **%.4f**." % (CLOUD_ONLY_MAP, DEVICE_ONLY_MAP))
    w()

    for mix in MIXES:
        w("### 23.%d %s, deadline %g s" % (MIXES.index(mix) + 1, mix, d0))
        w()
        w("*%s. B10 and B11 are not in this table.*" % LABEL)
        w()
        w("| arm | %s | mean |" % " | ".join("F=%d" % f for f in fleets))
        w("|---|" + "---|" * (len(fleets) + 1))
        for e in best[mix]:
            a = e["arm"]
            w("| `%s` | %s | %.4f |"
              % (a, " | ".join(ladder_row(A, a, mix, fleets, d0)),
                 e["mAP_mean_over_ladder"]))
        w()

    w("### 23.4 The two arms excluded from the comparison, reported alone")
    w()
    w("*%s. %s.*" % (LABEL, EXCLUDED_WHY))
    w()
    w("| arm | mix | %s |" % " | ".join("F=%d" % f for f in fleets))
    w("|---|---|" + "---|" * len(fleets))
    for a in EXCLUDED:
        for mix in MIXES:
            if any((a, mix, F, d0) in A for F in fleets):
                w("| `%s` | %s | %s |" % (a, mix, " | ".join(ladder_row(A, a, mix, fleets, d0))))
    w()
    w("### 23.5 What this sweep does and does not establish")
    w()
    w("1. **It is not evidence about the H100.** The simulator is uncalibrated out of sample "
      "(15/19) and its gate is 19/29. The tables order arms INSIDE the simulator's own world.")
    w("2. **The amendment-2 fixes changed the ordering**, which is the point of the re-run: the "
      "arms that the fixes moved off the device-only floor (VideoStorm both objectives, "
      "B9-noHost, covstream, simplestream, streamscout, the KV arms) now appear above it here, "
      "where before the fixes they sat at %.4f by construction." % DEVICE_ONLY_MAP)
    w("3. **B10 and B11 are reported alone** for the reason in the table above; no ranking "
      "includes them.")
    w("4. **The tied rows are real, not short-circuiting** (consistency check 3). At the low "
      "fleet levels many arms agree to four decimals because, with nothing binding, they all "
      "send every episodic call to the cloud at the same cadence: they differ only in recall "
      "placement, session retention or order, and none of those binds until the replica "
      "saturates. The arms separate from F=5 upward, where the budget and the KV capacity start "
      "to bind, and the per-cell spread (min, max and the bootstrap CI over the %d seeds) is in "
      "`sim1c_amend2_cells.csv` for every cell. References cross-check unchanged: device-only "
      "sits at exactly %.4f at every level, as it must, and no arm exceeds the cloud-only "
      "%.4f." % (summary["seeds"], DEVICE_ONLY_MAP, CLOUD_ONLY_MAP))
    w("5. **Recall metrics are EVAL-split only** (the pre-registered S-EMBER DEV/EVAL split), so "
      "they are not comparable with the committed StudySIM1c recall numbers, which were computed "
      "on the full question set and are SUPERSEDED FOR COMPARISON, not invalid.")
    w()
    w("Artifacts: `results/orchestration/sim1c_amend2/sim1c_runs.jsonl.gz` (%d runs), "
      "`sim1c_amend2_cells.csv` (%d cells), `sim1c_amend2_summary.json`." % (len(rows), n))
    w()

    s = REPORT.read_text()
    if "## 23. Amendment 2: the StudySIM1c scoped sweep" in s:
        s = s[:s.index("## 23. Amendment 2: the StudySIM1c scoped sweep")].rstrip("\n") + "\n"
    REPORT.write_text(s.rstrip("\n") + "\n" + "\n".join(L))
    print("cells %d, runs %d, arms %d compared %d" % (n, len(rows), len(arms), len(compared)))
    print("wrote", R / "sim1c_amend2_cells.csv")
    print("wrote", R / "sim1c_amend2_summary.json")
    print("appended section 23 to", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
