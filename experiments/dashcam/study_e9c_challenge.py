#!/usr/bin/env python3
"""StudyE9c-challenge-metric — the Nexar challenge's own evaluation metric, computed on our
validation clips.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
StudyD14b's committed 0.25-s trace; every latency is read from a committed StudyD4 / D7 / D7b / D8
measurement, through study_e9b_dense.py.

The project's streaming "Nexar AP" (StudyE5 Part G, StudyE9, StudyE9b) scores EVERY decision point
of every negative clip as a negative. The Nexar challenge (arXiv 2503.03848) scores ONE crop per
video, with roughly balanced classes, at horizons 0.5 / 1.0 / 1.5 s, and reports the unweighted
mean of the three per-horizon APs. This script computes the latter. Neither metric replaces the
other; both are reported, under their own names.
"""
import gzip, json, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402
import study_e9_episodes as E9  # noqa: E402
import study_e9b_dense as B  # noqa: E402
from sklearn.metrics import average_precision_score  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9c"
E9B = ROOT / "results/dashcam/study_e9b/e9b_study1_results.json"
SEED, NB = B.SEED, B.NB
STEP = B.STEP_DENSE
HORIZONS = (0.5, 1.0, 1.5)
MIN_CROP_S = 3.0 + 1.5          # so that fake_event - 1.5 s is on the grid
N_FAKE_SEEDS = 20
CADENCE = 0.5
FAR = 0.05                      # StudyE9b's primary alarm FPR (escalation only; AP is
                                # threshold-independent for the always-on arms)
TRIGGERS = (0.10, 0.20)
SETTINGS = ("measured@25", "measured@75")
ZERO_ARMS = [("4BI", 1), ("32BI", 1), ("32BI", 3), ("4BI", 3)]


def read_clip_meta():
    """time_of_alert and duration per clip, from one arm of the committed trace."""
    m = {}
    for ln in gzip.open(B.TRACE, "rt"):
        r = json.loads(ln)
        if r["model"] != "4BI" or int(r["n"]) != 1:
            continue
        c = r["file_name"]
        if c not in m:
            m[c] = dict(label=r["label"], duration=float(r["duration_s"]),
                        event=(None if r["time_of_event"] is None else float(r["time_of_event"])),
                        alert=(None if r["time_of_alert"] is None else float(r["time_of_alert"])))
    return m


def crop_index(meta, c, t_abs):
    """The grid point nearest an absolute time, clamped to the clip (StudyE9b's rule)."""
    ia = int(round(t_abs / STEP)) - int(round(B.T0 / STEP))
    return int(min(max(ia, 0), meta[c]["G"] - 1))


def fake_event_times(cm, neg_clips, sigma, seed):
    rng = np.random.default_rng(seed)
    out = {}
    for c in neg_clips:
        dur = cm[c]["duration"]
        t = dur / 2.0 + rng.normal(0.0, sigma)
        out[c] = float(min(max(t, MIN_CROP_S), dur))
    return out


def ap_sklearn(pos_scores, neg_scores):
    y = np.concatenate([np.ones(len(pos_scores)), np.zeros(len(neg_scores))])
    s = np.concatenate([pos_scores, neg_scores])
    return float(average_precision_score(y, s))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = B.build(step=STEP, horizons=B.HORIZONS_DENSE)
    meta, clips, tau, fold = ctx["meta"], ctx["clips"], ctx["tau"], ctx["fold"]
    pos_clips, neg_clips = ctx["pos"], ctx["neg"]
    cm = read_clip_meta()
    assert set(cm) == set(clips)

    # ---- sigma for the fake event times, from the positive clips
    devs = np.array([cm[c]["event"] - cm[c]["duration"] / 2.0 for c in pos_clips])
    sigma = float(devs.std(ddof=1))
    sigma_pop = float(devs.std(ddof=0))

    # ---- which horizons each positive clip contributes, per the paper's alert rule
    incl = {}
    for c in pos_clips:
        gap = cm[c]["event"] - cm[c]["alert"]
        incl[c] = tuple(h for h in HORIZONS if h <= 0.5 or gap > h)
    n_incl = {h: sum(1 for c in pos_clips if h in incl[c]) for h in HORIZONS}

    # ---- crop indices
    pos_idx = {(c, h): B.target_index(meta, c, h, STEP) for c in pos_clips for h in incl[c]}
    pos_tgt = {(c, h): cm[c]["event"] - h for c in pos_clips for h in incl[c]}
    fakes = {sd: fake_event_times(cm, neg_clips, sigma, sd) for sd in range(N_FAKE_SEEDS)}
    neg_idx = {sd: {(c, h): crop_index(meta, c, fakes[sd][c] - h)
                    for c in neg_clips for h in HORIZONS} for sd in range(N_FAKE_SEEDS)}

    res = dict(
        label="StudyE9c-challenge-metric: the Nexar challenge's own evaluation metric "
              "(arXiv 2503.03848) computed on StudyD14b's 300 validation clips. OFFLINE ANALYSIS "
              "OF COMMITTED RESULTS; CPU only on flash; no GPU, no model server, no inference. "
              "Scores are continuous log P(Yes); no literal Yes/No answer is used anywhere. These "
              "are NOT the challenge's test clips, so the numbers are NOT leaderboard-comparable.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, step_s=STEP,
        horizons=list(HORIZONS), cadence_s=CADENCE, alarm_fpr_for_escalation=FAR,
        n_clips=dict(positive=len(pos_clips), negative=len(neg_clips)),
        sigma_fake_event_s=sigma, sigma_fake_event_s_population=sigma_pop,
        sigma_note="the paper does not state the noise scale; sigma is the sample standard "
                   "deviation (ddof=1) of (time_of_event - duration/2) over the 150 positive "
                   "clips, as pre-registered",
        min_crop_time_s=MIN_CROP_S, n_fake_seeds=N_FAKE_SEEDS,
        horizon_inclusion_rule="h = 0.5 s always; h > 0.5 s only if time_of_event - "
                               "time_of_alert > h (the paper's rule)",
        n_positive_by_horizon={h: n_incl[h] for h in HORIZONS},
        base_rate_by_horizon={h: n_incl[h] / (n_incl[h] + len(neg_clips)) for h in HORIZONS},
        simplification="the paper also assigns negative clips fake ALERT times to match the "
                       "positive distribution; this study does not, so all 150 negatives enter "
                       "every horizon",
        arms={}, paired={}, controls={}, fake_time_sensitivity={}, side_by_side={})

    # ---- shared clip bootstrap, identical in construction to StudyE9b's
    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos_clips), len(pos_clips)),
              rng.integers(0, len(neg_clips), len(neg_clips))) for _ in range(NB)]

    def score_arm(streams, sd=0):
        """Per-horizon crop scores for one arm: (positives dict, negatives dict)."""
        P = {h: np.array([streams[c][pos_idx[(c, h)]] for c in pos_clips if h in incl[c]])
             for h in HORIZONS}
        N = {h: np.array([streams[c][neg_idx[sd][(c, h)]] for c in neg_clips])
             for h in HORIZONS}
        return P, N

    def evaluate(streams, sd=0, with_ci=True):
        P, N = score_arm(streams, sd)
        ap = {h: ap_sklearn(P[h], N[h]) for h in HORIZONS}
        out = dict(ap={h: dict(ap=ap[h], ci=None) for h in HORIZONS},
                   mAP=dict(value=float(np.mean([ap[h] for h in HORIZONS])), ci=None),
                   n_missing_crops=int(sum(int((P[h] <= B.MISSING / 2).sum()
                                               + (N[h] <= B.MISSING / 2).sum())
                                           for h in HORIZONS)))
        if not with_ci:
            return out, None
        pmask = {h: np.array([h in incl[c] for c in pos_clips]) for h in HORIZONS}
        pfull = {h: np.array([streams[c][pos_idx[(c, h)]] if h in incl[c] else np.nan
                              for c in pos_clips]) for h in HORIZONS}
        bs = np.empty((len(HORIZONS), NB))
        bm = np.empty(NB)
        for b, (pi, ni) in enumerate(boots):
            vals = []
            for k, h in enumerate(HORIZONS):
                sel = pi[pmask[h][pi]]
                a = ap_sklearn(pfull[h][sel], N[h][ni]) if len(sel) else 0.0
                bs[k, b] = a
                vals.append(a)
            bm[b] = float(np.mean(vals))
        for k, h in enumerate(HORIZONS):
            out["ap"][h]["ci"] = [float(np.percentile(bs[k], 2.5)),
                                  float(np.percentile(bs[k], 97.5))]
        out["mAP"]["ci"] = [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))]
        return out, dict(ap=bs, mAP=bm)

    # ---- arms -------------------------------------------------------------
    boot_store = {}

    def add(name, streams, setting, sd=0):
        o, bt = evaluate(streams, sd)
        o.update(arm=name, setting=setting)
        res["arms"][f"{name}|{setting}"] = o
        boot_store[f"{name}|{setting}"] = bt
        print("  scored", name, setting, flush=True)

    raw = {arm: {c: ctx["arrs"][arm][c] for c in clips} for arm in ZERO_ARMS}
    for arm in ZERO_ARMS:
        nm = f"{arm[0]}_N{arm[1]}" + (" (SECONDARY)" if arm == ("4BI", 3) else "")
        add(nm, raw[arm], "zero")

    mc = int(round(CADENCE / STEP))
    for st in SETTINGS:
        seen, mdev, Ddev, Ld = B.dev_seen_all(ctx, st)
        add("device-only 4BI_N1", seen, st)
        for arm in [("32BI", 1), ("32BI", 3)]:
            _d, Lc = B.latencies(st, *arm)
            Dc = B.steps_ceil(Lc, STEP)
            add(f"always-cloud {arm[0]}_N{arm[1]}",
                {c: B.held_stream(ctx["arrs"][arm][c], meta[c]["G"], mc, Dc) for c in clips}, st)
        for trig in TRIGGERS:
            r = B.run_escalation(ctx, "32BI", 1, st, CADENCE, FAR, trig,
                                 B.PRIMARY["k"], B.PRIMARY["q"], B.PRIMARY["lmax"],
                                 B.PRIMARY["c"])
            add(f"escalation-32B 32BI_N1 trig{int(trig*100)}", r["streams"], st)

    # ---- paired differences ----------------------------------------------
    def paired(a_key, b_key):
        ba, bb = boot_store[a_key], boot_store[b_key]
        if ba is None or bb is None:
            return None
        d = dict(horizons={})
        for k, h in enumerate(HORIZONS):
            diff = ba["ap"][k] - bb["ap"][k]
            d["horizons"][h] = dict(
                diff=res["arms"][a_key]["ap"][h]["ap"] - res["arms"][b_key]["ap"][h]["ap"],
                ci=[float(np.percentile(diff, 2.5)), float(np.percentile(diff, 97.5))])
        dm = ba["mAP"] - bb["mAP"]
        d["mAP"] = dict(diff=res["arms"][a_key]["mAP"]["value"] - res["arms"][b_key]["mAP"]["value"],
                        ci=[float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))])
        return d

    res["paired"]["32BI_N1 - 4BI_N1|zero"] = paired("32BI_N1|zero", "4BI_N1|zero")
    res["paired"]["32BI_N3 - 4BI_N3|zero"] = paired("32BI_N3|zero", "4BI_N3 (SECONDARY)|zero")
    for st in SETTINGS:
        res["paired"][f"always-cloud 32BI_N1 - device-only|{st}"] = paired(
            f"always-cloud 32BI_N1|{st}", f"device-only 4BI_N1|{st}")
        res["paired"][f"always-cloud 32BI_N3 - device-only|{st}"] = paired(
            f"always-cloud 32BI_N3|{st}", f"device-only 4BI_N1|{st}")
        for trig in TRIGGERS:
            res["paired"][f"escalation trig{int(trig*100)} - device-only|{st}"] = paired(
                f"escalation-32B 32BI_N1 trig{int(trig*100)}|{st}", f"device-only 4BI_N1|{st}")

    # ---- fake-time sensitivity (20 seeds) ---------------------------------
    for key, streams in (("32BI_N1|zero", raw[("32BI", 1)]), ("4BI_N1|zero", raw[("4BI", 1)])):
        vals = {h: [] for h in HORIZONS}
        maps = []
        for sd in range(N_FAKE_SEEDS):
            o, _ = evaluate(streams, sd, with_ci=False)
            for h in HORIZONS:
                vals[h].append(o["ap"][h]["ap"])
            maps.append(o["mAP"]["value"])
        res["fake_time_sensitivity"][key] = dict(
            ap_mean={h: float(np.mean(vals[h])) for h in HORIZONS},
            ap_min={h: float(np.min(vals[h])) for h in HORIZONS},
            ap_max={h: float(np.max(vals[h])) for h in HORIZONS},
            mAP_mean=float(np.mean(maps)), mAP_min=float(np.min(maps)),
            mAP_max=float(np.max(maps)), n_seeds=N_FAKE_SEEDS)
    st_dev = B.dev_seen_all(ctx, "measured@25")[0]
    vals = {h: [] for h in HORIZONS}
    maps = []
    for sd in range(N_FAKE_SEEDS):
        o, _ = evaluate(st_dev, sd, with_ci=False)
        for h in HORIZONS:
            vals[h].append(o["ap"][h]["ap"])
        maps.append(o["mAP"]["value"])
    res["fake_time_sensitivity"]["device-only 4BI_N1|measured@25"] = dict(
        ap_mean={h: float(np.mean(vals[h])) for h in HORIZONS},
        ap_min={h: float(np.min(vals[h])) for h in HORIZONS},
        ap_max={h: float(np.max(vals[h])) for h in HORIZONS},
        mAP_mean=float(np.mean(maps)), mAP_min=float(np.min(maps)),
        mAP_max=float(np.max(maps)), n_seeds=N_FAKE_SEEDS)

    # ---- control (a): zero-latency crops equal the committed trace exactly
    nck, nbad, worst_dt = 0, 0, 0.0
    for arm in ZERO_ARMS:
        for c in pos_clips:
            for h in incl[c]:
                i = pos_idx[(c, h)]
                nck += 1
                if raw[arm][c][i] != ctx["arrs"][arm][c][i]:
                    nbad += 1
                worst_dt = max(worst_dt, abs(B.T0 + i * STEP - pos_tgt[(c, h)]))
        for c in neg_clips:
            for h in HORIZONS:
                i = neg_idx[0][(c, h)]
                nck += 1
                if raw[arm][c][i] != ctx["arrs"][arm][c][i]:
                    nbad += 1
    nclamp = sum(1 for c in neg_clips for h in HORIZONS
                 if neg_idx[0][(c, h)] in (0, meta[c]["G"] - 1))
    res["controls"]["a_zero_latency_crops_equal_trace"] = dict(
        description="Every zero-latency crop score must be the committed StudyD14b trace value at "
                    "that grid point, and every positive crop must sit within half a grid step of "
                    "time_of_event - h.",
        crops_checked=nck, mismatches=nbad, all_equal=bool(nbad == 0),
        worst_abs_grid_offset_s=worst_dt, half_step_s=STEP / 2.0,
        within_half_step=bool(worst_dt <= STEP / 2.0 + 1e-12),
        negative_crops_clamped_to_clip_end=nclamp)

    # ---- control (b): shuffled labels must give mAP near the base rate
    shuf = {}
    for key, streams in (("32BI_N1|zero", raw[("32BI", 1)]),
                         ("device-only 4BI_N1|measured@25", st_dev)):
        P, N = score_arm(streams, 0)
        vals = []
        for sd in range(N_FAKE_SEEDS):
            rr = np.random.default_rng([SEED, sd])
            aps = []
            for h in HORIZONS:
                s = np.concatenate([P[h], N[h]])
                y = np.concatenate([np.ones(len(P[h])), np.zeros(len(N[h]))])
                aps.append(float(average_precision_score(rr.permutation(y), s)))
            vals.append(float(np.mean(aps)))
        br = float(np.mean([res["base_rate_by_horizon"][h] for h in HORIZONS]))
        shuf[key] = dict(mAP_mean=float(np.mean(vals)), mAP_min=float(np.min(vals)),
                         mAP_max=float(np.max(vals)), mean_base_rate=br,
                         ratio_to_base_rate=float(np.mean(vals)) / br, n_shuffles=N_FAKE_SEEDS)
    res["controls"]["b_label_shuffle_gives_base_rate"] = dict(
        description="Permuting the labels across the pooled crops of each horizon must drive mAP "
                    "to the mean base rate.", cells=shuf)

    # ---- side by side with StudyE9b's streaming AP ------------------------
    s1 = json.loads(E9B.read_text())
    sb = {}
    pairs = [("4BI_N1|zero", f"always-cloud/4BI_N1|zero|cad{int(CADENCE*100)}|far5", "baselines"),
             ("32BI_N1|zero", f"always-cloud/32BI_N1|zero|cad{int(CADENCE*100)}|far5", "baselines"),
             ("32BI_N3|zero", f"always-cloud/32BI_N3|zero|cad{int(CADENCE*100)}|far5", "baselines")]
    for st in SETTINGS:
        pairs += [(f"device-only 4BI_N1|{st}", f"device-only|{st}|far5", "baselines"),
                  (f"always-cloud 32BI_N1|{st}",
                   f"always-cloud/32BI_N1|{st}|cad{int(CADENCE*100)}|far5", "baselines"),
                  (f"always-cloud 32BI_N3|{st}",
                   f"always-cloud/32BI_N3|{st}|cad{int(CADENCE*100)}|far5", "baselines")]
    for mine, theirs, _grp in pairs:
        if mine not in res["arms"] or theirs not in s1["baselines"]:
            continue
        sb[mine] = dict(
            challenge={h: res["arms"][mine]["ap"][h]["ap"] for h in HORIZONS},
            challenge_mAP=res["arms"][mine]["mAP"]["value"],
            streaming={h: s1["baselines"][theirs]["ap"][str(h)]["ap"] for h in HORIZONS},
            streaming_key=theirs)
    res["side_by_side"] = dict(
        note="LEFT: this study's challenge metric (one crop per clip, roughly balanced, chance "
             "about %.3f). RIGHT: StudyE9b's streaming per-decision AP (every negative grid point "
             "a negative, chance %.5f). The two are NOT comparable in level; only the ORDERING of "
             "arms and the SIGN of differences may be compared."
             % (float(np.mean([res["base_rate_by_horizon"][h] for h in HORIZONS])),
                s1["chance_rate"]),
        streaming_chance=s1["chance_rate"], cells=sb)

    res["_provenance"] = stamp(script="study_e9c_challenge.py", model=None, device="cpu",
                               n=len(clips), args=None)
    (OUT / "e9c_results.json").write_text(json.dumps(res, indent=1, default=float))
    print("arms:", len(res["arms"]), "paired:", len(res["paired"]))


if __name__ == "__main__":
    main()
