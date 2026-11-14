#!/usr/bin/env python3
"""The S-EMBER DEVELOPMENT / EVALUATION split. CPU only.

StudyB-baselines amendment 2 (2026-11-13), pre-registered in `research/EXPERIMENTS.md` BEFORE it
was computed. StudyD3's development clips play this role for Nexar; S-EMBER had no such split, so
every S-EMBER-fitted constant in the suite was fitted on the questions it was then evaluated on.

THE RULE, fixed before computing:

  split BY VIDEO. Order the videos by sha256(video_id); the lowest 30 % of that order is DEV and
  the rest is EVAL. Stratify ONLY IF the hash split leaves a question-category or video-length
  bucket with less than 20 % of its share on either side, in which case the per-bucket counts are
  reported and the stratification rule is stated before it is applied.

WHAT IT BINDS. Any threshold, floor, profile, lookup table or prior fitted from S-EMBER data is
fitted on DEV only. Every reported recall metric is computed on EVAL only: the harness draws
recall arrivals from EVAL questions, so a DEV question never enters an evaluation run. This binds
every baseline AND our own scheduler.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "results/sember/study_r1/study_r1_inputs_manifest.jsonl.gz"
DEV_FRACTION = 0.30
MIN_BUCKET_SHARE = 0.20          # the stratification trigger, stated before it was computed

# THE STRATIFICATION RULE, stated 2026-11-13 BEFORE it was applied, because the unstratified
# hash split left two buckets below the trigger (question category `object_comparison` at a DEV
# share of 0.1868, and the video-length bucket `le120`, which holds 2 questions in total and 0 in
# DEV):
#
#   Strata are the VIDEO LENGTH buckets, which are a video-level attribute, so a video belongs to
#   exactly one. Within each stratum the videos are ordered by sha256(video_id) and the lowest
#   round(30 %) go to DEV, with at least one DEV video in any stratum holding at least two
#   videos. QUESTION CATEGORY is a question-level attribute and a video carries several
#   categories, so a video-level split cannot stratify on it: the per-category shares are
#   REPORTED after the stratified split and the split is accepted if every category's DEV share
#   lies in [0.20, 0.80]. A category still outside that band is REPORTED as a breach and the
#   split is NOT adjusted further, because adjusting a video-level assignment to hit a
#   question-level target would make the split depend on question content.
STRATIFY = True
BAND = (0.20, 0.80)

_META: Optional[Dict[str, Dict[str, object]]] = None
_SPLIT: Optional[Dict[str, Set[str]]] = None


def _meta() -> Dict[str, Dict[str, object]]:
    """question_id -> {video_id, question_time, question_category}, from StudyR1's manifest."""
    global _META
    if _META is None:
        out: Dict[str, Dict[str, object]] = {}
        for line in gzip.open(MANIFEST, "rt"):
            r = json.loads(line)
            if r.get("construction") != "RECENT":
                continue
            out.setdefault(r["question_id"], dict(video_id=r["video_id"],
                                                  question_time=float(r["question_time"]),
                                                  question_category=r["question_category"]))
        _META = out
    return _META


def _digest(video_id: str) -> str:
    return hashlib.sha256(video_id.encode()).hexdigest()


def split() -> Dict[str, Set[str]]:
    """-> {'dev_videos', 'eval_videos', 'dev_questions', 'eval_questions'} as sets."""
    global _SPLIT
    if _SPLIT is None:
        m = _meta()
        vids = sorted({str(v["video_id"]) for v in m.values()}, key=_digest)
        if not STRATIFY:
            dev_v = set(vids[:int(round(DEV_FRACTION * len(vids)))])
        else:
            times: Dict[str, List[float]] = defaultdict(list)
            for v in m.values():
                times[str(v["video_id"])].append(float(v["question_time"]))
            strata: Dict[str, List[str]] = defaultdict(list)
            for vid in vids:                       # already in digest order
                strata[_length_bucket(times[vid])].append(vid)
            dev_v = set()
            for _b, group in sorted(strata.items()):
                k = int(round(DEV_FRACTION * len(group)))
                if len(group) >= 2:
                    k = max(k, 1)
                dev_v |= set(group[:k])
        _SPLIT = dict(
            dev_videos=dev_v, eval_videos=set(vids) - dev_v,
            dev_questions={q for q, v in m.items() if str(v["video_id"]) in dev_v},
            eval_questions={q for q, v in m.items() if str(v["video_id"]) not in dev_v})
    return _SPLIT


def is_dev(question_id: str) -> bool:
    return question_id in split()["dev_questions"]


def is_eval(question_id: str) -> bool:
    return question_id in split()["eval_questions"]


def _length_bucket(times: List[float]) -> str:
    """A video's length proxy: its latest committed question time, in StudyE6b's own bins."""
    t = max(times) if times else 0.0
    return "le120" if t <= 120 else ("120-480" if t <= 480 else "gt480")


def report() -> Dict[str, object]:
    """Counts, the overlap check (which must be 0), and the per-bucket shares."""
    m, s = _meta(), split()
    by_video_times: Dict[str, List[float]] = defaultdict(list)
    for q, v in m.items():
        by_video_times[str(v["video_id"])].append(float(v["question_time"]))
    buckets: Dict[str, Dict[str, int]] = {}
    for key, fn in (("question_category", lambda q: str(m[q]["question_category"])),
                    ("video_length", lambda q: _length_bucket(
                        by_video_times[str(m[q]["video_id"])]))):
        counts: Dict[str, Counter] = defaultdict(Counter)
        for q in m:
            counts[fn(q)]["dev" if q in s["dev_questions"] else "eval"] += 1
        buckets[key] = {b: dict(dev=c["dev"], eval=c["eval"], n=c["dev"] + c["eval"],
                                dev_share=round(c["dev"] / max(c["dev"] + c["eval"], 1), 4))
                        for b, c in sorted(counts.items())}
    low = [f"{k}:{b}" for k, bb in buckets.items() for b, c in bb.items()
           if c["dev_share"] < MIN_BUCKET_SHARE or (1 - c["dev_share"]) < MIN_BUCKET_SHARE]
    return dict(
        rule=f"split by video on sha256(video_id); lowest {DEV_FRACTION:.0%} of the digest order "
             f"is DEV; stratify only if a bucket holds under {MIN_BUCKET_SHARE:.0%} of its share "
             f"on either side",
        n_questions=len(m), n_videos=len(by_video_times),
        n_dev_videos=len(s["dev_videos"]), n_eval_videos=len(s["eval_videos"]),
        n_dev_questions=len(s["dev_questions"]), n_eval_questions=len(s["eval_questions"]),
        dev_question_share=round(len(s["dev_questions"]) / max(len(m), 1), 4),
        overlap_questions=len(s["dev_questions"] & s["eval_questions"]),
        overlap_videos=len(s["dev_videos"] & s["eval_videos"]),
        buckets=buckets, buckets_below_trigger=sorted(set(low)),
        stratification_applied=bool(STRATIFY), stratification_band=list(BAND),
        category_band_breaches=sorted(
            b for b, c in buckets["question_category"].items()
            if not (BAND[0] <= c["dev_share"] <= BAND[1])),
        stratification_note=("the unstratified hash split left question category "
                             "`object_comparison` at a DEV share of 0.1868 and the video-length "
                             "bucket `le120` (2 questions in total) at 0.0, so the "
                             "pre-registered trigger fired. The stratification rule was written "
                             "into this module BEFORE it was applied: strata are the video "
                             "length buckets, the digest order inside a stratum is unchanged, "
                             "and question category is reported rather than stratified because "
                             "a video carries several categories"))


if __name__ == "__main__":
    print(json.dumps(report(), indent=1, default=str))
