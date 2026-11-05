#!/usr/bin/env python3
"""StudyD12-stark analysis (CPU; after the runs end). Pre-registered (StudyD12-stark).

Answer extraction: Thinking -> text after </think> if closed (else the whole text: a runaway). Categorical items: the
LAST [RESULTS_START] ... [RESULTS_END] span; first number in it vs the answer's value (all categorical answers are
0 / 1); no span -> failure. Continuous items: STARK's own error measure, ported from github.com/nesl/STARK_Benchmark
distance.py (compute_mse / string_to_np_array, behaviour kept incl. its parser removing every character except
digits '.', '[', ']', ','): RMSE, except relative L2 (||pred − gt|| / ||gt||) for the field-variable tasks
(spatial_impute, temporal_impute, spatiotemporal_impute, spatiotemporal_forecast); unparsable predictions on loc_ /
track_ families are filled with the benchmark's default ([5] for *_event_temp, else [5, 5]); a prediction shorter than
the answer is invalid (None). Truncation = finish_reason "length"; it counts as a failure AND is reported as its own
rate. Runaway (Thinking) = truncated or </think> never closed. Per arm: categorical accuracy, Wilson 95 %, majority
baseline, paired bootstrap of accuracy differences (2,000, seed 0) on items answered by both arms' runs; continuous:
parse rate, median / mean error per family; completion tokens; same-item comparison. Latency (if run): D10 method
summary per arm. Writes results/ts/study_d12_stark/stark_results_h100nvl.json.
"""
import ast
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

D = Path("results/ts/study_d12_stark")
FIELD = {"spatial_impute", "spatiotemporal_forecast", "spatiotemporal_impute", "temporal_impute"}
SPAN = re.compile(r"\[RESULTS_START\](.*?)\[RESULTS_END\]", re.S)
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?")


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [100 * (c - h), 100 * (c + h)]


def answer_text(r):
    t = r["text"] or ""
    if r["arm"] == "32BT":
        return t.split("</think>", 1)[1] if "</think>" in t else t
    return t


def stark_parse(s):
    """STARK distance.string_to_np_array (first span; non-numeric characters removed, as in the benchmark)."""
    m = re.search(r"\[RESULTS_START\](.*?)\[RESULTS_END\]", s, re.DOTALL)
    if not m:
        return np.array([np.nan])
    x = m.group(1).strip()
    x = re.sub(r"\s+", ",", x)
    x = re.sub(r",+", ",", x)
    x = re.sub(r"\[,", "[", x)
    x = re.sub(r",\]", "]", x)
    x = re.sub(r"[^\d\.\[\]\,]", "", x)
    try:
        a = np.array(ast.literal_eval(x), dtype=float)
        return a if a.size else np.array([np.nan])
    except Exception:  # noqa: BLE001
        return np.array([np.nan])


def stark_error(family, pred_text, gt):
    a1 = stark_parse(pred_text)
    filled = bool(np.isnan(a1).any())
    if filled and ("loc_" in family or "track_" in family):
        a1 = np.array([5.0]) if family in ("loc_event_temp", "track_event_temp_online") else np.array([5.0, 5.0])
    a2 = np.array(gt, dtype=float).T
    if family == "loc_event_temp":
        return float(np.sqrt(((a1 - a2) ** 2).mean())), filled
    if a1.shape == ():
        a1 = a1.reshape(1, 1)
    elif a1.size > 1:
        a1 = a1.squeeze()
    if len(np.atleast_1d(a1)) < len(np.atleast_1d(a2)):
        return None, filled
    if len(np.atleast_1d(a1)) > len(np.atleast_1d(a2)):
        a1 = np.atleast_1d(a1)[:len(np.atleast_1d(a2))]
    try:
        if family in FIELD and np.linalg.norm(a2) > 1e-10:
            return float(np.linalg.norm(a1 - a2) / np.linalg.norm(a2)), filled
        return float(np.sqrt(((a1 - a2) ** 2).mean())), filled
    except ValueError:
        return None, filled


def score(r, it):
    trunc = r["finish_reason"] == "length"
    t = answer_text(r)
    closed = ("</think>" in (r["text"] or "")) if r["arm"] == "32BT" else None
    out = dict(truncated=trunc, runaway=bool(r["arm"] == "32BT" and (trunc or not closed)),
               completion_tokens=r["completion_tokens"])
    if it["categorical"]:
        spans = SPAN.findall(t)
        nums = NUM.findall(spans[-1]) if spans else []
        ans = float(NUM.findall(it["answer"])[0])
        out.update(parsed=bool(nums) and not trunc, correct=bool(nums) and not trunc and float(nums[0]) == ans)
    else:
        try:
            gt = json.loads(it["answer"])
        except json.JSONDecodeError:
            gt = ast.literal_eval(it["answer"])
        err, filled = stark_error(it["family"], t, gt)
        out.update(parsed=bool(SPAN.search(t)) and not filled and not trunc, error=err, filled_default=filled)
    return out


def main():
    items = {it["item_id"]: it for it in map(json.loads, open(D / "stark_manifest.jsonl"))}
    rows = [json.loads(l) for l in open(D / "stark_requests_h100nvl.jsonl")]
    S = defaultdict(dict)
    for r in rows:
        if not r["error"]:
            S[r["arm"]][r["item_id"]] = score(r, items[r["item_id"]])
    meta = json.load(open(D / "stark_run_meta_h100nvl.json")) if (D / "stark_run_meta_h100nvl.json").exists() else {}
    res = dict(n_items=len(items), arms_answered={a: len(v) for a, v in S.items()},
               error_rows=sum(bool(r["error"]) for r in rows), thinking_projection=meta.get("thinking_projection"),
               per_arm={}, paired={})
    cat_ids = [i for i, it in items.items() if it["categorical"]]
    for a, sc in S.items():
        cats = [i for i in cat_ids if i in sc]
        k = sum(sc[i]["correct"] for i in cats)
        labs = Counter(float(NUM.findall(items[i]["answer"])[0]) for i in cats)
        cont = [i for i in sc if not items[i]["categorical"]]
        # Summary only (the per-item measure is unchanged): STARK leaves an unparsed prediction as NaN outside the loc_ /
        # track_ families, giving a NaN error; NaN errors are counted separately and kept out of median / mean.
        # Errors are also summarised over parsed items only (span found, no default fill, not truncated).
        fam_err, fam_err_nofill, fam_nan = defaultdict(list), defaultdict(list), Counter()
        for i in cont:
            e = sc[i]["error"]
            if e is None:
                continue
            if not math.isfinite(e):
                fam_nan[items[i]["family"]] += 1
                continue
            fam_err[items[i]["family"]].append(e)
            if sc[i]["parsed"]:
                fam_err_nofill[items[i]["family"]].append(e)
        res["per_arm"][a] = dict(
            n=len(sc), categorical=dict(n=len(cats), correct=k, accuracy_pct=100 * k / max(1, len(cats)),
                                        wilson95=wilson(k, len(cats)),
                                        majority_pct=100 * labs.most_common(1)[0][1] / max(1, len(cats)) if cats else None,
                                        failures_no_parse=sum(not sc[i]["parsed"] for i in cats),
                                        truncated=sum(sc[i]["truncated"] for i in cats)),
            continuous=dict(n=len(cont), parse_rate=float(np.mean([sc[i]["parsed"] for i in cont])) if cont else None,
                            filled_default=sum(sc[i].get("filled_default", False) for i in cont),
                            invalid=sum(sc[i]["error"] is None for i in cont),
                            nan_error=dict(fam_nan),
                            error_by_family={f: dict(n=len(v), median=float(np.median(v)), mean=float(np.mean(v)))
                                             for f, v in sorted(fam_err.items())},
                            error_by_family_parsed_only={f: dict(n=len(v), median=float(np.median(v)),
                                                                 mean=float(np.mean(v)))
                                                         for f, v in sorted(fam_err_nofill.items())},
                            invalid_by_family=dict(Counter(items[i]["family"] for i in cont
                                                           if sc[i]["error"] is None))),
            truncation_rate=float(np.mean([s["truncated"] for s in sc.values()])),
            runaway_rate=float(np.mean([s["runaway"] for s in sc.values()])),
            completion_tokens=dict(p50=float(np.median([s["completion_tokens"] for s in sc.values() if s["completion_tokens"]])),
                                   p90=float(np.percentile([s["completion_tokens"] for s in sc.values() if s["completion_tokens"]], 90)),
                                   max=int(max(s["completion_tokens"] or 0 for s in sc.values()))))
    arms = sorted(S)
    rng = np.random.default_rng(0)
    for i, a in enumerate(arms):
        for b in arms[i + 1:]:
            ids = [x for x in cat_ids if x in S[a] and x in S[b]]
            if not ids:
                continue
            d = np.array([int(S[a][x]["correct"]) - int(S[b][x]["correct"]) for x in ids], float)
            bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
            res["paired"][f"{a}_minus_{b}"] = dict(n=len(ids), diff_pp=100 * float(d.mean()),
                                                   ci95_pp=[100 * float(np.percentile(bs, 2.5)),
                                                            100 * float(np.percentile(bs, 97.5))],
                                                   acc_a=100 * float(np.mean([S[a][x]["correct"] for x in ids])),
                                                   acc_b=100 * float(np.mean([S[b][x]["correct"] for x in ids])))
    lat = D / "stark_latency_requests_h100nvl.jsonl"
    if lat.exists():
        lr = [json.loads(l) for l in open(lat)]
        iso = [json.loads(l) for l in open(D / "stark_latency_isolation_h100nvl.jsonl")]
        run = [x for x in iso if x["tag"] != "pre-start wait"]
        res["latency"] = dict(void=any(x["overlap"] for x in run), isolation_checks=len(run), arms={})
        for a in ("4BI", "32BI", "32BT"):
            rr = [r for r in lr if r["arm"] == a and not r["warmup"] and not r["error"]]
            if rr:
                def qq(x):
                    x = [v for v in x if v is not None]
                    return dict(p50=float(np.percentile(x, 50)), p90=float(np.percentile(x, 90)), max=float(max(x)))
                res["latency"]["arms"][a] = dict(n=len(rr), ttft_s=qq([r["ttft_s"] for r in rr]),
                                                 total_s=qq([r["total_s"] for r in rr]),
                                                 prompt_tokens=qq([r["prompt_tokens"] for r in rr]),
                                                 completion_tokens=qq([r["completion_tokens"] for r in rr]),
                                                 runaways=sum(r["runaway"] for r in rr))
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="study_d12_stark_analyse.py", model="4BI,32BI,32BT", device="cpu", n=len(rows))
    (D / "stark_results_h100nvl.json").write_text(json.dumps(res, indent=1, default=float))
    for a, v in res["per_arm"].items():
        c = v["categorical"]
        print(a, f"cat {c['accuracy_pct']:.1f}% ({c['correct']}/{c['n']}) {c['wilson95']} maj {c['majority_pct']}",
              "trunc", round(v["truncation_rate"], 3), "runaway", round(v["runaway_rate"], 3), "ctok", v["completion_tokens"],
              "cont parse", v["continuous"]["parse_rate"])
    print(json.dumps(res["paired"]))


if __name__ == "__main__":
    main()
