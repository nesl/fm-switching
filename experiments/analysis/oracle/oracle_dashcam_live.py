#!/usr/bin/env python3
"""StudyORACLE stage 2-live: dashcam episode valuation on the LIVE episodes (CPU, read-only, no
images). D240: 1x and kv0.5r reported separately.

Per episode e, per seed x memory:
  device score  : from the committed trace instants (device_score).
  cloud score   : from simplestream's committed cell (the arm-independent dense 32BI source,
                  verified; missing instants -> device-only, conservative).
  label/ref     : nexar crash/no-crash + time_of_event; crash episode = has a pre-event instant.
  thresholds    : D197 episode thresholds theta_dev=-0.2014, theta_cloud=-2.9298.
  work W_q      : per-instant warm-prefix EPG tokens 338*new_frames (+42 text once per episode)+2.

HINDSIGHT: actual crossing-model max-over-subsets (oracle_dashcam.max_over_subsets) -> gain_e in
  {0,1}, w_e = min work over improving subsets on THIS episode's actual scores.
FAIR (expected): value the episode by the DEV-calibrated per-tier accuracy for its class - crash
  uses TPR, no-crash uses TNR. v_e^dev = device class acc, v_e^max = max(device, cloud) class acc,
  gain_e = max(0, cloud_class_acc - device_class_acc) (flat per class), w_e = min cloud work over the
  episode's PRE-EVENT instants (crash) that realize the upgrade; no-crash gain is 0 here because
  TNR_cloud == TNR_dev by the FAR calibration. FAIR and HINDSIGHT therefore differ per episode.
"""
from __future__ import annotations
import json, os, sys, collections, statistics
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
sys.path.insert(0, str(REPO / "experiments/lib"))
import episodic_lib as E  # noqa: E402
import dashcam_episodic as DC  # noqa: E402
from oracle_dashcam import Instant, Episode, max_over_subsets  # noqa: E402
from _provenance import stamp  # noqa: E402

EPG_TEXT, EPG_PF, DECODE = 42, 338, 2
SEEDS = [4, 5, 6, 7]


def dev_tier_acc():
    """DEV-calibrated per-tier episode accuracy at the D197 thresholds: TPR (crash) and TNR."""
    te = DC.thresholds_episode(far=0.10)
    out = {}
    for tier, path in (("device", DC.DEV_4BI), ("cloud", DC.DEV_32BI)):
        dev = DC._load_dev_episodes(path)
        theta = te[tier]
        pos = [v["max"] for v in dev.values() if v["label"] == "positive"]
        neg = [v["max"] for v in dev.values() if v["label"] == "negative"]
        tpr = sum(1 for m in pos if m >= theta - 1e-12) / len(pos)
        tnr = sum(1 for m in neg if m < theta - 1e-12) / len(neg)
        out[tier] = {"theta": theta, "tpr": tpr, "tnr": tnr}
    return out, te["device"], te["cloud"]


def simplestream_cloud(seed, tag):
    for suf in ("_rerun", ""):
        c = RUNS / (f"simplestream_n16_s{seed}_1200s_h27_3t{tag}_L3_epg_rq30" + suf)
        if (c / "outcomes.jsonl.gz").exists():
            out = {}
            for o in E.read_jsonl_gz(str(c / "outcomes.jsonl")):
                if str(o.get("device_id", "")).startswith("dash"):
                    cp = o.get("cloud_payload") or {}
                    if cp.get("cloud_score") is not None:
                        out[o["opportunity_id"]] = cp["cloud_score"]
            return out
    return {}


def build_episodes(seed, tag, cloud, labels, th_dev, th_cloud):
    """Group live trace instants into Episodes with device+cloud scores and warm-prefix work."""
    instants = DC.load_trace_instants(seed)
    by_ep = collections.defaultdict(list)
    for r in instants:
        by_ep[r["episode_id"]].append(r)
    episodes = []
    n_cloud_missing = 0
    for eid, rows in by_ep.items():
        rows = sorted(rows, key=lambda r: float(r["clip_pts"]))
        clip = rows[0]["clip"]
        meta = labels.get(clip) or {}
        ref = meta.get("ref")
        is_pos = (meta.get("label") == "positive")
        pts = [float(r["clip_pts"]) for r in rows]
        is_crash = bool(is_pos and ref is not None and any(p < ref for p in pts))
        insts = []
        prev_ef = 0
        for r in rows:
            ef = int(r.get("episode_frames", 1))
            new = max(1, ef - prev_ef) if prev_ef else ef
            prev_ef = ef
            work = EPG_PF * new + (EPG_TEXT if r is rows[0] else 0) + DECODE
            cs = cloud.get(r["opportunity_id"])
            if cs is None:
                n_cloud_missing += 1
                cs = r["device_score"]  # conservative: device-only, cannot improve
            insts.append(Instant(pts=float(r["clip_pts"]), d_score=r["device_score"],
                                 c_score=cs, work=float(work)))
        episodes.append((Episode(eid, insts, is_crash, ref, th_dev, th_cloud), is_crash,
                         [r["clip_pts"] for r in rows], ref))
    return episodes, n_cloud_missing


def main():
    tier, th_dev, th_cloud = dev_tier_acc()
    labels = DC.nexar_labels()
    result = {"1x": {}, "kv0.5r": {}}
    for tag, mem in (("", "1x"), ("_kv0.5r", "kv0.5r")):
        for s in SEEDS:
            cloud = simplestream_cloud(s, tag)
            if not cloud:
                continue
            episodes, n_missing = build_episodes(s, tag, cloud, labels, th_dev, th_cloud)
            # HINDSIGHT via actual crossing max-over-subsets
            h_gains, h_works, h_floor = [], [], 0.0
            f_gains, f_works, f_floor = [], [], 0.0
            n_crash = n_nocrash = 0
            n_improv_h = n_improv_f = 0
            for ep, is_crash, allpts, ref in episodes:
                if is_crash:
                    n_crash += 1
                else:
                    n_nocrash += 1
                # HINDSIGHT
                mos = max_over_subsets(ep)
                h_floor += mos["v_dev"]
                if mos["gain"] > 0:
                    h_gains.append(mos["gain"]); h_works.append(mos["w"]); n_improv_h += 1
                # FAIR expected
                dacc = tier["device"]["tpr"] if is_crash else tier["device"]["tnr"]
                cacc = tier["cloud"]["tpr"] if is_crash else tier["cloud"]["tnr"]
                f_floor += dacc
                g = max(0.0, cacc - dacc)
                if g > 1e-12:
                    # w_e = min cloud work over the episode's PRE-EVENT instants (crash)
                    pre = [i.work for i in ep.instants if (ref is not None and i.pts < ref)]
                    we = min(pre) if pre else min(i.work for i in ep.instants)
                    f_gains.append(g); f_works.append(we); n_improv_f += 1
            result[mem][f"s{s}"] = {
                "n_episodes": len(episodes), "n_crash": n_crash, "n_nocrash": n_nocrash,
                "n_cloud_instants_missing": n_missing,
                "HINDSIGHT": {"device_floor": round(h_floor, 4), "n_improvable": n_improv_h,
                              "total_gain": round(sum(h_gains), 4),
                              "w_e_median": (round(statistics.median(h_works), 1) if h_works else None)},
                "FAIR": {"device_floor": round(f_floor, 4), "n_improvable": n_improv_f,
                         "total_gain": round(sum(f_gains), 4), "gain_per_crash": round(
                             tier["cloud"]["tpr"] - tier["device"]["tpr"], 4),
                         "w_e_median": (round(statistics.median(f_works), 1) if f_works else None)},
            }
    out = {"_what": "StudyORACLE stage 2-live: dashcam episode FAIR (expected per-tier accuracy) and "
                    "HINDSIGHT (actual crossing) valuation on live episodes. D240 1x/kv0.5r separate.",
           "dev_tier_accuracy": tier, "cloud_source": "simplestream (arm-independent, verified)",
           "results": result}
    out["_provenance"] = stamp(script="oracle_dashcam_live.py", model="qwen3vl32b", device="jetson_orin")
    outdir = REPO / "results/orchestration/live2/oracle"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "oracle_dashcam_live.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote", outdir / "oracle_dashcam_live.json")
    for mem in ("1x", "kv0.5r"):
        for s, r in result[mem].items():
            print(f"  {mem} {s}: eps={r['n_episodes']} crash={r['n_crash']} miss={r['n_cloud_instants_missing']} "
                  f"| HIND floor={r['HINDSIGHT']['device_floor']} improv={r['HINDSIGHT']['n_improvable']} gain={r['HINDSIGHT']['total_gain']} "
                  f"| FAIR floor={r['FAIR']['device_floor']} improv={r['FAIR']['n_improvable']} gain={r['FAIR']['total_gain']}")
    return out


if __name__ == "__main__":
    main()
