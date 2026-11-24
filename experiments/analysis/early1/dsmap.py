#!/usr/bin/env python3
"""StudyDSMAP (D202 (4)): delivered-stream challenge mAP per arm. Offline, read-only, CPU only.

Per decision instant the DELIVERED score is the cloud score where an on-time cloud answer exists
(outcomes.jsonl.gz, joined by opportunity_id), else the device score (dashcam_instants.jsonl.gz).
Each tier is Platt-calibrated on StudySH-EP DEV EP-G (D57) before mixing, so the mixed stream is on a
common log-odds scale. Scored with the Nexar challenge protocol (E9c machinery): AP at horizons 0.5
to 3.0 s, challenge mAP (mean at 0.5/1.0/1.5), per arm per seed and pooled; 95 percent CIs by clip
bootstrap (2000, seed 0); paired diffs vs rung 3 (covex-v6-fair-c5attr) and device-only. Splits ALL,
DEV (90), EVAL (210) from the StudySH-EP fold; stated for every number. Seeds 4-7. No em dashes.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/analysis/episodic"))
import episodic_lib as E  # noqa: E402  cell selection, read_jsonl
import dashcam_episodic as DC  # noqa: E402  nexar labels

HOR = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
CHALLENGE = [0.5, 1.0, 1.5]
NB = 2000
SEED = 0
RUNG3 = "fair-c5attr"
TRACE = ("results/orchestration/live2/frozen_test/traces/"
         "seed{s}_n16_1200s_A_r40-40-20_lh_req_ss2_L3_epg_perframe_rq30/dashcam_instants.jsonl.gz")
SHEP_4BI = ROOT / "results/dashcam/study_sh_ep/sh_ep_requests_4BI_shep1.jsonl"
SHEP_32BI = ROOT / "results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-EP-G.jsonl.gz"
D14B = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
OUT = ROOT / "reports/figures"


def platt(path):
    op = gzip.open if str(path).endswith(".gz") else open
    X, y = [], []
    with op(path, "rt") as fh:
        for l in fh:
            if '"EP-G"' not in l or '"DEV"' not in l:
                continue
            r = json.loads(l)
            if r.get("condition") != "EP-G" or r.get("side") != "DEV" or r.get("score") is None:
                continue
            X.append([float(r["score"])])
            y.append(1 if r.get("label") == "positive" else 0)
    clf = LogisticRegression(C=1e6, solver="lbfgs").fit(X, y)
    return float(clf.coef_[0][0]), float(clf.intercept_[0]), len(y), int(sum(y))


def sh_ep_side():
    side = {}
    for l in open(SHEP_4BI):
        if '"side"' not in l:
            continue
        r = json.loads(l)
        side.setdefault(r["file_name"], r.get("side"))
    return side


def durations_refs():
    dur = {}
    for l in gzip.open(D14B, "rt"):
        r = json.loads(l)
        dur.setdefault(r["file_name"], float(r["duration_s"]))
    labels = DC.nexar_labels()  # clip -> {ref, label}
    return dur, labels


_TRACE_CACHE = {}


def _trace(seed):
    if seed in _TRACE_CACHE:
        return _TRACE_CACHE[seed]
    p = ROOT / TRACE.format(s=seed)
    out = {}
    for l in gzip.open(p, "rt"):
        r = json.loads(l)
        out[r["opportunity_id"]] = (r["clip"], float(r["clip_pts"]), float(r["device_score"]))
    _TRACE_CACHE[seed] = out
    return out


def delivered_crops(arm_raw, seed, cal, dur, labels, fake, device_only=False):
    """One delivered calibrated score per (clip, horizon): mean over the clip's crop instants
    (nearest clip_pts to ref-h within 0.5 s) across plays. Returns {h: {clip: value}} for pos+neg."""
    a4, b4, a32, b32 = cal
    path, _ = E.cell_dir(arm_raw, seed)
    if path is None:
        return None
    tr = _trace(seed)
    # D226 (3): a delivered cloud score counts only when its request is VERIFIED (present in the
    # request log and not a refusal); an absent-row or refused request is unverifiable, so the
    # instant falls back to the device score. Without this a refused/dropped monitor leaks its
    # cloud score into the delivered-stream mAP.
    refused, present = E.refused_and_present(path)
    cloud = {}
    for o in E.read_jsonl_gz(os.path.join(path, "outcomes.jsonl")):
        if not str(o.get("device_id", "")).startswith("dash"):
            continue
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        verified = rid is not None and rid in present and rid not in refused
        cloud[o["opportunity_id"]] = (bool(cp.get("on_time")) and verified, cp.get("cloud_score"))
    # delivered calibrated score per instant, grouped by clip
    by_clip = defaultdict(list)  # clip -> list of (clip_pts, delivered_cal)
    for oid, (clip, pts, dscore) in tr.items():
        c = cloud.get(oid, (False, None))
        if (not device_only) and c[0] and c[1] is not None:
            val = a32 * float(c[1]) + b32
        else:
            val = a4 * dscore + b4
        by_clip[clip].append((pts, val))
    out = {h: {} for h in HOR}
    for clip, pts_vals in by_clip.items():
        meta = labels.get(clip) or {}
        if meta.get("label") == "positive" and meta.get("ref") is not None:
            ref = float(meta["ref"])
        elif meta.get("label") == "negative":
            ref = fake.get(clip)
        else:
            continue
        if ref is None:
            continue
        for h in HOR:
            tgt = ref - h
            near = [v for (p, v) in pts_vals if abs(p - tgt) <= 0.5 + 1e-9]
            if near:
                out[h][clip] = float(np.mean(near))
    return out


def _ap(pos, neg):
    """Average precision, vectorized (matches sklearn.average_precision_score). Called ~1e6 times
    in the bootstrap, so sklearn's per-call overhead is replaced with a numpy argsort."""
    s = np.concatenate([pos, neg])
    y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1.0 - y)
    denom = tp + fp
    precision = np.where(denom > 0, tp / denom, 0.0)
    npos = y.sum()
    return float(np.sum(precision * y) / npos) if npos else 0.0


def challenge(delivered, labels, pos_keep, neg_keep):
    """AP per horizon + mAP + clip-bootstrap CIs over the kept pos/neg clips."""
    pos = sorted(c for c in {cc for h in HOR for cc in delivered[h]}
                 if (labels.get(c) or {}).get("label") == "positive" and pos_keep(c))
    neg = sorted(c for c in {cc for h in HOR for cc in delivered[h]}
                 if (labels.get(c) or {}).get("label") == "negative" and neg_keep(c))
    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
             for _ in range(NB)]
    ap = {}
    boot_ap = {}
    for h in HOR:
        P = np.array([delivered[h][c] for c in pos if c in delivered[h]])
        N = np.array([delivered[h][c] for c in neg if c in delivered[h]])
        pt = _ap(P, N) if len(P) and len(N) else None
        Pf = np.array([delivered[h].get(c, np.nan) for c in pos])
        Nf = np.array([delivered[h].get(c, np.nan) for c in neg])
        pin = np.array([c in delivered[h] for c in pos])
        nin = np.array([c in delivered[h] for c in neg])
        bs = []
        for pi, ni in boots:
            ps = pi[pin[pi]]
            ns = ni[nin[ni]]
            if len(ps) and len(ns):
                bs.append(_ap(Pf[ps], Nf[ns]))
        ap[h] = {"ap": pt, "ci": ([float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
                                  if bs else None), "n_pos": int(pin.sum()), "n_neg": int(nin.sum())}
        boot_ap[h] = np.array(bs)
    mAP = float(np.mean([ap[h]["ap"] for h in CHALLENGE if ap[h]["ap"] is not None]))
    bm = np.mean([boot_ap[h][:min(len(boot_ap[h]) for h in CHALLENGE)] for h in CHALLENGE], axis=0) \
        if all(len(boot_ap[h]) for h in CHALLENGE) else np.array([])
    mAP_ci = ([float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))] if len(bm) else None)
    return {"ap": ap, "challenge_mAP": mAP, "challenge_mAP_ci": mAP_ci,
            "n_pos_clips": len(pos), "n_neg_clips": len(neg),
            "_boot": {h: boot_ap[h] for h in CHALLENGE}}


def paired_mAP(a, b):
    """paired challenge mAP diff a - b with clip-bootstrap CI (shared boots)."""
    if not a.get("_boot") or not b.get("_boot"):
        return None
    n = min(min(len(a["_boot"][h]) for h in CHALLENGE), min(len(b["_boot"][h]) for h in CHALLENGE))
    if n == 0:
        return None
    da = np.mean([a["_boot"][h][:n] for h in CHALLENGE], axis=0)
    db = np.mean([b["_boot"][h][:n] for h in CHALLENGE], axis=0)
    d = da - db
    return {"diff": a["challenge_mAP"] - b["challenge_mAP"],
            "ci": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}


def main():
    a4, b4, n4, p4 = platt(SHEP_4BI)
    a32, b32, n32, p32 = platt(SHEP_32BI)
    cal = (a4, b4, a32, b32)
    dur, labels = durations_refs()
    side = sh_ep_side()
    # fake event times for negatives: duration/2 + N(0,sigma), sigma from positive (ref - dur/2)
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}

    splits = {"ALL": (lambda c: True), "DEV": (lambda c: side.get(c) == "DEV"),
              "EVAL": (lambda c: side.get(c) == "EVAL")}
    results = {"_what": "StudyDSMAP: delivered-stream challenge mAP per arm (D202 (4)).",
               "horizons": HOR, "challenge_horizons": CHALLENGE, "n_bootstrap": NB, "seed": SEED,
               "platt_maps": {"device_4BI": {"a": a4, "b": b4, "dev_n": n4, "dev_pos": p4,
                                             "form": "cal_logodds = a*score + b, fit SH-EP DEV EP-G"},
                              "cloud_32BI": {"a": a32, "b": b32, "dev_n": n32, "dev_pos": p32}},
               "sigma_fake_event_s": sigma, "arms": {}}

    # pooled delivered crops per arm: one value per SOURCE CLIP (mean of its crop scores over all
    # seeds and plays), so the bootstrap in challenge() resamples SOURCE VIDEOS, as required.
    def pooled_delivered(arm_raw, device_only=False):
        acc = {h: defaultdict(list) for h in HOR}
        per_seed = {}
        got = False
        for s in E.SEEDS:
            d = delivered_crops(arm_raw, s, cal, dur, labels, fake, device_only)
            if d is None:
                continue
            got = True
            per_seed[s] = d
            for h in HOR:
                for c, v in d[h].items():
                    acc[h][c].append(v)
        if not got:
            return None, None
        pooled = {h: {c: float(np.mean(vs)) for c, vs in acc[h].items()} for h in HOR}
        return pooled, per_seed

    def seed_mAP(per_seed, keep):
        """point-estimate challenge mAP per seed (no CI), split by keep."""
        out = {}
        for s, d in per_seed.items():
            aps = []
            for h in CHALLENGE:
                P = [d[h][c] for c in d[h] if (labels.get(c) or {}).get("label") == "positive" and keep(c)]
                N = [d[h][c] for c in d[h] if (labels.get(c) or {}).get("label") == "negative" and keep(c)]
                if P and N:
                    aps.append(_ap(np.array(P), np.array(N)))
            out[s] = float(np.mean(aps)) if aps else None
        return out

    dev_pool, _dev_ps = pooled_delivered("hybrid-F-lhreq-noc3", device_only=True)
    rung3_pool, _r3_ps = pooled_delivered("covex-v6-fair-c5attr", device_only=False)

    def tab_for(pool, keep):
        return challenge(pool, labels, keep, keep)

    ref_rows = {}
    for sp, keep in splits.items():
        ref_rows[sp] = {"device-only": tab_for(dev_pool, keep),
                        "rung3-covex-v6-fair-c5attr": tab_for(rung3_pool, keep)}

    for disp, raw in E.ARMS + [("device-only", None)]:
        if disp == "device-only":
            pool, per_seed = dev_pool, _dev_ps
        else:
            pool, per_seed = pooled_delivered(raw, device_only=False)
        if pool is None:
            continue
        results["arms"][disp] = {"splits": {}, "per_seed_mAP": {}}
        for sp, keep in splits.items():
            tab = ref_rows[sp]["device-only"] if disp == "device-only" else tab_for(pool, keep)
            results["arms"][disp]["per_seed_mAP"][sp] = seed_mAP(per_seed, keep)
            r3 = ref_rows[sp]["rung3-covex-v6-fair-c5attr"]
            dv = ref_rows[sp]["device-only"]
            out = {"challenge_mAP": tab["challenge_mAP"], "challenge_mAP_ci": tab["challenge_mAP_ci"],
                   "n_pos_clips": tab["n_pos_clips"], "n_neg_clips": tab["n_neg_clips"],
                   "ap_by_horizon": {h: {"ap": tab["ap"][h]["ap"], "ci": tab["ap"][h]["ci"]}
                                     for h in HOR},
                   "paired_vs_rung3": paired_mAP(tab, r3),
                   "paired_vs_device_only": paired_mAP(tab, dv)}
            results["arms"][disp]["splits"][sp] = out

    # sanity: device-only delivered-stream mAP equals device-table-only computation (identical by
    # construction here, since device-only sets every instant to the device calibrated score)
    results["sanity_device_only_from_device_table"] = {
        "_claim": "device-only delivered stream uses only device scores, so it IS the device-table "
                  "computation; the two are identical by construction.",
        "device_only_EVAL_mAP": results["arms"]["device-only"]["splits"]["EVAL"]["challenge_mAP"]}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dsmap_results.json").write_text(json.dumps(results, indent=1, default=float))
    _plot(results)
    _md(results)
    print("wrote dsmap_results.json, dsmap_ap_vs_horizon.png, study_dsmap.md")
    print("device-only EVAL mAP:", round(results["arms"]["device-only"]["splits"]["EVAL"]["challenge_mAP"], 4))
    print("rung3 EVAL mAP:", round(results["arms"]["fair-c5attr"]["splits"]["EVAL"]["challenge_mAP"], 4))


def _plot(results):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    arms = ["device-only", "base", "fair-c5attr", "state-uo", "simplestream"]
    arms = [a for a in arms if a in results["arms"]]
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    cols = ["#000000", "#0072B2", "#D55E00", "#009E73", "#9A9A9A"]
    for a, col in zip(arms, cols):
        tab = results["arms"][a]["splits"]["EVAL"]
        ys = [tab["ap_by_horizon"][h]["ap"] for h in HOR]
        ax.plot(HOR, ys, marker="o", color=col, label=f"{a} (mAP {tab['challenge_mAP']:.2f})", lw=2)
    ax.set_xlabel("seconds before event (horizon t)")
    ax.set_ylabel("delivered-stream challenge AP")
    ax.set_title("StudyDSMAP: delivered-stream challenge AP vs horizon (EVAL, 210 clips)")
    ax.invert_xaxis()
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "dsmap_ap_vs_horizon.png", dpi=200, metadata={"Software": None},
                bbox_inches="tight")
    fig.savefig(OUT / "dsmap_ap_vs_horizon.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


def _md(results):
    L = []
    A = L.append
    pm = results["platt_maps"]
    A("# StudyDSMAP: delivered-stream challenge mAP per arm (D202 (4))")
    A("")
    A("Delivered score per decision instant: the cloud score where an on-time cloud answer exists "
      "(outcomes.jsonl.gz, joined by opportunity_id), else the device score (dashcam_instants). Each "
      "tier Platt-calibrated on StudySH-EP DEV EP-G before mixing (D57), then the Nexar challenge "
      "protocol (E9c). Seeds 4-7 pooled; splits ALL / DEV (90) / EVAL (210) from the StudySH-EP fold. "
      "Bootstrap over clips, 2000 resamples, seed 0.")
    A("")
    A(f"Platt maps (calibrated log-odds = a*score + b, fit on SH-EP DEV EP-G, n={pm['device_4BI']['dev_n']}): "
      f"device 4BI a={pm['device_4BI']['a']:.4f} b={pm['device_4BI']['b']:.4f}; "
      f"cloud 32BI a={pm['cloud_32BI']['a']:.4f} b={pm['cloud_32BI']['b']:.4f}.")
    A("")
    A("## Delivered-stream challenge mAP per arm (EVAL), paired vs rung 3")
    A("")
    A("| arm | mAP ALL | mAP EVAL [95% CI] | EVAL vs rung3 [CI] | EVAL vs device-only [CI] |")
    A("|---|---|---|---|---|")
    order = sorted(results["arms"], key=lambda a: -results["arms"][a]["splits"]["EVAL"]["challenge_mAP"])
    for a in order:
        e = results["arms"][a]["splits"]["EVAL"]
        al = results["arms"][a]["splits"]["ALL"]
        ci = e["challenge_mAP_ci"]
        cis = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "n/a"
        pr = e["paired_vs_rung3"]
        prs = f"{pr['diff']:+.3f} [{pr['ci'][0]:+.3f}, {pr['ci'][1]:+.3f}]" if pr else "n/a"
        pd = e["paired_vs_device_only"]
        pds = f"{pd['diff']:+.3f} [{pd['ci'][0]:+.3f}, {pd['ci'][1]:+.3f}]" if pd else "n/a"
        A(f"| {a} | {al['challenge_mAP']:.3f} | {e['challenge_mAP']:.3f} {cis} | {prs} | {pds} |")
    A("")
    A("## Sanity")
    A("")
    A(results["sanity_device_only_from_device_table"]["_claim"])
    A("")
    A("## Provenance")
    A("")
    A("Inputs: each arm's cell outcomes.jsonl.gz and the per-seed dashcam_instants traces; "
      "StudySH-EP DEV EP-G for Platt; E9c challenge protocol. Deterministic given inputs.")
    (ROOT / "reports/study_dsmap.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
