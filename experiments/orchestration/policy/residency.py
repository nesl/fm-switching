"""StudyRES1-residency: can the scheduler's own bookkeeping say where each history is?

WHAT THIS MODULE IS. A chunk-level two-tier (GPU and host) bookkeeping model of the serving
stack's cache, driven ONLY by what a scheduler knows online: each request's arrival, its prompt
length, which prefix it intends to reuse, its completion, and the two capacities. It reads no
measured cache-hit, load or compute counter, and a test asserts that no such field can reach it:
`Req` has no field for one.

THE RULE IT IMPLEMENTS is StudyENG1c-hostfull Part A's identified rule, quoted from that report's
section 3 and section 11:

  - write-through: every block computed on GPU is also stored on host;
  - a host chunk's recency is set when it is stored and refreshed when a request that used it
    finishes;
  - a request served WHOLLY from GPU refreshes all of its prefix on host;
  - a request that loads ANYTHING from host refreshes only what it loaded, so its GPU-served head
    is NOT refreshed on host;
  - misses refresh nothing;
  - within a history the tail is evicted first;
  - a block-aligned prompt must recompute its last block, so if the history is also on host the
    request takes the host-load path.

PART A IS IN-SAMPLE for this rule: it was finalized after seeing Part A's 95 probes, so Part A
cannot test it. The TEST set is Parts B, C, D (FIT pairs) and E.

THE COMPARISON PREDICTORS are the alternatives the rule has to beat, and they share every line of
this machinery except the policy switch, so a difference between them is the policy and nothing
else:

  - `fifo`: recency is set when a chunk is stored and never refreshed;
  - `lru_any`: any access refreshes the chunk on both tiers, with no host-path asymmetry;
  - `lru_host`: host recency is refreshed only by an actual host load, so a wholly-GPU request
    does not keep its host copy alive;
  - `occupancy`: no per-history state at all. It predicts from tier fullness, which is the
    "host-warm if the host is not full" reading the brief asks to rule out.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

TOKENS_PER_BLOCK = 16
HOST_TOKENS_PER_GIB = 4096          # 256 KiB per token at 16-token blocks (ENG1c section 1)
GPU_POOL_TOKENS_H100NVL = 62944     # measured at every one of ENG1c's 16 server starts

POLICIES = ("rule", "fifo", "lru_any", "lru_host", "occupancy")
CLASSES = ("GPU", "HOST", "COLD", "PARTIAL")


def host_tokens_for_cap(cap_gib: float) -> int:
    return int(round(float(cap_gib) * HOST_TOKENS_PER_GIB))


def n_chunks(tokens: int) -> int:
    return int(math.ceil(max(int(tokens), 0) / float(TOKENS_PER_BLOCK)))


@dataclass
class Req:
    """One request, as the scheduler sees it before it runs.

    There is deliberately NO field for a measured hit, load or compute count: the predictor
    cannot read one even by accident."""

    rid: str
    t_submit: float
    t_end: float
    prompt_tokens: int
    hid: Optional[str] = None          # the history whose prefix this request reuses
    hist_tokens: int = 0               # how much of that history is reusable, scheduler side
    writes_hid: Optional[str] = None   # the history this request's computed blocks belong to
    part: str = ""
    server: str = ""
    cap_gib: float = 0.0
    trial: str = ""
    conc: Optional[int] = None
    holdout: bool = False
    reuse: bool = False                # whether it is a scored reuse request
    meta: Dict[str, Any] = field(default_factory=dict)


class Tier:
    """One cache tier: items under a token capacity, evicted least-recent first.

    An item is either one 16-token BLOCK of a tracked history, keyed (hid, index), or one BULK
    write of untracked work, keyed by its request id. The distinction is pure bookkeeping
    economy: only histories that some request later reuses need block-level detail, and the rest
    of the stream matters solely through the tokens it occupies and when it was written. A bulk
    item is evicted partially when that is all the room the tier needs, so the token accounting
    is exact either way.

    Tail-first eviction within a history is not a special case: a refresh gives chunk 0 the
    highest recency and the last chunk the lowest, so ordinary least-recency eviction takes the
    tail first, which is what StudyENG1c Part A observed."""

    def __init__(self, capacity_tokens: int, name: str = "") -> None:
        self.capacity_tokens = int(capacity_tokens)
        self.name = name
        self.seq: Dict[Any, int] = {}
        self.size: Dict[Any, int] = {}
        self._total = 0
        self._heap: List[Tuple[int, Any]] = []
        self._clock = 1
        self.evicted_blocks = 0
        self.stored_blocks = 0

    # ---------------------------------------------------------------- queries
    def __contains__(self, key: Any) -> bool:
        return key in self.seq

    def tokens(self) -> int:
        return self._total

    def usage(self) -> float:
        if self.capacity_tokens <= 0:
            return 1.0
        return self._total / float(self.capacity_tokens)

    def leading_run(self, hid: str, start: int, n: int) -> int:
        """How many chunks of `hid` from index `start` are present, contiguously."""
        i = start
        seq = self.seq
        while i < n and (hid, i) in seq:
            i += 1
        return i - start

    # ---------------------------------------------------------------- updates
    def _put(self, key: Any, tokens: int, seq: int) -> None:
        old = self.size.get(key)
        if old is None:
            self.size[key] = int(tokens)
            self._total += int(tokens)
            self.stored_blocks += max(int(tokens) // TOKENS_PER_BLOCK, 1)
        self.seq[key] = seq
        heapq.heappush(self._heap, (seq, key))
        self._maybe_prune()

    def _maybe_prune(self) -> None:
        if len(self._heap) > 4 * len(self.seq) + 4096:
            self._heap = [(s, k) for k, s in self.seq.items()]
            heapq.heapify(self._heap)

    def touch(self, hid: str, indices: Sequence[int], only_present: bool = True) -> None:
        idx = sorted(indices)
        if not idx:
            return
        base = self._clock
        self._clock += len(idx) + 1
        for rank, i in enumerate(reversed(idx)):
            key = (hid, i)
            if only_present and key not in self.seq:
                continue
            self._put(key, TOKENS_PER_BLOCK, base + rank)

    def store(self, hid: str, indices: Sequence[int]) -> None:
        self.touch(hid, indices, only_present=False)

    def store_bulk(self, key: Any, tokens: int) -> None:
        """One untracked write, held as a single divisible item."""
        if tokens <= 0:
            return
        s = self._clock
        self._clock += 1
        self._put(("bulk", key), int(tokens), s)

    def _remove(self, key: Any) -> None:
        tok = self.size.pop(key, 0)
        self._total -= tok
        self.seq.pop(key, None)

    def evict_to_capacity(self, protected: Optional[set] = None) -> int:
        """Evict least-recent items until the tier is within capacity. `protected` holds the
        blocks of the request being served, which the engine cannot free under it."""
        freed = 0
        protected = protected or set()
        deferred: List[Tuple[int, Any]] = []
        while self._total > self.capacity_tokens and self._heap:
            s, key = heapq.heappop(self._heap)
            cur = self.seq.get(key)
            if cur is None or cur != s:
                continue
            if key in protected:
                deferred.append((s, key))
                if len(deferred) >= len(self.seq):
                    break
                continue
            over = self._total - self.capacity_tokens
            tok = self.size.get(key, 0)
            if tok > over and isinstance(key, tuple) and key and key[0] == "bulk":
                self.size[key] = tok - over
                self._total -= over
                heapq.heappush(self._heap, (s, key))
                freed += 1
                self.evicted_blocks += max(over // TOKENS_PER_BLOCK, 1)
                break
            self._remove(key)
            freed += 1
            self.evicted_blocks += max(tok // TOKENS_PER_BLOCK, 1)
        for item in deferred:
            heapq.heappush(self._heap, item)
        return freed

    def drop_history(self, hid: str, n: int) -> None:
        for i in range(n):
            if (hid, i) in self.seq:
                self._remove((hid, i))


@dataclass
class Prediction:
    cls: str
    gpu_chunks: int
    host_chunks: int
    hit_tokens: int
    recomputed_prefix_tokens: int
    host_fraction: float
    host_path: bool
    forced_last_block: bool

    def as_dict(self) -> Dict[str, Any]:
        return dict(predicted_class=self.cls, gpu_chunks=self.gpu_chunks,
                    host_chunks=self.host_chunks, hit_tokens=self.hit_tokens,
                    recomputed_prefix_tokens=self.recomputed_prefix_tokens,
                    predicted_host_fraction=self.host_fraction, host_path=self.host_path,
                    forced_last_block=self.forced_last_block)


class ResidencyModel:
    """The scheduler-side bookkeeping. One instance per server segment, since a server start
    empties both tiers."""

    def __init__(self, cap_gib: float, policy: str = "rule",
                 gpu_pool_tokens: int = GPU_POOL_TOKENS_H100NVL,
                 tracked: Optional[set] = None) -> None:
        if policy not in POLICIES:
            raise ValueError("policy must be one of %s, got %r" % (POLICIES, policy))
        self.policy = policy
        # Histories some request later reuses are tracked block by block; all other work is held
        # as one divisible bulk item per request, which changes no token accounting and no
        # prediction, only the bookkeeping cost. `None` tracks everything.
        self.tracked = tracked
        self.cap_gib = float(cap_gib)
        self.gpu = Tier(int(gpu_pool_tokens), "gpu")
        self.host = Tier(host_tokens_for_cap(cap_gib), "host")
        self.history_tokens: Dict[str, int] = {}
        self.ever_built: Dict[str, bool] = {}
        self.n_predictions = 0

    # ------------------------------------------------------------- prediction
    def predict(self, req: Req) -> Prediction:
        self.n_predictions += 1
        hid, hist = req.hid, int(req.hist_tokens or 0)
        if not hid or hist <= 0:
            return Prediction("COLD", 0, 0, 0, 0, 0.0, False, False)
        n = n_chunks(hist)
        if self.policy == "occupancy":
            return self._predict_occupancy(req, hid, hist, n)
        g = self.gpu.leading_run(hid, 0, n)
        h = self.host.leading_run(hid, g, n)
        forced = False
        host_path = h > 0
        # The engine must compute at least the last token of the prompt. It bites only when the
        # reusable prefix IS the whole prompt and the prompt is block aligned (ENG1c Part A: the
        # three PG misses). The connector then loads that last block from host if it is there,
        # and the request takes the host-load path.
        if hist >= req.prompt_tokens and req.prompt_tokens % TOKENS_PER_BLOCK == 0:
            if g + h >= n and n > 0:
                forced = True
                if (hid, n - 1) in self.host:
                    host_path = True
                    if h == 0:
                        h = 1
                        g = max(g - 1, 0)
        hit_chunks = min(g + h, n)
        hit_tokens = min(hit_chunks * TOKENS_PER_BLOCK, hist)
        recomputed = max(hist - hit_tokens, 0)
        host_fraction = (min(h * TOKENS_PER_BLOCK, hist) / float(hist)) if hist > 0 else 0.0
        if hit_chunks <= 1:
            cls = "COLD"
        elif recomputed <= TOKENS_PER_BLOCK:
            cls = "HOST" if host_path else "GPU"
        else:
            cls = "PARTIAL"
        return Prediction(cls, g, h, hit_tokens, recomputed, host_fraction, host_path, forced)

    def _predict_occupancy(self, req: Req, hid: str, hist: int, n: int) -> Prediction:
        """The alternative explanation to rule out: tier fullness alone, with no per-history
        state. A history that was ever built is called GPU-warm while the GPU pool is not full,
        host-warm while the host is not full, and cold once it is."""
        built = self.ever_built.get(hid, False)
        if not built:
            return Prediction("COLD", 0, 0, 0, hist, 0.0, False, False)
        if self.gpu.tokens() < self.gpu.capacity_tokens:
            return Prediction("GPU", n, 0, hist, 0, 0.0, False, False)
        if self.host.tokens() < self.host.capacity_tokens:
            return Prediction("HOST", 0, n, hist, 0, 1.0, True, False)
        return Prediction("COLD", 0, 0, 0, hist, 0.0, False, False)

    # ----------------------------------------------------------- state update
    def complete(self, req: Req, pred: Prediction) -> None:
        """Apply the request: its computed blocks are stored on GPU and written through to host,
        and the policy's refresh rule is applied to what it used."""
        hid = req.writes_hid or req.hid or req.rid
        total_chunks = n_chunks(req.prompt_tokens)
        hit_chunks = 0
        if req.hid and pred.hit_tokens > 0:
            hit_chunks = n_chunks(pred.hit_tokens)
        self.ever_built[hid] = True
        self.history_tokens[hid] = max(self.history_tokens.get(hid, 0), int(req.prompt_tokens))

        if self.tracked is not None and hid not in self.tracked:
            tokens = max(req.prompt_tokens - pred.hit_tokens, 0)
            self.gpu.store_bulk(req.rid, tokens)
            self.host.store_bulk(req.rid, tokens)
            self.gpu.evict_to_capacity({("bulk", req.rid)})
            self.host.evict_to_capacity({("bulk", req.rid)})
            return

        computed = list(range(hit_chunks, total_chunks))
        used_gpu = list(range(0, min(pred.gpu_chunks, total_chunks)))
        used_host = list(range(min(pred.gpu_chunks, total_chunks),
                               min(pred.gpu_chunks + pred.host_chunks, total_chunks)))
        reuse_same_history = bool(req.hid and (req.writes_hid in (None, req.hid)))

        if self.policy == "occupancy":
            self._store(hid, computed, req)
            return

        # GPU: every block the request used or computed is resident and most recently used.
        if self.policy == "fifo":
            self.gpu.store(hid, computed)
        else:
            if reuse_same_history:
                self.gpu.touch(hid, used_gpu + used_host, only_present=False)
            self.gpu.store(hid, computed)

        # Host: write-through for everything computed, plus the policy's refresh rule.
        host_refresh: List[int] = []
        if self.policy == "lru_any":
            host_refresh = used_gpu + used_host
        elif self.policy == "lru_host":
            host_refresh = used_host
        elif self.policy == "rule":
            if pred.host_path:
                host_refresh = used_host
            else:
                host_refresh = used_gpu + used_host
        if reuse_same_history and host_refresh:
            self.host.touch(hid, host_refresh, only_present=True)
        self.host.store(hid, computed)

        protected = {(hid, i) for i in range(total_chunks)}
        self.gpu.evict_to_capacity(protected)
        self.host.evict_to_capacity(protected)

    def _store(self, hid: str, computed: Sequence[int], req: Req) -> None:
        self.gpu.store(hid, computed)
        self.host.store(hid, computed)
        protected = {(hid, i) for i in range(n_chunks(req.prompt_tokens))}
        self.gpu.evict_to_capacity(protected)
        self.host.evict_to_capacity(protected)

    def state(self) -> Dict[str, Any]:
        return dict(policy=self.policy, cap_gib=self.cap_gib,
                    gpu_tokens=self.gpu.tokens(), gpu_capacity=self.gpu.capacity_tokens,
                    gpu_usage=self.gpu.usage(), host_tokens=self.host.tokens(),
                    host_capacity=self.host.capacity_tokens, host_usage=self.host.usage(),
                    gpu_evicted_blocks=self.gpu.evicted_blocks,
                    host_evicted_blocks=self.host.evicted_blocks,
                    n_histories=len(self.ever_built), n_predictions=self.n_predictions)


def tracked_histories(requests: Iterable[Req]) -> set:
    """The histories that some request in this stream reuses. Only these need block-level
    bookkeeping; everything else matters through its tokens and its recency alone."""
    out = set()
    for r in requests:
        if r.reuse and r.hid:
            out.add(r.hid)
            if r.writes_hid:
                out.add(r.writes_hid)
    return out


def replay(requests: Iterable[Req], cap_gib: float, policy: str = "rule",
           gpu_pool_tokens: int = GPU_POOL_TOKENS_H100NVL) -> List[Dict[str, Any]]:
    """Replay one server segment in arrival order and return a prediction row per reuse request.

    Requests are applied in submit order and their state effects at completion order, which is
    what a scheduler would see. Nothing measured is read."""
    requests = list(requests)
    model = ResidencyModel(cap_gib, policy, gpu_pool_tokens,
                           tracked=tracked_histories(requests))
    out: List[Dict[str, Any]] = []
    for req in sorted(requests, key=lambda r: (r.t_submit, r.rid)):
        pred = model.predict(req)
        if req.reuse:
            row = dict(rid=req.rid, part=req.part, server=req.server, cap_gib=req.cap_gib,
                       trial=req.trial, conc=req.conc, holdout=req.holdout,
                       hid=req.hid, hist_tokens=req.hist_tokens,
                       prompt_tokens=req.prompt_tokens, policy=policy,
                       state=model.state(), **pred.as_dict())
            row.update(req.meta)
            out.append(row)
        model.complete(req, pred)
    return out
