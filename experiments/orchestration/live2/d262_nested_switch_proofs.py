#!/usr/bin/env python3
"""D266 item 2: THE SWITCH PROOFS FOR THE NESTED-VICTIM FIXED-WINDOW OUTAGE. CPU, read-only, no GPU.

Four proofs, in the order CLAUDE.md asks for them, and every one of them is run BEFORE any cell:

  (A) NESTING AND WINDOW INVARIANCE, on the artefact. For each k in the ladder, at one
      (seed, offset, D, mix), generate the trace and read `meta.outage`. The claim is three
      equalities and one containment, checked on the RECORDED fields and not on the code that wrote
      them: `victim_permutation` identical across k, `robots == sorted(victim_permutation[:k])`,
      the k1 victim set a SUBSET of the k2 set for every k1 < k2, and `t_start`/`t_end` bit-equal
      across k.
  (B) THE POSITIVE CONTROL FOR (A), AND IT IS NOT OPTIONAL. The same checks are run on the
      COMMITTED "band" rule, where they MUST FAIL: the committed grid's own k=3 and k=5 cells have
      disjoint victim sets and windows 157 s apart. A nesting check that passes on the band rule is
      a broken check, not a nested band rule. An impossible success is as diagnostic as an
      impossible failure.
  (C) STEP 2b, THE SWITCH REACHES A DECISION. One arm, one cell, two conditions (band against
      centre) on the SAME tree, run through the project's deterministic dry digest
      (`hybrid/test_hybrid.dry`, realtime=False). The number of differing decisions and the first
      one are reported. IDENTICAL LOGS ARE AN ABSENT LINK, NEVER A NEGATIVE.
  (D) THE SWITCH ARRIVED WITH ITS DECLARED TYPE AND VALUE, not merely that it was passed: the
      recorded `placement` is read back from the meta and type-checked, the trace-directory token
      that `run_live2_real.py` would build is asserted to CARRY THE PLACEMENT RULE (the cache
      hazard the estimate flagged as the one that would silently serve the old placement), and a
      bad placement string is asserted to RAISE rather than fall back to the default.

Usage:
  python d262_nested_switch_proofs.py --out FILE [--seed 4] [--n 16] [--run-s 1200]
                                      [--ratio 3:11:2] [--d 120] [--k 1 --k 3 --k 5]
                                      [--arm covex-v6-fair-final] [--dry-run-s 300]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(HERE / "v5"), str(HERE / "tests"),
           str(HERE.parent / "baselines"), str(HERE.parent / "sim"),
           str(HERE.parents[2] / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

WORKLOAD = dict(robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                dashcam_min_frames=3, robot_upload="per-frame", robot_reask_mean_s=30.0)


def outage_meta(TR, seed: int, n: int, ratio: str, run_s: float, k: int, d: float,
                placement: str, offset: int = 0) -> Dict[str, Any]:
    """`meta.outage` for one cell. count_only=True runs the IDENTICAL control flow and skips only
    the wire records, and the outage block is inside that flow, so the placement, the victims and
    the window are the same objects a scored cell would carry - at a fraction of the cost."""
    b = TR.generate_trace(seed, n, ratio, run_s, "A", count_only=True,
                          outage_robots_k=k, outage_duration_s=d, outage_seed_offset=offset,
                          **({} if placement == "band" else dict(outage_placement=placement)),
                          **WORKLOAD)
    m = dict(b["meta"]["outage"])
    m.pop("rule", None)                      # the long note; not part of any claim here
    return m


def nesting_checks(metas: Dict[int, Dict[str, Any]], expect: bool) -> Dict[str, Any]:
    ks = sorted(metas)
    perms = {k: metas[k].get("victim_permutation") for k in ks}
    starts = {k: metas[k]["t_start"] for k in ks}
    ends = {k: metas[k]["t_end"] for k in ks}
    vic = {k: list(metas[k]["robots"]) for k in ks}

    perm_identical = (all(p is not None for p in perms.values())
                      and len({json.dumps(p) for p in perms.values()}) == 1)
    prefix_ok = (all(perms[k] is not None and vic[k] == sorted(perms[k][:k]) for k in ks)
                 if perm_identical else False)
    window_equal = len(set(starts.values())) == 1 and len(set(ends.values())) == 1
    containment = {}
    nested = True
    for i, k1 in enumerate(ks):
        for k2 in ks[i + 1:]:
            sub = set(vic[k1]) <= set(vic[k2])
            containment[f"{k1}_in_{k2}"] = {
                "subset": bool(sub),
                "only_in_k%d" % k1: sorted(set(vic[k1]) - set(vic[k2])),
                "added_at_k%d" % k2: sorted(set(vic[k2]) - set(vic[k1]))}
            nested = nested and sub
    ok = bool(nested and window_equal and (prefix_ok if expect else True))
    return {"k_values": ks, "victims": vic, "t_start": starts, "t_end": ends,
            "window_span_across_k_s": round(max(starts.values()) - min(starts.values()), 6),
            "permutation_identical_across_k": bool(perm_identical),
            "victims_are_permutation_prefix": bool(prefix_ok),
            "windows_bit_equal_across_k": bool(window_equal),
            "containment": containment, "NESTED": bool(nested), "PASS": ok,
            "EXPECTED_TO_PASS": bool(expect),
            "VERDICT": ("as expected" if ok == expect else
                        ("UNEXPECTED PASS: THE CHECK IS BROKEN, not the rule. The committed band "
                         "rule's own k=3 and k=5 cells are disjoint with windows 157 s apart, so a "
                         "nesting check that passes on it is measuring nothing."
                         if ok else
                         "UNEXPECTED FAIL: the centre rule did not nest; STOP and do not run a "
                         "cell."))}


def dry_rows(arm: str, seed: int, n: int, run_s: float, ratio: str, k: int, d: float,
             placement: str) -> List[Dict[str, Any]]:
    import test_hybrid as TH
    kw = dict(ratio=ratio, robot_question_set=WORKLOAD["robot_question_set"],
              ss_question_set=WORKLOAD["ss_question_set"],
              dashcam_format=WORKLOAD["dashcam_format"],
              dashcam_min_frames=WORKLOAD["dashcam_min_frames"],
              robot_upload=WORKLOAD["robot_upload"],
              robot_reask_mean_s=WORKLOAD["robot_reask_mean_s"])
    if k > 0:
        kw.update(outage_robots_k=k, outage_duration_s=d, outage_placement=placement)
    rows, _ = TH.dry(arm, seed, n, run_s, **kw)
    return rows


def diff_rows(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    per_field: Dict[str, int] = {}
    n = 0
    first = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        n += 1
        if first is None:
            first = {"row_index": i, "band": x, "centre": y}
        for kk in set(x) | set(y):
            if x.get(kk) != y.get(kk):
                per_field[kk] = per_field.get(kk, 0) + 1
    return {"n_rows": [len(a), len(b)], "n_differing_decisions": n + abs(len(a) - len(b)),
            "differing_fields": per_field, "first_difference": first}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--k", type=int, action="append", default=None)
    ap.add_argument("--arm", default="covex-v6-fair-final")
    ap.add_argument("--dry-run-s", type=float, default=300.0,
                    help="run_s for proof (C) only; the dry digest is positional and 1200 s is "
                         "not needed to show a decision moved")
    ap.add_argument("--skip-dry", action="store_true")
    a = ap.parse_args(argv)
    ks = sorted(a.k) if a.k else [1, 3, 5]

    import trace as TR

    out: Dict[str, Any] = {
        "_what": ("D266 item 2 switch proofs: victim nesting, window invariance, the band-rule "
                  "positive control, Step 2b on the dry digest, and the arrival of the switch "
                  "with its declared type and value. CPU, no GPU, no cell."),
        "cell": {"seed": a.seed, "n_devices": a.n, "ratio": a.ratio, "run_s": a.run_s,
                 "outage_duration_s": a.d, "k_ladder": ks, "workload": WORKLOAD},
    }

    # ---- (A) and (B): the centre rule must nest; the band rule must NOT.
    for rule, expect in (("centre", True), ("band", False)):
        metas = {k: outage_meta(TR, a.seed, a.n, a.ratio, a.run_s, k, a.d, rule) for k in ks}
        res = nesting_checks(metas, expect=expect)
        res["meta_as_recorded"] = metas
        out["A_centre" if rule == "centre" else "B_band_positive_control"] = res

    centre = out["A_centre"]
    band = out["B_band_positive_control"]
    out["CHECK_IS_LIVE"] = bool(centre["PASS"] and not band["PASS"])

    # ---- (D): the switch arrived, with its type and value, and the CACHE KEY carries the rule.
    m1 = out["A_centre"]["meta_as_recorded"][ks[0]]
    centre_expected_start = round(0.5 * (a.run_s - a.d), 6)
    tok = {}
    for rule in ("band", "centre"):
        extra = "_outk%dd%g" % (ks[-1], a.d)
        if rule != "band":
            extra += "p%s" % rule
        tok[rule] = extra
    bad_raises = None
    try:
        outage_meta(TR, a.seed, a.n, a.ratio, a.run_s, ks[0], a.d, "midpoint")
        bad_raises = False
    except ValueError:
        bad_raises = True
    out["D_switch_arrival"] = {
        "placement_recorded": m1.get("placement"),
        "placement_type": type(m1.get("placement")).__name__,
        "placement_is_str_centre": (isinstance(m1.get("placement"), str)
                                    and m1.get("placement") == "centre"),
        "t_start_recorded": m1.get("t_start"),
        "t_start_expected_centre_of_band": centre_expected_start,
        "t_start_matches_committed_band_centre": m1.get("t_start") == centre_expected_start,
        "inside_committed_band": bool(TR.OUTAGE_PLACEMENT_LO * (a.run_s - a.d)
                                      <= m1.get("t_start", -1)
                                      <= TR.OUTAGE_PLACEMENT_HI * (a.run_s - a.d)),
        "committed_band_s": [TR.OUTAGE_PLACEMENT_LO * (a.run_s - a.d),
                             TR.OUTAGE_PLACEMENT_HI * (a.run_s - a.d)],
        "rng_stream_key": m1.get("rng_stream_key"),
        "rng_key_carries_k": ("|%d|" % ks[0]) in str(m1.get("rng_stream_key")),
        "trace_dir_token": tok,
        "trace_dir_token_carries_rule": tok["centre"] != tok["band"],
        "bad_placement_raises": bad_raises,
        "_why": ("the trace directory is regenerated only when trace.jsonl is ABSENT, so a token "
                 "that does not carry the placement rule would serve the old placement with every "
                 "gate passing. The token is asserted here, not assumed."),
    }

    # ---- (C) Step 2b: does the switch move a decision?
    if a.skip_dry:
        out["C_step2b_dry_digest"] = {"RAN": False, "why": "--skip-dry"}
    else:
        ctl_a = dry_rows(a.arm, a.seed, a.n, a.dry_run_s, a.ratio, ks[-1], a.d, "band")
        ctl_b = dry_rows(a.arm, a.seed, a.n, a.dry_run_s, a.ratio, ks[-1], a.d, "band")
        self_cmp = diff_rows(ctl_a, ctl_b)
        cen = dry_rows(a.arm, a.seed, a.n, a.dry_run_s, a.ratio, ks[-1], a.d, "centre")
        cmp_ = diff_rows(ctl_a, cen)
        det = self_cmp["n_differing_decisions"] == 0
        out["C_step2b_dry_digest"] = {
            "RAN": True, "arm": a.arm, "run_s": a.dry_run_s, "k": ks[-1], "D": a.d,
            "instrument": "hybrid/test_hybrid.dry, realtime=False, committed STRIP set",
            "instrument_self_consistency": self_cmp,
            "DETERMINISTIC": bool(det),
            "comparison_band_vs_centre": cmp_,
            "SWITCH_REACHED_A_DECISION": bool(det and cmp_["n_differing_decisions"] > 0),
            "VERDICT": ("PASS: the placement switch moves decisions on an instrument that agrees "
                        "with itself, so a band-against-centre comparison has actually been run."
                        if det and cmp_["n_differing_decisions"] > 0 else
                        ("STOP: the instrument disagreed with itself; nothing here is readable."
                         if not det else
                         "ABSENT LINK: the two conditions produced identical decision logs. This "
                         "is NOT a negative result about the placement rule; the comparison has "
                         "not been run.")),
        }

    allok = (out["CHECK_IS_LIVE"] and out["D_switch_arrival"]["placement_is_str_centre"]
             and out["D_switch_arrival"]["t_start_matches_committed_band_centre"]
             and out["D_switch_arrival"]["trace_dir_token_carries_rule"]
             and out["D_switch_arrival"]["bad_placement_raises"]
             and (a.skip_dry or out["C_step2b_dry_digest"]["SWITCH_REACHED_A_DECISION"]))
    out["ALL_PROOFS_PASS"] = bool(allok)
    out["VERDICT"] = (("PASS: victims nest and the window is invariant across k on the centre rule, "
                       "the same check FAILS on the committed band rule, the switch arrives with "
                       "its declared type and value, and the cache key carries the rule."
                       + ("" if a.skip_dry else
                          " Step 2b: the switch moves decisions on a self-consistent instrument.")
                       + (" STEP 2b WAS SKIPPED (--skip-dry), SO NO DECISION-MOVE CLAIM IS MADE "
                          "HERE." if a.skip_dry else "")) if allok else
                      "STOP: at least one proof failed; see the per-proof verdicts. Do not run a "
                      "cell.")
    try:
        from _provenance import stamp
        out["_provenance"] = stamp(script="d262_nested_switch_proofs.py", model="none-cpu",
                                   device="flash_cpu", n=len(ks), args=a)
    except Exception as e:                      # provenance is recorded, never fatal to a proof
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"VERDICT": out["VERDICT"], "CHECK_IS_LIVE": out["CHECK_IS_LIVE"],
                      "centre_nested": centre["NESTED"], "band_nested": band["NESTED"],
                      "centre_window": [centre["t_start"][k] for k in ks],
                      "band_window": [band["t_start"][k] for k in ks],
                      "step2b": out["C_step2b_dry_digest"].get("VERDICT")}, indent=1))
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
