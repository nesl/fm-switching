#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of ECO-LLM's orchestration (arXiv:2507.09003).

Paper: P. Patidar, A. Crown, K. Hsieh, Y. Xu, "ECO-LLM: Orchestration for Domain-specific
Edge-Cloud Language Models", arXiv:2507.09003 (11 Jul 2025, Microsoft Research). No official or
author-endorsed code release was found.

> NAME NOTE, verified: arXiv:2507.09003's title is "Orchestration for Domain-specific Edge-Cloud
> Language Models" and ECO-LLM is the SYSTEM name inside it ("We introduce ECO-LLM (Edge-Cloud
> Orchestrator ...)"). A DIFFERENT 2024 paper, "ECO-LLM: LLM-based Edge Cloud Optimization", also
> uses the name; the id given in the task resolves to the Microsoft Research one, which is the
> system described here.

Mapping to the paper:
  The paper's insight is that prior work selects the best MODEL alone (it names RouteLLM and
  AutoMix), while the components of the serving pipeline - context retrieval, the model, and the
  rest of the configuration - must be chosen SIMULTANEOUSLY. ECO-LLM therefore
  (a) systematically explores the component-configuration space OFFLINE, with an **Emulator**
      that makes the exploration affordable, recording per-configuration quality and cost; and
  (b) DYNAMICALLY SELECTS, per query, the configuration that meets the user's SLOs.

  explore()   (a): enumerate the configuration space and attach a measured (quality, cost,
              latency) triple to each point. In the paper the Emulator runs the pipeline; here the
              triple is READ from our committed measurements, which is the adaptation.
  select()    (b): per query, choose the configuration maximising quality among those predicted
              to satisfy every SLO; if none is feasible, choose the one that violates the SLOs
              least, which is what an orchestrator with no feasible option must do.

NOT reconstructed, and why: the Emulator itself (it executes the pipeline, which needs
inference); the retrieval/RAG component of the configuration space (we have no retrieval stage);
the domain-specific tuning of its evaluation.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ConfigPoint:
    """One point of the configuration space, with its emulated/measured triple."""
    name: str
    knobs: Tuple[Tuple[str, object], ...]
    quality: float
    cost_gpu_s: float
    latency_s: float


@dataclass
class SLO:
    """User-defined SLOs. `None` means unconstrained on that axis."""
    max_latency_s: Optional[float] = None
    max_cost_gpu_s: Optional[float] = None
    min_quality: Optional[float] = None

    def violation(self, c: ConfigPoint) -> float:
        """0.0 when every SLO holds; otherwise the total normalised overshoot."""
        v = 0.0
        if self.max_latency_s is not None and c.latency_s > self.max_latency_s:
            v += (c.latency_s - self.max_latency_s) / max(self.max_latency_s, 1e-9)
        if self.max_cost_gpu_s is not None and c.cost_gpu_s > self.max_cost_gpu_s:
            v += (c.cost_gpu_s - self.max_cost_gpu_s) / max(self.max_cost_gpu_s, 1e-9)
        if self.min_quality is not None and c.quality < self.min_quality:
            v += (self.min_quality - c.quality) / max(abs(self.min_quality), 1e-9)
        return v

    def feasible(self, c: ConfigPoint) -> bool:
        return self.violation(c) <= 0.0


def explore(space: Sequence[Dict[str, object]],
            evaluate: Callable[[Dict[str, object]], Tuple[float, float, float]]
            ) -> List[ConfigPoint]:
    """Step (a). `evaluate` returns (quality, cost_gpu_s, latency_s) for one configuration.

    In the paper this is the Emulator; here the caller supplies a function reading committed
    measurements, so the exploration is exhaustive and exact rather than emulated.
    """
    out = []
    for cfg in space:
        q, c, l = evaluate(cfg)
        out.append(ConfigPoint(name="|".join(f"{k}={v}" for k, v in sorted(cfg.items())),
                               knobs=tuple(sorted(cfg.items())), quality=q,
                               cost_gpu_s=c, latency_s=l))
    return out


def select(points: Sequence[ConfigPoint], slo: SLO) -> Tuple[ConfigPoint, bool]:
    """Step (b). Highest quality among SLO-feasible points; otherwise the least-violating one.

    Returns (chosen, was_feasible). Ties on quality break toward lower cost, which is the
    paper's stated aim of meeting SLOs "while maintaining stable accuracy" at lower cost.
    """
    if not points:
        raise ValueError("empty configuration space")
    feas = [c for c in points if slo.feasible(c)]
    if feas:
        best = max(feas, key=lambda c: (c.quality, -c.cost_gpu_s))
        return best, True
    best = min(points, key=lambda c: (slo.violation(c), -c.quality, c.cost_gpu_s))
    return best, False
