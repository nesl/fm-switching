#!/usr/bin/env python3
"""StudyDASH2 Part 3: gap decomposition (D199). Offline, read-only, CPU only. Seeds 4-7.

Challenge mAP of the cloud-every-instant stream vs device-every-instant at each counterfactual step:
 (i)  SH-EP format (EP-G from clip start): cloud vs device on the SH-EP crops;
 (ii) workload format (same clips): cloud-every-instant vs device-every-instant;
 (iii) mixing tiers in one ranking (each arm's delivered stream at its own coverage) under three
       schemes fitted without the evaluated clip: Platt, isotonic, per-tier rank normalisation;
 (iv) only on-time cloud answers count, vs counting every cloud answer at its delivery time.
Plus each arm's cloud coverage restricted to instants 0.5 to 3.0 s before the event in crash clips,
against its overall coverage. Cross-fitted ALL primary, EVAL beside; paired clip-clustered CIs. No em
dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/early1"))
import dash2 as D2  # noqa: E402

HOR = D2.HOR
CHALLENGE = D2.CHALLENGE
OUT = ROOT / "reports/figures"


def build_calibrators(rows, folds):
    """per fold: Platt (a,b), isotonic model, and rank (sorted training scores)."""
    cal = {}
    for f in range(D2.NFOLD):
        sub = [r for r in rows if folds.get(r[0], -1) != f]
        X = np.array([r[1] for r in sub]); y = np.array([r[2] for r in sub])
        a, b = D2.fit_platt(sub)
        iso = IsotonicRegression(out_of_bounds="clip").fit(X, y)
        cal[f] = {"platt": (a, b), "iso": iso, "rank_sorted": np.sort(X), "n": len(X)}
    return cal


def apply_cal(cal, fold, scheme, score):
    c = cal[fold]
    if scheme == "platt":
        a, b = c["platt"]; return a * score + b
    if scheme == "iso":
        return float(c["iso"].predict([score])[0])
    # rank: percentile of score in the training distribution
    return float(np.searchsorted(c["rank_sorted"], score) / max(1, c["n"]))


def main():
    dur, labels = D2.DS.durations_refs()
    allclips = set()
    for s in D2.E.SEEDS:
        allclips |= set(c for c, _, _ in D2._trace(s).values())
    folds = D2.clip_folds(allclips)
    rows4 = D2.shep_instants(D2.SHEP_4BI)
    rows32 = D2.shep_instants(D2.SHEP_32BI)
    cal4 = build_calibrators(rows4, folds)
    cal32 = build_calibrators(rows32, folds)
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng0 = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng0.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    side = D2.DS.sh_ep_side()
    pos_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "positive")
    neg_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "negative")
    pos_eval = [c for c in pos_all if side.get(c) == "EVAL"]
    neg_eval = [c for c in neg_all if side.get(c) == "EVAL"]
    boot_all = D2.Boot(pos_all, neg_all)
    boot_eval = D2.Boot(pos_eval, neg_eval)

    def mAP_only(stream, boot):
        return boot.table(stream)["challenge_mAP"]

    # ---- (i) SH-EP format: cloud vs device on SH-EP EP-G crops (AP calibration-invariant) ----
    def shep_crops(rows):
        byclip = defaultdict(list)
        # need rel_to_ref; re-read with rel_to_ref
        return rows
    def shep_stream(path):
        byclip = defaultdict(list)
        op = gzip.open if str(path).endswith(".gz") else open
        for l in op(path, "rt"):
            if '"EP-G"' not in l:
                continue
            r = json.loads(l)
            if (r.get("condition") != "EP-G" or r.get("score") is None
                    or r.get("rel_to_ref") is None):
                continue
            byclip[r["file_name"]].append((float(r["rel_to_ref"]), float(r["score"])))
        out = {h: {} for h in HOR}
        for clip, rv in byclip.items():
            if clip not in allclips:
                continue
            for h in HOR:
                near = [sc for (rr, sc) in rv if abs(rr - (-h)) <= 0.5 + 1e-9]
                if near:
                    out[h][clip] = float(np.mean(near))
        return out
    shep_cloud = shep_stream(D2.SHEP_32BI)
    shep_dev = shep_stream(D2.SHEP_4BI)
    step_i = {"cloud_ALL": mAP_only(shep_cloud, boot_all), "device_ALL": mAP_only(shep_dev, boot_all),
              "cloud_EVAL": mAP_only(shep_cloud, boot_eval), "device_EVAL": mAP_only(shep_dev, boot_eval)}
    step_i["gap_ALL"] = step_i["cloud_ALL"] - step_i["device_ALL"]
    step_i["gap_EVAL"] = step_i["cloud_EVAL"] - step_i["device_EVAL"]

    # ---- workload streams: per instant cloud (on-time / every) + device, per arm ----
    valid_arms = [d for d in D2.ARMS_RAW if d != "device-only"
                  and any(D2.E.cell_dir(D2.ARMS_RAW[d], s)[0] for s in D2.E.SEEDS)]

    def device_every_stream(scheme):
        acc = {h: defaultdict(list) for h in HOR}
        for s in D2.E.SEEDS:
            for oid, (clip, pts, dscore) in D2._trace(s).items():
                fo = folds.get(clip, 0)
                acc_h(acc, clip, pts, apply_cal(cal4, fo, scheme, dscore), labels, fake)
        return pool(acc)

    def acc_h(acc, clip, pts, val, labels, fake):
        meta = labels.get(clip) or {}
        ref = (float(meta["ref"]) if meta.get("label") == "positive" and meta.get("ref") is not None
               else (fake.get(clip) if meta.get("label") == "negative" else None))
        if ref is None:
            return
        for h in HOR:
            if abs(pts - (ref - h)) <= 0.5 + 1e-9:
                acc[h][clip].append(val)

    def pool(acc):
        return {h: {c: float(np.mean(vs)) for c, vs in acc[h].items()} for h in HOR}

    # cloud-every-instant (union across arms), scheme-calibrated, device-filled
    def cloud_every_stream(scheme, which="on_time"):
        acc = {h: defaultdict(list) for h in HOR}
        for s in D2.E.SEEDS:
            tr = D2._trace(s)
            per_inst = defaultdict(list)
            for disp in valid_arms:
                path, _ = D2.E.cell_dir(D2.ARMS_RAW[disp], s)
                if path is None:
                    continue
                for o in D2.E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
                    if not str(o.get("device_id", "")).startswith("dash"):
                        continue
                    cp = o.get("cloud_payload") or {}
                    if cp.get("cloud_score") is None:
                        continue
                    if which == "on_time" and not cp.get("on_time"):
                        continue
                    per_inst[o["opportunity_id"]].append(float(cp["cloud_score"]))
            for oid, (clip, pts, dscore) in tr.items():
                fo = folds.get(clip, 0)
                if oid in per_inst:
                    v = apply_cal(cal32, fo, scheme, float(np.median(per_inst[oid])))
                else:
                    v = apply_cal(cal4, fo, scheme, dscore)
                acc_h(acc, clip, pts, v, labels, fake)
        return pool(acc)

    # ---- (ii) workload format: cloud-every (on-time) vs device-every, Platt ----
    dev_every = device_every_stream("platt")
    cloud_every_ot = cloud_every_stream("platt", "on_time")
    step_ii = {"cloud_every_ALL": mAP_only(cloud_every_ot, boot_all),
               "device_every_ALL": mAP_only(dev_every, boot_all),
               "cloud_every_EVAL": mAP_only(cloud_every_ot, boot_eval),
               "device_every_EVAL": mAP_only(dev_every, boot_eval)}
    step_ii["gap_ALL"] = step_ii["cloud_every_ALL"] - step_ii["device_every_ALL"]
    step_ii["gap_EVAL"] = step_ii["cloud_every_EVAL"] - step_ii["device_every_EVAL"]

    # ---- (iii) mixing schemes on each arm's delivered stream (on-time) ----
    def arm_delivered(arm_raw, scheme, which="on_time"):
        acc = {h: defaultdict(list) for h in HOR}
        for s in D2.E.SEEDS:
            path, _ = D2.E.cell_dir(arm_raw, s)
            if path is None:
                continue
            tr = D2._trace(s)
            cloud = {}
            for o in D2.E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
                if not str(o.get("device_id", "")).startswith("dash"):
                    continue
                cp = o.get("cloud_payload") or {}
                cloud[o["opportunity_id"]] = (bool(cp.get("on_time")), cp.get("cloud_score"))
            for oid, (clip, pts, dscore) in tr.items():
                fo = folds.get(clip, 0)
                con, cscore = cloud.get(oid, (False, None))
                use_cloud = cscore is not None and (con if which == "on_time" else True)
                v = (apply_cal(cal32, fo, scheme, float(cscore)) if use_cloud
                     else apply_cal(cal4, fo, scheme, dscore))
                acc_h(acc, clip, pts, v, labels, fake)
        return pool(acc)

    schemes = ["platt", "iso", "rank"]
    step_iii = {}
    step_iv = {}
    coverage = {}
    for disp in valid_arms:
        raw = D2.ARMS_RAW[disp]
        per_scheme = {}
        for sch in schemes:
            per_scheme[sch] = {"ALL": mAP_only(arm_delivered(raw, sch, "on_time"), boot_all),
                               "EVAL": mAP_only(arm_delivered(raw, sch, "on_time"), boot_eval)}
        step_iii[disp] = per_scheme
        # (iv) lateness: on-time vs every, Platt, with paired CI (ALL)
        ot = boot_all.table(arm_delivered(raw, "platt", "on_time"))
        ev = boot_all.table(arm_delivered(raw, "platt", "every"))
        pj = boot_all.paired(ev, ot)
        step_iv[disp] = {"on_time_ALL": ot["challenge_mAP"], "every_ALL": ev["challenge_mAP"],
                         "every_minus_on_time": {"diff": pj["diff"], "ci": pj["ci"]}}
        # coverage near-event (crash clips, 0.5 to 3.0 s before event) vs overall
        tot = near = tot_n = near_n = 0
        for s in D2.E.SEEDS:
            path, _ = D2.E.cell_dir(raw, s)
            if path is None:
                continue
            tr = D2._trace(s)
            on = set()
            for o in D2.E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
                if not str(o.get("device_id", "")).startswith("dash"):
                    continue
                cp = o.get("cloud_payload") or {}
                if cp.get("on_time") and cp.get("cloud_score") is not None:
                    on.add(o["opportunity_id"])
            for oid, (clip, pts, dscore) in tr.items():
                meta = labels.get(clip) or {}
                tot += 1
                if oid in on:
                    tot_n += 1
                if meta.get("label") == "positive" and meta.get("ref") is not None:
                    rel = pts - float(meta["ref"])
                    if -3.0 <= rel <= -0.5:
                        near += 1
                        if oid in on:
                            near_n += 1
        coverage[disp] = {"overall": (tot_n / tot if tot else None),
                          "near_event_crash": (near_n / near if near else None)}

    results = {"_what": "StudyDASH2 Part 3 gap decomposition (D199).",
               "step_i_shep_format": step_i, "step_ii_workload_format": step_ii,
               "step_iii_mixing_schemes": step_iii, "step_iv_lateness": step_iv,
               "coverage_near_vs_overall": coverage,
               "_decomposition_note": "steps i and ii are calibration-invariant (single-tier AP). "
                                      "The mixing schemes (iii) differ only in how cloud and device "
                                      "combine in one ranking; the lateness variant (iv) is on-time "
                                      "only vs every cloud answer at its delivery time."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dash2_part3_results.json").write_text(json.dumps(results, indent=1, default=float))
    print("step i (SH-EP): cloud", round(step_i["cloud_ALL"], 3), "device", round(step_i["device_ALL"], 3),
          "gap", round(step_i["gap_ALL"], 3), "(EVAL gap", round(step_i["gap_EVAL"], 3), ")")
    print("step ii (workload): cloud-every", round(step_ii["cloud_every_ALL"], 3), "device-every",
          round(step_ii["device_every_ALL"], 3), "gap", round(step_ii["gap_ALL"], 3))
    print("\nstep iii mixing (ALL delivered mAP per scheme), sample arms:")
    for a in ["fair-c5attr", "base", "simplestream", "always-cloud-fcfs"]:
        if a in step_iii:
            v = step_iii[a]
            print(f"  {a:20} platt {v['platt']['ALL']:.3f} iso {v['iso']['ALL']:.3f} rank {v['rank']['ALL']:.3f}")
    # mixing scheme spread across arms
    spreads = [max(step_iii[a][sch]["ALL"] for sch in schemes) - min(step_iii[a][sch]["ALL"] for sch in schemes)
               for a in step_iii]
    print("mixing-scheme max-min spread across arms: median", round(float(np.median(spreads)), 4),
          "max", round(float(np.max(spreads)), 4))
    print("\nstep iv lateness (every - on_time), sample arms:")
    for a in ["fair-c5attr", "base", "always-cloud-fcfs", "lmcache"]:
        if a in step_iv:
            v = step_iv[a]["every_minus_on_time"]
            print(f"  {a:20} on_time {step_iv[a]['on_time_ALL']:.3f} every {step_iv[a]['every_ALL']:.3f} "
                  f"delta {v['diff']:+.3f} [{v['ci'][0]:+.3f},{v['ci'][1]:+.3f}]")
    print("\ncoverage (near-event crash / overall), sample:")
    for a in ["fair-c5attr", "simplestream", "base", "device-only" if "device-only" in coverage else "lmcache"]:
        if a in coverage:
            print(f"  {a:20} near {coverage[a]['near_event_crash']} overall {coverage[a]['overall']}")


if __name__ == "__main__":
    main()
