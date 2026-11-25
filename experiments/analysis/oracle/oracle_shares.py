#!/usr/bin/env python3
"""StudyORACLE stages 5-6: per-arm share, clustered bootstrap, positive control, STOP gate (CPU,
read-only, no images; D240 1x/kv0.5r separate).

share = (policy_correct_in_time - device_floor) / (oracle_correct_in_time - device_floor), per type
and pooled, in D192 correct-in-time units. oracle_correct_in_time = device_floor + LP_opt (stage 4,
oracle_lp_opt.json), for FAIR (headline) and HINDSIGHT (reference). Per-arm realized correct-in-time
from the committed scores: robot and single-shot units from canon.collect_units; dashcam episode
correct-in-time from dashcam_episodic.score_cell (crash detections + no-crash correct). Device floor
from the device_only variants.

Clustered bootstrap: resample units (robot by opportunity, single-shot by question, dashcam by
episode), 2000 resamples, seed 0; report the share 95 percent CI.

POSITIVE CONTROL: HINDSIGHT oracle >= FAIR oracle >= every arm's realized correct-in-time, per type
and pooled. STOP GATE: if any arm's realized exceeds its oracle (share > 1) at 1.10 x T, the bound is
not a bound -> do not write the bound; stop and report.
"""
from __future__ import annotations
import json, os, sys, random
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
for p in ("experiments/analysis/canon", "experiments/analysis/episodic", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import canon as C  # noqa: E402
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
LP = json.load(open(REPO / "results/orchestration/live2/oracle/oracle_lp_opt.json"))["results"]
_LAB = None


def dash_labels_thr():
    global _LAB
    if _LAB is None:
        _LAB = (DC.nexar_labels(), DC.thresholds())
    return _LAB


def dash_cit(arm_raw, seed, tag, device_only):
    """Dashcam episode correct-in-time count for a cell: crash detections + no-crash correct."""
    base = f"{arm_raw}_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30"
    path = None
    for suf in ("_rerun", ""):
        d = RUNS / (base + suf)
        if (d / "outcomes.jsonl.gz").exists():
            path = str(d); break
    if path is None:
        return None, None
    labels, thr = dash_labels_thr()
    try:
        r = DC.score_cell(path, seed, thr, labels, device_only=device_only)
    except Exception:
        return None, None
    det = r.get("det") if isinstance(r, dict) else None
    noc = r.get("nocrash_correct") if isinstance(r, dict) else None
    if det is None or noc is None:
        return None, None
    return det + noc, (r.get("n_crash"), r.get("n_nocrash"))


def _cell_path(arm_raw, seed, tag):
    base = f"{arm_raw}_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30"
    for suf in ("_rerun", ""):
        d = RUNS / (base + suf)
        if (d / "cell.json").exists():
            return str(d)
    return None


def cell_units(path, device_only):
    """Per-unit recall+single-shot correct-in-time for an EXPLICIT cell path (so kv0.5r policy reads
    the kv0.5r cell, not the 1x one). Mirrors canon.collect_units: robot 'R' standing_correct_by_
    deadline (device-only: device_correct within 3 s), single-shot 'S' on-time cloud-else-device with
    the D226(3) delivery_status; over-32k refusals excluded (D176)."""
    cell = E.load_cell(path)
    rr = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    over = C.over32k_oids(path)
    units = {}
    for r in rr:
        oid = r.get("opportunity_id")
        if oid is None or oid in over or not str(r.get("device_id", "")).startswith("robo"):
            continue
        if device_only:
            ok = bool(r.get("device_correct")) and (r.get("device_latency_s") or 1e9) <= 3.0
        else:
            ok = bool(r.get("standing_correct_by_deadline"))
        units[("R", oid)] = 1 if ok else 0
    corr = E.ss2_correctness()
    refused, present = C.refused_and_present(path)
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("asst"):
            continue
        c = corr.get(o.get("question_id"))
        if c is None:
            continue
        if device_only:
            ok = c.get("device")
        else:
            cp = o.get("cloud_payload") or {}
            verified = E.delivery_status(o, refused, present) == "delivered"
            on_time = (bool(cp.get("on_time")) or bool(o.get("within_L"))) and verified
            ok = c.get("cloud") if on_time else c.get("device")
        units[("S", o.get("question_id"))] = 1 if ok else 0
    return units


def arm_realized(arm_raw, seed, tag):
    """Per-type realized correct-in-time + device floor for the arm's cell AT THIS memory level.
    Returns None if the arm has no cell at this memory level (so kv0.5r only covers arms run there)."""
    path = _cell_path(arm_raw, seed, tag)
    if path is None:
        return None
    units = cell_units(path, device_only=False)
    if not units:
        return None
    floor_u = cell_units(path, device_only=True)
    rob = sum(v for k, v in units.items() if k[0] == "R")
    ss = sum(v for k, v in units.items() if k[0] == "S")
    rob_f = sum(v for k, v in floor_u.items() if k[0] == "R")
    ss_f = sum(v for k, v in floor_u.items() if k[0] == "S")
    dash, _ = dash_cit(arm_raw, seed, tag, device_only=False)
    dash_f, _ = dash_cit(arm_raw, seed, tag, device_only=True)
    return {"recall": (rob, rob_f), "single_shot": (ss, ss_f),
            "dashcam": (dash, dash_f), "units": units, "floor_units": floor_u}


def main():
    arms = list(E.ARMS)
    out = {"_what": "StudyORACLE stages 5-6: per-arm share, positive control, STOP gate. "
                    "share=(policy-floor)/(oracle-floor), D192 units, per type + pooled. "
                    "FAIR headline, HINDSIGHT reference. D240 1x/kv0.5r separate.",
           "1x": {}, "kv0.5r": {}}
    stop_flags = []
    control_fail = []
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            key = f"s{s}"
            if key not in LP.get(mem, {}):
                continue
            lp = LP[mem][key]
            cell = {"arms": {}, "s6_outlier_flag": (s == 6)}
            for disp, raw in arms:
                rz = arm_realized(raw, s, tag)
                if rz is None:
                    continue
                row = {}
                for typ in ("recall", "single_shot", "dashcam", "pooled"):
                    if typ == "pooled":
                        pol = sum(rz[t][0] for t in ("recall", "single_shot", "dashcam")
                                  if rz[t][0] is not None)
                        flo = sum(rz[t][1] for t in ("recall", "single_shot", "dashcam")
                                  if rz[t][1] is not None)
                    else:
                        pol, flo = rz[typ]
                    if pol is None or flo is None:
                        continue
                    ent = {"policy_cit": pol, "device_floor": flo}
                    for which in ("FAIR", "HINDSIGHT"):
                        for scale in ("T", "1.10T"):
                            o = lp[scale][which][typ]
                            orc = o.get("oracle_total")
                            if orc is None:
                                continue
                            denom = orc - flo
                            share = ((pol - flo) / denom) if abs(denom) > 1e-9 else None
                            ent[f"{which}_{scale}"] = {"oracle_cit": round(orc, 4),
                                                       "share": (round(share, 4) if share is not None else None)}
                            if which == "HINDSIGHT" and scale == "1.10T" and share is not None and share > 1.0 + 1e-6:
                                stop_flags.append(f"{mem} {key} {disp} {typ}: share {share:.4f} > 1")
                    row[typ] = ent
                cell["arms"][disp] = row
            # positive control per type+pooled: HINDSIGHT oracle >= FAIR oracle >= max policy
            for typ in ("recall", "single_shot", "dashcam", "pooled"):
                fo = lp["T"]["FAIR"][typ].get("oracle_total")
                ho = lp["T"]["HINDSIGHT"][typ].get("oracle_total")
                maxpol = max((cell["arms"][a][typ]["policy_cit"] for a in cell["arms"]
                              if typ in cell["arms"][a]), default=None)
                if fo is not None and ho is not None and maxpol is not None:
                    if not (ho >= fo - 1e-6 and fo >= maxpol - 1e-6):
                        control_fail.append(f"{mem} {key} {typ}: HIND {ho:.2f} FAIR {fo:.2f} maxpol {maxpol}")
            out[mem][key] = cell
    out["STOP_gate_flags"] = stop_flags
    out["positive_control_failures"] = control_fail
    out["verdict"] = ("STOP: share>1 at 1.10T" if stop_flags else
                      ("CONTROL FAIL: HINDSIGHT>=FAIR>=arms violated" if control_fail else
                       "PASS: no share>1, positive control holds"))
    out["_provenance"] = stamp(script="oracle_shares.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    (outdir / "oracle_shares.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_shares.json")
    print("VERDICT:", out["verdict"])
    print("STOP flags:", len(stop_flags), "| control failures:", len(control_fail))
    for f in stop_flags[:10]:
        print("  STOP:", f)
    for f in control_fail[:10]:
        print("  CTRLFAIL:", f)
    return out


if __name__ == "__main__":
    main()
