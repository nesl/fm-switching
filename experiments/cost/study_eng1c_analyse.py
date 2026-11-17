#!/usr/bin/env python3
"""StudyENG1c-hostfull analysis (CPU only; run only when no server is up). Reads results/cost/study_eng1c/eng1c[_smoke]_*
and writes eng1c[_smoke]_results.json.

A: observed T / witness outcome per (cap, pattern) vs each candidate rule's pre-written prediction; rule = the
   candidate whose predictions match every pattern; probe effect = witness outcome by probe position.
B: per cell recovered fraction = host-loaded / evicted prefix tokens (resume window counters; ENG1b step attribution
   cross-check), Wilson CI over trials (trial-level: fully recovered), and the token ratio with a bootstrap CI;
   reload / rebuild / resident TTFT (filler finished before resume).
C: percent correct host vs cold per (cap, concurrency) for (i) API cached tokens, (ii) ENG1's metric-delta classifier,
   (iii) round-aggregate external counter (count of host histories).
D: per (cap, load, variant), FIT trials only (HOLDOUT excluded, never read beyond its flag): job TTFT and completion,
   imposed delay on others = sum over background requests of (with - without) latency (matched by index), median /
   p10 / p90, noise from the independent repeats; tier at arrival (simulator, R4) vs observed counters.
E: episodic TTFT and step durations, host full (27 / 38 / 60) vs empty (256 before population), bootstrap CI.
Machine: GPU 3 activity per trial window (utilization > 5 % in any 5-s sample) and host MemAvailable minimum.
"""
import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results/cost/study_eng1c"
RULES = ("FIFO", "LRU_any", "LRU_host", "R4_code")
FULL_TOL = 64


def rows(p):
    return [json.loads(l) for l in open(p)] if p.exists() else []


def med(x):
    x = [v for v in x if v is not None]
    return float(np.median(x)) if x else None


def pct(x, p):
    x = [v for v in x if v is not None]
    return float(np.percentile(x, p)) if x else None


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [(c - h) / d, (c + h) / d]


def boot_ci(x, fn=np.median, n=2000, seed=0):
    x = np.array([v for v in x if v is not None], dtype=float)
    if len(x) < 2:
        return [None, None]
    rng = np.random.default_rng(seed)
    b = [fn(x[rng.integers(0, len(x), len(x))]) for _ in range(n)]
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def boot_diff(a, b, fn=np.median, n=2000, seed=0):
    a = np.array([v for v in a if v is not None], dtype=float)
    b = np.array([v for v in b if v is not None], dtype=float)
    if len(a) < 2 or len(b) < 2:
        return None, [None, None]
    rng = np.random.default_rng(seed)
    d = [fn(a[rng.integers(0, len(a), len(a))]) - fn(b[rng.integers(0, len(b), len(b))]) for _ in range(n)]
    return float(fn(a) - fn(b)), [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]


# ------------------------------------------------------------------------------------------------ machine
class Machine:
    def __init__(self, pre):
        self.r = [x for x in rows(OUT / f"{pre}_machine_h100nvl.jsonl") if "gpus" in x]
        self.t = np.array([x["t"] for x in self.r]) if self.r else np.array([])

    def window(self, t0, t1):
        if not len(self.t):
            return dict(n=0)
        i0, i1 = np.searchsorted(self.t, t0 - 5), np.searchsorted(self.t, t1 + 5)
        w = self.r[i0:i1]
        g3 = [g for x in w for g in x["gpus"] if g["index"] == 3]
        u = [g["util"] for g in g3]
        return dict(n=len(w), gpu3_util_max=max(u) if u else None, gpu3_util_mean=float(np.mean(u)) if u else None,
                    gpu3_active=bool(u) and max(u) > 5, mem_avail_min=min((x["mem_gib"].get("MemAvailable") or 1e9)
                                                                          for x in w) if w else None)

    def summary(self):
        if not self.r:
            return {}
        g3 = [g["util"] for x in self.r for g in x["gpus"] if g["index"] == 3]
        g3m = [g["mem_mib"] for x in self.r for g in x["gpus"] if g["index"] == 3]
        ma = [x["mem_gib"].get("MemAvailable") for x in self.r]
        return dict(samples=len(self.r), gpu3_util_median=med(g3), gpu3_util_frac_active=float(np.mean([u > 5 for u in g3])),
                    gpu3_mem_mib_median=med(g3m), host_mem_available_min_gib=min(ma), host_mem_available_median=med(ma))


# ------------------------------------------------------------------------------------------------ A
def cls(loc, ext, n):
    if loc >= 0.5 * n:
        return "gpu"
    if ext >= 0.9 * (n - loc) and ext > 0:
        return "host"
    if ext > FULL_TOL:
        return "partial_host"
    return "cold"


def part_a(pre):
    S = [r for r in rows(OUT / f"{pre}_partA_h100nvl.jsonl") if r.get("kind") == "a_summary"]
    out = defaultdict(lambda: dict(n=0, observed=defaultdict(int), match={r: 0 for r in RULES + ("R4_code_obs_path",)}, trials=[]))
    pos = defaultdict(lambda: defaultdict(int))
    for s in S:
        key = f"{s['cap']}|{s['pattern']}"
        cell = out[key]
        cell["n"] += 1
        for i, pr in enumerate(s["probes"]):
            role = pr["probe_role"]
            n = pr["prompt_tokens"] or 1
            obs = cls(pr["m_local"], pr["m_external"], n)
            if role == "target":
                cell["observed"][obs] += 1
                for r in RULES:
                    p = s["predictions"][r][i]
                    pc = cls(p["gpu"], p["host"], p["gpu"] + p["host"] + p["compute"])
                    cell["match"][r] += int(pc == obs)
                # code reading conditioned on the OBSERVED touch path (post hoc, labelled): a touch served wholly
                # from GPU or wholly from host refreshes the whole prefix; a mixed touch (any host chunk) leaves the
                # GPU-hit head unrefreshed
                p = s["predictions"]["R4_code"][i]
                pc = cls(p["gpu"], p["host"], p["gpu"] + p["host"] + p["compute"])
                sg = s.get("segments") or {}
                if "touch_local" in sg:
                    mixed = sg["touch_local"] > 0 and sg["touch_external"] > 0
                    if mixed and pc == "host":
                        pc = "cold"
                    elif not mixed and pc == "cold" and s["pattern"] in ("PG", "PM"):
                        pc = "host"
                cell["match"]["R4_code_obs_path"] += int(pc == obs)
            else:
                p = s["predictions"]["R4_code"][i]
                pc = cls(p["gpu"], p["host"], p["gpu"] + p["host"] + p["compute"])
                pos[f"{s['cap']}|{s['pattern']}|pos{i}"][f"obs_{obs}|pred_{pc}"] += 1
            cell["trials"].append(dict(rep=s["rep"], role=role, pos=i, obs=obs, local=pr["m_local"],
                                       external=pr["m_external"], compute=pr["m_compute"], ttft=pr["ttft_s"]))
    res = {k: dict(n=v["n"], observed=dict(v["observed"]), match=v["match"], trials=v["trials"]) for k, v in out.items()}
    tot = {r: sum(v["match"][r] for v in out.values()) for r in RULES + ("R4_code_obs_path",)}
    ntot = sum(v["n"] for v in out.values())
    consistent = [r for r in tot if ntot and tot[r] == ntot]
    return dict(cells=res, rule_match_total=tot, n_target_probes=ntot, consistent_rules=consistent,
                witness_by_position={k: dict(v) for k, v in pos.items()})


# ------------------------------------------------------------------------------------------------ B
def part_b(pre, mach):
    T = rows(OUT / f"{pre}_trials_h100nvl.jsonl")
    out = []
    for t in T:
        d = t.get("resume_window_delta") or {}
        loc = d.get("prompt_tokens_by_source_total|local_cache_hit", 0.0)
        ext = d.get("prompt_tokens_by_source_total|external_kv_transfer", 0.0)
        P = t["prefix_tokens"]
        lost_gpu = max(0.0, P - loc)
        rec = min(ext, lost_gpu)
        kind = "resident" if loc >= P - FULL_TOL else ("reload" if rec >= lost_gpu - FULL_TOL else
                                                       ("partial" if rec > FULL_TOL else "rebuild"))
        w = mach.window(t["t_gap_start"], t["t_resume_issue"] + (t.get("resume_ttft") or 0) + 1)
        out.append(dict(cap=t["cap"], occ=t["occ"], older=t["older"], load=t["load"], rep=t["rep"], tag=t["tag"],
                        prefix=P, local=loc, external=ext, evicted=lost_gpu, recovered=rec,
                        frac=(rec / lost_gpu) if lost_gpu > FULL_TOL else None, kind=kind, ttft=t["resume_ttft"],
                        occ_tokens=t["occ_tokens"], filler_done=t["filler_finished_before_resume"],
                        pred_host=(t.get("sim_pred_at_resume") or {}).get("R4_code", {}).get("host"),
                        pred_gpu=(t.get("sim_pred_at_resume") or {}).get("R4_code", {}).get("gpu"),
                        gpu3_active=w.get("gpu3_active")))
    cells = defaultdict(list)
    for x in out:
        cells[(x["cap"], x["occ"], x["older"], x["load"])].append(x)
    tab = {}
    for (cap, occ, older, load), v in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1], kv[0][3])):
        ev = [x for x in v if x["frac"] is not None]
        k = sum(x["frac"] >= 0.99 for x in ev)
        tok = [x["recovered"] / x["evicted"] for x in ev]
        tab[f"{cap}|occ{occ}|{'older' if older else 'newer'}|{load}"] = dict(
            n=len(v), n_evicted=len(ev), p_full_recovery=(k / len(ev)) if ev else None, ci95=wilson(k, len(ev)),
            token_frac=(sum(x["recovered"] for x in ev) / sum(x["evicted"] for x in ev)) if ev else None,
            token_frac_trial_median=med(tok), token_frac_ci95=boot_ci(tok, np.mean),
            kinds={kk: sum(x["kind"] == kk for x in v) for kk in ("resident", "reload", "partial", "rebuild")},
            ttft_median=med([x["ttft"] for x in v]), ttft_filler_done_median=med([x["ttft"] for x in v if x["filler_done"]]),
            filler_done=sum(bool(x["filler_done"]) for x in v),
            pred_host_median=med([x["pred_host"] for x in v]), gpu3_active=sum(bool(x["gpu3_active"]) for x in v),
            occ_tokens_median=med([x["occ_tokens"] for x in v]))
    # restore times (filler finished / no load)
    def tt(kind, cond):
        return [x["ttft"] for x in out if x["kind"] == kind and cond(x) and (x["filler_done"] or x["load"] == "none")]
    resident = tt("resident", lambda x: x["load"] == "none")
    reload_ = tt("reload", lambda x: x["load"] != "none")
    rebuild = tt("rebuild", lambda x: x["load"] != "none")
    restore = dict(resident_median=med(resident), reload_median=med(reload_), rebuild_median=med(rebuild),
                   n=dict(resident=len(resident), reload=len(reload_), rebuild=len(rebuild)),
                   reload_minus_resident=(med(reload_) - med(resident)) if resident and reload_ else None,
                   rebuild_minus_resident=(med(rebuild) - med(resident)) if resident and rebuild else None,
                   eng1b_reference=dict(resident=0.621, reload=0.738, rebuild=2.758, reload_delta=0.12, rebuild_delta=2.15))
    ev = [x for x in out if x["cap"] == 256 and x["frac"] is not None]
    p_host_256 = (sum(x["recovered"] for x in ev) / sum(x["evicted"] for x in ev)) if ev else None
    return dict(cells=tab, restore=restore, p_host_256=p_host_256, trials=out)


# ------------------------------------------------------------------------------------------------ C
def part_c(pre):
    R = rows(OUT / f"{pre}_partC_h100nvl.jsonl")
    Q = [r for r in R if r.get("kind") == "query"]
    rounds = [r for r in R if r.get("kind") == "c_round"]
    cells = defaultdict(list)
    for q in Q:
        cells[(q["cap"], q["conc"])].append(q)
    tab = {}
    for (cap, conc), v in sorted(cells.items()):
        def truth(q):
            return "host" if q["state"] == "host" else ("gpu" if q["state"] == "gpu" else "cold")
        hc = [q for q in v if truth(q) in ("host", "cold")]
        api = [((q["cached_tokens"] or 0) >= 0.5 * (q["hist_tokens"] or q["prompt_tokens"] or 1)) == (truth(q) == "host")
               for q in hc]
        eng1 = [q["inferred_eng1"] == truth(q) for q in v]
        eng1_hc = [(q["inferred_eng1"] == "host") == (truth(q) == "host") for q in hc]
        sim_ok = []
        for q in v:
            s = (q.get("truth_sim") or {}).get("R4_code") or {}
            n = s.get("n") or 1
            st = "gpu" if s.get("gpu", 0) >= 0.5 * n else ("host" if s.get("gpu", 0) + s.get("host", 0) >= 0.9 * n
                                                         else "cold")
            sim_ok.append(st == truth(q))
        rd = [r for r in rounds if r["cap"] == cap and r["conc"] == conc]
        agg = []
        for r in rd:
            nh = r["states"].count("host")
            ext = r["round_delta"].get("prompt_tokens_by_source_total|external_kv_transfer", 0.0)
            agg.append(round(ext / 11000) == nh)
        tab[f"{cap}|c{conc}"] = dict(
            n=len(v), n_host=sum(truth(q) == "host" for q in v), n_cold=sum(truth(q) == "cold" for q in v),
            n_cold_fresh=sum(q["state"] == "cold_fresh" for q in v), n_gpu=sum(truth(q) == "gpu" for q in v),
            api_cached_host_vs_cold_pct=100 * float(np.mean(api)) if api else None,
            eng1_classifier_3way_pct=100 * float(np.mean(eng1)) if eng1 else None,
            eng1_classifier_host_vs_cold_pct=100 * float(np.mean(eng1_hc)) if eng1_hc else None,
            aggregate_external_count_pct=100 * float(np.mean(agg)) if agg else None,
            sim_truth_agreement_pct=100 * float(np.mean(sim_ok)) if sim_ok else None,
            host_ttft_median=med([q["ttft_s"] for q in v if truth(q) == "host"]),
            cold_ttft_median=med([q["ttft_s"] for q in v if truth(q) == "cold"]),
            queries_in_redrawn_rounds=sum(1 for q in v if q.get("redrawn")))
    return dict(cells=tab)


# ------------------------------------------------------------------------------------------------ D
def part_d(pre, mach):
    R = rows(OUT / f"{pre}_partD_h100nvl.jsonl")
    runs = defaultdict(lambda: defaultdict(list))
    jobs = {}
    for r in R:
        if r.get("sub") != "D" or "pair" not in r:
            continue
        if r.get("kind") == "episodic":
            runs[r["pair"]][r["mode"]].append(r)
        elif r.get("kind") == "job":
            jobs[r["pair"]] = r
    pairs = [r for r in R if r.get("kind") == "pair_check"]
    out = []
    for pc in pairs:
        if pc["holdout"]:
            continue                                   # HOLDOUT: recorded, not analysed
        rr = runs[pc["pair"]]
        j = jobs.get(pc["pair"])
        def lat(rs):
            return {x["idx"]: x["latency_s"] for x in rs if x.get("latency_s") is not None and not x.get("error")}
        w, wo = lat(rr["with"]), lat(rr["without"])
        common = sorted(set(w) & set(wo))
        imposed = sum(w[i] - wo[i] for i in common)
        noise = None
        if rr.get("repeat"):
            rp = lat(rr["repeat"])
            cm = sorted(set(rp) & set(wo))
            noise = sum(rp[i] - wo[i] for i in cm)
        t0 = min((x["t_submit"] for x in rr["with"]), default=None)
        t1 = max((x["t_end"] for x in rr["with"]), default=None)
        mw = mach.window(t0, t1) if t0 else {}
        tier = (j or {}).get("tier_at_arrival", {}).get("R4_code")
        obs = None
        if j:
            n = j.get("hist_tokens") or 1
            fc = j.get("first_cached", j.get("cached_sum")) or 0
            fp = j.get("first_prompt") or n
            obs = "warm" if fc >= 0.5 * min(n, fp) else "cold"
        out.append(dict(cap=pc["cap"], load=pc["load"], variant=pc["variant"], trial=pc["trial"], mismatches=pc["mismatches"],
                        imposed_s=imposed, noise_s=noise, job_ttft=(j or {}).get("job_ttft_s"),
                        job_completion=(j or {}).get("job_completion_s"), tier=tier, observed=obs,
                        tier_ok=(obs == ("warm" if tier in ("gpu", "host") else "cold")) if tier and obs else None,
                        n_requests=(j or {}).get("n_requests"), gpu3_active=mw.get("gpu3_active")))
    cells = defaultdict(list)
    for x in out:
        cells[(x["cap"], x["load"], x["variant"])].append(x)
    tab = {}
    for k, v in sorted(cells.items()):
        def stats(sel):
            imp = [x["imposed_s"] for x in sel]
            return dict(n=len(sel), job_ttft_median=med([x["job_ttft"] for x in sel]),
                        job_ttft_p10=pct([x["job_ttft"] for x in sel], 10), job_ttft_p90=pct([x["job_ttft"] for x in sel], 90),
                        job_completion_median=med([x["job_completion"] for x in sel]),
                        imposed_median=med(imp), imposed_p10=pct(imp, 10), imposed_p90=pct(imp, 90))
        noise = [x["noise_s"] for x in v if x["noise_s"] is not None]
        tab["|".join(map(str, k))] = dict(
            all=stats(v), by_tier={t: stats([x for x in v if x["tier"] == t]) for t in ("gpu", "host", "partial", "cold")
                                    if any(x["tier"] == t for x in v)},
            noise_abs_median=med([abs(z) for z in noise]), noise_n=len(noise),
            tier_check=dict(ok=sum(bool(x["tier_ok"]) for x in v), bad=sum(x["tier_ok"] is False for x in v)),
            mismatches=sum(x["mismatches"] for x in v), gpu3_active=sum(bool(x["gpu3_active"]) for x in v))
    # GPU 3 active vs idle (imposed delay, job ttft) where both occur
    g3 = {}
    for k, v in sorted(cells.items()):
        a = [x for x in v if x["gpu3_active"]]
        b = [x for x in v if x["gpu3_active"] is False]
        if a and b:
            g3["|".join(map(str, k))] = dict(n_active=len(a), n_idle=len(b),
                                             imposed_active=med([x["imposed_s"] for x in a]),
                                             imposed_idle=med([x["imposed_s"] for x in b]))
    hold = sum(1 for p in pairs if p["holdout"])
    return dict(cells=tab, n_fit_pairs=len(out), n_holdout_pairs_recorded=hold,
                mismatches_total=sum(p["mismatches"] for p in pairs), compared_total=sum(p["n"] for p in pairs),
                gpu3_active_vs_idle=g3, trials=out)


# ------------------------------------------------------------------------------------------------ E
def load_steps(pre, label):
    p = OUT / f"{pre}_steps" / f"{label}.jsonl.gz"
    return [json.loads(l) for l in gzip.open(p, "rt")] if p.exists() else []


def part_e(pre, mach):
    R = rows(OUT / f"{pre}_partE_h100nvl.jsonl")
    ep = [r for r in R if r.get("kind") == "episodic"]
    sm = [r for r in R if r.get("kind") == "run_summary"]
    by = defaultdict(list)
    for r in ep:
        by[(r["cap"], r["cond"])].append(r)
    steps = {}
    for s in sm:
        lab = f"{'SMK' if pre.endswith('smoke') else 'DE'}_c{s['cap']}"
        if lab not in steps:
            steps[lab] = load_steps(pre, lab)
    tab = {}
    empty = by.get((256, "empty"), [])
    for (cap, cond), v in sorted(by.items()):
        tt = [x["ttft_s"] for x in v]
        st = steps.get(f"{'SMK' if pre.endswith('smoke') else 'DE'}_c{cap}", [])
        win = [(s["t0_trace"], s["t_end_trace"]) for s in sm if s["cap"] == cap and s["cond"] == cond]
        sd = []
        prev = None
        for s in st:
            if "t" not in s:
                continue
            if prev is not None and any(a <= s["t"] <= b for a, b in win):
                sd.append(s["t"] - prev)
            prev = s["t"]
        g3 = [mach.window(a, b).get("gpu3_active") for a, b in win]
        d, ci = boot_diff(tt, [x["ttft_s"] for x in empty]) if cond == "full" and empty else (None, [None, None])
        tab[f"{cap}|{cond}"] = dict(n=len(v), ttft_median=med(tt), ttft_ci95=boot_ci(tt), ttft_p90=pct(tt, 90),
                                    step_s_median=med(sd), step_s_ci95=boot_ci(sd), n_steps=len(sd),
                                    ttft_minus_empty=d, ttft_minus_empty_ci95=ci,
                                    traces_gpu3_active=sum(bool(x) for x in g3), traces=len(win))
    return dict(cells=tab)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    pre = "eng1c_smoke" if a.smoke else "eng1c"
    mach = Machine(pre)
    meta = json.loads((OUT / f"{pre}_run_meta_h100nvl.json").read_text())
    res = dict(void=meta.get("void"), servers=[{k: s.get(k) for k in ("label", "cap_gib", "cap_tokens", "beyond_gpu_tokens",
                                                                      "mmap_gb", "cap_enforced", "kv_cache_tokens",
                                                                      "flags_diff_vs_eng1_kvhost", "flags_verified",
                                                                      "host_mem")} for s in meta.get("servers", [])],
               machine=mach.summary(), A=part_a(pre), B=part_b(pre, mach), C=part_c(pre), D=part_d(pre, mach),
               E=part_e(pre, mach), pair_cached_mismatch=meta.get("pair_cached_mismatch"))
    (OUT / f"{pre}_results.json").write_text(json.dumps(res, indent=1, default=str))
    short = {k: v for k, v in res.items() if k not in ("A", "B", "D")}
    short["A"] = {k: res["A"][k] for k in ("rule_match_total", "n_target_probes", "consistent_rules")}
    short["B"] = dict(restore=res["B"]["restore"], p_host_256=res["B"]["p_host_256"],
                      cells={k: {kk: v[kk] for kk in ("n", "p_full_recovery", "token_frac", "kinds")}
                             for k, v in res["B"]["cells"].items()})
    short["D"] = {k: res["D"][k] for k in ("n_fit_pairs", "n_holdout_pairs_recorded", "mismatches_total", "compared_total")}
    print(json.dumps(short, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
