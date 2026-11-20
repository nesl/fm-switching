"""DRY PRE-SCREEN of every registered live2 arm on the three-type workload (user, 2026-11-20).

One cell per arm: 40:40:20 dashcam : LH-REQ EVAL robot : SS2 EVAL single-shot, 1200 s, seed 4,
16 devices, dry engine. SCREENING ONLY. A dry run exercises the decision path with a stub bridge
and no engine, so nothing here is a latency, a quality or a capacity result for any arm.

It answers three questions that the live grid cannot afford to ask for 118 arms:

  1. WHICH ARMS ARE THE SAME ARM HERE. Arms are grouped by the digest of their decision log. Two
     arms in one group decided identically on this cell, so running both buys one row of
     information at twice the cost. Both a POSITIONAL digest (byte-identity including order) and a
     SETWISE digest (the same decisions in any order) are reported, because they are different
     claims and the pair separates "identical" from "identical up to ordering".

  2. WHETHER AN ARM EVER MAKES A DECISION OF ITS OWN KIND, the port-side rule in CLAUDE.md: the
     well-formedness and fairness proofs establish that an arm is legal and fairly treated, never
     that it does anything. A census of every observable decision channel is reported per arm
     (kinds, non-default representations and which ones, deferrals, declines, piece splits, tier
     requests). An arm whose census is channel-silent made no decision of its own kind on this
     cell and is FLAGGED, whatever that kind was meant to be.

  3. WHAT THE DISTINCT-ARM LIST IS, so the live grid runs one arm per group.

REGISTER, stated because it is the easiest thing to misread here. "Identical on this cell" is an
OBSERVED coincidence at seed 4, 16 devices, 1200 s, three types, NOT a constructed proof that two
arms are the same policy: a cell that never reaches an arm's branch cannot distinguish it from an
arm that lacks the branch. Equally, a channel-silent census is a statement about THIS cell, which
is why the flag names the cell. The two readings this file does NOT support are "arm X equals arm
Y" and "arm X does nothing".
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _p in (HERE, HERE / "hybrid", HERE / "fleet", HERE / "tests",
           REPO / "experiments/orchestration", REPO / "experiments/orchestration/baselines",
           REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

OUT = REPO / "results/orchestration/live2/frozen_test/baseline_prescreen.json"
ARMS_FILE = REPO / "results/orchestration/live2/frozen_test/runs/PRESCREEN_DISTINCT_ARMS"

SEED, N, RUN_S, RATIO = 4, 16, 1200.0, "40:40:20"
LH = dict(robot_question_set="lh_req", ss_question_set="ss2")

# The characteristic decision of each arm in the live comparison, named from its own committed
# report rather than guessed here. Every other arm is reported as UNDECLARED with its full census:
# an undeclared characteristic is not a zero, and must not be read as one.
DECLARED = {
    # Each arm's characteristic decision is the channel ITS OWN committed description names, not a
    # single channel applied to everything: b7 exists to defer and reject on feasibility, mooncake
    # to retain state, eco-llm to pick a representation per request. Reading one channel for all of
    # them is how a port passes both required proofs while making no decision of its own kind.
    "b7-edf-feasibility": "feasibility_actions",
    "mooncake": "state_action",
    "eco-llm": "recall_non_default_representation",
    # The frozen hybrids act mostly through channels decision.jsonl does not carry (C1's order, C2's
    # dashcam throttle, C5's cap). The one channel it does carry is C3's representation, so that is
    # what is counted here, and the count is a FLOOR on what the arm did, not a census of it.
    "hybrid-F-lhreq": "recall_non_default_representation",
    "hybrid-F6-lhreq": "recall_non_default_representation",
    "hybrid-F6r-lhreq": "recall_non_default_representation",
    "hybrid-F6rm-lhreq": "recall_non_default_representation",
}


def _digests(rows):
    pos = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                    default=float).encode()).hexdigest()[:16]
    keys = sorted(json.dumps([r.get("t"), r.get("kind"), r.get("opportunity_ids"),
                              r.get("representation"), r.get("defer_s")],
                             sort_keys=True, default=float) for r in rows)
    setw = hashlib.sha256("".join(keys).encode()).hexdigest()[:16]
    return pos, setw


def census(rows):
    c = dict(decisions=len(rows))
    c["kinds"] = dict(Counter(str(r.get("kind")) for r in rows))
    reps = Counter(str(r.get("representation")) for r in rows if r.get("representation") is not None)
    c["representations"] = dict(reps)
    c["recall_non_default_representation"] = sum(
        1 for r in rows if r.get("representation") is not None and not r.get("representation_defaulted"))
    c["defer"] = sum(1 for r in rows if r.get("defer_s") is not None)
    c["decline"] = sum(1 for r in rows if str(r.get("kind")) == "decline")
    c["state_action"] = sum(1 for r in rows if str(r.get("kind")) == "state_action")
    c["feasibility_actions"] = c["decline"] + c["defer"]
    c["piece_split"] = sum(1 for r in rows if r.get("piece_tokens") is not None)
    c["desired_tier_set"] = sum(1 for r in rows if r.get("desired_tier") is not None)
    c["mu_set"] = sum(1 for r in rows if r.get("mu") is not None)
    # Channel-silent: the arm emitted the two unavoidable release kinds and used no other channel.
    c["channel_silent"] = (c["recall_non_default_representation"] == 0 and c["defer"] == 0
                           and c["decline"] == 0 and c["piece_split"] == 0
                           and c["desired_tier_set"] == 0)
    return c


def one(arm):
    import test_hybrid as TH
    t0 = time.time()
    try:
        rows, st = TH.dry(arm, SEED, N, run_s=RUN_S, ratio=RATIO, **LH)
    except Exception as e:                                                     # noqa: BLE001
        return arm, dict(error=repr(e)[:400], wall_s=round(time.time() - t0, 1))
    pos, setw = _digests(rows)
    rec = census(rows)
    rec.update(digest=pos, digest_setwise=setw, wall_s=round(time.time() - t0, 1),
               stats=dict(st or {}), declared_characteristic=DECLARED.get(arm))
    rec["characteristic_count"] = (rec.get(DECLARED[arm]) if arm in DECLARED else None)
    return arm, rec


def main(names):
    import multiprocessing as mp
    with mp.Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 8) as pool:
        got = {}
        for arm, rec in pool.imap_unordered(one, names):
            got[arm] = rec
            flag = "ERROR" if "error" in rec else ("CHANNEL-SILENT" if rec["channel_silent"] else "")
            print(f"  {arm:<36} {rec.get('decisions', '-'):>7} {rec.get('digest', '-'):>17} "
                  f"{rec.get('wall_s'):>7}s {flag}", flush=True)
    groups = {}
    for arm, rec in got.items():
        if "error" in rec:
            continue
        groups.setdefault(rec["digest"], []).append(arm)
    out = dict(_note=__doc__.strip().splitlines()[0],
               cell=dict(seed=SEED, n_devices=N, run_s=RUN_S, ratio=RATIO, dry=True, **LH),
               arms=got,
               identical_groups={k: sorted(v) for k, v in sorted(groups.items()) if len(v) > 1},
               distinct_arms=sorted(sorted(v)[0] for v in groups.values()),
               channel_silent=sorted(a for a, r in got.items()
                                     if "error" not in r and r["channel_silent"]),
               errors=sorted(a for a, r in got.items() if "error" in r))
    return out


if __name__ == "__main__":
    import arms as A
    import hybrid
    hybrid.register()
    names = sorted(A.ARMS)
    if len(sys.argv) > 1 and sys.argv[1] != "all":
        names = [n for n in names if n.startswith(sys.argv[1])]
    print(f"{len(names)} arms, cell seed {SEED} n {N} {RUN_S}s {RATIO} dry", flush=True)
    res = main(names)
    try:
        import _provenance
        res["_provenance"] = _provenance.stamp(script="baseline_prescreen.py", model="none-dry",
                                               device="nvidia_rtx_a6000", n=len(names))
    except Exception as e:                                                     # noqa: BLE001
        res["_provenance"] = {"git_commit": "unstamped", "script": "baseline_prescreen.py",
                              "note": f"stamp failed: {e!r}"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2, default=float))
    print("wrote", OUT)
    print("distinct:", len(res["distinct_arms"]), "groups with >1:", len(res["identical_groups"]),
          "channel-silent:", len(res["channel_silent"]), "errors:", len(res["errors"]))
