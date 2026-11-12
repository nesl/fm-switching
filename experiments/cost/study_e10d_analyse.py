#!/usr/bin/env python3
"""StudyE10d-blocking analysis (CPU). Per cell: episodic p50 / p99 TTFT from the scheduled arrival (E10b / E10c
statistic), blocks = p99 > budget. Cold phases per request (client send, 'Received request' = rendered, 'Added request'
= engine arrival, first token). E10c section-6 analysis: slow episodic requests (TTFT > budget) submitted inside a cold
request's window [cold send, cold first token], their release (first token) relative to the cold first token, and
their submit time relative to the cold engine arrival. Idle phase medians per variant (server log + per-request
histogram deltas; logs re-parsed here) and the encoder-reuse test. Writes results/cost/study_e10/e10d_results.json."""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_e10"
BUDGET = 0.45
PAT = re.compile(r"E10D_(E\d)_(V\d)_N1_L(\d+)")
LOGLINE = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{3}) .*?(Received request|Added request) "
                     r"chatcmpl-(e10d-[\w-]+)")


def pct(xs, q):
    xs = [x for x in xs if x is not None]
    return float(np.percentile(xs, q)) if xs else None


def log_times(path):
    out = {}
    for line in Path(path).read_text(errors="replace").splitlines():
        m = LOGLINE.search(line)
        if m:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() + int(m.group(2)) / 1000
            out.setdefault(m.group(4), {}).setdefault("received" if m.group(3)[0] == "R" else "added", ts)
    return out


def match(times, rid):
    out = {}
    for k, v in times.items():
        if k == rid or k.startswith(rid + "-"):
            for kk, t in v.items():
                out.setdefault(kk, t)
    return out


def cell_stats(rs, cold):
    ep = [r for r in rs if r["kind"] == "episodic" and r["in_window"]]
    lat = [r["ttft_s"] for r in ep if not r["error"] and r["ttft_s"] is not None]
    nbad = len(ep) - len(lat)
    allv = lat + [float("inf")] * nbad
    p99 = float(np.percentile(allv, 99)) if nbad == 0 else float(np.percentile(allv, 99, method="higher"))
    c = dict(episodic_n=len(ep), episodic_errors=nbad, p50=pct(lat, 50), p90=pct(lat, 90), p99=p99,
             blocks=p99 > BUDGET)
    cw = [x for x in cold if x["t_first_abs"]]
    cin = [x for x in cold if x["in_window"]]
    c["cold"] = dict(n=len(cold), in_window=len(cin), errors=sum(bool(x["error"]) for x in cold),
                     logged=sum(bool(x["t_added_abs"]) for x in cold),
                     body_mb=pct([x["body_mb"] for x in cold], 50),
                     prompt_tokens_equal_expected=sum(x["prompt_tokens"] == x["expected_prompt_tokens"] for x in cold),
                     cached_tokens_max=max((x["cached_tokens"] or 0) for x in cold) if cold else None,
                     frontend_s_p50=pct([x["frontend_s"] for x in cold], 50),
                     frontend_s_max=max((x["frontend_s"] for x in cold if x["frontend_s"] is not None), default=None),
                     render_s_p50=pct([x["render_s"] for x in cold], 50),
                     added_to_first_s_p50=pct([x["added_to_first_s"] for x in cold], 50),
                     ttft_p50=pct([x["ttft_s"] for x in cold], 50), ttft_p99=pct([x["ttft_s"] for x in cin], 99))
    slow = [r for r in ep if r["ttft_s"] is not None and r["ttft_s"] > BUDGET]
    inside, rel_first, rel_added, rel_sent = 0, [], [], []
    for r in slow:
        s = r["t_sched_abs"] + r["dispatch_late_s"]
        hits = [x for x in cw if x["t_sent_abs"] <= s <= x["t_first_abs"]]
        if hits:
            inside += 1
            first = r["t_sched_abs"] + r["ttft_s"]
            x = min(hits, key=lambda x: abs(x["t_first_abs"] - first))
            rel_first.append(first - x["t_first_abs"])
            rel_sent.append(s - x["t_sent_abs"])
            if x["t_added_abs"]:
                rel_added.append(s - x["t_added_abs"])
    # unaffected episodic requests submitted between cold send and cold engine arrival (frontend phase)
    fe_ok = fe_n = 0
    for x in cw:
        if not x["t_added_abs"]:
            continue
        for r in ep:
            s = r["t_sched_abs"] + r["dispatch_late_s"]
            if x["t_sent_abs"] <= s and s + (r["ttft_s"] or 99) <= x["t_added_abs"]:
                fe_n += 1
                fe_ok += r["ttft_s"] is not None and r["ttft_s"] <= BUDGET
    c["hold"] = dict(slow=len(slow), slow_inside_cold_window=inside,
                     release_minus_cold_first_p10=pct(rel_first, 10), release_minus_cold_first_p50=pct(rel_first, 50),
                     release_minus_cold_first_p90=pct(rel_first, 90),
                     slow_submit_minus_cold_added_min=min(rel_added) if rel_added else None,
                     slow_submit_minus_cold_added_p50=pct(rel_added, 50),
                     slow_submit_minus_cold_sent_min=min(rel_sent) if rel_sent else None,
                     episodic_completed_during_cold_frontend=fe_n, of_which_within_budget=fe_ok)
    # episodic submitted in the cold frontend phase [cold sent, cold added - 0.2 s]: how many, how many slow;
    # and slow episodic submitted inside a window more than 0.2 s before that cold request's engine arrival
    fp_n = fp_slow = slow_pre = 0
    for x in cw:
        if not x["t_added_abs"]:
            continue
        for r in ep:
            s = r["t_sched_abs"] + r["dispatch_late_s"]
            if r["ttft_s"] is not None and x["t_sent_abs"] <= s < x["t_added_abs"] - 0.2:
                fp_n += 1
                fp_slow += r["ttft_s"] > BUDGET
    for r in slow:
        s = r["t_sched_abs"] + r["dispatch_late_s"]
        for x in cw:
            if x["t_added_abs"] and x["t_sent_abs"] <= s <= x["t_first_abs"]:
                slow_pre += s < x["t_added_abs"] - 0.2
                break
    c["hold"].update(submitted_in_cold_frontend_phase=fp_n, of_which_slow=fp_slow,
                     slow_submitted_over_0p2s_before_cold_added=slow_pre)
    # Step 3 trace: the cold request (in window, logged) with most episodic arrivals during its engine phase
    cand = [x for x in cw if x["in_window"] and x["t_added_abs"]]
    if cand:
        def n_eng(x):
            return sum(1 for r in ep if x["t_added_abs"] <= r["t_sched_abs"] + r["dispatch_late_s"] <= x["t_first_abs"])
        x = max(cand, key=n_eng)
        t0 = x["t_sent_abs"]
        tr = dict(received=x["t_received_abs"] - t0 if x.get("t_received_abs") else None,
                  added=x["t_added_abs"] - t0, first=x["t_first_abs"] - t0, episodic=[])
        for r in ep:
            s = r["t_sched_abs"] + r["dispatch_late_s"]
            if r["ttft_s"] is not None and t0 - 0.5 <= s <= x["t_first_abs"] + 0.5:
                tr["episodic"].append(dict(submit=round(s - t0, 3), ttft=round(r["ttft_s"], 3),
                                           release_minus_cold_first=round(r["t_sched_abs"] + r["ttft_s"] - x["t_first_abs"], 3)))
        c["trace"] = tr
    return c


def idle_rows(path, logs):
    rows = [json.loads(l) for l in open(path)]
    lt = {}
    for p in logs:
        lt.update(log_times(p))
    for r in rows:
        m = match(lt, r["vllm_request_id"])
        r["t_received_abs"], r["t_added_abs"] = m.get("received"), m.get("added")
        s = r["t_sent_abs"]
        r["render_s"] = m["received"] - s if m.get("received") else None
        r["frontend_s"] = m["added"] - s if m.get("added") else None
        r["added_to_first_s"] = r["t_first_abs"] - m["added"] if m.get("added") and r["t_first_abs"] else None
    return rows


def main():
    meta = json.load(open(OUT / "e10d_run_meta_h100nvl.json"))
    srv = {s["label"]: s["log"] for s in meta["servers"]}
    rows = [json.loads(l) for l in open(OUT / "e10d_requests_h100nvl.jsonl")]
    cold = [json.loads(l) for l in open(OUT / "e10d_cold_phases_h100nvl.jsonl")]
    by, cby = defaultdict(list), defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    for x in cold:
        cby[x["cell"]].append(x)
    cells = {}
    for tg in meta["done"]:
        e, v, lv = PAT.match(tg).groups()
        cells[tg] = dict(engine=e, variant=v, frac=int(lv) / 100, **cell_stats(by[tg], cby[tg]),
                         harness_summary=meta["experiments"][tg]["summary"])
    idle = idle_rows(OUT / "e10d_idle_h100nvl.jsonl", [srv["E0_idle"]])
    iv = {}
    for v in sorted({r["variant"] for r in idle}):
        rr = [r for r in idle if r["variant"] == v]
        iv[v] = {k: pct([r.get(k) for r in rr], 50) for k in (
            "body_mb", "render_s", "frontend_s", "request_queue_time_s", "request_prefill_time_s", "added_to_first_s",
            "time_to_first_token_s", "service_ttft_s", "prompt_tokens")}
        iv[v]["n"] = len(rr)
        iv[v]["prefill_all"] = [r["request_prefill_time_s"] for r in rr]
        iv[v]["frontend_all"] = [round(r["frontend_s"], 3) if r["frontend_s"] is not None else None for r in rr]
        iv[v]["cached_tokens_max"] = max((r["cached_tokens"] or 0) for r in rr)
    reuse = idle_rows(OUT / "e10d_reuse_h100nvl.jsonl", [srv["E0_reuse"]])
    ru = defaultdict(dict)
    for r in reuse:
        ru[r["request_id"]][r["step"]] = dict(prefill=r["request_prefill_time_s"], frontend=r["frontend_s"],
                                              service_ttft=r["service_ttft_s"],
                                              mm_cache_hits=r["metric_delta"].get("mm_cache_hits_total"),
                                              prompt_tokens=r["prompt_tokens"], cached=r["cached_tokens"])
    a1 = [v["A1"]["prefill"] for v in ru.values()]
    a2 = [v["A2"]["prefill"] for v in ru.values()]
    a3 = [v["A3"]["prefill"] for v in ru.values()]
    enc_v1_v3 = (iv["V1"]["request_prefill_time_s"] or 0) - (iv["V3"]["request_prefill_time_s"] or 0)
    reuse_sum = dict(per_question=ru, prefill_A1_p50=pct(a1, 50), prefill_A2_p50=pct(a2, 50), prefill_A3_p50=pct(a3, 50),
                     encoder_saving_A1_minus_A2_p50=pct([x - y for x, y in zip(a1, a2)], 50),
                     saving_A1_minus_A3_p50=pct([x - y for x, y in zip(a1, a3)], 50),
                     encoder_estimate_V1_minus_V3_idle=enc_v1_v3,
                     reused_immediately=all(y < x - 0.5 * enc_v1_v3 for x, y in zip(a1, a2)),
                     survives_20_episodic=all(z < x - 0.5 * enc_v1_v3 for x, z in zip(a1, a3)))
    verdict = {}
    for e in ("E0", "E2"):
        verdict[e] = {v: cells.get(f"E10D_{e}_{v}_N1_L10", {}).get("blocks") for v in ("V1", "V2", "V3")}
    res = dict(label="StudyE10d-blocking: cold-request variants vs episodic hold, 32B-I, one replica, H100 GPU 2 "
                     "(vLLM 0.31.0, prefix caching ON, C1 KV-GPU k 0 r 0.05, N = 1)", cells=cells, idle=iv,
               reuse=reuse_sum, control=meta.get("control"), v3=meta.get("v3"), void=meta.get("void"),
               blocks_at_10pct=verdict)
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10d_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / "e10d_results.json").write_text(json.dumps(res, indent=1, default=float))
    for tg, c in cells.items():
        h, cd = c["hold"], c["cold"]
        print(tg, f"p50 {c['p50']:.3f} p99 {c['p99']:.3f} blocks {c['blocks']} | cold body {cd['body_mb']} MB fe {cd['frontend_s_p50']} "
              f"eng {cd['added_to_first_s_p50']} ttft {cd['ttft_p50']} tok {cd['prompt_tokens_equal_expected']}/{cd['n']} | slow "
              f"{h['slow']} inside {h['slow_inside_cold_window']} rel_first p50 {h['release_minus_cold_first_p50']} "
              f"rel_added min {h['slow_submit_minus_cold_added_min']} fe-phase ok {h['of_which_within_budget']}/"
              f"{h['episodic_completed_during_cold_frontend']} | fe-phase n {h['submitted_in_cold_frontend_phase']} slow "
              f"{h['of_which_slow']} slow_pre {h['slow_submitted_over_0p2s_before_cold_added']}")
    print("idle", json.dumps({v: {k: x for k, x in d.items() if not k.endswith("_all")} for v, d in iv.items()}))
    print("reuse", json.dumps({k: v for k, v in reuse_sum.items() if k != "per_question"}))
    print("blocks@10%", verdict, "control", meta.get("control"))


if __name__ == "__main__":
    main()
