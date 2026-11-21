"""The D162 cost-model gate: healthy-regime NNLS refit on the load sweep.

Implements research/prereg_cost_model_gate_d162.md (committed 9bd6793, BEFORE the sweep existed)
without deviation. Nothing here is a choice made after seeing data; every bound, criterion and
split comes from that document.

Reuses the committed gate's conventions on purpose, so the numbers are comparable to the positive
control the criteria were calibrated against (cost_model_gate.py):
  * ratio_p50 is median(predicted) / median(actual), a ratio of medians, NOT a median of ratios;
  * rows are cloud requests with t_submit, t_first_token, t_done and prompt_tokens present;
  * cache state is warm iff cached_tokens > 0.

What is NEW here, and why (D159 (B), D160 (2), D162):
  1. queue_uncached_ahead REPLACES the committed overlap COUNT. What a queue makes you wait for is
     work, not requests, and the 160x overlap spread is what broke the linear form.
  2. Non-negative least squares (Lawson-Hanson), so predictions cannot be negative by construction.
     The D156 (4) gate failed on an intercept of -2.8699 with 59.8 percent negative predictions.
  3. Requests are classified by the observed first-token p50 of their own 100 s window, never by
     offered load, because the knee bracket was retracted. Only HEALTHY data is fitted or tested.
"""
import bisect
import gzip
import heapq
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
OUT = ROOT / "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"

# ---- all pre-registered, none fitted
WINDOW_S = 100.0
HEALTHY_MAX_S = 2.781
COLLAPSED_MIN_S = 31.0
PASS_ALL = (0.80, 1.25)
PASS_WARM = (0.70, 1.43)
SENS_HEALTHY = (2.0, 3.0, 4.0, 5.0)
SENS_COLLAPSED = (20.0, 25.0, 31.0)
ARM = "warm-all-lru-reactive"
NS = (4, 8, 12, 16, 20)
FIT_SEED, TEST_SEED = 4, 5


def cell_dir(n, seed):
    return RUNS / f"{ARM}_n{n}_s{seed}_1200s_h27_3t_L3_epg_ls{n:02d}"


def jl(p):
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            op = gzip.open if str(c).endswith(".gz") else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    return []


def _queue_ahead(items, weight_key):
    """For each interval, the summed WEIGHT of intervals open at its start instant.

    items: list of (start, end, weight, idx). O(n log n) by a sweep with a finish-heap, because a
    cell holds tens of thousands of requests and the naive pass does not finish over 10 cells.
    """
    out = [0.0] * len(items)
    live, running = [], 0.0
    for s, e, w, i in sorted(items, key=lambda x: x[0]):
        while live and live[0][0] <= s:
            running -= heapq.heappop(live)[1]
        out[i] = running                      # excludes this request, which is not yet open
        heapq.heappush(live, (e, w))
        running += w
    return out


def features(run):
    req = [r for r in jl(run / "request.jsonl")
           if r.get("t_submit") is not None and r.get("t_done") is not None
           and r.get("t_first_token") is not None and r.get("prompt_tokens")]
    if not req:
        return []
    sess = {r["opportunity_id"]: str(r.get("session_id") or "")
            for r in jl(run / "outcomes.jsonl") if r.get("opportunity_id")}
    base = []
    for i, r in enumerate(req):
        s, a, b = float(r["t_submit"]), float(r["t_first_token"]), float(r["t_done"])
        pt, ct = int(r["prompt_tokens"]), int(r.get("cached_tokens") or 0)
        ot = int(r.get("output_tokens") or 0)
        oid = r.get("opportunity_id")
        kind = ("robot" if str(sess.get(oid, "")).startswith("robo")
                else "single_shot" if str(sess.get(oid, "")).startswith("asst")
                else "dashcam")
        base.append(dict(i=i, kind=kind, t_submit=s, first_token_s=a - s, decode_s=b - a,
                         prompt_tokens=pt, cached_tokens=ct, output_tokens=ot,
                         uncached_tokens=max(pt - ct, 0), warm=bool(ct > 0)))
    qu = _queue_ahead([(r["t_submit"], r["t_submit"] + r["first_token_s"],
                        float(r["uncached_tokens"]), r["i"]) for r in base], "uncached")
    qd = _queue_ahead([(r["t_submit"] + r["first_token_s"],
                        r["t_submit"] + r["first_token_s"] + r["decode_s"],
                        float(r["output_tokens"]), r["i"]) for r in base], "decode")
    for r in base:
        r["queue_uncached_ahead"] = qu[r["i"]]
        r["queue_decode_ahead"] = qd[r["i"]]
    return base


def classify(rows, healthy_max=HEALTHY_MAX_S, collapsed_min=COLLAPSED_MIN_S):
    """Zone per request, inherited from the first-token p50 of its own 100 s submit window."""
    win = {}
    for r in rows:
        win.setdefault(int(r["t_submit"] // WINDOW_S), []).append(r["first_token_s"])
    zone_of, wins = {}, {}
    for k, v in win.items():
        p50 = st.median(v)
        z = ("healthy" if p50 <= healthy_max
             else "collapsed" if p50 > collapsed_min else "unclassified")
        zone_of[k] = z
        wins[k] = dict(window_index=k, n=len(v), first_token_p50=round(p50, 4), zone=z)
    for r in rows:
        r["zone"] = zone_of[int(r["t_submit"] // WINDOW_S)]
    return wins


def nnls(A, b, iters=200, tol=1e-12):
    """Lawson-Hanson active set, pure Python, so every coefficient is >= 0 by construction."""
    m, n = len(A), len(A[0])

    def solve_ls(cols):
        # normal equations on the passive set, Gauss-Jordan, in the house style
        k = len(cols)
        M = [[sum(A[r][cols[i]] * A[r][cols[j]] for r in range(m)) for j in range(k)]
             + [sum(A[r][cols[i]] * b[r] for r in range(m))] for i in range(k)]
        for c in range(k):
            p = max(range(c, k), key=lambda rr: abs(M[rr][c]))
            if abs(M[p][c]) < 1e-15:
                return None
            M[c], M[p] = M[p], M[c]
            d = M[c][c]
            M[c] = [x / d for x in M[c]]
            for rr in range(k):
                if rr != c and M[rr][c]:
                    f = M[rr][c]
                    M[rr] = [x - f * y for x, y in zip(M[rr], M[c])]
        return [M[i][k] for i in range(k)]

    x = [0.0] * n
    P = []
    for _ in range(iters):
        resid = [b[r] - sum(A[r][j] * x[j] for j in range(n)) for r in range(m)]
        w = [sum(A[r][j] * resid[r] for r in range(m)) for j in range(n)]
        cand = [j for j in range(n) if j not in P and w[j] > tol]
        if not cand:
            break
        P = sorted(P + [max(cand, key=lambda j: w[j])])
        for _ in range(iters):
            z = solve_ls(P)
            if z is None:
                return x
            if all(v > 0 for v in z):
                for j, v in zip(P, z):
                    x[j] = v
                break
            alpha = min((x[j] / (x[j] - v) for j, v in zip(P, z)
                         if v <= 0 and (x[j] - v) != 0), default=0.0)
            x = [x[j] + alpha * ((dict(zip(P, z)).get(j, 0.0)) - x[j]) for j in range(n)]
            P = [j for j in P if x[j] > tol]
            if not P:
                break
    return x


def fit(rows):
    one = [1.0] * len(rows)
    A1 = [[1.0, float(r["uncached_tokens"]), float(r["queue_uncached_ahead"])] for r in rows]
    ft = nnls(A1, [r["first_token_s"] for r in rows])
    A2 = [[1.0, float(r["queue_decode_ahead"])] for r in rows]
    dec = nnls(A2, [r["decode_s"] for r in rows])
    return dict(first_token=dict(intercept=ft[0], per_uncached_token=ft[1], per_queue_token=ft[2]),
                decode=dict(intercept=dec[0], per_queue_decode_token=dec[1]),
                n_fit=len(rows), form="NNLS, all coefficients >= 0 by construction")


def apply(m, r):
    f, d = m["first_token"], m["decode"]
    return (f["intercept"] + f["per_uncached_token"] * r["uncached_tokens"]
            + f["per_queue_token"] * r["queue_uncached_ahead"],
            d["intercept"] + d["per_queue_decode_token"] * r["queue_decode_ahead"])


def check(m, rows, name):
    out = {}
    for sel, label in ((lambda r: True, "all"), (lambda r: r["warm"], "warm"),
                       (lambda r: not r["warm"], "cold")):
        s = [r for r in rows if sel(r)]
        if not s:
            continue
        pf = [apply(m, r)[0] for r in s]
        pd = [apply(m, r)[1] for r in s]
        af = [r["first_token_s"] for r in s]
        ad = [r["decode_s"] for r in s]
        out[label] = dict(
            n=len(s), n_negative_predictions=sum(1 for p in pf if p < 0),
            first_token=dict(predicted_p50=round(st.median(pf), 4),
                             actual_p50=round(st.median(af), 4),
                             ratio_p50=(round(st.median(pf) / st.median(af), 4)
                                        if st.median(af) else None),
                             mae=round(st.fmean(abs(p - a) for p, a in zip(pf, af)), 4)),
            decode=dict(predicted_p50=round(st.median(pd), 4),
                        actual_p50=round(st.median(ad), 4),
                        ratio_p50=(round(st.median(pd) / st.median(ad), 4)
                                   if st.median(ad) else None),
                        mae=round(st.fmean(abs(p - a) for p, a in zip(pd, ad)), 4)))
    return dict(split=name, by_cache_state=out)


def selftest():
    """POSITIVE CONTROL ON THE FITTER ITSELF, recorded on every run.

    CLAUDE.md check 7: a known-good case must pass the check being applied, or the check is broken
    rather than the arm. A gate whose solver silently returned zeros would produce a confident
    verdict from nothing, and all-zeros is non-negative, so the NNLS constraint alone would not
    reveal it. Two cases: recover known non-negative coefficients, and clamp a genuinely negative
    one to zero WITHOUT collapsing the others.
    """
    import random
    random.seed(11)
    true = [0.25, 0.0004, 0.00002]
    A, b = [], []
    for _ in range(3000):
        u, q = random.uniform(100, 12000), random.uniform(0, 200000)
        A.append([1.0, u, q])
        b.append(true[0] + true[1] * u + true[2] * q + random.gauss(0, 0.01))
    got = nnls(A, b)
    rec = all(abs(g - t) <= max(0.02 * abs(t), 1e-4) for g, t in zip(got, true))
    A2, b2 = [], []
    for _ in range(3000):
        u, q = random.uniform(100, 12000), random.uniform(0, 200000)
        A2.append([1.0, u, q])
        b2.append(2.0 + 0.0005 * u - 0.000002 * q + random.gauss(0, 0.01))
    got2 = nnls(A2, b2)
    clamp = got2[0] > 0.5 and got2[1] > 1e-4 and got2[2] < 1e-9 and all(x >= 0 for x in got2)
    return dict(recovers_known_coefficients=dict(true=true, got=[round(x, 8) for x in got],
                                                 pass_=bool(rec)),
                clamps_negative_without_collapsing=dict(
                    got=[float(x) for x in got2], pass_=bool(clamp),
                    note="queue coefficient clamps to ~0 while intercept and uncached stay "
                         "positive, so the solver is not silently returning zeros"),
                all_pass=bool(rec and clamp))


def main():
    res = {"_prereg": "research/prereg_cost_model_gate_d162.md (9bd6793)",
           "_conventions": "ratio_p50 = median(predicted)/median(actual), as the committed gate"}
    res["solver_selftest"] = selftest()
    if not res["solver_selftest"]["all_pass"]:
        res["verdict"] = "WITHHELD: the NNLS solver failed its own positive control, so no " \
                         "verdict from it can be trusted. The check is broken, not the model."
        res["verdict_withheld"] = True
    cells, missing = {}, []
    for n in NS:
        for seed in (FIT_SEED, TEST_SEED):
            d = cell_dir(n, seed)
            if not (d / "request.jsonl.gz").exists() and not (d / "request.jsonl").exists():
                missing.append(d.name)
                continue
            rows = features(d)
            cells[(n, seed)] = rows
    res["cells_loaded"] = {f"n{n}_s{s}": len(v) for (n, s), v in sorted(cells.items())}
    res["cells_missing"] = missing

    allrows = [r for v in cells.values() for r in v]
    for (n, seed), rows in cells.items():
        classify(rows)
    res["zone_counts"] = {}
    for z in ("healthy", "unclassified", "collapsed"):
        sel = [r for r in allrows if r.get("zone") == z]
        res["zone_counts"][z] = dict(requests=len(sel),
                                     warm=sum(1 for r in sel if r["warm"]))

    fit_rows = [r for (n, s), v in cells.items() if s == FIT_SEED
                for r in v if r["zone"] == "healthy"]
    test_rows = [r for (n, s), v in cells.items() if s == TEST_SEED
                 for r in v if r["zone"] == "healthy"]
    res["warm_rows_held_out"] = sum(1 for r in test_rows if r["warm"])

    # PRECONDITION FIRST, before any verdict is computed or read.
    if missing:
        res["verdict"] = "WITHHELD: the sweep is incomplete, so the held-out set is not the " \
                         "pre-registered one. Missing: " + ", ".join(missing)
        res["verdict_withheld"] = True
    elif res["warm_rows_held_out"] <= 0:
        res["verdict"] = "SPLIT REJECTED: warm_rows_held_out = 0, the exact failure of the " \
                         "committed by_arm split. No verdict is reported."
        res["verdict_withheld"] = True

    if fit_rows:
        # Step 0: the queueing term must VARY, or the sweep cannot identify it (CONSTANT, stop).
        q = [r["queue_uncached_ahead"] for r in fit_rows]
        res["step0_queue_term_varies"] = dict(
            min=round(min(q), 1), p50=round(st.median(q), 1), max=round(max(q), 1),
            distinct=len({round(x, 3) for x in q}),
            verdict=("VARIES" if len({round(x, 3) for x in q}) > 10 else
                     "CONSTANT: the sweep cannot identify the queueing term (stopping condition)"))
        m = fit(fit_rows)
        res["model"] = m
        res["fit_check"] = check(m, fit_rows, f"fit seed {FIT_SEED} healthy")
        if test_rows:
            res["heldout_check"] = check(m, test_rows, f"held out seed {TEST_SEED} healthy")
        coll = [r for r in allrows if r.get("zone") == "collapsed"]
        if coll:
            res["collapsed_diagnostic"] = check(m, coll, "collapsed (DIAGNOSTIC ONLY, "
                                                         "cannot pass or fail the gate)")
        # sensitivity: the verdict must not move across the pre-registered bound ranges
        sens = []
        for hb in SENS_HEALTHY:
            for cb in SENS_COLLAPSED:
                for v in cells.values():
                    classify(v, healthy_max=hb, collapsed_min=cb)
                fr = [r for (n, s), v in cells.items() if s == FIT_SEED
                      for r in v if r["zone"] == "healthy"]
                tr = [r for (n, s), v in cells.items() if s == TEST_SEED
                      for r in v if r["zone"] == "healthy"]
                if not fr or not tr:
                    sens.append(dict(healthy_bound=hb, collapsed_bound=cb, verdict="NO DATA"))
                    continue
                mm = fit(fr)
                ck = check(mm, tr, "s")["by_cache_state"]
                ra = ck.get("all", {}).get("first_token", {}).get("ratio_p50")
                rw = ck.get("warm", {}).get("first_token", {}).get("ratio_p50")
                ok = (ra is not None and PASS_ALL[0] <= ra <= PASS_ALL[1]
                      and rw is not None and PASS_WARM[0] <= rw <= PASS_WARM[1])
                sens.append(dict(healthy_bound=hb, collapsed_bound=cb, ratio_all=ra,
                                 ratio_warm=rw, pass_=bool(ok)))
        res["sensitivity"] = sens
        for v in cells.values():      # restore the pre-registered bounds
            classify(v)

    if not res.get("verdict_withheld"):
        ck = res.get("heldout_check", {}).get("by_cache_state", {})
        ra = ck.get("all", {}).get("first_token", {}).get("ratio_p50")
        rw = ck.get("warm", {}).get("first_token", {}).get("ratio_p50")
        okall = ra is not None and PASS_ALL[0] <= ra <= PASS_ALL[1]
        okwarm = rw is not None and PASS_WARM[0] <= rw <= PASS_WARM[1]
        oksens = all(s.get("pass_") for s in res.get("sensitivity", []) if "pass_" in s)
        res["criteria"] = dict(ratio_all=ra, ratio_all_pass=okall, ratio_warm=rw,
                               ratio_warm_pass=okwarm, sensitivity_pass=oksens)
        res["verdict"] = ("PASS" if (okall and okwarm and oksens) else "FAIL")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(f"solver test  : {'PASS' if res['solver_selftest']['all_pass'] else 'FAIL'}")
    print(f"cells loaded : {res['cells_loaded']}")
    print(f"cells missing: {res['cells_missing']}")
    print(f"zones        : {res['zone_counts']}")
    print(f"warm held out: {res['warm_rows_held_out']}")
    if "step0_queue_term_varies" in res:
        print(f"step0 queue  : {res['step0_queue_term_varies']['verdict']}")
    if "model" in res:
        print(f"model        : {res['model']['first_token']}")
    if "heldout_check" in res:
        c = res["heldout_check"]["by_cache_state"]
        for k in ("all", "warm", "cold"):
            if k in c:
                print(f"  held out {k:5s} n={c[k]['n']:7d} ratio_p50 "
                      f"{c[k]['first_token']['ratio_p50']}")
    print(f"VERDICT      : {res['verdict']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
