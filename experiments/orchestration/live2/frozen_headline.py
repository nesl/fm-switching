#!/usr/bin/env python3
"""StudyFROZEN-test headline (user ruling 2026-11-20): pooled per-arm rates across seeds with PAIRED-BY-SEED bootstrap CIs.

Rates per arm, pooled over the seeds where EVERY listed arm has a kept run (common support):
  robot on time over FEASIBLE questions (D133; flash's feasibility rule per robot question from the run's own trace),
  SS on time within 2 s, dashcam all-meet (share of runs).
On time = delivered within the deadline by a request that returned HTTP 200 (D144 as corrected 2026-11-20).
Pairing: every arm runs the SAME trace per seed, so a question is the same opportunity across arms. Bootstrap resamples
opportunities WITHIN each seed (stratified), the same draw applied to every arm, B = 10,000; differences against b7 use
the same draws. Measurability (D82): >= 20 robot questions per run (all robot questions), feasible count reported beside.
The first attempt of a cell is the cell (reruns ignored). Read-only; run only when no live run's preflight can overlap.

Usage: python frozen_headline.py <runs dir> <n_devices> <out json>
"""
import gzip
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (HERE, HERE / "fleet", REPO / "experiments/orchestration/baselines", REPO / "experiments/orchestration/sim",
          REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
import costs as C          # noqa: E402
import traces as TRC       # noqa: E402

ARMS = ["b7-edf-feasibility", "eco-llm", "mooncake", "hybrid-F-lhreq", "hybrid-F6-lhreq"]
B = 10000
SS_L = 2.0


def jl(p):
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            op = gzip.open if c.suffix == ".gz" else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    raise FileNotFoundError(p)


def run_flags(d):
    c = json.loads((d / "cell.json").read_text())
    tr = jl(Path(c["trace_dir"]) / "trace.jsonl")
    link = TRC.RTT_MS / 1000.0
    feas, ssq = {}, set()
    for r in tr:
        if r.get("kind") != "recall_question":
            continue
        dev = str(r.get("device_id", ""))
        if dev.startswith("robo"):
            h = int(r.get("history_tokens") or 0)
            feas[r["opportunity_id"]] = (C.recall_ttft_s(h, "COLD") + C.recall_ttft_s(h, "GPU-WARM") + link) <= float(r.get("deadline_s") or 5.0)
        elif dev.startswith("asst"):
            ssq.add(r["opportunity_id"])
    failed = {r.get("request_id") for r in jl(d / "request.jsonl") if r.get("http_status") != 200}
    ont = {}
    for o in jl(d / "outcomes.jsonl"):
        if o.get("kind") != "recall":
            continue
        td = o.get("t_delivered")
        rid = (o.get("cloud_payload") or {}).get("request_id")
        L = SS_L if o["opportunity_id"] in ssq else float(o.get("deadline_s") or 5.0)
        ont[o["opportunity_id"]] = bool(td is not None and rid not in failed and float(td) - float(o["t_opportunity"]) <= L)
    sw = (((c.get("score") or {}).get("score") or {}).get("sweep") or [{}])[0]
    return dict(robot_feasible={k: ont.get(k, False) for k, v in feas.items() if v}, robot_all=len(feas),
                ss={k: ont.get(k, False) for k in ssq}, dash=bool(sw.get("dashcam_all_meet")),
                errors=c.get("n_errors"), requests=c.get("n_requests"))


def main(runs_dir, n, out):
    n = int(n)
    R = Path(runs_dir)
    runs = {}
    for a in ARMS:
        for s in (0, 4, 5, 6):
            d = R / f"{a}_n{n}_s{s}_1200s_h27_3t"
            if (d / "cell.json").exists():
                c = json.loads((d / "cell.json").read_text())
                if c.get("err") is None and c.get("run_valid") and c.get("digests_equal"):
                    runs[(a, s)] = run_flags(d)
    seeds = [s for s in (0, 4, 5, 6) if all((a, s) in runs for a in ARMS)]
    # the opportunity sets per seed are shared across arms (same trace); take them from b7
    rob_ids = {s: sorted(runs[("b7-edf-feasibility", s)]["robot_feasible"]) for s in seeds}
    ss_ids = {s: sorted(runs[("b7-edf-feasibility", s)]["ss"]) for s in seeds}
    for s in seeds:
        for a in ARMS:
            assert sorted(runs[(a, s)]["robot_feasible"]) == rob_ids[s] and sorted(runs[(a, s)]["ss"]) == ss_ids[s], (a, s)

    def pooled(a, rdraw, sdraw):
        rn = sum(runs[(a, s)]["robot_feasible"][k] for s in seeds for k in rdraw[s])
        rd = sum(len(rdraw[s]) for s in seeds)
        sn = sum(runs[(a, s)]["ss"][k] for s in seeds for k in sdraw[s])
        sd = sum(len(sdraw[s]) for s in seeds)
        return rn / rd, sn / sd

    import numpy as np
    point = {a: pooled(a, rob_ids, ss_ids) for a in ARMS}
    rng = np.random.default_rng(0)
    # per seed: an arms x questions 0/1 matrix; one index draw per seed per replicate, shared by every arm (paired)
    rob_num = np.zeros((len(ARMS), B)); ss_num = np.zeros((len(ARMS), B))
    rob_den = sum(len(rob_ids[s]) for s in seeds); ss_den = sum(len(ss_ids[s]) for s in seeds)
    for s in seeds:
        for ids, num, key in ((rob_ids[s], rob_num, "robot_feasible"), (ss_ids[s], ss_num, "ss")):
            if not ids:
                continue
            M = np.array([[runs[(a, s)][key][k] for k in ids] for a in ARMS], dtype=float)
            idx = rng.integers(0, len(ids), size=(B, len(ids)))
            num += M[:, idx].sum(axis=2)
    boots = {a: list(zip(rob_num[i] / rob_den, ss_num[i] / ss_den)) for i, a in enumerate(ARMS)}

    def ci(xs):
        xs = sorted(xs)
        return [round(xs[int(0.025 * B)], 4), round(xs[int(0.975 * B)], 4)]

    rows = []
    for a in ARMS:
        rows.append(dict(arm=a,
                         robot_feasible_on_time=round(point[a][0], 4), robot_ci95=ci([x[0] for x in boots[a]]),
                         robot_feasible_n=sum(len(rob_ids[s]) for s in seeds),
                         robot_feasible_hits=sum(runs[(a, s)]["robot_feasible"][k] for s in seeds for k in rob_ids[s]),
                         ss_on_time=round(point[a][1], 4), ss_ci95=ci([x[1] for x in boots[a]]),
                         ss_n=sum(len(ss_ids[s]) for s in seeds),
                         ss_hits=sum(runs[(a, s)]["ss"][k] for s in seeds for k in ss_ids[s]),
                         dashcam_all_meet_runs=f"{sum(runs[(a, s)]['dash'] for s in seeds)} of {len(seeds)}",
                         robot_minus_b7_ci95=ci([x[0] - y[0] for x, y in zip(boots[a], boots['b7-edf-feasibility'])]),
                         ss_minus_b7_ci95=ci([x[1] - y[1] for x, y in zip(boots[a], boots['b7-edf-feasibility'])]),
                         per_run=[dict(seed=s, robot_all=runs[(a, s)]["robot_all"], robot_feasible=len(rob_ids[s]),
                                       robot_feasible_hits=sum(runs[(a, s)]["robot_feasible"].values()),
                                       ss_hits=sum(runs[(a, s)]["ss"].values()), ss_n=len(ss_ids[s]),
                                       dash=runs[(a, s)]["dash"], errors=runs[(a, s)]["errors"]) for s in seeds]))
    res = dict(n_devices=n, seeds_common_support=seeds, bootstrap=f"paired by seed: opportunities resampled within each seed, same draw for every arm, B={B}",
               on_time_rule="delivered within the deadline (robot 5 s, SS 2 s) by an HTTP 200 request", rows=rows)
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print("seeds", seeds)
    for r in rows:
        print(f"{r['arm']:20s} robot {r['robot_feasible_hits']}/{r['robot_feasible_n']} = {r['robot_feasible_on_time']} {r['robot_ci95']} "
              f"diff {r['robot_minus_b7_ci95']} | SS {r['ss_hits']}/{r['ss_n']} = {r['ss_on_time']} {r['ss_ci95']} diff {r['ss_minus_b7_ci95']} | dash {r['dashcam_all_meet_runs']}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
