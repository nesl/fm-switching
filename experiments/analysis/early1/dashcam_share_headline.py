#!/usr/bin/env python3
"""Dashcam oracle on the HEADLINE metric (Nexar challenge mAP, D199): per-arm share

    share = (arm mAP - device-only mAP) / (ceiling mAP - device-only mAP)

ceiling = cloud-every-instant delivered stream (every trace instant scored by the dense simplestream
cloud score through the cloud Platt map; DSMAP Part 2 method). Pooled across 1x seeds 4 to 7; one value
per source clip (mean over seeds and plays), as in StudyDSMAP. Paired clip-clustered bootstrap CI
(2000 resamples, seed 0): every arm, device and ceiling use the same clip resamples in each draw.

Positive control: device-only and the arms' ALL-split mAP must reproduce the committed DSMAP values in
reports/figures/dsmap_results.json (device-only 0.627985) before any share is reported.
Minimum detectable difference: 2 x 1.96 x SE(share) (paired). Clips needed to resolve the ceiling gap:
N' = N x (2 x 1.96 x SE(gap) / gap)^2, the clip count at which the 95% half-width of the ceiling minus
device-only gap equals half the gap.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/early1"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import dsmap as D  # noqa: E402
import episodic_lib as E  # noqa: E402
import oracle_lp_run as R  # noqa: E402
from _provenance import stamp  # noqa: E402
from collections import defaultdict  # noqa: E402

SEEDS = [4, 5, 6, 7]
NB = 2000
SEED = 0
ARMS = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]
CH = D.CHALLENGE


def ceiling_crops(seed, cal, dur, labels, fake):
    """Cloud-every-instant delivered stream: every trace instant scored by the dense cloud score."""
    a4, b4, a32, b32 = cal
    tr = D._trace(seed)
    cloud = R.simplestream_cloud(seed, "")
    by_clip = defaultdict(list)
    for oid, (clip, pts, dscore) in tr.items():
        cs = cloud.get(oid)
        val = (a32 * float(cs) + b32) if cs is not None else (a4 * dscore + b4)
        by_clip[clip].append((pts, val))
    out = {h: {} for h in D.HOR}
    for clip, pv in by_clip.items():
        meta = labels.get(clip) or {}
        if meta.get("label") == "positive" and meta.get("ref") is not None:
            ref = float(meta["ref"])
        elif meta.get("label") == "negative":
            ref = fake.get(clip)
        else:
            continue
        if ref is None:
            continue
        for h in D.HOR:
            near = [v for (p, v) in pv if abs(p - (ref - h)) <= 0.5 + 1e-9]
            if near:
                out[h][clip] = float(np.mean(near))
    return out


def pooled(fn):
    acc = {h: defaultdict(list) for h in D.HOR}
    got = False
    for s in SEEDS:
        d = fn(s)
        if d is None:
            continue
        got = True
        for h in D.HOR:
            for c, v in d[h].items():
                acc[h][c].append(v)
    if not got:
        return None
    return {h: {c: float(np.mean(v)) for c, v in acc[h].items()} for h in D.HOR}


def mAP_on(table, labels, pos, neg, draw_p, draw_n):
    """challenge mAP over the resample (draw_p, draw_n index the pos/neg clip lists)."""
    aps = []
    for h in CH:
        P = np.array([table[h].get(pos[i], np.nan) for i in draw_p])
        N = np.array([table[h].get(neg[i], np.nan) for i in draw_n])
        P = P[~np.isnan(P)]; N = N[~np.isnan(N)]
        if len(P) and len(N):
            aps.append(D._ap(P, N))
    return float(np.mean(aps)) if aps else np.nan


def main():
    a4, b4, n4, p4 = D.platt(D.SHEP_4BI)
    a32, b32, n32, p32 = D.platt(D.SHEP_32BI)
    cal = (a4, b4, a32, b32)
    dur, labels = D.durations_refs()
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    # device-only reference (DSMAP: hybrid-F-lhreq-noc3 device-only path)
    dev = pooled(lambda s: D.delivered_crops("hybrid-F-lhreq-noc3", s, cal, dur, labels, fake, True))
    ceil = pooled(lambda s: ceiling_crops(s, cal, dur, labels, fake))
    arm_tabs = {}
    for disp, raw in ARMS:
        t = pooled(lambda s, raw=raw: D.delivered_crops(raw, s, cal, dur, labels, fake, False))
        if t is not None:
            arm_tabs[disp] = t
    pos = sorted(c for c in labels if labels[c].get("label") == "positive" and c in dur)
    neg = sorted(c for c in labels if labels[c].get("label") == "negative" and c in fake)
    rng = np.random.default_rng(SEED)
    draws = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg))) for _ in range(NB)]
    full = {"dev": mAP_on(dev, labels, pos, neg, np.arange(len(pos)), np.arange(len(neg))),
            "ceil": mAP_on(ceil, labels, pos, neg, np.arange(len(pos)), np.arange(len(neg)))}
    committed = json.load(open(REPO / "reports/figures/dsmap_results.json"))["arms"]
    pc = {"device_only_reproduced": round(full["dev"], 6),
          "device_only_committed": round(committed["device-only"]["splits"]["ALL"]["challenge_mAP"], 6)}
    dev_boot = np.array([mAP_on(dev, labels, pos, neg, a, b) for a, b in draws])
    ceil_boot = np.array([mAP_on(ceil, labels, pos, neg, a, b) for a, b in draws])
    gap = full["ceil"] - full["dev"]
    gap_boot = ceil_boot - dev_boot
    se_gap = float(np.std(gap_boot, ddof=1))
    N = len(pos) + len(neg)
    rows = {}
    for disp, tab in arm_tabs.items():
        am = mAP_on(tab, labels, pos, neg, np.arange(len(pos)), np.arange(len(neg)))
        ab = np.array([mAP_on(tab, labels, pos, neg, a, b) for a, b in draws])
        share = (am - full["dev"]) / gap if gap else np.nan
        sb = (ab - dev_boot) / np.where(np.abs(gap_boot) > 1e-12, gap_boot, np.nan)
        sb = sb[~np.isnan(sb)]
        se = float(np.std(sb, ddof=1))
        rows[disp] = {"arm_mAP": round(am, 6),
                      "share": round(share, 4),
                      "share_ci95": [round(float(np.percentile(sb, 2.5)), 4), round(float(np.percentile(sb, 97.5)), 4)],
                      "mdd_share": round(2 * 1.96 * se, 4)}
    out = {"_what": "Dashcam headline oracle: per-arm share on Nexar challenge mAP (ceiling = cloud every "
                    "instant). Paired clip-cluster bootstrap, 1x seeds 4-7 pooled.",
           "positive_control": pc,
           "device_only_mAP": round(full["dev"], 6), "ceiling_mAP": round(full["ceil"], 6),
           "gap_ceiling_minus_device": round(gap, 6), "se_gap": round(se_gap, 6),
           "n_pos_clips": len(pos), "n_neg_clips": len(neg), "N_clips": N,
           "clips_needed_to_resolve_gap": int(np.ceil(N * (2 * 1.96 * se_gap / gap) ** 2)) if gap > 0 else None,
           "arms": rows}
    out["_provenance"] = stamp(script="dashcam_share_headline.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/dashcam_share_headline.json").write_text(
        json.dumps(out, indent=1, default=float))
    print("control:", pc)
    print("device", round(full["dev"], 4), "ceiling", round(full["ceil"], 4), "gap", round(gap, 4),
          "se_gap", round(se_gap, 4), "clips needed", out["clips_needed_to_resolve_gap"])
    for disp, r in rows.items():
        print(f"  {disp:28s} share {r['share']:+.3f} CI {r['share_ci95']} MDD {r['mdd_share']}")


if __name__ == "__main__":
    main()
