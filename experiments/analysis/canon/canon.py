#!/usr/bin/env python3
"""StudyTABLE1 / D209 canonical scoring pipeline. Offline, read-only, CPU only. Seeds 4-7.

ONE pipeline that regenerates every reported per-cell number and records its own git sha (and the
shas of the component scorers it calls) in the output. It applies, together:
  robot correct-by-deadline (committed scorer headline) and the D176 column (exclude recall questions
      whose cloud request was a context-length refusal, http_status 400, the over-32k rows);
  single-shot correct-in-time (StudySS2 per-qid correctness, correct by 2 s);
  dashcam delivered-stream Nexar challenge mAP (D199, per-tier Platt on SH-EP DEV EP-G, on-time cloud
      only), with the D192 per-episode alert attainment kept beside it LABELLED not part of the claim;
  on-time service columns (robot on time, single-shot within 2 s, dashcam per-episode attainment);
  the pooled correct-in-time fraction over robot and single-shot units (dashcam is a ranking metric
      with no per-unit correctness, so it is not pooled into the unit count).

Excludes D205-superseded arms (results/orchestration/live2/d201_score_channels/d201_superseded_cells
.json) and anything marked superseded in results/INDEX.md. No em dashes.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/episodic"))
import episodic_lib as E  # noqa: E402  robot, SS, cell_dir, read_jsonl

SUPERSEDED = json.load(open(ROOT / "results/orchestration/live2/d201_score_channels/"
                            "d201_superseded_cells.json"))["the_seven_readers"].keys()
SUPERSEDED = set(SUPERSEDED)
RR = "fair-c5attr-rr"
DEVICE = "device-only"
OUTDIR = ROOT / "reports"
FIGDIR = ROOT / "reports/figures"


def git_sha(path):
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "log", "-1", "--format=%h", "--",
                                        path], text=True).strip() or "uncommitted"
    except Exception:
        return "unknown"


def over32k_oids(path):
    """robot opportunity_ids whose cloud request was a context-length refusal (http_status 400),
    the D176 over-32k rows."""
    oids = set()
    reqs = E.read_jsonl_gz(os.path.join(path, "request.jsonl")) \
        or E.read_jsonl_gz(os.path.join(path, "requests.jsonl"))
    for r in reqs:
        if str(r.get("device_id", "")).startswith("robo") and r.get("http_status") == 400:
            oids.add(r.get("opportunity_id"))
    return oids


def robot_d176(cell, path, std_correct, std_n):
    """D176: the committed robot correct-by-deadline with the over-32k (http-400 context-refusal)
    recalls removed from BOTH numerator and denominator. Defined relative to the committed standard
    counts, so it equals the standard exactly when a cell has no over-32k refusal."""
    if std_correct is None or std_n is None:
        return None, None
    over = over32k_oids(path)
    if not over:
        return std_correct, std_n
    rr = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    over_rows = [r for r in rr if r.get("opportunity_id") in over]
    over_correct = sum(1 for r in over_rows if r.get("standing_correct_by_deadline"))
    return std_correct - over_correct, std_n - len(over_rows)


def collect_units(arm_raw, seed, device_only=False):
    """Per-unit correct-in-time for one cell, keyed by question identity. Robot units key ('R', oid)
    carry standing_correct_by_deadline (device-only: device_correct within the 3 s deadline); single
    -shot units key ('S', qid) carry the on-time cloud-else-device correctness (device-only: device).
    These are the units the paired question-clustered bootstrap resamples."""
    path, _ = E.cell_dir(arm_raw, seed)
    if path is None:
        return {}
    cell = E.load_cell(path)
    rr = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    over = over32k_oids(path)
    units = {}
    for r in rr:
        oid = r.get("opportunity_id")
        if oid is None or oid in over:  # D176: over-32k refusals excluded from the unit pool
            continue
        if device_only:
            ok = bool(r.get("device_correct")) and (r.get("device_latency_s") or 1e9) <= 3.0
        else:
            ok = bool(r.get("standing_correct_by_deadline"))
        units[("R", oid)] = 1 if ok else 0
    corr = E.ss2_correctness()
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("asst"):
            continue
        qid = o.get("question_id")
        c = corr.get(qid)
        if c is None:
            continue
        if device_only:
            ok = c.get("device")
        else:
            on_time = bool((o.get("cloud_payload") or {}).get("on_time")) or bool(o.get("within_L"))
            ok = c.get("cloud") if on_time else c.get("device")
        units[("S", qid)] = 1 if ok else 0
    return units


def paired_ci(units_a, units_c, kind=None, nb=2000, seed=0):
    """Paired question-clustered bootstrap of the correct-in-time fraction difference A - C. Clusters
    are question identities present in BOTH arms; a resampled question contributes all its per-seed
    instances for both arms. kind filters to 'R' (robot) or 'S' (single-shot); None pools both.
    Returns (point_diff, lo95, hi95) or None."""
    import numpy as np
    # per-question lists across seeds, for the common questions
    agg_a, agg_c = {}, {}
    for s, u in units_a.items():
        for k, v in u.items():
            if kind and k[0] != kind:
                continue
            agg_a.setdefault(k, []).append(v)
    for s, u in units_c.items():
        for k, v in u.items():
            if kind and k[0] != kind:
                continue
            agg_c.setdefault(k, []).append(v)
    common = sorted(set(agg_a) & set(agg_c))
    if len(common) < 5:
        return None
    a_sum = np.array([sum(agg_a[k]) for k in common], float)
    a_n = np.array([len(agg_a[k]) for k in common], float)
    c_sum = np.array([sum(agg_c[k]) for k in common], float)
    c_n = np.array([len(agg_c[k]) for k in common], float)
    point = a_sum.sum() / a_n.sum() - c_sum.sum() / c_n.sum()
    rng = np.random.default_rng(seed)
    m = len(common)
    diffs = np.empty(nb)
    for b in range(nb):
        idx = rng.integers(0, m, m)
        diffs[b] = a_sum[idx].sum() / a_n[idx].sum() - c_sum[idx].sum() / c_n[idx].sum()
    return float(point), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def per_cell(arm_raw, seed):
    path, used_rerun = E.cell_dir(arm_raw, seed)
    if path is None:
        return None
    cell = E.load_cell(path)
    score = (cell.get("score") or {}).get("score") or {}
    sweep = (score.get("sweep") or [{}])[0]
    rk, rn, racc = E.robot_correct_in_time(cell)
    dk, dn = robot_d176(cell, path, rk, rn)
    sk, sn, sacc, _, _ = E.ss_correct_in_time(path)
    # robot device-only floor / robot on time / single-shot within 2 s / dashcam attainment
    return {
        "cell": os.path.basename(path), "used_rerun": used_rerun,
        "robot_correct": rk, "robot_n": rn, "robot_acc": racc,
        "robot_d176_correct": dk, "robot_d176_n": dn,
        "robot_d176_acc": (dk / dn if dn else None),
        "robot_on_time_frac": sweep.get("robot_pool_fraction"),
        "ss_correct": sk, "ss_n": sn, "ss_acc": sacc,
        "ss_within_2s_frac": sweep.get("ss_pool_fraction"),
        "pooled_correct": (rk + sk if rk is not None and sk is not None else None),
        "pooled_n": (rn + sn if rn is not None and sn is not None else None),
    }


def main():
    arms = [(disp, raw) for disp, raw in E.ARMS if disp not in SUPERSEDED]
    arms.append((RR, "covex-v6-fair-c5attr-rr"))
    # superseded arms that have committed cells (so the exclusion is visible even after they are
    # removed from the registry): D205.
    dropped = sorted(a for a in SUPERSEDED if any(E.cell_dir(a, s)[0] for s in E.SEEDS))

    rows = []
    for disp, raw in arms:
        for s in E.SEEDS:
            r = per_cell(raw, s)
            if r is None:
                continue
            r["arm"] = disp
            r["seed"] = s
            rows.append(r)
    # device-only reference (robot device-only accuracy + ss device-only)
    for s in E.SEEDS:
        path, _ = E.cell_dir("hybrid-F-lhreq-noc3", s)
        if path is None:
            continue
        cell = E.load_cell(path)
        dev = (((cell.get("score") or {}).get("score") or {}).get("device_only") or {})
        acc, n = dev.get("robot_accuracy"), dev.get("robot_n")
        corr = E.ss2_correctness()
        outs = E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl"))
        sk = sn = 0
        for o in outs:
            if not str(o.get("device_id", "")).startswith("asst"):
                continue
            c = corr.get(o.get("question_id"))
            if c is None:
                continue
            sn += 1
            sk += 1 if c.get("device") else 0
        rk = int(round(acc * n)) if acc is not None and n is not None else None
        rows.append({"arm": DEVICE, "seed": s, "cell": path and os.path.basename(path),
                     "robot_correct": rk, "robot_n": n, "robot_acc": acc,
                     "robot_d176_correct": rk, "robot_d176_n": n, "robot_d176_acc": acc,
                     "ss_correct": sk, "ss_n": sn, "ss_acc": (sk / sn if sn else None),
                     "pooled_correct": (rk + sk if rk is not None else None),
                     "pooled_n": (n + sn if n is not None else None)})

    # dashcam delivered-stream mAP (D199) per arm, and D192 episode attainment beside it
    dash = dashcam_delivered(arms)
    ep = dash["episode_attainment"]
    delivered = dash["delivered_mAP"]

    # four-seed means + csv
    COLS = ["arm", "seed", "cell", "used_rerun", "robot_correct", "robot_n", "robot_acc",
            "robot_d176_correct", "robot_d176_n", "robot_d176_acc", "robot_on_time_frac",
            "ss_correct", "ss_n", "ss_acc", "ss_within_2s_frac", "pooled_correct", "pooled_n"]
    FIGDIR.mkdir(parents=True, exist_ok=True)
    with open(FIGDIR / "table1.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})

    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for c in ("robot_acc", "robot_d176_acc", "robot_on_time_frac", "ss_acc",
                  "ss_within_2s_frac"):
            if r.get(c) is not None:
                agg[r["arm"]][c].append(r[c])
        if r.get("pooled_correct") is not None and r.get("pooled_n"):
            agg[r["arm"]]["pooled_frac"].append(r["pooled_correct"] / r["pooled_n"])

    def mean(a, c):
        v = agg[a][c]
        return sum(v) / len(v) if v else None

    sha = {"canon": git_sha("experiments/analysis/canon/canon.py"),
           "episodic_lib": git_sha("experiments/analysis/episodic/episodic_lib.py"),
           "dsmap": git_sha("experiments/analysis/early1/dsmap.py"),
           "dashcam_episodic": git_sha("experiments/analysis/episodic/dashcam_episodic.py")}
    means = {a: {c: mean(a, c) for c in ("robot_acc", "robot_d176_acc", "robot_on_time_frac",
                                         "ss_acc", "ss_within_2s_frac", "pooled_frac")}
             for a in agg}
    for a in means:
        means[a]["dashcam_delivered_mAP_EVAL"] = delivered.get(a)
        means[a]["dashcam_episode_attain_D192"] = ep.get(a)

    # paired question-clustered CIs of correct-in-time (pooled / robot / single-shot) vs the rung-3
    # peer covex-v6-fair-c5attr-rr and vs device-only. Units pooled over seeds, clustered by question.
    armmap = dict(arms)
    units = {disp: {s: collect_units(raw, s) for s in E.SEEDS} for disp, raw in arms}
    units[DEVICE] = {s: collect_units("hybrid-F-lhreq-noc3", s, device_only=True) for s in E.SEEDS}
    for disp in list(means):
        if disp not in units:
            continue
        for ref in (RR, DEVICE):
            if disp == ref or ref not in units:
                continue
            for kind, tag in ((None, "pooled"), ("R", "robot"), ("S", "ss")):
                ci = paired_ci(units[disp], units[ref], kind=kind)
                if ci:
                    means[disp][f"ci_vs_{'rr' if ref == RR else 'dev'}_{tag}"] = \
                        {"diff": ci[0], "lo": ci[1], "hi": ci[2]}

    result = {"_what": "StudyTABLE1 (D209 canonical pipeline).", "pipeline_sha": sha,
              "superseded_dropped": dropped, "seeds": E.SEEDS,
              "arms": sorted(means), "four_seed_means": means}
    (FIGDIR / "table1_means.json").write_text(json.dumps(result, indent=1, default=float))
    write_md(means, sha, dropped, dash)
    print("pipeline sha:", sha["canon"])
    print("dropped superseded:", dropped)
    print("arms:", len(means))
    for a in sorted(means, key=lambda a: -(means[a]["pooled_frac"] or 0))[:6]:
        m = means[a]
        ci = m.get("ci_vs_rr_pooled")
        cis = f" vs-rr pooled {ci['diff']:+.3f}[{ci['lo']:+.3f},{ci['hi']:+.3f}]" if ci else ""
        print(f"  {a:22} robot {m['robot_acc']:.3f} (D176 {m['robot_d176_acc']:.3f}) ss {m['ss_acc']:.3f} "
              f"pooled {m['pooled_frac']:.3f} dash_mAP {m.get('dashcam_delivered_mAP_EVAL')}{cis}")


def dashcam_delivered(arms):
    """delivered-stream challenge mAP (EVAL) per arm via the dsmap pipeline, and D192 episode
    attainment, excluding superseded arms. Reads the committed dsmap and episodic results and drops
    superseded entries (same metric, same shas recorded)."""
    delivered = {}
    ep = {}
    p = FIGDIR / "dsmap_results.json"
    if p.exists():
        d = json.load(open(p))
        for a, v in d.get("arms", {}).items():
            if a in SUPERSEDED:
                continue
            delivered[a] = v["splits"]["EVAL"]["challenge_mAP"]
    pe = FIGDIR / "episodic_scores.csv"
    if pe.exists():
        from collections import defaultdict
        agg = defaultdict(list)
        for r in csv.DictReader(open(pe)):
            if r["arm_family"] if False else None:
                pass
            try:
                v = float(r["alert_mean_per_episode_attain"])
                agg[r["arm_family"]].append(v)
            except (KeyError, ValueError):
                pass
        for a, vs in agg.items():
            if a not in SUPERSEDED and vs:
                ep[a] = sum(vs) / len(vs)
    return {"delivered_mAP": delivered, "episode_attainment": ep,
            "_note": "delivered mAP from the committed DSMAP pipeline (dsmap.py), D192 attainment from "
                     "the committed episodic pipeline; both regenerated under the poll; superseded "
                     "arms dropped."}


def write_md(means, sha, dropped, dash):
    L = []
    A = L.append
    A("# StudyTABLE1: canonical correct-by-deadline table (D209)")
    A("")
    A(f"Pipeline sha canon {sha['canon']} (episodic_lib {sha['episodic_lib']}, dsmap {sha['dsmap']}, "
      f"dashcam_episodic {sha['dashcam_episodic']}). Seeds 4-7, four-seed means. Superseded arms "
      f"dropped (D205): {', '.join(dropped) if dropped else 'none in this table'}.")
    A("")
    A("Columns: robot correct-by-deadline (correct by 3 s, cloud if on time else device); robot D176 "
      "(same, excluding the over-32k context-refusal recalls); single-shot correct by 2 s (StudySS2); "
      "pooled correct-in-time over robot and single-shot units; dashcam delivered-stream Nexar "
      "challenge mAP (D199, on-time cloud only, EVAL); and the on-time service columns. The dashcam "
      "D192 per-episode attainment is beside the mAP and is NOT part of the claim.")
    A("")
    A("| arm | robot | robot D176 | single-shot | pooled | dashcam mAP (EVAL) | robot on-time | SS within 2s | dash attain (D192) |")
    A("|---|---|---|---|---|---|---|---|---|")
    order = sorted(means, key=lambda a: -(means[a]["pooled_frac"] or 0))
    for a in order:
        m = means[a]
        def f(x):
            return f"{x:.3f}" if isinstance(x, (int, float)) else "n/a"
        A(f"| {a} | {f(m['robot_acc'])} | {f(m['robot_d176_acc'])} | {f(m['ss_acc'])} | "
          f"{f(m['pooled_frac'])} | {f(m.get('dashcam_delivered_mAP_EVAL'))} | "
          f"{f(m['robot_on_time_frac'])} | {f(m['ss_within_2s_frac'])} | "
          f"{f(m.get('dashcam_episode_attain_D192'))} |")
    A("")
    A("Dashcam is a ranking metric (challenge mAP) with no per-unit correctness, so it is not pooled "
      "into the unit count; the pooled column is robot and single-shot units only. The D192 column is "
      "the thresholded per-episode attainment, kept beside the mAP and labelled not part of the "
      "claim (D199).")
    A("")
    A("## Paired question-clustered CIs (correct-in-time diff, 2000 reps, seed 0)")
    A("")
    A("Diff = arm minus comparator, pooled over seeds 4-7, clusters resampled by question identity. "
      "Positive favours the arm.")
    A("")
    A("| arm | pooled vs -rr [95% CI] | pooled vs device-only [95% CI] | robot vs device-only | single-shot vs device-only |")
    A("|---|---|---|---|---|")

    def ci(m, key):
        c = m.get(key)
        return f"{c['diff']:+.3f} [{c['lo']:+.3f}, {c['hi']:+.3f}]" if c else "n/a"
    for a in order:
        m = means[a]
        A(f"| {a} | {ci(m, 'ci_vs_rr_pooled')} | {ci(m, 'ci_vs_dev_pooled')} | "
          f"{ci(m, 'ci_vs_dev_robot')} | {ci(m, 'ci_vs_dev_ss')} |")
    A("")
    A("The dashcam delivered-stream mAP paired CIs vs rung 3 and device-only are in the StudyDSMAP "
      "report (reports/study_dsmap.md); they are not separable (all span 0, MDE 0.048 > arm gaps).")
    (OUTDIR / "table1.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
