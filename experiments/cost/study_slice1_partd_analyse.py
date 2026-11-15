#!/usr/bin/env python3
"""StudySLICE1 Part D analysis (CPU). Per cell (mode a = known Poisson schedule, b = cadence-only streams, s0 / s20 =
jitter sensitivity; engine E0 / T1 = E10e P1): episodic p50 / p90 / p99 and capacity (D-a: highest ladder fraction,
D-b: highest stream count, with p99 <= 0.45 s and no errors, bottom-up, stop at first failure); cold recalls (Part B / C
measures); warm traffic (Part C measures; escalation letters vs P0 in the same mode / engine / condition, else Part C's
P0 in that condition, C4 -> C4a); lane (occupancy, max in flight, queue length, holds, gap / slack releases, predicted
vs measured service, EWMA, coalesced / absorbed); bunching in every cell (background units submitted within 50 ms of
another; max concurrently in flight); over-budget overlap classes; D-b per-call jitter and prediction error.
Decisions (pre-registered, report section 17): see decide(). Writes results/cost/study_slice1/<prefix>_results.json.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
sys.path.insert(0, str(HERE))
from study_slice1_partc_analyse import overlaps, pct  # noqa: E402

OUT = REPO / "results/cost/study_slice1"
LADDER = (0.10, 0.20, 0.25, 0.30, 0.40)
STREAMS = (1, 2, 3, 4, 5)
BUDGET = 0.45
PEAK = 15.1
# report section 17a: the D-b P6 lane deadlocks with warm sessions (escalation predicted 0.539 s cannot fit the 0.456-s
# cadence gap; escalations have no slack). Those cells carry starvation counts and no capacity figure.
DEGENERATE = {("b", "E0", "C4a", "P6")}
CAD = 0.5


def frac_ok(xs, f):
    return round(sum(map(f, xs)) / len(xs), 4) if xs else None


def to_streams(frac):
    return None if frac is None else int(math.floor(frac * PEAK * CAD + 1e-9))


def lev_name(mode, lev):
    return f"{int(round(lev * 100))} %" if mode == "a" else f"{lev} stream{'s' if lev > 1 else ''}"


def known_schedule():
    """Known-schedule (Poisson, oracle) capacities as fractions from committed Parts B / C and StudyE10e (tuned P1),
    plus this run's D-a. None = not measured under the known schedule."""
    kb = json.load(open(OUT / "slice1_live_results.json"))["table"]
    kc = json.load(open(OUT / "slice1_partc_results.json"))["table"]
    e10e = json.load(open(REPO / "results/cost/study_e10/e10e_results.json"))["capacity"]

    def lvl(t):
        return LADDER[t["capacity_idx"] - 1] if t["capacity_idx"] else 0.0
    k = {("E0", "C1a", p): (lvl(kb["C1a"][p]), "Part B") for p in ("P0", "P2", "P3_1024", "P4") if p in kb["C1a"]}
    k[("E0", "C4a", "P0")] = (0.0, "Part C (fails at 10 %)")
    k[("E0", "C4a", "P4")] = (lvl(kc["C4a"]["P4"]), "Part C")
    k[("E0", "C1b", "P0")] = (lvl(kb["C1b"]["P0"]), "Part B")
    k[("E0", "C1b", "P4_1024")] = (lvl(kc["C1b"]["P4_1024"]), "Part C")
    k[("E0", "C2", "P0")] = (lvl(kc["C2"]["P0"]), "Part C")
    k[("E0", "C0", "P0")] = (0.40, "Part B (ladder top 40 %, not failed)")
    k[("T1", "C0", "P0")] = (e10e["P1/C0"]["capacity_frac"] or 0.0, "StudyE10e P1 (ladder top, not failed)")
    k[("T1", "C1a", "P0")] = (e10e["P1/C1"]["capacity_frac"] or 0.0, "StudyE10e P1 C1 (K1 video cold body)")
    return k


def main(prefix="slice1_partd"):
    rows = [json.loads(l) for l in open(OUT / f"{prefix}_requests_h100nvl.jsonl")]
    warm = [json.loads(l) for l in open(OUT / f"{prefix}_warm_h100nvl.jsonl")] \
        if (OUT / f"{prefix}_warm_h100nvl.jsonl").exists() else []
    slices = [json.loads(l) for l in open(OUT / f"{prefix}_slices_h100nvl.jsonl")] \
        if (OUT / f"{prefix}_slices_h100nvl.jsonl").exists() else []
    lane = [json.loads(l) for l in open(OUT / f"{prefix}_lane_h100nvl.jsonl")] \
        if (OUT / f"{prefix}_lane_h100nvl.jsonl").exists() else []
    meta = json.load(open(OUT / f"{prefix}_run_meta_h100nvl.json"))
    exp = meta.get("experiments", {})
    disc = (meta.get("stack") or {}).get("discard", 30.0)
    by, wby, sby, lby = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    for r in warm:
        wby[r["cell"]].append(r)
    for r in slices:
        sby[r["cell"]].append(r)
    for r in lane:
        lby[r["cell"]].append(r)
    # escalation letter references: P0 cells of this run (mode, engine, cond), else Part C P0 (C4 -> C4a)
    ref = defaultdict(Counter)
    for tg, e in exp.items():
        if e.get("policy") == "P0":
            for x in wby[tg]:
                if x["kind"] == "recall_escalation" and x.get("letter"):
                    ref[(e["mode"], e["engine"], e["cond"], x["device"], x["session"], x["question_id"])][x["letter"]] += 1
    pc_ref = defaultdict(Counter)
    pc_meta = json.load(open(OUT / "slice1_partc_run_meta_h100nvl.json"))["experiments"]
    for l in open(OUT / "slice1_partc_warm_h100nvl.jsonl"):
        x = json.loads(l)
        e = pc_meta.get(x["cell"], {})
        if e.get("policy") == "P0" and x["kind"] == "recall_escalation" and x.get("letter"):
            pc_ref[(e["cond"], x["device"], x["session"], x["question_id"])][x["letter"]] += 1
    cells = {}
    for tg, rr in by.items():
        e = exp.get(tg, {})
        mode, eng, pol, cond, lev = e.get("mode"), e.get("engine"), e.get("policy"), e.get("cond"), e.get("lev")
        ep = [x for x in rr if x["kind"] == "episodic" and x["in_window"]]
        tt = [x["ttft_s"] for x in ep if x["ttft_s"] is not None]
        cold = [x for x in rr if x["kind"] == "cold_recall" and x["in_window"]]
        ww = [x for x in wby[tg] if x["in_window"]]
        app = [x for x in ww if x["kind"] == "recall_append"]
        esc = [x for x in ww if x["kind"] == "recall_escalation"]
        t0s = [x["t_sched_abs"] - x["t_sched"] for x in rr if x["kind"] == "cold_recall" and x.get("t_sched_abs")]
        t0 = float(np.median(t0s)) if t0s else None
        cold_iv = [(s["t_send"] - t0, s["t_send"] - t0 + s["latency_s"]) for s in sby[tg]
                   if t0 is not None and s.get("t_send") and s.get("latency_s") is not None]
        warm_iv = [(x["kind"].replace("recall_", ""), x["t_submit"], x["t_end"]) for x in rr
                   if x["kind"].startswith("recall_") and x["kind"] != "recall_warmup"
                   and x.get("t_submit") is not None and x.get("t_end") is not None]
        # bunching over background units (cold slices + warm appends / escalations), window only
        w0 = e.get("window_start") or 0.0
        bg = sorted([(a, b) for a, b in cold_iv] + [(a, b) for _, a, b in warm_iv])
        bg_w = [(a, b) for a, b in bg if a >= w0 + disc]
        subs = [a for a, _ in bg_w]
        within50 = sum(1 for i, a in enumerate(subs) if (i > 0 and a - subs[i - 1] < 0.05)
                       or (i + 1 < len(subs) and subs[i + 1] - a < 0.05))
        # concurrency with a 5-ms tolerance: row times are rounded to 1 ms, so back-to-back units can appear to overlap
        ev = sorted([(a, 1) for a, _ in bg_w] + [(b - 0.005, -1) for _, b in bg_w])
        conc = mx = 0
        for _, d in ev:
            conc += d
            mx = max(mx, conc)
        over = [x for x in ep if x["ttft_s"] is not None and x["ttft_s"] > BUDGET]
        ov = Counter("+".join(overlaps(x, cold_iv, warm_iv)) for x in over)
        lc = []
        for x in esc:
            c = ref.get((mode, eng, cond, x["device"], x["session"], x["question_id"])) if pol != "P0" else None
            if not c:
                c = pc_ref.get(("C4a" if cond == "C4" else cond, x["device"], x["session"], x["question_id"])) \
                    if pol != "P0" else None
            if c and x.get("letter") is not None:
                lc.append(x["letter"] == c.most_common(1)[0][0])
        lu = [x for x in lby[tg] if x.get("type") == "unit"]
        lsum = next((x for x in lby[tg] if x.get("type") == "summary"), None)
        perr = defaultdict(list)
        for x in lu:
            if x.get("meas_s") is not None and x.get("pred_s") is not None and x["in_window"]:
                perr[x["kind"]].append(x["meas_s"] - x["pred_s"])
        qlens = [q for t, q, i in (lsum or {}).get("qlog", []) if t >= w0 + disc]
        jit = [x.get("jitter_s") for x in ep if x.get("jitter_s") is not None]
        perr_arr = [x["t_sched"] - (x["predicted_arrival_s"] + (e.get("window_start") or 0))
                    for x in ep if x.get("predicted_arrival_s") is not None]
        tta = [x["t_answer_s"] for x in esc]
        cells[tg] = dict(
            mode=mode, engine=eng, policy=pol, cond=cond, lev=lev, frac=e.get("frac"), margin=e.get("margin"),
            jitter_p90=e.get("jitter_p90"), episodic_n=len(ep), episodic_errors=sum(bool(x["error"]) for x in ep),
            p50=pct(tt, 50), p90=pct(tt, 90), p99=pct(tt, 99),
            meets_budget=bool(tt) and len(tt) == len(ep) and pct(tt, 99) <= BUDGET and not any(x["error"] for x in ep),
            cold_n=len(cold), cold_t_answer=[x["ttft_s"] for x in cold],
            cold_meets_10s=sum(bool(x.get("meets_10s")) for x in cold), cold_meets_5s=sum(bool(x.get("meets_5s")) for x in cold),
            cold_letters_equal=sum(bool(x.get("letter_equal")) for x in cold),
            cold_first_cached_max=max((x["first_cached"] or 0 for x in cold), default=None),
            cold_gap_max=max((x["gap_max"] or 0 for x in cold), default=None),
            cold_computed_median=pct([x.get("computed_tokens") for x in cold], 50),
            cold_released_by=dict(Counter(rb for x in cold for rb in (x.get("released_by") or []) if rb)),
            appends=len(app), appends_coalesced=sum(bool(x.get("coalesced")) for x in app),
            appends_absorbed=sum(bool(x.get("absorbed")) for x in app),
            append_held_p50=pct([x["held_s"] for x in app if x.get("held_s") is not None and not x.get("coalesced")
                                 and not x.get("absorbed")], 50),
            append_held_max=max((x["held_s"] for x in app if x.get("held_s") is not None and not x.get("coalesced")
                                 and not x.get("absorbed")), default=None),
            releases=dict(Counter(x.get("release") for x in app + esc)),
            escalations=len(esc), esc_t_answer=tta,
            esc_within_1s=frac_ok(esc, lambda x: (x["t_answer_s"] or 1e9) <= 1),
            esc_within_2s=frac_ok(esc, lambda x: (x["t_answer_s"] or 1e9) <= 2),
            esc_within_5s=frac_ok(esc, lambda x: (x["t_answer_s"] or 1e9) <= 5),
            esc_t_answer_p50=pct(tta, 50), esc_t_answer_p90=pct(tta, 90),
            staleness_p50=pct([x.get("stale_frames") for x in esc], 50),
            staleness_max=max((x.get("stale_frames") or 0 for x in esc), default=None),
            esc_letters_compared=len(lc), esc_letters_equal=sum(lc),
            warm_computed=sum(x["computed_tokens"] or 0 for x in ww),
            warm_errors=sum(bool(x.get("error")) for x in wby[tg]),
            bg_units=len(bg_w), bg_within_50ms=within50, bg_max_concurrent=mx,
            lane=None if lsum is None else dict(
                max_inflight=lsum["max_inflight"], violations=lsum["violations"], occupancy=lsum["occupancy_window"],
                units=lsum["units"], dropped=lsum["dropped"], ewma_final=lsum["ewma_final"],
                qlen_p50=pct(qlens, 50), qlen_p90=pct(qlens, 90), qlen_max=max(qlens, default=None),
                hold_p50=pct([x["hold_s"] for x in lu if x["in_window"] and x["hold_s"] is not None and not x["dropped"]], 50),
                hold_p90=pct([x["hold_s"] for x in lu if x["in_window"] and x["hold_s"] is not None and not x["dropped"]], 90),
                reasons=dict(Counter(x["reason"] for x in lu if x["in_window"] and x["reason"])),
                dropped_by=dict(Counter(x["dropped"] for x in lu if x["dropped"])),
                pred_err={k: dict(n=len(v), p50=pct(v, 50), p90=pct(v, 90)) for k, v in perr.items()}),
            over_budget=len(over), over_budget_overlap=dict(ov),
            cold_unanswered=sum(x.get("ttft_s") is None for x in cold),
            esc_unanswered=sum(x.get("t_answer_s") is None for x in esc),
            lane_never_released=sum(1 for x in lu if not x.get("reason") and not x.get("dropped")),
            lane_last_release_s=max((x["t_rel"] - w0 for x in lu if x.get("reason") and x.get("t_rel")), default=None),
            deadline_releases={k: sum(1 for x in lu if x.get("reason") == "deadline" and
                                      ("catchup" if x.get("catchup") else x["kind"]) == k)
                               for k in ("escalation", "catchup", "append")},
            slack_releases=sum(1 for x in lu if x.get("reason") == "slack"),
            catchup_units=sum(1 for x in ww if x.get("catchup")),
            catchup_per_esc=[x.get("catchup_units") for x in esc],
            esc_pred_before=[x.get("pred_before_s") for x in esc],
            esc_pred_after=[x.get("pred_s") for x in esc],
            absorbed_catchup=sum(bool(x.get("absorbed_catchup")) for x in app),
            jitter_obs_p50=pct(jit, 50), jitter_obs_p90=pct(jit, 90),
            arrival_minus_predicted_p5_p50_p95=[pct(perr_arr, 5), pct(perr_arr, 50), pct(perr_arr, 95)] if perr_arr else None)
    # capacity tables
    table = defaultdict(dict)
    for key in sorted({(c["mode"], c["engine"], c["cond"], c["policy"]) for c in cells.values()}, key=str):
        mode, eng, cond, pol = key
        cs = sorted([c for c in cells.values() if (c["mode"], c["engine"], c["cond"], c["policy"]) == key],
                    key=lambda c: c["lev"])
        levels = LADDER if mode == "a" else STREAMS
        cap = None
        for c in cs:
            if not c["meets_budget"]:
                break
            cap = c["lev"]
        failed = any(not c["meets_budget"] for c in cs)
        single = len(cs) == 1 and cs[0]["lev"] != levels[0]
        tta = [t for c in cs for t in c["cold_t_answer"]]
        n = sum(c["cold_n"] for c in cs)
        esc = [t for c in cs for t in c["esc_t_answer"]]
        degenerate = key in DEGENERATE
        label = "DEGENERATE (lane deadlock; no capacity figure)" if degenerate else \
            (("< " + lev_name(mode, levels[0]) if cap is None else lev_name(mode, cap))
                 + ("" if failed else " (ladder top, not failed)")) if not single else \
            f"single cell {lev_name(mode, cs[0]['lev'])}: {'meets' if cs[0]['meets_budget'] else 'fails'}"
        table[f"{mode}/{eng}/{cond}"][pol] = dict(
            capacity=label, capacity_lev=None if degenerate else (cap or 0), ladder=not single and not degenerate,
            degenerate=degenerate,
            starvation=dict(cold_unanswered=sum(c["cold_unanswered"] for c in cs),
                            esc_unanswered=sum(c["esc_unanswered"] for c in cs),
                            lane_never_released=sum(c["lane_never_released"] for c in cs),
                            lane_last_release_s=[c["lane_last_release_s"] for c in cs]),
            deadline_releases=dict(sum((Counter(c["deadline_releases"]) for c in cs), Counter())),
            catchup_units=sum(c["catchup_units"] for c in cs),
            catchup_per_esc_p50=pct([v for c in cs for v in c["catchup_per_esc"]], 50),
            catchup_per_esc_max=max((v or 0 for c in cs for v in c["catchup_per_esc"]), default=None),
            esc_pred_before_p50=pct([v for c in cs for v in c["esc_pred_before"]], 50),
            esc_pred_after_p50=pct([v for c in cs for v in c["esc_pred_after"]], 50),
            capacity_frac=None if degenerate else ((cap or 0.0) if mode == "a" else (round((cap or 0) / CAD / PEAK, 4))),
            cells=[dict(lev=c["lev"], p50=c["p50"], p90=c["p90"], p99=c["p99"], meets=c["meets_budget"],
                        cold_n=c["cold_n"], escalations=c["escalations"], over_budget=c["over_budget"],
                        overlap=c["over_budget_overlap"], bg_within_50ms=c["bg_within_50ms"],
                        bg_max_concurrent=c["bg_max_concurrent"], lane=c["lane"]) for c in cs],
            recalls=n, frac_10s=(sum(c["cold_meets_10s"] for c in cs) / n) if n else None,
            frac_5s=(sum(c["cold_meets_5s"] for c in cs) / n) if n else None,
            t_answer_p50=pct(tta, 50), t_answer_p90=pct(tta, 90),
            t_answer_max=max((t for t in tta if t is not None), default=None),
            cold_letters_equal=sum(c["cold_letters_equal"] for c in cs),
            escalations=len(esc), esc_within_5s=(sum(t is not None and t <= 5 for t in esc) / len(esc)) if esc else None,
            esc_within_1s=(sum(t is not None and t <= 1 for t in esc) / len(esc)) if esc else None,
            esc_t_answer_p50=pct(esc, 50), esc_t_answer_p90=pct(esc, 90),
            esc_letters_equal=sum(c["esc_letters_equal"] for c in cs),
            esc_letters_compared=sum(c["esc_letters_compared"] for c in cs),
            appends=sum(c["appends"] for c in cs), coalesced=sum(c["appends_coalesced"] for c in cs),
            absorbed=sum(c["appends_absorbed"] for c in cs))
    decision = decide(table, cells)
    res = dict(label="StudySLICE1 Part D: one background lane (P6) under the known schedule (D-a) and cadence-only "
                     "streams (D-b, jitter half-normal p90 0.044 s ASSUMED), 32B-I vLLM 0.31.0 (E0 / E10e P1), H100 GPU 2",
               cells=cells, table=table, decision=decision, drift_check=meta.get("drift_check"),
               guard_stop=meta.get("guard_stop"), void=meta.get("void"), servers=len(meta.get("servers", [])),
               servers_flags_verified=sum(bool(s.get("flags_verified")) for s in meta.get("servers", [])))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_slice1_partd_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / f"{prefix}_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, d in table.items():
        for pol, t in d.items():
            print(k, pol, t["capacity"], "| rec", t["recalls"], "10s", t["frac_10s"] and round(t["frac_10s"], 3),
                  "| esc", t["escalations"], "5s", t["esc_within_5s"] and round(t["esc_within_5s"], 3),
                  "| coal", t["coalesced"], "abs", t["absorbed"], "|",
                  [(c["lev"], c["p99"], c["meets"], c["bg_max_concurrent"], c["bg_within_50ms"]) for c in t["cells"]])
    print("decision", json.dumps(decision, indent=1, default=str))


def decide(table, cells):
    d = {}
    for pol in ("P6", "P6b"):
        t = table.get("a/E0/C4a", {}).get(pol)
        if t:
            cap = t["capacity_frac"] or 0.0
            d[f"D1_C4a_{pol}"] = dict(capacity=t["capacity"], cold_frac_10s=t["frac_10s"], esc_frac_5s=t["esc_within_5s"],
                                      restores=bool(cap >= 0.20 and (t["frac_10s"] or 0) >= 0.90
                                                    and (t["esc_within_5s"] or 0) >= 0.90))
    for pol in ("P6_1024", "P6"):
        t = table.get("a/E0/C1b", {}).get(pol)
        if t:
            d[f"C1b_{pol}"] = dict(capacity=t["capacity"], frac_10s=t["frac_10s"],
                                   meets_rule=bool(t["capacity_frac"] >= 0.30 and (t["frac_10s"] or 0) >= 0.90))
    p6 = [c for c in cells.values() if c["policy"] in ("P6", "P6_1024", "P6b") and c["lane"]]
    d["mechanism_single_lane"] = dict(cells=len(p6), max_inflight=max((c["lane"]["max_inflight"] for c in p6), default=None),
                                      violations=sum(c["lane"]["violations"] for c in p6),
                                      ok=all(c["lane"]["max_inflight"] <= 1 and not c["lane"]["violations"] for c in p6))
    known = known_schedule()
    for k, dd in table.items():
        mode, eng, cond = k.split("/")
        if mode == "a" and eng == "E0":
            for pol, t in dd.items():
                if t["ladder"]:
                    known[(eng, cond, pol)] = (t["capacity_frac"], "Part D-a")
                    if pol == "P6":
                        known.setdefault((eng, cond, "P6b"), (None, "not run under D-a"))
    d2 = []
    for k, dd in sorted(table.items()):
        mode, eng, cond = k.split("/")
        if mode == "a":
            continue
        for pol, t in dd.items():
            kn = known.get((eng, cond, pol))
            ks = to_streams(kn[0]) if kn and kn[0] is not None else None
            d2.append(dict(mode=mode, engine=eng, cond=cond, policy=pol, cadence_capacity_streams=t["capacity_lev"],
                           cadence_capacity_label=t["capacity"],
                           known_capacity_frac=kn[0] if kn else None, known_source=kn[1] if kn else None,
                           known_capacity_streams=ks,
                           loss_streams=(ks - t["capacity_lev"]) if ks is not None and t["capacity_lev"] is not None
                           else None, degenerate=t.get("degenerate", False)))
    d["D2"] = d2
    return d


if __name__ == "__main__":
    main(*(sys.argv[1:2] or []))
