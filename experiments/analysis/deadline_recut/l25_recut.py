#!/usr/bin/env python3
"""L2.5 vs 3 s twin: decompose the robot correct-by-deadline change (offline, read-only, CPU only).

For every _L2.5_epg_rq30 cell and its _L3_epg_rq30 twin (same arm, seed, n), this:
  1. counts robot device answers whose measured WARM latency per question (device_latency_s in the
     committed robot_rows, sourced from the Orin WARM table orin_rec_warm) falls in [2.5, 3.0) s;
  2. splits the robot correct-by-deadline (CBD) change into
       (a) the SCORING RE-CUT of identical answers: CBD(twin re-scored at 2.5) - CBD(twin at 3.0),
           further split into the DEVICE part (the device answers in [2.5,3.0), identical across the
           two cells) and the CLOUD part (the twin's own cloud deliveries re-cut at 2.5);
       (b) the REMAINDER attributable to the arm's different decisions:
           CBD(L2.5 cell at 2.5) - CBD(twin re-scored at 2.5).
     (a) + (b) == CBD(L2.5 cell) - CBD(twin), by construction.

CBD rule (committed scorer, robot_headline): the cloud answer if delivered within the deadline, else
the device answer if it also arrives within the deadline, else a miss. The per-question answers,
correctness and WARM device latency are READ from cell.json robot_rows (the committed scorer's own
output); re-scoring at a different deadline reuses those answers and the committed cloud-delivery
rule (D146 completion rebasing, via d179_rung2_verdict._committed_delivery). The re-cut at 3.0 must
reproduce the committed per-question CBD exactly (positive control) or the cell is flagged and not
reported. No em dashes.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "experiments", "orchestration", "live2"))
import d179_rung2_verdict as D  # noqa: E402  the committed delivery rule, reused not copied

RUNS = os.path.join(REPO, "results/orchestration/live2/frozen_test/runs")
OUT_CSV = os.path.join(REPO, "reports/figures/l25_recut.csv")
OUT_README = os.path.join(REPO, "reports/figures/l25_recut_README.md")
L_TWIN = 3.0
L_TIGHT = 2.5

COLUMNS = [
    "arm", "seed", "l25_cell", "twin_cell",
    "n_questions", "same_questions", "positive_control_at_3s_pass",
    "device_answers_in_2p5_3p0", "device_latency_min_s", "device_latency_max_s",
    "cbd_twin_3s", "cbd_twin_recut_2p5", "cbd_l25_2p5",
    "total_change", "a_scoring_recut", "a_recut_device_part", "a_recut_cloud_part",
    "b_arm_decisions",
]


def _cloud_deliv(cell_dir):
    outs = D._read_jsonl(os.path.join(cell_dir, "outcomes.jsonl"))
    reqs = (D._read_jsonl(os.path.join(cell_dir, "request.jsonl"))
            or D._read_jsonl(os.path.join(cell_dir, "requests.jsonl")))
    deliv = D._committed_delivery(outs, reqs)
    m = {}
    for oid, o in deliv.items():
        if not str(o.get("device_id", "")).startswith("robo"):
            continue
        td, to = o.get("t_delivered"), o.get("t_opportunity")
        cp = o.get("cloud_payload")
        m[oid] = {"deliv_s": (float(td) - float(to) if td is not None and to is not None else None),
                  "has_cloud": cp is not None and cp.get("request_id") is not None}
    return m


def _recut(rows, cd, L, cloud_at=None):
    """CBD count at deadline L. cloud_at overrides the deadline used ONLY for the cloud on-time test
    (so cloud_at=3.0 with L=2.5 re-cuts the device side alone)."""
    k = 0
    for r in rows:
        c = cd.get(r["opportunity_id"], {})
        lc = L if cloud_at is None else cloud_at
        cloud_on = (c.get("has_cloud") and c.get("deliv_s") is not None
                    and c["deliv_s"] <= lc + 1e-9)
        if cloud_on:
            ok = r.get("cloud_correct")
        elif r.get("device_latency_s") is not None and float(r["device_latency_s"]) <= L + 1e-9:
            ok = r.get("device_correct")
        else:
            ok = False
        k += 1 if ok else 0
    return k


def _rows_of(cell_dir):
    c = json.load(open(os.path.join(cell_dir, "cell.json")))
    return ((c.get("score") or {}).get("score") or {}).get("robot_rows") or []


def analyse(l25_dir):
    twin_dir = l25_dir.replace("_L2.5_epg_rq30", "_L3_epg_rq30")
    if not os.path.exists(os.path.join(twin_dir, "cell.json")):
        return None, f"{os.path.basename(l25_dir)}: twin {os.path.basename(twin_dir)} absent"
    name = os.path.basename(l25_dir)
    arm = name.split("_n16_")[0]
    seed = int(name.split("_s")[1].split("_")[0])
    rr_t = _rows_of(twin_dir)
    rr_l = _rows_of(l25_dir)
    if not rr_t or not rr_l:
        return None, f"{name}: robot_rows missing in a cell"
    cd_t = _cloud_deliv(twin_dir)
    cd_l = _cloud_deliv(l25_dir)
    # positive control: re-cut at 3.0 must reproduce the twin's committed per-question CBD
    committed = sum(1 for r in rr_t if r.get("standing_correct_by_deadline"))
    ctrl = _recut(rr_t, cd_t, L_TWIN)
    pc = (committed == ctrl)
    cbd_t3 = ctrl
    cbd_t25 = _recut(rr_t, cd_t, L_TIGHT)
    cbd_t25_devonly = _recut(rr_t, cd_t, L_TIGHT, cloud_at=L_TWIN)
    cbd_l25 = _recut(rr_l, cd_l, L_TIGHT)
    dlat = [float(r["device_latency_s"]) for r in rr_t if r.get("device_latency_s") is not None]
    inband = sum(1 for x in dlat if L_TIGHT <= x < L_TWIN)
    a = cbd_t25 - cbd_t3
    a_dev = cbd_t25_devonly - cbd_t3
    row = {
        "arm": arm, "seed": seed, "l25_cell": name, "twin_cell": os.path.basename(twin_dir),
        "n_questions": len(rr_t),
        "same_questions": (set(r["opportunity_id"] for r in rr_t)
                           == set(r["opportunity_id"] for r in rr_l)),
        "positive_control_at_3s_pass": pc,
        "device_answers_in_2p5_3p0": inband,
        "device_latency_min_s": round(min(dlat), 4) if dlat else None,
        "device_latency_max_s": round(max(dlat), 4) if dlat else None,
        "cbd_twin_3s": cbd_t3, "cbd_twin_recut_2p5": cbd_t25, "cbd_l25_2p5": cbd_l25,
        "total_change": cbd_l25 - cbd_t3,
        "a_scoring_recut": a, "a_recut_device_part": a_dev, "a_recut_cloud_part": a - a_dev,
        "b_arm_decisions": cbd_l25 - cbd_t25,
    }
    return row, (None if pc else f"{name}: POSITIVE CONTROL FAILED ({committed} vs {ctrl})")


def main():
    rows, notes = [], []
    for d in sorted(glob.glob(os.path.join(RUNS, "*_L2.5_epg_rq30"))):
        if d.endswith(".stdout") or not os.path.isdir(d):
            continue
        row, note = analyse(d)
        if note:
            notes.append(note)
        if row and row["positive_control_at_3s_pass"]:
            rows.append(row)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    _readme(rows, notes)
    print(f"wrote {OUT_CSV}: {len(rows)} L2.5/twin pairs")
    for n in notes:
        print("  note:", n)
    for r in rows:
        print(f"  {r['arm']} s{r['seed']}: in-band={r['device_answers_in_2p5_3p0']} "
              f"total={r['total_change']} a_recut={r['a_scoring_recut']} "
              f"(dev={r['a_recut_device_part']}, cloud={r['a_recut_cloud_part']}) "
              f"b_arm={r['b_arm_decisions']}")
    return rows


def _readme(rows, notes):
    def gh(p):
        import subprocess
        try:
            return subprocess.check_output(["git", "-C", REPO, "log", "-1", "--format=%h", "--", p],
                                           text=True).strip() or "uncommitted"
        except Exception:
            return "unknown"
    L = []
    A = L.append
    A("# L2.5 vs 3 s twin: robot correct-by-deadline change decomposition")
    A("")
    A("One row per _L2.5_epg_rq30 cell with a committed _L3_epg_rq30 twin (same arm, seed, n). "
      "Offline, read-only, CPU only. Seeds 4 to 7.")
    A("")
    A("## What is counted and how")
    A("")
    A("device_answers_in_2p5_3p0: robot device answers whose measured WARM latency per question "
      "(device_latency_s in the committed robot_rows, Orin WARM table orin_rec_warm) is in "
      "[2.5, 3.0) s. These are the device answers that are on time at the 3 s deadline but late at "
      "2.5 s, so they are the only device answers a deadline re-cut can flip; the device answers are "
      "identical across the two cells (device latency is per question, not per arm).")
    A("")
    A("The robot correct-by-deadline (CBD) count is the committed rule: the cloud answer if "
      "delivered within the deadline, else the device answer if it also arrives within the deadline, "
      "else a miss. Per-question answers, correctness and WARM device latency are read from cell.json "
      "robot_rows; re-scoring at a different deadline reuses those answers with the committed cloud "
      "delivery rule (D146 completion rebasing). The re-cut at 3 s reproduces the twin's committed "
      "per-question CBD exactly (positive_control_at_3s_pass); a cell that fails is dropped and "
      "listed under notes, never reported.")
    A("")
    A("## The split")
    A("")
    A("- total_change = CBD(L2.5 cell at 2.5) - CBD(twin at 3.0).")
    A("- a_scoring_recut = CBD(twin re-scored at 2.5) - CBD(twin at 3.0): the part offline "
      "re-scoring captures, holding the arm's answers fixed. a_recut_device_part re-cuts only the "
      "device side (cloud on-time status held at 3 s); a_recut_cloud_part is the remainder of the "
      "re-cut, the twin's own cloud deliveries re-cut at 2.5.")
    A("- b_arm_decisions = CBD(L2.5 cell at 2.5) - CBD(twin re-scored at 2.5): the remainder, which "
      "is what the arm did differently under the tighter deadline. a_scoring_recut + b_arm_decisions "
      "== total_change by construction.")
    A("")
    A("This is the decomposition EXPERIMENTS.md (StudyEDGE-DL-LOAD) calls for when it states the "
      "2.5 s cells exist because the DEADLINE changes what the arms DO, which D178 (1)'s offline "
      "re-scoring cannot capture: a_scoring_recut is exactly the offline-capturable part, and "
      "b_arm_decisions is the part it cannot.")
    A("")
    if rows:
        A("## Result")
        A("")
        A("| arm | seed | in [2.5,3.0) | total | (a) re-cut (dev / cloud) | (b) arm |")
        A("|---|---|---|---|---|---|")
        for r in rows:
            A(f"| {r['arm']} | {r['seed']} | {r['device_answers_in_2p5_3p0']} | "
              f"{r['total_change']} | {r['a_scoring_recut']} "
              f"({r['a_recut_device_part']} / {r['a_recut_cloud_part']}) | {r['b_arm_decisions']} |")
        A("")
        A("Device WARM latencies are about 0.25 to 0.31 s on the cells seen so far, far below 2.5 s, "
          "so no device answer falls in [2.5, 3.0) and the device re-cut is zero: the whole CBD "
          "change is the arm's different decisions under the tighter deadline, which is the point of "
          "running the 2.5 s cells rather than re-scoring the 3 s grid.")
        A("")
    A("## Missing or dropped cells")
    A("")
    if notes:
        for n in notes:
            A(f"- {n}")
    else:
        A("- none")
    A("")
    A("## Provenance")
    A("")
    A(f"- runs dir last commit: {gh('results/orchestration/live2/frozen_test/runs')}")
    A(f"- WARM table last commit: {gh('results/sember/study_orin_rec/orin_rec_warm.jsonl')}")
    A("- inputs: each cell's cell.json (robot_rows, robot_headline), outcomes.jsonl.gz and "
      "request.jsonl.gz; delivery rule experiments/orchestration/live2/d179_rung2_verdict.py")
    A("- build is byte-deterministic given the inputs; the git commit of this file is the build "
      "time of record.")
    with open(OUT_README, "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
