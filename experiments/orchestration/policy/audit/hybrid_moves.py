#!/usr/bin/env python3
"""D138 P1 gate: prove each hybrid component MOVES A DECISION before any cell is scored.

A switch that is configured is not a switch that moved a decision. Five plumbing faults this week
were each found only after a null had been produced, and a port shipped today passed both required
proofs perfectly while producing zero decisions of its characteristic kind. Well-formedness and
fairness establish neither that a mechanism ran nor that it could.

This compares two ARM NAMES rather than two switch settings, because the hybrid lattice is
registered as fixed configurations. It diffs the decision log AND the emitted-action observables,
because `decision.jsonl` cannot see representation or session actions on its own.

SCOPED BY SIZE, because three verdicts this week needed a size scope rather than a correction: a
component inert at 10 may fire at 16.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

IGNORE = {"decision_latency_ms", "t", "arm", "arm_version", "note"}

# The isolating pairs. C2 requires C1 and C3 requires C1+C2, so only C1 and C5 can be tested
# alone; the rest are tested as the single addition to their own prerequisite.
PAIRS = [
    ("C1", "hybrid-base", "hybrid-c1"),
    ("C5", "hybrid-base", "hybrid-c5"),
    ("C1 under the C5 cap", "hybrid-c5", "hybrid-c1c5"),
    ("C2 (k_r 1.0)", "hybrid-c1", "hybrid-c1c2k1"),
    ("C2 (k_r 2.0)", "hybrid-c1", "hybrid-c1c2k2"),
    ("C3 (k_r 1.0)", "hybrid-c1c2k1", "hybrid-c1c2k1c3"),
    ("C3 (k_r 2.0)", "hybrid-c1c2k2", "hybrid-c1c2k2c3"),
]


def _register_hybrid() -> List[str]:
    """Importing `hybrid` is what registers its arms; `arms.py` does not import it.

    `live2/hybrid/__init__.py` calls `register()` on import, which inserts the CONFIGS into
    `arms.ARMS`. Nothing in the flash-owned path imports that package, so `make_arm("hybrid-c1")`
    raises until it is imported here. This touches no H100-owned file.
    """
    H.setup_paths()
    import hybrid  # noqa: F401
    import arms as A
    return sorted(n for n in A.ARMS if str(n).startswith("hybrid-"))


def _rows(run: Path) -> List[Dict[str, Any]]:
    out = []
    for line in open(Path(run) / "decision.jsonl"):
        try:
            out.append(json.loads(line))
        except Exception:                                              # noqa: BLE001
            continue
    return out


def _digest(rows: List[Dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for d in rows:
        h.update(json.dumps({k: v for k, v in d.items() if k not in IGNORE},
                            sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def one(arm: str, n: int, seed: int, run_s: float, tmp: Path) -> Dict[str, Any]:
    sink: Dict[str, Any] = {}
    with H.capture_emitted_actions(sink):
        r = H.run_fleet_cell(tmp / ("%s_n%d_s%d" % (arm, n, seed)), n, run_s=run_s, seed=seed,
                             arm_name=arm, switches={})
    rows = _rows(Path(r["outdir"]) / "run")
    rep = {k: v[0] for k, v in sink["recall_representation"].items()}
    return dict(
        arm=arm, n_decisions=len(rows), digest=_digest(rows),
        kinds=dict(Counter(d.get("kind") for d in rows)),
        representation=dict(Counter(rep.values())),
        credit=dict(Counter("INJECTED" if v is None else "CHOSEN"
                            for v in sink["pre_default_representation"].values())),
        session_actions=dict(Counter(a for _, a in sink["session_actions"])),
        rows=rows, rep_map=rep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="12,16")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-s", type=float, default=600.0)
    a = ap.parse_args(argv)
    H.assert_dev_seed(a.seed)

    names = _register_hybrid()
    print("registered hybrid arms: %d -> %s" % (len(names), names), flush=True)
    missing = sorted({x for _, b, t in PAIRS for x in (b, t)} - set(names))
    if missing:
        print("REFUSED: these configurations are not registered: %r" % missing)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="hybmoves_"))
    cache: Dict[Any, Dict[str, Any]] = {}
    results: List[Dict[str, Any]] = []
    for n in [int(x) for x in a.sizes.split(",") if x.strip()]:
        for label, base, test in PAIRS:
            for arm in (base, test):
                if (arm, n) not in cache:
                    cache[(arm, n)] = one(arm, n, a.seed, a.run_s, tmp)
            A_, B_ = cache[(base, n)], cache[(test, n)]
            ndiff = sum(1 for i in range(min(len(A_["rows"]), len(B_["rows"])))
                        if {k: v for k, v in A_["rows"][i].items() if k not in IGNORE}
                        != {k: v for k, v in B_["rows"][i].items() if k not in IGNORE})
            rep_diff = sum(1 for k in set(A_["rep_map"]) | set(B_["rep_map"])
                           if A_["rep_map"].get(k) != B_["rep_map"].get(k))
            sess_diff = A_["session_actions"] != B_["session_actions"]
            moved = bool(ndiff or rep_diff or sess_diff
                         or A_["n_decisions"] != B_["n_decisions"])
            results.append(dict(
                component=label, n_devices=n, base=base, test=test,
                decisions=[A_["n_decisions"], B_["n_decisions"]],
                digests=[A_["digest"], B_["digest"]],
                decision_rows_differing=ndiff, representation_differing=rep_diff,
                session_actions_differ=bool(sess_diff),
                representation=[A_["representation"], B_["representation"]],
                credit=[A_["credit"], B_["credit"]],
                MOVED=moved,
                verdict=("fires" if moved else
                         "DID NOT MOVE ANY DECISION at this size: UNEXERCISED (category 4), "
                         "not a negative. Scope the verdict by SIZE.")))
            print("n=%-3d %-22s %s  rows_diff=%d rep_diff=%d" %
                  (n, label, "MOVED" if moved else "NO MOVE", ndiff, rep_diff), flush=True)

    out = dict(check="hybrid_component_moves", is_measurement=False,
               label="D138 P1 gate. Each hybrid component must MOVE A DECISION before any cell is "
                     "scored. Decision-log diff plus emitted-action observables.",
               regime="Regime 3: DEFAULTS['representation'] = D2 restored at a0bcb51, so the b7 "
                      "base takes the FULL HISTORY and any RECENT share is a component CHOOSING "
                      "it rather than a default supplying it.",
               unexercised_by_design=dict(
                   C4="INERT until memory pressure exists; placeholder emits no session action",
                   C6="OFF until the chooser lands"),
               seed=a.seed, run_s=a.run_s, pairs=results)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
