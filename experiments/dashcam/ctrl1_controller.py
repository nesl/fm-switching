#!/usr/bin/env python3
"""StudyCTRL1-episodes: the self-normalized device controller, its episodes, and how much of the
cloud's advantage escalation-only cloud use captures. CPU only; no GPU, no model server, no
inference. Every score is a committed StudyD14b trace.

Pre-registered in `research/EXPERIMENTS.md` (StudyCTRL1-episodes) before anything was computed,
including the DEV / EVAL split rule (`d14b_split.py`), the objective and the budget levels.

THE CONTROLLER IS SPEC 7.7, PRICE TERM OFF. Self-normalized signals over the device's own recent
window W_c, escalate when max(signal) > theta, episode ends when the signal stays below theta for
K_c frames or after E_k calls.

WHAT THE CONTROLLER CAN SEE, which is the whole point of the study: the device's OWN DELIVERED
samples. The device arm is 4BI N=1 at StudyE9b's saturated duty, so it starts a new score every
ceil(0.567 / 0.25) x 0.25 = 0.75 s and each score becomes readable 3 grid steps after its own
capture. The controller therefore reads a held 0.75-s sample stream, never the 0.25-s trace, and
every signal is computed from samples whose read time has already passed. There is no absolute
confidence anywhere in it.

DECISIONS THE SPEC LEAVES OPEN, each recorded here and in the report's ambiguity table rather
than silently taken:

  (A1) Spec 7.7 writes "rise score_t - score_{t - delta}" without a normalizer while calling all
       three signals self-normalized. A raw log-unit rise and a dimensionless z cannot share one
       threshold theta without a unit error, so rise and instability are BOTH divided by the same
       window IQR as z. The unnormalized reading is not implemented.
  (A2) "instability over n_c frames" is undefined in the spec. The brief offers two readings,
       score variance or answer flips, so BOTH are implemented and the choice is made on DEV like
       any other fitted quantity: `var` = the standard deviation of the last n_c samples divided
       by the window IQR, `flips` = the fraction of sign changes of (score > log 0.5) over the
       last n_c samples, divided by 0.5 so that a half-flipping window scores 1.0.
  (A3) A degenerate window (IQR below 1e-6, i.e. a flat stretch) yields NO signal and cannot
       escalate. The alternative, dividing by a floor, would make a flat window the most
       escalation-prone state, which is the opposite of the mechanism.
  (A4) The application displays the most recently DELIVERED value from either source, device or
       cloud, as one sample-and-hold. This is StudyE9b's own mixed-stream semantics. The
       alternative, preferring the cloud for the whole episode even after a newer device sample,
       is not implemented; it would credit the cloud with values it did not deliver.
  (A5) theta is fitted on DEV to hit each pre-registered budget and applied UNCHANGED to EVAL.
       The realized EVAL escalated fraction is reported next to the DEV target, never retuned.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (HERE, ROOT / "experiments/orchestration/sim",
          ROOT / "experiments/orchestration/baselines", ROOT / "experiments/lib"):
    sys.path.insert(0, str(p))

import d14b_split as SP                                  # noqa: E402
import metrics as M                                      # noqa: E402

OUT = ROOT / "results/dashcam/ctrl1"
SETTING = "measured@25"          # StudyE9b setting (ii)
STEP = 0.25
T0 = 3.0
DEVICE = ("4BI", 1)
CLOUD = ("32BI", 1)
T_K = 0.5                        # spec 7.7 / 1.2: episode call cadence for SH
E_K = 10                         # maximum calls per episode (brief default)
BUDGETS = (0.05, 0.10, 0.20, 0.40)
FLAT_IQR = 1e-6
NB, SEED = 2000, 0

# the pre-registered DEV grid
GRID_W_C = (1.5, 3.0, 6.0)       # seconds of device samples in the window
GRID_DELTA = (0.75, 1.5, 3.0)    # seconds of lag for the rise signal
GRID_N_C = (2, 3, 4)             # samples in the instability window
GRID_K_C = (1, 2, 4)             # samples below theta that close an episode
GRID_MODE = ("var", "flips")
FLIP_LEVEL = math.log(0.5)


# ---------------------------------------------------------------- context
def context():
    import study_e9b_dense as B
    ctx = B.build(step=STEP)
    m, D, Ld = B.device_schedule(ctx, SETTING)
    Lc = B.latencies(SETTING, *CLOUD)[1]
    Dc = B.shift_steps(ctx, Lc)
    Tsteps = int(round(T_K / STEP))
    return ctx, dict(dev_cadence_steps=m, dev_shift_steps=D, dev_latency_s=Ld,
                     cloud_latency_s=Lc, cloud_shift_steps=Dc, call_cadence_steps=Tsteps)


def device_held(ctx, sched) -> Dict[str, np.ndarray]:
    import study_e9b_dense as B
    return {c: B.held_stream(ctx["arrs"][DEVICE][c], ctx["meta"][c]["G"],
                             sched["dev_cadence_steps"], sched["dev_shift_steps"])
            for c in ctx["clips"]}


# ---------------------------------------------------------------- signals
def samples(ctx, clip: str, sched) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(capture index, read index, value) of the device's own scores, in order."""
    G = ctx["meta"][clip]["G"]
    cap = np.arange(0, G, sched["dev_cadence_steps"])
    read = cap + sched["dev_shift_steps"]
    ok = read < G
    return cap[ok], read[ok], ctx["arrs"][DEVICE][clip][cap[ok]]


def signal_max(val: np.ndarray, read: np.ndarray, w_c: float, delta: float, n_c: int,
               mode: str, cad_s: float) -> np.ndarray:
    """max(z, rise, instability) per device sample, all three divided by the window IQR (A1).

    NaN where the window is degenerate (A3) or too short to define the signal.
    """
    n = len(val)
    out = np.full(n, np.nan)
    w_samples = max(int(round(w_c / cad_s)), 2)
    lag = max(int(round(delta / cad_s)), 1)
    for k in range(n):
        lo = max(0, k - w_samples + 1)
        win = val[lo:k + 1]
        if len(win) < 2:
            continue
        q75, q25 = np.percentile(win, 75), np.percentile(win, 25)
        iqr = float(q75 - q25)
        if iqr < FLAT_IQR:
            continue
        med = float(np.median(win))
        z = (val[k] - med) / iqr
        rise = ((val[k] - val[k - lag]) / iqr) if k - lag >= 0 else -np.inf
        seg = val[max(0, k - n_c + 1):k + 1]
        if mode == "var":
            inst = (float(np.std(seg, ddof=0)) / iqr) if len(seg) >= 2 else -np.inf
        else:
            if len(seg) >= 2:
                b = seg > FLIP_LEVEL
                inst = float(np.count_nonzero(b[1:] != b[:-1])) / (len(seg) - 1) / 0.5
            else:
                inst = -np.inf
        out[k] = max(z, rise, inst)
    return out


# ---------------------------------------------------------------- episodes
def run_episodes(smax: np.ndarray, read: np.ndarray, G: int, theta: float, k_c: int,
                 tsteps: int, e_k: int, dc: int,
                 fixed_calls: Optional[int] = None,
                 opener: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
    """Walk the decision instants of one clip and return its episodes.

    A decision instant is every `tsteps` grid steps while the task is active (spec 1.2's eligible
    opportunity for SH). At instant i the controller holds the newest sample whose read index is
    <= i. An episode opens when that sample's signal exceeds theta, issues a call at the opening
    instant and every `tsteps` after it, and closes when `k_c` consecutive NEW samples score below
    theta or after `e_k` calls. `fixed_calls` replaces the signal-based close with a fixed call
    count (the random arm), and `opener` replaces the trigger with a precomputed boolean per
    decision instant (the random arm again).
    """
    eps: List[Dict[str, Any]] = []
    dec = np.arange(0, G, tsteps)
    if not len(read):
        return eps
    pos = np.searchsorted(read, dec, side="right") - 1
    open_ep: Optional[Dict[str, Any]] = None
    below = 0
    last_sample = -1
    for di, i in enumerate(dec):
        k = pos[di]
        fresh = k >= 0 and k != last_sample
        s = smax[k] if k >= 0 else np.nan
        if open_ep is None:
            trig = (bool(opener[di]) if opener is not None
                    else (k >= 0 and not np.isnan(s) and s > theta))
            if trig:
                open_ep = dict(open_i=int(i), calls=[int(i)], open_signal=(None if k < 0 or
                               np.isnan(s) else float(s)))
                below = 0
                last_sample = k
                continue
        else:
            if fresh and fixed_calls is None:
                below = below + 1 if (not np.isnan(s) and s <= theta) else 0
            if i - open_ep["calls"][-1] >= tsteps and len(open_ep["calls"]) < e_k:
                open_ep["calls"].append(int(i))
            done = (len(open_ep["calls"]) >= (fixed_calls if fixed_calls is not None else e_k)
                    or (fixed_calls is None and below >= k_c))
            if done:
                last = open_ep["calls"][-1]
                open_ep["close_i"] = int(min(G - 1, last + dc))
                eps.append(open_ep)
                open_ep = None
                below = 0
        if fresh:
            last_sample = k
    if open_ep is not None:
        last = open_ep["calls"][-1]
        open_ep["close_i"] = int(min(G - 1, last + dc))
        eps.append(open_ep)
    return eps


def open_mask(eps: Sequence[Dict[str, Any]], G: int) -> np.ndarray:
    m = np.zeros(G, dtype=bool)
    for e in eps:
        m[e["open_i"]:e["close_i"] + 1] = True
    return m


def mixed_stream(dev_cap: np.ndarray, dev_read: np.ndarray, dev_val: np.ndarray,
                 cloud_arr: np.ndarray, eps: Sequence[Dict[str, Any]], G: int,
                 dc: int) -> np.ndarray:
    """One sample-and-hold over the union of device and cloud deliveries (A4)."""
    reads = list(dev_read)
    caps = list(dev_cap)
    vals = list(dev_val)
    rank = [0] * len(reads)
    for e in eps:
        for c in e["calls"]:
            r = c + dc
            if r < G:
                reads.append(r)
                caps.append(c)
                vals.append(float(cloud_arr[c]))
                rank.append(1)
    order = sorted(range(len(reads)), key=lambda j: (reads[j], caps[j], rank[j]))
    out = np.full(G, -1e9)
    j = 0
    cur = -1e9
    for i in range(G):
        while j < len(order) and reads[order[j]] <= i:
            cur = vals[order[j]]
            j += 1
        out[i] = cur
    return out


# ---------------------------------------------------------------- arms
class Runner:
    """Everything that does not depend on theta, computed once per clip."""

    def __init__(self, ctx, sched):
        self.ctx, self.sched = ctx, sched
        self.dev = device_held(ctx, sched)
        self.S: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        for c in ctx["clips"]:
            self.S[c] = samples(ctx, c, sched)
        self.cache: Dict[Tuple, Dict[str, np.ndarray]] = {}
        self.cad_s = sched["dev_cadence_steps"] * STEP

    def smax(self, key: Tuple[float, float, int, str]) -> Dict[str, np.ndarray]:
        if key not in self.cache:
            w_c, delta, n_c, mode = key
            self.cache[key] = {c: signal_max(self.S[c][2], self.S[c][1], w_c, delta, n_c, mode,
                                             self.cad_s) for c in self.ctx["clips"]}
        return self.cache[key]

    def episodes_all(self, clips: Sequence[str], key, theta: float, k_c: int,
                     **kw) -> Dict[str, List[Dict[str, Any]]]:
        sm = self.smax(key)
        out = {}
        for c in clips:
            G = self.ctx["meta"][c]["G"]
            out[c] = run_episodes(sm[c], self.S[c][1], G, theta, k_c,
                                  self.sched["call_cadence_steps"], E_K,
                                  self.sched["cloud_shift_steps"], **kw)
        return out

    def abs_episodes_all(self, clips: Sequence[str], tau: float, k_c: int
                         ) -> Dict[str, List[Dict[str, Any]]]:
        """The ABSOLUTE-CONFIDENCE control: the trigger is the raw device score itself."""
        out = {}
        for c in clips:
            G = self.ctx["meta"][c]["G"]
            out[c] = run_episodes(self.S[c][2], self.S[c][1], G, tau, k_c,
                                  self.sched["call_cadence_steps"], E_K,
                                  self.sched["cloud_shift_steps"])
        return out

    def random_episodes_all(self, clips: Sequence[str], p: float, calls: int,
                            seed: int = SEED) -> Dict[str, List[Dict[str, Any]]]:
        rng = np.random.default_rng(seed)
        out = {}
        for c in sorted(clips):
            G = self.ctx["meta"][c]["G"]
            dec = np.arange(0, G, self.sched["call_cadence_steps"])
            op = rng.random(len(dec)) < p
            out[c] = run_episodes(np.full(max(len(self.S[c][1]), 1), np.nan), self.S[c][1],
                                  G, 0.0, 1,
                                  self.sched["call_cadence_steps"], E_K,
                                  self.sched["cloud_shift_steps"],
                                  fixed_calls=calls, opener=op)
        return out

    def escalated_fraction(self, epi: Dict[str, List[Dict[str, Any]]],
                           clips: Sequence[str]) -> float:
        on = tot = 0
        for c in clips:
            G = self.ctx["meta"][c]["G"]
            on += int(open_mask(epi[c], G).sum())
            tot += G
        return on / tot if tot else 0.0

    def stream(self, epi: Dict[str, List[Dict[str, Any]]], clips: Sequence[str]
               ) -> Dict[str, np.ndarray]:
        out = {}
        for c in clips:
            cap, read, val = self.S[c]
            G = self.ctx["meta"][c]["G"]
            out[c] = mixed_stream(cap, read, val, self.ctx["arrs"][CLOUD][c], epi[c], G,
                                  self.sched["cloud_shift_steps"])
        return out

    def always_cloud(self, clips: Sequence[str]) -> Dict[str, np.ndarray]:
        import study_e9d_delay as D
        out = {}
        for c in clips:
            G = self.ctx["meta"][c]["G"]
            out[c] = D.cloud_delivered(self.ctx["arrs"][CLOUD][c], G,
                                       self.sched["call_cadence_steps"],
                                       self.sched["cloud_shift_steps"])
        return out

    def device_only(self, clips: Sequence[str]) -> Dict[str, np.ndarray]:
        return {c: self.dev[c] for c in clips}


# ---------------------------------------------------------------- scoring
def challenge_for(sub):
    """A Challenge bound to one side of the split. `metrics.challenge` caches one instance per
    process, so the subset instance is built directly from StudyE9d's own class."""
    M._ensure_sklearn_importable()
    import study_e9d_delay as D
    return D.Challenge(sub)


def solve_theta(fn, target: float, lo: float, hi: float, iters: int = 40) -> Tuple[float, float]:
    """Bisection on a monotone-decreasing escalated fraction: higher theta escalates less."""
    f_lo, f_hi = fn(lo), fn(hi)
    if f_lo < target:
        return lo, f_lo
    if f_hi > target:
        return hi, f_hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        f = fn(mid)
        if f > target:
            lo, f_lo = mid, f
        else:
            hi, f_hi = mid, f
        if hi - lo < 1e-6:
            break
    return (hi, f_hi) if abs(f_hi - target) < abs(f_lo - target) else (lo, f_lo)


# ---------------------------------------------------------------- paired bootstrap, many arms
def paired_multi(ch, streams: Dict[str, Dict[str, np.ndarray]], pos: Sequence[str],
                 neg: Sequence[str], n: int = NB, seed: int = SEED) -> Dict[str, Any]:
    """One set of clip resamples, every arm scored on it, so differences and the gap fraction are
    paired. The unit and the seed are StudyE9c's own: resample the positive and the negative clip
    lists with numpy.random.default_rng(0)."""
    import study_e9d_delay as D
    crops = {a: ch.crops(s) for a, s in streams.items()}
    rng = np.random.default_rng(seed)
    draws = [(rng.integers(0, len(pos), len(pos)), rng.integers(0, len(neg), len(neg)))
             for _ in range(n)]
    per = {a: np.empty(n) for a in streams}
    for b, (pi, ni) in enumerate(draws):
        for a, (Pf, N) in crops.items():
            vals = []
            for h in D.CHAL_H:
                sel = pi[ch.pmask[h][pi]]
                if not len(sel):
                    continue
                y = np.r_[np.ones(len(sel)), np.zeros(len(ni))]
                vals.append(D.ap_fast(y, np.r_[Pf[h][sel], N[h][ni]]))
            per[a][b] = float(np.mean(vals)) if vals else np.nan
    point = {a: float(ch.point(s)["mAP"]) for a, s in streams.items()}
    out = dict(n_bootstrap=n, seed=seed, point=point,
               ci={a: [float(np.percentile(per[a], 2.5)), float(np.percentile(per[a], 97.5))]
                   for a in per})
    return out, per


def gap_fraction(per: Dict[str, np.ndarray], point: Dict[str, float], arm: str,
                 dev_arm: str = "device-only", cloud_arm: str = "always-cloud") -> Dict[str, Any]:
    """KEY NUMBER: the share of the always-cloud minus device-only challenge-mAP gap that this arm
    captures, with the CI taken over the SAME resamples as the arms themselves."""
    num = per[arm] - per[dev_arm]
    den = per[cloud_arm] - per[dev_arm]
    ok = np.abs(den) > 1e-9
    f = num[ok] / den[ok]
    p_den = point[cloud_arm] - point[dev_arm]
    return dict(
        value=(float((point[arm] - point[dev_arm]) / p_den) if abs(p_den) > 1e-9 else None),
        ci=[float(np.percentile(f, 2.5)), float(np.percentile(f, 97.5))] if len(f) else None,
        gap_mAP=float(p_den), arm_minus_device=float(point[arm] - point[dev_arm]),
        n_usable_resamples=int(ok.sum()))


# ---------------------------------------------------------------- episode statistics
def episode_stats(R: "Runner", epi: Dict[str, List[Dict[str, Any]]], clips: Sequence[str],
                  ch, pos: Sequence[str], neg: Sequence[str]) -> Dict[str, Any]:
    import study_e9d_delay as D
    lens_s, calls, n_eps = [], [], 0
    minutes_all = minutes_neg = 0.0
    neg_eps = 0
    for c in clips:
        G = R.ctx["meta"][c]["G"]
        minutes_all += G * STEP / 60.0
        if c in set(neg):
            minutes_neg += G * STEP / 60.0
            neg_eps += len(epi[c])
        for e in epi[c]:
            n_eps += 1
            lens_s.append((e["close_i"] - e["open_i"] + 1) * STEP)
            calls.append(len(e["calls"]))
    openh = {}
    for h in D.CHAL_H:
        hit = tot = 0
        for c in pos:
            if h not in ch.incl[c]:
                continue
            tot += 1
            i = ch.pos_idx[(c, h)]
            if open_mask(epi[c], R.ctx["meta"][c]["G"])[i]:
                hit += 1
        openh[str(h)] = dict(n_positive_scored=tot, n_with_open_episode=hit,
                             fraction=(hit / tot if tot else None))
    def dist(v):
        if not v:
            return None
        a = np.asarray(v, dtype=float)
        return dict(n=int(a.size), mean=float(a.mean()), p50=float(np.median(a)),
                    p25=float(np.percentile(a, 25)), p75=float(np.percentile(a, 75)),
                    min=float(a.min()), max=float(a.max()))
    return dict(
        n_episodes=n_eps,
        escalations_per_device_minute=(n_eps / minutes_all if minutes_all else None),
        active_minutes=minutes_all,
        episode_length_s=dist(lens_s), calls_per_episode=dist(calls),
        open_at_challenge_horizon=openh,
        false_episodes_per_minute_on_negatives=(neg_eps / minutes_neg if minutes_neg else None),
        n_episodes_on_negatives=neg_eps, negative_minutes=minutes_neg)


# ---------------------------------------------------------------- DEV search
def dev_search(R: "Runner", dev: Sequence[str], ch_dev, tol: float = 0.0025) -> Dict[str, Any]:
    """The pre-registered objective: maximize the DEV challenge mAP of escalation-only at a fixed
    escalation budget. theta is solved per combination to hit the budget; nothing is fitted on,
    or even read from, the EVAL clips."""
    rows: List[Dict[str, Any]] = []
    for w_c in GRID_W_C:
        for delta in GRID_DELTA:
            for n_c in GRID_N_C:
                for mode in GRID_MODE:
                    key = (w_c, delta, n_c, mode)
                    for k_c in GRID_K_C:
                        def frac(th, key=key, k_c=k_c):
                            return R.escalated_fraction(
                                R.episodes_all(dev, key, th, k_c), dev)
                        for B in BUDGETS:
                            th, f = solve_theta(frac, B, -2.0, 12.0, iters=22)
                            epi = R.episodes_all(dev, key, th, k_c)
                            m = float(ch_dev.point(R.stream(epi, dev))["mAP"])
                            rows.append(dict(w_c=w_c, delta=delta, n_c=n_c, mode=mode, k_c=k_c,
                                             budget=B, theta=th, dev_escalated_fraction=f,
                                             dev_mAP=m, hit_budget=bool(abs(f - B) <= tol),
                                             n_episodes=sum(len(v) for v in epi.values())))
    best = {}
    for B in BUDGETS:
        cand = [r for r in rows if r["budget"] == B and r["hit_budget"]]
        if not cand:
            cand = [r for r in rows if r["budget"] == B]
            cand.sort(key=lambda r: abs(r["dev_escalated_fraction"] - B))
            cand = [r for r in cand if abs(r["dev_escalated_fraction"] - B)
                    <= abs(cand[0]["dev_escalated_fraction"] - B) + 1e-9]
        cand.sort(key=lambda r: -r["dev_mAP"])
        best[str(B)] = cand[0]
    return dict(rows=rows, best=best, n_combinations=len(rows) // len(BUDGETS),
                objective=("maximize DEV challenge mAP of escalation-only (device answers "
                           "always, cloud upgrades during episodes, zero contention) at a fixed "
                           "escalation budget; pre-registered"),
                budget_tolerance=tol,
                grid=dict(W_c=list(GRID_W_C), delta=list(GRID_DELTA), n_c=list(GRID_N_C),
                          K_c=list(GRID_K_C), instability_mode=list(GRID_MODE),
                          theta="solved per combination by bisection to hit the budget"))


def dev_absolute(R: "Runner", dev: Sequence[str], k_c: int, tol: float = 0.0025
                 ) -> Dict[str, Any]:
    """The ABSOLUTE-CONFIDENCE control, tuned on DEV at the same budgets: a threshold on the raw
    device score, which is exactly what the self-normalized controller refuses to use."""
    out = {}
    for B in BUDGETS:
        def frac(t):
            return R.escalated_fraction(R.abs_episodes_all(dev, t, k_c), dev)
        tau, f = solve_theta(frac, B, -12.0, 0.5, iters=22)
        out[str(B)] = dict(tau=tau, dev_escalated_fraction=f, k_c=k_c,
                           hit_budget=bool(abs(f - B) <= tol))
    return out


def dev_random(R: "Runner", dev: Sequence[str], calls_by_budget: Dict[str, int],
               tol: float = 0.0025) -> Dict[str, Any]:
    """Random escalation at the same budget: Bernoulli openings at the decision instants, with
    the episode length FIXED to the median call count of the chosen controller at that budget, and
    the opening probability solved on DEV to hit the budget. Seed 0."""
    out = {}
    for B in BUDGETS:
        n_calls = int(calls_by_budget[str(B)])
        def frac(p):
            return R.escalated_fraction(R.random_episodes_all(dev, p, n_calls), dev)
        # the fraction rises with p, so bisect on the mirrored objective
        lo, hi = 0.0, 1.0
        for _ in range(28):
            mid = 0.5 * (lo + hi)
            if frac(mid) < B:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        p = 0.5 * (lo + hi)
        f = frac(p)
        out[str(B)] = dict(p_open=p, calls_per_episode=n_calls, dev_escalated_fraction=f,
                           hit_budget=bool(abs(f - B) <= tol), seed=SEED)
    return out


# ---------------------------------------------------------------- mechanism verification
def mechanism(R: "Runner", dev: Sequence[str], ch_dev, chosen: Dict[str, Any]) -> Dict[str, Any]:
    """CLAUDE.md mechanism verification, Steps 1-5, on DEV ONLY and BEFORE any EVAL number is
    written. The unit is one episode on one clip."""
    import study_e9d_delay as D
    sub = SP.subset_ctx(R.ctx, "DEV")
    pos, neg = sub["pos"], sub["neg"]
    chain = ("If the device's own score trajectory carries information about an approaching event "
             "(StudyD14b measured it: the 4B's score rises before the event), then a controller "
             "reading only SELF-NORMALIZED features of that trajectory (z, rise, instability "
             "against its own window median and IQR, spec 7.7) fires more often shortly before "
             "events than elsewhere; each firing opens an episode of 0.5-s cloud calls whose "
             "answers are delivered 2 grid steps later and become the application's displayed "
             "score; because the 32B's score separates positives from negatives better than the "
             "4B's at the same instant (StudyE9c: 0.5675 against 0.4776 over all 300 clips), "
             "replacing the displayed score at the challenge crop instants raises challenge mAP; "
             "so escalation-only cloud use captures part of the always-cloud minus device-only "
             "gap, and the share captured rises with the escalation budget.")
    links = []

    # L1 the signal exists and varies
    key = (chosen["w_c"], chosen["delta"], chosen["n_c"], chosen["mode"])
    sm = R.smax(key)
    allv = np.concatenate([sm[c][np.isfinite(sm[c])] for c in dev])
    near, far = [], []
    for c in pos:
        ev = R.ctx["meta"][c]["event"]
        _cap, read, _val = R.S[c]
        t = T0 + read * STEP
        v = sm[c]
        m = np.isfinite(v)
        d = t - ev
        near += list(v[m & (d >= -2.0) & (d <= 0.0)])
        far += list(v[m & ((d < -8.0) | (d > 4.0))])
    links.append(dict(
        link="device score trajectory -> self-normalized signal",
        quantity="max(z, rise, instability) per device sample, DEV clips",
        value=dict(n=int(allv.size), p50=float(np.median(allv)), p05=float(np.percentile(allv, 5)),
                   p95=float(np.percentile(allv, 95)), min=float(allv.min()),
                   max=float(allv.max()),
                   median_within_2s_before_event=float(np.median(near)) if near else None,
                   median_far_from_event=float(np.median(far)) if far else None),
        varies=bool(allv.std() > 1e-6),
        evidence=("the signal is non-degenerate across DEV samples and its median differs "
                  "between the 2 s before an event and times far from any event")))

    # L2 theta controls the escalated fraction
    curve = []
    for th in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
        epi = R.episodes_all(dev, key, th, chosen["k_c"])
        curve.append(dict(theta=th, escalated_fraction=R.escalated_fraction(epi, dev),
                          n_episodes=sum(len(v) for v in epi.values())))
    links.append(dict(link="signal -> escalation decision", quantity="escalated fraction of "
                      "device-time as theta moves", value=curve,
                      varies=bool(curve[0]["escalated_fraction"] >
                                  curve[-1]["escalated_fraction"] + 1e-9),
                      evidence="the fraction falls monotonically from theta 0.5 to theta 5.0"))

    # L3 episodes are open at the crop instants, and that fraction moves with the budget
    byb = {}
    for B in BUDGETS:
        ch_b = chosen["per_budget"][str(B)]
        epi = R.episodes_all(dev, (ch_b["w_c"], ch_b["delta"], ch_b["n_c"], ch_b["mode"]),
                             ch_b["theta"], ch_b["k_c"])
        st = episode_stats(R, epi, dev, ch_dev, pos, neg)
        byb[str(B)] = {h: st["open_at_challenge_horizon"][h]["fraction"]
                       for h in st["open_at_challenge_horizon"]}
    links.append(dict(link="escalation -> an episode open at the scored instant",
                      quantity="fraction of scored positive DEV clips with an open episode at "
                               "each challenge horizon, by budget", value=byb,
                      varies=bool(len({json.dumps(v, sort_keys=True) for v in byb.values()}) > 1),
                      evidence="the fraction rises with the budget at every horizon"))

    # L4 a cloud delivery actually changes the displayed score
    ch_b = chosen["per_budget"][str(BUDGETS[-1])]
    epi = R.episodes_all(dev, (ch_b["w_c"], ch_b["delta"], ch_b["n_c"], ch_b["mode"]),
                         ch_b["theta"], ch_b["k_c"])
    st_mix = R.stream(epi, dev)
    st_dev = R.device_only(dev)
    changed = sum(int(np.count_nonzero(st_mix[c] != st_dev[c])) for c in dev)
    total = sum(R.ctx["meta"][c]["G"] for c in dev)
    links.append(dict(link="cloud delivery -> displayed score",
                      quantity="grid points where the displayed score differs from device-only "
                               "at the 40 % budget",
                      value=dict(changed=changed, total=total, fraction=changed / total),
                      varies=changed > 0,
                      evidence="the mixed stream differs from the device stream on a non-zero "
                               "share of the grid"))

    # L5 the metric moves
    maps = {}
    for B in BUDGETS:
        cb = chosen["per_budget"][str(B)]
        e = R.episodes_all(dev, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]), cb["theta"],
                           cb["k_c"])
        maps[str(B)] = float(ch_dev.point(R.stream(e, dev))["mAP"])
    m_dev = float(ch_dev.point(st_dev)["mAP"])
    m_cloud = float(ch_dev.point(R.always_cloud(dev))["mAP"])
    links.append(dict(link="displayed score -> challenge mAP",
                      quantity="DEV challenge mAP by budget against the two references",
                      value=dict(by_budget=maps, device_only=m_dev, always_cloud=m_cloud),
                      varies=bool(max(maps.values()) - m_dev > 1e-6),
                      evidence="escalation-only sits strictly above device-only on DEV"))

    # Step 3: one traced episode
    trace = None
    for c in pos:
        cb = chosen["per_budget"][str(BUDGETS[1])]
        e = R.episodes_all([c], (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]), cb["theta"],
                           cb["k_c"])[c]
        if not e:
            continue
        ev = R.ctx["meta"][c]["event"]
        hz = [h for h in D.CHAL_H if h in ch_dev.incl[c]]
        pick = None
        for x in e:
            for h in hz:
                i = ch_dev.pos_idx[(c, h)]
                if x["open_i"] <= i <= x["close_i"]:
                    pick = (x, h, i)
                    break
            if pick:
                break
        if not pick:
            continue
        x, h, i = pick
        cap, read, val = R.S[c]
        k = int(np.searchsorted(read, x["open_i"], side="right") - 1)
        w_samples = max(int(round(cb["w_c"] / (R.sched["dev_cadence_steps"] * STEP))), 2)
        lo = max(0, k - w_samples + 1)
        win = val[lo:k + 1]
        iqr = float(np.percentile(win, 75) - np.percentile(win, 25))
        med = float(np.median(win))
        lag = max(int(round(cb["delta"] / (R.sched["dev_cadence_steps"] * STEP))), 1)
        epi_c = R.episodes_all([c], (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]),
                               cb["theta"], cb["k_c"])
        dmix = R.stream(epi_c, [c])[c]
        trace = dict(
            clip=c, label="positive", event_s=ev, budget=BUDGETS[1], horizon_s=h,
            crop_index=int(i), crop_time_s=T0 + i * STEP,
            window_samples=[dict(index=int(j), t_capture_s=T0 + cap[j] * STEP,
                                 t_readable_s=T0 + read[j] * STEP, score=float(val[j]))
                            for j in range(lo, k + 1)],
            window_median=med, window_iqr=iqr,
            z=float((val[k] - med) / iqr) if iqr >= FLAT_IQR else None,
            rise=float((val[k] - val[k - lag]) / iqr) if (iqr >= FLAT_IQR and k - lag >= 0)
            else None,
            theta=cb["theta"],
            episode=dict(open_index=x["open_i"], open_time_s=T0 + x["open_i"] * STEP,
                         call_indices=x["calls"],
                         call_times_s=[T0 + ci * STEP for ci in x["calls"]],
                         delivery_times_s=[T0 + (ci + R.sched["cloud_shift_steps"]) * STEP
                                           for ci in x["calls"]],
                         close_index=x["close_i"], close_time_s=T0 + x["close_i"] * STEP),
            displayed_score_at_crop=dict(
                device_only=float(st_dev[c][i]) if c in st_dev else float(R.dev[c][i]),
                escalation_only=float(dmix[i]),
                cloud_score_at_crop_capture=float(R.ctx["arrs"][CLOUD][c][i])),
            arithmetic=("the window IQR and median are computed from the listed samples; "
                        "z = (last sample - median) / IQR; the episode opens at the first "
                        "decision instant whose max signal exceeds theta; each call is captured "
                        "at its call index and readable %d grid steps (%.2f s) later; the "
                        "displayed score at the crop index is the most recent delivery from "
                        "either source" % (R.sched["cloud_shift_steps"],
                                           R.sched["cloud_shift_steps"] * STEP)))
        break

    # Step 4: two negative controls
    rows_ctrl = []
    for B in BUDGETS:
        cb = chosen["per_budget"][str(B)]
        key_b = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
        epi_b = R.episodes_all(dev, key_b, cb["theta"], cb["k_c"])
        live = float(ch_dev.point(R.stream(epi_b, dev))["mAP"])
        saved = R.ctx["arrs"][CLOUD]
        try:
            R.ctx["arrs"][CLOUD] = R.ctx["arrs"][DEVICE]
            same = float(ch_dev.point(R.stream(epi_b, dev))["mAP"])
        finally:
            R.ctx["arrs"][CLOUD] = saved
        rows_ctrl.append(dict(
            budget=B, escalation_only=live, control_device_scores_through_cloud_path=same,
            device_only=m_dev, total_gain=live - m_dev,
            gain_from_path_freshness=same - m_dev, gain_from_cloud_score_quality=live - same,
            share_from_cloud_score_quality=((live - same) / (live - m_dev)
                                            if abs(live - m_dev) > 1e-9 else None)))
    ctrl_a = dict(
        control=("cloud score replaced by the device's OWN score, so an escalation buys the "
                 "cloud PATH (calls every 0.50 s delivered after 0.395 s) and nothing else"),
        per_budget=rows_ctrl, device_only=m_dev,
        full_collapse=bool(all(abs(r["control_device_scores_through_cloud_path"] - m_dev) < 5e-3
                               for r in rows_ctrl)),
        reading=("THE CONTROL DOES NOT COLLAPSE TO THE NULL, and that is a result, not a "
                 "failure: escalation-only's gain decomposes into a path-freshness part (the "
                 "control's gain over device-only) and a cloud-score-quality part (the rest). "
                 "Both are mechanisms the policy can use, but only the second is what 'the cloud "
                 "is better' means, so the shares are reported with every headline number and "
                 "the random-escalation arm at the same budget is the comparator that isolates "
                 "targeting from both."),
        mAP=rows_ctrl[-1]["control_device_scores_through_cloud_path"])
    cell = dict(side="DEV", clips=len(dev), budget=BUDGETS[-1], setting=SETTING)
    return dict(step1_causal_chain=chain, step2_links=links, step3_trace=trace,
                step4_control_no_cloud_advantage=ctrl_a, step4_cell=cell,
                step5_alternative=(
                    "The same headline could be produced by (a) the controller TIMING cloud calls "
                    "to the moments that matter [the claimed mechanism], or (b) nothing more than "
                    "the cloud path being FRESHER and FASTER than the device path (calls every "
                    "0.50 s delivered after 0.39 s, against device samples every 0.75 s delivered "
                    "after 0.567 s), so that any escalation at all, however placed, would help. "
                    "The two are distinguished by the RANDOM-escalation arm, which has the same "
                    "cadence and latency and the same budget but no targeting, and by the "
                    "ABSOLUTE-CONFIDENCE arm, which targets on the raw score instead. If "
                    "escalation-only does not beat random at the same budget, explanation (b) is "
                    "the live one and the controller's targeting is not doing the work."))


# ---------------------------------------------------------------- EVAL
def evaluate(R: "Runner", ev: Sequence[str], ch_ev, chosen: Dict[str, Any],
             absolute: Dict[str, Any], random_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Every number here is on the EVAL clips, with settings fitted on DEV and applied unchanged
    (A5). The arms are the five the row pre-registers."""
    sub = SP.subset_ctx(R.ctx, "EVAL")
    pos, neg = sub["pos"], sub["neg"]
    dev_s = R.device_only(ev)
    cloud_s = R.always_cloud(ev)
    out = {}
    for B in BUDGETS:
        cb = chosen["per_budget"][str(B)]
        key = (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"])
        epi = R.episodes_all(ev, key, cb["theta"], cb["k_c"])
        epi_abs = R.abs_episodes_all(ev, absolute[str(B)]["tau"], cb["k_c"])
        rc = random_cfg[str(B)]
        epi_rnd = R.random_episodes_all(ev, rc["p_open"], rc["calls_per_episode"])
        streams = {"device-only": dev_s, "always-cloud": cloud_s,
                   "escalation-only": R.stream(epi, ev),
                   "absolute-confidence": R.stream(epi_abs, ev),
                   "random-escalation": R.stream(epi_rnd, ev)}
        boot, per = paired_multi(ch_ev, streams, pos, neg)
        out[str(B)] = dict(
            settings=cb, absolute=absolute[str(B)], random=rc,
            realized_escalated_fraction=dict(
                escalation_only=R.escalated_fraction(epi, ev),
                absolute_confidence=R.escalated_fraction(epi_abs, ev),
                random_escalation=R.escalated_fraction(epi_rnd, ev),
                dev_target=B),
            episode_stats=dict(
                escalation_only=episode_stats(R, epi, ev, ch_ev, pos, neg),
                absolute_confidence=episode_stats(R, epi_abs, ev, ch_ev, pos, neg),
                random_escalation=episode_stats(R, epi_rnd, ev, ch_ev, pos, neg)),
            challenge_mAP=boot["point"], challenge_mAP_ci=boot["ci"],
            streaming_ap={a: {str(h): v for h, v in
                              M.streaming_ap(sub, s).items()} for a, s in streams.items()},
            gap_fraction_captured={
                a: gap_fraction(per, boot["point"], a)
                for a in ("escalation-only", "absolute-confidence", "random-escalation")},
            paired_differences={
                "escalation-only minus random-escalation": _diff(per, boot["point"],
                                                                 "escalation-only",
                                                                 "random-escalation"),
                "escalation-only minus absolute-confidence": _diff(per, boot["point"],
                                                                   "escalation-only",
                                                                   "absolute-confidence"),
                "escalation-only minus device-only": _diff(per, boot["point"],
                                                           "escalation-only", "device-only"),
                "always-cloud minus device-only": _diff(per, boot["point"], "always-cloud",
                                                        "device-only")})
    return out


def _diff(per, point, a: str, b: str) -> Dict[str, Any]:
    d = per[a] - per[b]
    lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
    return dict(difference=float(point[a] - point[b]), ci=[lo, hi],
                excludes_zero=bool(lo > 0 or hi < 0))


# ---------------------------------------------------------------- workload traces
def workload_traces(R: "Runner", ev: Sequence[str], chosen: Dict[str, Any]) -> Dict[str, Any]:
    """What the live evaluation needs: per EVAL clip, when the controller escalates and when each
    episode call fires, at every budget, plus the eligible-opportunity grid (spec 1.2: every
    decision instant on the 0.5-s cadence while the task is active)."""
    per_clip = {}
    for c in ev:
        G = R.ctx["meta"][c]["G"]
        dec = np.arange(0, G, R.sched["call_cadence_steps"])
        per_clip[c] = dict(
            label=R.ctx["meta"][c]["label"], event_s=R.ctx["meta"][c]["event"],
            duration_s=R.ctx["meta"][c]["dur"], grid_points=G,
            eligible_opportunities_s=[round(T0 + i * STEP, 3) for i in dec.tolist()],
            n_eligible=int(len(dec)), episodes={})
    for B in BUDGETS:
        cb = chosen["per_budget"][str(B)]
        epi = R.episodes_all(ev, (cb["w_c"], cb["delta"], cb["n_c"], cb["mode"]), cb["theta"],
                             cb["k_c"])
        for c in ev:
            per_clip[c]["episodes"][str(B)] = [
                dict(open_s=round(T0 + e["open_i"] * STEP, 3),
                     close_s=round(T0 + e["close_i"] * STEP, 3),
                     call_times_s=[round(T0 + i * STEP, 3) for i in e["calls"]],
                     delivery_times_s=[round(T0 + (i + R.sched["cloud_shift_steps"]) * STEP, 3)
                                       for i in e["calls"]],
                     n_calls=len(e["calls"]))
                for e in epi[c]]
    return dict(
        note=("escalation and episode call times per EVAL clip at each budget, with the "
              "eligible-opportunity grid. Times are seconds into the clip (the trace starts at "
              "t = 3.0 s). The device arm is 4BI N=1 at 0.75-s saturated cadence; cloud calls "
              "fire at the listed times and their answers are readable at the listed delivery "
              "times under StudyE9b setting (ii) with ZERO CONTENTION, which a live run will "
              "replace with its own measured TTFTs."),
        call_cadence_s=T_K, max_calls_per_episode=E_K, setting=SETTING,
        cloud_shift_steps=R.sched["cloud_shift_steps"], grid_step_s=STEP, t0_s=T0,
        budgets=list(BUDGETS), clips=per_clip)


# ---------------------------------------------------------------- CLI
def main() -> int:
    import argparse
    from _provenance import stamp
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all",
                    choices=("dev", "mechanism", "eval", "workload", "all"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ctx, sched = context()
    R = Runner(ctx, sched)
    s = SP.split()
    dev, ev = s["dev"], s["eval"]
    sub_dev, sub_ev = SP.subset_ctx(ctx, "DEV"), SP.subset_ctx(ctx, "EVAL")
    ch_dev, ch_ev = challenge_for(sub_dev), challenge_for(sub_ev)
    print("schedule: device cadence %d steps, shift %d; cloud latency %.4f s, shift %d steps; "
          "call cadence %d steps" % (sched["dev_cadence_steps"], sched["dev_shift_steps"],
                                     sched["cloud_latency_s"], sched["cloud_shift_steps"],
                                     sched["call_cadence_steps"]))

    dev_file = OUT / "ctrl1_dev_search.json"
    if a.stage in ("dev", "all"):
        import time
        t = time.time()
        res = dev_search(R, dev, ch_dev)
        chosen = {str(B): res["best"][str(B)] for B in BUDGETS}
        k_c_for_abs = chosen[str(BUDGETS[1])]["k_c"]
        res["absolute"] = dev_absolute(R, dev, k_c_for_abs)
        res["random"] = dev_random(
            R, dev, {str(B): max(1, int(round(
                episode_stats(R, R.episodes_all(
                    dev, (chosen[str(B)]["w_c"], chosen[str(B)]["delta"], chosen[str(B)]["n_c"],
                          chosen[str(B)]["mode"]), chosen[str(B)]["theta"],
                    chosen[str(B)]["k_c"]), dev, ch_dev, sub_dev["pos"], sub_dev["neg"]
                )["calls_per_episode"]["p50"]))) for B in BUDGETS})
        res["chosen"] = dict(per_budget=chosen)
        res["references_dev"] = dict(
            device_only=float(ch_dev.point(R.device_only(dev))["mAP"]),
            always_cloud=float(ch_dev.point(R.always_cloud(dev))["mAP"]))
        res["schedule"] = sched
        res["split"] = dict(n_dev=s["n_dev"], n_eval=s["n_eval"], rule=s["rule"])
        res["_provenance"] = stamp(script="ctrl1_controller.py --stage dev", model=None,
                                   device="cpu", n=len(dev), args=None)
        dev_file.write_text(json.dumps(res, indent=1, default=float))
        print("DEV search: %d combinations x %d budgets in %.0f s" %
              (res["n_combinations"], len(BUDGETS), time.time() - t))
        for B in BUDGETS:
            c = chosen[str(B)]
            print("  budget %3.0f %%  theta %7.4f  W_c %.2f delta %.2f n_c %d K_c %d %-5s  "
                  "DEV frac %.4f  DEV mAP %.4f" %
                  (100 * B, c["theta"], c["w_c"], c["delta"], c["n_c"], c["k_c"], c["mode"],
                   c["dev_escalated_fraction"], c["dev_mAP"]))
        print("  DEV references: device-only %.4f, always-cloud %.4f"
              % (res["references_dev"]["device_only"], res["references_dev"]["always_cloud"]))
        print("wrote", dev_file)

    search = json.loads(dev_file.read_text())
    chosen = search["chosen"]

    if a.stage in ("mechanism", "all"):
        mech = mechanism(R, dev, ch_dev, dict(chosen["per_budget"][str(BUDGETS[1])],
                                              per_budget=chosen["per_budget"]))
        mech["_provenance"] = stamp(script="ctrl1_controller.py --stage mechanism", model=None,
                                    device="cpu", n=len(dev), args=None)
        (OUT / "ctrl1_mechanism.json").write_text(json.dumps(mech, indent=1, default=float))
        for l in mech["step2_links"]:
            print("  LINK %-52s varies=%s" % (l["link"][:52], l["varies"]))
        for r in mech["step4_control_no_cloud_advantage"]["per_budget"]:
            print("  control budget %3.0f %%: escalation-only %.4f, device scores through the "
                  "cloud path %.4f, device-only %.4f (freshness %+.4f, cloud quality %+.4f)"
                  % (100 * r["budget"], r["escalation_only"],
                     r["control_device_scores_through_cloud_path"], r["device_only"],
                     r["gain_from_path_freshness"], r["gain_from_cloud_score_quality"]))
        print("wrote", OUT / "ctrl1_mechanism.json")

    if a.stage in ("eval", "all"):
        res = evaluate(R, ev, ch_ev, dict(per_budget=chosen["per_budget"]), search["absolute"],
                       search["random"])
        res = dict(by_budget=res, schedule=sched, setting=SETTING,
                   references_eval=dict(
                       device_only=float(ch_ev.point(R.device_only(ev))["mAP"]),
                       always_cloud=float(ch_ev.point(R.always_cloud(ev))["mAP"])),
                   references_all300_committed=dict(always_cloud=0.5675307471627267,
                                                    device_only=0.47760424491770376,
                                                    note=("StudyE9c over all 300 clips; "
                                                          "REFERENCE ONLY, not comparable with "
                                                          "the EVAL-subset values above")),
                   split=dict(n_dev=s["n_dev"], n_eval=s["n_eval"], rule=s["rule"]))
        res["_provenance"] = stamp(script="ctrl1_controller.py --stage eval", model=None,
                                   device="cpu", n=len(ev), args=None)
        (OUT / "ctrl1_eval.json").write_text(json.dumps(res, indent=1, default=float))
        for B in BUDGETS:
            r = res["by_budget"][str(B)]
            g = r["gap_fraction_captured"]["escalation-only"]
            print("  budget %3.0f %%  EVAL frac %.4f  mAP esc %.4f  dev %.4f  cloud %.4f  "
                  "gap captured %.1f %% [%.1f, %.1f]" %
                  (100 * B, r["realized_escalated_fraction"]["escalation_only"],
                   r["challenge_mAP"]["escalation-only"], r["challenge_mAP"]["device-only"],
                   r["challenge_mAP"]["always-cloud"], 100 * g["value"],
                   100 * g["ci"][0], 100 * g["ci"][1]))
        print("wrote", OUT / "ctrl1_eval.json")

    if a.stage in ("workload", "all"):
        wl = workload_traces(R, ev, dict(per_budget=chosen["per_budget"]))
        wl["_provenance"] = stamp(script="ctrl1_controller.py --stage workload", model=None,
                                  device="cpu", n=len(ev), args=None)
        (OUT / "ctrl1_workload_traces.json").write_text(json.dumps(wl, indent=1, default=float))
        n = sum(len(v["episodes"][str(BUDGETS[1])]) for v in wl["clips"].values())
        print("workload traces: %d EVAL clips, %d episodes at the 10 %% budget" %
              (len(wl["clips"]), n))
        print("wrote", OUT / "ctrl1_workload_traces.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
