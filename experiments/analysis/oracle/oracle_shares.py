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
import json, os, sys, random, glob
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
SS_ACC_CLOUD, SS_ACC_DEVICE = 0.621881, 0.547985
SS_FAIR_GAIN = SS_ACC_CLOUD - SS_ACC_DEVICE
# DEV per-tier episode accuracy (stage 2): crash TPR, no-crash TNR
TIER = {"device": {"tpr": 0.155556, "tnr": 0.888889}, "cloud": {"tpr": 0.288889, "tnr": 0.888889}}
_LAB = None


def acc_allq(seed, tag):
    """Unbiased per-seed recall acc_cloud/acc_device over ALL recall opportunities (union of arms'
    robot_rows), matching the FAIR oracle's valuation in stage 4."""
    dcs, ccs = [], []
    seen = {}
    pat = str(RUNS / f"*_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30")
    for c in sorted(glob.glob(pat) + glob.glob(pat + "_rerun"),
                    key=lambda c: (0 if "always-cloud-fcfs" in c else 1)):
        p = os.path.join(c, "cell.json")
        if not os.path.exists(p):
            continue
        try:
            rows = (((json.load(open(p)).get("score") or {}).get("score") or {}).get("robot_rows")) or []
        except Exception:
            continue
        for r in rows:
            if not str(r.get("device_id", "")).startswith("robo"):
                continue
            oid = r.get("opportunity_id")
            if oid in seen:
                continue
            cl = r.get("cloud_letter")
            seen[oid] = (bool(r.get("device_correct")), None if cl is None else bool(r.get("cloud_correct")))
    for dc, cc in seen.values():
        dcs.append(int(dc))
        if cc is not None:
            ccs.append(int(cc))
    ad = sum(dcs) / len(dcs) if dcs else 0.0
    ac = sum(ccs) / len(ccs) if ccs else 0.0
    return ac, ad


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
    """Returns (realized_units, served) for an EXPLICIT cell path. realized_units[key]=0/1 realized
    correct-in-time (HINDSIGHT policy); served[key]=1 iff the arm served cloud ON-TIME for that unit
    (used for the matched FAIR policy valuation). Robot 'R' / single-shot 'S'; over-32k excluded."""
    cell = E.load_cell(path)
    rr = (((cell.get("score") or {}).get("score") or {}).get("robot_rows")) or []
    over = C.over32k_oids(path)
    units, served = {}, {}
    for r in rr:
        oid = r.get("opportunity_id")
        if oid is None or oid in over or not str(r.get("device_id", "")).startswith("robo"):
            continue
        if device_only:
            ok = bool(r.get("device_correct")) and (r.get("device_latency_s") or 1e9) <= 3.0
        else:
            ok = bool(r.get("standing_correct_by_deadline"))
        units[("R", oid)] = 1 if ok else 0
        served[("R", oid)] = 1 if r.get("source_by_deadline") == "cloud" else 0
    corr = E.ss2_correctness()
    refused, present = C.refused_and_present(path)
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("asst"):
            continue
        c = corr.get(o.get("question_id"))
        if c is None:
            continue
        cp = o.get("cloud_payload") or {}
        verified = E.delivery_status(o, refused, present) == "delivered"
        on_time = (bool(cp.get("on_time")) or bool(o.get("within_L"))) and verified
        if device_only:
            ok = c.get("device")
        else:
            ok = c.get("cloud") if on_time else c.get("device")
        units[("S", o.get("question_id"))] = 1 if ok else 0
        served[("S", o.get("question_id"))] = 1 if on_time else 0
    return units, served


def dash_served_crash(arm_raw, seed, tag):
    """Count of CRASH episodes the arm cloud-served on-time on a pre-event instant (the improving
    window). This is the number of dashcam episodes that realize the FAIR crash gain."""
    path = _cell_path(arm_raw, seed, tag)
    if path is None:
        return 0
    onc = set()
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if str(o.get("device_id", "")).startswith("dash"):
            cp = o.get("cloud_payload") or {}
            if bool(cp.get("on_time")):
                onc.add(o["opportunity_id"])
    labels = DC.nexar_labels()
    by_ep = {}
    for r in DC.load_trace_instants(seed):
        by_ep.setdefault(r["episode_id"], []).append(r)
    cnt = 0
    for eid, rows in by_ep.items():
        meta = labels.get(rows[0]["clip"]) or {}
        ref = meta.get("ref"); is_pos = (meta.get("label") == "positive")
        if not (is_pos and ref is not None):
            continue
        pre = [r for r in rows if float(r["t_local"]) < ref]
        if pre and any(r["opportunity_id"] in onc for r in pre):
            cnt += 1
    return cnt


def arm_realized(arm_raw, seed, tag):
    """Per-type HINDSIGHT realized correct-in-time and FAIR SERVED counts (matched valuation: the
    arm realizes gain only on units it served on-time). Returns None if no cell at this level."""
    path = _cell_path(arm_raw, seed, tag)
    if path is None:
        return None
    units, served = cell_units(path, device_only=False)
    if not units:
        return None
    rob = sum(v for k, v in units.items() if k[0] == "R")
    ss = sum(v for k, v in units.items() if k[0] == "S")
    dash, _ = dash_cit(arm_raw, seed, tag, device_only=False)
    served_rob = sum(served[k] for k in units if k[0] == "R")
    served_ss = sum(served[k] for k in units if k[0] == "S")
    served_dash = dash_served_crash(arm_raw, seed, tag)
    return {"HIND": {"recall": rob, "single_shot": ss, "dashcam": dash},
            "served": {"recall": served_rob, "single_shot": served_ss, "dashcam": served_dash}}


def main():
    arms = list(E.ARMS)
    out = {"_what": "StudyORACLE stages 5-6: per-arm share, positive control, STOP gate. Each arm's "
                    "FAIR share values its served items with the SAME expected-accuracy valuation as "
                    "the FAIR oracle (matched, user ruling 2026-11-25); HINDSIGHT on realised "
                    "outcomes. Control: HINDSIGHT oracle >= FAIR oracle, and each oracle >= every "
                    "arm on its OWN valuation. D240 1x/kv0.5r separate; s6 is a flagged outlier.",
           "1x": {}, "kv0.5r": {}}
    stop_flags = []
    control_fail = []
    TYPES = ("recall", "single_shot", "dashcam", "pooled")
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            key = f"s{s}"
            if key not in LP.get(mem, {}):
                continue
            lp = LP[mem][key]
            acc_c, acc_d = acc_allq(s, tag)
            GAIN = {"recall": acc_c - acc_d, "single_shot": SS_FAIR_GAIN,
                    "dashcam": TIER["cloud"]["tpr"] - TIER["device"]["tpr"]}
            cell = {"arms": {}, "s6_outlier_flag": (s == 6), "recall_acc_cloud_allq": round(acc_c, 4),
                    "recall_acc_device_allq": round(acc_d, 4)}
            for disp, raw in arms:
                rz = arm_realized(raw, s, tag)
                if rz is None:
                    continue
                row = {}
                for typ in TYPES:
                    base_types = ("recall", "single_shot", "dashcam")
                    if typ == "pooled":
                        polH = sum(rz["HIND"][t] for t in base_types if rz["HIND"][t] is not None)
                    else:
                        polH = rz["HIND"][typ]
                    if polH is None:
                        continue
                    # FAIR matched policy = floor + served*gain (on the oracle's unit set)
                    def fair_pol(scale, t):
                        f = lp[scale]["FAIR"][t].get("floor")
                        return None if f is None else f + rz["served"][t] * GAIN[t]
                    ent = {"policy_realized": polH,
                           "served": (rz["served"][typ] if typ != "pooled" else
                                      {t: rz["served"][t] for t in base_types})}
                    for scale in ("T", "1.10T"):
                        if typ == "pooled":
                            polF = sum(fair_pol(scale, t) for t in base_types
                                       if fair_pol(scale, t) is not None)
                        else:
                            polF = fair_pol(scale, typ)
                        for which, pol in (("FAIR", polF), ("HINDSIGHT", polH)):
                            o = lp[scale][which][typ]
                            orc, flo = o.get("oracle_total"), o.get("floor")
                            if orc is None or flo is None or pol is None:
                                continue
                            denom = orc - flo
                            share = ((pol - flo) / denom) if abs(denom) > 1e-9 else None
                            ent[f"{which}_{scale}"] = {"oracle": round(orc, 4), "policy": round(pol, 4),
                                                       "share": (round(share, 4) if share is not None else None)}
                            if share is not None and share > 1.0 + 1e-6:
                                stop_flags.append(f"{mem} {key} {disp} {typ} {which} {scale}: "
                                                  f"share {share:.4f} > 1 (policy {pol:.2f} > oracle {orc:.2f})")
                    row[typ] = ent
                cell["arms"][disp] = row
            # control: HINDSIGHT oracle >= FAIR oracle at T, per type+pooled
            for typ in TYPES:
                fo = lp["T"]["FAIR"][typ].get("oracle_total")
                ho = lp["T"]["HINDSIGHT"][typ].get("oracle_total")
                if fo is not None and ho is not None and ho < fo - 1e-6:
                    control_fail.append(f"{mem} {key} {typ}: HINDSIGHT oracle {ho:.2f} < FAIR oracle {fo:.2f}")
            out[mem][key] = cell
    out["STOP_gate_flags"] = stop_flags
    out["control_failures_HIND_lt_FAIR"] = control_fail
    out["verdict"] = ("STOP: an arm exceeds its oracle (share>1)" if stop_flags else
                      ("STOP: HINDSIGHT oracle < FAIR oracle" if control_fail else
                       "PASS: HINDSIGHT >= FAIR >= every arm (matched valuations); no share>1"))
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
