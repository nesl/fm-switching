#!/usr/bin/env python3
"""StudyE9b-dense — StudyE9's episode study re-run on StudyD14b's 0.25-s grid with an explicit
delivery model (sample-and-hold on measured, unrounded latency) instead of d = ceil(latency).

CPU ONLY on the flash host: no GPU, no model server, no inference. Every score is read from
`results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz`; every latency and byte count is read from
a committed StudyD4 / StudyD7 / StudyD7b / StudyD8 measurement, through study_e9_episodes.py.

Predictive quality is the Nexar metric: AP at fixed horizons on CONTINUOUS scores (log P(Yes)).
Literal Yes/No answers are never used; alarm, dismiss and trigger are thresholds on the continuous
score. AP is comparable WITHIN one grid only and is also reported as a multiple of chance.

The same code runs the dense study and control (a): with step = 1 s, 1-s cadences, delivery mode
"ceil" and the integer-t rows only, it must reproduce StudyE9's committed numbers exactly.
"""
import collections, gzip, json, math, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/dashcam"))
from _provenance import stamp  # noqa: E402
import study_e9_episodes as E9  # noqa: E402

OUT = ROOT / "results/dashcam/study_e9b"
TRACE = ROOT / "results/dashcam/study_d14b/d14b_trace_h100nvl.jsonl.gz"
D14_TRACE = ROOT / "results/dashcam/study_d14_trace/d14_trace_h100nvl.jsonl.gz"

SEED, NB, NFOLD = E9.SEED, E9.NB, E9.NFOLD
MISSING = E9.MISSING
T0 = 3.0
STEP_DENSE = 0.25
HORIZONS_DENSE = (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)

DEVICE = E9.DEVICE                       # ("4BI", 1)
RESOLVERS_32B = [("32BI", 1), ("32BI", 3)]   # StudyD14b has no N = 9 arm
RESOLVER_4B = ("4BI", 1)

ALARM_FPR = E9.ALARM_FPR                 # (0.01, 0.05, 0.10)
TRIG_RATE = E9.TRIG_RATE                 # (0.05, 0.10, 0.20, 0.40)
CADENCES = (0.25, 0.5, 1.0)
CADENCE_PRIMARY = 0.5
PRIMARY = dict(k=2, q=0.75, lmax=10, c=0)
K_SENS = (1, 2, 3)
Q_SENS = (0.50, 0.75)
SETTINGS = ("zero", "measured@25", "measured@75", "jpeg@25", "jpeg@75")
JPEG_NOTE = ("(iii) JPEG upload, SENSITIVITY: model scores are the PNG scores; JPEG accuracy parity "
             "for S-EMBER was NOT established by StudyE10a-full, and Nexar ranking parity is cited "
             "from StudyE10a only.")

DEV_LAT_S = E9.DEV_LAT_S                 # 0.567, StudyD8 arm A total p50


# ---------------------------------------------------------------- latency
def cloud_latency_s(model, n, load_pct, jpeg=False):
    by = E9.FRAME_BYTES_JPEG if jpeg else E9.FRAME_BYTES
    return E9.RTT_S + by[n] / E9.UPLINK_BPS + E9.CLOUD_TTFT[(model, n, load_pct)]


def setting_parts(setting):
    """-> (zero?, load_pct, jpeg?)"""
    if setting == "zero":
        return True, None, False
    return False, (25 if setting.endswith("25") else 75), setting.startswith("jpeg")


def latencies(setting, model, n):
    """(L_device, L_cloud) in seconds, UNROUNDED measured values."""
    zero, load, jpeg = setting_parts(setting)
    if zero:
        return 0.0, 0.0
    return DEV_LAT_S, cloud_latency_s(model, n, load, jpeg)


def steps_ceil(L, step):
    """Sample-and-hold index shift: the first grid index at which a score computed on-grid at
    index j can be read is j + ceil(L / step). The latency itself is NOT rounded; only the
    moment the application can first read the score is quantised to its own decision grid."""
    return int(math.ceil(L / step - 1e-9))


def steps_ceil_second(L, step):
    """Control (a) only: StudyE9's d = ceil(latency) whole-second rule, expressed in grid steps."""
    return int(round(math.ceil(L - 1e-9) / step))


def device_cadence_steps(L, step):
    """The device can start a new score only after the previous one completes."""
    return max(1, steps_ceil(L, step))


# ---------------------------------------------------------------- data
def load(step=STEP_DENSE, integer_only=False, arms=None):
    """Scores on the grid t = 3.0, 3.0+step, ...  arrs[arm][clip][i] is the score computed at
    index i (t = 3.0 + i*step). STOP if a grid point is missing."""
    want = set(arms) if arms else None
    sc = collections.defaultdict(dict)
    meta = {}
    for ln in gzip.open(TRACE, "rt"):
        r = json.loads(ln)
        t = float(r["t"])
        if integer_only and abs(t - round(t)) > 1e-9:
            continue
        arm = (r["model"], int(r["n"]))
        if want is not None and arm not in want:
            continue
        clip = r["file_name"]
        i = int(round((t - T0) / step))
        assert abs(T0 + i * step - t) < 1e-9, (t, step)
        sc[arm].setdefault(clip, {})[i] = float(r["score"])
        if clip not in meta:
            meta[clip] = dict(label=r["label"],
                              event=(float(r["time_of_event"])
                                     if r["time_of_event"] is not None else None),
                              dur=float(r["duration_s"]))
    clips = sorted(meta)
    arrs = {}
    for arm, per in sc.items():
        a = {}
        for clip, d in per.items():
            idx = sorted(d)
            assert idx == list(range(idx[-1] + 1)), (arm, clip, "missing grid point")
            a[clip] = np.array([d[i] for i in idx])
        arrs[arm] = a
    for c in clips:
        meta[c]["G"] = len(arrs[DEVICE][c])
        meta[c]["T_last"] = T0 + (meta[c]["G"] - 1) * step
    return arrs, meta, clips


def load_d14():
    """StudyE9's own input, on its 1-s grid: used by control (a) variant a1 so that the check is
    purely a check of this code. StudyD14b's integer-t p_yes values are bit-identical to StudyD14's
    on 42,640 / 42,640, but 21 of them differ by 1 ulp in the derived score = log(p_yes), which is
    why the two variants are run separately."""
    a9, m9, c9 = E9.load()
    meta = {c: dict(label=m9[c]["label"],
                    event=(m9[c]["event"] if m9[c]["label"] == "positive" else None),
                    dur=m9[c]["dur"], G=m9[c]["T"] - 2, T_last=float(m9[c]["T"]))
            for c in c9}
    for c in c9:
        meta[c]["event"] = m9[c]["event"]
    return a9, meta, c9


def target_index(meta, c, h, step):
    """E9 / D14b rule: the grid point nearest time_of_event - h on the ABSOLUTE grid, clamped."""
    ia = int(round((meta[c]["event"] - h) / step))
    i = ia - int(round(T0 / step))
    return int(min(max(i, 0), meta[c]["G"] - 1))


# ---------------------------------------------------------------- delivery
def held_stream(arr, G, m, D):
    """Sample-and-hold of a source that computes at indices 0, m, 2m, ... and whose score becomes
    readable D steps after its own compute index. Returns MISSING before the first delivery."""
    out = np.full(G, MISSING)
    if D >= G:
        return out
    i = np.arange(D, G)
    j = ((i - D) // m) * m
    out[D:] = arr[j]
    return out


def upcrossings(stream, thr):
    a = stream >= thr
    if not a.any():
        return []
    return list(np.where(a & ~np.concatenate(([False], a[:-1])))[0])


# ---------------------------------------------------------------- episode simulation
def simulate(dev_seen, res, G, th_alarm, th_dismiss, th_trig, k, lmax_steps, cool_steps,
             mc, Dc):
    """One clip on the grid.

    dev_seen : the device's DELIVERED (sample-and-held) score per grid index.
    res      : the resolver's score per COMPUTE index (frame time).
    mc, Dc   : resolver cadence in steps, and its sample-and-hold shift in steps.

    The resolver is called at the trigger index and every mc steps while the episode is open;
    each call's score becomes readable Dc steps later. Alarm and dismiss are evaluated on
    DELIVERED resolver scores only; the application's stream holds the last delivered resolver
    score for the rest of the episode and the device's held score otherwise.
    """
    stream = np.full(G, MISSING)
    src = np.zeros(G, dtype=np.int8)          # 0 device, 1 resolver, 2 nothing available
    calls = []                                # ledger: every call issued, used or not
    episodes, invocations, ep_inv = [], 0, 0
    open_, i0, drun, cool_at = False, None, 0, -10 ** 9
    next_call, pending, res_held = None, {}, None
    for i in range(G):
        if not open_ and i >= cool_at:
            if dev_seen[i] > MISSING / 2.0 and dev_seen[i] >= th_trig:
                open_, i0, drun, ep_inv = True, i, 0, 0
                next_call, pending, res_held = i, {}, None
        if open_ and next_call is not None and i == next_call:
            invocations += 1
            ep_inv += 1
            pending[i + Dc] = i                # delivery index -> compute index
            calls.append(dict(i_issue=i, i_frame=i, i_deliver=i + Dc,
                              episode=len(episodes), used=False))
            next_call = i + mc
        outcome = None
        if open_ and i in pending:
            s = float(res[pending.pop(i)])
            res_held = s
            for cl in reversed(calls):
                if cl["i_deliver"] == i:
                    cl["used"] = True
                    break
            if s >= th_alarm:
                outcome = "alarm"
            else:
                drun = drun + 1 if s < th_dismiss else 0
                if drun >= k:
                    outcome = "dismiss"
        if open_ and res_held is not None:
            stream[i], src[i] = res_held, 1
        elif dev_seen[i] > MISSING / 2.0:
            stream[i], src[i] = dev_seen[i], 0
        else:
            src[i] = 2
        if open_ and outcome is None and (i - i0 + 1) >= lmax_steps:
            outcome = "cap"
        if open_ and outcome is None and i == G - 1:
            outcome = "clip_end"
        if open_ and outcome is not None:
            episodes.append(dict(i0=i0, i_close=i, outcome=outcome, invocations=ep_inv))
            open_, i0, drun = False, None, 0
            next_call, pending, res_held = None, {}, None
            cool_at = i + 1 + cool_steps
    return stream, src, episodes, invocations, calls


# ---------------------------------------------------------------- AP
def _ap_assemble(above_sorted, n_neg):
    """Average precision, computed BIT-IDENTICALLY to E9.ap_from without its O(N log N) sort.

    E9 sums `prec * y` over the merged positive+negative array, so the zeros of the negatives are
    part of the summation and numpy's pairwise blocking depends on the full length. Reproducing
    that means writing the positive terms at their merged positions into a zero array of the same
    length and summing it, which is what this does. `above_sorted[i]` is the number of negatives
    strictly above the i-th positive in descending order (ties go to positives, as E9's stable
    argsort does), so the i-th positive sits at merged index i + above_sorted[i].
    """
    P = len(above_sorted)
    if P == 0:
        return 0.0
    r = np.arange(1, P + 1, dtype=np.float64)
    arr = np.zeros(P + int(n_neg))
    arr[(r - 1).astype(np.int64) + above_sorted.astype(np.int64)] = r / (r + above_sorted)
    return float(arr.sum() / float(P))


def ap_point(pos, neg):
    """Identical to E9.ap_from, O(P log N) after one sort of the negatives."""
    ns = np.sort(neg)
    v = pos[np.argsort(-pos, kind="stable")]
    above = (len(ns) - np.searchsorted(ns, v, side="right")).astype(np.float64)
    return _ap_assemble(above, len(ns))


class ApEngine:
    """AP and a clip-clustered bootstrap CI at several horizons for one policy's streams.

    The bootstrap is the same shared, label-stratified clip resample E9 uses, so differences
    between policies are paired. Negatives enter only through per-clip counts of scores strictly
    above each positive's value, which makes 2,000 resamples a matrix product.
    """

    def __init__(self, meta, pos_clips, neg_clips, horizons, step):
        self.meta, self.pos, self.neg = meta, pos_clips, neg_clips
        self.H, self.step = tuple(horizons), step
        rng = np.random.default_rng(SEED)
        self.boots = [(rng.integers(0, len(pos_clips), len(pos_clips)),
                       rng.integers(0, len(neg_clips), len(neg_clips))) for _ in range(NB)]
        self.PI = np.array([b[0] for b in self.boots])
        self.M = np.zeros((NB, len(neg_clips)), dtype=np.float64)
        for b, (_pi, ni) in enumerate(self.boots):
            np.add.at(self.M[b], ni, 1.0)
        self.ti = {(c, h): target_index(meta, c, h, step) for c in pos_clips for h in self.H}
        self.neg_len = np.array([meta[c]["G"] for c in neg_clips], dtype=np.float64)

    def _pos_values(self, streams):
        return {h: np.array([streams[c][self.ti[(c, h)]] for c in self.pos]) for h in self.H}

    def point(self, streams):
        V = self._pos_values(streams)
        Ncat = np.concatenate([streams[c] for c in self.neg])
        return {h: ap_point(V[h], Ncat) for h in self.H}

    def full(self, streams):
        V = self._pos_values(streams)
        srt = [np.sort(streams[c]) for c in self.neg]
        out, boot = {}, {}
        for h in self.H:
            v = V[h]
            C = np.empty((len(self.neg), len(v)))
            for j, s in enumerate(srt):
                C[j] = len(s) - np.searchsorted(s, v, side="right")
            order = np.argsort(-v, kind="stable")
            pt = _ap_assemble(C.sum(0)[order], self.neg_len.sum())
            NA = self.M @ C                                    # (NB, n_pos)
            vb = v[self.PI]                                    # (NB, n_pos)
            ob = np.argsort(-vb, axis=1, kind="stable")
            nab = np.take_along_axis(np.take_along_axis(NA, self.PI, axis=1), ob, axis=1)
            nneg = self.M @ self.neg_len
            bs = np.array([_ap_assemble(nab[b], nneg[b]) for b in range(NB)])
            out[h] = dict(ap=pt, ci=[float(np.percentile(bs, 2.5)),
                                     float(np.percentile(bs, 97.5))])
            boot[h] = bs
        return out, boot


# ---------------------------------------------------------------- Study 1 runner
def gpu_s(model, n, inv):
    return inv * E9.PROMPT_TOK[n] / E9.PREFILL_TOK_S[model]


def always_cloud_calls(G, mc):
    return (G + mc - 1) // mc


def build(step=STEP_DENSE, horizons=HORIZONS_DENSE, integer_only=False, ceil_delivery=False,
          use_d14=False):
    """Everything that does not depend on a policy: scores, folds, thresholds, AP engine."""
    if use_d14:
        arrs, meta, clips = load_d14()
    else:
        arrs, meta, clips = load(step=step, integer_only=integer_only)
    fold = E9.folds(clips, meta)
    tau = E9.fit_thresholds(arrs, meta, clips, fold)
    pos = [c for c in clips if meta[c]["label"] == "positive"]
    neg = [c for c in clips if meta[c]["label"] == "negative"]
    eng = ApEngine(meta, pos, neg, horizons, step)
    ctx = dict(arrs=arrs, meta=meta, clips=clips, fold=fold, tau=tau, pos=pos, neg=neg, eng=eng,
               step=step, horizons=tuple(horizons), ceil=ceil_delivery,
               neg_pts=sum(meta[c]["G"] for c in neg), pos_pts=sum(meta[c]["G"] for c in pos))
    ctx["chance"] = len(pos) / (len(pos) + ctx["neg_pts"])
    ctx["hours_all"] = (ctx["pos_pts"] + ctx["neg_pts"]) * step / 3600.0
    ctx["hours_pos"] = ctx["pos_pts"] * step / 3600.0
    ctx["hours_neg"] = ctx["neg_pts"] * step / 3600.0
    return ctx


def shift_steps(ctx, L):
    return steps_ceil_second(L, ctx["step"]) if ctx["ceil"] else steps_ceil(L, ctx["step"])


def device_schedule(ctx, setting):
    """(cadence in steps, hold shift in steps, measured L). In control (a) mode the device scores
    every grid point, which is what StudyE9 replayed; on the dense grid it can only start a new
    score when the previous one has completed."""
    Ld, _ = latencies(setting, *DEVICE)
    D = shift_steps(ctx, Ld)
    m = 1 if ctx["ceil"] else device_cadence_steps(Ld, ctx["step"])
    return m, D, Ld


def dev_seen_all(ctx, setting):
    m, D, Ld = device_schedule(ctx, setting)
    return {c: held_stream(ctx["arrs"][DEVICE][c], ctx["meta"][c]["G"], m, D) for c in ctx["clips"]}, m, D, Ld


def alarm_stats(ctx, alarm_i, n_alarm_neg):
    meta, pos, step = ctx["meta"], ctx["pos"], ctx["step"]
    rel = [T0 + alarm_i[c] * step - meta[c]["event"] for c in pos if c in alarm_i]
    out = dict(n_positive_alarmed=len(rel), fraction_positive_alarmed=len(rel) / len(pos),
               alarm_rel_event_s=(dict(p50=float(np.median(rel)),
                                       p25=float(np.percentile(rel, 25)),
                                       p75=float(np.percentile(rel, 75))) if rel else None),
               fraction_alarmed_by_horizon={})
    for h in ctx["horizons"]:
        out["fraction_alarmed_by_horizon"][h] = sum(
            1 for c in pos if c in alarm_i
            and T0 + alarm_i[c] * step <= meta[c]["event"] - h) / len(pos)
    out["false_alarm_events_negative"] = n_alarm_neg
    out["false_alarms_per_clip_hour"] = n_alarm_neg / ctx["hours_neg"]
    return out


def episode_stats(ctx, eps, inv, model, n):
    meta = ctx["meta"]
    o = {}
    for lab, cl, hours in (("positive", ctx["pos"], ctx["hours_pos"]),
                           ("negative", ctx["neg"], ctx["hours_neg"])):
        ee = [e for c in cl for e in eps[c]]
        iv = sum(inv[c] for c in cl)
        cnt = collections.Counter(e["outcome"] for e in ee)
        o[lab] = dict(
            episodes=len(ee), episodes_per_clip=len(ee) / len(cl),
            outcomes={k: cnt.get(k, 0) for k in ("alarm", "dismiss", "cap", "clip_end")},
            invocations=iv, invocations_per_clip_hour=iv / hours,
            gpu_seconds=gpu_s(model, n, iv), gpu_seconds_per_clip_hour=gpu_s(model, n, iv) / hours,
            invocations_per_episode=(iv / len(ee) if ee else None),
            episode_length_s_mean=(float(np.mean([(e["i_close"] - e["i0"] + 1) * ctx["step"]
                                                  for e in ee])) if ee else None),
            re_escalations_per_clip=sum(max(0, len(eps[c]) - 1) for c in cl) / len(cl))
    fd = 0
    for c in ctx["pos"]:
        for e in eps[c]:
            if e["outcome"] in ("dismiss", "cap") and T0 + e["i_close"] * ctx["step"] < meta[c]["event"]:
                fd += 1
    o["false_dismissals_positive_before_event"] = fd
    spans = [(eps[c][-1]["i_close"] - eps[c][0]["i0"] + 1) * ctx["step"]
             for c in ctx["clips"] if eps[c]]
    o["first_trigger_to_final_resolution_s"] = (
        dict(mean=float(np.mean(spans)), p50=float(np.median(spans)), max=float(max(spans)))
        if spans else None)
    return o


def run_escalation(ctx, rmodel, rn, setting, cadence, far, trig, k, q, lmax, cooldown,
                   shuffle=False, resolver_override=None, L_cloud_override=None):
    """One escalation cell over all 300 clips."""
    meta, tau, fold, step = ctx["meta"], ctx["tau"], ctx["fold"], ctx["step"]
    seen_all, _m, _D, _Ld = dev_seen_all(ctx, setting)
    _Ld2, Lc = latencies(setting, rmodel, rn)
    if L_cloud_override is not None:
        Lc = L_cloud_override
    Dc = shift_steps(ctx, Lc)
    mc = max(1, int(round(cadence / step)))
    lmax_steps = int(round(lmax / step))
    cool_steps = int(round(cooldown / step))
    src_arm = resolver_override or (rmodel, rn)
    streams, eps, inv, alarm_i, nev, wasted = {}, {}, {}, {}, 0, {}
    rng_s = np.random.default_rng(SEED)
    for c in ctx["clips"]:
        G = meta[c]["G"]
        rs = ctx["arrs"][src_arm][c]
        if shuffle:
            rs = rs[rng_s.permutation(len(rs))]
        th = tau[(src_arm, fold[c])]
        s, _src, e, iv, cl = simulate(seen_all[c], rs, G, th["alarm"][far], th["dismiss"][q],
                                      tau[(DEVICE, fold[c])]["trig"][trig], k, lmax_steps,
                                      cool_steps, mc, Dc)
        streams[c], eps[c], inv[c] = s, e, iv
        wasted[c] = sum(1 for x in cl if not x["used"])
        al = [x for x in e if x["outcome"] == "alarm"]
        if meta[c]["label"] == "positive":
            if al:
                alarm_i[c] = al[0]["i_close"]
        else:
            nev += len(al)
    return dict(streams=streams, eps=eps, inv=inv, alarm_i=alarm_i, nev=nev, Dc=Dc, mc=mc,
                L_cloud=Lc, wasted=wasted)


def paired_inv_ci(ctx, inv_a, inv_b, group):
    cl = {"positive": ctx["pos"], "negative": ctx["neg"], "all": ctx["clips"]}[group]
    da = np.array([inv_a[c] for c in cl], dtype=float)
    db = np.array([inv_b[c] for c in cl], dtype=float)
    pts = np.array([ctx["meta"][c]["G"] for c in cl], dtype=float)
    hours = pts.sum() * ctx["step"] / 3600.0
    diff = (da.sum() - db.sum()) / hours
    rng = np.random.default_rng(SEED)
    J = rng.integers(0, len(cl), (NB, len(cl)))
    bs = (da[J].sum(1) - db[J].sum(1)) / (pts[J].sum(1) * ctx["step"] / 3600.0)
    return dict(diff_per_clip_hour=float(diff),
                ci=[float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))])


def horizon_shift(ctx, boot32, boot4, ap32, ap4):
    """StudyE9 §3.1, unchanged: at the AP the 4B arm reaches at horizon h, how much further ahead
    the 32B arm reaches the same AP, by linear interpolation of the AP-vs-horizon curve. It is a
    property of the curves and says nothing about when either model notices a given crash."""
    hs = np.array(ctx["horizons"])

    def one(a32, a4):
        out = {}
        for i, h in enumerate(hs):
            y, g = a4[i], a32
            j = np.where(g <= y)[0]
            if len(j) == 0:
                out[h] = float(hs[-1] - h)
                continue
            j0 = j[0]
            if j0 == 0:
                out[h] = float(hs[0] - h)
                continue
            x0, x1, y0, y1 = hs[j0 - 1], hs[j0], g[j0 - 1], g[j0]
            out[h] = float(x0 + (y0 - y) * (x1 - x0) / max(y0 - y1, 1e-12) - h)
        return out
    H = ctx["horizons"]
    point = one(np.array([ap32[h] for h in H]), np.array([ap4[h] for h in H]))
    bs = {h: [] for h in H}
    for b in range(NB):
        o = one(np.array([boot32[h][b] for h in H]), np.array([boot4[h][b] for h in H]))
        for h in H:
            bs[h].append(o[h])
    return {h: dict(shift_s=point[h], ci=[float(np.percentile(bs[h], 2.5)),
                                          float(np.percentile(bs[h], 97.5))]) for h in H}


def ap_block(ctx, ap):
    return {h: dict(ap=ap[h]["ap"], ci=ap[h]["ci"],
                    multiple_of_chance=ap[h]["ap"] / ctx["chance"]) for h in ctx["horizons"]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    step = STEP_DENSE
    ctx = build(step=step, horizons=HORIZONS_DENSE)
    meta, clips, tau, fold, eng = ctx["meta"], ctx["clips"], ctx["tau"], ctx["fold"], ctx["eng"]
    P = PRIMARY
    res = dict(
        label="StudyE9b-dense Study 1 (StudyE9 re-run): OFFLINE REPLAY OF COMMITTED RESULTS "
              "(StudyD14b 0.25-s traces). CPU only on flash; no GPU, no model server, no inference. "
              "Scores are continuous log P(Yes); no literal Yes/No answer is used anywhere. Every "
              "score has a compute time and a delivery time = compute time + the MEASURED latency; "
              "the application reads the most recent score already delivered (sample-and-hold). AP "
              "is comparable WITHIN this grid only.",
        at=datetime.now().isoformat(), seed=SEED, n_bootstrap=NB, step_s=step,
        horizons=list(HORIZONS_DENSE), primary_config=PRIMARY, cadences=list(CADENCES),
        cadence_primary=CADENCE_PRIMARY, settings=list(SETTINGS), jpeg_note=JPEG_NOTE,
        n_clips=dict(positive=len(ctx["pos"]), negative=len(ctx["neg"])),
        grid_points=dict(positive=ctx["pos_pts"], negative=ctx["neg_pts"]),
        chance_rate=ctx["chance"], chance_rate_1s_grid=150.0 / (150.0 + 5196.0),
        device_cadence_s=device_cadence_steps(DEV_LAT_S, step) * step,
        device_latency_s=DEV_LAT_S, delivery=dict(), thresholds={},
        baselines={}, cells={}, sensitivity={}, controls={}, trace_example=None)

    for st in SETTINGS:
        Ld, _ = latencies(st, *DEVICE)
        for arm in RESOLVERS_32B + [RESOLVER_4B]:
            _d, Lc = latencies(st, *arm)
            res["delivery"][f"{st}/{arm[0]}_N{arm[1]}"] = dict(
                device_latency_s=Ld, device_hold_shift_steps=steps_ceil(Ld, step),
                device_hold_shift_s=steps_ceil(Ld, step) * step,
                device_cadence_s=device_cadence_steps(Ld, step) * step,
                rtt_s=(0.0 if st == "zero" else E9.RTT_S),
                upload_s=(0.0 if st == "zero" else
                          (E9.FRAME_BYTES_JPEG if st.startswith("jpeg") else E9.FRAME_BYTES)[arm[1]]
                          / E9.UPLINK_BPS),
                server_ttft_s=(0.0 if st == "zero" else
                               E9.CLOUD_TTFT[(arm[0], arm[1], setting_parts(st)[1])]),
                cloud_latency_s=Lc, cloud_hold_shift_steps=steps_ceil(Lc, step),
                cloud_hold_shift_s=steps_ceil(Lc, step) * step,
                cloud_minus_device_shift_s=(steps_ceil(Lc, step) - steps_ceil(Ld, step)) * step,
                d_cloud_1s_grid_StudyE9=steps_ceil_second(Lc, 1.0))
    for (arm, fi), v in tau.items():
        res["thresholds"][f"{arm[0]}_N{arm[1]}/fold{fi}"] = v

    # ---------------- baselines ----------------
    base_boot = {}
    for st in SETTINGS:
        seen_all, mdev, Ddev, Ld = dev_seen_all(ctx, st)
        for far in ALARM_FPR:
            at, nev = {}, 0
            for c in clips:
                up = upcrossings(seen_all[c], tau[(DEVICE, fold[c])]["alarm"][far])
                if meta[c]["label"] == "positive":
                    if up:
                        at[c] = up[0]
                else:
                    nev += len(up)
            ap, boot = eng.full(seen_all)
            key = f"device-only|{st}|far{int(far*100)}"
            res["baselines"][key] = dict(
                policy="device-only", latency=st, cadence_s=mdev * step, alarm_fpr=far,
                ap=ap_block(ctx, ap), alarms=alarm_stats(ctx, at, nev),
                cloud=dict(invocations=0, invocations_per_clip_hour=0.0, gpu_seconds=0.0,
                           gpu_seconds_per_clip_hour=0.0))
            base_boot[key] = boot
        for cad in CADENCES:
            mc = int(round(cad / step))
            for arm in RESOLVERS_32B + [RESOLVER_4B]:
                _d, Lc = latencies(st, *arm)
                Dc = steps_ceil(Lc, step)
                streams = {c: held_stream(ctx["arrs"][arm][c], meta[c]["G"], mc, Dc) for c in clips}
                calls = sum(always_cloud_calls(meta[c]["G"], mc) for c in clips)
                for far in ALARM_FPR:
                    at, nev = {}, 0
                    for c in clips:
                        up = upcrossings(streams[c], tau[(arm, fold[c])]["alarm"][far])
                        if meta[c]["label"] == "positive":
                            if up:
                                at[c] = up[0]
                        else:
                            nev += len(up)
                    ap, boot = eng.full(streams)
                    key = f"always-cloud/{arm[0]}_N{arm[1]}|{st}|cad{int(cad*100)}|far{int(far*100)}"
                    res["baselines"][key] = dict(
                        policy=f"always-cloud/{arm[0]}_N{arm[1]}", latency=st, cadence_s=cad,
                        alarm_fpr=far, ap=ap_block(ctx, ap), alarms=alarm_stats(ctx, at, nev),
                        cloud=dict(invocations=calls,
                                   invocations_per_clip_hour=calls / ctx["hours_all"],
                                   gpu_seconds=gpu_s(arm[0], arm[1], calls),
                                   gpu_seconds_per_clip_hour=gpu_s(arm[0], arm[1], calls)
                                   / ctx["hours_all"]))
                    base_boot[key] = boot
        print("baselines done for", st, len(res["baselines"]), flush=True)
    # ---------------- escalation sweep ----------------
    def pack(rmodel, rn, st, cad, far, trig, k, q, lmax, cd, with_ci=True, **kw):
        r = run_escalation(ctx, rmodel, rn, st, cad, far, trig, k, q, lmax, cd, **kw)
        d = dict(policy=("escalation-32B" if rmodel == "32BI" else "escalation-4B"),
                 resolver=f"{rmodel}_N{rn}", latency=st, cadence_s=cad, alarm_fpr=far,
                 dismiss_q=q, trigger_rate=trig, k=k, l_max=lmax, cooldown=cd,
                 cloud_latency_s=r["L_cloud"], cloud_hold_shift_s=r["Dc"] * step,
                 episodes=episode_stats(ctx, r["eps"], r["inv"], rmodel, rn),
                 alarms=alarm_stats(ctx, r["alarm_i"], r["nev"]))
        tot = sum(r["inv"].values())
        wst = sum(r["wasted"].values())
        d["cloud"] = dict(invocations=tot, invocations_per_clip_hour=tot / ctx["hours_all"],
                          gpu_seconds=gpu_s(rmodel, rn, tot),
                          gpu_seconds_per_clip_hour=gpu_s(rmodel, rn, tot) / ctx["hours_all"],
                          calls_answered_after_episode_closed=wst,
                          fraction_of_calls_wasted=(wst / tot if tot else None))
        if with_ci:
            ap, boot = eng.full(r["streams"])
            d["ap"] = ap_block(ctx, ap)
        else:
            ap = eng.point(r["streams"])
            boot = None
            d["ap"] = {h: dict(ap=ap[h], ci=None, multiple_of_chance=ap[h] / ctx["chance"])
                       for h in ctx["horizons"]}
        return d, r, boot

    inv_store = {}
    n = 0
    for st in SETTINGS:
        for cad in CADENCES:
            for rmodel, rn in RESOLVERS_32B + [RESOLVER_4B]:
                for far in ALARM_FPR:
                    for trig in TRIG_RATE:
                        d, r, _b = pack(rmodel, rn, st, cad, far, trig,
                                        P["k"], P["q"], P["lmax"], P["c"])
                        key = (f"{d['policy']}|{rmodel}_N{rn}|{st}|cad{int(cad*100)}|"
                               f"far{int(far*100)}|trig{int(trig*100)}|q{int(P['q']*100)}|"
                               f"k{P['k']}|L{P['lmax']}|c{P['c']}")
                        d["is_primary_config"] = True
                        res["cells"][key] = d
                        inv_store[key] = r["inv"]
                        n += 1
        print("swept setting", st, "cells", n, flush=True)

    # ---------------- k and dismiss-quantile sensitivity, primary setting and cadence ----------
    for (k, q) in [(1, P["q"]), (3, P["q"]), (P["k"], 0.50)]:
        for rmodel, rn in RESOLVERS_32B + [RESOLVER_4B]:
            for far in ALARM_FPR:
                for trig in TRIG_RATE:
                    d, r, _b = pack(rmodel, rn, "measured@25", CADENCE_PRIMARY, far, trig,
                                    k, q, P["lmax"], P["c"], with_ci=False)
                    d["is_primary_config"] = False
                    res["sensitivity"][(f"{d['policy']}|{rmodel}_N{rn}|measured@25|"
                                        f"cad{int(CADENCE_PRIMARY*100)}|far{int(far*100)}|"
                                        f"trig{int(trig*100)}|q{int(q*100)}|k{k}")] = d
    print("sensitivity cells", len(res["sensitivity"]), flush=True)

    # ---------------- decision rule 1 ----------------
    rule1 = {}
    for st in SETTINGS:
        for cad in CADENCES:
            for rmodel, rn in RESOLVERS_32B:
                for far in ALARM_FPR:
                    for trig in TRIG_RATE:
                        suf = (f"{st}|cad{int(cad*100)}|far{int(far*100)}|trig{int(trig*100)}|"
                               f"q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}")
                        a = res["cells"][f"escalation-32B|{rmodel}_N{rn}|{suf}"]
                        b = res["cells"][f"escalation-4B|4BI_N1|{suf}"]
                        ia = inv_store[f"escalation-32B|{rmodel}_N{rn}|{suf}"]
                        ib = inv_store[f"escalation-4B|4BI_N1|{suf}"]
                        rule1[f"{rmodel}_N{rn}|{suf}"] = dict(
                            all=paired_inv_ci(ctx, ia, ib, "all"),
                            positive=paired_inv_ci(ctx, ia, ib, "positive"),
                            negative=paired_inv_ci(ctx, ia, ib, "negative"),
                            inv_32B_per_clip_hour=a["cloud"]["invocations_per_clip_hour"],
                            inv_4B_per_clip_hour=b["cloud"]["invocations_per_clip_hour"])
    res["decision_rule_1_capability_shortens_episodes"] = dict(
        statement="PRE-REGISTERED (StudyE9, unchanged): capability shortens episodes if "
                  "escalation-32B has lower total cloud invocations per clip-hour than "
                  "escalation-4B at matched tau_trig and matched alarm FPR, with a paired "
                  "clip-bootstrap CI excluding 0, in at least 2 of the 3 alarm FPR levels, under "
                  "latency setting (ii).", cells=rule1)

    # ---------------- decision rule 2 ----------------
    TOL, TOL_SCALED = 0.01, 0.01 * ctx["chance"] / (150.0 / (150.0 + 5196.0))
    rule2 = {}
    H1 = [h for h in ctx["horizons"] if h <= 1.0]
    for st in SETTINGS:
        for cad in CADENCES:
            for rmodel, rn in RESOLVERS_32B:
                for far in ALARM_FPR:
                    ac = res["baselines"][(f"always-cloud/{rmodel}_N{rn}|{st}|cad{int(cad*100)}|"
                                           f"far{int(far*100)}")]
                    for trig in TRIG_RATE:
                        suf = (f"{st}|cad{int(cad*100)}|far{int(far*100)}|trig{int(trig*100)}|"
                               f"q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}")
                        e = res["cells"][f"escalation-32B|{rmodel}_N{rn}|{suf}"]
                        gaps = {h: ac["ap"][h]["ap"] - e["ap"][h]["ap"] for h in H1}
                        ov = {h: not (e["ap"][h]["ci"][1] < ac["ap"][h]["ci"][0]
                                      or ac["ap"][h]["ci"][1] < e["ap"][h]["ci"][0]) for h in H1}
                        frac = (e["cloud"]["gpu_seconds"] / ac["cloud"]["gpu_seconds"]
                                if ac["cloud"]["gpu_seconds"] else None)
                        rule2[f"{rmodel}_N{rn}|{suf}"] = dict(
                            ap_gap={h: gaps[h] for h in H1}, ci_overlap={h: ov[h] for h in H1},
                            work_fraction_of_always_cloud=frac,
                            invocations_per_clip_hour=e["cloud"]["invocations_per_clip_hour"],
                            always_cloud_invocations_per_clip_hour=ac["cloud"]["invocations_per_clip_hour"],
                            gpu_seconds_per_clip_hour=e["cloud"]["gpu_seconds_per_clip_hour"],
                            met=bool(all(gaps[h] <= TOL for h in H1) and all(ov.values())
                                     and frac is not None and frac <= 0.50),
                            met_scale_matched_SECONDARY=bool(
                                all(gaps[h] <= TOL_SCALED for h in H1) and all(ov.values())
                                and frac is not None and frac <= 0.50))
    res["decision_rule_2_escalation_is_efficient"] = dict(
        statement="PRE-REGISTERED (StudyE9, unchanged): escalation is efficient if it keeps AP "
                  "within 0.01 of always-cloud at h <= 1 s (CIs overlapping) while using <= 50% of "
                  "always-cloud's cloud work, at some tau_trig.",
        tolerance=TOL, tolerance_scale_matched_SECONDARY=TOL_SCALED,
        scale_note="On this grid chance AP is %.5f against %.5f on StudyE9's 1-s grid, so the "
                   "unchanged 0.01 tolerance is 1.37x the entire chance rate. The rule is applied "
                   "UNCHANGED as pre-registered; the scale-matched column is a LABELLED SECONDARY "
                   "and is not the rule." % (ctx["chance"], 150.0 / (150.0 + 5196.0)),
        cells=rule2)

    # ---------------- AP-curve horizon shift ----------------
    hs = {}
    for st in SETTINGS:
        for far in ALARM_FPR:
            kd = f"device-only|{st}|far{int(far*100)}"
            b4 = res["baselines"][kd]
            for cad in CADENCES:
                for arm in RESOLVERS_32B:
                    k32 = (f"always-cloud/{arm[0]}_N{arm[1]}|{st}|cad{int(cad*100)}|"
                           f"far{int(far*100)}")
                    b32 = res["baselines"][k32]
                    hs[f"{arm[0]}_N{arm[1]}_vs_4BI_N1|{st}|cad{int(cad*100)}|far{int(far*100)}"] = \
                        horizon_shift(ctx, base_boot[k32], base_boot[kd],
                                      {h: b32["ap"][h]["ap"] for h in ctx["horizons"]},
                                      {h: b4["ap"][h]["ap"] for h in ctx["horizons"]})
    res["ap_curve_horizon_shift"] = dict(
        note="CURVE SHIFT, NOT a per-event time: at the AP the 4B device arm reaches at horizon h, "
             "this is how much further ahead the 32B arm reaches the same AP, by linear "
             "interpolation of the AP-vs-horizon curve on the 0.25-s grid. It says nothing about "
             "when either model first notices a given crash.", cells=hs)

    # ---------------- controls ----------------
    ok_b = all(np.array_equal(held_stream(ctx["arrs"][a][c], meta[c]["G"], 1, 0),
                              ctx["arrs"][a][c]) for a in ctx["arrs"] for c in clips)
    res["controls"]["b_zero_latency_delivered_equals_compute"] = dict(
        description="Under setting (i) zero latency the sample-and-hold stream must equal the "
                    "compute stream for every arm and every clip.",
        arms_checked=len(ctx["arrs"]), clips_checked=len(clips), all_equal=bool(ok_b))

    ctrl_sw = {}
    for st in SETTINGS:
        for cad in CADENCES:
            for far in ALARM_FPR:
                for trig in TRIG_RATE:
                    d, _r, _b = pack("32BI", 1, st, cad, far, trig, P["k"], P["q"], P["lmax"],
                                     P["c"], with_ci=False, resolver_override=RESOLVER_4B,
                                     L_cloud_override=latencies(st, *RESOLVER_4B)[1])
                    suf = (f"{st}|cad{int(cad*100)}|far{int(far*100)}|trig{int(trig*100)}|"
                           f"q{int(P['q']*100)}|k{P['k']}|L{P['lmax']}|c{P['c']}")
                    ref = res["cells"][f"escalation-4B|4BI_N1|{suf}"]
                    same = (d["episodes"]["positive"]["invocations"] == ref["episodes"]["positive"]["invocations"]
                            and d["episodes"]["negative"]["invocations"] == ref["episodes"]["negative"]["invocations"]
                            and d["alarms"]["n_positive_alarmed"] == ref["alarms"]["n_positive_alarmed"]
                            and d["alarms"]["false_alarm_events_negative"] == ref["alarms"]["false_alarm_events_negative"]
                            and all(abs(d["ap"][h]["ap"] - ref["ap"][h]["ap"]) < 1e-15
                                    for h in ctx["horizons"]))
                    ctrl_sw[suf] = bool(same)
    res["controls"]["c_swap_resolver_to_4B"] = dict(
        description="escalation-32B's code path run with 4B N1 resolver scores, 4B N1 thresholds "
                    "and 4B N1 cloud latency must equal escalation-4B exactly (StudyE9's control).",
        cells_checked=len(ctrl_sw), all_equal=all(ctrl_sw.values()),
        mismatches=[k for k, v in ctrl_sw.items() if not v])

    ctrl_sh = {}
    for st in ("zero", "measured@25"):
        for arm in RESOLVERS_32B:
            d, _r, _b = pack(arm[0], arm[1], st, CADENCE_PRIMARY, 0.05, 0.20, P["k"], P["q"],
                             P["lmax"], P["c"], with_ci=False, shuffle=True)
            suf = (f"{st}|cad{int(CADENCE_PRIMARY*100)}|far5|trig20|q{int(P['q']*100)}|"
                   f"k{P['k']}|L{P['lmax']}|c{P['c']}")
            base = res["cells"][f"escalation-32B|{arm[0]}_N{arm[1]}|{suf}"]
            ctrl_sh[f"{arm[0]}_N{arm[1]}|{st}"] = dict(
                ap_shuffled={h: d["ap"][h]["ap"] for h in ctx["horizons"]},
                ap_real={h: base["ap"][h]["ap"] for h in ctx["horizons"]},
                multiple_of_chance_shuffled={h: d["ap"][h]["ap"] / ctx["chance"]
                                             for h in ctx["horizons"]})
    res["controls"]["d_shuffle_resolver_within_clip"] = dict(
        description="resolver scores permuted across grid points within each clip (alarm FPR 5%, "
                    "trigger 20%, cadence 0.5 s, primary config). AP must fall toward chance.",
        chance_rate=ctx["chance"], cells=ctrl_sh)

    # ---------------- Step 4 control: disable the delivery link ----------------
    dis = {}
    for Lb in (None, 10.0):
        d, _r, _b = pack("32BI", 1, "measured@25", CADENCE_PRIMARY, 0.05, 0.10, P["k"], P["q"],
                         P["lmax"], P["c"], with_ci=False, L_cloud_override=Lb)
        dis["measured" if Lb is None else "L_cloud_10s"] = {h: d["ap"][h]["ap"]
                                                            for h in ctx["horizons"]}
    dis["device_only_reference"] = {h: res["baselines"]["device-only|measured@25|far5"]["ap"][h]["ap"]
                                    for h in ctx["horizons"]}
    dis["collapses_to_device_only"] = bool(all(
        abs(dis["L_cloud_10s"][h] - dis["device_only_reference"][h]) < 1e-15
        for h in ctx["horizons"]))
    res["controls"]["e_disable_delivery_link"] = dict(
        description="CLAUDE.md Step 4: with L_cloud raised to 10 s (= L_max) no resolver answer can "
                    "arrive before the episode caps, so escalation-32B must collapse to device-only.",
        cell="escalation-32B|32BI_N1|measured@25|cad50|far5|trig10 (primary config)", values=dis)

    # ---------------- instrumented episode on the dense grid ----------------
    st, rmodel, rn, cad, far, trig = "measured@25", "32BI", 1, CADENCE_PRIMARY, 0.05, 0.20
    seen_all, mdev, Ddev, Ld = dev_seen_all(ctx, st)
    _d, Lc = latencies(st, rmodel, rn)
    Dc, mc = steps_ceil(Lc, step), int(round(cad / step))
    lmax_steps = int(round(P["lmax"] / step))
    pick = None
    for c in ctx["pos"]:
        G = meta[c]["G"]
        th = tau[((rmodel, rn), fold[c])]
        s, src, e, iv, cl = simulate(seen_all[c], ctx["arrs"][(rmodel, rn)][c], G,
                                     th["alarm"][far], th["dismiss"][P["q"]],
                                     tau[(DEVICE, fold[c])]["trig"][trig],
                                     P["k"], lmax_steps, 0, mc, Dc)
        fd = [x for x in e if x["outcome"] in ("dismiss", "cap")
              and T0 + x["i_close"] * step < meta[c]["event"]]
        if fd and len(e) > 1:
            pick = (c, s, src, e, iv, cl)
            break
    if pick:
        c, s, src, e, iv, cl = pick
        G = meta[c]["G"]
        th = tau[((rmodel, rn), fold[c])]
        issue = {x["i_issue"]: x for x in cl}
        deliv = {x["i_deliver"]: x for x in cl if x["used"]}
        dropped = {x["i_deliver"]: x for x in cl if not x["used"]}
        rows = []
        for i in range(G):
            t = T0 + i * step
            jdev = ((i - Ddev) // mdev) * mdev if i >= Ddev else None
            rows.append(dict(
                t=round(t, 3), rel_event_s=round(t - meta[c]["event"], 3),
                device_frame_t=(None if jdev is None else round(T0 + jdev * step, 3)),
                device_score=(None if jdev is None else
                              round(float(ctx["arrs"][DEVICE][c][jdev]), 4)),
                device_delivered_at=(None if jdev is None else round(T0 + jdev * step + Ld, 4)),
                device_score_age_s=(None if jdev is None else round((i - jdev) * step, 2)),
                resolver_call_issued_at_t=(round(t, 3) if i in issue else None),
                resolver_delivery_t=(round(T0 + i * step + Lc, 4) if i in issue else None),
                resolver_score_delivered=(
                    round(float(ctx["arrs"][(rmodel, rn)][c][deliv[i]["i_frame"]]), 4)
                    if i in deliv else None),
                resolver_frame_t=(round(T0 + deliv[i]["i_frame"] * step, 3) if i in deliv else None),
                resolver_delivery_dropped_after_episode_closed=(
                    round(T0 + dropped[i]["i_frame"] * step, 3) if i in dropped else None),
                application_score=(None if s[i] == MISSING else round(float(s[i]), 4)),
                application_source=("resolver" if src[i] == 1 else
                                    ("device" if src[i] == 0 else "none")),
                episode_open=any(x["i0"] <= i <= x["i_close"] for x in e)))
        res["trace_example"] = dict(
            clip=c, label=meta[c]["label"], event_s=meta[c]["event"], duration_s=meta[c]["dur"],
            step_s=step, resolver=f"{rmodel}_N{rn}", latency=st, cadence_s=cad,
            device_latency_s=Ld, device_cadence_s=mdev * step, device_hold_shift_s=Ddev * step,
            cloud_latency_s=Lc, cloud_hold_shift_s=Dc * step,
            tau_trigger=round(tau[(DEVICE, fold[c])]["trig"][trig], 4),
            tau_alarm=round(th["alarm"][far], 4), tau_dismiss=round(th["dismiss"][P["q"]], 4),
            k=P["k"], l_max_s=P["lmax"], cooldown_s=P["c"],
            episodes=[dict(t0=round(T0 + x["i0"] * step, 3),
                           t_close=round(T0 + x["i_close"] * step, 3),
                           outcome=x["outcome"], invocations=x["invocations"]) for x in e],
            total_invocations=iv, gpu_seconds=round(gpu_s(rmodel, rn, iv), 4), grid=rows)

    res["sensitivity"] = {k: v for k, v in res["sensitivity"].items()}
    res["_provenance"] = stamp(script="study_e9b_dense.py", model=None, device="cpu",
                               n=len(clips), args=None)
    (OUT / "e9b_study1_results.json").write_text(json.dumps(res, indent=1, default=float))
    print("cells:", len(res["cells"]), "baselines:", len(res["baselines"]),
          "sensitivity:", len(res["sensitivity"]))


if __name__ == "__main__":
    main()
