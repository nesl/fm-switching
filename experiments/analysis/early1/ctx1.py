#!/usr/bin/env python3
"""StudyCTX1 (D207): verify StudyDASH2 Part 6 before a build. Offline, read-only, CPU only. Seeds
4-7. D199 metric. Three checks + the pre-registered decision rule.

Check 1: select on DEV, confirm on EVAL. Conditions C1/C3/C6/EP-B/EP-G, device stream the workload's
default EP-G device scores. Calibration fitted on SH-EP DEV EP-G only (per tier, no cross-fit into
EVAL). D153 applied: a crop whose condition query sees fewer than 3 frames (n_frames < 3) is NOT a
decision instant, so the live device score stands there.
Check 2: trace what stands at restart crops (done in the report: cloud serves 100 percent of the 43
restart crops, so the 0.170 is small-sample on fresh context, not a which-score-stands artefact).
Check 3: non-decision crop fraction per condition under D153, and the recomputed condition mAP.
Cost: uncached tokens per decision instant and peak per-device episode KV (prompt) tokens.
No em dashes.
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
CONDS = ["C1", "C3", "C6", "EP-B", "EP-G"]
CONDFILE = {c: ROOT / f"results/dashcam/study_sh_ep/h100/sh_ep_requests_32BI_shep2-{c}.jsonl.gz"
            for c in CONDS}
OUT = ROOT / "reports/figures"


def dev_platt(path, cond="EP-G"):
    """Platt on SH-EP DEV EP-G only (per the task: calibration fitted on DEV EP-G clips)."""
    from sklearn.linear_model import LogisticRegression
    X, y = [], []
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        for l in fh:
            if '"EP-G"' not in l or '"DEV"' not in l:
                continue
            r = json.loads(l)
            if r.get("condition") != "EP-G" or r.get("side") != "DEV" or r.get("score") is None:
                continue
            X.append([float(r["score"])]); y.append(1 if r.get("label") == "positive" else 0)
    clf = LogisticRegression(C=1e6, solver="lbfgs").fit(X, y)
    return float(clf.coef_[0][0]), float(clf.intercept_[0])


def main():
    dur, labels = D2.DS.durations_refs()
    allclips = set()
    for s in D2.E.SEEDS:
        allclips |= set(c for c, _, _ in D2._trace(s).values())
    side = D2.DS.sh_ep_side()
    pos_dev = [labels[c]["ref"] - dur.get(c, 0) / 2 for c in labels
               if labels[c].get("label") == "positive" and labels[c].get("ref") is not None
               and c in dur]
    sigma = float(np.array(pos_dev).std(ddof=1))
    rng0 = np.random.default_rng(0)
    fake = {c: float(min(max(dur[c] / 2 + rng0.normal(0, sigma), 4.5), dur[c]))
            for c in sorted(labels) if labels[c].get("label") == "negative" and c in dur}

    a4, b4 = dev_platt(D2.SHEP_4BI)   # device Platt (DEV EP-G)
    a32, b32 = dev_platt(D2.SHEP_32BI)  # cloud Platt (DEV EP-G)

    # ---- workload device crops (device stream, 4BI calibrated), pooled over seeds ----
    dev_acc = {h: defaultdict(list) for h in HOR}
    dev_at = {}  # (clip,h) -> device cal, for the D153 fill
    for s in D2.E.SEEDS:
        for oid, (clip, pts, dscore) in D2._trace(s).items():
            meta = labels.get(clip) or {}
            ref = (float(meta["ref"]) if meta.get("label") == "positive" and meta.get("ref") is not None
                   else (fake.get(clip) if meta.get("label") == "negative" else None))
            if ref is None:
                continue
            for h in HOR:
                if abs(pts - (ref - h)) <= 0.5 + 1e-9:
                    dev_acc[h][clip].append(a4 * dscore + b4)
    dev_stream = {h: {c: float(np.mean(v)) for c, v in dev_acc[h].items()} for h in HOR}
    for h in HOR:
        for c, v in dev_stream[h].items():
            dev_at[(c, h)] = v

    # ---- clips split ----
    pos_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "positive")
    neg_all = sorted(c for c in allclips if (labels.get(c) or {}).get("label") == "negative")
    pos_dev_c = [c for c in pos_all if side.get(c) == "DEV"]
    neg_dev_c = [c for c in neg_all if side.get(c) == "DEV"]
    pos_ev_c = [c for c in pos_all if side.get(c) == "EVAL"]
    neg_ev_c = [c for c in neg_all if side.get(c) == "EVAL"]
    boot_dev = D2.Boot(pos_dev_c, neg_dev_c)
    boot_eval = D2.Boot(pos_ev_c, neg_ev_c)
    boot_all = D2.Boot(pos_all, neg_all)

    # ---- condition streams with D153 (device-fill where n_frames < 3) ----
    def cond_stream(c):
        byclip = defaultdict(list)  # clip -> [(rel_to_ref, score, n_frames)]
        tok_unc, tok_prompt = [], []
        for l in gzip.open(CONDFILE[c], "rt"):
            r = json.loads(l)
            if r.get("condition") != c or r.get("rel_to_ref") is None or r.get("score") is None:
                continue
            byclip[r["file_name"]].append((float(r["rel_to_ref"]), float(r["score"]),
                                           r.get("n_frames")))
            pt, ct = r.get("prompt_tokens"), r.get("cached_tokens")
            if pt is not None and ct is not None:
                tok_unc.append(pt - ct); tok_prompt.append(pt)
        stream = {h: {} for h in HOR}
        n_crop = n_nondec = 0
        for clip, rv in byclip.items():
            if clip not in allclips:
                continue
            for h in HOR:
                near = [(sc, nf) for (rr, sc, nf) in rv if abs(rr - (-h)) <= 0.5 + 1e-9]
                if not near:
                    continue
                n_crop += 1
                sc, nf = near[0]
                if nf is not None and nf < 3:  # D153: non-decision, device stands
                    n_nondec += 1
                    if (clip, h) in dev_at:
                        stream[h][clip] = dev_at[(clip, h)]
                else:
                    stream[h][clip] = a32 * sc + b32
        return stream, (n_nondec / n_crop if n_crop else None), tok_unc, tok_prompt

    def mAP(stream, boot):
        return boot.table(stream)

    dev_tab_dev = mAP(dev_stream, boot_dev)
    dev_tab_eval = mAP(dev_stream, boot_eval)

    conds = {}
    for c in CONDS:
        stream, nondec, tu, tp = cond_stream(c)
        tdev = mAP(stream, boot_dev)
        teval = mAP(stream, boot_eval)
        conds[c] = {"stream": stream, "tdev": tdev, "teval": teval, "nondec_frac": nondec,
                    "unc_tok_median": (statistics.median(tu) if tu else None),
                    "peak_prompt_tok": (max(tp) if tp else None),
                    "dev_mAP": tdev["challenge_mAP"], "eval_mAP": teval["challenge_mAP"],
                    "dev_gain_vs_device": tdev["challenge_mAP"] - dev_tab_dev["challenge_mAP"]}

    # ---- CHECK 1 selection on DEV (fixed rule) ----
    # largest DEV gain over device-only; tie within 0.02 -> fewer uncached tokens
    ranked = sorted(CONDS, key=lambda c: -conds[c]["dev_gain_vs_device"])
    top = ranked[0]
    tied = [c for c in CONDS if conds[c]["dev_gain_vs_device"] >= conds[top]["dev_gain_vs_device"] - 0.02]
    selected = min(tied, key=lambda c: (conds[c]["unc_tok_median"] or 1e9))
    # EVAL confirmation of the selected condition
    sel = conds[selected]
    eval_vs_dev = boot_eval.paired(sel["teval"], dev_tab_eval)
    eval_vs_epg = boot_eval.paired(sel["teval"], conds["EP-G"]["teval"])
    shift = D2.horizon_shift(sel["teval"], dev_tab_eval)

    # sanity: label shuffle drops to base rate (selected condition, EVAL)
    rngc = np.random.default_rng([0, 9])
    aps = []
    for h in CHALLENGE:
        P = [sel["stream"][h][c] for c in pos_ev_c if c in sel["stream"][h]]
        N = [sel["stream"][h][c] for c in neg_ev_c if c in sel["stream"][h]]
        y = np.concatenate([np.ones(len(P)), np.zeros(len(N))])
        s = np.concatenate([P, N])
        from sklearn.metrics import average_precision_score
        aps.append(float(average_precision_score(rngc.permutation(y), s)))
    shuffle_mAP = float(np.mean(aps))
    base_rate = len(pos_ev_c) / (len(pos_ev_c) + len(neg_ev_c))

    # workload DEV/EVAL clip counts
    wl_dev = len([c for c in allclips if side.get(c) == "DEV"])
    wl_eval = len([c for c in allclips if side.get(c) == "EVAL"])
    n_crash_dev = len(pos_dev_c); n_crash_eval = len(pos_ev_c)

    # ---- CHECK 3 recomputed Part 6 (D153) vs Part 6 as-was (no D153) for contrast ----
    # Part 6 as-was used cross-fit ALL; here report the D153 ALL mAP per condition for comparison
    conds_all = {c: mAP(conds[c]["stream"], boot_all)["challenge_mAP"] for c in CONDS}

    results = {"_what": "StudyCTX1: verify StudyDASH2 Part 6 (D207).",
               "calibration": {"note": "Platt on SH-EP DEV EP-G only, per tier",
                               "device_4BI": [a4, b4], "cloud_32BI": [a32, b32]},
               "workload_clip_counts": {"DEV": wl_dev, "EVAL": wl_eval,
                                        "crash_DEV": n_crash_dev, "crash_EVAL": n_crash_eval},
               "device_only": {"DEV_mAP": dev_tab_dev["challenge_mAP"],
                               "EVAL_mAP": dev_tab_eval["challenge_mAP"]},
               "check1_conditions": {c: {
                   "DEV_mAP": conds[c]["dev_mAP"], "DEV_gain_vs_device": conds[c]["dev_gain_vs_device"],
                   "EVAL_mAP": conds[c]["eval_mAP"], "ALL_mAP_D153": conds_all[c],
                   "nondecision_crop_frac_D153": conds[c]["nondec_frac"],
                   "uncached_tok_per_decision_instant": conds[c]["unc_tok_median"],
                   "peak_prompt_tokens": conds[c]["peak_prompt_tok"]} for c in CONDS},
               "check1_selection": {
                   "dev_ranked": ranked, "tied_within_0p02": tied, "SELECTED": selected,
                   "selected_EVAL_mAP": sel["eval_mAP"],
                   "selected_EVAL_gain_vs_device": {"diff": eval_vs_dev["diff"], "ci": eval_vs_dev["ci"]},
                   "selected_EVAL_gain_vs_EP_G": {"diff": eval_vs_epg["diff"], "ci": eval_vs_epg["ci"]},
                   "selected_horizon_shift_vs_device": shift,
                   "selected_EVAL_ap_by_horizon": {h: sel["teval"]["ap"][h]["ap"] for h in HOR}},
               "check2_restart": {
                   "n_restart_crops": 43, "cloud_served_fraction": 1.0,
                   "finding": "at restart crops the cloud serves 100 percent of instants (43 of 43), "
                              "so the StudyDASH2 Part 3-ext 0.170 is NOT a device-fill or "
                              "which-score-stands artefact; it is a small-sample value (43 positive "
                              "crops) on genuinely fresh short context, and it does not enter any "
                              "committed headline (the ceiling, StudyDSMAP and StudyEXIT2 use all "
                              "crops, not the restart split). No committed headline is affected, so "
                              "no escalation on Check 2."},
               "check3_d153": {
                   "part6_applied_d153": False,
                   "finding": "StudyDASH2 Part 6 did NOT apply D153; it scored the cloud at every "
                              "crop including non-decision instants. Under D153 C1 is 100 percent "
                              "non-decision (one frame below the three-frame minimum, not "
                              "deployable), EP-B is 24.5 percent non-decision (device stands on the "
                              "first two instants of each 5 s block), and C3/C6/EP-G are 0 percent. "
                              "The condition mAPs here are the D153-correct recomputation.",
                   "nondecision_crop_frac": {c: conds[c]["nondec_frac"] for c in CONDS}},
               "sanity": {"device_only_from_device_table": dev_tab_eval["challenge_mAP"],
                          "label_shuffle_selected_EVAL_mAP": shuffle_mAP, "base_rate_EVAL": base_rate}}

    # ---- DECISION ----
    a_ok = eval_vs_dev["ci"][0] > 0
    b_ok = eval_vs_epg["diff"] > 0
    c_ok = (selected not in ("C1",)) and (conds[selected]["nondec_frac"] or 0) < 0.5  # survives D153
    build = a_ok and b_ok and c_ok
    results["DECISION"] = {
        "BUILD_READY": build, "selected_condition": selected,
        "a_eval_gain_vs_device_ci_lb_gt0": a_ok,
        "b_eval_gain_vs_epg_point_positive": b_ok,
        "c_survives_checks_2_and_3": c_ok,
        "reason": ("build ready" if build else
                   "the DEV-selected condition does not meet all three decision conditions under "
                   "D153")}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ctx1_results.json").write_text(json.dumps(
        {k: v for k, v in results.items()}, indent=1, default=float,
        skipkeys=True))
    _plot(results, conds, dev_tab_dev, dev_tab_eval)
    print("device-only DEV/EVAL:", round(dev_tab_dev["challenge_mAP"], 3),
          round(dev_tab_eval["challenge_mAP"], 3))
    for c in CONDS:
        v = results["check1_conditions"][c]
        print(f"  {c:5}: DEV {v['DEV_mAP']:.3f} (gain {v['DEV_gain_vs_device']:+.3f}) EVAL "
              f"{v['EVAL_mAP']:.3f} nondec {v['nondecision_crop_frac_D153']:.3f} "
              f"unc_tok {v['uncached_tok_per_decision_instant']:.0f} peak_prompt {v['peak_prompt_tokens']}")
    print("SELECTED (DEV):", selected,
          "| EVAL vs device", round(eval_vs_dev["diff"], 3), eval_vs_dev["ci"],
          "| EVAL vs EP-G", round(eval_vs_epg["diff"], 3))
    print("DECISION:", json.dumps(results["DECISION"]))
    print("sanity shuffle mAP", round(shuffle_mAP, 3), "base rate", round(base_rate, 3))


def _plot(results, conds, dev_dev, dev_eval):
    import matplotlib
    os.environ.setdefault("SOURCE_DATE_EPOCH", "1700000000")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    x = np.arange(len(CONDS))
    w = 0.38
    dv = [results["check1_conditions"][c]["DEV_mAP"] for c in CONDS]
    ev = [results["check1_conditions"][c]["EVAL_mAP"] for c in CONDS]
    ax.bar(x - w / 2, dv, w, label="DEV", color="#56B4E9")
    ax.bar(x + w / 2, ev, w, label="EVAL", color="#0072B2")
    ax.axhline(dev_dev["challenge_mAP"], color="#000000", ls="--", lw=1, label="device-only (DEV)")
    sel = results["check1_selection"]["SELECTED"]
    ax.annotate("DEV-selected", (list(CONDS).index(sel), dv[list(CONDS).index(sel)] + 0.01),
                ha="center", fontsize=8, color="#D55E00")
    ax.set_xticks(x); ax.set_xticklabels([f"{c}\n({results['check1_conditions'][c]['nondecision_crop_frac_D153']*100:.0f}% nd)" for c in CONDS], fontsize=8)
    ax.set_ylabel("challenge mAP (D153 applied)")
    ax.set_title("StudyCTX1 Check 1/3: condition challenge mAP by split, D153 applied")
    ax.legend(fontsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "ctx1_by_condition.png", dpi=200, metadata={"Software": None}, bbox_inches="tight")
    fig.savefig(OUT / "ctx1_by_condition.pdf", metadata={"Creator": None, "Producer": None},
                bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
