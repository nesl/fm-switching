#!/usr/bin/env python3
"""Generalise oracle_feasible.py to a cell's device count and tag (n20, n32, and B2 arms at n16 s4).

usage: python3 -I oracle_feasible_pop.py N TAG SEEDS      e.g.  20 _c3-11-2 4   |  16 "" 4
CPU, read-only, committed data. NO PLOTS. NEW output file only:
  results/orchestration/live2/oracle/oracle_feasible_pop_n{N}{tag}.json

Why source substitution: oracle_bootstrap.py, oracle_lp_run.py and the trace call hard-code the cell
pattern "_n16_s" and n_devices=16. For a cell at N devices both are replaced in the module SOURCE and
the module is executed under its own namespace, so the n16 committed modules are not modified. The
feasibility definitions (B_feas, B_cap, positive reference) are those of oracle_feasible.py.
"""
from __future__ import annotations
import glob, json, math, os, sys, types, collections
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/oracle", "experiments/analysis/episodic", "experiments/analysis/canon",
          "experiments/lib", "experiments/orchestration/live2/fleet", "experiments/orchestration/baselines"):
    sys.path.insert(0, str(REPO / p))
import episodic_lib as E  # noqa: E402
import canon as C  # noqa: E402
import oracle_feasible as OF  # noqa: E402  (feasibility rules, cap_alpha; import has no side effects)
from _provenance import stamp  # noqa: E402

RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
N = int(sys.argv[1]); TAG = sys.argv[2]; SEEDS = [int(x) for x in sys.argv[3].split(",")]
RATIO = "3:11:2" if TAG == "_c3-11-2" else "40:40:20"   # tag c3-11-2 = device mix 3:11:2 (run_meta.ratio)
OD = REPO / "experiments/analysis/oracle"


def load_mod(name, fname, subs, prelude=None):
    src = open(OD / fname).read()
    for name_, a, b in subs:
        n = src.count(a)
        if n < 1:
            raise SystemExit(f"substitution pattern {name_!r} matched 0 times in {fname}: {a!r}")
        print(f"substitution {name_!r} in {fname}: {n} match(es)", file=sys.stderr)
        src = src.replace(a, b)
    mod = types.ModuleType(name)
    mod.__file__ = str(OD / fname)
    if prelude:
        mod.__dict__.update(prelude)
    exec(compile(src, str(OD / fname), "exec"), mod.__dict__)
    return mod


LRN = load_mod("LRN", "oracle_lp_run.py", [("cell-pattern", "_n16_s", f"_n{N}_s"), ("trace-devices", "n_devices=16", f"n_devices={N}"), ("trace-mix", 'ratio="40:40:20"', f'ratio="{RATIO}"')])
OBN = load_mod("OBN", "oracle_bootstrap.py", [("cell-pattern", "_n16_s", f"_n{N}_s"),
                                              ("module-link", "import oracle_lp_run as R  # noqa: E402", "R = LRN  # n-substituted")],
               prelude={"LRN": LRN})
OBN.R = LRN


def cells_for(arm_raw=None):
    """raw arm name -> {seed: cell path} for this N and TAG."""
    out = collections.defaultdict(dict)
    for s in SEEDS:
        for p in glob.glob(str(RUNS / f"*_n{N}_s{s}_1200s_h27_3t{TAG}_L3_epg_rq30")) + \
                 glob.glob(str(RUNS / f"*_n{N}_s{s}_1200s_h27_3t{TAG}_L3_epg_rq30_rerun")):
            base = os.path.basename(p)
            raw = base.split(f"_n{N}_s{s}")[0]
            if not os.path.exists(os.path.join(p, "cell.json")):
                continue
            # _rerun wins over plain, as in OB._cell
            if s not in out[raw] or p.endswith("_rerun"):
                out[raw][s] = p
    return out


def ss_min_latency(seed):
    lat = {}
    for raw, bys in cells_for().items():
        if seed not in bys:
            continue
        for o in E.read_jsonl_gz(os.path.join(bys[seed], "outcomes.jsonl")):
            if not str(o.get("device_id", "")).startswith("asst"):
                continue
            td, to = o.get("t_delivered"), o.get("t_opportunity")
            if td is None or to is None:
                continue
            q = o.get("question_id")
            lat[q] = min(lat.get(q, math.inf), float(td) - float(to))
    return lat


def main():
    per_arm = collections.defaultdict(list)   # raw arm -> [(ideal, feas) per seed]
    reasons_tot = collections.Counter()
    cells = {}
    cap = {}
    tier, th_dev, th_cloud = LRN.dev_tier()
    ssbox = LRN.ss_box()
    for s in SEEDS:
        rc = LRN.recall_correctness(s, TAG)
        ac, ad = LRN.acc_cloud_device(s, TAG)
        cloud = LRN.simplestream_cloud(s, TAG)
        recall_unc = LRN.min_recall_uncached(s, TAG)
        units, floor = LRN.build_units(s, TAG, f"n{N}", rc, ac, ad, ssbox, cloud, tier, th_dev, th_cloud, recall_unc)
        import trace as TR
        recs = TR.generate_trace(seed=s, n_devices=N, ratio=RATIO, run_s=1200.0, mode="A",
                                 robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                                 robot_upload="per-frame", robot_reask_mean_s=30.0)["records"]
        hist = {r["opportunity_id"]: int(r["history_tokens"]) for r in recs if r["kind"] == "recall_question"}
        cap[s] = {"units": units, "floor": floor, "hist": hist}
        lat = ss_min_latency(s)
        for raw, bys in cells_for().items():
            if s not in bys:
                continue
            path = bys[s]
            pt = OBN.req_pt(path)
            ideal = OBN.arm_units(raw, s, TAG, rc, {}, {})
            if ideal is None:
                continue
            rows = {}
            for r in (((E.load_cell(path).get("score") or {}).get("score") or {}).get("robot_rows") or []):
                if str(r.get("device_id", "")).startswith("robo") and r.get("opportunity_id") is not None:
                    rows.setdefault(r.get("question_id") or r["opportunity_id"], []).append(
                        pt.get(r["opportunity_id"], 0))
            feas_r = {q: all(OF.feasible_recall(t) for t in ts if t) for q, ts in rows.items()}
            for q, ts in rows.items():
                for t in ts:
                    if t and not OF.reason_recall(t)["ok_cold"]:
                        reasons_tot["cold-tier TTFT + RTT + upload > 3 s (sensitivity)"] += 1
                    if t and not OF.reason_recall(t)["ok_best"]:
                        reasons_tot["best-tier TTFT + RTT + upload > 3 s"] += 1
            ss_q = {u[0] for u in ideal if u[1] == "single_shot"}
            feas_s = {q: (lat.get(q, 0.0) <= OF.L_SS + 1e-9) for q in ss_q}
            def gate(u, ok):
                return u if ok else (u[0], u[1], u[2], u[3], u[3], u[5], u[6], u[6])
            feas = [gate(u, feas_r.get(u[0], True) if u[1] == "recall" else feas_s.get(u[0], True))
                    for u in ideal]
            per_arm[raw].append((s, ideal, feas))
            cells[f"{raw}|s{s}"] = {"robot_n": sum(1 for u in ideal if u[1] == "recall"),
                                    "ss_n": sum(1 for u in ideal if u[1] == "single_shot"),
                                    "robot_infeasible_B_feas": sum(1 for q, ok in feas_r.items() if not ok),
                                    "ss_infeasible_B_feas": sum(1 for q, ok in feas_s.items() if not ok),
                                    "ss_no_committed_latency": sum(1 for q in ss_q if q not in lat)}
    shares = {}
    for raw, lst in per_arm.items():
        ideal_all = [u for _, i, _ in lst for u in i]
        feas_all = [u for _, _, f in lst for u in f]
        row = {}
        for name, uu_all in (("ideal", ideal_all), ("B_feas", feas_all)):
            for typ in ("recall", "single_shot", "pooled"):
                uu = uu_all if typ == "pooled" else [u for u in uu_all if u[1] == typ]
                if not uu:
                    continue
                pf, lf, hf = OBN.share_ci(uu, "F", np.random.default_rng(0))
                ph, lh, hh = OBN.share_ci(uu, "H", np.random.default_rng(0))
                row.setdefault(name, {})[typ] = {"FAIR": [pf, lf, hf], "HIND": [ph, lh, hh]}
        shares[raw] = row
    OF.SEEDS = SEEDS
    alpha, per = OF.cap_alpha(cap)
    out = {"_what": f"Feasibility-aware bound at N={N} devices, tag '{TAG}', seeds {SEEDS}. Same definitions "
                    "as oracle_feasible.py. The population for the capacity fraction is the N-device trace. "
                    "NEW output only.",
           "n_devices": N, "tag": TAG, "seeds": SEEDS, "arms": sorted(per_arm), "cells": cells,
           "robot_infeasible_reasons_rows": dict(reasons_tot), "shares": shares,
           "capacity_alpha": alpha, "_provenance": stamp(script="oracle_feasible_pop.py", model="none",
                                                          device="jetson_orin")}
    dst = REPO / f"results/orchestration/live2/oracle/oracle_feasible_pop_n{N}{TAG}.json"
    dst.write_text(json.dumps(out, indent=1, default=float))
    print(f"wrote {dst.name}: arms={len(per_arm)} cells={len(cells)} alpha_pooled={alpha.get('FAIR', {}).get('pooled')}")


if __name__ == "__main__":
    main()
