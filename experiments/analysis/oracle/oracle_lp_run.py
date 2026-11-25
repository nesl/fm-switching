#!/usr/bin/env python3
"""StudyORACLE stage 4: assemble units and run the transportation LP at T and 1.10xT, per type and
pooled, FAIR and HINDSIGHT, for s4-s7 x {1x, kv0.5r} (CPU, read-only, no images; D240 separate).

Units (pre-reg): recall question, single-shot question, dashcam EPISODE. Each carries value (FAIR
gain acc_cloud-acc_device / HINDSIGHT gain [cloud right]-[device right]; dashcam from stage 2-live),
best-case warm work W_q, and a window [arrival, deadline - net]. The LP maximizes served gain under
one preemptible capacity T; oracle_total = device_floor + LP_opt. Step 2b records whether capacity
binds. No bound file is written here; stage 6 applies the positive control and STOP gate first.
"""
from __future__ import annotations
import json, os, sys, glob, collections, statistics
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
for p in ("experiments/orchestration/live2/fleet", "experiments/analysis/episodic",
          "experiments/analysis/oracle", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import trace as TR  # noqa: E402
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
from oracle_dashcam import Instant, Episode, max_over_subsets  # noqa: E402
from oracle_lp import Unit, solve_oracle_lp, greedy_edf  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
T_CAP = {"1x": 17945.2, "kv0.5r": 15569.8}
NET = 0.044 / 2.0
L = {"recall": 3.0, "single_shot": 2.0, "dashcam": 1.0}
EPG_TEXT, EPG_PF, DECODE = 42, 338, 2
D2_TOK, D2_HDR = 90, 31


def recall_correctness(seed, tag):
    out = {}
    pat = str(RUNS / f"*_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30")
    cells = sorted(glob.glob(pat) + glob.glob(pat + "_rerun"),
                   key=lambda c: (0 if "always-cloud-fcfs" in c else 1))
    for c in cells:
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
            cl = r.get("cloud_letter")
            cc = None if cl is None else bool(r.get("cloud_correct"))
            if oid not in out:
                out[oid] = [bool(r.get("device_correct")), cc]
            elif out[oid][1] is None and cc is not None:
                out[oid][1] = cc
    return out


def acc_cloud_device(seed, tag):
    for suf in ("_rerun", ""):
        p = RUNS / (f"covex-v6-fair-final_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf) / "cell.json"
        if p.exists():
            rh = ((json.load(open(p)).get("score") or {}).get("score") or {}).get("robot_headline") or {}
            return rh.get("cloud_accuracy_on_served"), rh.get("device_only_accuracy")
    return None, None


def simplestream_cloud(seed, tag):
    for suf in ("_rerun", ""):
        c = RUNS / (f"simplestream_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf)
        if (c / "outcomes.jsonl.gz").exists():
            return {o["opportunity_id"]: (o.get("cloud_payload") or {}).get("cloud_score")
                    for o in E.read_jsonl_gz(str(c / "outcomes.jsonl"))
                    if str(o.get("device_id", "")).startswith("dash")
                    and (o.get("cloud_payload") or {}).get("cloud_score") is not None}
    return {}


def dev_tier():
    te = DC.thresholds_episode(far=0.10)
    out = {}
    for tier, path in (("device", DC.DEV_4BI), ("cloud", DC.DEV_32BI)):
        dev = DC._load_dev_episodes(path); th = te[tier]
        pos = [v["max"] for v in dev.values() if v["label"] == "positive"]
        neg = [v["max"] for v in dev.values() if v["label"] == "negative"]
        out[tier] = {"theta": th, "tpr": sum(1 for m in pos if m >= th - 1e-12) / len(pos),
                     "tnr": sum(1 for m in neg if m < th - 1e-12) / len(neg)}
    return out, te["device"], te["cloud"]


def ss_box():
    return E.ss2_correctness()


def build_units(seed, tag, mem, rc, acc_c, acc_d, ssbox, cloud, tier, th_dev, th_cloud):
    recs = TR.generate_trace(seed=seed, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                             robot_question_set="lh_req", ss_question_set="ss2",
                             dashcam_format="epg", robot_upload="per-frame",
                             robot_reask_mean_s=30.0)["records"]
    units = {"recall": [], "single_shot": [], "dashcam": []}
    floor = {"recall": {"FAIR": 0.0, "HINDSIGHT": 0}, "single_shot": {"FAIR": 0.0, "HINDSIGHT": 0},
             "dashcam": {"FAIR": 0.0, "HINDSIGHT": 0}}
    vgap = acc_c - acc_d if (acc_c is not None and acc_d is not None) else 0.0
    # recall + single-shot warm W_q (incremental D2 frames per session)
    by_sess = collections.defaultdict(list)
    for r in recs:
        if r["kind"] == "recall_question":
            by_sess[r["session_id"]].append(r)
    for sid, qs in by_sess.items():
        qs.sort(key=lambda r: r["t"]); prev = 0
        for r in qs:
            nfr = int(round((int(r["history_tokens"]) - D2_HDR) / D2_TOK))
            is_rob = str(r["device_id"]).startswith("robo")
            a = r["t"]
            if is_rob:
                new = max(0, nfr - prev); hdr = D2_HDR if prev == 0 else 0
                W = D2_TOK * new + hdr + DECODE
                prev = max(prev, nfr)
                dc_cc = rc.get(r["opportunity_id"])
                if dc_cc is None:
                    continue
                dc, cc = dc_cc
                floor["recall"]["FAIR"] += acc_d; floor["recall"]["HINDSIGHT"] += int(dc)
                vF = vgap
                vH = (0.0 if cc is None else (int(cc) - int(dc)))
                units["recall"].append((Unit(r["opportunity_id"], vF, W, a, a + L["recall"] - NET),
                                        vF, vH))
            else:
                W = int(r["history_tokens"]) + DECODE
                v = ssbox.get(r.get("question_id"))
                if not v or "device" not in v or "cloud" not in v:
                    continue
                dc, cc = int(v["device"]), int(v["cloud"])
                floor["single_shot"]["FAIR"] += 0.073896; floor["single_shot"]["HINDSIGHT"] += dc
                units["single_shot"].append((Unit(r["opportunity_id"], 0.073896, W, a,
                                                   a + L["single_shot"] - NET), 0.073896, cc - dc))
    # dashcam episodes
    inst = [r for r in recs if r["kind"] == "monitor_opportunity"]
    by_ep = collections.defaultdict(list)
    for r in inst:
        by_ep[r["episode_id"]].append(r)
    labels = DC.nexar_labels()
    for eid, rows in by_ep.items():
        rows.sort(key=lambda r: float(r["t_local"]))
        clip = rows[0]["clip"]; meta = labels.get(clip) or {}
        ref = meta.get("ref"); is_pos = (meta.get("label") == "positive")
        is_crash = bool(is_pos and ref is not None and any(float(r["t_local"]) < ref for r in rows))
        insts = []; prev_ef = 0
        for r in rows:
            ef = int(r.get("episode_frames", 1)); new = max(1, ef - prev_ef) if prev_ef else ef
            prev_ef = ef
            work = EPG_PF * new + (EPG_TEXT if r is rows[0] else 0) + DECODE
            ds = r.get("device_score")
            ds = -1e9 if ds is None else ds           # None -> never crosses
            cs = cloud.get(r["opportunity_id"])
            cs = ds if cs is None else cs             # missing cloud -> device-only (conservative)
            insts.append((Instant(float(r["t_local"]), ds, cs, float(work)), r["t"]))
        ep = Episode(eid, [i for i, _ in insts], is_crash, ref, th_dev, th_cloud)
        mos = max_over_subsets(ep)
        a = min(t for _, t in insts); d = max(t for _, t in insts) + L["dashcam"] - NET
        # FAIR
        dacc = tier["device"]["tpr"] if is_crash else tier["device"]["tnr"]
        cacc = tier["cloud"]["tpr"] if is_crash else tier["cloud"]["tnr"]
        floor["dashcam"]["FAIR"] += dacc; floor["dashcam"]["HINDSIGHT"] += mos["v_dev"]
        gF = max(0.0, cacc - dacc)
        preW = [i.work for i, _ in insts if (ref is not None and i.pts < ref)]
        wF = min(preW) if preW else min(i.work for i, _ in insts)
        if gF > 1e-12:
            units["dashcam"].append((Unit(eid + "_F", gF, wF, a, d), gF, None))
        gH, wH = mos["gain"], mos["w"]
        if gH > 0:
            units["dashcam"].append((Unit(eid + "_H", gH, max(wH, 1.0), a, d), None, gH))
    return units, floor


def run_lp(units_list, T, which):
    """which: 'FAIR' or 'HINDSIGHT'. Build Unit list with that value, solve + greedy."""
    us = []
    for u, vF, vH in units_list:
        v = vF if which == "FAIR" else vH
        if v is None:
            continue
        us.append(Unit(u.uid, v, u.work, u.release, u.deadline))
    r = solve_oracle_lp(us, T)
    g = greedy_edf(us, T)
    return r, g


def main():
    tier, th_dev, th_cloud = dev_tier()
    ssbox = ss_box()
    results = {"1x": {}, "kv0.5r": {}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        T = T_CAP[mem]
        for s in SEEDS:
            rc = recall_correctness(s, tag)
            ac, ad = acc_cloud_device(s, tag)
            cloud = simplestream_cloud(s, tag)
            units, floor = build_units(s, tag, mem, rc, ac, ad, ssbox, cloud, tier, th_dev, th_cloud)
            cell = {"device_floor": floor, "n_units": {k: len(v) for k, v in units.items()}}
            for scale, Tc in (("T", T), ("1.10T", 1.10 * T)):
                cell[scale] = {}
                for which in ("FAIR", "HINDSIGHT"):
                    per = {}
                    pooled_units = []
                    for typ in ("recall", "single_shot", "dashcam"):
                        r, g = run_lp(units[typ], Tc, which)
                        per[typ] = {"lp_opt": r["lp_value"], "greedy": g,
                                    "capacity_binds": r["capacity_binds"],
                                    "floor": floor[typ][which],
                                    "oracle_total": (floor[typ][which] + r["lp_value"]
                                                     if r["lp_value"] is not None else None)}
                        pooled_units += units[typ]
                    rp, gp = run_lp(pooled_units, Tc, which)
                    pooled_floor = sum(floor[t][which] for t in ("recall", "single_shot", "dashcam"))
                    per["pooled"] = {"lp_opt": rp["lp_value"], "greedy": gp,
                                     "capacity_binds": rp["capacity_binds"], "floor": pooled_floor,
                                     "oracle_total": (pooled_floor + rp["lp_value"]
                                                      if rp["lp_value"] is not None else None)}
                    cell[scale][which] = per
            results[mem][f"s{s}"] = cell
            print(f"{mem} s{s}: units {cell['n_units']} | "
                  f"POOLED T FAIR lp={cell['T']['FAIR']['pooled']['lp_opt']} "
                  f"HIND lp={cell['T']['HINDSIGHT']['pooled']['lp_opt']} "
                  f"binds={cell['T']['HINDSIGHT']['pooled']['capacity_binds']}")
    out = {"_what": "StudyORACLE stage 4: transportation LP at T and 1.10xT, per type and pooled, "
                    "FAIR and HINDSIGHT, s4-s7 x {1x,kv0.5r} (D240 separate). oracle_total = "
                    "device_floor + lp_opt. Intermediate; bound written after stage 6 control+STOP.",
           "capacity_T": T_CAP, "net_s": NET, "results": results}
    out["_provenance"] = stamp(script="oracle_lp_run.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    (outdir / "oracle_lp_opt.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_lp_opt.json")
    return out


if __name__ == "__main__":
    main()
