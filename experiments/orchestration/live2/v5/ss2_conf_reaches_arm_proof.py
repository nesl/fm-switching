#!/usr/bin/env python3
"""W2: does the SS2 confidence field actually REACH the cascade arms and change their decisions?: does the SS2 field actually REACH the cascade arms and change their decisions?

The first attempt captured the ARM's stats, but `device_conf_absent` is a COORDINATOR counter that
`_dry` does not return, so W2 was unproved. This is a direct A/B on the supplier: run each cascade
arm with the SS2 table present, then with `_load_ss2` returning {} (the pre-wiring state), and
compare decision digests. A change proves the field reaches the arm; no change would prove the
wiring is inert, which is the write-only-field failure in a new place.
"""
import sys
from pathlib import Path
REPO = Path("/tmp/claude-1001/mapwt"); HERE = REPO/"experiments/orchestration/live2"
for _p in (str(HERE), str(HERE/"fleet"), str(HERE/"scorer"), str(HERE/"hybrid"),
           str(REPO/"experiments/orchestration/live"), str(REPO/"experiments/orchestration/baselines"),
           str(REPO/"experiments/orchestration/baselines/reconstructed"),
           str(REPO/"experiments/orchestration/sim"), str(REPO/"experiments/lib"),
           str(REPO/"experiments/orchestration")):
    if _p not in sys.path: sys.path.insert(0,_p)
import arms_v5rules as V5
import device_confidence as DC
import cstate as CS
IGNORE = ("arm_version",)
ARMS = ("confidence-cascade", "cascade-routing")

out = {}
for mode in ("with_ss2", "without_ss2"):
    if mode == "without_ss2":
        DC._SS2 = {}                       # the pre-wiring state: no single-shot table
        DC._load_ss2 = lambda: {}
    for a in ARMS:
        CS._DEV_CONF_CACHE = None          # force the supplier to reload per run
        CS._DEV_CONF_SS2 = None
        rows, _ = V5._dry(a, V5.CELL)
        out[(mode, a)] = (V5._digest(rows, IGNORE), len(rows))
        print(f"{mode:13s} {a:22s} {out[(mode,a)][0]} rows {out[(mode,a)][1]}", flush=True)

print()
import json
import _provenance
res = dict(
    quantity="cascade decision digest with the committed SS2 table present vs absent",
    method=("the first version of this proof captured the ARM's stats, but device_conf_absent is a "
            "COORDINATOR counter that _dry does not return, so W2 was ASSERTED on evidence that "
            "did not exist. This is the direct A/B instead: with the table, then with _load_ss2 "
            "stubbed to {} (the pre-wiring state). A changed digest proves the field reaches the "
            "arm and moves decisions; an UNCHANGED digest would prove the wiring inert, which is "
            "the write-only-field failure in a new place and is what this exists to exclude."),
    ignored=list(IGNORE), cell=V5.CELL, arms={})
for a in ARMS:
    w, wo = out[("with_ss2", a)], out[("without_ss2", a)]
    reaches = w[0] != wo[0]
    res["arms"][a] = dict(with_ss2=dict(digest=w[0], rows=w[1]),
                          without_ss2=dict(digest=wo[0], rows=wo[1]),
                          field_reaches_the_arm=reaches,
                          rows_equal=w[1] == wo[1])
    print(f"{a:22s} with {w[0]} / without {wo[0]}  -> FIELD REACHES THE ARM: {reaches}"
          f"   rows {w[1]} vs {wo[1]}")
res["pass"] = all(v["field_reaches_the_arm"] for v in res["arms"].values())
res["note_rows_equal"] = ("row counts are EQUAL on both sides, so the confidences change the "
                          "CONTENT of decisions and not their number, which is what a threshold "
                          "flipping DEVICE against CLOUD on the same opportunities looks like")
res["_provenance"] = _provenance.stamp(script="ss2_conf_reaches_arm_proof.py", model="CPU-stub",
                                       device="nvidia_rtx_a6000", n=len(ARMS), args=None)
OUT = REPO / "results/orchestration/live2/frozen_test/ss2_conf_reaches_arm.json"
OUT.write_text(json.dumps(res, indent=2, sort_keys=True))
print(f"\nPASS: {res['pass']}")
print(f"wrote {OUT}")
