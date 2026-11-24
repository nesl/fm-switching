#!/usr/bin/env python3
"""D209 (2) Step 2b at row level: how many decisions differ between the before and after trees on
one dry s4 cell, and the FIRST one.

BOTH COUNTS ARE REPORTED AND THEY ARE NOT THE SAME CLAIM, per `test_hybrid._differing`'s own
warning and the D205 step-2b precedent (`1b99b6af`): the POSITIONAL count saturates near the log
length once an early divergence desynchronises the rest, so the SETWISE count is the move proof and
the positional count is reported beside it, never read as the magnitude.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load(p: Path) -> List[Dict[str, Any]]:
    return json.loads(p.read_text())


def key(r: Dict[str, Any]) -> str:
    return json.dumps(r, sort_keys=True, separators=(",", ":"), default=float)


def decision_key(r: Dict[str, Any]):
    """The COMMITTED definition of a decision, copied from `test_hybrid._decision_key`: the
    period, the action kind, the opportunities it acts on, the representation and the defer. A
    whole-row diff is STRICTER than this and counts a changed note or piece_tokens as a differing
    decision, so both are reported and the committed key is the one comparable with the D205
    step-2b numbers."""
    return (r.get("t"), r.get("kind"), tuple(r.get("opportunity_ids") or ()),
            r.get("representation"), r.get("defer_s"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    b, af = load(Path(a.before)), load(Path(a.after))
    kb, ka = [key(r) for r in b], [key(r) for r in af]
    sb, sa = set(kb), set(ka)

    positional = sum(1 for i in range(max(len(kb), len(ka)))
                     if (kb[i] if i < len(kb) else None) != (ka[i] if i < len(ka) else None))
    first = None
    for i in range(max(len(kb), len(ka))):
        x = b[i] if i < len(b) else None
        y = af[i] if i < len(af) else None
        if key(x) if x is not None else None:
            pass
        if (kb[i] if i < len(kb) else None) != (ka[i] if i < len(ka) else None):
            diff_fields = sorted(
                k for k in set(list((x or {}).keys()) + list((y or {}).keys()))
                if (x or {}).get(k) != (y or {}).get(k))
            first = {"row_index": i, "before": x, "after": y, "fields_that_differ": diff_fields}
            break

    from collections import Counter
    cb_, ca_ = (Counter(decision_key(r) for r in b), Counter(decision_key(r) for r in af))
    committed_setwise = sum(((cb_ - ca_) + (ca_ - cb_)).values())

    doc = {"label": a.label,
           "setwise_differing_decisions_COMMITTED_KEY": committed_setwise,
           "before_rows": len(b), "after_rows": len(af),
           "setwise_only_in_before": len(sb - sa), "setwise_only_in_after": len(sa - sb),
           "setwise_differing_decisions": len(sb ^ sa),
           "positional_differing_rows_NOT_the_magnitude": positional,
           "identical": sb == sa and kb == ka,
           "first_differing_decision": first}
    Path(a.out).write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({k: doc[k] for k in
                      ("label", "before_rows", "after_rows", "setwise_differing_decisions", "setwise_differing_decisions_COMMITTED_KEY",
                       "positional_differing_rows_NOT_the_magnitude", "identical")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
