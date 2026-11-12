#!/usr/bin/env python3
"""FAITHFUL RECONSTRUCTION of INAR-VL's input-aware router (arXiv:2605.18853, EdgeSys 2026).

Paper: A. Sabanovic, P. J. Maliakel, I. Brandic, "INAR-VL: Input-Aware Routing for Edge-Cloud
Vision-Language Inference". No official or author-endorsed code release was found.

Mapping to the paper's Section 3 / Figure 1 pipeline, stage by stage:
  (1) input ingestion     an (image, question) pair.
  (2) feature extraction  image branch: blur, exposure, artifact, detail (4 signals).
                          text branch: length, entity/numeric density, question type, vocabulary
                          complexity, reasoning markers, context-dependency markers (6 signals).
  (3) fusion              "both branches are normalized and merged into a 10-dimensional request
                          descriptor r".
  (4) router              "jointly selects model and placement by optimizing predicted accuracy
                          against latency and energy, approximating the Pareto frontier over edge
                          and cloud candidates". Each candidate model "carries three normalized
                          strength descriptors in [0, 1] (blur robustness, detail/OCR capability,
                          and reasoning ability), which are used by the router's quality
                          predictor".
  (5) decision            "the system prioritizes edge execution when the predicted quality is
                          sufficient, and otherwise offloads to the cloud only if the expected
                          quality gain justifies the additional cost".

NOT reconstructed, and why: the actual image signal extractors (they read pixels; the paper's
blur/exposure/artifact/detail estimators are standard but unspecified numerically) and the
quality predictor's fitted weights (not published). Both are supplied by the caller, so the
PIPELINE and the DECISION RULE are the paper's and only their inputs are ours. The 10-30 ms CPU
overhead is not modelled.

CPU only; no GPU, no inference.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

IMAGE_SIGNALS = ("blur", "exposure", "artifact", "detail")
TEXT_SIGNALS = ("length", "entity_numeric_density", "question_type", "vocabulary_complexity",
                "reasoning_markers", "context_dependency")
DESCRIPTOR_FIELDS = IMAGE_SIGNALS + TEXT_SIGNALS          # the 10 dimensions of r


@dataclass
class Candidate:
    """One (model, placement) candidate, with the paper's three strength descriptors."""
    name: str
    placement: str                   # "edge" | "cloud"
    blur_robustness: float           # in [0, 1]
    detail_ocr: float                # in [0, 1]
    reasoning: float                 # in [0, 1]
    latency_s: float
    energy_j: float


def fuse(image_signals: Dict[str, float], text_signals: Dict[str, float]) -> List[float]:
    """Stage (3): normalise both branches and merge into the 10-dimensional descriptor r."""
    r = []
    for k in IMAGE_SIGNALS:
        r.append(min(max(float(image_signals.get(k, 0.0)), 0.0), 1.0))
    for k in TEXT_SIGNALS:
        r.append(min(max(float(text_signals.get(k, 0.0)), 0.0), 1.0))
    return r


def predicted_quality(r: Sequence[float], c: Candidate) -> float:
    """Stage (4)'s quality predictor: the model's strengths matched against what the input
    demands. A blurred input rewards blur robustness, a detail-heavy one rewards detail/OCR, a
    reasoning-marked question rewards reasoning ability.

    The paper does not publish the predictor's weights, so this is the paper's STRUCTURE with
    unit weights; the adapted version replaces it with our measured accuracies, which is the
    whole point of the adaptation (recorded as reconstruction gap G1 in the card).
    """
    d = dict(zip(DESCRIPTOR_FIELDS, r))
    demand_blur = d["blur"]
    demand_detail = d["detail"] + d["entity_numeric_density"]
    demand_reason = d["reasoning_markers"] + d["context_dependency"] + d["vocabulary_complexity"]
    tot = demand_blur + demand_detail + demand_reason
    if tot <= 0:
        return (c.blur_robustness + c.detail_ocr + c.reasoning) / 3.0
    return (demand_blur * c.blur_robustness
            + demand_detail * c.detail_ocr
            + demand_reason * c.reasoning) / tot


def pareto_frontier(cands: Sequence[Candidate], r: Sequence[float]
                    ) -> List[Tuple[Candidate, float]]:
    """Stage (4): "approximating the Pareto frontier over edge and cloud candidates" in
    (predicted accuracy, latency, energy). A candidate is kept unless another dominates it on
    all three."""
    scored = [(c, predicted_quality(r, c)) for c in cands]
    out = []
    for c, q in scored:
        dominated = any(
            (q2 >= q and c2.latency_s <= c.latency_s and c2.energy_j <= c.energy_j
             and (q2 > q or c2.latency_s < c.latency_s or c2.energy_j < c.energy_j))
            for c2, q2 in scored if c2.name != c.name)
        if not dominated:
            out.append((c, q))
    return out


def route(r: Sequence[float], cands: Sequence[Candidate], quality_floor: float,
          gain_per_second: float, gain_per_joule: float) -> Tuple[Candidate, float, str]:
    """Stage (5): prioritise edge when the predicted quality is sufficient; otherwise offload to
    the cloud only if the expected quality gain justifies the additional latency and energy.

    Returns (chosen candidate, predicted quality, reason).
    """
    front = pareto_frontier(cands, r) or [(c, predicted_quality(r, c)) for c in cands]
    edge = [(c, q) for c, q in front if c.placement == "edge"]
    cloud = [(c, q) for c, q in front if c.placement == "cloud"]
    # "prioritizes edge execution when the predicted quality is sufficient"
    ok_edge = [(c, q) for c, q in edge if q >= quality_floor]
    if ok_edge:
        c, q = max(ok_edge, key=lambda t: t[1])
        return c, q, "edge: predicted quality sufficient"
    if not cloud:
        if not edge:
            raise ValueError("no candidates")
        c, q = max(edge, key=lambda t: t[1])
        return c, q, "edge: no cloud candidate"
    best_edge = max(edge, key=lambda t: t[1]) if edge else None
    c_cl, q_cl = max(cloud, key=lambda t: t[1])
    if best_edge is None:
        return c_cl, q_cl, "cloud: no edge candidate"
    c_ed, q_ed = best_edge
    # "offloads to the cloud only if the expected quality gain justifies the additional cost"
    gain = q_cl - q_ed
    cost = (max(c_cl.latency_s - c_ed.latency_s, 0.0) * gain_per_second
            + max(c_cl.energy_j - c_ed.energy_j, 0.0) * gain_per_joule)
    if gain > cost:
        return c_cl, q_cl, f"cloud: gain {gain:.3f} > cost {cost:.3f}"
    return c_ed, q_ed, f"edge: gain {gain:.3f} <= cost {cost:.3f}"
