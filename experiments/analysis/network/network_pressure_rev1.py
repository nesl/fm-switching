#!/usr/bin/env python3
"""Network scenario design, revision 1 (D325). OFFLINE, CPU only, committed code and data, read-only, no cells.

Adds revision-1 keys to results/orchestration/live2/network_pressure/network_pressure_check.json. The original
keys (conditions C1, C2, C3 with the 16-device... trace burst rules, FAST and SLOW) are left as they are.

1. Measured sustained uncached prefill throughput per committed cell: each request's uncached tokens
   (prompt_tokens - cached_tokens) spread uniformly over [t_submit, t_first_token] and binned per second;
   best 1 s, 10 s and 30 s windowed mean.  Design rate = the 30 s best of the same fleet size's rung 3 cell.
   Background-adjusted burst: effective rate = design rate - mean uncached rate of the same fleet's committed
   no-outage rung 3 cell over [R, R + B] (fixed point in B).
2. Exposure inside [R, R + B]: single-shot, robot follow-ups and dashcam frames, each separately.
3. Conditions C2 (n32, 22 robots, d 188) primary, C1 (n20, 14 robots, d 188). C3 dropped (57 over-32k per start).
4. Rebuild share: host tier 27 GiB at 262,144 B per token = 110,592 tokens (costs.py:90, h27). Backlog tokens
   above that cannot stay resident (upper bound, assuming the host tier is free for the backlog). They are
   rebuilt cold at the committed nearest-size rate (costs.recall_ttft_s COLD); the extra seconds are added to B.
5. Placement: rank starts by exposure (single-shot + robot follow-ups, then dashcam); t0 = median of the top 10.
   This maximises dose by construction.
6. Control validity: candidate cells carry _qp (question priority) and are not outage-paired; link and sync
   tokens are refused without an outage (driver lines 318-338), so a paired control drops the outage tokens only.
"""
from __future__ import annotations
import gzip, json, sys, bisect
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/network", "experiments/orchestration/live2/fleet",
          "experiments/orchestration/baselines", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import network_pressure_check as NPC  # noqa: E402  (committed original rules; import has no side effects)
import costs as CO  # noqa: E402
from _provenance import stamp  # noqa: E402

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
OUT = REPO / "results/orchestration/live2/network_pressure/network_pressure_check.json"
HOST_TIER_GIB = 27.0
TOK_PER_HOST = HOST_TIER_GIB * 1024 ** 3 / NPC.KV_BYTES_PER_TOKEN      # 110,592
D = 188.0
CELL = {
    "n16_rung3": "covex-v6-fair-final_n16_s4_1200s_h27_3t_L3_epg_rq30",
    "n16_always_cloud": "always-cloud-fcfs_n16_s4_1200s_h27_3t_L3_epg_rq30",
    "n16_la-er-cu_outage": "covex-v6-fair-final-la-er-cu_n16_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_out-k11-d188_evid-t5355_link_up2.219_qp",
    "n20_rung3": "covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30",
    "n20_cand_qp": "covex-v6-fair-final-cand_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp",
    "n32_rung3": "covex-v6-fair-final_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30",
    "n32_cand_qp": "covex-v6-fair-final-cand_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30_qp",
}
TIME_HORIZON = 1200


def uncached_bins(cell_name):
    """per-second uncached prefill tokens: each request spread uniformly over [t_submit, t_first_token]."""
    p = RUNS / cell_name / "request.jsonl.gz"
    bins = np.zeros(TIME_HORIZON + 60)
    with gzip.open(p, "rt") as f:
        for line in f:
            r = json.loads(line)
            ts, tf = r.get("t_submit"), r.get("t_first_token")
            pt, ct = r.get("prompt_tokens"), r.get("cached_tokens") or 0
            if ts is None or tf is None or pt is None:
                continue
            unc = max(0, int(pt) - int(ct))
            if unc <= 0:
                continue
            if tf - ts <= 1e-9:
                bins[min(int(ts), len(bins) - 1)] += unc
                continue
            rate = unc / (tf - ts)
            t = float(ts)
            while t < tf:
                w = int(t)
                seg = min(float(tf), w + 1.0) - t
                if w < len(bins):
                    bins[w] += rate * seg
                t = w + 1.0
    return bins


def windowed_best(bins, w):
    cs = np.concatenate([[0.0], np.cumsum(bins)])
    m = (cs[w:] - cs[:-w]) / w
    i = int(np.argmax(m))
    return {"best_mean_tok_s": round(float(m[i]), 1), "window_start_s": i, "window_s": w}


def window_mean(bins, a, b):
    a, b = int(np.floor(a)), int(np.ceil(b))
    return float(bins[a:b].sum() / max(b - a, 1))


def throughput_table():
    out = {}
    for key, cell in CELL.items():
        if key == "n16_la-er-cu_outage":
            continue
        bins = uncached_bins(cell)
        out[key] = {"cell": cell, "1s": windowed_best(bins, 1), "10s": windowed_best(bins, 10),
                    "30s": windowed_best(bins, 30)}
    lb = uncached_bins(CELL["n16_la-er-cu_outage"])
    out["n16_la-er-cu_outage"] = {"cell": CELL["n16_la-er-cu_outage"],
                                  "mean_uncached_tok_s_in_723.5_753.5": round(window_mean(lb, 723.5, 753.5), 1),
                                  "30s_best": windowed_best(lb, 30)}
    return out


def burst_for_start(bins_bg, backlog, Rd, R):
    """background-adjusted burst: effective rate = Rd - mean background over [R, R+B]; fixed point in B."""
    if backlog <= 0:
        return 0.0, 0.0
    B = backlog / Rd
    for _ in range(50):
        bg = window_mean(bins_bg, R, R + B) if B > 0 else 0.0
        Reff = Rd - bg
        if Reff <= 1e-9:
            return float("inf"), bg
        Bn = backlog / Reff
        if abs(Bn - B) < 1e-3:
            return Bn, bg
        B = Bn
    return B, bg


def stat(vals):
    v = np.array(vals, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return None
    return {"median": float(np.median(v)), "p10": float(np.percentile(v, 10)),
            "p90": float(np.percentile(v, 90)), "n": int(v.size)}


def condition(n, d, Rd, bins_bg, label):
    recs = NPC.trace_for(n)
    ix = NPC.index(recs)
    starts = []
    for t0 in np.arange(0.0, TIME_HORIZON, 1.0):
        t0 = float(t0)
        bl = NPC.backlog_window(ix, t0, d)
        total = sum(bl.values())
        R = t0 + d
        B_design = total / Rd if Rd > 0 else float("inf")
        B_adj, bg = burst_for_start(bins_bg, total, Rd, R)
        if not np.isfinite(B_adj) or t0 + d + B_adj > TIME_HORIZON:
            continue
        sq = NPC.count(ix["rq_asst"], R, R + B_adj)
        fu = NPC.count(ix["rq_robo_t"], R, R + B_adj)
        dsh = NPC.count(ix["dash"], R, R + B_adj)
        # rebuild share: backlog above the host tier cannot stay resident (upper bound)
        excess = max(0.0, total - TOK_PER_HOST)
        if total > 0:
            extra = 0.0
            for dev, v in bl.items():
                nonres = excess * v / total
                extra += NPC.cold_time(nonres)
        else:
            extra = 0.0
        starts.append({"t0": t0, "backlog_total": total, "B_design_s": B_design, "B_adj_s": B_adj,
                       "background_tok_s": bg, "single_shot": sq, "robot_followups": fu, "dash_frames": dsh,
                       "sq_plus_fu": sq + fu, "excess_over_host_tier_tokens": excess,
                       "rebuild_extra_s": extra})
    res = {"label": label, "n_devices": n, "d_s": d, "design_rate_tok_s": Rd,
           "accepted_starts": len(starts),
           "burst_design_B_s": stat([s["B_design_s"] for s in starts]),
           "burst_bg_adjusted_B_s": stat([s["B_adj_s"] for s in starts]),
           "background_mean_tok_s": stat([s["background_tok_s"] for s in starts]),
           "exposed_single_shot": stat([s["single_shot"] for s in starts]),
           "exposed_robot_followups": stat([s["robot_followups"] for s in starts]),
           "exposed_dash_frames": stat([s["dash_frames"] for s in starts]),
           "exposed_sq_plus_fu": stat([s["sq_plus_fu"] for s in starts]),
           "backlog_total_tokens": stat([s["backlog_total"] for s in starts]),
           "excess_over_host_tier_tokens": stat([s["excess_over_host_tier_tokens"] for s in starts]),
           "rebuild_extra_burst_s": stat([s["rebuild_extra_s"] for s in starts])}
    ranked = sorted(starts, key=lambda s: (s["sq_plus_fu"], s["dash_frames"]), reverse=True)[:10]
    t_top = [s["t0"] for s in ranked]
    med_t0 = float(np.median(t_top)) if t_top else None
    res["top10_starts"] = [{"t0": s["t0"], "sq_plus_fu": s["sq_plus_fu"], "dash": s["dash_frames"]}
                           for s in ranked]
    res["proposed_t0"] = med_t0
    res["proposed_token"] = f"_evid-t{int(round(med_t0 * 10))}" if med_t0 is not None else None
    res["bar_design_pass"] = bool(res["exposed_sq_plus_fu"] and res["exposed_sq_plus_fu"]["median"] >= 15
                                  and res["burst_bg_adjusted_B_s"] and res["burst_bg_adjusted_B_s"]["median"] >= 4.0)
    return res


def main():
    tp = throughput_table()
    rate32 = tp["n32_rung3"]["30s"]["best_mean_tok_s"]
    rate20 = tp["n20_rung3"]["30s"]["best_mean_tok_s"]
    bg32 = uncached_bins(CELL["n32_rung3"])
    bg20 = uncached_bins(CELL["n20_rung3"])
    c2 = condition(32, D, rate32, bg32, "C2 n32 all 22 robots d188 (primary)")
    c1 = condition(20, D, rate20, bg20, "C1 n20 all 14 robots d188")
    controls = {
        "paired_control_C2": "covex-v6-fair-final_n32_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30",
        "paired_control_C1": "covex-v6-fair-final_n20_s4_1200s_h27_3t_c3-11-2_L3_epg_rq30",
        "candidate_3_n20": CELL["n20_cand_qp"], "candidate_4_n32": CELL["n32_cand_qp"],
        "candidate_3_4_valid_paired_controls": False,
        "reason": ("each candidate carries _qp (question priority on the uplink queue, driver v45), which changes "
                   "the arm's queue order with no outage; the driver refuses _link and _sync without an outage "
                   "(driver lines 318-338), so the paired control is the plain cell at the same n with the outage "
                   "tokens removed"),
        "C2_outage_cell_line": "covex-v6-fair-final_n32 32 4 _c3-11-2_L3_epg_rq30_out-k22-d188_evid-tTBD_link_sync",
        "C1_outage_cell_line": "covex-v6-fair-final_n20 20 4 _c3-11-2_L3_epg_rq30_out-k14-d188_evid-tTBD_link_sync",
    }
    rev = {"_what": "Network scenario design revision 1 (D325). Design only: no cells. Burst from the measured "
                    "30 s throughput; background-adjusted burst; exposure by type; rebuild share; placement by "
                    "exposure ranking (maximises dose by construction).",
           "host_tier_tokens": TOK_PER_HOST, "throughput": tp,
           "design_rate_tok_s": {"n32_30s_best_rung3": rate32, "n20_30s_best_rung3": rate20},
           "C2": c2, "C1": c1, "controls": controls,
           "_provenance": stamp(script="network_pressure_rev1.py", model="none", device="jetson_orin")}
    doc = json.loads(OUT.read_text())
    doc["revision_1"] = rev
    OUT.write_text(json.dumps(doc, indent=1, default=float))
    print("design rates", rate32, rate20)
    for c in (c2, c1):
        print(c["label"], "accepted", c["accepted_starts"], "sq+fu med", c["exposed_sq_plus_fu"]["median"],
              "B_adj med", round(c["burst_bg_adjusted_B_s"]["median"], 2), "bar", c["bar_design_pass"],
              "t0", c["proposed_t0"], c["proposed_token"])


if __name__ == "__main__":
    main()
