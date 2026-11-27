#!/usr/bin/env python3
"""Feasibility-aware oracle bound (B_feas), capacity-window bounds (B_cap), and per-cell infeasibility
counts. CPU, read-only, committed data. NO PLOTS. NEW outputs only (never the committed oracle files).

Units and conventions follow oracle_bootstrap.py (D268 FAIR valuation table oracle_fair_table.json,
over-32k exclusion canon.over32k_oids, clip-cluster bootstrap 2000 resamples seed 0).

Ideal bound (committed): every robot question has a cloud answer with history, on time; every
single-shot question has a cloud answer; no capacity, memory or deadline constraint.

B_feas (feasibility in isolation): a robot question is cloud-servable only if the best-case first
token (costs.recall_ttft_s at its context size, readiness GPU-WARM) + LINK_RTT + upload of the 1200 B
question text stays within the recall deadline L_rob = 3.0 s. A single-shot question is cloud-servable
only if its best committed cloud completion latency (min over committed cells at the same condition,
t_delivered - t_opportunity) is within the 2.0 s deadline; a question with no committed cloud latency
is left servable (unevaluated, so the bound stays an upper bound). Infeasible questions have oracle
value = device floor (no gain).

B_cap (capacity window): the trace-population LP and greedy from oracle_lp_run.build_units, with:
  - COLD charge: recall work = trace history_tokens + DECODE; single-shot work = history + DECODE.
  - greedy_edf at T = 3800 tok/s (committed cold rate at 28k, costs.COLD_PREFILL_TOK_S): a FEASIBLE
    schedule under the cold charge (lower bound on that problem's optimum).
  - solve_oracle_lp at T = 3800 under the cold charge (LP relaxation, upper bound on that problem).
  - solve_oracle_lp at T = 17945.2 (committed measured uncached peak, D230 (12)) under the WARM charge
    (warm uncached recall work), the cheapest charge: an upper bound on any schedule in the committed
    cost model.
"""
from __future__ import annotations
import json, math, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/oracle", "experiments/analysis/episodic", "experiments/analysis/canon",
          "experiments/lib", "experiments/orchestration/live2/fleet", "experiments/orchestration/baselines"):
    sys.path.insert(0, str(REPO / p))
import oracle_bootstrap as OB  # noqa: E402
import oracle_lp_run as LR  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
import episodic_lib as E  # noqa: E402
import canon as C  # noqa: E402
import trace as TR  # noqa: E402
import costs as CO  # noqa: E402
from _provenance import stamp  # noqa: E402
from oracle_lp import Unit  # noqa: E402

SEEDS = [4, 5, 6, 7]
NB, BSEED = 2000, 0
L_ROB = 3.0            # recall deadline (fleet deadline, oracle_lp_run L["recall"])
L_SS = 2.0             # single-shot deadline
RTT_S = 0.044          # LINK_RTT_S (v5/cf_ontime_d162.py:53); traces.RTT_MS = 44.0 (traces.py:42)
UPLINK_MBPS = 13.6     # traces.py:41
QUESTION_TEXT_B = 1200 # fleet/emulator.py:73
DECODE = LR.DECODE
T_COLD = CO.COLD_PREFILL_TOK_S[28000]   # 3800 tok/s, costs.py:81
T_UNC = LR.T_CAP["1x"]                  # 17945.2 tok/s, oracle_lp_run.py:30
ARMS = list(OB.ARMS)


def upload_s():
    return QUESTION_TEXT_B * 8.0 / (UPLINK_MBPS * 1e6)


def ttft_best(tokens):
    return CO.recall_ttft_s(int(tokens), "GPU-WARM")


def feasible_recall(tokens):
    return ttft_best(tokens) + RTT_S + upload_s() <= L_ROB + 1e-9


def reason_recall(tokens):
    cold = CO.recall_ttft_s(int(tokens), "COLD") + RTT_S + upload_s()
    best = ttft_best(tokens) + RTT_S + upload_s()
    return {"best_tier_s": round(best, 4), "cold_tier_s": round(cold, 4),
            "ok_best": best <= L_ROB + 1e-9, "ok_cold": cold <= L_ROB + 1e-9}


def ss_min_latency(seed, tag):
    """question_id -> min committed cloud completion latency over all committed arms (this condition)."""
    lat = {}
    for disp, raw in ARMS:
        path = OB._cell(raw, seed, tag)
        if path is None:
            continue
        refused, present = C.refused_and_present(path)
        for o in E.read_jsonl_gz(f"{path}/outcomes.jsonl"):
            if not str(o.get("device_id", "")).startswith("asst"):
                continue
            td, to = o.get("t_delivered"), o.get("t_opportunity")
            if td is None or to is None:
                continue
            q = o.get("question_id")
            v = float(td) - float(to)
            lat[q] = min(lat.get(q, math.inf), v)
    return lat


def cap_alpha(cap):
    """Capacity fraction alpha per type (and pooled) on the trace population, seeds 4-7, 1x.
    alpha = constrained value / uncapacitated value. Bracketed by a feasible greedy schedule (LB, cold
    charge at T_COLD) and an LP relaxation (UB): UB_cold (cold charge, T_COLD) and UB_warm (warm
    charge, T_UNC, the cheapest charge at the best measured rate). Population: 16-device trace, the same
    arrival-independent units the committed LP uses (oracle_lp_run.build_units)."""
    import oracle_lp_d270 as D70
    acc = {m: {"ideal": 0.0, "LB": 0.0, "UB_cold": 0.0, "UB_warm": 0.0} for m in ("FAIR", "HIND")}
    per = {}
    for s in SEEDS:
        units, floor = cap[s]["units"], cap[s]["floor"]
        units, floor = D70.revalue(units, floor)
        hist = cap[s]["hist"]
        cold = {}
        for typ in ("recall", "single_shot"):
            lst = []
            for (u, vF, vH) in units[typ]:
                w = (hist.get(u.uid, u.work) + DECODE) if typ == "recall" else u.work
                lst.append((Unit(u.uid, vF, w, u.release, u.deadline), vF, vH))
            cold[typ] = lst
        cold_all = cold["recall"] + cold["single_shot"]
        warm_all = units["recall"] + units["single_shot"]
        for which, key in (("FAIR", "FAIR"), ("HINDSIGHT", "HIND")):
            for typ_name, lists in (("recall", (cold["recall"], units["recall"])),
                                    ("single_shot", (cold["single_shot"], units["single_shot"])),
                                    ("pooled", (cold_all, warm_all))):
                cl, wl = lists
                ideal = sum(max(0.0, (x[1] if which == "FAIR" else x[2]) or 0.0) for x in wl)
                lb = LR.run_lp(cl, T_COLD, which)[1]
                ub_c = LR.run_lp(cl, T_COLD, which)[0]["lp_value"]
                ub_w = LR.run_lp(wl, T_UNC, which)[0]["lp_value"]
                per.setdefault(f"s{s}|{key}|{typ_name}", {"ideal": ideal, "LB": lb, "UB_cold": ub_c,
                                                         "UB_warm": ub_w})
    alpha = {}
    for key in ("FAIR", "HIND"):
        alpha[key] = {}
        for typ in ("recall", "single_shot", "pooled"):
            tot = collections.Counter()
            for s in SEEDS:
                v = per[f"s{s}|{key}|{typ}"]
                for k in ("ideal", "LB", "UB_cold", "UB_warm"):
                    tot[k] += float(v[k] or 0.0)
            if tot["ideal"] <= 0:
                continue
            alpha[key][typ] = {"alpha_LB": round(tot["LB"] / tot["ideal"], 6),
                                "alpha_UB_cold": round(tot["UB_cold"] / tot["ideal"], 6),
                                "alpha_UB_warm": round(tot["UB_warm"] / tot["ideal"], 6),
                                "ideal_value": round(tot["ideal"], 6), "greedy_LB_value": round(tot["LB"], 6),
                                "LP_UB_cold_value": round(tot["UB_cold"], 6),
                                "LP_UB_warm_value": round(tot["UB_warm"], 6)}
    return alpha, per


def main():
    out = {"_what": "Feasibility-aware bound (B_feas), capacity-window bounds (B_cap), infeasibility counts. "
                    "Cells: n16 1x s4-s7 and s4 _kv0.5r_h0.5. NEW output file only.",
           "constants": {"L_rob_s": L_ROB, "L_ss_s": L_SS, "rtt_s": RTT_S, "upload_s": upload_s(),
                         "question_text_B": QUESTION_TEXT_B, "decode_tokens": DECODE,
                         "T_cold_tok_s": T_COLD, "T_uncached_peak_tok_s": T_UNC,
                         "best_tier": "GPU-WARM", "cold_tier": "COLD"},
           "sources": {"recall_ttft": "experiments/orchestration/baselines/costs.py:106 recall_ttft_s",
                       "cold_prefill": "costs.py:81 COLD_PREFILL_TOK_S", "rtt": "v5/cf_ontime_d162.py:53",
                       "uplink": "traces.py:41 UPLINK_MBPS", "question_bytes": "fleet/emulator.py:73",
                       "T_uncached": "oracle_lp_run.py:30", "ss_latency": "outcomes t_delivered - t_opportunity"},
           "cells": {}}
    # --- per-seed population for the capacity LP (1x trace, arm-independent)
    cap = {}
    for s in SEEDS:
        rc = LR.recall_correctness(s, "")
        ac, ad = LR.acc_cloud_device(s, "")
        cloud = LR.simplestream_cloud(s, "")
        tier, th_dev, th_cloud = LR.dev_tier()
        recall_unc = LR.min_recall_uncached(s, "")
        units, floor = LR.build_units(s, "", "1x", rc, ac, ad, LR.ss_box(), cloud, tier, th_dev, th_cloud,
                                      recall_unc)
        recs = TR.generate_trace(seed=s, n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                                 robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                                 robot_upload="per-frame", robot_reask_mean_s=30.0)["records"]
        hist = {r["opportunity_id"]: int(r["history_tokens"]) for r in recs if r["kind"] == "recall_question"}
        cap[s] = {"units": units, "floor": floor, "hist": hist}
    # --- positive control and per-cell shares (ideal, B_feas), n16 1x and h0.5 s4
    cells_cfg = [("", "1x", SEEDS), ("_kv0.5r_h0.5", "h0.5", [4])]
    pooled_units = {"1x": collections.defaultdict(list), "h0.5": collections.defaultdict(list)}
    for tag, mem, seeds in cells_cfg:
        for s in seeds:
            lat = ss_min_latency(s, tag)
            for disp, raw in ARMS:
                path = OB._cell(raw, s, tag)
                if path is None:
                    continue
                rc = LR.recall_correctness(s, tag)
                pt = OB.req_pt(path)
                units = OB.arm_units(raw, s, tag, rc, {}, {})
                if units is None:
                    continue
                rob = [u for u in units if u[1] == "recall"]
                ss = [u for u in units if u[1] == "single_shot"]
                # feasibility by question: recall by its actual prompt (context sent), ss by min latency
                rows = {}
                for r in (((E.load_cell(path).get("score") or {}).get("score") or {}).get("robot_rows") or []):
                    if str(r.get("device_id", "")).startswith("robo") and r.get("opportunity_id") is not None:
                        rows.setdefault(r.get("question_id") or r["opportunity_id"], []).append(
                            pt.get(r["opportunity_id"], 0))
                feas_r = {q: all(feasible_recall(t) for t in ts if t) for q, ts in rows.items()}
                reasons = collections.Counter()
                for q, ts in rows.items():
                    for t in ts:
                        if not t:
                            continue
                        rs = reason_recall(t)
                        if not rs["ok_best"]:
                            reasons["best-tier TTFT + RTT + upload > 3 s"] += 1
                        if not rs["ok_cold"]:
                            reasons["cold-tier TTFT + RTT + upload > 3 s (sensitivity)"] += 1
                feas_s = {q: (lat.get(q, 0.0) <= L_SS + 1e-9) for q in {u[0] for u in ss}}
                unlat = sum(1 for q in feas_s if q not in lat)
                # build B_feas tuples
                def gate(u, ok):
                    return u if ok else (u[0], u[1], u[2], u[3], u[3], u[5], u[6], u[6])
                ideal = [u for u in rob + ss]
                feas = [gate(u, feas_r.get(u[0], True) if u[1] == "recall" else feas_s.get(u[0], True))
                        for u in ideal]
                key = f"{mem}|{disp}|s{s}"
                out["cells"].setdefault(key, {})["robot_n"] = len(rob)
                out["cells"][key]["ss_n"] = len(ss)
                out["cells"][key]["robot_infeasible_B_feas"] = sum(1 for q, ok in feas_r.items() if not ok)
                out["cells"][key]["robot_infeasible_reasons_rows"] = dict(reasons)
                out["cells"][key]["ss_infeasible_B_feas"] = sum(1 for q, ok in feas_s.items() if not ok)
                out["cells"][key]["ss_no_committed_latency"] = unlat
                pooled_units[mem][disp].append((ideal, feas))
    # --- shares and positive control
    shares = {}
    for mem in ("1x", "h0.5"):
        shares[mem] = {}
        for disp in pooled_units[mem]:
            ideal_all = [u for ideal, _ in pooled_units[mem][disp] for u in ideal]
            feas_all = [u for _, feas in pooled_units[mem][disp] for u in feas]
            row = {}
            for name, units in (("ideal", ideal_all), ("B_feas", feas_all)):
                for typ in ("recall", "single_shot", "pooled"):
                    uu = units if typ == "pooled" else [u for u in units if u[1] == typ]
                    if not uu:
                        continue
                    pf, lf, hf = OB.share_ci(uu, "F", np.random.default_rng(BSEED))
                    ph, lh, hh = OB.share_ci(uu, "H", np.random.default_rng(BSEED))
                    row.setdefault(name, {})[typ] = {"FAIR": [pf, lf, hf], "HIND": [ph, lh, hh]}
            shares[mem][disp] = row
    out["shares"] = shares
    alpha, per = cap_alpha(cap)
    out["capacity_alpha"] = alpha
    out["capacity_lp_per_seed"] = per
    # B_cap shares: share/alpha. alpha_UB gives the LOW end, alpha_LB gives the HIGH end.
    cap_shares = {}
    for disp, raw in ARMS:
        if disp not in shares["1x"]:
            continue
        ideal = shares["1x"][disp]["ideal"]
        row = {}
        for typ, nm in (("recall", "recall"), ("single_shot", "single_shot"), ("pooled", "pooled")):
            if typ not in ideal or nm not in alpha["FAIR"]:
                continue
            S = ideal[typ]["FAIR"][0]
            aU = alpha["FAIR"][nm]["alpha_UB_cold"]; aL = alpha["FAIR"][nm]["alpha_LB"]
            row[typ] = {"FAIR_low": S / aU if aU else None, "FAIR_high": S / aL if aL else None,
                        "alpha_UB_cold": aU, "alpha_LB": aL}
        cap_shares[disp] = row
    out["capacity_bound_shares_1x"] = cap_shares
    # positive control: ideal pooled FAIR for rung 3 at 1x must equal the committed 0.9438
    committed = json.load(open(REPO / "results/orchestration/live2/oracle/oracle_results.json"))
    cval = committed["pooled_over_seeds_robot_single_shot_1x"]["fair-final-rung3"]["FAIR"]["share"]
    mine = shares["1x"]["fair-final-rung3"]["ideal"]["pooled"]["FAIR"][0]
    out["positive_control"] = {"committed_rung3_1x_FAIR_robot_ss": cval, "recomputed_ideal": mine,
                               "reproduces": bool(abs(cval - mine) < 5e-4)}
    out["_provenance"] = stamp(script="oracle_feasible.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/oracle_feasible_bound.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("positive control:", out["positive_control"])


if __name__ == "__main__":
    main()
