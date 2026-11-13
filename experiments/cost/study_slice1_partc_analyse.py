#!/usr/bin/env python3
"""StudySLICE1 Part C analysis (CPU). Per (condition, policy): episodic capacity (highest ladder level with episodic
p99 TTFT from the scheduled arrival <= 0.45 s and no errors, bottom-up, stop at first failure), per-cell p50 / p90 /
p99; cold recalls (Part B measures); warm traffic: appends issued / coalesced / dispatched, hold times and release
reasons, escalation time to answer from the scheduled time (fraction within 1 / 2 / 5 s), staleness (frames not yet
dispatched at the escalation's arrival), escalation letters vs P0's letters in the same condition (C4 -> C4a P0),
warm computed tokens vs P0 at the same level; over-budget episodic calls classified by the requests in flight during
[scheduled arrival, first token] (cold, warm append, warm escalation, none).
Decision (pre-registered, report section 11): see decide().
Writes results/cost/study_slice1/<prefix>_results.json.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_slice1"
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
LEVELS = ("< 10 %", "10 %", "20 %", "25 %", "30 %", "40 %")
BUDGET = 0.45
LETTER_REF_COND = {"C4a": "C4a", "C4": "C4a", "C2": "C2"}


def pct(x, q):
    x = [v for v in x if v is not None]
    return round(float(np.percentile(x, q)), 4) if x else None


def frac(xs, f):
    return round(sum(map(f, xs)) / len(xs), 4) if xs else None


def overlaps(ep, cold_iv, warm_iv):
    """Requests in flight during the episodic call's [scheduled arrival, first token]."""
    a, b = ep["t_sched"], ep["t_sched"] + ep["ttft_s"]
    hit = set()
    for s, e in cold_iv:
        if s < b and e > a:
            hit.add("cold")
    for kind, s, e in warm_iv:
        if s < b and e > a:
            hit.add(kind)
    return tuple(sorted(hit)) or ("none",)


def main(prefix="slice1_partc"):
    rows = [json.loads(l) for l in open(OUT / f"{prefix}_requests_h100nvl.jsonl")]
    warm = [json.loads(l) for l in open(OUT / f"{prefix}_warm_h100nvl.jsonl")]
    slices = [json.loads(l) for l in open(OUT / f"{prefix}_slices_h100nvl.jsonl")] \
        if (OUT / f"{prefix}_slices_h100nvl.jsonl").exists() else []
    meta = json.load(open(OUT / f"{prefix}_run_meta_h100nvl.json"))
    exp = meta.get("experiments", {})
    by, wby, sby = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    for r in warm:
        wby[r["cell"]].append(r)
    for r in slices:
        sby[r["cell"]].append(r)
    # reference escalation letters: P0 cells of the reference condition, per (device, session, question)
    ref = defaultdict(Counter)
    for tg, e in exp.items():
        if e.get("policy") == "P0" and e.get("cond") in ("C4a", "C2"):
            for x in wby[tg]:
                if x["kind"] == "recall_escalation" and x.get("letter"):
                    ref[(e["cond"], x["device"], x["session"], x["question_id"])][x["letter"]] += 1
    cells = {}
    for tg, rr in by.items():
        e = exp.get(tg, {})
        pol, cond, fr = e.get("policy"), e.get("cond"), e.get("frac")
        ep = [x for x in rr if x["kind"] == "episodic" and x["in_window"]]
        tt = [x["ttft_s"] for x in ep if x["ttft_s"] is not None]
        cold = [x for x in rr if x["kind"] == "cold_recall" and x["in_window"]]
        ww = [x for x in wby[tg] if x["in_window"]]
        app = [x for x in ww if x["kind"] == "recall_append"]
        esc = [x for x in ww if x["kind"] == "recall_escalation"]
        # time base: cell-relative (t0). Cold slice t_send is absolute -> t0 from the cold rows.
        t0s = [x["t_sched_abs"] - x["t_sched"] for x in rr if x["kind"] == "cold_recall" and x.get("t_sched_abs")]
        t0 = float(np.median(t0s)) if t0s else None
        cold_iv = [(s["t_send"] - t0, s["t_send"] - t0 + s["latency_s"]) for s in sby[tg]
                   if t0 is not None and s.get("t_send") and s.get("latency_s") is not None]
        warm_iv = [(x["kind"].replace("recall_", ""), x["t_submit"], x["t_end"]) for x in rr
                   if x["kind"].startswith("recall_") and x.get("t_submit") is not None and x.get("t_end") is not None]
        over = [x for x in ep if x["ttft_s"] is not None and x["ttft_s"] > BUDGET]
        ov = Counter("+".join(overlaps(x, cold_iv, warm_iv)) for x in over)
        ov_any = Counter(k for x in over for k in overlaps(x, cold_iv, warm_iv))
        lref = LETTER_REF_COND.get(cond)
        lc = []
        for x in esc:
            c = ref.get((lref, x["device"], x["session"], x["question_id"]))
            if c and x.get("letter") is not None:
                lc.append(x["letter"] == c.most_common(1)[0][0])
        tta = [x["t_answer_s"] for x in esc]
        cells[tg] = dict(
            policy=pol, cond=cond, frac=fr, episodic_n=len(ep), episodic_errors=sum(bool(x["error"]) for x in ep),
            p50=pct(tt, 50), p90=pct(tt, 90), p99=pct(tt, 99),
            meets_budget=bool(tt) and len(tt) == len(ep) and pct(tt, 99) <= BUDGET and not any(x["error"] for x in ep),
            recorded_meets_budget=(e.get("summary") or {}).get("meets_budget"),
            cold_n=len(cold), cold_t_answer=[x["ttft_s"] for x in cold],
            cold_meets_10s=sum(bool(x.get("meets_10s")) for x in cold),
            cold_meets_5s=sum(bool(x.get("meets_5s")) for x in cold),
            cold_letters_equal=sum(bool(x.get("letter_equal")) for x in cold),
            cold_first_cached_max=max((x["first_cached"] or 0 for x in cold), default=None),
            cold_gap_max=max((x["gap_max"] or 0 for x in cold), default=None),
            cold_computed_median=pct([x.get("computed_tokens") for x in cold], 50),
            cold_held_median_s=pct([x.get("held_s") for x in cold], 50),
            cold_released_by=dict(Counter(rb for x in cold for rb in (x.get("released_by") or []) if rb)),
            appends=len(app), appends_coalesced=sum(x["coalesced"] for x in app),
            appends_dispatched=sum(not x["coalesced"] for x in app),
            append_held_p50=pct([x["held_s"] for x in app if not x["coalesced"]], 50),
            append_held_p90=pct([x["held_s"] for x in app if not x["coalesced"]], 90),
            append_held_max=max((x["held_s"] for x in app if not x["coalesced"]), default=None),
            releases=dict(Counter(x["release"] for x in app + esc)),
            escalations=len(esc), esc_t_answer=tta, esc_unanswered=sum(t is None for t in tta),
            esc_within_1s=frac(esc, lambda x: (x["t_answer_s"] or 1e9) <= 1),
            esc_within_2s=frac(esc, lambda x: (x["t_answer_s"] or 1e9) <= 2),
            esc_within_5s=frac(esc, lambda x: (x["t_answer_s"] or 1e9) <= 5),
            esc_t_answer_p50=pct(tta, 50), esc_t_answer_p90=pct(tta, 90),
            esc_t_answer_max=max((t for t in tta if t is not None), default=None),
            esc_held_p50=pct([x["held_s"] for x in esc], 50), esc_held_max=max((x["held_s"] or 0 for x in esc), default=None),
            esc_flushed=sum(bool(x.get("flushed_append")) for x in esc),
            staleness_p50=pct([x.get("stale_frames") for x in esc], 50),
            staleness_max=max((x.get("stale_frames") or 0 for x in esc), default=None),
            esc_letters_compared=len(lc), esc_letters_equal=sum(lc),
            warm_computed=sum(x["computed_tokens"] or 0 for x in ww),
            warm_fallbacks=sum(bool(x.get("fallback")) for x in wby[tg]),
            warm_errors=sum(bool(x.get("error")) for x in wby[tg]),
            warmups_ending_in_window=(e.get("warm") or {}).get("warmups_ending_in_window"),
            over_budget=len(over), over_budget_overlap=dict(ov), over_budget_overlap_any=dict(ov_any))
    # P0 warm work reference per (cond, frac)
    for c in cells.values():
        # warm pass-through reference at the same condition and level: P0, else P4 (warm traffic identical)
        ref_c = sorted([d for d in cells.values() if d["policy"] in ("P0", "P4") and d["cond"] == c["cond"]
                        and d["frac"] == c["frac"]], key=lambda d: d["policy"])
        c["warm_ref_policy"] = ref_c[0]["policy"] if ref_c else None
        c["warm_computed_vs_p0"] = (round(c["warm_computed"] / ref_c[0]["warm_computed"], 4)
                                    if ref_c and ref_c[0]["warm_computed"] else None)
    table = defaultdict(dict)
    for cond in ("C4a", "C4", "C2", "C1b"):
        for pol in ("P0", "P4", "P5", "P5nc", "P4_1024"):
            cs = sorted([c for c in cells.values() if c["cond"] == cond and c["policy"] == pol], key=lambda c: c["frac"])
            if not cs:
                continue
            single = len(cs) == 1 and pol in ("P0", "P4", "P5nc") and cond in ("C4a", "C4")
            cap = 0
            for c in cs:
                if not c["meets_budget"]:
                    break
                cap = LADDER.index(c["frac"]) + 1
            failed = any(not c["meets_budget"] for c in cs)
            tta = [t for c in cs for t in c["cold_t_answer"]]
            n = sum(c["cold_n"] for c in cs)
            esc = [t for c in cs for t in c["esc_t_answer"]]
            ne = len(esc)
            table[cond][pol] = dict(
                capacity=(LEVELS[cap] + ("" if failed else " (ladder top, not failed)")) if not single
                else f"single cell {int(cs[0]['frac'] * 100)} %: {'meets' if cs[0]['meets_budget'] else 'fails'}",
                capacity_idx=cap, ladder=not single,
                cells=[dict(frac=c["frac"], p50=c["p50"], p90=c["p90"], p99=c["p99"], meets=c["meets_budget"],
                            cold_n=c["cold_n"], escalations=c["escalations"], over_budget=c["over_budget"],
                            overlap=c["over_budget_overlap"], warm_computed_vs_p0=c["warm_computed_vs_p0"])
                       for c in cs],
                recalls=n, t_answer_p50=pct(tta, 50), t_answer_p90=pct(tta, 90),
                t_answer_max=max((t for t in tta if t is not None), default=None),
                frac_10s=(sum(c["cold_meets_10s"] for c in cs) / n) if n else None,
                frac_5s=(sum(c["cold_meets_5s"] for c in cs) / n) if n else None,
                cold_letters_equal=sum(c["cold_letters_equal"] for c in cs),
                escalations=ne, esc_within_1s=(sum(t is not None and t <= 1 for t in esc) / ne) if ne else None,
                esc_within_2s=(sum(t is not None and t <= 2 for t in esc) / ne) if ne else None,
                esc_within_5s=(sum(t is not None and t <= 5 for t in esc) / ne) if ne else None,
                esc_t_answer_p50=pct(esc, 50), esc_t_answer_p90=pct(esc, 90),
                staleness_p50=pct([c["staleness_p50"] for c in cs], 50),
                staleness_max=max((c["staleness_max"] or 0 for c in cs), default=None),
                esc_letters_compared=sum(c["esc_letters_compared"] for c in cs),
                esc_letters_equal=sum(c["esc_letters_equal"] for c in cs),
                appends=sum(c["appends"] for c in cs), appends_coalesced=sum(c["appends_coalesced"] for c in cs),
                releases=dict(sum((Counter(c["releases"]) for c in cs), Counter())))
    decision = decide(table, cells, meta)
    res = dict(label="StudySLICE1 Part C: warm management (P5) vs P0 / P4 under KV-HOST warm sessions + cold ~11k D2 "
                     "recall, and P4_1024 at C1b; 32B-I vLLM 0.31.0 E0, H100 GPU 2",
               cells=cells, table=table, decision=decision, drift_check=meta.get("drift_check"),
               void=meta.get("void"), servers=len(meta.get("servers", [])),
               servers_flags_verified=sum(bool(s.get("flags_verified")) for s in meta.get("servers", [])))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_slice1_partc_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / f"{prefix}_results.json").write_text(json.dumps(res, indent=1, default=float))
    for cond, d in table.items():
        for pol, t in d.items():
            print(cond, pol, t["capacity"], "| recalls", t["recalls"], "10s", t["frac_10s"] and round(t["frac_10s"], 3),
                  "| esc", t["escalations"], "5s", t["esc_within_5s"] and round(t["esc_within_5s"], 3),
                  "letters", t["esc_letters_equal"], "/", t["esc_letters_compared"], "| coalesced", t["appends_coalesced"],
                  "/", t["appends"], "|", [(c["frac"], c["p99"], c["meets"], c["overlap"]) for c in t["cells"]])
    print("decision", json.dumps(decision, indent=1))


def decide(table, cells, meta):
    d = {}
    c2 = table.get("C2", {}).get("P0")
    c2_idx = c2["capacity_idx"] if c2 else None
    for cond in ("C4a", "C4"):
        t = table.get(cond, {}).get("P5")
        if not t or c2_idx is None:
            continue
        within = t["capacity_idx"] >= c2_idx - 1
        d[cond] = dict(p5_capacity=t["capacity"], c2_p0_capacity=LEVELS[c2_idx], within_one_level=within,
                       cold_frac_10s=t["frac_10s"], esc_frac_5s=t["esc_within_5s"],
                       restores=bool(within and (t["frac_10s"] or 0) >= 0.90 and (t["esc_within_5s"] or 0) >= 0.90))
    t = table.get("C2", {}).get("P5")
    if t and c2_idx is not None:
        d["C2_warm_only"] = dict(p5_capacity=t["capacity"], p0_capacity=LEVELS[c2_idx],
                                 helps=t["capacity_idx"] >= c2_idx + 1)
    t = table.get("C1b", {}).get("P4_1024")
    if t:
        d["C1b_P4_1024"] = dict(capacity=t["capacity"], frac_10s=t["frac_10s"],
                                meets_rule=t["capacity_idx"] >= LADDER.index(0.30) + 1 and (t["frac_10s"] or 0) >= 0.90)
    lt = {cond: (sum(table[cond][p]["esc_letters_equal"] for p in table[cond] if p != "P0"),
                 sum(table[cond][p]["esc_letters_compared"] for p in table[cond] if p != "P0"))
          for cond in ("C4a", "C4", "C2") if cond in table}
    # replicate (registered as coalescing OFF; relabelled before the sweep): p99 difference vs the C4a P5 cell
    rep = [c for c in cells.values() if c["policy"] == "P5nc" and c["cond"] == "C4a"]
    if rep:
        r = rep[0]
        twin = [c for c in cells.values() if c["policy"] == "P5" and c["cond"] == "C4a" and c["frac"] == r["frac"]]
        if twin:
            t = twin[0]
            d["replicate"] = dict(frac=r["frac"], p99_p5=t["p99"], p99_replicate=r["p99"],
                                  p99_diff=round(r["p99"] - t["p99"], 4), p99_ratio=round(r["p99"] / t["p99"], 4),
                                  meets_p5=t["meets_budget"], meets_replicate=r["meets_budget"],
                                  coalesced_p5=t["appends_coalesced"], coalesced_replicate=r["appends_coalesced"],
                                  next_append_due_replicate=r["releases"].get("next_append_due", 0))
    d["warm_computed_vs_p0"] = {f"{c['cond']} {c['policy']} {int(c['frac'] * 100)} % (vs {c['warm_ref_policy']})": c["warm_computed_vs_p0"]
                                for c in sorted(cells.values(), key=lambda c: (c["cond"] or "", c["policy"] or "", c["frac"] or 0))
                                if c["warm_computed_vs_p0"] is not None and c["policy"] not in ("P0", "P4")}
    d["escalation_letters"] ={c: dict(equal=e, compared=n, frac=(e / n) if n else None,
                                       flagged=bool(n) and e / n < 0.95) for c, (e, n) in lt.items()}
    return d


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
