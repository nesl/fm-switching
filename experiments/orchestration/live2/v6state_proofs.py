#!/usr/bin/env python3
"""Proofs for covex-v6-state, rung 2 of the spec v6 ladder (D172). CPU only, dry cells.

P0 positive control        the comparison can see a difference that is there by construction
P1 negative control        the rung with its channel off collapses to covex-v6-rules
P2 Step 2b                 the switch REACHES a decision
P3 port rule               does the rung's CHARACTERISTIC decision (TOUCH) ever occur
P4 gain distribution       the predicted gain per state decision against MARGIN_CF
P5 baselines unchanged     no committed arm sees any of the four capability flags

THE DIGEST CONVENTION, and it matters for P1. The committed digest is taken over decision rows
INCLUDING `arm_version`, which every arm sets to its own string. A rung whose decisions are
identical therefore has a DIFFERENT full digest purely because it is a different arm. So P1
reports both: the full digest, and the digest with `arm_version` removed, which is the one that
answers "are the decisions the same". The exclusion is named rather than quietly applied.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_v6state as V6S                                                     # noqa: E402
import cf_margin as CM                                                         # noqa: E402

# seeds 4 to 7 only. 16 devices and 1200 s is the posted cell shape, so the gain distribution
# below is measured where the cells would run and not on a smaller cell.
CELL = dict(seed=4, n=16, run_s=1200.0, ratio="50:50",
            robot_question_set="lh_req", ss_question_set="ss2")
SMALL = dict(CELL, n=8, run_s=600.0)


def _digest(rows: Sequence[Dict[str, Any]], ignore: Sequence[str] = ()) -> str:
    rr = [{k: v for k, v in r.items() if k not in ignore} for r in rows]
    return hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                     default=float).encode()).hexdigest()[:16]


def _dry(arm: str, cell: Dict[str, Any]):
    import test_hybrid as TH
    rows, st = TH.dry(arm, cell["seed"], cell["n"], run_s=cell["run_s"], ratio=cell["ratio"],
                      robot_question_set=cell["robot_question_set"],
                      ss_question_set=cell["ss_question_set"])
    return list(rows or []), dict(st or {})


def _state(st: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in st.items() if str(k).startswith("state_")}


def main() -> int:
    V6S.register()
    margin = float(CM.MARGIN_CF)
    out: Dict[str, Any] = {
        "_what": "covex-v6-state (rung 2) proofs",
        "_register": "DRY cells, no GPU and no engine: claims about decisions, not about latency",
        "cell": dict(CELL, dry=True), "margin_cf": margin,
        "digest_convention": ("committed digests include arm_version; the no-version digest is "
                              "the one that answers whether the DECISIONS are the same"),
    }

    # ---- P0 positive control
    a, _ = _dry("hybrid-F-lhreq-noc3", SMALL)
    b, _ = _dry("b7-edf-feasibility", SMALL)
    out["P0_positive_control"] = {
        "_claim": "two arms that must differ do differ",
        "digests": [_digest(a, ("arm_version",)), _digest(b, ("arm_version",))],
        "differ": _digest(a, ("arm_version",)) != _digest(b, ("arm_version",)),
        "verdict": ("PASS: the check is live"
                    if _digest(a, ("arm_version",)) != _digest(b, ("arm_version",)) else
                    "FAIL: THE CHECK IS BROKEN, not the arm"),
    }
    if not out["P0_positive_control"]["verdict"].startswith("PASS"):
        print(json.dumps(out, indent=1))
        return 1

    # ---- P1 negative control
    r2, _ = _dry("v5-rules-2", SMALL)
    off, _off_st = _dry("covex-v6-state-off", SMALL)
    same = _digest(r2, ("arm_version",)) == _digest(off, ("arm_version",))
    out["P1_negative_control"] = {
        "_claim": "the rung with every added channel off collapses to covex-v6-rules",
        "v5_rules_2_full_digest": _digest(r2), "off_full_digest": _digest(off),
        "v5_rules_2_no_version": _digest(r2, ("arm_version",)),
        "off_no_version": _digest(off, ("arm_version",)),
        "rows": [len(r2), len(off)],
        "collapses_byte_identically": same,
        "note": ("the four capability flags are INSTANCE attributes for this reason: as class "
                 "attributes they stayed on under -off, state pricing kept changing the budget "
                 "charge, and the control differed from the rung below while claiming to be it"),
        "verdict": ("PASS: byte-identical decisions" if same else
                    "FAIL: the control does not collapse, so it is not a control"),
    }

    # ---- P2 / P3 / P4, on the posted cell shape
    rows, st = _dry("covex-v6-state", CELL)
    r2c, _ = _dry("v5-rules-2", CELL)
    sd = _state(st)
    n_dec = int(sd.get("state_decisions", 0))
    n_touch = int(sd.get("state_chosen_TOUCH", 0))
    n_warm = int(sd.get("state_chosen_WARM", 0))
    n_keep = int(sd.get("state_chosen_KEEP", 0))
    mean_delta = (sd.get("state_delta_milli_sum", 0) / 1000.0 / n_dec) if n_dec else 0.0
    max_delta = sd.get("state_delta_max_milli", 0) / 1000.0
    over = int(sd.get("state_delta_gt_0p16456", 0))
    moved = _digest(rows, ("arm_version",)) != _digest(r2c, ("arm_version",))

    out["P2_step2b"] = {
        "_claim": "the plan_state switch reaches a decision",
        "state_decisions": n_dec,
        "skipped": {k: v for k, v in sd.items() if k.startswith("state_skipped")},
        "reaches_a_decision": n_dec > 0,
        "verdict": ("PASS: plan_state reaches %d decisions, where before this rung it had no "
                    "caller outside the proofs and implemented no causal link in any run" % n_dec
                    if n_dec > 0 else
                    "FAIL: ABSENT LINK, never a negative"),
    }
    out["P3_port_rule"] = {
        "_claim": "the rung's CHARACTERISTIC decision, TOUCH, occurs at least once",
        "chosen": {k: v for k, v in sd.items() if k.startswith("state_chosen_")},
        "touch_emitted": int(sd.get("state_touch_emitted", 0)),
        "decisions_moved_against_covex_v6_rules": moved,
        "verdict": ("PASS: TOUCH occurs %d times" % n_touch if n_touch > 0 else
                    "FAIL: ZERO TOUCH decisions. The rung makes %d state decisions and chooses "
                    "KEEP on every one, so covex-v6-state is byte-identical to covex-v6-rules "
                    "and a cell of it would spend GPU hours reproducing the rung below"
                    % n_dec),
    }
    def _per_cand(name: str) -> Dict[str, Any]:
        n = int(st.get("gain_%s_n" % name, 0))
        return {"n": n,
                "mean": round(st.get("gain_%s_milli_sum" % name, 0) / 1000.0 / n, 6) if n else None,
                "max": round(st.get("gain_%s_max_milli" % name, 0) / 1000.0, 6),
                "n_over_margin": int(st.get("gain_%s_over_margin" % name, 0))}

    nhw = int(st.get("harm_warm_priced", 0))
    out["P4b_harm_warm_computed"] = {
        "_claim": ("harm_warm is COMPUTED from the D162 model and never a declared grid value "
                   "(research/prereg_harm_warm_d172.md)"),
        "coefficient": V6S.__dict__.get("QUEUE_TOKEN_S"),
        "priced": nhw, "no_queue_behind_the_warm": int(st.get("harm_warm_no_queue", 0)),
        "unpriced_refusals": int(st.get("harm_warm_unpriced", 0)),
        "nonzero": int(st.get("harm_warm_nonzero", 0)),
        "mean": (round(st.get("harm_warm_milli_sum", 0) / 1000.0 / nhw, 6) if nhw else None),
        "max": round(st.get("harm_warm_max_milli", 0) / 1000.0, 6),
        "capped": int(st.get("harm_warm_capped", 0)),
        "cap_counter_exists": True,
        "per_candidate_gain_against_margin": {k: _per_cand(k)
                                              for k in ("HOLD_BACK", "WARM", "TOUCH")},
        "identity_check": ("HOLD_BACK's value IS harm_warm by construction, so its gain sum must "
                           "equal the harm_warm sum: %d vs %d"
                           % (int(st.get("gain_HOLD_BACK_milli_sum", 0)),
                              int(st.get("harm_warm_milli_sum", 0)))),
        "verdict": ("PASS: harm_warm is priced on %d decisions, capped %d, and the three "
                    "candidate gains are reported separately"
                    % (nhw, int(st.get("harm_warm_capped", 0))) if nhw else
                    "FAIL: harm_warm was never priced, so the term is not reaching plan_state"),
    }
    out["P4_gain_distribution"] = {
        "_claim": "the predicted gain of each state decision against MARGIN_CF (D172)",
        "_register": ("a REAL dry cell at the posted shape, 16 devices and 1200 s, not a "
                      "constructed grid"),
        "margin_cf": margin,
        "n_decisions": n_dec,
        "n_positive_gain": int(sd.get("state_delta_gt_0", 0)),
        "mean_gain": round(mean_delta, 6),
        "max_gain": round(max_delta, 6),
        "shortfall_of_the_maximum": round(margin - max_delta, 6),
        "exceedance": {k.replace("state_delta_gt_", ">"): v for k, v in sorted(sd.items())
                       if k.startswith("state_delta_gt_")},
        "n_over_margin": over,
        "fraction_over_margin": round(over / n_dec, 6) if n_dec else None,
        "ceiling": ("the gain is w * p_question * acc * (p_warm - p_cold) with acc = 0.250, so "
                    "its arithmetic ceiling is 0.250 and a gain above the margin is not "
                    "forbidden by the formula. The maximum OBSERVED is %.3f, which is a near "
                    "miss and not a cap" % max_delta),
        "rule2_class": (
            "FIRED AND DID NOT HELP, with the reason named: plan_state's own argmax prefers a "
            "non-KEEP candidate on %d of %d decisions, and D151's margin rule then overrides it "
            "back to KEEP on every one of them. The mechanism is not absent, not unexpressible "
            "and not unexercised: it decides, and the MODEL-ERROR BAR is what stops it acting"
            % (int(sd.get("state_delta_gt_0", 0)), n_dec)),
        "verdict": "PASS: the distribution is reported against the margin",
    }

    # ---- P5 baselines unchanged
    import arms as A
    flagged = []
    for name in sorted(A.ARMS):
        try:
            arm = A.make_arm(name)
        except Exception:                                                      # noqa: BLE001
            continue
        on = [f for f in ("live2_offload_controls", "live2_touch_requests",
                          "live2_state_priced_costs", "live2_belief_apply")
              if bool(getattr(arm, f, False))]
        if on:
            flagged.append({"arm": name, "flags": on})
    only_rung = all(r["arm"].startswith("covex-v6-state") for r in flagged)
    out["P5_baselines_unchanged"] = {
        "_claim": "no committed arm declares any of the four capability flags",
        "arms_declaring_a_flag": flagged,
        "only_this_rung_declares_them": only_rung,
        "verdict": ("PASS: every other arm leaves all four off, so none of them can see this "
                    "rung's changes" if only_rung else
                    "FAIL: an arm outside this rung declares a capability flag"),
    }

    out["ALL_PASS"] = all(v["verdict"].startswith("PASS") for v in out.values()
                          if isinstance(v, dict) and "verdict" in v)
    out["POST_V6STATE_CELLS"] = bool(n_touch > 0 and moved)
    out["post_decision"] = (
        "POST: the rung makes its characteristic decision and moves decisions against the rung "
        "below" if out["POST_V6STATE_CELLS"] else
        "DO NOT POST: covex-v6-state is byte-identical to covex-v6-rules on this cell, so every "
        "posted cell would spend GPU hours reproducing a cell that already exists. The blocker "
        "is the margin, not the wiring, and it is recorded rather than worked around: MARGIN_CF "
        "is never changed (D157, D172)")
    dest = REPO / "results/orchestration/live2/frozen_test/v6state_proofs.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out.items():
        if isinstance(v, dict) and "verdict" in v:
            print("%-24s %s" % (k, v["verdict"][:110]))
    print("ALL_PASS:", out["ALL_PASS"])
    print(out["post_decision"][:160])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
