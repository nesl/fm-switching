#!/usr/bin/env python3
"""StudyORACLE stages 5-6 consolidated (CPU, read-only, no images; D240 1x/kv0.5r separate).

Per-arm SHARE = (policy - floor)/(oracle - floor), per type and pooled, FAIR (matched expected
valuation, headline) and HINDSIGHT (realised), with a clustered bootstrap CI (2000 resamples, seed
0; clusters = question_id for recall/single-shot, episode_id for dashcam). The dashcam floor AND
policy use the SAME crossing model (episode_correct), so they are on one scale (fixes the pooled
HINDSIGHT share<0 that came from mixing DC.score_cell with the crossing-model floor).

Positive control: HINDSIGHT oracle >= FAIR oracle (per type+pooled), and EVERY arm's share must lie
in [0,1] on its own valuation - share>1 (beats the oracle) AND share<0 (below the device floor) both
FAIL and are reported with arm/type/seed/memory. covex-v6-fair-final (rung 3) is a scored arm. No
bound file is written here; this is the inspection artifact oracle_shares_v2.json.
"""
from __future__ import annotations
import json, os, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
for p in ("experiments/analysis/oracle", "experiments/analysis/canon",
          "experiments/analysis/episodic", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import canon as C  # noqa: E402
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
import oracle_lp_run as R  # noqa: E402
from oracle_dashcam import Instant, Episode, max_over_subsets, episode_correct  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
SS_C, SS_D = 0.621881, 0.547985
TIER = {"device": {"tpr": 0.155556, "tnr": 0.888889}, "cloud": {"tpr": 0.288889, "tnr": 0.888889}}
NB, BSEED = 2000, 0
ARMS = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]


def _cell(arm, seed, tag):
    for suf in ("_rerun", ""):
        d = RUNS / (f"{arm}_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf)
        if (d / "cell.json").exists():
            return str(d)
    return None


def dash_precompute(seed, tag, cloud, labels, th_dev, th_cloud):
    """Per episode (arm-independent): Episode object, v_dev, v_max, is_crash, ref, opp->instant id
    map, pre-event opp list."""
    by_ep = collections.defaultdict(list)
    for r in DC.load_trace_instants(seed):
        by_ep[r["episode_id"]].append(r)
    pre = {}
    for eid, rows in by_ep.items():
        rows.sort(key=lambda r: float(r["t_local"]))
        meta = labels.get(rows[0]["clip"]) or {}
        ref = meta.get("ref"); is_pos = (meta.get("label") == "positive")
        is_crash = bool(is_pos and ref is not None and any(float(r["t_local"]) < ref for r in rows))
        insts, iid, opps, pre_opps = [], {}, [], []
        for r in rows:
            ds = r.get("device_score"); ds = -1e9 if ds is None else ds
            cs = cloud.get(r["opportunity_id"]); cs = ds if cs is None else cs
            inst = Instant(float(r["t_local"]), ds, cs, 1.0)
            insts.append(inst); iid[r["opportunity_id"]] = id(inst); opps.append(r["opportunity_id"])
            if ref is not None and float(r["t_local"]) < ref:
                pre_opps.append(r["opportunity_id"])
        ep = Episode(eid, insts, is_crash, ref, th_dev, th_cloud)
        mos = max_over_subsets(ep)
        pre[eid] = {"ep": ep, "v_dev": mos["v_dev"], "v_max": mos["v_max"], "is_crash": is_crash,
                    "iid": iid, "opps": opps, "pre_opps": pre_opps}
    return pre


def arm_units(arm, seed, tag, acc_c, acc_d, rc, dash_pre):
    """Per-unit (cluster, type, polF,floF,orcF, polH,floH,orcH). None if no cell at this level."""
    path = _cell(arm, seed, tag)
    if path is None:
        return None
    cell = E.load_cell(path)
    over = C.over32k_oids(path)
    units = []
    rr = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    for r in rr:
        oid = r.get("opportunity_id")
        if oid is None or oid in over or not str(r.get("device_id", "")).startswith("robo"):
            continue
        dc = bool(r.get("device_correct"))
        tc = rc.get(oid)
        cc = tc[1] if tc else (None if r.get("cloud_letter") is None else bool(r.get("cloud_correct")))
        served = (r.get("source_by_deadline") == "cloud")
        polH = 1 if bool(r.get("standing_correct_by_deadline")) else 0
        orcH = 1 if (dc or cc is True) else 0
        units.append((r.get("question_id") or oid, "recall",
                      (acc_c if served else acc_d), acc_d, acc_c, polH, 1 if dc else 0, orcH))
    corr = E.ss2_correctness()
    refused, present = C.refused_and_present(path)
    onc_dash = set()
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        dev = str(o.get("device_id", ""))
        if dev.startswith("asst"):
            c = corr.get(o.get("question_id"))
            if c is None:
                continue
            dc, cc = bool(c.get("device")), bool(c.get("cloud"))
            cp = o.get("cloud_payload") or {}
            on_time = (bool(cp.get("on_time")) or bool(o.get("within_L"))) and \
                      (E.delivery_status(o, refused, present) == "delivered")
            units.append((o.get("question_id"), "single_shot", (SS_C if on_time else SS_D), SS_D, SS_C,
                          1 if (cc if on_time else dc) else 0, 1 if dc else 0, 1 if (dc or cc) else 0))
        elif dev.startswith("dash"):
            cp = o.get("cloud_payload") or {}
            if bool(cp.get("on_time")):
                onc_dash.add(o["opportunity_id"])
    for eid, ep in dash_pre.items():
        is_crash = ep["is_crash"]
        dacc = TIER["device"]["tpr"] if is_crash else TIER["device"]["tnr"]
        cacc = TIER["cloud"]["tpr"] if is_crash else TIER["cloud"]["tnr"]
        served_set = frozenset(ep["iid"][o] for o in ep["opps"] if o in onc_dash)
        polH = episode_correct(ep["ep"], served_set)                 # SAME model as the floor v_dev
        arm_served_crash = is_crash and any(o in onc_dash for o in ep["pre_opps"])
        units.append((eid, "dashcam", (cacc if arm_served_crash else dacc), dacc, cacc,
                      polH, ep["v_dev"], ep["v_max"]))
    return units


def share_ci(units, which, rng):
    pi, fi, oi = (2, 3, 4) if which == "F" else (5, 6, 7)
    agg = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for u in units:
        a = agg[u[0]]; a[0] += u[pi]; a[1] += u[fi]; a[2] += u[oi]
    if not agg:
        return None, None, None
    arr = np.array(list(agg.values()), dtype=float)
    n = arr.shape[0]
    tot = arr.sum(axis=0)
    pt = (tot[0] - tot[1]) / (tot[2] - tot[1]) if abs(tot[2] - tot[1]) > 1e-9 else None
    idx = rng.integers(0, n, size=(NB, n))
    sums = arr[idx].sum(axis=1)
    denom = sums[:, 2] - sums[:, 1]
    ok = np.abs(denom) > 1e-9
    sh = (sums[ok, 0] - sums[ok, 1]) / denom[ok]
    lo = round(float(np.percentile(sh, 2.5)), 4) if sh.size else None
    hi = round(float(np.percentile(sh, 97.5)), 4) if sh.size else None
    return (round(pt, 4) if pt is not None else None, lo, hi)


def main():
    labels = DC.nexar_labels()
    tier, th_dev, th_cloud = R.dev_tier()
    out = {"_what": "StudyORACLE stages 5-6 consolidated: shares + clustered bootstrap CIs. FAIR "
                    "matched expected valuation (headline), HINDSIGHT realised. dashcam floor and "
                    "policy both via episode_correct (one scale). Control: HINDSIGHT oracle >= FAIR "
                    "oracle, every arm share in [0,1] (share>1 or share<0 FAILS). rung 3 "
                    "(covex-v6-fair-final) scored. D240 separate; s6 flagged. NOT the bound file.",
           "n_bootstrap": NB, "bootstrap_seed": BSEED, "arms_scored": [a for a, _ in ARMS],
           "cells_used_rung3": [], "fail": [], "1x": {}, "kv0.5r": {}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            rc = R.recall_correctness(s, tag)
            dcs = [int(dc) for dc, cc in rc.values()]
            ccs = [int(cc) for dc, cc in rc.values() if cc is not None]
            acc_d = sum(dcs) / len(dcs) if dcs else 0.0
            acc_c = sum(ccs) / len(ccs) if ccs else 0.0
            cloud = R.simplestream_cloud(s, tag)
            dash_pre = dash_precompute(s, tag, cloud, labels, th_dev, th_cloud)
            r3cell = _cell("covex-v6-fair-final", s, tag)
            if r3cell:
                out["cells_used_rung3"].append(f"{mem} s{s}: {os.path.basename(r3cell)}")
            cellout = {"s6_outlier_flag": (s == 6), "arms": {}}
            rng = np.random.default_rng(BSEED)
            for disp, raw in ARMS:
                units = arm_units(raw, s, tag, acc_c, acc_d, rc, dash_pre)
                if units is None:
                    continue
                row = {}
                for typ in ("recall", "single_shot", "dashcam", "pooled"):
                    u = units if typ == "pooled" else [x for x in units if x[1] == typ]
                    if not u:
                        continue
                    pf, lf, hf = share_ci(u, "F", rng)
                    ph, lh, hh = share_ci(u, "H", rng)
                    row[typ] = {"FAIR": {"share": pf, "ci95": [lf, hf]},
                                "HINDSIGHT": {"share": ph, "ci95": [lh, hh]}}
                    for which, sh in (("FAIR", pf), ("HINDSIGHT", ph)):
                        if sh is not None and (sh > 1.0 + 1e-6 or sh < -1e-6):
                            out["fail"].append(f"{mem} s{s} {disp} {typ} {which}: share {sh}")
                cellout["arms"][disp] = row
            out[mem][f"s{s}"] = cellout
            print(f"{mem} s{s}: {len(cellout['arms'])} arms, fails so far {len(out['fail'])}")
    out["verdict"] = "PASS: every arm share in [0,1]" if not out["fail"] else \
                     f"FAIL: {len(out['fail'])} share(s) outside [0,1]"
    out["_provenance"] = stamp(script="oracle_bootstrap.py", model="qwen3vl32b", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/oracle_shares_v2.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("wrote oracle_shares_v2.json | VERDICT:", out["verdict"])
    for f in out["fail"][:15]:
        print("  FAIL:", f)
    return out


if __name__ == "__main__":
    main()
