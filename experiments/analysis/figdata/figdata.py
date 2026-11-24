#!/usr/bin/env python3
"""StudyFIGDATA (D214): collect, once and reproducibly, the data every paper figure (F1 to F17)
needs. NO FIGURES are produced here; this writes one provenance-stamped table per figure under
reports/figdata/ plus a JSON schema per table and a READINESS.md. Offline, CPU only, read-only on
every cell. No em dashes.

Every row carries provenance: arm, policy_version, rung, run_dir, run_commit (the code commit of the
run, from run_meta.json), pipeline_sha (the D209 canonical scorer, canon.py), seed, the condition
columns (memory, n_devices, deadline_s, reask_s, ratio, network), status, port_limited, and
date_scored. No row is written without provenance.

Arm set (D214): our development arms covex-v6-fair-c5attr-rr (current best), covex-v6-fair-c5attr,
covex-v6-state-uo-c5attr, covex-v6-base, covex-v6-rules; the paper baseline set (the BASELINE_MATRIX
active arms, kvflow-prefetch marked port-limited, device-only); cascade-routing and
confidence-cascade are GAPS until their reruns land; r3-streaming and the D205 superseded arms are
excluded. When final-ladder cells land, their rows are added with policy_version=final and the
development rows are kept with status=superseded-by-final (the switch is a filter, not a recompute).
"""
from __future__ import annotations

import csv
import glob
import gzip
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(ROOT, "experiments/analysis/canon"))
import canon as C  # noqa: E402  reuses per_cell/collect_units/dash_attainment/robot_d176 and C.E, C.V

RUNS = os.path.join(ROOT, "results/orchestration/live2/frozen_test/runs")
OUT = os.path.join(ROOT, "reports/figdata")
DSMAP = os.path.join(ROOT, "reports/figures/dsmap_results.json")
PIPELINE_SHA = C.git_sha("experiments/analysis/canon/canon.py")
TODAY = date(2026, 11, 23).isoformat()

SUPERSEDED = C.SUPERSEDED  # the D205 seven
EXCLUDED = {"r3-streaming"} | SUPERSEDED

# Corrected network labelling (user, 2026-11-23). The 13.6 Mbit/s / 44 ms point is NOT the US 5G
# median: per Ookla H2 2025 it is the best-performing US carrier's 5G median.
NETWORK_LABEL = ("uniform 13.6 Mbit/s / 44 ms uplink: best-performing US carrier's 5G median "
                 "(Ookla H2 2025), close to the 12 Mbit/s Bay Area 5G median (Khan et al. 2024)")
UPLINK_SWEEP = ("Tier-1 uplink values are the committed StudyE1 sweep: 5 / 12 / 13.6 / 25 / 88 "
                "Mbit/s and RTT 22 / 44 / 142 ms, each with its cited uplink source; never the "
                "Irish 5G downlink percentiles")

# display -> (raw at 1x, raw at other memory, policy_version, rung, role)
OURS = [
    ("fair-c5attr-rr", "covex-v6-fair-c5attr-rr", "covex-v6-fair-c5attr-rr", "development-best", "rung3"),
    ("fair-c5attr", "covex-v6-fair-c5attr", "covex-v6-fair-c5attr", "development", "rung3"),
    ("state-uo-c5attr", "covex-v6-state-uo-c5attr", "covex-v6-state-uo-c5attr", "development", "rung2"),
    ("base", "hybrid-F-lhreq-noc3", "covex-v6-base", "development", "rung0"),
    ("rules", "v5-rules-2", "covex-v6-rules", "development", "rung1"),
]
# final-ladder targets: development raw -> final raw (auto-switch when the final cells land)
FINAL_MAP = {
    "covex-v6-state-uo-c5attr": "covex-v6-state-final",
    "covex-v6-fair-c5attr": "covex-v6-fair-final",
    "covex-v6-fair-c5attr-rr": "covex-v6-fair-final",
}
BASELINES = ["edf", "llf", "b7-edf-feasibility", "always-cloud-fcfs", "simplestream",
             "querystream-proactive", "mooncake", "attentionstore-prefetch", "warm-all-lru",
             "hybrid-F-lhreq", "v5-rules", "lmcache", "streamscout", "eco-llm", "kvflow-prefetch"]
PORT_LIMITED = {"kvflow-prefetch": "port rule: characteristic decision unexpressible on this harness "
                "(kvflow_prefetch_proofs.json: validate_action refused all 8,600 fetches, Step 2b "
                "absent link); numbers plotted with this marker"}
# gaps until a rerun lands: display -> reason
GAPS = {
    "cascade-routing": "no scored cell yet (H100 filler, D212); when it lands it is the "
                       "device-only-floor baseline (its sufficiency proxy cannot fire here)",
    "confidence-cascade": "superseded cells (D205 constant-0.0 reader); gap until the D205 rerun lands",
}

SEEDS = [4, 5, 6, 7]
NAME_RE = re.compile(r"^(?P<arm>.+)_n(?P<n>\d+)_s(?P<seed>\d+)_1200s_h27_3t(?P<tag>.*?)$")


def parse_condition(tag):
    """Condition dict from the cell-dir tag after _1200s_h27_3t. Defaults are the standard grid."""
    mem = "1x"
    m = re.search(r"_kv([0-9.]+)", tag)
    if m:
        mem = m.group(1) + "x"
    dl = "3.0"
    m = re.search(r"_L([0-9.]+)(?:_|$)", tag)
    if m:
        dl = "%.1f" % float(m.group(1))  # normalize: _L3_ -> 3.0, _L2.5_ -> 2.5
    rq = None
    m = re.search(r"_rq(\d+)", tag)
    if m:
        rq = m.group(1)
    net = "none"
    extras = []
    for pat, lab in ((r"_lpt(\d+)", "long_prompt"), (r"_ls(\d+)", "loadsweep")):
        mm = re.search(pat, tag)
        if mm:
            extras.append(lab + mm.group(1))
    return {"memory": mem, "deadline_s": dl, "reask_s": rq or "", "ratio": "40:40:20",
            "network": net, "extras": ";".join(extras)}


def run_commit(path):
    for f in ("run_meta.json", "header.json"):
        p = os.path.join(path, f)
        if os.path.exists(p):
            try:
                return json.load(open(p)).get("git_commit", "")[:12] or ""
            except Exception:
                pass
    return ""


def discover():
    """Scan runs/ once. Return {display_arm: [cellinfo...]} where cellinfo has path, n, seed, tag,
    condition, rerun, run_commit. Prefers a _rerun dir over its plain twin for the same key."""
    want = {}  # raw -> display
    for disp, r1, r2, _pv, _rung in OURS:
        want[r1] = disp
        want[r2] = disp
    for b in BASELINES:
        want[b] = b
    for raw_fin in set(FINAL_MAP.values()):
        want[raw_fin] = raw_fin  # final arms discovered under their own display name
    by_arm = defaultdict(dict)  # display -> key(n,seed,tag_wo_rerun) -> cellinfo (rerun wins)
    for d in sorted(glob.glob(os.path.join(RUNS, "*_1200s_h27_3t*"))):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "cell.json")):
            continue
        name = os.path.basename(d)
        if name.endswith(".stdout") or "REFUSED" in name:
            continue
        rerun = name.endswith("_rerun")
        base = name[:-6] if rerun else name
        m = NAME_RE.match(base)
        if not m:
            continue
        raw = m.group("arm")
        if raw in EXCLUDED or raw not in want:
            continue
        disp = want[raw]
        tag = m.group("tag")
        # Keep only the committed grid family (rq30 reask grid or the ls fleet sweep); this drops
        # older/straggler dirs with bare tags like '', '_L3', '_L3_epg' that are a different workload.
        if not re.search(r"_epg_(rq30|ls\d+)", tag):
            continue
        key = (int(m.group("n")), int(m.group("seed")), tag)
        info = {"path": d, "raw": raw, "n": int(m.group("n")), "seed": int(m.group("seed")),
                "tag": tag, "rerun": rerun, "cond": parse_condition(tag),
                "run_commit": run_commit(d), "reldir": os.path.relpath(d, ROOT)}
        prev = by_arm[disp].get(key)
        if prev is None or (rerun and not prev["rerun"]):
            by_arm[disp][key] = info
    result = {disp: sorted(cs.values(), key=lambda c: (c["n"], c["seed"], c["tag"]))
              for disp, cs in by_arm.items()}
    # device-only is not a run; it is the device_only block of the base cell. Inject base cells
    # flagged device_only so every builder can emit the device floor from them.
    dev = []
    for info in result.get("base", []):
        di = dict(info)
        di["device_only"] = True
        di["base_raw"] = info["raw"]
        di["raw"] = "device-only"
        dev.append(di)
    if dev:
        result["device-only"] = dev
    return result


def policy_of(disp, raw):
    for d, r1, r2, pv, rung in OURS:
        if d == disp:
            return pv, rung, (raw if raw.startswith("covex-v6-") else raw)
    if disp in set(FINAL_MAP.values()):
        return "final", "rung-final", disp
    return "baseline", "-", disp


def prov(disp, raw, info, status, notes=""):
    pv, rung, _ = policy_of(disp, raw)
    c = info["cond"]
    return {
        "arm": disp, "policy_version": pv, "rung": rung, "run_dir": info["reldir"],
        "run_commit": info["run_commit"], "pipeline_sha": PIPELINE_SHA, "seed": info["seed"],
        "cond_memory": c["memory"], "cond_n_devices": info["n"], "cond_deadline_s": c["deadline_s"],
        "cond_reask_s": c["reask_s"], "cond_ratio": c["ratio"], "cond_network": c["network"],
        "cond_extras": c["extras"], "status": status,
        "port_limited": disp in PORT_LIMITED, "date_scored": TODAY, "notes": notes,
    }


PROV_COLS = ["arm", "policy_version", "rung", "run_dir", "run_commit", "pipeline_sha", "seed",
             "cond_memory", "cond_n_devices", "cond_deadline_s", "cond_reask_s", "cond_ratio",
             "cond_network", "cond_extras", "status", "port_limited", "date_scored", "notes"]


def status_for(disp, info):
    if disp in PORT_LIMITED:
        return "valid"
    for d, *_ in OURS:
        if d == disp:
            return "provisional"  # development policy arm, superseded-by-final when final lands
    return "valid"


# ------------------------------------------------------------------ dsmap mAP (EVAL + ALL) per arm
def load_dsmap():
    out = {}
    if os.path.exists(DSMAP):
        d = json.load(open(DSMAP))
        for a, v in (d.get("arms") or {}).items():
            sp = v.get("splits") or {}
            out[a] = {"EVAL": (sp.get("EVAL") or {}).get("challenge_mAP"),
                      "ALL": (sp.get("ALL") or {}).get("challenge_mAP")}
    return out


def open_gz_text(path):
    """Deterministic gzip text writer (mtime=0) so an unchanged table recompresses to identical
    bytes and the standing poll makes no spurious commit."""
    return io.TextIOWrapper(gzip.GzipFile(path, "wb", mtime=0), newline="")


def read_jl(path, name):
    for cand in (name + ".gz", name):
        p = os.path.join(path, cand)
        if os.path.exists(p):
            op = gzip.open if cand.endswith(".gz") else open
            with op(p, "rt") as fh:
                return [json.loads(l) for l in fh if l.strip()]
    return []


# =============================================================== table writers
def write_table(fig, rows, extra_cols, descr, per="row"):
    """Write reports/figdata/<fig>.csv and <fig>.schema.json. Prov columns first, then extra_cols."""
    os.makedirs(OUT, exist_ok=True)
    cols = PROV_COLS + extra_cols
    with open(os.path.join(OUT, fig + ".csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    schema = {"figure": fig, "describes": descr, "unit": per, "n_rows": len(rows),
              "pipeline_sha": PIPELINE_SHA, "date": TODAY,
              "provenance_columns": PROV_COLS, "data_columns": extra_cols,
              "status_values": ["valid", "provisional", "superseded-by-final", "gap"]}
    json.dump(schema, open(os.path.join(OUT, fig + ".schema.json"), "w"), indent=1)
    return len(rows)


# =============================================================== per-cell core metric extraction
def cell_core(info):
    """The F1/F2 per-cell metrics, reused for the standard grid and for every condition cell."""
    path = info["path"]
    cell = C.E.load_cell(path)
    score = (cell.get("score") or {}).get("score") or {}
    sweep = (score.get("sweep") or [{}])[0]
    if info.get("device_only"):
        dev = score.get("device_only") or {}
        acc, rn = dev.get("robot_accuracy"), dev.get("robot_n")
        rk = int(round(acc * rn)) if acc is not None and rn is not None else None
        corr = C.E.ss2_correctness()
        sk = sn = 0
        for o in read_jl(path, "outcomes.jsonl"):
            if not str(o.get("device_id", "")).startswith("asst"):
                continue
            c = corr.get(o.get("question_id"))
            if c is None:
                continue
            sn += 1
            sk += 1 if c.get("device") else 0
        return {"robot_correct": rk, "robot_n": rn, "robot_frac": acc,
                "robot_d176_correct": rk, "robot_d176_n": rn, "robot_d176_frac": acc,
                "robot_on_time_frac": None, "ss_correct": sk, "ss_n": sn,
                "ss_frac": (sk / sn if sn else None), "ss_on_time_frac": None,
                "dash_attain_per_episode": 0.0, "dash_frac_ep_ge_025": 0.0,
                "dash_on_time_pooled": 0.0,
                "pooled_correct": (rk + sk if rk is not None else None),
                "pooled_n": (rn + sn if rn is not None else None),
                "_sweep": {}, "_score": score}
    rk, rn, racc = C.E.robot_correct_in_time(cell)
    dk, dn = C.robot_d176(cell, path, rk, rn)
    sk, sn, sacc, _, _ = C.E.ss_correct_in_time(path)
    attain, frac025 = C.dash_attainment(path)
    return {
        "robot_correct": rk, "robot_n": rn, "robot_frac": racc,
        "robot_d176_correct": dk, "robot_d176_n": dn,
        "robot_d176_frac": (dk / dn if dn else None),
        "robot_on_time_frac": sweep.get("robot_pool_fraction"),
        "ss_correct": sk, "ss_n": sn, "ss_frac": sacc,
        "ss_on_time_frac": sweep.get("ss_pool_fraction"),
        "dash_attain_per_episode": attain, "dash_frac_ep_ge_025": frac025,
        "dash_on_time_pooled": _pooled_dash_on_time(sweep),
        "pooled_correct": (rk + sk if rk is not None and sk is not None else None),
        "pooled_n": (rn + sn if rn is not None and sn is not None else None),
        "_sweep": sweep, "_score": score,
    }


def _pooled_dash_on_time(sweep):
    pd = sweep.get("dashcam_per_device") or {}
    k = sum(v.get("on_time", 0) for v in pd.values())
    n = sum(v.get("n_instants", 0) for v in pd.values())
    return (k / n) if n else None


def is_standard(info):
    # the committed standard grid cell: 1x memory, 16 devices, deadline 3.0 s, EP-G, rq30
    return info["tag"] == "_L3_epg_rq30" and info["n"] == 16


# =============================================================== F1
def build_F1(disc, dsmap):
    rows, unit_rows = [], []
    for disp in _figure_arms(disc):
        std = [i for i in disc.get(disp, []) if is_standard(i)]
        means = defaultdict(list)
        for info in std:
            core = cell_core(info)
            r = prov(disp, info["raw"], info, status_for(disp, info),
                     notes=PORT_LIMITED.get(disp, ""))
            for k in ("robot_correct", "robot_n", "robot_d176_correct", "robot_d176_n",
                      "ss_correct", "ss_n", "pooled_correct", "pooled_n",
                      "dash_attain_per_episode", "dash_frac_ep_ge_025"):
                r[k] = core[k]
            r["dash_mAP_EVAL"] = ""
            r["dash_mAP_ALL"] = ""
            rows.append(r)
            # CI inputs: per-question correctness
            _uraw = info.get("base_raw", info["raw"])
            for (kind, qid), ok in C.collect_units(_uraw, info["seed"],
                                                   device_only=info.get("device_only", False)).items():
                u = prov(disp, info["raw"], info, status_for(disp, info))
                u["unit_type"] = "robot" if kind == "R" else "single-shot"
                u["qid"] = qid
                u["correct_by_deadline"] = ok
                unit_rows.append(u)
            for k in ("robot_frac", "ss_frac", "dash_attain_per_episode"):
                if core[k] is not None:
                    means[k].append(core[k])
        # pooled-across-seeds row carrying the delivered-stream mAP
        if std:
            info = std[-1]
            pr = prov(disp, info["raw"], info, status_for(disp, info),
                      notes="delivered-stream mAP is pooled across seeds (dsmap), not per-seed")
            pr["seed"] = "all"
            dm = dsmap.get(disp, {})
            pr["dash_mAP_EVAL"] = dm.get("EVAL", "")
            pr["dash_mAP_ALL"] = dm.get("ALL", "")
            rows.append(pr)
    cols = ["robot_correct", "robot_n", "robot_d176_correct", "robot_d176_n", "ss_correct",
            "ss_n", "pooled_correct", "pooled_n", "dash_attain_per_episode", "dash_frac_ep_ge_025",
            "dash_mAP_EVAL", "dash_mAP_ALL"]
    n = write_table("F1", rows, cols,
                    "correct-by-deadline per type (robot, robot D176, single-shot), pooled unit "
                    "count, per-episode on-time attainment and fraction of episodes >= 0.25 (per "
                    "seed); delivered-stream challenge mAP EVAL and cross-fitted ALL on the seed=all "
                    "row (pooled across seeds).")
    # CI-input companion (per question), gzipped
    _write_units("F1_units", unit_rows,
                 ["unit_type", "qid", "correct_by_deadline"],
                 "per-question correct-by-deadline (robot and single-shot) so clustered CIs can be "
                 "recomputed; dashcam per-clip CI inputs are in the DSMAP pipeline (dsmap.py "
                 "delivered_crops).")
    return n, len(unit_rows)


def _write_units(fig, rows, extra, descr):
    cols = PROV_COLS + extra
    with open_gz_text(os.path.join(OUT, fig + ".csv.gz")) as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    json.dump({"figure": fig, "describes": descr, "unit": "per-unit", "n_rows": len(rows),
               "compressed": True, "pipeline_sha": PIPELINE_SHA, "date": TODAY,
               "provenance_columns": PROV_COLS, "data_columns": extra},
              open(os.path.join(OUT, fig + ".schema.json"), "w"), indent=1)


# =============================================================== F2
def build_F2(disc, dsmap):
    rows = []
    for disp in _figure_arms(disc):
        for info in [i for i in disc.get(disp, []) if is_standard(i)]:
            core = cell_core(info)
            base = prov(disp, info["raw"], info, status_for(disp, info),
                        notes=PORT_LIMITED.get(disp, ""))
            for typ, ot, cr in (
                ("robot", core["robot_on_time_frac"], core["robot_frac"]),
                ("single-shot", core["ss_on_time_frac"], core["ss_frac"]),
                ("dashcam-alert", core["dash_on_time_pooled"], core["dash_attain_per_episode"])):
                r = dict(base)
                r["type"] = typ
                r["on_time_rate"] = ot
                r["correct_by_deadline"] = cr
                if typ == "dashcam-alert":
                    r["notes"] = ("on_time_rate is pooled instant on-time; correct_by_deadline is "
                                  "per-episode attainment (no per-unit correctness for dashcam)")
                rows.append(r)
    return write_table("F2", rows, ["type", "on_time_rate", "correct_by_deadline"],
                       "per arm per type (per seed): on-time rate and correct-by-deadline. Dashcam "
                       "correctness is the per-episode attainment.")


# =============================================================== F4
def build_F4(disc):
    rows = []
    for disp in _figure_arms(disc):
        for info in [i for i in disc.get(disp, []) if is_standard(i)]:
            sweep = cell_core(info)["_sweep"]
            for typ, key in (("robot", "robot_per_device"), ("single-shot", "ss_per_device"),
                             ("dashcam-alert", "dashcam_per_device")):
                for dev, v in sorted((sweep.get(key) or {}).items()):
                    r = prov(disp, info["raw"], info, status_for(disp, info))
                    r["type"] = typ
                    r["device_id"] = dev
                    r["n_units"] = v.get("n_questions", v.get("n_instants"))
                    r["on_time"] = v.get("on_time")
                    r["attainment"] = v.get("fraction")
                    r["meets_target"] = v.get("meets", "")
                    rows.append(r)
    return write_table("F4", rows,
                       ["type", "device_id", "n_units", "on_time", "attainment", "meets_target"],
                       "per device per type (per seed): on-time attainment.")


# =============================================================== F13 (GPU / tokens)
def build_F13(disc):
    rows = []
    for disp in _figure_arms(disc):
        for info in disc.get(disp, []):
            if info.get("device_only"):
                continue  # device-only has no cloud GPU/token charge of its own
            path = info["path"]
            core = cell_core(info)
            co = {}
            p = os.path.join(path, "coordinator_result.json")
            if os.path.exists(p):
                co = json.load(open(p))
            reqs = read_jl(path, "request.jsonl")
            unc = 0
            missing_cache = 0
            out_tok = 0
            for rq in reqs:
                pt, ct = rq.get("prompt_tokens"), rq.get("cached_tokens")
                out_tok += rq.get("output_tokens") or 0
                if pt is None:
                    continue
                if ct is None:
                    missing_cache += 1
                    continue
                unc += max(0, pt - ct)
            gpu_s = co.get("budget_spent_gpu_s")
            r = prov(disp, info["raw"], info, status_for(disp, info),
                     notes=PORT_LIMITED.get(disp, ""))
            r["correct_answers_robot_plus_ss"] = (
                (core["robot_correct"] or 0) + (core["ss_correct"] or 0))
            r["gpu_busy_s_measured"] = gpu_s
            r["uncached_tokens_D174"] = unc
            r["cache_absent_requests"] = missing_cache
            r["output_tokens"] = out_tok
            r["uncached_tokens_per_gpu_s"] = (unc / gpu_s) if gpu_s else ""
            r["correct_per_gpu_s"] = (r["correct_answers_robot_plus_ss"] / gpu_s) if gpu_s else ""
            rows.append(r)
    return write_table("F13", rows,
                       ["correct_answers_robot_plus_ss", "gpu_busy_s_measured",
                        "uncached_tokens_D174", "cache_absent_requests", "output_tokens",
                        "uncached_tokens_per_gpu_s", "correct_per_gpu_s"],
                       "per cell: correct answers, measured GPU busy seconds "
                       "(coordinator budget_spent_gpu_s), D174 uncached-token charge, tokens/s.")


# =============================================================== F14 (decision latency live)
def build_F14(disc):
    import numpy as np
    rows = []
    for disp in _figure_arms(disc):
        for info in disc.get(disp, []):
            if info.get("device_only"):
                continue  # device-only makes no scheduling decisions of its own
            dt = read_jl(info["path"], "decision_time.jsonl")
            wall = np.array([d.get("wall_ms") for d in dt if d.get("wall_ms") is not None], float)
            cpu = np.array([d.get("cpu_ms") for d in dt if d.get("cpu_ms") is not None], float)
            r = prov(disp, info["raw"], info, status_for(disp, info),
                     notes=PORT_LIMITED.get(disp, ""))
            r["n_decisions"] = int(wall.size)
            r["decision_wall_ms_p50"] = float(np.percentile(wall, 50)) if wall.size else ""
            r["decision_wall_ms_p99"] = float(np.percentile(wall, 99)) if wall.size else ""
            r["decision_cpu_ms_p50"] = float(np.percentile(cpu, 50)) if cpu.size else ""
            r["decision_cpu_ms_p99"] = float(np.percentile(cpu, 99)) if cpu.size else ""
            r["basis"] = "live"
            rows.append(r)
    return write_table("F14", rows,
                       ["n_decisions", "decision_wall_ms_p50", "decision_wall_ms_p99",
                        "decision_cpu_ms_p50", "decision_cpu_ms_p99", "basis"],
                       "per cell: live decision latency p50/p99 (decision_time.jsonl wall_ms and "
                       "cpu_ms). Dry latency at 16/24/32/48 devices is a flash gap.")


# =============================================================== F8-F12 (conditions)
def build_conditions(disc):
    """One row per arm x seed x condition cell with the F1/F2 metrics. Routed to F8 memory, F9 fleet,
    F10 deadline, F11 composition/reask, F12 network by which dimension departs from the standard."""
    buckets = {"F8": [], "F9": [], "F10": [], "F11": [], "F12": []}
    for disp in _figure_arms(disc):
        for info in disc.get(disp, []):
            c = info["cond"]
            tgt = None
            if c["memory"] != "1x":
                tgt = "F8"
            elif info["n"] != 16 or c["extras"].startswith("loadsweep"):
                tgt = "F9"
            elif c["deadline_s"] != "3.0":
                tgt = "F10"
            elif c["reask_s"] not in ("", "30") or c["ratio"] != "40:40:20":
                tgt = "F11"
            elif c["network"] != "none":
                tgt = "F12"
            else:
                continue  # the standard cell is the reference point, already in F1/F2
            core = cell_core(info)
            r = prov(disp, info["raw"], info, status_for(disp, info),
                     notes=PORT_LIMITED.get(disp, ""))
            for k in ("robot_frac", "robot_d176_frac", "robot_on_time_frac", "ss_frac",
                      "ss_on_time_frac", "pooled_correct", "pooled_n",
                      "dash_attain_per_episode", "dash_frac_ep_ge_025", "dash_on_time_pooled"):
                r[k] = core[k]
            buckets[tgt].append(r)
    cols = ["robot_frac", "robot_d176_frac", "robot_on_time_frac", "ss_frac", "ss_on_time_frac",
            "pooled_correct", "pooled_n", "dash_attain_per_episode", "dash_frac_ep_ge_025",
            "dash_on_time_pooled"]
    descr = {"F8": "memory (KV / GPU-block) sweep", "F9": "fleet-size sweep",
             "F10": "robot-deadline sweep", "F11": "composition and re-ask sweep",
             "F12": "network sweep"}
    counts = {}
    for fig, rows in buckets.items():
        extra = cols + (["capacity_largest_fleet_all_D178"] if fig == "F9" else [])
        counts[fig] = write_table(fig, rows, extra,
                                  "F1/F2 columns for the " + descr[fig] + " condition cells (per "
                                  "arm per seed). " + ("Capacity = largest fleet meeting all three "
                                  "D178 targets (column filled once a fleet sweep exists)."
                                  if fig == "F9" else ""))
    return counts


# =============================================================== F3 (per-request latency)
def build_F3(disc):
    rows = []
    for disp in _figure_arms(disc):
        for info in [i for i in disc.get(disp, []) if is_standard(i)]:
            if info.get("device_only"):
                continue  # device-only has no cloud requests of its own
            path = info["path"]
            reqs = {r.get("opportunity_id"): r for r in read_jl(path, "request.jsonl")}
            outs = read_jl(path, "outcomes.jsonl")
            dl = {"robo": 3.0, "dash": 1.0, "asst": 2.0}
            for o in outs:
                oid = o.get("opportunity_id")
                did = str(o.get("device_id", ""))[:4]
                typ = {"robo": "robot", "dash": "dashcam-alert", "asst": "single-shot"}.get(did)
                if typ is None:
                    continue
                rq = reqs.get(oid, {})
                td = o.get("t_delivered")
                topp = o.get("t_opportunity")
                tsub = rq.get("t_submit")
                tft = rq.get("t_first_token")
                tdone = rq.get("t_done")
                r = prov(disp, info["raw"], info, status_for(disp, info))
                r["type"] = typ
                r["deadline_s"] = dl.get(did)
                r["standing_latency_s"] = (float(td) - float(topp)
                                           if td is not None and topp is not None else "")
                r["cloud_latency_s"] = (float(tdone) - float(tsub)
                                        if tdone is not None and tsub is not None else "")
                r["stamp_queue_prefill_s"] = (float(tft) - float(tsub)
                                              if tft is not None and tsub is not None else "")
                r["stamp_decode_s"] = (float(tdone) - float(tft)
                                       if tdone is not None and tft is not None else "")
                rows.append(r)
    # gzip (large)
    cols = PROV_COLS + ["type", "deadline_s", "standing_latency_s", "cloud_latency_s",
                        "stamp_queue_prefill_s", "stamp_decode_s"]
    with open_gz_text(os.path.join(OUT, "F3.csv.gz")) as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    json.dump({"figure": "F3", "describes": "per request (standard 1x/16-device condition): type, "
               "standing-answer latency, cloud latency, deadline, and the latency stamps that exist "
               "(queue+prefill = t_first_token - t_submit; decode = t_done - t_first_token). "
               "STAMPS ABSENT in request.jsonl: upload, coordinator hold, engine queue (separate), "
               "and return hop are not individually recorded, so only the two composite stamps "
               "exist per cell.", "unit": "per-request", "compressed": True, "n_rows": len(rows),
               "pipeline_sha": PIPELINE_SHA, "date": TODAY, "provenance_columns": PROV_COLS,
               "data_columns": cols[len(PROV_COLS):]},
              open(os.path.join(OUT, "F3.schema.json"), "w"), indent=1)
    return len(rows)


# =============================================================== F6 (time-series availability)
def build_F6(disc):
    series = {"kv_pool": "residency.jsonl", "host_load": "host_load.jsonl",
              "decisions": "decision.jsonl", "late_alerts": "lateness_detail.jsonl"}
    rows = []
    cand = [d for d in ("fair-c5attr-rr", "fair-c5attr", "state-uo-c5attr", "base") if d in disc]
    for disp in cand:
        for info in [i for i in disc.get(disp, []) if is_standard(i)]:
            r = prov(disp, info["raw"], info, status_for(disp, info))
            for lab, fn in series.items():
                r["has_" + lab] = (os.path.exists(os.path.join(info["path"], fn))
                                   or os.path.exists(os.path.join(info["path"], fn + ".gz")))
            r["note"] = ("warms/touches/deferrals derive from decision.jsonl decision kinds; late "
                         "alerts from lateness_detail; series themselves not dumped here")
            rows.append(r)
    return write_table("F6", rows, ["has_kv_pool", "has_host_load", "has_decisions",
                                    "has_late_alerts", "note"],
                       "time-series AVAILABILITY per candidate cell (KV pool, host load, decisions, "
                       "late alerts). The series are read from the cell logs at plot time; this "
                       "table records which exist.")


# =============================================================== F7 (counterfactual decisions) - gap
def build_F7():
    rows = []
    write_table("F7", rows, ["basis", "decision_kind", "count", "condition"],
                "counterfactual decisions by kind per condition (dry and live). GAP: the "
                "counterfactual arm (covex-v6-cf*, rung 4) is not in the figure arm set (D210 "
                "ablation) and its dry cells are produced on flash; no rows yet.")
    return 0


# =============================================================== F15/F16/F17 (external studies)
def build_external():
    # F15 history matters, F16 cold vs warm: pointers to the committed source studies (not run cells)
    f15 = [{"arm": "-", "policy_version": "-", "rung": "-",
            "run_dir": "reports/study_early1.md / reports/phase1_cost_profiling.md",
            "run_commit": "committed-study", "pipeline_sha": "-", "seed": "-",
            "cond_memory": "-", "cond_n_devices": "-", "cond_deadline_s": "-", "cond_reask_s": "-",
            "cond_ratio": "-", "cond_network": "-", "cond_extras": "-", "status": "gap",
            "port_limited": False, "date_scored": TODAY,
            "notes": "F15 (history matters) source: StudyEARLY1 reconstruction cost vs history "
                     "length. Extract the per-N reconstruction cost series into this table on "
                     "request; not yet transcribed."}]
    write_table("F15", f15, [], "history-matters data; source StudyEARLY1 / phase1 cost profiling "
                "(pointer row until transcribed).")
    f16 = [{"arm": "-", "policy_version": "-", "rung": "-",
            "run_dir": "reports/phase1_cost_profiling.md / results/cost/cost_matrix.csv",
            "run_commit": "committed-study", "pipeline_sha": "-", "seed": "-",
            "cond_memory": "-", "cond_n_devices": "-", "cond_deadline_s": "-", "cond_reask_s": "-",
            "cond_ratio": "-", "cond_network": "-", "cond_extras": "-", "status": "gap",
            "port_limited": False, "date_scored": TODAY,
            "notes": "F16 (cold vs warm cost) source: phase1 cost profiling and cost_matrix.csv "
                     "(cold prefill vs warm append per depth). Pointer row until transcribed."}]
    write_table("F16", f16, [], "cold-vs-warm cost data; source phase1 cost profiling / "
                "cost_matrix.csv (pointer row until transcribed).")
    write_table("F17", [], [], "real-deployment figure: PLACEHOLDER, no real-deployment data exists "
                "yet (D214 F17).")
    return {"F15": len(f15), "F16": len(f16), "F17": 0}


# =============================================================== figure arm ordering
def _figure_arms(disc):
    order = [d for d, *_ in OURS] + BASELINES + ["device-only"]
    # final arms appended if present
    order += [a for a in disc if a in set(FINAL_MAP.values())]
    return [a for a in order if a in disc]


# =============================================================== READINESS + main
def condition_coverage(disc):
    """Which non-standard conditions have cells, across the figure arms."""
    mem, dl, fleet, reask, net = set(), set(), set(), set(), set()
    for disp in _figure_arms(disc):
        for info in disc.get(disp, []):
            c = info["cond"]
            if c["memory"] != "1x":
                mem.add(c["memory"])
            if c["deadline_s"] != "3.0":
                dl.add(c["deadline_s"])
            if info["n"] != 16:
                fleet.add(info["n"])
            if c["reask_s"] not in ("", "30"):
                reask.add(c["reask_s"])
            if c["network"] != "none":
                net.add(c["network"])
    return {"memory": sorted(mem), "deadline": sorted(dl), "fleet": sorted(fleet),
            "reask": sorted(reask), "network": sorted(net)}


def write_readiness(disc, counts, dsmap):
    L = []
    A = L.append
    A("# Figure-data readiness (StudyFIGDATA, D214)")
    A("")
    A(f"Pipeline sha (D209 canonical scorer): `{PIPELINE_SHA}`. Generated {TODAY}. Tables in "
      "`reports/figdata/`. NO FIGURES until the user says plot.")
    A("")
    A("## Arm coverage (standard grid: 1x memory, 16 devices, robot deadline 3.0 s, rq30)")
    A("")
    A("| arm | policy_version | rung | seeds present | status |")
    A("|---|---|---|---|---|")
    for disp in [d for d, *_ in OURS] + BASELINES + (["device-only"] if "device-only" in disc else []):
        std = [i for i in disc.get(disp, []) if is_standard(i)]
        seeds = sorted({i["seed"] for i in std})
        pv, rung, _ = policy_of(disp, disc.get(disp, [{}])[0].get("raw", disp) if disc.get(disp) else disp)
        st = status_for(disp, {}) if disp in disc else "gap"
        note = " (port-limited)" if disp in PORT_LIMITED else ""
        A(f"| {disp}{note} | {pv} | {rung} | {seeds or 'NONE'} | {st} |")
    A("")
    A("## Gaps until reruns land")
    A("")
    for g, why in GAPS.items():
        A(f"- **{g}**: {why}")
    A(f"- **final ladder** (covex-v6-state-final / -fair-final / -final): not present; when cells "
      "land they are added as policy_version=final and the development rows are kept as "
      "status=superseded-by-final. Producer: H100 (flash gates the list).")
    A("")
    A("## Condition coverage (F8-F12)")
    A("")
    cov = condition_coverage(disc)
    A(f"- F8 memory: present {cov['memory'] or 'NONE beyond 1x'} (targets 0.25x, 0.5x).")
    A(f"- F9 fleet: present {cov['fleet'] or 'NONE beyond 16'}; capacity (largest fleet meeting all "
      "three D178 targets) needs a fleet sweep, column left blank until it lands. Producer: flash/H100.")
    A(f"- F10 deadline: present {cov['deadline'] or 'NONE beyond 3.0'} (target 2.5 s).")
    A(f"- F11 composition/reask: present {cov['reask'] or 'NONE beyond rq30 / 40:40:20'}.")
    A(f"- F12 network: present {cov['network'] or 'NONE'} (no network-condition cells exist).")
    A("")
    A("## Network / uplink operating point (corrected label, user 2026-11-23)")
    A("")
    A(f"- Main operating point: {NETWORK_LABEL}. It is the BEST-PERFORMING US carrier's 5G median "
      "(T-Mobile per Ookla H2 2025), NOT the US 5G median.")
    A(f"- {UPLINK_SWEEP}.")
    A("- The orchestration standard grid cells are NOT bandwidth-limited (header network=none; the "
      "uplink is modelled as a near-instant wire hop, uplink_queue_p99 ~0 s), so their provenance "
      "carries cond_network=none, not this operating point. The 13.6 Mbit/s / 44 ms label belongs "
      "to the StudyE1 Nexar-lead delivery study (reports/study_e1_nexar_lead.md, corrected in "
      "place) and to any network-conditioned figure (F12) when its cells land.")
    A("")
    A("## Instrumentation gaps by field")
    A("")
    A("- **F3 latency stamps**: request.jsonl records t_submit, t_first_token, t_done only, so only "
      "two composite stamps exist (queue+prefill, decode). ABSENT: upload, coordinator hold, engine "
      "queue (separate), return hop. Producer: the live runner (flash/H100) would need to emit them.")
    A("- **F13 GPU busy**: present (coordinator_result.budget_spent_gpu_s). Uncached-token charge "
      "(D174) and output tokens present from request.jsonl.")
    A("- **F14 dry decision latency** at 16/24/32/48 devices: ABSENT (live p50/p99 present). "
      "Producer: flash dry sweep.")
    A("- **F6 series**: KV pool (residency.jsonl), host load, decisions, late alerts present on the "
      "candidate cells; the series are read at plot time, not dumped here.")
    A("- **F7 counterfactual decisions**: ABSENT (covex-v6-cf* not in the figure arm set, D210; dry "
      "cells on flash).")
    A("- **F15/F16**: pointer rows only; the history-matters and cold-vs-warm series live in "
      "StudyEARLY1 / phase1 cost profiling and are transcribed on request.")
    A("- **F17**: placeholder, no real-deployment data exists.")
    A("- **dashcam delivered-stream mAP cross-fitted ALL**: "
      + ("present" if any(v.get("ALL") is not None for v in dsmap.values()) else "ABSENT in "
         "dsmap_results (only EVAL); rerun dsmap to add ALL") + ".")
    A("")
    A("## Table row counts")
    A("")
    for fig in sorted(counts, key=lambda x: (len(x), x)):
        A(f"- {fig}: {counts[fig]} rows")
    open(os.path.join(OUT, "READINESS.md"), "w").write("\n".join(L) + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    disc = discover()
    dsmap = load_dsmap()
    counts = {}
    counts["F1"], counts["F1_units"] = build_F1(disc, dsmap)
    counts["F2"] = build_F2(disc, dsmap)
    counts["F3"] = build_F3(disc)
    counts["F4"] = build_F4(disc)
    counts["F6"] = build_F6(disc)
    counts["F7"] = build_F7()
    counts.update(build_conditions(disc))
    counts["F13"] = build_F13(disc)
    counts["F14"] = build_F14(disc)
    counts.update(build_external())
    write_readiness(disc, counts, dsmap)
    print("pipeline sha:", PIPELINE_SHA)
    for fig in sorted(counts, key=lambda x: (len(x), x)):
        print(f"  {fig}: {counts[fig]} rows")
    arms_present = [d for d in ([x for x, *_ in OURS] + BASELINES + ["device-only"]) if d in disc]
    print("arms present:", len(arms_present), arms_present)


if __name__ == "__main__":
    main()
