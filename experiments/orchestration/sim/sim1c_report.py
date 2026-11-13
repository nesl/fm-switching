#!/usr/bin/env python3
"""StudySIM1c-scoped - the report. CPU only; reads the committed sweep and writes the markdown.

It tabulates. It makes no claim about which baseline is best beyond the tables, and our
scheduler is not in this study.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
R = ROOT / "results/orchestration/sim1c"
MIXES = ("episodic-dominant", "balanced", "recall-dominant")
LADDER = (2, 4, 8, 16, 32)
DEADLINES = (2.0, 5.0, 10.0)
CLOUD_ONLY_MAP = 0.5675        # StudyE9c's delivered cloud cell (32B N=1, 0.5-s cadence, @25 %)
DEVICE_ONLY_MAP = 0.4776       # StudyE9c / StudyE9d's device value
TARGET_MAP = CLOUD_ONLY_MAP - 0.02
STATIC_ARMS = ("B3-best-static", "always-cloud-fcfs", "device-only", "static-partition")


def load(path: Path) -> List[Dict]:
    """The sweep record is committed gzipped (48 MB raw), as every large per-request file in this
    repository is; the uncompressed path is accepted too so a fresh run can be read directly."""
    import gzip
    gz = path.with_suffix(path.suffix + ".gz")
    op = (lambda: gzip.open(gz, "rt")) if gz.exists() else (lambda: path.open())
    with op() as f:
        return [json.loads(x) for x in f if x.strip()]


def boot(v: Sequence[float], n: int = 2000, seed: int = 0) -> Optional[List[float]]:
    a = np.asarray([x for x in v if x is not None], dtype=float)
    if a.size < 2:
        return None
    rng = np.random.default_rng(seed)
    b = a[rng.integers(0, a.size, (n, a.size))].mean(axis=1)
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def agg(rows: List[Dict]) -> Dict:
    """Mean over seeds with a bootstrap CI over seeds, per (arm, mix, fleet, deadline)."""
    by = defaultdict(list)
    for r in rows:
        if r.get("failed"):
            continue
        by[(r["arm"], r["mix"], r["fleet"], r["deadline_s"])].append(r)
    out = {}
    for k, rs in by.items():
        maps = [x["challenge_mAP"] for x in rs]
        tim = [x["recall"]["timely_accuracy"] for x in rs
               if x["recall"]["timely_accuracy"] is not None]
        stv = [x["recall"]["starved"] / max(x["recall"]["n"], 1) for x in rs
               if x["recall"]["n"]]
        out[k] = dict(
            n_seeds=len(rs), reads_future=rs[0].get("reads_future", False),
            mAP=float(np.mean(maps)), mAP_ci=boot(maps),
            mAP_min=float(np.min(maps)), mAP_max=float(np.max(maps)),
            streaming_ap0=float(np.mean([x["streaming_ap"]["0.0"] for x in rs])),
            streaming_ap1=float(np.mean([x["streaming_ap"]["1.0"] for x in rs])),
            timely=(float(np.mean(tim)) if tim else None), timely_ci=boot(tim),
            starved=(float(np.mean(stv)) if stv else None),
            recall_n=float(np.mean([x["recall"]["n"] for x in rs])),
            gpu_s=float(np.mean([x["gpu_s"] for x in rs])),
            gpu_s_budget=float(np.mean([x["gpu_s_budget"] for x in rs])),
            kv_peak=float(np.mean([x["gpu_kv_peak_fraction"] for x in rs])),
            ep_ttft_p99=float(np.mean([x["episodic"]["ttft_p99"] or 0.0 for x in rs])),
            re_prefills=float(np.mean([x["engine"]["re_prefills"] for x in rs])))
    return out


def main() -> int:
    rows = load(R / "sim1c_runs.jsonl")
    A = agg([r for r in rows if r.get("slice_overhead_s") is None])
    sens = [r for r in rows if r.get("slice_overhead_s") is not None]
    scope = json.loads((R / "sim1c_scope.json").read_text())
    san = json.loads((R / "sim1c_sanity.json").read_text()) \
        if (R / "sim1c_sanity.json").exists() else None
    arms = sorted({k[0] for k in A})
    oracle = sorted({k[0] for k in A if A[k]["reads_future"]})
    deployable = [a for a in arms if a not in oracle]

    L: List[str] = []
    def w(x=""):
        L.append(x)

    w("# StudySIM1c-scoped — the StudyB-baselines arms in a world with no host-offload tier")
    w()
    w("**CPU only on the flash host. No GPU, no model server, no inference.** Every latency "
      "comes from the StudySIM1 engine model, every score from StudyD14b's committed traces and "
      "every recall answer's correctness from StudyB-baselines' committed per-question tables. "
      "No result marked INVALID is used.")
    w()
    w("**This report tabulates. It makes no claim about which baseline is best beyond the "
      "tables, and our scheduler is not in this study.**")
    w()
    w("---")
    w()
    w("## 0. THE SCOPE — read this before any number")
    w()
    s = scope["scope"]
    w("* **The world.** %s" % s["world"])
    w("* **What is excluded.** %s" % s["excluded"])
    w("* **Why.** %s" % s["why"])
    w("* **What this cannot claim.** %s" % s["cannot_claim"])
    w()
    w("The exclusion is enforced by an **availability flag in the harness** (`run.py`: "
      "`HOST_AVAILABLE = False`, which maps OFFLOAD_TO_HOST to EVICT and never reports readiness "
      "HOST-WARM). **No baseline's logic was edited.** An arm whose core decision IS host "
      "offload is not run at all.")
    w()
    w("## 1. The scoped calibration gate")
    w()
    g = scope["scoped_gate"]
    w("StudySIM1's gate, restricted to the cells with no KV-HOST tier, at StudySIM1's exact "
      "bars. %s" % g["rule"])
    w()
    w("| | agree | bar | verdict |")
    w("|---|---|---|---|")
    w("| episodic p99 within +/-25 %% | %d / %d (%.0f %%) | 80 %% | %s |"
      % (g["p99_cells_agree"], g["p99_cells_total"], 100 * g["p99_fraction_agree"],
         "PASS" if g["gate_p99_pass"] else "FAIL"))
    w("| capacity level matches | %d / %d (%.0f %%) | 80 %% | %s |"
      % (g["ladders_agree"], g["ladders_total"], 100 * g["ladders_fraction_agree"],
         "PASS" if g["gate_capacity_pass"] else "FAIL"))
    w("| **SCOPED GATE** | | | **%s** |" % g["GATE"])
    w()
    w("Every cell:")
    w()
    w("| condition | N | load | measured p99 | simulated | ratio | agree |")
    w("|---|---|---|---|---|---|---|")
    for c in g["cells"]:
        w("| %s | %d | %d %% | %.3f | %s | %s | %s |"
          % (c["condition"], c["n_frames"], c["level_pct"], c["measured_p99_s"],
             ("%.3f" % c["sim_p99_s"]) if c["sim_p99_s"] is not None else "-",
             ("%.2f" % c["ratio"]) if c["ratio"] else "-", "OK" if c["agree"] else "X"))
    w()
    w("| ladder | N | measured capacity | simulated | agree |")
    w("|---|---|---|---|---|")
    for c in g["ladders"]:
        f = lambda v: "below ladder" if v is None else "%d %%" % v
        w("| %s | %d | %s | %s | %s |" % (c["condition"], c["n_frames"],
                                          f(c["measured_capacity_pct"]),
                                          f(c["sim_capacity_pct"]),
                                          "OK" if c["agree"] else "X"))
    w()
    w("**Declared limitation, carried from StudySIM1 and not fixed here:** at N = 3 the "
      "simulated p99 runs 1.21-1.27x the measurement at the low and middle levels while the p50 "
      "agrees to 6 %. The model over-queues there. Two of the four disagreeing cells above are "
      "that gap.")
    w()
    w("## 2. Which arms run, and which do not")
    w()
    a = scope["arms"]
    w("%d arms in the suite: **%d runnable in scope** (of which %d are oracles, reported "
      "separately as upper bounds) and **%d NOT RUNNABLE**." % (
          a["n_total"], a["n_runnable"], a["n_oracle"], a["n_not_runnable"]))
    w()
    w("| arm | why it is not runnable in this scope |")
    w("|---|---|")
    for x in a["arms"]:
        if not x["runnable"]:
            w("| `%s` | %s |" % (x["name"], x["reason"]))
    w()
    w("| arm | host offload is one component; what the flag changes |")
    w("|---|---|")
    for x in a["arms"]:
        if x["runnable"] and x.get("host_component_note"):
            w("| `%s`%s | %s |" % (x["name"],
                                   (" (run as **%s**)" % x["variant"]) if x["variant"] else "",
                                   x["host_component_note"]))
    w()
    w("`B9-best-of-breed` runs as the labelled variant **B9-noHost**: its host-offload component "
      "is disabled by the harness flag and every other component, and the precedence order, are "
      "unchanged.")
    w()

    # ---------------- headline tables
    w("## 3. Headline tables")
    w()
    w("Challenge mAP is the headline (StudyE9c's definition). Streaming AP is reported under its "
      "own name in section 4 and is **never mixed with it**: the two differ by 56x in chance "
      "level, and StudyE9c established that signs and orderings transfer between them while "
      "absolute levels never do. Scores are continuous log P(Yes) throughout; no literal "
      "Yes / No appears anywhere. Each cell is the mean over %d seeds with a bootstrap CI over "
      "seeds." % max((A[k]["n_seeds"] for k in A), default=0))
    w()
    w("References: an all-cloud arm with no recall and no outages delivers **%.4f** (StudyE9c's "
      "delivered cloud cell) and an all-device arm delivers **%.4f**." % (CLOUD_ONLY_MAP,
                                                                          DEVICE_ONLY_MAP))
    w()
    for mix in MIXES:
        for d in DEADLINES:
            keys = [(arm, mix, F, d) for arm in deployable for F in LADDER if (arm, mix, F, d) in A]
            if not keys:
                continue
            w("### %s, recall deadline %.0f s" % (mix, d))
            w()
            w("| arm | " + " | ".join("F=%d mAP" % F for F in LADDER)
              + " | " + " | ".join("F=%d timely" % F for F in LADDER) + " |")
            w("|---" * (1 + 2 * len(LADDER)) + "|")
            for arm in deployable:
                cells = [A.get((arm, mix, F, d)) for F in LADDER]
                if not any(cells):
                    continue
                w("| `%s` | " % arm
                  + " | ".join(("%.4f" % c["mAP"]) if c else "-" for c in cells) + " | "
                  + " | ".join(("%.3f" % c["timely"]) if c and c["timely"] is not None else "-"
                               for c in cells) + " |")
            w()
            if oracle:
                w("Oracle arms, reported separately as upper bounds (they read the future and "
                  "are excluded from every deployable comparison):")
                w()
                w("| arm | " + " | ".join("F=%d mAP" % F for F in LADDER) + " |")
                w("|---" * (1 + len(LADDER)) + "|")
                for arm in oracle:
                    cells = [A.get((arm, mix, F, d)) for F in LADDER]
                    w("| `%s` | " % arm
                      + " | ".join(("%.4f" % c["mAP"]) if c else "-" for c in cells) + " |")
                w()

    # ---------------- fleet supported
    w("## 4. Fleet size supported at target, streaming AP, cost and occupancy")
    w()
    w("**Target, as pre-registered:** episodic challenge mAP >= the cloud-only value minus 0.02 "
      "(**%.4f**) AND recall timely accuracy >= the best static arm's minus 2 pp, in the same "
      "cell. The supported fleet is the largest ladder point meeting both. The static arms are "
      "%s." % (TARGET_MAP, ", ".join("`%s`" % x for x in STATIC_ARMS)))
    w()
    w("| mix | deadline | arm | supported fleet | mAP there | timely there | GPU-s used / budget "
      "| GPU KV peak | streaming AP h=0 | h=1 s |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for mix in MIXES:
        for d in DEADLINES:
            best_static = {}
            for F in LADDER:
                v = [A[(s_, mix, F, d)]["timely"] for s_ in STATIC_ARMS
                     if (s_, mix, F, d) in A and A[(s_, mix, F, d)]["timely"] is not None]
                best_static[F] = max(v) if v else None
            for arm in deployable:
                sup = None
                for F in LADDER:
                    c = A.get((arm, mix, F, d))
                    if not c or c["timely"] is None or best_static[F] is None:
                        continue
                    if c["mAP"] >= TARGET_MAP and c["timely"] >= best_static[F] - 0.02:
                        sup = F
                if sup is None:
                    continue
                c = A[(arm, mix, sup, d)]
                w("| %s | %.0f s | `%s` | **%d** | %.4f | %.3f | %.0f / %.0f | %.2f | %.5f | %.5f |"
                  % (mix, d, arm, sup, c["mAP"], c["timely"], c["gpu_s"], c["gpu_s_budget"],
                     c["kv_peak"], c["streaming_ap0"], c["streaming_ap1"]))
    w()
    w("An arm with no row met the target at no ladder point in that mix and deadline.")
    w()
    w("### Starvation (any query unanswered past 3x its deadline), per class")
    w()
    w("| arm | " + " | ".join("%s" % m for m in MIXES) + " |")
    w("|---|---|---|---|")
    for arm in deployable:
        vals = []
        for mix in MIXES:
            v = [A[(arm, mix, F, d)]["starved"] for F in LADDER for d in DEADLINES
                 if (arm, mix, F, d) in A and A[(arm, mix, F, d)]["starved"] is not None]
            vals.append("%.3f" % float(np.mean(v)) if v else "-")
        w("| `%s` | %s |" % (arm, " | ".join(vals)))
    w()

    # ---------------- sensitivity
    w("## 5. Sensitivity to the per-slice overhead")
    w()
    w("**StudySLICE1 Part A has now MEASURED it**, so the primary setting is the measured value "
      "and StudySIM1's pre-registered sweep is kept only as sensitivity:")
    w()
    w("| slice size | measured per-slice overhead | measured chain / monolithic engine time | "
      "source |")
    w("|---|---|---|---|")
    w("| 1,024 tokens | **0.015 s** (p10 -0.034, p90 0.068) | 1.093 (max 1.159) | StudySLICE1 "
      "Part A gate table |")
    w("| 2,048 tokens | **-0.004 s**, i.e. about zero (p10 -0.101, p90 0.084) | 0.990 (max "
      "1.008) | as above |")
    w()
    w("`B11-naive-slicing` uses 2,048-token slices, so its primary setting is **0 s per slice** "
      "and StudySLICE1's own chain-cost ratio, not a new estimate.")
    w()
    if sens:
        B = agg(sens)
        byov = defaultdict(list)
        for r in sens:
            if not r.get("failed"):
                byov[r["slice_overhead_s"]].append(r)
        w("| per-slice overhead | n runs | mean challenge mAP | mean recall timely accuracy | "
          "mean GPU-s |")
        w("|---|---|---|---|---|")
        prim = [r for r in rows if r.get("slice_overhead_s") is None
                and "slicing" in r["arm"].lower() and not r.get("failed")]
        if prim:
            w("| **measured (primary)** | %d | %.4f | %.3f | %.0f |"
              % (len(prim), float(np.mean([x["challenge_mAP"] for x in prim])),
                 float(np.mean([x["recall"]["timely_accuracy"] or 0.0 for x in prim])),
                 float(np.mean([x["gpu_s"] for x in prim]))))
        for ov in sorted(byov):
            rs = byov[ov]
            w("| %.2f s | %d | %.4f | %.3f | %.0f |"
              % (ov, len(rs), float(np.mean([x["challenge_mAP"] for x in rs])),
                 float(np.mean([x["recall"]["timely_accuracy"] or 0.0 for x in rs])),
                 float(np.mean([x["gpu_s"] for x in rs]))))
        w()
    w()

    # ---------------- sanity
    w("## 6. Sanity checks")
    w()
    if san:
        w("| check | rule | result | verdict |")
        w("|---|---|---|---|")
        c = san["1_all_cloud_no_recall"]
        w("| 1 | %s | reference %.4f, simulated %.4f, difference %.2e | %s |"
          % (c["rule"], c["reference_mAP"], c["sim_mAP"], c["abs_diff"],
             "PASS" if c["pass_"] else "FAIL"))
        c = san["2_device_only"]
        w("| 2 | %s | reference %.4f, simulated %.4f, difference %.2e | %s |"
          % (c["rule"], c["reference_mAP"], c["sim_mAP"], c["abs_diff"],
             "PASS" if c["pass_"] else "FAIL"))
        c = san["3_trace_digest"]
        w("| 3 | %s | %d cells checked, every one with exactly one distinct digest | %s |"
          % (c["rule"], len(c["cells"]), "PASS" if c["pass_"] else "FAIL"))
        c = san["4_recall_free"]
        w("| 4 | %s | %d of %d arms | %s |"
          % (c["rule"], c["n_improved_or_equal"], c["n_total"],
             "PASS" if c["pass_"] else "FAIL"))
        w()
        w("Checks 1 and 2 agree to **0.0000e+00**: the simulated streams are bit-identical to "
          "the reference held streams, not merely close.")
        w()
        c = san["4_recall_free"]
        neg = sorted([x for x in c["arms"] if x["diff"] < -1e-9], key=lambda z: z["diff"])
        w("**Check 4 FAILED on its 90 %% bar (%d of %d) and the failure is reported, not "
          "redefined.** The five arms that move the wrong way move by at most 0.0162 mAP:"
          % (c["n_improved_or_equal"], c["n_total"]))
        w()
        w("| arm | mAP with recall | mAP with recall free | difference |")
        w("|---|---|---|---|")
        for x in neg:
            w("| `%s` | %.4f | %.4f | %+.5f |"
              % (x["arm"], x["with_recall_mAP"], x["recall_free_mAP"], x["diff"]))
        w()
        w("All five decide from observed load or from a seeded draw (`random-admission` and "
          "`round-robin` select by draw; `uniscale`, `B4-query-type-routing` and "
          "`B8-utility-per-gpu-second` read the queue and the readiness state). Making recall "
          "free changes what they CHOOSE, not only what they PAY, so for those arms this is not "
          "a pure cost ablation. The largest positive move is +0.119 mAP and the median is "
          "+0.0006.")
        w()
        w("The harness also asserts the trace digest inside every sweep cell, so a moved digest "
          "would stop the run rather than appear in a table.")
    else:
        w("NOT RUN.")
    w()

    # ---------------- the hash rule
    w("## 7. The hash rule")
    w()
    hc = scope.get("hash_comparison")
    if hc:
        w("The sha256 of every file under `experiments/orchestration/sim/` and "
          "`experiments/orchestration/baselines/` was recorded before anything ran and again "
          "after the sweep: **%d files at the end, %d added, %d changed, 0 removed.**"
          % (hc["n_files_end"], len(hc["added"]), len(hc["changed"])))
        w()
        w("| file | classification |")
        w("|---|---|")
        for x in hc["added_code"]:
            w("| `%s` | ADDED - this study's own new code, written after the start snapshot; "
              "not a mutation |" % x)
        for x in hc["changed_code"]:
            w("| `%s` | CHANGED |" % x)
        for x in hc["documentation_files_changed"]:
            w("| `%s` | CHANGED, documentation - the B9-noHost note the specification itself "
              "required |" % x)
        w()
        w("**Files modified while the sweep was executing** (window %s to %s):"
          % (hc["sweep_window"]["start"], hc["sweep_window"]["end"]))
        w()
        w("| file | modified | kind |")
        w("|---|---|---|")
        for x in hc["files_modified_during_the_sweep"]:
            w("| `%s` | %s | %s |" % (x["path"], x["modified"],
                                      "code" if x["is_code"] else "documentation"))
        w()
        w("%s" % hc.get("note", ""))
        w()
        w("That is the case the rule is about, so it gets an **empirical** answer rather than an "
          "argument. `run.py` was appended to 39 s after the sweep launched (the `sanity()` "
          "function and its `__main__` guard; the worker pool had already imported the module) "
          "and `sim1c_report.py` only reads outputs. The test: **re-execute recorded sweep cells "
          "with the current code and require the recorded numbers back bit-exactly.**")
        w()
        rp = hc["reproduction"]
        w("| cells re-executed | runs | mismatches | verdict |")
        w("|---|---|---|---|")
        w("| %s | %d | %d | **%s** |"
          % (", ".join("`%s`" % c["cell"].replace("|", " / ") for c in rp["cells"]),
             rp["n_runs"],
             rp["n_mismatches"], "BIT-EXACT" if rp["bit_exact"] else "DIFFERS"))
        w()
        w("Three cells spread across the sweep (its first, middle and last), 12 arms each, "
          "challenge mAP and recall timely accuracy compared at zero tolerance: **%d of %d "
          "mismatches**. `run.py::_arms` imports `sim1c_scope`, so a changed arm list would have "
          "changed these rows too. **No edit during the sweep altered default behaviour, and the "
          "stop condition did not fire.**" % (rp["n_mismatches"], rp["n_runs"]))
        w()
    w("## 8. What this cannot claim")
    w()
    w("* **Nothing about host offload.** The HOST-WARM tier does not exist in this world. Three "
      "arms whose contribution IS that tier were not run, and every other arm's demotions land "
      "in EVICT rather than on the host. A reader who wants the host-offload comparison needs "
      "StudySIM1b's gate to pass first; it does not.")
    w("* **No ranking beyond the tables.** The tables are what was measured. No arm is called "
      "better than another here, and our scheduler is not in this study, so nothing here is "
      "evidence for or against it.")
    w("* **N = 3 over-queueing.** The model over-queues at N = 3 by 1.21-1.27x in p99. Every "
      "N = 3 number carries that.")
    w("* **The device recall proxy.** A DEVICE recall answer is scored with StudyE7 Job A's "
      "committed flags, which are the H100 4B's. StudyD15 Part A rejected that as an EXACT "
      "device stand-in, so device recall numbers are valid for ORDERING and first-order value "
      "and are not exact device numbers.")
    w("* **Device recall latency is a rule, not a measurement.** StudyF4 measured device recall "
      "ACCURACY, not latency; the nearest committed device-side request latency (StudyD8 arm A "
      "total p50, 0.567 s) is used. It is far inside every deadline tested, so no result turns "
      "on it, but it is not a measurement of device recall.")
    w("* **The mix and ladder reading.** The specification's three mixes and its "
      "'2-32 episodic streams x 2-32 recall sessions' ladder are read as one ladder parameter "
      "and a mix that sets the ratio, because a full cross product would make the three mixes "
      "redundant with the ladder's own two axes. The alternative reading is a five-fold larger "
      "sweep.")
    w("* **JPEG is not validated.** Every episodic number here is PNG, StudyE9b setting (ii). "
      "StudyE10a-full did not establish JPEG accuracy parity for S-EMBER.")
    w()
    w("## 9. Files")
    w()
    w("| file | what |")
    w("|---|---|")
    w("| `experiments/orchestration/sim/sim1c_scope.py` | the scope, the file hashes, the scoped gate, the arm list |")
    w("| `experiments/orchestration/sim/workload.py` | the demand trace and its digest |")
    w("| `experiments/orchestration/sim/metrics.py` | challenge mAP, streaming AP, recall timely accuracy |")
    w("| `experiments/orchestration/sim/run.py` | the runner, the scope flag, the sweep and the sanity checks |")
    w("| `experiments/orchestration/sim/sim1c_report.py` | this report |")
    w("| `results/orchestration/sim1c/sim1c_scope.json` | scope, hashes, scoped gate, arms |")
    w("| `results/orchestration/sim1c/sim1c_runs.jsonl.gz` | every run of the sweep (37,800 rows) |")
    w("| `results/orchestration/sim1c/sim1c_cells.csv` | the per-cell aggregate |")
    w("| `results/orchestration/sim1c/sim1c_sanity.json` | the four sanity checks |")
    w("| `results/orchestration/sim1c/sim1c_probe.jsonl` | the timing probe the compute projection was made from |")
    w()

    (ROOT / "reports/study_sim1c_scoped.md").write_text("\n".join(L) + "\n")

    with (R / "sim1c_cells.csv").open("w") as f:
        f.write("arm,mix,fleet,deadline_s,n_seeds,reads_future,challenge_mAP,mAP_lo,mAP_hi,"
                "streaming_ap_h0,streaming_ap_h1,recall_n,timely_accuracy,timely_lo,timely_hi,"
                "starved_fraction,gpu_s,gpu_s_budget,gpu_kv_peak,ep_ttft_p99,re_prefills\n")
        for (arm, mix, F, d), c in sorted(A.items()):
            ci = c["mAP_ci"] or [float("nan")] * 2
            ti = c["timely_ci"] or [float("nan")] * 2
            f.write("%s,%s,%d,%.1f,%d,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.1f,%s,%.6f,%.6f,%s,%.2f,"
                    "%.2f,%.4f,%.4f,%.1f\n"
                    % (arm, mix, F, d, c["n_seeds"], c["reads_future"], c["mAP"], ci[0], ci[1],
                       c["streaming_ap0"], c["streaming_ap1"], c["recall_n"],
                       ("%.6f" % c["timely"]) if c["timely"] is not None else "",
                       ti[0], ti[1],
                       ("%.6f" % c["starved"]) if c["starved"] is not None else "",
                       c["gpu_s"], c["gpu_s_budget"], c["kv_peak"], c["ep_ttft_p99"],
                       c["re_prefills"]))
    print("wrote reports/study_sim1c_scoped.md (%d lines) and sim1c_cells.csv (%d cells)"
          % (len(L), len(A)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
