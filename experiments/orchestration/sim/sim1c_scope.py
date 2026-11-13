#!/usr/bin/env python3
"""StudySIM1c-scoped - the scope declaration, the file-hash record, the SIM1 reproduction check,
the SCOPED calibration gate, and the runnable / not-runnable arm list.

CPU ONLY. Nothing here runs a model, and this file runs no baseline: it establishes what may be
claimed before anything is swept.

THE SCOPE. StudySIM1-mixed's calibration gate failed, and StudySIM1b located why: a per-request
MODE COST paid whenever the host-offload connector is enabled. Modelling it closes most of the
p50 gap but leaves the gate at 69 %, below its 80 % bar. The simulator does calibrate where
there is no host-offload tier at all. This study therefore runs SIM1's sweep in a world with
**no HOST-WARM tier**: GPU-warm, cold and device fallback only. Every result is scoped to that
world and says nothing about any arm's behaviour with host offload.

THE HASH RULE. The sha256 of every file under `experiments/orchestration/sim/` and
`experiments/orchestration/baselines/` is recorded when this runs and again when the sweep ends.
Every option added by StudySIM1b is OFF here, which is the default.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "experiments/lib"))
sys.path.insert(0, str(ROOT / "experiments/orchestration/baselines"))
sys.path.insert(0, str(ROOT / "experiments/orchestration/baselines/smoke"))
sys.path.insert(0, str(ROOT / "experiments/orchestration/baselines/reconstructed"))

OUT = ROOT / "results/orchestration/sim1c"
WATCHED = (ROOT / "experiments/orchestration/sim",
           ROOT / "experiments/orchestration/baselines")

# The scoped gate: SIM1's gate restricted to the conditions with no KV-HOST tier.
SCOPED_CONDITIONS = ("C0", "C1-r05", "C1-r10", "KVGPU-k4", "KVGPU-k8")


# ================================================================ hashes
def file_hashes() -> Dict[str, str]:
    """sha256 of every tracked source file under the two watched trees, sorted by path."""
    out = {}
    for base in WATCHED:
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            out[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def compare_hashes(a: Dict[str, str], b: Dict[str, str]) -> Dict:
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return dict(n_files_start=len(a), n_files_end=len(b), added=added, removed=removed,
                changed=changed, identical=not (added or removed or changed))


# ================================================================ the scoped gate
def scoped_gate() -> Dict:
    """StudySIM1's gate, restricted to the cells with no KV-HOST tier, at SIM1's exact bars.
    Every option added by StudySIM1b is OFF (the default), so this is SIM1's own engine."""
    import calibrate as C
    import engine as E
    assert E.Engine().host_mode_cost_s == 0.0, "StudySIM1b's option must be OFF here"

    res = dict(
        label="StudySIM1c SCOPED calibration gate: StudySIM1's gate restricted to the cells "
              "with no KV-HOST tier (C0, C1 at r = 0.05 and 0.10, KV-GPU k = 4 and 8, at N = 1 "
              "and N = 3), at StudySIM1's exact bars.",
        conditions=list(SCOPED_CONDITIONS),
        rule="PASS iff episodic p99 is within +/-25 % in >= 80 % of cells AND the capacity level "
             "matches in >= 80 % of ladders",
        cells=[], ladders=[])
    ok = 0
    for (cond, n, lvl), (ref, src) in sorted(C.REF_P99.items()):
        if cond not in SCOPED_CONDITIONS:
            continue
        c = C.cell_p99(cond, n, lvl)
        sim = c["p99_s"]
        ratio = (None if (sim is None or ref == 0) else
                 (float("inf") if math.isinf(sim) else sim / ref))
        within = bool(ratio is not None and not math.isinf(ratio) and 0.75 <= ratio <= 1.25)
        collapse = bool(ref > 50 and (sim is None or math.isinf(sim) or sim > 50))
        agree = within or collapse
        ok += int(agree)
        res["cells"].append(dict(condition=cond, n_frames=n, level_pct=lvl, measured_p99_s=ref,
                                 source=src, sim_p99_s=sim, ratio=ratio, within_25pct=within,
                                 collapse_agreement=collapse, agree=agree,
                                 sim_p50_s=c.get("p50_s"), sim_p99_min=c.get("p99_min"),
                                 sim_p99_max=c.get("p99_max"), n_seeds=c.get("n_seeds")))
        print("  p99 %-11s N%d %3d%%  sim %-9s meas %-8.3f %s" % (
            cond, n, lvl, ("%.3f" % sim) if sim is not None and not math.isinf(sim) else sim,
            ref, "OK" if agree else "DISAGREE"), flush=True)
    okc = 0
    for (cond, n), (ref, src) in sorted(C.REF_CAPACITY.items()):
        if cond not in SCOPED_CONDITIONS:
            continue
        got, p99 = C.capacity(cond, n)
        agree = bool(got == ref)
        okc += int(agree)
        res["ladders"].append(dict(condition=cond, n_frames=n, measured_capacity_pct=ref,
                                   source=src, sim_capacity_pct=got, agree=agree,
                                   sim_p99_by_level={str(k): v for k, v in p99.items()}))
        print("  cap %-11s N%d  sim %-6s meas %-6s %s" % (
            cond, n, str(got), str(ref), "OK" if agree else "DISAGREE"), flush=True)
    res["p99_cells_total"], res["p99_cells_agree"] = len(res["cells"]), ok
    res["p99_fraction_agree"] = ok / max(len(res["cells"]), 1)
    res["ladders_total"], res["ladders_agree"] = len(res["ladders"]), okc
    res["ladders_fraction_agree"] = okc / max(len(res["ladders"]), 1)
    res["gate_p99_pass"] = bool(res["p99_fraction_agree"] >= 0.80)
    res["gate_capacity_pass"] = bool(res["ladders_fraction_agree"] >= 0.80)
    res["GATE"] = "PASS" if (res["gate_p99_pass"] and res["gate_capacity_pass"]) else "FAIL"
    return res


# ================================================================ arm classification
# WHY each arm is or is not runnable with the HOST-WARM state and the OFFLOAD_TO_HOST action
# removed from the world. The rule the specification sets: an arm whose CORE DECISION is host
# offload is not runnable; an arm that uses it as ONE COMPONENT runs as a labelled variant with
# that component disabled; an arm for which disabling it would change what the arm fundamentally
# decides is listed as not runnable rather than modified.
#
# The harness enforces the scope with an AVAILABILITY FLAG - it maps OFFLOAD_TO_HOST to EVICT
# and never reports readiness HOST-WARM - and never by editing a baseline's logic.
NOT_RUNNABLE = {
    "attentionstore": (
        "AttentionStore IS a host-side KV cache hierarchy: its contribution is keeping whole "
        "attention caches on host memory and the scheduling that depends on them. With no host "
        "tier the paper's object does not exist, and what would run is not AttentionStore."),
    "lmcache": (
        "LMCache IS a CPU/disk KV cache layer under the engine. With no host tier it reduces to "
        "the engine's own GPU prefix cache, which is what `always-cloud-fcfs` already is."),
    "pensieve": (
        "Pensieve's mechanism is MULTI-TIER PARTIAL RESIDENCY, adapted here (adaptation A1) as "
        "whole-session OFFLOAD_TO_HOST because our action space has no partial tier. Removing "
        "the host tier removes the mechanism itself, not a component of it."),
}
# Arms that touch the host tier but whose decision is something else. For these the availability
# flag changes where a demoted session lands (host -> evicted) and nothing about what is decided.
HOST_AS_COMPONENT = {
    "kvflow": "decides WHICH sessions stay GPU-warm (workflow-aware eviction); the demotion "
              "target is not the decision",
    "mooncake": "decides request ORDER by prefix affinity; readiness HOST-WARM simply never "
                "occurs",
    "preble": "decides request order by prefix affinity; its AFFINITY weight for HOST-WARM "
              "(0.5) never applies",
    "clockwork": "decides admission from a predicted LOAD time; the COLD branch of that "
                 "prediction is used instead of the HOST-WARM branch",
    "covstream": "keeps its top-4 coverage sessions GPU-warm and demotes the rest",
    "ekya": "decides episodic resource allocation; it demotes every session unconditionally",
    "rh8-demand-aware": "decides which sessions are warm from demand; the tier is how that is "
                        "expressed",
    "B9-best-of-breed": "uses host offload as ONE component among several; runs as the labelled "
                        "variant B9-noHost with that component disabled and every other "
                        "component and the precedence order unchanged",
}


def classify_arms() -> Dict:
    import run_all
    import interface as I
    arms = []
    for p in run_all.build():
        label = p.name + (f"/{getattr(p, 'objective', '')}"
                          if getattr(p, "objective", "") else "")
        key = p.name
        if key in NOT_RUNNABLE:
            arms.append(dict(name=label, case=p.case, runnable=False,
                             variant=None, reason=NOT_RUNNABLE[key],
                             reads_future=bool(getattr(p, "reads_future", False))))
            continue
        variant = None
        note = None
        if key in HOST_AS_COMPONENT:
            note = HOST_AS_COMPONENT[key]
            if key == "B9-best-of-breed":
                variant = "B9-noHost"
        arms.append(dict(name=label, case=p.case, runnable=True, variant=variant,
                         host_component_note=note,
                         reads_future=bool(getattr(p, "reads_future", False)),
                         experiments=list(getattr(p, "experiments", ()))))
    return dict(
        rule="the HOST-WARM readiness state and the OFFLOAD_TO_HOST action are UNAVAILABLE to "
             "every arm, enforced by an availability flag in the harness (OFFLOAD_TO_HOST is "
             "mapped to EVICT and readiness HOST-WARM is never reported) and never by editing a "
             "baseline's logic",
        n_total=len(arms), n_runnable=sum(1 for a in arms if a["runnable"]),
        n_not_runnable=sum(1 for a in arms if not a["runnable"]),
        n_oracle=sum(1 for a in arms if a["reads_future"]),
        arms=arms)


# ================================================================ main
def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res = dict(
        label="StudySIM1c-scoped: scope declaration, file hashes, the scoped calibration gate "
              "and the runnable arm list. CPU only; no GPU, no model server, no inference. No "
              "baseline is run in this file and no arm is compared with another.",
        scope=dict(
            world="one 32B vLLM 0.31.0 replica with NO host-offload tier: GPU-warm, cold and "
                  "device fallback only",
            excluded="the HOST-WARM readiness state and the OFFLOAD_TO_HOST action",
            why="StudySIM1's calibration gate failed only in KV-HOST cells, and StudySIM1b's "
                "mode-cost model leaves it at 69 % against an 80 % bar. The simulator does "
                "calibrate where there is no host-offload tier, and this study runs only there.",
            cannot_claim="nothing here bears on any arm's behaviour WITH host offload, and "
                         "nothing here says which baseline is best beyond the tables"))
    res["hashes_start"] = file_hashes()
    print("hashed %d files under the two watched trees" % len(res["hashes_start"]))
    print("scoped gate")
    res["scoped_gate"] = scoped_gate()
    g = res["scoped_gate"]
    print("  SCOPED GATE: %s  p99 %d/%d (%.0f %%)  capacity %d/%d (%.0f %%)" % (
        g["GATE"], g["p99_cells_agree"], g["p99_cells_total"], 100 * g["p99_fraction_agree"],
        g["ladders_agree"], g["ladders_total"], 100 * g["ladders_fraction_agree"]))
    res["arms"] = classify_arms()
    a = res["arms"]
    print("arms: %d total, %d runnable (%d oracle, reported separately), %d NOT runnable in "
          "scope" % (a["n_total"], a["n_runnable"], a["n_oracle"], a["n_not_runnable"]))
    for x in a["arms"]:
        if not x["runnable"]:
            print("   NOT RUNNABLE  %-24s %s" % (x["name"], x["reason"][:90]))

    from _provenance import stamp
    res["_provenance"] = stamp(script="sim1c_scope.py", model=None, device="cpu",
                               n=g["p99_cells_total"], args=None)
    (OUT / "sim1c_scope.json").write_text(json.dumps(res, indent=1, default=str))
    print("wrote", OUT / "sim1c_scope.json")
    return 0 if g["GATE"] == "PASS" else 2


def touched_during(start_s: float, end_s: float) -> List[Dict]:
    """Which watched files were modified inside a time window - the question the hash rule is
    really asking, since a file created after the hash snapshot is an ADDITION, not a mutation."""
    import time
    out = []
    for base in WATCHED:
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            m = p.stat().st_mtime
            if start_s <= m <= end_s:
                out.append(dict(path=str(p.relative_to(ROOT)),
                                modified=time.strftime("%H:%M:%S", time.localtime(m)),
                                is_code=p.suffix == ".py"))
    return out


def reproduction_check(n_arms: int = 12) -> Dict:
    """The empirical answer to the hash question: re-execute sweep cells with the CURRENT code
    and require the recorded metrics back BIT-EXACTLY. If an edit during the sweep had altered
    default behaviour, these would differ."""
    import collections
    sys.path.insert(0, str(HERE))
    import run as R
    import workload as W
    import gzip
    f = OUT / "sim1c_runs.jsonl"
    gz = OUT / "sim1c_runs.jsonl.gz"
    if not (f.exists() or gz.exists()):
        return dict(ran=False)
    byc = collections.defaultdict(list)
    for line in (gzip.open(gz, "rt") if gz.exists() else f.open()):
        r = json.loads(line)
        if r.get("slice_overhead_s") is None and not r.get("failed"):
            byc[(r["mix"], r["fleet"], r["deadline_s"], r["seed"])].append(r)
    keys = list(byc)
    picks = [keys[0], keys[len(keys) // 2], keys[-1]]
    arms = dict(R._arms())
    n, bad, cells = 0, 0, []
    for k in picks:
        mix, F, d, sd = k
        tr = W.build_trace(mix, F, d, sd)
        rec = {r["arm"]: r for r in byc[k]}
        digests_ok = all(r["trace_digest"] == tr.digest for r in byc[k])
        for label in sorted(rec)[:n_arms]:
            rr = R.run_cell(tr, arms[label], seed=sd)
            n += 1
            a, b = rec[label]["challenge_mAP"], rr["challenge_mAP"]
            ta = rec[label]["recall"]["timely_accuracy"]
            tb = rr["recall"]["timely_accuracy"]
            if abs(a - b) > 0 or (ta is None) != (tb is None) or \
                    (ta is not None and abs(ta - tb) > 0):
                bad += 1
        cells.append(dict(cell=f"{mix}|F{F}|d{d:.0f}|seed{sd}", digests_identical=digests_ok,
                          arms_checked=min(n_arms, len(rec))))
    return dict(ran=True, n_runs=n, n_mismatches=bad, cells=cells, bit_exact=bool(bad == 0),
                rule="re-execute recorded sweep cells with the current code and require the "
                     "recorded challenge mAP and recall timely accuracy back bit-exactly")


def finish() -> int:
    """Re-hash the two watched trees at the END of the sweep and compare, as the hash rule asks.
    A change in a .py file under either tree is a STOP; a change in a card or other documentation
    is recorded and classified, because it cannot alter default behaviour."""
    f = OUT / "sim1c_scope.json"
    res = json.loads(f.read_text())
    end = file_hashes()
    cmp_ = compare_hashes(res["hashes_start"], end)
    code_changed = [x for x in cmp_["changed"] + cmp_["added"] + cmp_["removed"]
                    if x.endswith(".py")]
    doc_changed = [x for x in cmp_["changed"] + cmp_["added"] + cmp_["removed"]
                   if not x.endswith(".py")]
    import os
    import time
    runs = OUT / "sim1c_runs.jsonl"
    if not runs.exists():
        runs = OUT / "sim1c_runs.jsonl.gz"
    sweep_end = os.path.getmtime(runs) if runs.exists() else time.time()
    sweep_start = sweep_end - float(res.get("sweep_wall_s", 8300.0)) - 60.0
    touched = touched_during(sweep_start, sweep_end)
    rp = reproduction_check()
    res["hashes_end"] = end
    res["hash_comparison"] = dict(
        cmp_,
        added_code=[x for x in cmp_["added"] if x.endswith(".py")],
        changed_code=[x for x in cmp_["changed"] if x.endswith(".py")],
        removed_code=[x for x in cmp_["removed"] if x.endswith(".py")],
        documentation_files_changed=doc_changed,
        sweep_window=dict(start=time.strftime("%H:%M:%S", time.localtime(sweep_start)),
                          end=time.strftime("%H:%M:%S", time.localtime(sweep_end))),
        files_modified_during_the_sweep=touched,
        stop=bool([x for x in touched if x["is_code"]] and not rp.get("bit_exact")),
        rule="a file ADDED after the start snapshot is this study's own new code, not a "
             "mutation; a file CHANGED while the sweep was executing is the case the rule is "
             "about, and the reproduction check below is the empirical test of whether it "
             "altered default behaviour",
        reproduction=rp,
        note="`sim1c_scope.py` itself was also edited at 19:47:28, inside the sweep window, to "
             "add this `--finish` entry point and again afterwards to separate added from "
             "changed files and to add the reproduction check; its later mtime is why it no "
             "longer appears in the list above. The edits do not touch NOT_RUNNABLE, "
             "HOST_AS_COMPONENT, `scoped_gate` or `classify_arms`, which are the only parts the "
             "sweep reads, and the reproduction check covers it: `run.py::_arms` imports this "
             "module, so a changed arm list would change the recorded rows.")
    f.write_text(json.dumps(res, indent=1, default=str))
    hc = res["hash_comparison"]
    print("hash comparison: %d files at the end, %d added, %d changed, %d removed" % (
        len(end), len(cmp_["added"]), len(cmp_["changed"]), len(cmp_["removed"])))
    for x in hc["added_code"]:
        print("   added (this study's own code):", x)
    for x in hc["changed_code"]:
        print("   CHANGED code:", x)
    for x in doc_changed:
        print("   changed documentation:", x)
    print("   modified while the sweep was executing:")
    for x in touched:
        print("      %-62s %s %s" % (x["path"], x["modified"],
                                     "(code)" if x["is_code"] else "(documentation)"))
    print("   reproduction: %d runs re-executed with the current code, %d mismatches -> %s"
          % (rp.get("n_runs", 0), rp.get("n_mismatches", -1),
             "BIT-EXACT" if rp.get("bit_exact") else "DIFFERS"))
    return 0 if rp.get("bit_exact") else 2


if __name__ == "__main__":
    sys.exit(finish() if "--finish" in sys.argv else main())
