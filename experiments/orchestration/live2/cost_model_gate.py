#!/usr/bin/env python3
"""POLICY v2 item 3: recalibrate the cost model on committed live data, with a HELD-OUT check.

  python3 -I experiments/orchestration/live2/cost_model_gate.py

The v2 planner's latest-safe-start deferral is only as good as its estimate of when an answer will
land. Section 16's calibration fitted an interference factor on the warming-free arms and then
validated on edf and llf, where the COLD side transferred within 1 to 5 percent and the WARM side
missed badly, warm single-shot by 0.27x and build by 0.65x. Everything v2 wants to do is on the warm
side, so that gap is the gate.

WHAT IS FITTED, on committed live requests only

  first-token latency   from the submitted request's prompt tokens, its CACHE STATE (the engine's
                        own per-request cached_tokens, not a belief), and the number of requests
                        overlapping it
  decode                from the number of requests overlapping the DECODE WINDOW alone, because a
                        robot answer is two tokens and its decode is set by the crowd and not by
                        the token count (frozen_test 18.7.2, 19.5)

HOW IT IS HELD OUT, two ways, because they fail differently

  by seed   fit on seeds 0 and 4, predict seeds 5 and 6, same arms. Tests generalisation across
            workload draws.
  by arm    fit on the non-hybrid arms, predict the hybrids. Tests generalisation across POLICIES,
            which is the one section 16 failed, and it is the one v2 needs because v2 is a new
            policy whose request stream no fitted arm has produced.

NOTHING HERE IS A LIVE RUN. CPU only, committed logs only.
"""
from __future__ import annotations

import gzip
import json
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _provenance  # noqa: E402

RUNS = ROOT / "results/orchestration/live2/frozen_test/runs"
OUT = ROOT / "results/orchestration/live2/frozen_test/cost_model_gate.json"
HYBRID = ("hybrid-F-lhreq", "hybrid-F6-lhreq")
CELL = "_n16_s%d_1200s_h27_3t"
SEEDS = (0, 4, 5, 6)


def jl(p):
    for c in (p, p.with_name(p.name + ".gz")):
        if c.exists():
            op = gzip.open if str(c).endswith(".gz") else open
            with op(c, "rt") as f:
                return [json.loads(x) for x in f if x.strip()]
    return []


def features(run: Path):
    """One row per cloud request: what the model would be given, and what happened."""
    req = [r for r in jl(run / "request.jsonl")
           if r.get("t_submit") is not None and r.get("t_done") is not None
           and r.get("t_first_token") is not None and r.get("prompt_tokens")]
    if not req:
        return []
    # Overlap counts by two bisects, not by scanning. A cell holds about 54,000 requests, so the
    # naive O(n^2) pass over 20 cells does not finish: for an interval [s, e) the number of other
    # intervals overlapping it is (how many START before e) minus (how many END at or before s).
    import bisect
    starts = sorted(float(r["t_submit"]) for r in req)
    ends = sorted(float(r["t_done"]) for r in req)

    def overlaps(s0, e0):
        return bisect.bisect_left(starts, e0) - bisect.bisect_right(ends, s0) - 1
    sess = {r["opportunity_id"]: str(r.get("session_id") or "")
            for r in jl(run / "outcomes.jsonl") if r.get("opportunity_id")}
    rows = []
    for r in req:
        a, b, s = float(r["t_first_token"]), float(r["t_done"]), float(r["t_submit"])
        ov_ft = overlaps(s, a)
        ov_dec = overlaps(a, b)
        ct = int(r.get("cached_tokens") or 0)
        pt = int(r["prompt_tokens"])
        oid = r.get("opportunity_id")
        kind = ("robot" if str(sess.get(oid, "")).startswith("robo")
                else "single_shot" if str(sess.get(oid, "")).startswith("asst")
                else "dashcam")
        rows.append(dict(kind=kind, prompt_tokens=pt, cached_tokens=ct,
                         uncached_tokens=max(pt - ct, 0), warm=bool(ct > 0),
                         overlap_ft=max(ov_ft, 0), overlap_decode=max(ov_dec, 0),
                         first_token_s=a - s, decode_s=b - a))
    return rows


def fit(rows):
    """Least squares on the two terms, with no library beyond the standard one.

    first_token ~ a0 + a1 * uncached_tokens + a2 * overlap_ft
    decode      ~ b0 + b1 * overlap_decode

    Deliberately linear and tiny. The point of this gate is whether a model this simple transfers
    across policies, since a model that needs per-arm terms cannot price a policy that has not run.
    """
    def ols(xs, ys):
        n = len(ys)
        k = len(xs)
        A = [[sum(xs[i][t] * xs[j][t] for t in range(n)) for j in range(k)] for i in range(k)]
        c = [sum(xs[i][t] * ys[t] for t in range(n)) for i in range(k)]
        for i in range(k):                               # Gauss-Jordan, k is 2 or 3
            p = max(range(i, k), key=lambda z: abs(A[z][i]))
            A[i], A[p] = A[p], A[i]
            c[i], c[p] = c[p], c[i]
            if abs(A[i][i]) < 1e-12:
                return [0.0] * k
            for j in range(i + 1, k):
                f = A[j][i] / A[i][i]
                for t in range(i, k):
                    A[j][t] -= f * A[i][t]
                c[j] -= f * c[i]
        out = [0.0] * k
        for i in reversed(range(k)):
            out[i] = (c[i] - sum(A[i][j] * out[j] for j in range(i + 1, k))) / A[i][i]
        return out
    one = [1.0] * len(rows)
    ft = ols([one, [r["uncached_tokens"] for r in rows], [float(r["overlap_ft"]) for r in rows]],
             [r["first_token_s"] for r in rows])
    dec = ols([one, [float(r["overlap_decode"]) for r in rows]],
              [r["decode_s"] for r in rows])
    return dict(first_token=dict(intercept=ft[0], per_uncached_token=ft[1], per_overlap=ft[2]),
                decode=dict(intercept=dec[0], per_overlap=dec[1]))


def apply(m, r):
    f = m["first_token"]
    d = m["decode"]
    return (f["intercept"] + f["per_uncached_token"] * r["uncached_tokens"]
            + f["per_overlap"] * r["overlap_ft"],
            d["intercept"] + d["per_overlap"] * r["overlap_decode"])


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
            n=len(s),
            first_token=dict(
                predicted_p50=round(st.median(pf), 4), actual_p50=round(st.median(af), 4),
                ratio_p50=round(st.median(pf) / st.median(af), 4) if st.median(af) else None,
                mae=round(st.fmean(abs(p - a) for p, a in zip(pf, af)), 4)),
            decode=dict(
                predicted_p50=round(st.median(pd), 4), actual_p50=round(st.median(ad), 4),
                ratio_p50=round(st.median(pd) / st.median(ad), 4) if st.median(ad) else None,
                mae=round(st.fmean(abs(p - a) for p, a in zip(pd, ad)), 4)))
    return dict(split=name, by_cache_state=out)


def main():
    data = defaultdict(list)
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or "_n16_s" not in d.name or "_rerun" in d.name \
                or d.name.endswith("_postfix") or any(
                    s in d.name for s in ("REFUSED", "ABORTED", "SKIPPED", "STOPPED")):
            continue
        try:
            c = json.loads((d / "cell.json").read_text())
        except Exception:                                                      # noqa: BLE001
            continue
        if c.get("err") is not None or not c.get("run_valid") or c.get("seed") not in SEEDS:
            continue
        for r in features(d):
            r["arm"], r["seed"] = c["arm"], c["seed"]
            data[(c["arm"], c["seed"])].append(r)
    allrows = [r for v in data.values() for r in v]
    res = dict(
        label="POLICY v2 item 3: cost-model recalibration on committed live requests, with "
              "held-out checks by seed and by arm. CPU only; no live run.",
        at=datetime.now().isoformat(), n_requests=len(allrows),
        n_cells=len(data), arms=sorted({a for a, _ in data}),
        warm_requests=sum(1 for r in allrows if r["warm"]),
        splits=[])
    # ---- held out by seed
    tr = [r for r in allrows if r["seed"] in (0, 4)]
    te = [r for r in allrows if r["seed"] in (5, 6)]
    m = fit(tr)
    res["splits"].append(dict(name="by_seed", fit_on="seeds 0 and 4", test_on="seeds 5 and 6",
                              n_fit=len(tr), model=m,
                              held_out=check(m, te, "seeds 5 and 6"),
                              in_sample=check(m, tr, "seeds 0 and 4")))
    # ---- held out by arm: fit on the non-hybrids, predict the hybrids
    tr2 = [r for r in allrows if r["arm"] not in HYBRID]
    te2 = [r for r in allrows if r["arm"] in HYBRID]
    m2 = fit(tr2)
    res["splits"].append(dict(name="by_arm", fit_on="non-hybrid arms", test_on="the hybrids",
                              n_fit=len(tr2), model=m2,
                              held_out=check(m2, te2, "the hybrids"),
                              in_sample=check(m2, tr2, "non-hybrid arms")))
    res["_provenance"] = _provenance.stamp(script="cost_model_gate.py", model="none",
                                           device="cpu", n=len(allrows), args=None)
    OUT.write_text(json.dumps(res, indent=1))
    print(f"{len(allrows):,} requests over {len(data)} cells, {res['warm_requests']} warm")
    for sp in res["splits"]:
        print(f"\n--- held out {sp['name']}: fit on {sp['fit_on']}, test on {sp['test_on']} ---")
        print("    first_token = %.4f + %.3e * uncached + %.4f * overlap" % (
            sp["model"]["first_token"]["intercept"],
            sp["model"]["first_token"]["per_uncached_token"],
            sp["model"]["first_token"]["per_overlap"]))
        print("    decode      = %.4f + %.4f * overlap" % (
            sp["model"]["decode"]["intercept"], sp["model"]["decode"]["per_overlap"]))
        for where in ("in_sample", "held_out"):
            for state, v in sp[where]["by_cache_state"].items():
                print(f"    {where:10s} {state:5s} n {v['n']:6d} | first token pred/act "
                      f"{v['first_token']['predicted_p50']:.3f}/"
                      f"{v['first_token']['actual_p50']:.3f} ratio "
                      f"{v['first_token']['ratio_p50']} | decode "
                      f"{v['decode']['predicted_p50']:.3f}/{v['decode']['actual_p50']:.3f} "
                      f"ratio {v['decode']['ratio_p50']}")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
