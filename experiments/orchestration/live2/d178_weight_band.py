#!/usr/bin/env python3
"""THE WEIGHT-SENSITIVE BAND: what bounds the FLEXIBLE-SPLIT consumer, and what does not bound it.

SCOPE, AND IT IS NARROWER THAN THIS FILE'S FIRST VERSION CLAIMED. Addendum 12 item 3 gives the
deficit weights TWO consumers, and this analysis bounds ONE of them:

  CONSUMER 2, THE FLEXIBLE SPLIT, IS BAND-LIMITED, and everything below is about it. The weights
  scale the flexible pool and hence `own_share`, so they can change an admission only for a
  request whose size falls in the band `own_floor < u <= own_share`.

  CONSUMER 1, THE ORDERING, IS NOT BAND-LIMITED AT ALL, and nothing here applies to it. It changes
  WHICH of the competing requests is considered first, not whether any single one fits a share, so
  it can move a decision for request sizes anywhere - including the 95.0 percent of share
  decisions that take `own_floor`, where two alert requests from differently starved devices now
  compete in a different order while both remain inside the same floor. That is why the user calls
  ordering the PRIMARY consumer, and it is what this file's own numbers predict: a mechanism acting
  only through `own_share` had almost nothing to act on.

So the verdict below is a statement about the SPLIT consumer in isolation. The Step 2b attribution
in `d178_deficit_feed_proofs.json` is what measures each consumer against the gain-0 comparator,
and it supersedes any reading of this file as a verdict on the rung.

CLAUDE.md Rule 2 asks which kind of null this is, and this file is the answer's evidence. It is
pure arithmetic over the FROZEN capacity numbers (`share_capacity.py`) and the reason histogram
`d178_deficit_feed_proofs.json` already measured. It runs no cell and constructs no arm.

THE ARGUMENT, IN ONE LINE. The deficit weights enter `share_admission.allowed` in exactly one
place: they scale the FLEXIBLE pool, hence `own_share = own_floor + flex_share`
(share_admission.py:162-168). So a weight can change an answer only for a request whose size falls
in the band

    own_floor  <  u  <=  own_share

because below the floor the admission GUARANTEE fires first (`own_floor`, tested before headroom
on purpose) and above the share the OVERSIZE rule fires (`oversize_alone` or
`oversize_wait_for_own_type`), and neither branch reads the weights. Borrowing is bounded by other
types' FLOORS, which D179 (3) does not weight, so it does not read them either.

WHAT THE MEASURED SIZES DO TO THAT BAND. `share_capacity.FACTORS` carries each type's MEASURED
median uncached tokens, from committed covex-v6-base cells in healthy windows:

    alert        374  tokens, against its own floor of 1,622.1  -> BELOW the band
    recall     7,717  tokens, against a share of at most 1,707.3 -> ABOVE the band (1.8x W_max)
    assistance 1,372  tokens, against a share of 515.9 to 1,294.3 -> ABOVE the band, by 78 tokens

So at the committed floors every type's TYPICAL request takes a weight-independent branch, and the
weighting is alive, correct, varying, delivered, read, and unable to change an admission. That is
Rule 2's CANCELLED BY GEOMETRY and it is not evidence about the deficit weighting.

ASSISTANCE IS THE NEAR MISS AND IS WORTH THE USER'S ATTENTION: 1,372 against 1,294.3 at the
maximum weight. It is 78 tokens, 6 percent, outside the band. So the mechanism is not far from
expressible, and whether it becomes expressible depends on numbers (the flexible fraction, the
floors) that D179 (3) and D180 fixed for other reasons.

THIS IS NOT A LIST OF REMEDIES. Every way to widen the band is a POLICY change and the user's to
rule on: weighting the floors (which D179 (3) explicitly does not do), making the oversize-alone
rule weight-sensitive, ordering the queue by weight instead of sizing the share by it, or changing
the flexible fraction. They are named so the report can name them, not chosen here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROOFS = REPO / "results/orchestration/live2/frozen_test/d178_deficit_feed_proofs.json"
OUT = REPO / "results/orchestration/live2/frozen_test/d178_weight_band.json"

for p in (str(HERE),):
    if p not in sys.path:
        sys.path.insert(0, p)
import share_admission as SA        # noqa: E402
import share_capacity as SCAP       # noqa: E402

W_MIN, W_MAX_WEIGHT = 1.0, 2.8      # the reachable range at gain 2.0 for a 0.90 target


def own_share(qtype: str, w_self: float, w_other: float) -> float:
    wt = {t: (w_self if t == qtype else w_other) for t in SA.TYPES}
    tot = sum(wt.values())
    return SCAP.FLOORS_TOKENS[qtype] + SCAP.FLEXIBLE_TOKENS * (wt[qtype] / tot)


def main() -> int:
    bands: Dict[str, Any] = {}
    for t in SA.TYPES:
        u = float(SCAP.FACTORS[t]["median_uncached"])
        lo = own_share(t, W_MIN, W_MAX_WEIGHT)          # this type at its weakest
        hi = own_share(t, W_MAX_WEIGHT, W_MIN)          # this type at its strongest
        eq = own_share(t, 1.0, 1.0)
        floor = SCAP.FLOORS_TOKENS[t]
        inside = floor < u <= hi
        decided_by_weight = lo < u <= hi
        branch = ("own_floor (the admission GUARANTEE, tested before headroom)" if u <= floor
                  else ("own_share or borrow (WEIGHT-SENSITIVE)" if u <= hi
                        else "oversize (weight-independent)"))
        bands[t] = dict(
            median_uncached=u, floor=floor,
            own_share_at_weakest=round(lo, 1), own_share_equal=round(eq, 1),
            own_share_at_strongest=round(hi, 1),
            weight_sensitive_band=[floor, round(hi, 1)],
            median_inside_band=bool(inside),
            median_decision_changes_with_weight=bool(decided_by_weight),
            branch_a_median_request_takes=branch,
            distance_to_band_tokens=round(u - hi, 1) if u > hi else round(u - floor, 1),
            distance_to_band_pct=(round(100.0 * (u - hi) / hi, 1) if u > hi
                                  else round(100.0 * (u - floor) / max(floor, 1.0), 1)),
            source=SCAP.FACTORS[t].get("lambda_basis", ""))
    out: Dict[str, Any] = {
        "_what": ("why the D178 (1) deficit weights move no admission at the committed D179 / "
                  "D180 / D181 floors: the weight-sensitive band and where each type's measured "
                  "median request sits relative to it"),
        "_not_a_cell": "pure arithmetic over frozen numbers plus an already-measured histogram",
        "_the_one_read_of_the_weights": "share_admission.py:162-168, which scales the FLEXIBLE "
                                        "pool only; the floors are not weighted (D179 (3))",
        "capacity": dict(w_max_tokens=SCAP.W_MAX_TOKENS,
                         floors_tokens=dict(SCAP.FLOORS_TOKENS),
                         flexible_tokens=round(SCAP.FLEXIBLE_TOKENS, 1)),
        "weight_range_at_gain_2": {"alert": [1.0, 1.5], "recall": [1.0, 2.8],
                                   "assistance": [1.0, 2.8],
                                   "_why_they_differ": ("a shortfall cannot exceed its own "
                                                        "target, and the form is unnormalised")},
        "bands": bands,
        "_scope": ("this bounds the FLEXIBLE-SPLIT consumer ONLY. The ORDERING consumer is not "
                   "band-limited: it reorders requests that are all inside their own floor, where "
                   "95.0 percent of share decisions sit, so none of the numbers below bound it."),
        "verdict": ("FOR THE SPLIT CONSUMER ALONE: cancelled by geometry, with a measured "
                    "denominator. Of the 10,657 share "
                    "decisions in the dry seed-4 posted cell, 10,120 (95.0 percent) took "
                    "`own_floor`, 197 + 56 + 26 took an OVERSIZE branch, 57 took `w_max` and 17 "
                    "took a background borrow bounded by other types' unweighted FLOORS: 10,473 "
                    "decisions, 98.3 percent, on branches that do not read the weights at all. "
                    "The 184 that DID take the weight-sensitive `own_share` branch are all RECALL "
                    "ADMITS, and the feed RAISED recall's weight (median 1.97 against 1.0 at the "
                    "equal split), so its share grew and every one of the 184 admitted either "
                    "way. Nothing was left that a weight could flip. The structural reason is the "
                    "band: alert's median request is BELOW its own floor (374 against 1,622.1, so "
                    "the admission guarantee fires first), recall's is 4.5x ABOVE the top of its "
                    "band and 1.8x above W_max (7,717 against 1,707.3), and assistance's is 6 "
                    "percent above the top of its band (1,372 against 1,294.3)."),
        "weight_sensitive_decision_share": {
            "own_share_decisions": 184, "total_share_decisions": 10657,
            "fraction": 0.0173,
            "_all_184_are": "recall ADMITS, which the feed's higher recall weight only made more "
                            "comfortable, so none could flip"},
    }
    if PROOFS.exists():
        p = json.loads(PROOFS.read_text())
        hist = {}
        def _counts(d: Any) -> Dict[str, Any]:
            return {k: v for k, v in (d or {}).items() if k.startswith("share_reason_")}
        rows = (p.get("a_other_arms_unchanged") or {}).get("rows") or []
        for r in rows:
            if str(r.get("arm", "")).startswith("covex-v6-state-shares"):
                hist[r["arm"]] = _counts(r.get("share_counts"))
        out["measured_reason_histogram"] = hist
        out["_histogram_note"] = (
            "every reason a share decision took in the dry cell. A reason that is never "
            "`own_share` or `borrow_*` is a decision the weights could not have changed.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({t: dict(u=b["median_uncached"], floor=b["floor"],
                              share_max=b["own_share_at_strongest"],
                              branch=b["branch_a_median_request_takes"],
                              weight_can_change_it=b["median_decision_changes_with_weight"])
                      for t, b in bands.items()}, indent=1))
    print(out["verdict"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
