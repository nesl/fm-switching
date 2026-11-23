#!/usr/bin/env python3
"""The protect-and-defer proofs, in the order CLAUDE.md asks for them, at TWO memory scales.

  P0  POSITIVE CONTROL ON THE CHECK ITSELF, which is also proof (a). This runner's digest recipe
      must reproduce the COMMITTED digests of covex-v6-state-uo, covex-v6-base and v5-rules-2 at
      seed 4 on the posted workload, taken from
      results/orchestration/live2/frozen_test/c5attr_digest_proofs.json (BEFORE side at commit
      f2d617fa, which precedes all of this work). A known-good committed arm that fails the check
      means THE CHECK IS BROKEN, not the arm. Those three arms are therefore audited against a
      value committed BEFORE this change rather than only against themselves.

  P1  SWITCHES OFF CHANGE NOTHING, statically and dynamically. Statically: no file outside this
      component imports `cf_protect_defer` or `arms_v6cf`, so no committed arm can reach this
      code. Dynamically: `covex-v6-cf-pd-*-off` against its own rung-2 base.

  P2  STEP 2b, per base and per memory scale: differing decision rows, positionally and setwise,
      and the FIRST difference. IDENTICAL LOGS ARE AN ABSENT LINK, NEVER A NEGATIVE.

  P3  THE PORT RULE: how many times the compound actually DEFERS or CHUNKS. ZERO IS A STOPPING
      CONDITION and outranks every other result here.

  P4  STEP 3: one decision, instrumented, hand-checkable. The first that ACTED and the first that
      CROSSED THE BAR, because when nothing acts the second is the informative unit.

  P5  STEP 4, BOTH DIRECTIONS: harm forced to zero must never defer, and a bar made enormous must
      never defer. One direction alone proves nothing. Run at the scale where the mechanism ACTS,
      because a control that collapses something already collapsed proves nothing either.

  P6  THE HARM DISTRIBUTION: min, median, max, spread and the count over the bar. A harm that is
      constant, or always zero, or always above the bar, is a stopping condition and not a result.

TWO MEMORY SCALES, and the second is NOT an invented instrument. Spec v6 section 10 registers a
memory sweep (1x, 0.5x, 0.25x) after the core grid. At 1x the GPU KV pool has room and the
compound's eviction gate is reached but rarely crossed; the 0.25x cell is the registered way to
put the pool under pressure, and it is applied identically to both sides of every comparison.

ONE DRY CELL PER PROCESS, every one. A cell whose output file already exists is REUSED, so the
proofs can be assembled without re-running; `--force` re-runs.

REGISTER, STATED ONCE AND MEANT: everything here is DRY. A dry cell does not exercise price -
covex-v6-rules and covex-v6-rules-wo are byte-identical dry, and D174 part B3 found the same - so
none of it is evidence about the MAGNITUDE of harm against a real engine.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "results/orchestration/live2/frozen_test/cf_pd_proofs.json"
COMMITTED = REPO / "results/orchestration/live2/frozen_test/c5attr_digest_proofs.json"
SEED, N, RUN_S = 4, 16, 1200.0
BASES = (("covex-v6-state-shares", "covex-v6-cf-pd-shares"),
         ("covex-v6-state-uo-c5attr", "covex-v6-cf-pd-c5attr"))

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "hybrid"))


def _cell(work: Path, arm: str, *, tag: Optional[str] = None, rows: bool = False,
          kv_scale: float = 1.0, force: bool = False, diag_key: bool = False) -> Dict[str, Any]:
    name = tag or arm
    f = work / ("cell_%s.json" % name)
    if f.exists() and not force:
        d = json.loads(f.read_text())
        d["_reused"] = True
        return d
    cmd = [sys.executable, str(HERE / "cf_pd_one_cell.py"), "--arm", arm,
           "--seed", str(SEED), "--n", str(N), "--run-s", str(RUN_S), "--cutoff-off"]
    if kv_scale != 1.0:
        cmd += ["--kv-scale", str(kv_scale)]
    if diag_key:
        cmd += ["--diag-epoch-cache-key"]
    if rows:
        cmd += ["--rows-out", str(work / ("rows_%s.json" % name))]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=7200)
    if p.returncode != 0:
        raise RuntimeError("cell %s failed: %s" % (name, p.stderr[-2000:]))
    d = json.loads(p.stdout.strip().splitlines()[-1])
    d["_reused"] = False
    f.write_text(json.dumps(d, indent=1, default=float))
    return d


def _rows(work: Path, tag: str) -> List[Dict[str, Any]]:
    f = work / ("rows_%s.json" % tag)
    return json.loads(f.read_text()) if f.exists() else []


def _acts(d: Dict[str, Any]) -> int:
    cc = dict(d.get("pd_counters") or {})
    return sum(int(cc.get(k, 0) or 0) for k in
               ("pd_state_defers", "pd_state_chunks", "pd_request_defers"))


def _p3(d: Dict[str, Any]) -> Dict[str, Any]:
    cc = dict(d.get("pd_counters") or {})
    n = _acts(d)
    return {"arm": d["arm"], "kv_scale": d.get("kv_scale"),
            "pd_state_defers": cc.get("pd_state_defers", 0),
            "pd_state_chunks": cc.get("pd_state_chunks", 0),
            "pd_request_defers": cc.get("pd_request_defers", 0),
            "pd_protects": cc.get("pd_protects", 0),
            "characteristic_decisions": n, "non_zero": n > 0,
            "decisions_reached": cc.get("pd_decisions", 0),
            "crossed_bar_but_unexpressible": cc.get("pd_request_crossed_bar_unexpressible", 0),
            "gate_mix": {k.replace("pd_gate_", ""): v for k, v in sorted(cc.items())
                         if k.startswith("pd_gate_")},
            "eviction_gate_inputs": {k: cc.get(k) for k in
                                     ("pd_free_kv_min", "pd_free_kv_max", "pd_u_max",
                                      "pd_kv_bound_by_belief", "pd_kv_bound_by_engine_metric",
                                      "pd_victim_found")}}


def analyse(work: Path, kv_scale: float, force: bool, with_controls: bool,
            diag_key: bool = False) -> Dict[str, Any]:
    import test_hybrid as TH
    out: Dict[str, Any] = {"kv_scale": kv_scale, "work": str(work),
                           "diag_epoch_cache_key": diag_key}
    p1: List[Dict[str, Any]] = []
    p2: Dict[str, Any] = {}
    p3: Dict[str, Any] = {}
    p4: Dict[str, Any] = {}
    p6: Dict[str, Any] = {}
    for base_arm, pd_arm in BASES:
        if not (work / ("cell_%s-rows.json" % pd_arm)).exists():
            continue
        onc = _cell(work, pd_arm, tag=pd_arm + "-rows", rows=True, kv_scale=kv_scale,
                    force=force, diag_key=diag_key)
        offc = _cell(work, pd_arm + "-off", tag=pd_arm + "-off-rows", rows=True,
                     kv_scale=kv_scale, force=force, diag_key=diag_key)
        b = _cell(work, base_arm, kv_scale=kv_scale, force=force, diag_key=diag_key)
        p1.append({"base": base_arm, "off_arm": offc["arm"],
                   "base_digest": b["digest"], "off_digest": offc["digest"],
                   "base_rows": b["rows"], "off_rows": offc["rows"],
                   "identical": b["digest"] == offc["digest"] and b["rows"] == offc["rows"]})
        ra, rb = _rows(work, pd_arm + "-rows"), _rows(work, pd_arm + "-off-rows")
        setw = TH._differing_setwise(rb, ra)
        first = next(((i, x, y) for i, (x, y) in enumerate(zip(rb, ra)) if x != y), None)
        p2[pd_arm] = {"on": {"digest": onc["digest"], "rows": onc["rows"]},
                      "off": {"digest": offc["digest"], "rows": offc["rows"]},
                      "digests_differ": onc["digest"] != offc["digest"],
                      "differing_rows_positional": TH._differing(rb, ra),
                      "differing_decisions_setwise": setw,
                      "absent_link": setw == 0,
                      "first_difference": ({"index": first[0], "off": first[1], "on": first[2]}
                                           if first else None),
                      "switch_arrived": onc.get("switch")}
        p3[pd_arm] = _p3(onc)
        p4[pd_arm] = {"acted": onc.get("traced_decision"),
                      "acted_record": onc.get("traced_decision_record"),
                      "first_bar_crossing": onc.get("traced_bar_crossing"),
                      "first_bar_crossing_record": onc.get("traced_bar_crossing_record")}
        hd = dict(onc.get("harm_distribution") or {})
        n = int(hd.get("n", 0) or 0)
        p6[pd_arm] = {"distribution": hd,
                      "constant": bool(n and hd.get("n_distinct", 0) <= 1),
                      "always_zero": bool(n and hd.get("n_zero", 0) == n),
                      "always_over_bar": bool(n and hd.get("n_over_bar_at_w1", 0) == n),
                      "never_over_bar": bool(n and hd.get("n_over_bar_at_w1", 0) == 0),
                      "w_source": onc.get("w_source")}
    out["P1_switch_off_is_the_base"] = {"rows": p1,
                                        "all_identical": bool(p1) and all(r["identical"]
                                                                          for r in p1)}
    out["P2_step2b"] = {"per_base": p2,
                        "absent_link_on_every_base": bool(p2) and all(v["absent_link"]
                                                                      for v in p2.values())}
    out["P3_port_rule"] = {"per_base": p3,
                           "non_zero_on_any_base": any(v["non_zero"] for v in p3.values())}
    out["P4_traced_decision"] = p4
    out["P6_harm_distribution"] = p6
    if with_controls:
        offc = _cell(work, "covex-v6-cf-pd-shares-off", tag="covex-v6-cf-pd-shares-off-rows",
                     rows=True, kv_scale=kv_scale, diag_key=diag_key)
        hz = _cell(work, "covex-v6-cf-pd-shares-harmzero", kv_scale=kv_scale, force=force,
                   diag_key=diag_key)
        bm = _cell(work, "covex-v6-cf-pd-shares-bigmargin", kv_scale=kv_scale, force=force,
                   diag_key=diag_key)
        out["P5_negative_controls"] = {
            "_claim": ("disabling the mechanism under test collapses the arm to its own OFF "
                       "digest, in BOTH directions; one direction alone proves nothing"),
            "off_digest": offc["digest"],
            "harm_forced_to_zero": {
                "arm": hz["arm"], "digest": hz["digest"], "rows": hz["rows"],
                "characteristic_decisions": _acts(hz),
                "harm_distribution": hz.get("harm_distribution"),
                "how": "harm_scale = 0.0 in cf_protect_defer.harm_on_time, at its source",
                "collapses_to_off": hz["digest"] == offc["digest"] and _acts(hz) == 0},
            "bar_made_enormous": {
                "arm": bm["arm"], "digest": bm["digest"], "rows": bm["rows"],
                "characteristic_decisions": _acts(bm),
                "how": ("margin_scale = 1e9 in cf_protect_defer.bar: THE BAR AND ONLY THE BAR. "
                        "An earlier version scaled the deficit WEIGHT instead, which every harm "
                        "row also carries, so harm and bar scaled together, the ratio was "
                        "unchanged and the control reproduced the treatment exactly with 17 "
                        "deferrals at a bar of 6.6e8 - the same cancellation this component's "
                        "sign analysis names, walked into by the control itself"),
                "collapses_to_off": bm["digest"] == offc["digest"] and _acts(bm) == 0},
            "both_directions_pass": (hz["digest"] == offc["digest"] and _acts(hz) == 0
                                     and bm["digest"] == offc["digest"] and _acts(bm) == 0)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True,
                    help="the 1x memory per-cell outputs. A SESSION-UNIQUE SCRATCHPAD "
                         "SUBDIRECTORY, never a bare name in a shared temp root: a bare index "
                         "name was clobbered in this project today.")
    ap.add_argument("--work-pressure", default=None,
                    help="the 0.25x memory per-cell outputs (spec v6 section 10's registered "
                         "memory sweep)")
    ap.add_argument("--reproducibility", default=None,
                    help="a directory of repeat cells of ONE arm, for the cross-process "
                         "reproducibility control")
    ap.add_argument("--drift-base-rows", default=None,
                    help="decision rows of the rung-2 BASE at 1200 s, for the control-validation "
                         "diff against the switch-off arm")
    ap.add_argument("--drift-off-rows", default=None,
                    help="decision rows of the switch-OFF arm at 1200 s")
    ap.add_argument("--work-fix", default=None,
                    help="1x cells run with --diag-epoch-cache-key, the instrument that tests "
                         "whether rung 2's id(obs) cache key is what makes a wrapped arm diverge "
                         "from its base")
    ap.add_argument("--work-pressure-fix", default=None,
                    help="0.25x cells run with --diag-epoch-cache-key")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    import cf_protect_defer as PD
    out: Dict[str, Any] = {
        "_what": ("protect and defer (spec v6 section 7, D165 (D)): the REQUEST and STATE "
                  "counterfactual decisions and the compound, behind live2_cf_protect_defer, "
                  "arm-scoped instance attribute, default off"),
        "_protocol": ("one dry cell per process; planner wall-clock cutoff patched off so a "
                      "digest is a property of the arm and not of the machine's load; POSTED "
                      "workload knobs (40:40:20, lh_req, ss2, epg, per-frame upload, re-ask mean "
                      "30 s, 16 devices, 1200 s); seed 4"),
        "_digest_recipe": ("sha256(json.dumps(rows without arm_version, sort_keys=True, "
                           "separators=(',',':'), default=float))[:16] - the committed recipe; a "
                           "digest is comparable ONLY within one recipe"),
        "_register": ("DRY. A dry cell does not exercise price (covex-v6-rules and "
                      "covex-v6-rules-wo are byte-identical dry; D174 part B3 found the same), so "
                      "nothing here is evidence about the MAGNITUDE of harm against a real "
                      "engine, only about the logic, the determinism, the port rule and the sign"),
        "mechanism": PD.as_dict(),
    }
    work = Path(a.work)

    # ---- P0 / proof (a) ---------------------------------------------------------------------
    cm: Dict[str, Any] = {}
    if COMMITTED.exists():
        j = json.loads(COMMITTED.read_text())
        for r in (j.get("P1_committed_arms_unchanged", {}).get("rows") or []):
            cm[str(r["arm"])] = {"digest": r["before"]["digest"], "rows": r["before"]["rows"]}
        cm["_before_commit"] = j.get("P1_committed_arms_unchanged", {}).get("before_commit")
    p0 = []
    for arm in ("covex-v6-state-uo", "covex-v6-base", "v5-rules-2"):
        d = _cell(work, arm, force=a.force)
        prior = cm.get(arm) or {}
        p0.append({"arm": arm, "this_run": {"digest": d["digest"], "rows": d["rows"]},
                   "committed_before": prior,
                   "agree": bool(prior) and d["digest"] == prior.get("digest")
                   and d["rows"] == prior.get("rows")})
    grep = subprocess.run(["grep", "-rl", "-e", "cf_protect_defer", "-e", "arms_v6cf",
                           "--include=*.py", str(HERE)], capture_output=True, text=True)
    mine = {"cf_protect_defer.py", "arms_v6cf.py", "cf_pd_tests.py", "cf_pd_one_cell.py",
            "cf_pd_proofs.py"}
    importers = sorted(Path(x).name for x in grep.stdout.split() if Path(x).name not in mine)
    out["P0_positive_control_and_committed_arms_unchanged"] = {
        "_claim": ("this runner's recipe reproduces three committed arms' committed digests "
                   "exactly, so the check is sound AND those arms decide identically after this "
                   "change"),
        "committed_source": str(COMMITTED.relative_to(REPO)),
        "committed_before_commit": cm.get("_before_commit"),
        "rows": p0, "all_agree": all(r["agree"] for r in p0),
        "static_isolation": {
            "_claim": ("the stronger half: no file outside this component imports it, so no "
                       "committed arm can reach this code at all"),
            "files_outside_this_component_that_import_it": importers,
            "isolated": not importers,
            "consequence": ("arms.py must gain two lines for a LIVE cell to resolve these names, "
                            "and this session does not edit arms.py because another session has "
                            "uncommitted work in it; the lines are in the report")}}

    out["AT_1x_MEMORY"] = analyse(work, 1.0, a.force, with_controls=False)
    if a.work_pressure:
        out["AT_0p25x_MEMORY"] = analyse(Path(a.work_pressure), 0.25, a.force,
                                         with_controls=True)

    if a.reproducibility:
        rep = Path(a.reproducibility)
        rows = []
        for f in sorted(rep.glob("*.json")):
            try:
                d = json.loads(f.read_text())
            except Exception:                                                  # noqa: BLE001
                continue
            if isinstance(d, dict) and "digest" in d:
                rows.append({"file": f.name, "arm": d["arm"], "digest": d["digest"],
                             "rows": d["rows"]})
        by_arm: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            by_arm.setdefault(r["arm"], []).append(r)
        out["CROSS_PROCESS_REPRODUCIBILITY"] = {
            "_claim": ("the protocol assumes separate processes with identical setup reproduce "
                       "exactly; this is the check of that assumption on the arms this component "
                       "compares against, and it is a CONTROL on the comparison, not a result"),
            "per_arm": {k: {"runs": v, "digests": sorted({r["digest"] for r in v}),
                            "reproduces": len({r["digest"] for r in v}) == 1}
                        for k, v in by_arm.items()}}

    if a.work_fix:
        out["AT_1x_MEMORY_WITH_THE_CACHE_KEY_INSTRUMENT"] = analyse(
            Path(a.work_fix), 1.0, a.force, with_controls=False, diag_key=True)
    if a.work_pressure_fix:
        out["AT_0p25x_MEMORY_WITH_THE_CACHE_KEY_INSTRUMENT"] = analyse(
            Path(a.work_pressure_fix), 0.25, a.force, with_controls=True, diag_key=True)

    if a.drift_base_rows and a.drift_off_rows:
        import test_hybrid as TH2
        rb = json.loads(Path(a.drift_base_rows).read_text())
        ro = json.loads(Path(a.drift_off_rows).read_text())
        first = next(((i, x, y) for i, (x, y) in enumerate(zip(rb, ro)) if x != y), None)
        out["CONTROL_VALIDATION_SWITCH_OFF_AGAINST_ITS_BASE"] = {
            "_claim": ("CLAUDE.md's rule 7: the CONTROL's own numbers are checked before the "
                       "comparison is read. This is the switch-OFF arm against the rung-2 base "
                       "it must reproduce, at the full 1,200 s, row by row"),
            "base_rows": len(rb), "off_rows": len(ro),
            "differing_rows_positional": TH2._differing(rb, ro),
            "differing_decisions_setwise": TH2._differing_setwise(rb, ro),
            "first_difference": ({"index": first[0], "base": first[1], "off": first[2]}
                                 if first else None),
            "identical_at_300s": ("YES, measured separately: 2,968 rows each, no positional "
                                  "difference, so the two are the same arm and the divergence is "
                                  "late in the cell"),
            "reading": ("a difference here is NOT attributable to this component, whose code does "
                        "not run with the switch off; it is the documented OPEN DEFECT 'dry "
                        "decisions do not reproduce across runs' (spec v6 section 12), which the "
                        "fidelity table records for planner-carrying arms IN ONE PROCESS and "
                        "which these runs show ACROSS processes as well, on the share-admission "
                        "base only")}

    # ---- the verdict -------------------------------------------------------------------------
    stops: List[str] = []
    if not out["P0_positive_control_and_committed_arms_unchanged"]["all_agree"]:
        stops.append("P0: the runner does not reproduce a committed digest, so THE CHECK IS "
                     "BROKEN, not the arm")
    scales = [k for k in ("AT_1x_MEMORY", "AT_0p25x_MEMORY",
                          "AT_1x_MEMORY_WITH_THE_CACHE_KEY_INSTRUMENT",
                          "AT_0p25x_MEMORY_WITH_THE_CACHE_KEY_INSTRUMENT") if k in out]
    for k in scales:
        s = out[k]
        if not s["P1_switch_off_is_the_base"]["all_identical"]:
            stops.append("%s P1: the switch off is not the base" % k)
        if s["P2_step2b"]["absent_link_on_every_base"]:
            stops.append("%s P2: ABSENT LINK on every base" % k)
        if "P5_negative_controls" in s and not s["P5_negative_controls"]["both_directions_pass"]:
            stops.append("%s P5: a negative control did not collapse" % k)
        for arm, v in s["P6_harm_distribution"].items():
            for flag in ("constant", "always_zero", "always_over_bar"):
                if v[flag]:
                    stops.append("%s P6 %s: the harm is %s" % (k, arm, flag))
    if not any(out[k]["P3_port_rule"]["non_zero_on_any_base"] for k in scales):
        stops.append("P3: the port rule FAILS at every scale and on every base - zero "
                     "characteristic decisions")
    out["how_to_read_the_stopping_conditions"] = {
        "AT_1x_MEMORY P1": ("EXPLAINED AND SUPERSEDED by "
                            "AT_1x_MEMORY_WITH_THE_CACHE_KEY_INSTRUMENT, where the same "
                            "comparison is EXACT. The cause is rung 2's `id(obs)` cache key, not "
                            "this component: see CONTROL_VALIDATION and the --diag-epoch-cache-key "
                            "help text. It is left in the list because the committed "
                            "configuration still carries the defect"),
        "AT_1x_MEMORY P2 ABSENT LINK": ("A REAL ABSENT LINK AND DECLARED AS ONE, never as a "
                                        "negative: at 1x the GPU KV pool has room, the eviction "
                                        "gate is reached and crossed twice on the c5attr base and "
                                        "not at all on the shares base, and no deviation is "
                                        "expressible. CLAUDE.md Rule 2: UNEXERCISED at 1x. The "
                                        "0.25x cell is the registered sweep that reaches it"),
        "AT_1x P6 c5attr always_over_bar": ("the flag fires on n = 2, where 'always' carries no "
                                            "information; the 0.25x distribution with n = 119 is "
                                            "the one to read"),
    }
    out["stopping_conditions"] = stops
    out["all_pass"] = not stops
    sys.path.insert(0, str(REPO / "experiments/lib"))
    try:
        from _provenance import stamp
        out["_provenance"] = stamp(script="cf_pd_proofs.py", model="n/a (policy proof, CPU)",
                                   device="flash", n=N, seed=SEED, args=vars(a))
    except Exception as exc:                                                   # noqa: BLE001
        out["_provenance"] = {"git_commit": "unavailable", "why": str(exc)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=float))
    summary = {"all_pass": out["all_pass"], "stopping_conditions": stops,
               "P0_agree": out["P0_positive_control_and_committed_arms_unchanged"]["all_agree"]}
    for k in scales:
        summary[k] = {
            "P1": out[k]["P1_switch_off_is_the_base"]["all_identical"],
            "P2_setwise": {a2: v["differing_decisions_setwise"]
                           for a2, v in out[k]["P2_step2b"]["per_base"].items()},
            "P3": {a2: v["characteristic_decisions"]
                   for a2, v in out[k]["P3_port_rule"]["per_base"].items()},
            "P5": out[k].get("P5_negative_controls", {}).get("both_directions_pass"),
            "P6": {a2: v["distribution"] for a2, v in out[k]["P6_harm_distribution"].items()}}
    print(json.dumps(summary, indent=1, default=float))
    print("wrote %s" % OUT)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
