#!/usr/bin/env python3
"""Dashcam diagnosis (CPU, committed data, read-only, fixes nothing).

1. Episode false-alarm rate per tier (device-only, cloud-only) on DEV vs EVAL at the two threshold
   sets (episode D197 and instant score_cell), from the committed SH-EP EP-G per-instant scores.
2. Mixing effect on the live s4 1x episodes: for no-crash episodes, false alarms of the arm's MIXED
   stream (served instants use the cloud score, others the device score) vs pure device-only and
   pure cloud-only on the same episodes. Extra chances = episodes where the mixed walk crosses but
   neither pure tier does.
"""
from __future__ import annotations
import gzip, json, sys, collections
from pathlib import Path

REPO = Path("/home/nesl/fm-switching")
SH4 = REPO / "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
SH32 = REPO / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(REPO / "experiments/analysis/episodic"))
sys.path.insert(0, str(REPO / "experiments/analysis/oracle"))
import dashcam_episodic as DC  # noqa: E402
import oracle_lp_run as R  # noqa: E402
from oracle_dashcam import Instant, Episode, episode_correct  # noqa: E402

EP_THR = {"device": -0.2014, "cloud": -2.9298}                  # D197 episode thresholds
INST_THR = {"device": DC.thresholds()["device"], "cloud": DC.thresholds()["cloud"]}  # score_cell


def sh_scores(path, tier):
    """EP-G rows -> {side: {clip: [(t, score)]}}, labels {clip: label}."""
    op = gzip.open if str(path).endswith(".gz") else open
    out = {"DEV": collections.defaultdict(list), "EVAL": collections.defaultdict(list)}
    lab = {}
    with op(path, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r.get("condition") != "EP-G" or r.get("side") not in ("DEV", "EVAL"):
                continue
            if r.get("score") is None:
                continue
            clip = r.get("file_name")
            out[r["side"]][clip].append((float(r.get("t") or 0.0), float(r["score"])))
            lab[clip] = r.get("label")
    return out, lab


def far(scores, labels, side, thr):
    """Episode false-alarm rate: fraction of NEGATIVE clips with any instant >= thr."""
    neg = [c for c, l in labels.items() if l == "negative" and c in scores[side]]
    if not neg:
        return None, 0
    fa = sum(1 for c in neg if any(s >= thr - 1e-12 for _, s in scores[side][c]))
    return round(fa / len(neg), 4), len(neg)


def part1():
    d4, lab4 = sh_scores(SH4, "device")
    d32, lab32 = sh_scores(SH32, "cloud")
    lab = {**lab4, **lab32}
    out = {}
    for level, thr in (("episode_D197", EP_THR), ("instant_score_cell", INST_THR)):
        for side in ("DEV", "EVAL"):
            fd, nd = far(d4, lab, side, thr["device"])
            fc, nc = far(d32, lab, side, thr["cloud"])
            out[f"{level}|{side}"] = {"device_FAR": fd, "cloud_FAR": fc, "n_negative_clips": nd}
    return out


def part2(arms=("covex-v6-fair-final", "state-uo", "base"), tier_thr=INST_THR, level="instant_score_cell"):
    """Mixed vs pure false alarms on live s4 1x no-crash episodes at the given threshold set."""
    labels = DC.nexar_labels()
    s = 4
    cloud = R.simplestream_cloud(s, "")
    by_ep = collections.defaultdict(list)
    for r in DC.load_trace_instants(s):
        by_ep[r["episode_id"]].append(r)
    base_eps = {}
    for eid, rows in by_ep.items():
        rows.sort(key=lambda r: float(r["t_local"]))
        meta = labels.get(rows[0]["clip"]) or {}
        ref = meta.get("ref")
        is_crash = bool(meta.get("label") == "positive" and ref is not None
                        and any(float(r["t_local"]) < ref for r in rows))
        if is_crash:
            continue                                            # FA is defined on no-crash episodes
        insts, iid, opps = [], {}, []
        for r in rows:
            ds = r.get("device_score"); ds = -1e9 if ds is None else ds
            cs = cloud.get(r["opportunity_id"]); cs = ds if cs is None else cs
            it = Instant(float(r["t_local"]), ds, cs, 1.0)
            insts.append(it); iid[r["opportunity_id"]] = id(it); opps.append(r["opportunity_id"])
        base_eps[eid] = (Episode(eid, insts, False, ref, tier_thr["device"], tier_thr["cloud"]), iid, opps)
    n = len(base_eps)
    res = {"n_nocrash_episodes": n, "thresholds": level, "thr": tier_thr}
    pure_dev_fa = sum(1 for e, _, _ in base_eps.values() if not episode_correct(e, frozenset()))
    pure_cld_fa = 0
    for eid, (e, iid, opps) in base_eps.items():
        if not episode_correct(e, frozenset(iid.values())):
            pure_cld_fa += 1
    res["pure_device_FA"] = pure_dev_fa
    res["pure_cloud_FA"] = pure_cld_fa
    for arm in arms:
        cj = RUNS / f"{arm}_n16_s{s}_1200s_h27_3t_L3_epg_rq30" / "outcomes.jsonl.gz"
        if not cj.exists():
            continue
        onc = set()
        with gzip.open(cj, "rt") as f:
            for line in f:
                o = json.loads(line)
                if str(o.get("device_id", "")).startswith("dash") and (o.get("cloud_payload") or {}).get("on_time"):
                    onc.add(o["opportunity_id"])
        mixed_fa = 0
        extra = 0
        for eid, (e, iid, opps) in base_eps.items():
            served = frozenset(iid[o] for o in opps if o in onc)
            mixed_correct = episode_correct(e, served)
            pdev = episode_correct(e, frozenset())
            pcld = episode_correct(e, frozenset(iid.values()))
            if not mixed_correct:
                mixed_fa += 1
            if mixed_correct is False and pdev and pcld:
                extra += 1
        res[f"{arm}_mixed_FA"] = mixed_fa
        res[f"{arm}_extra_chance_FA"] = extra
    return res


def part3(tier_thr, level, arms=("covex-v6-fair-final", "state-uo", "base"), s=4):
    """All s4 1x episodes: correct counts split crash vs no-crash, device-only floor vs each arm."""
    labels = DC.nexar_labels()
    cloud = R.simplestream_cloud(s, "")
    by_ep = collections.defaultdict(list)
    for r in DC.load_trace_instants(s):
        by_ep[r["episode_id"]].append(r)
    eps = {}
    for eid, rows in by_ep.items():
        rows.sort(key=lambda r: float(r["t_local"]))
        meta = labels.get(rows[0]["clip"]) or {}
        ref = meta.get("ref")
        is_crash = bool(meta.get("label") == "positive" and ref is not None
                        and any(float(r["t_local"]) < ref for r in rows))
        insts, iid, opps = [], {}, []
        for r in rows:
            ds = r.get("device_score"); ds = -1e9 if ds is None else ds
            cs = cloud.get(r["opportunity_id"]); cs = ds if cs is None else cs
            it = Instant(float(r["t_local"]), ds, cs, 1.0)
            insts.append(it); iid[r["opportunity_id"]] = id(it); opps.append(r["opportunity_id"])
        eps[eid] = (Episode(eid, insts, is_crash, ref, tier_thr["device"], tier_thr["cloud"]), iid, opps, is_crash)
    def tally(served_fn):
        c = collections.Counter()
        for eid, (e, iid, opps, crash) in eps.items():
            ok = episode_correct(e, served_fn(iid, opps))
            c["crash_correct" if crash else "nocrash_correct"] += int(bool(ok))
            c["crash_n" if crash else "nocrash_n"] += 1
        return dict(c)
    res = {"level": level, "thr": tier_thr, "device_only": tally(lambda iid, opps: frozenset())}
    for arm in arms:
        cj = RUNS / f"{arm}_n16_s{s}_1200s_h27_3t_L3_epg_rq30" / "outcomes.jsonl.gz"
        if not cj.exists():
            continue
        onc = set()
        with gzip.open(cj, "rt") as f:
            for line in f:
                o = json.loads(line)
                if str(o.get("device_id", "")).startswith("dash") and (o.get("cloud_payload") or {}).get("on_time"):
                    onc.add(o["opportunity_id"])
        res[arm] = tally(lambda iid, opps, onc=onc: frozenset(iid[o] for o in opps if o in onc))
    res["cloud_only"] = tally(lambda iid, opps: frozenset(iid.values()))
    return res


if __name__ == "__main__":
    p1 = part1()
    print(json.dumps(p1, indent=1))
    for level, thr in (("instant_score_cell", INST_THR), ("episode_D197", EP_THR)):
        print(json.dumps(part2(tier_thr=thr, level=level), indent=1))
        print(json.dumps(part3(thr, level), indent=1))
