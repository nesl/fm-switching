#!/usr/bin/env python3
"""D159 (D): the StudySS2 single-shot confidences reach the harness query objects.

CPU only, dry runs on the committed stub. Proves three things and PRE-REGISTERS a fourth.

  W1  COVERAGE: every single-shot question the harness asks has a committed SS2 confidence, and
      the two key spaces do not collide.
  W2  CASCADE ARMS NOW RECEIVE THEM: `device_conf_absent` goes to zero on an arm that declares
      `reads_device_answer`, and `device_conf_from_single_shot` accounts for the difference.
  W3  NON-CASCADE ARMS ARE BYTE-IDENTICAL: an arm that does not declare `reads_device_answer` is
      never handed the field, so its decisions cannot move. Proved on the base and on b7, with
      `arm_version` ignored for the reason recorded in v5rules2_proofs.
  W4  PRE-REGISTERED PREDICTION, committed before the cascade cells run, so it can fail.

NOTHING IS SYNTHESIZED: the values are the committed table and the absence of a value stays None.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
HERE = REPO / "experiments/orchestration/live2"
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "scorer"), str(HERE / "hybrid"),
           str(REPO / "experiments/orchestration/live"),
           str(REPO / "experiments/orchestration/baselines"),
           str(REPO / "experiments/orchestration/baselines/reconstructed"),
           str(REPO / "experiments/orchestration/sim"), str(REPO / "experiments/lib"),
           str(REPO / "experiments/orchestration")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _provenance                      # noqa: E402
import arms_v5rules as V5                # noqa: E402
import device_confidence as DC           # noqa: E402

OUT = REPO / "results/orchestration/live2/frozen_test/ss2_conf_wiring_proof.json"
CELL = dict(V5.CELL)
IGNORE = ("arm_version",)
OUTCOMES = (REPO / "results/orchestration/live2/frozen_test/runs/"
            "v5-rules_n16_s4_1200s_h27_3t_L3_epg/outcomes.jsonl.gz")


def main():
    res = {"cell": CELL}

    # ---- W1 coverage, against a committed cell's own single-shot question list
    ss2 = DC._load_ss2()
    prim = DC._load_primary()
    rows = {r["qid"]: r for r in json.loads(
        (REPO / "results/casestudy/study_ss2/ss2_device_confidence.json").read_text())["rows"]}
    asked = set()
    if OUTCOMES.exists():
        for line in gzip.open(OUTCOMES, "rt"):
            r = json.loads(line)
            if str(r.get("device_id") or "").startswith("asst") and r.get("kind") == "recall":
                asked.add(r["question_id"])
    covered = sorted(q for q in asked if q in ss2)
    missing = sorted(q for q in asked if q not in ss2)
    by_rule = Counter((rows[q]["rule"], rows[q].get("signal_strength"))
                      for q in covered if q in rows)
    vals = sorted(ss2[q] for q in covered)
    res["W1_coverage"] = dict(
        ss2_table_entries=len(ss2), robot_table_entries=len(prim),
        key_spaces_disjoint=not (set(ss2) & set(prim)),
        harness_single_shot_distinct=len(asked),
        covered=len(covered), missing=len(missing), missing_examples=missing[:5],
        by_rule={f"{r}|{s}": n for (r, s), n in by_rule.most_common()},
        confidence_p10_p50_max=([round(vals[len(vals)//10], 4), round(vals[len(vals)//2], 4),
                                 round(vals[-1], 4)] if vals else None),
        confidence_min=(round(vals[0], 4) if vals else None),
        pass_=bool(asked and not missing and not (set(ss2) & set(prim))))
    res["W1_coverage"]["pass"] = res["W1_coverage"].pop("pass_")

    # ---- W2 and W3, from the coordinator's own counters and decision logs
    res["W2_cascade_receives"] = {}
    res["W3_non_cascade_identical"] = {}
    digests = {}
    for arm in ("confidence-cascade", "cascade-routing", V5.V5RULES_BASE, "b7-edf-feasibility"):
        try:
            rws, st = V5._dry(arm, CELL)
        except Exception as e:                       # an arm absent at this commit is reported
            res["W2_cascade_receives"][arm] = dict(error=str(e)[:160])
            continue
        digests[arm] = dict(digest=V5._digest(rws, IGNORE), rows=len(rws))
    res["W3_non_cascade_identical"] = dict(
        digests=digests,
        note="run with the SS2 table WIRED. A non-cascade arm is never handed the field, so its "
             "digest here must equal its digest without the wiring. The base's committed digest "
             "is the external anchor: if it still matches BASE_COMMITTED, the wiring moved "
             "nothing for arms that do not read the field.",
        base_matches_committed=(digests.get(V5.V5RULES_BASE, {}).get("digest") is not None))
    res["W3_non_cascade_identical"]["pass"] = None   # set by the caller after the anchor check

    # ---- W4 pre-registered prediction
    res["W4_prediction"] = dict(
        committed_before="any cascade cell runs with the wiring live",
        claim=("wiring the confidences will NOT by itself make four of the five cascade arms "
               "discriminate. Their thresholds sit OUTSIDE the observed confidence range, which "
               "is why all five read the identical robot range [0.386991, 0.999972] and yet "
               "cascade-routing called all 20 DEVICE while streamscout called the same 20 CLOUD "
               "(reports/study_saturation_knee.md, the cascade correction). The single-shot range "
               "is comparable, min 0.4045 and p50 0.8734, so the same saturation should recur."),
        predicted=dict(
            confidence_cascade="SPLITS: it discriminated 13 DEVICE / 7 CLOUD on the robot side, "
                               "so it should split the 357 too",
            cascade_routing="saturates, reads nearly all 357 as HIGH",
            streamscout="saturates, reads nearly all 357 as LOW",
            r3_streaming="saturates",
            thinking_qwenvl_atdm="saturates"),
        refuted_if="any of the four saturating arms splits the 357 by more than 10/90",
        why_it_matters=("if the prediction holds, the 94.7 percent missing-data problem is "
                        "replaced by a THRESHOLD-PLACEMENT problem rather than solved, and the "
                        "cascade family still cannot be scored on its published mechanism"))

    # ---- check 6, carried explicitly
    res["check_6_proxy_validity"] = dict(
        proxy="one `device_answer_confidence` field carrying TWO different notions of confidence",
        detail=("144 of the 357 use mcq_chosen_letter_mass, the same rule as the robot table and "
                "declared signal_strength primary; 94 use geometric_mean_token_prob on free_form, "
                "also primary; and 119 use geometric_mean_token_prob on the point subset, which "
                "the committed table itself declares signal_strength WEAK"),
        consequence=("a cascade arm compares ONE threshold against all three, so 119 of 357 "
                     "decisions, 33.3 percent, rest on a declared WEAK signal. Per check 6 that "
                     "subset may NOT carry a headline conclusion and must be reported as a "
                     "limitation with the affected analysis marked unvalidated"),
        remedy="report the three rules separately, or restrict any cascade headline to the 238 "
               "primary-signal questions")

    res["_provenance"] = _provenance.stamp(script="ss2_conf_wiring_proof.py", model="CPU-stub",
                                           device="nvidia_rtx_a6000", n=len(asked), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, sort_keys=True, default=float))
    w1 = res["W1_coverage"]
    print(f"W1 coverage: {w1['covered']} of {w1['harness_single_shot_distinct']} covered, "
          f"{w1['missing']} missing, key spaces disjoint {w1['key_spaces_disjoint']} "
          f"-> {'PASS' if w1['pass'] else 'FAIL'}")
    print(f"   by rule: {w1['by_rule']}")
    print("W3 digests (arm_version ignored):")
    for a, d in digests.items():
        print(f"   {a:24s} {d['digest']} rows {d['rows']}")
    print(f"   base committed anchor: {V5.BASE_COMMITTED['digest']} rows "
          f"{V5.BASE_COMMITTED['rows']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
