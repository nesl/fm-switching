#!/usr/bin/env python3
"""StudyD10 analysis (CPU; run AFTER the D10 run ends). Per load x benchmark: TTFT, total latency, time to </think>,
prompt / completion tokens (p50, p90, max), runaways, GPU-2 SM clock during each request, neighbour flags.
Neighbour flag (StudyClean rule): a >= 50-point SM-utilisation step on any OTHER GPU between consecutive 1-s
`nvidia-smi dmon -o DT` samples within [start - 1 s, end + 1 s]; flagged requests are reported, never dropped.
Warm-up requests (first after each model load) are excluded from the statistics and listed. VOID status from the
run's isolation record (any work of ours outside the run's session at any check -> VOID).
Writes results/cost/study_d10/study_d10_results_h100nvl.json.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

D = Path("results/cost/study_d10")
REQ = D / "study_d10_requests_h100nvl.jsonl"
META = D / "study_d10_run_meta_h100nvl.json"
ISO = D / "study_d10_isolation_h100nvl.jsonl"
DMON = Path("logs/study_d10_dmon.log")
OUT = D / "study_d10_results_h100nvl.json"
OWN_GPU = 2
SHARP = 50


def steps():
    prev, out = {}, {}
    if not DMON.exists():
        return out
    for line in DMON.read_text().splitlines():
        f = line.split()
        if not f or f[0].startswith("#") or len(f) < 4:
            continue
        try:
            ts = int(datetime.strptime(f"{f[0]} {f[1]}", "%Y%m%d %H:%M:%S").timestamp())
            g, sm = int(f[2]), f[3]
        except ValueError:
            continue
        if g == OWN_GPU or sm == "-":
            continue
        sm = int(sm)
        if g in prev:
            out[ts] = max(out.get(ts, 0), abs(sm - prev[g]))
        prev[g] = sm
    return out


def q(x):
    x = [v for v in x if v is not None]
    if not x:
        return None
    return dict(n=len(x), p50=float(np.percentile(x, 50)), p90=float(np.percentile(x, 90)), max=float(max(x)),
                min=float(min(x)))


def main():
    rows = [json.loads(l) for l in open(REQ)]
    st = steps()
    for r in rows:
        a, b = int(r["wall_start"]) - 1, int(r["wall_end"]) + 1
        r["neighbour_step_max"] = max([st.get(t, 0) for t in range(a, b + 1)] or [0])
        r["neighbour_flag"] = r["neighbour_step_max"] >= SHARP
    meas = [r for r in rows if not r["warmup"]]
    iso = [json.loads(l) for l in open(ISO)]
    meta = json.load(open(META))
    res = dict(void=any(i["overlap"] for i in iso if i["tag"] != "pre-start wait"),
               isolation_checks=len([i for i in iso if i["tag"] != "pre-start wait"]),
               isolation_overlaps=[i for i in iso if i["overlap"] and i["tag"] != "pre-start wait"],
               cache_checks=meta.get("cache_checks"), errors=sum(bool(r["error"]) for r in meas),
               warmups=[dict(load=r["load"], bench=r["bench"], qid=r["qid"], ttft_s=r["ttft_s"], total_s=r["total_s"])
                        for r in rows if r["warmup"]],
               conditions="h100nvl GPU 2, shared host (other users on other GPUs), localhost, one request at a time, "
                          "prefix caching off, processor cache off, bodies pre-serialised; first request per load "
                          "discarded", cells={})
    for load in ("sember_T", "images_T", "images_I"):
        for bench in ("sember", "erqa", "mvrb"):
            rs = [r for r in meas if r["load"] == load and r["bench"] == bench]
            if not rs:
                continue
            ok = [r for r in rs if not r["error"]]
            res["cells"][f"{load}/{bench}"] = dict(
                n=len(rs), errors=len(rs) - len(ok), ttft_s=q([r["ttft_s"] for r in ok]),
                total_s=q([r["total_s"] for r in ok]), time_to_think_end_s=q([r.get("time_to_think_end_s") for r in ok]),
                prompt_tokens=q([r["prompt_tokens"] for r in ok]), completion_tokens=q([r["completion_tokens"] for r in ok]),
                runaways=sum(r["runaway"] for r in ok), think_closed=sum(bool(r["think_closed"]) for r in ok)
                if load.endswith("_T") else None,
                sm_mhz_median=q([r["gpu2"].get("sm_mhz_median") for r in ok]),
                sm_mhz_min=min([r["gpu2"].get("sm_mhz_min") for r in ok if r["gpu2"].get("sm_mhz_min")] or [None]),
                n_neighbour_flagged=sum(r["neighbour_flag"] for r in ok),
                flagged=[r["qid"] for r in ok if r["neighbour_flag"]],
                ttft_s_unflagged=q([r["ttft_s"] for r in ok if not r["neighbour_flag"]]),
                total_s_unflagged=q([r["total_s"] for r in ok if not r["neighbour_flag"]]),
                acc_indicative=float(np.mean([r["correct"] for r in ok])) if ok else None,
                decode_tok_per_s=q([(r["completion_tokens"] - 1) / (r["total_s"] - r["ttft_s"]) for r in ok
                                    if r["completion_tokens"] and r["completion_tokens"] > 1 and r["ttft_s"]
                                    and r["total_s"] > r["ttft_s"]]),
                prefill_tok_per_s=q([r["prompt_tokens"] / r["ttft_s"] for r in ok if r["ttft_s"]]))
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d10_analyse.py", model="32BT,32BI", device="cpu", n=len(meas))
    OUT.write_text(json.dumps(res, indent=1, default=float))
    print("VOID" if res["void"] else "not void", "errors", res["errors"])
    for k, v in res["cells"].items():
        print(k, v["n"], "ttft p50", round(v["ttft_s"]["p50"], 3), "total p50/p90/max", round(v["total_s"]["p50"], 2),
              round(v["total_s"]["p90"], 2), round(v["total_s"]["max"], 2), "ctok p50/max", v["completion_tokens"]["p50"],
              v["completion_tokens"]["max"], "runaways", v["runaways"], "flagged", v["n_neighbour_flagged"])


if __name__ == "__main__":
    main()
