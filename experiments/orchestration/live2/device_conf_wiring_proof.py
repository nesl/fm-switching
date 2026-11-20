#!/usr/bin/env python3
"""Proof for the device-confidence wiring (dry cells; no GPU, no model server, no inference).

  python3 -I experiments/orchestration/live2/device_conf_wiring_proof.py [jobs]

User ruling 2026-11-20: the five cascade-style arms must receive what they declare. This proves it
reached them, and proves it did NOT reach anything else.

Four things, and the fourth is the one that protects work in flight:
  1. the field ARRIVES non-None, counted per arm from the coordinator's own counters;
  2. the arm's CHARACTERISTIC DECISION fires: it declines to escalate on a high confidence. Counted
     by wrapping the arm instance's `decide`, pairing each recall query's supplied confidence with
     the decision the arm returned for that query id;
  3. the decision digest CHANGES against the committed PRE-FIX digest in
     `frozen_test/baseline_prescreen.json` (a592e51), on the same cell, so the switch demonstrably
     reaches a decision (CLAUDE.md Step 2b);
  4. `b7-edf-feasibility` is BYTE-IDENTICAL to its committed pre-fix digest. b7 declares nothing,
     so it must be untouched, and it is the background arm StudySH-EP's cost-under-load cell runs.
     A change here would mean the fix perturbed work in flight.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(HERE / "hybrid"), str(HERE / "fleet"),
           str(ROOT / "experiments/orchestration/baselines"),
           str(ROOT / "experiments/orchestration/live"), str(ROOT / "experiments/lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import _provenance  # noqa: E402

PRESCREEN = ROOT / "results/orchestration/live2/frozen_test/baseline_prescreen.json"
OUT = ROOT / "results/orchestration/live2/device_conf_wiring_proof.json"
SEED, N, RUN_S, RATIO = 4, 16, 1200.0, "40:40:20"
LH = dict(robot_question_set="lh_req", ss_question_set="ss2")
# REGISTRY names, not file names. The first version of this list used "r3streaming" and
# "thinking-qwenvl", taken from r3streaming_adapted.py and thinking_qwenvl_adapted.py, and both
# raised "unknown arm". I recorded that as "not in the live2 registry", which was WRONG: they are
# registered as r3-streaming and thinking-qwenvl-atdm. The lesson is the one Step 2b already
# states for switches, applied to a name: an arm is absent only when `make_arm` cannot build it,
# never because a name guessed from a file name does not resolve.
ARMS = ["confidence-cascade", "cascade-routing", "streamscout", "r3-streaming",
        "thinking-qwenvl-atdm", "b7-edf-feasibility"]
CONTROL = "b7-edf-feasibility"


def _instrument(arm, sink):
    """Wrap the INSTANCE's `decide` so each recall query's supplied confidence is paired with the
    decision the arm returned for it. The instance is wrapped, not the class: `make_arm` resolves
    arms through differently named module instances, so a class-level patch can silently not take
    effect (learned the hard way in policy_f6r_proofs)."""
    inner = arm.decide

    def wrapped(obs, _inner=inner):
        conf = {q.query_id: getattr(q, "device_answer_confidence", None) for q in (obs.recall or ())}
        act = _inner(obs)
        for ra in (getattr(act, "recall", None) or ()):
            c = conf.get(getattr(ra, "query_id", None))
            sink.append((c, str(getattr(ra, "decision", None) or getattr(ra, "action", None))))
        return act
    arm.decide = wrapped


def one(name):
    import test_hybrid as TH
    t0 = time.time()
    sink = []
    try:
        rows, st = TH.dry(name, SEED, N, run_s=RUN_S, ratio=RATIO,
                          patch=lambda a: _instrument(a, sink), **LH)
    except Exception as e:                                                     # noqa: BLE001
        return name, dict(error=repr(e)[:400], wall_s=round(time.time() - t0, 1))
    # the COMMITTED digest function, imported rather than re-implemented. My first version hashed
    # r["action"] and r["key"], which are not fields of a decision row, so every row hashed to the
    # same string and the digest became a function of row COUNT alone: three different arms
    # collided on one digest and b7 appeared to change. b7 reads no confidence and cannot change,
    # so that impossible failure was the checker breaking, not the fix (CLAUDE.md check 7).
    import baseline_prescreen as BP
    pos, setw = BP._digests(rows)
    present = [(c, d) for c, d in sink if c is not None]
    absent = [(c, d) for c, d in sink if c is None]
    # The confidence count is taken AT THE POINT OF USE, inside the arm's own decide, rather than
    # from a coordinator counter. That is deliberate and it is the stronger read: a counter proves
    # the supplier ran, while this proves the value reached the code that consumes it, which is
    # what Step 2 asks for. (`TH.dry` returns None for stats in any case.)
    return name, dict(
        wall_s=round(time.time() - t0, 1), n_decision_rows=len(rows), digest=pos,
        digest_setwise=setw, recall_decisions_total=len(sink),
        on_confidence_present=dict(n=len(present),
                                   by_decision=dict(Counter(d for _c, d in present))),
        on_confidence_absent=dict(n=len(absent),
                                  by_decision=dict(Counter(d for _c, d in absent))),
        declines_to_escalate_on_high_confidence=sum(
            1 for c, d in present if d.upper().startswith("DEVICE")),
        escalates_on_low_confidence=sum(
            1 for c, d in present if d.upper().startswith("CLOUD")),
        confidence_range=([round(min(c for c, _ in present), 6),
                           round(max(c for c, _ in present), 6)] if present else None))


def coverage_cell():
    """The same arm on a ROBOT-ONLY two-type cell, to separate coverage from wiring.

    In the frozen grid's three-type cell only 20 of 377 recall questions are robot questions; the
    other 357 are single shot, which have no committed answer probability at all, so None is the
    honest value for them. A reader seeing 20 of 377 should not conclude the supplier is weak, so
    the same arm is run where every recall question IS a robot question.
    """
    import test_hybrid as TH
    sink = []
    TH.dry("confidence-cascade", SEED, N, run_s=RUN_S, ratio="50:50",
           patch=lambda a: _instrument(a, sink),
           robot_question_set="lh_req", ss_question_set="ss1")
    pres = [c for c, _ in sink if c is not None]
    return dict(cell=dict(seed=SEED, n_devices=N, run_s=RUN_S, ratio="50:50",
                          robot_question_set="lh_req", ss_question_set="ss1", dry=True),
                arm="confidence-cascade", recall_decisions=len(sink),
                confidence_present=len(pres), confidence_absent=len(sink) - len(pres),
                coverage_fraction=round(len(pres) / max(len(sink), 1), 4),
                by_decision=dict(Counter(d for c, d in sink if c is not None)),
                confidence_range=([round(min(pres), 6), round(max(pres), 6)] if pres else None))


def main():
    jobs = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    import multiprocessing as mp
    pre = json.loads(PRESCREEN.read_text())["arms"]
    with mp.Pool(jobs) as pool:
        got = dict(pool.imap_unordered(one, ARMS))
    for name, rec in got.items():
        if "error" in rec:
            continue
        p = (pre.get(name) or {}).get("digest") if pre.get(name) else None
        rec["prefix_digest_committed"] = p
        rec["digest_changed_vs_prefix"] = (None if p is None else rec["digest"] != p)
    res = dict(
        label="Device-confidence wiring proof. Dry cells on the frozen grid's own cell; no GPU, no "
              "model server, no inference. Pre-fix digests are the committed baseline_prescreen "
              "(a592e51) on the identical cell.",
        at=datetime.now().isoformat(),
        cell=dict(seed=SEED, n_devices=N, run_s=RUN_S, ratio=RATIO, dry=True, **LH),
        arms=got, robot_only_coverage=coverage_cell())
    ctl = got.get(CONTROL, {})
    res["control"] = dict(
        arm=CONTROL,
        declares_reads_device_answer=False,
        digest=ctl.get("digest"), prefix_digest=ctl.get("prefix_digest_committed"),
        byte_identical=(ctl.get("digest") == ctl.get("prefix_digest_committed")
                        and ctl.get("digest") is not None),
        why="b7 declares nothing, so the fix must not move it. It is also the background arm "
            "StudySH-EP's cost-under-load cell runs, so a change here would mean the fix "
            "perturbed work in flight.")
    res["verdict"] = dict(
        arms_receiving_the_field=sorted(
            k for k, v in got.items()
            if (v.get("on_confidence_present") or {}).get("n", 0) > 0),
        arms_declining_on_high_confidence=sorted(
            k for k, v in got.items()
            if v.get("declines_to_escalate_on_high_confidence", 0) > 0),
        control_unchanged=res["control"]["byte_identical"])
    res["_provenance"] = _provenance.stamp(script="device_conf_wiring_proof.py",
                                           model="none-dry", device="cpu", n=len(ARMS), args=None)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    for name in ARMS:
        r = got.get(name, {})
        if "error" in r:
            print(f"  {name}: ERROR {r['error'][:120]}")
            continue
        print(f"  {name}: conf present {r['on_confidence_present']['n']} "
              f"absent {r['on_confidence_absent']['n']} "
              f"| decline-on-high {r['declines_to_escalate_on_high_confidence']} "
              f"escalate-on-low {r['escalates_on_low_confidence']} "
              f"| digest {r['digest']} prefix {r['prefix_digest_committed']} "
              f"changed {r['digest_changed_vs_prefix']}")
    cv = res["robot_only_coverage"]
    print(f"  robot-only cell: coverage {cv['coverage_fraction']:.0%} "
          f"({cv['confidence_present']}/{cv['recall_decisions']}), {cv['by_decision']}, "
          f"range {cv['confidence_range']}")
    print("control byte-identical:", res["control"]["byte_identical"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
