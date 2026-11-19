"""Scorer-input domain audit: verify a scorer's INPUT is a measurement before reading its OUTPUT.

D134. Session 2's Part C robot-accuracy column ranked every arm BACKWARDS because
`cloud_payload.cloud_letter` is the placeholder "X" on the dry screen while gold letters are A to
E, so `cloud_correct` was always False and standing accuracy collapsed to
(fraction answered on device) x device accuracy, a column that PENALISES on-time delivery.

The lesson is not "look for a flat column". The column was NOT flat: it spread 0.0289 to 0.2143,
because the spread tracked how many questions each arm delivered on time, each then scored against
a guaranteed-wrong placeholder. A flat column advertises that something is broken; a spread looks
like a result. Consistency check 3, which watches for constants where a distribution is expected,
would have passed it.

So this check runs one layer earlier: for every field the scorer consumes, compare the OBSERVED
domain against the domain the field is supposed to have, and refuse the column when they do not
meet. It is the same discipline as the read-path check used on `order`, `desired_tier` and
`representation` -- there, that a mechanism's output reaches a decision; here, that a scorer's
input is a measurement rather than a placeholder.

Usage:  python3 published_scoring_inputs.py <run_dir_with_outcomes.jsonl> [...]
"""
from __future__ import annotations
import collections, json, sys
from pathlib import Path

GOLD_LETTERS = set("ABCDE")

# field -> (accessor, expected domain description, predicate for a REAL value)
def _cp(r):
    return r.get("cloud_payload") or {}

FIELDS = {
    "cloud_payload.cloud_letter": (lambda r: _cp(r).get("cloud_letter"),
                                   "a gold letter in %s" % sorted(GOLD_LETTERS),
                                   lambda v: v in GOLD_LETTERS),
    "cloud_payload.cloud_score": (lambda r: _cp(r).get("cloud_score"),
                                  "a float score, not None",
                                  lambda v: isinstance(v, (int, float))),
    "cloud_payload.on_time": (lambda r: _cp(r).get("on_time"),
                              "True or False",
                              lambda v: isinstance(v, bool)),
    "within_L": (lambda r: r.get("within_L"), "True or False",
                 lambda v: isinstance(v, bool)),
}


def audit(rows):
    report = {}
    for name, (get, expected, ok) in FIELDS.items():
        vals = [get(r) for r in rows]
        present = [v for v in vals if v is not None]
        real = [v for v in present if ok(v)]
        dist = collections.Counter(repr(v) for v in present)
        report[name] = dict(
            rows=len(vals), present=len(present), distinct=len(dist),
            observed=dict(list(dist.most_common(8))),
            expected_domain=expected,
            real_values=len(real),
            usable=bool(real),
            verdict=("USABLE" if real else
                     ("PLACEHOLDER: present but no value lies in the expected domain"
                      if present else "ABSENT: never populated")),
        )
    return report


def main(argv):
    rows = []
    for d in argv:
        f = Path(d)
        f = f if f.name == "outcomes.jsonl" else f / "outcomes.jsonl"
        rows += [json.loads(l) for l in open(f)]
    rep = audit(rows)
    rep["_rows"] = len(rows)
    rep["_scorable"] = sorted(k for k, v in rep.items() if isinstance(v, dict) and v.get("usable"))
    rep["_refused"] = sorted(k for k, v in rep.items()
                             if isinstance(v, dict) and not v.get("usable"))
    print(json.dumps(rep, indent=1))
    return 0 if not rep["_refused"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
