#!/usr/bin/env python3
"""StudyENG1f-disk analysis (CPU only; run with no server up). HOLDOUT pairs dropped before anything is computed.

Inputs (results/cost/study_eng1f/): eng1f_equivalence.json; eng1f_<stage>_requests_h100nvl.jsonl for stages equiv_p1,
p2_P25, p2_P40, p3_unloaded, p3_P25, p4; ENG1 plugin rows eng1f_<stage>_statlog/<server>.jsonl(.gz); machine rows.
Decision rules: report section 2 (D1 / D2), EXPERIMENTS.md row (F6 for Part 4).
"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from study_eng1d_analyse import jl, stats, machine_flags  # noqa: E402

OUT = HERE.parents[1] / "results/cost/study_eng1f"
RNG = np.random.default_rng(20261125)


def rows(stage):
    p = OUT / f"eng1f_{stage}_requests_h100nvl.jsonl"
    return jl(p if p.exists() else Path(str(p) + ".gz"))


def mach(stage):
    p = OUT / f"eng1f_{stage}_machine_h100nvl.jsonl"
    return [m for m in jl(p if p.exists() else Path(str(p) + ".gz")) if "gpus" in m]


def imposed(a, b, key):
    ta = {r["idx"]: r[key] for r in a if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    tb = {r["idx"]: r[key] for r in b if r.get("kind") == "episodic" and r.get(key) is not None and not r.get("error")}
    return sum(ta[i] - tb[i] for i in ta if i in tb)


def part1():
    R = [r for r in rows("equiv_p1") if r.get("kind") == "recall"]
    out = {}
    for size in ("11k", "28k"):
        for st in ("cold", "host", "disk"):
            v = [r for r in R if r.get("size") == size and r.get("state") == st]
            out[f"{size}|{st}"] = dict(
                n=len(v), ttft_s=stats([r["ttft_s"] for r in v]), latency_s=stats([r["latency_s"] for r in v]),
                prompt_tokens=stats([r["prompt_tokens"] for r in v]), cached_tokens=stats([r["cached_tokens"] for r in v]),
                secondary_read_gb=stats([r["secondary_read_bytes"] / 1e9 for r in v]),
                secondary_read_s=stats([r["secondary_read_s"] for r in v]),
                read_rate_gbps=stats([r["secondary_read_bytes"] / 1e9 / r["secondary_read_s"] for r in v
                                      if r["secondary_read_s"]]),
                loaded_from_disk=sum(1 for r in v if r["secondary_read_bytes"] > 0),
                external_tokens=stats([r["m_external"] for r in v]), errors=sum(1 for r in v if r.get("error")))
    return out


def part2(load):
    R = rows(f"p2_{load}")
    M = mach(f"p2_{load}")
    runs = defaultdict(lambda: defaultdict(list))
    for r in R:
        if r.get("part") == "P2" and r.get("arm") and r.get("kind") != "pair_check":
            runs[r["pair"]][r["arm"]].append(r)
    pcs = [r for r in R if r.get("kind") == "pair_check"]
    cells = {}
    for st in ("cold", "host", "disk"):
        T = []
        nh = 0
        for pc in pcs:
            if pc["state"] != st:
                continue
            if pc["holdout"]:
                nh += 1
                continue
            rr = runs[pc["pair"]]
            w, wo = rr["with"], rr["without"]
            inj = next((x for x in w if x.get("kind") == "inject"), {})
            sm = next((x for x in w if x.get("kind") == "run_summary"), {})
            t0 = min(x["t_submit"] for x in w if "t_submit" in x)
            t1 = max(x["t_end"] for x in w if "t_end" in x)
            noise = imposed(rr["repeat"], wo, "latency_s") if rr.get("repeat") else None
            T.append(dict(trial=pc["trial"], lat=imposed(w, wo, "latency_s"), ttft=imposed(w, wo, "ttft_s"), noise=noise,
                          inj_ttft=inj.get("ttft_s"), inj_cached=inj.get("cached_tokens"), inj_prompt=inj.get("prompt_tokens"),
                          read_bytes=sm.get("secondary_read_bytes", 0.0), mismatches=pc["mismatches"],
                          **machine_flags(M, t0, t1)))
        cells[st] = dict(n_fit=len(T), n_holdout_recorded=nh, imposed_lat_s=stats([t["lat"] for t in T]),
                         imposed_ttft_s=stats([t["ttft"] for t in T]),
                         noise_abs_lat_s=stats([abs(t["noise"]) for t in T if t["noise"] is not None]),
                         inject_ttft_s=stats([t["inj_ttft"] for t in T]),
                         inject_cached_frac=stats([t["inj_cached"] / t["inj_prompt"] for t in T if t["inj_prompt"]]),
                         with_runs_reading_disk=sum(1 for t in T if t["read_bytes"] > 0),
                         mismatches=sum(t["mismatches"] for t in T), flagged_gpu=sum(t["other_gpu"] for t in T),
                         flagged_cpu=sum(t["cpu_high"] for t in T), trials=T)
    return cells


def part3():
    out = {}
    U = [r for r in rows("p3_unloaded") if r.get("kind") == "recall"]
    for k in (1, 2, 4):
        v = [r for r in U if r.get("k") == k]
        groups = defaultdict(list)
        for r in v:
            groups[r["rep"]].append(r)
        out[f"unloaded|k{k}"] = dict(n=len(v), per_load_ttft_s=stats([r["ttft_s"] for r in v]),
                                     group_max_ttft_s=stats([max(x["ttft_s"] for x in g) for g in groups.values()]),
                                     loaded_from_disk=sum(1 for r in v if r["secondary_read_bytes"] > 0))
    L = rows("p3_P25")
    by = defaultdict(lambda: defaultdict(list))
    for r in L:
        if r.get("part") == "P3" and r.get("arm") and r.get("k") is not None:
            by[(r["k"], r["rep"])][r["arm"]].append(r)
    for k in (1, 2, 4):
        imp, ttft = [], []
        for (kk, rep), d in by.items():
            if kk != k or "with" not in d or "without" not in d:
                continue
            imp.append(imposed(d["with"], d["without"], "latency_s"))
            ttft += [x["ttft_s"] for x in d["with"] if x.get("kind") == "inject" and x.get("ttft_s")]
        out[f"P25|k{k}"] = dict(n=len(imp), imposed_lat_s=stats(imp), per_load_ttft_s=stats(ttft))
    return out


def part4():
    R = [r for r in rows("p4") if r.get("part") == "P4" and not r.get("warm")]
    steps = {}
    for lb in ("P4_OFF1", "P4_ON1", "P4_ON2", "P4_OFF2"):
        p = OUT / "eng1f_p4_statlog" / f"{lb}.jsonl.gz"
        steps[lb] = [x for x in jl(p) if "it" in x]
    out = {}
    for load in ("P40", "P25"):
        per = {}
        for s in [r for r in R if r["kind"] == "run_summary" and r["load"] == load]:
            st = [x["it"][5] for x in steps.get(s["server"], []) if s["t0_trace"] - 0.05 <= x["t"] <= s["t_end"]]
            tt = [r["ttft_s"] for r in R if r.get("run_ns") == s["run_ns"] and r["kind"] == "episodic" and r.get("ttft_s")]
            per[(s["cond"], s["inst"], s["trial"])] = dict(st=st, tt=tt)
        trials = sorted({t for (_, _, t) in per})
        trials = [t for t in trials if all((c, i, t) in per for c in ("ON", "OFF") for i in (1, 2))]
        # PROTOCOL DEVIATION (2026-11-18 06:14:27 to 06:14:39, during P4_ON1): an analysis process ran on the host while
        # the server was up. Traces overlapping that window are excluded from every condition (paired by trace).
        dev = (1795011262.0, 1795011284.0)
        hit = {s["trial"] for s in R if s["kind"] == "run_summary" and s["load"] == load
               and s["t0_trace"] - 1 <= dev[1] and s["t_end"] >= dev[0]}
        trials = [t for t in trials if t not in hit]
        out.setdefault("deviation_excluded_traces", {})[load] = sorted(hit)

        def med(cond, insts, idx, key):
            return float(np.median(np.concatenate([per[(cond, i, t)][key] for t in idx for i in insts])))
        res = {}
        for key, name in (("st", "median_step_ms"), ("tt", "median_ttft_s")):
            pt = med("ON", (1, 2), trials, key) / med("OFF", (1, 2), trials, key)
            bs = [med("ON", (1, 2), list(ix), key) / med("OFF", (1, 2), list(ix), key)
                  for ix in (RNG.choice(trials, size=len(trials)) for _ in range(2000))]
            inst = {c: med(c, (2,), trials, key) / med(c, (1,), trials, key) for c in ("OFF", "ON")}
            res[name] = dict(ratio_on_off=round(pt, 5), ci95=[round(float(np.percentile(bs, 2.5)), 5),
                                                               round(float(np.percentile(bs, 97.5)), 5)],
                             instance_ratio={c: round(v, 5) for c, v in inst.items()}, n_traces=len(trials))
        s, t = res["median_step_ms"], res["median_ttft_s"]
        s["tolerance"] = round(0.01 + max(abs(v - 1) for v in s["instance_ratio"].values()), 5)
        s["passed"] = abs(s["ratio_on_off"] - 1) <= s["tolerance"]
        t["passed"] = t["ci95"][0] <= 1.0 <= t["ci95"][1]
        out[load] = res
    return out


def main():
    eq = json.loads((OUT / "eng1f_equivalence.json").read_text())
    res = dict(equivalence={k: v for k, v in eq.items() if k != "rows"}, part1=part1())
    for load in ("P25", "P40"):
        try:
            res[f"part2_{load}"] = part2(load)
        except Exception as e:  # noqa: BLE001
            res[f"part2_{load}"] = dict(not_run=str(e))
    for name, fn in (("part3", part3), ("part4", part4)):
        try:
            res[name] = fn()
        except Exception as e:  # noqa: BLE001
            res[name] = dict(not_run=f"{type(e).__name__}: {e}")
    (OUT / "eng1f_results.json").write_text(json.dumps(res, indent=1, default=float))
    p1 = res["part1"]
    for k, v in p1.items():
        print("P1", k, v["n"], "ttft", v["ttft_s"].get("median"), "read GB", v["secondary_read_gb"].get("median"),
              "rate", v["read_rate_gbps"].get("median"), "disk", v["loaded_from_disk"])
    for load in ("P25", "P40"):
        c = res[f"part2_{load}"]
        if "not_run" in c:
            print("P2", load, c)
            continue
        for st, v in c.items():
            print("P2", load, st, v["n_fit"], "lat", v["imposed_lat_s"].get("median"), v["imposed_lat_s"].get("ci95"),
                  "noise", v["noise_abs_lat_s"].get("median"), "inj ttft", v["inject_ttft_s"].get("median"),
                  "disk reads", v["with_runs_reading_disk"], "mism", v["mismatches"])
    print("P3", json.dumps(res["part3"], default=float)[:1500])
    print("P4", json.dumps(res["part4"], default=float)[:1500])


if __name__ == "__main__":
    main()
