#!/usr/bin/env python3
"""StudyDASH2 addendum: Part 3 extension (context length and restart split) and Part 6 (cloud context
lifecycle across StudySH-EP conditions). Offline, read-only, CPU only. Seeds 4-7. D199 metric.

Part 3 ext: for crash-clip crop instants, the cloud episode context length (frames seen since the
episode restart) and whether the episode restarted within 3 s before the event; the cloud-every-
instant challenge mAP split by context length (under 6 / 6-12 / over 12 frames) and by restart.
Part 6: for each condition C1/C3/C6/EP-B/EP-G, the cloud-every-instant stream from StudySH-EP 32BI
scores at each crop (device stream unchanged); challenge mAP, horizon curve and shift vs device-only,
cross-fitted ALL primary, paired clip-clustered CIs, coverage, and per-instant token cost (warm
uncached vs cold prompt). No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/early1"))
import dash2 as D2  # noqa: E402

HOR = D2.HOR
CHALLENGE = D2.CHALLENGE
OUT = ROOT / "reports/figures"
CONDS = ["C1", "C3", "C6", "EP-B", "EP-G"]
CONDFILE = {c: ROOT / f"results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-{c}.jsonl.gz"
            for c in CONDS}


def ap(pos, neg):
    return D2._ap(np.array(pos), np.array(neg)) if len(pos) and len(neg) else None


def main():
    dur, labels = D2.DS.durations_refs()
    allclips = set()
    for s in D2.E.SEEDS:
        allclips |= set(c for c, _, _ in D2._trace(s).values())
    folds = D2.clip_folds(allclips)
    cf4, dev4 = D2.crossfit_maps(D2.shep_instants(D2.SHEP_4BI), folds)
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng0 = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng0.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}
    side = D2.DS.sh_ep_side()
    pos_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "positive")
    neg_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "negative")
    boot_all = D2.Boot(pos_all, neg_all)

    # ---- device-only crops (reference), cross-fit ALL ----
    def device_crops():
        acc = {h: defaultdict(list) for h in HOR}
        for s in D2.E.SEEDS:
            tr = D2._trace(s)
            byclip = defaultdict(list)
            for oid, (clip, pts, dscore) in tr.items():
                fo = folds.get(clip, 0)
                byclip[clip].append((pts, cf4[fo][0] * dscore + cf4[fo][1]))
            for clip, pv in byclip.items():
                meta = labels.get(clip) or {}
                ref = (float(meta["ref"]) if meta.get("label") == "positive"
                       and meta.get("ref") is not None
                       else (fake.get(clip) if meta.get("label") == "negative" else None))
                if ref is None:
                    continue
                for h in HOR:
                    near = [v for (p, v) in pv if abs(p - (ref - h)) <= 0.5 + 1e-9]
                    if near:
                        acc[h][clip].append(float(np.mean(near)))
        return {h: {c: float(np.mean(vs)) for c, vs in acc[h].items()} for h in HOR}
    dev_stream = device_crops()
    dev_tab = boot_all.table(dev_stream)

    # ---- Part 3 extension: context length + restart on the workload cloud-every-instant stream ----
    valid_arms = [d for d in D2.ARMS_RAW if d != "device-only"
                  and any(D2.E.cell_dir(D2.ARMS_RAW[d], s)[0] for s in D2.E.SEEDS)]
    # per crop crash-clip instant: context length (pos+1), restart flag, cloud-every score
    pos_by_bucket = {"<6": {h: defaultdict(list) for h in HOR},
                     "6-12": {h: defaultdict(list) for h in HOR},
                     ">12": {h: defaultdict(list) for h in HOR}}
    pos_by_restart = {"restart": {h: defaultdict(list) for h in HOR},
                      "no_restart": {h: defaultdict(list) for h in HOR}}
    neg_cloud = {h: defaultdict(list) for h in HOR}
    for s in D2.E.SEEDS:
        per_inst, _ = D2.cloud_every_instant(s, valid_arms, D2.crossfit_maps(
            D2.shep_instants(D2.SHEP_32BI), folds)[0], folds)
        cf32 = D2.crossfit_maps(D2.shep_instants(D2.SHEP_32BI), folds)[0]
        # episode structure
        eps = defaultdict(list)
        for l in gzip.open(ROOT / D2.DS.TRACE.format(s=s), "rt"):
            r = json.loads(l)
            eps[r["episode_id"]].append((r["opportunity_id"], r["clip"], float(r["clip_pts"])))
        for eid, insts in eps.items():
            insts.sort(key=lambda x: x[2])
            clip = insts[0][1]
            meta = labels.get(clip) or {}
            is_pos = meta.get("label") == "positive" and meta.get("ref") is not None
            ref = (float(meta["ref"]) if is_pos
                   else (fake.get(clip) if meta.get("label") == "negative" else None))
            if ref is None:
                continue
            ep_start = insts[0][2]
            restart = (ep_start > ref - 3.0)  # episode began within 3 s before the event
            for pos, (oid, _c, pts) in enumerate(insts):
                fo = folds.get(clip, 0)
                cloud = None
                if oid in per_inst:
                    cloud = cf32[fo][0] * float(np.median(per_inst[oid])) + cf32[fo][1]
                for h in HOR:
                    if abs(pts - (ref - h)) <= 0.5 + 1e-9 and cloud is not None:
                        if is_pos:
                            ctx = pos + 1
                            b = "<6" if ctx < 6 else ("6-12" if ctx <= 12 else ">12")
                            pos_by_bucket[b][h][clip].append(cloud)
                            pos_by_restart["restart" if restart else "no_restart"][h][clip].append(cloud)
                        else:
                            neg_cloud[h][clip].append(cloud)
    negp = {h: {c: float(np.mean(v)) for c, v in neg_cloud[h].items()} for h in HOR}

    def map_split(posd):
        p = {h: {c: float(np.mean(v)) for c, v in posd[h].items()} for h in HOR}
        aps = []
        n = {}
        for h in CHALLENGE:
            P = list(p[h].values()); N = list(negp[h].values())
            a = ap(P, N)
            if a is not None:
                aps.append(a)
            n[h] = len(P)
        return {"challenge_mAP": (float(np.mean(aps)) if aps else None), "n_pos_by_h": n}

    part3 = {"by_context_length": {b: map_split(pos_by_bucket[b]) for b in pos_by_bucket},
             "by_restart": {r: map_split(pos_by_restart[r]) for r in pos_by_restart},
             "_note": "cloud-every-instant challenge mAP on crash-clip crops, positives split by the "
                      "cloud episode context length (frames since restart) and by whether the episode "
                      "restarted within 3 s before the event; negatives are the common reference."}

    # ---- Part 6: cloud context lifecycle per condition ----
    def cond_stream(c):
        rows = defaultdict(list)  # clip -> [(rel_to_ref, score)]
        tok_unc, tok_prompt = [], []
        for l in gzip.open(CONDFILE[c], "rt"):
            r = json.loads(l)
            if r.get("condition") != c or r.get("rel_to_ref") is None or r.get("score") is None:
                continue
            rows[r["file_name"]].append((float(r["rel_to_ref"]), float(r["score"])))
            pt, ct = r.get("prompt_tokens"), r.get("cached_tokens")
            if pt is not None and ct is not None:
                tok_unc.append(pt - ct); tok_prompt.append(pt)
        # cross-fit Platt on this condition's DEV instants
        allrows = []
        for l in gzip.open(CONDFILE[c], "rt"):
            r = json.loads(l)
            if r.get("condition") != c or r.get("score") is None or r.get("label") is None:
                continue
            allrows.append((r["file_name"], float(r["score"]),
                            1 if r["label"] == "positive" else 0, r.get("side")))
        cfc, _ = D2.crossfit_maps(allrows, folds)
        stream = {h: {} for h in HOR}
        cov_tot = cov = 0
        for clip, rv in rows.items():
            meta = labels.get(clip) or {}
            if clip not in allclips:
                continue
            fo = folds.get(clip, 0)
            for h in HOR:
                cov_tot += 1
                near = [sc for (rr, sc) in rv if abs(rr - (-h)) <= 0.5 + 1e-9]
                if near:
                    cov += 1
                    stream[h][clip] = cfc[fo][0] * float(np.mean(near)) + cfc[fo][1]
        return stream, (cov / cov_tot if cov_tot else None), tok_unc, tok_prompt

    part6 = {"device_only_mAP_ALL": dev_tab["challenge_mAP"], "conditions": {}}
    cond_tabs = {}
    for c in CONDS:
        stream, coverage, tu, tp = cond_stream(c)
        tab = boot_all.table(stream)
        cond_tabs[c] = tab
        pj = boot_all.paired(tab, dev_tab)
        part6["conditions"][c] = {
            "challenge_mAP_ALL": tab["challenge_mAP"], "ci": tab["challenge_mAP_ci"],
            "vs_device_only": {"diff": pj["diff"], "ci": pj["ci"]},
            "horizon_shift_vs_device": D2.horizon_shift(tab, dev_tab),
            "ap_by_horizon": {h: tab["ap"][h]["ap"] for h in HOR},
            "crop_coverage": coverage,
            "uncached_tokens_median": (statistics.median(tu) if tu else None),
            "prompt_tokens_median": (statistics.median(tp) if tp else None),
            "mAP_gain_per_1k_uncached_tok": ((pj["diff"] / (statistics.median(tu) / 1000))
                                             if tu and statistics.median(tu) else None)}

    # ---- decision ----
    epg = part6["conditions"]["EP-G"]
    best_per_tok = max(CONDS, key=lambda c: (part6["conditions"][c]["mAP_gain_per_1k_uncached_tok"]
                                             or -9))
    results = {"_what": "StudyDASH2 addendum: Part 3 ext + Part 6 (D199).",
               "part3_extension": part3, "part6": part6,
               "decision": {
                   "restart_explains_gap": {
                       "no_restart_mAP": part3["by_restart"]["no_restart"]["challenge_mAP"],
                       "restart_mAP": part3["by_restart"]["restart"]["challenge_mAP"],
                       "long_context_mAP": part3["by_context_length"][">12"]["challenge_mAP"],
                       "short_context_mAP": part3["by_context_length"]["<6"]["challenge_mAP"],
                       "epg_full_runup_vs_device": epg["vs_device_only"]["diff"],
                       "_reading": "if long-context / no-restart instants score materially higher "
                                   "than short-context / restart instants, and EP-G (full run-up) "
                                   "recovers more than the workload cloud-every, the 21-frame restart "
                                   "explains part of the 0.108 to 0.044 shrink"},
                   "best_condition_per_uncached_token": best_per_tok,
                   "best_condition_gain_per_1k": part6["conditions"][best_per_tok]["mAP_gain_per_1k_uncached_tok"]}}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dash2_context_results.json").write_text(json.dumps(results, indent=1, default=float))
    _plot(results)
    print("Part3 by context length:", {b: round(part3["by_context_length"][b]["challenge_mAP"] or 0, 4)
                                        for b in part3["by_context_length"]})
    print("Part3 by restart:", {r: round(part3["by_restart"][r]["challenge_mAP"] or 0, 4)
                                 for r in part3["by_restart"]})
    print("device-only mAP:", round(dev_tab["challenge_mAP"], 4))
    for c in CONDS:
        v = part6["conditions"][c]
        print(f"  {c:5}: mAP {v['challenge_mAP_ALL']:.3f} vs dev {v['vs_device_only']['diff']:+.3f}"
              f"[{v['vs_device_only']['ci'][0]:+.3f},{v['vs_device_only']['ci'][1]:+.3f}] "
              f"unc_tok {v['uncached_tokens_median']:.0f} gain/1ktok {v['mAP_gain_per_1k_uncached_tok']:+.4f} "
              f"shift {v['horizon_shift_vs_device']}")
    print("best per uncached token:", best_per_tok)


def _plot(results):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p6 = results["part6"]["conditions"]
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    cols = {"C1": "#999999", "C3": "#56B4E9", "C6": "#009E73", "EP-B": "#E69F00", "EP-G": "#0072B2"}
    ax.plot(HOR, [results["part6"]["device_only_mAP_ALL"]] * len(HOR), "k--", lw=1, label="device-only level")
    for c in CONDS:
        ax.plot(HOR, [p6[c]["ap_by_horizon"][h] for h in HOR], marker="o", color=cols[c],
                label=f"{c} (mAP {p6[c]['challenge_mAP_ALL']:.2f}, {p6[c]['uncached_tokens_median']:.0f} unc tok)")
    ax.set_xlabel("seconds before event (horizon t)")
    ax.set_ylabel("cloud challenge AP (cross-fitted ALL)")
    ax.set_title("StudyDASH2 Part 6: cloud context lifecycle (SH-EP conditions)")
    ax.invert_xaxis(); ax.grid(True, alpha=0.25); ax.legend(fontsize=7.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "dash2_context.png", dpi=200, metadata={"Software": None}, bbox_inches="tight")
    fig.savefig(OUT / "dash2_context.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
