#!/usr/bin/env python3
"""StudyE10c-engine analysis (CPU). Same per-cell statistics as study_e10b_analyse (episodic in-window TTFT from the
scheduled arrival, linear p99 as D7 — nearest-rank with unfinished = inf when any are unfinished; recall append /
escalation / cold TTFT; warm misses; window /metrics and Sampler averages). Per (engine, condition, N): capacity =
highest level of the bottom-up ladder meeting the budget. Restoration: capacity under C1-C4 vs the same engine's C0
and vs E0's C0. Recall cost flags: any recall-class p99 > 10 s, any request unfinished at the drain cap. Control: E0 C0
N1 25 % and N3 50 % vs E10b's KV-GPU baseline p99 (within 2x). Writes results/cost/study_e10/e10c_results.json."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "experiments/lib"))
import study_e10b_analyse as B  # noqa: E402

OUT = B.OUT
PEAK, BUDGET = B.PEAK, B.BUDGET
LEVELS = {1: (0.10, 0.20, 0.25, 0.30, 0.40, 0.50), 3: (0.10, 0.20, 0.25, 0.35, 0.50)}
E10B_CTRL = {(1, 0.25): "E10B_KVGPU_k0_r0_N1_L25", (3, 0.5): "E10B_KVGPU_k0_r0_N3_L50"}
PAT = re.compile(r"E10C_(E\d)_(C\d)_N(\d)_L(\d+)")


def cell_stats(rs, met, cpu):
    ep = [r for r in rs if r["kind"] == "episodic" and r["in_window"]]
    ok = [r for r in ep if not r["error"]]
    lat = [r["ttft_s"] for r in ok if r["ttft_s"] is not None]
    n_bad = len(ep) - len(lat)
    lat_all = lat + [float("inf")] * n_bad
    p99 = (float(np.percentile(lat_all, 99)) if n_bad == 0 else float(np.percentile(lat_all, 99, method="higher"))) if lat_all else None
    N = rs[0]["N"]
    c = dict(episodic_n=len(ep), episodic_errors=n_bad, error_types=dict(Counter(str(r["error"])[:60] for r in ep if r["error"])),
             p50=B.pct(lat, 50), p90=B.pct(lat, 90), p99=p99,
             p99_nearest_rank=float(np.percentile(lat_all, 99, method="higher")) if lat_all else None,
             dispatch_late_p99=B.pct([r["dispatch_late_s"] for r in ep], 99), meets_budget=p99 is not None and p99 <= BUDGET[N])
    for kind in ("recall_append", "recall_escalation", "cold_recall"):
        k_rows = [r for r in rs if r["kind"] == kind and r.get("in_window")]
        kok = [r for r in k_rows if not r["error"] and r.get("ttft_s") is not None]
        unfinished = sum(1 for r in k_rows if r["error"] and "unfinished" in str(r["error"]))
        c[kind] = dict(n=len(k_rows), errors=len(k_rows) - len(kok), unfinished=unfinished,
                       ttft_p50=B.pct([r["ttft_s"] for r in kok], 50), ttft_p99=B.pct([r["ttft_s"] for r in kok], 99),
                       cached_frac_median=B.pct([(r["cached_tokens"] or 0) / max(r["prompt_tokens"] or 1, 1) for r in kok], 50))
    sess = defaultdict(list)
    for r in rs:
        if r["kind"] in ("recall_warmup", "recall_append", "recall_escalation") and not r["error"]:
            sess[(r["device"], r["session"], r["video_id"])].append(r)
    miss = tot = 0
    for v in sess.values():
        v.sort(key=lambda r: r["t_submit"])
        for prev, cur in zip(v, v[1:]):
            if cur.get("in_window"):
                tot += 1
                miss += (cur["cached_tokens"] or 0) < 0.5 * prev["prompt_tokens"]
    c["warm_followups"], c["warm_misses"] = tot, miss
    c["unfinished_any"] = sum(1 for r in rs if r.get("error") and "unfinished" in str(r["error"]))
    c["recall_p99_over_10s"] = [k for k in ("recall_append", "recall_escalation", "cold_recall")
                                if (c[k]["ttft_p99"] or 0) > 10]
    c["server"] = B.window_metrics(met, cpu) if met and cpu else {}
    return c


def main():
    rows = [json.loads(l) for l in open(OUT / "e10c_requests_h100nvl.jsonl")]
    mets = {m["cell"]: m for m in map(json.loads, open(OUT / "e10c_metrics_h100nvl.jsonl"))}
    cpus = {c["cell"]: c for c in map(json.loads, open(OUT / "e10c_cpu_h100nvl.jsonl"))}
    meta = json.load(open(OUT / "e10c_run_meta_h100nvl.json"))
    by = defaultdict(list)
    for r in rows:
        by[r["cell"]].append(r)
    cells = {}
    for tg in meta["done"]:
        e, cnd, n, lv = PAT.match(tg).groups()
        c = cell_stats(by[tg], mets.get(tg), cpus.get(tg))
        c.update(engine=e, cond=cnd, N=int(n), frac=int(lv) / 100, rate=int(lv) / 100 * PEAK[int(n)],
                 harness_meets_budget=meta["experiments"][tg]["summary"]["meets_budget"])
        cells[tg] = c
    cond = defaultdict(dict)
    for tg, c in cells.items():
        cond[(c["engine"], c["cond"], c["N"])][c["frac"]] = c
    cap = {}
    for (e, cn, n), lv in sorted(cond.items()):
        best = None
        for f in LEVELS[n]:
            if f in lv and lv[f]["meets_budget"]:
                best = f
            else:
                break
        top = max(lv)
        cap[f"{e}/{cn}/N{n}"] = dict(engine=e, cond=cn, N=n, levels_run=sorted(lv), capacity_frac=best,
                                     capacity_rps=best * PEAK[n] if best else 0.0,
                                     capacity_label=(f"{int(round(best * 100))} %" if best else "< 10 %") +
                                     (" (ladder top, not failed)" if best == top and lv[top]["meets_budget"] else ""),
                                     p99_by_level={str(f): lv[f]["p99"] for f in sorted(lv)})
    for k, v in cap.items():
        own = cap.get(f"{v['engine']}/C0/N{v['N']}")
        e0 = cap.get(f"E0/C0/N{v['N']}")
        v["restores_own_C0"] = None if not own or v["cond"] == "C0" else (v["capacity_frac"] or 0) >= (own["capacity_frac"] or 0)
        v["restores_E0_C0"] = None if not e0 or v["cond"] == "C0" else (v["capacity_frac"] or 0) >= (e0["capacity_frac"] or 0)
        v["vs_E0_same_cond"] = None
        e0c = cap.get(f"E0/{v['cond']}/N{v['N']}")
        if e0c and v["engine"] != "E0":
            v["vs_E0_same_cond"] = round(((v["capacity_frac"] or 0) - (e0c["capacity_frac"] or 0)) * PEAK[v["N"]], 3)
    b = json.load(open(OUT / "e10b_results.json"))["cells"]
    ctrl = []
    for (n, f), btg in E10B_CTRL.items():
        tg = f"E10C_E0_C0_N{n}_L{int(f * 100)}"
        if tg in cells:
            ratio = cells[tg]["p99"] / b[btg]["p99"]
            ctrl.append(dict(cell=tg, p99=cells[tg]["p99"], e10b_p99=b[btg]["p99"], ratio=ratio, within_2x=0.5 <= ratio <= 2.0,
                             p50=cells[tg]["p50"], e10b_p50=b[btg]["p50"]))
    servers = meta.get("servers", [])
    defaults = sorted({(s.get("engine"), s.get("log_max_num_batched_tokens"), s.get("log_chunked_prefill"),
                        s.get("log_scheduling_policy")) for s in servers if s.get("engine")}, key=str)
    res = dict(label="StudyE10c-engine: engine settings vs recall interference, 32B-I, one replica, H100 GPU 2 (vLLM 0.31.0, "
                     "prefix caching ON)", cells=cells, capacity=cap, control=ctrl,
               control_pass=bool(ctrl) and all(x["within_2x"] for x in ctrl), engine_server_settings=defaults,
               parity={k: v.get("passed") for k, v in meta.get("parity", {}).items()}, void=meta.get("void"))
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_e10c_analyse.py", model="32BI", device="cpu", n=len(rows))
    (OUT / "e10c_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in cap.items():
        print(k, v["capacity_label"], {f: round(p, 3) if p not in (None, float("inf")) else p for f, p in v["p99_by_level"].items()},
              "own", v["restores_own_C0"], "E0", v["restores_E0_C0"])
    print("control", ctrl)
    print("settings", defaults)


if __name__ == "__main__":
    main()
