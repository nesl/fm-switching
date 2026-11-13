#!/usr/bin/env python3
"""StudySLICE1 Part B analysis (CPU). Per (condition, policy): episodic capacity (highest ladder level whose episodic
p99 TTFT from the scheduled arrival <= 0.45 s with no errors, bottom-up, stop at first failure), episodic p50 / p90 /
p99 per cell; cold recalls in the scored window over all cells of that ladder: time to answer from the scheduled
arrival (p50 / p90 / max), fraction meeting 5 s / 10 s, letters equal to the Part A monolithic answer, computed
tokens per recall (GPU work), holds. Decision (pre-registered): slicing restores capacity if P3 or P4's C1 capacity is
within one ladder level of C0's AND >= 90 % of their recalls meet the 10-s deadline; P2 reported against the same rule.
Applied separately at C1 r 0.05 (C1a, primary) and r 0.1 (C1b). Writes results/cost/study_slice1/<prefix>_results.json.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_slice1"
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
LEVELS = ("< 10 %", "10 %", "20 %", "25 %", "30 %", "40 %")
POLICIES = ("P0", "P1", "P2", "P3_1024", "P3_2048", "P4")
BUDGET = 0.45


def pct(x, q):
    x = [v for v in x if v is not None]
    return round(float(np.percentile(x, q)), 4) if x else None


def main(prefix="slice1_live"):
    rows = [json.loads(l) for l in open(OUT / f"{prefix}_requests_h100nvl.jsonl")]
    meta = json.load(open(OUT / f"{prefix}_run_meta_h100nvl.json"))
    exp = meta.get("experiments", {})
    by = defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    cells = {}
    for tg, rr in by.items():
        e = exp.get(tg, {})
        pol, cond, frac = e.get("policy"), e.get("cond"), e.get("frac")
        ep = [x for x in rr if x["kind"] == "episodic" and x["in_window"]]
        tt = [x["ttft_s"] for x in ep if x["ttft_s"] is not None]
        cold = [x for x in rr if x["kind"] == "cold_recall" and x["in_window"]]
        cells[tg] = dict(policy=pol, cond=cond, frac=frac, episodic_n=len(ep), episodic_errors=sum(bool(x["error"]) for x in ep),
                         p50=pct(tt, 50), p90=pct(tt, 90), p99=pct(tt, 99),
                         meets_budget=bool(tt) and len(tt) == len(ep) and pct(tt, 99) <= BUDGET
                         and not any(x["error"] for x in ep),
                         cold_n=len(cold), cold_t_answer=[x["ttft_s"] for x in cold],
                         cold_meets_10s=sum(bool(x.get("meets_10s")) for x in cold),
                         cold_meets_5s=sum(bool(x.get("meets_5s")) for x in cold),
                         letters_equal=sum(bool(x.get("letter_equal")) for x in cold),
                         computed_tokens_median=pct([x.get("computed_tokens") for x in cold], 50),
                         held_median_s=pct([x.get("held_s") for x in cold], 50),
                         admitted_after_median_s=pct([x.get("admitted_after_s") for x in cold], 50),
                         cold_errors=sum(bool(x.get("error")) for x in cold),
                         released_by=dict(sorted(__import__("collections").Counter(
                             rb for x in cold for rb in (x.get("released_by") or []) if rb).items())),
                         recorded_meets_budget=(e.get("summary") or {}).get("meets_budget"))
    table = defaultdict(dict)
    for cond in ("C1a", "C4", "C0", "C1b"):
        for pol in POLICIES:
            cs = sorted([c for c in cells.values() if c["cond"] == cond and c["policy"] == pol], key=lambda c: c["frac"])
            if not cs:
                continue
            cap = 0
            for c in cs:
                if not c["meets_budget"]:
                    break
                cap = LADDER.index(c["frac"]) + 1
            ladder_top_failed = any(not c["meets_budget"] for c in cs)
            tta = [t for c in cs for t in c["cold_t_answer"]]
            n = sum(c["cold_n"] for c in cs)
            table[cond][pol] = dict(
                capacity=LEVELS[cap] + ("" if ladder_top_failed or cond == "C0" else " (ladder top, not failed)"),
                capacity_idx=cap, cells=[dict(frac=c["frac"], p50=c["p50"], p90=c["p90"], p99=c["p99"],
                                              meets=c["meets_budget"], cold_n=c["cold_n"]) for c in cs],
                recalls=n, t_answer_p50=pct(tta, 50), t_answer_p90=pct(tta, 90),
                t_answer_max=max((t for t in tta if t is not None), default=None),
                unanswered=sum(t is None for t in tta),
                frac_10s=(sum(c["cold_meets_10s"] for c in cs) / n) if n else None,
                frac_5s=(sum(c["cold_meets_5s"] for c in cs) / n) if n else None,
                letters_equal=sum(c["letters_equal"] for c in cs),
                computed_tokens_median=pct([c["computed_tokens_median"] for c in cs], 50))
    c0 = table.get("C0", {}).get("P0")
    c0_idx = None
    if c0:
        c0_idx = max((LADDER.index(c["frac"]) + 1 for c in c0["cells"] if c["meets"]), default=0)
    decision = {}
    for cond in ("C1a", "C1b"):
        d = {}
        for pol in ("P2", "P3_1024", "P3_2048", "P4", "P0", "P1"):
            t = table.get(cond, {}).get(pol)
            if not t or c0_idx is None:
                continue
            within = t["capacity_idx"] >= c0_idx - 1
            d[pol] = dict(capacity=t["capacity"], c0=LEVELS[c0_idx], within_one_level=within,
                          frac_10s=t["frac_10s"], meets_rule=within and (t["frac_10s"] or 0) >= 0.90)
        d["slicing_restores_capacity"] = any(d.get(p, {}).get("meets_rule") for p in ("P3_1024", "P3_2048", "P4"))
        decision[cond] = d
    res = dict(label="StudySLICE1 Part B: orchestrator policies (pass-through / EDF / blocking-aware / sliced) under "
                     "cold ~11k D2 recall, 32B-I vLLM 0.31.0 E0, H100 GPU 2", cells=cells, table=table,
               c0_capacity=LEVELS[c0_idx] if c0_idx is not None else None, decision=decision,
               void=meta.get("void"), servers=len(meta.get("servers", [])))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_slice1_live_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / f"{prefix}_results.json").write_text(json.dumps(res, indent=1, default=float))
    for cond, d in table.items():
        for pol, t in d.items():
            print(cond, pol, t["capacity"], "| recalls", t["recalls"], "10s", t["frac_10s"] and round(t["frac_10s"], 3),
                  "5s", t["frac_5s"] and round(t["frac_5s"], 3), "tta p50/p90", t["t_answer_p50"], t["t_answer_p90"],
                  "letters", t["letters_equal"], "|", [(c["frac"], c["p99"], c["meets"]) for c in t["cells"]])
    print("decision", json.dumps(decision))


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
