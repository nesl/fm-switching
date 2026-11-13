#!/usr/bin/env python3
"""StudySIM1-mixed — the engine model: ONE 32B vLLM 0.31.0 replica, calibrated to measurements.

CPU ONLY. Nothing here runs a model. Every constant is a committed measurement with its source
named, or a RULE that says so in its own docstring; there are no fitted parameters except the one
the spec declares unmeasured (the per-slice overhead, swept by `run.py`).

The mechanism this model exists to reproduce is the one StudyE10b / E10c / E10d / E10e located:

  * vLLM 0.31.0's V1 scheduler serves RUNNING requests first and chunks prefills to a per-step
    token budget (8,192 by default).
  * A long prefill therefore takes the WHOLE budget each step until its last, so a short episodic
    request that arrives meanwhile is not scheduled until the step in which the long prefill's
    remainder leaves room - which is the step that produces the long request's first token.
    StudyE10c section 6 and StudyE10d measured exactly that: 99 % of slow episodic requests were
    submitted inside a cold recall's prefill window and were released a median 0.00-0.24 s after
    the cold request's first token.
  * `--long-prefill-token-threshold T` caps a running prefill at T tokens per step, leaving
    budget - T for waiting requests, and is SKIPPED when the long request is the only one in the
    system (vLLM's own "nobody to starve" exemption). StudyE10e measured the result: the hold
    falls 19-30 % and does not go away.
  * GPU KV holds 62,944 tokens. Past that, warm prefixes are evicted; with GPU-only KV the next
    touch re-prefills the whole history (StudyRH5's collapse at D = 8, StudyE10b's at k = 8) and
    with host offload it reloads over PCIe instead (StudyRH5 Part A).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ============================================================ calibration constants
# Every entry names the committed measurement it comes from. NOTHING here is fitted.
MAX_NUM_BATCHED_TOKENS = 8192        # vLLM 0.31.0 default, confirmed in StudyE10c's 87 server logs
GPU_KV_TOKENS = 62944                # StudyRH3 / RH4 / RH5 / E10b, the image server's KV
HOST_KV_TOKENS = 1_048_576           # StudyRH5's 256 GiB pinned region / 262,144 B per token

# Prefill rate per request kind and size. StudyD7 / D7b: 32B peak 15.10 req/s at 378 tokens
# = 5.71k tok/s, and 5.38 req/s at 1,062 = 5.71k tok/s - the same rate at both N, as compute-bound
# prefill predicts. StudyRH5 Part A measured the cold D2 re-prefill rates by size, and StudyE10d
# decomposed a cold K1 RICH recall's 12,645 tokens into 2.17 s of LM prefill (5.83k tok/s).
RATE_EPISODIC_TOK_S = 15.10 * 378.0                  # 5,708 tok/s  (StudyD7b peak)
RATE_COLD_BY_SIZE = {11050: 4500.0, 28114: 3800.0}   # StudyRH5 Part A
RATE_COLD_K1_TOK_S = 12645 / 2.17                    # 5,827 tok/s  (StudyE10d LM prefill)

# Per-request client/API handling before the engine sees the request ("frontend phase").
# StudyD7b concurrency 1: TTFT p50 0.134 s for 378 tokens, of which 378 / 5,708 = 0.066 s is
# compute, leaving 0.068 s. StudyE10d measured the frontend phase of a cold recall directly.
FRONTEND_EPISODIC_S = 0.134 - 378.0 / RATE_EPISODIC_TOK_S     # 0.0678 s
FRONTEND_COLD_PNG_S = 1.47           # StudyE10d idle-phase decomposition (50.3 MB body)
FRONTEND_COLD_TEXT_S = 0.04          # StudyE10d V3 (text-only, token-matched)
FRONTEND_WARM_S = 0.04               # StudyE10b: warm sessions send uuid references, bodies tiny
VISION_ENCODER_S = 0.20              # StudyE10d: one unsplittable step before the LM prefill

# Warm recall (append / escalation over a cached prefix). StudyRH5 Part A isolated TTFT medians.
WARM_TTFT_S = {(11050, "GPU-WARM"): 0.382, (11050, "HOST-WARM"): 0.459,
               (28114, "GPU-WARM"): 0.874, (28114, "HOST-WARM"): 1.001}
# StudyRH5 Part A, visible cost of a host reload over a GPU-warm hit at the same size.
HOST_RELOAD_VISIBLE_S = {11050: 0.031, 28114: 0.117}
HOST_BYTES_PER_TOKEN = 262144
D2_TOKENS_PER_S = 45.0       # StudyRH4 D2: 90 tokens per 2-s frame
WARM_DELTA_TOKENS = 450      # StudyE10b: five new frames per 10-s append x 90 tokens
D2_MAX_HISTORY_TOKENS = 11050  # StudyRH5's "11k" size; StudyRH4's D2 sessions run to ~11.8 min
# Engine time a warm request spends attending over its CACHED prefix, per token of history.
# DERIVED from StudyE10b's own utilisation deltas, and the two derivations disagree, so the
# midpoint is used and both are reported (as with STEP_OVERHEAD_S):
#   KV-HOST k = 8, N = 1, 25 %: GPU util 0.45 vs 0.39 at k = 0 -> 14.4 s over 210 warm requests
#     = 0.069 s each;
#   KV-HOST k = 16, N = 1, 25 %: 0.64 vs 0.39 -> 60 s over 424 warm requests = 0.142 s each.
# A warm request's delta tokens alone account for 450 / 5,708 = 0.079 s, so the attention term is
# set to put the total at the midpoint 0.105 s at StudyE10b's mean history of about 9,600 tokens.
WARM_ATTENTION_S_PER_TOKEN = (0.105 - WARM_DELTA_TOKENS / (15.10 * 378.0)) / 9600.0
WARM_ATTENTION_DERIVATIONS_S = (0.069, 0.142)
# StudyRH5 / StudyE10b's warm-miss rule. The warm footprint is sum(history) / GPU KV - StudyRH2's
# and RH5's own pre-registered fluid-model metric. Measured outcomes:
#   StudyE10b k = 2 (0.3x): 0 misses of 54;  k = 4 (0.6x): 1 of 106;
#   k = 8 (about 1.2x): 167 of 207 = 0.81;   k = 16 (about 2.4x): 255 of 281 = 0.91.
#   StudyRH5 GPU-only token hit: 0.96 at 0.66x, 0.72 at 1.19x, 0.38 at 2.48x, 0.24 at 3.96x.
# A miss re-prefills the WHOLE history: StudyE10b measured a median cached fraction of 0.002 on
# those appends, which is why the chain is eviction -> whole-history re-prefill -> saturation.
# This is a LOOKUP from those measurements, not a fit.
WARM_MISS_BY_FOOTPRINT = ((1.0, 0.0), (1.5, 0.81), (float("inf"), 0.91))


def warm_miss_fraction(footprint: float) -> float:
    for lim, miss in WARM_MISS_BY_FOOTPRINT:
        if footprint <= lim:
            return miss
    return WARM_MISS_BY_FOOTPRINT[-1][1]        # StudyRH5 (64 layers x 8 KV heads x 128 x K,V x bf16)

# Per-step overhead. DERIVED, and the derivation disagrees with itself, so it is stated as a range
# and the midpoint is used - never re-tuned. StudyE10e capped a 12,645-token cold prefill at 1,024
# tokens (P1), turning 2 steps into 13, and its cold TTFT p50 rose 5 % (3.899 -> 4.075 s), which
# implies 0.176 / 11 = 0.016 s per step. P2 (512 tokens, 25 steps) rose only 2 % (+0.073 s), which
# implies 0.003 s per step. The two cannot both be right; the midpoint is used and both are
# reported. Every calibration-gate cell runs at P0, where a request takes 1-2 steps, so the gate
# is nearly insensitive to this value (sensitivity reported by `calibrate.py`).
STEP_OVERHEAD_S = 0.010
STEP_OVERHEAD_RANGE_S = (0.003, 0.016)

# StudyE10e's measured engine configurations. The cap is the only lever that acts at all.
CONFIGS: Dict[str, Dict] = {
    "P0": dict(long_prefill_token_threshold=0, policy="fcfs",
               source="StudyE10e P0 = StudyE10c E0 = StudyE10b's server (0.31.0 defaults)"),
    "P1": dict(long_prefill_token_threshold=1024, policy="fcfs",
               source="StudyE10e P1 - THE TUNED ENGINE (user decision 2026-11-12)"),
    "P2": dict(long_prefill_token_threshold=512, policy="fcfs", source="StudyE10e P2"),
    "P3": dict(long_prefill_token_threshold=1024, policy="priority", source="StudyE10e P3"),
    "E2": dict(long_prefill_token_threshold=0, policy="fcfs", max_num_batched_tokens=2048,
               source="StudyE10c E2 (2,048-token step budget)"),
}
PRIORITY = dict(episodic=0, warm=1, cold=2)     # StudyE10c / E10e's priority assignment

KINDS = ("episodic", "append", "escalation", "cold", "host_reload", "slice")


# ============================================================ requests
@dataclass
class Request:
    rid: str
    kind: str                      # in KINDS
    arrival_s: float
    prompt_tokens: int = 0
    compute_tokens: int = 0        # prompt - cached; what the GPU must actually prefill
    session: Optional[str] = None
    frontend_s: float = 0.0
    encoder_s: float = 0.0
    rate_tok_s: float = RATE_EPISODIC_TOK_S
    unit_s: float = 0.0            # a measured, unsplittable compute unit (warm recall)
    reload_s: float = 0.0          # host->GPU KV reload, charged on its first scheduled step
    deadline_s: Optional[float] = None
    meta: Dict = field(default_factory=dict)
    # ---- filled by the engine
    visible_s: float = 0.0
    first_sched_s: Optional[float] = None
    done_s: Optional[float] = None
    remaining: float = 0.0
    encoder_left: float = 0.0
    steps: int = 0

    def ttft_s(self) -> Optional[float]:
        return None if self.done_s is None else self.done_s - self.arrival_s

    def priority(self) -> int:
        return PRIORITY.get("episodic" if self.kind == "episodic"
                            else ("cold" if self.kind in ("cold", "slice") else "warm"), 1)


# ============================================================ the engine
class Engine:
    """One 32B replica. Deterministic: given the same arrivals it produces the same timeline."""

    def __init__(self, config: str = "P0", kv_mode: str = "GPU",
                 gpu_kv_tokens: int = GPU_KV_TOKENS,
                 step_overhead_s: float = STEP_OVERHEAD_S) -> None:
        if config not in CONFIGS:
            raise ValueError(f"unmeasured engine configuration {config!r}; measured: "
                             f"{sorted(CONFIGS)}")
        c = CONFIGS[config]
        self.config = config
        self.cap = int(c["long_prefill_token_threshold"])
        self.policy = c["policy"]
        self.budget = int(c.get("max_num_batched_tokens", MAX_NUM_BATCHED_TOKENS))
        self.kv_mode = kv_mode
        self.gpu_kv_tokens = int(gpu_kv_tokens)
        self.step_overhead_s = float(step_overhead_s)
        self.clock = 0.0
        self._pending: List[Tuple[float, int, Request]] = []    # heap by visible time
        self._seq = 0
        self.waiting: List[Request] = []
        self.running: List[Request] = []
        self.done: List[Request] = []
        # KV residency: session -> tokens held on GPU / host, with an LRU clock
        self.gpu: Dict[str, int] = {}
        self.host: Dict[str, int] = {}
        self.touch: Dict[str, float] = {}
        self.stats = dict(steps=0, step_tokens=0.0, gpu_busy_s=0.0, evictions=0, re_prefills=0,
                          host_reloads=0, host_reload_tokens=0, cap_applied=0, cap_exempt=0,
                          gpu_kv_peak=0, slice_steps=0)

    # ---------------------------------------------------------------- KV bookkeeping
    def kv_used(self) -> int:
        return sum(self.gpu.values())

    def gpu_kv_fraction(self) -> float:
        return self.kv_used() / float(self.gpu_kv_tokens)

    def host_kv_fraction(self) -> float:
        return sum(self.host.values()) / float(HOST_KV_TOKENS)

    def readiness(self, session: str) -> str:
        if session in self.gpu:
            return "GPU-WARM"
        if session in self.host:
            return "HOST-WARM"
        return "COLD"

    def place(self, session: str, tokens: int, tier: str) -> None:
        """Put a session's history in a tier, evicting by LRU when GPU KV will not hold it."""
        if tier == "gpu":
            self.host.pop(session, None)
            self.gpu[session] = int(tokens)
            self._evict_gpu()
        elif tier == "host":
            self.gpu.pop(session, None)
            self.host[session] = int(tokens)
        else:
            self.gpu.pop(session, None)
            self.host.pop(session, None)
        self.touch[session] = self.clock
        self.stats["gpu_kv_peak"] = max(self.stats["gpu_kv_peak"], self.kv_used())

    def _evict_gpu(self) -> None:
        """StudyRH5 / StudyE10b's mechanism: past GPU KV, prefixes are evicted LRU. With host
        offload the evicted copy lands on the host tier and its next touch RELOADS; with GPU-only
        KV it is gone and its next touch RE-PREFILLS the whole history."""
        while self.kv_used() > self.gpu_kv_tokens and self.gpu:
            victim = min(self.gpu, key=lambda s: self.touch.get(s, -1.0))
            tok = self.gpu.pop(victim)
            self.stats["evictions"] += 1
            if self.kv_mode == "HOST":
                self.host[victim] = tok

    # ---------------------------------------------------------------- submission
    def submit(self, r: Request) -> Request:
        r.visible_s = r.arrival_s + r.frontend_s
        r.remaining = float(r.compute_tokens)
        r.encoder_left = float(r.encoder_s)
        self._seq += 1
        heapq.heappush(self._pending, (r.visible_s, self._seq, r))
        return r

    def n_in_system(self) -> int:
        return len(self.waiting) + len(self.running)

    def next_event_s(self) -> Optional[float]:
        if self._pending:
            return self._pending[0][0]
        return None

    def _admit_visible(self) -> None:
        while self._pending and self._pending[0][0] <= self.clock + 1e-12:
            _t, _s, r = heapq.heappop(self._pending)
            self.waiting.append(r)

    def _order(self, rs: List[Request]) -> List[Request]:
        if self.policy == "priority":
            return sorted(rs, key=lambda r: (r.priority(), r.visible_s))
        return sorted(rs, key=lambda r: r.visible_s)

    # ---------------------------------------------------------------- one scheduler step
    def step(self) -> List[Request]:
        """Run one scheduler step. Returns the requests whose first token this step produced."""
        self._admit_visible()
        if not self.waiting and not self.running:
            nxt = self.next_event_s()
            if nxt is None:
                return []
            self.clock = max(self.clock, nxt)
            self._admit_visible()
        # the vision encoder is one unsplittable step that holds the whole engine (StudyE10d)
        for r in self._order(self.running) + self._order(self.waiting):
            if r.encoder_left > 0:
                dur = r.encoder_left
                r.encoder_left = 0.0
                if r in self.waiting:
                    self.waiting.remove(r)
                    self.running.append(r)
                if r.first_sched_s is None:
                    r.first_sched_s = self.clock
                self.clock += dur
                self.stats["steps"] += 1
                self.stats["gpu_busy_s"] += dur
                return []
        budget = float(self.budget)
        step_time = 0.0
        n_sys = self.n_in_system()
        finished: List[Request] = []
        for r in self._order(self.running) + self._order(self.waiting):
            if budget <= 0:
                break
            if r.unit_s > 0:
                # a measured, unsplittable compute unit (warm recall over a cached prefix)
                if r in self.waiting:
                    self.waiting.remove(r)
                    self.running.append(r)
                if r.first_sched_s is None:
                    r.first_sched_s = self.clock
                    step_time += r.reload_s
                    if r.reload_s:
                        self.stats["host_reloads"] += 1
                        self.stats["host_reload_tokens"] += r.prompt_tokens
                step_time += r.unit_s
                r.unit_s = 0.0
                r.remaining = 0.0
                r.steps += 1
                finished.append(r)
                budget = 0.0            # it occupied the step
                continue
            take = min(r.remaining, budget)
            if self.cap > 0 and r.remaining > self.cap:
                if n_sys > 1:
                    take = min(take, float(self.cap))
                    self.stats["cap_applied"] += 1
                else:
                    # vLLM's own exemption: "when it is the only request there is nobody to
                    # starve, so let it use the whole budget" (scheduler.py l. 611-619)
                    self.stats["cap_exempt"] += 1
            if take <= 0:
                continue
            if r in self.waiting:
                self.waiting.remove(r)
                self.running.append(r)
            if r.first_sched_s is None:
                r.first_sched_s = self.clock
                step_time += r.reload_s
                if r.reload_s:
                    self.stats["host_reloads"] += 1
                    self.stats["host_reload_tokens"] += r.prompt_tokens
            r.remaining -= take
            r.steps += 1
            budget -= take
            step_time += take / r.rate_tok_s
            self.stats["step_tokens"] += take
            if r.kind == "slice":
                self.stats["slice_steps"] += 1
            if r.remaining <= 1e-9:
                finished.append(r)
        step_time += self.step_overhead_s
        self.clock += step_time
        self.stats["steps"] += 1
        self.stats["gpu_busy_s"] += step_time
        for r in finished:
            r.done_s = self.clock
            self.running.remove(r)
            self.done.append(r)
            if r.session is not None:
                self.touch[r.session] = self.clock
        return finished

    def run_until(self, t_end: float, max_steps: int = 2_000_000) -> None:
        n = 0
        while n < max_steps:
            n += 1
            if not self.waiting and not self.running:
                nxt = self.next_event_s()
                if nxt is None or nxt > t_end:
                    self.clock = max(self.clock, min(t_end, nxt if nxt else t_end))
                    return
                self.clock = max(self.clock, nxt)
            if self.clock > t_end and not self.running and not self.waiting:
                return
            self.step()
            if self.clock > t_end and not self.running and not self.waiting and not self._pending:
                return

    def drain(self, cap_s: float = 300.0) -> None:
        t0 = self.clock
        while (self.waiting or self.running or self._pending) and self.clock - t0 < cap_s:
            self.step()


# ============================================================ request builders
def episodic_request(rid: str, t: float, n_frames: int = 1) -> Request:
    """One episodic Nexar decision. StudyD3 / D14 prompt tokens: 378 at N = 1, 1,062 at N = 3."""
    tok = {1: 378, 3: 1062}[n_frames]
    return Request(rid=rid, kind="episodic", arrival_s=t, prompt_tokens=tok, compute_tokens=tok,
                   frontend_s=FRONTEND_EPISODIC_S, rate_tok_s=RATE_EPISODIC_TOK_S,
                   meta=dict(n_frames=n_frames))


def cold_recall_request(rid: str, t: float, tokens: int = 12645, session: Optional[str] = None,
                        body: str = "png", encoder: bool = True,
                        slice_tokens: Optional[int] = None,
                        slice_overhead_s: float = 0.0) -> Request:
    """A cold recall: the whole history is prefilled. StudyE10d's phase decomposition, and
    StudyE10e's cap behaviour, both apply. `slice_tokens` chains the prefill in slices, whose
    PER-SLICE OVERHEAD IS NOT A MEASURED QUANTITY (StudySIM1 sweeps it)."""
    rate = (RATE_COLD_K1_TOK_S if abs(tokens - 12645) < 2000
            else RATE_COLD_BY_SIZE[min(RATE_COLD_BY_SIZE, key=lambda s: abs(s - tokens))])
    r = Request(rid=rid, kind="cold" if slice_tokens is None else "slice", arrival_s=t,
                prompt_tokens=tokens, compute_tokens=tokens, session=session,
                frontend_s=(FRONTEND_COLD_PNG_S if body == "png" else FRONTEND_COLD_TEXT_S),
                encoder_s=(VISION_ENCODER_S if encoder else 0.0), rate_tok_s=rate,
                meta=dict(slice_tokens=slice_tokens, slice_overhead_s=slice_overhead_s))
    if slice_tokens:
        n_slices = int(math.ceil(tokens / float(slice_tokens)))
        # the chain's overhead is charged as extra compute time, converted to tokens at this
        # request's own rate so the engine model needs no special case
        r.compute_tokens = tokens + (n_slices - 1) * slice_overhead_s * rate
        r.remaining = r.compute_tokens
        r.meta["n_slices"] = n_slices
    return r


def warm_recall_request(rid: str, t: float, session: str, history_tokens: int, readiness: str,
                        kind: str = "append", delta_tokens: int = 450) -> Request:
    """A warm append or escalation over a cached prefix.

    **The measured TTFT is DECOMPOSED, and the decomposition is itself calibrated.** StudyRH5
    Part A measured an isolated warm request's TTFT (0.382 s GPU-WARM / 0.459 s HOST-WARM at 11k
    tokens; 0.874 / 1.001 at 28k) while computing only its new tokens. Charging that whole TTFT
    as engine occupancy would be wrong, and StudyE10b says by how much: at KV-HOST k = 8, N = 1,
    25 %, 0.875 warm requests per second raised GPU utilisation from 39 % to 45 % and computed
    tok/s from 1,423 to 1,804 - about 0.07 s of GPU per warm request, not 0.37 s. So:

      engine occupancy = its DELTA tokens at the measured prefill rate
                         (StudyE10b: a D2 append is 90 tokens per frame, five new frames per
                         10-s append = 450 tokens; an escalation's question tail is ~90)
      the remainder    = non-blocking time (host load, API handling, and attention over the
                         cached prefix that overlaps other requests' work), carried as the
                         request's own frontend so its ISOLATED TTFT still equals StudyRH5's
                         measurement.

    The size interpolation between StudyRH5's 11k and 28k points is linear in tokens - a RULE,
    stated here, in `costs.py` and in the report.
    """
    lo, hi = 11050, 28114
    a, b = WARM_TTFT_S[(lo, readiness)], WARM_TTFT_S[(hi, readiness)]
    tokens = max(int(history_tokens), 1)
    if tokens <= lo:
        ttft = a * tokens / lo
    elif tokens >= hi:
        ttft = b * tokens / hi
    else:
        ttft = a + (b - a) * (tokens - lo) / (hi - lo)
    rl, rh = HOST_RELOAD_VISIBLE_S[lo], HOST_RELOAD_VISIBLE_S[hi]
    reload_s = 0.0
    if readiness == "HOST-WARM":
        reload_s = (rl * tokens / lo if tokens <= lo else
                    (rh * tokens / hi if tokens >= hi else
                     rl + (rh - rl) * (tokens - lo) / (hi - lo)))
    gpu_s = (delta_tokens / RATE_EPISODIC_TOK_S
             + WARM_ATTENTION_S_PER_TOKEN * tokens)
    return Request(rid=rid, kind=kind, arrival_s=t, prompt_tokens=tokens,
                   compute_tokens=delta_tokens + WARM_ATTENTION_S_PER_TOKEN * tokens
                   * RATE_EPISODIC_TOK_S, session=session,
                   frontend_s=max(ttft - gpu_s, FRONTEND_WARM_S),
                   rate_tok_s=RATE_EPISODIC_TOK_S,
                   meta=dict(readiness=readiness, history_tokens=tokens,
                             measured_isolated_ttft_s=ttft, host_reload_s=reload_s,
                             engine_occupancy_s=gpu_s))


SOURCES = {
    "MAX_NUM_BATCHED_TOKENS": "vLLM 0.31.0 default, verified in StudyE10c's 87 server logs",
    "GPU_KV_TOKENS": "StudyRH3 / RH4 / RH5 / E10b: 62,944 tokens on the image server",
    "RATE_EPISODIC_TOK_S": "StudyD7b peak 15.10 req/s x 378 tokens = 5,708 tok/s",
    "RATE_COLD_BY_SIZE": "StudyRH5 Part A cold re-prefill rates (4.5k at 11k, 3.8k at 28k)",
    "RATE_COLD_K1_TOK_S": "StudyE10d: 12,645 tokens of LM prefill in 2.17 s",
    "FRONTEND_EPISODIC_S": "StudyD7b concurrency 1 TTFT p50 0.134 s minus 378 / 5,708 s",
    "FRONTEND_COLD_PNG_S": "StudyE10d frontend phase, 50.3 MB PNG body",
    "VISION_ENCODER_S": "StudyE10d: one unsplittable encoder step of about 0.2 s",
    "WARM_TTFT_S": "StudyRH5 Part A isolated TTFT medians, D2 format, DECOMPOSED into engine "
                   "occupancy (delta tokens at the measured rate) and non-blocking time, with "
                   "the split calibrated against StudyE10b's GPU utilisation and computed tok/s",
    "WARM_DELTA_TOKENS": "StudyE10b: a D2 append is 90 tokens per frame and carries five new "
                         "2-s-stride frames per 10-s append = 450 tokens",
    "WARM_ATTENTION_S_PER_TOKEN": "DERIVED from StudyE10b's GPU-utilisation deltas at KV-HOST "
                                  "k = 8 and k = 16; the two derivations disagree (0.069 s and "
                                  "0.142 s per warm request) and the midpoint is used",
    "WARM_MISS_BY_FOOTPRINT": "StudyE10b's measured warm-miss counts by warm footprint (0 below "
                              "1x KV, 0.81 at about 1.2x, 0.91 at about 2.4x) with StudyRH5's "
                              "GPU-only token hits as the cross-check; a miss re-prefills the "
                              "WHOLE history (StudyE10b median cached fraction 0.002)",
    "D2_TOKENS_PER_S": "StudyRH4 D2: 90 tokens per 2-s frame = 45 tokens per second of session",
    "HOST_RELOAD_VISIBLE_S": "StudyRH5 Part A visible cost of a host reload vs a GPU-warm hit",
    "STEP_OVERHEAD_S": "DERIVED from StudyE10e's cold-TTFT ratios; the two implied values "
                       "disagree (0.003 and 0.016 s), so the midpoint is used and both reported",
    "CONFIGS": "StudyE10e P0-P3 and StudyE10c E2, with vLLM's own cap exemption",
}
