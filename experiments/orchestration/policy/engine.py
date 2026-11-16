"""Spec 5.1 and 10.2: the engine model, PLUGGABLE so M1's measurement replaces it without
touching the policy.

The policy only ever calls the `EngineModel` protocol. `PlaceholderEngine` implements it from
COMMITTED evidence and nothing else, and says so for every term:

  prefill rate            StudyRH5 cold re-prefill (4,500 tok/s at 11k, 3,800 at 28k)
  episodic first token    StudyD7 / D7b TTFT at 25 % and 75 % of peak load
  recall first token      StudyRH5 Part A TTFT by readiness
  contention              StudySIM1d: an overlap cost of about 0.05 s per CONCURRENT warm request
                          in both KV modes, and NO sub-linear batching in the step model
  no preemption           spec A4; a submitted request runs to completion

WHAT THE PLACEHOLDER CANNOT DO, stated because T0 exists to catch exactly this: StudySIM1d failed
OUT OF SAMPLE on slice-versus-episodic interactions. The placeholder reproduces the committed
in-sample behaviour and must not be trusted on mixtures it was not measured on. Every call
returns a `Prediction` carrying `in_sample`, and `Rollout` propagates it so T0 can separate the
two cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

OVERLAP_COST_S = 0.05            # StudySIM1d, per concurrent warm request
PREFILL_TOK_S = {11000: 4500.0, 28000: 3800.0}
CHAIN_OVER_MONOLITHIC = 1.0      # SLICE1 Part A: near-monolithic total work at 1-2k pieces


@dataclass
class Request:
    kind: str                    # "episode_call" | "rc_piece" | "state_action" | "summary"
    device: str
    tokens: int = 0
    frames: int = 1
    model: str = "32BI"
    readiness: str = "COLD"      # COLD | GPU-WARM | HOST-WARM
    job_id: Optional[str] = None
    piece_index: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Prediction:
    first_token_s: float
    service_s: float
    gpu_s: float
    in_sample: bool
    basis: str


class EngineModel(Protocol):
    def predict(self, req: Request, concurrent: int, load_pct: int = 25) -> Prediction: ...

    def capacity_tokens(self) -> Tuple[int, int]: ...

    def describe(self) -> Dict[str, Any]: ...


def _rate(tokens: int) -> float:
    k = min(PREFILL_TOK_S, key=lambda s: abs(s - max(tokens, 1)))
    return PREFILL_TOK_S[k]


@dataclass
class PlaceholderEngine:
    """Committed-evidence engine model. To be replaced by M1 (`research/POLICY_SPEC_v3.md` 10.2)."""

    gpu_kv_tokens: int = 0
    host_kv_tokens: int = 0
    profiles: Any = None
    overlap_cost_s: float = OVERLAP_COST_S

    def predict(self, req: Request, concurrent: int, load_pct: int = 25) -> Prediction:
        if concurrent < 0:
            raise ValueError("concurrent must be >= 0")
        overlap = self.overlap_cost_s * concurrent
        in_sample = True
        basis = []
        if req.kind == "episode_call":
            if self.profiles is None:
                raise ValueError("PlaceholderEngine needs profiles for episodic TTFT")
            ttft = self.profiles.episodic_ttft_s(req.model, req.frames, load_pct)
            basis.append("StudyD7 / D7b episodic TTFT at load %d %%" % load_pct)
            gpu = ttft
            service = ttft
        elif req.kind in ("rc_piece", "state_action", "summary"):
            if req.readiness in ("GPU-WARM", "HOST-WARM") and self.profiles is not None:
                ttft = self.profiles.recall_ttft_s(req.readiness, max(req.tokens, 1))
                basis.append("StudyRH5 Part A TTFT, readiness %s" % req.readiness)
            else:
                ttft = req.tokens / _rate(req.tokens)
                basis.append("StudyRH5 cold prefill %d tok/s" % int(_rate(req.tokens)))
            gpu = req.tokens / _rate(req.tokens) * CHAIN_OVER_MONOLITHIC
            service = max(ttft, gpu)
            if req.kind == "summary":
                in_sample = False
                basis.append("NOT IN SAMPLE: no committed summary generation cost (StudyF2 "
                             "inconclusive)")
        else:
            raise ValueError("unknown request kind %r" % req.kind)
        if concurrent > 0 and req.kind == "rc_piece":
            in_sample = False
            basis.append("NOT IN SAMPLE: StudySIM1d's engine model failed out of sample on "
                         "slice-versus-episodic interactions; the overlap cost is applied "
                         "linearly because no sub-linear batching was measured")
        return Prediction(first_token_s=ttft + overlap, service_s=service + overlap, gpu_s=gpu,
                          in_sample=in_sample, basis="; ".join(basis))

    def capacity_tokens(self) -> Tuple[int, int]:
        return self.gpu_kv_tokens, self.host_kv_tokens

    def describe(self) -> Dict[str, Any]:
        return dict(
            name="PlaceholderEngine",
            replace_with="M1 measured step-time and admission model on the H100",
            overlap_cost_s=self.overlap_cost_s,
            prefill_tok_s=PREFILL_TOK_S,
            sub_linear_batching=False,
            sources=["StudySIM1d overlap cost and no sub-linear batching",
                     "StudyRH5 prefill and readiness TTFT",
                     "StudyD7 / D7b episodic TTFT",
                     "SLICE1 Part A near-monolithic prefix-chained total work"],
            known_failure="StudySIM1d failed out of sample on slice-versus-episodic "
                          "interactions, which is why T0 precedes any reliance on this")
