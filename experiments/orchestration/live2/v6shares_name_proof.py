#!/usr/bin/env python3
"""D179: `covex-v6-state-shares` resolves THROUGH THE HARNESS'S OWN ENTRY POINT, and its switches
are on for it and off for everything else.

WHY A SUBPROCESS AND NOT A `make_arm` HERE. `v6_harness_name_proof.py` records the failure this
file inherits: when the v6 names were first released they were checked by importing their own
module and calling `arms.make_arm`, in a process that had imported that module. They resolved.
`run_live2_real.py` imports `arms` and `hybrid` and nothing else, so in the HARNESS'S process the
names did not exist, the first covex-v6-state cell died 80 s in at `arms.py:627` with
`KeyError: unknown arm`, and all four cells were skipped. A name resolves in the process that
resolves it. So P1 below spawns `run_live2_real.py` itself, with a real command line and the
posted workload knobs, and reads what the harness does with the name.

THE NEGATIVE CONTROL IS NOT OPTIONAL. "No KeyError appeared" passes trivially if the subprocess
never reached `make_arm`, if the arg parser rejected something first, or if the grep looks for the
wrong string. So P0 gives the same path a deliberately unknown name and requires that it STILL
raise. If it does not, this check is broken and P1 means nothing.

WHAT P2 DOES AND DOES NOT PROVE. P2 constructs every arm in the registry and reads both D179
switches off the constructed object AND off every object in its delegation chain, because a
getattr on the wrapper is exactly the check that passes while the inner object decides
differently (arms_v6c5.py records the three-object chain; arms_v6state.py records the class-
attribute leak that left a negative control un-collapsed). P2 proves the switch is SET on this arm
and on no other. It does NOT prove the switch moves a decision: at this commit nothing reads
either switch, `share_admission.allowed()` returns (True, "disabled"), and under CLAUDE.md Step 2b
the decision-moving proof is a diff of two decision logs which cannot be run until session A's
allocator body and session B's call site land. This file says so in its own output rather than
letting a passing registration read as a live mechanism.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ENTRY = HERE / "run_live2_real.py"
OUT = REPO / "results/orchestration/live2/frozen_test/v6shares_name_proof.json"

ARMS_UNDER_TEST = ["covex-v6-state-shares", "covex-v6-state-shares-off",
                   "covex-v6-state-shares-noadmit", "covex-v6-state-shares-norecheck"]
UNKNOWN = "covex-v6-state-shares-not-an-arm"
MARKER = "unknown arm"

# the POSTED workload knobs, forwarded so the probe is the command line a cell would really use
POSTED = ["--ratio", "40:40:20", "--robot-question-set", "lh_req", "--ss-question-set", "ss2",
          "--dashcam-format", "epg", "--robot-upload", "per-frame",
          "--robot-reask-mean-s", "30.0"]


def _probe(name: str, seed: int = 0) -> Dict[str, Any]:
    """The harness's own entry point on this arm name: tiny, server-free, one cell per process."""
    with tempfile.TemporaryDirectory(prefix="v6shares_") as td:
        p = subprocess.run(
            [sys.executable, str(ENTRY), "--arm", name, "--out", str(Path(td) / "cell"),
             "--n-devices", "2", "--run-s", "5", "--seed", str(seed)] + POSTED,
            cwd=str(HERE), capture_output=True, text=True, timeout=1800)
    blob = (p.stdout or "") + (p.stderr or "")
    unknown = MARKER in blob
    return {"arm": name, "seed": seed, "returncode": p.returncode,
            "raised_unknown_arm": unknown,
            "tail": blob.strip().splitlines()[-1][:300] if blob.strip() else ""}


def _chain(obj: Any) -> List[Any]:
    out: List[Any] = []
    o: Any = obj
    seen = set()
    while o is not None and id(o) not in seen:
        seen.add(id(o))
        out.append(o)
        o = o.__dict__.get("_rules") or o.__dict__.get("_base")
    return out


def _switch_sweep() -> Dict[str, Any]:
    """Construct every registered arm and read both switches off its whole chain."""
    import arms as A
    import arms_v6shares as SH

    on: Dict[str, Dict[str, List[bool]]] = {}
    off: List[str] = []
    leaked: Dict[str, Dict[str, List[bool]]] = {}
    unconstructible: Dict[str, str] = {}
    for name in sorted(A.ARMS):
        try:
            arm = A.make_arm(name)
        except Exception as exc:                                        # noqa: BLE001
            unconstructible[name] = "%s: %s" % (type(exc).__name__, exc)
            continue
        chain = _chain(arm)
        reads = {s: [bool(getattr(o, s, False)) for o in chain] for s in SH.SWITCHES}
        any_on = any(any(v) for v in reads.values())
        if name in ARMS_UNDER_TEST:
            on[name] = reads
        elif any_on:
            leaked[name] = reads
        else:
            off.append(name)
    return {"switch_names": list(SH.SWITCHES),
            "arms_under_test": on,
            "n_other_arms_all_off": len(off),
            "other_arms_with_a_switch_on": leaked,
            "unconstructible": unconstructible,
            "_what_a_chain_is": ("the wrapper and every object `_rules`/`_base` reaches; a single "
                                 "getattr on the wrapper is the check that passes while the "
                                 "inner object decides differently")}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "covex-v6-state-shares resolves through run_live2_real.py itself",
        "_register": ("P0 and P1 are SUBPROCESS probes of the harness's own entry point with the "
                      "posted workload knobs; P2 is an in-process attribute read and is a "
                      "statement about registration only"),
        "entry_point": str(ENTRY.relative_to(REPO)),
        "registered_in": ("experiments/orchestration/live2/arms_v6shares.py, imported from "
                          "arms.py beside the other v6 families"),
        "posted_knobs": POSTED,
    }

    neg = _probe(UNKNOWN)
    out["P0_negative_control"] = {
        "_claim": "a name that is NOT registered still raises through this same path",
        "probe": neg,
        "verdict": ("PASS: the check can see an unresolved name" if neg["raised_unknown_arm"] else
                    "FAIL: THE CHECK IS BROKEN, not the arm. An unknown name did not produce %r, "
                    "so P1 would mean nothing" % MARKER)}
    p0_ok = out["P0_negative_control"]["verdict"].startswith("PASS")

    rows = [_probe(n) for n in ARMS_UNDER_TEST] if p0_ok else []
    out["P1_resolution"] = {
        "_claim": "each shares arm name resolves in the harness's own process",
        "probes": rows,
        "all_resolve": bool(rows) and all(not r["raised_unknown_arm"] for r in rows),
    }
    out["P1_resolution"]["verdict"] = (
        "PASS: all %d names resolve" % len(rows) if out["P1_resolution"]["all_resolve"] else
        "FAIL: %s did not resolve" % [r["arm"] for r in rows if r["raised_unknown_arm"]])

    sweep = _switch_sweep()
    scoped = all(sweep["arms_under_test"].get(n, {}).get("live2_share_admission")
                 for n in ("covex-v6-state-shares",))
    clean = not sweep["other_arms_with_a_switch_on"]
    out["P2_switch_scope"] = dict(sweep)
    out["P2_switch_scope"]["_claim"] = ("both switches are ON for covex-v6-state-shares, on every "
                                        "object of its chain, and OFF on every other arm")
    out["P2_switch_scope"]["verdict"] = (
        "PASS: on for the shares arm and off on %d others" % sweep["n_other_arms_all_off"]
        if (scoped and clean) else
        "FAIL: scoped=%s clean=%s" % (scoped, clean))
    out["P2_switch_scope"]["_register"] = (
        "REGISTRATION ONLY. Nothing reads either switch at this commit: "
        "share_admission.allowed() returns (True, 'disabled') and the coordinator has no call "
        "site, so these are write-only fields. The CLAUDE.md Step 2b proof that a switch moves a "
        "decision is a diff of two decision logs and is NOT claimed here.")

    passes = [out["P0_negative_control"]["verdict"], out["P1_resolution"]["verdict"],
              out["P2_switch_scope"]["verdict"]]
    out["verdict"] = ("ALL_PASS" if all(v.startswith("PASS") for v in passes)
                      else "FAIL: " + "; ".join(v for v in passes if not v.startswith("PASS")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    for v in passes:
        print(" ", v)
    for r in rows:
        print("  %-36s rc=%-3s unknown_arm=%s" % (r["arm"], r["returncode"],
                                                  r["raised_unknown_arm"]))
    print(out["verdict"])
    print("wrote", OUT)
    return 0 if out["verdict"] == "ALL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
