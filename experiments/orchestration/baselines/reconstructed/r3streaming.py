#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of R3-Streaming's three decisions (arXiv:2605.17921).

Paper: J. Liu et al., "An Efficient Streaming Video Understanding Framework with Agentic
Control" (R3-Streaming: Remember, Respond, Reason). No official or author-endorsed code release
was found.

Mapping to the paper, Section 4:
  active_forgetting()  Section 4.2 "Remember (Active Forgetting)": a TRAINING-FREE, age-aware
                       memory compressor. The paper's finding (Section 3, Figure 2) is an
                       asymmetry - "preserving Nearby context is critical, while Historical
                       memory can be compressed more aggressively", with the best setting
                       "Nearby = 1.0, Historical = 0.01" reaching 71.0 on StreamingBench,
                       "+2.4 over no compression". Reconstructed as: frames inside the nearby
                       window keep ratio 1.0, older frames keep ratio r_hist.
  readiness()          Section 4 "(ii) Proactive Response, a readiness head that emits <Routine>
                       and defers answering when evidence is insufficient". Reconstructed as a
                       predicate over an evidence score and a threshold; the paper trains a
                       lightweight head on the frozen fast model, which needs a GPU, so the head
                       is supplied by the caller.
  adaptive_thinking()  Section 4 "(iii) Adaptive Thinking, a routing policy" - "routes only hard
                       queries to slow/thinking inference instead of using an always-on large
                       model", trained with TB-GRPO so that routing stays "within deployable
                       escalation budgets". Reconstructed as: escalate the hardest queries, under
                       a budget on the escalation RATE, which is what the target-balanced
                       objective enforces at deployment time.

NOT reconstructed, and why: TB-GRPO itself (a reinforcement-learning TRAINING objective, needing
GPUs and the model); the readiness head's weights; the visual-token compressor's internals. What
is reconstructed is the three DECISIONS and the budget-respecting routing they imply.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

ROUTINE, REASON = "Routine", "Reason"


@dataclass
class Frame:
    index: int
    age_s: float
    tokens: int


def active_forgetting(frames: Sequence[Frame], now_s: float, nearby_window_s: float,
                      ratio_nearby: float = 1.0, ratio_historical: float = 0.01
                      ) -> List[Tuple[Frame, float, int]]:
    """Section 4.2 / Figure 2. Returns (frame, kept ratio, kept tokens) per frame.

    The paper's best setting is ratio_nearby = 1.0 and ratio_historical = 0.01; both are exposed
    so the ablation of Figure 2 can be reproduced.
    """
    out = []
    for f in frames:
        nearby = f.age_s <= nearby_window_s
        ratio = ratio_nearby if nearby else ratio_historical
        out.append((f, ratio, max(int(round(f.tokens * ratio)), 1 if ratio > 0 else 0)))
    return out


def readiness(evidence_score: float, threshold: float) -> bool:
    """Section 4 (ii). True = answer now; False = defer, because evidence is insufficient."""
    return evidence_score >= threshold


def adaptive_thinking(difficulty: Sequence[float], escalation_budget: float
                      ) -> List[str]:
    """Section 4 (iii). Route only the hardest fraction to the stronger ("thinking") model, so
    the escalation rate stays inside the deployable budget TB-GRPO is trained to respect."""
    n = len(difficulty)
    if n == 0:
        return []
    k = int(round(max(min(escalation_budget, 1.0), 0.0) * n))
    if k <= 0:
        return [ROUTINE] * n
    order = sorted(range(n), key=lambda i: -difficulty[i])
    hard = set(order[:k])
    return [REASON if i in hard else ROUTINE for i in range(n)]


def pipeline(frames: Sequence[Frame], now_s: float, nearby_window_s: float,
             evidence_score: float, readiness_threshold: float,
             difficulty: float, escalation_budget: float,
             ratio_historical: float = 0.01) -> Dict[str, object]:
    """The three decisions in the paper's order: Remember, then Respond, then Reason."""
    kept = active_forgetting(frames, now_s, nearby_window_s,
                             ratio_historical=ratio_historical)
    tokens = sum(t for _f, _r, t in kept)
    ready = readiness(evidence_score, readiness_threshold)
    path = adaptive_thinking([difficulty], escalation_budget)[0] if ready else None
    return dict(kept=kept, kept_tokens=tokens, ready=ready, path=path,
                decision=("defer" if not ready else path))
