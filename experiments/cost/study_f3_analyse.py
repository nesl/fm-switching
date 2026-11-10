#!/usr/bin/env python3
"""StudyF3-latency analysis (CPU; dashcam venv). Per cell and per token bin: TTFT and total latency p50 / p90 / max
(discarded warm-up rows and superseded rows excluded). Fitted latency vs prompt tokens per model x format x cache state
(linear and quadratic least squares on TTFT and total; WARM and COLD never pooled, video and images never pooled).
Format reconciliation (cell f): K1 / K3 video vs images on the same frames, and vs E4's sources (R1 single, H5).
Exclusivity: monitor summary; VOID flag. Writes results/cost/study_f3/f3_results.json."""
import collections
import gzip
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments/lib"))
OUT = REPO / "results/cost/study_f3"


def q(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return dict(n=len(xs), p50=float(np.percentile(xs, 50)), p90=float(np.percentile(xs, 90)), max=float(max(xs)),
                min=float(min(xs)))


def fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    out = {}
    for deg in (1, 2):
        if len(x) <= deg + 1:
            continue
        c = np.polyfit(x, y, deg)
        pred = np.polyval(c, x)
        ss = float(np.sum((y - y.mean()) ** 2))
        out[f"deg{deg}"] = dict(coef_high_to_low=[float(v) for v in c],
                                r2=1 - float(np.sum((y - pred) ** 2)) / ss if ss else None,
                                resid_abs_p90=float(np.percentile(np.abs(y - pred), 90)))
    if "deg1" in out:
        out["deg1"]["ms_per_1k_tokens"] = out["deg1"]["coef_high_to_low"][0] * 1000 * 1000
    out["token_range"] = [float(x.min()), float(x.max())]
    for t in (2000, 6000, 12400, 20000):
        if x.min() <= t <= x.max() and "deg2" in out:
            out[f"at_{t}"] = float(np.polyval(out["deg2"]["coef_high_to_low"], t))
    return out


def main():
    rows = [json.loads(l) for l in open(OUT / "f3_requests_h100nvl.jsonl")]
    rows = [r for r in rows if not r.get("superseded")]
    meta = json.loads((OUT / "f3_run_meta_h100nvl.json").read_text())
    good = [r for r in rows if not r["discarded"] and not r["error"]]
    res = dict(label="StudyF3-latency: single request, localhost, h100nvl GPU 1, max_tokens 8; COLD = prefix caching off; "
               "WARM = prefix caching on (cell d only)", void=meta.get("void"), checks={}, cells={}, bins={},
               curves={}, format_reconciliation={})
    res["checks"] = dict(
        rows=len(rows), discarded=sum(r["discarded"] for r in rows), errors=sum(bool(r["error"]) for r in rows),
        cold_with_cached_tokens=sum(1 for r in good if r["label"] == "cold" and r["cached_tokens"]),
        missing_ttft=sum(1 for r in good if r["ttft_s"] is None),
        sm_clock_at_send=sorted({r["sm_at_send"].split(",")[0] for r in good}))
    by = collections.defaultdict(list)
    for r in good:
        by[(r["model"], r["cell"])].append(r)
    for (m, c), rs in sorted(by.items()):
        res["cells"][f"{m}/{c}"] = dict(fmt=rs[0]["fmt"], cache="WARM" if rs[0]["prefix_caching"] else "COLD",
                                        prompt_tokens=q([r["prompt_tokens"] for r in rs]),
                                        cached_tokens=q([r["cached_tokens"] or 0 for r in rs]),
                                        ttft_s=q([r["ttft_s"] for r in rs]), total_s=q([r["total_s"] for r in rs]),
                                        body_MB=q([r["body_bytes"] / 1e6 for r in rs]))
        if "bin" in rs[0]:
            for b in sorted({r["bin"] for r in rs}):
                rb = [r for r in rs if r["bin"] == b]
                res["bins"][f"{m}/{c}/bin{b}"] = dict(prompt_tokens=q([r["prompt_tokens"] for r in rb]),
                                                      ttft_s=q([r["ttft_s"] for r in rb]),
                                                      total_s=q([r["total_s"] for r in rb]))
        if c == "d_D2_WARM":
            res["cells"][f"{m}/{c}"]["first_in_session"] = dict(
                ttft_s=q([r["ttft_s"] for r in rs if r["pos"] == 0]),
                cached_tokens=q([r["cached_tokens"] or 0 for r in rs if r["pos"] == 0]))
            res["cells"][f"{m}/{c}"]["later_in_session"] = dict(
                ttft_s=q([r["ttft_s"] for r in rs if r["pos"] > 0]),
                cached_tokens=q([r["cached_tokens"] or 0 for r in rs if r["pos"] > 0]),
                uncached_tokens=q([r["prompt_tokens"] - (r["cached_tokens"] or 0) for r in rs if r["pos"] > 0]))
    grp = collections.defaultdict(list)
    for r in good:
        grp[(r["model"], r["fmt"], "WARM" if r["prefix_caching"] else "COLD")].append(r)
    for (m, f, cs), rs in sorted(grp.items()):
        key = f"{m}/{f}/{cs}"
        x = [r["prompt_tokens"] for r in rs]
        res["curves"][key] = dict(n=len(rs), cells=sorted({r["cell"] for r in rs}),
                                  ttft=fit(x, [r["ttft_s"] for r in rs]), total=fit(x, [r["total_s"] for r in rs]))
        if cs == "WARM":
            xu = [r["prompt_tokens"] - (r["cached_tokens"] or 0) for r in rs]
            res["curves"][key]["ttft_vs_uncached_tokens"] = fit(xu, [r["ttft_s"] for r in rs])
    # format reconciliation (cell f) vs E4 sources
    for cell in ("K1", "K3"):
        v = by.get(("32BI", f"f_{cell}_video"), [])
        im = by.get(("32BI", f"f_{cell}_images"), [])
        pv = {r["question_id"]: r for r in v}
        pi = {r["question_id"]: r for r in im}
        both = sorted(set(pv) & set(pi))
        res["format_reconciliation"][cell] = dict(
            n_paired=len(both), video=dict(tokens=q([pv[k]["prompt_tokens"] for k in both]), ttft=q([pv[k]["ttft_s"] for k in both]),
                                           total=q([pv[k]["total_s"] for k in both])),
            images=dict(tokens=q([pi[k]["prompt_tokens"] for k in both]), ttft=q([pi[k]["ttft_s"] for k in both]),
                        total=q([pi[k]["total_s"] for k in both])),
            images_minus_video_total_paired_p50=float(np.median([pi[k]["total_s"] - pv[k]["total_s"] for k in both])) if both else None)
    prior = {}
    r1 = [json.loads(l) for l in gzip.open(REPO / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz", "rt")]
    for cell in ("K1", "K3"):
        s = [r for r in r1 if r["cell"] == cell and r["mode"] == "single" and not r["error"]]
        prior[f"R1_single_{cell}_video"] = dict(n=len(s), tokens=q([r["prompt_tokens"] for r in s]),
                                                ttft=q([r["ttft_s"] for r in s]), total=q([r["latency_s"] for r in s]))
    h5 = [json.loads(l) for l in gzip.open(REPO / "results/cost/study_clean/study_clean_h5_requests_h100nvl.jsonl.gz", "rt")]
    s = [r for r in h5 if r["model"] == "32BI" and r["N"] == 37 and not r["warmup"] and not r["error"]]
    prior["H5_32BI_N37_images"] = dict(n=len(s), tokens=q([r["prompt_tokens"] for r in s]), ttft=q([r["ttft_s"] for r in s]),
                                       total=q([r["total_s"] for r in s]))
    res["format_reconciliation"]["prior_E4_sources"] = prior
    mon = [json.loads(l) for l in open(OUT / "f3_monitor_h100nvl.jsonl")]
    res["exclusivity"] = dict(snapshots=len(mon), ours_outside_job=sum(bool(m["ours_outside_job"]) for m in mon),
                              foreign_on_gpu1=sum(bool(m["foreign_on_gpu1"]) for m in mon),
                              other_users_gpu=sorted({p["user"] for m in mon for p in m["gpu_procs"]}),
                              gpu1_sm_clock_values=sorted({m["gpu1"].split(",")[0] for m in mon}),
                              first=mon[0]["at"] if mon else None, last=mon[-1]["at"] if mon else None)
    from _provenance import stamp
    res["_provenance"] = stamp(script="study_f3_analyse.py", model="4BI,32BI", device="cpu", n=len(good))
    (OUT / "f3_results.json").write_text(json.dumps(res, indent=1, default=float))
    for k, v in res["cells"].items():
        print(k, v["fmt"], v["cache"], "tok", round(v["prompt_tokens"]["p50"]), "ttft p50", round(v["ttft_s"]["p50"], 3),
              "total p50/p90", round(v["total_s"]["p50"], 3), round(v["total_s"]["p90"], 3))


if __name__ == "__main__":
    main()
