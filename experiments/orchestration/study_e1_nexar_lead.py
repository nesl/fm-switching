#!/usr/bin/env python3
"""StudyE1-nexar-lead — OFFLINE ANALYSIS OF EXISTING SCORES (StudyD14-trace validation traces). CPU only.

Per event: how much earlier does cloud 32B raise a correct alarm than device 4B, at deployable false-alarm rates,
after delivery latency, and with which escalation signal?

Data: results/dashcam/study_d14_trace/ (300 validation clips; one decision per second t = 3..floor(duration);
4B-I N=1/3, 32B-I N=1/3/9; flow features). Score = log P(Yes) (D14). Grey rows are not in the trace (checked).
Cross-fitting: 2 folds by clip, stratified by label, seed 0 (StratifiedKFold(2, shuffle=True, random_state=0) over
clips sorted by name); every threshold is fit on one fold and evaluated on the other; pooled over the two directions.
Alarm rule (primary): the rule fires at second t if score(t) >= thr; first alarm = first firing second of a clip.
Secondary: 2-of-3 consecutive (fires at t if >= 2 of score(t-2..t) >= thr, within the clip).
False alarm: a negative-clip decision second at which the rule fires; FA/h = count / (negative decision seconds / 3600).
Threshold for a target: the lowest threshold whose training-fold FA/h <= target.
Part A: detection rate (positives with any alarm), first-alarm time relative to time_of_event and time_of_alert, a
timing breakdown (< event - 3 s / [-3, +2] s / > +2 s / none), paired 32B - 4B first-alarm time per positive clip
(both detected), clip bootstrap 2,000 seed 0; clips detected by one model only. AUROC-threshold lead (first offset
where event-relative AUROC >= 0.70 / 0.75) only as a D3 reference.
Part B: delivered alarm = first-alarm second + latency. Device (Orin 4B total, study_d4_orin.md / D8): N=1 0.555,
N=3 1.394, N=9 3.926 s. Cloud: H100 32B total 0.162 / 0.285 / 0.640 s (study_d4_latency.md) + upload + RTT; upload =
N x bytes per frame x 8 / uplink (raw RGB 995,328 B/frame; PNG and JPEG q90 = study_d4_latency.md per-request image
medians: PNG 354,902 / 1,057,532 / 3,188,243 B, JPEG 59,601 / 177,773 / 529,361 B for N = 1 / 3 / 9). TCP slow start
ignored. JPEG accuracy never measured: JPEG rows assume unchanged scores.
Part C: device runs 4B every second (N=1 or 3); escalates to 32B (N=1/3/9) when a signal fires; alarm = the 32B rule
at that second. Delivered at 13.6 Mbit/s, 44 ms RTT, raw frames: 4B signals add the device 4B latency; the flow
signal adds 0.261 s (d2_flow window cost on the Orin CPU, study_d4_orin.md Part C, measured at 384x216); random adds 0.
Signals: 4B P(Yes); rise in 4B log P(Yes) over the last 2 s (score(t) - score(t-2), earliest available second if t-2
is off the grid); flow LR (StandardScaler + LogisticRegression on the 17 flow features; y = 1 for positive-clip seconds
in [event - 3, event + 2], y = 0 for negative-clip seconds; fit on the training fold only); random (seed 0).
Budget b in {5, 10, 25, 50} % of seconds: the signal threshold is the training-fold quantile giving escalation on b of
all training-fold seconds; the 32B threshold is then fit on training-fold negative escalated seconds for 5 FA/h overall.
Baselines: device-only 4B and cloud-always 32B at 5 FA/h.
Sign convention: differences are 32B - 4B (negative = 32B earlier), as specified.
Writes results/orchestration/study_e1/e1_results.json (+ e1_partA_*.csv, e1_partB.csv, e1_partC.csv).
"""
import collections
import csv
import gzip
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

D14 = ROOT / "results/dashcam/study_d14_trace"
OUT = ROOT / "results/orchestration/study_e1"
ARMS = ["4BI_N1", "4BI_N3", "32BI_N1", "32BI_N3", "32BI_N9"]
TARGETS = [1, 5, 20]
NB, SEED = 2000, 0
DEV = {1: 0.555, 3: 1.394, 9: 3.926}
CLOUD = {1: 0.162, 3: 0.285, 9: 0.640}
BYTES = {"raw": {1: 995328, 3: 3 * 995328, 9: 9 * 995328},
         "png": {1: 354902, 3: 1057532, 9: 3188243},
         "jpeg_q90": {1: 59601, 3: 177773, 9: 529361}}
UPLINKS = [5, 12, 13.6, 25, 88]
RTTS = [0.022, 0.044, 0.142]
FLOW_COST = 0.261
PAIRS = [("32BI_N1", "4BI_N1"), ("32BI_N3", "4BI_N3"), ("32BI_N9", "4BI_N3")]


def load():
    trace = collections.defaultdict(dict)          # arm -> clip -> {t: (score, p_yes)}
    meta = {}
    n_grey = 0
    for l in gzip.open(D14 / "d14_trace_h100nvl.jsonl.gz", "rt"):
        r = json.loads(l)
        if r.get("grey") or r.get("label") not in ("positive", "negative"):
            n_grey += 1
            continue
        arm = f"{r['model']}_N{r['n']}"
        trace[arm].setdefault(r["file_name"], {})[int(r["t"])] = (r["score"], r["p_yes"])
        meta[r["file_name"]] = dict(label=r["label"], toe=r["time_of_event"], toa=r["time_of_alert"],
                                    dur=r["duration_s"])
    flow = {}
    rd = csv.DictReader(gzip.open(D14 / "d14_flow_features.csv.gz", "rt"))
    fcols = [c for c in rd.fieldnames if c not in ("request_id", "file_name", "t")]
    for r in rd:
        flow[(r["file_name"], int(float(r["t"])))] = [float(r[c]) for c in fcols]
    clips = sorted(meta)
    grid = {c: sorted(trace["4BI_N1"][c]) for c in clips}
    for a in ARMS:
        for c in clips:
            assert sorted(trace[a][c]) == grid[c], (a, c)
    return trace, meta, flow, fcols, clips, grid, n_grey


def auroc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    allv = np.concatenate([pos, neg])
    ranks = _rankdata(allv)
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _rankdata(x):
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return r


def folds(clips, meta):
    from sklearn.model_selection import StratifiedKFold
    y = [meta[c]["label"] == "positive" for c in clips]
    sk = StratifiedKFold(2, shuffle=True, random_state=SEED)
    out = []
    for tr, te in sk.split(np.zeros(len(clips)), y):
        out.append(([clips[i] for i in tr], [clips[i] for i in te]))
    return out


def fires(series, thr, rule):
    """series: list of scores in time order -> list of booleans (rule fires at that second)."""
    hit = [s >= thr for s in series]
    if rule == "first":
        return hit
    out = []
    for i in range(len(hit)):
        w = hit[max(0, i - 2):i + 1]
        out.append(sum(w) >= 2)
    return out


def fa_per_hour(series_by_clip, thr, rule):
    n_fire = sum(sum(fires(s, thr, rule)) for s in series_by_clip)
    n_sec = sum(len(s) for s in series_by_clip)
    return n_fire / (n_sec / 3600.0), n_fire, n_sec


def fit_thr(neg_series, target, rule):
    """Lowest threshold with training FA/h <= target (FA count monotone non-increasing in thr)."""
    vals = np.unique(np.concatenate([np.asarray(s) for s in neg_series]))
    cand = np.concatenate([vals, [np.nextafter(vals[-1], np.inf)]])
    lo, hi = 0, len(cand) - 1                      # find smallest index with fa <= target
    while lo < hi:
        mid = (lo + hi) // 2
        if fa_per_hour(neg_series, cand[mid], rule)[0] <= target:
            hi = mid
        else:
            lo = mid + 1
    return float(cand[lo])


def first_alarm(ts, series, thr, rule, mask=None):
    f = fires(series, thr, rule)
    for i, (t, x) in enumerate(zip(ts, f)):
        if x and (mask is None or mask[i]):
            return t
    return None


def boot_ci(vals, fn, rng):
    vals = np.asarray(vals, float)
    if len(vals) == 0:
        return None
    bs = [fn(vals[rng.integers(0, len(vals), len(vals))]) for _ in range(NB)]
    return [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def timing_bin(rel):
    if rel is None:
        return "none"
    return "early(<-3s)" if rel < -3 else ("near[-3,+2]" if rel <= 2 else "late(>+2s)")


def part_a(trace, meta, clips, grid, fl, rng):
    res, firsts = {}, {}
    for rule in ("first", "2of3"):
        for target in TARGETS:
            for a in ARMS:
                fa_ach, fa_n, fa_s, det = [], 0, 0, {}
                for tr, te in fl:
                    neg_tr = [[trace[a][c][t][0] for t in grid[c]] for c in tr if meta[c]["label"] == "negative"]
                    thr = fit_thr(neg_tr, target, rule)
                    neg_te = [[trace[a][c][t][0] for t in grid[c]] for c in te if meta[c]["label"] == "negative"]
                    _, n, s = fa_per_hour(neg_te, thr, rule)
                    fa_n += n
                    fa_s += s
                    for c in te:
                        if meta[c]["label"] == "positive":
                            det[c] = first_alarm(grid[c], [trace[a][c][t][0] for t in grid[c]], thr, rule)
                pos = [c for c in clips if meta[c]["label"] == "positive"]
                rel_e = [det[c] - meta[c]["toe"] for c in pos if det[c] is not None]
                rel_a = [det[c] - meta[c]["toa"] for c in pos if det[c] is not None]
                bins = collections.Counter(timing_bin(None if det[c] is None else det[c] - meta[c]["toe"]) for c in pos)
                key = f"{rule}/{target}/{a}"
                res[key] = dict(fa_per_hour_heldout=fa_n / (fa_s / 3600.0), fa_count_heldout=fa_n,
                                neg_hours=fa_s / 3600.0, target=target,
                                fa_within_x2=(fa_n / (fa_s / 3600.0)) <= 2 * target,
                                detection_rate=sum(det[c] is not None for c in pos) / len(pos),
                                n_pos=len(pos), n_detected=sum(det[c] is not None for c in pos),
                                first_alarm_rel_event=dict(median=float(np.median(rel_e)) if rel_e else None,
                                                           p25=float(np.percentile(rel_e, 25)) if rel_e else None,
                                                           p75=float(np.percentile(rel_e, 75)) if rel_e else None),
                                first_alarm_rel_alert_median=float(np.median(rel_a)) if rel_a else None,
                                timing_bins=dict(bins))
                firsts[key] = det
    paired = {}
    for rule in ("first", "2of3"):
        for target in TARGETS:
            for big, small in PAIRS:
                db, ds = firsts[f"{rule}/{target}/{big}"], firsts[f"{rule}/{target}/{small}"]
                both = [c for c in db if db[c] is not None and ds[c] is not None]
                d = [db[c] - ds[c] for c in both]
                paired[f"{rule}/{target}/{big}-{small}"] = dict(
                    n_both=len(both), only_32B=sum(db[c] is not None and ds[c] is None for c in db),
                    only_4B=sum(db[c] is None and ds[c] is not None for c in db),
                    neither=sum(db[c] is None and ds[c] is None for c in db),
                    mean_diff=float(np.mean(d)) if d else None, mean_ci=boot_ci(d, np.mean, rng),
                    median_diff=float(np.median(d)) if d else None, median_ci=boot_ci(d, np.median, rng),
                    frac_32B_earlier=float(np.mean([x < 0 for x in d])) if d else None,
                    frac_same=float(np.mean([x == 0 for x in d])) if d else None,
                    input_note=("same frames (D14: identical frame SHA-256 and prompt tokens), same stack, greedy"
                                if big[-2:] == small[-2:] else "32B N=9 vs 4B N=3: different frame count (9 vs 3 frames)"))
    return res, paired, firsts


def auroc_lead(trace, meta, clips, grid):
    """D3 reference only: event-relative AUROC at offsets k (positive row at round(toe)+k vs all negative rows)."""
    out = {}
    neg_rows = {a: [trace[a][c][t][0] for c in clips if meta[c]["label"] == "negative" for t in grid[c]] for a in ARMS}
    for a in ARMS:
        curve = {}
        for k in range(-10, 4):
            pos = []
            for c in clips:
                if meta[c]["label"] != "positive":
                    continue
                t = int(round(meta[c]["toe"])) + k
                if grid[c][0] <= t <= grid[c][-1]:
                    pos.append(trace[a][c][t][0])
            if len(pos) >= 30:
                curve[k] = dict(auroc=auroc(pos, neg_rows[a]), n_pos=len(pos))
        out[a] = dict(curve=curve, first_offset_ge_070=next((k for k in sorted(curve) if curve[k]["auroc"] >= 0.70), None),
                      first_offset_ge_075=next((k for k in sorted(curve) if curve[k]["auroc"] >= 0.75), None))
    return out


def cloud_lat(n, fmt, up, rtt):
    return CLOUD[n] + BYTES[fmt][n] * 8 / (up * 1e6) + rtt


def part_b(meta, firsts, rng):
    rows = []
    for target in TARGETS:
        for big, small in PAIRS:
            nb, ns = int(big[-1]), int(small[-1])
            db, ds = firsts[f"first/{target}/{big}"], firsts[f"first/{target}/{small}"]
            both = [c for c in db if db[c] is not None and ds[c] is not None]
            rec = [db[c] - ds[c] for c in both]
            m_rec = float(np.mean(rec)) if rec else None
            med_rec = float(np.median(rec)) if rec else None
            for fmt in BYTES:
                for rtt in RTTS:
                    # uplink at which the mean delivered difference reaches zero: rec + CLOUD + upload + rtt - DEV = 0
                    need = None if m_rec is None else DEV[ns] - m_rec - CLOUD[nb] - rtt
                    zero_up = (BYTES[fmt][nb] * 8 / need / 1e6) if (need is not None and need > 0) else None
                    for up in UPLINKS:
                        cl = cloud_lat(nb, fmt, up, rtt)
                        d = [x + cl - DEV[ns] for x in rec]
                        rows.append(dict(target=target, pair=f"{big}-{small}", fmt=fmt, uplink_mbps=up, rtt_s=rtt,
                                         cloud_latency_s=cl, device_latency_s=DEV[ns], n_both=len(both),
                                         recog_mean_diff=m_rec, recog_median_diff=med_rec,
                                         delivered_mean_diff=float(np.mean(d)) if d else None,
                                         delivered_mean_ci=boot_ci(d, np.mean, rng) if d else None,
                                         delivered_median_diff=float(np.median(d)) if d else None,
                                         frac_32B_delivered_earlier=float(np.mean([x < 0 for x in d])) if d else None,
                                         uplink_mbps_at_zero_mean=zero_up,
                                         jpeg_note="JPEG accuracy never measured; scores assumed unchanged" if fmt == "jpeg_q90" else None))
    return rows


def part_c(trace, meta, flow, clips, grid, fl, rng):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    up, rtt, fmt = 13.6, 0.044, "raw"
    rs = np.random.default_rng(SEED)
    rand = {(c, t): rs.random() for c in clips for t in grid[c]}
    results, per_clip = [], {}

    def sig_series(kind, n4, c, model=None):
        a = f"4BI_N{n4}"
        ts = grid[c]
        if kind == "conf":
            return [trace[a][c][t][1] for t in ts]
        if kind == "rise":
            sc = [trace[a][c][t][0] for t in ts]
            return [sc[i] - sc[max(0, i - 2)] for i in range(len(sc))]
        if kind == "flow":
            X = np.array([flow[(c, t)] for t in ts])
            return list(model.predict_proba(X)[:, 1])
        return [rand[(c, t)] for t in ts]

    configs = []
    for n4 in (1, 3):
        for n32 in (1, 3, 9):
            for kind in ("conf", "rise", "flow", "random"):
                for b in (0.05, 0.10, 0.25, 0.50):
                    configs.append((n4, n32, kind, b))
    for n4, n32, kind, b in configs:
        a32 = f"32BI_N{n32}"
        extra = DEV[n4] if kind in ("conf", "rise") else (FLOW_COST if kind == "flow" else 0.0)
        lat = extra + cloud_lat(n32, fmt, up, rtt)
        det, fa_n, fa_s, esc_n, esc_s = {}, 0, 0, 0, 0
        for tr, te in fl:
            model = None
            if kind == "flow":
                X, y = [], []
                for c in tr:
                    for t in grid[c]:
                        if meta[c]["label"] == "negative":
                            X.append(flow[(c, t)]); y.append(0)
                        elif meta[c]["toe"] - 3 <= t <= meta[c]["toe"] + 2:
                            X.append(flow[(c, t)]); y.append(1)
                model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(np.array(X), np.array(y))
            sig_tr = np.concatenate([sig_series(kind, n4, c, model) for c in tr])
            sthr = float(np.quantile(sig_tr, 1 - b))
            neg32 = []
            for c in tr:
                if meta[c]["label"] != "negative":
                    continue
                ss = sig_series(kind, n4, c, model)
                neg32.append([trace[a32][c][t][0] if s >= sthr else -np.inf for t, s in zip(grid[c], ss)])
            thr32 = fit_thr(neg32, 5, "first") if any(np.isfinite(x).any() for x in map(np.asarray, neg32)) else np.inf
            for c in te:
                ss = sig_series(kind, n4, c, model)
                esc = [s >= sthr for s in ss]
                esc_n += sum(esc)
                esc_s += len(esc)
                sc = [trace[a32][c][t][0] if e else -np.inf for t, e in zip(grid[c], esc)]
                if meta[c]["label"] == "negative":
                    fa_n += sum(x >= thr32 for x in sc)
                    fa_s += len(sc)
                else:
                    f = first_alarm(grid[c], sc, thr32, "first")
                    det[c] = None if f is None else f + lat
        pos = sorted(det)
        rel = [det[c] - meta[c]["toe"] for c in pos if det[c] is not None]
        key = f"4BI_N{n4}->32BI_N{n32}/{kind}/{int(b * 100)}%"
        per_clip[key] = det
        results.append(dict(policy=key, n4=n4, n32=n32, signal=kind, budget=b, latency_s=lat,
                            escalation_rate_heldout=esc_n / esc_s, fa_per_hour_heldout=fa_n / (fa_s / 3600.0),
                            detection_rate=sum(det[c] is not None for c in pos) / len(pos),
                            detection_ci=boot_ci([det[c] is not None for c in pos], np.mean, rng),
                            median_delivered_rel_event=float(np.median(rel)) if rel else None,
                            median_ci=boot_ci(rel, np.median, rng) if rel else None))
    # baselines at 5 FA/h (first rule), delivered
    base = {}
    for a in ARMS:
        n = int(a[-1])
        lat = DEV[n] if a.startswith("4B") else cloud_lat(n, fmt, up, rtt)
        det = {}
        fa_n = fa_s = 0
        for tr, te in fl:
            thr = fit_thr([[trace[a][c][t][0] for t in grid[c]] for c in tr if meta[c]["label"] == "negative"], 5, "first")
            for c in te:
                s = [trace[a][c][t][0] for t in grid[c]]
                if meta[c]["label"] == "negative":
                    fa_n += sum(x >= thr for x in s)
                    fa_s += len(s)
                else:
                    f = first_alarm(grid[c], s, thr, "first")
                    det[c] = None if f is None else f + lat
        pos = sorted(det)
        rel = [det[c] - meta[c]["toe"] for c in pos if det[c] is not None]
        key = ("device-only " if a.startswith("4B") else "cloud-always ") + a
        per_clip[key] = det
        base[key] = dict(latency_s=lat, fa_per_hour_heldout=fa_n / (fa_s / 3600.0),
                         detection_rate=sum(det[c] is not None for c in pos) / len(pos),
                         detection_ci=boot_ci([det[c] is not None for c in pos], np.mean, rng),
                         median_delivered_rel_event=float(np.median(rel)) if rel else None,
                         median_ci=boot_ci(rel, np.median, rng) if rel else None)
    # signal vs 4B-confidence at the same (n4, n32, budget): paired detection and delivered time
    vs_conf = []
    for r in results:
        if r["signal"] == "conf":
            continue
        kc = r["policy"].replace(f"/{r['signal']}/", "/conf/")
        A, C = per_clip[r["policy"]], per_clip[kc]
        dd = [float(A[c] is not None) - float(C[c] is not None) for c in A]
        both = [c for c in A if A[c] is not None and C[c] is not None]
        dt = [A[c] - C[c] for c in both]
        vs_conf.append(dict(policy=r["policy"], vs=kc, det_diff=float(np.mean(dd)), det_diff_ci=boot_ci(dd, np.mean, rng),
                            time_diff_median=float(np.median(dt)) if dt else None,
                            time_diff_ci=boot_ci(dt, np.median, rng) if dt else None, n_both=len(both)))
    return results, base, vs_conf


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trace, meta, flow, fcols, clips, grid, n_grey = load()
    rng = np.random.default_rng(SEED)
    res = dict(label="OFFLINE ANALYSIS OF EXISTING SCORES (StudyD14-trace validation traces); no new inference",
               at=datetime.now().isoformat(), checks={})
    # sanity 1: D14 offset-0 AUROCs
    d14 = json.loads((D14 / "d14_results_h100nvl.json").read_text())
    rep = {}
    for a in ARMS:
        pos = [trace[a][c][min(max(int(round(meta[c]["toe"])), grid[c][0]), grid[c][-1])][0]
               for c in clips if meta[c]["label"] == "positive"]
        neg = [trace[a][c][t][0] for c in clips if meta[c]["label"] == "negative" for t in grid[c]]
        ours = auroc(pos, neg)
        ref = d14["arms"][a]["b_auroc_event_nearest_t"]["auroc"]
        rep[a] = dict(ours=ours, d14=ref, abs_diff=None if ref is None else abs(ours - ref), n_pos=len(pos), n_neg=len(neg))
    res["checks"]["d14_auroc_reproduction"] = rep
    res["checks"]["grey_rows_excluded"] = n_grey
    res["checks"]["positives_with_time_of_event"] = sum(1 for c in clips if meta[c]["label"] == "positive" and meta[c]["toe"] is not None)
    res["checks"]["n_pos"] = sum(1 for c in clips if meta[c]["label"] == "positive")
    res["checks"]["n_neg"] = sum(1 for c in clips if meta[c]["label"] == "negative")
    res["checks"]["decision_seconds"] = sum(len(grid[c]) for c in clips)
    if any(v["abs_diff"] is None or v["abs_diff"] > 0.002 for v in rep.values()) or \
            res["checks"]["positives_with_time_of_event"] != res["checks"]["n_pos"]:
        (OUT / "e1_results.json").write_text(json.dumps(res, indent=1, default=float))
        print(json.dumps(res["checks"], indent=1, default=float))
        raise SystemExit("SANITY CHECK FAILED — stop and ask")
    fl = folds(clips, meta)
    res["folds"] = [dict(train=len(tr), test=len(te), test_pos=sum(meta[c]["label"] == "positive" for c in te)) for tr, te in fl]
    res["partA"], res["partA_paired"], firsts = part_a(trace, meta, clips, grid, fl, rng)
    res["partA_auroc_lead_D3_reference"] = auroc_lead(trace, meta, clips, grid)
    res["partB"] = part_b(meta, firsts, rng)
    res["partC"], res["partC_baselines"], res["partC_vs_conf"] = part_c(trace, meta, flow, clips, grid, fl, rng)
    res["_provenance"] = stamp(script="study_e1_nexar_lead.py", model="4BI,32BI (scores)", device="cpu", n=len(clips))
    (OUT / "e1_results.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["checks"], indent=1, default=float)[:3000])


if __name__ == "__main__":
    main()
