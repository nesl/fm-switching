#!/usr/bin/env python3
"""StudyE9-episodes — device-triggered cloud escalation, offline replay of StudyD14 score traces.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
`results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz`; every latency and byte count is read
from a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 measurement.

Predictive quality is the Nexar metric (StudyE5 Part G): AP at fixed horizons on CONTINUOUS scores
(log P(Yes)). Literal Yes/No answers are never used; alarm, dismiss and trigger are thresholds on
the continuous score.
"""
import collections, gzip, json, math, os, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9"
TRACE = ROOT / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz"
SEED, NB, NFOLD = 0, 2000, 2
HORIZONS = (0.0, 0.5, 1.0, 1.5, 2.0)
MISSING = -1e9

DEVICE = ("4BI", 1)
RESOLVERS_32B = [("32BI", 1), ("32BI", 3), ("32BI", 9)]
RESOLVER_4B = ("4BI", 1)

ALARM_FPR = (0.01, 0.05, 0.10)
DISMISS_Q = (0.50, 0.75)
TRIG_RATE = (0.05, 0.10, 0.20, 0.40)
K_CONSEC = (1, 2, 3)
L_MAX = (5, 10, 20)
COOLDOWN = (0, 2)
PRIMARY = dict(k=2, q=0.75, lmax=10, c=0)

# ---- committed measurements -------------------------------------------------
FRAME_BYTES = {1: 354902, 3: 1057532, 9: 3188243}      # StudyD4 median PNG bytes per request
FRAME_BYTES_JPEG = {1: 59601, 3: 177773, 9: 529361}    # StudyD4 JPEG q90 bytes per request
UPLINK_BPS = 13.6e6 / 8.0
RTT_S = 0.044
DEV_LAT_S = 0.567                                       # StudyD8 arm A, sustained 1 Hz N=1, total p50
DEV_LAT_N3_S = 1.394                                    # StudyD4-orin Part A, N=3 total p50 (SECONDARY)
CLOUD_TTFT = {                                          # open-loop TTFT p50 from scheduled arrival
    ("32BI", 1, 25): 0.1422, ("32BI", 1, 75): 0.2976,   # StudyD7b
    ("32BI", 3, 25): 0.2643, ("32BI", 3, 75): 0.5915,   # StudyD7
    ("32BI", 9, 25): 0.6347, ("32BI", 9, 75): 1.9803,   # StudyD7
    ("4BI", 1, 25): 0.0827, ("4BI", 1, 75): 0.1359,     # StudyD7b
}
PREFILL_TOK_S = {"32BI": 5600.0, "4BI": 29500.0}        # saturated prefill, StudyD7 / D7b
PROMPT_TOK = {1: 378, 3: 1062, 9: 3090}                 # StudyD3 / D4 / D14


def upload_s(n):
    return UPLOAD_BYTES[n] / UPLINK_BPS


def cloud_delay_s(model, n, load_pct):
    return RTT_S + upload_s(n) + CLOUD_TTFT[(model, n, load_pct)]


LATENCY_SETTINGS = ["zero", "measured@25", "measured@75"]
UPLOAD_BYTES = FRAME_BYTES
OUTFILE = "e9_results.json"

# Latency setting (iii), JPEG upload: SENSITIVITY ONLY. Model scores are unchanged (they are the
# PNG scores); only the upload time, hence d_cloud, changes. JPEG accuracy parity is pending
# StudyE10a. Setting (i) and (ii) numbers are never recomputed here: this mode writes its own file.
JPEG_MODE = "--jpeg" in sys.argv
if JPEG_MODE:
    UPLOAD_BYTES = FRAME_BYTES_JPEG
    LATENCY_SETTINGS = ["jpeg@25", "jpeg@75"]
    DISMISS_Q = (PRIMARY["q"],)
    K_CONSEC = (PRIMARY["k"],)
    L_MAX = (PRIMARY["lmax"],)
    COOLDOWN = (PRIMARY["c"],)
    OUTFILE = "e9_results_jpeg.json"


def delays(setting, model, n):
    """(d_device, d_cloud) in whole seconds; d = ceil(latency)."""
    if setting == "zero":
        return 0, 0
    load = 25 if setting.endswith("25") else 75
    return math.ceil(DEV_LAT_S), math.ceil(cloud_delay_s(model, n, load))


# ---- data -------------------------------------------------------------------
def load():
    sc = collections.defaultdict(dict)
    meta = {}
    for ln in gzip.open(TRACE, "rt"):
        r = json.loads(ln)
        arm, clip, t = (r["model"], int(r["n"])), r["file_name"], int(r["t"])
        sc[arm].setdefault(clip, {})[t] = float(r["score"])
        if clip not in meta:
            meta[clip] = dict(label=r["label"], event=r["time_of_event"], dur=r["duration_s"])
    clips = sorted(meta)
    arrs = {}
    for arm, per in sc.items():
        a = {}
        for clip, d in per.items():
            ts = sorted(d)
            assert ts == list(range(3, ts[-1] + 1)), (arm, clip)   # STOP if seconds are missing
            a[clip] = np.array([d[t] for t in ts])                 # index 0 == t = 3
        arrs[arm] = a
    for c in clips:
        meta[c]["T"] = 3 + len(arrs[DEVICE][c]) - 1
    return arrs, meta, clips


# ---- thresholds -------------------------------------------------------------
def folds(clips, meta):
    rng = np.random.default_rng(SEED)
    f = {}
    for lab in ("positive", "negative"):
        g = [c for c in clips if meta[c]["label"] == lab]
        idx = rng.permutation(len(g))
        for j, i in enumerate(idx):
            f[g[i]] = j % NFOLD
    return f


def fit_thresholds(arrs, meta, clips, fold):
    """tau[(arm, fold)] -> dict of thresholds fitted on the OTHER fold's negative seconds."""
    tau = {}
    for arm in arrs:
        for fi in range(NFOLD):
            tr = np.concatenate([arrs[arm][c] for c in clips
                                 if meta[c]["label"] == "negative" and fold[c] != fi])
            assert len(tr) > 100, (arm, fi, len(tr))   # STOP if a fold cannot be fitted
            tau[(arm, fi)] = dict(
                alarm={f: float(np.quantile(tr, 1.0 - f)) for f in ALARM_FPR},
                dismiss={q: float(np.quantile(tr, q)) for q in DISMISS_Q},
                trig={r: float(np.quantile(tr, 1.0 - r)) for r in TRIG_RATE},
                n_train_neg_seconds=int(len(tr)))
    return tau


# ---- episode simulation -----------------------------------------------------
def simulate(dev, res, T, t_alarm_thr, t_dismiss_thr, t_trig, k, lmax, c, d_dev, d_cloud):
    """One clip. dev/res are score arrays indexed from t = 3. Returns stream and episodes."""
    n = T - 3 + 1
    stream = np.full(n, MISSING)
    src = np.zeros(n, dtype=np.int8)          # 0 device, 1 resolver, 2 nothing available
    episodes, invocations = [], 0
    open_, t0, drun, cool_until = False, None, 0, -10**9
    for t in range(3, T + 1):
        i = t - 3
        if not open_ and t >= cool_until:
            u = t - d_dev
            if u >= 3 and dev[u - 3] >= t_trig:
                open_, t0, drun = True, t, 0
        got = False
        outcome = None
        if open_:
            u = t - d_cloud
            if u >= t0:
                s = res[u - 3]
                stream[i], src[i], got = s, 1, True
                if s >= t_alarm_thr:
                    outcome = "alarm"
                else:
                    drun = drun + 1 if s < t_dismiss_thr else 0
                    if drun >= k:
                        outcome = "dismiss"
        if not got:
            u = t - d_dev
            if u >= 3:
                stream[i], src[i] = dev[u - 3], 0
            else:
                src[i] = 2
        if open_ and outcome is None and (t - t0 + 1) >= lmax:
            outcome = "cap"
        if open_ and outcome is None and t == T:
            outcome = "clip_end"
        if open_ and outcome is not None:
            inv = t - t0 + 1
            invocations += inv
            episodes.append(dict(t0=t0, t_close=t, outcome=outcome, invocations=inv))
            open_, t0, drun = False, None, 0
            cool_until = t + 1 + c
    return stream, src, episodes, invocations


def baseline_stream(arr, T, d):
    n = T - 3 + 1
    s = np.full(n, MISSING)
    for t in range(3, T + 1):
        u = t - d
        if u >= 3:
            s[t - 3] = arr[u - 3]
    return s


def upcrossings(stream, thr):
    """Distinct alarm events: seconds at or above thr whose predecessor was below."""
    a = stream >= thr
    if not a.any():
        return []
    idx = np.where(a & ~np.concatenate(([False], a[:-1])))[0]
    return list(idx)


# ---- AP ---------------------------------------------------------------------
def ap_from(pos, neg):
    y = np.concatenate([np.ones(len(pos)), np.zeros(len(neg))])
    s = np.concatenate([pos, neg])
    o = np.argsort(-s, kind="mergesort")
    y = y[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / max(y.sum(), 1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    arrs, meta, clips = load()
    fold = folds(clips, meta)
    tau = fit_thresholds(arrs, meta, clips, fold)
    pos_clips = [c for c in clips if meta[c]["label"] == "positive"]
    neg_clips = [c for c in clips if meta[c]["label"] == "negative"]
    neg_seconds = sum(meta[c]["T"] - 2 for c in neg_clips)
    pos_seconds = sum(meta[c]["T"] - 2 for c in pos_clips)
    assert neg_seconds == 5196, neg_seconds

    # shared bootstrap resamples (stratified by label, clip-level), used by every cell
    rng = np.random.default_rng(SEED)
    boots = [(rng.integers(0, len(pos_clips), len(pos_clips)),
              rng.integers(0, len(neg_clips), len(neg_clips))) for _ in range(NB)]

    def target_index(c, h):
        T = meta[c]["T"]
        return int(min(max(round(meta[c]["event"] - h), 3), T)) - 3

    neg_len = None
    neg_take = None

    def ap_all(streams):
        """AP and CI at every horizon for one policy's per-clip streams.
        One negative resample is built per bootstrap draw and shared by all five horizons."""
        nonlocal neg_len, neg_take
        P = [np.array([streams[c][target_index(c, h)] for c in pos_clips]) for h in HORIZONS]
        Ncat = np.concatenate([streams[c] for c in neg_clips])
        if neg_len is None:
            neg_len = np.array([len(streams[c]) for c in neg_clips])
            off = np.concatenate([[0], np.cumsum(neg_len)])
            neg_take = [np.concatenate([np.arange(off[j], off[j + 1]) for j in ni])
                        for _, ni in boots]
        pts = [ap_from(P[i], Ncat) for i in range(len(HORIZONS))]
        bs = np.empty((len(HORIZONS), NB))
        for b, (pi, _ni) in enumerate(boots):
            nn = Ncat[neg_take[b]]
            for i in range(len(HORIZONS)):
                bs[i, b] = ap_from(P[i][pi], nn)
        return {h: dict(ap=pts[i],
                        ci=[float(np.percentile(bs[i], 2.5)), float(np.percentile(bs[i], 97.5))],
                        boot=bs[i].copy())
                for i, h in enumerate(HORIZONS)}

    res = dict(
        label="StudyE9-episodes: OFFLINE ANALYSIS OF COMMITTED RESULTS (StudyD14 traces). CPU only on "
              "flash; no GPU, no model server, no inference. Scores are continuous log P(Yes); no "
              "literal Yes/No answer is used anywhere.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB,
        horizons=list(HORIZONS), primary_config=PRIMARY,
        n_clips=dict(positive=len(pos_clips), negative=len(neg_clips)),
        seconds=dict(positive=pos_seconds, negative=neg_seconds),
        base_rate=len(pos_clips) / (len(pos_clips) + neg_seconds),
        latency_components={}, thresholds={}, cells={}, baselines={}, controls={}, trace_example=None)

    for st in LATENCY_SETTINGS:
        for model, n in RESOLVERS_32B + [RESOLVER_4B]:
            dd, dc = delays(st, model, n)
            res["latency_components"][f"{st}/{model}_N{n}"] = dict(
                device_latency_s=(0.0 if st == "zero" else DEV_LAT_S), d_device_s=dd,
                rtt_s=(0.0 if st == "zero" else RTT_S),
                upload_s=(0.0 if st == "zero" else upload_s(n)),
                server_ttft_s=(0.0 if st == "zero" else CLOUD_TTFT[(model, n, 25 if st.endswith("25") else 75)]),
                cloud_latency_s=(0.0 if st == "zero" else cloud_delay_s(model, n, 25 if st.endswith("25") else 75)),
                d_cloud_s=dc)
    for (arm, fi), v in tau.items():
        res["thresholds"][f"{arm[0]}_N{arm[1]}/fold{fi}"] = {k2: v2 for k2, v2 in v.items()}

    def gpu_s(model, n, inv):
        return inv * PROMPT_TOK[n] / PREFILL_TOK_S[model]

    def episode_stats(per_clip_eps, per_clip_inv, model, n, far):
        """Aggregate episode outcomes and cloud work over clips, split by label."""
        o = {}
        for lab, cl in (("positive", pos_clips), ("negative", neg_clips)):
            eps = [e for c in cl for e in per_clip_eps[c]]
            inv = sum(per_clip_inv[c] for c in cl)
            secs = sum(meta[c]["T"] - 2 for c in cl)
            cnt = collections.Counter(e["outcome"] for e in eps)
            o[lab] = dict(
                episodes=len(eps), episodes_per_clip=len(eps) / len(cl),
                outcomes={k2: cnt.get(k2, 0) for k2 in ("alarm", "dismiss", "cap", "clip_end")},
                invocations=inv, invocations_per_clip_hour=inv / (secs / 3600.0),
                gpu_seconds=gpu_s(model, n, inv),
                gpu_seconds_per_clip_hour=gpu_s(model, n, inv) / (secs / 3600.0),
                invocations_per_episode=(inv / len(eps) if eps else None),
                episode_length_s_mean=(float(np.mean([e["t_close"] - e["t0"] + 1 for e in eps]))
                                       if eps else None),
                re_escalations_per_clip=sum(max(0, len(per_clip_eps[c]) - 1) for c in cl) / len(cl))
        fd = 0
        for c in pos_clips:
            ev = meta[c]["event"]
            for e in per_clip_eps[c]:
                if e["outcome"] in ("dismiss", "cap") and e["t_close"] < ev:
                    fd += 1
        o["false_dismissals_positive_before_event"] = fd
        o["first_trigger_to_final_resolution_s"] = None
        spans = []
        for c in clips:
            e = per_clip_eps[c]
            if e:
                spans.append(e[-1]["t_close"] - e[0]["t0"] + 1)
        if spans:
            o["first_trigger_to_final_resolution_s"] = dict(
                mean=float(np.mean(spans)), p50=float(np.median(spans)), max=int(max(spans)))
        return o

    def alarm_stats(alarm_t, lab_clips_pos, n_alarm_events_neg):
        rel = []
        for c in lab_clips_pos:
            t = alarm_t.get(c)
            if t is not None:
                rel.append(t - meta[c]["event"])
        out = dict(n_positive_alarmed=len(rel),
                   fraction_positive_alarmed=len(rel) / len(pos_clips),
                   alarm_rel_event_s=(dict(p50=float(np.median(rel)), p25=float(np.percentile(rel, 25)),
                                           p75=float(np.percentile(rel, 75))) if rel else None),
                   fraction_alarmed_by_horizon={})
        for h in HORIZONS:
            out["fraction_alarmed_by_horizon"][h] = sum(
                1 for c in lab_clips_pos if alarm_t.get(c) is not None
                and alarm_t[c] <= meta[c]["event"] - h) / len(pos_clips)
        out["false_alarms_per_clip_hour"] = n_alarm_events_neg / (neg_seconds / 3600.0)
        out["false_alarm_events_negative"] = n_alarm_events_neg
        return out

    # ---------------- baselines: device-only and always-cloud ----------------
    for st in LATENCY_SETTINGS:
        for model, n in [DEVICE] + RESOLVERS_32B:
            name = "device-only" if (model, n) == DEVICE else f"always-cloud/{model}_N{n}"
            dd, dc = delays(st, model, n)
            d = dd if (model, n) == DEVICE else dc
            streams = {c: baseline_stream(arrs[(model, n)][c], meta[c]["T"], d) for c in clips}
            for far in ALARM_FPR:
                at, nev = {}, 0
                for c in clips:
                    thr = tau[((model, n), fold[c])]["alarm"][far]
                    up = upcrossings(streams[c], thr)
                    if meta[c]["label"] == "positive":
                        if up:
                            at[c] = up[0] + 3
                    else:
                        nev += len(up)
                secs = pos_seconds + neg_seconds
                inv = 0 if (model, n) == DEVICE else sum(meta[c]["T"] - 2 for c in clips)
                key = f"{name}|{st}|far{int(far*100)}"
                ap = ap_all(streams)
                res["baselines"][key] = dict(
                    policy=name, latency=st, alarm_fpr=far,
                    ap={h: dict(ap=v["ap"], ci=v["ci"]) for h, v in ap.items()},
                    alarms=alarm_stats(at, pos_clips, nev),
                    cloud=dict(invocations=inv,
                               invocations_per_clip_hour=inv / (secs / 3600.0),
                               gpu_seconds=(0.0 if inv == 0 else gpu_s(model, n, inv)),
                               gpu_seconds_per_clip_hour=(0.0 if inv == 0 else
                                                          gpu_s(model, n, inv) / (secs / 3600.0))))
                res["baselines"][key]["_boot"] = {h: ap[h]["boot"] for h in HORIZONS}

    print("baselines done:", len(res["baselines"]), flush=True)

    # ---------------- escalation sweep ----------------
    def run_cell(rmodel, rn, st, far, q, trig, k, lmax, c, shuffle=False):
        dd, dc = delays(st, rmodel, rn)
        streams, eps, inv, at, nev = {}, {}, {}, {}, 0
        rng_s = np.random.default_rng(SEED)
        for clip in clips:
            T = meta[clip]["T"]
            dv = arrs[DEVICE][clip]
            rs = arrs[(rmodel, rn)][clip]
            if shuffle:
                rs = rs[rng_s.permutation(len(rs))]
            th = tau[((rmodel, rn), fold[clip])]
            s, _src, e, iv = simulate(dv, rs, T, th["alarm"][far], th["dismiss"][q],
                                      tau[(DEVICE, fold[clip])]["trig"][trig],
                                      k, lmax, c, dd, dc)
            streams[clip], eps[clip], inv[clip] = s, e, iv
            if meta[clip]["label"] == "positive":
                a = [x for x in e if x["outcome"] == "alarm"]
                if a:
                    at[clip] = a[0]["t_close"]
            else:
                nev += sum(1 for x in e if x["outcome"] == "alarm")
        return streams, eps, inv, at, nev

    def pack(rmodel, rn, st, far, q, trig, k, lmax, c, with_ap, shuffle=False):
        streams, eps, inv, at, nev = run_cell(rmodel, rn, st, far, q, trig, k, lmax, c, shuffle)
        d = dict(resolver=f"{rmodel}_N{rn}", latency=st, alarm_fpr=far, dismiss_q=q,
                 trigger_rate=trig, k=k, l_max=lmax, cooldown=c,
                 episodes=episode_stats(eps, inv, rmodel, rn, far),
                 alarms=alarm_stats(at, pos_clips, nev),
                 invocations_per_clip={cl: inv[cl] for cl in clips})
        if with_ap:
            ap = ap_all(streams)
            d["ap"] = {h: dict(ap=v["ap"], ci=v["ci"]) for h, v in ap.items()}
            d["_boot"] = {h: ap[h]["boot"] for h in HORIZONS}
        return d, streams, eps

    P = PRIMARY
    sweep_count = 0
    for st in LATENCY_SETTINGS:
        for rmodel, rn in RESOLVERS_32B + [RESOLVER_4B]:
            pol = "escalation-32B" if rmodel == "32BI" else "escalation-4B"
            for far in ALARM_FPR:
                for trig in TRIG_RATE:
                    for q in DISMISS_Q:
                        for k in K_CONSEC:
                            for lmax in L_MAX:
                                for c in COOLDOWN:
                                    primary = (q == P["q"] and k == P["k"]
                                               and lmax == P["lmax"] and c == P["c"])
                                    d, _s, _e = pack(rmodel, rn, st, far, q, trig, k, lmax, c,
                                                     with_ap=primary)
                                    d["policy"] = pol
                                    d["is_primary_config"] = primary
                                    key = (f"{pol}|{rmodel}_N{rn}|{st}|far{int(far*100)}|"
                                           f"trig{int(trig*100)}|q{int(q*100)}|k{k}|L{lmax}|c{c}")
                                    res["cells"][key] = d
                                    sweep_count += 1
        print("swept latency setting", st, "cells so far", sweep_count, flush=True)

    # ---------------- negative controls ----------------
    # (a) 32B resolver scores replaced by 4B N1 scores, with 4B N1 thresholds and 4B N1 cloud
    #     latency: the result must be escalation-4B exactly.
    ctrl_a = {}
    for st in LATENCY_SETTINGS:
        for far in ALARM_FPR:
            for trig in TRIG_RATE:
                d, _s, _e = pack("4BI", 1, st, far, P["q"], trig, P["k"], P["lmax"], P["c"], False)
                ref = res["cells"][(f"escalation-4B|4BI_N1|{st}|far{int(far*100)}|"
                                    f"trig{int(trig*100)}|q{int(P['q']*100)}|k{P['k']}|"
                                    f"L{P['lmax']}|c{P['c']}")]
                same = (d["episodes"]["positive"]["invocations"] == ref["episodes"]["positive"]["invocations"]
                        and d["episodes"]["negative"]["invocations"] == ref["episodes"]["negative"]["invocations"]
                        and d["alarms"]["n_positive_alarmed"] == ref["alarms"]["n_positive_alarmed"]
                        and d["alarms"]["false_alarm_events_negative"] == ref["alarms"]["false_alarm_events_negative"])
                ctrl_a[f"{st}|far{int(far*100)}|trig{int(trig*100)}"] = bool(same)
    res["controls"]["a_swap_resolver_to_4B"] = dict(
        description="escalation-32B's code path run with 4B N1 resolver scores, 4B N1 thresholds and "
                    "4B N1 cloud latency must equal escalation-4B exactly.",
        cells_checked=len(ctrl_a), all_equal=all(ctrl_a.values()),
        mismatches=[k for k, v in ctrl_a.items() if not v])

    # (b) resolver scores shuffled across seconds within each clip
    ctrl_b = {}
    for st in LATENCY_SETTINGS:
        for rmodel, rn in RESOLVERS_32B:
            for far in (0.05,):
                for trig in (0.20,):
                    d, _s, _e = pack(rmodel, rn, st, far, P["q"], trig, P["k"], P["lmax"], P["c"],
                                     with_ap=True, shuffle=True)
                    key = (f"escalation-32B|{rmodel}_N{rn}|{st}|far{int(far*100)}|"
                           f"trig{int(trig*100)}|q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}")
                    base = res["cells"][key]
                    ctrl_b[f"{rmodel}_N{rn}|{st}"] = dict(
                        ap_shuffled={h: d["ap"][h]["ap"] for h in HORIZONS},
                        ap_real={h: base["ap"][h]["ap"] for h in HORIZONS})
    res["controls"]["b_shuffle_resolver_within_clip"] = dict(
        description="resolver scores permuted across seconds within each clip (alarm FPR 5%, trigger "
                    "20%, primary config). AP at h <= 1 s must fall toward the base rate.",
        base_rate=res["base_rate"], cells=ctrl_b)

    # ---------------- one instrumented episode trace ----------------
    st, rmodel, rn, far, trig = "measured@25", "32BI", 1, 0.05, 0.20
    dd, dc = delays(st, rmodel, rn)
    pick = None
    for clip in pos_clips:
        T = meta[clip]["T"]
        th = tau[((rmodel, rn), fold[clip])]
        s, src, e, iv = simulate(arrs[DEVICE][clip], arrs[(rmodel, rn)][clip], T,
                                 th["alarm"][far], th["dismiss"][P["q"]],
                                 tau[(DEVICE, fold[clip])]["trig"][trig],
                                 P["k"], P["lmax"], P["c"], dd, dc)
        fd = [x for x in e if x["outcome"] in ("dismiss", "cap") and x["t_close"] < meta[clip]["event"]]
        if fd and len(e) > 1:
            pick = (clip, s, src, e, iv)
            break
    if pick:
        clip, s, src, e, iv = pick
        T = meta[clip]["T"]
        th = tau[((rmodel, rn), fold[clip])]
        rows = []
        for t in range(3, T + 1):
            i = t - 3
            rows.append(dict(
                t=t, rel_event_s=round(t - meta[clip]["event"], 3),
                device_score_seen=(None if t - dd < 3 else round(float(arrs[DEVICE][clip][t - dd - 3]), 4)),
                device_frame_second=(t - dd if t - dd >= 3 else None),
                resolver_score_seen=(round(float(s[i]), 4) if src[i] == 1 else None),
                resolver_frame_second=(t - dc if src[i] == 1 else None),
                stream_score=(None if s[i] == MISSING else round(float(s[i]), 4)),
                stream_source=("resolver" if src[i] == 1 else ("device" if src[i] == 0 else "none")),
                episode_open=any(x["t0"] <= t <= x["t_close"] for x in e)))
        res["trace_example"] = dict(
            clip=clip, label=meta[clip]["label"], event_s=meta[clip]["event"], duration_s=meta[clip]["dur"],
            resolver=f"{rmodel}_N{rn}", latency=st, d_device_s=dd, d_cloud_s=dc,
            tau_trigger=round(tau[(DEVICE, fold[clip])]["trig"][trig], 4),
            tau_alarm=round(th["alarm"][far], 4), tau_dismiss=round(th["dismiss"][P["q"]], 4),
            k=P["k"], l_max=P["lmax"], cooldown=P["c"],
            episodes=e, total_invocations=iv,
            gpu_seconds=round(gpu_s(rmodel, rn, iv), 4), seconds=rows)

    # ---------------- paired decision-rule contrasts ----------------
    def paired_inv_ci(a_cell, b_cell, group):
        cl = pos_clips if group == "positive" else (neg_clips if group == "negative" else clips)
        secs = sum(meta[c]["T"] - 2 for c in cl) / 3600.0
        da = np.array([a_cell["invocations_per_clip"][c] for c in cl], dtype=float)
        db = np.array([b_cell["invocations_per_clip"][c] for c in cl], dtype=float)
        sec_each = np.array([meta[c]["T"] - 2 for c in cl], dtype=float)
        diff = (da.sum() - db.sum()) / secs
        rng2 = np.random.default_rng(SEED)
        J = rng2.integers(0, len(cl), (NB, len(cl)))
        bs = (da[J].sum(1) - db[J].sum(1)) / (sec_each[J].sum(1) / 3600.0)
        return dict(diff_per_clip_hour=float(diff),
                    ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])

    rule1 = {}
    for st in LATENCY_SETTINGS:
        for rmodel, rn in RESOLVERS_32B:
            for far in ALARM_FPR:
                for trig in TRIG_RATE:
                    suff = (f"{st}|far{int(far*100)}|trig{int(trig*100)}|q{int(P['q']*100)}|"
                            f"k{P['k']}|L{P['lmax']}|c{P['c']}")
                    a = res["cells"][f"escalation-32B|{rmodel}_N{rn}|{suff}"]
                    b = res["cells"][f"escalation-4B|4BI_N1|{suff}"]
                    rule1[f"{rmodel}_N{rn}|{suff}"] = dict(
                        all=paired_inv_ci(a, b, "all"),
                        positive=paired_inv_ci(a, b, "positive"),
                        negative=paired_inv_ci(a, b, "negative"),
                        inv_32B_per_clip_hour=a["episodes"]["positive"]["invocations_per_clip_hour"],
                        inv_4B_per_clip_hour=b["episodes"]["positive"]["invocations_per_clip_hour"])
    res["decision_rule_1_capability_shortens_episodes"] = rule1

    # ---------------- AP-curve horizon shift, 32B vs 4B ----------------
    def shift(boot32, boot4, ap32, ap4):
        hs = np.array(HORIZONS)

        def one(a32, a4):
            out = {}
            for i, h in enumerate(hs):
                y = a4[i]
                g = a32
                j = np.where(g <= y)[0]
                if len(j) == 0:
                    out[h] = float(hs[-1] - h)
                    continue
                j0 = j[0]
                if j0 == 0:
                    out[h] = float(hs[0] - h)
                    continue
                x0, x1, y0, y1 = hs[j0 - 1], hs[j0], g[j0 - 1], g[j0]
                hh = x0 + (y0 - y) * (x1 - x0) / max(y0 - y1, 1e-12)
                out[h] = float(hh - h)
            return out
        point = one(np.array([ap32[h] for h in HORIZONS]), np.array([ap4[h] for h in HORIZONS]))
        bs = {h: [] for h in HORIZONS}
        for b in range(NB):
            o = one(np.array([boot32[h][b] for h in HORIZONS]),
                    np.array([boot4[h][b] for h in HORIZONS]))
            for h in HORIZONS:
                bs[h].append(o[h])
        return {h: dict(shift_s=point[h],
                        ci=[float(np.percentile(bs[h], 2.5)), float(np.percentile(bs[h], 97.5))])
                for h in HORIZONS}

    hs_out = {}
    for st in LATENCY_SETTINGS:
        for far in ALARM_FPR:
            b4 = res["baselines"][f"device-only|{st}|far{int(far*100)}"]
            for model, n in RESOLVERS_32B:
                b32 = res["baselines"][f"always-cloud/{model}_N{n}|{st}|far{int(far*100)}"]
                hs_out[f"{model}_N{n}_vs_4BI_N1|{st}|far{int(far*100)}"] = shift(
                    b32["_boot"], b4["_boot"],
                    {h: b32["ap"][h]["ap"] for h in HORIZONS},
                    {h: b4["ap"][h]["ap"] for h in HORIZONS})
    res["ap_curve_horizon_shift"] = dict(
        note="CURVE SHIFT, NOT a per-event time: at the AP the 4B arm reaches at horizon h, this is "
             "how much further ahead the 32B arm reaches the same AP, by linear interpolation of the "
             "AP-vs-horizon curve. It says nothing about when either model first notices a given crash.",
        cells=hs_out)

    # ---------------- labelled SECONDARY: 4BI N3 as the device arm ----------------
    # The Orin CANNOT sustain N=3 at 1 Hz (StudyD4-orin: N=3 total p99 1.448 s, cadence 2 s), so a
    # 1 Hz replay of this arm is counterfactual. Reported as a labelled secondary only.
    sec = {}
    for st in LATENCY_SETTINGS:
        d_dev3 = 0 if st == "zero" else math.ceil(DEV_LAT_N3_S)
        streams = {c: baseline_stream(arrs[("4BI", 3)][c], meta[c]["T"], d_dev3) for c in clips}
        for far in ALARM_FPR:
            at, nev = {}, 0
            for c in clips:
                thr = tau[(("4BI", 3), fold[c])]["alarm"][far]
                up = upcrossings(streams[c], thr)
                if meta[c]["label"] == "positive":
                    if up:
                        at[c] = up[0] + 3
                else:
                    nev += len(up)
            ap = ap_all(streams)
            sec[f"device-only-SECONDARY/4BI_N3|{st}|far{int(far*100)}"] = dict(
                policy="device-only (SECONDARY, 4BI N3)", latency=st, alarm_fpr=far,
                d_device_s=d_dev3, device_latency_s=(0.0 if st == "zero" else DEV_LAT_N3_S),
                ap={h: dict(ap=v["ap"], ci=v["ci"]) for h, v in ap.items()},
                alarms=alarm_stats(at, pos_clips, nev))
    res["secondary_device_arm_4BI_N3"] = dict(
        note="LABELLED SECONDARY. The Jetson Orin cannot sustain 4B N=3 at 1 Hz (StudyD4-orin: N=3 "
             "total latency p99 1.448 s, so its registered cadence is 2 s). These rows replay the arm "
             "at 1 Hz anyway, which is counterfactual, and charge StudyD4-orin's measured N=3 total "
             "p50 of 1.394 s as the device latency. They are not used for any decision rule.",
        cells=sec)

    for k2 in list(res["secondary_device_arm_4BI_N3"]["cells"]):
        res["secondary_device_arm_4BI_N3"]["cells"][k2].pop("_boot", None)
    for k2 in list(res["baselines"]):
        res["baselines"][k2].pop("_boot", None)
    for k2 in list(res["cells"]):
        res["cells"][k2].pop("_boot", None)
        res["cells"][k2].pop("invocations_per_clip", None)
    res["_provenance"] = stamp(script="study_e9_episodes.py", model=None, device="cpu",
                               n=len(clips), args=("--jpeg" if JPEG_MODE else None))
    res["upload_bytes_per_request"] = dict(UPLOAD_BYTES)
    res["jpeg_sensitivity"] = JPEG_MODE
    if JPEG_MODE:
        res["label"] = ("StudyE9-episodes latency setting (iii) JPEG upload, SENSITIVITY: model "
                        "scores are the PNG scores; JPEG accuracy parity is pending StudyE10a. "
                        "Only upload time (hence d_cloud) differs from setting (ii). Primary "
                        "episode config only (k=2, q=0.75, L_max=10, c=0).")
    (OUT / OUTFILE).write_text(json.dumps(res, indent=1))
    print("cells:", len(res["cells"]), "baselines:", len(res["baselines"]))


if __name__ == "__main__":
    main()
