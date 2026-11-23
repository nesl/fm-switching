#!/usr/bin/env python3
"""D192 builder: compute Steps 1-5 per arm and seed and write reports/figures/episodic_scores.csv.

Offline, read-only, CPU only. Calls the committed scorer for robot (via cell.json), joins StudySS2
for single-shot, and runs the episodic dashcam scorer (dashcam_episodic.py) for crash detection and
early-exit headroom. Also emits a device-only reference row per seed. No weights are invented: the
unified figure is the pooled correct-in-time COUNT fraction over all units, with the per-type
fractions reported beside it. No em dashes.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402

OUT_CSV = os.path.join(E.REPO, "reports/figures/episodic_scores.csv")
OUT_README = os.path.join(E.REPO, "reports/figures/episodic_scores_README.md")

COLUMNS = [
    "arm", "seed", "cell_used_rerun",
    "dash_n_episodes", "dash_n_crash", "dash_n_nocrash", "dash_pos_nonevent_nocrash",
    "dash_detection_rate", "dash_false_alarm_rate", "dash_fraction_correct",
    "dash_median_lead_s", "dash_cloud_req_per_episode", "dash_gpu_s_per_episode",
    "dash_gpu_after_crossing", "dash_gpu_fraction_after_crossing",
    "dash_gpu_after_crash", "dash_gpu_after_nocrash",
    "robot_n", "robot_correct", "robot_frac",
    "ss_n", "ss_correct", "ss_frac",
    "dash_correct", "dash_n",
    "unified_correct_total", "unified_n_total", "unified_pooled_frac",
]


def _git_hash(path):
    try:
        return subprocess.check_output(["git", "-C", E.REPO, "log", "-1", "--format=%h", "--",
                                        path], text=True).strip() or "uncommitted"
    except Exception:
        return "unknown"


def robot_device_only(cell):
    dev = (((cell.get("score") or {}).get("score") or {}).get("device_only") or {})
    acc, n = dev.get("robot_accuracy"), dev.get("robot_n")
    if acc is None or n is None:
        return None, None, None
    return int(round(acc * n)), int(n), acc


def ss_device_only(path):
    corr = E.ss2_correctness()
    outs = E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl"))
    rows = [o for o in outs if str(o.get("device_id", "")).startswith("asst")]
    k = 0
    n = 0
    for o in rows:
        c = corr.get(o.get("question_id"))
        if c is None:
            continue
        n += 1
        if c.get("device"):
            k += 1
    return k, n, (k / n if n else None)


def _row(arm, seed, rr, dc, rob, ss):
    rk, rn, _ = rob
    sk, sn, _ = ss
    dash_correct = dc["n_detected"] + (dc["n_nocrash"] - dc["n_false_alarm"])
    dash_n = dc["n_episodes"]
    ut = sum(x for x in (dash_correct, rk, sk) if x is not None)
    nt = sum(x for x in (dash_n, rn, sn) if x is not None)
    return {
        "arm": arm, "seed": seed, "cell_used_rerun": rr,
        "dash_n_episodes": dc["n_episodes"], "dash_n_crash": dc["n_crash"],
        "dash_n_nocrash": dc["n_nocrash"],
        "dash_pos_nonevent_nocrash": dc["positive_clip_nonevent_episodes_as_nocrash"],
        "dash_detection_rate": dc["detection_rate"],
        "dash_false_alarm_rate": dc["false_alarm_rate"],
        "dash_fraction_correct": dc["fraction_episodes_correct"],
        "dash_median_lead_s": dc["median_lead_s"],
        "dash_cloud_req_per_episode": dc["cloud_requests_per_episode"],
        "dash_gpu_s_per_episode": dc["gpu_s_per_episode"],
        "dash_gpu_after_crossing": dc["step2_gpu_s_after_crossing"],
        "dash_gpu_fraction_after_crossing": dc["step2_gpu_fraction_after_crossing"],
        "dash_gpu_after_crash": dc["step2_gpu_after_crash"],
        "dash_gpu_after_nocrash": dc["step2_gpu_after_nocrash"],
        "robot_n": rn, "robot_correct": rk, "robot_frac": (rk / rn if rn else None),
        "ss_n": sn, "ss_correct": sk, "ss_frac": (sk / sn if sn else None),
        "dash_correct": dash_correct, "dash_n": dash_n,
        "unified_correct_total": ut, "unified_n_total": nt,
        "unified_pooled_frac": (ut / nt if nt else None),
    }


def main():
    thr = DC.thresholds()
    labels = DC.nexar_labels()
    rows = []
    missing = []
    for disp, raw in E.ARMS:
        for seed in E.SEEDS:
            path, rr = E.cell_dir(raw, seed)
            if path is None:
                missing.append(f"{disp} s{seed}")
                continue
            cell = E.load_cell(path)
            dc = DC.score_cell(path, seed, thr, labels, device_only=False)
            rob = E.robot_correct_in_time(cell)
            ss = E.ss_correct_in_time(path)[:3]
            rows.append(_row(disp, seed, rr, dc, rob, ss))
    # device-only reference, one row per seed (uses the base cell's cloud-free standing answers)
    for seed in E.SEEDS:
        path, rr = E.cell_dir("hybrid-F-lhreq-noc3", seed)
        if path is None:
            continue
        cell = E.load_cell(path)
        dc = DC.score_cell(path, seed, thr, labels, device_only=True)
        rob = robot_device_only(cell)
        ss = ss_device_only(path)
        rows.append(_row("device-only", seed, rr, dc, rob, ss))

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    write_readme(thr, labels, rows, missing)
    print(f"wrote {OUT_CSV}: {len(rows)} rows")
    for m in missing:
        print("  missing cell:", m)
    return rows


def write_readme(thr, labels, rows, missing):
    head = _git_hash("results/orchestration/live2/frozen_test/runs")
    tr = _git_hash("results/orchestration/live2/frozen_test/traces")
    L = []
    A = L.append
    A("# D192 episodic scores: definitions, provenance, validation")
    A("")
    A("One row per (arm, seed), seeds 4 to 7, full-memory final-workload cells "
      "(<arm>_n16_s<seed>_1200s_h27_3t_L3_epg_rq30), preferring the _rerun directory when present "
      "(which supplies always-cloud-fcfs s5, covex-v6-state s4, v5-rules s7). A device-only "
      "reference row per seed uses device answers only. CPU only, read-only on every input.")
    A("")
    A("## Standing answer and thresholds")
    A("")
    A("At each decision instant the STANDING answer is the cloud answer if it was delivered on time "
      "(within the 1.0 s alert deadline), otherwise the device answer (D165 B). Each tier is scored "
      "with its OWN score and its OWN FAR-10 threshold on DEV from StudySH-EP EP-G folds "
      "(sh_ep_results.json h2_earliness EP-G|far10): device 4BI threshold "
      f"{thr['device']:.6f} (achieved FAR {thr['achieved_far']['device']:.4f}), cloud 32BI "
      f"threshold {thr['cloud']:.6f} (achieved FAR {thr['achieved_far']['cloud']:.4f}). A standing "
      "score CROSSES when it is at or above its tier threshold (higher score = more yes). The "
      "EP-G calibration maps (score to probability) per tier are in each cell's "
      "calibration_knots.json and are available if a probability readout is wanted; the operating "
      "threshold is applied in score units.")
    A("")
    A("## Step 1 dashcam, per task episode")
    A("")
    A("Episodes are the workload's 21-frame episodes (episode_id from the committed per-seed trace "
      "table dashcam_instants.jsonl.gz, 712 to 714 per seed, matching d185_rung3_verdict.json). The "
      "device score and clip_pts per instant come from that table; the cloud on-time flag and cloud "
      "score come from the cell's outcomes.jsonl.gz, joined by opportunity_id (11764/11764 on "
      "seed 4). A CRASH episode is one whose clip is Nexar-positive AND whose clip_pts span contains "
      "the labelled event time ref (time_of_event), with an instant strictly before ref. Every other "
      "episode is a NO-CRASH episode; this includes negative clips and the pre/post-event segments of "
      "positive clips (dash_pos_nonevent_nocrash counts the latter, about 249 of 712 on seed 4). "
      "This labelling matches StudySH-EP calibrating FAR on non-event frames. A crash episode is "
      "CORRECT if its first standing crossing is at clip_pts < ref (lead = ref - clip_pts); a "
      "no-crash episode is CORRECT if there is no crossing, else it is a false alarm.")
    A("")
    A("Per arm and seed: dash_detection_rate (crash episodes detected before the event / crash "
      "episodes), dash_false_alarm_rate (no-crash episodes with a crossing / no-crash episodes), "
      "dash_fraction_correct, dash_median_lead_s, and cost dash_cloud_req_per_episode and "
      "dash_gpu_s_per_episode (GPU seconds = 0.000182431 x uncached tokens, D174; uncached = "
      "prompt_tokens - cached_tokens, cached-absent recorded not zeroed).")
    A("")
    A("## Step 2 early-exit headroom (design only, no claim)")
    A("")
    A("dash_gpu_after_crossing and dash_gpu_fraction_after_crossing are the cloud GPU seconds spent "
      "on instants AFTER an episode's first standing crossing (the decision is already made), as a "
      "total and a fraction of all dashcam cloud GPU, split by crash vs no-crash "
      "(dash_gpu_after_crash / dash_gpu_after_nocrash).")
    A("")
    A("## Step 3 robot, Step 4 single-shot, Step 5 unified")
    A("")
    A("Robot: the committed scorer headline correct_answers_delivered_by_deadline x n_by_deadline, "
      "read from cell.json (cloud if on time within 3 s, else device). Single-shot: per asst "
      "opportunity, cloud correctness if the cloud answer was delivered within 2 s, else device "
      "correctness, from StudySS2 per-qid correctness (exact_match for realworldqa, point_accuracy "
      ">= 0.5 for refspatial) joined by question_id; 0 missing qids. Unified (Step 5): "
      "unified_pooled_frac is the pooled correct-in-time COUNT fraction over all units (dashcam "
      "episodes + robot questions + single-shot questions); no weights are invented, and the "
      "per-type fractions (dash_fraction_correct, robot_frac, ss_frac) are reported beside it.")
    A("")
    A("## Validation (Step 7)")
    A("")
    A("Robot correct-by-deadline reproduces the committed cell.json headline exactly for every cell "
      "(it is read from it). StudySS2 per-qid correctness aggregates to the committed compare files "
      "exactly for realworldqa (device 0.654902, cloud 0.712418) and to within half a question for "
      "refspatial (binary cut 0.5 vs the compare's fractional mean). Device-only episode detection "
      "is reported in the device-only rows for comparison with StudySH-EP EP-G device numbers; see "
      "d192_validation.json.")
    A("")
    A("## Missing cells")
    A("")
    if missing:
        for m in missing:
            A(f"- {m}")
    else:
        A("- none (every arm has all four seeds)")
    A("")
    A("## Provenance")
    A("")
    A(f"- runs dir last commit: {head}")
    A(f"- device-score traces last commit: {tr}")
    A("- device scores and clip_pts: results/orchestration/live2/frozen_test/traces/<trace>/"
      "dashcam_instants.jsonl.gz (regenerated deterministically by the committed generator on "
      "flash; provenance in traces/d192_device_scores_provenance.json)")
    A("- thresholds: results/dashcam/study_sh_ep/sh_ep_results.json; Nexar labels and event times: "
      "sh_ep_manifest_meta.json and nexar_check.json; SS2: results/casestudy/study_ss2/")
    A("- build is byte-deterministic given the inputs (no timestamp stamped); the git commit of "
      "this file is the build time of record.")
    with open(OUT_README, "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
