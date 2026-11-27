#!/usr/bin/env python3
"""Per-seed placement for the revision-2 rule (D329), n20 _c3-11-2, all 14 robots, d 188. CPU, read-only, no cells.

usage: python3 -I network_placement_seed.py <seed>          (default 5)

Same rule as network_scenario_rev2.py, parameterised by seed: harmable counts are the committed no-outage control's
outcomes with within_L, inside [R, R + B_cap], R = t0 + 188, B_cap from the revision-1 background-adjusted burst at
capacity 7,860.2 tok/s with the control's own uncached rate as background. Starts t0 in 1 s steps with
t0 + 188 + B_cap <= 1200. Top 10 by harmable single-shot + follow-ups, then dashcam; t0 = median of the top 10;
token = _evid-t<tenths>.

Also reports the same ranking with the fixed window [R, R + 120 s] for the note (peer ruling), but the placement
token follows the revision-2 rule.
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

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 5
D = 188.0
CAP = 7860.2
N = 20
CONTROL = f"covex-v6-fair-final_n20_s{SEED}_1200s_h27_3t_c3-11-2_L3_epg_rq30"


def trace_index():
    recs = TR.generate_trace(seed=SEED, n_devices=N, ratio="3:11:2", run_s=1200.0, mode="A",
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


def ontime(ix, cell):
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
            dev = str(o.get("device_id", "")); oid = o["opportunity_id"]
            if dev.startswith("asst") and oid in ix["t_ss"]:
                out["ss"].append(ix["t_ss"][oid])
            elif dev.startswith("robo") and oid in ix["t_rob"]:
                out["rob"].append(ix["t_rob"][oid])
            elif dev.startswith("dash") and oid in ix["t_dash"]:
                out["dash"].append(ix["t_dash"][oid])
    return {k: sorted(v) for k, v in out.items()}


def cnt(s, a, b):
    return bisect.bisect_left(s, b) - bisect.bisect_left(s, a)


def main():
    cell = RUNS / CONTROL
    if not (cell / "cell.json").exists():
        raise SystemExit(f"control not present yet: {CONTROL} (lands with the H100 push)")
    cj = json.loads((cell / "cell.json").read_text())
    if not (cj.get("run_valid") and cj.get("digests_equal")):
        raise SystemExit(f"control not valid: {CONTROL}")
    bins = R1.uncached_bins(CONTROL)
    own = float(R1.windowed_best(bins, 30)["best_mean_tok_s"])
    ix = trace_index()
    on = ontime(ix, CONTROL)
    iss = {"ss": sorted(ix["t_ss"].values()), "rob": sorted(ix["t_rob"].values()),
           "dash": sorted(ix["t_dash"].values())}
    rows = []
    for t0 in np.arange(0.0, 1200.0, 1.0):
        t0 = float(t0)
        bl = NPC.backlog_window(ix, t0, D)
        tot = sum(bl.values())
        R = t0 + D
        B, bg = R1.burst_for_start(bins, tot, CAP, R)
        if not np.isfinite(B) or t0 + D + B > 1200.0:
            continue
        a, b = R, R + B
        rows.append({"t0": t0, "B_cap_s": B, "ss": cnt(on["ss"], a, b), "fu": cnt(on["rob"], a, b),
                     "dash": cnt(on["dash"], a, b), "issued_ss": cnt(iss["ss"], a, b),
                     "issued_fu": cnt(iss["rob"], a, b), "issued_dash": cnt(iss["dash"], a, b)})
    rank = sorted(rows, key=lambda r: (r["ss"] + r["fu"], r["dash"]), reverse=True)
    top = rank[:10]
    med = float(np.median([r["t0"] for r in top]))
    tok = f"_evid-t{int(round(med * 10))}"
    # fixed window [R, R+120] for the note (peer ruling): same ranking on counts in that window
    fixed = []
    for t0 in np.arange(0.0, 1200.0 - D - 120.0, 1.0):
        t0 = float(t0); R = t0 + D
        fixed.append({"t0": t0, "ss": cnt(on["ss"], R, R + 120), "fu": cnt(on["rob"], R, R + 120),
                      "dash": cnt(on["dash"], R, R + 120)})
    frank = sorted(fixed, key=lambda r: (r["ss"] + r["fu"], r["dash"]), reverse=True)[:10]
    out = {"seed": SEED, "control": CONTROL, "control_valid": True, "own_rate_tok_s": own, "capacity_tok_s": CAP,
           "accepted_starts": len(rows), "robots": len(ix["robots"]) if "robots" in ix else None,
           "top10": [{k: round(r[k], 2) for k in ("t0", "B_cap_s", "ss", "fu", "dash")} for r in top],
           "median_top10_t0": med, "token_revision2": tok,
           "fixed_window_120_top10_t0": sorted(r["t0"] for r in frank),
           "fixed_window_120_median_t0": float(np.median([r["t0"] for r in frank])),
           "control_ontime_rate_top10": {
               "ss": sum(r["ss"] for r in top) / max(sum(r["issued_ss"] for r in top), 1),
               "fu": sum(r["fu"] for r in top) / max(sum(r["issued_fu"] for r in top), 1),
               "dash": sum(r["dash"] for r in top) / max(sum(r["issued_dash"] for r in top), 1)}}
    dst = REPO / f"results/orchestration/live2/network_pressure/placement_seed{SEED}_n20.json"
    dst.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in ("seed", "own_rate_tok_s", "accepted_starts", "median_top10_t0",
                                          "token_revision2", "fixed_window_120_median_t0")}, indent=1))
    for r in top:
        print(f"  t0 {r['t0']:.0f} B_cap {r['B_cap_s']:.1f} ss {r['ss']} fu {r['fu']} dash {r['dash']}")


if __name__ == "__main__":
    main()
