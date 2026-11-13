#!/usr/bin/env python3
"""StudySIM1b-hosttax - what the KV-HOST episodic slowdown actually is, from committed data.

CPU ONLY. Nothing here runs a model and nothing is simulated: every number is computed from
committed per-request records of StudyE10b, StudyE10c and StudyE10e. No INVALID result is used.

StudySIM1-mixed's calibration gate failed, and every capacity mismatch and the whole p50 gap sat
in KV-HOST cells. SIM1 attributed the gap to "a resident long-context recall request lengthens
every step it shares". This file tests that against a competing hypothesis raised from committed
data: that the slowdown is a per-request MODE COST paid whenever the host-offload connector is
enabled, independent of warm sessions. StudyE10b's KVHOST k = 0 cells decide it, and they appear
in NO SIM1 gate cell, so they are a genuinely held-out comparison.

  STEP 0  clock and field audit
  STEP 1  MODE COST   (held out: KVHOST k = 0 vs KVGPU k = 0, StudyE10b only)
  STEP 2  OVERLAP COST (every KV-HOST k > 0 cell, with KV-GPU k in {2,4} as the control)
  STEP 3  the pre-registered decision

The decision rule in Step 3 was fixed by the specification before any of these numbers existed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))

E10 = ROOT / "results/cost/study_e10"
OUT = ROOT / "results/orchestration/sim1b"
NB, SEED = 2000, 0
RECALL_KINDS = ("recall_append", "recall_escalation", "recall_warmup")


# ================================================================ loading
def load(study: str) -> List[Dict]:
    f = E10 / f"{study}_requests_h100nvl.jsonl"
    return [json.loads(line) for line in f.open()]


def submit_s(r: Dict) -> Optional[float]:
    """One per-cell clock for every kind. Episodic and cold_recall records carry the scheduled
    time and the dispatch lateness; recall records carry the submit time directly."""
    if r["kind"] in ("episodic", "cold_recall"):
        if r.get("t_sched") is None:
            return None
        return float(r["t_sched"]) + float(r.get("dispatch_late_s") or 0.0)
    return None if r.get("t_submit") is None else float(r["t_submit"])


def end_s(r: Dict) -> Optional[float]:
    t = submit_s(r)
    if t is None:
        return None
    if r["kind"] in ("episodic", "cold_recall"):
        return None if r.get("ttft_s") is None else t + float(r["ttft_s"])
    return None if r.get("t_end") is None else float(r["t_end"])


def usable(r: Dict) -> bool:
    return (not r.get("error")) and r.get("ttft_s") is not None and bool(r.get("in_window"))


# ================================================================ statistics
def boot_diff(a: Sequence[float], b: Sequence[float], stat=np.median) -> Dict:
    """Difference of a statistic, b minus a, with a percentile bootstrap CI. Requests are the
    resampling unit WITHIN a cell, which is the unit the specification names."""
    A, B = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(SEED)
    ia = rng.integers(0, len(A), (NB, len(A)))
    ib = rng.integers(0, len(B), (NB, len(B)))
    d = stat(B[ib], axis=1) - stat(A[ia], axis=1)
    return dict(point=float(stat(B) - stat(A)),
                ci=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
                excludes_zero=bool(np.percentile(d, 2.5) > 0 or np.percentile(d, 97.5) < 0))


def boot_ratio(a: Sequence[float], b: Sequence[float], stat=np.median) -> Dict:
    A, B = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(SEED)
    ia = rng.integers(0, len(A), (NB, len(A)))
    ib = rng.integers(0, len(B), (NB, len(B)))
    d = stat(B[ib], axis=1) / stat(A[ia], axis=1)
    return dict(point=float(stat(B) / stat(A)),
                ci=[float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))])


def pcts(v: Sequence[float]) -> Dict:
    a = np.asarray(v, float)
    return dict(n=int(a.size), p10=float(np.percentile(a, 10)), p50=float(np.percentile(a, 50)),
                p90=float(np.percentile(a, 90)), p99=float(np.percentile(a, 99)),
                mean=float(a.mean()))


# ================================================================ STEP 0
def step0(studies: Dict[str, List[Dict]]) -> Dict:
    out = dict(label="STEP 0 - clock and field audit", schema={}, checks={})
    for name, rows in studies.items():
        sch = defaultdict(set)
        for r in rows:
            sch[r["kind"]].update(r.keys())
        out["schema"][name] = {k: sorted(v) for k, v in sorted(sch.items())}

    worst_tend, n_tend = 0.0, 0
    worst_ep, n_ep = 0.0, 0
    for name, rows in studies.items():
        for r in rows:
            if r["kind"] in RECALL_KINDS and r.get("t_end") is not None:
                n_tend += 1
                worst_tend = max(worst_tend,
                                 abs(r["t_end"] - (r["t_submit"] + r["latency_s"])))
            if r["kind"] == "episodic" and r.get("service_ttft_s") is not None:
                n_ep += 1
                worst_ep = max(worst_ep, abs(r["ttft_s"] - r["service_ttft_s"]
                                             - (r.get("dispatch_late_s") or 0.0)))
    # t_submit, latency_s and t_end are each committed rounded to the millisecond, so the
    # identity can miss by up to half a unit on each of the three: the tolerance is 1.5 ms, not
    # 1 ms, and the worst observed deviation is reported so the reader can see which it is.
    out["checks"]["recall_t_end_identity"] = dict(
        rule="t_end = t_submit + latency_s within 1.5 ms (three millisecond-rounded fields)",
        n=n_tend, worst_abs_s=worst_tend, pass_=bool(worst_tend <= 1.5e-3))
    out["checks"]["episodic_ttft_identity"] = dict(
        rule="ttft_s = service_ttft_s + dispatch_late_s within 1.5 ms", n=n_ep,
        worst_abs_s=worst_ep, pass_=bool(worst_ep <= 1.5e-3))

    # interleaving: in every mixed cell the two kinds must share one time axis
    inter = []
    for name, rows in studies.items():
        bycell = defaultdict(list)
        for r in rows:
            bycell[r["cell"]].append(r)
        for cell, rs in sorted(bycell.items()):
            ep = [submit_s(r) for r in rs if r["kind"] == "episodic" and submit_s(r) is not None]
            rc = [submit_s(r) for r in rs if r["kind"] in RECALL_KINDS
                  and submit_s(r) is not None]
            if not ep or not rc:
                continue
            lo, hi = max(min(ep), min(rc)), min(max(ep), max(rc))
            span = (hi - lo) / max(max(max(ep), max(rc)) - min(min(ep), min(rc)), 1e-9)
            inter.append(dict(study=name, cell=cell, episodic_span_s=[min(ep), max(ep)],
                              recall_span_s=[min(rc), max(rc)], overlap_fraction=float(span)))
    out["checks"]["interleaving"] = dict(
        rule="in every mixed cell the episodic and recall submit spans overlap on one clock",
        n_cells=len(inter), min_overlap_fraction=(min(x["overlap_fraction"] for x in inter)
                                                  if inter else None),
        pass_=bool(inter and min(x["overlap_fraction"] for x in inter) > 0.5))
    out["interleaving_cells"] = inter
    out["pass"] = all(c["pass_"] for c in out["checks"].values())
    return out


# ================================================================ STEP 1
LOADS = (25, 50, 75, 90)


def step1(e10b: List[Dict], e10c: List[Dict]) -> Dict:
    ep = defaultdict(list)
    for r in e10b:
        if r["kind"] == "episodic" and usable(r):
            ep[r["cell"]].append(float(r["ttft_s"]))
    out = dict(label="STEP 1 - MODE COST from HELD-OUT cells (StudyE10b KVHOST k=0 vs KVGPU k=0; "
                     "neither appears in any StudySIM1 gate cell)", cells=[], n3_cells_exist=True)
    for N in (1, 3):
        for L in LOADS:
            g, h = f"E10B_KVGPU_k0_r0_N{N}_L{L}", f"E10B_KVHOST_k0_r0_N{N}_L{L}"
            if g not in ep or h not in ep:
                out["cells"].append(dict(n_frames=N, level_pct=L, missing=[c for c in (g, h)
                                                                          if c not in ep]))
                continue
            A, B = ep[g], ep[h]
            row = dict(n_frames=N, level_pct=L, gpu_cell=g, host_cell=h,
                       gpu=pcts(A), host=pcts(B))
            for lab, q in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99)):
                row[f"diff_{lab}_s"] = boot_diff(A, B, stat=lambda x, axis=None, _q=q:
                                                 np.percentile(x, _q, axis=axis))
            row["ratio_p50"] = boot_ratio(A, B, stat=lambda x, axis=None:
                                          np.percentile(x, 50, axis=axis))
            out["cells"].append(row)

    # additive or multiplicative? compare the spread of the per-load differences against the
    # spread of the per-load ratios, each normalised by its own mean.
    for N in (1, 3):
        rows = [c for c in out["cells"] if c.get("n_frames") == N and "diff_p50_s" in c]
        d = np.array([c["diff_p50_s"]["point"] for c in rows])
        rr = np.array([c["ratio_p50"]["point"] for c in rows])
        out[f"form_N{N}"] = dict(
            levels=[c["level_pct"] for c in rows],
            diff_p50_s=[float(x) for x in d], ratio_p50=[float(x) for x in rr],
            cv_additive=float(np.std(d) / abs(np.mean(d))) if np.mean(d) else None,
            cv_multiplicative=float(np.std(rr - 1.0) / abs(np.mean(rr - 1.0)))
            if np.mean(rr - 1.0) else None)

    # between-study drift for the SAME configuration = the noise floor
    epc = defaultdict(list)
    for r in e10c:
        if r["kind"] == "episodic" and usable(r):
            epc[r["cell"]].append(float(r["ttft_s"]))
    drift = []
    for N, cb, cc in ((1, "E10B_KVGPU_k0_r0_N1_L25", "E10C_E0_C0_N1_L25"),
                      (3, "E10B_KVGPU_k0_r0_N3_L25", "E10C_E0_C0_N3_L25"),
                      (1, "E10B_KVGPU_k0_r0_N1_L50", "E10C_E0_C0_N1_L50"),
                      (3, "E10B_KVGPU_k0_r0_N3_L50", "E10C_E0_C0_N3_L50")):
        if cb in ep and cc in epc:
            drift.append(dict(n_frames=N, e10b_cell=cb, e10c_cell=cc,
                              e10b_p50=float(np.median(ep[cb])),
                              e10c_p50=float(np.median(epc[cc])),
                              diff_s=float(np.median(epc[cc]) - np.median(ep[cb])),
                              **{"boot": boot_diff(ep[cb], epc[cc])}))
    out["between_study_drift"] = drift
    # THE NOISE FLOOR, as the specification defines it: the drift between two studies running the
    # SAME configuration, at the same N. StudyE10b and StudyE10c ran E0 / KVGPU k = 0 / r = 0
    # weeks apart on the same host, so whatever separates their medians is what a difference of
    # this size is worth before any mechanism is invoked. It is taken at 25 % load, the lowest
    # level both studies share, and it is PER N because the N = 3 drift is twice the N = 1 drift.
    out["noise_floor_by_n_frames_s"] = {
        str(N): float(abs(d["diff_s"])) for N in (1, 3)
        for d in drift if d["n_frames"] == N and d["e10b_cell"].endswith("L25")}
    out["noise_floor_s"] = out["noise_floor_by_n_frames_s"].get("1")
    out["noise_floor_rule"] = ("per-N drift between StudyE10b and StudyE10c on the same "
                               "configuration at 25 % load; the other load levels are reported "
                               "beside it")
    return out


# ================================================================ STEP 2
def _intervals(rows: List[Dict], kinds) -> List[Tuple[float, float, Dict]]:
    iv = []
    for r in rows:
        if r["kind"] in kinds and not r.get("error"):
            a, b = submit_s(r), end_s(r)
            if a is not None and b is not None:
                iv.append((a, b, r))
    iv.sort(key=lambda x: (x[0], x[1]))
    return iv


def label_cell(rs: List[Dict]) -> Tuple[List[Dict], int]:
    """Label every usable episodic request OVERLAP / CLEAR against the recall requests in flight.
    Requests overlapping a COLD recall are excluded: that is the head-of-line hold StudySIM1
    already models, and mixing it in would measure the mechanism twice."""
    rec = _intervals(rs, RECALL_KINDS)
    cold = _intervals(rs, ("cold_recall",))
    out, excluded = [], 0
    for r in rs:
        if r["kind"] != "episodic" or not usable(r):
            continue
        a = submit_s(r)
        b = a + float(r["ttft_s"])
        if any(x[0] < b and a < x[1] for x in cold):
            excluded += 1
            continue
        hit = [x for x in rec if x[0] < b and a < x[1]]
        cached = max((int(x[2].get("cached_tokens") or 0) for x in hit), default=0)
        newtok = max((int(x[2].get("prompt_tokens") or 0) - int(x[2].get("cached_tokens") or 0)
                      for x in hit), default=0)
        out.append(dict(ttft_s=float(r["ttft_s"]), overlap=bool(hit), n_concurrent=len(hit),
                        cached_tokens=cached, new_tokens=newtok, frac=float(r.get("frac") or 0.0),
                        cell=r["cell"], kv=r.get("kv"), k=int(r.get("k") or 0),
                        N=int(r.get("N") or r.get("n") or 1)))
    return out, excluded


def step2(studies: Dict[str, List[Dict]]) -> Dict:
    out = dict(label="STEP 2 - OVERLAP COST in every KV-HOST k > 0 cell, with KV-GPU k in {2,4} "
                     "as the control (no collapse there)", cells=[], excluded_cold_overlap=0)
    pooled: List[Dict] = []
    for name, rows in studies.items():
        bycell = defaultdict(list)
        for r in rows:
            bycell[r["cell"]].append(r)
        for cell, rs in sorted(bycell.items()):
            kv = next((r.get("kv") for r in rs if r.get("kv")), None)
            k = next((int(r.get("k") or 0) for r in rs if r.get("k") is not None), 0)
            if k <= 0:
                continue
            group = ("HOST" if kv == "KVHOST" else ("GPU-CONTROL" if k in (2, 4) else None))
            if group is None:
                continue
            lab, exc = label_cell(rs)
            out["excluded_cold_overlap"] += exc
            if not lab:
                continue
            ov = [x["ttft_s"] for x in lab if x["overlap"]]
            cl = [x["ttft_s"] for x in lab if not x["overlap"]]
            row = dict(study=name, cell=cell, group=group, kv=kv, k=k,
                       n_frames=lab[0]["N"], level_pct=int(round(100 * lab[0]["frac"])),
                       n=len(lab), n_overlap=len(ov), n_clear=len(cl),
                       overlap_fraction=len(ov) / float(len(lab)),
                       excluded_cold_overlap=exc)
            if ov and cl:
                row["overlap"] = pcts(ov)
                row["clear"] = pcts(cl)
                row["diff_p50_s"] = boot_diff(cl, ov)
                row["diff_p99_s"] = boot_diff(cl, ov, stat=lambda x, axis=None:
                                              np.percentile(x, 99, axis=axis))
            out["cells"].append(row)
            for x in lab:
                x["group"] = group
                x["study"] = name
            pooled += lab

    # pooled difference per group
    out["groups"] = {}
    for grp in ("HOST", "GPU-CONTROL"):
        sel = [x for x in pooled if x["group"] == grp]
        ov = [x["ttft_s"] for x in sel if x["overlap"]]
        cl = [x["ttft_s"] for x in sel if not x["overlap"]]
        if ov and cl:
            out["groups"][grp] = dict(n=len(sel), n_overlap=len(ov), n_clear=len(cl),
                                      overlap=pcts(ov), clear=pcts(cl),
                                      diff_p50_s=boot_diff(cl, ov),
                                      diff_mean_s=boot_diff(cl, ov, stat=np.mean))

    # regression on the KV-HOST requests
    sel = [x for x in pooled if x["group"] == "HOST"]
    if sel:
        X = np.column_stack([
            np.ones(len(sel)),
            np.array([1.0 if x["overlap"] else 0.0 for x in sel]),
            np.array([float(x["n_concurrent"]) for x in sel]),
            np.array([x["cached_tokens"] / 1000.0 for x in sel]),
            np.array([x["new_tokens"] / 1000.0 for x in sel]),
            np.array([x["frac"] for x in sel])])
        y = np.array([x["ttft_s"] for x in sel])
        names = ["intercept", "overlap", "n_concurrent", "cached_ktokens", "new_ktokens",
                 "load_fraction"]
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        rng = np.random.default_rng(SEED)
        bs = np.empty((200, X.shape[1]))
        for i in range(200):
            idx = rng.integers(0, len(y), len(y))
            bs[i], *_ = np.linalg.lstsq(X[idx], y[idx], rcond=None)
        resid = y - X @ beta
        out["regression"] = dict(
            model="ttft_s ~ 1 + overlap + n_concurrent + cached_ktokens + new_ktokens + "
                  "load_fraction, OLS on every KV-HOST k > 0 episodic request not overlapping a "
                  "cold recall; CIs from 200 bootstrap refits (requests resampled)",
            n=len(y), r2=float(1.0 - resid.var() / y.var()),
            coefficients={nm: dict(beta=float(b),
                                   ci=[float(np.percentile(bs[:, j], 2.5)),
                                       float(np.percentile(bs[:, j], 97.5))])
                          for j, (nm, b) in enumerate(zip(names, beta))})
    return out


# ================================================================ STEP 3
def step3(s1: Dict, s2: Dict) -> Dict:
    floors = {int(k): v for k, v in s1["noise_floor_by_n_frames_s"].items()}
    floor = s1.get("noise_floor_s") or 0.0
    # (i): the held-out k = 0 difference, judged against its OWN N's drift floor
    cells = [c for c in s1["cells"] if "diff_p50_s" in c]
    sig = [c for c in cells if c["diff_p50_s"]["excludes_zero"]
           and c["diff_p50_s"]["point"] > floors.get(c["n_frames"], floor)]
    i_ok = bool(sig)
    host = s2["groups"].get("HOST")
    ctrl = s2["groups"].get("GPU-CONTROL")
    ii_ok = bool(host and ctrl and host["diff_p50_s"]["excludes_zero"]
                 and host["diff_p50_s"]["point"] > ctrl["diff_p50_s"]["point"])
    # the pooled comparison mixes cells of different N and load, and one control cell
    # (KVGPU k = 4, N = 3, 50 %) is a RE-PREFILL COLLAPSE cell whose overlap difference is
    # +1.59 s, so the pooled control is not a like-for-like contrast. The cell-matched
    # comparison below is reported beside it and is what the report reads.
    matched = []
    for n_f, lvl in sorted({(c["n_frames"], c["level_pct"]) for c in s2["cells"]
                            if "diff_p50_s" in c}):
        h = [c for c in s2["cells"] if c.get("group") == "HOST" and "diff_p50_s" in c
             and c["n_frames"] == n_f and c["level_pct"] == lvl]
        g = [c for c in s2["cells"] if c.get("group") == "GPU-CONTROL" and "diff_p50_s" in c
             and c["n_frames"] == n_f and c["level_pct"] == lvl]
        if h and g:
            matched.append(dict(
                n_frames=n_f, level_pct=lvl,
                host_cells=[c["cell"] for c in h], gpu_cells=[c["cell"] for c in g],
                host_diff_p50_s=[c["diff_p50_s"]["point"] for c in h],
                gpu_diff_p50_s=[c["diff_p50_s"]["point"] for c in g],
                host_median=float(np.median([c["diff_p50_s"]["point"] for c in h])),
                gpu_median=float(np.median([c["diff_p50_s"]["point"] for c in g])),
                host_exceeds_gpu=bool(np.median([c["diff_p50_s"]["point"] for c in h])
                                      > np.median([c["diff_p50_s"]["point"] for c in g]))))
    verdict = ("(iii) both" if i_ok and ii_ok else
               "(i) mode cost only" if i_ok else
               "(ii) overlap cost only" if ii_ok else "(iv) neither")
    return dict(label="STEP 3 - the pre-registered decision",
                noise_floor_s=floor,
                noise_floor_by_n_frames_s=s1["noise_floor_by_n_frames_s"],
                i_supported=i_ok,
                i_evidence=[dict(n_frames=c["n_frames"], level_pct=c["level_pct"],
                                 diff_p50_s=c["diff_p50_s"]["point"],
                                 ci=c["diff_p50_s"]["ci"]) for c in cells],
                i_cells_significant=[f"N{c['n_frames']}|L{c['level_pct']}" for c in sig],
                ii_supported=ii_ok,
                ii_evidence=dict(host=(host or {}).get("diff_p50_s"),
                                 gpu_control=(ctrl or {}).get("diff_p50_s")),
                ii_cell_matched=matched,
                ii_cell_matched_host_exceeds_gpu=sum(1 for m in matched
                                                     if m["host_exceeds_gpu"]),
                ii_cell_matched_n=len(matched),
                verdict=verdict)


# ================================================================ STEPS 4-5: the gate
def run_gate(label: str, **kw) -> Dict:
    """StudySIM1's calibration gate, UNCHANGED: the same 29 p99 cells, 16 ladders and 8 p50
    cells, the same 5 arrival seeds, the same +/-25 % and 80 % bars and the same collapse rule.
    `kw` is passed straight to `calibrate.run_cell`, so with no `kw` this reproduces SIM1."""
    import math
    sys.path.insert(0, str(HERE))
    import calibrate as C

    res = dict(label=label, options=dict(kw), cells=[], ladders=[], p50_cells=[])
    ok = 0
    for (cond, n, lvl), (ref, src) in sorted(C.REF_P99.items()):
        c = C.cell_p99(cond, n, lvl, **kw)
        sim = c["p99_s"]
        ratio = (None if (sim is None or ref == 0) else
                 (float("inf") if math.isinf(sim) else sim / ref))
        within = bool(ratio is not None and not math.isinf(ratio) and 0.75 <= ratio <= 1.25)
        collapse = bool(ref > 50 and (sim is None or math.isinf(sim) or sim > 50))
        agree = within or collapse
        ok += int(agree)
        res["cells"].append(dict(condition=cond, n_frames=n, level_pct=lvl,
                                 measured_p99_s=ref, source=src, sim_p99_s=sim, ratio=ratio,
                                 within_25pct=within, collapse_agreement=collapse, agree=agree,
                                 sim_p50_s=c.get("p50_s"),
                                 sim_p99_min=c.get("p99_min"), sim_p99_max=c.get("p99_max")))
        print("   p99 %-11s N%d %3d%%  sim %-9s meas %-8.3f %s" % (
            cond, n, lvl, ("%.3f" % sim) if sim is not None and not math.isinf(sim) else sim,
            ref, "OK" if agree else "DISAGREE"), flush=True)
    okc = 0
    for (cond, n), (ref, src) in sorted(C.REF_CAPACITY.items()):
        got, p99 = C.capacity(cond, n, **kw)
        agree = bool(got == ref)
        okc += int(agree)
        res["ladders"].append(dict(condition=cond, n_frames=n, measured_capacity_pct=ref,
                                   source=src, sim_capacity_pct=got, agree=agree,
                                   sim_p99_by_level={str(k): v for k, v in p99.items()}))
        print("   cap %-11s N%d  sim %-6s meas %-6s %s" % (
            cond, n, str(got), str(ref), "OK" if agree else "DISAGREE"), flush=True)
    for (cond, n, lvl), (ref, src) in sorted(C.REF_P50.items()):
        c = C.cell_p99(cond, n, lvl, **kw)
        sim = c.get("p50_s")
        res["p50_cells"].append(dict(condition=cond, n_frames=n, level_pct=lvl,
                                     measured_p50_s=ref, source=src, sim_p50_s=sim,
                                     ratio=(sim / ref if sim else None)))
    res["p99_cells_total"], res["p99_cells_agree"] = len(res["cells"]), ok
    res["p99_fraction_agree"] = ok / max(len(res["cells"]), 1)
    res["ladders_total"], res["ladders_agree"] = len(res["ladders"]), okc
    res["ladders_fraction_agree"] = okc / max(len(res["ladders"]), 1)
    res["gate_p99_pass"] = bool(res["p99_fraction_agree"] >= 0.80)
    res["gate_capacity_pass"] = bool(res["ladders_fraction_agree"] >= 0.80)
    res["GATE"] = "PASS" if (res["gate_p99_pass"] and res["gate_capacity_pass"]) else "FAIL"
    print("  %s: %s  p99 %d/%d (%.0f %%)  capacity %d/%d (%.0f %%)" % (
        label, res["GATE"], ok, len(res["cells"]), 100 * res["p99_fraction_agree"],
        okc, len(res["ladders"]), 100 * res["ladders_fraction_agree"]), flush=True)
    return res


def gate_main() -> int:
    """Step 5, run ONCE with the option ON, with the OFF run beside it and the three controls."""
    sys.path.insert(0, str(HERE))
    import calibrate as C
    import engine as E
    OUT.mkdir(parents=True, exist_ok=True)
    steps = json.loads((OUT / "sim1b_steps.json").read_text())
    if not steps["step3"]["i_supported"]:
        print("Step 3 did not support (i); the option must not be used.")
        return 2
    cost = E.HOST_MODE_COST_S
    res = dict(label="StudySIM1b Step 5: StudySIM1's calibration gate, unchanged, with the "
                     "host-mode-cost option OFF and ON. The option's value comes only from "
                     "Step 1's held-out cells; no gate cell was used to choose it and no other "
                     "SIM1 constant was adjusted.",
               host_mode_cost_s=cost,
               overlap_option="NOT IMPLEMENTED: Step 3 did not support hypothesis (ii), and the "
                              "specification's Step 4 adds only the supported effects. The "
                              "'(ii) only' ablation therefore does not exist, and 'both ON' is "
                              "the same configuration as '(i) only'.",
               runs={})
    print("gate: option OFF (must reproduce StudySIM1)")
    res["runs"]["off"] = run_gate("option OFF")
    print("gate: option ON (i) host mode cost = %.4f s" % cost)
    res["runs"]["mode_cost_on"] = run_gate("(i) host mode cost ON", host_mode_cost_s=cost)

    # ---- negative controls
    ctl = {}
    same = []
    for cond, n, lvl in (("C0", 1, 25), ("C1-r05", 1, 10), ("KVGPU-k4", 1, 25),
                         ("C1-r10", 3, 25)):
        a = C.cell_p99(cond, n, lvl)["p99_s"]
        b = C.cell_p99(cond, n, lvl, host_mode_cost_s=cost)["p99_s"]
        same.append(dict(condition=cond, n_frames=n, level_pct=lvl, off=a, on=b,
                         identical=bool(abs(a - b) < 1e-12)))
    ctl["gpu_cells_untouched"] = dict(
        description="Control 1: with the option ON but the KV mode GPU, every KV-GPU and cold "
                    "cell must be unchanged - the cost is defined to be paid only when the "
                    "host-offload connector is enabled.",
        cells=same, pass_=all(x["identical"] for x in same))
    ctl["zero_reproduces_sim1"] = dict(
        description="Control 2: the option set to 0 must reproduce StudySIM1 exactly.",
        p99_cells_agree=res["runs"]["off"]["p99_cells_agree"],
        ladders_agree=res["runs"]["off"]["ladders_agree"],
        gate=res["runs"]["off"]["GATE"])
    forced = []
    for cond, n, lvl in (("C0", 1, 25), ("C0", 1, 40)):
        ref = C.REF_P99[(cond, n, lvl)][0]
        a = C.cell_p99(cond, n, lvl)["p99_s"]
        b = C.cell_p99(cond, n, lvl, host_mode_cost_s=cost,
                       host_mode_cost_force=True)["p99_s"]
        forced.append(dict(condition=cond, n_frames=n, level_pct=lvl, measured_p99_s=ref,
                           off=a, forced_on=b, ratio_off=a / ref, ratio_forced=b / ref,
                           agreed_off=bool(0.75 <= a / ref <= 1.25),
                           agrees_forced=bool(0.75 <= b / ref <= 1.25)))
    # SUPPLEMENTARY, added after the control below returned FAIL on its stated criterion: the
    # p99 band is +/-25 % of a 0.27-0.38 s number, so a 0.0385 s cost cannot by itself push a
    # C0 cell outside it. The p50 is the quantity the cost acts on directly, and it is reported
    # here so the reader can see the direction and size of the damage. It is EVIDENCE, not a
    # replacement criterion: the control's verdict stands as specified.
    forced_p50 = []
    for cond, n, lvl in (("C0", 1, 25), ("C0", 1, 40)):
        ref = C.REF_P50[(cond, n, lvl)][0]
        a = C.cell_p99(cond, n, lvl).get("p50_s")
        b = C.cell_p99(cond, n, lvl, host_mode_cost_s=cost,
                       host_mode_cost_force=True).get("p50_s")
        forced_p50.append(dict(condition=cond, n_frames=n, level_pct=lvl, measured_p50_s=ref,
                               off=a, forced_on=b, ratio_off=a / ref, ratio_forced=b / ref,
                               agrees_forced=bool(0.75 <= b / ref <= 1.25)))
    ctl["forced_on_gpu_must_disagree"] = dict(
        description="Control 3: applying the cost where it was not measured - a KV-GPU cell - "
                    "must push that cell AWAY from its measurement. A cost that improves every "
                    "cell it touches is a fudge, not a mechanism.",
        cells=forced, p50_cells=forced_p50,
        moves_away_from_measurement=all(abs(x["ratio_forced"] - 1.0)
                                        > abs(x["ratio_off"] - 1.0) for x in forced),
        p50_disagrees=all(not x["agrees_forced"] for x in forced_p50),
        pass_=all(x["agreed_off"] and not x["agrees_forced"] for x in forced))
    res["controls"] = ctl
    for k, v in ctl.items():
        if "pass_" in v:
            print("  control %-28s %s" % (k, "PASS" if v["pass_"] else "FAIL"))

    # ---- the N = 3 over-queueing gap, reported separately and NOT fixed here
    n3 = [c for c in res["runs"]["mode_cost_on"]["cells"]
          if c["n_frames"] == 3 and c["ratio"] and c["ratio"] not in (float("inf"),)]
    res["n3_overqueueing"] = dict(
        description="StudySIM1's second, smaller gap: at N = 3 the simulated p99 runs above the "
                    "measurement at the low and middle levels while the p50 agrees. It is "
                    "reported here and NOT addressed by this study.",
        ratios={f"{c['condition']}|{c['level_pct']}%": c["ratio"] for c in n3})

    from _provenance import stamp
    res["_provenance"] = stamp(script="sim1b_hosttax.py --gate", model=None, device="cpu",
                               n=len(res["runs"]["off"]["cells"]), args=None)
    (OUT / "sim1b_gate.json").write_text(json.dumps(res, indent=1, default=str))
    with (OUT / "sim1b_gate_cells.csv").open("w") as f:
        f.write("condition,n_frames,level_pct,measured_p99_s,sim_off_s,ratio_off,agree_off,"
                "sim_on_s,ratio_on,agree_on\n")
        for a, b in zip(res["runs"]["off"]["cells"], res["runs"]["mode_cost_on"]["cells"]):
            f.write("%s,%d,%d,%.4f,%s,%s,%s,%s,%s,%s\n" % (
                a["condition"], a["n_frames"], a["level_pct"], a["measured_p99_s"],
                a["sim_p99_s"], a["ratio"], a["agree"], b["sim_p99_s"], b["ratio"], b["agree"]))
    print("wrote", OUT / "sim1b_gate.json")
    return 0


# ================================================================ main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    studies = {s: load(s) for s in ("e10b", "e10c", "e10e")}
    res = dict(label="StudySIM1b-hosttax Steps 0-3: what the KV-HOST episodic slowdown is, "
                     "computed from committed per-request records only. CPU only; no GPU, no "
                     "model server, no inference; nothing is simulated in this file.",
               inputs=[str((E10 / f"{s}_requests_h100nvl.jsonl").relative_to(ROOT))
                       for s in studies],
               n_records={s: len(v) for s, v in studies.items()},
               bootstrap=dict(n=NB, seed=SEED, unit="request within cell"))
    res["step0"] = step0(studies)
    if not res["step0"]["pass"]:
        print("STEP 0 FAILED - clocks cannot be aligned; stopping.")
        (OUT / "sim1b_steps.json").write_text(json.dumps(res, indent=1, default=float))
        return 2
    res["step1"] = step1(studies["e10b"], studies["e10c"])
    res["step2"] = step2(studies)
    res["step3"] = step3(res["step1"], res["step2"])

    from _provenance import stamp
    res["_provenance"] = stamp(script="sim1b_hosttax.py", model=None, device="cpu",
                               n=sum(res["n_records"].values()), args=None)
    (OUT / "sim1b_steps.json").write_text(json.dumps(res, indent=1, default=float))

    with (OUT / "sim1b_step1_mode_cost.csv").open("w") as f:
        f.write("n_frames,level_pct,gpu_cell,host_cell,n,gpu_p10,gpu_p50,gpu_p90,gpu_p99,"
                "host_p10,host_p50,host_p90,host_p99,diff_p10_s,diff_p50_s,diff_p50_lo,"
                "diff_p50_hi,diff_p50_excludes_zero,ratio_p50\n")
        for c in res["step1"]["cells"]:
            if "diff_p50_s" not in c:
                continue
            f.write("%d,%d,%s,%s,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,"
                    "%.4f,%s,%.4f\n" % (
                        c["n_frames"], c["level_pct"], c["gpu_cell"], c["host_cell"],
                        c["gpu"]["n"], c["gpu"]["p10"], c["gpu"]["p50"], c["gpu"]["p90"],
                        c["gpu"]["p99"], c["host"]["p10"], c["host"]["p50"], c["host"]["p90"],
                        c["host"]["p99"], c["diff_p10_s"]["point"], c["diff_p50_s"]["point"],
                        c["diff_p50_s"]["ci"][0], c["diff_p50_s"]["ci"][1],
                        c["diff_p50_s"]["excludes_zero"], c["ratio_p50"]["point"]))
    with (OUT / "sim1b_step2_overlap.csv").open("w") as f:
        f.write("study,cell,group,kv,k,n_frames,level_pct,n,n_overlap,n_clear,overlap_fraction,"
                "excluded_cold_overlap,clear_p50,overlap_p50,diff_p50_s,diff_p50_lo,diff_p50_hi,"
                "clear_p99,overlap_p99,diff_p99_s\n")
        for c in res["step2"]["cells"]:
            if "diff_p50_s" not in c:
                f.write("%s,%s,%s,%s,%d,%d,%d,%d,%d,%d,%.4f,%d,,,,,,,,\n" % (
                    c["study"], c["cell"], c["group"], c["kv"], c["k"], c["n_frames"],
                    c["level_pct"], c["n"], c["n_overlap"], c["n_clear"],
                    c["overlap_fraction"], c["excluded_cold_overlap"]))
                continue
            f.write("%s,%s,%s,%s,%d,%d,%d,%d,%d,%d,%.4f,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,"
                    "%.4f\n" % (
                        c["study"], c["cell"], c["group"], c["kv"], c["k"], c["n_frames"],
                        c["level_pct"], c["n"], c["n_overlap"], c["n_clear"],
                        c["overlap_fraction"], c["excluded_cold_overlap"],
                        c["clear"]["p50"], c["overlap"]["p50"], c["diff_p50_s"]["point"],
                        c["diff_p50_s"]["ci"][0], c["diff_p50_s"]["ci"][1],
                        c["clear"]["p99"], c["overlap"]["p99"], c["diff_p99_s"]["point"]))

    print("STEP 0:", "PASS" if res["step0"]["pass"] else "FAIL")
    print("STEP 1: noise floor %.4f s" % (res["step1"]["noise_floor_s"] or 0.0))
    for c in res["step1"]["cells"]:
        if "diff_p50_s" in c:
            print("   N%d L%2d%%  gpu p50 %.4f  host p50 %.4f  diff %+.4f [%+.4f, %+.4f] %s"
                  % (c["n_frames"], c["level_pct"], c["gpu"]["p50"], c["host"]["p50"],
                     c["diff_p50_s"]["point"], c["diff_p50_s"]["ci"][0],
                     c["diff_p50_s"]["ci"][1],
                     "*" if c["diff_p50_s"]["excludes_zero"] else ""))
    for g, v in res["step2"]["groups"].items():
        print("STEP 2 %-12s overlap p50 %.4f vs clear %.4f  diff %+.4f [%+.4f, %+.4f]"
              % (g, v["overlap"]["p50"], v["clear"]["p50"], v["diff_p50_s"]["point"],
                 v["diff_p50_s"]["ci"][0], v["diff_p50_s"]["ci"][1]))
    print("STEP 3:", res["step3"]["verdict"])
    print("wrote", OUT / "sim1b_steps.json")
    return 0


if __name__ == "__main__":
    sys.exit(gate_main() if "--gate" in sys.argv else main())
