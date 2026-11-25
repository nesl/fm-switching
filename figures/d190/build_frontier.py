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
  cells     *_n16_s<seed>_1200s_h27_3t[_kv0.5r]_L3_epg_rq30[_rerun]
  seeds     4, 5, 6, 7 ONLY (never 1 to 3; the D179 scorer refuses them)
  memory    1x = no kv tag (full memory); 0.5x = the _kv0.5r tag (the real-pool halved budget)

D232-era pattern fix (user ruling 2026-11-24): the token is "_kv0.5r" (real pool), not "_kv0.5";
the old regex therefore matched NO 0.5x cell and dropped every one from the frontier. The regex now
accepts "_kv0.5r" and an optional trailing "_rerun", the glob now also sees the "_rq30_rerun"
directories, and memory is recorded as its own column (1x or 0.5x).

Validity and reruns (user ruling 2026-11-24):
  - a cell whose header.json source_agreement.verdict starts with INVALID is NEVER used; it is
    listed in the output as excluded, not scored;
  - a cell with no source_agreement key is kept and marked source_agreement = ABSENT;
  - when a (arm, seed, memory) has both a plain cell and a _rerun cell, the _rerun is kept and the
    row records which cell it supersedes.

A cell with no outcomes.jsonl.gz is a preflight-only stub (an incomplete or pruned run): it has
no cell.json and cannot be scored. It is reported in the missing list, never guessed.

Outputs (the only files written, both under reports/figures/; NO images):
  reports/figures/frontier_data.csv
  reports/figures/frontier_data_README.md

No em dashes anywhere in the output, by project convention.
"""
from __future__ import annotations

import csv
import glob
import json
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

# "_kv0.5r" (real-pool halved budget) and an optional trailing "_rerun". The old pattern used
# "_kv0.5" (no r) and no rerun, so it matched no 0.5x cell and no rerun at all.
CELL_RE = re.compile(
    r"^(?P<arm>.+)_n16_s(?P<seed>\d)_1200s_h27_3t(?P<kv>_kv0\.5r)?_L3_epg_rq30(?P<rerun>_rerun)?$")

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
    "arm_family", "raw_arm", "seed", "memory", "is_rerun", "supersedes", "source_agreement",
    "scorable",
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


def _source_agreement(cell_dir):
    """header.json source_agreement.verdict, or 'ABSENT' when the key is missing. Never guessed."""
    hp = os.path.join(cell_dir, "header.json")
    if not os.path.exists(hp):
        return "ABSENT"
    try:
        h = json.load(open(hp))
    except Exception:
        return "ABSENT"
    sa = h.get("source_agreement")
    if sa is None:
        return "ABSENT"
    if isinstance(sa, dict):
        v = sa.get("verdict")
        return v if (isinstance(v, str) and v) else "ABSENT"
    return sa if isinstance(sa, str) else str(sa)


# D205: the seven delivered_scores constant-0.0 readers are superseded; drop from every figure.
SUPERSEDED = {"inar-vl", "hybrid-llm", "routellm", "confidence-cascade", "thinking-qwenvl-atdm",
              "uniscale", "B4-query-type-routing"}


def _metrics_row(d):
    """Call the pre-registered D179 scorer on a scorable cell and return the metric fields."""
    c = D.read_cell(d)
    cm = c["committed_score_block"]
    rc = c["recomputed"]
    ae = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["per_episode_PRIMARY"])
    pooled = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["pooled_BESIDE"])
    n_ep = (c["alert_episodes"]["numerator_COMMITTED_RULE_PRIMARY"]["n_episodes"])
    rbd = cm["robot_by_deadline_ACCURACY_BESIDE"]
    alert_on = rc["alert"]["on_time_COMMITTED_RULE"]
    ctrl_robot_ss = (cm["robot_pool_on_time"] == rc["recall"]["on_time_COMMITTED_RULE"]
                     and cm["robot_pool_n"] == rc["recall"]["n_opportunities_OFFERED"]
                     and cm["ss_pool_on_time"] == rc["assistance"]["on_time_COMMITTED_RULE"]
                     and cm["ss_pool_n"] == rc["assistance"]["n_opportunities_OFFERED"])
    dash_drift = ((cm["dashcam_on_time"] - alert_on)
                  if (cm["dashcam_on_time"] is not None and alert_on is not None) else "")
    return {
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
        "alert_n_instants": cm["dashcam_n_instants"], "alert_on_time": cm["dashcam_on_time"],
        "late_alert_frames": ((cm["dashcam_n_instants"] - cm["dashcam_on_time"])
                              if (cm["dashcam_n_instants"] is not None
                                  and cm["dashcam_on_time"] is not None) else ""),
        "alert_mean_per_episode_attain": ae["mean_attainment"],
        "alert_frac_episodes_ge_0p25": ae["fraction_of_episodes_at_or_above_target"],
        "alert_pooled_attain": pooled["attainment"], "n_episodes": n_ep,
    }


def scan():
    """Return (rows, stubs, excluded). rows carry the memory column and, for a _rerun cell, the
    name of the cell it supersedes. INVALID cells (header source_agreement.verdict starts with
    INVALID) are never scored and are returned in `excluded`."""
    stubs = []
    excluded = []          # (name, verdict) never used, D-rule "never use INVALID cells"
    groups = {}            # (raw, seed, mem) -> [candidate dicts]
    paths = (glob.glob(os.path.join(RUNS, "*_rq30"))
             + glob.glob(os.path.join(RUNS, "*_rq30_rerun")))
    for d in sorted(set(paths)):
        name = os.path.basename(d)
        m = CELL_RE.match(name)
        if not m:
            stubs.append((name, "name did not match the rq30 cell pattern"))
            continue
        raw = m["arm"]
        if raw in SUPERSEDED:  # D205: drop superseded arms from every table and figure
            continue
        agree = _source_agreement(d)
        invalid = agree.upper().startswith("INVALID")   # never USED, but kept for supersedes notes
        if invalid:
            excluded.append((name, agree))
        has_cell = os.path.exists(os.path.join(d, "cell.json"))
        has_out = os.path.exists(os.path.join(d, "outcomes.jsonl.gz"))
        key = (raw, int(m["seed"]), "0.5x" if m["kv"] else "1x")
        groups.setdefault(key, []).append({
            "name": name, "dir": d, "is_rerun": bool(m["rerun"]), "agreement": agree,
            "invalid": invalid, "has_cell": has_cell, "has_out": has_out,
            "scorable": has_cell and has_out})

    rows = []
    rerun_1x_available = []   # scorable 1x _rerun cells NOT folded in (would change committed 1x)
    for (raw, seed, mem), cands in sorted(groups.items()):
        eligible = [e for e in cands if not e["invalid"]]   # INVALID cells are never a winner
        if not eligible:
            continue   # every cell for this key is INVALID: nothing usable, already in `excluded`
        if mem == "1x":
            # 1x stays EXACTLY as the committed frontier built it: plain cells only, no _rerun
            # dedup, so no committed 1x value moves (user task 2d). Any scorable 1x _rerun is
            # recorded separately for a future decision, never silently applied here.
            for e in eligible:
                if e["is_rerun"] and e["scorable"]:
                    rerun_1x_available.append((raw, seed, e["name"]))
            plains = [e for e in eligible if not e["is_rerun"]]
            if not plains:
                continue   # a 1x key that exists only as a _rerun was never in the committed table
            win = sorted(plains, key=lambda e: (e["scorable"],), reverse=True)[0]
            supersedes = ""
        else:
            # 0.5x: this is the data the fix adds. Prefer a scorable cell, and a scorable _rerun
            # over a plain (the stateoff _rerun supersedes its torn/INVALID plain). A STUB rerun
            # never clobbers a scorable plain. supersedes may name an INVALID plain this _rerun
            # replaces (recorded, though that plain's data is never used).
            win = sorted(eligible, key=lambda e: (e["scorable"], e["is_rerun"]), reverse=True)[0]
            others = [e for e in cands if e["name"] != win["name"]]
            supersedes = others[0]["name"] if (win["is_rerun"] and others) else ""
        fam = FAMILY.get(raw, raw)
        common = {"arm_family": fam, "raw_arm": raw, "seed": seed, "memory": mem,
                  "is_rerun": win["is_rerun"], "supersedes": supersedes,
                  "source_agreement": win["agreement"]}
        if not win["scorable"]:
            missing = [x for x, ok in (("cell.json", win["has_cell"]),
                                       ("outcomes.jsonl.gz", win["has_out"])) if not ok]
            stubs.append((win["name"], "preflight-only stub, absent: " + ", ".join(missing)))
            rows.append({c: "" for c in COLUMNS} | common | {"scorable": False})
            continue
        rows.append({c: "" for c in COLUMNS} | common | _metrics_row(win["dir"]))
    return rows, stubs, excluded, rerun_1x_available


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
    rows, stubs, excluded, rerun_1x = scan()
    add_retention(rows)
    rows.sort(key=lambda r: (r["arm_family"], r["memory"], r["seed"]))
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    write_readme(rows, stubs, excluded, rerun_1x)
    n_ok = sum(1 for r in rows if r["scorable"])
    n_05 = sum(1 for r in rows if r["memory"] == "0.5x")
    print(f"wrote {OUT_CSV}: {len(rows)} rows, {n_ok} scorable, {len(rows)-n_ok} stub rows, "
          f"{n_05} at 0.5x")
    print(f"wrote {OUT_README}")
    for name, why in stubs:
        print(f"  STUB/MISSING: {name}  ({why})")
    for name, verdict in excluded:
        print(f"  EXCLUDED (INVALID): {name}  ({verdict})")
    for raw, seed, name in rerun_1x:
        print(f"  1x RERUN AVAILABLE (not folded in, see task 2d): {name}")
    return rows, stubs, excluded, rerun_1x


def write_readme(rows, stubs, excluded, rerun_1x=()):
    head = _git_hash("results/orchestration/live2/frozen_test/runs")
    sc_score = _git_hash("experiments/orchestration/live2/scorer/score.py")
    sc_d179 = _git_hash("experiments/orchestration/live2/d179_rung2_verdict.py")
    fams = sorted({r["arm_family"] for r in rows if r["scorable"]})
    reruns = [(r["raw_arm"], r["seed"], r["memory"], r["supersedes"]) for r in rows
              if r["is_rerun"] and r["supersedes"]]
    absent = [(r["raw_arm"], r["seed"], r["memory"]) for r in rows
              if r["source_agreement"] == "ABSENT"]
    lines = []
    A = lines.append
    A("# D190 frontier data: definitions and provenance")
    A("")
    A("One row per (arm, seed, memory). Full memory (1x) and the 0.5x KV sweep (the _kv0.5r tag).")
    A("Seeds 4 to 7 only. CPU only, read-only on every input, NO images written. No row is guessed:")
    A("a cell with no outcomes.jsonl.gz is a preflight-only stub, marked scorable=false with blank")
    A("metrics.")
    A("")
    A("## Columns new in the D232-era fix (2026-11-24)")
    A("")
    A("- memory: 1x (no kv tag) or 0.5x (the _kv0.5r real-pool halved-budget tag). The old parser")
    A("  used the token _kv0.5 (no r), matched no 0.5x cell, and dropped every one; it is fixed.")
    A("- is_rerun / supersedes: a _rerun cell is kept and supersedes names the plain cell it")
    A("  replaces for that (arm, seed, memory).")
    A("- source_agreement: the header.json source_agreement.verdict, or ABSENT when the key is")
    A("  missing. A cell whose verdict starts with INVALID is NEVER used (listed below), per the")
    A("  project rule; an ABSENT cell is kept and marked, never dropped.")
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
      "computed by the D179 scorer's _alert_episode_block from outcomes.jsonl.gz, per-episode "
      "denominator per D178 / D232 (2); target 0.25. alert_pooled_attain is the pooled reading "
      "BESIDE them and is never the verdict.")
    A("- late_alert_frames: alert instants offered minus alert instants on time. This lumps "
      "delivered-but-late with never-delivered; the split is drawn only in F4.")
    A("")
    A("## Positive control (consistency check 7)")
    A("")
    A("For every scorable cell the D179 scorer re-derives the counts from the raw logs. The HEADLINE "
      "counts, robot on-time, robot pool, assistance on-time and assistance pool, must EQUAL the "
      "cell's own committed counts exactly; control_robot_ss_exact records this. crosstab_ok "
      "requires the (prefix, kind, deadline) cross-tab to be exactly {(dash, monitor, 1.0), (robo, "
      "recall, 3.0), (asst, recall, 2.0)}; a false value means the cell must not be read.")
    A("")
    A("## Arm families present (scorable)")
    A("")
    A(", ".join(fams))
    A("")
    A("base and rules each cover two raw arm names at different memory: base = "
      "hybrid-F-lhreq-noc3 (1x) and covex-v6-base (0.5x); rules = v5-rules-2 (1x) and "
      "covex-v6-rules (0.5x).")
    A("")
    A("## _rerun cells kept and the cell each supersedes")
    A("")
    if reruns:
        for raw, seed, mem, sup in sorted(reruns):
            A(f"- {raw} s{seed} {mem}: supersedes {sup}")
    else:
        A("- none")
    A("")
    A("## 1x _rerun cells AVAILABLE but NOT folded in (would change committed 1x values; user 2d)")
    A("")
    A("These 1x arms have a scorable _rerun cell. The committed 1x frontier is built from the PLAIN")
    A("cells, and folding the _rerun in would move those 1x rows, which this task forbids (task 2d:")
    A("any 1x value change is a bug). They are listed here for a separate decision, not applied.")
    A("")
    if rerun_1x:
        for raw, seed, name in sorted(rerun_1x):
            A(f"- {raw} s{seed}: {name}")
    else:
        A("- none")
    A("")
    A("## Cells EXCLUDED as INVALID (header source_agreement.verdict starts with INVALID; never used)")
    A("")
    if excluded:
        for name, verdict in sorted(excluded):
            A(f"- {name}: {verdict}")
    else:
        A("- none")
    A("")
    A("## Cells with no source_agreement key (kept, marked ABSENT)")
    A("")
    if absent:
        for raw, seed, mem in sorted(absent):
            A(f"- {raw} s{seed} {mem}")
    else:
        A("- none")
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
      "input. The git commit of this file is the build time of record.")
    A("- source data: results/orchestration/live2/frozen_test/runs/<cell>/cell.json and "
      "outcomes.jsonl.gz; scorers experiments/orchestration/live2/scorer/score.py and "
      "experiments/orchestration/live2/d179_rung2_verdict.py")
    with open(OUT_README, "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
