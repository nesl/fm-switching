#!/usr/bin/env python3
"""STANDING CHECK: before reporting any A-versus-B comparison, confirm at least one DECISION differs.

Three times in two nights a switch was reported as a result when it never reached a decision:
my own `--candidate` parser turning `mu_mode=scarcity` into a literal key, the class-level
`C_INFLIGHT_DEFAULT` that `make_arm` discarded, and D131's B2 whose `z[RC]` reaches 543.58 and
never reaches admission. In each case A and B were byte-identical and the honest reading was
"the mechanism is ABSENT", not "the mechanism failed".

This runs two conditions on the SAME seed and size and answers one question: do the decision logs
differ, and where. It also surfaces each arm's own `stats`, so a counter that a switch is supposed
to increment (`rc_priority_epochs`) can be seen to fire or not fire rather than inferred.

A null from two identical decision logs is an ABSENT-LINK result under CLAUDE.md Step 2 and may
not be reported as a negative.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

# Fields that differ for bookkeeping reasons and say nothing about the decision taken.
IGNORE = {"decision_latency_ms", "t"}


def _decisions(run_dir: Path) -> List[Dict[str, Any]]:
    p = Path(run_dir) / "decision.jsonl"
    out = []
    for line in open(p):
        try:
            out.append(json.loads(line))
        except Exception:                                              # noqa: BLE001
            continue
    return out


def _key(d: Dict[str, Any]) -> Tuple:
    return tuple(sorted((k, json.dumps(v, sort_keys=True, default=str))
                        for k, v in d.items() if k not in IGNORE))


def compare(a_sw: Dict[str, Any], b_sw: Dict[str, Any], n: int, seed: int, run_s: float,
            arm: str) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="covex_moves_"))
    res = {}
    for label, sw in (("A", a_sw), ("B", b_sw)):
        r = H.run_fleet_cell(tmp / label, n, run_s=run_s, seed=seed, arm_name=arm, switches=sw)
        res[label] = r
    da, db = _decisions(Path(res["A"]["outdir"]) / "run"), _decisions(Path(res["B"]["outdir"]) / "run")

    n_diff = 0
    first = None
    fields: Dict[str, int] = {}
    for i in range(min(len(da), len(db))):
        if _key(da[i]) != _key(db[i]):
            n_diff += 1
            if first is None:
                first = dict(index=i,
                             A={k: da[i].get(k) for k in sorted(da[i]) if k not in IGNORE},
                             B={k: db[i].get(k) for k in sorted(db[i]) if k not in IGNORE})
            for k in set(da[i]) | set(db[i]):
                if k in IGNORE:
                    continue
                if json.dumps(da[i].get(k), sort_keys=True, default=str) != \
                   json.dumps(db[i].get(k), sort_keys=True, default=str):
                    fields[k] = fields.get(k, 0) + 1

    moved = bool(n_diff or len(da) != len(db))
    return dict(
        n_decisions=dict(A=len(da), B=len(db)),
        decisions_differing=n_diff,
        differing_fields=dict(sorted(fields.items(), key=lambda x: -x[1])),
        first_difference=first,
        SWITCH_MOVED=moved,
        verdict=("the switch reaches at least one decision; an A-vs-B comparison is meaningful"
                 if moved else
                 "ABSENT LINK. The decision logs are IDENTICAL, so the switch never reaches a "
                 "decision. Any null here is an absent-mechanism artefact under CLAUDE.md Step 2 "
                 "and MUST NOT be reported as a negative result."),
        arm_stats=dict(A=res["A"].get("arm_stats"), B=res["B"].get("arm_stats")),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-devices", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--run-s", type=float, default=600.0)
    ap.add_argument("--arm", default="covex-v13")
    ap.add_argument("--pairs", required=True,
                    help="name:Aswitches|Bswitches;... with switches as k=v,k=v (empty = base)")
    a = ap.parse_args(argv)
    H.assert_dev_seed(a.seed)

    def parse(s: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for item in s.split(","):
            item = item.strip()
            if not item:
                continue
            k, _, v = item.partition("=")
            if not _:
                out[k] = True
                continue
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
        return out

    results = {}
    for spec in a.pairs.split(";"):
        spec = spec.strip()
        if not spec:
            continue
        name, _, rest = spec.partition(":")
        asw, _, bsw = rest.partition("|")
        results[name] = compare(parse(asw), parse(bsw), a.n_devices, a.seed, a.run_s, a.arm)
        print(name, "SWITCH_MOVED =", results[name]["SWITCH_MOVED"],
              "| differing decisions:", results[name]["decisions_differing"], flush=True)

    out = dict(check="covex_harden_switch_moves", is_measurement=False,
               label="STANDING CHECK. Does the switch reach a DECISION. Identical decision logs "
                     "mean an ABSENT LINK, not a negative result.",
               n_devices=a.n_devices, seed=a.seed, arm=a.arm, pairs=results)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
