"""StudySS2 kit: the CODA-LM 1-10 judge parser and its gate.

WHY THIS FILE EXISTS BEFORE THE DATA DOES. The StudySS1 rating parser dropped 667 of 700
judgements while reporting a working `judge_mean 0.1818` and an `agreement 0.5758`, and the largest
single cause (399 of 667) was the judge obeying the required `[[x]]` format while the regex
rejected the VALUE, because `[01](?:\\.5)?` does not match `1.0`. A 1-10 scale with CODA-LM's own
prompt shares none of that regex's assumptions, so this parser is NEW CODE and is gated before any
1-10 number is committed.

THE SPECIFIC TRAP ON A 1-10 SCALE IS `10`, AND IT IS WORSE THAN A PARSE FAILURE. A pattern built
from a single digit class reads `10` as `1`: it does not drop the rating, it silently returns the
BOTTOM of the scale for an answer the judge placed at the TOP. That is a confident wrong number
rather than a missing one, and it would not appear in a coverage figure at all. `_RATING10` therefore
matches `10` before any single digit, and `parse_codalm_rating` rejects anything outside 1 to 10.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Order matters: 10 must be tried before the single digits, or "10" parses as "1".
# Accepts the shapes a judge was OBSERVED to emit on StudySS1 (double bracket, single bracket, bare
# after a label) plus "n/10", and tolerates a trailing ".0".
# `_N` is the number alternative. The trailing (?![\d.]) is LOAD-BEARING: without it "Rating: 11"
# matches the leading 1 and returns 1.0, and "Rating: 100" matches 10 and returns 10.0. Both are
# CONFIDENT WRONG NUMBERS at the ends of the scale rather than parse failures, so neither would show
# up in a coverage figure. The self-test below caught both in this file's own first pattern.
_N = r"(10(?:\.0+)?|[1-9](?:\.\d+)?)(?![\d.])"
_RATING10 = re.compile(
    r"(?:\[\[\s*" + _N + r"\s*\]\]"                                  # [[7]]  [[10]]  [[7.5]]
    r"|\[\s*" + _N + r"\s*\]"                                          # [7]    [10]
    r"|(?:[Rr]ating|[Ss]core)\s*[:=]\s*" + _N +                          # Rating: 7
    r"|\b" + _N + r"\s*/\s*10\b)"                                      # 7/10   10/10
)


def parse_codalm_rating_detail(text: str) -> Tuple[Optional[float], str]:
    """Return (rating, reason). The REASON distinguishes three outcomes that must not be conflated.

    D142 note 3. Out-of-range routes to UNPARSED, never clamped: clamping 11 to 10 silently invents
    a value the judge did not give, and nothing downstream would look wrong. But "the judge emitted
    no rating" and "the judge emitted a rating outside 1-10" are different facts about judge
    COMPLIANCE, and collapsing both to None loses the second. So the reason is carried, and the
    out-of-range rate becomes a reported quantity rather than a correction nobody sees.

    reasons: "ok" | "no_match" (no rating token at all) | "out_of_range" (a number was emitted and
    it is not in 1-10) | "unparseable_number".
    """
    ms = _RATING10.findall(text or "")
    if not ms:
        # A number may still be present without any accepted framing; look for a bare integer that
        # a looser reader would have taken, so "out of range" is not misreported as "no rating".
        loose = re.search(r"(?:[Rr]ating|[Ss]core)\s*[:=]\s*(\d+(?:\.\d+)?)", text or "")
        if loose:
            try:
                v = float(loose.group(1))
            except ValueError:
                return None, "unparseable_number"
            if not (1.0 <= v <= 10.0):
                return None, "out_of_range"
        return None, "no_match"
    vals = [g for m in ms for g in (m if isinstance(m, tuple) else (m,)) if g]
    if not vals:
        return None, "no_match"
    try:
        v = float(vals[-1])
    except ValueError:
        return None, "unparseable_number"
    if 1.0 <= v <= 10.0:
        return v, "ok"
    return None, "out_of_range"


def parse_codalm_rating(text: str) -> Optional[float]:
    """Parse the LAST 1-10 rating in `text`; None if none is present.

    Returns a float so a judge emitting `7.5` is not silently floored. Values outside [1, 10] are
    rejected rather than clamped, because a clamp turns an unparseable answer into a plausible one.
    A rating stated only in prose is NOT matched: a pattern loose enough to catch it would capture
    unrelated numbers, and on StudySS1 that class was 16 of 700.
    """
    ms = _RATING10.findall(text or "")
    if not ms:
        return None
    vals = [g for m in ms for g in (m if isinstance(m, tuple) else (m,)) if g]
    if not vals:
        return None
    try:
        v = float(vals[-1])
    except ValueError:
        return None
    return v if 1.0 <= v <= 10.0 else None


# Pre-registered 2x2 cut for the 1-10 scale, FIXED BEFORE THE DISTRIBUTION IS SEEN, because an
# unregistered threshold already moved a StudySS1 headline by 17 points (agreement 0.633 against
# 0.805 on whether a 0.5 counts as correct).
# CHECKED AGAINST THE PAPER (arXiv:2404.10595): CODA-LM does NOT binarise. Its primary metric is
# "Text-Score", the simple mean of per-sample 1-10 scores over the evaluation set, reported per task
# and rescaled to 1-100 in its Table 2 for readability. It names NO pass/fail threshold. So the MEAN
# is CODA-LM's own quantity and the 2x2 below is OUR derived object with a cut WE chose; the cut must
# be named at the point of use and never presented as the benchmark's.
CODALM_CUT_PRIMARY = 6.0          # OURS, not CODA-LM's: first integer above the 5.5 midpoint
CODALM_CUT_SENSITIVITY = (4.0, 5.0, 7.0, 8.0)


def parser_gate(texts: List[str]) -> dict:
    """Run the parser over a SMALL sample and report the parse rate as a GATE.

    The rule from StudySS1: never publish a mean without its coverage beside it. This is run on 20
    to 30 judge outputs before any full pass, so a parse rate of 5 percent is caught on 30 calls
    rather than on 700.
    """
    from collections import Counter
    n = len(texts)
    pairs = [parse_codalm_rating_detail(t) for t in texts]
    ok = [v for v, r in pairs if v is not None]
    reasons = Counter(r for _, r in pairs)
    return dict(n=n, n_parsed=len(ok), parse_rate=(round(len(ok) / n, 4) if n else None),
                reason_breakdown=dict(reasons),
                out_of_range_n=reasons.get("out_of_range", 0),
                out_of_range_note=("an out-of-range rating is routed to UNPARSED, never clamped, and "
                                   "is counted separately from 'no rating emitted' because the two "
                                   "are different facts about judge compliance."),
                distinct_values=sorted({v for v in ok}),
                unparsed_samples=[t[:200] for t, (v, _) in zip(texts, pairs) if v is None][:5],
                gate="PASS" if n and len(ok) / n >= 0.95 else "FAIL: investigate before any full pass")


# ---- self-test vectors: the shapes observed on StudySS1 plus the 1-10 specific ones
_VECTORS: Tuple[Tuple[str, Optional[float]], ...] = (
    ("Rating: 7", 7.0),
    ("Rating: [7]", 7.0),
    ("Rating: [[7]]", 7.0),
    ("Score: 7", 7.0),
    ("[[10]]", 10.0),                 # THE TRAP: must be 10, not 1
    ("Rating: 10", 10.0),
    ("Rating: [10]", 10.0),
    ("10/10", 10.0),
    ("I would give this 7/10 overall.", 7.0),
    ("[[7.5]]", 7.5),
    ("[[10.0]]", 10.0),
    ("Rating: 1", 1.0),
    ("Rating: 0", None),              # out of range low
    ("Rating: 11", None),             # out of range high
    ("Rating: 100", None),
    ("no rating at all here", None),
    ("I would rate it as 7", None),    # prose, deliberately not matched
    ("The answer mentions 3 cars and 2 signs. Rating: 8", 8.0),   # last match wins
)


def self_test() -> dict:
    fails = []
    for text, want in _VECTORS:
        got = parse_codalm_rating(text)
        if got != want:
            fails.append(dict(text=text, want=want, got=got))
    return dict(n=len(_VECTORS), n_fail=len(fails), fails=fails,
                verdict="PASS" if not fails else "FAIL")


if __name__ == "__main__":
    import json
    print(json.dumps(self_test(), indent=1))
