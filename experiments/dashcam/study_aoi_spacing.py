#!/usr/bin/env python3
"""StudyAOI-spacing - do dashcam cloud checks interact over time? OFFLINE, committed data only.

CPU ONLY on the Jetson AGX Orin host: no GPU, no model server, no inference. Every score is read
from a committed body; every metric is computed with the committed scorer, imported rather than
re-implemented, so this study cannot drift from StudyE9b / StudyE9c / StudyE9d / StudyCTRL1c.

THE QUESTION. We currently treat each dashcam decision instant (every 0.5 s) as an independent
opportunity. Two offline tests decide whether an age-of-information view is warranted:
  (1) does the SPACING of cloud checks matter, at a fixed cloud-served budget f, on the dataset's
      own metric (streaming AP, and the challenge mAP)?
  (2) does any dependence show up at particular horizons before the event (challenge AP per
      horizon), even if pooled AP hides it?
AP stays the headline. No first-Yes / time-to-alert / threshold-crossing measure is added (those
were rejected for this project: the models are Yes/No-biased and the challenge metric is decided).

DATA (all committed; cited in the report and the output JSON _provenance / sources block):
  device (Orin 4B) per-instant raw score  results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz
  cloud  (32B JPEG)  per-instant raw score results/orchestration/live2/pre/live2_pre_part2_requests.jsonl.gz
  clip meta (label, event, alert, duration, grid) results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz
  D105 FINAL calibration maps + 5-fold-by-clip fold map
      results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json
      (cross-fitted: each clip calibrated out of fold by folds.maps[fold(clip)], device tier
       'device_4b_orin', cloud tier 'h100_32b'; logit = a*score + b, the committed apply_map)
  fold definition (D6 / StudyCTRL1b)  results/dashcam/ctrl1b/d14b_folds.json  (assignment identical
      to the calibration file's, verified)

SCORERS (imported, never re-implemented):
  streaming AP  study_e9b_dense.ApEngine  (StudyE9b: 0.5 s decisions held forward onto the 0.25 s
      grid; positives one crop per horizon at event-h, negatives every grid point)
  challenge mAP study_e9d_delay.Challenge (StudyE9c's one-crop-per-clip metric at horizons
      0.5 / 1.0 / 1.5 s, unweighted mean; the per-horizon AP is the time-resolved view)
  calibration   ctrl1c_calibrate.apply_map (logit = a*score + b)

SCHEDULES. At each cloud-served fraction f in {0.10, 0.25, 0.50, 0.75} we decide, per clip, which
of its 0.5 s decision instants are cloud-served; a served instant takes the (calibrated) cloud
score, every other instant the (calibrated) device score, held forward one 0.25 s point.
  EVEN      - m = round(n*f) served instants, evenly spaced, random phase per clip (100 seeds)
  CLUSTERED - contiguous blocks of k in {2,4,8}, spaced to give fraction f, random phase (100 seeds)
  RANDOM    - i.i.d. Bernoulli(f) per instant (100 seeds)
  references: device-only (f=0), always-cloud (f=1)
  sanity:     FRONT-loaded, BACK-loaded (first / last f of each clip)
No cloud transit latency is modelled: this study isolates the VALUE OF SPACING at a fixed budget,
not the cost of delay (StudyE9d studies delay). Stated PROVISIONAL and recorded in the JSON.
"""
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "experiments/lib", ROOT / "experiments/dashcam",
          ROOT / "experiments/orchestration/sim", ROOT / "experiments/orchestration/baselines"):
    sys.path.insert(0, str(p))

from _provenance import stamp                 # noqa: E402
import metrics as M                           # noqa: E402
M._ensure_sklearn_importable()                # install the raising sklearn stub BEFORE the imports
import study_e9b_dense as B                   # noqa: E402  (ApEngine, target_index, T0, STEP_DENSE)
import study_e9c_challenge as Cq              # noqa: E402  (read_clip_meta, geometry)
import study_e9d_delay as D                   # noqa: E402  (Challenge, ap_fast)
import ctrl1c_calibrate as CAL                # noqa: E402  (apply_map)

OUT = ROOT / "results/dashcam/study_aoi"
DEV_BODY = ROOT / "results/dashcam/study_orin1/orin1_dense_scores.jsonl.gz"
CLOUD_BODY = ROOT / "results/orchestration/live2/pre/live2_pre_part2_requests.jsonl.gz"
CALIB = ROOT / "results/orchestration/live2/calibration/live2_calibration_dense_jpeg.json"
FOLDS = ROOT / "results/dashcam/ctrl1b/d14b_folds.json"
E9C = ROOT / "results/dashcam/study_e9c/e9c_results.json"

STEP = B.STEP_DENSE                 # 0.25 s scoring grid
T0 = B.T0                           # 3.0 s
DECISION_CADENCE_S = 0.5            # the dashcam decision cadence
DSTEP = int(round(DECISION_CADENCE_S / STEP))   # 2 grid points per decision
STREAM_H = (0.0, 0.5, 1.0, 1.5)     # streaming-AP horizons (StudyE9b / CTRL1c)
PRIMARY_H = (0.5, 1.0, 1.5)         # CTRL1c primary streaming horizons
CHAL_H = Cq.HORIZONS                # (0.5, 1.0, 1.5) challenge horizons
FRACTIONS = (0.10, 0.25, 0.50, 0.75)
CLUSTER_K = (2, 4, 8)
N_SEED = 100                        # phase / draw seeds per schedule family (prompt)
NB = B.NB                           # 2000 clip-bootstrap resamples (committed)
ACF_MAX_LAG = 12                    # decisions (= 6.0 s)
DEV_KEY, CLOUD_KEY = "device_4b_orin", "h100_32b"


# ======================================================================== data
def _read_dev():
    """clip -> np.array of raw device (Orin 4B) scores on the 0.25 s grid from t=3.0."""
    per = {}
    for ln in gzip.open(DEV_BODY, "rt"):
        r = json.loads(ln)
        c = r["file_name"]
        i = int(round((float(r["t"]) - T0) / STEP))
        per.setdefault(c, {})[i] = float(r["score"])
    return _to_arrays(per)


def _read_cloud():
    """clip -> np.array of raw cloud (32B JPEG) scores. frame_ref = '00005.mp4|t0003.00'."""
    per = {}
    for ln in gzip.open(CLOUD_BODY, "rt"):
        r = json.loads(ln)
        c, ts = r["frame_ref"].split("|")
        t = float(ts.replace("t", ""))
        i = int(round((t - T0) / STEP))
        per.setdefault(c, {})[i] = float(r["score"])
    return _to_arrays(per)


def _to_arrays(per):
    out = {}
    for c, d in per.items():
        idx = sorted(d)
        assert idx == list(range(idx[-1] + 1)), (c, "missing grid point")
        out[c] = np.array([d[i] for i in idx], dtype=float)
    return out


def _meta():
    """clip -> {label, event, alert, dur, G, T_last} from the committed D14b trace (4BI_N1 arm)."""
    cm = Cq.read_clip_meta()           # label, duration, event, alert from the committed trace
    return cm


def load_calibration():
    cal = json.loads(CALIB.read_text())
    assert cal.get("label") == "FINAL", "calibration file is not the FINAL (D105) map"
    folds = cal["folds"]
    assignment = folds["assignment"]
    maps = {int(k): v for k, v in folds["maps"].items()}
    # cross-check the committed fold definition (D6 / StudyCTRL1b)
    fd = json.loads(FOLDS.read_text())
    same = (fd["assignment"] == assignment)
    return cal, assignment, maps, dict(folds_file=str(FOLDS.relative_to(ROOT)),
                                       fold_assignment_matches_ctrl1b=bool(same),
                                       n_folds=folds["n_folds"], by=folds["by"],
                                       fold_rule=cal.get("fold_rule"))


def platt(m):
    return dict(kind="platt", a=float(m["a"]), b=float(m["b"]))


def calibrate_oof(raw, assignment, maps, tier_key):
    """Every clip calibrated by the map of ITS OWN fold (fitted on the other four): the committed
    crossfit convention. Returns clip -> calibrated logit array (a*score + b)."""
    out = {}
    for c, v in raw.items():
        m = platt(maps[assignment[c]][tier_key])
        out[c] = CAL.apply_map(m, v)
    return out


# ==================================================================== schedules
def even_served(n, f, phase):
    """m = round(n*f) evenly spaced served decision indices in [0, n), with a phase in [0,1)."""
    m = int(round(n * f))
    served = np.zeros(n, dtype=bool)
    if m <= 0:
        return served
    if m >= n:
        served[:] = True
        return served
    pos = np.floor((np.arange(m) + phase) * n / m).astype(int)
    pos = np.clip(pos, 0, n - 1)
    served[np.unique(pos)] = True
    return served


def clustered_served(n, f, k, phase):
    """Blocks of length k, spaced to give fraction f, random phase; blocks clipped to the clip."""
    served = np.zeros(n, dtype=bool)
    target = int(round(n * f))
    if target <= 0:
        return served
    if target >= n:
        served[:] = True
        return served
    nb = max(1, int(round(target / k)))
    starts = np.floor((np.arange(nb) + phase) * n / nb).astype(int)
    for s in starts:
        served[s:min(s + k, n)] = True
    return served


def random_served(n, f, rng):
    return rng.random(n) < f


def front_served(n, f):
    m = int(np.ceil(n * f))
    served = np.zeros(n, dtype=bool)
    served[:m] = True
    return served


def back_served(n, f):
    m = int(np.ceil(n * f))
    served = np.zeros(n, dtype=bool)
    if m:
        served[n - m:] = True
    return served


def build_streams(dev_cal, cloud_cal, clips, dec_idx, served_by_clip):
    """Delivered calibrated score per 0.25 s grid point: the chosen tier's value at each 0.5 s
    decision, held forward onto the skipped 0.25 s point (StudyE9b hold; StudyLIVE2 _ap_streams)."""
    streams = {}
    for c in clips:
        g = dev_cal[c].shape[0]
        di = dec_idx[c]
        served = served_by_clip[c]
        arr = np.empty(g, dtype=float)
        src = np.where(served, cloud_cal[c][di], dev_cal[c][di])   # value at each decision index
        for j, gi in enumerate(di):
            arr[gi] = src[j]
            if gi + 1 < g:
                arr[gi + 1] = src[j]
        streams[c] = arr
    return streams


# ====================================================================== scoring
def score(streams, eng, chal):
    sap, sboot = eng.full(streams)
    cap, cboot = chal.full(streams)
    pt = dict(streaming={float(h): float(sap[h]["ap"]) for h in STREAM_H},
              streaming_primary=float(np.mean([sap[h]["ap"] for h in PRIMARY_H])),
              challenge={float(h): float(cap[h]["ap"]) for h in CHAL_H},
              challenge_mAP=float(cap["mAP"]["value"]))
    boot = dict(streaming={h: sboot[h] for h in STREAM_H},
                streaming_primary=np.mean([sboot[h] for h in PRIMARY_H], axis=0),
                challenge={h: cboot["ap"][h] for h in CHAL_H},
                challenge_mAP=cboot["mAP"])
    return pt, boot


def pct_ci(v):
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def accumulate(seeds_pts, seeds_boots):
    """Mean over seeds of the point values and of the per-resample bootstrap vectors (StudyE9d's
    placement-averaging convention), so the family's CI and the paired difference are shared and
    paired on the same clip resamples."""
    n = len(seeds_pts)
    acc_pt = dict(streaming={h: float(np.mean([p["streaming"][h] for p in seeds_pts]))
                             for h in [float(x) for x in STREAM_H]},
                  streaming_primary=float(np.mean([p["streaming_primary"] for p in seeds_pts])),
                  challenge={h: float(np.mean([p["challenge"][h] for p in seeds_pts]))
                             for h in [float(x) for x in CHAL_H]},
                  challenge_mAP=float(np.mean([p["challenge_mAP"] for p in seeds_pts])))
    acc_boot = dict(streaming={h: np.mean([b["streaming"][h] for b in seeds_boots], axis=0)
                               for h in STREAM_H},
                    streaming_primary=np.mean([b["streaming_primary"] for b in seeds_boots], axis=0),
                    challenge={h: np.mean([b["challenge"][h] for b in seeds_boots], axis=0)
                               for h in CHAL_H},
                    challenge_mAP=np.mean([b["challenge_mAP"] for b in seeds_boots], axis=0))
    return acc_pt, acc_boot, n


def cell_summary(pt, boot, achieved_f):
    return dict(
        achieved_cloud_fraction=achieved_f,
        streaming={str(h): dict(ap=pt["streaming"][float(h)], ci=pct_ci(boot["streaming"][h]))
                   for h in STREAM_H},
        streaming_primary=dict(ap=pt["streaming_primary"], ci=pct_ci(boot["streaming_primary"])),
        challenge={str(h): dict(ap=pt["challenge"][float(h)], ci=pct_ci(boot["challenge"][h]))
                   for h in CHAL_H},
        challenge_mAP=dict(ap=pt["challenge_mAP"], ci=pct_ci(boot["challenge_mAP"])))


def paired(a_pt, a_boot, b_pt, b_boot, label):
    """a - b, paired on the shared clip resamples (and seed-averaged). excludes_zero if CI avoids 0."""
    def one(av, bv, ab, bb):
        d = ab - bb
        lo, hi = pct_ci(d)
        return dict(diff=float(av - bv), ci=[lo, hi],
                    excludes_zero=bool(lo > 0 or hi < 0),
                    a_beats_b=bool(lo > 0), b_beats_a=bool(hi < 0))
    out = dict(comparison=label,
               streaming_primary=one(a_pt["streaming_primary"], b_pt["streaming_primary"],
                                     a_boot["streaming_primary"], b_boot["streaming_primary"]),
               streaming={}, challenge={})
    for h in STREAM_H:
        out["streaming"][str(h)] = one(a_pt["streaming"][float(h)], b_pt["streaming"][float(h)],
                                       a_boot["streaming"][h], b_boot["streaming"][h])
    for h in CHAL_H:
        out["challenge"][str(h)] = one(a_pt["challenge"][float(h)], b_pt["challenge"][float(h)],
                                       a_boot["challenge"][h], b_boot["challenge"][h])
    out["challenge_mAP"] = one(a_pt["challenge_mAP"], b_pt["challenge_mAP"],
                               a_boot["challenge_mAP"], b_boot["challenge_mAP"])
    return out


# ================================================================= autocorrelation
def gain_autocorr(dev_cal, cloud_cal, clips, dec_idx):
    """Per-clip autocorrelation of the cloud-minus-device calibrated-score gain at the 0.5 s
    decision cadence, averaged across clips with enough decisions. Gives the redundancy timescale:
    the lag at which consecutive-instant gain decorrelates."""
    acf = {lag: [] for lag in range(ACF_MAX_LAG + 1)}
    means, vars_ = [], []
    nclip = 0
    for c in clips:
        di = dec_idx[c]
        g = cloud_cal[c][di] - dev_cal[c][di]
        n = g.shape[0]
        if n < ACF_MAX_LAG + 2:
            continue
        nclip += 1
        gm = g - g.mean()
        c0 = float(np.dot(gm, gm) / n)
        means.append(float(g.mean()))
        vars_.append(c0)
        if c0 <= 0:
            continue
        for lag in range(ACF_MAX_LAG + 1):
            ck = float(np.dot(gm[:n - lag], gm[lag:]) / n)
            acf[lag].append(ck / c0)
    mean_acf = {lag: float(np.mean(acf[lag])) for lag in acf}
    # redundancy timescale: first lag whose mean ACF drops below 1/e and below 0
    inv_e = 1.0 / np.e
    tau_inv_e = next((lag * DECISION_CADENCE_S for lag in range(ACF_MAX_LAG + 1)
                      if mean_acf[lag] < inv_e), None)
    tau_zero = next((lag * DECISION_CADENCE_S for lag in range(ACF_MAX_LAG + 1)
                     if mean_acf[lag] < 0.0), None)
    return dict(
        n_clips=nclip, lag_step_s=DECISION_CADENCE_S,
        mean_acf_by_lag={str(lag * DECISION_CADENCE_S): mean_acf[lag] for lag in acf},
        n_clips_per_lag={str(lag * DECISION_CADENCE_S): len(acf[lag]) for lag in acf},
        gain_mean=float(np.mean(means)), gain_mean_abs=float(np.mean(np.abs(means))),
        gain_var_mean=float(np.mean(vars_)),
        redundancy_timescale_s_1_over_e=tau_inv_e,
        redundancy_timescale_s_zero_crossing=tau_zero,
        note=("gain_t = calibrated_cloud_logit - calibrated_device_logit at each 0.5 s decision; "
              "ACF averaged over clips with at least %d decisions; the 1/e lag is the redundancy "
              "timescale (how long the cloud's per-instant advantage stays correlated)."
              % (ACF_MAX_LAG + 2)))


# ============================================================================ main
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    smoke = "--smoke" in sys.argv

    cm = _meta()
    dev_raw, cloud_raw = _read_dev(), _read_cloud()
    clips = sorted(cm)
    assert set(dev_raw) == set(clips) == set(cloud_raw), "clip set mismatch across bodies"

    # meta for the scorers: label, event, G (grid points), T_last
    meta = {}
    for c in clips:
        g = dev_raw[c].shape[0]
        assert cloud_raw[c].shape[0] == g, (c, "device/cloud grid length mismatch")
        meta[c] = dict(label=cm[c]["label"], event=cm[c]["event"], dur=cm[c]["duration"],
                       alert=cm[c]["alert"], G=g, T_last=T0 + (g - 1) * STEP)
    pos = [c for c in clips if meta[c]["label"] == "positive"]
    neg = [c for c in clips if meta[c]["label"] == "negative"]

    cal, assignment, maps, fold_info = load_calibration()
    dev_cal = calibrate_oof(dev_raw, assignment, maps, DEV_KEY)
    cloud_cal = calibrate_oof(cloud_raw, assignment, maps, CLOUD_KEY)

    dec_idx = {c: np.arange(0, meta[c]["G"], DSTEP) for c in clips}
    n_dec = {c: dec_idx[c].shape[0] for c in clips}
    total_dec = int(sum(n_dec.values()))

    ctx = dict(meta=meta, pos=pos, neg=neg, clips=clips, step=STEP)
    eng = B.ApEngine(meta, pos, neg, STREAM_H, STEP)
    chal = D.Challenge(ctx)

    res = dict(
        label="StudyAOI-spacing: does the SPACING of cloud checks matter at a fixed budget, on the "
              "Nexar metric (streaming AP and challenge mAP), and at which horizons before the "
              "event? OFFLINE ANALYSIS OF COMMITTED RESULTS; CPU only on the Orin; no GPU, no model "
              "server, no inference. Scores are continuous log P(Yes), calibrated per tier out of "
              "fold with the D105 FINAL maps; no literal Yes/No answer is used. No cloud transit "
              "latency is modelled (this isolates the value of SPACING at a fixed budget, not the "
              "cost of delay, which StudyE9d covers).",
        at=datetime.now().isoformat(), host="jetson_orin", seed_bootstrap=B.SEED, n_bootstrap=NB,
        n_phase_seeds=N_SEED, step_s=STEP, decision_cadence_s=DECISION_CADENCE_S,
        streaming_horizons=list(STREAM_H), primary_streaming_horizons=list(PRIMARY_H),
        challenge_horizons=list(CHAL_H), fractions=list(FRACTIONS), cluster_k=list(CLUSTER_K),
        n_clips=dict(positive=len(pos), negative=len(neg)),
        decision_instants_total=total_dec,
        decision_instants_per_clip=dict(min=int(min(n_dec.values())),
                                        max=int(max(n_dec.values())),
                                        mean=float(np.mean(list(n_dec.values())))),
        sources=dict(
            device_body=str(DEV_BODY.relative_to(ROOT)) + " (Orin 4B, StudyORIN1-dense)",
            cloud_body=str(CLOUD_BODY.relative_to(ROOT)) + " (32B JPEG, StudyLIVE2-pre Part 2)",
            clip_meta=str((ROOT / 'results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz')
                          .relative_to(ROOT)) + " (labels, event, alert, duration, grid; 4BI_N1 arm)",
            calibration=str(CALIB.relative_to(ROOT)) + " (D105 FINAL, cross-fitted out of fold)",
            device_tier_key=DEV_KEY, cloud_tier_key=CLOUD_KEY, **fold_info),
        device_proxy_note=M.DEVICE_PROXY_NOTE if hasattr(M, "DEVICE_PROXY_NOTE") else None,
        provisional_decisions=[
            "No cloud transit latency: a served instant delivers its cloud score at its own 0.5 s "
            "decision point, held forward one 0.25 s point (zero added delay). This isolates "
            "SPACING at a fixed budget; StudyE9d covers the cost of delay. PROVISIONAL.",
            "Cloud-served fraction f is the fraction of a clip's 0.5 s DECISION instants served by "
            "the cloud; references are device-only (f=0) and always-cloud (f=1). PROVISIONAL.",
            "Schedule randomness: 100 phase/draw seeds per family; metric and bootstrap vector "
            "averaged over seeds (StudyE9d placement convention). PROVISIONAL."],
        calibration_maps_used={str(k): dict(device=platt(maps[k][DEV_KEY]),
                                            cloud=platt(maps[k][CLOUD_KEY])) for k in maps},
        references={}, families={}, paired_vs_random={}, largest_gap={}, autocorrelation={},
        controls={}, consistency_check={})

    # ---------------------------------------------------------------- references
    for name, sv in (("device-only", {c: np.zeros(n_dec[c], dtype=bool) for c in clips}),
                     ("always-cloud", {c: np.ones(n_dec[c], dtype=bool) for c in clips})):
        streams = build_streams(dev_cal, cloud_cal, clips, dec_idx, sv)
        pt, boot = score(streams, eng, chal)
        af = sum(int(sv[c].sum()) for c in clips) / total_dec
        res["references"][name] = cell_summary(pt, boot, af)
        res["references"][name + "__boot_keep"] = None
        globals()[f"_ref_{name}"] = (pt, boot)   # keep for controls
        print("reference %-12s streaming_primary %.4f challenge_mAP %.4f"
              % (name, pt["streaming_primary"], pt["challenge_mAP"]), flush=True)

    fracs = FRACTIONS if not smoke else (0.25,)
    seeds = N_SEED if not smoke else 5

    # ---------------------------------------------------------------- sweep
    fam_boot = {}      # (family, f) -> (acc_pt, acc_boot)
    for f in fracs:
        res["families"][str(f)] = {}
        families = {"EVEN": ("even", None), "RANDOM": ("random", None)}
        for k in CLUSTER_K:
            families[f"CLUSTERED_k{k}"] = ("clustered", k)
        for fam, (kind, k) in families.items():
            seeds_pt, seeds_boot, served_counts = [], [], 0
            for sd in range(seeds):
                rng = np.random.default_rng([B.SEED, hash(fam) & 0xFFFF, int(f * 1000), sd])
                sv = {}
                for c in clips:
                    n = n_dec[c]
                    ph = float(rng.random())
                    if kind == "even":
                        sv[c] = even_served(n, f, ph)
                    elif kind == "clustered":
                        sv[c] = clustered_served(n, f, k, ph)
                    else:
                        sv[c] = random_served(n, f, rng)
                served_counts += sum(int(sv[c].sum()) for c in clips)
                streams = build_streams(dev_cal, cloud_cal, clips, dec_idx, sv)
                pt, boot = score(streams, eng, chal)
                seeds_pt.append(pt)
                seeds_boot.append(boot)
            acc_pt, acc_boot, nseed = accumulate(seeds_pt, seeds_boot)
            achieved = served_counts / (total_dec * seeds)
            res["families"][str(f)][fam] = cell_summary(acc_pt, acc_boot, achieved)
            res["families"][str(f)][fam]["n_seeds"] = nseed
            fam_boot[(fam, f)] = (acc_pt, acc_boot)
            print("  f=%.2f %-14s streaming_primary %.4f challenge_mAP %.4f (served %.3f)"
                  % (f, fam, acc_pt["streaming_primary"], acc_pt["challenge_mAP"], achieved),
                  flush=True)

        # paired: EVEN vs RANDOM, CLUSTERED_k vs RANDOM
        rpt, rboot = fam_boot[("RANDOM", f)]
        res["paired_vs_random"][str(f)] = {}
        for fam in ["EVEN"] + [f"CLUSTERED_k{k}" for k in CLUSTER_K]:
            apt, aboot = fam_boot[(fam, f)]
            res["paired_vs_random"][str(f)][fam] = paired(apt, aboot, rpt, rboot,
                                                          f"{fam} - RANDOM @ f={f}")

        # sanity: FRONT / BACK (point only, no bootstrap families)
        for name, fn in (("FRONT", front_served), ("BACK", back_served)):
            sv = {c: fn(n_dec[c], f) for c in clips}
            streams = build_streams(dev_cal, cloud_cal, clips, dec_idx, sv)
            pt, boot = score(streams, eng, chal)
            af = sum(int(sv[c].sum()) for c in clips) / total_dec
            res["families"][str(f)][name] = cell_summary(pt, boot, af)

    # ---------------------------------------------------------------- largest gap
    for metric in ("streaming_primary", "challenge_mAP"):
        rows = {}
        for f in fracs:
            e = res["paired_vs_random"][str(f)]["EVEN"][metric]
            cworst = max((res["paired_vs_random"][str(f)][f"CLUSTERED_k{k}"][metric]
                          for k in CLUSTER_K), key=lambda d: -d["diff"])
            rows[str(f)] = dict(even_minus_random=e["diff"], even_excludes_zero=e["excludes_zero"],
                                worst_clustered_minus_random=cworst["diff"],
                                clustered_excludes_zero=cworst["excludes_zero"])
        best_even = max(fracs, key=lambda f: abs(rows[str(f)]["even_minus_random"]))
        best_clu = min(fracs, key=lambda f: rows[str(f)]["worst_clustered_minus_random"])
        res["largest_gap"][metric] = dict(by_fraction=rows, f_largest_even_gap=best_even,
                                          f_largest_clustered_loss=best_clu,
                                          target_fraction_note="0.25 is the current per-device target")

    # ---------------------------------------------------------------- autocorrelation
    res["autocorrelation"] = gain_autocorr(dev_cal, cloud_cal, clips, dec_idx)
    print("redundancy timescale (1/e): %s s" %
          res["autocorrelation"]["redundancy_timescale_s_1_over_e"], flush=True)

    # ---------------------------------------------------------------- controls
    # (1) negative control: cloud == device -> spacing cannot matter; all schedules coincide.
    worst = 0.0
    f0 = fracs[0]
    base_streams = None
    for fam, (kind, k) in (("EVEN", ("even", None)), ("RANDOM", ("random", None)),
                           ("CLUSTERED_k4", ("clustered", 4))):
        rng = np.random.default_rng([B.SEED, 7, fam == "RANDOM"])
        sv = {}
        for c in clips:
            n = n_dec[c]
            ph = float(rng.random())
            sv[c] = (even_served(n, f0, ph) if kind == "even" else
                     clustered_served(n, f0, k, ph) if kind == "clustered" else
                     random_served(n, f0, rng))
        streams = build_streams(dev_cal, dev_cal, clips, dec_idx, sv)   # cloud := device
        pt, _ = score(streams, eng, chal)
        dev_pt = globals()["_ref_device-only"][0]
        worst = max(worst, abs(pt["streaming_primary"] - dev_pt["streaming_primary"]),
                    abs(pt["challenge_mAP"] - dev_pt["challenge_mAP"]))
    res["controls"]["negative_cloud_equals_device"] = dict(
        description="With the cloud score set equal to the device score, spacing carries no "
                    "information, so every schedule must reproduce device-only exactly.",
        worst_abs_diff_vs_device_only=float(worst), passes=bool(worst < 1e-9))

    # (2) f=0 / f=1 coincidence is structural (device-only / always-cloud); recorded by reference.
    res["controls"]["endpoints"] = dict(
        description="f=0 is device-only and f=1 is always-cloud by construction; all families "
                    "collapse to these at the endpoints.",
        device_only_streaming_primary=res["references"]["device-only"]["streaming_primary"]["ap"],
        always_cloud_streaming_primary=res["references"]["always-cloud"]["streaming_primary"]["ap"])

    # ---------------------------------------------------------------- consistency check
    rows = []
    try:
        s2 = json.loads(E9C.read_text())
        ac = globals()["_ref_always-cloud"][0]
        dv = globals()["_ref_device-only"][0]
        for h in CHAL_H:
            rows.append(dict(quantity="challenge AP always-cloud h=%s" % h,
                             this_run=ac["challenge"][float(h)],
                             prior=s2["arms"]["always-cloud 32BI_N1|measured@25"]["ap"][str(h)]["ap"],
                             prior_source="StudyE9c 32BI_N1 measured@25 (PNG H100 32B, with latency)"))
        rows.append(dict(quantity="challenge mAP always-cloud",
                         this_run=ac["challenge_mAP"],
                         prior=s2["arms"]["always-cloud 32BI_N1|measured@25"]["mAP"]["value"],
                         prior_source="StudyE9c"))
    except Exception as e:
        rows.append(dict(note="StudyE9c cross-check skipped: %s" % e))
    res["consistency_check"] = dict(
        note=("Single-tier AP is invariant to a monotone per-tier calibration, so always-cloud / "
              "device-only AP depends only on the raw scores. This run's cloud is the 32B JPEG body "
              "and device is the Orin 4B, while StudyE9c used the PNG H100 32B/4B trace WITH cloud "
              "latency, so these are a PLAUSIBILITY check (expected close, not identical), not an "
              "exact reproduction."), rows=rows)

    # strip the throwaway keep-keys
    for k in [k for k in res["references"] if k.endswith("__boot_keep")]:
        del res["references"][k]

    res["_provenance"] = stamp(script="study_aoi_spacing.py", model=None, device="cpu",
                               n=len(clips), args=sys.argv[1:])
    name = "aoi_spacing_results.json" if not smoke else "aoi_spacing_smoke.json"
    (OUT / name).write_text(json.dumps(res, indent=1, default=float))
    print("\nwrote", OUT / name)


if __name__ == "__main__":
    main()
