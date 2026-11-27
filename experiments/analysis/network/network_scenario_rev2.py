#!/usr/bin/env python3
"""Network scenario design, revision 2 (D329). OFFLINE, CPU only, committed data, read-only, no cells.

HARMABLE DOSE per (fleet, t0): the queries that are ON TIME in the committed no-outage control inside the
post-reconnect burst window [R, R + B], R = t0 + 188. Burst B = revision 1 background-adjusted method with
CAPACITY = the saturated n32 30 s sustained rate (7,860.2 tok/s) and, for comparison, the fleet's own
demand-limited 30 s rate. Background = that fleet's committed rung 3 no-outage control over [R, R+B].

Fleets: n16 _c3-11-2 (11 robots; control = covex-v6-fair-final_n16 _c3-11-2 _preD249, the default 13.6 Mbps cell,
flagged pre-D249) and n20 _c3-11-2 (14 robots; control = covex-v6-fair-final_n20 _c3-11-2, plain; candidate
control (3) = covex-v6-fair-final-cand_n20 _c3-11-2 _qp). No committed n16 _c3-11-2 candidate exists.

B_obs calibration: from the committed group-A cell (rung 3 n32, outage k22 d188 at t0 529.5), the time after R at
which the outage cell's 10 s uncached prefill rate returns to within 10 % of the n32 control's rate at the same
seconds. Compared with the predicted B for the same placement.

Method check: the n32 control counts in [R, R + 60] at R = 529.5 + 188 are compared with the reported
single-shot 4/24 and dashcam 14/601 on time.
"""
from __future__ import annotations
import bisect, gzip, json, sys
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/network", "experiments/orchestration/live2/fleet",
          "experiments/orchestration/baselines", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import network_pressure_check as NPC  # noqa: E402
import network_pressure_rev1 as R1  # noqa: E402
import trace as TR  # noqa: E402
from _provenance import stamp  # noqa: E402

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
OUT = REPO / "results/orchestration/live2/network_pressure/network_pressure_check.json"
D = 188.0
C_CAP = 7860.2                     # n32 rung 3, 30 s best (revision 1), saturated capacity
HORIZON = 1200.0
FLEETS = {
    "n16": {"n": 16, "control": "covex-v6-fair-final_n16_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_preD249",
            "rate_own": "computed", "note": "control is the default 13.6 Mbps cell, pre-D249 (flagged)"},
    "n20": {"n": 20, "control": "covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30",
            "rate_own": "computed", "note": "control = committed plain rung 3 cell at 13.6 Mbps"},
}
N32_CONTROL = "covex-v6-fair-final_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30"
GROUP_A = "covex-v6-fair-final_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k22-d188_evid-t5295_link_sync"


def trace_index(n):
    recs = TR.generate_trace(seed=4, n_devices=n, ratio="3:11:2", run_s=1200.0, mode="A",
                             robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                             robot_upload="per-frame", robot_reask_mean_s=30.0)["records"]
    ix = NPC.index(recs)
    t_ss, t_rob, t_dash = {}, {}, {}
    for r in recs:
        if r["kind"] == "recall_question":
            if str(r["device_id"]).startswith("asst"):
                t_ss[r["opportunity_id"]] = float(r["t"])
            elif str(r["device_id"]).startswith("robo"):
                t_rob[r["opportunity_id"]] = float(r["t"])
        elif r["kind"] == "monitor_opportunity" and str(r["device_id"]).startswith("dash"):
            t_dash[r["opportunity_id"]] = float(r["t"])
    ix.update({"t_ss": t_ss, "t_rob": t_rob, "t_dash": t_dash})
    return ix


def control_events(cell):
    """on-time events of a committed cell: (type, time) with on_time flags, from the cell's own records."""
    cj = json.loads((RUNS / cell / "cell.json").read_text())
    sc = (cj.get("score") or {}).get("score") or {}
    return sc


def ontime_times(cell, ix):
    """on time = the committed outcome flag within_L (delivered within the deadline), for single-shot, robot
    and dashcam. Reproduces the reported control counts (single-shot 4/24, dashcam 14/601 in [R, R+60])."""
    p = RUNS / cell / "outcomes.jsonl.gz"
    op = gzip.open if p.exists() else open
    if not p.exists():
        p = RUNS / cell / "outcomes.jsonl"
    out = {"ss": [], "rob": [], "dash": []}
    with op(p, "rt") as f:
        for line in f:
            o = json.loads(line)
            if not o.get("within_L"):
                continue
            dev = str(o.get("device_id", ""))
            oid = o["opportunity_id"]
            if dev.startswith("asst") and oid in ix["t_ss"]:
                out["ss"].append(ix["t_ss"][oid])
            elif dev.startswith("robo") and oid in ix["t_rob"]:
                out["rob"].append(ix["t_rob"][oid])
            elif dev.startswith("dash") and oid in ix["t_dash"]:
                out["dash"].append(ix["t_dash"][oid])
    return {k: sorted(v) for k, v in out.items()}


def issued_times(ix):
    return {"ss": sorted(ix["t_ss"].values()), "rob": sorted(ix["t_rob"].values()),
            "dash": sorted(ix["t_dash"].values())}


def cnt(sorted_list, a, b):
    return bisect.bisect_left(sorted_list, b) - bisect.bisect_left(sorted_list, a)


def fleet_block(name, cfg, cap, own_rate):
    if own_rate == "computed":
        own_rate = float(R1.windowed_best(R1.uncached_bins(cfg["control"]), 30)["best_mean_tok_s"])
    ix = trace_index(cfg["n"])
    on = ontime_times(cfg["control"], ix)
    iss = issued_times(ix)
    bins_ctrl = R1.uncached_bins(cfg["control"])
    bl_ix = NPC.index(TR.generate_trace(seed=4, n_devices=cfg["n"], ratio="3:11:2", run_s=1200.0, mode="A",
                                        robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                                        robot_upload="per-frame", robot_reask_mean_s=30.0)["records"])
    rows = []
    for t0 in np.arange(0.0, HORIZON, 1.0):
        t0 = float(t0)
        bl = NPC.backlog_window(bl_ix, t0, D)
        total = sum(bl.values())
        R = t0 + D
        B_cap, bg = R1.burst_for_start(bins_ctrl, total, cap, R)
        if not np.isfinite(B_cap) or t0 + D + B_cap > HORIZON:
            continue
        B_own = None
        if own_rate:
            B_own, _ = R1.burst_for_start(bins_ctrl, total, own_rate, R)
        a, b = R, R + B_cap
        hs = cnt(on["ss"], a, b); hf = cnt(on["rob"], a, b); hd = cnt(on["dash"], a, b)
        rows.append({"t0": t0, "B_cap_s": B_cap, "B_own_s": B_own, "background_tok_s": bg,
                     "harm_ss": hs, "harm_fu": hf, "harm_dash": hd,
                     "issued_ss": cnt(iss["ss"], a, b), "issued_fu": cnt(iss["rob"], a, b),
                     "issued_dash": cnt(iss["dash"], a, b),
                     "relief_ontime_ss": cnt(on["ss"], t0, R), "relief_ontime_fu": cnt(on["rob"], t0, R),
                     "relief_ontime_dash": cnt(on["dash"], t0, R)})
    ranked = sorted(rows, key=lambda r: (r["harm_ss"] + r["harm_fu"], r["harm_dash"]), reverse=True)
    top = ranked[:10]
    med = float(np.median([r["t0"] for r in top]))
    # exact row at the (possibly half-second) median, same rules as the grid
    bl_m = NPC.backlog_window(bl_ix, med, D)
    tot_m = sum(bl_m.values())
    B_m, _ = R1.burst_for_start(bins_ctrl, tot_m, cap, med + D)
    a_m, b_m = med + D, med + D + B_m
    rel_at_med = {"t0": med, "B_cap_s": B_m, "harm_ss": cnt(on["ss"], a_m, b_m), "harm_fu": cnt(on["rob"], a_m, b_m),
                  "harm_dash": cnt(on["dash"], a_m, b_m), "issued_ss": cnt(iss["ss"], a_m, b_m),
                  "issued_fu": cnt(iss["rob"], a_m, b_m), "issued_dash": cnt(iss["dash"], a_m, b_m),
                  "relief_ontime_ss": cnt(on["ss"], med, a_m), "relief_ontime_fu": cnt(on["rob"], med, a_m),
                  "relief_ontime_dash": cnt(on["dash"], med, a_m)}
    return {"fleet": name, "n_devices": cfg["n"], "robots": len(bl_ix["robots"]), "control": cfg["control"],
            "note": cfg["note"], "accepted_starts": len(rows), "capacity_tok_s": cap,
            "own_rate_tok_s": own_rate, "top10": [{k: r[k] for k in ("t0", "B_cap_s", "B_own_s", "harm_ss",
                                                                       "harm_fu", "harm_dash")} for r in top],
            "proposed_t0": med, "proposed_token": f"_evid-t{int(round(med * 10))}",
            "outage_cell_line_rung3": f"covex-v6-fair-final_{name} {cfg['n']} 4 _c3-11-2_L3_epg_rq30_out-k{len(bl_ix['robots'])}-d188_evid-t{int(round(med * 10))}_link_sync",
            "per_start_stats": {k: R1.stat([r[k] for r in rows]) for k in
                                ("B_cap_s", "B_own_s", "harm_ss", "harm_fu", "harm_dash")},
            "at_proposed_t0": rel_at_med,
            "control_on_time_rate_in_burst_at_proposed": {
                "single_shot": (rel_at_med["harm_ss"] / rel_at_med["issued_ss"]) if rel_at_med["issued_ss"] else None,
                "robot_followup": (rel_at_med["harm_fu"] / rel_at_med["issued_fu"]) if rel_at_med["issued_fu"] else None,
                "dashcam": (rel_at_med["harm_dash"] / rel_at_med["issued_dash"]) if rel_at_med["issued_dash"] else None},
            "design_guide_met_at_proposed": bool(rel_at_med["harm_ss"] + rel_at_med["harm_fu"] >= 10
                                                 and rel_at_med["harm_dash"] >= 100)}


def method_check():
    """Reproduce the reported n32 control counts in [R, R+60] at R = 529.5 + 188."""
    ix = trace_index(32)
    on = ontime_times(N32_CONTROL, ix)
    R = 529.5 + D
    return {"R": R, "window_s": 60.0,
            "single_shot_on_time": cnt(on["ss"], R, R + 60), "single_shot_issued": cnt(issued_times(ix)["ss"], R, R + 60),
            "dash_on_time": cnt(on["dash"], R, R + 60), "dash_issued": cnt(issued_times(ix)["dash"], R, R + 60),
            "reported_by_user": {"single_shot": "4/24", "dash": "14/601"}}


def b_obs():
    """Group A outage cell. B_obs = the first start b >= 0 after R from which EVERY 30 s window (up to 300 s) has the
    outage cell's uncached mean <= 1.10 x the n32 control's mean. Sustained, so a single quiet window cannot end it."""
    bo = R1.uncached_bins(GROUP_A)
    bc = R1.uncached_bins(N32_CONTROL)
    R = 529.5 + D
    def wmean(x, a):
        return float(x[int(a):int(a) + 30].mean())
    ok = []
    for b in range(0, 300):
        ok.append(wmean(bo, R + b) <= 1.10 * wmean(bc, R + b) + 1e-9)
    found = None
    for b in range(0, 270):
        if all(ok[b:]):
            found = float(b)
            break
    bl_ix = NPC.index(TR.generate_trace(seed=4, n_devices=32, ratio="3:11:2", run_s=1200.0, mode="A",
                                        robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                                        robot_upload="per-frame", robot_reask_mean_s=30.0)["records"])
    bl = NPC.backlog_window(bl_ix, 529.5, D)
    total = sum(bl.values())
    Bc, _ = R1.burst_for_start(bc, total, C_CAP, R)
    Bo, _ = R1.burst_for_start(bc, total, 7860.2, R)
    return {"R": R, "B_obs_s": found, "predicted_B_cap_s": Bc, "predicted_B_design_s": Bo,
            "backlog_total_tokens": total,
            "cumulative_excess_uncached_tokens_300s": float((bo[int(R):int(R) + 300] - bc[int(R):int(R) + 300]).sum()),
            "rule": "first b >= 0 from which every 30 s window has outage-cell uncached mean <= 1.10 x n32 control mean"}


def main():
    cap = C_CAP
    out = {"_what": "Network scenario design revision 2 (D329): harmable dose at capacity B; design guide only.",
           "capacity_tok_s": cap, "fleets": {}}
    for name, cfg in FLEETS.items():
        out["fleets"][name] = fleet_block(name, cfg, cap, cfg["rate_own"])
    out["method_check_n32_control"] = method_check()
    out["b_obs_group_A"] = b_obs()
    out["_provenance"] = stamp(script="network_scenario_rev2.py", model="none", device="jetson_orin")
    doc = json.loads(OUT.read_text())
    doc["revision_2"] = out
    OUT.write_text(json.dumps(doc, indent=1, default=float))
    print(json.dumps(out["method_check_n32_control"]))
    print(json.dumps(out["b_obs_group_A"]))
    for name, f in out["fleets"].items():
        print(name, "accepted", f["accepted_starts"], "top10 median t0", f["proposed_t0"], f["proposed_token"],
              "harm_ss med", f["per_start_stats"]["harm_ss"]["median"], "fu", f["per_start_stats"]["harm_fu"]["median"],
              "dash med", f["per_start_stats"]["harm_dash"]["median"], "B_cap med", round(f["per_start_stats"]["B_cap_s"]["median"], 2))


if __name__ == "__main__":
    main()
