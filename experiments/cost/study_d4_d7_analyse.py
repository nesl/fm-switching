#!/usr/bin/env python3
"""StudyD4-latency and StudyD7-capacity analysis (CPU; run after both runs end).

D4: per model x N (warm-ups excluded and listed): TTFT and total p50 / p90 / p99 / max, prompt tokens, request bytes
    (PNG as sent; JPEG q90 equivalent), image bytes, GPU-2 SM clock, errors; VOID from the isolation record (in-run
    checks only); other users' activity summary.
D7: per model x N x level: the run's own level summaries; derived streams per GPU for a stream evaluating every
    T in {1, 2, 5} s under p99 TTFT <= L in {1, 2, 5} s = (highest OPEN-LOOP achieved throughput among levels whose
    p99 TTFT <= L and errors + unfinished = 0) x T. Arithmetic for this input and server setup on localhost (no
    network); not a deployment claim. "< lowest tested level" when even the 25 % level misses L.
Writes results/cost/study_d4/study_d4_results_h100nvl.json and results/cost/study_d7/study_d7_results_h100nvl.json.
StudyD7b (N = 1; `d7b` argument): same D7 summary and formula on results/cost/study_d7b/study_d7b_*; both d7 and d7b
also count, per level, how many request ids recur within the level (the D3 manifest has 6,010 requests per N, so a
level above ~20 req/s over 300 s must cycle; caches are off, so a repeat is recomputed in full).
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

D4 = Path("results/cost/study_d4")
D7 = Path("results/cost/study_d7")


def q(x):
    x = [v for v in x if v is not None]
    if not x:
        return None
    return dict(n=len(x), p50=float(np.percentile(x, 50)), p90=float(np.percentile(x, 90)),
                p99=float(np.percentile(x, 99)), max=float(max(x)), min=float(min(x)))


def d4():
    rows = [json.loads(l) for l in open(D4 / "study_d4_requests_h100nvl.jsonl")]
    iso = [json.loads(l) for l in open(D4 / "study_d4_isolation_h100nvl.jsonl")]
    run = [i for i in iso if i["tag"] != "pre-start wait"]
    oth = [json.loads(l) for l in open(D4 / "study_d4_others_h100nvl.jsonl")] if (D4 / "study_d4_others_h100nvl.jsonl").exists() else []
    meta = json.load(open(D4 / "study_d4_run_meta_h100nvl.json"))
    res = dict(void=any(i["overlap"] for i in run), isolation_checks=len(run),
               warmups=[dict(model=r["model"], n=r["n"], ttft_s=r["ttft_s"], total_s=r["total_s"]) for r in rows if r["warmup"]],
               cache_checks=meta.get("cache_checks"), others=oth, cells={})
    for m in ("4BI", "32BI"):
        for n in (1, 3, 9):
            rs = [r for r in rows if r["model"] == m and r["n"] == n and not r["warmup"]]
            ok = [r for r in rs if not r["error"]]
            if not rs:
                continue
            res["cells"][f"{m}/N{n}"] = dict(
                n=len(rs), errors=len(rs) - len(ok), ttft_s=q([r["ttft_s"] for r in ok]), total_s=q([r["total_s"] for r in ok]),
                prompt_tokens=q([r["prompt_tokens"] for r in ok]), completion_tokens=q([r["completion_tokens"] for r in ok]),
                body_bytes_png=q([r["body_bytes_png"] for r in ok]), body_bytes_jpeg90=q([r["body_bytes_jpeg90"] for r in ok]),
                image_bytes_png=q([r["image_bytes_png"] for r in ok]), image_bytes_jpeg90=q([r["image_bytes_jpeg90"] for r in ok]),
                sm_mhz_median=q([r["gpu2"].get("sm_mhz_median") for r in ok]),
                cached_tokens=dict(Counter(r.get("cached_tokens") for r in ok)))
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d4_d7_analyse.py", model="4BI,32BI", device="cpu", n=len(rows))
    (D4 / "study_d4_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res["cells"].items():
        print("D4", k, "ttft", {x: round(v["ttft_s"][x], 3) for x in ("p50", "p90", "p99", "max")},
              "total p50", round(v["total_s"]["p50"], 3), "tok", v["prompt_tokens"]["p50"],
              "bytes png/jpg", int(v["body_bytes_png"]["p50"]), int(v["body_bytes_jpeg90"]["p50"]))
    print("D4 VOID", res["void"])


def repeats(path):
    import gzip
    ids = {}
    for l in gzip.open(path, "rt"):
        r = json.loads(l)
        if r.get("request_id"):
            ids.setdefault(r["level"], []).append(r["request_id"])
    return {k: dict(requests=len(v), distinct=len(set(v)), repeated=len(v) - len(set(v))) for k, v in ids.items()}


def d7(D7=D7, slug="study_d7", ns=(3, 9)):
    lv = [json.loads(l) for l in open(D7 / f"{slug}_levels_h100nvl.jsonl")]
    iso = [json.loads(l) for l in open(D7 / f"{slug}_isolation_h100nvl.jsonl")]
    run = [i for i in iso if i["tag"] != "pre-start wait"]
    mp = D7 / f"{slug}_run_meta_h100nvl.json"
    meta = json.load(open(mp)) if mp.exists() else {}
    res = dict(void=any(i["overlap"] for i in run), isolation_checks=len(run), settings=meta.get("settings"),
               levels=lv, derived={})
    for m in ("32BI", "4BI"):
        for n in ns:
            op = [l for l in lv if l["model"] == m and l["n"] == n and l["part"] == "B_open"]
            for L in (1.0, 2.0, 5.0):
                good = [l for l in op if l["ttft_p99"] <= L and l["errors"] == 0 and l["unfinished"] == 0]
                thr = max((l["throughput_rps"] for l in good), default=None)
                for T in (1.0, 2.0, 5.0):
                    res["derived"][f"{m}/N{n}/p99<={L:g}s/every{T:g}s"] = (
                        dict(streams=thr * T, sustained_rps=thr) if thr is not None
                        else dict(streams=None, note="even the lowest tested open-loop level missed the p99 limit"))
    res["derived_note"] = ("streams = highest open-loop throughput meeting p99 TTFT <= L with no errors x evaluation "
                           "interval T; arithmetic for this input / server on localhost, no network; not a deployment claim")
    res["repeats_within_level"] = repeats(D7 / f"{slug}_requests_h100nvl.jsonl.gz")
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d4_d7_analyse.py", model="32BI,4BI", device="cpu", n=len(lv))
    (D7 / f"{slug}_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    for l in lv:
        print("D7", l["model"], f"N{l['n']}", l["part"], l["level"], f"{l['throughput_rps']:.2f} rps",
              f"p50 {l['ttft_p50']:.3f} p99 {l['ttft_p99']:.3f}", "err", l["errors"], "unf", l["unfinished"],
              "util", round(l["gpu"].get("util_mean", -1)), "mem", round(l["gpu"].get("mem_gib_max", -1), 1))
    print("D7 VOID", res["void"])


if __name__ == "__main__":
    which = sys.argv[1:] or ["d4", "d7"]
    if "d4" in which:
        d4()
    if "d7" in which:
        d7()
    if "d7b" in which:
        d7(Path("results/cost/study_d7b"), "study_d7b", (1,))
