#!/usr/bin/env python3
"""The DEVICE answer's confidence, per question, read from committed tables only.

StudyB-baselines amendment 2 (2026-11-13), item 3. CPU only; nothing here runs a model and
NOTHING IS SYNTHESIZED: a question with no committed device-answer probability returns None and
every policy that reads it must handle None.

WHICH TABLE, AND WHY. The harness scores a DEVICE recall answer as `4B-D2` (StudyE7 Job A, the
DEVICE PROXY of `recall_profiles.py`), so the confidence that belongs to that answer is StudyE7's
own per-question `letter_probs`: the probability mass on the letter the 4B actually emitted.

  primary    StudyE7 Job A  results/sember/study_e7/e7_requests_h100nvl.jsonl
             `letter_probs.mass[first_token]` - the same configuration the harness answers with
  secondary  StudyF4 Part A results/device/study_f4/partA_accuracy.jsonl
             `answer_logprob.logprob` on the real Jetson Orin, N = 1 (a last-3-s window, not D2)

The secondary table is the TRUE DEVICE measurement but a different representation, so it is used
only as a cross-check (`agreement()`), never as the value a policy reads. StudyD15 Part A
rejected the H100-for-Orin proxy as an exact numerical stand-in; both tables are therefore valid
for ordering and first-order value, not as exact device numbers.

LIMITATION, declared here and in the report: a policy that reads this confidence is assuming the
device answered BEFORE the decision epoch. The harness does not charge that device answer's
latency (StudyD8's 0.567 s) to an arm that then escalates to the cloud.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[3]
E7 = ROOT / "results/sember/study_e7/e7_requests_h100nvl.jsonl"
F4 = ROOT / "results/device/study_f4/partA_accuracy.jsonl"
# Single-shot confidences, written by experiments/casestudy/ss2_device_confidence.py from a
# re-recorded Orin 4B pass with logprobs (user ruling 2026-11-20). Absent until that pass runs, and
# absence is NOT an error: StudySS1 and StudySS2 recorded no probabilities, so None is the honest
# value for a single-shot question until it does.
SS2 = ROOT / "results/casestudy/study_ss2/ss2_device_confidence.json"

_PRIMARY: Optional[Dict[str, float]] = None
_SECONDARY: Optional[Dict[str, float]] = None

SOURCE = dict(
    primary="StudyE7 Job A (4BI on StudyRH4's D2 input), per-question letter_probs mass on the "
            "emitted letter; the harness's own DEVICE answer configuration (4B-D2)",
    secondary="StudyF4 Part A (Jetson Orin, N = 1 last-3-s window), exp(answer_logprob); the "
              "true device but a different representation, used only as a cross-check",
    rule="committed values only; a question with no committed probability returns None")


def _load_primary() -> Dict[str, float]:
    global _PRIMARY
    if _PRIMARY is None:
        out: Dict[str, float] = {}
        if E7.exists():
            for line in E7.open():
                r = json.loads(line)
                lp = r.get("letter_probs") or {}
                mass, tok = lp.get("mass"), lp.get("first_token")
                if not mass or tok is None or tok not in mass:
                    continue
                v = float(mass[tok])
                q = r["question_id"]
                # several rows exist per question (retries); the LAST committed one wins, which
                # is the row `recall_profiles` also counts
                out[q] = max(0.0, min(v, 1.0))
        _PRIMARY = out
    return _PRIMARY


def _load_secondary() -> Dict[str, float]:
    global _SECONDARY
    if _SECONDARY is None:
        out: Dict[str, float] = {}
        if F4.exists():
            for line in F4.open():
                r = json.loads(line)
                if r.get("N") != 1:
                    continue
                al = r.get("answer_logprob") or {}
                if not isinstance(al, dict) or al.get("logprob") is None:
                    continue
                out[r["question_id"]] = float(math.exp(al["logprob"]))
        _SECONDARY = out
    return _SECONDARY


_SS2: Optional[Dict[str, float]] = None


def _load_ss2() -> Dict[str, float]:
    """Single-shot confidences, keyed by the SS2 qid (e.g. "realworldqa/0122").

    Kept in a SEPARATE table from the robot one on purpose. The mcq rule is byte-identical to the
    robot rule, the committed `letter_probs` mass on the emitted letter, but the free-form and
    point rules are a geometric mean token probability, and the point case is declared a WEAK
    signal. Merging them into one dict without that provenance would make two different notions of
    confidence indistinguishable at the point of use, which is the kind of thing `source_of()`
    exists to keep answerable.
    """
    global _SS2
    if _SS2 is None:
        out: Dict[str, float] = {}
        if SS2.exists():
            doc = json.loads(SS2.read_text())
            for q, v in (doc.get("confidence") or {}).items():
                out[str(q)] = max(0.0, min(float(v), 1.0))
        _SS2 = out
    return _SS2


def confidence(question_id: str) -> Optional[float]:
    """The committed device-answer confidence for one question, or None. Never synthesized.

    Robot questions come from StudyE7 Job A; single-shot questions from the re-recorded SS2 pass
    when it exists. The two key spaces are disjoint (a 64-hex digest against "<dataset>/<id>"), so
    the lookup order cannot mask one with the other.
    """
    v = _load_primary().get(question_id)
    if v is None:
        v = _load_ss2().get(question_id)
    return v


def source_of(question_id: str) -> Optional[str]:
    """Which table a value came from, so a report never has to guess."""
    if question_id in _load_primary():
        return "StudyE7 Job A letter_probs (robot)"
    if question_id in _load_ss2():
        return "StudySS2 re-record (single shot)"
    return None


def dev_median() -> Optional[float]:
    """The median committed device confidence over S-EMBER DEV questions ONLY.

    StudyB-baselines amendment 2 (2026-11-13): any constant fitted from S-EMBER data is fitted on
    the pre-registered DEV split (`sember_split.py`) and never on the questions a recall metric
    is reported over.
    """
    import statistics
    import sember_split as SS
    v = [c for q, c in _load_primary().items() if SS.is_dev(q)]
    return float(statistics.median(v)) if v else None


def coverage() -> Dict[str, object]:
    p, s = _load_primary(), _load_secondary()
    both = sorted(set(p) & set(s))
    import statistics
    d = [p[q] - s[q] for q in both]
    return dict(
        n_primary=len(p), n_secondary=len(s), n_both=len(both),
        primary_median=(statistics.median(p.values()) if p else None),
        secondary_median=(statistics.median(s.values()) if s else None),
        median_difference=(statistics.median(d) if d else None),
        spearman_like_agreement_rank=(_rank_agreement([p[q] for q in both],
                                                      [s[q] for q in both]) if both else None),
        source=SOURCE)


def _rank_agreement(a, b) -> float:
    """Spearman rho, written out so this module needs no scipy."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for k, i in enumerate(order):
            r[i] = float(k)
        return r
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return float(num / den) if den else 0.0


if __name__ == "__main__":
    print(json.dumps(coverage(), indent=1, default=str))
