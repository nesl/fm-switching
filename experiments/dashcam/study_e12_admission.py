#!/usr/bin/env python3
"""StudyE12-admission — which device-triggered escalations to admit under a cloud capacity budget.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
StudyD14's committed trace; every latency and byte count is read from a committed StudyD4 /
StudyD7 / StudyD7b / StudyD8 measurement, through study_e9_episodes.py.

Evaluation is the Nexar metric: AP at fixed horizons on CONTINUOUS scores (log P(Yes)), exactly as
StudyE5 Part G and StudyE9. No literal Yes/No answer is used anywhere. The per-episode utility is
a TRAINING target for the admission ranking only and is never an evaluation metric.
"""
import collections, json, os, sys, zlib
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402
import study_e9_episodes as E9  # noqa: E402
from sklearn.linear_model import LogisticRegression, PoissonRegressor  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

OUT = ROOT / "results/dashcam/study_e12"
SEED, NB, NFOLD = E9.SEED, E9.NB, E9.NFOLD
HORIZONS = E9.HORIZONS
MISSING = E9.MISSING
DEVICE = E9.DEVICE
PRIMARY = dict(k=2, q=0.75, lmax=10, c=0)
RESOLVERS = [("32BI", 1), ("32BI", 3)]
BUDGETS = (0.25, 0.50, 0.75)
CONTROL_BUDGET = 1.0
ALARM_FPR = (0.01, 0.05, 0.10)
TRIG_RATE = (0.10, 0.20)
LAT = ("measured@25", "zero")
H_STAR = 0.5
LAMBDA = 150.0 / 5196.0            # one false alarm costs what the base rate implies
LAMBDA_MULT = (0.5, 1.0, 2.0)
REESC_WINDOW_S = 10                # "remaining work" includes re-escalations within 10 s
N_RANDOM_SEEDS = 20
POLICIES = ["admit-none", "P-random", "P-score", "P-trajectory", "P-trajectory-work",
            "P-oracle", "admit-all"]


# ---------------------------------------------------------------- ranking tiebreak
JIT = 1e-9


def tiebreak(clip, t):
    """Deterministic uniform in [0,1) per (clip, trigger second), stable across processes.
    The benefit label is discrete (mostly exactly 0), so without a tiebreak a quantile cutoff
    admits every trigger at or above 0 and the budget is not enforced. The same draw is used
    when fitting the cutoff and when deciding, so the two agree exactly."""
    h = zlib.crc32(f"{SEED}|{clip}|{t}".encode())
    return (h % (1 << 30)) / float(1 << 30)


# ---------------------------------------------------------------- features
FEATNAMES = (["dev_score_t"]
             + [f"{s}_{w}s" for w in (3, 5) for s in ("mean", "max", "slope", "std")]
             + ["n_prior_triggers", "n_prior_alarm", "n_prior_dismiss", "n_prior_cap", "d_cloud"])


def window_feats(seen, i, w):
    """seen[j] is the device score the application carries at second j (already delayed).
    Window is the w seconds up to and including i; only indices with a score are used."""
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


def trigger_features(seen, i, prior, d_cloud):
    return ([float(seen[i]) if seen[i] > MISSING / 2.0 else 0.0]
            + window_feats(seen, i, 3) + window_feats(seen, i, 5)
            + [float(prior["n"]), float(prior["alarm"]), float(prior["dismiss"]),
               float(prior["cap"]), float(d_cloud)])


# ---------------------------------------------------------------- one-episode rollout
def rollout(dev, res, T, t0, th_a, th_d, k, lmax, d_dev, d_cloud, admit):
    """Run ONE episode opened at t0 to its close, in isolation. `admit` picks the resolver
    (32B, d_cloud) or the device's own score (4B, d_dev, no cloud work). Returns the stream
    seconds it produced, its outcome, the second it closed, its alarm second, its resolver
    invocations, and the alarm seconds it raised."""
    src_arr, src_d = (res, d_cloud) if admit else (dev, d_dev)
    drun, alarms = 0, []
    prev_above = None
    for t in range(t0, T + 1):
        u = t - src_d
        out = None
        avail = (u >= t0) if admit else (u >= 3)
        if avail:
            s = src_arr[u - 3]
            above = s >= th_a
            if above and prev_above is not True:
                alarms.append(t)
            prev_above = above
            if above:
                out = "alarm"
            else:
                drun = drun + 1 if s < th_d else 0
                if drun >= k:
                    out = "dismiss"
        if out is None and (t - t0 + 1) >= lmax:
            out = "cap"
        if out is None and t == T:
            out = "clip_end"
        if out is not None:
            inv = (t - t0 + 1) if admit else 0
            return dict(outcome=out, t_close=t, alarm_t=(alarms[0] if alarms else None),
                        invocations=inv, alarms=alarms)
    return dict(outcome="clip_end", t_close=T, alarm_t=(alarms[0] if alarms else None),
                invocations=((T - t0 + 1) if admit else 0), alarms=alarms)


def episode_utility(ep, label, event, lam):
    """U = 1[alarm on a positive clip at least h* before the event] - lam * (false alarms)."""
    hit = 0.0
    if label == "positive" and ep["alarm_t"] is not None and ep["alarm_t"] <= event - H_STAR:
        hit = 1.0
    fa = len(ep["alarms"]) if label == "negative" else 0
    return hit - lam * fa, hit, fa


# ---------------------------------------------------------------- policy run over a clip
def run_clip(dev, res, T, th_a_cloud, th_d_cloud, th_a_dev, th_d_dev, t_trig, k, lmax, c,
             d_dev, d_cloud, decide):
    """Whole-clip replay with an admission decision at every trigger. `decide(i, prior, seen)`
    returns True to admit. The application's stream carries the resolver's score inside an
    admitted open episode and the device's score otherwise."""
    n = T - 3 + 1
    stream = np.full(n, MISSING)
    seen = np.full(n, MISSING)                 # device-visible score, for features
    for t in range(3, T + 1):
        u = t - d_dev
        if u >= 3:
            seen[t - 3] = dev[u - 3]
    episodes, inv_total, alarms_all = [], 0, []
    prior = dict(n=0, alarm=0, dismiss=0, cap=0)
    open_, t0, drun, cool_until, adm = False, None, 0, -10**9, False
    prev_above = None
    trig_rows = []
    for t in range(3, T + 1):
        i = t - 3
        if not open_ and t >= cool_until:
            u = t - d_dev
            if u >= 3 and dev[u - 3] >= t_trig:
                adm = bool(decide(i, dict(prior), seen))
                open_, t0, drun = True, t, 0
                prev_above = None
                trig_rows.append(dict(t=t, admitted=adm, features=trigger_features(seen, i, prior, d_cloud)))
                prior["n"] += 1
        got, out = False, None
        th_a = th_a_cloud if adm else th_a_dev
        th_d = th_d_cloud if adm else th_d_dev
        if open_:
            if adm:
                u = t - d_cloud
                if u >= t0:
                    s = res[u - 3]
                    stream[i], got = s, True
            else:
                u = t - d_dev
                if u >= 3:
                    stream[i], got = dev[u - 3], True
            if got:
                s = stream[i]
                above = s >= th_a
                if above and prev_above is not True:
                    alarms_all.append(t)
                prev_above = above
                if above:
                    out = "alarm"
                else:
                    drun = drun + 1 if s < th_d else 0
                    if drun >= k:
                        out = "dismiss"
        if not got:
            if seen[i] > MISSING / 2.0:
                stream[i] = seen[i]
        if open_ and out is None and (t - t0 + 1) >= lmax:
            out = "cap"
        if open_ and out is None and t == T:
            out = "clip_end"
        if open_ and out is not None:
            inv = (t - t0 + 1) if adm else 0
            inv_total += inv
            episodes.append(dict(t0=t0, t_close=t, outcome=out, invocations=inv, admitted=adm))
            if out in ("alarm", "dismiss", "cap"):
                prior[out] = prior.get(out, 0) + 1
            open_, t0, drun, adm = False, None, 0, False
            prev_above = None
            cool_until = t + 1 + c
    return stream, episodes, inv_total, alarms_all, trig_rows, seen


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    arrs, meta, clips = E9.load()
    fold = E9.folds(clips, meta)
    tau = E9.fit_thresholds(arrs, meta, clips, fold)
    pos_clips = [c for c in clips if meta[c]["label"] == "positive"]
    neg_clips = [c for c in clips if meta[c]["label"] == "negative"]
    neg_seconds = sum(meta[c]["T"] - 2 for c in neg_clips)
    pos_seconds = sum(meta[c]["T"] - 2 for c in pos_clips)
    assert neg_seconds == 5196, neg_seconds
    assert abs(LAMBDA - 150.0 / 5196.0) < 1e-12

    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos_clips), len(pos_clips)),
              rng.integers(0, len(neg_clips), len(neg_clips))) for _ in range(NB)]

    def target_index(c, h):
        T = meta[c]["T"]
        return int(min(max(round(meta[c]["event"] - h), 3), T)) - 3

    neg_len = None
    neg_take = None

    def ap_point(streams):
        """AP at every horizon, no bootstrap (used for the secondary configurations)."""
        Ncat = np.concatenate([streams[c] for c in neg_clips])
        out = {}
        for h in HORIZONS:
            Pp = np.array([streams[c][target_index(c, h)] for c in pos_clips])
            out[h] = dict(ap=E9.ap_from(Pp, Ncat), ci=None)
        return out

    def ap_all(streams):
        nonlocal neg_len, neg_take
        P = [np.array([streams[c][target_index(c, h)] for c in pos_clips]) for h in HORIZONS]
        Ncat = np.concatenate([streams[c] for c in neg_clips])
        if neg_len is None:
            neg_len = np.array([len(streams[c]) for c in neg_clips])
            off = np.concatenate([[0], np.cumsum(neg_len)])
            neg_take = [np.concatenate([np.arange(off[j], off[j + 1]) for j in ni])
                        for _, ni in boots]
        pts = [E9.ap_from(P[i], Ncat) for i in range(len(HORIZONS))]
        bs = np.empty((len(HORIZONS), NB))
        for b, (pi, _ni) in enumerate(boots):
            nn = Ncat[neg_take[b]]
            for i in range(len(HORIZONS)):
                bs[i, b] = E9.ap_from(P[i][pi], nn)
        return {h: dict(ap=pts[i], ci=[float(np.percentile(bs[i], 2.5)),
                                       float(np.percentile(bs[i], 97.5))],
                        boot=bs[i].copy()) for i, h in enumerate(HORIZONS)}

    PREFILL = E9.PREFILL_TOK_S
    PROMPT = E9.PROMPT_TOK

    def gpu_s(model, n, inv):
        return inv * PROMPT[n] / PREFILL[model]

    res = dict(
        label="StudyE12-admission: OFFLINE ANALYSIS OF COMMITTED RESULTS (StudyD14 traces). CPU "
              "only on flash; no GPU, no model server, no inference. Evaluation is the Nexar AP on "
              "continuous log P(Yes) scores; the per-episode utility is a TRAINING target for the "
              "admission ranking only and is never an evaluation metric.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, horizons=list(HORIZONS),
        primary_config=PRIMARY, budgets=list(BUDGETS), control_budget=CONTROL_BUDGET,
        lambda_value=LAMBDA, lambda_multipliers=list(LAMBDA_MULT), h_star=H_STAR,
        reescalation_window_s=REESC_WINDOW_S, feature_names=list(FEATNAMES),
        n_random_seeds=N_RANDOM_SEEDS, policies=list(POLICIES),
        n_clips=dict(positive=len(pos_clips), negative=len(neg_clips)),
        seconds=dict(positive=pos_seconds, negative=neg_seconds),
        base_rate=len(pos_clips) / (len(pos_clips) + neg_seconds),
        excluded_features=["elapsed time since clip start", "time since the standing query began",
                           "clip metadata (scene, light, weather) - primary predictor"],
        cells={}, diagnostics={}, controls={}, trace_example=None)

    # ---------------- per-(resolver, latency, far, trig) sweep ----------------
    P = PRIMARY
    sweep = 0
    for rmodel, rn in RESOLVERS:
        for st in LAT:
            d_dev, d_cloud = E9.delays(st, rmodel, rn)
            d_dev_dev, _ = E9.delays(st, *DEVICE)
            for far in ALARM_FPR:
                for trig in TRIG_RATE:
                    key_base = f"{rmodel}_N{rn}|{st}|far{int(far*100)}|trig{int(trig*100)}"
                    # ---- labels on every trigger, from isolated rollouts (policy-independent)
                    TR = {}
                    for clip in clips:
                        T = meta[clip]["T"]
                        dv, rs = arrs[DEVICE][clip], arrs[(rmodel, rn)][clip]
                        thc = tau[((rmodel, rn), fold[clip])]
                        thd = tau[(DEVICE, fold[clip])]
                        rows = []
                        # enumerate triggers along the admit-all trajectory
                        _s, _e, _i, _a, trows, seen = run_clip(
                            dv, rs, T, thc["alarm"][far], thc["dismiss"][P["q"]],
                            thd["alarm"][far], thd["dismiss"][P["q"]], thd["trig"][trig],
                            P["k"], P["lmax"], P["c"], d_dev, d_cloud, lambda *_: True)
                        for trow in trows:
                            t0 = trow["t"]
                            ea = rollout(dv, rs, T, t0, thc["alarm"][far], thc["dismiss"][P["q"]],
                                         P["k"], P["lmax"], d_dev, d_cloud, True)
                            el = rollout(dv, rs, T, t0, thd["alarm"][far], thd["dismiss"][P["q"]],
                                         P["k"], P["lmax"], d_dev, d_cloud, False)
                            # remaining work: this episode plus admitted re-escalations within 10 s
                            work = ea["invocations"]
                            tt = ea["t_close"] + 1 + P["c"]
                            while tt <= min(ea["t_close"] + REESC_WINDOW_S, T):
                                u = tt - d_dev
                                if u >= 3 and dv[u - 3] >= thd["trig"][trig]:
                                    nx = rollout(dv, rs, T, tt, thc["alarm"][far],
                                                 thc["dismiss"][P["q"]], P["k"], P["lmax"],
                                                 d_dev, d_cloud, True)
                                    work += nx["invocations"]
                                    tt = nx["t_close"] + 1 + P["c"]
                                else:
                                    tt += 1
                            u_a = {m: episode_utility(ea, meta[clip]["label"], meta[clip]["event"],
                                                      LAMBDA * m)[0] for m in LAMBDA_MULT}
                            u_l = {m: episode_utility(el, meta[clip]["label"], meta[clip]["event"],
                                                      LAMBDA * m)[0] for m in LAMBDA_MULT}
                            rows.append(dict(
                                t=t0, features=trow["features"],
                                benefit={m: u_a[m] - u_l[m] for m in LAMBDA_MULT},
                                work=work, admit_outcome=ea["outcome"], local_outcome=el["outcome"],
                                admit_alarm_t=ea["alarm_t"], local_alarm_t=el["alarm_t"],
                                admit_inv=ea["invocations"]))
                        TR[clip] = rows
                    ntrig = sum(len(v) for v in TR.values())

                    # ---- cross-fitted predictors and cutoffs
                    FEAT = {c: (np.array([r["features"] for r in TR[c]], dtype=float)
                                if TR[c] else np.zeros((0, len(FEATNAMES)))) for c in clips}
                    diag = {}
                    models, cuts = {}, {}
                    for lam_m in LAMBDA_MULT:
                        for fi in range(NFOLD):
                            tr_c = [c for c in clips if fold[c] != fi]
                            Xtr = np.concatenate([FEAT[c] for c in tr_c if len(TR[c])]) \
                                if any(TR[c] for c in tr_c) else np.zeros((0, len(FEATNAMES)))
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
                                    benefit_positive_rate=float(ytr.mean()) if len(ytr) else None,
                                    auroc_benefit_gt0=auc, work_r2_train=ss,
                                    work_mean=float(wtr.mean()) if len(wtr) else None,
                                    coef=(None if mb is None else
                                          {n: float(v) for n, v in zip(FEATNAMES, mb.coef_[0])}))
                            # cutoffs per policy and budget, fitted on TRAINING triggers
                            tbtr = np.array([tiebreak(c, r["t"]) for c in tr_c for r in TR[c]])
                            strj = ptr + JIT * tbtr
                            strw = ptr / wpred_tr + JIT * tbtr
                            ssc = (Xtr[:, 0] + JIT * tbtr) if len(Xtr) else np.zeros(0)
                            sorc = btr + JIT * tbtr
                            for B in list(BUDGETS) + [CONTROL_BUDGET]:
                                for nm, v in (("P-score", ssc), ("P-trajectory", strj),
                                              ("P-trajectory-work", strw), ("P-oracle", sorc)):
                                    cuts[(lam_m, fi, nm, B)] = (
                                        -np.inf if B >= 1.0 else
                                        float(np.quantile(v, 1.0 - B)) if len(v) else np.inf)
                    res["diagnostics"][key_base] = dict(n_triggers=ntrig, folds=diag)

                    # ---- run every policy at every budget
                    LBL = {}

                    def labels_for(clip, t0):
                        """Per-trigger labels from isolated rollouts: policy-independent, so a
                        trigger that only some policies reach still has an exact label."""
                        kk = (clip, t0)
                        if kk in LBL:
                            return LBL[kk]
                        T = meta[clip]["T"]
                        dv, rs = arrs[DEVICE][clip], arrs[(rmodel, rn)][clip]
                        thc = tau[((rmodel, rn), fold[clip])]
                        thd = tau[(DEVICE, fold[clip])]
                        ea = rollout(dv, rs, T, t0, thc["alarm"][far], thc["dismiss"][P["q"]],
                                     P["k"], P["lmax"], d_dev, d_cloud, True)
                        el = rollout(dv, rs, T, t0, thd["alarm"][far], thd["dismiss"][P["q"]],
                                     P["k"], P["lmax"], d_dev, d_cloud, False)
                        b = {m: (episode_utility(ea, meta[clip]["label"], meta[clip]["event"],
                                                 LAMBDA * m)[0]
                                 - episode_utility(el, meta[clip]["label"], meta[clip]["event"],
                                                   LAMBDA * m)[0]) for m in LAMBDA_MULT}
                        LBL[kk] = (b, ea, el)
                        return LBL[kk]

                    POOL = {fi: np.concatenate([FEAT[c] for c in clips
                                                if fold[c] == fi and len(TR[c])])
                            for fi in range(NFOLD)}

                    def policy_run(nm, B, lam_m=1.0, shuffle=False, rseed=0):
                        streams, eps, invs, al = {}, {}, {}, {}
                        admitted = {}
                        rr = np.random.default_rng([SEED, rseed])
                        for clip in clips:
                            T = meta[clip]["T"]
                            dv, rs = arrs[DEVICE][clip], arrs[(rmodel, rn)][clip]
                            thc = tau[((rmodel, rn), fold[clip])]
                            thd = tau[(DEVICE, fold[clip])]
                            fi = fold[clip]
                            sc, mb, mw = models[(lam_m, fi)]
                            pool = POOL[fi]

                            def decide(i, prior, seen, _c=clip, _fi=fi):
                                if nm == "admit-all" or B >= 1.0:
                                    return True
                                if nm == "admit-none":
                                    return False
                                if nm == "P-random":
                                    return bool(rr.random() < B)
                                # features are built HERE, from information available at the
                                # trigger second only; the trigger set shifts with the budget, so
                                # they cannot be read from a precomputed per-trigger array.
                                x = np.array([trigger_features(seen, i, prior, d_cloud)], dtype=float)
                                if shuffle and len(pool):
                                    x = pool[int(rr.integers(len(pool)))][None, :].copy()
                                tb = JIT * tiebreak(_c, i + 3)
                                if nm == "P-score":
                                    v = float(x[0, 0]) + tb
                                elif nm == "P-oracle":
                                    v = float(labels_for(_c, i + 3)[0][lam_m]) + tb
                                else:
                                    pb = (mb.predict_proba(sc.transform(x))[:, 1][0]
                                          if mb is not None else 0.0)
                                    if nm == "P-trajectory":
                                        v = float(pb) + tb
                                    else:
                                        v = float(pb / max(mw.predict(sc.transform(x))[0], 1e-6)) + tb
                                return bool(v >= cuts[(lam_m, _fi, nm, B)])

                            s, e, iv, a, _tr, _seen = run_clip(
                                dv, rs, T, thc["alarm"][far], thc["dismiss"][P["q"]],
                                thd["alarm"][far], thd["dismiss"][P["q"]], thd["trig"][trig],
                                P["k"], P["lmax"], P["c"], d_dev, d_cloud, decide)
                            streams[clip], eps[clip], invs[clip], al[clip] = s, e, iv, a
                            admitted[clip] = (sum(1 for x in e if x["admitted"]), len(e))
                        return streams, eps, invs, al, admitted

                    def summarise(streams, eps, invs, al, admitted, with_ap=True, ci=True):
                        nad = sum(v[0] for v in admitted.values())
                        nep = sum(v[1] for v in admitted.values())
                        inv_all = sum(invs.values())
                        secs = (pos_seconds + neg_seconds) / 3600.0
                        apos = sum(1 for c in pos_clips if al[c])
                        nfa = sum(len(al[c]) for c in neg_clips)
                        d = dict(
                            episodes=nep, admitted=nad,
                            realized_admitted_fraction=(nad / nep if nep else None),
                            invocations=inv_all,
                            invocations_per_clip_hour=inv_all / secs,
                            gpu_seconds=gpu_s(rmodel, rn, inv_all),
                            gpu_seconds_per_clip_hour=gpu_s(rmodel, rn, inv_all) / secs,
                            fraction_positive_alarmed=apos / len(pos_clips),
                            false_alarm_events_negative=nfa,
                            false_alarms_per_clip_hour=nfa / (neg_seconds / 3600.0))
                        if with_ap and ci:
                            ap = ap_all(streams)
                            d["ap"] = {h: dict(ap=v["ap"], ci=v["ci"]) for h, v in ap.items()}
                            d["_boot"] = {h: ap[h]["boot"] for h in HORIZONS}
                        elif with_ap:
                            d["ap"] = ap_point(streams)
                        return d

                    cellset = {}
                    IS_PRIMARY = (far == 0.05 and trig == 0.20 and st == "measured@25")
                    for B in list(BUDGETS) + [CONTROL_BUDGET]:
                        for nm in POLICIES:
                            if nm == "P-random":
                                accs, bo = [], None
                                for sd in range(N_RANDOM_SEEDS):
                                    o = summarise(*policy_run(nm, B, rseed=sd), ci=IS_PRIMARY)
                                    accs.append(o)
                                    bo = o if bo is None else bo
                                d = dict(bo)
                                for fld in ("invocations", "invocations_per_clip_hour",
                                            "gpu_seconds", "gpu_seconds_per_clip_hour",
                                            "fraction_positive_alarmed",
                                            "false_alarms_per_clip_hour", "admitted", "episodes",
                                            "realized_admitted_fraction"):
                                    vals = [a[fld] for a in accs if a[fld] is not None]
                                    d[fld] = float(np.mean(vals)) if vals else None
                                d["ap"] = {h: dict(
                                    ap=float(np.mean([a["ap"][h]["ap"] for a in accs])),
                                    ci=([float(np.mean([a["ap"][h]["ci"][0] for a in accs])),
                                         float(np.mean([a["ap"][h]["ci"][1] for a in accs]))]
                                        if IS_PRIMARY else None)) for h in HORIZONS}
                                if IS_PRIMARY:
                                    d["_boot"] = {h: np.mean([a["_boot"][h] for a in accs], axis=0)
                                                  for h in HORIZONS}
                                d["n_seeds"] = N_RANDOM_SEEDS
                            else:
                                d = summarise(*policy_run(nm, B), ci=IS_PRIMARY)
                            d.update(policy=nm, budget=B, resolver=f"{rmodel}_N{rn}", latency=st,
                                     alarm_fpr=far, trigger_rate=trig)
                            cellset[(nm, B)] = d
                    # paired contrasts against P-score and P-random
                    for (nm, B), d in cellset.items():
                        for ref in ("P-score", "P-random"):
                            if nm == ref or "_boot" not in d or "_boot" not in cellset[(ref, B)]:
                                continue
                            rb = cellset[(ref, B)]
                            dd = {}
                            for h in HORIZONS:
                                diff = d["_boot"][h] - rb["_boot"][h]
                                dd[h] = dict(
                                    diff=float(d["ap"][h]["ap"] - rb["ap"][h]["ap"]),
                                    ci=[float(np.percentile(diff, 2.5)),
                                        float(np.percentile(diff, 97.5))])
                            d[f"vs_{ref}"] = dd
                            d[f"gpu_ratio_vs_{ref}"] = (
                                d["gpu_seconds"] / rb["gpu_seconds"] if rb["gpu_seconds"] else None)
                    for (nm, B), d in cellset.items():
                        d.pop("_boot", None)
                        res["cells"][f"{key_base}|B{int(B*100)}|{nm}"] = d
                    sweep += 1
                    print("  swept", key_base, "cells", len(res['cells']), flush=True)

                    # ---- lambda sensitivity and control (b), primary configuration only
                    if (far == 0.05 and trig == 0.20 and st == "measured@25"):
                        sens = {}
                        for lam_m in LAMBDA_MULT:
                            for B in BUDGETS:
                                for nm in ("P-trajectory", "P-trajectory-work"):
                                    o = summarise(*policy_run(nm, B, lam_m=lam_m))
                                    o.pop("_boot", None)
                                    sens[f"lam{lam_m}|B{int(B*100)}|{nm}"] = dict(
                                        ap={h: o["ap"][h]["ap"] for h in HORIZONS},
                                        gpu_seconds_per_clip_hour=o["gpu_seconds_per_clip_hour"],
                                        realized_admitted_fraction=o["realized_admitted_fraction"])
                        res.setdefault("lambda_sensitivity", {})[key_base] = sens
                        ctb = {}
                        for B in BUDGETS:
                            o = summarise(*policy_run("P-trajectory", B, shuffle=True))
                            o.pop("_boot", None)
                            ctb[f"B{int(B*100)}"] = dict(
                                ap={h: o["ap"][h]["ap"] for h in HORIZONS},
                                realized_admitted_fraction=o["realized_admitted_fraction"],
                                gpu_seconds_per_clip_hour=o["gpu_seconds_per_clip_hour"],
                                ap_P_random={h: res["cells"][f"{key_base}|B{int(B*100)}|P-random"]["ap"][h]["ap"]
                                             for h in HORIZONS},
                                ap_P_trajectory={h: res["cells"][f"{key_base}|B{int(B*100)}|P-trajectory"]["ap"][h]["ap"]
                                                 for h in HORIZONS})
                        res["controls"].setdefault("b_shuffle_features_within_fold", dict(
                            description="each trigger's feature vector is replaced by one drawn "
                                        "uniformly from that fold's pool of trigger feature "
                                        "vectors (seed 0), which breaks the feature-label "
                                        "association while preserving the marginal feature "
                                        "distribution. Labels, cutoff procedure and budget are "
                                        "unchanged. P-trajectory must fall to P-random's level.",
                            cells={}))["cells"][key_base] = ctb

                        # ---- instrumented trigger trace
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
                                    trigger_second=r["t"],
                                    rel_event_s=round(r["t"] - meta[pick]["event"], 3),
                                    features={n: round(v, 4) for n, v in zip(FEATNAMES, r["features"])},
                                    predicted_benefit_gt0=round(float(pb[j]), 4),
                                    predicted_work=round(float(wp[j]), 3),
                                    rank_score_P_score=round(r["features"][0], 4),
                                    rank_score_P_trajectory=round(float(pb[j]), 4),
                                    rank_score_P_trajectory_work=round(float(pb[j] / wp[j]), 6),
                                    true_benefit=r["benefit"][1.0], true_work=r["work"],
                                    admit_path=dict(outcome=r["admit_outcome"],
                                                    alarm_t=r["admit_alarm_t"],
                                                    invocations=r["admit_inv"]),
                                    local_path=dict(outcome=r["local_outcome"],
                                                    alarm_t=r["local_alarm_t"], invocations=0),
                                    admitted_at={f"B{int(B*100)}": bool(
                                        float(pb[j]) >= cuts[(1.0, fi, 'P-trajectory', B)])
                                        for B in BUDGETS}))
                            res["trace_example"] = dict(
                                cell=key_base, clip=pick, label=meta[pick]["label"],
                                event_s=meta[pick]["event"], duration_s=meta[pick]["dur"],
                                fold=fi, d_device_s=d_dev, d_cloud_s=d_cloud,
                                tau_trigger=round(tau[(DEVICE, fi)]["trig"][trig], 4),
                                tau_alarm_cloud=round(tau[((rmodel, rn), fi)]["alarm"][far], 4),
                                tau_alarm_device=round(tau[(DEVICE, fi)]["alarm"][far], 4),
                                cutoffs={f"B{int(B*100)}": round(cuts[(1.0, fi, 'P-trajectory', B)], 6)
                                         for B in BUDGETS},
                                lambda_value=LAMBDA, h_star=H_STAR, triggers=rows)

    # ---------------- negative control (a): budget 1.0 ----------------
    nca = {}
    for k in list(res["cells"]):
        if "|B100|" not in k:
            continue
        base = k.rsplit("|", 1)[0]
        nm = k.rsplit("|", 1)[1]
        ref = res["cells"][f"{base}|admit-all"]
        d = res["cells"][k]
        h0 = HORIZONS[0]
        same = (abs(d["ap"][h0]["ap"] - ref["ap"][h0]["ap"]) < 1e-12
                and d["invocations"] == ref["invocations"]
                and abs(d["fraction_positive_alarmed"] - ref["fraction_positive_alarmed"]) < 1e-12
                and abs(d["false_alarms_per_clip_hour"] - ref["false_alarms_per_clip_hour"]) < 1e-9)
        nca[f"{base}|{nm}"] = bool(same)
    res["controls"]["a_budget_1_equals_admit_all"] = dict(
        description="At budget 1.0 every policy must equal admit-all exactly (AP at h=0, "
                    "invocations, fraction of positives alarmed, false alarms per clip-hour).",
        cells_checked=len(nca), all_equal=all(nca.values()),
        mismatches=[k for k, v in nca.items() if not v])

    res["_provenance"] = stamp(script="study_e12_admission.py", model=None, device="cpu",
                               n=len(clips), args=None)
    (OUT / "e12_results.json").write_text(json.dumps(res, indent=1))
    print("cells:", len(res["cells"]), "sweeps:", sweep)


if __name__ == "__main__":
    main()
