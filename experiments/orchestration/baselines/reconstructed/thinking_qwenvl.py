#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of the ATDM response-timing controller (arXiv:2604.18459).

Paper: K. Zhang, Z. Yang, M. Han, H. Hao et al., "Progressive Online Video Understanding with
Evidence-Aligned Timing and Transparent Decisions", arXiv:2604.18459 (20 Apr 2026); referred to
in the task as Thinking-QwenVL. The task cites ICLR 2026, which could not be verified in an
index; the arXiv id IS verified. No official or author-endorsed code release was found.

Mapping to the paper:
  The problem: "a visual agent should answer only once the video first contains sufficient
  evidence, and it should show when and why it decided".
  The mechanism: the **Active Thinking Decision Maker (ATDM)**, "a transparent reasoning
  controller that externalizes its decision process using observable progress (rho) and
  confidence [...] to pinpoint the sufficient-evidence timestamp t*". A second module, HPSI
  (Hierarchical Progressive Semantic Integration), integrates semantics.

  atdm()        the decision rule over the two OBSERVABLE quantities the paper names: progress
                rho (how much of the evidence the agent judges it has) and confidence. It answers
                at the first timestamp where BOTH clear their thresholds, which is the paper's
                "sufficient-evidence timestamp t*", and it RECORDS the reason, which is the
                transparency the paper is about.
  t_star()      the first such timestamp over a stream, i.e. the response time ATDM commits to.

NOT reconstructed, and why: the model-internal estimation of rho and confidence (they are the
VLM's own outputs, which need inference); HPSI's semantic integration; the paper's timing metrics.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class Decision:
    answer_now: bool
    reason: str
    progress: float
    confidence: float


def atdm(progress: float, confidence: float, progress_threshold: float,
         confidence_threshold: float) -> Decision:
    """The transparent rule: answer only when progress AND confidence are both sufficient.

    The `reason` string is the point of the paper - the decision is externalised, not implicit.
    """
    if progress < progress_threshold:
        return Decision(False, f"wait: progress {progress:.3f} < {progress_threshold:.3f}",
                        progress, confidence)
    if confidence < confidence_threshold:
        return Decision(False,
                        f"wait: confidence {confidence:.3f} < {confidence_threshold:.3f}",
                        progress, confidence)
    return Decision(True, f"answer: progress {progress:.3f} and confidence {confidence:.3f} "
                          f"both sufficient", progress, confidence)


def t_star(progress: Sequence[float], confidence: Sequence[float], times_s: Sequence[float],
           progress_threshold: float, confidence_threshold: float
           ) -> Tuple[Optional[float], List[Decision]]:
    """The first timestamp at which ATDM commits to an answer, with the decision trace."""
    trace: List[Decision] = []
    out: Optional[float] = None
    for p, c, t in zip(progress, confidence, times_s):
        d = atdm(p, c, progress_threshold, confidence_threshold)
        trace.append(d)
        if d.answer_now and out is None:
            out = float(t)
    return out, trace
