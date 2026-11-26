#!/usr/bin/env python3
"""StudyORACLE provisional figure data and note (robot and single-shot scope), parameterised by the
policy arm. Freeze rerun: `python3 oracle_writeup.py --policy-arm <frozen-arm> --status FROZEN`.
Default policy arm: covex-v6-fair-final (rung 3). NO PLOTS: outputs are tables only.

Per arm (every paper baseline plus the policy arm, 1x seeds 4-7): FAIR and HINDSIGHT shares over robot
(recall) and single-shot units, pooled and per seed, with clip-cluster bootstrap CIs (2000, seed 0).
The s6 flag is carried on every per-seed row (recall device accuracy from 20 to 25 distinct questions).
Output: results/orchestration/live2/oracle/oracle_robot_ss_figdata.csv and .json; note in
reports/oracle_results_provisional.md.
"""
from __future__ import annotations
import argparse, csv, json, sys
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
import oracle_bootstrap as OB  # noqa: E402
import oracle_lp_run as R  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
# paper baselines (ruling set); confidence-cascade is flagged superseded (D205)
PAPER = {"base", "confidence-cascade", "llf", "mooncake", "eco-llm", "simplestream"}
OUT = REPO / "results/orchestration/live2/oracle"


def share_row(units, rng_seed=OB.BSEED):
    rf = np.random.default_rng(rng_seed)
    pf, lf, hf = OB.share_ci(units, "F", rf)
    rh = np.random.default_rng(rng_seed)
    ph, lh, hh = OB.share_ci(units, "H", rh)
    return {"FAIR": pf, "FAIR_lo": lf, "FAIR_hi": hf, "HIND": ph, "HIND_lo": lh, "HIND_hi": hh}


def role_of(disp, policy_disp):
    if disp == policy_disp:
        return "policy"
    return "paper baseline" if disp in PAPER else "other arm (ablation)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-arm", default="covex-v6-fair-final")
    ap.add_argument("--status", default="PROVISIONAL", choices=["PROVISIONAL", "FROZEN"])
    a = ap.parse_args()
    labels = DC.nexar_labels()
    dash_by = {s: OB.dash_precompute(s, R.simplestream_cloud(s, ""), labels) for s in SEEDS}
    dta = OB.dash_tier_acc(dash_by)
    by_seed = {}
    for s in SEEDS:
        rc = R.recall_correctness(s, "")
        by_seed[s] = {}
        for disp, raw in OB.ARMS:
            units = OB.arm_units(raw, s, "", rc, dash_by[s], dta)
            if units is None:
                continue
            by_seed[s][disp] = [u for u in units if u[1] in ("recall", "single_shot")]
    rows = []
    arms = sorted({d for s in by_seed for d in by_seed[s]})
    policy_disp = None
    for disp, raw in OB.ARMS:
        if raw == a.policy_arm:
            policy_disp = disp
    for disp in arms:
        pooled = [u for s in SEEDS for u in by_seed[s].get(disp, [])]
        role = role_of(disp, policy_disp)
        row = {"arm": disp, "role": role, "seeds": "4-7 pooled",
               "s6_flag": "s6 recall device acc from 20-25 questions (single-question basis)"}
        row.update(share_row(pooled))
        row["n_units"] = len(pooled)
        rows.append(row)
        for s in SEEDS:
            u = by_seed[s].get(disp, [])
            r = {"arm": disp, "role": role_of(disp, policy_disp), "seeds": f"s{s}",
                 "s6_flag": "yes" if s == 6 else "no"}
            r.update(share_row(u))
            r["n_units"] = len(u)
            rows.append(r)
    fields = ["arm", "role", "seeds", "n_units", "FAIR", "FAIR_lo", "FAIR_hi", "HIND", "HIND_lo", "HIND_hi", "s6_flag"]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "oracle_robot_ss_figdata.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    payload = {"status": a.status, "policy_arm": a.policy_arm, "policy_row": policy_disp,
               "scope": "robot (recall) and single-shot only; dashcam excluded (82f5d019, b84a9f1d)",
               "rows": rows, "_provenance": stamp(script="oracle_writeup.py", model="none", device="jetson_orin")}
    (OUT / "oracle_robot_ss_figdata.json").write_text(json.dumps(payload, indent=1, default=float))
    pol = next((r for r in rows if r["arm"] == policy_disp and r["seeds"] == "4-7 pooled"), None)
    best = max((r for r in rows if r["role"] == "paper baseline" and r["seeds"] == "4-7 pooled"),
               key=lambda r: r["FAIR"] or -9)
    note = [f"# StudyORACLE results, {a.status} (robot and single-shot scope)", "",
            f"**{a.status}: recomputed on the {'frozen' if a.status=='FROZEN' else 'current'} policy arm `{a.policy_arm}` "
            f"(row `{policy_disp}`).** 1x, seeds 4-7 pooled. Dashcam excluded (oracle share dropped, "
            "82f5d019). kv0.5r and h0.5 excluded (kv0.5r retired; h0.5 not in this block).", "",
            "| arm | role | FAIR share (95% CI) | HINDSIGHT share (95% CI) | units |",
            "|---|---|---|---|---|"]
    for r in rows:
        if r["seeds"] != "4-7 pooled":
            continue
        note.append(f"| {r['arm']} | {r['role']} | {r['FAIR']:.3f} ({r['FAIR_lo']:.3f}, {r['FAIR_hi']:.3f}) | "
                    f"{r['HIND']:.3f} ({r['HIND_lo']:.3f}, {r['HIND_hi']:.3f}) | {r['n_units']} |")
    note += ["", f"Policy arm `{policy_disp}` FAIR {pol['FAIR']:.3f}, best paper baseline by FAIR: `{best['arm']}` "
             f"{best['FAIR']:.3f}." if pol else "Policy arm not found in the arm list.", "",
             "Limits: s6 recall device accuracy rests on 20 to 25 distinct questions per seed (flagged in every "
             "per-seed row). Capacity T does not bind in value (oracle_lp_d270.json). The FAIR table is pooled "
             "over the 1x and kv0.5r cells (D268).", ""]
    (REPO / "reports/oracle_results_provisional.md").write_text("\n".join(note))
    print(f"{a.status}: policy {policy_disp} FAIR {pol['FAIR'] if pol else None} | "
          f"best baseline {best['arm']} {best['FAIR']:.3f}")


if __name__ == "__main__":
    main()
