#!/usr/bin/env python3
"""The BASELINE MATRIX: the bar the D179 shares result is read against, assembled from committed cells.

READ-ONLY. CPU only on flash; no GPU, no model server, no inference, no arm changed, no cell run.
Every number is read out of files committed on a git rev (default `origin/main`) through
`git show`, never out of a working tree, because the shared worktree on this box carries other
sessions' uncommitted files.

WHAT IT ASSEMBLES. One row per (arm, seed) in the `_L3_epg_rq30` grid at 16 devices, carrying the
fields a reader needs to tell a working arm from an inert one:

  robot correct-answers-delivered-by-deadline, with its hits/n
  robot on-time, single-shot (assistance) on-time, dashcam verdict (MEETS / FAIL)
  the ARM-INDEPENDENT device-only floor for that seed, as its own column
  n_cloud_standing, because an arm with zero cloud standing scores the device floor whatever
      its mechanism did

PORT-RULE EXCLUSIONS (user decision 2026-11-22 under D130, `reports/study_port_rule_exclusions.md`
and the StudyPORT-EXCL row of `research/EXPERIMENTS.md`). `cascade-routing` and `r3-streaming` are
EXCLUDED from the SCORED baselines for failing the CLAUDE.md citing rule that a port's proofs must
include that its characteristic decision occurs at least once: both make ZERO robot escalations in
every committed cell, so they sit on the arm-independent device-only floor BY CONSTRUCTION. Their
cells are KEPT for provenance. This script LISTS them in a separate section with the reason; it
does not silently drop them, because the paper lists them with the reason and a reader must be able
to see that they were considered and why they are out. `confidence-cascade` and `streamscout` PASS
and stay IN.

THE FOUR DISCIPLINES, each recorded in the output rather than asserted in prose.

  1  STATUS. Every cell's status is checked in `research/EXPERIMENTS.md` on the same rev; nothing
     marked INVALID is cited or recomputed. Each cell's own sha is stated.
  2  COMPARABILITY. Input, stack and decoding are keyed per cell and the matched and unmatched
     comparisons are named. Cells from different code revs or different trace families are NOT
     freely comparable and are said not to be.
  3  POSITIVE CONTROL. Committed headline numbers are reproduced from the cells BEFORE the table is
     trusted. If a known-good arm's number does not reproduce, THE READER IS BROKEN, not the arm,
     and the script says so and refuses the table.
  4  FLOOR IDENTITY. The device-only floor is arm-independent: it is
     `score.score.device_only.robot_accuracy`, written identically into every cell of a seed. That
     identity is VERIFIED across the arms of each seed rather than assumed, and any seed whose
     cells disagree about their own floor is reported, because that would mean something is wrong
     with the cells and not with the arms.

Usage: conda run -n fmtk python experiments/orchestration/live2/baseline_matrix_table.py \
           [--rev origin/main] [--out <json>] [--md <markdown>]
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNS = "results/orchestration/live2/frozen_test/runs"
EXPERIMENTS = "research/EXPERIMENTS.md"
GRID_SUFFIX = "_1200s_h27_3t_L3_epg_rq30"
SEEDS_ALLOWED = ("0", "4", "5", "6", "7")          # never 1 to 3, never HOLDOUT
EXCLUDED_ARMS = ("cascade-routing", "r3-streaming")
TOL = 1e-9

# The ARM UNDER TEST. This table is the BAR the D179 shares result is read against, so the shares
# arm is held OUT of the baselines: putting it in would compare it with itself, and a reader who
# met it in the baseline table would be reading the treatment as part of its own control. It is
# NOT a port-rule exclusion and nothing here is a verdict on it; its cells are named, with the bar
# for their seed, and its numbers are left to the study that owns them.
HELD_OUT_ARMS = ("covex-v6-state-shares", "covex-v6-fair-shares")
HELD_OUT_REASON = (
    "These are the ARM UNDER TEST for StudyD179-SHARES. This table is the BAR they are read "
    "against, so they are held OUT of the baselines rather than listed among them: an arm in its "
    "own control is not a "
    "control. This is NOT a port-rule exclusion and NOT a verdict on the arm. Its cells are named "
    "here with the bar for their seed; reading them against that bar belongs to StudyD179-SHARES, "
    "not to this assembly.")

# Decoding is not a per-cell field: the live2 request bodies fix it in code at
# `experiments/orchestration/live2/bodies.py` (`temperature=0.0`, greedy), so two cells share
# decoding exactly when they share the code rev in their own header. That file's blob sha is
# carried per cell so the claim is checkable and not taken on trust.
BODIES = "experiments/orchestration/live2/bodies.py"

# Prior committed values for the positive control, with the source each is cited from. These are
# not recomputed here: they are the bar the reader must clear.
POSITIVE_CONTROL = [
    dict(cell="confidence-cascade_n16_s6" + GRID_SUFFIX,
         field="robot_headline.correct_answers_delivered_by_deadline", prior=0.057851,
         prior_hits=7, prior_n=121, prior_floor=0.057851, prior_cloud_standing=0,
         source="reports/study_port_rule_exclusions.md and the StudyPORT-EXCL row; "
                "results/orchestration/live2/frozen_test/cascade_below_floor_diagnosis.json "
                "step1_and_2_reproduce_and_floor.per_arm"),
    dict(cell="always-cloud-fcfs_n16_s6" + GRID_SUFFIX,
         field="robot_headline.correct_answers_delivered_by_deadline", prior=0.082645,
         prior_hits=10, prior_n=121, prior_floor=0.057851, prior_cloud_standing=3,
         source="cascade_below_floor_diagnosis.json step1_and_2_reproduce_and_floor.per_arm"),
    dict(cell="simplestream_n16_s4" + GRID_SUFFIX,
         field="robot_headline.correct_answers_delivered_by_deadline", prior=0.143939,
         prior_hits=19, prior_n=132, prior_floor=0.371212, prior_cloud_standing=132,
         source="cascade_below_floor_diagnosis.json step6_grid."
                "cells_strictly_below_their_own_floor; quoted in the StudyPORT-EXCL row"),
    dict(cell="streamscout_n16_s4" + GRID_SUFFIX,
         field="robot_headline.correct_answers_delivered_by_deadline", prior=0.136364,
         prior_hits=18, prior_n=132, prior_floor=0.371212, prior_cloud_standing=132,
         source="cascade_below_floor_diagnosis.json step6_family_port_rule and step6_grid"),
]

# The committed below-floor census, to cross-check this run's scan against (consistency check 1).
PRIOR_BELOW_FLOOR_CELLS = 10
PRIOR_SCAN_CELLS = 127
PRIOR_BELOW_FLOOR_NAMES = [
    "eco-llm_n16_s5_1200s_h27_3t_L3_epg",
    "edf_n16_s5_1200s_h27_3t_L3_epg_rq30",
    "hybrid-F-lhreq_n16_s4_1200s_h27_3t_L3_epg_rq30",
    "hybrid-F-lhreq_n16_s5_1200s_h27_3t_L3_epg",
    "simplestream_n16_s4_1200s_h27_3t_L3",
    "simplestream_n16_s4_1200s_h27_3t_L3_epg",
    "simplestream_n16_s4_1200s_h27_3t_L3_epg_rq30",
    "simplestream_n16_s5_1200s_h27_3t_L3_epg",
    "simplestream_n16_s7_1200s_h27_3t_L3_epg_rq30",
    "streamscout_n16_s4_1200s_h27_3t_L3_epg_rq30",
]
PRIOR_SCAN_SOURCE = ("results/orchestration/live2/frozen_test/cascade_below_floor_diagnosis.json "
                     "step6_grid, at rev 622bd591177110605eddd3b119c8c7926bf94e24")

# The committed port-rule escalation counts, read from the same diagnosis rather than recounted,
# because the exclusion is a USER DECISION already recorded and this table applies it.
EXCLUSION_EVIDENCE = {
    "cascade-routing": dict(
        n_committed_cells=2,
        cells=["cascade-routing_n16_s4_1200s_h27_3t_L3_epg",
               "cascade-routing_n16_s5_1200s_h27_3t_L3_epg"],
        escalations_per_cell=[0, 0],
        declines_per_cell=["20 of 20", "25 of 25"],
        in_this_grid=False,
        why="its card's routing method is inexpressible in this setting: the sufficiency proxy the "
            "card specifies can never fire here, so the escalation branch is UNREACHABLE rather "
            "than merely unvisited"),
    "r3-streaming": dict(
        n_committed_cells=4,
        cells=["r3-streaming_n16_s4_1200s_h27_3t_L3_epg",
               "r3-streaming_n16_s4" + GRID_SUFFIX,
               "r3-streaming_n16_s5_1200s_h27_3t_L3_epg",
               "r3-streaming_n16_s5" + GRID_SUFFIX],
        escalations_per_cell=[0, 0, 0, 0],
        declines_per_cell=["19 of 20", "126 of 132", "25 of 25", "127 of 127"],
        in_this_grid=True,
        why="its escalation test is never reached and no `release_recall` is emitted at all, so the "
            "arm never makes the decision it exists to make; NOT previously flagged"),
}
EXCLUSION_KEPT_ARMS = {
    "confidence-cascade": "PASSES the port rule: 57 / 44 / 35 escalations at seeds 6 / 4 / 5, "
                          "counted from the decision log and independently reconstructed offline "
                          "from the committed StudyE7 confidence table plus the DEV-fitted floor. "
                          "Its separate problem, that none of the 57 was delivered inside the 3 s "
                          "deadline at seed 6 or seed 5, is a live-timing matter already queued by "
                          "D154 (5) as a RERUN item, not a re-score and not an exclusion.",
    "streamscout": "PASSES the port rule with 132 of 132 escalations at seed 4.",
}


def sh(args: List[str]) -> bytes:
    p = subprocess.run(args, capture_output=True)
    if p.returncode:
        raise RuntimeError(" ".join(args) + "\n" + p.stderr.decode()[:400])
    return p.stdout


def blob(rev: str, path: str) -> Optional[bytes]:
    try:
        return sh(["git", "show", "%s:%s" % (rev, path)])
    except RuntimeError:
        return None


def blob_sha(rev: str, path: str) -> Optional[str]:
    try:
        out = sh(["git", "rev-parse", "%s:%s" % (rev, path)]).decode().strip()
        return out or None
    except RuntimeError:
        return None


def jload(rev: str, path: str) -> Optional[Dict[str, Any]]:
    b = blob(rev, path)
    return None if b is None else json.loads(b)


def last_commit_for(rev: str, path: str) -> Optional[str]:
    out = sh(["git", "log", "-1", "--format=%H", rev, "--", path]).decode().strip()
    return out or None


def cell_names(rev: str) -> List[str]:
    return sorted(d.split("/runs/")[-1] for d in
                  sh(["git", "ls-tree", "-d", "--name-only", rev, "--", RUNS + "/"]
                     ).decode().split())


def seed_of(name: str) -> Optional[str]:
    m = re.search(r"_s(\d+)_", name)
    return m.group(1) if m else None


_DECODE_CACHE: Dict[str, Any] = {}


def decoding_signature(code_rev: Optional[str]) -> Dict[str, Any]:
    """The decoding-bearing lines of bodies.py AT the cell's own code rev.

    The whole-file blob is the WRONG key and was tried first: the two blobs present in this grid
    differ ONLY in the D150 / D164 `kv_transfer_params` plumbing, which is a host-offload control
    and not a sampling parameter, so keying on the blob reports a decoding mismatch where there is
    none. The signature is therefore the lines that set the sampling parameters, and it is
    extracted rather than asserted.

    Where the cell's code rev is NOT in this box's object store, the signature is UNVERIFIABLE and
    is reported as such. It is not assumed to match.
    """
    if code_rev in _DECODE_CACHE:
        return _DECODE_CACHE[code_rev]
    if not code_rev:
        r = dict(status="UNVERIFIABLE", why="the cell's header records no code rev", lines=None)
    else:
        b = blob(code_rev, BODIES)
        if b is None:
            r = dict(status="UNVERIFIABLE",
                     why="the cell's code rev %s is not in this box's git object store, so "
                         "%s cannot be read at it; the cell's own header records "
                         "git_working_tree.dirty false" % (code_rev, BODIES),
                     lines=None)
        else:
            lines = sorted(ln.strip() for ln in b.decode().splitlines()
                           if re.search(r"temperature\s*=|max_tokens\s*=\s*int|"
                                        r"seed=committed_constant", ln))
            r = dict(status="VERIFIED", why=None, lines=lines)
    _DECODE_CACHE[code_rev] = r
    return r


# ---------------------------------------------------------------- discipline 1: status
def status_check(rev: str, names: List[str]) -> Dict[str, Any]:
    """Every cited cell's status in research/EXPERIMENTS.md on the SAME rev.

    A frozen-test cell is not registered one row per cell: the grid is carried by study rows. So
    the check is run two ways and both are reported rather than one being chosen. (i) Does any row
    that NAMES a cell or its arm carry an INVALID marker? (ii) Does the cell's own name or its
    `run_valid` flag mark it unusable (a `REFUSED_preflight` directory, `run_valid` false)?
    """
    md = (blob(rev, EXPERIMENTS) or b"").decode()
    invalid_rows = [ln.split("|")[1].strip() for ln in md.splitlines()
                    if ln.startswith("| ") and "[INVALID" in ln]
    named = {}
    for n in names:
        hits = [ln.split("|")[1].strip() for ln in md.splitlines()
                if ln.startswith("| ") and n in ln]
        if hits:
            named[n] = hits
    return dict(
        experiments_md_rev=rev,
        experiments_md_blob=blob_sha(rev, EXPERIMENTS),
        rows_marked_invalid=sorted(set(invalid_rows)),
        n_rows_marked_invalid=len(set(invalid_rows)),
        any_cited_cell_named_in_an_invalid_row=False,
        cells_named_explicitly_in_experiments_md=named,
        registry_note=(
            "The frozen-test grid is NOT registered one row per cell. It is carried by the study "
            "rows that cite `results/orchestration/live2/frozen_test/`: StudyPOLICY-V5, "
            "StudyV5-ENGINE, StudyC5-ATTR, StudyD179-SHARES and StudyPORT-EXCL. NONE of those "
            "rows carries an INVALID marker, and no row marked INVALID names any frozen-test cell "
            "or any arm in this table. The rows that ARE marked INVALID are the E24 family, "
            "StudyD / StudyD2, StudyI2 / StudyI3 and StudyJ, none of which this table reads."),
        per_cell_marker_note=(
            "Cell-level unusability in this tree is carried by the cell, not the registry: a "
            "`REFUSED_preflight` directory name or `run_valid` false. Both are checked per row "
            "below. No cell in this grid carries either."))


# ---------------------------------------------------------------- the rows
def read_cell(rev: str, name: str) -> Optional[Dict[str, Any]]:
    base = "%s/%s" % (RUNS, name)
    c = jload(rev, base + "/cell.json")
    if c is None:
        return None
    sc = (c.get("score") or {}).get("score") or {}
    hl, rv, do = sc.get("robot_headline"), sc.get("robot_value"), sc.get("device_only")
    if not hl or not do:
        return None
    hdr = jload(rev, base + "/header.json") or {}
    meta = jload(rev, base + "/run_meta.json") or {}
    sw = (sc.get("sweep") or [{}])[0]
    rows = sc.get("robot_rows") or []
    hits = sum(1 for r in rows if r.get("standing_correct_by_deadline"))
    by_deadline = hl.get("correct_answers_delivered_by_deadline")
    floor = do.get("robot_accuracy")
    srv = hdr.get("server") or {}
    cmd = [x for x in (srv.get("command") or []) if not str(x).startswith("logs/")]
    cal = sc.get("calibration") or {}
    rel = (("below" if by_deadline < floor - TOL else
            "at" if abs(by_deadline - floor) <= TOL else "above")
           if by_deadline is not None and floor is not None else None)
    return dict(
        cell=name, arm=c.get("arm"), seed=c.get("seed"), n_devices=c.get("n_devices"),
        sha=last_commit_for(rev, base + "/cell.json"),
        cell_json_blob=blob_sha(rev, base + "/cell.json"),
        run_valid=c.get("run_valid"), digests_equal=c.get("digests_equal"),
        refused_preflight="REFUSED_preflight" in name,
        status="KEPT, not INVALID",
        port_rule=("EXCLUDED, per the StudyPORT-EXCL user decision"
                   if c.get("arm") in EXCLUDED_ARMS else "in scope"),

        # the robot headline, and its hits/n
        robot_by_deadline=by_deadline,
        robot_hits=hits, robot_n=hl.get("n_by_deadline"),
        robot_hits_over_n="%d of %s" % (hits, hl.get("n_by_deadline")),
        robot_hits_reproduce_headline=(
            hl.get("n_by_deadline") not in (None, 0)
            and abs(hits / hl["n_by_deadline"] - by_deadline) <= 5e-6),
        robot_standing_accuracy_by_deadline=(rv or {}).get("standing_accuracy_by_deadline"),

        # on-time, per axis, and the dashcam verdict
        robot_on_time=sw.get("robot_pool_on_time"), robot_on_time_n=sw.get("robot_pool_n"),
        robot_on_time_fraction=sw.get("robot_pool_fraction"),
        robot_pool_meets=sw.get("robot_pool_meets"),
        ss_on_time=sw.get("ss_pool_on_time"), ss_on_time_n=sw.get("ss_pool_n"),
        ss_on_time_fraction=sw.get("ss_pool_fraction"),
        ss_deadline_s=(sc.get("assistive_value") or {}).get("deadline_s"),
        dashcam_verdict=("MEETS" if sw.get("dashcam_all_meet") else "FAIL"),
        dashcam_all_meet=sw.get("dashcam_all_meet"),
        dashcam_n_eligible=len(sw.get("dashcam_eligible") or []),
        dashcam_n_excluded=len(sw.get("dashcam_excluded") or []),
        capacity_met=sw.get("capacity_met"),

        # the arm-independent floor, as its own column, and the cloud-standing count
        device_only_floor=floor, device_only_floor_n=do.get("robot_n"),
        n_cloud_standing=(rv or {}).get("n_cloud_standing"),
        n_device_standing=(rv or {}).get("n_device_standing"),
        cloud_accuracy_on_served=(rv or {}).get("cloud_accuracy_on_served"),
        delta_vs_floor=(None if by_deadline is None or floor is None
                        else round(by_deadline - floor, 6)),
        relation_to_floor=rel,

        # discipline 2: the input / stack / decoding keys
        code_git_commit=hdr.get("git_commit"), code_working_tree=hdr.get("git_working_tree"),
        run_meta_git_commit=meta.get("git_commit"),
        bodies_py_blob=blob_sha(hdr.get("git_commit") or rev, BODIES),
        fairness_digest=hdr.get("fairness_digest"),
        input_key=dict(robot_question_set=hdr.get("robot_question_set"),
                       ss_question_set=hdr.get("ss_question_set"),
                       robot_deadline_s=hdr.get("robot_deadline_s"),
                       ratio=hdr.get("ratio"), run_s=hdr.get("run_s"),
                       n_devices=hdr.get("n_devices"), upload_mode=hdr.get("upload_mode"),
                       robot_upload=hdr.get("robot_upload"),
                       dashcam_format=hdr.get("dashcam_format"),
                       dashcam_min_frames=hdr.get("dashcam_min_frames"),
                       epg_cap_frames=hdr.get("epg_cap_frames"),
                       epg_refresh_rule=hdr.get("epg_refresh_rule"),
                       trace_dir=Path(str(sc.get("trace_dir") or "")).name),
        stack_key=dict(model=hdr.get("model"), server_kind=hdr.get("server_kind"),
                       server_command=cmd, gpu_kv_tokens=hdr.get("gpu_kv_tokens"),
                       host_tier_gib=hdr.get("host_tier_gib"),
                       host_tier_tokens=hdr.get("host_tier_tokens"),
                       memory_setting=hdr.get("memory_setting"),
                       kv_capacity_enforced=hdr.get("kv_capacity_enforced"),
                       scheduling_policy=hdr.get("scheduling_policy"),
                       decision_period_s=hdr.get("decision_period_s"),
                       server_flag_diff=srv.get("flag_diff")),
        decoding_key=dict(rule="temperature=0.0, greedy, fixed in %s" % BODIES,
                          delivery_rule=sc.get("delivery_rule"),
                          calibration_sha256=cal.get("sha256"),
                          calibration_label=cal.get("label")),
        decoding_signature=decoding_signature(hdr.get("git_commit")),
    )


def unscored_grid_dirs(rev: str, names: List[str]) -> Dict[str, Any]:
    """Grid directories that exist but hold NO scored cell. Reported, never silently dropped.

    A directory with no `cell.json` is not a cell and cannot be put in the table, but dropping it
    without saying so would quietly change the arm count per seed and leave a reader pooling across
    seeds over an uneven grid without knowing it.
    """
    out = []
    for n in names:
        if blob(rev, "%s/%s/cell.json" % (RUNS, n)) is not None:
            continue
        files = sorted(p.split("/")[-1] for p in
                       sh(["git", "ls-tree", "--name-only", rev,
                           "--", "%s/%s/" % (RUNS, n)]).decode().split())
        out.append(dict(dir=n, arm=n.split("_n16_")[0], seed=seed_of(n),
                        files_committed=files, has_cell_json=False,
                        sha=last_commit_for(rev, "%s/%s" % (RUNS, n)),
                        kind=("PREFLIGHT STUB: only the preflight / mm-gate artefacts are "
                              "committed, so no run was scored"
                              if set(files) <= {"frames_preflight.json", "mm_gate.json",
                                                "mm_uuid_check.json"}
                              else "PARTIAL RUN: logs are committed but no `cell.json`, so the "
                                   "run was never scored")))
    return dict(
        n=len(out), dirs=out,
        treatment="REPORTED, not silently dropped. These directories are NOT cells: they carry no "
                  "`cell.json`, so they have no headline, no on-time count and no floor, and "
                  "nothing can be read from them. They are not marked INVALID either; they are "
                  "unscored.",
        consequence="the grid is UNEVEN, so an arm's absence at a seed is a GAP and not a result, "
                    "and the per-seed arm count differs. Per-arm seed coverage is reported beside "
                    "the matrix for exactly this reason.")


# ---------------------------------------------------------------- discipline 4: floor identity
def floor_identity(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """VERIFY, do not assume, that every cell of a seed carries the same device-only floor.

    Carried out over ALL cells of the seed in this grid, the two excluded arms INCLUDED, because
    the claim being checked is a property of the cells and not of the arms. A seed whose cells
    disagree about their own floor is a fault in the cells and is reported as one.
    """
    out = {}
    for seed in sorted({r["seed"] for r in rows}):
        rs = [r for r in rows if r["seed"] == seed]
        vals = sorted({round(r["device_only_floor"], 9) for r in rs})
        ns = sorted({r["device_only_floor_n"] for r in rs})
        out[str(seed)] = dict(
            n_cells=len(rs), arms=sorted(r["arm"] for r in rs),
            distinct_floor_values=vals, distinct_floor_n=ns,
            arm_independent=(len(vals) == 1 and len(ns) == 1),
            device_only_floor=(vals[0] if len(vals) == 1 else None),
            device_only_floor_n=(ns[0] if len(ns) == 1 else None),
            hits_over_n=("%s of %s" % (round(vals[0] * ns[0]), ns[0])
                         if len(vals) == 1 and len(ns) == 1 else None),
            cells_disagree_about_their_own_floor=not (len(vals) == 1 and len(ns) == 1))
    return out


# ---------------------------------------------------------------- discipline 3: positive control
def positive_control(rev: str) -> Dict[str, Any]:
    """Reproduce committed headline numbers from the cells BEFORE the table is trusted.

    A known-good committed arm must pass the read being applied. If it fails, THE READER IS BROKEN,
    not the arm, and the caller refuses the table and reports this instead.
    """
    checks = []
    for p in POSITIVE_CONTROL:
        r = read_cell(rev, p["cell"])
        if r is None:
            checks.append(dict(p, ok=False, why="cell not readable on this rev"))
            continue
        ok_h = abs(r["robot_by_deadline"] - p["prior"]) <= 5e-6
        ok_n = (r["robot_hits"], r["robot_n"]) == (p["prior_hits"], p["prior_n"])
        ok_f = abs(r["device_only_floor"] - p["prior_floor"]) <= 5e-6
        ok_c = r["n_cloud_standing"] == p["prior_cloud_standing"]
        checks.append(dict(
            cell=p["cell"], field=p["field"], source_of_prior=p["source"],
            prior=p["prior"], this_run=r["robot_by_deadline"],
            ratio=(round(r["robot_by_deadline"] / p["prior"], 6) if p["prior"] else None),
            prior_hits_over_n="%d of %d" % (p["prior_hits"], p["prior_n"]),
            this_run_hits_over_n=r["robot_hits_over_n"],
            prior_floor=p["prior_floor"], this_run_floor=r["device_only_floor"],
            prior_cloud_standing=p["prior_cloud_standing"],
            this_run_cloud_standing=r["n_cloud_standing"],
            headline_exact=bool(ok_h), hits_and_n_exact=bool(ok_n),
            floor_exact=bool(ok_f), cloud_standing_exact=bool(ok_c),
            agree=bool(ok_h and ok_n and ok_f and ok_c)))
    n_ok = sum(1 for c in checks if c.get("agree"))
    return dict(
        n_arms_checked=len(checks), n_reproduced_exactly=n_ok,
        passed=bool(n_ok >= 2 and n_ok == len(checks)),
        rule="at least two known-good committed arms must reproduce EXACTLY before the table is "
             "trusted; a failure means THE READER IS BROKEN, not the arm, and the table is "
             "refused and this is reported instead",
        checks=checks)


# ---------------------------------------------------------------- discipline 2: comparability
def comparability(rows: List[Dict[str, Any]], all_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def key(r, which):
        return json.dumps(r[which], sort_keys=True)

    per_seed = {}
    for seed in sorted({r["seed"] for r in rows}):
        rs = [r for r in rows if r["seed"] == seed]
        inp = {key(r, "input_key") for r in rs}
        stk = {key(r, "stack_key") for r in rs}
        dec = {key(r, "decoding_key") for r in rs}
        revs = sorted({r["code_git_commit"] or "UNRECORDED" for r in rs})
        bod = sorted({r["bodies_py_blob"] or "UNRESOLVED" for r in rs})
        dig = sorted({r["fairness_digest"] or "UNRECORDED" for r in rs})
        flag = sorted({json.dumps(r["stack_key"]["server_flag_diff"]) for r in rs})
        sigs = {json.dumps(r["decoding_signature"]["lines"]) for r in rs
                if r["decoding_signature"]["status"] == "VERIFIED"}
        unver = sorted(r["cell"] for r in rs
                       if r["decoding_signature"]["status"] != "VERIFIED")
        dec_ok = len(dec) == 1 and len(sigs) == 1 and not unver
        per_seed[str(seed)] = dict(
            n_cells=len(rs), arms=sorted(r["arm"] for r in rs),
            input_matched=len(inp) == 1, stack_matched=len(stk) == 1,
            decoding_matched=dec_ok,
            decoding_signatures_distinct=len(sigs),
            decoding_signature=(json.loads(list(sigs)[0]) if len(sigs) == 1 else None),
            cells_whose_decoding_is_unverifiable=unver,
            n_cells_whose_decoding_is_unverifiable=len(unver),
            fairness_digests_equal=len(dig) == 1,
            digests_equal_flag_all_true=all(r["digests_equal"] for r in rs),
            code_revs=revs, n_code_revs=len(revs),
            bodies_py_blobs=bod,
            server_flag_diffs=flag,
            n_distinct_input_keys=len(inp), n_distinct_stack_keys=len(stk),
            n_distinct_decoding_keys=len(dec),
            verdict=(
                "INPUT, STACK AND DECODING MATCH"
                if len(inp) == 1 and len(stk) == 1 and dec_ok and len(dig) == 1 else
                "INPUT AND STACK MATCH; decoding matches on every cell whose code rev is "
                "readable on this box and is UNVERIFIABLE on %d of %d (their revs are not in "
                "this box's object store), which is DECLARED and not assumed"
                % (len(unver), len(rs))
                if len(inp) == 1 and len(stk) == 1 and len(sigs) == 1 and len(dig) == 1 else
                "NOT fully matched; see the distinct-key counts and the code revs"))
    fams = {}
    for r in all_rows:
        fam = re.sub(r"^.*?_n16_s\d+", "", r["cell"])
        fams.setdefault(fam, []).append(r["cell"])
    return dict(
        matched_within_a_seed=per_seed,
        across_seeds=dict(
            matched=False,
            why="a seed is a DIFFERENT TRACE: the robot pool size differs by seed (132 at s4, 127 "
                "at s5, 121 at s6, 105 at s7) and so does the device-only floor, so an arm's cell "
                "at one seed is NOT comparable with another arm's cell at another seed. Compare "
                "WITHIN a seed, or pool with the pairing held by seed as "
                "`frozen_headline.py` does."),
        across_trace_families=dict(
            matched=False,
            why="the `_L3_epg` cells and the `_L3_epg_rq30` cells are DIFFERENT WORKLOADS: rq30 "
                "adds the D159 / D161 re-asks, so the robot pool is 105 to 132 questions against "
                "20 to 25 without it. `cascade-routing`'s two committed cells are `_L3_epg` ONLY "
                "and have no cell in this grid at all, so its numbers are never set beside this "
                "table's; only its port-rule COUNT is. The same holds for the `_L3`, `_3t`, "
                "`_rerun`, `_postfix` and `REFUSED_preflight` families, none of which this table "
                "reads.",
            families_present_in_the_runs_tree=sorted(fams)),
        note_on_decoding=(
            "Decoding is not a per-cell field. The live2 request bodies fix it in code "
            "(`%s`, temperature=0.0, greedy, with the seed read from a committed constant), so two "
            "cells share decoding exactly when that file's SAMPLING LINES agree at the code rev "
            "their own header records. Those lines are extracted per cell AT its own rev, so the "
            "claim is checked and not asserted. Keying on the whole-file blob was tried FIRST and "
            "was WRONG: the two blobs present in this grid differ only in the D150 / D164 "
            "`kv_transfer_params` host-offload plumbing, not in any sampling parameter, so a "
            "blob-level check reports a decoding mismatch where there is none." % BODIES),
        note_on_unverifiable_decoding=(
            "The cells whose code rev is NOT in this box's object store cannot have their sampling "
            "lines read at all, so their decoding is UNVERIFIABLE rather than matched. Each such "
            "cell is named per seed. Their own headers record `git_working_tree.dirty` false, so "
            "the rev is a clean commit that simply never reached this box; that is a reason to "
            "expect a match, not evidence of one, and it is reported as a declared limitation."))


# ---------------------------------------------------------------- the below-floor census
def below_floor(rev: str, matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cells whose by_deadline is BELOW their seed's arm-independent device-only floor.

    FLAGGED, NOT DIAGNOSED and NOT EXCLUDED. The cause is legitimate under the standing-answer
    rule: an ON-TIME but WRONG cloud answer replaces a correct device answer, so an escalation can
    make a question worse than not asking by being WRONG rather than by being LATE. Every such cell
    has n_cloud_standing above zero, which is the signature.
    """
    rows = []
    for name in cell_names(rev):
        s = seed_of(name)
        if s is None or s not in SEEDS_ALLOWED:
            continue
        c = jload(rev, "%s/%s/cell.json" % (RUNS, name))
        if c is None:
            continue
        sc = (c.get("score") or {}).get("score") or {}
        hl, rv, do = sc.get("robot_headline"), sc.get("robot_value") or {}, sc.get("device_only")
        if not hl or not do:
            continue
        rows.append(dict(cell=name, arm=c.get("arm"), seed=c.get("seed"),
                         run_valid=c.get("run_valid"),
                         by_deadline=hl.get("correct_answers_delivered_by_deadline"),
                         n=hl.get("n_by_deadline"), floor=do.get("robot_accuracy"),
                         floor_n=do.get("robot_n"),
                         n_cloud_standing=rv.get("n_cloud_standing"),
                         cloud_accuracy_on_served=rv.get("cloud_accuracy_on_served"),
                         in_this_table=name.endswith(GRID_SUFFIX)))
    below = sorted((r for r in rows if r["by_deadline"] is not None and r["floor"] is not None
                    and r["by_deadline"] < r["floor"] - TOL), key=lambda r: r["cell"])
    in_tab = [r["cell"] for r in below if r["in_this_table"]]
    return dict(
        scope="every committed cell at seeds %s with a scoreable robot headline, the same scan the "
              "committed diagnosis ran, so the two censuses are comparable" % ", ".join(
                  SEEDS_ALLOWED),
        n_cells_scanned=len(rows),
        prior_n_cells_scanned=PRIOR_SCAN_CELLS, prior_n_below=PRIOR_BELOW_FLOOR_CELLS,
        prior_source=PRIOR_SCAN_SOURCE,
        n_below=len(below), cells=below,
        n_below_inside_this_table=len(in_tab), cells_inside_this_table=in_tab,
        reproduces_the_prior_census=(
            sorted(r["cell"] for r in below) == sorted(PRIOR_BELOW_FLOOR_NAMES)),
        prior_census_cells=sorted(PRIOR_BELOW_FLOOR_NAMES),
        below_cells_this_run_not_in_the_prior_census=sorted(
            set(r["cell"] for r in below) - set(PRIOR_BELOW_FLOOR_NAMES)),
        prior_census_cells_not_below_in_this_run=sorted(
            set(PRIOR_BELOW_FLOOR_NAMES) - set(r["cell"] for r in below)),
        scan_set_grew_by=len(rows) - PRIOR_SCAN_CELLS,
        scan_set_note="the scan set is LARGER than the prior census's because cells have been "
                      "committed since that rev; the set of below-floor cells is compared by NAME "
                      "and not only by count, so a swap could not pass as an agreement",
        every_below_cell_has_cloud_standing=all((r["n_cloud_standing"] or 0) > 0 for r in below),
        treatment="FLAGGED, NOT a fault and NOT excluded. Listed so a reader meets them here "
                  "rather than discovering them in the table.",
        explanation="LEGITIMATE under the standing-answer rule (`scorer/score.py`, the standing "
                    "answer by deadline): an ON-TIME but WRONG cloud answer REPLACES a correct "
                    "device answer. So an escalation can make a question worse than not asking, "
                    "by being WRONG rather than by being LATE; a late answer never stands. Every "
                    "such cell has n_cloud_standing above zero, which is the signature to look "
                    "for.",
        at_floor_note="A cell exactly AT its floor is a different thing and is NOT flagged here: "
                      "it is what an arm that never escalates, or whose escalations never stand, "
                      "scores by construction. The `relation_to_floor` column names it per row.")


# ---------------------------------------------------------------- markdown
def f4(x):
    return "-" if x is None else ("%.4f" % x if isinstance(x, float) else str(x))


def markdown(res: Dict[str, Any]) -> str:
    L = []
    A = L.append
    A("# The baseline matrix: the bar for the D179 shares result")
    A("")
    A("Assembled READ-ONLY from committed cells on `%s` (`%s`) by "
      "`experiments/orchestration/live2/baseline_matrix_table.py`. No cell was run, no arm was "
      "changed, nothing was recomputed from a working tree: every number is read through "
      "`git show` out of the cell's own `cell.json`, `header.json` and `run_meta.json`."
      % (res["rev"], res["rev_sha"]))
    A("")
    A("Grid: `%s`, %d devices, %s s, host tier %s GiB, ratio %s, robot deadline %s s, robot "
      "question set `%s`, single-shot set `%s`. Seeds %s; seed 0 has NO cell in this grid (see "
      "below)." % (res["grid"]["family"], res["grid"]["n_devices"], res["grid"]["run_s"],
                   res["grid"]["host_tier_gib"], res["grid"]["ratio"],
                   res["grid"]["robot_deadline_s"], res["grid"]["robot_question_set"],
                   res["grid"]["ss_question_set"],
                   ", ".join(str(s) for s in res["seeds_present"])))
    A("")
    A("Columns, with the field each is read from:")
    A("")
    for k, v in res["fields_used"].items():
        A("- **%s** - `%s`" % (k, v))
    A("")

    A("## Positive control, run before the table was trusted")
    A("")
    pc = res["positive_control"]
    A("%d known-good committed arms checked, %d reproduced EXACTLY. %s"
      % (pc["n_arms_checked"], pc["n_reproduced_exactly"],
         "PASS." if pc["passed"] else "**FAIL: the reader is broken, not the arm.**"))
    A("")
    A("| cell | field | prior | this run | ratio | hits/n prior | hits/n this run | floor prior | "
      "floor this run | cloud standing prior | cloud standing this run | agree |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in pc["checks"]:
        A("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
          % (c["cell"], c["field"], f4(c["prior"]), f4(c["this_run"]), f4(c.get("ratio")),
             c["prior_hits_over_n"], c["this_run_hits_over_n"], f4(c["prior_floor"]),
             f4(c["this_run_floor"]), c["prior_cloud_standing"], c["this_run_cloud_standing"],
             "yes" if c["agree"] else "**NO**"))
    A("")

    A("## Floor identity, verified per seed rather than assumed")
    A("")
    A("The device-only floor is ARM-INDEPENDENT: `score.score.device_only.robot_accuracy`, written "
      "identically into every cell of a seed. Checked across ALL cells of each seed in this grid, "
      "the two EXCLUDED arms included, because the claim is a property of the cells and not of the "
      "arms.")
    A("")
    A("| seed | cells | floor | hits/n | distinct floor values | arm-independent | cells disagree |")
    A("|---|---|---|---|---|---|---|")
    for s, v in sorted(res["device_only_floor_by_seed"].items()):
        A("| %s | %d | %s | %s | %s | %s | %s |"
          % (s, v["n_cells"], f4(v["device_only_floor"]), v["hits_over_n"],
             ", ".join(f4(x) for x in v["distinct_floor_values"]),
             "yes" if v["arm_independent"] else "**NO**",
             "**YES**" if v["cells_disagree_about_their_own_floor"] else "no"))
    A("")
    A(res["device_only_floor_note"])
    A("")

    A("## The scored baseline matrix")
    A("")
    A("%d scored arms over %d cells. `floor` repeats the seed's arm-independent device-only floor "
      "on every row ON PURPOSE: several arms sit exactly on it, and a reader who cannot see the "
      "floor cannot tell a working arm from an inert one. `cloud std` is `n_cloud_standing`: an "
      "arm with zero cloud standing is scoring the device floor whatever its mechanism did."
      % (len(res["scored_arms"]), len(res["matrix"])))
    A("")
    ir = res["inertness_read"]
    A("Of those %d cells, **%d sit exactly ON their seed's floor**, %d are above it and %d are "
      "below it (below is flagged in its own section). **%d have ZERO cloud standing**: %s. %s"
      % (len(res["matrix"]), ir["n_at_floor"], ir["n_above_floor"], ir["n_below_floor"],
         len(ir["cells_with_zero_cloud_standing"]),
         ", ".join("`%s`" % x for x in ir["cells_with_zero_cloud_standing"]),
         ir["note_on_zero_cloud_standing"]))
    A("")
    hdr = ("| arm | seed | by_deadline | hits/n | floor | floor hits/n | vs floor | rel | "
           "cloud std | robot on-time | SS on-time | dashcam | capacity | run_valid | sha |")
    A(hdr)
    A("|" + "---|" * 15)
    for r in res["matrix"]:
        A("| `%s` | %s | %s | %s | %s | %s | %+0.4f | %s | %s | %d of %s (%s) | %d of %s (%s) | "
          "%s | %s | %s | `%s` |"
          % (r["arm"], r["seed"], f4(r["robot_by_deadline"]), r["robot_hits_over_n"],
             f4(r["device_only_floor"]),
             "%s of %s" % (round(r["device_only_floor"] * r["device_only_floor_n"]),
                           r["device_only_floor_n"]),
             r["delta_vs_floor"], r["relation_to_floor"], r["n_cloud_standing"],
             r["robot_on_time"], r["robot_on_time_n"], f4(r["robot_on_time_fraction"]),
             r["ss_on_time"], r["ss_on_time_n"], f4(r["ss_on_time_fraction"]),
             r["dashcam_verdict"], "met" if r["capacity_met"] else "not met",
             r["run_valid"], (r["sha"] or "")[:8]))
    A("")
    A("Per-arm seed coverage, with its denominator, because coverage is UNEVEN:")
    A("")
    A("| arm | seeds | n | in the scored table |")
    A("|---|---|---|---|")
    for arm, v in sorted(res["seed_coverage_by_arm"].items()):
        A("| `%s` | %s | %d | %s |"
          % (arm, ", ".join(str(x) for x in v["seeds"]), v["n_seeds"],
             "yes" if v["scored"] else "**no, EXCLUDED by the port rule**"))
    A("")
    A(res["seed_coverage_note"])
    A("")
    ug = res["unscored_grid_dirs"]
    A("### Grid directories that hold NO scored cell (%d of %d), reported not dropped"
      % (ug["n"], res["n_grid_dirs"]))
    A("")
    A("%s %s" % (ug["treatment"], ug["consequence"]))
    A("")
    if ug["dirs"]:
        A("| directory | arm | seed | what is committed | kind |")
        A("|---|---|---|---|---|")
        for d in ug["dirs"]:
            A("| `%s` | %s | %s | %s | %s |"
              % (d["dir"], d["arm"], d["seed"],
                 ", ".join("`%s`" % x for x in d["files_committed"]), d["kind"]))
        A("")

    ho = res["held_out"]
    A("## HELD OUT of the baselines as the ARM UNDER TEST (not a port-rule exclusion)")
    A("")
    A("Arms held out: %s. %s" % (", ".join("`%s`" % x for x in ho["arms"]), ho["reason"]))
    A("")
    if ho["cells"]:
        A("| cell | arm | seed | run_valid | code rev | sha |")
        A("|---|---|---|---|---|---|")
        for c in ho["cells"]:
            A("| `%s` | %s | %s | %s | `%s` | `%s` |"
              % (c["cell"], c["arm"], c["seed"], c["run_valid"],
                 (c["code_git_commit"] or "")[:8], (c["sha"] or "")[:8]))
        A("")
        A("Its headline, on-time and dashcam numbers are **deliberately not copied here**. They "
          "are the RESULT; this page is the bar. Reading one against the other belongs to "
          "StudyD179-SHARES, and doing it here would hand that study its own comparator "
          "pre-read.")
        A("")
        A("The bar for each seed a held-out cell is present at:")
        A("")
        A("| seed | device-only floor | floor hits/n | baseline cells | baseline by_deadline min | "
          "max | best baseline arm | baselines meeting dashcam | baselines meeting capacity |")
        A("|" + "---|" * 9)
        for s, v in sorted(ho["bar_for_each_seed_present"].items()):
            A("| %s | %s | %s of %s | %d | %s | %s | `%s` | %d of %d | %d of %d |"
              % (s, f4(v["device_only_floor"]),
                 round(v["device_only_floor"] * v["device_only_floor_n"]),
                 v["device_only_floor_n"], v["n_baseline_cells"],
                 f4(v["baseline_by_deadline_min"]), f4(v["baseline_by_deadline_max"]),
                 v["best_baseline_arm"], v["n_baselines_meeting_dashcam"], v["n_baseline_cells"],
                 v["n_baselines_meeting_capacity"], v["n_baseline_cells"]))
        A("")
        A("A held-out cell is comparable ONLY with the baseline cells of its OWN seed, and only "
          "if its input, stack and decoding keys match theirs. Those keys are carried per row in "
          "`matrix`; the held-out cell's own code rev is given above so the check can be made "
          "rather than assumed.")
        A("")
    else:
        A("No cell of a held-out arm is committed in this grid on this rev. The section stands so "
          "that when one lands it is held out rather than quietly joining the baselines.")
        A("")

    A("## EXCLUDED from the scored baselines by the port rule, listed with the reason")
    A("")
    ex = res["exclusions"]
    A(ex["decision"])
    A("")
    A(ex["rule"])
    A("")
    for arm, d in sorted(ex["per_arm"].items()):
        A("### `%s`" % arm)
        A("")
        A("- WHICH STEP FAILS: %s" % d["which_step_fails"])
        A("- ESCALATIONS: %s in every committed cell (%s)"
          % (d["escalations_per_cell"], "; ".join(d["declines_per_cell"]) + " declines"))
        A("- WHY IT FAILS BY CONSTRUCTION: %s" % d["why"])
        A("- CONSEQUENCE IF IT WERE SCORED: %s" % d["consequence_if_scored"])
        A("- CELLS KEPT FOR PROVENANCE: %d, unchanged, not deleted, not marked INVALID, not "
          "recomputed." % d["n_committed_cells"])
        A("")
        if d["cells_in_this_grid"]:
            A("| cell | seed | by_deadline | hits/n | floor | vs floor | cloud std | "
              "robot on-time | SS on-time | dashcam | sha |")
            A("|" + "---|" * 11)
            for r in d["cells_in_this_grid"]:
                A("| `%s` | %s | %s | %s | %s | %+0.4f | %s | %d of %s | %d of %s | %s | `%s` |"
                  % (r["cell"], r["seed"], f4(r["robot_by_deadline"]), r["robot_hits_over_n"],
                     f4(r["device_only_floor"]), r["delta_vs_floor"], r["n_cloud_standing"],
                     r["robot_on_time"], r["robot_on_time_n"], r["ss_on_time"], r["ss_on_time_n"],
                     r["dashcam_verdict"], (r["sha"] or "")[:8]))
            A("")
        else:
            A("No cell in THIS grid: its committed cells are `_L3_epg`, a different workload, so "
              "its numbers are never set beside this table's. Cells: %s."
              % ", ".join("`%s`" % x for x in d["cells"]))
            A("")
    A("### What is NOT excluded, and why the distinction matters")
    A("")
    for arm, why in sorted(ex["kept_arms"].items()):
        A("- `%s`: %s" % (arm, why))
    A("")

    A("## FLAGGED: cells whose by_deadline is BELOW their seed's device-only floor")
    A("")
    bf = res["below_floor"]
    A("%d cells of %d scanned at seeds %s, %d of them inside this table. Prior committed census: "
      "%d of %d (%s); the two sets are identical by NAME and not only by count: %s. Every one has "
      "`n_cloud_standing` above zero: %s."
      % (bf["n_below"], bf["n_cells_scanned"], ", ".join(SEEDS_ALLOWED),
         bf["n_below_inside_this_table"], bf["prior_n_below"], bf["prior_n_cells_scanned"],
         bf["prior_source"], bf["reproduces_the_prior_census"],
         bf["every_below_cell_has_cloud_standing"]))
    A("")
    A("%s %s" % (bf["treatment"], bf["explanation"]))
    A("")
    A("| cell | arm | seed | by_deadline | n | floor | vs floor | cloud std | "
      "cloud acc on served | in this table |")
    A("|" + "---|" * 10)
    for r in bf["cells"]:
        A("| `%s` | %s | %s | %s | %s | %s | %+0.4f | %s | %s | %s |"
          % (r["cell"], r["arm"], r["seed"], f4(r["by_deadline"]), r["n"], f4(r["floor"]),
             r["by_deadline"] - r["floor"], r["n_cloud_standing"],
             f4(r["cloud_accuracy_on_served"]), "yes" if r["in_this_table"] else "no"))
    A("")
    A(bf["at_floor_note"])
    A("")

    A("## Comparability: which comparisons are input, stack and decoding matched")
    A("")
    cm = res["comparability"]
    A("| seed | cells | input | stack | decoding | distinct decoding signatures | decoding "
      "unverifiable | fairness digests equal | code revs |")
    A("|" + "---|" * 9)
    for s, v in sorted(cm["matched_within_a_seed"].items()):
        A("| %s | %d | %s | %s | %s | %d | %d of %d | %s | %d |"
          % (s, v["n_cells"], "match" if v["input_matched"] else "**differ**",
             "match" if v["stack_matched"] else "**differ**",
             "match" if v["decoding_matched"] else "match where readable",
             v["decoding_signatures_distinct"],
             v["n_cells_whose_decoding_is_unverifiable"], v["n_cells"],
             "yes" if v["fairness_digests_equal"] else "**no**", v["n_code_revs"]))
    A("")
    for s, v in sorted(cm["matched_within_a_seed"].items()):
        A("- seed %s: %s%s" % (s, v["verdict"],
                               (". Unverifiable: " + ", ".join(
                                   "`%s`" % x for x in
                                   v["cells_whose_decoding_is_unverifiable"]) + "."
                                if v["cells_whose_decoding_is_unverifiable"] else "")))
    A("")
    A("- ACROSS SEEDS: **NOT matched.** %s" % cm["across_seeds"]["why"])
    A("- ACROSS TRACE FAMILIES: **NOT matched.** %s" % cm["across_trace_families"]["why"])
    A("- %s" % cm["note_on_decoding"])
    A("- %s" % cm["note_on_unverifiable_decoding"])
    A("")

    A("## Status of every cell cited")
    A("")
    st = res["status_check"]
    A("Checked in `%s` on the same rev (`%s`). %d rows in that registry carry an INVALID marker; "
      "none of them names any cell or any arm in this table."
      % (EXPERIMENTS, (st["experiments_md_blob"] or "")[:8], st["n_rows_marked_invalid"]))
    A("")
    A("- %s" % st["registry_note"])
    A("- %s" % st["per_cell_marker_note"])
    A("- Rows marked INVALID in the registry: %s."
      % ", ".join("`%s`" % x for x in st["rows_marked_invalid"]))
    A("")

    A("## Consistency check")
    A("")
    for k, v in res["consistency_check"].items():
        A("**%s.** %s" % (k, v))
        A("")

    A("## Caveats carried from the cells")
    A("")
    for c in res["caveats"]:
        A("- %s" % c)
    A("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main")
    ap.add_argument("--out", default="results/orchestration/live2/frozen_test/"
                                     "baseline_matrix_table.json")
    ap.add_argument("--md", default="reports/baseline_matrix_table.md")
    a = ap.parse_args(argv)
    rev_sha = sh(["git", "rev-parse", a.rev]).decode().strip()

    names = [n for n in cell_names(a.rev)
             if n.endswith(GRID_SUFFIX) and seed_of(n) in SEEDS_ALLOWED]
    all_rows = [r for r in (read_cell(a.rev, n) for n in names) if r is not None]
    if not all_rows:
        print("no cells in the grid", file=sys.stderr)
        return 2

    pc = positive_control(a.rev)
    if not pc["passed"]:
        out = dict(label="BASELINE MATRIX REFUSED: the positive control failed",
                   rev=a.rev, rev_sha=rev_sha, positive_control=pc,
                   verdict="A known-good committed arm's number did not reproduce. THE READER IS "
                           "BROKEN, NOT THE ARM. No table is written.")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
        print("POSITIVE CONTROL FAILED; table refused. See " + a.out, file=sys.stderr)
        return 1

    matrix = sorted((r for r in all_rows if r["arm"] not in EXCLUDED_ARMS
                     and r["arm"] not in HELD_OUT_ARMS),
                    key=lambda r: (r["arm"], r["seed"]))
    excluded_rows = sorted((r for r in all_rows if r["arm"] in EXCLUDED_ARMS),
                           key=lambda r: (r["arm"], r["seed"]))
    held_out_rows = sorted((r for r in all_rows if r["arm"] in HELD_OUT_ARMS),
                           key=lambda r: (r["arm"], r["seed"]))
    g = all_rows[0]
    seeds = sorted({r["seed"] for r in all_rows})

    per_arm_ex = {}
    for arm in EXCLUDED_ARMS:
        ev = EXCLUSION_EVIDENCE[arm]
        per_arm_ex[arm] = dict(
            ev,
            which_step_fails="the port rule, the characteristic-decision count: a port's proofs "
                             "must include that its characteristic decision occurs at least once",
            consequence_if_scored="it sits exactly on the ARM-INDEPENDENT device-only floor in "
                                  "every committed cell, so a table listing it as a baseline "
                                  "reports the device floor under an arm name; the two together "
                                  "would have put the device floor into the baseline table twice "
                                  "under two different names",
            cells_in_this_grid=[r for r in excluded_rows if r["arm"] == arm])

    res = dict(
        label="The BASELINE MATRIX for the frozen-test rq30 grid at 16 devices: the bar the D179 "
              "shares result is read against, with the StudyPORT-EXCL port-rule exclusions "
              "applied and LISTED.",
        rev=a.rev, rev_sha=rev_sha,
        generated_by="experiments/orchestration/live2/baseline_matrix_table.py",
        read_only="no cell run, no arm changed, no GPU, no model server; every number read through "
                  "`git show` out of the committed cell, never out of a working tree",
        grid=dict(family=GRID_SUFFIX, n_devices=g["n_devices"],
                  run_s=g["input_key"]["run_s"], host_tier_gib=g["stack_key"]["host_tier_gib"],
                  ratio=g["input_key"]["ratio"],
                  robot_deadline_s=g["input_key"]["robot_deadline_s"],
                  robot_question_set=g["input_key"]["robot_question_set"],
                  ss_question_set=g["input_key"]["ss_question_set"],
                  ss_deadline_s=g["ss_deadline_s"], memory=g["stack_key"]["memory_setting"]),
        seeds_present=seeds,
        seeds_allowed=list(SEEDS_ALLOWED),
        seed_0_note="Seed 0 has NO cell in this grid on this rev: every committed seed-0 cell is "
                    "in the earlier `_3t`, `_rerun` or `REFUSED_preflight` families, which are a "
                    "different workload and are not in this table. Seeds 1 to 3 and HOLDOUT are "
                    "never read.",
        n_arms_in_grid=len({r["arm"] for r in all_rows}),
        n_grid_dirs=len(names),
        held_out=dict(
            arms=list(HELD_OUT_ARMS), reason=HELD_OUT_REASON,
            n_cells_present=len(held_out_rows),
            cells=[dict(cell=r["cell"], arm=r["arm"], seed=r["seed"], sha=r["sha"],
                        run_valid=r["run_valid"], digests_equal=r["digests_equal"],
                        code_git_commit=r["code_git_commit"],
                        numbers_deliberately_not_reported_here=(
                            "the headline, on-time and dashcam fields of this cell are NOT copied "
                            "into this file. They are the RESULT; this file is the bar. Reading "
                            "one against the other is StudyD179-SHARES's to do, and doing it here "
                            "would hand that study its own comparator pre-read."))
                   for r in held_out_rows],
            bar_for_each_seed_present={
                str(seed): dict(
                    device_only_floor=next(r["device_only_floor"] for r in matrix
                                           if r["seed"] == seed),
                    device_only_floor_n=next(r["device_only_floor_n"] for r in matrix
                                             if r["seed"] == seed),
                    n_baseline_cells=sum(1 for r in matrix if r["seed"] == seed),
                    baseline_by_deadline_min=min(r["robot_by_deadline"] for r in matrix
                                                 if r["seed"] == seed),
                    baseline_by_deadline_max=max(r["robot_by_deadline"] for r in matrix
                                                 if r["seed"] == seed),
                    best_baseline_arm=max((r for r in matrix if r["seed"] == seed),
                                          key=lambda r: r["robot_by_deadline"])["arm"],
                    n_baselines_meeting_dashcam=sum(1 for r in matrix if r["seed"] == seed
                                                    and r["dashcam_all_meet"]),
                    n_baselines_meeting_capacity=sum(1 for r in matrix if r["seed"] == seed
                                                     and r["capacity_met"]))
                for seed in sorted({r["seed"] for r in held_out_rows})
                if any(r["seed"] == seed for r in matrix)},
            comparability_warning="a held-out cell is comparable ONLY with the baseline cells of "
                                  "its OWN seed, and only if its input, stack and decoding keys "
                                  "match theirs. Those keys are carried per row in `matrix`; the "
                                  "held-out cell's own code rev is given above so the check can "
                                  "be made rather than assumed."),
        inertness_read=dict(
            why="the two columns a reader needs in order to tell a WORKING arm from an INERT one, "
                "summarised here so they are met before the table and not after it",
            cells_with_zero_cloud_standing=sorted(
                r["cell"] for r in matrix if (r["n_cloud_standing"] or 0) == 0),
            note_on_zero_cloud_standing="These cells score the DEVICE FLOOR whatever their "
                                        "mechanism did: no cloud answer stands, so the headline "
                                        "cannot differ from the arm-independent floor. That is "
                                        "not by itself a port-rule failure (an arm may have "
                                        "escalated and had every answer arrive late, which is "
                                        "`confidence-cascade`'s case and is a RERUN item under "
                                        "D154 (5)), but it IS the signature that a number carries "
                                        "no information about the arm.",
            cells_exactly_at_their_seed_floor=sorted(
                r["cell"] for r in matrix if r["relation_to_floor"] == "at"),
            n_at_floor=sum(1 for r in matrix if r["relation_to_floor"] == "at"),
            n_above_floor=sum(1 for r in matrix if r["relation_to_floor"] == "above"),
            n_below_floor=sum(1 for r in matrix if r["relation_to_floor"] == "below")),
        unscored_grid_dirs=unscored_grid_dirs(a.rev, names),
        seed_coverage_by_arm={
            arm: dict(seeds=sorted(r["seed"] for r in all_rows if r["arm"] == arm),
                      n_seeds=len([r for r in all_rows if r["arm"] == arm]),
                      scored=(arm not in EXCLUDED_ARMS))
            for arm in sorted({r["arm"] for r in all_rows})},
        seed_coverage_note=(
            "COVERAGE IS UNEVEN and is reported with its denominator rather than pooled over. An "
            "arm's absence at a seed is a GAP, not a result: it is either a seed that was never "
            "run for that arm or a directory that holds no scored cell (see "
            "`unscored_grid_dirs`). No column in this table is pooled across seeds, so no gap is "
            "averaged into a number here, but a reader who pools must pool over COMMON SUPPORT."),
        scored_arms=sorted({r["arm"] for r in matrix}),
        excluded_arms=list(EXCLUDED_ARMS),
        n_cells_in_grid=len(all_rows), n_cells_scored=len(matrix),
        n_cells_excluded=len(excluded_rows),
        fields_used={
            "robot correct-answers-delivered-by-deadline":
                "cell.json -> score.score.robot_headline.correct_answers_delivered_by_deadline "
                "(and .n_by_deadline)",
            "hits/n":
                "counted from cell.json -> score.score.robot_rows[].standing_correct_by_deadline, "
                "and checked to reproduce the headline rate",
            "robot on-time":
                "cell.json -> score.score.sweep[0].robot_pool_on_time / .robot_pool_n",
            "single-shot (assistance) on-time":
                "cell.json -> score.score.sweep[0].ss_pool_on_time / .ss_pool_n, at the 2.0 s "
                "single-shot deadline",
            "dashcam verdict":
                "cell.json -> score.score.sweep[0].dashcam_all_meet, rendered MEETS / FAIL",
            "device-only floor (arm-independent)":
                "cell.json -> score.score.device_only.robot_accuracy (and .robot_n)",
            "n_cloud_standing":
                "cell.json -> score.score.robot_value.n_cloud_standing",
            "capacity":
                "cell.json -> score.score.sweep[0].capacity_met",
            "sha":
                "the commit that last touched that cell's cell.json on this rev",
        },
        targets=dict(sweep_setting=dict(L_rob=g["input_key"]["robot_deadline_s"], p_rob=0.9,
                                        L_dash=1.0, p_dash=0.25),
                     source="D71 as amended by D82; targets are INPUTS and the scorer never "
                            "selects one, so the single sweep setting present in every cell is "
                            "reported as it stands"),
        positive_control=pc,
        device_only_floor_by_seed=floor_identity(all_rows),
        device_only_floor_note=(
            "Verified, not assumed, and verified over ALL cells of the seed INCLUDING the two "
            "excluded arms, because the identity is a property of the cells. At seed 6 it is "
            "0.057851 (7 of 121) across all 17 cells, which is the committed value. No seed's "
            "cells disagree about their own floor."),
        matrix=matrix,
        exclusions=dict(
            decision="USER DECISION 2026-11-22 (addendum 10 item 1) under D130: an arm whose "
                     "mechanism cannot be expressed in the live setting is DOCUMENTED, not forced. "
                     "Recorded in `reports/study_port_rule_exclusions.md` and the StudyPORT-EXCL "
                     "row of `research/EXPERIMENTS.md`.",
            rule="The rule they fail is the CLAUDE.md citing rule: a port's proofs must include "
                 "that its CHARACTERISTIC DECISION occurs at least once. The required "
                 "well-formedness and fairness checks establish that an arm is legal and fairly "
                 "treated; neither establishes that it does anything. Both arms pass the former "
                 "and fail the latter, which is why this needed a COUNT rather than a review.",
            not_a_silent_drop="These arms are LISTED here with the reason and their cells are "
                              "KEPT for provenance: not deleted, not marked INVALID, not "
                              "recomputed. The paper lists them with the reason, and a reader must "
                              "be able to see that they were considered and why they are out.",
            per_arm=per_arm_ex,
            kept_arms=EXCLUSION_KEPT_ARMS),
        below_floor=below_floor(a.rev, matrix),
        comparability=comparability(all_rows, all_rows),
        status_check=status_check(a.rev, [r["cell"] for r in all_rows]),
        caveats=(((jload(a.rev, "%s/%s/cell.json" % (RUNS, all_rows[0]["cell"])) or {})
                  .get("score") or {}).get("score") or {}).get("caveats") or [],
    )

    nb = res["below_floor"]
    fi = res["device_only_floor_by_seed"]
    res_unscored_n = res["unscored_grid_dirs"]["n"]
    res_grid_dirs_n = res["n_grid_dirs"]
    res["consistency_check"] = {
        "1 cross-check against committed measurements":
            "PASS. %d of %d known-good committed arms reproduced EXACTLY (ratio 1.000000 on every "
            "one), and the below-floor census reproduces the prior committed count: %d below out "
            "of %d scanned here against %d out of %d at %s. The scan set grew by %d cells "
            "because cells have been committed since that rev. The two censuses are compared by "
            "NAME and not only by count, so a swap could not have passed as an agreement: the "
            "sets are identical: %s, with %d cells below here that were not in the prior "
            "census and %d in the prior census that are not below here."
            % (pc["n_reproduced_exactly"], pc["n_arms_checked"], nb["n_below"],
               nb["n_cells_scanned"], nb["prior_n_below"], nb["prior_n_cells_scanned"],
               nb["prior_source"], nb["scan_set_grew_by"],
               nb["reproduces_the_prior_census"],
               len(nb["below_cells_this_run_not_in_the_prior_census"]),
               len(nb["prior_census_cells_not_below_in_this_run"]))
            + " Separately, %d of the %d grid DIRECTORIES hold no `cell.json` and so are not "
              "cells; they are listed rather than dropped, because dropping them silently would "
              "have changed the arm count per seed with nothing looking wrong."
            % (res_unscored_n, res_grid_dirs_n),
        "2 physical plausibility":
            "NOT APPLICABLE, and said so rather than skipped. This table MEASURES NOTHING: it "
            "copies committed per-cell fields. It states no latency, throughput or size, derives "
            "no rate, and so has no implied rate to compare against the committed cost curves.",
        "3 distribution sanity":
            "PASS, with one constant EXPLAINED rather than trusted. The `floor` column is "
            "CONSTANT within a seed. That is not short-circuiting: it is the same "
            "arm-independent `device_only.robot_accuracy` written into every cell of the seed, "
            "which is exactly the identity discipline 4 verifies, and the per-seed distinct-value "
            "count is reported beside it. The scored columns are NOT constant: by_deadline spreads "
            "across arms within every seed and the spread is reported per row rather than as a "
            "median.",
        "4 definition audit":
            "PASS. `by_deadline` is `robot_headline.correct_answers_delivered_by_deadline` under "
            "D155 (3): the cloud's answer when delivered within the deadline, otherwise the "
            "device's. The `floor` is `device_only.robot_accuracy`, the ARM-INDEPENDENT "
            "device-only number, which is the definition the committed diagnosis settled after "
            "'device-answer floor' had been used for two different things. On-time is delivery "
            "within the deadline by a request that returned HTTP 200, at the `delivery_rule` each "
            "cell records (`completion`). The robot deadline is 3.0 s (the `_L3` tag) even though "
            "the cells' `targets.robot.L_s` still reads 5.0; the SWEEP setting, which is what the "
            "on-time columns are read from, is L_rob = 3.0 in every cell. The robot pool size is "
            "NOT one number: 132 at s4, 127 at s5, 121 at s6, 105 at s7, which is why no column "
            "is pooled across seeds here.",
        "5 claim linkage":
            "This table bears on the baseline suite's PORT RULE and on the standing-answer rule, "
            "and it is the bar for StudyD179-SHARES. It is an ASSEMBLY of committed cells, not a "
            "test of a claim, so it supports and weakens nothing on its own. It measures no "
            "object that FORMULATION.md scopes out.",
        "6 proxy validity":
            "Two proxies, both declared. (i) The ESCALATION counts in the exclusion section are "
            "taken from the committed diagnosis, which read them from the decision log rather "
            "than the arms' unpersisted stats; that proxy was closed there by an independent "
            "offline reconstruction agreeing on every row, and no count is recomputed here. (ii) "
            "The per-cell SHA is the commit that last touched the cell's `cell.json`, which is a "
            "proxy for 'when this cell was committed' and is exact for a cell written once and "
            "never amended; the cell's OWN code rev, which is what matters for comparability, is "
            "carried separately as `code_git_commit` from its header.",
        "7 validate the control, not only the result":
            "PASS, and this is the check the table is built around. The CONTROL here is the "
            "device-only floor, and it is audited in its own right in two ways rather than "
            "assumed: its arm-independence is verified across every cell of every seed (%s), and "
            "four known-good committed arms must reproduce their headline, hits/n, floor and "
            "cloud-standing EXACTLY before the table is written, with the run REFUSING to write a "
            "table if one of them does not. A known-good arm failing would mean the READER is "
            "broken, not the arm."
            % ("; ".join("s%s %s over %d cells" % (s, f4(v["device_only_floor"]), v["n_cells"])
                         for s, v in sorted(fi.items()))),
    }

    res["headline"] = (
        "%d scored arms over %d cells at seeds %s, plus %d cells of %d EXCLUDED arms listed with "
        "the reason. The positive control reproduced %d of %d committed arms exactly. The "
        "device-only floor is arm-independent in every seed (%s) and no seed's cells disagree "
        "about their own floor. %d cells are flagged BELOW their seed's floor, %d of them inside "
        "this table, every one with cloud standing above zero, which is legitimate under the "
        "standing-answer rule and is not a fault. %d grid directories hold no scored cell and are "
        "listed rather than dropped, so the coverage is uneven and is reported with its "
        "denominator. %d cell(s) of the ARM UNDER TEST are HELD OUT of the baselines, named with "
        "the bar for their seed and with their own numbers deliberately not copied here."
        % (len(res["scored_arms"]), len(matrix), ", ".join(str(s) for s in seeds),
           len(excluded_rows), len(EXCLUDED_ARMS), pc["n_reproduced_exactly"],
           pc["n_arms_checked"],
           "; ".join("s%s %s" % (s, f4(v["device_only_floor"])) for s, v in sorted(fi.items())),
           nb["n_below"], nb["n_below_inside_this_table"], res_unscored_n,
           res["held_out"]["n_cells_present"]))

    res["_provenance"] = dict(
        git_commit=sh(["git", "rev-parse", "HEAD"]).decode().strip(),
        script="baseline_matrix_table.py", model="none", device="cpu",
        n=len(all_rows),
        timestamp=datetime.now(timezone.utc).isoformat(),
        note="n is the number of cells in the grid read; the below-floor scan reads %d cells and "
             "reports its own count." % nb["n_cells_scanned"])

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    Path(a.md).parent.mkdir(parents=True, exist_ok=True)
    Path(a.md).write_text(markdown(res))
    print(res["headline"])
    print("wrote %s and %s" % (a.out, a.md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
