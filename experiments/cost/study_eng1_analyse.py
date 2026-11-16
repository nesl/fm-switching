#!/usr/bin/env python3
"""StudyENG1-steptime analysis (CPU only). Reads results/cost/study_eng1/eng1[_smoke]_*; writes eng1[_smoke]_results.json
and eng1_step_model.json (full run only). HOLDOUT trials of Part C are only counted and checked against the split file,
never analysed: this script drops them before any Part C statistic.

Step durations: under vLLM 0.31.0's default async scheduling the iteration-details elapsed_ms is the residual wait for
the step's GPU result, not the step duration (smoke check, report section 3.2). The step duration used here is the
interval between consecutive engine output batches received by the API server while the engine stays busy (the
previous batch left running or waiting requests), and, for a step that starts after idle and holds exactly one
request's whole prefill, that request's engine prefill time (scheduled -> first token) from the plugin.
"""
import argparse
import gzip
import json
import statistics as stt
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/cost/study_eng1"
D7 = {1: (0.134, "StudyD7b 32B-I N=1 closed-loop concurrency 1 TTFT p50 (caches off)"),
      3: (0.264, "StudyD7 32B-I N=3 concurrency 1 TTFT p50 (caches off)")}
GATE = {"mono11k": (2.7004, "StudySLICE1 Part A monolithic ~11k TTFT median (100 requests)"),
        "piece2048": (0.48585, "StudySLICE1 Part A n=2,048 chain slice TTFT median (non-final, ~11k sessions)")}
KNOTS = (512, 2048, 4096)
A_PART1_END = 1794784118.960808 + 0.5       # last kept A2 c0 request end (15:08:38) + 0.5 s


def rows(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in open(path)]


def steps(path):
    op = gzip.open if str(path).endswith(".gz") else open
    out = []
    for l in op(path, "rt"):
        r = json.loads(l)
        if "it" in r:
            out.append(r)
    return out


def med(x):
    x = [v for v in x if v is not None]
    return float(np.median(x)) if x else None


def q(x, p):
    x = [v for v in x if v is not None]
    return float(np.percentile(x, p)) if x else None


def boot_ratio(a, b, k, n=2000, seed=0):
    """CI of median(a) / (k x median(b))."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a), np.asarray(b)
    r = [np.median(rng.choice(a, len(a))) / (k * np.median(rng.choice(b, len(b)))) for _ in range(n)]
    return float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


# ------------------------------------------------------------------------------------------------ step durations
def step_durations(st):
    """Attach 'dur' (s) to steps that follow a busy step (interval between consecutive output batches)."""
    for i, s in enumerate(st):
        s["dur"] = None
        if i and (st[i - 1].get("run", 0) > 0 or st[i - 1].get("wait", 0) > 0):
            d = s["t"] - st[i - 1]["t"]
            if 0 < d < 10:
                s["dur"] = d
    return st


def first_step_from_pf(st):
    """Steps that start after idle and finish exactly one request's prefill: duration = that request's pf."""
    fin = {}
    for s in st:
        for f in s.get("fin", []):
            fin[f["id"]] = f
    return fin


# ------------------------------------------------------------------------------------------------ overhead gate
def overhead(pre):
    R = rows(OUT / f"{pre}_overhead_requests_h100nvl.jsonl")
    if not R:
        return None
    out = {}
    for k in (1, 8):
        d = {}
        for srv in ("plain", "instrumented"):
            x = [r for r in R if r["k"] == k and r["server"] == srv]
            bt = defaultdict(list)
            for r in x:
                bt[r["trial"]].append(r["ttft_s"])
            d[srv] = dict(per_request_median=med([r["ttft_s"] for r in x]),
                          batch_max_median=med([max(v) for v in bt.values()]),
                          batch_mean_median=med([float(np.mean(v)) for v in bt.values()]), n=len(x))
        out[f"k{k}"] = dict(d, ratio_per_request=d["instrumented"]["per_request_median"] / d["plain"]["per_request_median"],
                            ratio_batch_max=d["instrumented"]["batch_max_median"] / d["plain"]["batch_max_median"],
                            ratio_batch_mean=d["instrumented"]["batch_mean_median"] / d["plain"]["batch_mean_median"])
    return out


# ------------------------------------------------------------------------------------------------ Part A
def part_a(pre):
    R = rows(OUT / f"{pre}_partA_requests_h100nvl.jsonl")
    res = {}
    # A1 batches
    a1 = [r for r in R if r.get("sub") == "A1"]
    bt = defaultdict(list)
    for r in a1:
        bt[(r["N"], r["k"], r["trial"])].append(r)
    tab = {}
    for (n, k, t), v in bt.items():
        tab.setdefault((n, k), []).append(max(x["ttft_s"] for x in v if x["ttft_s"]))
    res["A1"] = {f"N{n}_k{k}": dict(batch_max_median=med(v), p10=q(v, 10), p90=q(v, 90), n=len(v),
                                     per_request_median=med([x["ttft_s"] for (nn, kk, _), w in bt.items()
                                                             if (nn, kk) == (n, k) for x in w]))
                 for (n, k), v in sorted(tab.items())}
    hs = {}
    for n in (1, 3):
        if (n, 16) in tab and (n, 1) in tab:
            r_ = med(tab[(n, 16)]) / (16 * med(tab[(n, 1)]))
            lo, hi = boot_ratio(tab[(n, 16)], tab[(n, 1)], 16)
            hs[f"N{n}"] = dict(ratio=r_, ci95=[lo, hi],
                               verdict="SUB-LINEAR" if r_ < 0.8 and hi < 0.8 else "LINEAR")
    res["H_step_batch"] = hs
    # cross-check vs D7 / D7b
    res["crosscheck"] = []
    for n in (1, 3):
        if (n, 1) in tab:
            v = med(tab[(n, 1)])
            res["crosscheck"].append(dict(quantity=f"N={n} single-request TTFT", this=v, prior=D7[n][0],
                                          source=D7[n][1], ratio=v / D7[n][0], flag=v / D7[n][0] > 1.25))
    # A2 pieces
    a2 = [r for r in R if r.get("sub") == "A2" and r["kind"] == "piece"]
    pc = defaultdict(list)
    for r in a2:
        if r.get("prefix_ok") and r["ttft_s"]:
            pc[(r["c_lbl"], r["s_tok"], r["j"])].append(r)
    res["A2"] = {f"{c}_s{s}_j{j}": dict(ttft_median=med([x["ttft_s"] for x in v]),
                                         computed_median=med([x["prompt_tokens"] - (x["cached_tokens"] or 0) for x in v]),
                                         n=len(v)) for (c, s, j), v in sorted(pc.items())}
    ep2 = defaultdict(list)
    for r in R:
        if r.get("sub") == "A2" and r["kind"] == "episodic" and r["ttft_s"]:
            ep2[(r["c_lbl"], r["s_tok"], r["j"])].append(r["ttft_s"])
    res["A2_episodic"] = {f"{c}_s{s}_j{j}": dict(ttft_median=med(v), ttft_max_median=None, n=len(v))
                          for (c, s, j), v in sorted(ep2.items())}
    res["A2_prefix_failures"] = sum(1 for r in a2 if r.get("prefix_ok") is False)
    # piece overhead vs monolithic control: piece(c, s) vs mono(c + s) - prefix build(c)
    mono = defaultdict(list)
    for r in R:
        if r.get("sub") == "A2mono" and r["ttft_s"]:
            mono[(r["c_lbl"], r["s_tok"])].append(r["ttft_s"])
    build = defaultdict(list)
    for r in R:
        if r.get("sub") == "A2" and r["kind"] == "build" and r["ttft_s"]:
            build[r["c_lbl"]].append(r["ttft_s"])
    ov = {}
    for (c, s), v in sorted(mono.items()):
        p = res["A2"].get(f"{c}_s{s}_j0")
        if p and build.get(c):
            ov[f"{c}_s{s}"] = dict(piece=p["ttft_median"], mono_cs=med(v), build_c=med(build[c]),
                                   extra_vs_marginal=p["ttft_median"] - (med(v) - med(build[c])),
                                   chain_over_mono=(med(build[c]) + p["ttft_median"]) / med(v))
    res["piece_overhead"] = ov
    # A3 residents
    a3 = defaultdict(list)
    for r in R:
        if r.get("sub") == "A3" and r["kind"] in ("append", "escalation") and r["ttft_s"]:
            a3[(r["c_lbl"], r["kind"], r["j"])].append(r["ttft_s"])
    res["A3"] = {f"{c}_{k}_j{j}": dict(ttft_median=med(v), n=len(v)) for (c, k, j), v in sorted(a3.items())}
    ep3 = defaultdict(list)
    for r in R:
        if r.get("sub") == "A3" and r["kind"] == "episodic" and r["ttft_s"]:
            ep3[(r["c_lbl"], r["resident"], r["j"])].append(r["ttft_s"])
    res["A3_episodic"] = {f"{c}_{k}_j{j}": dict(ttft_median=med(v), n=len(v)) for (c, k, j), v in sorted(ep3.items())}
    # elapsed_ms check (lone requests)
    lone = [r for r in R if r.get("sub") in ("lone_ep", "lone_piece8192")]
    res["lone"] = [dict(sub=r["sub"], ttft=r["ttft_s"], prompt=r["prompt_tokens"]) for r in lone]
    cold = [r for r in R if r["kind"] in ("build", "mono") or r.get("sub") == "A1"]
    res["cold_violations"] = sum(1 for r in cold if (r["cached_tokens"] or 0) > 16)
    res["errors"] = sum(1 for r in R if r.get("error"))
    return res, R


def a_steps_table(pre, label, R):
    """Per-step rows of one server with the trial context attached (by time window). Each row also carries the
    encoder inputs / encoder tokens of the NEXT output batch: an output batch that immediately precedes a step with
    images is that step's admission step (multimodal preparation on the engine's critical path, amendment 2)."""
    p = OUT / f"{pre}_steps" / f"{label}.jsonl.gz"
    if not p.exists():
        return []
    st = steps(p)
    if label == "A_E0_part1":                 # kept part of the VOID load: steps up to the end of A2 c0 only
        st = [x for x in st if x["t"] <= A_PART1_END]
    st = step_durations(st)
    win = []
    for r in R:
        if r["kind"] in ("piece", "append", "escalation", "mono11k", "piece2048", "piece1024") and r.get("t_first"):
            win.append((r["t_submit"], r["t_end"] + 0.005, r["cached_tokens"] or 0))
    win.sort()
    import bisect
    starts = [w[0] for w in win]
    out = []
    for i, s in enumerate(st):
        it = s["it"]
        if it[8] or it[1] + it[3] == 0:
            continue
        nx = st[i + 1]["it"] if i + 1 < len(st) else None
        k = bisect.bisect_right(starts, s["t"]) - 1
        c = 0
        while k >= 0 and win[k][0] > s["t"] - 30:
            if win[k][0] <= s["t"] <= win[k][1]:
                c = max(c, win[k][2])
            k -= 1
        out.append(dict(server=label, t=s["t"], ctx_reqs=it[1], ctx_tok=it[2], gen_reqs=it[3], enc_in=it[6],
                        enc_tok=it[7], elapsed_ms=it[5], dur=s["dur"], ctx_attended=c,
                        adm_img=(nx[6] if nx else 0), adm_enc_tok=(nx[7] if nx else 0)))
    return out


STEP_NAMES = ["intercept_ms", "per_tok_ms"] + [f"per_tok_above_{k}_ms" for k in KNOTS] + \
    ["per_encoder_input_ms", "per_decode_req_ms", "per_prefill_req_ms", "per_tok_x_ctx_per_1e6_ms",
     "admission_per_image_ms", "admission_per_1k_encoder_tokens_ms"]


def step_features(s):
    tok = s["ctx_tok"]
    return [1.0, tok] + [max(0.0, tok - k) for k in KNOTS] + [s["enc_in"], s["gen_reqs"], s["ctx_reqs"],
                                                              tok * s["ctx_attended"] / 1e6, s["adm_img"],
                                                              s["adm_enc_tok"] / 1000]


def fit_steps(tab):
    """Step-time model (non-learned, piecewise-linear), fitted by least squares on busy-interval step durations:
    ms = intercept + per_tok*tok + sum_k per_tok_above_k*max(0, tok - k) + per_encoder_input*images_in_step
       + per_decode_req*decode_reqs + per_prefill_req*prefill_reqs + per_tok_x_ctx*tok*ctx/1e6
       + admission_per_image*images_of_next_step + admission_per_1k_encoder_tokens*encoder_tokens_of_next_step/1e3
    The last two terms are the admission step (the next step's multimodal preparation stalls this step's output);
    they are reported as their own term, separate from prefill compute and from front-end serialization."""
    use = [s for s in tab if s["dur"] is not None]
    if len(use) < 20:
        return None
    X = np.asarray([step_features(s) for s in use])
    y = np.asarray([s["dur"] * 1000 for s in use])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    bands = {}
    for lo, hi in ((0, 1), (1, 512), (512, 2048), (2048, 4096), (4096, 8193)):
        m = (X[:, 1] >= lo) & (X[:, 1] < hi)
        if m.any():
            bands[f"tok_{lo}_{hi}"] = dict(n=int(m.sum()), median_abs_res_ms=float(np.median(np.abs(res[m]))),
                                          p90_abs_res_ms=float(np.percentile(np.abs(res[m]), 90)),
                                          median_rel_res=float(np.median(np.abs(res[m]) / np.maximum(y[m], 1))))
    adm = X[:, 9] > 0
    bands["admission_steps"] = dict(n=int(adm.sum()), median_abs_res_ms=float(np.median(np.abs(res[adm])))
                                    if adm.any() else None)
    by_server = {}
    for sv in sorted({s["server"] for s in use}):
        m = np.asarray([s["server"] == sv for s in use])
        by_server[sv] = dict(n=int(m.sum()), median_abs_res_ms=float(np.median(np.abs(res[m]))))
    return dict(form=fit_steps.__doc__.split("\n    The last")[0].strip(), knots=KNOTS,
                coef=dict(zip(STEP_NAMES, map(float, coef))), n=int(len(y)), r2=float(1 - res.var() / y.var()),
                residual_bands=bands, residual_by_server=by_server)


def admission_model(tab):
    """Admission stall on its own: for output batches that are decode-only and precede a step with images, the excess
    over the median decode-only interval at the same number of decode requests (steps not preceding images)."""
    base = defaultdict(list)
    for s in tab:
        if s["dur"] is not None and s["ctx_tok"] == 0 and s["adm_img"] == 0:
            base[s["gen_reqs"]].append(s["dur"])
    bm = {k: med(v) for k, v in base.items()}
    pts = [(s["adm_img"], s["adm_enc_tok"], s["dur"] - bm[s["gen_reqs"]]) for s in tab
           if s["dur"] is not None and s["ctx_tok"] == 0 and s["adm_img"] > 0 and s["gen_reqs"] in bm]
    if len(pts) < 10:
        return dict(n=len(pts))
    X = np.asarray([[1.0, a] for a, _, _ in pts])
    y = np.asarray([z * 1000 for _, _, z in pts])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    bins = defaultdict(list)
    for a, _, z in pts:
        bins[1 if a == 1 else (2 if a <= 4 else (5 if a <= 15 else (16 if a <= 40 else 41)))].append(z * 1000)
    return dict(n=len(pts), form="stall_ms = a + b * images admitted in the next step (decode-only admission steps)",
                a_ms=float(coef[0]), b_ms_per_image=float(coef[1]), median_abs_res_ms=float(np.median(np.abs(res))),
                by_image_bin={f">={k}": dict(n=len(v), median_ms=med(v)) for k, v in sorted(bins.items())},
                decode_baseline_ms={k: v * 1000 for k, v in sorted(bm.items()) if k <= 16},
                effect_on_running="every request decoding during an admission step waits the stall: its inter-token "
                                  "gap grows by the stall (the step's output is delayed for all running requests)")


# ------------------------------------------------------------------------------------------------ Part B
def part_b(pre, meta):
    R = rows(OUT / f"{pre}_partB_requests_h100nvl.jsonl")
    out = {}
    for eng in ("E0", "T1"):
        ref = (meta.get("partB_ref") or {}).get(eng)
        if not ref:
            continue
        cells = defaultdict(list)
        for r in R:
            if r.get("sub") == "inject" and r.get("engine") == eng and r["kind"] == "episodic" and r["ttft_s"]:
                cells[(r["long"], r["offset"])].append(r)
        steps_ = {}
        for L, D_L in ref["D_L"].items():
            steps_[L] = D_L if L != "mono11k" else D_L / 2            # placeholder, replaced by step data below
        tab = {}
        for (L, off), v in sorted(cells.items()):
            D_L = ref["D_L"][L]
            R_ = D_L * (1 - off)
            waits = [x["ttft_s"] - ref["solo_ep"] for x in v]
            rhos = [w / R_ for w in waits]
            rm = med(rhos)
            wm = med(waits)
            one_step = ONE_STEP.get((eng, L))
            reg = "a" if rm >= 0.8 else ("b" if rm <= 0.2 or (one_step and wm <= one_step) else "c")
            tab[f"{L}_off{int(off * 100)}"] = dict(n=len(v), ttft_median=med([x["ttft_s"] for x in v]),
                                                   wait_median=wm, R=R_, rho_median=rm, rho_p10=q(rhos, 10),
                                                   rho_p90=q(rhos, 90), one_step_s=one_step, regime=reg)
        out[eng] = dict(ref=ref, cells=tab)
    return out


ONE_STEP = {}


# ------------------------------------------------------------------------------------------------ Part C
def part_c(pre, split):
    R = rows(OUT / f"{pre}_partC_requests_h100nvl.jsonl")
    hold_rows = [r for r in R if r.get("holdout")]
    fit = [r for r in R if not r.get("holdout")]
    # HOLDOUT verification only
    recorded = sorted({(r["load"], r["action"], r["trial"]) for r in hold_rows if r.get("load")})
    bad = [x for x in recorded if x[2] not in split["holdout"].get(f"{x[0]}|{x[1]}", [])]
    hv = dict(holdout_triples_recorded=len(recorded), not_in_split=bad,
              holdout_rows=len(hold_rows), note="HOLDOUT rows counted and checked against the split only")
    runs = defaultdict(dict)
    for r in fit:
        if r.get("kind") == "episodic":
            runs[(r["load"], r["action"], r["trial"], r["mode"])][r["idx"]] = r
    inj = defaultdict(list)
    for r in fit:
        if r.get("kind") == "inject":
            inj[(r["load"], r["action"], r["trial"])].append(r)
    cells = defaultdict(list)
    noise = defaultdict(list)
    per_req = []
    for (ld, a, t, m), w in runs.items():
        if m != "with":
            continue
        wo = runs.get((ld, a, t, "without"))
        if not wo:
            continue
        ti = inj[(ld, a, t)][0]["t_sched"] - inj[(ld, a, t)][0]["t0_trace"] if inj[(ld, a, t)] else None
        ds = []
        for i, r in w.items():
            o = wo.get(i)
            if o and r["ttft_s"] and o["ttft_s"]:
                d = r["ttft_s"] - o["ttft_s"]
                ds.append(d)
                per_req.append(dict(load=ld, action=a, trial=t, idx=i, arrival=r["arrival_rel"],
                                    rel=r["arrival_rel"] - ti if ti is not None else None, delta=d))
        cells[(ld, a)].append(dict(trial=t, total=sum(ds), max=max(ds) if ds else None,
                                   n_hit=sum(x > 0.05 for x in ds), n=len(ds),
                                   inj_ttft=med([x["ttft_s"] for x in inj[(ld, a, t)]])))
        rp = runs.get((ld, a, t, "repeat"))
        if rp:
            dn = [rp[i]["ttft_s"] - o["ttft_s"] for i, o in wo.items() if i in rp and rp[i]["ttft_s"] and o["ttft_s"]]
            noise[(ld, a)].append(dict(trial=t, total=sum(dn), median_abs=med([abs(x) for x in dn]),
                                       p90_abs=q([abs(x) for x in dn], 90), max_abs=max(abs(x) for x in dn)))
    tab = {}
    for (ld, a), v in sorted(cells.items()):
        tot = [x["total"] for x in v]
        nz = noise.get((ld, a), [])
        tab[f"{ld}|{a}"] = dict(n_pairs=len(v), total_median=med(tot), total_p10=q(tot, 10), total_p90=q(tot, 90),
                                max_delta_median=med([x["max"] for x in v]), n_hit_median=med([x["n_hit"] for x in v]),
                                inj_ttft_median=med([x["inj_ttft"] for x in v]),
                                noise_total_abs_median=med([abs(x["total"]) for x in nz]),
                                noise_req_median_abs=med([x["median_abs"] for x in nz]),
                                noise_req_p90_abs=med([x["p90_abs"] for x in nz]), noise_n=len(nz),
                                noise_flag=bool(nz) and med([abs(x["total"]) for x in nz]) > 0.5 * max(1e-9, abs(med(tot) or 0)))
    pc = [r for r in R if r.get("kind") == "pair_check"]
    return dict(holdout=hv, cells=tab, pair_checks=dict(pairs=len(pc), mismatches=sum(x["mismatches"] for x in pc),
                                                        compared=sum(x["n"] for x in pc),
                                                        warm_unequal=sum(1 for x in pc if x.get("warm_cached_equal") is False))), per_req


# ------------------------------------------------------------------------------------------------ Part D
def part_d(pre):
    R = [r for r in rows(OUT / f"{pre}_partD_requests_h100nvl.jsonl") if r["kind"] == "query"]
    out = {}
    for conc in (1, 4):
        v = [r for r in R if r["conc"] == conc]
        cm = Counter((r["state"], r["inferred"]) for r in v)
        acc = sum(cm[(s, s)] for s in ("gpu", "host", "cold")) / max(1, len(v))
        cached = defaultdict(list)
        for r in v:
            cached[r["state"]].append((r["cached_tokens"] or 0) / max(1, r["prompt_tokens"] or 1))
        out[f"conc{conc}"] = dict(n=len(v), accuracy=acc,
                                  confusion={f"{a}->{b}": n for (a, b), n in sorted(cm.items())},
                                  cached_fraction_median={k: med(x) for k, x in cached.items()},
                                  ttft_median={s: med([r["ttft_s"] for r in v if r["state"] == s])
                                               for s in ("gpu", "host", "cold")})
    keys = Counter(k for r in R for k in r.get("metrics_delta", {}))
    out["signals_seen"] = sorted(keys)
    if "conc1" in out and "conc4" in out:
        a1, a4 = out["conc1"]["accuracy"], out["conc4"]["accuracy"]
        out["H_tier"] = dict(unambiguous_conc1=a1 >= 0.95, degrades_conc4=(a1 - a4) > 0.10, acc1=a1, acc4=a4)
    return out


# ------------------------------------------------------------------------------------------------ gate re-run (1b)
TIER_GAP = 0.04


def tiers(batch):
    """Admission tiers of one batch: requests sorted by first-token time; a new tier starts after a gap > 40 ms."""
    b = sorted(batch, key=lambda r: r["t_first"])
    tier, out, prev = 1, [], None
    for r in b:
        if prev is not None and r["t_first"] - prev > TIER_GAP:
            tier += 1
        out.append((tier, r))
        prev = r["t_first"]
    return out


def fisher_two_sided(a, n1, b, n2):
    """Fisher exact test (two-sided) on a/n1 vs b/n2 successes."""
    from math import comb
    K, N = a + b, n1 + n2

    def p(x):
        return comb(n1, x) * comb(n2, K - x) / comb(N, K)
    p0 = p(a)
    return float(min(1.0, sum(p(x) for x in range(max(0, K - n2), min(K, n1) + 1) if p(x) <= p0 + 1e-12)))


def gate_isolation(pre="eng1_gate"):
    """Component isolation (amendment 2): per server the 1/7 split rate (Fisher vs plain), tier-1 time, batch ratios."""
    R = [r for r in rows(OUT / f"{pre}_overhead_requests_h100nvl.jsonl") if r["k"] == 8 and r["t_first"]]
    out = {}
    for srv in ("plain", "instrumented", "plugin_only", "plugin_only_r2", "iter_only"):
        x = [r for r in R if r["server"] == srv]
        if not x:
            continue
        bt = defaultdict(list)
        for r in x:
            bt[r["trial"]].append(r)
        n17, t1 = 0, []
        for v in bt.values():
            tv = tiers(v)
            sizes = Counter(t for t, _ in tv)
            if [sizes[i] for i in sorted(sizes)] == [1, 7]:
                n17 += 1
            t1 += [r["ttft_s"] for t, r in tv if t == 1]
        out[srv] = dict(batches=len(bt), split_1_7=n17, tier1_median=med(t1),
                        batch_max_median=med([max(r["ttft_s"] for r in v) for v in bt.values()]),
                        batch_mean_median=med([float(np.mean([r["ttft_s"] for r in v])) for v in bt.values()]))
    pl = out["plain"]
    for srv, d in out.items():
        d["fisher_p_vs_plain"] = fisher_two_sided(d["split_1_7"], d["batches"], pl["split_1_7"], pl["batches"])
        d["tier1_ratio"] = d["tier1_median"] / pl["tier1_median"]
        d["batch_max_ratio"] = d["batch_max_median"] / pl["batch_max_median"]
        d["batch_mean_ratio"] = d["batch_mean_median"] / pl["batch_mean_median"]
        d["shows_effect"] = d["split_1_7"] >= 4 or d["tier1_ratio"] > 1.02
    prim = "plugin_only_r2" if "plugin_only_r2" in out else "plugin_only"      # clean repeat is primary
    eff = {k: out[k]["shows_effect"] for k in (prim, "iter_only") if k in out}
    eff = {("plugin_only" if k == prim else k): v for k, v in eff.items()}
    if len(eff) == 2:
        if all(eff.values()):
            dec = "BOTH components show the effect: STOP AND ASK"
        elif eff["plugin_only"]:
            dec = "drop the plugin, keep the iteration-details flag"
        elif eff["iter_only"]:
            dec = "drop the iteration-details flag, keep the plugin"
        else:
            dec = "neither component alone shows the effect: accept the full instrumentation"
    else:
        dec = None
    return dict(servers=out, decision=dec)


def gate(pre="eng1_gate"):
    R = rows(OUT / f"{pre}_overhead_requests_h100nvl.jsonl")
    if not R:
        return None
    res = {}
    for k in (1, 8):
        d = {}
        for srv in ("plain", "instrumented"):
            x = [r for r in R if r["k"] == k and r["server"] == srv and r["t_first"]]
            bt = defaultdict(list)
            for r in x:
                bt[r["trial"]].append(r)
            tier_tt = defaultdict(list)
            split = Counter()
            for v in bt.values():
                tv = tiers(v)
                split[tuple(Counter(t for t, _ in tv)[i] for i in sorted(set(t for t, _ in tv)))] += 1
                for t, r in tv:
                    tier_tt[t].append(r["ttft_s"])
            d[srv] = dict(n=len(x), batches=len(bt), pooled_median=med([r["ttft_s"] for r in x]),
                          batch_max_median=med([max(r["ttft_s"] for r in v) for v in bt.values()]),
                          batch_mean_median=med([float(np.mean([r["ttft_s"] for r in v])) for v in bt.values()]),
                          tier_median={t: med(v) for t, v in sorted(tier_tt.items())},
                          tier_n={t: len(v) for t, v in sorted(tier_tt.items())},
                          tier_splits={"/".join(map(str, kk)): n for kk, n in split.most_common()})
        pl, ins = d["plain"], d["instrumented"]
        rr = dict(pooled=ins["pooled_median"] / pl["pooled_median"],
                  batch_max=ins["batch_max_median"] / pl["batch_max_median"],
                  batch_mean=ins["batch_mean_median"] / pl["batch_mean_median"],
                  tiers={t: ins["tier_median"][t] / pl["tier_median"][t] for t in pl["tier_median"]
                         if t in ins["tier_median"]})
        if k == 1:
            ok = rr["pooled"] <= 1.03
        else:
            ok = rr["batch_max"] <= 1.03 and rr["batch_mean"] <= 1.03 and all(v <= 1.03 for v in rr["tiers"].values())
        res[f"k{k}"] = dict(d, ratios=rr, passes=ok)
    res["gate_passes"] = all(res[f"k{k}"]["passes"] for k in (1, 8))
    return res


def validate(pre="eng1_gate", label="GATE_E0"):
    """Interval-method step duration vs the engine's per-request prefill time (test requests behind a decode pacer)."""
    R = [r for r in rows(OUT / f"{pre}_validate_requests_h100nvl.jsonl") if r["kind"] == "test"]
    p = OUT / f"{pre}_steps" / f"{label}.jsonl.gz"
    if not R or not p.exists():
        return None
    allst = []
    op = gzip.open
    for l in op(p, "rt"):
        allst.append(json.loads(l))
    fin = {}
    for s in allst:
        for f in s.get("fin", []):
            fin[f["id"]] = f
    st = step_durations([s for s in allst if "it" in s])
    out = []
    for r in R:
        f = fin.get("chatcmpl-" + r["rid"])
        if not f or not r["t_first"]:
            continue
        idx = [i for i, s in enumerate(st) if r["t_submit"] <= s["t"] <= r["t_first"] + 0.01 and s["it"][2] > 0]
        ss = [st[i] for i in idx]
        # implementation fix (user decision 2, 2026-11-15): include the admission step, i.e. the output batch
        # immediately preceding the first prefill step (multimodal input preparation on the engine's critical path)
        adm = st[idx[0] - 1] if idx and idx[0] >= 1 else None
        ok = bool(ss) and adm is not None and all(s["dur"] is not None for s in ss + [adm])
        tot = sum(s["dur"] for s in ss + [adm]) if ok else None
        adm_s = adm["dur"] if ok else None
        out.append(dict(test=r["test"], prompt=r["prompt_tokens"], engine_prefill_s=f["pf"], engine_queue_s=f["q"],
                        steps=len(ss), interval_sum_s=tot, elapsed_sum_s=sum(s["it"][5] for s in ss) / 1000,
                        ratio=tot / f["pf"] if tot else None, client_ttft=r["ttft_s"], admission_step_s=adm_s,
                        images=r["prompt_tokens"] and (1 if r["test"] == "ep1" else int(r["test"][5:]))))
    summ = {}
    for k in sorted({x["test"] for x in out}):
        v = [x for x in out if x["test"] == k and x["ratio"]]
        summ[k] = dict(n=len(v), ratio_median=med([x["ratio"] for x in v]), ratio_min=min(x["ratio"] for x in v),
                       ratio_max=max(x["ratio"] for x in v), engine_prefill_median=med([x["engine_prefill_s"] for x in v]),
                       interval_sum_median=med([x["interval_sum_s"] for x in v]),
                       elapsed_over_prefill_median=med([x["elapsed_sum_s"] / x["engine_prefill_s"] for x in v]),
                       steps=sorted({x["steps"] for x in v}))
    within = all(abs(v["ratio_median"] - 1) <= 0.05 for v in summ.values()) if summ else None
    return dict(per_kind=summ, within_5pct=within, rows=out)


# ------------------------------------------------------------------------------------------------ front-end serialization
def frontend(pre, req_rows, fin_by_id):
    """Front-end time per request = 'Added' (handed to the engine core) - client submit; split into 'Received' -
    submit and Added - Received. Serial model: each request's front-end service starts at max(submit, previous
    request's Added) and lasts s(images, MB); s fitted on requests that found the front end idle."""
    fe = {r["rid"]: r for r in rows(OUT / f"{pre}_frontend_requests_h100nvl.jsonl")}
    xs = []
    for r in req_rows:
        f = fe.get(r.get("rid"))
        if not f or "added_t" not in f or not r.get("t_submit"):
            continue
        n_img = r.get("n_images")
        xs.append(dict(rid=r["rid"], kind=r["kind"], t_submit=r["t_submit"], received=f.get("received_t"),
                       added=f["added_t"], mb=r.get("body_mb"), n_img=n_img, server=f["server"],
                       admit=(f["added_t"] + fin_by_id["chatcmpl-" + r["rid"]]["q"])
                       if ("chatcmpl-" + r["rid"]) in fin_by_id else None))
    if not xs:
        return None
    xs.sort(key=lambda x: (x["server"], x["added"]))
    idle = []
    prev_added = {}
    for x in xs:
        pa = prev_added.get(x["server"])
        x["fe_s"] = x["added"] - x["t_submit"]
        x["idle_start"] = pa is None or pa <= x["t_submit"]
        prev_added[x["server"]] = x["added"]
        if x["idle_start"] and x["mb"] is not None:
            idle.append(x)
    if len(idle) < 10:
        return dict(n=len(xs), n_idle=len(idle))
    X = np.asarray([[1.0, x["mb"]] for x in idle])
    y = np.asarray([x["fe_s"] for x in idle])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ coef
    # serial-model check on requests that found the front end busy
    busy = [x for x in xs if not x["idle_start"] and x["mb"] is not None]
    pred_err = []
    last_end = {}
    for x in xs:
        if x["mb"] is None:
            continue
        s_ = coef[0] + coef[1] * x["mb"]
        start = max(x["t_submit"], last_end.get(x["server"], 0.0))
        pe = start + s_
        last_end[x["server"]] = x["added"]          # condition on the observed previous end (one-step-ahead)
        if not x["idle_start"]:
            pred_err.append(pe - x["added"])
    by_kind = defaultdict(list)
    for x in idle:
        by_kind[x["kind"]].append(x["fe_s"])
    # busy service: time from max(submit, previous request's Added) to this request's Added
    prev = {}
    bx, by = [], []
    for x in xs:
        pa = prev.get(x["server"])
        if pa is not None and pa > x["t_submit"] and x["mb"] is not None:
            bx.append([1.0, x["mb"]])
            by.append(x["added"] - pa)
        prev[x["server"]] = x["added"]
    bfit = None
    if len(by) >= 10:
        bc, *_ = np.linalg.lstsq(np.asarray(bx), np.asarray(by), rcond=None)
        br = np.asarray(by) - np.asarray(bx) @ bc
        bfit = dict(form="busy service = a + b * body_MB, from the previous request's Added to this one's Added",
                    a_s=float(bc[0]), b_s_per_MB=float(bc[1]), n=len(by),
                    median_abs_res_s=float(np.median(np.abs(br))), p90_abs_res_s=float(np.percentile(np.abs(br), 90)))
    adm = [x["admit"] - x["added"] for x in xs if x["admit"] is not None]
    return dict(n=len(xs), n_idle=len(idle), n_busy=len(busy),
                fit=dict(form="front-end service s = a + b * body_MB (requests that found the front end idle)",
                         a_s=float(coef[0]), b_s_per_MB=float(coef[1]),
                         median_abs_res_s=float(np.median(np.abs(res))), p90_abs_res_s=float(np.percentile(np.abs(res), 90))),
                serial_check=dict(n=len(pred_err), median_err_s=med(pred_err),
                                  median_abs_err_s=med([abs(e) for e in pred_err]),
                                  p90_abs_err_s=q([abs(e) for e in pred_err], 90)),
                idle_fe_median_by_kind={k: med(v) for k, v in by_kind.items()}, busy_fit=bfit,
                engine_queue_after_added=dict(n=len(adm), median_s=med(adm), p90_s=q(adm, 90)),
                received_share_median=med([(x["received"] - x["t_submit"]) / x["fe_s"] for x in idle
                                           if x["received"] and x["fe_s"] > 0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    if a.gate:
        g, v, iso = gate(), validate(), gate_isolation()
        (OUT / "eng1_gate_results.json").write_text(json.dumps(dict(gate=g, validate=v, isolation=iso), indent=1,
                                                               default=str))
        print(json.dumps(dict(gate_ratios={k: g[k]["ratios"] for k in ("k1", "k8")},
                              validate={k: v[k] for k in ("per_kind", "within_5pct")} if v else None,
                              isolation=iso), indent=1, default=str))
        return
    pre = "eng1_smoke" if a.smoke else "eng1"
    meta = json.loads((OUT / f"{pre}_run_meta_h100nvl.json").read_text())
    split = json.loads((OUT / "eng1_holdout_split.json").read_text())
    res = dict(overhead=overhead(pre))
    A, RA = part_a(pre)
    res["A"] = A
    labs = [("SMK_E0", RA)] if a.smoke else [("A_E0_part1", RA), ("A_E0", RA),
                                             ("B_E0", rows(OUT / f"{pre}_partB_requests_h100nvl.jsonl"))]
    tab = [x for lab, rr in labs for x in a_steps_table(pre, lab, rr)]
    res["steps_fit"] = dict(servers=[l for l, _ in labs], n=len(tab),
                            with_duration=sum(1 for s in tab if s["dur"] is not None))
    fit = fit_steps(tab)
    res["step_model"] = fit
    res["admission_model"] = admission_model(tab)
    # one step of each long request (Part B): median busy interval of steps carrying >= 1,024 prefill tokens
    for eng, lab_b in (("E0", "SMK_E0" if a.smoke else "B_E0"), ("T1", "B_T1")):
        p = OUT / f"{pre}_steps" / f"{lab_b}.jsonl.gz"
        if p.exists():
            st = step_durations(steps(p))
            big = [s["dur"] for s in st if s["dur"] and s["it"][2] >= 1024]
            for L in ("mono11k", "piece2048", "piece1024"):
                ONE_STEP[(eng, L)] = med(big)
    res["B"] = part_b(pre, meta)
    if not a.smoke:
        fin = {}
        for lab in ("A_E0_part1", "A_E0", "B_E0", "B_T1", "C_P25_E0", "C_P40_E0", "C_S2_E0", "C_S4_E0"):
            pth = OUT / f"{pre}_steps" / f"{lab}.jsonl.gz"
            if pth.exists():
                for l in gzip.open(pth, "rt"):
                    for f in json.loads(l).get("fin", []):
                        fin[f["id"]] = f
        req = rows(OUT / f"{pre}_partA_requests_h100nvl.jsonl") + rows(OUT / f"{pre}_partB_requests_h100nvl.jsonl") + \
            [r for r in rows(OUT / f"{pre}_partC_requests_h100nvl.jsonl") if not r.get("holdout")]
        res["frontend"] = frontend(pre, req, fin)
    C, per_req = part_c(pre, split)
    res["C"] = C
    res["D"] = part_d(pre)
    res["servers"] = [dict(label=s["label"], flags_verified=s.get("flags_verified"), plugin=s.get("plugin_loaded"),
                           extra=s.get("extra_flags"), unexpected=s.get("unexpected"), missing=s.get("missing"))
                      for s in meta.get("servers", [])]
    res["void"] = meta.get("void")
    res["remaining_at_guard"] = meta.get("remaining_at_guard")
    (OUT / f"{pre}_results.json").write_text(json.dumps(res, indent=1, default=str))
    if fit and not a.smoke:
        (OUT / "eng1_step_model.json").write_text(json.dumps(dict(fit, admission=res["admission_model"],
                                                                  fit_data="Part A (A_E0) and Part B E0 (B_E0) steps; "
                                                                  "Part C (incl. HOLDOUT) not used"), indent=1))
    print(json.dumps({k: res[k] for k in ("overhead",)}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()


# ------------------------------------------------------------------------------------------------ iteration-log extraction
def extract_iterlog():
    """Recover per-step rows from the servers' --enable-logging-iteration-details lines (ms timestamps, local time).
    Needed because the plugin wrote no rows on the KV-HOST servers (fixed in the plugin on 2026-11-16, after the
    full run). Written for every full-run server so the E0 servers give a plugin-vs-log cross-check."""
    import re
    import time as _t
    rx = re.compile(r"INFO (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d{3}) \[loggers\.py:\d+\] Engine \d+: Iteration\((\d+)\): "
                    r"(\d+) context requests, (\d+) context tokens, (\d+) generation requests, (\d+) generation tokens, "
                    r"iteration elapsed time: ([\d.]+) ms(?: \(dummy\))?, GPU KV cache usage: ([\d.]+)%"
                    r"(?:, encoder inputs: (\d+), encoder output embeddings: (\d+))?")
    metas = [json.loads((OUT / "eng1_run_meta_h100nvl.json").read_text()),
             json.loads((OUT / "eng1_void1_run_meta_h100nvl.json").read_text())]
    servers = {}
    for m in metas:
        for s in m.get("servers", []):
            lab = "A_E0_part1" if (s["label"] == "A_E0" and m is metas[1]) else s["label"]
            servers[lab] = s["log"]
    out = {}
    for lab, log in servers.items():
        rows = []
        for line in open(REPO / log, errors="replace"):
            if "Iteration(" not in line:
                continue
            g = rx.search(line)
            if not g:
                continue
            t = _t.mktime(_t.strptime(g.group(1), "%Y-%m-%d %H:%M:%S")) + int(g.group(2)) / 1000
            rows.append(dict(t=round(t, 3), it=[int(g.group(3)), int(g.group(4)), int(g.group(5)), int(g.group(6)),
                                                int(g.group(7)), float(g.group(8)), int(g.group(10) or 0),
                                                int(g.group(11) or 0), 0], kv=float(g.group(9)) / 100))
        p = OUT / "eng1_steps" / f"{lab}_iterlog.jsonl.gz"
        with gzip.open(p, "wt") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        out[lab] = len(rows)
    return out
