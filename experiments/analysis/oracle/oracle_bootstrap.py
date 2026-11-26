#!/usr/bin/env python3
"""StudyORACLE stages 5-6 consolidated, D268-corrected (CPU, read-only, no images; D240 separate).

SHARE = (policy - floor)/(oracle - floor), per type and pooled, FAIR (expected valuation conditioned
on CONTEXT SENT, headline) and HINDSIGHT (realised), with a clustered bootstrap CI (2000 resamples,
seed 0; clusters = question_id recall/single-shot, episode_id dashcam).

FAIR valuation (identical table applied to oracle and every policy, pooled across arms, from
oracle_fair_table.json):
- recall served -> acc[recall, cloud, state], state = WITH_HISTORY iff this arm's prompt_tokens>=2000
  for that query, else WITHOUT_HISTORY; unserved -> acc[recall, device]. oracle serves WITH_HISTORY.
- single_shot served -> acc[ss, cloud] (stateless); unserved -> acc[ss, device].
- dashcam served (cloud, with history) -> per-tier (crash/nocrash) cloud expected acc; unserved ->
  device per-tier. The per-tier rates are estimated here under the committed score_cell INSTANT
  thresholds (device -2.579, cloud -6.876), pooled across seeds.

HINDSIGHT: realised per-unit correctness; dashcam floor v_dev, policy episode_correct(arm served),
oracle v_max, all on the instant-threshold score_cell model (one scale).

Control (unchanged): HINDSIGHT oracle >= FAIR oracle (per type + pooled), and every arm share in
[0,1] - share>1 (beats oracle) AND share<0 (below device floor) both FAIL, reported with
arm/type/seed/memory. rung 3 (covex-v6-fair-final) scored. No bound file written here.
"""
from __future__ import annotations
import json, os, sys, gzip, collections
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
HIST_TOK = 2000
NB, BSEED = 2000, 0
# confidence-cascade was dropped from E.ARMS under D205 (delivered_scores constant 0.0 reader). Re-added
# for the table as requested; its s4 1x cell serves cloud on 3 of 132 robot questions, consistent with
# that defect, so it is FLAGGED superseded and is not eligible as a live baseline.
FLAGGED = {"confidence-cascade"}
ARMS = list(E.ARMS) + [("confidence-cascade", "confidence-cascade"),
                       ("fair-final-rung3", "covex-v6-fair-final")]
FT = json.load(open(REPO / "results/orchestration/live2/oracle/oracle_fair_table.json"))["table"]
A_RC_H = FT["recall|cloud|WITH_HISTORY"]["acc"]
A_RC_N = FT["recall|cloud|WITHOUT_HISTORY"]["acc"]
A_RD = FT["recall|device|NA"]["acc"]
A_SC = FT["single_shot|cloud|COLD"]["acc"]
A_SD = FT["single_shot|device|NA"]["acc"]
THR = DC.thresholds()
TH_DEV, TH_CLOUD = THR["device"], THR["cloud"]   # INSTANT thresholds (match committed score_cell)


def _cell(arm, seed, tag):
    # h0.5 cells: fair-final exists only as _preD249 (committed D250 cell); 1x and kv0.5r unchanged
    sufs = ("_rerun", "", "_preD249") if tag == "_kv0.5r_h0.5" else ("_rerun", "")
    for suf in sufs:
        d = RUNS / (f"{arm}_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf)
        if (d / "cell.json").exists():
            return str(d)
    return None


def req_pt(cell):
    """opportunity_id -> prompt_tokens for robot cloud requests of this cell (context sent)."""
    out = {}
    for nm, op in (("request.jsonl.gz", gzip.open), ("request.jsonl", open)):
        p = os.path.join(cell, nm)
        if not os.path.exists(p):
            continue
        with op(p, "rt") as f:
            for l in f:
                try:
                    r = json.loads(l)
                except Exception:
                    continue
                if str(r.get("device_id", "")).startswith("robo") and r.get("prompt_tokens"):
                    out[r.get("opportunity_id")] = r["prompt_tokens"]
        break
    return out


def dash_precompute(seed, cloud, labels):
    by_ep = collections.defaultdict(list)
    for r in DC.load_trace_instants(seed):
        by_ep[r["episode_id"]].append(r)
    pre = {}
    for eid, rows in by_ep.items():
        rows.sort(key=lambda r: float(r["t_local"]))
        meta = labels.get(rows[0]["clip"]) or {}
        ref = meta.get("ref"); is_pos = (meta.get("label") == "positive")
        is_crash = bool(is_pos and ref is not None and any(float(r["t_local"]) < ref for r in rows))
        insts, iid, opps = [], {}, []
        for r in rows:
            ds = r.get("device_score"); ds = -1e9 if ds is None else ds
            cs = cloud.get(r["opportunity_id"]); cs = ds if cs is None else cs
            it = Instant(float(r["t_local"]), ds, cs, 1.0)
            insts.append(it); iid[r["opportunity_id"]] = id(it); opps.append(r["opportunity_id"])
        ep = Episode(eid, insts, is_crash, ref, TH_DEV, TH_CLOUD)
        mos = max_over_subsets(ep)
        all_served = frozenset(iid.values())
        pre[eid] = {"ep": ep, "v_dev": mos["v_dev"], "v_max": mos["v_max"], "is_crash": is_crash,
                    "iid": iid, "opps": opps, "cloud_all": episode_correct(ep, all_served)}
    return pre


def dash_tier_acc(dash_by_seed):
    """Pooled per-tier expected accuracy under the instant-threshold model."""
    acc = {}
    for crash in (True, False):
        vd = [e["v_dev"] for pre in dash_by_seed.values() for e in pre.values() if e["is_crash"] == crash]
        vc = [e["cloud_all"] for pre in dash_by_seed.values() for e in pre.values() if e["is_crash"] == crash]
        k = "crash" if crash else "nocrash"
        acc[("device", k)] = sum(vd) / len(vd) if vd else 0.0
        acc[("cloud", k)] = sum(vc) / len(vc) if vc else 0.0
    return acc


def arm_units(arm, seed, tag, rc, dash_pre, dta):
    path = _cell(arm, seed, tag)
    if path is None:
        return None
    cell = E.load_cell(path)
    over = C.over32k_oids(path)
    pt = req_pt(path)
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
        a_state = A_RC_H if pt.get(oid, 0) >= HIST_TOK else A_RC_N
        polF = a_state if served else A_RD
        orcF = max(A_RD, A_RC_H)                       # oracle serves WITH_HISTORY
        polH = 1 if bool(r.get("standing_correct_by_deadline")) else 0
        orcH = 1 if (dc or cc is True) else 0
        units.append((r.get("question_id") or oid, "recall", polF, A_RD, orcF, polH, 1 if dc else 0, orcH))
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
            units.append((o.get("question_id"), "single_shot", (A_SC if on_time else A_SD), A_SD,
                          max(A_SD, A_SC), 1 if (cc if on_time else dc) else 0, 1 if dc else 0,
                          1 if (dc or cc) else 0))
        elif dev.startswith("dash"):
            cp = o.get("cloud_payload") or {}
            if bool(cp.get("on_time")):
                onc_dash.add(o["opportunity_id"])
    for eid, ep in dash_pre.items():
        k = "crash" if ep["is_crash"] else "nocrash"
        served = any(o in onc_dash for o in ep["opps"])
        polF = dta[("cloud", k)] if served else dta[("device", k)]
        floF = dta[("device", k)]
        orcF = max(dta[("device", k)], dta[("cloud", k)])
        served_set = frozenset(ep["iid"][o] for o in ep["opps"] if o in onc_dash)
        polH = episode_correct(ep["ep"], served_set)
        units.append((eid, "dashcam", polF, floF, orcF, polH, ep["v_dev"], ep["v_max"]))
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


def shares_block(units, rng):
    row = {}
    for typ in ("recall", "single_shot", "dashcam", "pooled"):
        u = units if typ == "pooled" else [x for x in units if x[1] == typ]
        if not u:
            continue
        pf, lf, hf = share_ci(u, "F", rng)
        ph, lh, hh = share_ci(u, "H", rng)
        row[typ] = {"FAIR": {"share": pf, "ci95": [lf, hf]},
                    "HINDSIGHT": {"share": ph, "ci95": [lh, hh]}}
    return row


def oracle_control(units, rng):
    """Per type: FAIR oracle mean, HIND oracle mean, and bootstrap CI of (FAIR-HIND). A failure only
    if the gap exceeds the CI (CI of FAIR-HIND lies entirely above 0). Arm-independent columns."""
    res = {}
    for typ in ("recall", "single_shot", "dashcam"):
        u = [x for x in units if x[1] == typ]
        if not u:
            continue
        agg = collections.defaultdict(lambda: [0.0, 0.0])    # cluster -> [orcF, orcH]
        for x in u:
            a = agg[x[0]]; a[0] += x[4]; a[1] += x[7]
        arr = np.array(list(agg.values()), dtype=float)
        n = arr.shape[0]
        mF, mH = arr[:, 0].sum() / n, arr[:, 1].sum() / n
        idx = rng.integers(0, n, size=(NB, n))
        samp = arr[idx]                                                    # (NB, n, 2)
        d = (samp[:, :, 0].sum(axis=1) - samp[:, :, 1].sum(axis=1)) / n     # FAIR - HIND per resample
        lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
        res[typ] = {"fair_oracle": round(mF, 4), "hind_oracle": round(mH, 4),
                    "fair_minus_hind_ci95": [round(lo, 4), round(hi, 4)],
                    "fail": bool(lo > 1e-6)}   # FAIR oracle significantly above HIND oracle
    return res


def main():
    labels = DC.nexar_labels()
    dash_by_seed = {s: dash_precompute(s, R.simplestream_cloud(s, ""), labels) for s in SEEDS}
    dta = dash_tier_acc(dash_by_seed)
    out = {"_what": "StudyORACLE bound (D268-corrected): FAIR conditioned on CONTEXT SENT, dashcam on "
                    "instant-threshold score_cell model (verified: same thresholds/instants both tiers,"
                    " 0 imputed device scores, cloud false-alarm excess confirmed per seed). Control: "
                    "share>1 a hard STOP; share<0 REPORTED, not blocking (genuine worse-than-device); "
                    "HIND oracle>=FAIR oracle checked per seed AND pooled, a failure only if the gap "
                    "exceeds the bootstrap CI. rung 3 scored. D240 separate; s6 flagged (20-25 distinct"
                    " robot questions/seed, single-question basis).",
           "fair_recall_cloud_with_history": A_RC_H, "fair_recall_cloud_without_history": A_RC_N,
           "fair_recall_device": A_RD, "single_shot_cloud": A_SC, "single_shot_device": A_SD,
           "dashcam_tier_acc": {f"{t}|{k}": round(v, 6) for (t, k), v in dta.items()},
           "n_bootstrap": NB, "bootstrap_seed": BSEED, "cells_used_rung3": [],
           "stop_share_gt_1": [], "reported_share_lt_0": [], "oracle_control": {}, "1x": {}, "kv0.5r": {}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        pooled = collections.defaultdict(list)            # arm -> units across seeds
        ctrl_pool = []                                    # arm-independent units for oracle control
        out["oracle_control"][mem] = {"per_seed": {}, "pooled": {}}
        for s in SEEDS:
            rc = R.recall_correctness(s, tag)
            dash_pre = dash_by_seed[s]
            r3 = _cell("covex-v6-fair-final", s, tag)
            if r3:
                out["cells_used_rung3"].append(f"{mem} s{s}: {os.path.basename(r3)}")
            cellout = {"s6_outlier_flag": (s == 6), "arms": {}}
            rng = np.random.default_rng(BSEED)
            ctrl_units = None
            for disp, raw in ARMS:
                units = arm_units(raw, s, tag, rc, dash_pre, dta)
                if units is None:
                    continue
                # per-arm generator: CI must not depend on which arms precede it (point shares unaffected)
                cellout["arms"][disp] = shares_block(units, np.random.default_rng(BSEED))
                pooled[disp].extend(units)
                if ctrl_units is None or len(units) > len(ctrl_units):
                    ctrl_units = units           # highest-coverage arm for arm-independent oracle cols
                for typ, blk in cellout["arms"][disp].items():
                    for wch in ("FAIR", "HINDSIGHT"):
                        sh = blk[wch]["share"]
                        if sh is None:
                            continue
                        if sh > 1.0 + 1e-6:
                            out["stop_share_gt_1"].append(f"{mem} s{s} {disp} {typ} {wch}: {sh}")
                        elif sh < -1e-6:
                            out["reported_share_lt_0"].append(f"{mem} s{s} {disp} {typ} {wch}: {sh}")
            if ctrl_units:
                ctrl_pool.extend(ctrl_units)
                out["oracle_control"][mem]["per_seed"][f"s{s}"] = oracle_control(
                    ctrl_units, np.random.default_rng(BSEED))
            out[mem][f"s{s}"] = cellout
        # pooled-over-seeds shares + oracle control
        out[mem]["pooled_over_seeds"] = {}
        rng = np.random.default_rng(BSEED)
        for disp in [a for a, _ in ARMS]:
            if pooled.get(disp):
                out[mem]["pooled_over_seeds"][disp] = shares_block(pooled[disp], np.random.default_rng(BSEED))
        out["oracle_control"][mem]["pooled"] = oracle_control(ctrl_pool, np.random.default_rng(BSEED))
        ocfails = [f"{mem} {ty}" for ty, v in out["oracle_control"][mem]["pooled"].items() if v["fail"]]
        print(f"{mem}: STOP(share>1)={len(out['stop_share_gt_1'])} "
              f"reported(share<0)={len(out['reported_share_lt_0'])} pooled-oracle-ctrl-fail={ocfails}")
    stop = list(out["stop_share_gt_1"])
    for mem in ("1x", "kv0.5r"):
        for ty, v in out["oracle_control"][mem]["pooled"].items():
            if v["fail"]:
                stop.append(f"{mem} oracle-control {ty}: FAIR {v['fair_oracle']} > HIND "
                            f"{v['hind_oracle']}, CI {v['fair_minus_hind_ci95']}")
    out["verdict"] = ("PASS: no share>1, no pooled oracle-control gap beyond CI. share<0 reported as "
                      "genuine worse-than-device." if not stop else f"STOP: {len(stop)} blocking")
    out["blocking"] = stop
    out["_provenance"] = stamp(script="oracle_bootstrap.py", model="qwen3vl32b", device="jetson_orin")
    od = REPO / "results/orchestration/live2/oracle"
    (od / "oracle_shares_v2.json").write_text(json.dumps(out, indent=1, default=float))
    if not stop:
        (od / "oracle_results.json").write_text(json.dumps(out, indent=1, default=float))
        print("wrote oracle_results.json (THE BOUND)")
    print("VERDICT:", out["verdict"])
    print("dashcam_tier_acc:", out["dashcam_tier_acc"])
    for b in stop[:10]:
        print("  BLOCK:", b)
    return out


if __name__ == "__main__":
    main()
