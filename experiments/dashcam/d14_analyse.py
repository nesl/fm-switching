#!/usr/bin/env python3
"""StudyD14-trace sanity analysis (CPU; after the runs end). Pre-registered (StudyD14-trace). NO policy, NO threshold
fitting, NO latency.

Score = D3's: log P(Yes) floored at 1e-12, P(Yes) = Yes / (Yes + No) first-token logprob mass (top 20).
Per arm (4BI N1, 4BI N3, 32BI N1, 32BI N3, 32BI N9):
 (a) median score over time by label: positives aligned to the event (rel = t − time_of_event, binned to the nearest
     whole second), negatives by clip time t;
 (b) AUROC of each positive clip's row at the whole-second t nearest time_of_event (clamped to the clip's grid)
     against ALL negative rows of the arm; clip bootstrap (positive clips and negative clips resampled separately,
     2,000, seed 0). Compared with StudyD3 offset-0 AUROC (scored positives vs offset-0 negatives) — NOT like-for-like
     (different clips, different negatives, t rounded to a whole second);
 raw Yes rate per hour on negative clips: rows with P(Yes) > 0.5, one decision per second, so rate/h = Yes rows /
     negative rows × 3600 (RAW, not a tuned false-alarm rate);
 requests, error rows (retries), still failed, neither-Yes-nor-No, grey Yes rate, identical frames / prompt tokens
     across models per (clip, t, N), frame disk use, flow-feature coverage.
Also writes the joined trace (one row per arm × clip × t with labels) for the later simulation, gzips the raw request
rows, and splits any results file > 90 MB.
"""
import csv
import gzip
import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from _provenance import stamp  # noqa: E402

REPO = HERE.parents[1]
OUT = REPO / "results/dashcam/study_d14_trace"
FR = Path.home() / "data/dashcam/d14_frames"
REQ = OUT / "d14_requests_h100nvl.jsonl"
D3RES = REPO / "results/dashcam/study_d3_nexar/d3_results_h100nvl.json"
ARMS = [("4BI", 1), ("4BI", 3), ("32BI", 1), ("32BI", 3), ("32BI", 9)]
FLOOR, NBOOT, SEED, LIMIT = 1e-12, 2000, 0, 90 * 2 ** 20


def score(p):
    return float(np.log(max(p, FLOOR)))


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def open_rows():
    if REQ.exists():
        return [json.loads(l) for l in open(REQ)]
    return [json.loads(l) for l in gzip.open(str(REQ) + ".gz", "rt")]


def main():
    mp = OUT / "d14_requests_manifest.jsonl"
    man = {r["request_id"]: r for r in map(json.loads, open(mp) if mp.exists() else gzip.open(str(mp) + ".gz", "rt"))}
    rows = open_rows()
    res = dict(arms={}, checks={})
    last = {}
    for r in rows:
        if not r["error"]:
            last[(r["model"], r["n"], r["request_id"])] = r
    for m, n in ARMS:
        allr = [r for r in rows if r["model"] == m and r["n"] == n]
        keys = {r["request_id"] for r in allr}
        ok = {k[2]: v for k, v in last.items() if k[0] == m and k[1] == n}
        real = {k: v for k, v in ok.items() if not v["grey"]}
        grey = [v for v in ok.values() if v["grey"]]
        exp = [k for k, v in man.items() if v["n"] == n]
        nei = sum(bool(v["neither"]) for v in real.values())
        S = {k: score(v["p_yes"]) for k, v in real.items() if v["p_yes"] is not None}
        pos_rows = [k for k in S if man[k]["label"] == "positive"]
        neg_rows = [k for k in S if man[k]["label"] == "negative"]
        # (a) median score over time
        a_pos, a_neg = defaultdict(list), defaultdict(list)
        for k in pos_rows:
            a_pos[int(round(man[k]["t"] - man[k]["time_of_event"]))].append(S[k])
        for k in neg_rows:
            a_neg[man[k]["t"]].append(S[k])
        trace_pos = {str(b): dict(n=len(v), median=float(np.median(v)), q25=float(np.percentile(v, 25)),
                                  q75=float(np.percentile(v, 75))) for b, v in sorted(a_pos.items())}
        trace_neg = {str(b): dict(n=len(v), median=float(np.median(v)), q25=float(np.percentile(v, 25)),
                                  q75=float(np.percentile(v, 75))) for b, v in sorted(a_neg.items())}
        # (b) AUROC at nearest whole second to the event vs all negative rows
        by_clip_pos = {}
        for k in pos_rows:
            r = man[k]
            grid = range(3, math.floor(r["duration_s"]) + 1)
            tn = min(max(int(round(r["time_of_event"])), grid[0]), grid[-1])
            if r["t"] == tn:
                by_clip_pos[r["file_name"]] = S[k]
        negc = defaultdict(list)
        for k in neg_rows:
            negc[man[k]["file_name"]].append(S[k])
        pc, nc = list(by_clip_pos), list(negc)
        pv = np.array([by_clip_pos[c] for c in pc])
        point = auc(pv, [s for c in nc for s in negc[c]])
        rng = np.random.default_rng(SEED)
        bs = []
        for _ in range(NBOOT):
            ip = rng.integers(0, len(pc), len(pc))
            ineg = rng.integers(0, len(nc), len(nc))
            bs.append(auc(pv[ip], [s for j in ineg for s in negc[nc[j]]]))
        # raw Yes per hour on negative clips
        yes_neg = sum(real[k]["p_yes"] > 0.5 for k in neg_rows)
        clips_with_yes = len({man[k]["file_name"] for k in neg_rows if real[k]["p_yes"] > 0.5})
        res["arms"][f"{m}_N{n}"] = dict(
            expected=len(exp), ok_rows=len(real), grey_ok=len(grey), attempts_rows=len(allr),
            error_rows=sum(bool(r["error"]) for r in allr), still_failed=len(keys - set(ok)), neither=nei,
            grey_yes_rate=float(np.mean([g["p_yes"] > 0.5 for g in grey if g["p_yes"] is not None])) if grey else None,
            grey_p_yes_median=float(np.median([g["p_yes"] for g in grey if g["p_yes"] is not None])) if grey else None,
            yes_rate_all_rows=float(np.mean([v["p_yes"] > 0.5 for v in real.values() if v["p_yes"] is not None])),
            a_median_score_pos_by_rel_event_s=trace_pos, a_median_score_neg_by_t=trace_neg,
            b_auroc_event_nearest_t=dict(auroc=point, ci95=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))],
                                         n_pos_clips=len(pc), n_neg_rows=len(neg_rows), n_neg_clips=len(nc)),
            raw_yes_neg=dict(yes_rows=int(yes_neg), neg_rows=len(neg_rows), neg_hours=len(neg_rows) / 3600,
                             raw_yes_per_hour=yes_neg / len(neg_rows) * 3600, neg_clips_with_any_yes=clips_with_yes,
                             neg_clips=len(nc)),
            prompt_tokens=sorted({v["prompt_tokens"] for v in real.values()}))
    # identical frames and prompt tokens across models
    ident = {}
    for n in (1, 3):
        a = {k[2]: v for k, v in last.items() if k[0] == "4BI" and k[1] == n and not v["grey"]}
        b = {k[2]: v for k, v in last.items() if k[0] == "32BI" and k[1] == n and not v["grey"]}
        common = set(a) & set(b)
        ident[f"N{n}"] = dict(compared=len(common),
                              frame_sha_mismatch=sum(a[k]["frame_sha256"] != b[k]["frame_sha256"] for k in common),
                              prompt_token_mismatch=sum(a[k]["prompt_tokens"] != b[k]["prompt_tokens"] for k in common),
                              manifest_sha_mismatch=sum(a[k]["frame_sha256"] != man[k]["small_sha256"] for k in common))
    res["checks"]["identical_across_models"] = ident
    res["checks"]["all_frames_at_or_before_t"] = all(max(r["frame_pts"]) <= r["t"] + 1e-9 for r in man.values())
    meta = json.load(open(OUT / "d14_run_meta_h100nvl.json"))
    res["checks"]["prompt_trace"] = meta.get("prompt_trace")
    flow = OUT / "d14_flow_features.csv.gz"
    if flow.exists():
        fr = list(csv.DictReader(gzip.open(flow, "rt")))
        res["checks"]["flow"] = dict(rows=len(fr), expected=sum(r["n"] == 9 for r in man.values()),
                                     nonfinite=sum(not all(math.isfinite(float(v)) for kk, v in x.items()
                                                           if kk not in ("request_id", "file_name", "t")) for x in fr))
    du = subprocess.run(["du", "-sb", str(FR)], capture_output=True, text=True).stdout.split()
    res["frames_disk"] = dict(bytes=int(du[0]) if du else None, path=str(FR),
                              unique_frames=json.load(open(OUT / "d14_sample.json"))["unique_frames"])
    # D3 offset-0 comparison (not like-for-like)
    d3 = json.load(open(D3RES))["secondary"]["e_overall"]
    res["d3_offset0_scored_auroc"] = {f"{m}_N{n}": d3[f"N{n}"]["auroc"][f"{m}/scored/0.0"]["auroc"] for m, n in ARMS}
    # joined trace for the later simulation
    with gzip.open(OUT / "d14_trace_h100nvl.jsonl.gz", "wt") as f:
        for (m, n, rid), v in sorted(last.items()):
            if v["grey"]:
                continue
            r = man[rid]
            f.write(json.dumps(dict(model=m, n=n, file_name=r["file_name"], label=r["label"], t=r["t"],
                                    time_of_event=r["time_of_event"], time_of_alert=r["time_of_alert"],
                                    duration_s=r["duration_s"], scene=r["scene"], light=r["light"],
                                    weather=r["weather"], p_yes=v["p_yes"],
                                    score=score(v["p_yes"]) if v["p_yes"] is not None else None,
                                    first_token=v["first_token"], prompt_tokens=v["prompt_tokens"],
                                    request_id=rid)) + "\n")
    # gzip raw request rows
    if REQ.exists():
        n_plain = sum(1 for _ in open(REQ))
        with open(REQ, "rb") as fi, gzip.open(str(REQ) + ".gz", "wb") as fo:
            fo.write(fi.read())
        assert sum(1 for _ in gzip.open(str(REQ) + ".gz", "rt")) == n_plain
        REQ.unlink()
    res["request_rows_total"] = len(rows)
    # size check / split
    splits = {}
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.stat().st_size > LIMIT:
            splits[p.name] = p.stat().st_size
            raise SystemExit(f"{p.name} exceeds 90 MB ({p.stat().st_size} B) — split needed (not yet implemented)")
    res["files_over_90mb"] = splits
    res["at"] = datetime.now().isoformat()
    res["_provenance"] = stamp(script="d14_analyse.py", model="4BI,32BI", device="cpu", n=len(rows))
    (OUT / "d14_results_h100nvl.json").write_text(json.dumps(res, indent=1))
    for k, v in res["arms"].items():
        b = v["b_auroc_event_nearest_t"]
        print(k, "ok", v["ok_rows"], "/", v["expected"], "err", v["error_rows"], "failed", v["still_failed"], "neither",
              v["neither"], "grey yes", v["grey_yes_rate"], "| AUROC", round(b["auroc"], 3), [round(x, 3) for x in b["ci95"]],
              "D3", round(res["d3_offset0_scored_auroc"][k], 3), "| raw yes/h", round(v["raw_yes_neg"]["raw_yes_per_hour"], 1),
              "yes all", round(v["yes_rate_all_rows"], 3), "ptok", v["prompt_tokens"][:4])
    print(json.dumps(res["checks"], default=str)[:1500])
    print(res["frames_disk"])


if __name__ == "__main__":
    main()
