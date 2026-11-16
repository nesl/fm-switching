#!/usr/bin/env python3
"""StudyENG1b-prefix-survival analysis (CPU only). Reads results/cost/study_eng1b/eng1b[_smoke]_*; writes
eng1b[_smoke]_results.json.

Per trial: the resume piece's prefix tokens are split into LOCAL hit, EXTERNAL (host) hit and recomputed, from the
plugin step row of the resume piece's first-token step (prompt tokens by source; exact when no other request with
prefix hits produced its first token in the same step, else flagged AMBIGUOUS), cross-checked with the Prometheus
counter deltas over the resume window and with the API's cached tokens. Pressure = KV allocated by other work during
the gap = context tokens scheduled between the gap start and the resume issue (step rows) minus the resume piece's
own (none before issue); also reported against the pre-registered fill level and the filler tokens completed.
"""
import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/cost/study_eng1b"
FULL_TOL = 32           # prefix counted fully resident if local hits >= prefix - 32 (block / template tolerance)


def rows(p):
    return [json.loads(l) for l in open(p)] if p.exists() else []


def med(x):
    x = [v for v in x if v is not None]
    return float(np.median(x)) if x else None


def q(x, p):
    x = [v for v in x if v is not None]
    return float(np.percentile(x, p)) if x else None


def wilson(k, n, z=1.96):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (c - h) / d, (c + h) / d


def load_steps(pre, label):
    p = OUT / f"{pre}_steps" / f"{label}.jsonl.gz"
    if not p.exists():
        return []
    return [json.loads(l) for l in gzip.open(p, "rt")]


def attribute(trial, res, st):
    """Split the resume piece's prompt into computed / local / external from its first-token step row."""
    tf = res.get("t_first")
    if not tf:
        return None
    cand = [s for s in st if "pts" in s and tf - 0.5 <= s["t"] <= tf + 0.01 and s["pts"][4] >= (res["prompt_tokens"] or 0)]
    if not cand:
        return dict(source="none")
    s = min(cand, key=lambda x: abs(x["t"] - tf))
    comp, loc, ext, cached, total = s["pts"]
    i = st.index(s)
    t_adm = st[i - 1]["t"] if i >= 1 else None        # end of the step before the resume's prefill step (admission)
    others = total - (res["prompt_tokens"] or 0)
    amb = others > 0 and (loc + ext) > (res["cached_tokens"] or 0)
    return dict(source="step", local=loc, external=ext, computed=comp, step_total=total, others_tokens=others,
                ambiguous=bool(amb), dt_ms=round((s["t"] - tf) * 1000, 1), t_admission=t_adm)


def allocated_before(st, t0, t1):
    """Context (prefill) tokens scheduled by all requests between t0 and t1 (step rows), i.e. new KV allocated."""
    return sum(s["it"][2] for s in st if "it" in s and t0 < s["t"] <= t1)


def analyse(pre):
    T = [t for t in rows(OUT / f"{pre}_trials_h100nvl.jsonl") if t.get("resume_rid")]
    R = {r["rid"]: r for r in rows(OUT / f"{pre}_requests_h100nvl.jsonl") if r.get("kind") == "resume"}
    meta = json.loads((OUT / f"{pre}_run_meta_h100nvl.json").read_text())
    steps_by = {}
    out = []
    for t in T:
        res = R.get(t["resume_rid"])
        if not res:
            continue
        lab = ("SMK_E0" if t["server"] == "E0" else "SMK_KVHOST") if pre.endswith("smoke") else \
            f"{'E0' if t['server'] == 'E0' else 'KVHOST'}_{t['size']}"
        if lab not in steps_by:
            steps_by[lab] = load_steps(pre, lab)
        st = steps_by[lab]
        a = attribute(t, res, st)
        P = t["prefix_tokens"]
        d = t.get("resume_window_delta") or {}
        cloc = d.get("prompt_tokens_by_source_total|local_cache_hit", 0.0)
        cext = d.get("prompt_tokens_by_source_total|external_kv_transfer", 0.0)
        loc = a["local"] if a and a.get("source") == "step" else None
        ext = a["external"] if a and a.get("source") == "step" else None
        if loc is None:                   # fall back to the counter deltas (flagged)
            loc, ext = cloc, cext
        cached = res["cached_tokens"] or 0
        rec = max(0, P - min(P, loc + ext))
        alloc = allocated_before(st, t["t_gap_start"], t["t_resume_issue"]) if t.get("t_gap_start") else None
        t_adm = (a or {}).get("t_admission")
        alloc_s = allocated_before(st, t["t_gap_start"], t_adm) if (t.get("t_gap_start") and t_adm) else None
        free = (t["kv_capacity_tokens"] or 0) - P
        out.append(dict(server=t["server"], size=t["size"], load=t["load"], gap=t["gap"], rep=t["rep"], tag=t["tag"],
                        prefix=P, local=loc, external=ext, recomputed=rec, cached=cached,
                        full_resident=loc >= P - FULL_TOL, lost_tokens=max(0, P - loc),
                        attribution=(a or {}).get("source", "none") if (a and a.get("source") == "step") else "counters",
                        ambiguous=bool(a and a.get("ambiguous")),
                        counters_agree=abs((cloc + cext) - (loc + ext)) <= 64 if d else None,
                        alloc_before_resume=alloc, alloc_frac_free=(alloc / free) if (alloc is not None and free > 0) else None,
                        alloc_before_sched=alloc_s,
                        alloc_sched_frac_free=(alloc_s / free) if (alloc_s is not None and free > 0) else None,
                        filler_target=t.get("filler_target"), filler_done=t.get("filler_tokens_done_before_resume"),
                        filler_finished=t.get("filler_finished_before_resume"), resume_ttft=res["ttft_s"],
                        kv_build=t.get("kv_usage_after_build"), kv_resume=t.get("kv_usage_at_resume"),
                        running=t.get("running_at_resume"), waiting=t.get("waiting_at_resume")))
    res = dict(n_trials=len(out), void=meta.get("void"), remaining_at_guard=meta.get("remaining_at_guard"),
               kv_capacity=meta.get("kv_capacity_tokens"))
    # survival per (server, size, load, gap)
    cells = defaultdict(list)
    for x in out:
        cells[(x["server"], x["size"], x["load"], x["gap"])].append(x)
    tab = {}
    for (sv, sz, ld, g), v in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], kv[0][3] or 0)):
        k = sum(x["full_resident"] for x in v)
        lo, hi = wilson(k, len(v))
        lost = [x["lost_tokens"] for x in v]
        ev = sum(lost)
        tab[f"{sv}|{sz}|{ld}|{g}"] = dict(n=len(v), p_full=k / len(v), ci95=[lo, hi], lost_median=med(lost),
                                          p_host=(sum(x["external"] for x in v) / ev) if ev else None,
                                          ttft_median=med([x["resume_ttft"] for x in v]),
                                          alloc_frac_median=med([x["alloc_frac_free"] for x in v]),
                                          filler_finished=sum(bool(x["filler_finished"]) for x in v),
                                          ambiguous=sum(x["ambiguous"] for x in v))
    res["cells"] = tab
    # survival vs pressure (allocated tokens before resume as a fraction of the free pool), per server and size
    bins = (0, 0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 10)
    pv = {}
    for var in ("alloc_frac_free", "alloc_sched_frac_free"):
      for sv in ("E0", "KVHOST"):
        for sz in (2048, 1024):
            v = [x for x in out if x["server"] == sv and x["size"] == sz and x[var] is not None]
            b = {}
            for lo, hi in zip(bins[:-1], bins[1:]):
                w = [x for x in v if lo <= x[var] < hi]
                if w:
                    k = sum(x["full_resident"] for x in w)
                    b[f"{lo}-{hi}"] = dict(n=len(w), p_full=k / len(w), ci95=list(wilson(k, len(w))),
                                           lost_frac_median=med([x["lost_tokens"] / x["prefix"] for x in w]))
            if b:
                pv[f"{var}|{sv}|{sz}"] = b
    res["survival_vs_pressure"] = pv
    # P_host and restore time
    ev = [x for x in out if x["server"] == "KVHOST" and x["lost_tokens"] > FULL_TOL]
    res["P_host"] = dict(n_trials_with_eviction=len(ev),
                         recovered_from_host=sum(x["external"] for x in ev), evicted=sum(x["lost_tokens"] for x in ev),
                         p_host=(sum(x["external"] for x in ev) / sum(x["lost_tokens"] for x in ev)) if ev else None)
    rt = defaultdict(list)
    for x in out:
        kind = "resident" if x["full_resident"] else ("reload" if x["external"] >= x["lost_tokens"] - FULL_TOL else "rebuild")
        rt[(x["server"], x["size"], kind, bool(x["filler_finished"]) or not x["filler_target"])].append(x)
    res["restore"] = {f"{sv}|{sz}|{k}|filler_{'done_or_none' if fd else 'running'}": dict(
        n=len(v), ttft_median=med([x["resume_ttft"] for x in v]), ttft_p90=q([x["resume_ttft"] for x in v], 90),
        lost_median=med([x["lost_tokens"] for x in v]), recomputed_median=med([x["recomputed"] for x in v]))
        for (sv, sz, k, fd), v in sorted(rt.items())}
    # KV-pool state at resume
    res["kv_pool"] = dict(usage_after_build_median=med([x["kv_build"] for x in out]),
                          usage_at_resume_median=med([x["kv_resume"] for x in out]),
                          usage_after_build_max=max([x["kv_build"] or 0 for x in out], default=None),
                          note="kv_cache_usage counts referenced blocks only (vLLM 0.31.0 block_pool.get_usage: 1 - "
                               "free / total; cached-unreferenced blocks are in the free queue)")
    res["attribution"] = dict(step=sum(x["attribution"] == "step" for x in out),
                              counters_fallback=sum(x["attribution"] == "counters" for x in out),
                              ambiguous=sum(x["ambiguous"] for x in out),
                              counters_agree=sum(bool(x["counters_agree"]) for x in out),
                              counters_disagree=sum(x["counters_agree"] is False for x in out))
    res["trials"] = out
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    pre = "eng1b_smoke" if a.smoke else "eng1b"
    r = analyse(pre)
    (OUT / f"{pre}_results.json").write_text(json.dumps(r, indent=1, default=str))
    print(json.dumps({k: v for k, v in r.items() if k != "trials" and k != "cells"}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
