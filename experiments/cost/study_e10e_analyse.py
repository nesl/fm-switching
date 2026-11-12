#!/usr/bin/env python3
"""StudyE10e-partial-prefill analysis (CPU). Per cell: E10c's statistics (study_e10c_analyse.cell_stats: episodic
p50 / p90 / p99 from scheduled arrival, cold / append / escalation TTFT, unfinished, window /metrics + sampler means:
GPU util, computed tok/s, waiting, preemptions) and E10d's hold analysis (study_e10d_analyse.cell_stats: slow episodic
inside cold windows, release relative to the cold first token, submit relative to cold engine arrival, Step 3 trace).
Capacity per (config, condition) for V1 = highest level of the bottom-up ladder meeting the budget (P1-P3 C0: 25 / 40 %
only). Pre-registered decision: a config removes the interference iff its C1 capacity is within one ladder level of
its own C0 capacity. Cost: cold TTFT p50 / p99 vs P0 at the same cell; C0 capacity vs P0.
Writes results/cost/study_e10/e10e_results.json."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "experiments/lib"))
import study_e10c_analyse as C  # noqa: E402
import study_e10d_analyse as DA  # noqa: E402

OUT = C.OUT
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
PAT = re.compile(r"E10E_(P\d)_(C\d)_(V\d)_N1_L(\d+)")
CONFIGS = ("P0", "P1", "P2", "P3")


def idx(f):
    return LADDER.index(f) if f else -1          # < 10 % -> -1


def main():
    rows = [json.loads(l) for l in open(OUT / "e10e_requests_h100nvl.jsonl")]
    cold = [json.loads(l) for l in open(OUT / "e10e_cold_phases_h100nvl.jsonl")]
    mets = {m["cell"]: m for m in map(json.loads, open(OUT / "e10e_metrics_h100nvl.jsonl"))}
    cpus = {c["cell"]: c for c in map(json.loads, open(OUT / "e10e_cpu_h100nvl.jsonl"))}
    meta = json.load(open(OUT / "e10e_run_meta_h100nvl.json"))
    by, cby = defaultdict(list), defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    for x in cold:
        cby[x["cell"]].append(x)
    cells = {}
    for tg in meta["done"]:
        p, cn, v, lv = PAT.match(tg).groups()
        c = C.cell_stats(by[tg], mets.get(tg), cpus.get(tg))
        d = DA.cell_stats(by[tg], cby[tg]) if cby[tg] else {}
        c.update(config=p, cond=cn, variant=v, frac=int(lv) / 100, hold=d.get("hold"), cold_phases=d.get("cold"),
                 trace=d.get("trace"), harness_meets_budget=meta["experiments"][tg]["summary"]["meets_budget"])
        cells[tg] = c
    lad = defaultdict(dict)
    for tg, c in cells.items():
        if c["variant"] == "V1":
            lad[(c["config"], c["cond"])][c["frac"]] = c
    cap = {}
    for (p, cn), lv in sorted(lad.items()):
        levels = sorted(lv)
        best = None
        for f in [x for x in LADDER if x in lv or (p != "P0" and cn == "C0")]:
            if f not in lv:
                continue                          # P1-P3 C0: only 25 / 40 % run
            if lv[f]["meets_budget"]:
                best = f
            else:
                break
        top_ok = levels and lv[levels[-1]]["meets_budget"] and levels[-1] == LADDER[-1]
        label = (f"{int(round(best * 100))} %" if best else ("< 10 %" if levels[0] == 0.10 else f"< {int(levels[0] * 100)} %"))
        cap[f"{p}/{cn}"] = dict(config=p, cond=cn, levels_run=levels, capacity_frac=best,
                                capacity_label=label + (" (ladder top, not failed)" if top_ok else ""),
                                p99_by_level={str(f): lv[f]["p99"] for f in levels})
    decision = {}
    for p in CONFIGS:
        c0, c1, c4 = cap.get(f"{p}/C0"), cap.get(f"{p}/C1"), cap.get(f"{p}/C4")
        if not c0 or not c1:
            continue
        gap = idx(c0["capacity_frac"]) - idx(c1["capacity_frac"])
        decision[p] = dict(C0=c0["capacity_label"], C1=c1["capacity_label"], C4=c4["capacity_label"] if c4 else None,
                           C1_levels_below_C0=gap, removes_interference=gap <= 1,
                           C4_levels_below_C0=(idx(c0["capacity_frac"]) - idx(c4["capacity_frac"])) if c4 else None,
                           C0_vs_P0_levels=idx(c0["capacity_frac"]) - idx(cap["P0/C0"]["capacity_frac"]) if "P0/C0" in cap else None)
    cost = {}
    for tg, c in cells.items():
        if c["config"] == "P0" or c["cond"] == "C0":
            continue
        ref = cells.get(tg.replace(f"_{c['config']}_", "_P0_"))
        if not ref:
            continue
        cr, rr = c["cold_recall"], ref["cold_recall"]
        cost[tg] = dict(cold_ttft_p50=cr["ttft_p50"], cold_ttft_p99=cr["ttft_p99"], P0_cold_ttft_p50=rr["ttft_p50"],
                        P0_cold_ttft_p99=rr["ttft_p99"],
                        ratio_p50=cr["ttft_p50"] / rr["ttft_p50"] if cr["ttft_p50"] and rr["ttft_p50"] else None,
                        ratio_p99=cr["ttft_p99"] / rr["ttft_p99"] if cr["ttft_p99"] and rr["ttft_p99"] else None,
                        append_p50=c["recall_append"]["ttft_p50"], P0_append_p50=ref["recall_append"]["ttft_p50"],
                        escalation_p50=c["recall_escalation"]["ttft_p50"],
                        P0_escalation_p50=ref["recall_escalation"]["ttft_p50"])
    ctrl = meta.get("control", {})
    servers = [dict(label=s["label"], config=s.get("config"), threshold=s.get("log_long_prefill_token_threshold"),
                    policy=s.get("log_scheduling_policy"), mnbt=s.get("log_max_num_batched_tokens"),
                    chunked=s.get("log_chunked_prefill"), verified=s.get("flags_verified")) for s in meta.get("servers", [])]
    res = dict(label="StudyE10e-partial-prefill: long-prefill cap vs cold-recall interference, 32B-I, one replica, H100 "
                     "GPU 2 (vLLM 0.31.0, prefix caching ON, N = 1)", cells=cells, capacity=cap, decision=decision,
               cold_cost=cost, control=ctrl, control_pass=bool(ctrl) and all(x["within_2x"] for v in ctrl.values() for x in v),
               servers=servers, all_flags_verified=all(s["verified"] for s in servers), void=meta.get("void"))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10e_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / "e10e_results.json").write_text(json.dumps(res, indent=1, default=float))
    for tg, c in cells.items():
        h = c["hold"] or {}
        s = c["server"]
        print(tg, f"p50 {c['p50']:.3f} p90 {c['p90']:.3f} p99 {c['p99']:.3f} ok {c['meets_budget']} | cold p50 "
              f"{c['cold_recall']['ttft_p50']} p99 {c['cold_recall']['ttft_p99']} | app {c['recall_append']['ttft_p50']} esc "
              f"{c['recall_escalation']['ttft_p50']} | gpu {s.get('gpu_util_mean')} tok/s {s.get('computed_tok_s')} wait "
              f"{s.get('waiting_mean')} pre {s.get('preemptions')} unf {c['unfinished_any']} | slow {h.get('slow')} inside "
              f"{h.get('slow_inside_cold_window')} rel_first p50 {h.get('release_minus_cold_first_p50')}")
    for k, v in cap.items():
        print(k, v["capacity_label"], {f: round(x, 3) for f, x in v["p99_by_level"].items()})
    print("decision", json.dumps(decision))
    print("control", ctrl, "flags verified", res["all_flags_verified"])


if __name__ == "__main__":
    main()
