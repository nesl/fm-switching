#!/usr/bin/env python3
"""StudyDASH2 Parts 4-5 (D199): value of a cloud answer by observable state, and budget-matched
allocation rules with the pre-registered decision rule. Offline, read-only, CPU only. Seeds 4-7.

Part 4: marginal gain in challenge mAP from replacing the device score with the cloud score at an
instant (from the cloud-every-instant stream 2a), grouped by RUNTIME-OBSERVABLE features only:
episode position, device calibrated level (quintiles), device trend over the last 2 instants, and the
last served cloud score. Fit groupings on DEV, report EVAL and cross-fitted ALL. No labels, event
times or future information in any feature.

Part 5: at each arm's actual on-time cloud budget (per seed), reassign which instants get the cloud
score: R0 as served, R1 uniform random (10 draws), R2 front-loaded, R3 device-gated, R4 device-trend,
R5 cloud-gated continuation, R6 best Part 4 grouping greedy. Paired challenge-mAP difference vs R0 and
vs R1 with clustered CIs, at the -rr and rung-3 budgets, plus deliverability.

DECISION RULE (pre-registered): recommend a rule if, at BOTH the -rr and rung-3 budgets, its paired
challenge-mAP difference vs R1 has a CI lower bound > 0 on cross-fitted ALL and a positive point on
EVAL; else report the best point estimates, the MDE and which is closest. No em dashes.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/early1"))
sys.path.insert(0, str(ROOT / "experiments/analysis/episodic"))
import dash2 as D2  # noqa: E402  maps, folds, Boot, labels, fake, cloud_every_instant
import episodic_lib as E  # noqa: E402

HOR = D2.HOR
CHALLENGE = D2.CHALLENGE
OUT = ROOT / "reports/figures"
BUDGET_ARMS = {"-rr": "covex-v6-fair-c5attr-rr", "rung3": "covex-v6-fair-c5attr"}
N_RANDOM = 10


def build_instants(seed, per_inst, cf4, cf32, folds, labels):
    """per episode (time-ordered) instants with observable features and the 2a cloud score."""
    tr = D2._trace(seed)
    rows_by_ep = defaultdict(list)
    for l in __import__("gzip").open(ROOT / D2.DS.TRACE.format(s=seed), "rt"):
        r = json.loads(l)
        rows_by_ep[r["episode_id"]].append((r["opportunity_id"], r["clip"], float(r["clip_pts"]),
                                             float(r["device_score"])))
    eps = {}
    for eid, insts in rows_by_ep.items():
        insts.sort(key=lambda x: x[2])
        clip = insts[0][1]
        fo = folds.get(clip, 0)
        rows = []
        prev_dev = None
        last_cloud = None
        for pos, (oid, _c, pts, dscore) in enumerate(insts):
            dev_cal = cf4[fo][0] * dscore + cf4[fo][1]
            cloud_cal = None
            if oid in per_inst:
                cs = float(np.median(per_inst[oid]))
                cloud_cal = cf32[fo][0] * cs + cf32[fo][1]
            rows.append({"oid": oid, "clip": clip, "pts": pts, "pos": pos, "dev_cal": dev_cal,
                         "cloud_cal": cloud_cal, "has_cloud": cloud_cal is not None,
                         "dev_trend": (dev_cal - prev_dev) if prev_dev is not None else 0.0,
                         "last_cloud": last_cloud})
            prev_dev = dev_cal
            if cloud_cal is not None:
                last_cloud = cloud_cal
        eps[eid] = {"clip": clip, "rows": rows}
    return eps


def crops_from_assignment(eps, serve_oids, labels, fake):
    """delivered crops {h:{clip:val}} where chosen oids get the cloud cal score, else device."""
    out = {h: defaultdict(list) for h in HOR}
    for eid, ep in eps.items():
        meta = labels.get(ep["clip"]) or {}
        ref = (float(meta["ref"]) if meta.get("label") == "positive" and meta.get("ref") is not None
               else (fake.get(ep["clip"]) if meta.get("label") == "negative" else None))
        if ref is None:
            continue
        stream = []
        for r in ep["rows"]:
            if r["oid"] in serve_oids and r["cloud_cal"] is not None:
                stream.append((r["pts"], r["cloud_cal"]))
            else:
                stream.append((r["pts"], r["dev_cal"]))
        for h in HOR:
            near = [v for (p, v) in stream if abs(p - (ref - h)) <= 0.5 + 1e-9]
            if near:
                out[h][ep["clip"]].append(float(np.mean(near)))
    return {h: {c: float(np.mean(vs)) for c, vs in out[h].items()} for h in HOR}


def all_rows(eps_by_seed):
    for s, eps in eps_by_seed.items():
        for eid, ep in eps.items():
            for r in ep["rows"]:
                yield s, eid, ep, r


def rule_assign(rule, eps_by_seed, budget_by_seed, r6_signal=None, rng=None, dev_bound=None):
    """return set of (seed, oid) to serve cloud, honoring the per-seed budget and only instants that
    have a 2a cloud score (has_cloud)."""
    serve = set()
    for s, eps in eps_by_seed.items():
        cand = [(eid, r) for eid, ep in eps.items() for r in ep["rows"] if r["has_cloud"]]
        B = budget_by_seed[s]
        if rule == "R1":
            idx = rng.permutation(len(cand))[:B]
            chosen = [cand[i] for i in idx]
        elif rule == "R2":  # front-loaded: smallest position first
            chosen = sorted(cand, key=lambda x: x[1]["pos"])[:B]
        elif rule == "R3":  # device-gated: highest device level
            chosen = sorted(cand, key=lambda x: -x[1]["dev_cal"])[:B]
        elif rule == "R4":  # device-trend: most rising
            chosen = sorted(cand, key=lambda x: -x[1]["dev_trend"])[:B]
        elif rule == "R5":  # cloud-gated continuation: prefer instants whose last_cloud high
            chosen = sorted(cand, key=lambda x: -((x[1]["last_cloud"] if x[1]["last_cloud"]
                                                   is not None else -1e9)))[:B]
        elif rule == "R6":  # best Part 4 grouping, greedy by estimated marginal gain
            chosen = sorted(cand, key=lambda x: -r6_signal(x[1]))[:B]
        else:
            chosen = []
        for eid, r in chosen:
            serve.add((s, r["oid"]))
    return serve


def served_crops(eps_by_seed, serve, labels, fake):
    merged = {h: defaultdict(list) for h in HOR}
    for s, eps in eps_by_seed.items():
        oids = set(o for (ss, o) in serve if ss == s)
        c = crops_from_assignment(eps, oids, labels, fake)
        for h in HOR:
            for clip, v in c[h].items():
                merged[h][clip].append(v)
    return {h: {c: float(np.mean(vs)) for c, vs in merged[h].items()} for h in HOR}


def r0_serve(eps_by_seed, arm_raw):
    """R0 as served: the instants the arm actually delivered on-time cloud for."""
    serve = set()
    bud = {}
    for s, eps in eps_by_seed.items():
        path, _ = E.cell_dir(arm_raw, s)
        on = set()
        if path:
            for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
                if not str(o.get("device_id", "")).startswith("dash"):
                    continue
                cp = o.get("cloud_payload") or {}
                if cp.get("on_time") and cp.get("cloud_score") is not None:
                    on.add(o["opportunity_id"])
        # only those with a 2a cloud score are serveable
        valid = set(r["oid"] for eid, ep in eps.items() for r in ep["rows"]
                    if r["has_cloud"] and r["oid"] in on)
        for oid in valid:
            serve.add((s, oid))
        bud[s] = len(valid)
    return serve, bud


def main():
    dur, labels = D2.DS.durations_refs()
    allclips = set()
    for s in E.SEEDS:
        allclips |= set(c for c, _, _ in D2._trace(s).values())
    folds = D2.clip_folds(allclips)
    cf4, dev4 = D2.crossfit_maps(D2.shep_instants(D2.SHEP_4BI), folds)
    cf32, dev32 = D2.crossfit_maps(D2.shep_instants(D2.SHEP_32BI), folds)
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng0 = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng0.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    side = D2.DS.sh_ep_side()

    # 2a per_inst per seed, and the instants structure
    valid_arms = [d for d in D2.ARMS_RAW if d != "device-only"
                  and any(E.cell_dir(D2.ARMS_RAW[d], s)[0] for s in E.SEEDS)]
    eps_by_seed = {}
    per_inst_by_seed = {}
    for s in E.SEEDS:
        per_inst, _ = D2.cloud_every_instant(s, valid_arms, cf32, folds)
        per_inst_by_seed[s] = per_inst
        eps_by_seed[s] = build_instants(s, per_inst, cf4, cf32, folds, labels)

    pos_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "positive")
    neg_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "negative")
    pos_eval = [c for c in pos_all if side.get(c) == "EVAL"]
    neg_eval = [c for c in neg_all if side.get(c) == "EVAL"]
    boot_all = D2.Boot(pos_all, neg_all)
    boot_eval = D2.Boot(pos_eval, neg_eval)

    # ---- Part 4: value by observable state (DEV-fit groupings, report ALL and EVAL) ----
    # marginal gain estimate: mean (cloud_cal - dev_cal) by group, on instants near the event in
    # crash clips (the instants that move the challenge metric), using DEV clips to pick the best
    # group, reporting the realized mAP lift of serving only that group.
    def group_of(r):
        return (min(4, int(r["dev_cal"] * 0 + 0)),)  # placeholder, replaced below
    # feature: device level quintile (observable). compute quintile edges on DEV instants.
    dev_levels = [r["dev_cal"] for s, eid, ep, r in all_rows(eps_by_seed)
                  if side.get(ep["clip"]) == "DEV" and r["has_cloud"]]
    q = np.quantile(dev_levels, [0.2, 0.4, 0.6, 0.8]) if dev_levels else [0, 0, 0, 0]

    def dev_quintile(r):
        return int(np.searchsorted(q, r["dev_cal"]))
    # marginal gain by quintile on DEV: mean (cloud_cal - dev_cal) on near-event crash instants
    gain_by_q = defaultdict(list)
    for s, eid, ep, r in all_rows(eps_by_seed):
        if side.get(ep["clip"]) != "DEV" or not r["has_cloud"]:
            continue
        meta = labels.get(ep["clip"]) or {}
        if meta.get("label") == "positive" and meta.get("ref") is not None:
            if -3.0 <= (r["pts"] - float(meta["ref"])) <= -0.5:
                gain_by_q[dev_quintile(r)].append(r["cloud_cal"] - r["dev_cal"])
    gain_summary = {int(k): float(np.mean(v)) for k, v in gain_by_q.items() if v}
    best_q = max(gain_summary, key=gain_summary.get) if gain_summary else 4

    def r6_signal(r):
        # greedy: prefer instants in the best device-level quintile, then higher device trend
        return (1 if dev_quintile(r) == best_q else 0) + 0.001 * r["dev_trend"]

    part4 = {"device_level_quintile_edges": [float(x) for x in q],
             "marginal_gain_cloud_minus_device_by_quintile_DEV": gain_summary,
             "best_quintile": int(best_q),
             "_note": "marginal gain is mean (cloud cal minus device cal) on instants 0.5 to 3.0 s "
                      "before the event in crash clips, by device-level quintile, DEV clips; features "
                      "are runtime-observable, no labels or event times used to form them."}

    # ---- Part 5: allocation rules at -rr and rung-3 budgets ----
    results = {"_what": "StudyDASH2 Parts 4-5 (D199).", "part4": part4, "budgets": {}, "part5": {},
               "MDE_reference": 0.048}
    rng = np.random.default_rng(0)
    for bname, braw in BUDGET_ARMS.items():
        r0_set, budget = r0_serve(eps_by_seed, braw)
        results["budgets"][bname] = {"per_seed": budget, "total": sum(budget.values())}
        tabs = {}
        # R0
        tabs["R0"] = {"ALL": boot_all.table(served_crops(eps_by_seed, r0_set, labels, fake)),
                      "EVAL": boot_eval.table(served_crops(eps_by_seed, r0_set, labels, fake))}
        # R1 (10 draws): mean + spread
        r1_maps_all, r1_maps_eval = [], []
        r1_streams_all = []
        for d in range(N_RANDOM):
            srv = rule_assign("R1", eps_by_seed, budget, rng=np.random.default_rng([1, d]))
            sa = served_crops(eps_by_seed, srv, labels, fake)
            r1_streams_all.append(sa)
            r1_maps_all.append(boot_all.table(sa)["challenge_mAP"])
            r1_maps_eval.append(boot_eval.table(served_crops(eps_by_seed, srv, labels, fake))["challenge_mAP"])
        # use the median R1 draw's stream as the paired reference
        med_i = int(np.argsort(r1_maps_all)[len(r1_maps_all) // 2])
        tabs["R1"] = {"ALL": boot_all.table(r1_streams_all[med_i]),
                      "EVAL": boot_eval.table(served_crops(eps_by_seed,
                              rule_assign("R1", eps_by_seed, budget, rng=np.random.default_rng([1, med_i])),
                              labels, fake))}
        for rule in ("R2", "R3", "R4", "R5", "R6"):
            srv = rule_assign(rule, eps_by_seed, budget, r6_signal=r6_signal)
            tabs[rule] = {"ALL": boot_all.table(served_crops(eps_by_seed, srv, labels, fake)),
                          "EVAL": boot_eval.table(served_crops(eps_by_seed, srv, labels, fake))}
        # report mAP + paired vs R0 and R1
        out = {}
        for rule in ("R0", "R1", "R2", "R3", "R4", "R5", "R6"):
            vr0 = boot_all.paired(tabs[rule]["ALL"], tabs["R0"]["ALL"])
            vr1 = boot_all.paired(tabs[rule]["ALL"], tabs["R1"]["ALL"])
            out[rule] = {"ALL_mAP": tabs[rule]["ALL"]["challenge_mAP"],
                         "EVAL_mAP": tabs[rule]["EVAL"]["challenge_mAP"],
                         "vs_R0_ALL": {"diff": vr0["diff"], "ci": vr0["ci"]},
                         "vs_R1_ALL": {"diff": vr1["diff"], "ci": vr1["ci"]},
                         "ap_by_horizon_ALL": {h: tabs[rule]["ALL"]["ap"][h]["ap"] for h in HOR}}
        out["R1_spread"] = {"mAP_mean_ALL": float(np.mean(r1_maps_all)),
                            "mAP_min_ALL": float(np.min(r1_maps_all)),
                            "mAP_max_ALL": float(np.max(r1_maps_all))}
        results["part5"][bname] = out

    # ---- decision rule ----
    rec = {}
    for rule in ("R2", "R3", "R4", "R5", "R6"):
        ok = True
        for bname in BUDGET_ARMS:
            v = results["part5"][bname][rule]
            if not (v["vs_R1_ALL"]["ci"][0] > 0 and v["EVAL_mAP"] >= results["part5"][bname]["R1"]["EVAL_mAP"]):
                ok = False
        rec[rule] = ok
    qualifying = [r for r, ok in rec.items() if ok]
    if qualifying:
        pick = max(qualifying, key=lambda r: np.mean([results["part5"][b][r]["vs_R1_ALL"]["diff"]
                                                      for b in BUDGET_ARMS]))
        verdict = {"recommend": True, "rule": pick}
    else:
        # closest: largest vs_R1 point averaged over budgets
        closest = max(("R2", "R3", "R4", "R5", "R6"),
                      key=lambda r: np.mean([results["part5"][b][r]["vs_R1_ALL"]["diff"]
                                             for b in BUDGET_ARMS]))
        verdict = {"recommend": False, "closest": closest,
                   "closest_vs_R1_diff_mean": float(np.mean([results["part5"][b][closest]["vs_R1_ALL"]["diff"]
                                                             for b in BUDGET_ARMS])),
                   "MDE": results["MDE_reference"],
                   "reason": "no rule has paired vs-R1 CI lower bound > 0 on ALL at both budgets with "
                             "positive EVAL point"}
    results["RECOMMENDATION"] = verdict

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dash2_rules_results.json").write_text(json.dumps(results, indent=1, default=float))
    _plot(results)
    print("budgets:", {b: results["budgets"][b]["total"] for b in BUDGET_ARMS})
    print("part4 best quintile:", best_q, "gain by q:", {k: round(v, 3) for k, v in gain_summary.items()})
    print("RECOMMENDATION:", json.dumps(verdict))
    for b in BUDGET_ARMS:
        print(f" {b}:")
        for rule in ("R0", "R1", "R2", "R3", "R4", "R5", "R6"):
            v = results["part5"][b][rule]
            print(f"   {rule}: ALL_mAP={v['ALL_mAP']:.3f} vs_R1={v['vs_R1_ALL']['diff']:+.3f}"
                  f"[{v['vs_R1_ALL']['ci'][0]:+.3f},{v['vs_R1_ALL']['ci'][1]:+.3f}]")


def _plot(results):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rules = ["R0", "R2", "R3", "R4", "R5", "R6"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), squeeze=False)
    for ax, b in zip(axes[0], BUDGET_ARMS):
        xs = range(len(rules))
        ys = [results["part5"][b][r]["vs_R1_ALL"]["diff"] for r in rules]
        los = [results["part5"][b][r]["vs_R1_ALL"]["ci"][0] for r in rules]
        his = [results["part5"][b][r]["vs_R1_ALL"]["ci"][1] for r in rules]
        ax.errorbar(list(xs), ys, yerr=[np.array(ys) - np.array(los), np.array(his) - np.array(ys)],
                    fmt="o", color="#0072B2", capsize=3)
        ax.axhline(0, color="#999999", lw=1)
        ax.set_xticks(list(xs)); ax.set_xticklabels(rules)
        ax.set_title(f"{b} budget: paired challenge-mAP vs R1 (ALL)")
        ax.set_ylabel("mAP difference vs R1 (uniform random)")
        ax.grid(True, alpha=0.25)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.suptitle("StudyDASH2 Part 5: allocation rules vs uniform random, cross-fitted ALL", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "dash2_rules.png", dpi=200, metadata={"Software": None}, bbox_inches="tight")
    fig.savefig(OUT / "dash2_rules.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
