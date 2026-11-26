#!/usr/bin/env python3
"""StudyORACLE for the half-GPU-plus-half-host condition (_kv0.5r_h0.5_L3_epg_rq30), offline.

Reuses the verified per-unit bound machinery (oracle_bootstrap: arm_units, dash_precompute,
dash_tier_acc, shares_block, oracle_control) with the h0.5 tag and its own simplestream dense cloud.
Does NOT write oracle_results.json. Output: results/orchestration/live2/oracle/oracle_h05_shares.json.

Capacity T for this condition is measured from its own cells (oracle_capacity_window.py): the max
1 s-window uncached prefill rate over the valid h0.5 cells, floored at 5600 tok/s. Recorded in the
output as capacity_T_h05; the per-unit shares here are capacity-UNCONSTRAINED (the LP at T is a
separate, open item; see output note).
"""
from __future__ import annotations
import json, sys, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
import oracle_bootstrap as OB  # noqa: E402
import oracle_lp_run as R  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
from _provenance import stamp  # noqa: E402

TAG, MEM = "_kv0.5r_h0.5", "h0.5"
SEEDS = [4]                       # s4 now; add 5-7 as cells land
CAPACITY_T_H05 = 11619.8          # max valid h0.5 cell (covex-v6-fair-final s4 _preD249), 1 s window @ 924 s


def main():
    labels = DC.nexar_labels()
    dash_by_seed = {s: OB.dash_precompute(s, R.simplestream_cloud(s, TAG), labels) for s in SEEDS}
    dta = OB.dash_tier_acc(dash_by_seed)
    out = {"_what": "StudyORACLE, half-GPU-plus-half-host condition (_kv0.5r_h0.5), offline. Same "
                    "per-unit bound method as oracle_results.json (D268 conditioned FAIR, dashcam "
                    "instant-threshold model). NOT the bound file. Capacity T measured from this "
                    "condition's cells: T_h0.5 = 11619.8 tok/s (see capacity_T_h05). Shares here are "
                    "capacity-UNCONSTRAINED per-unit oracle; the T-constrained LP is an open item. "
                    "covex-v6-fair-final h0.5 cell is the pre-D249 variant (_preD249) by necessity: "
                    "no post-D249 h0.5 cell exists. FAIR table is the D268 table pooled over 1x and "
                    "kv0.5r cells, applied identically to every arm here.",
           "condition": TAG, "seeds_done": SEEDS, "capacity_T_h05": CAPACITY_T_H05,
           "dashcam_tier_acc": {f"{t}|{k}": round(v, 6) for (t, k), v in dta.items()},
           "flagged_superseded": sorted(OB.FLAGGED), "stop_share_gt_1": [], "reported_share_lt_0": [],
           "per_seed": {}, "pooled_over_seeds": {}, "oracle_control": {}}
    pooled = collections.defaultdict(list)
    ctrl = []
    for s in SEEDS:
        rc = R.recall_correctness(s, TAG)
        cellout = {"arms": {}}
        ctrl_units = None
        for disp, raw in OB.ARMS:
            units = OB.arm_units(raw, s, TAG, rc, dash_by_seed[s], dta)
            if units is None:
                continue
            cellout["arms"][disp] = OB.shares_block(units, np.random.default_rng(OB.BSEED))
            pooled[disp].extend(units)
            if ctrl_units is None or len(units) > len(ctrl_units):
                ctrl_units = units
            for typ, blk in cellout["arms"][disp].items():
                for w in ("FAIR", "HINDSIGHT"):
                    sh = blk[w]["share"]
                    if sh is None:
                        continue
                    if sh > 1.0 + 1e-6:
                        out["stop_share_gt_1"].append(f"s{s} {disp} {typ} {w}: {sh}")
                    elif sh < -1e-6:
                        out["reported_share_lt_0"].append(f"s{s} {disp} {typ} {w}: {sh}")
        if ctrl_units:
            ctrl.extend(ctrl_units)
            out["oracle_control"][f"s{s}"] = OB.oracle_control(ctrl_units, np.random.default_rng(OB.BSEED))
        out["per_seed"][f"s{s}"] = cellout
    for disp in [a for a, _ in OB.ARMS]:
        if pooled.get(disp):
            out["pooled_over_seeds"][disp] = OB.shares_block(pooled[disp], np.random.default_rng(OB.BSEED))
    out["oracle_control"]["pooled"] = OB.oracle_control(ctrl, np.random.default_rng(OB.BSEED)) if ctrl else {}
    blocking = list(out["stop_share_gt_1"]) + [
        f"oracle-control {t}: FAIR {v['fair_oracle']} > HIND {v['hind_oracle']}, CI {v['fair_minus_hind_ci95']}"
        for t, v in out["oracle_control"].get("pooled", {}).items() if v["fail"]]
    out["blocking"] = blocking
    out["verdict"] = ("PASS: no share>1, no pooled oracle-control gap beyond CI (share<0 reported)"
                      if not blocking else f"STOP: {len(blocking)} blocking")
    out["_provenance"] = stamp(script="oracle_h05.py", model="qwen3vl32b", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/oracle_h05_shares.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("VERDICT:", out["verdict"], "| share<0 reported:", len(out["reported_share_lt_0"]))
    return out


if __name__ == "__main__":
    main()
