"""Proofs required before "policy-F ready", after D143 rulings A and B.

Three of them, each answering a question that a pass elsewhere does not answer:

  1. RULING B IS INERT ON ROBOTS. hybrid-F must still be byte-identical to the screened
     hybrid2-c1c2k15c3c5 on a two-type cell. k_r is now 0.3 x each type's own deadline; 0.3 x 5.0
     is exactly 1.5 in float64 (both are 3/2), so every robot comparison should be bit-identical
     and the whole effect of the ruling should be confined to single-shot. If this fails, the
     ruling changed robot behaviour and the screened numbers no longer carry over.

  2. STEP 2b PER COMPONENT, on a THREE-TYPE LH-REQ cell. For each component, run the frozen policy
     with that component off and diff the decision logs. A component that moves no decision is
     recorded as an ABSENT LINK at this cell, which per the user's ruling does not stop the freeze;
     only base-with-switches-off differing from b7 stops it. The point is to say which is which
     rather than to report one number for all of them.

  3. DRY SMOKE CELLS, labelled dry-run screening and not a result. 16 / 20 / 32 devices, seeds 0
     and 4, for hybrid-F, hybrid-F6, b7, eco-llm and mooncake.

Everything here is a DRY run: no GPU, no server, stub bridge. These are decision-path proofs, not
timing or quality measurements, and nothing in this file may be read as a policy result.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "fleet"))
sys.path.insert(0, str(HERE.parent / "tests"))

import test_hybrid as TH   # noqa: E402

REPO = HERE.parents[3]
OUT = REPO / "results/orchestration/live2/hybrid/policy_f_proofs.json"

# Development seeds only, never 1 to 3 and never HOLDOUT.
SEEDS = (0, 4)
SIZES = (16, 20, 32)
RUN_S = 1200.0
THREE = "40:40:20"
TWO = "50:50"
LH = dict(robot_question_set="lh_req", ss_question_set="ss2")

COMPONENTS = ("c1", "c2", "c3", "c5", "c6")


def _digest(rows):
    import hashlib
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=float)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def proof1_ruling_b_inert_on_robots():
    rows = []
    for seed in SEEDS:
        for n in (12, 16):
            a, _ = TH.dry("hybrid2-c1c2k15c3c5", seed, n, run_s=600.0, ratio=TWO)
            b, sb = TH.dry("hybrid-F", seed, n, run_s=600.0, ratio=TWO)
            rows.append(dict(seed=seed, n=n, ratio=TWO,
                             screened_decisions=len(a), frozen_decisions=len(b),
                             screened_digest=_digest(a), frozen_digest=_digest(b),
                             differing=TH._differing(a, b),
                             identical=(_digest(a) == _digest(b) and len(a) == len(b)),
                             ss_seen=(sb or {}).get("ss_seen", 0)))
    return dict(
        question="is hybrid-F still byte-identical to the screened hybrid2-c1c2k15c3c5 with SS "
                 "absent, after D143 ruling B replaced the flat k_r with 0.3 x deadline?",
        why="0.3 x 5.0 is exactly 1.5 in float64, so a robot's threshold is bit-identical and the "
            "ruling should touch single-shot only. This is what lets every screened seed-0 and "
            "seed-4 number carry over to hybrid-F unchanged.",
        rows=rows, all_identical=all(r["identical"] for r in rows))


_ABSENT_DEFAULT = ("ABSENT LINK at this cell. Which of the five null categories applies is NOT "
                   "settled by a zero: name it from the code path or label it unclassified.")
_ABSENT_NOTES = {
    "c1": "ABSENT LINK, category 1, CANCELLED BY GEOMETRY, and structural rather than specific to "
          "this cell. C1's only read is the ordering index at hybrid_arm.py:317, fed by the value "
          "field written at :260 (dashcam) and :311-312 (recall and SS). Dashcam items carry ONE "
          "constant value and ONE constant work, so the index is a monotone function of slack and "
          "slack is monotone in the deadline: C1's dashcam order is IDENTICALLY EDF order. Every "
          "recall item is kept unconditionally by _cap_dashcam_only (:436-437), so C1's placement "
          "of robot and SS items reaches only the emitted action sequence, the `order` channel this "
          "project already records as unexpressible. CONSEQUENCE: the value / quality table has no "
          "other read, so D143 ruling A cannot move a decision in hybrid-F. See proof 4.",
}


def _absent_class(comp: str) -> str:
    return _ABSENT_NOTES.get(comp, _ABSENT_DEFAULT)


def proof2_step2b_per_component():
    rows = []
    base, _ = TH.dry("hybrid-F6-lhreq", 0, 20, run_s=RUN_S, ratio=THREE, **LH)
    for comp in COMPONENTS:
        def patch(arm, comp=comp):
            arm.sw[comp] = False
        off, st = TH.dry("hybrid-F6-lhreq", 0, 20, run_s=RUN_S, ratio=THREE, patch=patch, **LH)
        d = TH._differing_setwise(base, off)
        d_pos = TH._differing(base, off)
        first = None
        for x, y in zip(base, off):
            if x != y:
                first = dict(on={k: x.get(k) for k in sorted(x)},
                             off={k: y.get(k) for k in sorted(y)})
                break
        rows.append(dict(
            component=comp, decisions_on=len(base), decisions_off=len(off), differing=d,
            differing_positional=d_pos,
            register=("`differing` is a MULTISET difference over (period, kind, opportunities, "
                      "representation, defer_s): a reordering scores 0. `differing_positional` is "
                      "the old order-sensitive count, kept only to show how far the two diverge."),
            moves_decisions=bool(d),
            classification=("moves decisions" if d else _absent_class(comp)),
            first_difference=first))
    return dict(
        cell=dict(arm="hybrid-F6-lhreq", seed=0, n_devices=20, ratio=THREE, run_s=RUN_S,
                  robot_question_set="lh_req", ss_question_set="ss2"),
        question="does each component move a decision on a three-type LH-REQ cell?",
        rule="an identical log is an ABSENT LINK, never a negative (CLAUDE.md Step 2b)",
        rows=rows,
        moved=[r["component"] for r in rows if r["moves_decisions"]],
        absent=[r["component"] for r in rows if not r["moves_decisions"]])


def proof3_smoke():
    arms = ("hybrid-F-lhreq", "hybrid-F6-lhreq", "b7-edf-feasibility", "eco-llm", "mooncake")
    rows = []
    for n in SIZES:
        for seed in SEEDS:
            for arm in arms:
                try:
                    r, st = TH.dry(arm, seed, n, run_s=RUN_S, ratio=THREE, **LH)
                    rows.append(dict(arm=arm, seed=seed, n=n, decisions=len(r),
                                     digest=_digest(r), ok=True,
                                     ss_seen=(st or {}).get("ss_seen"),
                                     ss_at_risk=(st or {}).get("ss_at_risk"),
                                     c6_calls=(st or {}).get("c6_calls"),
                                     c6_deviations=(st or {}).get("c6_deviations"),
                                     throttled_dash=(st or {}).get("c2_throttled_dash"),
                                     throttle_periods=(st or {}).get("c2_throttle_periods")))
                except Exception as exc:
                    rows.append(dict(arm=arm, seed=seed, n=n, ok=False,
                                     error="%s: %s" % (type(exc).__name__, exc)))
                print("  smoke %-20s seed %d n %-3d %s" % (arm, seed, n, rows[-1].get("decisions", rows[-1].get("error"))))
    return dict(
        label="DRY-RUN SCREENING, not a result. No GPU, no server, stub bridge; decision-path "
              "only, so no timing or quality number here is meaningful.",
        cells=rows, n_ok=sum(1 for r in rows if r["ok"]), n_total=len(rows))



def proof4_value_term_negative_control():
    """CLAUDE.md Step 4 on the value term, which proof 2 made unavoidable.

    Proof 2's C1 row is zero, and C1's ordering index is the ONLY read of the value / quality
    tables. If scrambling the table moves no decision, then D143 ruling A - the LH-REQ value swap,
    the 4.4x correction and the SS ordering flip - changes a quantity nothing reads, and the freeze
    has to say so rather than quote the new table as if it priced anything.
    """
    def _flat(a):
        a.values.update(dashcam=0.1, recall=0.1)
        a._ss_values.update({k: 0.1 for k in a._ss_values})

    def _dash100(a):
        a.values.update(dashcam=10.0, recall=0.1)
        a._ss_values.update({k: 0.1 for k in a._ss_values})

    def _robot100(a):
        a.values.update(dashcam=0.001, recall=10.0)
        a._ss_values.update({k: 0.001 for k in a._ss_values})

    def _ss1000(a):
        a._ss_values.update({k: 100.0 for k in a._ss_values})

    variants = (("flat_all_equal", _flat), ("dashcam_100x", _dash100),
                ("robot_100x", _robot100), ("ss_1000x", _ss1000))
    out = {}
    for arm in ("hybrid-F-lhreq", "hybrid-F6-lhreq"):
        base, _ = TH.dry(arm, 0, 20, run_s=RUN_S, ratio=THREE, **LH)
        rows = []
        for name, fn in variants:
            got, _st = TH.dry(arm, 0, 20, run_s=RUN_S, ratio=THREE, patch=fn, **LH)
            rows.append(dict(variant=name, decisions=len(got), digest=_digest(got),
                             differing=TH._differing_setwise(base, got),
                             differing_positional=TH._differing(base, got),
                             identical=(len(got) == len(base) and _digest(got) == _digest(base))))
            print("  %-18s %-16s decisions moved %d (positional %d)"
                  % (arm, name, rows[-1]["differing"], rows[-1]["differing_positional"]))
        out[arm] = dict(base_decisions=len(base), base_digest=_digest(base), variants=rows,
                        all_inert=all(r["differing"] == 0 for r in rows),
                        byte_identical=all(r["identical"] for r in rows))
    return dict(
        cell=dict(seed=0, n_devices=20, ratio=THREE, run_s=RUN_S, **LH),
        question="does the value / quality table reach a decision at all?",
        reads="written at hybrid_arm.py:260 and :311-312, read ONLY at :317 through idx()",
        rows=out,
        verdict=("the value term is DECISION-INERT in both frozen arms: ruling A changes a quantity "
                 "nothing reads" if all(v["all_inert"] for v in out.values()) else
                 "the value term moves decisions in at least one arm; see the rows"))


def main():
    out = {}
    print("proof 1: ruling B inert on robots")
    out["proof1_ruling_b_inert_on_robots"] = proof1_ruling_b_inert_on_robots()
    print("  all identical:", out["proof1_ruling_b_inert_on_robots"]["all_identical"])
    print("proof 2: Step 2b per component on a three-type LH-REQ cell")
    out["proof2_step2b_per_component"] = proof2_step2b_per_component()
    for r in out["proof2_step2b_per_component"]["rows"]:
        print("  %-3s differing %-6d %s" % (r["component"], r["differing"],
                                            "moves" if r["moves_decisions"] else "ABSENT LINK"))
    print("proof 3: dry smoke cells")
    out["proof3_smoke"] = proof3_smoke()
    print("proof 4: value-term negative control")
    out["proof4_value_term_negative_control"] = proof4_value_term_negative_control()
    print("  verdict:", out["proof4_value_term_negative_control"]["verdict"])
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
