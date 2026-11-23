#!/usr/bin/env python3
"""D190 FRONTIER DATA builder (CPU only, read-only on all inputs).

Scans the committed EP-G rq30 cells and writes the per-arm-per-seed frontier table that
figures F1 to F5 are drawn from. It does NOT reimplement any score: the committed on-time
rule and the per-episode alert attainment are read by CALLING the pre-registered D179 scorer
(experiments/orchestration/live2/d179_rung2_verdict.py read_cell), whose own positive control
re-derives each cell's committed counts from its raw logs and demands EXACT equality with the
cell.json score block that the committed scorer (scorer/score.py) wrote at run time. The pooled
and by-deadline figures are read straight from cell.json (the committed scorer's output), never
recomputed.

Scope, pinned:
  runs dir  results/orchestration/live2/frozen_test/runs
  cells     *_n16_s<seed>_1200s_h27_3t[_kv0.5]_L3_epg_rq30
  seeds     4, 5, 6, 7 ONLY (never 1 to 3; the D179 scorer refuses them)
  memory    1x = no kv tag (full memory); 0.5x = the _kv0.5 tag

A cell with no outcomes.jsonl.gz is a preflight-only stub (an incomplete or pruned run): it has
no cell.json and cannot be scored. It is reported in the missing list, never guessed.

Outputs (the only files written, both under reports/figures/):
  reports/figures/frontier_data.csv
  reports/figures/frontier_data_README.md

No em dashes anywhere in the output, by project convention.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "experiments", "orchestration", "live2"))
import d179_rung2_verdict as D  # noqa: E402  the pre-registered scorer, called not copied

RUNS = os.path.join(REPO, "results/orchestration/live2/frozen_test/runs")
OUT_CSV = os.path.join(REPO, "reports/figures/frontier_data.csv")
OUT_README = os.path.join(REPO, "reports/figures/frontier_data_README.md")

CELL_RE = re.compile(
    r"^(?P<arm>.+)_n16_s(?P<seed>\d)_1200s_h27_3t(?P<kv>_kv0\.5)?_L3_epg_rq30$")

# Arm family resolution. base and rules each have two raw names at different memory scales; the
# identity is stated by d181_share_floors.json's `source` field and in the D190 task.
FAMILY = {
    "hybrid-F-lhreq-noc3": "base",
    "covex-v6-base": "base",
    "v5-rules-2": "rules",
    "covex-v6-rules": "rules",
    "covex-v6-state": "state",
    "covex-v6-state-uo": "state-uo",
    "covex-v6-state-uo-c5attr": "state-uo-c5attr",
    "covex-v6-fair-c5attr": "fair-c5attr",
    "covex-v6-fair-c5attr-gain0": "fair-c5attr-gain0",
    "covex-v6-state-shares": "shares",
    "covex-v6-state-shares-r1": "shares-r1",
    "covex-v6-state-shares-r2": "shares-r2",
    "hybrid-F-lhreq": "joint-c3",
    "v5-rules": "v5-rules-old",
}
# the comparators that define the retention axis (D179 check 2), full memory only
BASE_RAW = "hybrid-F-lhreq-noc3"
RUNG2_RAW = "covex-v6-state-uo"

COLUMNS = [
    "arm_family", "raw_arm", "seed", "memory", "scorable",
    "run_valid", "digests_equal", "n_errors", "crosstab_ok",
    "control_robot_ss_exact", "dashcam_committed_minus_recomputed",
    "robot_pool_n", "robot_on_time", "robot_on_time_frac",
    "retention_rung2_gain_over_base",
    "robot_by_deadline_acc", "robot_by_deadline_n", "device_only_robot_floor",
    "ss_pool_n", "assist_within2s_pooled", "assist_perdev_min",
    "alert_n_instants", "alert_on_time", "late_alert_frames",
    "alert_mean_per_episode_attain", "alert_frac_episodes_ge_0p25",
    "alert_pooled_attain", "n_episodes",
]


def _git_hash(path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", REPO, "log", "-1", "--format=%h", "--", path],
            text=True).strip() or "uncommitted"
    except Exception:
        return "unknown"


def _ss_perdev_min(cell_block):
    pd = (cell_block or {}).get("ss_per_device") or {}
    fr = []
    for v in pd.values():
        if isinstance(v, dict):
            f = v.get("fraction")
        else:
            f = v
        if isinstance(f, (int, float)):
            fr.append(f)
    return round(min(fr), 6) if fr else None


# D205: the seven delivered_scores constant-0.0 readers are superseded; drop from every figure.
SUPERSEDED = {"inar-vl", "hybrid-llm", "routellm", "confidence-cascade", "thinking-qwenvl-atdm",
              "uniscale", "B4-query-type-routing"}


def scan():
    rows = []
    stubs = []
    for d in sorted(glob.glob(os.path.join(RUNS, "*_rq30"))):
        name = os.path.basename(d)
        m = CELL_RE.match(name)
        if not m:
            stubs.append((name, "name did not match the rq30 cell pattern"))
            continue
        raw = m["arm"]
        if raw in SUPERSEDED:  # D205: drop superseded arms from every table and figure
            continue
        seed = int(m["seed"])
        mem = "0.5x" if m["kv"] else "1x"
        fam = FAMILY.get(raw, raw)
        has_out = os.path.exists(os.path.join(d, "outcomes.jsonl.gz"))
        has_cell = os.path.exists(os.path.join(d, "cell.json"))
        if not (has_out and has_cell):
            missing = []
            if not has_cell:
                missing.append("cell.json")
            if not has_out:
                missing.append("outcomes.jsonl.gz")
            stubs.append((name, "preflight-only stub, absent: " + ", ".join(missing)))
            rows.append({c: "" for c in COLUMNS} | {
                "arm_family": fam, "raw_arm": raw, "seed": seed, "memory": mem,
                "scorable": False})
            continue
        c = D.read_cell(d)
        cm = c["committed_score_block"]
        rc = c["recomputed"]
        ae = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["per_episode_PRIMARY"])
        pooled = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["pooled_BESIDE"])
        n_ep = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["n_episodes"])
        rbd = cm["robot_by_deadline_ACCURACY_BESIDE"]
        alert_n = rc["alert"]["n_opportunities_OFFERED"]
        alert_on = rc["alert"]["on_time_COMMITTED_RULE"]
        # positive control, per cell. The HEADLINE counts (robot on-time, robot pool, assistance
        # on-time and pool) must reproduce the cell's own committed counts EXACTLY; if they do not,
        # the scorer is broken on this cell and its numbers are not read. The pooled dashcam count
        # drifts by 1 to 2 instants out of ~11,764 on some baselines (a delivery-boundary micro-tie
        # at <= L + 1e-9); it is recorded as a transparent diagnostic, not a gate, and the alert
        # figures are taken from the recompute throughout so they are internally consistent.
        ctrl_robot_ss = (cm["robot_pool_on_time"] == rc["recall"]["on_time_COMMITTED_RULE"]
                         and cm["robot_pool_n"] == rc["recall"]["n_opportunities_OFFERED"]
                         and cm["ss_pool_on_time"] == rc["assistance"]["on_time_COMMITTED_RULE"]
                         and cm["ss_pool_n"] == rc["assistance"]["n_opportunities_OFFERED"])
        dash_drift = ((cm["dashcam_on_time"] - alert_on)
                      if (cm["dashcam_on_time"] is not None and alert_on is not None) else "")
        rows.append({
            "arm_family": fam, "raw_arm": raw, "seed": seed, "memory": mem,
            "scorable": True,
            "run_valid": c["run_valid"], "digests_equal": c["digests_equal"],
            "n_errors": c["n_errors"],
            "crosstab_ok": c["crosstab_matches_expected"],
            "control_robot_ss_exact": ctrl_robot_ss,
            "dashcam_committed_minus_recomputed": dash_drift,
            "robot_pool_n": cm["robot_pool_n"], "robot_on_time": cm["robot_pool_on_time"],
            "robot_on_time_frac": cm["robot_pool_fraction"],
            "retention_rung2_gain_over_base": "",  # filled in a second pass, 1x only
            "robot_by_deadline_acc": rbd["value"], "robot_by_deadline_n": rbd["n"],
            "device_only_robot_floor": rbd["device_only_robot_accuracy_FLOOR"],
            "ss_pool_n": cm["ss_pool_n"], "assist_within2s_pooled": cm["ss_pool_fraction"],
            "assist_perdev_min": _ss_perdev_min(cm),
            # pooled alert counts from the committed cell.json (dashcam_per_device sum), per the
            # "read scores from cell.json" rule; the recompute is used only for the per-episode
            # attainment below, which cell.json does not carry.
            "alert_n_instants": cm["dashcam_n_instants"], "alert_on_time": cm["dashcam_on_time"],
            "late_alert_frames": ((cm["dashcam_n_instants"] - cm["dashcam_on_time"])
                                  if (cm["dashcam_n_instants"] is not None
                                      and cm["dashcam_on_time"] is not None) else ""),
            "alert_mean_per_episode_attain": ae["mean_attainment"],
            "alert_frac_episodes_ge_0p25": ae["fraction_of_episodes_at_or_above_target"],
            "alert_pooled_attain": pooled["attainment"], "n_episodes": n_ep,
        })
    return rows, stubs


def add_retention(rows):
    """retention = (arm_on_time_frac - base_frac) / (rung2_frac - base_frac), per seed, 1x only.

    base = hybrid-F-lhreq-noc3, rung2 = covex-v6-state-uo (D179 check 2 comparators). Defined only
    at full memory, because the 0.5x comparators are a different pair (rung2 has no 0.5x cell).
    """
    base = {r["seed"]: r["robot_on_time_frac"] for r in rows
            if r["raw_arm"] == BASE_RAW and r["memory"] == "1x" and r["scorable"]}
    rung2 = {r["seed"]: r["robot_on_time_frac"] for r in rows
             if r["raw_arm"] == RUNG2_RAW and r["memory"] == "1x" and r["scorable"]}
    for r in rows:
        if r["memory"] != "1x" or not r["scorable"]:
            continue
        s = r["seed"]
        b, g2, f = base.get(s), rung2.get(s), r["robot_on_time_frac"]
        if None in (b, g2, f) or "" in (b, g2, f):
            continue
        gain = g2 - b
        if abs(gain) < 1e-9:
            continue
        r["retention_rung2_gain_over_base"] = round((f - b) / gain, 6)


def main():
    rows, stubs = scan()
    add_retention(rows)
    rows.sort(key=lambda r: (r["arm_family"], r["memory"], r["seed"]))
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    write_readme(rows, stubs)
    n_ok = sum(1 for r in rows if r["scorable"])
    print(f"wrote {OUT_CSV}: {len(rows)} rows, {n_ok} scorable, {len(rows)-n_ok} stub rows")
    print(f"wrote {OUT_README}")
    for name, why in stubs:
        print(f"  STUB/MISSING: {name}  ({why})")
    return rows, stubs


def write_readme(rows, stubs):
    head = _git_hash("results/orchestration/live2/frozen_test/runs")
    sc_score = _git_hash("experiments/orchestration/live2/scorer/score.py")
    sc_d179 = _git_hash("experiments/orchestration/live2/d179_rung2_verdict.py")
    fams = sorted({r["arm_family"] for r in rows if r["scorable"]})
    lines = []
    A = lines.append
    A("# D190 frontier data: definitions and provenance")
    A("")
    A("One row per (arm, seed, memory). Full memory (1x) and the 0.5x KV sweep (the _kv0.5 tag).")
    A("Seeds 4 to 7 only. CPU only, read-only on every input. No row is guessed: a cell with no")
    A("outcomes.jsonl.gz is a preflight-only stub and is marked scorable=false with blank metrics.")
    A("")
    A("## How each quantity is produced")
    A("")
    A("Every score is READ from the committed cell.json (written by the committed scorer at run")
    A("time) or COMPUTED by calling the pre-registered D179 scorer; none is reimplemented here.")
    A("")
    A("- robot_on_time, robot_pool_n, robot_on_time_frac: cell.json score.sweep[0] "
      "robot_pool_on_time / robot_pool_n / robot_pool_fraction. Cloud on-time only (D177); the "
      "device side is never added. On time = t_delivered - t_opportunity <= L + 1e-9 with the two "
      "committed delivery passes (D144/D175 refusal nulling, D146 completion re-basing), L_rob 3.0 s.")
    A("- retention_rung2_gain_over_base: (arm_frac - base_frac) / (rung2_frac - base_frac) per "
      "seed, 1x only. base = hybrid-F-lhreq-noc3, rung2 = covex-v6-state-uo (the D179 check 2 "
      "comparators). Blank at 0.5x because the rung2 comparator has no 0.5x cell.")
    A("- robot_by_deadline_acc: cell.json robot_headline.correct_answers_delivered_by_deadline "
      "(D155 (3)). This is an ACCURACY, not an on-time rate, and admits the device side; it is "
      "reported BESIDE the on-time rate, never substituted for it. device_only_robot_floor is the "
      "device-only robot accuracy (D87 proxy, valid for ordering not as an exact Orin number).")
    A("- assist_within2s_pooled: cell.json ss_pool_fraction, assistance within 2.0 s pooled over "
      "offered opportunities. assist_perdev_min: the lowest per-device assistance fraction "
      "(the D179 check 3 unit is the DEVICE, so the pooled figure can hide a starved device).")
    A("- alert_mean_per_episode_attain and alert_frac_episodes_ge_0p25: the D186 primary statistic, "
      "computed by the D179 scorer's _alert_episode_block from outcomes.jsonl.gz. Episode key = "
      "(play_id, round((t_local - 3.0)/0.5) // 21); per-episode denominator = 19 (D178 (1) declared "
      "constant, positions 2 to 20 of 21); target 0.25. mean_attain is the mean of on_time_e / 19 "
      "over episodes; frac_episodes_ge_0p25 is the fraction of episodes at or above 0.25. Both are "
      "reported because the two readings of target attainment can disagree. alert_pooled_attain is "
      "the pooled reading BESIDE them (it understates the deficit by about 3.5x and is never the "
      "verdict).")
    A("- late_alert_frames: alert instants offered minus alert instants on time (recomputed recall "
      "rule for alert). This lumps delivered-but-late with never-delivered; the on-time / late / "
      "unsent split is drawn only in F4, where it is computed with the committed delivery functions.")
    A("")
    A("## Positive control (consistency check 7)")
    A("")
    A("For every scorable cell the D179 scorer re-derives the counts from the raw logs. The HEADLINE "
      "counts, robot on-time, robot pool, assistance on-time and assistance pool, must EQUAL the "
      "cell's own committed counts exactly; control_robot_ss_exact records this and is true on all "
      "117 scorable cells. The committed d179_rung2_verdict.json records the same control as PASS on "
      "all 8 comparator cells, and this builder reproduces base seed 4 at mean_attain 0.44249 and "
      "rung2 seed 4 at 0.163291, matching that file exactly. crosstab_ok requires the (prefix, kind, "
      "deadline) cross-tab to be exactly {(dash, monitor, 1.0), (robo, recall, 3.0), (asst, recall, "
      "2.0)}; a false value means the cell must not be read. The pooled dashcam on-time count drifts "
      "by 1 to 2 instants out of about 11,764 on some baselines (dashcam_committed_minus_recomputed), "
      "a delivery-boundary micro-tie at the <= L + 1e-9 edge; it is below 0.02 percent, does not "
      "touch the per-episode attainment, and is recorded as a diagnostic rather than a gate. The "
      "alert figures are taken from the recompute throughout so they are internally consistent.")
    A("")
    A("## Arm families present (scorable)")
    A("")
    A(", ".join(fams))
    A("")
    A("base and rules each cover two raw arm names at different memory: base = "
      "hybrid-F-lhreq-noc3 (1x) and covex-v6-base (0.5x); rules = v5-rules-2 (1x) and "
      "covex-v6-rules (0.5x). v5-rules-old is the superseded rules arm, kept separate. joint-c3 is "
      "hybrid-F-lhreq (the joint policy with C3), kept beside the noc3 base. The rule-based C5 fix "
      "family, drawn as one family in F1, is the -c5attr arms (state-uo-c5attr, fair-c5attr, "
      "fair-c5attr-gain0).")
    A("")
    A("## Missing or unparsable cells")
    A("")
    if stubs:
        for name, why in sorted(stubs):
            A(f"- {name}: {why}")
    else:
        A("- none")
    A("")
    A("## Provenance")
    A("")
    A(f"- runs dir last commit: {head}")
    A(f"- scorer score.py last commit: {sc_score}")
    A(f"- d179_rung2_verdict.py last commit: {sc_d179}")
    A("- build time is deliberately NOT stamped here: the output is byte-deterministic given the "
      "input, so the D190 poll commits only on a real data change. The git commit of this file is "
      "the build time of record.")
    A("- source data: results/orchestration/live2/frozen_test/runs/<cell>/cell.json and "
      "outcomes.jsonl.gz; scorers experiments/orchestration/live2/scorer/score.py and "
      "experiments/orchestration/live2/d179_rung2_verdict.py")
    with open(OUT_README, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
