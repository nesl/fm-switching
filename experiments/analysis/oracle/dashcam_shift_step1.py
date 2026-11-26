#!/usr/bin/env python3
"""Step 1 diagnostic (pre-registered in reports/study_dashcam_diagnosis.md): live versus SH-EP 32B
cloud score on identical (clip, instant) pairs. Read-only, fixes nothing.

Pair key: (clip, t) with t rounded to 0.01 s. Live: per-arm on-time dashcam cloud_score (committed 1x
outcomes, seeds 4 to 7). SH-EP: 32B EP-G score at the same clip and time. d = live minus SH-EP.
Body: per live request, cache_path, prompt_tokens and the frame time order (mm_uuids). SH-EP: n_frames,
prompt_tokens, cached_tokens, frame order.
"""
from __future__ import annotations
import gzip, json, sys, collections, re
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
SH32 = REPO / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
import episodic_lib as E  # noqa: E402

SEEDS = [4, 5, 6, 7]
ARMS = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]


def key(clip, t):
    return (clip, round(float(t), 2))


def sh_index():
    idx = {}
    with gzip.open(SH32, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("condition") != "EP-G" or r.get("score") is None or r.get("t") is None:
                continue
            k = key(r["file_name"], r["t"])
            idx.setdefault(k, r)
    return idx


def frame_times(mm):
    out = []
    for u in mm or []:
        m = re.search(r"t(\d+\.\d+)$", str(u))
        if m:
            out.append(float(m.group(1)))
    return out


def main():
    sh = sh_index()
    pairs = []   # dict rows
    for disp, raw in ARMS:
        for s in SEEDS:
            cell = RUNS / f"{raw}_n16_s{s}_1200s_h27_3t_L3_epg_rq30"
            oc = cell / "outcomes.jsonl.gz"
            rq = cell / "request.jsonl.gz"
            if not oc.exists() or not rq.exists():
                continue
            req = {}
            with gzip.open(rq, "rt") as f:
                for line in f:
                    r = json.loads(line)
                    if str(r.get("device_id", "")).startswith("dash"):
                        req[r["opportunity_id"]] = r
            with gzip.open(oc, "rt") as f:
                for line in f:
                    o = json.loads(line)
                    if not str(o.get("device_id", "")).startswith("dash"):
                        continue
                    cp = o.get("cloud_payload") or {}
                    if not cp.get("on_time") or cp.get("cloud_score") is None:
                        continue
                    k = key(o["clip"], o["t_local"])
                    if k not in sh:
                        continue
                    s32 = sh[k]
                    rqr = req.get(o["opportunity_id"], {})
                    live_frames = frame_times(rqr.get("mm_uuids"))
                    pairs.append({
                        "arm": disp, "seed": s, "clip": o["clip"], "t": k[1],
                        "live": float(cp["cloud_score"]), "sh": float(s32["score"]),
                        "d": float(cp["cloud_score"]) - float(s32["score"]),
                        "cache_path": rqr.get("cache_path"),
                        "live_prompt": rqr.get("prompt_tokens"),
                        "live_n_frames": len(live_frames),
                        "live_frame_order_ok": live_frames == sorted(live_frames),
                        "sh_n_frames": s32.get("n_frames"),
                        "sh_prompt": s32.get("prompt_tokens"),
                        "sh_cached": s32.get("cached_tokens"),
                    })
    d = np.array([p["d"] for p in pairs])
    out = {"_what": "Step 1: live vs SH-EP 32B score on identical (clip, t) pairs.",
           "n_pairs": len(pairs), "n_clips": len({p["clip"] for p in pairs})}
    def summ(vals):
        v = np.array(vals, float)
        if len(v) == 0:
            return None
        return {"n": int(len(v)), "mean": round(float(v.mean()), 4), "median": round(float(np.median(v)), 4),
                "p5": round(float(np.percentile(v, 5)), 4), "p95": round(float(np.percentile(v, 95)), 4),
                "iqr": [round(float(np.percentile(v, 25)), 4), round(float(np.percentile(v, 75)), 4)]}
    out["overall"] = summ(d)
    out["by_cache_path"] = {cp: summ([p["d"] for p in pairs if p["cache_path"] == cp])
                            for cp in sorted({str(p["cache_path"]) for p in pairs})}
    def bucket(n):
        return "1-4" if n <= 4 else ("5-8" if n <= 8 else "9+")
    out["by_frame_bucket"] = {b: summ([p["d"] for p in pairs if bucket(p["live_n_frames"]) == b])
                              for b in ("1-4", "5-8", "9+")}
    out["by_arm"] = {a: summ([p["d"] for p in pairs if p["arm"] == a]) for a in sorted({p["arm"] for p in pairs})}
    # body check: same instant, live versus SH-EP, frame count / order / prompt tokens
    nf_match = sum(1 for p in pairs if p["live_n_frames"] == p["sh_n_frames"])
    order_ok = sum(1 for p in pairs if p["live_frame_order_ok"])
    prompt_match = sum(1 for p in pairs if p["live_prompt"] == p["sh_prompt"])
    out["body_check"] = {"n": len(pairs), "frame_count_match": nf_match,
                         "live_frame_order_sorted": order_ok, "prompt_tokens_match": prompt_match,
                         "example": pairs[0] if pairs else None}
    out["cache_path_counts"] = dict(collections.Counter(str(p["cache_path"]) for p in pairs))
    # body by cache path: frames sent live versus frames in the SH-EP reference request
    xt = {}
    for cp in sorted({str(p["cache_path"]) for p in pairs}):
        sub = [p for p in pairs if str(p["cache_path"]) == cp]
        xt[cp] = {"n": len(sub),
                  "live_frames_median": float(np.median([p["live_n_frames"] for p in sub])),
                  "sh_frames_median": float(np.median([p["sh_n_frames"] for p in sub if p["sh_n_frames"] is not None])),
                  "frame_count_match": sum(1 for p in sub if p["live_n_frames"] == p["sh_n_frames"]),
                  "live_frames_le_3": sum(1 for p in sub if p["live_n_frames"] <= 3),
                  "live_prompt_median": float(np.median([p["live_prompt"] for p in sub if p["live_prompt"] is not None])),
                  "sh_cached_median": float(np.median([p["sh_cached"] for p in sub if p["sh_cached"] is not None]))}
    out["body_by_cache_path"] = xt
    (REPO / "results/orchestration/live2/oracle/dashcam_shift_step1.json").write_text(
        json.dumps(out, indent=1, default=float))
    print(json.dumps({k: out[k] for k in ("n_pairs", "n_clips", "overall", "by_cache_path",
                                          "by_frame_bucket", "body_check", "cache_path_counts")},
                     indent=1, default=float)[:3000])


if __name__ == "__main__":
    main()
