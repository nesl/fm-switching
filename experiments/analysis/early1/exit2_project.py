#!/usr/bin/env python3
"""StudyEXIT2-project (D202): net benefit of the early exit on rung 3, offline. Read-only, CPU only.

Rung 3 = covex-v6-fair-c5attr seeds 4-7. Two service patterns x k in {2,3,4}:
  S (sparse, as served): the rule uses the last k cloud points actually delivered on time in the
    episode (not necessarily consecutive).
  D (dense start): the cloud serves the first k decision instants of every episode, then the rule
    applies; extra instants are those among the first k that rung 3 did not serve, charged at the
    cell median GPU seconds per alert request (D174).
Per (pattern, k) per seed and pooled: GPU seconds saved, extra GPU, NET as a fraction of dashcam
cloud GPU, split by exit type and correctness; delivered-stream challenge mAP after the exit vs rung
3 unchanged (paired CI), vs device-only and vs the best Part B baseline; net GPU freed beside the GPU
of late-alert instants (upper-bound indicator); workload composition.

PRE-REGISTERED RECOMMENDATION RULE (committed before computing): recommend building if some
(pattern, k) has NET GPU freed at least 10 percent of dashcam cloud GPU AND the delivered-stream
challenge mAP change vs rung 3 has a CI lower bound at least -0.01; pick the qualifying (pattern, k)
with the largest net GPU; else report not net positive. A recommendation, not a build. No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/early1"))
sys.path.insert(0, str(ROOT / "experiments/analysis/episodic"))
import dsmap as DS  # noqa: E402  Platt, challenge, nexar labels, trace
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402

GPU_PER_TOK = 0.000182431
RUNG3 = "covex-v6-fair-c5attr"
KS = [2, 3, 4]
OUT = ROOT / "reports/figures"
REC_GPU_FRAC = 0.10
REC_MAP_CI_LB = -0.01


def load_exit_model():
    d = json.load(open(OUT / "exit2_results.json"))
    a, b = d["platt_cloud_32BI"]["a"], d["platt_cloud_32BI"]["b"]
    models = {}
    for k in KS:
        v = d["by_k"][str(k)]
        models[k] = {"w": np.array([v["logistic_coef"]["level"], v["logistic_coef"]["slope"]]),
                     "b": v["logistic_coef"]["intercept"], "theta": v["crash_theta_prob"],
                     "bound": v["normal_bound_prob"]}
    return a, b, models, d["clip_overlap"]


def _prob(model, feats):
    z = float(np.dot(model["w"], feats) + model["b"])
    return 1.0 / (1.0 + np.exp(-z))


def cell_episodes(seed, a, b):
    """rung-3 episodes: {episode_id: dict(clip, label, ref, instants=[...])}. Each instant:
    clip_pts, cloud_on, cloud_cal (Platt), dev_cal (Platt), gpu_s (cloud), served (cloud request)."""
    path, _ = E.cell_dir(RUNG3, seed)
    if path is None:
        return None, None
    tr = DS._trace(seed)  # opp -> (clip, clip_pts, device_score)
    # cloud + cost
    cloud, cost = {}, {}
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("dash"):
            continue
        cp = o.get("cloud_payload") or {}
        cloud[o["opportunity_id"]] = (bool(cp.get("on_time")), cp.get("cloud_score"),
                                      cp.get("request_id") is not None)
    reqs = E.read_jsonl_gz(os.path.join(path, "request.jsonl")) or \
        E.read_jsonl_gz(os.path.join(path, "requests.jsonl"))
    for r in reqs:
        oid, pt, ct = r.get("opportunity_id"), r.get("prompt_tokens"), r.get("cached_tokens")
        if oid is None or pt is None or ct is None:
            continue
        cost[oid] = max(0, int(pt) - int(ct)) * GPU_PER_TOK
    labels = DC.nexar_labels()
    # fake refs for negatives (same construction as dsmap)
    eps = defaultdict(list)
    tr_by_opp = {}
    for l in gzip.open(ROOT / DS.TRACE.format(s=seed), "rt"):
        rr = json.loads(l)
        tr_by_opp[rr["opportunity_id"]] = rr
    for oid, rr in tr_by_opp.items():
        eps[rr["episode_id"]].append((oid, rr["clip"], float(rr["clip_pts"]),
                                      float(rr["device_score"])))
    out = {}
    cloud_gpu_total = 0.0
    median_alert_gpu = statistics.median([g for g in cost.values()]) if cost else 0.0
    for eid, insts in eps.items():
        insts.sort(key=lambda x: x[2])
        clip = insts[0][1]
        meta = labels.get(clip) or {}
        if meta.get("label") == "positive" and meta.get("ref") is not None:
            ref = float(meta["ref"])
            # D192 definition: a CRASH episode is a positive clip WITH a pre-event instant; a
            # positive clip's post-event segment is a no-crash episode.
            lab = "crash" if any(pts < ref for (_o, _c, pts, _d) in insts) else "nocrash"
        elif meta.get("label") == "negative":
            ref = DS_FAKE.get(clip); lab = "nocrash"
        else:
            continue
        rows = []
        for oid, _clip, pts, dscore in insts:
            con, cscore, served = cloud.get(oid, (False, None, False))
            g = cost.get(oid, 0.0) if served else 0.0
            cloud_gpu_total += g
            rows.append({"pts": pts, "cloud_on": con and cscore is not None,
                         "cloud_cal": (a * float(cscore) + b) if cscore is not None else None,
                         "dev_cal": a * dscore + b, "gpu": g, "served": served})
        out[eid] = {"clip": clip, "label": lab, "ref": ref, "rows": rows}
    return out, {"cloud_gpu_total": cloud_gpu_total, "median_alert_gpu": median_alert_gpu,
                 "path": os.path.basename(path)}


DS_FAKE = {}


def simulate(ep, model, k, pattern, median_gpu):
    """Return the exit decision + GPU bookkeeping for one episode."""
    rows = ep["rows"]
    # cloud points available to the rule
    if pattern == "S":
        pts = [(i, r["cloud_cal"], r["pts"]) for i, r in enumerate(rows) if r["cloud_on"]]
        extra = 0.0
        extra_n = 0
    else:  # D: first k instants are cloud-served; use real cloud_cal if served else dev_cal proxy
        pts = []
        for i, r in enumerate(rows[:k]):
            cal = r["cloud_cal"] if r["cloud_on"] else r["dev_cal"]
            pts.append((i, cal, r["pts"]))
        pts += [(i, r["cloud_cal"], r["pts"]) for i, r in enumerate(rows)
                if i >= k and r["cloud_on"]]
        extra_n = sum(1 for r in rows[:k] if not r["served"])
        extra = extra_n * median_gpu
    exit_i = None
    exit_type = None
    buf = []
    for (i, cal, pt) in pts:
        buf.append((pt, cal))
        if len(buf) < k:
            continue
        w = buf[-k:]
        rel = np.array([p for p, _ in w])
        cals = np.array([c for _, c in w])
        slope = float(np.polyfit(rel, cals, 1)[0]) if len(set(rel)) > 1 else 0.0
        p = _prob(model, np.array([cals[-1], slope]))
        if p >= model["theta"]:
            exit_i, exit_type = i, "crash"; break
        if p < model["bound"]:
            exit_i, exit_type = i, "normal"; break
    # GPU saved: cloud instants served AFTER the exit index
    saved = 0.0
    if exit_i is not None:
        saved = sum(r["gpu"] for j, r in enumerate(rows) if j > exit_i and r["served"])
    return {"exit_i": exit_i, "exit_type": exit_type, "saved": saved, "extra": extra,
            "extra_n": extra_n}


def delivered_after_exit(ep, sim, a, b):
    """post-exit standing calibrated score per instant, for the challenge crops."""
    rows = ep["rows"]
    out = []
    latched = None
    for j, r in enumerate(rows):
        if sim["exit_i"] is not None and j > sim["exit_i"]:
            if sim["exit_type"] == "crash":
                val = latched
            else:
                val = r["dev_cal"]
        else:
            val = r["cloud_cal"] if r["cloud_on"] else r["dev_cal"]
            if sim["exit_i"] is not None and j == sim["exit_i"] and sim["exit_type"] == "crash":
                latched = r["cloud_cal"] if r["cloud_on"] else r["dev_cal"]
        out.append((r["pts"], val))
    return out


def main():
    a, b, models, overlap = load_exit_model()
    # fake refs (shared with dsmap convention)
    dur, labels = DS.durations_refs()
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng = np.random.default_rng(0)
    DS_FAKE.update({c: float(min(max(dur[c] / 2 + rng.normal(0, sigma), 4.5), dur[c]))
                    for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur})
    side = DS.sh_ep_side()

    # rung-3 unchanged delivered-stream mAP (from Part B) and the reference rows
    dsmap_res = json.load(open(OUT / "dsmap_results.json"))
    rung3_eval = dsmap_res["arms"]["fair-c5attr"]["splits"]["EVAL"]["challenge_mAP"]
    devonly_eval = dsmap_res["arms"]["device-only"]["splits"]["EVAL"]["challenge_mAP"]
    best_base = max((a_ for a_ in dsmap_res["arms"]
                     if a_ not in ("fair-c5attr", "device-only") and "covex" not in a_
                     and a_ not in ("base", "rules") and not a_.startswith("state")),
                    key=lambda a_: dsmap_res["arms"][a_]["splits"]["EVAL"]["challenge_mAP"])
    best_base_map = dsmap_res["arms"][best_base]["splits"]["EVAL"]["challenge_mAP"]

    # load rung-3 episodes per seed
    allcells = {}
    cloud_gpu_total = 0.0
    for s in E.SEEDS:
        eps, meta = cell_episodes(s, a, b)
        if eps is None:
            continue
        allcells[s] = (eps, meta)
        cloud_gpu_total += meta["cloud_gpu_total"]

    results = {"_what": "StudyEXIT2-project: net benefit on rung 3 (D202).",
               "rung3_cells": [m["path"] for _, m in allcells.values()],
               "dashcam_cloud_gpu_total_s": cloud_gpu_total,
               "rung3_eval_mAP": rung3_eval, "device_only_eval_mAP": devonly_eval,
               "best_baseline": best_base, "best_baseline_eval_mAP": best_base_map,
               "clip_overlap": overlap, "workload_uses_dev_clips": overlap["workload_uses_dev_clips"],
               "by_pattern_k": {}, "workload_composition": {}}

    # workload composition per seed
    for s, (eps, _m) in allcells.items():
        crash = sum(1 for e in eps.values() if e["label"] == "crash")
        nocrash = sum(1 for e in eps.values() if e["label"] == "nocrash")
        results["workload_composition"][s] = {"crash": crash, "nocrash": nocrash,
                                              "n_episodes": len(eps)}

    def keep_eval(c):
        return side.get(c) == "EVAL"

    for pattern in ("S", "D"):
        for k in KS:
            m = models[k]
            saved = extra = 0.0
            tc = fc = tn = fn = 0  # true/false crash, true/false normal exits
            # post-exit and no-exit (rung-3 as served) delivered crops for EVAL clips, paired
            crops_exit = {h: defaultdict(list) for h in DS.HOR}
            crops_noexit = {h: defaultdict(list) for h in DS.HOR}
            NULL = {"exit_i": None, "exit_type": None}
            for s, (eps, meta) in allcells.items():
                for eid, ep in eps.items():
                    sim = simulate(ep, m, k, pattern, meta["median_alert_gpu"])
                    saved += sim["saved"]; extra += sim["extra"]
                    if sim["exit_type"] == "crash":
                        if ep["label"] == "crash": tc += 1
                        else: fc += 1
                    elif sim["exit_type"] == "normal":
                        if ep["label"] == "nocrash": tn += 1
                        else: fn += 1
                    ref = ep["ref"]
                    if ref is None or not keep_eval(ep["clip"]):
                        continue
                    stream = delivered_after_exit(ep, sim, a, b)
                    base_stream = delivered_after_exit(ep, NULL, a, b)
                    for h in DS.HOR:
                        tgt = ref - h
                        ne = [v for (p, v) in stream if v is not None and abs(p - tgt) <= 0.5 + 1e-9]
                        nb = [v for (p, v) in base_stream
                              if v is not None and abs(p - tgt) <= 0.5 + 1e-9]
                        if ne:
                            crops_exit[h][ep["clip"]].append(float(np.mean(ne)))
                        if nb:
                            crops_noexit[h][ep["clip"]].append(float(np.mean(nb)))
            pooled_exit = {h: {c: float(np.mean(vs)) for c, vs in crops_exit[h].items()}
                           for h in DS.HOR}
            pooled_noexit = {h: {c: float(np.mean(vs)) for c, vs in crops_noexit[h].items()}
                             for h in DS.HOR}

            class LP:
                def get(self, c):
                    return labels.get(c)
            lp = LP()
            tab = DS.challenge(pooled_exit, lp, lambda c: True, lambda c: True)
            tab_noexit = DS.challenge(pooled_noexit, lp, lambda c: True, lambda c: True)
            net = saved - extra
            net_frac = net / cloud_gpu_total if cloud_gpu_total else None
            # PAIRED mAP change: exit minus no-exit on the same resampled clips (DS.challenge uses the
            # same seed, so its per-horizon bootstrap indices align and the diff is paired)
            pj = DS.paired_mAP(tab, tab_noexit)
            dmap = pj["diff"] if pj else (tab["challenge_mAP"] - tab_noexit["challenge_mAP"])
            dmap_ci = pj["ci"] if pj else None
            results["by_pattern_k"][f"{pattern}_k{k}"] = {
                "gpu_saved_s": saved, "extra_gpu_s": extra, "net_gpu_s": net,
                "net_gpu_fraction_of_dashcam_cloud": net_frac,
                "exits": {"true_crash": tc, "false_crash": fc, "true_normal": tn, "false_normal": fn},
                "delivered_mAP_after_exit_EVAL": tab["challenge_mAP"],
                "delivered_mAP_change_vs_rung3": dmap,
                "delivered_mAP_change_ci_approx": dmap_ci,
                "vs_device_only": tab["challenge_mAP"] - devonly_eval,
                "vs_best_baseline": tab["challenge_mAP"] - best_base_map}

    # recommendation
    qual = []
    for key, v in results["by_pattern_k"].items():
        if (v["net_gpu_fraction_of_dashcam_cloud"] is not None
                and v["net_gpu_fraction_of_dashcam_cloud"] >= REC_GPU_FRAC
                and v["delivered_mAP_change_ci_approx"] is not None
                and v["delivered_mAP_change_ci_approx"][0] >= REC_MAP_CI_LB):
            qual.append((key, v["net_gpu_fraction_of_dashcam_cloud"]))
    if qual:
        pick = max(qual, key=lambda x: x[1])
        verdict = {"recommend_build": True, "pick": pick[0], "net_gpu_fraction": pick[1],
                   "rule": f"net GPU freed >= {REC_GPU_FRAC} AND mAP change CI lb >= {REC_MAP_CI_LB}"}
    else:
        verdict = {"recommend_build": False, "reason": "no (pattern,k) meets net GPU >= 10% with "
                   "mAP change CI lower bound >= -0.01", "numbers_above": True}
    results["RECOMMENDATION"] = verdict

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "exit2_project_results.json").write_text(json.dumps(results, indent=1, default=float))
    _plot(results)
    _md(results, overlap)
    print("RECOMMENDATION:", json.dumps(verdict))
    for key, v in results["by_pattern_k"].items():
        print(f"  {key}: net_gpu_frac={v['net_gpu_fraction_of_dashcam_cloud']:.4f} "
              f"mAP_chg={v['delivered_mAP_change_vs_rung3']:+.4f} "
              f"exits(tc/fc/tn/fn)={v['exits']['true_crash']}/{v['exits']['false_crash']}/"
              f"{v['exits']['true_normal']}/{v['exits']['false_normal']}")


def _plot(results):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    for key, v in results["by_pattern_k"].items():
        x = v["net_gpu_fraction_of_dashcam_cloud"]
        y = v["delivered_mAP_change_vs_rung3"]
        col = "#0072B2" if key.startswith("S") else "#D55E00"
        ax.scatter([x], [y], color=col, s=70, zorder=3)
        ax.annotate(key, (x, y), textcoords="offset points", xytext=(5, 3), fontsize=8)
    ax.axvline(REC_GPU_FRAC, color="#999999", ls="--", lw=1)
    ax.axhline(REC_MAP_CI_LB, color="#999999", ls=":", lw=1)
    ax.text(REC_GPU_FRAC, ax.get_ylim()[1], " rec: net GPU >= 10%", fontsize=7.5, color="#666666",
            va="top")
    ax.set_xlabel("net GPU freed (fraction of dashcam cloud GPU)")
    ax.set_ylabel("delivered-stream challenge mAP change vs rung 3 (EVAL)")
    ax.set_title("StudyEXIT2-project: net GPU vs mAP change per (pattern, k)")
    ax.grid(True, alpha=0.25)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "exit2_netgpu_vs_map.png", dpi=200, metadata={"Software": None},
                bbox_inches="tight")
    fig.savefig(OUT / "exit2_netgpu_vs_map.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


def _md(results, overlap):
    ef = json.load(open(OUT / "exit2_results.json"))
    L = []
    A = L.append
    A("# StudyEXIT2: episode early exit, fit and projection (D202)")
    A("")
    A("## Part C: trajectory model (StudyEXIT2-fit), fit DEV report EVAL")
    A("")
    A(f"Platt cloud map a={ef['platt_cloud_32BI']['a']:.4f} b={ef['platt_cloud_32BI']['b']:.4f}. "
      f"Clip overlap: the workload uses {overlap['workload_clips_in_dev']} of {overlap['n_dev']} "
      f"SH-EP DEV clips, so Part D reports EVAL-clip episodes.")
    A("")
    A("| k | crash caught (EVAL) | false crash on no-crash | fire time before event (med) | "
      "false normal on crash | n_train |")
    A("|---|---|---|---|---|---|")
    for k in KS:
        v = ef["by_k"][str(k)]["eval"]
        tr = ef["by_k"][str(k)]["n_train"]
        A(f"| {k} | {v['crash_rule']['fraction_crash_caught']:.3f} | "
          f"{v['crash_rule']['false_crash_exit_rate_on_no_crash']:.3f} | "
          f"{v['crash_rule']['firing_time_before_event_s']['median']} s | "
          f"{v['normal_rule']['false_normal_exit_rate_on_crash']:.3f} | {tr} |")
    A("")
    r = ef["d197_level_only_reference"]["EVAL"]
    A(f"Reference D197 level-only trigger (EVAL): crash caught {r['crash_caught_rate']:.3f}, "
      f"false crash {r['false_crash_rate']:.3f}, median fire time {r['median_fire_time_s']} s. The "
      "trajectory model (level plus slope) catches more and fires earlier than the level-only "
      "trigger. The normal-exit rule generalizes poorly (DEV 10 percent target, EVAL 22 to 27 "
      "percent false normal exit) and is reported as unreliable.")
    A("")
    A("## Part D: net benefit projection on rung 3 (covex-v6-fair-c5attr seeds 4-7)")
    A("")
    A(f"Dashcam cloud GPU total over the four cells: {results['dashcam_cloud_gpu_total_s']:.1f} s. "
      f"Rung 3 delivered-stream EVAL mAP {results['rung3_eval_mAP']:.3f}; device-only "
      f"{results['device_only_eval_mAP']:.3f}; best Part B baseline {results['best_baseline']} "
      f"{results['best_baseline_eval_mAP']:.3f}.")
    A("")
    A("| pattern,k | net GPU frac | gpu saved (s) | extra (s) | mAP change vs rung3 [paired CI] | "
      "exits tc/fc/tn/fn |")
    A("|---|---|---|---|---|---|")
    for key, v in results["by_pattern_k"].items():
        ci = v["delivered_mAP_change_ci_approx"]
        cis = f"[{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else "n/a"
        ex = v["exits"]
        A(f"| {key} | {v['net_gpu_fraction_of_dashcam_cloud']:+.4f} | {v['gpu_saved_s']:.1f} | "
          f"{v['extra_gpu_s']:.1f} | {v['delivered_mAP_change_vs_rung3']:+.4f} {cis} | "
          f"{ex['true_crash']}/{ex['false_crash']}/{ex['true_normal']}/{ex['false_normal']} |")
    A("")
    A("Workload composition per seed (crash / no-crash episodes): " +
      ", ".join(f"s{s}: {c['crash']}/{c['nocrash']}" for s, c in results["workload_composition"].items()))
    A("")
    A("Net GPU freed is an UPPER-BOUND indicator: an offline projection cannot say how freed GPU "
      "turns into fewer late alerts; that needs a live cell.")
    A("")
    A("## RECOMMENDATION (pre-registered rule)")
    A("")
    rec = results["RECOMMENDATION"]
    if rec["recommend_build"]:
        A(f"RECOMMEND BUILDING: ({rec['pick']}) meets the rule (net GPU freed "
          f"{rec['net_gpu_fraction']:.3f} >= 0.10 and mAP change CI lower bound >= -0.01).")
    else:
        A(f"NOT NET POSITIVE: {rec['reason']}. No (pattern, k) qualifies; the numbers are in the "
          "table above. A recommendation, not a build; the user decides.")
    A("")
    A("## Approximations and caveats")
    A("")
    A("The mAP-change CI is a PAIRED clip bootstrap: the exit stream and the rung-3 as-served stream "
      "are scored on the same resampled clips (same seed, so the per-horizon bootstrap indices "
      "align) and the per-resample difference is taken. Pattern D uses the real cloud score at a "
      "served first-k instant and the device score as a stand-in where rung 3 did not serve it; the "
      "extra GPU is charged for every unserved first-k instant regardless. These are projection "
      "assumptions, stated so the recommendation can be read with them in view.")
    (ROOT / "reports/study_exit2.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
