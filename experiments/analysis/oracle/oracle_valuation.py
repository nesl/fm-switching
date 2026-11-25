#!/usr/bin/env python3
"""StudyORACLE stage 1: per-type FAIR valuation inputs (CPU, read-only, no images).

FAIR (pre-reg headline): a served cloud recall/single-shot unit is worth its own type's acc_cloud,
an unserved one its own type's acc_device; the per-unit FAIR GAIN of serving is v = acc_cloud -
acc_device, and the device FLOOR is sum over units of acc_device(type). D240: 1x and kv0.5r kept
separate (recall acc is per seed and stable across memory; reported for both).

Per-type accuracies, from committed gold grading only:
- single-shot: the SS2 box (episodic_lib.ss2_correctness), acc_cloud / acc_device pooled over the
  committed SS2 questions (device-independent box).
- recall (robot): the committed robot_headline of the rung-3 cell per seed:
  acc_cloud = cloud_accuracy_on_served, acc_device = device_only_accuracy. These are PER SEED
  (the question set differs by seed). acc_cloud is "on served"; rung 3 is the highest-delivery arm,
  so its served set is the most complete estimate of the per-seed cloud accuracy available offline
  (stated limitation, not hidden).
- dashcam: valued by the max-over-subsets rule in stage 2 (D197 tiers), not here.

This writes the valuation INPUTS (a verification artifact), not the oracle bound.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import episodic_lib as E  # noqa: E402
from _provenance import stamp  # noqa: E402
SEEDS = [4, 5, 6, 7]


def rung3_robot_headline(seed, tag):
    for suf in ("_rerun", ""):
        p = RUNS / (f"covex-v6-fair-final_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf) / "cell.json"
        if p.exists():
            d = json.load(open(p))
            return ((d.get("score") or {}).get("score") or {}).get("robot_headline") or {}
    return None


def ss_box_acc():
    ss = E.ss2_correctness()
    dev = [v["device"] for v in ss.values() if "device" in v]
    cld = [v["cloud"] for v in ss.values() if "cloud" in v]
    return (round(sum(cld) / len(cld), 6), round(sum(dev) / len(dev), 6), len(ss))


def main():
    ss_cloud, ss_dev, ss_n = ss_box_acc()
    out = {"_what": "StudyORACLE stage 1: per-type FAIR valuation inputs (acc_cloud, acc_device, "
                    "gain v = acc_cloud - acc_device). Verification artifact, not the bound. "
                    "D240: 1x and kv0.5r separate.",
           "single_shot": {"acc_cloud": ss_cloud, "acc_device": ss_dev, "n_box": ss_n,
                           "v_fair_gain": round(ss_cloud - ss_dev, 6),
                           "source": "SS2 box (episodic_lib.ss2_correctness), pooled"},
           "recall": {"1x": {}, "kv0.5r": {}}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            rh = rung3_robot_headline(s, tag)
            if not rh:
                continue
            ac = rh.get("cloud_accuracy_on_served")
            ad = rh.get("device_only_accuracy")
            out["recall"][mem][f"s{s}"] = {
                "acc_cloud": ac, "acc_device": ad,
                "v_fair_gain": (round(ac - ad, 6) if (ac is not None and ad is not None) else None),
                "n_by_deadline": rh.get("n_by_deadline"),
                "source": "rung-3 robot_headline cloud_accuracy_on_served / device_only_accuracy"}
    # verification: v must be finite; acc in [0,1]; acc_cloud >= acc_device expected (cloud helps),
    # flag any seed where it is not (a negative-value type means serving hurts on average).
    flags = []
    if not (0 <= ss_cloud <= 1 and 0 <= ss_dev <= 1):
        flags.append("single-shot acc out of [0,1]")
    for mem in ("1x", "kv0.5r"):
        for s, r in out["recall"][mem].items():
            ac, ad = r["acc_cloud"], r["acc_device"]
            if ac is None or ad is None or not (0 <= ac <= 1 and 0 <= ad <= 1):
                flags.append(f"recall {mem} {s} acc out of [0,1] or missing")
            elif ac < ad:
                flags.append(f"recall {mem} {s} acc_cloud < acc_device (negative FAIR gain)")
    out["verification_flags"] = flags
    out["_provenance"] = stamp(script="oracle_valuation.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "oracle_fair_valuation.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_fair_valuation.json")
    print("single-shot FAIR gain:", out["single_shot"]["v_fair_gain"],
          f"(cloud {ss_cloud} device {ss_dev}, n {ss_n})")
    for mem in ("1x", "kv0.5r"):
        print(mem, "recall FAIR gain per seed:",
              {s: r["v_fair_gain"] for s, r in out["recall"][mem].items()})
    print("verification flags:", flags or "none")
    return out


if __name__ == "__main__":
    main()
