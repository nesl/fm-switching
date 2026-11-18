#!/usr/bin/env python3
"""StudyORIN3-vllm Part 1 analysis: score agreement, calibration, challenge AP, latency.

CPU only; reads committed traces and the vLLM scores this study wrote. No GPU, no server.

Agreement: vLLM-on-Orin vs llama.cpp-on-Orin (StudyORIN2 for d3dev, StudyORIN1 for d14b) and
vs the H100 4B, on the SAME requests (Pearson, mean signed = vLLM minus other, median abs).

Calibration: fit the vLLM-on-Orin Platt map on the 6,010 d3dev requests with the committed
ctrl1c routine (fit_platt), reproduce the H100 4B map (a=0.114603,b=1.140751) as a check, and
compare with the llama.cpp-on-Orin map (a=0.114932,b=1.174287) and the H100 maps; residual tier
offset vs the calibrated H100 32B on d3dev (both tiers present).

Challenge AP: self-contained request-level average precision over the sample (score ranked
against the binary clip label), computed identically for vLLM, llama.cpp-Orin and H100 4B. This
is NOT StudyCTRL1b's streaming/horizon mAP; it is a flat AP for a cross-stack ranking comparison.
"""
import gzip, json, math, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dashcam"))
import ctrl1c_calibrate as K  # committed Platt routine (fit_platt) + H100 map reproduction
OUTD = ROOT / "results/dashcam/study_orin3"
D3_H100 = ROOT / "results/dashcam/study_d3_nexar/d3_requests_h100nvl.jsonl.gz"
D14B_H100 = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
ORIN2_SCORES = ROOT / "results/dashcam/study_orin2/orin2_d3dev_scores.jsonl.gz"
H100_4B_MAP = {"a": 0.114603, "b": 1.140751}
H100_32B_MAP = {"a": 0.129472, "b": 1.848187}
ORIN_LLAMACPP_MAP = {"a": 0.114932, "b": 1.174287}


def rd(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as f:
        return [json.loads(l) for l in f]


def clip_label(r):
    lab = r.get("label") or r.get("gt")
    return 1 if str(lab).lower() == "positive" else 0


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs); sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def agree(a_by_id, b_by_id):
    """a minus b on matched ids (a = vLLM)."""
    xa, xb = [], []
    for rid, sa in a_by_id.items():
        sb = b_by_id.get(rid)
        if sa is not None and sb is not None:
            xa.append(sa); xb.append(sb)
    if not xa:
        return {"n_matched": 0}
    diffs = [a - b for a, b in zip(xa, xb)]
    return {"n_matched": len(xa), "pearson": round(pearson(xa, xb), 4),
            "mean_signed_vllm_minus_other": round(sum(diffs) / len(diffs), 4),
            "median_abs_diff": round(st.median(abs(d) for d in diffs), 4)}


def average_precision(scores, labels):
    """Standard AP: sort by score desc, AP = sum over positives of precision@rank. Ties broken by
    stable order. Request-level, clip label. Identical routine applied to each score source."""
    pairs = sorted(zip(scores, labels), key=lambda t: -t[0])
    P = sum(labels)
    if P == 0:
        return None
    tp = 0
    ap = 0.0
    for i, (_, y) in enumerate(pairs, 1):
        if y == 1:
            tp += 1
            ap += tp / i
    return ap / P


def pctl(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * q
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def lat_stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {}
    return {"n": len(vals), "p50": round(pctl(vals, 0.5), 4), "p90": round(pctl(vals, 0.9), 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
            "mean": round(sum(vals) / len(vals), 4)}


def h100_scores(path, model, by="request_id"):
    out = {}
    for r in rd(path):
        if str(r.get("model")) == model and str(r.get("n")) == "1" and not r.get("grey"):
            p = r.get("p_yes")
            if p is not None:
                out[r[by]] = math.log(max(p, 1e-12))
    return out


def analyse(setname):
    OUTD.mkdir(parents=True, exist_ok=True)
    sp = OUTD / f"orin3_{setname}_scores.jsonl"
    if not sp.exists():
        sp = sp.with_suffix(".jsonl.gz")
    vrows = rd(sp)
    n_null = sum(1 for r in vrows if r.get("score") is None)
    n_neither = sum(1 for r in vrows if r.get("neither"))
    n_err = sum(1 for r in vrows if r.get("error"))
    clocks = [r.get("clock_hz") for r in vrows if r.get("clock_hz") is not None]
    clock_all = all(c == 1300500000 for c in clocks) and len(clocks) == len(vrows)
    cached_vals = [r.get("cached_tokens") for r in vrows]
    ptoks = sorted(set(r.get("prompt_tokens") for r in vrows if r.get("prompt_tokens") is not None))
    v_by_id = {r["request_id"]: r.get("score") for r in vrows}

    res = {"set": setname, "n_scores": len(vrows),
           "sanity": {"n_null": n_null, "n_neither": n_neither, "n_error": n_err,
                      "clock_pinned_all_1.3005GHz": clock_all,
                      "prompt_tokens_distinct": ptoks,
                      "prompt_tokens_matches_d15_378": (ptoks == [378]) if setname == "d3dev" else None,
                      "cached_tokens_nonnull": sum(1 for c in cached_vals if c),
                      "cached_tokens_note": ("vLLM returned no prompt_tokens_details.cached_tokens for "
                                             "one-frame requests: the shared header prefix is shorter "
                                             "than one 16-token KV block, so no block is cacheable "
                                             "before the differing image")}}

    if setname == "d3dev":
        orin_llama = {r["request_id"]: r.get("score") for r in rd(ORIN2_SCORES)}
        h4 = h100_scores(D3_H100, "4BI")
        h32 = h100_scores(D3_H100, "32BI")
        res["agreement_vs_llamacpp_orin"] = agree(v_by_id, orin_llama)
        res["agreement_vs_h100_4b"] = agree(v_by_id, h4)
        # calibration: fit vLLM Platt map on d3dev (clip label), committed routine
        logp = [r["score"] for r in vrows if r.get("score") is not None]
        y = [clip_label(r) for r in vrows if r.get("score") is not None]
        m = K.fit_platt(logp, y)
        va, vb = m["a"], m["b"]
        raw_at_half = (-vb / va) if va else None
        # H100 4B reproduction check via committed routine
        repro = K.fit_maps_d3dev()["device_4BI_N1"]
        res["platt_validation"] = {
            "routine": "ctrl1c_calibrate.fit_platt (Newton/IRLS, committed)",
            "h100_4b_reproduction": {"a": round(repro["a"], 6), "b": round(repro["b"], 6),
                                     "target_a": H100_4B_MAP["a"], "target_b": H100_4B_MAP["b"],
                                     "reproduces": bool(abs(repro["a"] - H100_4B_MAP["a"]) < 1e-3
                                                        and abs(repro["b"] - H100_4B_MAP["b"]) < 1e-3)}}
        res["vllm_orin_4b_map"] = {"a": round(va, 6), "b": round(vb, 6),
                                   "raw_logpyes_at_p0.5": round(raw_at_half, 6) if raw_at_half else None,
                                   "n_fit": len(logp), "n_clips": len(set(r["clip"] for r in vrows)),
                                   "feature": "log_pyes", "form": "log_odds = a*log(p_yes) + b"}
        res["compare_maps"] = {"vllm_orin_4b": {"a": round(va, 6), "b": round(vb, 6)},
                               "llamacpp_orin_4b": ORIN_LLAMACPP_MAP,
                               "h100_4b": H100_4B_MAP, "h100_32b": H100_32B_MAP}
        # tier residual: calibrated vLLM-4B minus calibrated H100-32B on d3dev (both present)
        resid = []
        for r in vrows:
            s = r.get("score"); s32 = h32.get(r["request_id"])
            if s is not None and s32 is not None:
                resid.append((va * s + vb) - (H100_32B_MAP["a"] * s32 + H100_32B_MAP["b"]))
        res["tier_residual"] = {"set": "d3dev (both tiers present)", "n": len(resid),
                                "vllm4b_minus_cal32b_logodds": round(sum(resid) / len(resid), 6) if resid else None,
                                "llamacpp_orin_ref_orin2": -0.0171, "h100_4b_ref_ctrl1c": -0.1197}
        # latency vs llama.cpp-Orin (StudyORIN2 d3dev, cold cache_prompt=False)
        o2 = {r["request_id"]: r for r in rd(ORIN2_SCORES)}
        res["latency_warm_header"] = {
            "vllm_ttft_s": lat_stats([r.get("ttft_s") for r in vrows]),
            "vllm_total_s": lat_stats([r.get("total_s") for r in vrows]),
            "llamacpp_orin_ttft_s": lat_stats([o2[r["request_id"]].get("ttft_s")
                                               for r in vrows if r["request_id"] in o2]),
            "llamacpp_orin_total_s": lat_stats([o2[r["request_id"]].get("total_s")
                                                for r in vrows if r["request_id"] in o2]),
            "note": "vLLM prefix caching ON (warm header); StudyORIN2 llama.cpp cache_prompt=False (cold)"}
        _coldcheck(res, vrows, setname)

    elif setname == "d14b":
        orin1 = {r["request_id"]: r.get("orin1_score") for r in vrows}
        h4 = h100_scores(D14B_H100, "4BI")
        res["agreement_vs_llamacpp_orin1"] = agree(v_by_id, orin1)
        res["agreement_vs_h100_4b"] = agree(v_by_id, h4)
        # challenge AP over the sample
        def ap_for(by_id):
            sc, lb = [], []
            for r in vrows:
                s = by_id.get(r["request_id"])
                if s is not None:
                    sc.append(s); lb.append(clip_label(r))
            return {"n": len(sc), "ap": round(average_precision(sc, lb), 4) if sc else None}
        res["challenge_ap_sample"] = {
            "definition": "request-level average precision over the 2,000-request sample, score ranked vs clip label",
            "vllm_orin": ap_for(v_by_id),
            "llamacpp_orin1": ap_for(orin1),
            "h100_4b": ap_for(h4)}
        res["latency_warm_header"] = {
            "vllm_ttft_s": lat_stats([r.get("ttft_s") for r in vrows]),
            "vllm_total_s": lat_stats([r.get("total_s") for r in vrows]),
            "llamacpp_orin1_ttft_s": lat_stats([r.get("orin1_ttft_s") for r in vrows]),
            "llamacpp_orin1_total_s": lat_stats([r.get("orin1_total_s") for r in vrows]),
            "note": "vLLM prefix caching ON (warm header); StudyORIN1 llama.cpp dense latencies"}
        _coldcheck(res, vrows, setname)

    out = OUTD / f"study_orin3_part1_{setname}_analysis.json"
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))
    print("wrote", out)
    # write the calibration map file (d3dev only)
    if setname == "d3dev":
        from _provenance import stamp
        cmap = {"model": "4bi_bf16_orin_vllm", "stack": "vLLM 0.20.0+cu126",
                "feature": "log_pyes", "form": "log_odds = a*log(p_yes) + b",
                "a": res["vllm_orin_4b_map"]["a"], "b": res["vllm_orin_4b_map"]["b"],
                "raw_logpyes_at_p0.5": res["vllm_orin_4b_map"]["raw_logpyes_at_p0.5"],
                "fit_split": "StudyD3 DEV (601 clips x 10 offsets = 6010 N=1)",
                "clip_level_label": True, "seed": 0,
                "compare": {"llamacpp_orin_4b": ORIN_LLAMACPP_MAP, "h100_4b": H100_4B_MAP,
                            "h100_32b": H100_32B_MAP},
                "_provenance": stamp(script="study_orin3_analyse.py", model="qwenvl4b",
                                     device="jetson_orin", n=res["vllm_orin_4b_map"]["n_fit"],
                                     args={"part": 1})}
        json.dump(cmap, open(OUTD / "orin3_calibration.json", "w"), indent=1)
        print("wrote", OUTD / "orin3_calibration.json")
    return res


def _coldcheck(res, vrows, setname):
    cp = OUTD / f"orin3_{setname}_coldcheck_scores.jsonl"
    if not cp.exists():
        res["coldcheck"] = {"status": "not run yet"}
        return
    cold = {r["request_id"]: r for r in rd(cp)}
    warm = {r["request_id"]: r for r in vrows if r["request_id"] in cold}
    warm_ttft = [warm[i].get("ttft_s") for i in cold if i in warm]
    cold_ttft = [cold[i].get("ttft_s") for i in cold if i in warm]
    ws, cs = lat_stats(warm_ttft), lat_stats(cold_ttft)
    diff_p50 = None
    if ws.get("p50") and cs.get("p50"):
        diff_p50 = round((cs["p50"] - ws["p50"]) / ws["p50"] * 100, 2)
    res["coldcheck"] = {"n": len(cold), "seed": 0,
                        "warm_ttft_s": ws, "cold_ttft_s": cs,
                        "cold_minus_warm_p50_pct": diff_p50,
                        "exceeds_5pct": (abs(diff_p50) > 5) if diff_p50 is not None else None,
                        "verdict": ("header caching materially affects TTFT (>5% at p50)"
                                    if (diff_p50 is not None and abs(diff_p50) > 5)
                                    else "header caching does not affect the comparison (<=5% at p50)")}


if __name__ == "__main__":
    analyse(sys.argv[1] if len(sys.argv) > 1 else "d3dev")
