#!/usr/bin/env python3
"""StudyE9b-dense Study 2 — StudyE12's admission study re-run on StudyD14b's 0.25-s grid with the
explicit delivery model of study_e9b_dense.py instead of d = ceil(latency).

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
StudyD14b's committed trace; every latency and byte count is read from a committed StudyD4 / D7 /
D7b / D8 measurement, through study_e9_episodes.py.

Evaluation is the Nexar metric: AP at fixed horizons on CONTINUOUS scores (log P(Yes)). No literal
Yes/No answer is used anywhere. The per-episode utility is a TRAINING target for the admission
ranking only and is never an evaluation metric. With step = 1 s, 1-s cadences and delivery mode
"ceil" this code must reproduce StudyE12's committed numbers exactly (control (a)).
"""
import json, sys, zlib
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402
import study_e9_episodes as E9  # noqa: E402
import study_e9b_dense as B  # noqa: E402
from sklearn.linear_model import LogisticRegression, PoissonRegressor  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9b"
SEED, NB, NFOLD = E9.SEED, E9.NB, E9.NFOLD
MISSING = B.MISSING
T0 = B.T0
DEVICE = B.DEVICE
PRIMARY = dict(k=2, q=0.75, lmax=10, c=0)
RESOLVERS = [("32BI", 1), ("32BI", 3)]
BUDGETS = (0.25, 0.50, 0.75)
CONTROL_BUDGET = 1.0
ALARM_FPR = (0.01, 0.05, 0.10)
TRIG_RATE = (0.10, 0.20)
LAT = ("measured@25", "zero")
CADENCE = 0.5
H_STAR = 0.5
REESC_WINDOW_S = 10
N_RANDOM_SEEDS = 20
RULE_HORIZONS = (0.25, 0.5)
POLICIES = ["admit-none", "P-random", "P-score", "P-trajectory", "P-trajectory-work",
            "P-oracle", "admit-all"]
JIT = 1e-9
WINDOWS_S = (3, 5)
FEATNAMES = (["dev_score_t"]
             + [f"{s}_{w}s" for w in WINDOWS_S for s in ("mean", "max", "slope", "std")]
             + ["n_prior_triggers", "n_prior_alarm", "n_prior_dismiss", "n_prior_cap", "d_cloud"])


def tie_label(i, step):
    """The tiebreak key must be StudyE12's own key when step = 1 s, so the CRC32 draw and therefore
    every fitted cutoff reproduce exactly. 'g' renders 7.0 as '7' and 4.25 as '4.25'."""
    return format(T0 + i * step, "g")


def tiebreak(clip, key):
    """Deterministic uniform in [0,1) per (clip, trigger grid point), stable across processes.
    The benefit label is discrete (mostly exactly 0), so without a tiebreak a quantile cutoff
    admits every trigger at or above 0 and the budget is not enforced. The same draw is used when
    fitting the cutoff and when deciding, so the two agree exactly."""
    h = zlib.crc32(f"{SEED}|{clip}|{key}".encode())
    return (h % (1 << 30)) / float(1 << 30)


def window_feats(seen, i, w):
    """seen[j] is the device score the application carries at grid point j (already delivered).
    The window is the w grid points up to and including i; only points with a score are used.
    The slope is per grid point, as in StudyE12."""
    lo = max(0, i - w + 1)
    v = seen[lo:i + 1]
    v = v[v > MISSING / 2.0]
    if len(v) == 0:
        return [0.0, 0.0, 0.0, 0.0]
    x = np.arange(len(v), dtype=float)
    sl = 0.0
    if len(v) >= 2 and x.std() > 0:
        sl = float(np.polyfit(x, v, 1)[0])
    return [float(v.mean()), float(v.max()), sl, float(v.std())]


def trigger_features(seen, i, prior, d_cloud_s, wsteps):
    return ([float(seen[i]) if seen[i] > MISSING / 2.0 else 0.0]
            + window_feats(seen, i, wsteps[0]) + window_feats(seen, i, wsteps[1])
            + [float(prior["n"]), float(prior["alarm"]), float(prior["dismiss"]),
               float(prior["cap"]), float(d_cloud_s)])


def rollout(dev, seen, res, G, i0, th_a, th_d, k, lmax_steps, mdev, Ddev, mc, Dc, admit):
    """Run ONE episode opened at grid point i0 to its close, in isolation. `admit` picks the cloud
    resolver (called every mc steps, each answer readable Dc steps later) or the device's own
    delivered score (a new one every mdev steps, no cloud work)."""
    drun, alarms, inv = 0, [], 0
    prev_above = None
    next_call, pending, held = (i0 if admit else None), {}, None
    for i in range(i0, G):
        if admit and i == next_call:
            inv += 1
            pending[i + Dc] = i
            next_call = i + mc
        out = None
        fresh = None
        if admit:
            if i in pending:
                fresh = float(res[pending.pop(i)])
        else:
            if i >= Ddev and (i - Ddev) % mdev == 0 and seen[i] > MISSING / 2.0:
                fresh = float(seen[i])
        if fresh is not None:
            held = fresh
            above = fresh >= th_a
            if above and prev_above is not True:
                alarms.append(i)
            prev_above = above
            if above:
                out = "alarm"
            else:
                drun = drun + 1 if fresh < th_d else 0
                if drun >= k:
                    out = "dismiss"
        if out is None and (i - i0 + 1) >= lmax_steps:
            out = "cap"
        if out is None and i == G - 1:
            out = "clip_end"
        if out is not None:
            return dict(outcome=out, i_close=i, alarm_i=(alarms[0] if alarms else None),
                        invocations=inv, alarms=alarms)
    return dict(outcome="clip_end", i_close=G - 1, alarm_i=(alarms[0] if alarms else None),
                invocations=inv, alarms=alarms)


def episode_utility(ep, label, event, lam, step):
    """U = 1[alarm on a positive clip at least h* before the event] - lam * (false alarms)."""
    hit = 0.0
    if (label == "positive" and ep["alarm_i"] is not None
            and T0 + ep["alarm_i"] * step <= event - H_STAR):
        hit = 1.0
    fa = len(ep["alarms"]) if label == "negative" else 0
    return hit - lam * fa, hit, fa


def run_clip(clip, dev, seen, res, G, step, th_a_cloud, th_d_cloud, th_a_dev, th_d_dev, t_trig,
             k, lmax_steps, cool_steps, mdev, Ddev, mc, Dc, d_cloud_s, wsteps, decide):
    """Whole-clip replay with an admission decision at every trigger. `decide(i, prior, seen)`
    returns True to admit. The application's stream carries the resolver's held score inside an
    admitted open episode and the device's held score otherwise."""
    stream = np.full(G, MISSING)
    episodes, inv_total, alarms_all, trig_rows = [], 0, [], []
    prior = dict(n=0, alarm=0, dismiss=0, cap=0)
    open_, i0, drun, cool_at, adm = False, None, 0, -10 ** 9, False
    prev_above = None
    next_call, pending, held = None, {}, None
    ep_inv = 0
    for i in range(G):
        if not open_ and i >= cool_at:
            if seen[i] > MISSING / 2.0 and seen[i] >= t_trig:
                adm = bool(decide(i, dict(prior), seen))
                open_, i0, drun, ep_inv = True, i, 0, 0
                prev_above, held, pending = None, None, {}
                next_call = i if adm else None
                trig_rows.append(dict(i=i, admitted=adm,
                                      features=trigger_features(seen, i, prior, d_cloud_s, wsteps)))
                prior["n"] += 1
        th_a = th_a_cloud if adm else th_a_dev
        th_d = th_d_cloud if adm else th_d_dev
        if open_ and adm and i == next_call:
            inv_total += 1
            ep_inv += 1
            pending[i + Dc] = i
            next_call = i + mc
        out, fresh = None, None
        if open_:
            if adm:
                if i in pending:
                    fresh = float(res[pending.pop(i)])
            else:
                if i >= Ddev and (i - Ddev) % mdev == 0 and seen[i] > MISSING / 2.0:
                    fresh = float(seen[i])
            if fresh is not None:
                held = fresh
                above = fresh >= th_a
                if above and prev_above is not True:
                    alarms_all.append(i)
                prev_above = above
                if above:
                    out = "alarm"
                else:
                    drun = drun + 1 if fresh < th_d else 0
                    if drun >= k:
                        out = "dismiss"
        if open_ and held is not None:
            stream[i] = held
        elif seen[i] > MISSING / 2.0:
            stream[i] = seen[i]
        if open_ and out is None and (i - i0 + 1) >= lmax_steps:
            out = "cap"
        if open_ and out is None and i == G - 1:
            out = "clip_end"
        if open_ and out is not None:
            episodes.append(dict(i0=i0, i_close=i, outcome=out, invocations=ep_inv, admitted=adm))
            if out in ("alarm", "dismiss", "cap"):
                prior[out] = prior.get(out, 0) + 1
            open_, i0, drun, adm = False, None, 0, False
            prev_above, held, next_call, pending = None, None, None, {}
            cool_at = i + 1 + cool_steps
    return stream, episodes, inv_total, alarms_all, trig_rows


def main(step=B.STEP_DENSE, horizons=B.HORIZONS_DENSE, cadence=CADENCE, integer_only=False,
         ceil_delivery=False, use_d14=False, outfile="e9b_study2_results.json", lat=LAT,
         far_list=ALARM_FPR, trig_list=TRIG_RATE):
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = B.build(step=step, horizons=horizons, integer_only=integer_only,
                  ceil_delivery=ceil_delivery, use_d14=use_d14)
    meta, clips, tau, fold, eng = ctx["meta"], ctx["clips"], ctx["tau"], ctx["fold"], ctx["eng"]
    arrs, pos_clips, neg_clips = ctx["arrs"], ctx["pos"], ctx["neg"]
    HOR = ctx["horizons"]
    P = PRIMARY
    LAMBDA = len(pos_clips) / float(ctx["neg_pts"])
    LAMBDA_MULT = (0.5, 1.0, 2.0) if ceil_delivery else (0.5, 1.0, 2.0, 20467.0 / 5196.0)
    wsteps = tuple(max(1, int(round(w / step))) for w in WINDOWS_S)
    lmax_steps = int(round(P["lmax"] / step))
    cool_steps = int(round(P["c"] / step))
    reesc_steps = int(round(REESC_WINDOW_S / step))
    mc = max(1, int(round(cadence / step)))

    def gpu_s(model, n, inv):
        return inv * E9.PROMPT_TOK[n] / E9.PREFILL_TOK_S[model]

    res = dict(
        label="StudyE9b-dense Study 2 (StudyE12 re-run): OFFLINE REPLAY OF COMMITTED RESULTS "
              "(StudyD14b 0.25-s traces). CPU only on flash; no GPU, no model server, no "
              "inference. Evaluation is the Nexar AP on continuous log P(Yes) scores; the "
              "per-episode utility is a TRAINING target for the admission ranking only and is "
              "never an evaluation metric. AP is comparable WITHIN this grid only.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, step_s=step,
        horizons=list(HOR), cadence_s=cadence, primary_config=P, budgets=list(BUDGETS),
        control_budget=CONTROL_BUDGET, lambda_value=LAMBDA, lambda_multipliers=list(LAMBDA_MULT),
        lambda_note=("lambda = positives per negative grid point on THIS grid (%d / %d). "
                     "StudyE12's 1-s-grid lambda was 150 / 5196 = %.7f, which is %.4fx this "
                     "value and is covered by the last sensitivity multiplier."
                     % (len(pos_clips), ctx["neg_pts"], 150.0 / 5196.0,
                        (150.0 / 5196.0) / LAMBDA)),
        h_star=H_STAR, reescalation_window_s=REESC_WINDOW_S, feature_names=list(FEATNAMES),
        feature_window_steps=list(wsteps), n_random_seeds=N_RANDOM_SEEDS, policies=list(POLICIES),
        rule_horizons=list(RULE_HORIZONS),
        n_clips=dict(positive=len(pos_clips), negative=len(neg_clips)),
        grid_points=dict(positive=ctx["pos_pts"], negative=ctx["neg_pts"]),
        chance_rate=ctx["chance"],
        excluded_features=["elapsed time since clip start", "time since the standing query began",
                           "clip metadata (scene, light, weather) - primary predictor"],
        cells={}, diagnostics={}, controls={}, trace_example=None)

    sweep = 0
    for rmodel, rn in RESOLVERS:
        for st in lat:
            seen_all, mdev, Ddev, Ld = B.dev_seen_all(ctx, st)
            _d, Lc = B.latencies(st, rmodel, rn)
            Dc = B.shift_steps(ctx, Lc)
            d_cloud_s = Dc * step
            for far in far_list:
                for trig in trig_list:
                    key_base = f"{rmodel}_N{rn}|{st}|far{int(far*100)}|trig{int(trig*100)}"
                    TR = {}
                    for clip in clips:
                        G = meta[clip]["G"]
                        dv, rs, seen = arrs[DEVICE][clip], arrs[(rmodel, rn)][clip], seen_all[clip]
                        thc, thd = tau[((rmodel, rn), fold[clip])], tau[(DEVICE, fold[clip])]
                        rows = []
                        _s, _e, _i, _a, trows = run_clip(
                            clip, dv, seen, rs, G, step, thc["alarm"][far], thc["dismiss"][P["q"]],
                            thd["alarm"][far], thd["dismiss"][P["q"]], thd["trig"][trig],
                            P["k"], lmax_steps, cool_steps, mdev, Ddev, mc, Dc, d_cloud_s,
                            wsteps, lambda *_: True)
                        for trow in trows:
                            i0 = trow["i"]
                            ea = rollout(dv, seen, rs, G, i0, thc["alarm"][far],
                                         thc["dismiss"][P["q"]], P["k"], lmax_steps,
                                         mdev, Ddev, mc, Dc, True)
                            el = rollout(dv, seen, rs, G, i0, thd["alarm"][far],
                                         thd["dismiss"][P["q"]], P["k"], lmax_steps,
                                         mdev, Ddev, mc, Dc, False)
                            work = ea["invocations"]
                            tt = ea["i_close"] + 1 + cool_steps
                            while tt <= min(ea["i_close"] + reesc_steps, G - 1):
                                if seen[tt] > MISSING / 2.0 and seen[tt] >= thd["trig"][trig]:
                                    nx = rollout(dv, seen, rs, G, tt, thc["alarm"][far],
                                                 thc["dismiss"][P["q"]], P["k"], lmax_steps,
                                                 mdev, Ddev, mc, Dc, True)
                                    work += nx["invocations"]
                                    tt = nx["i_close"] + 1 + cool_steps
                                else:
                                    tt += 1
                            lab, ev = meta[clip]["label"], meta[clip]["event"]
                            u_a = {m: episode_utility(ea, lab, ev, LAMBDA * m, step)[0]
                                   for m in LAMBDA_MULT}
                            u_l = {m: episode_utility(el, lab, ev, LAMBDA * m, step)[0]
                                   for m in LAMBDA_MULT}
                            rows.append(dict(
                                i=i0, t=T0 + i0 * step, features=trow["features"],
                                benefit={m: u_a[m] - u_l[m] for m in LAMBDA_MULT}, work=work,
                                admit_outcome=ea["outcome"], local_outcome=el["outcome"],
                                admit_alarm_i=ea["alarm_i"], local_alarm_i=el["alarm_i"],
                                admit_inv=ea["invocations"]))
                        TR[clip] = rows
                    ntrig = sum(len(v) for v in TR.values())

                    FEAT = {c: (np.array([r["features"] for r in TR[c]], dtype=float)
                                if TR[c] else np.zeros((0, len(FEATNAMES)))) for c in clips}
                    diag, models, cuts = {}, {}, {}
                    for lam_m in LAMBDA_MULT:
                        for fi in range(NFOLD):
                            tr_c = [c for c in clips if fold[c] != fi]
                            Xtr = (np.concatenate([FEAT[c] for c in tr_c if len(TR[c])])
                                   if any(TR[c] for c in tr_c)
                                   else np.zeros((0, len(FEATNAMES))))
                            btr = np.array([r["benefit"][lam_m] for c in tr_c for r in TR[c]])
                            wtr = np.array([r["work"] for c in tr_c for r in TR[c]], dtype=float)
                            ytr = (btr > 0).astype(int)
                            sc = StandardScaler().fit(Xtr)
                            if ytr.max() == ytr.min():
                                mb, auc = None, None
                                ptr = np.full(len(ytr), float(ytr[0]) if len(ytr) else 0.0)
                            else:
                                mb = LogisticRegression(max_iter=4000, C=1.0,
                                                        random_state=SEED).fit(sc.transform(Xtr), ytr)
                                ptr = mb.predict_proba(sc.transform(Xtr))[:, 1]
                                auc = float(roc_auc_score(ytr, ptr))
                            mw = PoissonRegressor(alpha=1e-3, max_iter=5000).fit(
                                sc.transform(Xtr), np.maximum(wtr, 0.0))
                            wpred_tr = np.maximum(mw.predict(sc.transform(Xtr)), 1e-6)
                            ss = float(1.0 - np.sum((wtr - wpred_tr) ** 2)
                                       / max(np.sum((wtr - wtr.mean()) ** 2), 1e-12))
                            models[(lam_m, fi)] = (sc, mb, mw)
                            if lam_m == 1.0:
                                diag[f"fold{fi}"] = dict(
                                    n_train_triggers=int(len(ytr)),
                                    benefit_positive_rate=(float(ytr.mean()) if len(ytr) else None),
                                    auroc_benefit_gt0=auc, work_r2_train=ss,
                                    work_mean=(float(wtr.mean()) if len(wtr) else None),
                                    coef=(None if mb is None else
                                          {n: float(v) for n, v in zip(FEATNAMES, mb.coef_[0])}))
                            tbtr = np.array([tiebreak(c, tie_label(r["i"], step))
                                             for c in tr_c for r in TR[c]])
                            strj = ptr + JIT * tbtr
                            strw = ptr / wpred_tr + JIT * tbtr
                            ssc = (Xtr[:, 0] + JIT * tbtr) if len(Xtr) else np.zeros(0)
                            sorc = btr + JIT * tbtr
                            for Bg in list(BUDGETS) + [CONTROL_BUDGET]:
                                for nm, v in (("P-score", ssc), ("P-trajectory", strj),
                                              ("P-trajectory-work", strw), ("P-oracle", sorc)):
                                    cuts[(lam_m, fi, nm, Bg)] = (
                                        -np.inf if Bg >= 1.0 else
                                        float(np.quantile(v, 1.0 - Bg)) if len(v) else np.inf)
                    res["diagnostics"][key_base] = dict(n_triggers=ntrig, folds=diag)

                    LBL = {}

                    def labels_for(clip, i0, _rm=rmodel, _rn=rn, _far=far):
                        kk = (clip, i0)
                        if kk in LBL:
                            return LBL[kk]
                        G = meta[clip]["G"]
                        dv, rs, seen = arrs[DEVICE][clip], arrs[(_rm, _rn)][clip], seen_all[clip]
                        thc, thd = tau[((_rm, _rn), fold[clip])], tau[(DEVICE, fold[clip])]
                        ea = rollout(dv, seen, rs, G, i0, thc["alarm"][_far],
                                     thc["dismiss"][P["q"]], P["k"], lmax_steps,
                                     mdev, Ddev, mc, Dc, True)
                        el = rollout(dv, seen, rs, G, i0, thd["alarm"][_far],
                                     thd["dismiss"][P["q"]], P["k"], lmax_steps,
                                     mdev, Ddev, mc, Dc, False)
                        lab, ev = meta[clip]["label"], meta[clip]["event"]
                        b = {m: (episode_utility(ea, lab, ev, LAMBDA * m, step)[0]
                                 - episode_utility(el, lab, ev, LAMBDA * m, step)[0])
                             for m in LAMBDA_MULT}
                        LBL[kk] = (b, ea, el)
                        return LBL[kk]

                    POOL = {fi: (np.concatenate([FEAT[c] for c in clips
                                                 if fold[c] == fi and len(TR[c])])
                                 if any(len(TR[c]) for c in clips if fold[c] == fi)
                                 else np.zeros((0, len(FEATNAMES)))) for fi in range(NFOLD)}

                    def policy_run(nm, Bg, lam_m=1.0, shuffle=False, rseed=0):
                        streams, eps, invs, al, admitted = {}, {}, {}, {}, {}
                        rr = np.random.default_rng([SEED, rseed])
                        for clip in clips:
                            G = meta[clip]["G"]
                            dv, rs = arrs[DEVICE][clip], arrs[(rmodel, rn)][clip]
                            seen = seen_all[clip]
                            thc, thd = tau[((rmodel, rn), fold[clip])], tau[(DEVICE, fold[clip])]
                            fi = fold[clip]
                            sc, mb, mw = models[(lam_m, fi)]
                            pool = POOL[fi]

                            def decide(i, prior, sn, _c=clip, _fi=fi):
                                if nm == "admit-all" or Bg >= 1.0:
                                    return True
                                if nm == "admit-none":
                                    return False
                                if nm == "P-random":
                                    return bool(rr.random() < Bg)
                                x = np.array([trigger_features(sn, i, prior, d_cloud_s, wsteps)],
                                             dtype=float)
                                if shuffle and len(pool):
                                    x = pool[int(rr.integers(len(pool)))][None, :].copy()
                                tb = JIT * tiebreak(_c, tie_label(i, step))
                                if nm == "P-score":
                                    v = float(x[0, 0]) + tb
                                elif nm == "P-oracle":
                                    v = float(labels_for(_c, i)[0][lam_m]) + tb
                                else:
                                    pb = (mb.predict_proba(sc.transform(x))[:, 1][0]
                                          if mb is not None else 0.0)
                                    if nm == "P-trajectory":
                                        v = float(pb) + tb
                                    else:
                                        v = float(pb / max(mw.predict(sc.transform(x))[0], 1e-6)) + tb
                                return bool(v >= cuts[(lam_m, _fi, nm, Bg)])

                            s, e, iv, a, _tr = run_clip(
                                clip, dv, seen, rs, G, step, thc["alarm"][far],
                                thc["dismiss"][P["q"]], thd["alarm"][far], thd["dismiss"][P["q"]],
                                thd["trig"][trig], P["k"], lmax_steps, cool_steps, mdev, Ddev,
                                mc, Dc, d_cloud_s, wsteps, decide)
                            streams[clip], eps[clip], invs[clip], al[clip] = s, e, iv, a
                            admitted[clip] = (sum(1 for x in e if x["admitted"]), len(e))
                        return streams, eps, invs, al, admitted

                    def summarise(streams, eps, invs, al, admitted, with_ap=True, ci=True):
                        nad = sum(v[0] for v in admitted.values())
                        nep = sum(v[1] for v in admitted.values())
                        inv_all = sum(invs.values())
                        hours = ctx["hours_all"]
                        apos = sum(1 for c in pos_clips if al[c])
                        nfa = sum(len(al[c]) for c in neg_clips)
                        d = dict(episodes=nep, admitted=nad,
                                 realized_admitted_fraction=(nad / nep if nep else None),
                                 invocations=inv_all, invocations_per_clip_hour=inv_all / hours,
                                 gpu_seconds=gpu_s(rmodel, rn, inv_all),
                                 gpu_seconds_per_clip_hour=gpu_s(rmodel, rn, inv_all) / hours,
                                 fraction_positive_alarmed=apos / len(pos_clips),
                                 false_alarm_events_negative=nfa,
                                 false_alarms_per_clip_hour=nfa / ctx["hours_neg"])
                        if with_ap and ci:
                            ap, boot = eng.full(streams)
                            d["ap"] = {h: dict(ap=ap[h]["ap"], ci=ap[h]["ci"],
                                               multiple_of_chance=ap[h]["ap"] / ctx["chance"])
                                       for h in HOR}
                            d["_boot"] = boot
                        elif with_ap:
                            pt = eng.point(streams)
                            d["ap"] = {h: dict(ap=pt[h], ci=None,
                                               multiple_of_chance=pt[h] / ctx["chance"])
                                       for h in HOR}
                        return d

                    cellset = {}
                    IS_PRIMARY = (far == 0.05 and trig == 0.20 and st == "measured@25")
                    for Bg in list(BUDGETS) + [CONTROL_BUDGET]:
                        for nm in POLICIES:
                            if nm == "P-random":
                                accs, bo = [], None
                                for sd in range(N_RANDOM_SEEDS):
                                    o = summarise(*policy_run(nm, Bg, rseed=sd), ci=IS_PRIMARY)
                                    accs.append(o)
                                    bo = o if bo is None else bo
                                d = dict(bo)
                                for fl in ("invocations", "invocations_per_clip_hour",
                                           "gpu_seconds", "gpu_seconds_per_clip_hour",
                                           "fraction_positive_alarmed",
                                           "false_alarms_per_clip_hour", "admitted", "episodes",
                                           "realized_admitted_fraction"):
                                    vals = [a[fl] for a in accs if a[fl] is not None]
                                    d[fl] = float(np.mean(vals)) if vals else None
                                d["ap"] = {h: dict(
                                    ap=float(np.mean([a["ap"][h]["ap"] for a in accs])),
                                    ci=([float(np.mean([a["ap"][h]["ci"][0] for a in accs])),
                                         float(np.mean([a["ap"][h]["ci"][1] for a in accs]))]
                                        if IS_PRIMARY else None),
                                    multiple_of_chance=float(np.mean(
                                        [a["ap"][h]["ap"] for a in accs])) / ctx["chance"])
                                    for h in HOR}
                                if IS_PRIMARY:
                                    d["_boot"] = {h: np.mean([a["_boot"][h] for a in accs], axis=0)
                                                  for h in HOR}
                                d["n_seeds"] = N_RANDOM_SEEDS
                            else:
                                d = summarise(*policy_run(nm, Bg), ci=IS_PRIMARY)
                            d.update(policy=nm, budget=Bg, resolver=f"{rmodel}_N{rn}", latency=st,
                                     alarm_fpr=far, trigger_rate=trig, cadence_s=cadence)
                            cellset[(nm, Bg)] = d
                    for (nm, Bg), d in cellset.items():
                        for ref in ("P-score", "P-random"):
                            if nm == ref or "_boot" not in d or "_boot" not in cellset[(ref, Bg)]:
                                continue
                            rb = cellset[(ref, Bg)]
                            dd = {}
                            for h in HOR:
                                df = d["_boot"][h] - rb["_boot"][h]
                                dd[h] = dict(diff=float(d["ap"][h]["ap"] - rb["ap"][h]["ap"]),
                                             ci=[float(np.percentile(df, 2.5)),
                                                 float(np.percentile(df, 97.5))])
                            d[f"vs_{ref}"] = dd
                            d[f"gpu_ratio_vs_{ref}"] = (d["gpu_seconds"] / rb["gpu_seconds"]
                                                        if rb["gpu_seconds"] else None)
                    for (nm, Bg), d in cellset.items():
                        d.pop("_boot", None)
                        res["cells"][f"{key_base}|B{int(Bg*100)}|{nm}"] = d
                    sweep += 1
                    print("  swept", key_base, "cells", len(res["cells"]), flush=True)

                    if IS_PRIMARY:
                        sens = {}
                        for lam_m in LAMBDA_MULT:
                            for Bg in BUDGETS:
                                for nm in ("P-trajectory", "P-trajectory-work"):
                                    o = summarise(*policy_run(nm, Bg, lam_m=lam_m))
                                    o.pop("_boot", None)
                                    sens[f"lam{lam_m:g}|B{int(Bg*100)}|{nm}"] = dict(
                                        ap={h: o["ap"][h]["ap"] for h in HOR},
                                        gpu_seconds_per_clip_hour=o["gpu_seconds_per_clip_hour"],
                                        realized_admitted_fraction=o["realized_admitted_fraction"])
                        res.setdefault("lambda_sensitivity", {})[key_base] = sens
                        ctb = {}
                        for Bg in BUDGETS:
                            o = summarise(*policy_run("P-trajectory", Bg, shuffle=True))
                            o.pop("_boot", None)
                            ctb[f"B{int(Bg*100)}"] = dict(
                                ap={h: o["ap"][h]["ap"] for h in HOR},
                                realized_admitted_fraction=o["realized_admitted_fraction"],
                                gpu_seconds_per_clip_hour=o["gpu_seconds_per_clip_hour"],
                                ap_P_random={h: res["cells"][f"{key_base}|B{int(Bg*100)}|P-random"]["ap"][h]["ap"]
                                             for h in HOR},
                                ap_P_trajectory={h: res["cells"][f"{key_base}|B{int(Bg*100)}|P-trajectory"]["ap"][h]["ap"]
                                                 for h in HOR})
                        res["controls"].setdefault("c_shuffle_features_within_fold", dict(
                            description="each trigger's feature vector is replaced by one drawn "
                                        "uniformly from that fold's pool of trigger feature "
                                        "vectors (seed 0), which breaks the feature-label "
                                        "association while preserving the marginal feature "
                                        "distribution. Labels, cutoff procedure and budget are "
                                        "unchanged. P-trajectory must fall to P-random's level.",
                            cells={}))["cells"][key_base] = ctb

                        pick = None
                        for c in pos_clips:
                            if len(TR[c]) >= 3:
                                pick = c
                                break
                        if pick:
                            fi = fold[pick]
                            sc, mb, mw = models[(1.0, fi)]
                            X = FEAT[pick]
                            pb = (mb.predict_proba(sc.transform(X))[:, 1] if mb is not None
                                  else np.zeros(len(X)))
                            wp = np.maximum(mw.predict(sc.transform(X)), 1e-6)
                            rows = []
                            for j, r in enumerate(TR[pick]):
                                rows.append(dict(
                                    trigger_t=round(r["t"], 3),
                                    rel_event_s=round(r["t"] - meta[pick]["event"], 3),
                                    features={n: round(v, 4)
                                              for n, v in zip(FEATNAMES, r["features"])},
                                    predicted_benefit_gt0=round(float(pb[j]), 4),
                                    predicted_work=round(float(wp[j]), 3),
                                    rank_score_P_score=round(r["features"][0], 4),
                                    rank_score_P_trajectory=round(float(pb[j]), 4),
                                    rank_score_P_trajectory_work=round(float(pb[j] / wp[j]), 6),
                                    true_benefit=r["benefit"][1.0], true_work=r["work"],
                                    admit_path=dict(outcome=r["admit_outcome"],
                                                    alarm_t=(None if r["admit_alarm_i"] is None else
                                                             round(T0 + r["admit_alarm_i"] * step, 3)),
                                                    invocations=r["admit_inv"]),
                                    local_path=dict(outcome=r["local_outcome"],
                                                    alarm_t=(None if r["local_alarm_i"] is None else
                                                             round(T0 + r["local_alarm_i"] * step, 3)),
                                                    invocations=0),
                                    admitted_at={f"B{int(Bg*100)}": bool(
                                        float(pb[j]) >= cuts[(1.0, fi, 'P-trajectory', Bg)])
                                        for Bg in BUDGETS}))
                            res["trace_example"] = dict(
                                cell=key_base, clip=pick, label=meta[pick]["label"],
                                event_s=meta[pick]["event"], duration_s=meta[pick]["dur"],
                                fold=fi, step_s=step, device_cadence_s=mdev * step,
                                device_hold_shift_s=Ddev * step, cloud_latency_s=Lc,
                                cloud_hold_shift_s=Dc * step, cadence_s=cadence,
                                tau_trigger=round(tau[(DEVICE, fi)]["trig"][trig], 4),
                                tau_alarm_cloud=round(tau[((rmodel, rn), fi)]["alarm"][far], 4),
                                tau_alarm_device=round(tau[(DEVICE, fi)]["alarm"][far], 4),
                                cutoffs={f"B{int(Bg*100)}":
                                         round(cuts[(1.0, fi, 'P-trajectory', Bg)], 6)
                                         for Bg in BUDGETS},
                                lambda_value=LAMBDA, h_star=H_STAR, triggers=rows)

    nca = {}
    for k in list(res["cells"]):
        if "|B100|" not in k:
            continue
        base, nm = k.rsplit("|", 1)[0], k.rsplit("|", 1)[1]
        ref, d = res["cells"][f"{base}|admit-all"], res["cells"][k]
        h0 = HOR[0]
        nca[f"{base}|{nm}"] = bool(
            abs(d["ap"][h0]["ap"] - ref["ap"][h0]["ap"]) < 1e-12
            and d["invocations"] == ref["invocations"]
            and abs(d["fraction_positive_alarmed"] - ref["fraction_positive_alarmed"]) < 1e-12
            and abs(d["false_alarms_per_clip_hour"] - ref["false_alarms_per_clip_hour"]) < 1e-9)
    res["controls"]["b_budget_1_equals_admit_all"] = dict(
        description="At budget 1.0 every policy must equal admit-all exactly (AP at the first "
                    "horizon, invocations, fraction of positives alarmed, false alarms per "
                    "clip-hour).",
        cells_checked=len(nca), all_equal=all(nca.values()),
        mismatches=[k for k, v in nca.items() if not v])

    res["_provenance"] = stamp(script="study_e9b_admission.py", model=None, device="cpu",
                               n=len(clips), args=None)
    (OUT / outfile).write_text(json.dumps(res, indent=1, default=float))
    print("cells:", len(res["cells"]), "sweeps:", sweep)
    return res


if __name__ == "__main__":
    main()
