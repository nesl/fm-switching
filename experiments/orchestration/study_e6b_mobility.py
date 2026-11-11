#!/usr/bin/env python3
"""StudyE6b-mobility STAGE A — offline replay of committed results over network traces.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every accuracy and every
latency is read from a committed result file of an earlier study.

Stage A delivers: the rebuilt cost model (errors 1-3 of StudyE4/StudyE6(b) fixed), the static
configurations, P1 and the oracle for all regimes, negative control (a), E4 table 4.1 recomputed
under both deployment modes, and one instrumented per-question trace through an outage.
Configurations that need StudyE7/StudyE8 are listed PENDING and never estimated.
"""
import collections, gzip, json, os, sys
from datetime import datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
from _provenance import stamp  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.model_selection import KFold  # noqa: E402

OUT = ROOT / "results/orchestration/study_e6b"
E4D = ROOT / "results/orchestration/study_e4"
SEED, NB, NOFF, NFOLD = 0, 2000, 20, 5
# uplink Mbit/s -> RTT s, as pre-registered
NETS = {"5Mbps_60ms": (5.0, 0.060), "13.6Mbps_44ms": (13.6, 0.044), "88Mbps_22ms": (88.0, 0.022)}
DEADLINES = (1, 2, 5, 10)
MODES = ("STREAM", "ON_DEMAND")
PRIMARY_FMT = "png"
D2_TOKENS_PER_S = 45.0          # RH4: 5 images (450 tokens) per 10 s of session
D2_WARM_TOTAL_MINUS_TTFT = 0.027  # F3 cell d, measured


def jl(p):
    op = gzip.open if str(p).endswith(".gz") else open
    return [json.loads(l) for l in op(p, "rt")]


FB = {}


def fbytes(hw, fmt):
    k = f"{hw[1]}x{hw[0]}"
    if k not in FB:
        k = f"{hw[0]}x{hw[1]}"
    return float(FB[k]["png_median"] if fmt == "png" else FB[k]["raw"])


# ---------------------------------------------------------------- latency curves (StudyF3)
class PolyCurve:
    """StudyF3 fitted curve. Inside token_range: deg2 fit. Outside: UNKNOWN (primary) or the
    deg1 fit (labelled linear-extrapolation sensitivity)."""

    def __init__(self, d, which="total"):
        self.lo, self.hi = d[which]["token_range"]
        self.q = np.array(d[which]["deg2"]["coef_high_to_low"])
        self.l = np.array(d[which]["deg1"]["coef_high_to_low"])
        self.src = which

    def at(self, x, extrap=False):
        if x is None:
            return None, "INFEASIBLE"
        if self.lo <= x <= self.hi:
            return float(np.polyval(self.q, x)), "measured"
        if not extrap:
            return None, "UNKNOWN"
        return float(max(np.polyval(self.l, x), 0.0)), "EXTRAPOLATED"


class BinCurve:
    """Binned-median interpolation (StudyE4's device curve, kept so check 1 can compare)."""

    def __init__(self, points, binw=100):
        b = collections.defaultdict(list)
        for x, y in points:
            b[int(x // binw)].append((x, y))
        self.cx = np.array([np.median([a for a, _ in v]) for _, v in sorted(b.items())])
        self.cy = np.array([np.median([c for _, c in v]) for _, v in sorted(b.items())])
        self.lo, self.hi = float(self.cx[0]), float(self.cx[-1])

    def at(self, x, extrap=False):
        if x is None:
            return None, "INFEASIBLE"
        if self.lo <= x <= self.hi:
            return float(np.interp(x, self.cx, self.cy)), "measured"
        if not extrap:
            return None, "UNKNOWN"
        s = (self.cy[-1] - self.cy[-2]) / (self.cx[-1] - self.cx[-2])
        return float(max(self.cy[-1] + s * (x - self.hi), 0.0)), "EXTRAPOLATED"


# ---------------------------------------------------------------- configurations
# name, model, location, representation, cache, answers key, curve key, stream rate class
CONFIGS = [
    ("cl-4B-RECENT",   "4B",  "cloud",  "RECENT", "cold", "H1",  "4BI/video/COLD",   "RECENT"),
    ("cl-4B-RICH",     "4B",  "cloud",  "RICH",   "cold", "H2",  "4BI/video/COLD",   "RICH"),
    ("cl-4B-U",        "4B",  "cloud",  "U",      "cold", "U4",  "4BI/video/COLD",   "U"),
    ("cl-32B-RECENT",  "32B", "cloud",  "RECENT", "cold", "K3",  "32BI/video/COLD",  "RECENT"),
    ("cl-32B-RICH",    "32B", "cloud",  "RICH",   "cold", "K1",  "32BI/video/COLD",  "RICH"),
    ("cl-32B-U",       "32B", "cloud",  "U",      "cold", "U32", "32BI/video/COLD",  "U"),
    ("cl-32B-D2-cold", "32B", "cloud",  "D2",     "cold", "D2",  "32BI/images/COLD", "D2"),
    ("cl-32B-D2-warm", "32B", "cloud",  "D2",     "warm", "D2",  "32BI/images/WARM", "D2"),
    ("dev-4B-SHORT-N1", "4B", "device", "SHORT1", "cold", "F4N1", "device_fixed",    None),
    ("dev-4B-SHORT-N3", "4B", "device", "SHORT3", "cold", "F4N3", "device_fixed",    None),
    ("dev-4B-SHORT-N9", "4B", "device", "SHORT9", "cold", "F4N9", "device_fixed",    None),
    ("dev-4B-RECENT",  "4B",  "device", "RECENT", "cold", "H1",  "device_cold",      None),
]
PENDING = {
    "cl-4B-D2-cold": "StudyE7 (4B D2 letters)",
    "cl-4B-D2-warm": "StudyE7 (4B D2 letters)",
    "dev-4B-D2-warm": "StudyE7 letters + StudyE8 Part D parity, Part B warm-up curve",
    "dev-4B-D2-cold": "StudyE7 letters + StudyE8 Part D parity",
    "device keep-warm energy": "StudyE8 Parts A and C",
}


def load():
    man = collections.defaultdict(dict)
    for r in jl(ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"):
        man[r["question_id"]][r["construction"]] = r
    ans, tok = {}, {}

    def put(key, rows, f):
        ans[key], tok[key] = {}, {}
        for r in rows:
            if r.get("error") or not f(r):
                continue
            ans[key][r["question_id"]] = bool(r["correct"])
            tok[key][r["question_id"]] = r.get("prompt_tokens")

    r1 = jl(ROOT / "results/sember/study_r1/study_r1_requests_h100nvl.jsonl.gz")
    put("K3", r1, lambda r: r["cell"] == "K3" and r["mode"] == "batched")
    put("K1", r1, lambda r: r["cell"] == "K1" and r["mode"] == "batched")
    cl = jl(ROOT / "results/cost/study_clean/study_clean_requests_h100nvl.jsonl.gz")
    put("H1", cl, lambda r: r["cell"] == "H1" and r["mode"] == "batched")
    put("H2", cl, lambda r: r["cell"] == "H2" and r["mode"] == "batched")
    put("D2", jl(ROOT / "results/sember/study_rh4/study_rh4_requests_h100nvl.jsonl.gz"),
        lambda r: r["cell"] == "D2" and r["mode"] == "batched")
    d11 = jl(ROOT / "results/cost/study_d11/study_d11_requests_h100nvl.jsonl")
    put("U4", d11, lambda r: r["arm"] == "U" and r["model"] == "4BI")
    put("U32", d11, lambda r: r["arm"] == "U" and r["model"] == "32BI")
    f4 = jl(ROOT / "results/device/study_f4/partA_accuracy.jsonl")
    for n in (1, 3, 9):
        ans[f"F4N{n}"] = {r["question_id"]: bool(r["correct"]) for r in f4
                          if int(r["n_frames"]) == n and not r.get("error")}
        tok[f"F4N{n}"] = {r["question_id"]: r.get("input_tokens") for r in f4 if int(r["n_frames"]) == n}
    return man, ans, tok


def device_fixed_latency():
    """StudyF4 Part B total latency p50 per N (device, cold, measured)."""
    rows = jl(ROOT / "results/device/study_f4/partB_latency.jsonl")
    out = {}
    for n in (1, 3, 9):
        v = [r["total_latency_s"] for r in rows if int(r["n_frames"]) == n
             and r.get("total_latency_s") and not r.get("warmup")]
        out[n] = float(np.median(v))
        assert len(v) >= 40, (n, len(v))
    return out


def device_cold_curve():
    pts = []
    for p in ("devfast_4bi_f16_n9.jsonl", "devfast_4bi_f16_n18.jsonl",
              "devfast_4bi_f16_n37.jsonl", "dev_one_n1.jsonl"):
        pts += [(r["input_tokens"], r["total_latency_s"]) for r in jl(ROOT / "results/device" / p)
                if r.get("total_latency_s") and (r.get("input_tokens") or 0) > 100]
    return BinCurve(pts)


# ---------------------------------------------------------------- network replay
def prefix_connected(conn):
    c = np.zeros(len(conn) + 1)
    c[1:] = np.cumsum(conn)
    return c


def queue_bytes(conn, gen_bps, up_bps):
    """Backlog at the START of each second for a FIFO queue fed at gen_bps and drained at
    up_bps while connected. queue[t] = S[t] - min_{k<=t} S[k] (reflected random walk)."""
    d = gen_bps - up_bps * conn
    s = np.zeros(len(conn) + 1)
    s[1:] = np.cumsum(d)
    return s - np.minimum.accumulate(s)


def drain_s(C, t0, need_s):
    """Wall-clock seconds from t0 until `need_s` seconds of CONNECTED time have elapsed.
    None if the trace ends first."""
    if need_s <= 0:
        return 0.0
    base = C[t0]
    k = int(np.searchsorted(C[t0:], base + need_s, side="left"))
    if k >= len(C) - t0:
        return None
    full = C[t0 + k - 1] - base
    return float((k - 1) + (need_s - full))


def main():
    global FB
    OUT.mkdir(parents=True, exist_ok=True)
    FB = json.loads((E4D / "e4_frame_bytes.json").read_text())["sizes"]
    f3 = json.loads((ROOT / "results/cost/study_f3/f3_results.json").read_text())["curves"]
    man, ans, tok = load()
    Q = sorted(man)
    assert len(Q) == 845
    meta = {q: dict(video=man[q]["RECENT"]["video_id"], qt=float(man[q]["RECENT"]["question_time"]),
                    cat=man[q]["RECENT"]["question_category"]) for q in Q}
    qi = {q: i for i, q in enumerate(Q)}
    N = len(Q)

    # ---- curves
    curves = {"4BI/video/COLD": PolyCurve(f3["4BI/video/COLD"]),
              "32BI/video/COLD": PolyCurve(f3["32BI/video/COLD"]),
              "32BI/images/COLD": PolyCurve(f3["32BI/images/COLD"])}
    warm = f3["32BI/images/WARM"]["ttft_vs_uncached_tokens"]
    curves["32BI/images/WARM"] = PolyCurve({"total": warm}, "total")
    dev_fixed, dev_curve = device_fixed_latency(), device_cold_curve()

    # ---- frames per arm (E4/E6 definitions, unchanged)
    byv = collections.defaultdict(list)
    for q in Q:
        byv[meta[q]["video"]].append(q)
    prev_qt = {}
    for v, qs in byv.items():
        qs.sort(key=lambda q: (meta[q]["qt"], q))
        for i, q in enumerate(qs):
            e = [meta[p]["qt"] for p in qs[:i] if meta[p]["qt"] < meta[q]["qt"]]
            prev_qt[q] = max(e) if e else None

    def frames(rep, q):
        rec, rich = man[q]["RECENT"], man[q]["RICH"]
        if rep == "RECENT":
            return [(t, rec["final_hw"]) for t in rec["frame_t"]]
        if rep == "RICH":
            return [(t, rich["final_hw"]) for t in rich["frame_t"]]
        if rep == "U":
            t0 = min(rec["frame_t"]) if rec["frame_t"] else meta[q]["qt"]
            return ([(t, rich["final_hw"]) for t in rich["frame_t"] if t < t0]
                    + [(t, rec["final_hw"]) for t in rec["frame_t"]])
        if rep == "D2":
            return [(float(t), (256, 352)) for t in range(0, int(meta[q]["qt"]) + 1, 2)]
        raise ValueError(rep)

    STREAM_RATE = {}   # representation -> bytes per second offered, per format
    for fmt in ("png", "raw"):
        STREAM_RATE[("RECENT", fmt)] = fbytes((384, 512), fmt) * 1.0
        STREAM_RATE[("RICH", fmt)] = fbytes((256, 352), fmt) * 1.0
        STREAM_RATE[("U", fmt)] = (fbytes((384, 512), fmt) + fbytes((256, 352), fmt)) * 1.0
        STREAM_RATE[("D2", fmt)] = fbytes((256, 352), fmt) * 0.5

    NEWEST_FRAME = {}  # the frame captured at the question instant is still pending (E6 Part 0 rule)
    for fmt in ("png", "raw"):
        NEWEST_FRAME[("RECENT", fmt)] = fbytes((384, 512), fmt)
        NEWEST_FRAME[("U", fmt)] = fbytes((384, 512), fmt)
        NEWEST_FRAME[("RICH", fmt)] = fbytes((256, 352), fmt)
        NEWEST_FRAME[("D2", fmt)] = fbytes((256, 352), fmt)

    ondemand = {}      # (rep, fmt) -> array over Q
    for rep in ("RECENT", "RICH", "U", "D2"):
        for fmt in ("png", "raw"):
            ondemand[(rep, fmt)] = np.array([sum(fbytes(hw, fmt) for _, hw in frames(rep, q)) for q in Q])

    # ---- per-config compute latency and correctness
    comp, comp_x, status, corr, avail = {}, {}, {}, {}, {}
    for name, model, loc, rep, cache, key, ck, _rate in CONFIGS:
        c = np.full(N, np.nan); cx = np.full(N, np.nan)
        st = np.empty(N, dtype=object); y = np.zeros(N); av = np.zeros(N, dtype=bool)
        for q in Q:
            i = qi[q]
            if q not in ans[key]:
                st[i] = "INFEASIBLE"
                continue
            y[i] = 1.0 if ans[key][q] else 0.0
            av[i] = True
            if ck == "device_fixed":
                n = int(rep[-1]); c[i] = cx[i] = dev_fixed[n]; st[i] = "measured"
            elif ck == "device_cold":
                v, s = dev_curve.at(tok[key].get(q)); vx, _ = dev_curve.at(tok[key].get(q), True)
                c[i] = np.nan if v is None else v; cx[i] = np.nan if vx is None else vx; st[i] = s
            elif cache == "warm":
                un = (D2_TOKENS_PER_S * (meta[q]["qt"] - prev_qt[q])) if prev_qt[q] is not None else None
                if un is None:
                    st[i] = "COLD_FIRST_QUESTION"   # no warm session yet; handled by the cold config
                    av[i] = False
                    continue
                v, s = curves[ck].at(un); vx, _ = curves[ck].at(un, True)
                c[i] = np.nan if v is None else v + D2_WARM_TOTAL_MINUS_TTFT
                cx[i] = np.nan if vx is None else vx + D2_WARM_TOTAL_MINUS_TTFT
                st[i] = s
            else:
                v, s = curves[ck].at(tok[key].get(q)); vx, _ = curves[ck].at(tok[key].get(q), True)
                c[i] = np.nan if v is None else v; cx[i] = np.nan if vx is None else vx; st[i] = s
        comp[name], comp_x[name], status[name], corr[name], avail[name] = c, cx, st, y, av

    # ---- E6 setting (a) best rule: evidence-only, F1, logreg, cross-fit by video, seed 0
    E6CELLS = ["H1", "H2", "K3", "K1"]
    E6MODEL = {"H1": "4B", "H2": "4B", "K3": "32B", "K1": "32B"}
    cats = sorted({meta[q]["cat"] for q in Q})
    bins = ["le120", "120-480", "gt480"]

    def qbin(t):
        return "le120" if t <= 120 else ("120-480" if t <= 480 else "gt480")

    X = np.array([[1.0 * (meta[q]["cat"] == c) for c in cats]
                  + [1.0 * (qbin(meta[q]["qt"]) == b) for b in bins]
                  + [meta[q]["qt"], meta[q]["qt"] / 600.0] for q in Q])
    Yc = {c: np.array([1.0 if ans[c][q] else 0.0 for q in Q]) for c in E6CELLS}
    vids = sorted(byv)
    vfold = {}
    for fi, (_, te) in enumerate(KFold(NFOLD, shuffle=True, random_state=SEED).split(vids)):
        for i in te:
            vfold[vids[i]] = fi
    fold = np.array([vfold[meta[q]["video"]] for q in Q])
    P = {c: np.zeros(N) for c in E6CELLS}
    for fi in range(NFOLD):
        tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
        sc = StandardScaler(with_mean=False).fit(X[tr])
        for c in E6CELLS:
            m = LogisticRegression(max_iter=3000, C=1.0, random_state=SEED).fit(sc.transform(X[tr]), Yc[c][tr])
            P[c][te] = m.predict_proba(sc.transform(X[te]))[:, 1]
    e6_cell = np.empty(N, dtype=object)
    e6_static = {}
    for fi in range(NFOLD):
        tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
        bstat = max(E6CELLS, key=lambda c: (Yc[c][tr].mean(), c))
        e6_static[fi] = bstat
        keep = [c for c in E6CELLS if E6MODEL[c] == E6MODEL[bstat]]
        for i in te:
            e6_cell[i] = max(keep, key=lambda c: (P[c][i], c))
    CELL2CFG = {"H1": "cl-4B-RECENT", "H2": "cl-4B-RICH", "K3": "cl-32B-RECENT", "K1": "cl-32B-RICH"}
    p1_cfg = np.array([CELL2CFG[c] for c in e6_cell], dtype=object)

    # ---- traces
    tz = np.load(OUT / "e6b_traces.npz")
    regimes = collections.defaultdict(dict)
    for k in tz.files:
        rg, sid = k.split("|")
        regimes[rg][sid] = tz[k].astype(np.int8)
    span = {v: int(np.ceil(max(meta[q]["qt"] for q in qs))) + 1 for v, qs in byv.items()}

    def align(rg):
        """(video, offset) -> (session id, start second) or None when no session is long enough."""
        pool = sorted(regimes[rg])
        a = {}
        for o in range(NOFF):
            rng = np.random.default_rng([SEED, o])
            for v in vids:
                elig = [s for s in pool if len(regimes[rg][s]) >= span[v]]
                if not elig:
                    a[(v, o)] = None
                    rng.random()
                    continue
                s = elig[int(rng.integers(len(elig)))]
                st = int(rng.integers(len(regimes[rg][s]) - span[v] + 1))
                a[(v, o)] = (s, st)
        return a

    cloud_cfgs = [c for c in CONFIGS if c[2] == "cloud"]
    dev_cfgs = [c for c in CONFIGS if c[2] == "device"]
    cloud_names = [c[0] for c in cloud_cfgs]
    names = [c[0] for c in CONFIGS]
    reps_used = sorted({c[3] for c in cloud_cfgs})

    results = dict(
        label="StudyE6b-mobility STAGE A: OFFLINE REPLAY OF COMMITTED RESULTS. CPU only on flash; "
              "no GPU, no model server, no inference.",
        at=datetime.now().isoformat(), seed=SEED, n_questions=N, n_videos=len(vids),
        n_offsets=NOFF, primary_format=PRIMARY_FMT, pending_configurations=PENDING,
        e6_rule=dict(policy="evidence-only, F1, logistic regression, 5-fold cross-fit by video, "
                            "seed 0, unconstrained budget (StudyE6 setting (a)'s best realised policy, 0.4036)",
                     best_static_cell_per_fold=e6_static,
                     cells_chosen=dict(collections.Counter(e6_cell.tolist()))),
        latency_status={n: dict(collections.Counter(status[n].tolist())) for n in names},
        stream_rate_bytes_per_s={f"{r}/{f}": STREAM_RATE[(r, f)] for r in reps_used for f in ("png", "raw")},
        stream_uplink_MB_per_hour={f"{r}/{f}": STREAM_RATE[(r, f)] * 3600 / 1e6
                                   for r in reps_used for f in ("png", "raw")},
        ondemand_bytes_per_question={f"{r}/{f}": dict(
            median=float(np.median(ondemand[(r, f)])), mean=float(np.mean(ondemand[(r, f)])),
            max=float(np.max(ondemand[(r, f)]))) for r in reps_used for f in ("png", "raw")},
        device_fixed_latency_s=dev_fixed,
        cells=dict(), checks=dict(), trace_example=None)

    # accuracy of each configuration when always delivered (sanity / check 1)
    results["accuracy_if_always_delivered"] = {
        n: float(corr[n][avail[n]].mean()) for n in names}
    results["n_available"] = {n: int(avail[n].sum()) for n in names}

    # ---------------------------------------------------------- the replay
    _only = os.environ.get("E6B_REGIMES")
    alignments = {rg: align(rg) for rg in sorted(regimes)
                  if (not _only or rg in _only.split(","))}
    results["alignment_coverage"] = {
        rg: dict(pairs=len(a), unmappable=sum(1 for v in a.values() if v is None),
                 videos_never_mappable=sum(1 for v in vids if all(a[(v, o)] is None for o in range(NOFF))))
        for rg, a in alignments.items()}

    qidx_by_v = {v: np.array([qi[q] for q in sorted(qs, key=lambda q: (meta[q]["qt"], q))]) for v, qs in byv.items()}
    qt_by_v = {v: np.array([meta[Q[i]]["qt"] for i in qidx_by_v[v]]) for v in byv}

    def replay(rg, net, mode, fmt, extrap=False):
        """Returns lat[(name)] of shape (N, NOFF) (np.inf = not delivered) and diagnostics."""
        up_mbps, rtt = NETS[net]
        R = up_mbps * 1e6 / 8.0
        lat = {n: np.full((N, NOFF), np.inf) for n in cloud_names}
        reach = np.zeros((N, NOFF), dtype=np.int8)
        valid = np.zeros((N, NOFF), dtype=bool)
        up_mb = collections.defaultdict(list)
        pend_s = collections.defaultdict(list); drain_st = collections.defaultdict(list)
        a = alignments[rg]
        comp_use = comp_x if extrap else comp
        for v in vids:
            qs, qts = qidx_by_v[v], qt_by_v[v]
            for o in range(NOFF):
                al = a[(v, o)]
                if al is None:
                    continue
                sid, st = al
                conn = regimes[rg][sid][st:st + span[v]]
                C = prefix_connected(conn)
                tsec = qts.astype(int)
                ok = conn[tsec] == 1
                valid[qs, o] = True
                reach[qs, o] = ok.astype(np.int8)
                for rep in reps_used:
                    if mode == "STREAM":
                        qb = queue_bytes(conn, STREAM_RATE[(rep, fmt)], R)
                        pend = qb[tsec] + NEWEST_FRAME[(rep, fmt)]
                        up_mb[rep].append(STREAM_RATE[(rep, fmt)] * len(conn) / 1e6)
                    else:
                        pend = ondemand[(rep, fmt)][qs]
                        up_mb[rep].append(float(pend.sum()) / 1e6)
                    dr = np.full(len(qs), np.inf)
                    for j in range(len(qs)):
                        if not ok[j]:
                            continue
                        d = drain_s(C, int(tsec[j]), float(pend[j]) / R)
                        dr[j] = np.inf if d is None else d
                    pend_s[rep].append(np.asarray(pend, dtype=float))
                    drain_st[rep].append(dr[ok])
                    for nm, _m, _l, r2, _c, _k, _ck, _rt in cloud_cfgs:
                        if r2 != rep:
                            continue
                        cc = comp_use[nm][qs]
                        tot = dr + rtt + cc
                        tot = np.where(np.isnan(cc) | ~avail[nm][qs], np.inf, tot)
                        lat[nm][qs, o] = tot
        sess_s = sum(span[v] for v in vids for o in range(NOFF) if a[(v, o)] is not None)
        mb_hr = {rep: (float(np.sum(up_mb[rep])) / (sess_s / 3600.0)) if sess_s else 0.0 for rep in reps_used}
        diag = {}
        for rep in reps_used:
            pv = np.concatenate(pend_s[rep]) if pend_s[rep] else np.zeros(1)
            dv = np.concatenate(drain_st[rep]) if drain_st[rep] else np.zeros(1)
            fin = dv[np.isfinite(dv)]
            diag[rep] = dict(
                pending_B_p50=float(np.median(pv)), pending_B_p95=float(np.percentile(pv, 95)),
                pending_B_max=float(pv.max()),
                pending_above_one_frame_fraction=float((pv > NEWEST_FRAME[(rep, fmt)] * 1.001).mean()),
                upload_s_p50=float(np.median(fin)) if len(fin) else None,
                upload_s_p95=float(np.percentile(fin, 95)) if len(fin) else None,
                upload_s_max=float(fin.max()) if len(fin) else None,
                never_uploaded_fraction=float((~np.isfinite(dv)).mean()) if len(dv) else None)
        return lat, reach, valid, mb_hr, diag

    dev_lat = {}
    for nm, _m, _l, _r, _c, _k, ck, _rt in dev_cfgs:
        c = comp[nm].copy()
        c[np.isnan(c) | ~avail[nm]] = np.inf
        dev_lat[nm] = c

    # bootstrap resamples over videos (clusters) and offsets
    rng = np.random.default_rng(SEED)
    v_index = {v: np.array([qi[q] for q in byv[v]]) for v in vids}
    boots = []
    for _ in range(NB):
        vs = rng.choice(len(vids), len(vids), replace=True)
        offs = rng.integers(0, NOFF, len(vids))
        qsel = np.concatenate([v_index[vids[k]] for k in vs])
        osel = np.concatenate([np.full(len(v_index[vids[k]]), offs[j]) for j, k in enumerate(vs)])
        boots.append((qsel, osel))

    def mean_ci(mat, valid):
        pts = [float(np.mean(mat[qs, os][valid[qs, os]])) if valid[qs, os].any() else np.nan
               for qs, os in boots]
        pts = np.array([p for p in pts if not np.isnan(p)])
        return [float(np.percentile(pts, 2.5)), float(np.percentile(pts, 97.5))]

    def paired_ci(a, b, valid):
        pts = [float(np.mean(a[qs, os][valid[qs, os]] - b[qs, os][valid[qs, os]]))
               for qs, os in boots if valid[qs, os].any()]
        return [float(np.percentile(pts, 2.5)), float(np.percentile(pts, 97.5))]

    off_fold = np.arange(NOFF) % NFOLD   # cross-fitting over trace offsets

    only = os.environ.get("E6B_REGIMES")
    todo = sorted(regimes) if not only else [r for r in sorted(regimes) if r in only.split(",")]
    for rg in todo:
        for net in NETS:
            for mode in MODES:
                lat, reach, valid, mb_hr, diag = replay(rg, net, mode, PRIMARY_FMT)
                for dl in DEADLINES:
                    U = {}
                    for n in cloud_names:
                        U[n] = ((lat[n] <= dl) & (corr[n][:, None] > 0)).astype(float)
                    for n in dev_lat:
                        U[n] = np.tile(((dev_lat[n] <= dl) & (corr[n] > 0)).astype(float)[:, None], NOFF)
                    stack = np.stack([U[n] for n in names])
                    oracle = stack.max(axis=0)
                    # best static, cross-fitted over offsets
                    static = np.zeros((N, NOFF))
                    static_pick = {}
                    for f in range(NFOLD):
                        tr = np.where(off_fold != f)[0]; te = np.where(off_fold == f)[0]
                        sc = [(float(U[n][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0, n)
                              for n in names]
                        best = max(sc, key=lambda x: (x[0], x[1]))[1]
                        static_pick[int(f)] = best
                        static[:, te] = U[best][:, te]
                        # best device configuration without pre-warming, same training folds
                    dev_pick = {}
                    p1 = np.zeros((N, NOFF)); p1_dev_used = np.zeros((N, NOFF))
                    u_cloud = np.zeros((N, NOFF))
                    for nm in cloud_names:
                        m = p1_cfg == nm
                        u_cloud[m] = U[nm][m]
                    for f in range(NFOLD):
                        tr = np.where(off_fold != f)[0]; te = np.where(off_fold == f)[0]
                        dsc = [(float(U[n][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0, n)
                               for n in dev_lat]
                        bd = max(dsc, key=lambda x: (x[0], x[1]))[1]
                        dev_pick[int(f)] = bd
                        r = reach[:, te] == 1
                        p1[:, te] = np.where(r, u_cloud[:, te], U[bd][:, te])
                        p1_dev_used[:, te] = (~r).astype(float)
                    if mode != "STREAM":
                        p1[:] = np.nan; p1_dev_used[:] = np.nan
                    cell = dict(
                        regime=rg, uplink=net, mode=mode, deadline_s=dl, format=PRIMARY_FMT,
                        n_pairs=int(valid.sum()),
                        reachable_fraction=float(reach[valid].mean()),
                        oracle=float(oracle[valid].mean()), oracle_ci=mean_ci(oracle, valid),
                        best_static=float(static[valid].mean()), best_static_ci=mean_ci(static, valid),
                        best_static_pick=static_pick,
                        P1=(None if mode != "STREAM" else float(p1[valid].mean())),
                        P1_ci=(None if mode != "STREAM" else mean_ci(p1, valid)),
                        P1_device_fallback_fraction=(None if mode != "STREAM" else float(p1_dev_used[valid].mean())),
                        P1_cloud_only_utility=(None if mode != "STREAM" else float(u_cloud[valid].mean())),
                        P1_device_config=dev_pick,
                        P1_minus_static=(None if mode != "STREAM" else float((p1 - static)[valid].mean())),
                        P1_minus_static_ci=(None if mode != "STREAM" else paired_ci(p1, static, valid)),
                        oracle_minus_P1=(None if mode != "STREAM" else float((oracle - p1)[valid].mean())),
                        oracle_minus_P1_ci=(None if mode != "STREAM" else paired_ci(oracle, p1, valid)),
                        per_config={n: float(U[n][valid].mean()) for n in names},
                        uplink_MB_per_hour={r: mb_hr[r] for r in reps_used},
                        upload_diagnostics=diag,
                        utility_split_by_reachability=dict(
                            connected=dict(
                                n=int((valid & (reach == 1)).sum()),
                                P1=(float(p1[valid & (reach == 1)].mean()) if mode == "STREAM" and (valid & (reach == 1)).any() else None),
                                static=float(static[valid & (reach == 1)].mean()) if (valid & (reach == 1)).any() else None,
                                oracle=float(oracle[valid & (reach == 1)].mean()) if (valid & (reach == 1)).any() else None),
                            outage=dict(
                                n=int((valid & (reach == 0)).sum()),
                                P1=(float(p1[valid & (reach == 0)].mean()) if mode == "STREAM" and (valid & (reach == 0)).any() else None),
                                static=float(static[valid & (reach == 0)].mean()) if (valid & (reach == 0)).any() else None,
                                oracle=float(oracle[valid & (reach == 0)].mean()) if (valid & (reach == 0)).any() else None)),
                    )
                    results["cells"][f"{rg}|{net}|{mode}|{dl}s"] = cell
        print("done regime", rg, flush=True)

    # ---------------------------------------------------------- negative control (a)
    if True:
        nc = {}
        for net in NETS:
            for dl in DEADLINES:
                k = f"synthetic_0pct|{net}|STREAM|{dl}s"
                c = results["cells"].get(k)
                if c is None:
                    continue
                nc[k] = dict(reachable_fraction=c["reachable_fraction"],
                             P1_device_fallback_fraction=c["P1_device_fallback_fraction"],
                             P1=c["P1"], P1_cloud_only_utility=c["P1_cloud_only_utility"],
                             abs_diff=abs(c["P1"] - c["P1_cloud_only_utility"]))
        results["negative_control_a"] = dict(
            description="Outage fraction 0 (synthetic_0pct). P1 must never fall back to the device, "
                        "so its device-fallback fraction must be 0 and P1 must equal the always-cloud "
                        "decomposed policy.", cells=nc)

    # ---------------------------------------------------------- UNKNOWN sensitivity
    sens = {}
    for rg in todo:
        for dl in (2, 5):
            lat, reach, valid, _mb, _dg = replay(rg, "13.6Mbps_44ms", "STREAM", PRIMARY_FMT, extrap=True)
            U = {n: ((lat[n] <= dl) & (corr[n][:, None] > 0)).astype(float) for n in cloud_names}
            for n in dev_lat:
                cx = comp_x[n].copy(); cx[np.isnan(cx) | ~avail[n]] = np.inf
                U[n] = np.tile(((cx <= dl) & (corr[n] > 0)).astype(float)[:, None], NOFF)
            st = np.stack([U[n] for n in names])
            base = results["cells"][f"{rg}|13.6Mbps_44ms|STREAM|{dl}s"]
            sens[f"{rg}|13.6Mbps_44ms|STREAM|{dl}s"] = dict(
                oracle_primary=base["oracle"], oracle_extrapolated=float(st.max(axis=0)[valid].mean()),
                per_config_primary=base["per_config"],
                per_config_extrapolated={n: float(U[n][valid].mean()) for n in names})
    results["unknown_sensitivity_linear_extrapolation"] = sens

    # ---------------------------------------------------------- instrumented trace
    if "outdoor_driving" in todo:
        rg, net, mode, fmt, dl = "outdoor_driving", "13.6Mbps_44ms", "STREAM", PRIMARY_FMT, 5
        up_mbps, rtt = NETS[net]; R = up_mbps * 1e6 / 8.0
        pick = None
        for v in vids:
            for o in range(NOFF):
                al = alignments[rg][(v, o)]
                if al is None:
                    continue
                sid, stt = al
                conn = regimes[rg][sid][stt:stt + span[v]]
                ts = qt_by_v[v].astype(int)
                if (conn[ts] == 0).any():
                    pick = (v, o, sid, stt); break
            if pick:
                break
        if pick:
            v, o, sid, stt = pick
            conn = regimes[rg][sid][stt:stt + span[v]]
            C = prefix_connected(conn)
            rows = []
            for j, i in enumerate(qidx_by_v[v]):
                q = Q[i]; tsec = int(meta[q]["qt"])
                r = dict(question_id=q, question_time_s=meta[q]["qt"], trace_second=stt + tsec,
                         connected_at_question=int(conn[tsec]),
                         outage_seconds_in_last_60s=int((conn[max(0, tsec - 60):tsec] == 0).sum()),
                         configs={})
                for nm, _m, loc, rep, cache, key, _ck, _rt in CONFIGS:
                    e = dict(correct=(None if not avail[nm][i] else bool(corr[nm][i] > 0)),
                             compute_s=(None if np.isnan(comp[nm][i]) else round(float(comp[nm][i]), 4)),
                             status=status[nm][i])
                    if loc == "cloud":
                        qb = queue_bytes(conn, STREAM_RATE[(rep, fmt)], R)
                        pend = float(qb[tsec] + NEWEST_FRAME[(rep, fmt)])
                        e.update(queue_backlog_B=round(float(qb[tsec]), 1),
                                 newest_frame_B=round(NEWEST_FRAME[(rep, fmt)], 1),
                                 pending_B=round(pend, 1), rtt_s=rtt)
                        if conn[tsec] == 0:
                            e.update(upload_s=None, total_s=None, delivered=False,
                                     note="cloud unreachable at question time")
                        else:
                            d = drain_s(C, tsec, pend / R)
                            tot = None if (d is None or np.isnan(comp[nm][i]) or not avail[nm][i]) else d + rtt + float(comp[nm][i])
                            e.update(upload_s=(None if d is None else round(d, 4)),
                                     total_s=(None if tot is None else round(tot, 4)),
                                     delivered=bool(tot is not None and tot <= dl))
                    else:
                        tot = None if (np.isnan(comp[nm][i]) or not avail[nm][i]) else float(comp[nm][i])
                        e.update(upload_s=0.0, total_s=(None if tot is None else round(tot, 4)),
                                 delivered=bool(tot is not None and tot <= dl))
                    e["utility"] = int(bool(e.get("delivered")) and e["correct"] is True)
                    r["configs"][nm] = e
                rows.append(r)
            results["trace_example"] = dict(
                regime=rg, uplink=net, mode=mode, format=fmt, deadline_s=dl, video_id=v, offset=o,
                trace_session=sid, trace_start_second=stt, video_span_s=span[v],
                outage_seconds_in_window=int((conn == 0).sum()),
                stream_rate_bytes_per_s={rep: STREAM_RATE[(rep, fmt)] for rep in reps_used},
                uplink_MB_per_hour={rep: STREAM_RATE[(rep, fmt)] * 3600 / 1e6 for rep in reps_used},
                questions=rows)

    # ---------------------------------------------------------- E4 table 4.1, corrected costs
    E4CFG = [("dev-4B-RECENT", "device", "RECENT", "H1", "device_cold"),
             ("dev-4B-RICH", "device", "RICH", "H2", "device_cold"),
             ("cl-4B-RECENT", "cloud", "RECENT", "H1", "4BI/video/COLD"),
             ("cl-4B-RICH", "cloud", "RICH", "H2", "4BI/video/COLD"),
             ("cl-4B-U", "cloud", "U", "U4", "4BI/video/COLD"),
             ("cl-32B-RECENT", "cloud", "RECENT", "K3", "32BI/video/COLD"),
             ("cl-32B-RICH", "cloud", "RICH", "K1", "32BI/video/COLD"),
             ("cl-32B-U", "cloud", "U", "U32", "32BI/video/COLD"),
             ("cl-32B-D2", "cloud", "D2", "D2", "32BI/images/COLD")]
    e4comp, e4corr, e4avail = {}, {}, {}
    for nm, loc, rep, key, ck in E4CFG:
        c = np.full(N, np.nan); y = np.zeros(N); av = np.zeros(N, dtype=bool)
        for q in Q:
            i = qi[q]
            if q not in ans[key]:
                continue
            y[i] = 1.0 if ans[key][q] else 0.0; av[i] = True
            cu = dev_curve if ck == "device_cold" else curves[ck]
            val, _s = cu.at(tok[key].get(q))
            c[i] = np.nan if val is None else val
        e4comp[nm], e4corr[nm], e4avail[nm] = c, y, av
    e4names = [c[0] for c in E4CFG]
    qtype = {q: (meta[q]["cat"], qbin(meta[q]["qt"])) for q in Q}
    kf2 = {}
    for fi, (_, te) in enumerate(KFold(2, shuffle=True, random_state=SEED).split(vids)):
        for i in te:
            kf2[vids[i]] = fi
    f2 = np.array([kf2[meta[q]["video"]] for q in Q])
    rng2 = np.random.default_rng(SEED)
    vboot = [np.concatenate([v_index[vids[k]] for k in rng2.choice(len(vids), len(vids), replace=True)])
             for _ in range(NB)]
    e4tab = {}
    for mode in MODES:
        for net in NETS:
            up_mbps, rtt = NETS[net]; R = up_mbps * 1e6 / 8.0
            for fmt in ("png", "raw"):
                for dl in DEADLINES:
                    U = {}
                    for nm, loc, rep, key, ck in E4CFG:
                        if loc == "device":
                            tot = e4comp[nm]
                        else:
                            b = NEWEST_FRAME[(rep, fmt)] if mode == "STREAM" else ondemand[(rep, fmt)]
                            tot = e4comp[nm] + (b / R) + rtt
                        U[nm] = np.where(np.isnan(tot) | ~e4avail[nm], 0.0,
                                         ((tot <= dl) & (e4corr[nm] > 0)).astype(float))
                    orc = np.max(np.stack([U[n] for n in e4names]), axis=0)
                    stc = np.zeros(N); tyc = np.zeros(N)
                    picks = {}
                    for fi in (0, 1):
                        tr = np.where(f2 != fi)[0]; te = np.where(f2 == fi)[0]
                        b = max(e4names, key=lambda n: (U[n][tr].mean(), n))
                        picks[fi] = b; stc[te] = U[b][te]
                        pool = collections.defaultdict(list)
                        for i in tr:
                            pool[qtype[Q[i]]].append(i)
                        for i in te:
                            ix = pool.get(qtype[Q[i]]) or list(tr)
                            bt = max(e4names, key=lambda n: (np.mean(U[n][ix]), np.mean(U[n][tr]), n))
                            tyc[i] = U[bt][i]
                    hs = [float(np.mean(orc[s] - tyc[s])) for s in vboot]
                    e4tab[f"{mode}/{net}/{fmt}/{dl}s"] = dict(
                        oracle=float(orc.mean()), static_crossfit=float(stc.mean()),
                        pertype_crossfit=float(tyc.mean()), best_static_pick=picks,
                        headroom_over_pertype=float(np.mean(orc - tyc)),
                        headroom_over_pertype_ci=[float(np.percentile(hs, 2.5)), float(np.percentile(hs, 97.5))],
                        headroom_over_static=float(np.mean(orc - stc)),
                        per_config={n: float(U[n].mean()) for n in e4names})
    results["e4_table41_recomputed"] = dict(
        note="StudyE4 table 4.1 recomputed with StudyF3's per-format, per-cache-state latency curves "
             "and ONE deployment mode applied to all cloud arms. RTTs are StudyE6b's pre-registered "
             "values (60/44/22 ms); StudyE4 used 142 ms at 5 Mbit/s. No network outages, as in StudyE4.",
        cells=e4tab)

    results["_provenance"] = stamp(script="study_e6b_mobility.py", model=None, device="cpu",
                                   n=N * NOFF, args=None)
    (OUT / "e6b_results.json").write_text(json.dumps(results, indent=1))
    print("cells:", len(results["cells"]))


if __name__ == "__main__":
    main()
