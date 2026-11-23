#!/usr/bin/env python3
"""Assemble the D190/D191 rung-4 proofs into ONE JSON, from the battery's cell outputs.

Run with the repo CLEAN CHECKOUT dir as argv[1] and the cell output dir as argv[2].
Nothing here recomputes a digest: it reads the digests `cf_pd_one_cell` produced.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

TREE = Path(sys.argv[1]).resolve()
CELLS = Path(sys.argv[2]).resolve()
COMMIT = sys.argv[3]
LIVE2 = TREE / "experiments/orchestration/live2"
PY = "/home/pragya/miniconda3/envs/fmtk/bin/python"

POSTED_CLI = ["--ratio", "40:40:20", "--robot-question-set", "lh_req",
              "--ss-question-set", "ss2", "--dashcam-format", "epg",
              "--robot-upload", "per-frame", "--robot-reask-mean-s", "30.0"]

# The COMMITTED bars. Source for each is named so a reader can check it, and a first run with no
# committed bar is labelled as such rather than quietly becoming its own bar.
COMMITTED = {
    "covex-v6-base": ("af8befb9420ad86a", 12085,
                      "results/orchestration/live2/frozen_test/c5attr_digest_proofs.json"),
    "covex-v6-state-uo-c5attr": ("9a4be873eb3c5fba", 14218,
                                 "results/orchestration/live2/frozen_test/"
                                 "d185_fair_c5attr_gate.json (2_off_switch_identity.base_digest)"),
    "covex-v6-fair-c5attr": ("12e4f73ce0ebd865", 13812,
                             "results/orchestration/live2/frozen_test/"
                             "d185_fair_c5attr_gate.json (1_step2b...both_consumers)"),
}


def cell(lab: str) -> Optional[Dict[str, Any]]:
    p = CELLS / (lab + ".json")
    # A reader doing `json.load(open(p)) if exists(p) else {}` silently returns an EMPTY DICT for
    # a cell that crashed and wrote nothing. Both cases are handled and a MISSING cell FAILS
    # LOUDLY here rather than becoming a zero downstream.
    if not p.exists():
        raise SystemExit("MISSING CELL FILE %s - refusing to report a proof over it" % p)
    txt = p.read_text().strip()
    if not txt:
        err = (CELLS / (lab + ".err"))
        raise SystemExit("EMPTY CELL FILE %s; stderr tail: %s"
                         % (p, (err.read_text()[-800:] if err.exists() else "<none>")))
    return json.loads(txt.splitlines()[-1])


def rows(lab: str) -> List[Dict[str, Any]]:
    p = CELLS / (lab + ".rows.json")
    if not p.exists() or not p.stat().st_size:
        raise SystemExit("MISSING OR EMPTY ROWS FILE %s" % p)
    return json.loads(p.read_text())


def rd(lab: str) -> Dict[str, Any]:
    p = CELLS / (lab + ".rd.json")
    if not p.exists() or not p.stat().st_size:
        return {"present": False}
    return json.loads(p.read_text())


def diff(a_lab: str, b_lab: str) -> Dict[str, Any]:
    """Step 2b: how many decisions differ, and the FIRST one. Setwise and positional, which is
    the pair the committed rung-3 gate reports, so the numbers are comparable with it."""
    A, B = rows(a_lab), rows(b_lab)
    ka = [json.dumps(r, sort_keys=True, separators=(",", ":"), default=float) for r in A]
    kb = [json.dumps(r, sort_keys=True, separators=(",", ":"), default=float) for r in B]
    sa, sb = set(ka), set(kb)
    setwise = len(sa ^ sb)
    pos = 0
    first = None
    for i in range(max(len(ka), len(kb))):
        x = ka[i] if i < len(ka) else None
        y = kb[i] if i < len(kb) else None
        if x != y:
            pos += 1
            if first is None:
                first = {"index": i,
                         "A": (json.loads(x) if x else None),
                         "B": (json.loads(y) if y else None)}
    return {"A": a_lab, "B": b_lab, "rows_A": len(A), "rows_B": len(B),
            "differing_setwise": setwise, "differing_positional": pos,
            "identical": bool(setwise == 0 and pos == 0),
            "first_difference": first}


def name_probe(arm: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="d190name_") as td:
        p = subprocess.run(
            [PY, str(LIVE2 / "run_live2_real.py"), "--arm", arm,
             "--out", str(Path(td) / "cell"), "--n-devices", "2", "--run-s", "5",
             "--seed", "4"] + POSTED_CLI,
            cwd=str(LIVE2), capture_output=True, text=True, timeout=1800)
    blob = (p.stdout or "") + (p.stderr or "")
    return {"arm": arm, "returncode": p.returncode,
            "raised_unknown_arm": ("unknown arm" in blob),
            "tail": (blob.strip().splitlines()[-1][:300] if blob.strip() else "")}


def bar_check(lab: str) -> Dict[str, Any]:
    c = cell(lab)
    arm = c["arm"]
    if arm not in COMMITTED:
        return {"arm": arm, "this_run": [c["digest"], c["rows"]],
                "committed": None, "verdict": "FIRST RUN, NO COMMITTED BAR",
                "register": "labelled as a first run; it does not become its own bar"}
    d, n, src = COMMITTED[arm]
    ok = (c["digest"] == d and c["rows"] == n)
    return {"arm": arm, "this_run": [c["digest"], c["rows"]], "committed": [d, n],
            "source_of_prior": src, "verdict": ("PASS" if ok else "FAIL")}


def main() -> int:
    out: Dict[str, Any] = {}
    out["_what"] = (
        "D190 (3) / D191 items 1 and 2: the proofs for RUNG 4 ON THE RUNG-3 BASE "
        "(covex-v6-cf-c5attr) before any cell of it is posted. One JSON, as asked.")
    out["_register"] = (
        "EVERY cell below was run on a CLEAN `git archive` CHECKOUT of the commit named in "
        "_provenance, NOT in the shared worktree, ONE DRY CELL PER PROCESS, and at CONCURRENCY 1. "
        "Concurrency 1 is not caution: see host_load_hazard_measured.")
    out["cell"] = ("dry, seed 4, 16 devices, 1200 s, posted knobs (ratio 40:40:20, lh_req, ss2, "
                   "epg, per-frame, reask 30.0), planner wall-clock cutoff off")
    out["digest_recipe"] = ("sha256(json.dumps(rows_without_arm_version, sort_keys=True, "
                            "separators=(',',':'), default=float))[:16], computed by the "
                            "COMMITTED cf_pd_one_cell.py and not reimplemented here")
    out["concurrency"] = 1
    # The 1-minute load average AT THE START OF EACH CELL, recorded by the battery itself. It is
    # here because another session was running three concurrent dry cells in the same scratchpad
    # throughout, so "concurrency 1" is MINE and not the HOST'S, and that distinction is exactly
    # what moved a digest earlier today. The positive controls are what decide whether it mattered.
    blog = CELLS.parent / "d190_battery.log"
    out["host_load_at_each_cell_start"] = [
        ln.strip() for ln in (blog.read_text().splitlines() if blog.exists() else [])
        if ln.startswith("===")]
    out["concurrency_caveat"] = (
        "concurrency 1 FROM THIS SESSION. Another session ran three concurrent dry cells in the "
        "same scratchpad for part of this battery, so host load was 2 to 6 and is recorded per "
        "cell above. The three positive controls are the check on whether it perturbed anything.")

    # ---- 0. the import blocker, which is why this rung could be built at all ---------------
    imp = subprocess.run(
        [PY, "-c", "import sys; sys.path.insert(0,'experiments/orchestration/live2'); "
                   "import arms; print(len(arms.ARMS))"],
        cwd=str(TREE), capture_output=True, text=True, timeout=600)
    out["import_on_a_clean_checkout"] = {
        "_claim": ("`import arms` succeeds on a CLEAN COMMITTED checkout WITH rung 4 registered. "
                   "This was the standing blocker: cf_protect_defer.py:150 read "
                   "cf_objective.attainment_margin, which is in no commit, so on origin the "
                   "import raised AttributeError and EVERY ARM DIED AT CELL START (2026-11-22 "
                   "22:46, five gated cells). A SECOND read, cf_objective.ON_TIME_UNITS, raised "
                   "at RUN TIME on the first decision that reached the harm, which the import "
                   "fix alone did not surface."),
        "returncode": imp.returncode,
        "arms_registered": (imp.stdout or "").strip(),
        "verdict": "PASS" if imp.returncode == 0 else "FAIL",
        "stderr_tail": (imp.stderr or "").strip()[-300:],
        "both_fixes_are_derivation_or_reporting_only": {
            "MARGIN_CF_ON_TIME": ("prefers cf_objective.attainment_margin; otherwise "
                                  "cf_margin.MARGIN_CF / cf_ontime_frozen.A_D2_DEV, the same two "
                                  "committed constants the function divides. 0.65824, asserted."),
            "on_time_units": ("a REPORTED field. The harm call passes acc_cloud=1.0, "
                              "acc_device=0.0, under which the committed option_value is w * p, "
                              "which is exactly D177's branch. Nothing that decides moves."),
        },
        "track_A_status_at_measurement": ("cf_objective.attainment_margin is STILL NOT in any "
                                          "commit; the fallback path is the one in force, and "
                                          "every cell below records which path it used"),
    }

    # ---- 5. POSITIVE CONTROL FIRST. If a committed arm fails, the INSTRUMENT is broken. ----
    out["proof_5_positive_control"] = {
        "_claim": ("three COMMITTED arms reproduce their committed digests on this clean tree. "
                   "CLAUDE.md: an impossible failure and an impossible success are equally "
                   "diagnostic, and if a known-good arm fails, the check is broken, not the arm."),
        "cells": [bar_check(l) for l in ("pos_base", "pos_uo", "pos_fair")],
    }
    out["proof_5_positive_control"]["verdict"] = (
        "PASS" if all(c["verdict"] == "PASS"
                      for c in out["proof_5_positive_control"]["cells"]) else "FAIL")

    out["host_load_hazard_measured"] = {
        "_what": ("why every cell here runs ALONE. The same three arms were first run at "
                  "CONCURRENCY 3 on this host."),
        "at_concurrency_3": {"covex-v6-base": ["af8befb9420ad86a", 12085, "matched"],
                             "covex-v6-fair-c5attr": ["12e4f73ce0ebd865", 13812, "matched"],
                             "covex-v6-state-uo-c5attr": ["639cd15ed38c9da0", 14207,
                                                          "MISMATCH against 9a4be873eb3c5fba / "
                                                          "14,218"]},
        "alone": {"covex-v6-state-uo-c5attr": ["9a4be873eb3c5fba", 14218, "matched exactly"]},
        "reading": ("the rung-2 arm's dry digest is sensitive to host load and the two other arms' "
                    "are not, so a concurrent run can move one side of a comparison and not the "
                    "other. Consistent with the documented `id(obs)` cache key in "
                    "arms_v6state._queued_behind, which makes decisions depend on allocation "
                    "history; that fix stays OFF per D190 (6). Everything below is concurrency 1."),
    }

    # ---- 2. BYTE IDENTITY of other arms with the switch off --------------------------------
    out["proof_2_byte_identity_of_other_arms"] = {
        "_claim": ("the two committed files this work touched (cf_protect_defer.py, arms.py) move "
                   "NO other arm. Each arm below is a committed arm run on this tree, where the "
                   "rung-4 switches are default OFF and rung 4 is registered."),
        "cells": [bar_check(l) for l in ("pos_base", "pos_uo", "pos_fair")],
        "note": ("the rung-4 family is registered in arms.py in these very processes, so this "
                 "also proves the registration itself is additive and perturbs nothing"),
    }

    # ---- 3. OFF-SWITCH IDENTITY against the COMMITTED RUNG-3 cell digest -------------------
    off, fair = cell("r4_off"), cell("pos_fair")
    out["proof_3_off_switch_identity"] = {
        "_claim": ("covex-v6-cf-c5attr-off, with BOTH compounds off, is byte-identical to the "
                   "COMMITTED RUNG-3 arm. The bar is RUNG 3 (12e4f73ce0ebd865 / 13,812), NOT "
                   "rung 2 (9a4be873eb3c5fba / 14,218): checking the wrong one would credit "
                   "rung 4 with the rung below it."),
        "off_arm": {"arm": off["arm"], "digest": off["digest"], "rows": off["rows"]},
        "rung3_this_run": {"arm": fair["arm"], "digest": fair["digest"], "rows": fair["rows"]},
        "committed_rung3": list(COMMITTED["covex-v6-fair-c5attr"][:2]),
        "equals_rung3_this_run": bool(off["digest"] == fair["digest"]
                                      and off["rows"] == fair["rows"]),
        "equals_committed_rung3": bool(off["digest"] == COMMITTED["covex-v6-fair-c5attr"][0]
                                       and off["rows"] == COMMITTED["covex-v6-fair-c5attr"][1]),
        "diff": diff("r4_off", "pos_fair"),
    }
    out["proof_3_off_switch_identity"]["verdict"] = (
        "PASS" if (out["proof_3_off_switch_identity"]["equals_rung3_this_run"]
                   and out["proof_3_off_switch_identity"]["equals_committed_rung3"]) else "FAIL")

    # ---- 1. STEP 2b, on the base and at the memory settings the cells run at ---------------
    s2b: Dict[str, Any] = {
        "_claim": ("CLAUDE.md Step 2b, run BEFORE any cell is posted, on the RUNG-3 BASE the "
                   "cells will run on and at the MEMORY SETTING they will run at. Each leg "
                   "separately, which is addendum 12 item 5: a combined count that cannot be "
                   "attributed is not a pass."),
        "comparator": "covex-v6-cf-c5attr-off at the SAME memory setting",
    }
    s2b["a_protect_and_defer_at_1x"] = dict(
        diff("r4_pdonly", "r4_off"),
        arm="covex-v6-cf-c5attr-pdonly",
        counters=cell("r4_pdonly")["pd_counters"],
        gate_mix={k: v for k, v in cell("r4_pdonly")["pd_counters"].items()
                  if k.startswith("pd_gate_")},
        harm_distribution=cell("r4_pdonly").get("harm_distribution"),
        traced_decision=cell("r4_pdonly").get("traced_decision"),
    )
    s2b["b_protect_and_defer_at_0p25x"] = dict(
        diff("r4_pdonly_kv025", "r4_off_kv025"),
        arm="covex-v6-cf-c5attr-pdonly at --kv-scale 0.25",
        counters=cell("r4_pdonly_kv025")["pd_counters"],
        gate_mix={k: v for k, v in cell("r4_pdonly_kv025")["pd_counters"].items()
                  if k.startswith("pd_gate_")},
        harm_distribution=cell("r4_pdonly_kv025").get("harm_distribution"),
        traced_decision=cell("r4_pdonly_kv025").get("traced_decision"),
        matched_memory_control="covex-v6-cf-c5attr-off at --kv-scale 0.25, in this comparison",
    )
    s2b["c_question_deferral_at_1x"] = dict(
        diff("r4_rqonly", "r4_off"),
        arm="covex-v6-cf-c5attr-rqonly",
        counters=rd("r4_rqonly").get("rd_counters"),
        report=rd("r4_rqonly").get("rd_report"),
    )
    s2b["d_FULL_RUNG_4_at_1x"] = dict(
        diff("r4_full", "r4_off"),
        arm="covex-v6-cf-c5attr",
        rd_counters=rd("r4_full").get("rd_counters"),
        pd_counters=cell("r4_full")["pd_counters"],
        rd_report=rd("r4_full").get("rd_report"),
        w_wired_proof=rd("r4_full").get("w_wired_proof"),
    )
    s2b["e_FULL_RUNG_4_at_0p25x"] = dict(
        diff("r4_full_kv025", "r4_off_kv025"),
        arm="covex-v6-cf-c5attr at --kv-scale 0.25",
    )
    out["proof_1_step_2b"] = s2b

    # ---- PORT RULE: the characteristic decision count, before any score is read ------------
    def chars(lab: str) -> Dict[str, Any]:
        pc = cell(lab)["pd_counters"]
        rc = rd(lab).get("rd_counters") or {}
        pd_def = int(pc.get("pd_state_defers", 0) or 0)
        pd_ch = int(pc.get("pd_state_chunks", 0) or 0)
        pd_rq = int(pc.get("pd_request_defers", 0) or 0)
        q = int(rc.get("rd_question_defers", 0) or 0)
        tot = pd_def + pd_ch + pd_rq + q
        return {"cell": lab, "pd_state_defers": pd_def, "pd_state_chunks": pd_ch,
                "pd_request_defers": pd_rq, "rd_question_defers": q,
                "TOTAL_characteristic_decisions": tot, "non_zero": bool(tot > 0)}
    out["port_rule_characteristic_decisions"] = {
        "_claim": ("CLAUDE.md 'Citing results': the count of the decision kind this arm EXISTS TO "
                   "MAKE, recorded and confirmed NON-ZERO before the arm is scored. ZERO is an "
                   "ABSENT LINK and is reported as such, never as a negative about the policy."),
        "per_cell": [chars(l) for l in ("r4_pdonly", "r4_rqonly", "r4_full",
                                        "r4_pdonly_kv025", "r4_full_kv025")],
    }

    # ---- 4. HARNESS NAME PROOF, with a negative control ------------------------------------
    probes = {}
    for a in ("covex-v6-cf-c5attr", "covex-v6-cf-c5attr-off", "covex-v6-cf-c5attr-pdonly",
              "covex-v6-cf-c5attr-rqonly", "covex-v6-cf-c5attr-not-an-arm"):
        probes[a] = name_probe(a)
    neg = probes["covex-v6-cf-c5attr-not-an-arm"]
    pos_ok = all(not probes[a]["raised_unknown_arm"]
                 for a in probes if a != "covex-v6-cf-c5attr-not-an-arm")
    out["proof_4_harness_name_proof"] = {
        "_claim": ("every rung-4 name a cell line could carry resolves through "
                   "run_live2_real.py ITSELF, spawned as a subprocess with the POSTED KNOBS. A "
                   "bare make_arm in this process is the check that passed while the harness was "
                   "failing."),
        "entry_point": "experiments/orchestration/live2/run_live2_real.py",
        "posted_knobs_on_the_command_line": POSTED_CLI,
        "probes": probes,
        "negative_control": {
            "_claim": "an UNKNOWN name must STILL exit non-zero through this same path",
            "arm": neg["arm"], "returncode": neg["returncode"],
            "raised_unknown_arm": neg["raised_unknown_arm"],
            "verdict": ("PASS" if (neg["returncode"] != 0 and neg["raised_unknown_arm"])
                        else "FAIL - this check is broken, not the arms")},
        "verdict": ("PASS" if (pos_ok and neg["returncode"] != 0 and neg["raised_unknown_arm"])
                    else "FAIL"),
    }

    # ---- STEP 4 NEGATIVE CONTROLS, as named arms --------------------------------------------
    out["step_4_negative_controls"] = {
        "_claim": ("the mechanism disabled AT ITS SOURCE must collapse to the -off digest. Both "
                   "controls are NAMED ARMS, so each control is a cell and not a code edit."),
        "harm_zero": dict(diff("r4_harm0", "r4_off"),
                          _what="harm_scale = 0.0 on BOTH legs, every hook and counter still live",
                          digest=cell("r4_harm0")["digest"], rows=cell("r4_harm0")["rows"]),
        "margin_huge": dict(diff("r4_marginhuge", "r4_off"),
                            _what=("the BAR AND ONLY THE BAR scaled by 1e9. Scaling the WEIGHT "
                                   "instead is the broken control cf_protect_defer records: every "
                                   "harm row carries the same weight, so harm and bar scale "
                                   "together and the control reproduces the treatment."),
                            digest=cell("r4_marginhuge")["digest"],
                            rows=cell("r4_marginhuge")["rows"]),
    }
    for k in ("harm_zero", "margin_huge"):
        out["step_4_negative_controls"][k]["verdict"] = (
            "PASS (collapses to -off)" if out["step_4_negative_controls"][k]["identical"]
            else "FAIL (does not collapse)")

    # ---- THE WEIGHT: is it in the inequality, or cancelled by geometry? ---------------------
    out["is_the_deficit_weight_live"] = {
        "_claim": ("the whole reason rung 4 is built on the RUNG-3 base. On the rung-2 base w_j "
                   "and w_R are identically 1.0, the deciding ratio is harm / MARGIN_CF, and the "
                   "deficit counters cannot move a deferral: Rule 2's `cancelled by geometry` BY "
                   "CONSTRUCTION. Here the bar must be a DISTRIBUTION, not a constant."),
        "bar_distribution_full_rung4": (rd("r4_full").get("rd_report") or {}).get("bar"),
        "w1_ablation": dict(diff("r4_w1", "r4_full"),
                            _what=("both compounds ON, w_d pinned at 1.0. A difference against "
                                   "the live-weight arm is the WEIGHT's and nothing else's")),
        # AN EXPECTATION I WROTE DOWN AND THE MEASUREMENT CORRECTED, recorded rather than quietly
        # replaced. I predicted gain0 would reproduce the -w1 arm, on the reasoning that both put
        # every weight at 1.0. They do NOT, and the reason is that the two arms pin DIFFERENT
        # weights: `-w1` pins the COMPOUND's w_d while rung 3's ordering consumer keeps its live
        # weights underneath, whereas `gain0` sets rung 3's GAIN to zero, which flattens the
        # ORDERING key as well and collapses the pending-work order back to the frozen one. So
        # gain0's comparator is the RUNG-2 arm, not -w1. Both diffs are reported.
        "gain0_control": {
            "_what": ("rung 3's gain set to 0 with both compounds on. This is a control for the "
                      "RUNG BELOW, not for the compound's weight: it flattens the ordering key "
                      "too, so it tests the deficit feed and not the inequality."),
            "against_w1_which_is_NOT_its_bar": diff("r4_gain0", "r4_w1"),
            "against_rung2_which_is": diff("r4_gain0", "pos_uo"),
            "_my_corrected_expectation": ("gain0 should sit NEAR rung 2 (same frozen order) and "
                                          "differ from it by the compound's own deferrals, not "
                                          "near -w1"),
        },
        "w_source_in_the_full_arm": rd("r4_full").get("w_source"),
    }

    # ---- D193 (2) REQUIREMENT 1: u under the rule in force AGAINST u under built_tokens alone
    def u_compare(lab: str) -> Dict[str, Any]:
        r = rd(lab)
        dec = r.get("rd_decisions") or []
        reached = [d for d in dec if d.get("u_detail")]
        fired = [d for d in dec if str(d.get("action")) == "DEFER_TO_LATEST_SAFE_START"]
        def pairs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            o = []
            for d in rows[:40]:
                ud = d.get("u_detail") or {}
                o.append({"t": d.get("t"), "readiness": ud.get("readiness"),
                          "prompt_tokens": ud.get("prompt_tokens"),
                          "u_in_force": ud.get("u"),
                          "u_built_tokens_only": ud.get("u_built_only"),
                          "built_tokens": ud.get("built_tokens"),
                          "telemetry_cached_tokens": ud.get("telemetry_cached_tokens"),
                          "rule": ud.get("rule"),
                          "ratio_builtonly_over_inforce": (
                              (float(ud["u_built_only"]) / float(ud["u"]))
                              if ud.get("u") else None)})
            return o
        return {"counters": {k: v for k, v in (r.get("rd_counters") or {}).items()
                             if k.startswith("rd_u_")},
                "all_candidates_sample": pairs(reached),
                "deferral_candidates_that_FIRED": pairs(fired),
                "n_candidates": len(reached), "n_fired": len(fired)}

    out["proof_6_pricing_requirement_1_u"] = {
        "_claim": ("u is computed by the D186 / r1 correction, not by built_tokens alone, and the "
                   "two forms are SHOWN SIDE BY SIDE rather than assumed equal (D193 (2))."),
        "rule": ("u = tokens if readiness is COLD, else max(tokens - max(built, telemetry), 0); "
                 "the telemetry is trusted only while NOT believed COLD because it is never reset "
                 "on eviction (the e9569009 guard)"),
        "why_it_matters_here": ("built_tokens alone priced recall 15.6x too high under shares. In "
                               "this module u multiplies the queued-ahead price, so it would "
                               "OVER-PRICE THE HARM OF SENDING NOW and therefore OVER-DEFER: a "
                               "failure that would look like the mechanism working."),
        "engine_reported_uncached_is_NOT_available_dry": (
            "a dry cell has no engine, so there is no engine-reported uncached count to compare "
            "against. What IS compared is the two PREDICTIONS, per candidate, above. The external "
            "register is the committed engine-reported figures for these same lagging devices in "
            "d190_recall_lag_diagnosis.json: 8,215 and 14,516 (robo001, seed 5) and 4,181, 313 "
            "and 1,921 (robo004, seed 7). A live cell is where the third column comes from."),
        "full_rung4": u_compare("r4_full"),
        "rqonly": u_compare("r4_rqonly"),
    }

    # ---- D193 (2) REQUIREMENT 2 and the self-inflicted-loss column -------------------------
    ms = json.loads(subprocess.run(
        [PY, "-c", "import sys,json; sys.path.insert(0,'experiments/orchestration/live2'); "
                   "import d190_measured_safety as M; print(json.dumps(M.INFO))"],
        cwd=str(TREE), capture_output=True, text=True, timeout=600).stdout or "{}")

    def miss_col(lab: str) -> Dict[str, Any]:
        r = rd(lab)
        dec = r.get("rd_decisions") or []
        fired = [d for d in dec if str(d.get("action")) == "DEFER_TO_LATEST_SAFE_START"]
        rows = []
        n_miss_worst = n_miss_kappa = 0
        for d in fired:
            m = d.get("would_miss_under_measured_bias") or {}
            w = (m.get("at_measured_worst_bias") or {})
            k = (m.get("at_committed_kappa") or {})
            n_miss_worst += 1 if w.get("would_miss") else 0
            n_miss_kappa += 1 if k.get("would_miss") else 0
            rows.append({"t": d.get("t"), "deferral_s": d.get("deferral_s"),
                         "predicted_total_service_s": m.get("predicted_total_service_s"),
                         "overrun_at_measured_worst_bias_s": w.get("overrun_s"),
                         "would_miss_at_measured_worst_bias": w.get("would_miss"),
                         "overrun_at_committed_kappa_s": k.get("overrun_s"),
                         "would_miss_under_committed_kappa": k.get("would_miss")})
        return {"n_deferrals": len(fired),
                "deferred_and_would_have_missed_at_measured_worst_bias": n_miss_worst,
                "deferred_and_would_have_missed_under_the_committed_kappa": n_miss_kappa,
                "slack_used_s": sorted(round(float(d.get("deferral_s") or 0.0), 6)
                                       for d in fired),
                "per_deferral": rows[:40],
                "counters": {k2: v for k2, v in (r.get("rd_counters") or {}).items()
                             if "would_miss" in k2 or "slack" in k2 or "defer" in k2}}

    out["proof_7_pricing_requirement_2_safety_factor"] = {
        "_claim": ("the latest safe start carries the MEASURED D162 under-prediction as its "
                   "safety factor, derived from committed RUNG-3 data, with the quantile and "
                   "source stated (D193 (2))."),
        "measured_safety_factor": ms,
        "scope": ("cf_request_defer only. cf_protect_defer.KAPPA is LEFT AS COMMITTED at "
                  "1.5775406165458339 because its arms have a posted cell list owned by another "
                  "session; the tree holds two factors on purpose and each records which it is."),
        "self_inflicted_loss_column": {
            "_claim": ("how many DEFERRED QUESTIONS would have missed the 3 s deadline under the "
                       "measured bias. D191 names this as the column that can turn a pass into a "
                       "real harm, so it is here and not in a footnote."),
            "arithmetic": ("overrun = (bias - safety_factor) x predicted_service, so it is at or "
                           "below zero for every bias at or below the factor. That is why the "
                           "factor is the q90 and not the median."),
            "full_rung4": miss_col("r4_full"),
            "rqonly": miss_col("r4_rqonly"),
        },
    }

    out["residency_input_of_the_prediction"] = {
        "_claim": ("D190 (5) track C asked which residency input the latest-safe-start prediction "
                   "consumes. STATED, and in the data on every decision as `residency_input`."),
        "declared": json.loads(subprocess.run(
            [PY, "-c", "import sys,json; "
                       "sys.path.insert(0,'experiments/orchestration/live2'); "
                       "import cf_request_defer as RD; print(json.dumps(RD.RESIDENCY_INPUT))"],
            cwd=str(TREE), capture_output=True, text=True, timeout=600).stdout or "{}"),
    }

    out["_provenance"] = {"git_commit": COMMIT,
                          "script": "d190_proofs.py over cfr3_one_cell.py cells",
                          "model": None, "device": "flash_cpu", "n": 16,
                          "_note": ("stamped to the commit the clean checkout was archived from, "
                                    "which is the commit measured")}
    Path(sys.argv[4]).write_text(json.dumps(out, indent=1, default=float))
    print("wrote %s" % sys.argv[4])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
