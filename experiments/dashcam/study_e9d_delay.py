#!/usr/bin/env python3
"""StudyE9d-delay — what a DELAY costs, as a curve.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
StudyD14b's committed 0.25-s trace; every latency is read from a committed StudyD4 / D7 / D7b / D8
measurement through study_e9_episodes.py; the delivery model, episode engine, AP engine and
thresholds are imported unchanged from study_e9b_dense.py and the challenge-metric crop geometry
from study_e9c_challenge.py.

THIS JOB PRODUCES CURVES AND MAKES NO POLICY CLAIM. Two parts:

(a) V(d): the challenge mAP and the streaming AP of each arm when every CLOUD score is delivered
    d seconds later than its base delivery, for d = 0, 0.25, ..., 3.0 s. The device arm is
    unchanged and is the reference; d* is the added delay at which a cloud arm falls to the
    device's value - the cloud's lead, in seconds.

(b) Blocking windows: a window of length w during which the cloud path is down, either QUEUE
    (scores still computed, delivered at the window's end) or SUSPEND (no call issued; the
    application uses the device's latest score). Loss per window, and whether it is convex in w.

Scores are continuous log P(Yes). No literal Yes/No answer is used anywhere. Challenge mAP and
streaming AP are NEVER mixed: StudyE9c's rule is that signs and orderings transfer between them,
excess-over-chance ratios only while both arms are near chance, and absolute levels never.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402
import study_e9_episodes as E9  # noqa: E402
import study_e9b_dense as B  # noqa: E402
import study_e9c_challenge as Cq  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9d"
SEED, NB = B.SEED, B.NB
STEP = B.STEP_DENSE
MISSING = B.MISSING

SETTING = "measured@25"                     # setting (ii) at 25 % load, the pre-registered base
STREAM_H = (0.0, 0.5, 1.0, 1.5)             # streaming AP horizons
CHAL_H = Cq.HORIZONS                        # (0.5, 1.0, 1.5), the challenge's own
CADENCES = (0.5, 1.0)
CAD_PRIMARY = 0.5
CLOUD_ARMS = (("32BI", 1), ("32BI", 3))
DEVICE = B.DEVICE                           # ("4BI", 1)
DELAYS_S = tuple(round(0.25 * k, 2) for k in range(13))          # 0 .. 3.0 s
WINDOWS_S = (0.25, 0.5, 1.0, 2.0, 2.5, 4.0)
MODES = ("QUEUE", "SUSPEND")
N_PLACE = 20
CONVEX_PAIRS = ((0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 4.0))


# ================================================================ AP (challenge form)
def ap_fast(y, s):
    """scikit-learn's `average_precision_score`, written so the bootstrap can afford it.

    sklearn computes AP as sum_k (R_k - R_{k-1}) * P_k over the precision-recall curve's
    threshold points, which are the LAST index of each tie group in descending score order. Ties
    matter here because a bootstrap resample repeats clips, making exactly equal scores common.
    Control (d) asserts this function equals `average_precision_score` on every real cell.
    """
    s = np.asarray(s, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    P = y.sum()
    if P <= 0:
        return 0.0
    o = np.argsort(-s, kind="mergesort")
    ys, ss = y[o], s[o]
    tps = np.cumsum(ys)
    fps = np.cumsum(1.0 - ys)
    last = np.r_[ss[1:] != ss[:-1], True]           # last index of each tie group
    tp, fp = tps[last], fps[last]
    prec = tp / (tp + fp)
    rec = tp / P
    return float(np.sum(np.diff(np.r_[0.0, rec]) * prec))


# ================================================================ delivery
def cloud_delivered(arr, G, mc, D, window=None, mode=None, dev_seen=None):
    """The application-visible cloud score at every grid index.

    `arr` is the arm's score per COMPUTE index, `mc` its cadence in steps and `D` its base
    sample-and-hold shift (ceil(L / step), the latency itself never rounded). With no window this
    is exactly StudyE9b's `held_stream`.

    `window = (j0, j1)` is an inclusive index range during which the cloud path is down:
      QUEUE   - calls are still computed on cadence, and anything that would have been readable
                inside the window becomes readable at j1 + 1 (the window's end). During the
                window the application holds its last PRE-window cloud delivery.
      SUSPEND - no call is computed at a compute index inside the window, and during the window
                the application uses the DEVICE's latest delivered score. A call issued before
                the window whose delivery would land inside it is also held to j1 + 1: the link
                is down for it too.
    """
    comp = np.arange(0, G, mc)
    if window is not None and mode == "SUSPEND":
        j0, j1 = window
        comp = comp[(comp < j0) | (comp > j1)]
    dliv = comp + D
    if window is not None:
        j0, j1 = window
        dliv = np.where((dliv >= j0) & (dliv <= j1), j1 + 1, dliv)
    out = np.full(G, MISSING)
    if len(comp):
        k = np.searchsorted(dliv, np.arange(G), side="right") - 1
        ok = k >= 0
        out[ok] = arr[comp[k[ok]]]
    if window is not None and mode == "SUSPEND":
        j0, j1 = window
        u = np.arange(max(j0, 0), min(j1, G - 1) + 1)
        if len(u):
            out[u] = dev_seen[u]
    return out


# ================================================================ challenge metric
class Challenge:
    """StudyE9c's challenge metric: one crop per clip, horizons 0.5 / 1.0 / 1.5 s, the paper's
    alert rule, fake negative event times at duration/2 + N(0, sigma) with sigma the positive
    clips' own dispersion, scikit-learn AP per horizon, unweighted mean. Geometry and sigma are
    recomputed with StudyE9c's own functions so the two studies cannot drift apart."""

    def __init__(self, ctx):
        self.ctx = ctx
        meta, pos, neg = ctx["meta"], ctx["pos"], ctx["neg"]
        cm = Cq.read_clip_meta()
        assert set(cm) == set(ctx["clips"])
        self.cm = cm
        devs = np.array([cm[c]["event"] - cm[c]["duration"] / 2.0 for c in pos])
        self.sigma = float(devs.std(ddof=1))
        self.incl = {c: tuple(h for h in CHAL_H
                              if h <= 0.5 or (cm[c]["event"] - cm[c]["alert"]) > h) for c in pos}
        self.n_incl = {h: sum(1 for c in pos if h in self.incl[c]) for h in CHAL_H}
        self.base = {h: self.n_incl[h] / (self.n_incl[h] + len(neg)) for h in CHAL_H}
        self.pos_idx = {(c, h): B.target_index(meta, c, h, STEP) for c in pos for h in self.incl[c]}
        fake = Cq.fake_event_times(cm, neg, self.sigma, 0)
        self.fake = fake
        self.neg_idx = {(c, h): Cq.crop_index(meta, c, fake[c] - h) for c in neg for h in CHAL_H}
        rng = np.random.default_rng(SEED)
        self.boots = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
                      for _ in range(NB)]
        self.pmask = {h: np.array([h in self.incl[c] for c in pos]) for h in CHAL_H}

    def crops(self, streams):
        pos, neg = self.ctx["pos"], self.ctx["neg"]
        Pf = {h: np.array([streams[c][self.pos_idx[(c, h)]] if h in self.incl[c] else np.nan
                           for c in pos]) for h in CHAL_H}
        N = {h: np.array([streams[c][self.neg_idx[(c, h)]] for c in neg]) for h in CHAL_H}
        return Pf, N

    def point(self, streams, ap=ap_fast):
        Pf, N = self.crops(streams)
        out = {}
        for h in CHAL_H:
            p = Pf[h][self.pmask[h]]
            y = np.r_[np.ones(len(p)), np.zeros(len(N[h]))]
            out[h] = ap(y, np.r_[p, N[h]])
        out["mAP"] = float(np.mean([out[h] for h in CHAL_H]))
        return out

    def full(self, streams):
        Pf, N = self.crops(streams)
        pt = self.point(streams)
        bs = {h: np.empty(NB) for h in CHAL_H}
        bm = np.empty(NB)
        for b, (pi, ni) in enumerate(self.boots):
            vals = []
            for h in CHAL_H:
                sel = pi[self.pmask[h][pi]]
                nn = N[h][ni]
                if len(sel):
                    y = np.r_[np.ones(len(sel)), np.zeros(len(nn))]
                    a = ap_fast(y, np.r_[Pf[h][sel], nn])
                else:
                    a = 0.0
                bs[h][b] = a
                vals.append(a)
            bm[b] = float(np.mean(vals))
        out = {h: dict(ap=pt[h], ci=[float(np.percentile(bs[h], 2.5)),
                                     float(np.percentile(bs[h], 97.5))]) for h in CHAL_H}
        out["mAP"] = dict(value=pt["mAP"], ci=[float(np.percentile(bm, 2.5)),
                                               float(np.percentile(bm, 97.5))])
        return out, dict(ap=bs, mAP=bm)


# ================================================================ crossing
def crossing(delays, curve, target):
    """The added delay at which a falling cloud curve first reaches the device's value, by linear
    interpolation between the two bracketing delays. None when it never reaches it."""
    d = np.asarray(delays, dtype=np.float64)
    v = np.asarray(curve, dtype=np.float64)
    below = np.where(v <= target)[0]
    if len(below) == 0:
        return None
    k = int(below[0])
    if k == 0:
        return 0.0
    v0, v1 = v[k - 1], v[k]
    if v0 == v1:
        return float(d[k])
    return float(d[k - 1] + (v0 - target) * (d[k] - d[k - 1]) / (v0 - v1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = B.build(step=STEP, horizons=STREAM_H)
    meta, clips = ctx["meta"], ctx["clips"]
    eng, chal = ctx["eng"], Challenge(ctx)
    G = {c: meta[c]["G"] for c in clips}

    dev_seen, m_dev, D_dev, L_dev = B.dev_seen_all(ctx, SETTING)
    sched = {}
    for arm in CLOUD_ARMS:
        _d, Lc = B.latencies(SETTING, *arm)
        sched[arm] = dict(L=Lc, D=B.steps_ceil(Lc, STEP))

    res = dict(
        label="StudyE9d-delay: delivered value as a function of ADDED DELAY, and the loss from a "
              "blocking window, on StudyD14b's 0.25-s grid with StudyE9b's delivery model. OFFLINE "
              "REPLAY OF COMMITTED RESULTS; CPU only on flash; no GPU, no model server, no "
              "inference. Scores are continuous log P(Yes); no literal Yes/No answer is used "
              "anywhere. THIS JOB PRODUCES CURVES AND MAKES NO POLICY CLAIM. Challenge mAP and "
              "streaming AP are reported under their own names and are never mixed (StudyE9c).",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, step_s=STEP, setting=SETTING,
        delays_s=list(DELAYS_S), windows_s=list(WINDOWS_S), modes=list(MODES),
        n_placements=N_PLACE, cadences=list(CADENCES), cadence_primary=CAD_PRIMARY,
        streaming_horizons=list(STREAM_H), challenge_horizons=list(CHAL_H),
        n_clips=dict(positive=len(ctx["pos"]), negative=len(ctx["neg"])),
        streaming_chance=ctx["chance"],
        challenge_chance=float(np.mean([chal.base[h] for h in CHAL_H])),
        challenge_base_rate_by_horizon={h: chal.base[h] for h in CHAL_H},
        challenge_n_positive_by_horizon={h: chal.n_incl[h] for h in CHAL_H},
        challenge_sigma_s=chal.sigma,
        device=dict(arm="4BI_N1", latency_s=L_dev, cadence_steps=m_dev,
                    cadence_s=m_dev * STEP, hold_shift_steps=D_dev, hold_shift_s=D_dev * STEP),
        cloud={f"{a[0]}_N{a[1]}": dict(latency_s=sched[a]["L"], hold_shift_steps=sched[a]["D"],
                                       hold_shift_s=sched[a]["D"] * STEP) for a in CLOUD_ARMS},
        vd={}, dstar={}, blocking={}, convexity={}, controls={})

    # ---------------------------------------------------------------- device reference
    sap, sboot = eng.full(dev_seen)
    cap, cboot = chal.full(dev_seen)
    res["vd"]["device-only 4BI_N1"] = dict(
        arm="4BI_N1", kind="device", cadence_s=m_dev * STEP, delay_s=0.0,
        streaming={str(h): dict(ap=sap[h]["ap"], ci=sap[h]["ci"],
                                multiple_of_chance=sap[h]["ap"] / ctx["chance"]) for h in STREAM_H},
        challenge={str(h): dict(ap=cap[h]["ap"], ci=cap[h]["ci"]) for h in CHAL_H},
        challenge_mAP=cap["mAP"])
    dev_ref = dict(streaming={h: sap[h]["ap"] for h in STREAM_H}, mAP=cap["mAP"]["value"])
    dev_boot = dict(streaming={h: sboot[h] for h in STREAM_H}, mAP=cboot["mAP"])
    print("device reference: mAP %.4f, streaming h0 %.4f" % (dev_ref["mAP"],
                                                             dev_ref["streaming"][0.0]), flush=True)

    # ---------------------------------------------------------------- Part (a): V(d)
    curves = {}
    for arm in CLOUD_ARMS:
        nm = f"{arm[0]}_N{arm[1]}"
        for cad in CADENCES:
            mc = int(round(cad / STEP))
            key = f"always-cloud {nm}@{cad}"
            cur = dict(streaming={h: [] for h in STREAM_H}, mAP=[],
                       boot_streaming={h: [] for h in STREAM_H}, boot_mAP=[])
            for d in DELAYS_S:
                add = int(round(d / STEP))
                streams = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc,
                                              sched[arm]["D"] + add) for c in clips}
                sa, sb = eng.full(streams)
                ca, cb = chal.full(streams)
                res["vd"][f"{key}|d{d}"] = dict(
                    arm=nm, kind="cloud", cadence_s=cad, delay_s=d,
                    base_hold_shift_s=sched[arm]["D"] * STEP,
                    total_hold_shift_s=(sched[arm]["D"] + add) * STEP,
                    streaming={str(h): dict(ap=sa[h]["ap"], ci=sa[h]["ci"],
                                            multiple_of_chance=sa[h]["ap"] / ctx["chance"])
                               for h in STREAM_H},
                    challenge={str(h): dict(ap=ca[h]["ap"], ci=ca[h]["ci"]) for h in CHAL_H},
                    challenge_mAP=ca["mAP"])
                for h in STREAM_H:
                    cur["streaming"][h].append(sa[h]["ap"])
                    cur["boot_streaming"][h].append(sb[h])
                cur["mAP"].append(ca["mAP"]["value"])
                cur["boot_mAP"].append(cb["mAP"])
                print("  V(d) %-28s d=%.2f mAP %.4f  sAP@0 %.4f" %
                      (key, d, ca["mAP"]["value"], sa[0.0]["ap"]), flush=True)
            curves[key] = cur

            # ---- d*, with a bootstrap CI from the paired resamples
            ds = {}
            pt = crossing(DELAYS_S, cur["mAP"], dev_ref["mAP"])
            bsv = []
            for b in range(NB):
                bsv.append(crossing(DELAYS_S, [cur["boot_mAP"][i][b] for i in range(len(DELAYS_S))],
                                    dev_boot["mAP"][b]))
            fin = [x for x in bsv if x is not None]
            ds["challenge_mAP"] = dict(
                d_star_s=pt, exceeds_max_delay=bool(pt is None), max_delay_s=DELAYS_S[-1],
                ci=[float(np.percentile(fin, 2.5)), float(np.percentile(fin, 97.5))] if fin else None,
                n_bootstrap_crossing=len(fin), n_bootstrap=NB,
                device_value=dev_ref["mAP"], cloud_value_at_zero=cur["mAP"][0])
            for h in STREAM_H:
                pth = crossing(DELAYS_S, cur["streaming"][h], dev_ref["streaming"][h])
                bb = [crossing(DELAYS_S, [cur["boot_streaming"][h][i][b]
                                          for i in range(len(DELAYS_S))],
                               dev_boot["streaming"][h][b]) for b in range(NB)]
                ff = [x for x in bb if x is not None]
                ds[f"streaming_h{h}"] = dict(
                    d_star_s=pth, exceeds_max_delay=bool(pth is None), max_delay_s=DELAYS_S[-1],
                    ci=([float(np.percentile(ff, 2.5)), float(np.percentile(ff, 97.5))]
                        if ff else None),
                    n_bootstrap_crossing=len(ff), n_bootstrap=NB,
                    device_value=dev_ref["streaming"][h], cloud_value_at_zero=cur["streaming"][h][0])
            res["dstar"][key] = ds

    # ---------------------------------------------------------------- Part (b): blocking windows
    rng = np.random.default_rng(SEED)
    U = rng.random((N_PLACE, len(clips)))                 # one placement draw per clip, per repeat
    place = {}
    for wi, w in enumerate(WINDOWS_S):
        W = int(round(w / STEP))
        pos = {}
        for p in range(N_PLACE):
            for ci, c in enumerate(clips):
                span = G[c] - W
                assert span >= 0, (c, w)
                j0 = int(np.floor(U[p, ci] * (span + 1)))
                j0 = min(j0, span)
                pos[(p, c)] = (j0, j0 + W - 1)
        place[w] = pos
    res["blocking_placement_rule"] = (
        "window start index uniform on [0, G - W] so the window lies ENTIRELY inside the clip and "
        "every window has exactly length w; 20 placements per clip from one rng(seed 0) draw "
        "shared across arms, modes and window lengths (so the comparison is paired); 0 clips were "
        "too short for any w (min G = %d steps, max W = %d)" % (min(G.values()),
                                                                int(round(max(WINDOWS_S) / STEP))))

    for arm in CLOUD_ARMS:
        nm = f"{arm[0]}_N{arm[1]}"
        cad = CAD_PRIMARY
        mc = int(round(cad / STEP))
        key = f"always-cloud {nm}@{cad}"
        base_s = {h: curves[key]["streaming"][h][0] for h in STREAM_H}
        base_m = curves[key]["mAP"][0]
        base_bs = {h: curves[key]["boot_streaming"][h][0] for h in STREAM_H}
        base_bm = curves[key]["boot_mAP"][0]
        mode_boot = {}
        for mode in MODES:
            for w in WINDOWS_S:
                per = dict(mAP=[], streaming={h: [] for h in STREAM_H})
                acc_bm = np.zeros(NB)
                acc_bs = {h: np.zeros(NB) for h in STREAM_H}
                for p in range(N_PLACE):
                    streams = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"],
                                                  window=place[w][(p, c)], mode=mode,
                                                  dev_seen=dev_seen[c]) for c in clips}
                    sa, sb = eng.full(streams)
                    ca, cb = chal.full(streams)
                    per["mAP"].append(ca["mAP"]["value"])
                    acc_bm += cb["mAP"]
                    for h in STREAM_H:
                        per["streaming"][h].append(sa[h]["ap"])
                        acc_bs[h] += sb[h]
                acc_bm /= N_PLACE
                for h in STREAM_H:
                    acc_bs[h] /= N_PLACE
                dm = base_bm - acc_bm
                cell = dict(
                    arm=nm, cadence_s=cad, mode=mode, window_s=w, n_placements=N_PLACE,
                    baseline_mAP=base_m, baseline_streaming={str(h): base_s[h] for h in STREAM_H},
                    mAP=dict(mean=float(np.mean(per["mAP"])), min=float(np.min(per["mAP"])),
                             max=float(np.max(per["mAP"])),
                             iqr=[float(np.percentile(per["mAP"], 25)),
                                  float(np.percentile(per["mAP"], 75))],
                             per_placement=[float(x) for x in per["mAP"]]),
                    mAP_loss=dict(mean=float(base_m - np.mean(per["mAP"])),
                                  ci=[float(np.percentile(dm, 2.5)),
                                      float(np.percentile(dm, 97.5))],
                                  min=float(base_m - np.max(per["mAP"])),
                                  max=float(base_m - np.min(per["mAP"]))),
                    streaming={}, streaming_loss={})
                for h in STREAM_H:
                    v = per["streaming"][h]
                    dd = base_bs[h] - acc_bs[h]
                    cell["streaming"][str(h)] = dict(
                        mean=float(np.mean(v)), min=float(np.min(v)), max=float(np.max(v)),
                        iqr=[float(np.percentile(v, 25)), float(np.percentile(v, 75))])
                    cell["streaming_loss"][str(h)] = dict(
                        mean=float(base_s[h] - np.mean(v)),
                        ci=[float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))],
                        mean_as_multiple_of_chance=float((base_s[h] - np.mean(v)) / ctx["chance"]))
                mode_boot[(mode, w)] = (acc_bm.copy(), {h: acc_bs[h].copy() for h in STREAM_H})
                res["blocking"][f"{key}|{mode}|w{w}"] = cell
                print("  block %-24s %-8s w=%.2f  mAP loss %.4f  sAP@0 loss %.5f" %
                      (key, mode, w, cell["mAP_loss"]["mean"],
                       cell["streaming_loss"]["0.0"]["mean"]), flush=True)

        # ---- QUEUE vs SUSPEND, paired on the same bootstrap resamples and the same placements
        for w in WINDOWS_S:
            qm, qs = mode_boot[("QUEUE", w)]
            sm, ss = mode_boot[("SUSPEND", w)]
            qc = res["blocking"][f"{key}|QUEUE|w{w}"]
            sc = res["blocking"][f"{key}|SUSPEND|w{w}"]
            dm = qm - sm
            cell = dict(arm=nm, cadence_s=cad, window_s=w,
                        challenge_mAP=dict(
                            queue=qc["mAP"]["mean"], suspend=sc["mAP"]["mean"],
                            queue_minus_suspend=qc["mAP"]["mean"] - sc["mAP"]["mean"],
                            ci=[float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))],
                            queue_better=bool(qc["mAP"]["mean"] > sc["mAP"]["mean"]),
                            ci_excludes_zero=bool(np.percentile(dm, 2.5) > 0
                                                  or np.percentile(dm, 97.5) < 0)),
                        streaming={})
            for h in STREAM_H:
                dd = qs[h] - ss[h]
                qv = qc["streaming"][str(h)]["mean"]
                sv = sc["streaming"][str(h)]["mean"]
                cell["streaming"][str(h)] = dict(
                    queue=qv, suspend=sv, queue_minus_suspend=qv - sv,
                    ci=[float(np.percentile(dd, 2.5)), float(np.percentile(dd, 97.5))],
                    queue_better=bool(qv > sv),
                    ci_excludes_zero=bool(np.percentile(dd, 2.5) > 0
                                          or np.percentile(dd, 97.5) < 0))
            res.setdefault("queue_vs_suspend", {})[f"{key}|w{w}"] = cell

        # ---- convexity
        for mode in MODES:
            conv = {}
            for w, w2 in CONVEX_PAIRS:
                a = res["blocking"][f"{key}|{mode}|w{w}"]
                b2 = res["blocking"][f"{key}|{mode}|w{w2}"]
                row = {}
                for lab, la, lb in (("challenge_mAP", a["mAP_loss"]["mean"],
                                     b2["mAP_loss"]["mean"]),) + tuple(
                        (f"streaming_h{h}", a["streaming_loss"][str(h)]["mean"],
                         b2["streaming_loss"][str(h)]["mean"]) for h in STREAM_H):
                    row[lab] = dict(loss_w=la, loss_2w=lb, two_times_loss_w=2.0 * la,
                                    ratio=(lb / la if la != 0 else None),
                                    convex=bool(lb > 2.0 * la), concave=bool(lb < 2.0 * la))
                conv[f"w{w}->{w2}"] = row
            res["convexity"][f"{key}|{mode}"] = conv

    # ---------------------------------------------------------------- controls
    s1 = json.loads((ROOT / "results/dashcam/study_e9b/e9b_study1_results.json").read_text())
    s2 = json.loads((ROOT / "results/dashcam/study_e9c/e9c_results.json").read_text())
    rows, worst_s, worst_c = [], 0.0, 0.0

    def row(q, a, b2, src, bucket):
        nonlocal worst_s, worst_c
        d = abs(a - b2)
        rows.append(dict(quantity=q, prior=a, mine=b2, abs_diff=d, source=src, bucket=bucket))
        if bucket == "streaming":
            worst_s = max(worst_s, d)
        else:
            worst_c = max(worst_c, d)

    for arm in CLOUD_ARMS:
        nm = f"{arm[0]}_N{arm[1]}"
        mc = int(round(CAD_PRIMARY / STEP))
        for cad in CADENCES:
            k9 = f"always-cloud/{nm}|{SETTING}|cad{int(round(cad * 100))}|far5"
            mine = res["vd"][f"always-cloud {nm}@{cad}|d0.0"]
            for h in STREAM_H:
                pr = s1["baselines"][k9]["ap"][str(h)]
                row(f"streaming AP {nm}@{cad} h={h}", pr["ap"], mine["streaming"][str(h)]["ap"],
                    "StudyE9b e9b_study1_results.json", "streaming")
                row(f"streaming AP CI lo {nm}@{cad} h={h}", pr["ci"][0],
                    mine["streaming"][str(h)]["ci"][0], "StudyE9b", "streaming")
                row(f"streaming AP CI hi {nm}@{cad} h={h}", pr["ci"][1],
                    mine["streaming"][str(h)]["ci"][1], "StudyE9b", "streaming")
        # challenge: recomputed with scikit-learn itself, the function StudyE9c used, so that the
        # comparison is bit-level and not a comparison of two AP implementations (control (d)).
        streams0 = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"])
                    for c in clips}
        sk = chal.point(streams0, ap=average_precision_score)
        cell = s2["arms"][f"always-cloud {nm}|{SETTING}"]
        row(f"challenge mAP {nm}", cell["mAP"]["value"], sk["mAP"], "StudyE9c e9c_results.json",
            "challenge")
        for h in CHAL_H:
            row(f"challenge AP {nm} h={h}", cell["ap"][str(h)]["ap"], sk[h], "StudyE9c",
                "challenge")
    dk = f"device-only|{SETTING}|far5"
    for h in STREAM_H:
        pr = s1["baselines"][dk]["ap"][str(h)]
        d9 = res["vd"]["device-only 4BI_N1"]["streaming"][str(h)]
        row(f"streaming AP device h={h}", pr["ap"], d9["ap"], "StudyE9b", "streaming")
        row(f"streaming AP CI lo device h={h}", pr["ci"][0], d9["ci"][0], "StudyE9b", "streaming")
        row(f"streaming AP CI hi device h={h}", pr["ci"][1], d9["ci"][1], "StudyE9b", "streaming")
    devc = s2["arms"][f"device-only 4BI_N1|{SETTING}"]
    skd = chal.point(dev_seen, ap=average_precision_score)
    row("challenge mAP device", devc["mAP"]["value"], skd["mAP"], "StudyE9c", "challenge")
    for h in CHAL_H:
        row(f"challenge AP device h={h}", devc["ap"][str(h)]["ap"], skd[h], "StudyE9c",
            "challenge")
    worst = max(worst_s, worst_c)
    res["controls"]["a_zero_delay_reproduces_e9b_and_e9c"] = dict(
        description="At d = 0 this engine must reproduce StudyE9b's streaming AP (point AND CI) "
                    "and StudyE9c's challenge AP / mAP for the same arms, setting and cadence. A "
                    "failure is a STOP condition. The streaming cells use StudyE9b's own AP code "
                    "and must agree BIT FOR BIT; the challenge cells are recomputed here with "
                    "scikit-learn, the function StudyE9c used, so they must agree bit for bit too "
                    "(control (d) separately licenses the vectorised AP used inside the "
                    "bootstrap).",
        cells=len(rows), worst_abs_diff=worst,
        worst_abs_diff_streaming=worst_s, worst_abs_diff_challenge=worst_c,
        exact=bool(worst == 0.0), rows=rows)

    # control (b): w = 0 must reproduce d = 0
    wb = []
    for arm in CLOUD_ARMS:
        nm = f"{arm[0]}_N{arm[1]}"
        mc = int(round(CAD_PRIMARY / STEP))
        for mode in MODES:
            streams = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"],
                                          window=(5, 4), mode=mode, dev_seen=dev_seen[c])
                       for c in clips}
            ref = {c: B.held_stream(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"]) for c in clips}
            bad = sum(int(np.sum(streams[c] != ref[c])) for c in clips)
            wb.append(dict(arm=nm, mode=mode, empty_window="(5, 4), i.e. zero steps",
                           grid_points_differing=bad))
    res["controls"]["b_empty_window_reproduces_zero_delay"] = dict(
        description="An EMPTY window (j1 < j0, zero steps long) must leave the delivered stream "
                    "identical to StudyE9b's held_stream at the same cadence and shift.",
        cells=wb, all_equal=bool(all(x["grid_points_differing"] == 0 for x in wb)))

    # control (c): SUSPEND over the whole clip must equal the device arm exactly
    cc = []
    for arm in CLOUD_ARMS:
        nm = f"{arm[0]}_N{arm[1]}"
        mc = int(round(CAD_PRIMARY / STEP))
        streams = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"],
                                      window=(0, G[c] - 1), mode="SUSPEND",
                                      dev_seen=dev_seen[c]) for c in clips}
        bad = sum(int(np.sum(streams[c] != dev_seen[c])) for c in clips)
        sa, _ = eng.full(streams)
        ca, _ = chal.full(streams)
        cc.append(dict(arm=nm, grid_points_differing=bad,
                       streaming_ap_h0=sa[0.0]["ap"], device_streaming_ap_h0=dev_ref["streaming"][0.0],
                       challenge_mAP=ca["mAP"]["value"], device_challenge_mAP=dev_ref["mAP"],
                       equal=bool(bad == 0 and sa[0.0]["ap"] == dev_ref["streaming"][0.0]
                                  and ca["mAP"]["value"] == dev_ref["mAP"])))
    res["controls"]["c_full_clip_suspend_equals_device"] = dict(
        description="SUSPEND with a window covering every grid index must deliver exactly the "
                    "device's own stream, so both metrics must equal the device arm's.",
        cells=cc, all_equal=bool(all(x["equal"] for x in cc)))

    # control (d): the vectorised AP equals scikit-learn's on every real cell
    nck, nbad, wd = 0, 0, 0.0
    for key, cell in list(res["vd"].items()):
        if cell["kind"] == "device":
            streams = dev_seen
        else:
            arm = ("32BI", int(cell["arm"].split("_N")[1]))
            add = int(round(cell["delay_s"] / STEP))
            mc = int(round(cell["cadence_s"] / STEP))
            streams = {c: cloud_delivered(ctx["arrs"][arm][c], G[c], mc, sched[arm]["D"] + add)
                       for c in clips}
        mine = chal.point(streams, ap=ap_fast)
        ref = chal.point(streams, ap=average_precision_score)
        for h in CHAL_H:
            nck += 1
            dd = abs(mine[h] - ref[h])
            wd = max(wd, dd)
            if dd > 1e-12:
                nbad += 1
    res["controls"]["d_vectorised_ap_equals_sklearn"] = dict(
        description="The AP used inside the bootstrap must equal sklearn.metrics."
                    "average_precision_score on every real cell, including its tie handling.",
        cells_checked=nck, mismatches=nbad, worst_abs_diff=wd,
        tolerance=1e-12, equal_within_tolerance=bool(nbad == 0),
        note="the two differ only in floating-point summation order; the worst difference is "
             "reported so the reader can see its size rather than take 'equal' on trust")

    res["_provenance"] = stamp(script="study_e9d_delay.py", model=None, device="cpu",
                               n=len(clips), args=None)
    (OUT / "e9d_results.json").write_text(json.dumps(res, indent=1, default=float))

    # ---------------------------------------------------------------- machine-readable tables
    with (OUT / "e9d_vd_curves.csv").open("w") as f:
        f.write("arm,kind,cadence_s,added_delay_s,total_hold_shift_s,challenge_mAP,"
                "challenge_mAP_lo,challenge_mAP_hi," +
                ",".join(f"streaming_ap_h{h}" for h in STREAM_H) + "\n")
        for key, c in res["vd"].items():
            f.write("%s,%s,%s,%s,%s,%.6f,%.6f,%.6f,%s\n" % (
                c["arm"], c["kind"], c["cadence_s"], c["delay_s"],
                c.get("total_hold_shift_s", c.get("hold_shift_s", "")),
                c["challenge_mAP"]["value"], c["challenge_mAP"]["ci"][0],
                c["challenge_mAP"]["ci"][1],
                ",".join("%.6f" % c["streaming"][str(h)]["ap"] for h in STREAM_H)))
    with (OUT / "e9d_dstar.csv").open("w") as f:
        f.write("arm,cadence_s,metric,device_value,cloud_value_at_zero,d_star_s,ci_lo,ci_hi,"
                "exceeds_max_delay\n")
        for key, ds in res["dstar"].items():
            arm = key.split()[1].split("@")[0]
            cad = key.split("@")[1]
            for metric, v in ds.items():
                ci = v["ci"] or [None, None]
                f.write("%s,%s,%s,%.6f,%.6f,%s,%s,%s,%s\n" % (
                    arm, cad, metric, v["device_value"], v["cloud_value_at_zero"],
                    v["d_star_s"], ci[0], ci[1], v["exceeds_max_delay"]))
    with (OUT / "e9d_blocking_loss.csv").open("w") as f:
        f.write("arm,cadence_s,mode,window_s,baseline_challenge_mAP,challenge_mAP_loss,"
                "challenge_mAP_loss_ci_lo,challenge_mAP_loss_ci_hi," +
                ",".join(f"streaming_h{h}_loss" for h in STREAM_H) + "\n")
        for key, c in res["blocking"].items():
            f.write("%s,%s,%s,%s,%.6f,%.6f,%.6f,%.6f,%s\n" % (
                c["arm"], c["cadence_s"], c["mode"], c["window_s"], c["baseline_mAP"],
                c["mAP_loss"]["mean"], c["mAP_loss"]["ci"][0], c["mAP_loss"]["ci"][1],
                ",".join("%.6f" % c["streaming_loss"][str(h)]["mean"] for h in STREAM_H)))
    print("\nwrote", OUT / "e9d_results.json")
    print("control (a) worst abs diff:", worst)
    print("control (d) mismatches:", nbad, "of", nck)


if __name__ == "__main__":
    main()
