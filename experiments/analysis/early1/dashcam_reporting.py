#!/usr/bin/env python3
"""Dashcam reporting, 1x seeds 4-7, pooled and per seed (ruling after 82f5d019; the dashcam oracle share
is dropped).

(1) Per-arm challenge-mAP difference from device-only (paired clip-clustered bootstrap, 2000 resamples,
    seed 0, the same clip resamples for arm and device in each draw), 95% CI, and the minimum detectable
    difference (2 x 1.96 x SE of the paired difference). Labelled UNDERPOWERED at 300 clips when the CI
    includes zero.
(2) Per-arm per-episode on-time attainment (canon.dash_attainment, D179 (6) definition): mean per-episode
    attainment and the fraction of episodes at or above the 0.25 target (p_dash, D71).
Output: results/orchestration/live2/oracle/dashcam_reporting.json
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

REPO = Path("/home/nesl/fm-switching")
for p in ("experiments/analysis/early1", "experiments/analysis/episodic", "experiments/analysis/canon",
          "experiments/analysis/oracle", "experiments/lib"):
    sys.path.insert(0, str(REPO / p))
import dsmap as D  # noqa: E402
import dashcam_share_headline as H  # noqa: E402
import episodic_lib as E  # noqa: E402
import canon as C  # noqa: E402
from _provenance import stamp  # noqa: E402

ALL_SEEDS = [4, 5, 6, 7]
NB, SEED = 2000, 0
ARMS = list(E.ARMS) + [("fair-final-rung3", "covex-v6-fair-final")]
TARGET = 0.25


def setup():
    a4, b4, _, _ = D.platt(D.SHEP_4BI)
    a32, b32, _, _ = D.platt(D.SHEP_32BI)
    cal = (a4, b4, a32, b32)
    dur, labels = D.durations_refs()
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    return cal, dur, labels, fake


def tables(seeds, raw, cal, dur, labels, fake, device_only=False):
    acc = {h: {} for h in D.HOR}
    got = False
    for s in seeds:
        d = D.delivered_crops(raw, s, cal, dur, labels, fake, device_only)
        if d is None:
            continue
        got = True
        for h in D.HOR:
            for c, v in d[h].items():
                acc[h].setdefault(c, []).append(v)
    if not got:
        return None
    return {h: {c: float(np.mean(v)) for c, v in acc[h].items()} for h in D.HOR}


def run_block(seeds, cal, dur, labels, fake, dev_tab):
    pos = sorted(c for c in labels if labels[c].get("label") == "positive" and c in dur)
    neg = sorted(c for c in labels if labels[c].get("label") == "negative" and c in fake)
    rng = np.random.default_rng(SEED)
    draws = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg))) for _ in range(NB)]
    full_dev = H.mAP_on(dev_tab, labels, pos, neg, np.arange(len(pos)), np.arange(len(neg)))
    dev_boot = np.array([H.mAP_on(dev_tab, labels, pos, neg, a, b) for a, b in draws])
    res = {"n_pos_clips": len(pos), "n_neg_clips": len(neg), "device_only_mAP": round(full_dev, 6),
           "arms": {}}
    for disp, raw in ARMS:
        tab = tables(seeds, raw, cal, dur, labels, fake)
        if tab is None:
            continue
        am = H.mAP_on(tab, labels, pos, neg, np.arange(len(pos)), np.arange(len(neg)))
        ab = np.array([H.mAP_on(tab, labels, pos, neg, a, b) for a, b in draws])
        diff_boot = ab - dev_boot
        diff_boot = diff_boot[~np.isnan(diff_boot)]
        se = float(np.std(diff_boot, ddof=1))
        lo, hi = float(np.percentile(diff_boot, 2.5)), float(np.percentile(diff_boot, 97.5))
        res["arms"][disp] = {
            "arm_mAP": round(am, 6), "diff_vs_device": round(am - full_dev, 6),
            "diff_ci95": [round(lo, 6), round(hi, 6)], "mdd": round(2 * 1.96 * se, 6),
            "label": "UNDERPOWERED (300 clips)" if lo <= 0 <= hi else "resolved"}
    return res


def attainment(seeds):
    out = {}
    for disp, raw in ARMS:
        vals = {}
        for s in seeds:
            path, _ = E.cell_dir(raw, s)
            if path is None:
                continue
            mean_att, frac = C.dash_attainment(path)
            if mean_att is None:
                continue
            vals[f"s{s}"] = {"mean_per_episode_attainment": round(float(mean_att), 4),
                             "fraction_episodes_at_or_above_0.25": round(float(frac), 4)}
        if vals:
            out[disp] = vals
    return out


def main():
    cal, dur, labels, fake = setup()
    dev_all = tables(ALL_SEEDS, "hybrid-F-lhreq-noc3", cal, dur, labels, fake, device_only=True)
    out = {"_what": "Dashcam reporting (headline challenge mAP; per-episode attainment). 1x seeds 4-7.",
           "target_p_dash": TARGET, "pooled_seeds_4_to_7": run_block(ALL_SEEDS, cal, dur, labels, fake, dev_all),
           "per_seed": {}, "attainment": {"per_seed": attainment(ALL_SEEDS)}}
    for s in ALL_SEEDS:
        dev_s = tables([s], "hybrid-F-lhreq-noc3", cal, dur, labels, fake, device_only=True)
        out["per_seed"][f"s{s}"] = run_block([s], cal, dur, labels, fake, dev_s)
    out["_provenance"] = stamp(script="dashcam_reporting.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/dashcam_reporting.json").write_text(
        json.dumps(out, indent=1, default=float))
    pooled = out["pooled_seeds_4_to_7"]
    print("device-only pooled", pooled["device_only_mAP"], "| clips pos/neg", pooled["n_pos_clips"], pooled["n_neg_clips"])
    for disp, r in pooled["arms"].items():
        print(f"  {disp:28s} diff {r['diff_vs_device']:+.4f} CI {r['diff_ci95']} MDD {r['mdd']} {r['label']}")
    return out


if __name__ == "__main__":
    main()
