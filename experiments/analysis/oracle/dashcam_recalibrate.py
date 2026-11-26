#!/usr/bin/env python3
"""Dashcam episode thresholds recalibrated on LIVE scores, DEV clips only (ruling D6), both tiers.

Same rule as dashcam_episodic.thresholds_episode (D197): theta = k-th largest no-crash episode
maximum with k = ceil(far * n), an episode crosses at or above theta. Here the episodes are the live
trace's (device score per instant; cloud = arm-independent simplestream dense score), restricted to
DEV clips (sh_ep_side split), one episode per clip (max over its instants and over seeds 4 to 7),
negatives only. EVAL is never read here. Output: results/orchestration/live2/oracle/dashcam_thresholds_live_dev.json
"""
from __future__ import annotations
import json, math, sys, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/analysis/early1"))
import dashcam_episodic as DC  # noqa: E402
import oracle_lp_run as R  # noqa: E402
from dsmap import sh_ep_side  # noqa: E402
from _provenance import stamp  # noqa: E402

SEEDS = [4, 5, 6, 7]
FAR = 0.10


def main():
    labels = DC.nexar_labels()
    side = sh_ep_side()                       # file_name ("00005.mp4") -> DEV / EVAL (SH-EP split)
    dev_max = {"device": {}, "cloud": {}}     # clip -> max over instants and seeds
    for s in SEEDS:
        cloud = R.simplestream_cloud(s, "")
        for r in DC.load_trace_instants(s):
            clip = r["clip"]
            if side.get(clip) != "DEV":          # trace clip names already carry .mp4
                continue
            if (labels.get(clip) or {}).get("label") != "negative":
                continue                       # thresholds are set on no-crash episodes only
            ds = r.get("device_score")
            if ds is not None:
                dev_max["device"][clip] = max(dev_max["device"].get(clip, -1e18), float(ds))
            cs = cloud.get(r["opportunity_id"])
            if cs is not None:
                dev_max["cloud"][clip] = max(dev_max["cloud"].get(clip, -1e18), float(cs))
    out = {"_what": "Dashcam episode thresholds recalibrated on LIVE scores, DEV clips only, both tiers "
                    "(D6). Rule = D197 (k-th largest no-crash episode max, k=ceil(0.10 n)). EVAL not read.",
           "far_target": FAR, "tiers": {}}
    for tier in ("device", "cloud"):
        m = sorted(dev_max[tier].values(), reverse=True)
        n = len(m)
        k = math.ceil(FAR * n)
        theta = m[k - 1] if 0 < k <= n else m[-1]
        achieved = sum(1 for v in m if v >= theta - 1e-12) / n
        out["tiers"][tier] = {"theta": round(theta, 6), "n_negative_dev_clips": n, "k_allowed": k,
                              "achieved_dev_episode_far": round(achieved, 4)}
    out["_provenance"] = stamp(script="dashcam_recalibrate.py", model="none", device="jetson_orin")
    (REPO / "results/orchestration/live2/oracle/dashcam_thresholds_live_dev.json").write_text(
        json.dumps(out, indent=1, default=float))
    print(json.dumps(out["tiers"], indent=1))
    return out


if __name__ == "__main__":
    main()
