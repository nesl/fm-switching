#!/usr/bin/env python3
"""StudyE6b-mobility STAGE B — keep-warm policies over network traces.

CPU ONLY on the flash host: no GPU, no model server, no inference. Every accuracy and every
latency is read from a committed result file of an earlier study (StudyE7-d2-4b, StudyE8-device-
warm, StudyF3, StudyF4, StudyR1, StudyRH4, StudyClean, StudyD11, StudyD4-orin).

Stage B adds the 4B cloud D2 arms and the device D2 arms (warm and cold), policies P2 / P3 /
P3-noncausal / oracle keep-warm, keep-warm costs, both negative controls and the pre-registered
decision rule. Stage A's P1, best-static and oracle are recomputed here from the same code path so
every Stage B contrast is paired against a Stage A number produced the same way.
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

sys.path.insert(0, str(ROOT / "experiments/orchestration"))
import study_e6b_mobility as A  # noqa: E402

OUT = ROOT / "results/orchestration/study_e6b"
SEED, NB, NOFF, NFOLD = A.SEED, A.NB, A.NOFF, A.NFOLD
NETS, DEADLINES, PRIMARY_FMT = A.NETS, A.DEADLINES, A.PRIMARY_FMT
D2_TOKENS_PER_S = A.D2_TOKENS_PER_S
D2_FRAME_PERIOD_S = 2.0
D2_TOK_PER_FRAME = 90.0            # StudyE8: one 352x256 D2 frame, evaluated 95 incl. template tail
WARM_DELTA_W = 5.2087              # StudyE8 Part C, board power above loaded idle while keeping warm
CROSSOVER_TOK = 15069              # StudyE8 Part C: append latency crosses the 2 s cadence here
P3_THETAS = (0.05, 0.10, 0.20, 0.40)       # absolute grid, reported for transparency
P3_QLEVELS = (0.0, 0.25, 0.50, 0.75, 0.90)  # primary grid: quantiles of the predictor's own risk
P3_HORIZONS = (30, 60, 120)
STALE_TOL_S = 2.0                  # primary: device-warm may answer only if its ingest lag <= one frame


def jl(p):
    return A.jl(p)


def e7_answers():
    """StudyE7 Job A: 4B on RH4's D2 history. Letters are the H100 4B's; StudyE8 Part D measured
    device-vs-H100 agreement at 68/68 warm and 27/27 cold on byte-identical inputs."""
    rows = [r for r in jl(ROOT / "results/sember/study_e7/e7_requests_h100nvl.jsonl")
            if not r.get("error") and r.get("grey") in (False, "False")
            and r.get("infeasible") in (False, "False")]
    ans = {r["question_id"]: bool(r["correct"]) for r in rows}
    tok = {r["question_id"]: int(r["prompt_tokens"]) for r in rows}
    assert len(ans) == 839, len(ans)
    return ans, tok


def e8_curves():
    """Device curves from StudyE8's RAW rows (not the binned report tables)."""
    a = [r for r in jl(ROOT / "results/device/study_e8/partA_warm.jsonl") if r.get("clock_ok")]
    app = [(float(r["prompt_tokens"]), float(r["total_latency_s"]))
           for r in a if r["kind"] == "append" and r.get("total_latency_s")]
    qn = [(float(r["prompt_tokens"]), float(r["total_latency_s"]))
          for r in a if r["kind"] == "question" and r.get("total_latency_s")]
    b = [(float(r["prompt_tokens"]), float(r["total_latency_s"]))
         for r in jl(ROOT / "results/device/study_e8/partB_cold.jsonl") if r.get("total_latency_s")]
    assert len(app) > 4000 and len(qn) > 60 and len(b) == 30, (len(app), len(qn), len(b))
    return (A.BinCurve(app, binw=1000), A.BinCurve(qn, binw=3000), A.BinCurve(b, binw=3000))


class DeviceWarmSim:
    """Exact replay of StudyE8's measured keep-warm dynamics on a D2 frame stream.

    A device that turns warm at session second s0 must first reconstruct the history it already
    holds (StudyE8 Part B cold curve at 45 tok/s * s0), during which new frames queue; afterwards
    it appends frames one at a time at StudyE8 Part A's measured append cost, which grows with the
    history, so past ~15 k tokens it ingests more slowly than the 2 s cadence and falls behind.
    Append cost depends only on the number of frames already in the history, so the cumulative
    ingest schedule is a prefix sum and every (s0, question time) query is O(log n)."""

    def __init__(self, append_curve, cold_curve, max_frames):
        self.K = int(max_frames) + 2
        k = np.arange(self.K)
        tok = k * D2_TOK_PER_FRAME
        self.t_app = np.array([append_curve.at(float(max(x, append_curve.lo)), True)[0] for x in tok])
        self.A = np.concatenate([[0.0], np.cumsum(self.t_app)])     # A[j] = time to append j frames
        self.cold = cold_curve

    def cold_prefill_s(self, s0):
        tokens = max(D2_TOKENS_PER_S * s0, self.cold.lo)
        return float(self.cold.at(tokens, True)[0])

    def ingest(self, s0, qts):
        """Device turns warm at second s0. Returns, per question time in `qts`:
        ready (bool), lag_s, hist_tok held, and the wall second the state is current to."""
        k0 = int(s0 // D2_FRAME_PERIOD_S)                 # frames already in the session at s0
        T0 = s0 + self.cold_prefill_s(s0)                 # warm state exists from here
        nf = int(max(qts) // D2_FRAME_PERIOD_S) + 1
        j = np.arange(1, max(nf - k0, 0) + 1)             # appends after the warm-up
        if len(j) == 0:
            fin = np.array([])
        else:
            arr = s0 + (k0 + j) * D2_FRAME_PERIOD_S       # arrival of each later frame
            start_floor = np.maximum(arr, T0)
            # T_j = max_{i<=j} (start_floor_i + A[k0+j+1] - A[k0+i])  (FIFO, no preemption)
            base = self.A[k0 + 1: k0 + len(j) + 1]
            run = np.maximum.accumulate(start_floor - base)
            fin = run + self.A[k0 + 2: k0 + len(j) + 2]
        out = []
        for qt in qts:
            if qt < T0:
                out.append((False, None, None, None))
                continue
            done = int(np.searchsorted(fin, qt, side="right")) if len(fin) else 0
            cur_frame = k0 + done
            cur_time = min(cur_frame * D2_FRAME_PERIOD_S, qt)
            out.append((True, float(qt - cur_time), float(cur_frame * D2_TOK_PER_FRAME), float(cur_time)))
        return out


def risk_features(conn, H):
    """Causal predictor features at every second: no-cell fraction over the last 30/60/120 s and
    seconds since the last outage. Uses past trace seconds only."""
    n = len(conn)
    out = np.zeros((n, 4))
    c = np.concatenate([[0.0], np.cumsum(1.0 - conn)])
    for j, w in enumerate((30, 60, 120)):
        lo = np.maximum(np.arange(n) - w, 0)
        out[:, j] = (c[np.arange(n)] - c[lo]) / np.maximum(np.arange(n) - lo, 1)
    since = np.zeros(n); last = -1
    for t in range(n):
        if conn[t] == 0:
            last = t
        since[t] = (t - last) if last >= 0 else n
    out[:, 3] = np.minimum(since, 600) / 600.0
    return out


def future_outage(conn, H):
    """Label: is there any outage second in (t, t+H]?  Also the non-causal P3 oracle signal."""
    n = len(conn)
    c = np.concatenate([[0.0], np.cumsum(1.0 - conn)])
    hi = np.minimum(np.arange(n) + H, n)
    return ((c[hi] - c[np.minimum(np.arange(n) + 1, n)]) > 0).astype(float)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A.FB = json.loads((A.E4D / "e4_frame_bytes.json").read_text())["sizes"]
    f3 = json.loads((ROOT / "results/cost/study_f3/f3_results.json").read_text())["curves"]
    e7c = json.loads((ROOT / "results/sember/study_e7/e7_results.json").read_text())["job_b"]["curves"]
    man, ans, tok = A.load()
    ans["E7D2"], tok["E7D2"] = e7_answers()
    Q = sorted(man)
    N = len(Q)
    meta = {q: dict(video=man[q]["RECENT"]["video_id"], qt=float(man[q]["RECENT"]["question_time"]),
                    cat=man[q]["RECENT"]["question_category"]) for q in Q}
    qi = {q: i for i, q in enumerate(Q)}

    CONFIGS = list(A.CONFIGS) + [
        ("cl-4B-D2-cold",  "4B", "cloud",  "D2", "cold", "E7D2", "4B/images/COLD",  "D2"),
        ("cl-4B-D2-warm",  "4B", "cloud",  "D2", "warm", "E7D2", "4B/images/WARM",  "D2"),
        ("dev-4B-D2-cold", "4B", "device", "D2", "cold", "E7D2", "device_d2_cold",  None),
        ("dev-4B-D2-warm", "4B", "device", "D2", "warm", "E7D2", "device_d2_warm",  None),
    ]
    names = [c[0] for c in CONFIGS]
    cloud_cfgs = [c for c in CONFIGS if c[2] == "cloud"]
    cloud_names = [c[0] for c in cloud_cfgs]
    # device arms usable with no pre-warming (Stage A's fallback set)
    dev_nowarm = [c[0] for c in CONFIGS if c[2] == "device" and c[0] != "dev-4B-D2-warm"]
    reps_used = sorted({c[3] for c in cloud_cfgs})

    curves = {"4BI/video/COLD": A.PolyCurve(f3["4BI/video/COLD"]),
              "32BI/video/COLD": A.PolyCurve(f3["32BI/video/COLD"]),
              "32BI/images/COLD": A.PolyCurve(f3["32BI/images/COLD"]),
              "4B/images/COLD": A.PolyCurve(e7c["4B/images/COLD"])}
    curves["32BI/images/WARM"] = A.PolyCurve({"total": f3["32BI/images/WARM"]["ttft_vs_uncached_tokens"]}, "total")
    curves["4B/images/WARM"] = A.PolyCurve({"total": e7c["4B/images/WARM"]["ttft_vs_uncached_tokens"]}, "total")
    dev_fixed, dev_curve = A.device_fixed_latency(), A.device_cold_curve()
    app_curve, warmq_curve, coldq_curve = e8_curves()

    byv = collections.defaultdict(list)
    for q in Q:
        byv[meta[q]["video"]].append(q)
    vids = sorted(byv)
    prev_qt = {}
    for v, qs in byv.items():
        qs.sort(key=lambda q: (meta[q]["qt"], q))
        for i, q in enumerate(qs):
            e = [meta[p]["qt"] for p in qs[:i] if meta[p]["qt"] < meta[q]["qt"]]
            prev_qt[q] = max(e) if e else None

    STREAM_RATE, NEWEST_FRAME, ondemand = {}, {}, {}
    for fmt in ("png", "raw"):
        STREAM_RATE[("RECENT", fmt)] = A.fbytes((384, 512), fmt)
        STREAM_RATE[("RICH", fmt)] = A.fbytes((256, 352), fmt)
        STREAM_RATE[("U", fmt)] = A.fbytes((384, 512), fmt) + A.fbytes((256, 352), fmt)
        STREAM_RATE[("D2", fmt)] = A.fbytes((256, 352), fmt) * 0.5
        for rep in ("RECENT", "RICH", "U", "D2"):
            NEWEST_FRAME[(rep, fmt)] = A.fbytes((384, 512) if rep in ("RECENT", "U") else (256, 352), fmt)

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
        return [(float(t), (256, 352)) for t in range(0, int(meta[q]["qt"]) + 1, 2)]

    for rep in ("RECENT", "RICH", "U", "D2"):
        for fmt in ("png", "raw"):
            ondemand[(rep, fmt)] = np.array([sum(A.fbytes(hw, fmt) for _, hw in frames(rep, q)) for q in Q])

    # ---------------------------------------------------------------- per-config compute + letters
    comp, status, corr, avail = {}, {}, {}, {}
    for name, model, loc, rep, cache, key, ck, _rate in CONFIGS:
        c = np.full(N, np.nan); st = np.empty(N, dtype=object)
        y = np.zeros(N); av = np.zeros(N, dtype=bool)
        for q in Q:
            i = qi[q]
            if q not in ans[key]:
                st[i] = "INFEASIBLE"
                continue
            y[i] = 1.0 if ans[key][q] else 0.0
            av[i] = True
            if ck == "device_fixed":
                c[i] = dev_fixed[int(rep[-1])]; st[i] = "measured"
            elif ck == "device_cold":
                v, s = dev_curve.at(tok[key].get(q)); c[i] = np.nan if v is None else v; st[i] = s
            elif ck == "device_d2_cold":
                v, s = coldq_curve.at(tok[key].get(q)); c[i] = np.nan if v is None else v; st[i] = s
            elif ck == "device_d2_warm":
                c[i] = np.nan; st[i] = "state_dependent"   # filled per (video, offset) by the sim
            elif cache == "warm":
                un = (D2_TOKENS_PER_S * (meta[q]["qt"] - prev_qt[q])) if prev_qt[q] is not None else None
                if un is None:
                    st[i] = "COLD_FIRST_QUESTION"; av[i] = False
                    continue
                v, s = curves[ck].at(un)
                c[i] = np.nan if v is None else v + A.D2_WARM_TOTAL_MINUS_TTFT; st[i] = s
            else:
                v, s = curves[ck].at(tok[key].get(q)); c[i] = np.nan if v is None else v; st[i] = s
        comp[name], status[name], corr[name], avail[name] = c, st, y, av

    # device-warm answer latency as a function of the history the device actually holds
    def warm_answer_s(hist_tok):
        return float(warmq_curve.at(max(hist_tok, warmq_curve.lo), True)[0])

    # ---------------------------------------------------------------- E6(a) rule (Stage A's P1)
    E6CELLS = ["H1", "H2", "K3", "K1"]
    E6MODEL = {"H1": "4B", "H2": "4B", "K3": "32B", "K1": "32B"}
    cats = sorted({meta[q]["cat"] for q in Q})

    def qbin(t):
        return "le120" if t <= 120 else ("120-480" if t <= 480 else "gt480")

    X = np.array([[1.0 * (meta[q]["cat"] == c) for c in cats]
                  + [1.0 * (qbin(meta[q]["qt"]) == b) for b in ["le120", "120-480", "gt480"]]
                  + [meta[q]["qt"], meta[q]["qt"] / 600.0] for q in Q])
    Yc = {c: np.array([1.0 if ans[c][q] else 0.0 for q in Q]) for c in E6CELLS}
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
    for fi in range(NFOLD):
        tr, te = np.where(fold != fi)[0], np.where(fold == fi)[0]
        bstat = max(E6CELLS, key=lambda c: (Yc[c][tr].mean(), c))
        keep = [c for c in E6CELLS if E6MODEL[c] == E6MODEL[bstat]]
        for i in te:
            e6_cell[i] = max(keep, key=lambda c: (P[c][i], c))
    CELL2CFG = {"H1": "cl-4B-RECENT", "H2": "cl-4B-RICH", "K3": "cl-32B-RECENT", "K1": "cl-32B-RICH"}
    p1_cfg = np.array([CELL2CFG[c] for c in e6_cell], dtype=object)

    # ---------------------------------------------------------------- traces and alignment
    tz = np.load(OUT / "e6b_traces.npz")
    regimes = collections.defaultdict(dict)
    for k in tz.files:
        rg, sid = k.split("|")
        regimes[rg][sid] = tz[k].astype(np.int8)
    span = {v: int(np.ceil(max(meta[q]["qt"] for q in qs))) + 1 for v, qs in byv.items()}

    def align(rg):
        pool = sorted(regimes[rg]); a = {}
        for o in range(NOFF):
            rng = np.random.default_rng([SEED, o])
            for v in vids:
                elig = [s for s in pool if len(regimes[rg][s]) >= span[v]]
                if not elig:
                    a[(v, o)] = None; rng.random(); continue
                s = elig[int(rng.integers(len(elig)))]
                st = int(rng.integers(len(regimes[rg][s]) - span[v] + 1))
                a[(v, o)] = (s, st)
        return a

    qidx_by_v = {v: np.array([qi[q] for q in sorted(qs, key=lambda q: (meta[q]["qt"], q))]) for v, qs in byv.items()}
    qt_by_v = {v: np.array([meta[Q[i]]["qt"] for i in qidx_by_v[v]]) for v in byv}
    sim = DeviceWarmSim(app_curve, coldq_curve, max(span.values()) / D2_FRAME_PERIOD_S)

    # P2's device state is the same for every video and offset: warm from second 0.
    warm_from0 = {}
    for v in vids:
        warm_from0[v] = sim.ingest(0.0, list(qt_by_v[v]))

    _only = os.environ.get("E6B_REGIMES")
    todo = [r for r in sorted(regimes) if (not _only or r in _only.split(","))]
    alignments = {rg: align(rg) for rg in todo}

    results = dict(
        label="StudyE6b-mobility STAGE B: OFFLINE REPLAY OF COMMITTED RESULTS. CPU only on flash; "
              "no GPU, no model server, no inference. Adds the 4B cloud D2 arms, the device D2 arms, "
              "P2/P3/P3-noncausal/oracle keep-warm, keep-warm costs, both negative controls and the "
              "pre-registered decision rule.",
        at=datetime.now().isoformat(), seed=SEED, n_questions=N, n_videos=len(vids), n_offsets=NOFF,
        primary_format=PRIMARY_FMT, stale_tolerance_s=STALE_TOL_S,
        device_keepwarm_power_W=WARM_DELTA_W,
        new_configurations={
            "cl-4B-D2-cold": "StudyE7 Job A letters (839), StudyE7 Job B 4B/images/COLD total curve",
            "cl-4B-D2-warm": "StudyE7 Job A letters, StudyE7 Job B 4B/images/WARM ttft vs uncached "
                             "tokens (R^2 0.325 - FLAGGED, weakest curve in the study)",
            "dev-4B-D2-cold": "StudyE7 Job A letters (parity StudyE8 Part D cold 27/27), StudyE8 "
                              "Part B cold curve on the device",
            "dev-4B-D2-warm": "StudyE7 Job A letters (parity StudyE8 Part D warm 68/68), StudyE8 "
                              "Part A warm-question curve at the history the device actually holds"},
        latency_status={n: dict(collections.Counter(status[n].tolist())) for n in names},
        accuracy_if_always_delivered={n: float(corr[n][avail[n]].mean()) for n in names},
        n_available={n: int(avail[n].sum()) for n in names},
        device_curves=dict(
            append_total_s={str(int(x)): round(float(app_curve.at(max(x, app_curve.lo), True)[0]), 4)
                            for x in (500, 2000, 5000, 10000, 15000, 25000, 40000)},
            warm_question_total_s={str(int(x)): round(warm_answer_s(x), 4)
                                   for x in (1000, 5000, 10000, 15000, 25000, 45000)},
            cold_question_total_s={str(int(x)): round(float(coldq_curve.at(max(x, coldq_curve.lo), True)[0]), 4)
                                   for x in (1000, 5000, 10000, 15000, 25000, 45000)},
            cold_curve_token_range=[coldq_curve.lo, coldq_curve.hi],
            warm_curve_token_range=[warmq_curve.lo, warmq_curve.hi],
            append_curve_token_range=[app_curve.lo, app_curve.hi],
            two_second_crossover_tokens=CROSSOVER_TOK),
        cells=dict(), checks=dict())

    # ---------------------------------------------------------------- the replay
    def replay(rg, net, fmt):
        up_mbps, rtt = NETS[net]
        R = up_mbps * 1e6 / 8.0
        lat = {n: np.full((N, NOFF), np.inf) for n in cloud_names}
        reach = np.zeros((N, NOFF), dtype=np.int8)
        valid = np.zeros((N, NOFF), dtype=bool)
        dw_lat = np.full((N, NOFF), np.inf)       # device-warm (P2 state: warm from second 0)
        dw_ok = np.zeros((N, NOFF), dtype=bool)
        dw_lag = np.full((N, NOFF), np.nan)
        dw_hist = np.full((N, NOFF), np.nan)
        dw_any = np.zeros((N, NOFF), dtype=bool)        # OPTIMISTIC: warm, ignoring ingest lag
        dw_lat_opt = np.full((N, NOFF), np.inf)
        up_mb = collections.defaultdict(float)
        sess_s = 0
        a = alignments[rg]
        for v in vids:
            qs, qts = qidx_by_v[v], qt_by_v[v]
            w0 = warm_from0[v]
            for o in range(NOFF):
                al = a[(v, o)]
                if al is None:
                    continue
                sid, st = al
                conn = regimes[rg][sid][st:st + span[v]]
                C = A.prefix_connected(conn)
                tsec = qts.astype(int)
                ok = conn[tsec] == 1
                valid[qs, o] = True
                reach[qs, o] = ok.astype(np.int8)
                sess_s += span[v]
                for j, (ready, lag, ht, _cur) in enumerate(w0):
                    if not ready:
                        continue
                    dw_lag[qs[j], o] = lag; dw_hist[qs[j], o] = ht
                    if not avail["dev-4B-D2-warm"][qs[j]]:
                        continue
                    dw_any[qs[j], o] = True
                    dw_lat_opt[qs[j], o] = warm_answer_s(ht)
                    if lag <= STALE_TOL_S:
                        dw_ok[qs[j], o] = True
                        dw_lat[qs[j], o] = warm_answer_s(ht)
                for rep in reps_used:
                    qb = A.queue_bytes(conn, STREAM_RATE[(rep, fmt)], R)
                    pend = qb[tsec] + NEWEST_FRAME[(rep, fmt)]
                    up_mb[rep] += STREAM_RATE[(rep, fmt)] * len(conn) / 1e6
                    dr = np.full(len(qs), np.inf)
                    for j in range(len(qs)):
                        if ok[j]:
                            d = A.drain_s(C, int(tsec[j]), float(pend[j]) / R)
                            dr[j] = np.inf if d is None else d
                    for nm, _m, _l, r2, _c, _k, _ck, _rt in cloud_cfgs:
                        if r2 != rep:
                            continue
                        cc = comp[nm][qs]
                        tot = dr + rtt + cc
                        lat[nm][qs, o] = np.where(np.isnan(cc) | ~avail[nm][qs], np.inf, tot)
        mb_hr = {rep: up_mb[rep] / (sess_s / 3600.0) if sess_s else 0.0 for rep in reps_used}
        return (lat, reach, valid, dw_lat, dw_ok, dw_lag, dw_hist, mb_hr, sess_s,
                dw_any, dw_lat_opt)

    # P3 predictor: fitted per regime, cross-fit by trace session (5 folds, seed 0)
    def p3_signals(rg):
        sess = sorted(regimes[rg])
        sf = {}
        for fi, (_, te) in enumerate(KFold(NFOLD, shuffle=True, random_state=SEED).split(sess)):
            for i in te:
                sf[sess[i]] = fi
        out = {}
        for H in P3_HORIZONS:
            F = {s: risk_features(regimes[rg][s].astype(float), H) for s in sess}
            Y = {s: future_outage(regimes[rg][s].astype(float), H) for s in sess}
            pr = {}
            for fi in range(NFOLD):
                tr = [s for s in sess if sf[s] != fi]
                Xtr = np.concatenate([F[s] for s in tr]); Ytr = np.concatenate([Y[s] for s in tr])
                if Ytr.max() == Ytr.min():
                    for s in sess:
                        if sf[s] == fi:
                            pr[s] = np.full(len(F[s]), float(Ytr[0]))
                    continue
                sc = StandardScaler().fit(Xtr)
                m = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED).fit(sc.transform(Xtr), Ytr)
                for s in sess:
                    if sf[s] == fi:
                        pr[s] = m.predict_proba(sc.transform(F[s]))[:, 1]
            out[H] = dict(pred=pr, truth=Y, session_fold=sf)
        return out

    def warm_schedule(onoff):
        """From a per-second warm/cold decision, the (start, end) warm intervals."""
        d = np.diff(np.concatenate([[0], onoff.astype(np.int8), [0]]))
        return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))

    def device_state_from_schedule(intervals, qts):
        """Device-warm readiness at each question under an arbitrary warm schedule (P3).
        A warm interval starting at s0 pays StudyE8 Part B's cold prefill of the history held at
        s0 before it can answer; the warm state is dropped when the interval ends. Only the
        interval covering a question matters, so this is O(#questions), not O(#intervals)."""
        res = [(False, None, None)] * len(qts)
        warm_s = float(sum(s1 - s0 for s0, s1 in intervals))
        warmup_s = float(sum(min(sim.cold_prefill_s(float(s0)), s1 - s0) for s0, s1 in intervals))
        if not intervals:
            return res, warm_s, warmup_s
        starts = np.array([s0 for s0, _ in intervals], dtype=float)
        ends = np.array([s1 for _, s1 in intervals], dtype=float)
        for j, qt in enumerate(qts):
            k = int(np.searchsorted(starts, qt, side="right")) - 1
            if k < 0 or qt >= ends[k]:
                continue
            ready, lag, ht, _c = sim.ingest(float(starts[k]), [float(qt)])[0]
            if ready and lag is not None and lag <= STALE_TOL_S:
                res[j] = (True, lag, ht)
        return res, warm_s, warmup_s

    def theta_grid(sig, H, nc):
        """The absolute risk thresholds the quantile grid maps to. The predicted risk of 'an outage
        somewhere in the next H s' saturates near 1 on these traces (outages are frequent and
        short), so a fixed absolute grid would put every threshold below the predictor's support
        and make P3 identical to P2 by construction. The grid levels are fixed constants; only the
        level -> threshold calibration uses the pooled predictions, and WHICH level is used is
        cross-fitted by trace session."""
        allp = np.concatenate([(sig[H]["truth"][s] if nc else sig[H]["pred"][s]) for s in sig[H]["pred"]])
        return {q: float(np.quantile(allp, q)) for q in P3_QLEVELS}

    def p3_states(rg, sig, a):
        """Per regime, the device-warm state under every (H, theta) schedule, for the causal and
        the non-causal predictor. Independent of uplink and deadline, so computed once."""
        out = {}
        sfold = np.full((N, NOFF), -1, dtype=np.int8)
        for H in P3_HORIZONS:
            for nc in (False, True):
                tg = theta_grid(sig, H, nc)
                out[("thetas", H, nc)] = tg
                for q in P3_QLEVELS:
                    th = tg[q]
                    ready = np.zeros((N, NOFF), dtype=bool)
                    hist = np.full((N, NOFF), np.nan)
                    ws = wu = ts = 0.0
                    for v in vids:
                        qs, qts = qidx_by_v[v], qt_by_v[v]
                        for o in range(NOFF):
                            al = a[(v, o)]
                            if al is None:
                                continue
                            sid, stt = al
                            sfold[qs, o] = sig[H]["session_fold"][sid]
                            sg = (sig[H]["truth"][sid] if nc else sig[H]["pred"][sid])[stt:stt + span[v]]
                            # a zero predicted risk must mean "never warm": with th == 0 a >= test
                            # would latch the device warm forever (this is what negative control
                            # (a) is for, and it caught it).
                            on = (sg >= th) if th > 0 else (sg > 0)
                            st_, w_, wu_ = device_state_from_schedule(warm_schedule(on), list(qts))
                            ws += w_; wu += wu_; ts += span[v]
                            for j, (r_, _lag, ht) in enumerate(st_):
                                if r_:
                                    ready[qs[j], o] = True
                                    hist[qs[j], o] = ht
                    wlat = np.full((N, NOFF), np.inf)
                    mm = ready & np.isfinite(hist)
                    if mm.any():
                        wlat[mm] = np.array([warm_answer_s(float(x)) for x in hist[mm]])
                    out[(H, q, nc)] = dict(ready=ready, hist=hist, wlat=wlat, theta=th,
                                           warm_s=ws, warmup_s=wu, total_s=ts)
        return out, sfold

    off_fold = np.arange(NOFF) % NFOLD
    rng = np.random.default_rng(SEED)
    v_index = {v: np.array([qi[q] for q in byv[v]]) for v in vids}
    boots = []
    for _ in range(NB):
        vs = rng.choice(len(vids), len(vids), replace=True)
        offs = rng.integers(0, NOFF, len(vids))
        boots.append((np.concatenate([v_index[vids[k]] for k in vs]),
                      np.concatenate([np.full(len(v_index[vids[k]]), offs[j]) for j, k in enumerate(vs)])))

    def mean_ci(mat, valid):
        pts = np.array([float(np.mean(mat[qs, os][valid[qs, os]])) for qs, os in boots if valid[qs, os].any()])
        return [float(np.percentile(pts, 2.5)), float(np.percentile(pts, 97.5))]

    def paired_ci(a_, b_, valid):
        pts = np.array([float(np.mean(a_[qs, os][valid[qs, os]] - b_[qs, os][valid[qs, os]]))
                        for qs, os in boots if valid[qs, os].any()])
        return [float(np.percentile(pts, 2.5)), float(np.percentile(pts, 97.5))]

    for rg in todo:
        sig = p3_signals(rg)
        a = alignments[rg]
        P3ST, SFOLD = p3_states(rg, sig, a)
        print("  p3 states built for", rg, flush=True)
        for net in NETS:
            (lat, reach, valid, dw_lat, dw_ok, dw_lag, dw_hist, mb_hr, sess_s,
             dw_any, dw_lat_opt) = replay(rg, net, PRIMARY_FMT)
            for dl in DEADLINES:
                U = {}
                for n in cloud_names:
                    U[n] = ((lat[n] <= dl) & (corr[n][:, None] > 0)).astype(float)
                for n in dev_nowarm:
                    c = comp[n].copy(); c[np.isnan(c) | ~avail[n]] = np.inf
                    U[n] = np.tile(((c <= dl) & (corr[n] > 0)).astype(float)[:, None], NOFF)
                CW = corr["dev-4B-D2-warm"][:, None]
                CB = corr["dev-4B-SHORT-N1"][:, None]      # negative control (b) letters
                CWF = np.tile(CW, (1, NOFF))
                U["dev-4B-D2-warm"] = (dw_ok & (dw_lat <= dl) & (CW > 0)).astype(float)
                U_warm_opt = (dw_any & (dw_lat_opt <= dl) & (CW > 0)).astype(float)
                U_warm_ctrlb = (dw_ok & (dw_lat <= dl) & (CB > 0)).astype(float)
                stack = np.stack([U[n] for n in names])
                oracle_kw = stack.max(axis=0)
                stack_a = np.stack([U[n] for n in names if n != "dev-4B-D2-warm"])
                oracle_nokw = stack_a.max(axis=0)

                u_cloud = np.zeros((N, NOFF))
                for nm in cloud_names:
                    m = p1_cfg == nm
                    u_cloud[m] = U[nm][m]

                static = np.zeros((N, NOFF)); static_pick = {}
                p1 = np.zeros((N, NOFF)); p2 = np.zeros((N, NOFF)); dev_pick = {}
                p2_opt = np.zeros((N, NOFF)); p2_cb = np.zeros((N, NOFF))
                p2_lat = np.zeros((N, NOFF))
                dw_used_p2 = np.zeros((N, NOFF))
                for f in range(NFOLD):
                    tr, te = np.where(off_fold != f)[0], np.where(off_fold == f)[0]
                    sc = [(float(U[n][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0, n) for n in names]
                    best = max(sc, key=lambda x: (x[0], x[1]))[1]
                    static_pick[int(f)] = best
                    static[:, te] = U[best][:, te]
                    dsc = [(float(U[n][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0, n)
                           for n in dev_nowarm]
                    bd = max(dsc, key=lambda x: (x[0], x[1]))[1]
                    dev_pick[int(f)] = bd
                    r = reach[:, te] == 1
                    p1[:, te] = np.where(r, u_cloud[:, te], U[bd][:, te])
                    # P2: cloud as P1 when reachable; otherwise the faster-deliverable device arm
                    dlat_bd = np.tile(np.where(np.isnan(comp[bd]) | ~avail[bd], np.inf,
                                               comp[bd])[:, None], NOFF)[:, te]
                    # deliverability of each device option, and the training-fold utility of each
                    warm_ok = dw_ok[:, te] & (dw_lat[:, te] <= dl)
                    bd_ok = dlat_bd <= dl
                    uw_tr = (float(U["dev-4B-D2-warm"][:, tr][valid[:, tr]].mean())
                             if valid[:, tr].any() else 0.0)
                    ub_tr = float(U[bd][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0
                    warm_better_tr = uw_tr > ub_tr
                    # PRIMARY: take the warm arm when it is deliverable and either the fallback is
                    # not deliverable or the warm arm scored higher on the training folds.
                    use_warm = warm_ok & (~bd_ok | warm_better_tr)
                    dev_u = np.where(use_warm, U["dev-4B-D2-warm"][:, te], U[bd][:, te])
                    p2[:, te] = np.where(r, u_cloud[:, te], dev_u)
                    dw_used_p2[:, te] = np.where(r, 0.0, use_warm.astype(float))
                    # VARIANT, literal "faster-deliverable": lower latency wins even when both meet
                    # the deadline.
                    use_warm_lat = warm_ok & (dw_lat[:, te] < dlat_bd)
                    p2_lat[:, te] = np.where(r, u_cloud[:, te],
                                             np.where(use_warm_lat, U["dev-4B-D2-warm"][:, te], U[bd][:, te]))
                    # OPTIMISTIC: no staleness gate on the warm state
                    warm_ok_o = dw_any[:, te] & (dw_lat_opt[:, te] <= dl)
                    uo = warm_ok_o & (~bd_ok | warm_better_tr)
                    p2_opt[:, te] = np.where(r, u_cloud[:, te],
                                             np.where(uo, U_warm_opt[:, te], U[bd][:, te]))
                    p2_cb[:, te] = np.where(r, u_cloud[:, te],
                                            np.where(use_warm, U_warm_ctrlb[:, te], U[bd][:, te]))

                # ---- P3 and P3-noncausal: theta/H cross-fitted by trace session
                def p3_utility(H, q, nc, cw=None):
                    stt = P3ST[(H, q, nc)]
                    u = np.zeros((N, NOFF))
                    m = stt["ready"] & avail["dev-4B-D2-warm"][:, None]
                    wl = np.where(m, stt["wlat"], np.inf)
                    for f in range(NFOLD):
                        tr = np.where(off_fold != f)[0]
                        te = np.where(off_fold == f)[0]
                        bd = dev_pick[int(f)]
                        bl = np.tile(np.where(np.isnan(comp[bd]) | ~avail[bd], np.inf, comp[bd])[:, None], NOFF)[:, te]
                        cwt = (CWF if cw is None else cw)[:, te]
                        uw = (m[:, te] & (wl[:, te] <= dl) & (cwt > 0)).astype(float)
                        uw_tr2 = (float(U["dev-4B-D2-warm"][:, tr][valid[:, tr]].mean())
                                  if valid[:, tr].any() else 0.0)
                        ub_tr2 = float(U[bd][:, tr][valid[:, tr]].mean()) if valid[:, tr].any() else 0.0
                        usew = (m[:, te] & (wl[:, te] <= dl)) & ((bl > dl) | (uw_tr2 > ub_tr2))
                        devu = np.where(usew, uw, U[bd][:, te])
                        u[:, te] = np.where(reach[:, te] == 1, u_cloud[:, te], devu)
                    return u

                def run_p3(nc, cw=None):
                    util = np.zeros((N, NOFF)); picks = {}
                    ws = wu = ts = 0.0
                    cand = {(H, q): p3_utility(H, q, nc, cw) for H in P3_HORIZONS for q in P3_QLEVELS}
                    for f in range(NFOLD):
                        trm = valid & (SFOLD != f) & (SFOLD >= 0)
                        tem = valid & (SFOLD == f)
                        grid = []
                        for H in P3_HORIZONS:
                            for q in P3_QLEVELS:
                                st_ = P3ST[(H, q, nc)]
                                sc_ = float(cand[(H, q)][trm].mean()) if trm.any() else 0.0
                                wf = st_["warm_s"] / st_["total_s"] if st_["total_s"] else 0.0
                                grid.append((sc_, wf, H, q))
                        top = max(g[0] for g in grid)
                        # PRIMARY criterion: the cheapest schedule whose training utility is within
                        # 1 pp of the best -- the only criterion under which the pre-registered
                        # decision rule ("matches P2 within 1 pp at lower energy") can discriminate.
                        ok = [g for g in grid if g[0] >= top - 0.01]
                        bu, bwf, H, q = min(ok, key=lambda g: (g[1], -g[0], g[2], g[3]))
                        bu_umax, wf_u, H_u, q_u = max(grid, key=lambda g: (g[0], -g[1]))
                        best = (H, q)
                        picks[int(f)] = dict(
                            H_s=H, quantile_level=q, theta=P3ST[(H, q, nc)]["theta"],
                            train_utility=bu, warm_fraction=bwf,
                            grid=[dict(H_s=g[2], quantile_level=g[3], train_utility=g[0],
                                       warm_fraction=g[1]) for g in grid],
                            utility_only_fit=dict(H_s=H_u, quantile_level=q_u,
                                                  train_utility=bu_umax, warm_fraction=wf_u))
                        util[tem] = cand[(H, q)][tem]
                        st_ = P3ST[(H, q, nc)]
                        frac = float(tem.sum()) / max(float(valid.sum()), 1.0)
                        ws += st_["warm_s"] / max(st_["total_s"], 1e-9) * frac
                        wu += st_["warmup_s"] / max(st_["total_s"], 1e-9) * frac
                        ts += frac
                    return util, (ws / ts if ts else 0.0), (wu / ts if ts else 0.0), picks

                p3, p3_wf, p3_wuf, p3_pick = run_p3(False)
                p3n, p3n_wf, _p3n_wuf, p3n_pick = run_p3(True)
                p3cb, _a1, _a2, _a3 = run_p3(False, np.tile(CB, (1, NOFF)))

                energy = dict(
                    P1_Wh_per_hour=0.0, P2_Wh_per_hour=WARM_DELTA_W,
                    P3_Wh_per_hour=WARM_DELTA_W * p3_wf,
                    P3_warmup_share_of_warm_time=(p3_wuf / p3_wf if p3_wf > 0 else 0.0),
                    P2_J_per_hour=WARM_DELTA_W * 3600.0,
                    P3_J_per_hour=WARM_DELTA_W * 3600.0 * p3_wf,
                    P3_warm_fraction=p3_wf, P3_noncausal_warm_fraction=p3n_wf,
                    note="Device energy above loaded idle at StudyE8 Part C's measured 5.21 W delta "
                         "(15.1 Wh per warm-hour). P3's warm-up prefill is charged at the same delta "
                         "because StudyE8 did not measure cold-prefill power, which makes P3's "
                         "energy a LOWER BOUND. No cloud capacity limit is modelled (see RH5/RH8).")

                cell = dict(
                    regime=rg, uplink=net, mode="STREAM", deadline_s=dl, format=PRIMARY_FMT,
                    n_pairs=int(valid.sum()), reachable_fraction=float(reach[valid].mean()),
                    oracle_no_keepwarm=float(oracle_nokw[valid].mean()),
                    oracle_keepwarm=float(oracle_kw[valid].mean()),
                    oracle_keepwarm_ci=mean_ci(oracle_kw, valid),
                    best_static=float(static[valid].mean()), best_static_ci=mean_ci(static, valid),
                    best_static_pick=static_pick, P1_device_config=dev_pick,
                    P1=float(p1[valid].mean()), P1_ci=mean_ci(p1, valid),
                    P2=float(p2[valid].mean()), P2_ci=mean_ci(p2, valid),
                    P3=float(p3[valid].mean()), P3_ci=mean_ci(p3, valid),
                    P3_noncausal=float(p3n[valid].mean()),
                    P2_minus_P1=float((p2 - p1)[valid].mean()), P2_minus_P1_ci=paired_ci(p2, p1, valid),
                    P3_minus_P1=float((p3 - p1)[valid].mean()), P3_minus_P1_ci=paired_ci(p3, p1, valid),
                    P3_minus_P2=float((p3 - p2)[valid].mean()), P3_minus_P2_ci=paired_ci(p3, p2, valid),
                    P2_minus_static=float((p2 - static)[valid].mean()),
                    P2_minus_static_ci=paired_ci(p2, static, valid),
                    P3_noncausal_minus_P3=float((p3n - p3)[valid].mean()),
                    P3_params=p3_pick, P3_noncausal_params=p3n_pick, energy=energy,
                    P2_optimistic_no_staleness_gate=float(p2_opt[valid].mean()),
                    P2_literal_faster_deliverable=float(p2_lat[valid].mean()),
                    P2_literal_minus_P1=float((p2_lat - p1)[valid].mean()),
                    P2_optimistic_minus_P1=float((p2_opt - p1)[valid].mean()),
                    P2_optimistic_minus_P1_ci=paired_ci(p2_opt, p1, valid),
                    negative_control_b=dict(
                        description="device-warm letters replaced by the device short-window (F4 "
                                    "N=1) letters; every latency, cost and schedule unchanged.",
                        P2_controlb=float(p2_cb[valid].mean()),
                        P2_controlb_minus_P1=float((p2_cb - p1)[valid].mean()),
                        P2_controlb_minus_P1_ci=paired_ci(p2_cb, p1, valid),
                        P3_controlb=float(p3cb[valid].mean()),
                        P3_controlb_minus_P1=float((p3cb - p1)[valid].mean()),
                        collapse_fraction_P2=(float((p2_cb - p1)[valid].mean() / (p2 - p1)[valid].mean())
                                              if abs(float((p2 - p1)[valid].mean())) > 1e-12 else None)),
                    device_warm_ready_fraction=float(dw_ok[valid].mean()),
                    device_warm_lag_p50=float(np.nanmedian(dw_lag[valid])) if np.isfinite(np.nanmedian(dw_lag[valid])) else None,
                    device_warm_hist_tok_p50=float(np.nanmedian(dw_hist[valid])),
                    device_warm_used_fraction_P2=float(dw_used_p2[valid].mean()),
                    device_warm_any_fraction=float(dw_any[valid].mean()),
                    device_warm_lag_s=dict(
                        p50=float(np.nanpercentile(dw_lag[valid], 50)),
                        p90=float(np.nanpercentile(dw_lag[valid], 90)),
                        max=float(np.nanmax(dw_lag[valid])),
                        fraction_le_2s=float(np.nanmean(dw_lag[valid] <= STALE_TOL_S))),
                    per_config={n: float(U[n][valid].mean()) for n in names},
                    uplink_MB_per_hour=mb_hr,
                    split_by_reachability=dict(
                        connected=dict(n=int((valid & (reach == 1)).sum()),
                                       P1=float(p1[valid & (reach == 1)].mean()) if (valid & (reach == 1)).any() else None,
                                       P2=float(p2[valid & (reach == 1)].mean()) if (valid & (reach == 1)).any() else None,
                                       P3=float(p3[valid & (reach == 1)].mean()) if (valid & (reach == 1)).any() else None),
                        outage=dict(n=int((valid & (reach == 0)).sum()),
                                    P1=float(p1[valid & (reach == 0)].mean()) if (valid & (reach == 0)).any() else None,
                                    P2=float(p2[valid & (reach == 0)].mean()) if (valid & (reach == 0)).any() else None,
                                    P3=float(p3[valid & (reach == 0)].mean()) if (valid & (reach == 0)).any() else None)))
                results["cells"][f"{rg}|{net}|STREAM|{dl}s"] = cell
        print("done regime", rg, flush=True)

    # ---------------------------------------------------------------- pre-registered decision rule
    PRE_CELLS = [f"{rg}|13.6Mbps_44ms|STREAM|{dl}s"
                 for rg in ("outdoor_driving", "synthetic_5pct", "synthetic_10pct",
                            "synthetic_20pct", "synthetic_30pct") for dl in (2, 5)]
    rule = {}
    for k in PRE_CELLS:
        c = results["cells"].get(k)
        if c is None:
            continue
        d21 = c["P2_minus_P1"]; c21 = c["P2_minus_P1_ci"]
        d31 = c["P3_minus_P1"]; c31 = c["P3_minus_P1_ci"]
        d32 = c["P3_minus_P2"]; c32 = c["P3_minus_P2_ci"]
        matches_p2 = abs(d32) <= 0.01 and c32[0] >= -0.01 and c32[1] <= 0.01
        cheaper = c["energy"]["P3_Wh_per_hour"] < c["energy"]["P2_Wh_per_hour"] * 0.999
        beats_p1 = c31[0] > 0.0
        rule[k] = dict(
            P2_minus_P1=d21, P2_minus_P1_ci=c21,
            P3_minus_P1=d31, P3_minus_P1_ci=c31,
            P3_minus_P2=d32, P3_minus_P2_ci=c32,
            P2_Wh_per_hour=c["energy"]["P2_Wh_per_hour"],
            P3_Wh_per_hour=c["energy"]["P3_Wh_per_hour"],
            P3_warm_fraction=c["energy"]["P3_warm_fraction"],
            P3_matches_P2_within_1pp=bool(matches_p2),
            P3_strictly_cheaper_than_P2=bool(cheaper),
            P3_beats_P1_ci_excludes_0=bool(beats_p1),
            keepwarm_decision_nontrivial=bool((matches_p2 and cheaper) or beats_p1),
            P2_equals_P1=bool(abs(d21) <= 1e-12))
    results["decision_rule"] = dict(
        description="Pre-registered: the keep-warm decision is NON-TRIVIAL if P3 matches P2's "
                    "utility (difference CI within +/-1 pp) at significantly lower device energy, "
                    "or beats P1 with a CI excluding 0, in at least one pre-specified cell "
                    "(outdoor-driving or synthetic >= 5%, uplink 13.6 Mbit/s, deadline 2 or 5 s). "
                    "If P2 = P1 everywhere, device-warm has no value on this workload. If P3 = P2 "
                    "at equal energy, the decision is a static rule.",
        cells=rule,
        any_cell_nontrivial=bool(any(v["keepwarm_decision_nontrivial"] for v in rule.values())),
        cells_nontrivial=[k for k, v in rule.items() if v["keepwarm_decision_nontrivial"]],
        P2_equals_P1_everywhere=bool(all(abs(c["P2_minus_P1"]) <= 1e-12
                                         for c in results["cells"].values())))

    # ---------------------------------------------------------------- negative control (a)
    nca = {}
    for k, c in results["cells"].items():
        if not k.startswith("synthetic_0pct|"):
            continue
        nca[k] = dict(reachable_fraction=c["reachable_fraction"], P1=c["P1"], P2=c["P2"], P3=c["P3"],
                      P3_warm_fraction=c["energy"]["P3_warm_fraction"],
                      abs_P2_minus_P1=abs(c["P2_minus_P1"]), abs_P3_minus_P1=abs(c["P3_minus_P1"]))
    results["negative_control_a"] = dict(
        description="Outage fraction 0 (synthetic_0pct): P3's warm fraction must go to ~0 and P2/P3 "
                    "must equal P1, because the device is never the only node that can answer.",
        cells=nca,
        pass_warm_fraction=bool(all(v["P3_warm_fraction"] < 1e-9 for v in nca.values())),
        pass_equal_P1=bool(all(v["abs_P2_minus_P1"] < 1e-12 and v["abs_P3_minus_P1"] < 1e-12
                               for v in nca.values())))

    # ---------------------------------------------------------------- instrumented trace
    if "outdoor_driving" in todo:
        rg, net, dl, fmt = "outdoor_driving", "13.6Mbps_44ms", 5, PRIMARY_FMT
        up_mbps, rtt = NETS[net]; R = up_mbps * 1e6 / 8.0
        a = alignments[rg]; pick = None
        for v in vids:
            for o in range(NOFF):
                al = a[(v, o)]
                if al is None:
                    continue
                sid, stt = al
                conn = regimes[rg][sid][stt:stt + span[v]]
                if (conn[qt_by_v[v].astype(int)] == 0).any():
                    pick = (v, o, sid, stt); break
            if pick:
                break
        if pick:
            v, o, sid, stt = pick
            conn = regimes[rg][sid][stt:stt + span[v]]
            C = A.prefix_connected(conn)
            w0 = warm_from0[v]
            rows = []
            for j, i in enumerate(qidx_by_v[v]):
                q = Q[i]; ts = int(meta[q]["qt"])
                ready, lag, ht, cur = w0[j]
                r = dict(question_id=q, question_time_s=meta[q]["qt"], trace_second=stt + ts,
                         connected_at_question=int(conn[ts]),
                         outage_seconds_in_last_60s=int((conn[max(0, ts - 60):ts] == 0).sum()),
                         device_warm_state=dict(
                             warm_since_s=0.0, ready=bool(ready), ingest_lag_s=lag,
                             history_tokens_held=ht, history_current_to_s=cur,
                             full_history_tokens=D2_TOKENS_PER_S * meta[q]["qt"],
                             past_2s_cadence_crossover=bool((ht or 0) > CROSSOVER_TOK),
                             usable_under_primary_rule=bool(ready and lag is not None
                                                            and lag <= STALE_TOL_S)),
                         keepwarm_charges=dict(
                             device_J_since_session_start=round(WARM_DELTA_W * meta[q]["qt"], 1),
                             device_W_above_idle=WARM_DELTA_W),
                         configs={})
                for nm, _m, loc, rep, cache, key, _ck, _rt in CONFIGS:
                    e = dict(correct=(None if not avail[nm][i] else bool(corr[nm][i] > 0)),
                             status=status[nm][i])
                    if loc == "cloud":
                        qb = A.queue_bytes(conn, STREAM_RATE[(rep, fmt)], R)
                        pend = float(qb[ts] + NEWEST_FRAME[(rep, fmt)])
                        e.update(queue_backlog_B=round(float(qb[ts]), 1), pending_B=round(pend, 1),
                                 rtt_s=rtt, compute_s=(None if np.isnan(comp[nm][i]) else round(float(comp[nm][i]), 4)))
                        if conn[ts] == 0:
                            e.update(upload_s=None, total_s=None, delivered=False,
                                     note="cloud unreachable at question time")
                        else:
                            d = A.drain_s(C, ts, pend / R)
                            tot = (None if (d is None or np.isnan(comp[nm][i]) or not avail[nm][i])
                                   else d + rtt + float(comp[nm][i]))
                            e.update(upload_s=(None if d is None else round(d, 4)),
                                     total_s=(None if tot is None else round(tot, 4)),
                                     delivered=bool(tot is not None and tot <= dl))
                    elif nm == "dev-4B-D2-warm":
                        usable = bool(ready and lag is not None and lag <= STALE_TOL_S and avail[nm][i])
                        tot = warm_answer_s(ht) if (ready and ht is not None) else None
                        e.update(upload_s=0.0, compute_s=(None if tot is None else round(tot, 4)),
                                 total_s=(None if tot is None else round(tot, 4)),
                                 delivered=bool(usable and tot is not None and tot <= dl),
                                 note="warm answer costs the question tail only; history reused")
                    else:
                        tot = None if (np.isnan(comp[nm][i]) or not avail[nm][i]) else float(comp[nm][i])
                        e.update(upload_s=0.0, compute_s=(None if tot is None else round(tot, 4)),
                                 total_s=(None if tot is None else round(tot, 4)),
                                 delivered=bool(tot is not None and tot <= dl))
                    e["utility"] = int(bool(e.get("delivered")) and e["correct"] is True)
                    r["configs"][nm] = e
                rows.append(r)
            results["trace_example_stageb"] = dict(
                regime=rg, uplink=net, mode="STREAM", format=fmt, deadline_s=dl, video_id=v,
                offset=o, trace_session=sid, trace_start_second=stt, video_span_s=span[v],
                outage_seconds_in_window=int((conn == 0).sum()),
                device_policy="P2 (always-warm from session second 0)",
                questions=rows)

    results["_provenance"] = stamp(script="study_e6b_stageb.py", model=None, device="cpu",
                                   n=N * NOFF, args=None)
    (OUT / "e6b_stageb_results.json").write_text(json.dumps(results, indent=1))
    print("cells:", len(results["cells"]))


if __name__ == "__main__":
    main()
