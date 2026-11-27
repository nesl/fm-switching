"""Layer P (A1).

PROVISIONAL APPROXIMATION: the shadow pins the prompts of every in-flight request and has no
scheduler admission; the faithful vLLM 0.31.0 admission model (scheduler.py:1209,
config/scheduler.py:191, kv_cache_manager.py:519-534) is an option (`admission=True`), default OFF;
validation on five committed s4 cells: all-robot accuracy >= 0.90 in 4 of 5 cells (n32 0.882).

Layer P (A1): a SHADOW OF THE ENGINE PREFIX CACHE driven only by what the coordinator sends and books.

OBSERVE-ONLY. No decision reads P in A1; `p_cached_fraction(...)` is exposed for later consumers.

WHAT IS MODELLED (vLLM 0.31.0 as served in the committed cells):
  * block-hash prefix cache, BLOCK_SIZE = 16 tokens, FULL blocks only (a partial tail block is never
    hashed, so a prompt of n tokens leaves floor(n/16) reusable blocks).
  * a hit is the longest CONTIGUOUS run of blocks from block 0 of the chain (find_longest_cache_hit).
  * blocks of requests in flight are PINNED (ref-counted); on completion they join the free queue,
    in REVERSE block order (tail first), so the oldest-freed tail is evicted first; plain LRU on the
    free queue, DEMAND-driven: nothing is evicted until an allocation does not fit.
  * the host tier (`--kv-offloading-backend native`) is modelled as a second LRU of blocks. WHICH
    blocks are written: with the arm's `live2_offload_controls` ON (`offload_policy.RULE`: dashcam and
    assistive send `max_offload_tokens: 0`, robot sends none) only ROBOT-kind requests store; with it
    OFF every kind writes through (`offload_controls` ctor arg = coordinator `_offload_controls`).
    The GPU shadow holds every kind either way; evicted only when an incoming store does not fit
    (study_d250_host_drop_diagnosis.md: plain LRU on exhaustion, no watermark).
  * WHAT `cached_tokens` COUNTS: GPU hits PLUS host-connector hits (vLLM reports num_computed_tokens
    at first schedule, local + external). The committed evidence is robot `cached_tokens == 0` on
    0.8 pct of requests at 27 GiB while the 22-session working set is 3.3x the host tier and
    >5x the GPU pool. `gpu_only=True` is the diagnostic alternative, not the default.
CAPACITIES are inputs (no fitted constants): gpu_blocks = gpu_kv_tokens // 16 from the cell header
(1x: 62,944 tokens = 3,934 blocks; halved: --num-gpu-blocks-override 1968), host_blocks =
host_tier_tokens // 16 from the header (27 GiB: 110,630 tokens = 6,914 blocks).

Pure: no coordinator imports. Switch `live2_predictive_belief`: DEFAULT OFF, INSTANCE attribute only;
a truthy class attribute raises and a non-bool value raises.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Hashable, List, Optional, Tuple

SWITCH = "live2_predictive_belief"
BLOCK = 16


ENGINE_RESYNC_SWITCH = "live2_pb_engine_resync"


def engine_resync_enables(arm: Any) -> bool:
    """Same contract as `arm_enables`: arm-scoped INSTANCE bool, DEFAULT OFF, a class attribute or a
    non-bool raises."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if ENGINE_RESYNC_SWITCH not in own:
        for klass in type(arm).__mro__:
            if ENGINE_RESYNC_SWITCH in klass.__dict__ and bool(klass.__dict__[ENGINE_RESYNC_SWITCH]):
                raise PredictiveBeliefSwitchError(
                    "%s is ON as a CLASS attribute of %s; it requires an arm-scoped INSTANCE attribute"
                    % (ENGINE_RESYNC_SWITCH, klass.__name__))
        return False
    v = own[ENGINE_RESYNC_SWITCH]
    if not isinstance(v, bool):
        raise PredictiveBeliefSwitchError("%s must be a bool, got %r (%s)"
                                          % (ENGINE_RESYNC_SWITCH, v, type(v).__name__))
    return v


WIRE_TOKENS_SWITCH = "live2_pb_wire_tokens"
HOST_ENGINE_SWITCH = "live2_pb_host_engine_model"


def host_engine_enables(arm: Any) -> bool:
    """Same contract as `engine_resync_enables`: arm-scoped INSTANCE bool, DEFAULT OFF, a class
    attribute or a non-bool raises. ON: P models the engine's host tier (`host_engine_model`)."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if HOST_ENGINE_SWITCH not in own:
        for klass in type(arm).__mro__:
            if HOST_ENGINE_SWITCH in klass.__dict__ and bool(klass.__dict__[HOST_ENGINE_SWITCH]):
                raise PredictiveBeliefSwitchError(
                    "%s is ON as a CLASS attribute of %s; it requires an arm-scoped INSTANCE attribute"
                    % (HOST_ENGINE_SWITCH, klass.__name__))
        return False
    v = own[HOST_ENGINE_SWITCH]
    if not isinstance(v, bool):
        raise PredictiveBeliefSwitchError("%s must be a bool, got %r (%s)"
                                          % (HOST_ENGINE_SWITCH, v, type(v).__name__))
    return v



def wire_tokens_enables(arm: Any) -> bool:
    """Same contract as `engine_resync_enables`: arm-scoped INSTANCE bool, DEFAULT OFF, a class
    attribute or a non-bool raises. ON: P is told a PIECE request's prompt size from the frames its
    wire body carries (frames[:already] + new) x D2_TOK_PER_IMG + D2_HEADER_TOK, not the cumulative
    `built_tokens + piece` (which excludes frames submitted but not yet completed)."""
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if WIRE_TOKENS_SWITCH not in own:
        for klass in type(arm).__mro__:
            if WIRE_TOKENS_SWITCH in klass.__dict__ and bool(klass.__dict__[WIRE_TOKENS_SWITCH]):
                raise PredictiveBeliefSwitchError(
                    "%s is ON as a CLASS attribute of %s; it requires an arm-scoped INSTANCE attribute"
                    % (WIRE_TOKENS_SWITCH, klass.__name__))
        return False
    v = own[WIRE_TOKENS_SWITCH]
    if not isinstance(v, bool):
        raise PredictiveBeliefSwitchError("%s must be a bool, got %r (%s)"
                                          % (WIRE_TOKENS_SWITCH, v, type(v).__name__))
    return v


def wire_prompt_tokens(n_frames: int, tok_per_img: int, header_tok: int) -> int:
    return int(n_frames) * int(tok_per_img) + int(header_tok)


class PredictiveBeliefSwitchError(RuntimeError):
    """The switch was declared on a class, or with a non-bool value."""


def arm_enables(arm: Any) -> bool:
    try:
        own = vars(arm)
    except TypeError:                                                          # pragma: no cover
        own = {}
    if SWITCH not in own:
        for klass in type(arm).__mro__:
            if SWITCH in klass.__dict__ and bool(klass.__dict__[SWITCH]):
                raise PredictiveBeliefSwitchError(
                    "%s is ON as a CLASS attribute of %s; layer P requires an arm-scoped "
                    "INSTANCE attribute" % (SWITCH, klass.__name__))
        return False
    v = own[SWITCH]
    if not isinstance(v, bool):
        raise PredictiveBeliefSwitchError("%s must be a bool, got %r (%s)"
                                          % (SWITCH, v, type(v).__name__))
    return v


class PredictiveBelief:
    def __init__(self, gpu_blocks: int, host_blocks: int, gpu_only: bool = False,
                 offload_controls: bool = True, max_num_seqs: int = 1024,
                 prefill_s_per_token: Optional[float] = None, admission: bool = False,
                 engine_resync: bool = False, host_engine_model: bool = False) -> None:
        if not isinstance(host_engine_model, bool):
            raise PredictiveBeliefSwitchError("host_engine_model must be a bool, got %r" % (host_engine_model,))
        self.host_engine = host_engine_model
        self._touch: Dict[str, List[Tuple[Hashable, int]]] = {}
        self._protect: set = set()
        self.admission = bool(admission)
        self.engine_resync = bool(engine_resync)
        self._rob: Dict[str, bool] = {}
        self.prefill_s = None if prefill_s_per_token is None else float(prefill_s_per_token)
        self._server_free = 0.0
        self.offload_controls = bool(offload_controls)
        self.gpu_cap = int(gpu_blocks)
        self.host_cap = int(host_blocks)
        self.gpu_only = bool(gpu_only)
        self._pin: Dict[Tuple[Hashable, int], int] = {}                 # block -> refcount
        self._free: "OrderedDict[Tuple[Hashable, int], None]" = OrderedDict()
        self._host: "OrderedDict[Tuple[Hashable, int], None]" = OrderedDict()
        self._req: Dict[str, Tuple[Hashable, int, int, int]] = {}            # rid -> (key, nblocks, hit_blocks)
        self._last_nb: Dict[Hashable, int] = {}                         # key -> blocks of last chain
        self._orphans = 0
        self._partial = 0
        self._wait: List[Tuple[str, Hashable, int, Optional[int], bool, float]] = []
        self._last_event = 0.0
        self._kv_block = False
        self.max_num_seqs = int(max_num_seqs)
        self.stats = dict(pb_sends_observed=0, pb_evictions_shadow=0, pb_resyncs=0,
                          pb_predictions=0, pb_resync_changed=0, pb_pinned_overshoot=0, pb_chain_resets=0,
                          pb_host_evictions=0, pb_queue_stale=0, pb_provisional_no_admission=int(not self.admission))

    def _hit_blocks(self, key: Hashable, nb: int) -> int:
        n = 0
        while n < nb:
            b = (key, n)
            if b in self._pin or b in self._free or (not self.gpu_only and b in self._host):
                n += 1
            else:
                break
        return n

    def p_cached_fraction(self, key: Hashable, prefix_tokens: int, now: float = 0.0,
                          shared_tokens: Optional[int] = None) -> Tuple[float, int]:
        """(estimated cached fraction of the prefix, implied cached tokens), PRE-SEND, read-only.
        `shared_tokens`: tokens of this prompt known (from what the coordinator itself presents) to
        be identical to the previous prompt under `key`; None means the whole prompt."""
        self.stats["pb_predictions"] += 1
        pt = int(prefix_tokens)
        if pt <= 0:
            return 0.0, 0
        nb = min(pt // BLOCK, max(pt - 1, 0) // BLOCK)                  # kv_cache_manager.py:295
        if shared_tokens is not None:
            nb = min(nb, max(int(shared_tokens), 0) // BLOCK)
        h = self._hit_blocks(key, nb)
        tok = min(h * BLOCK, pt)
        return tok / float(pt), tok

    def _alloc_gpu(self) -> None:
        while self._used() >= self.gpu_cap:
            if not self._free:
                self.stats["pb_pinned_overshoot"] += 1
                return
            self._free.popitem(last=False)
            self.stats["pb_evictions_shadow"] += 1

    def _host_put(self, b: Tuple[Hashable, int]) -> None:
        if self.host_engine:
            if b in self._host:
                return
            if len(self._host) >= self.host_cap:
                for v in self._host:
                    if v not in self._protect:
                        del self._host[v]
                        self.stats["pb_host_evictions"] += 1
                        break
                else:
                    self.stats["pb_host_dropped"] = self.stats.get("pb_host_dropped", 0) + 1
                    return
            self._host[b] = None
            return
        if b in self._host:
            self._host.move_to_end(b)
            return
        while len(self._host) >= self.host_cap and self._host:
            self._host.popitem(last=False)
            self.stats["pb_host_evictions"] += 1
        self._host[b] = None

    def _orphan(self, key: Hashable, sb: int) -> None:
        """Blocks (key, i >= sb) hold OLD content once the prompt diverges at block sb: they stay in
        the pool (they still occupy it and are evicted in order) but can no longer be hit."""
        lc = self._last_nb.get(key, 0)
        if sb >= lc:
            return
        self.stats["pb_chain_resets"] += 1
        self._orphans += 1
        for i in range(lc - 1, sb - 1, -1):
            b, nb_ = (key, i), (("o", self._orphans, key), i)
            if b in self._pin:
                del self._pin[b]                      # old content of a live request: freed, orphaned
                self._free[nb_] = None
            elif b in self._free:
                del self._free[b]
                self._free[nb_] = None
            if b in self._host:
                del self._host[b]
                self._host[nb_] = None

    def _used(self) -> int:
        return len(self._pin) + len(self._free) + self._partial

    def _admit(self, now: float = 0.0) -> None:
        """vLLM 0.31.0 scheduler, FCFS. A WAITING request holds NO blocks (blocks are touched and
        allocated only inside allocate_slots at scheduling time, scheduler.py:1209). With the default
        `scheduler_reserve_full_isl=True` (config/scheduler.py:191) it is admitted only if the FULL
        prompt's new blocks fit in the free queue (kv_cache_manager.py:519-534, watermark default 0.0,
        config/scheduler.py:197); otherwise the loop breaks (scheduler.py:1226-1232) and later
        requests wait behind it. Admission is also bounded by max_num_seqs (scheduler.py:124, default
        1024 on a >=70 GiB device, arg_utils.py:2870-2878)."""
        while self._wait:
            rid, key, n, sh, robot, t_sub = self._wait[0]
            cand = t_sub if (self.prefill_s is None or not self.admission) else max(t_sub, self._server_free)
            if cand > now:
                return
            nb = n // BLOCK
            if sh is not None and max(int(sh), 0) // BLOCK < nb:
                self._orphan(key, max(int(sh), 0) // BLOCK)
            h = self._hit_blocks(key, min(nb, max(n - 1, 0) // BLOCK))   # kv_cache_manager.py:295
            if sh is not None:
                h = min(h, max(int(sh), 0) // BLOCK)
            total = -(-n // BLOCK)
            hit_pinned = sum(1 for i in range(h) if (key, i) in self._pin)
            need = total - hit_pinned
            if not self.admission:
                pass
            elif len(self._req) >= self.max_num_seqs:
                self._kv_block = True
                return
            elif need > self.gpu_cap - len(self._pin) - self._partial and (self._pin or self._partial):
                self._kv_block = True
                return
            if self.admission and need > self.gpu_cap - len(self._pin) - self._partial:
                self.stats["pb_pinned_overshoot"] += 1
            self._wait.pop(0)
            self._start(rid, key, n, nb, h, robot)
            if self.prefill_s is not None:
                start = max(cand, self._last_event) if self._kv_block else cand
                self._server_free = start + max(n - h * BLOCK, 0) * self.prefill_s
            self._kv_block = False

    def _start(self, rid, key, n, nb, h, robot) -> None:
        self._last_nb[key] = nb
        g = 0
        if self.host_engine:
            while g < h and ((key, g) in self._pin or (key, g) in self._free):
                g += 1
        for i in range(h - 1, -1, -1):
            b = (key, i)
            if b in self._pin:
                self._pin[b] += 1
            else:
                if b in self._free:
                    del self._free[b]
                else:
                    self._alloc_gpu()
                self._pin[b] = 1
            if b in self._host and not self.host_engine:
                self._host.move_to_end(b)
        if self.host_engine:
            hl = list(range(g, h))
            store = robot or not self.offload_controls
            for i in range(nb - 1, h - 1, -1):
                b = (key, i)
                self._alloc_gpu()
                self._pin[b] = 1
            first = h if hl else 0
            offer = [(key, i) for i in range(first, nb)] if store else []
            self._protect = set(offer)
            for b in offer:
                self._host_put(b)
            self._protect = set()
            self._touch[rid] = [(key, i) for i in hl if (key, i) not in set(offer)] + offer
        else:
          for i in range(nb - 1, h - 1, -1):
            b = (key, i)
            self._alloc_gpu()
            self._pin[b] = 1
            if robot or not self.offload_controls:
                self._host_put(b)
        part = (-(-n // BLOCK)) - nb
        if part:
            self._alloc_gpu()
            self._partial += part
        self._req[rid] = (key, nb, h, part)
        self._rob[rid] = bool(robot)

    def observe_send(self, rid: str, key: Hashable, prompt_tokens: int, now: float = 0.0,
                     shared_tokens: Optional[int] = None, robot: bool = True) -> int:
        """Record a send. The request joins the shadow's WAITING queue and starts holding blocks only
        when the scheduler rule in `_admit` admits it. Returns the hit token count at admission, or 0
        while it waits."""
        self.stats["pb_sends_observed"] += 1
        self._last_event = float(now)
        self._wait.append((rid, key, int(prompt_tokens), shared_tokens, robot, float(now)))
        self._admit(float(now))
        rec = self._req.get(rid)
        return rec[2] * BLOCK if rec else 0

    def observe_completion(self, rid: str, cached_tokens: Optional[int], now: float = 0.0,
                           prompt_tokens: Optional[int] = None) -> None:
        self._last_event = float(now)
        self._admit(float(now))
        """Unpin the request's blocks into the free queue (tail first); RESYNC from the engine's own
        cached_tokens. A request that completed while the shadow still queued it means the shadow was
        behind the engine: it is run to completion at once (`pb_queue_stale`)."""
        for j, w in enumerate(self._wait):
            if w[0] == rid:
                self._wait.pop(j)
                self.stats["pb_queue_stale"] += 1
                _, key, n, sh, robot, _t = w
                nb = n // BLOCK
                self._start(rid, key, n, nb, self._hit_blocks(key, min(nb, max(n - 1, 0) // BLOCK)), robot)
                break
        rec = self._req.pop(rid, None)
        if rec is None:
            return
        key, nb, h, part = rec
        self._partial -= part
        er = self.engine_resync
        robot = self._rob.pop(rid, True)
        cap = nb
        if er:
            # ENGINE RULES at completion (switch `live2_pb_engine_resync`, default OFF): the engine
            # holds only the blocks of the prompt it actually served (usage.prompt_tokens, not the
            # coordinator's estimate), and its host tier stores only blocks of requests the per-request
            # offload control allows (robot; dashcam and assistive send max_offload_tokens 0).
            if prompt_tokens is not None:
                cap = min(nb, max(int(prompt_tokens), 0) // BLOCK)
                self._last_nb[key] = cap
            if cached_tokens is not None:
                ch = int(cached_tokens) // BLOCK
                if ch != h:
                    self.stats["pb_resyncs"] += 1
                    if ch < h:
                        self.stats["pb_resync_changed"] += 1
                        store = robot or not self.offload_controls
                        for i in range(ch, min(h, cap)):
                            self._host.pop((key, i), None)
                            if store:
                                self._host_put((key, i))
        elif cached_tokens is not None:
            ch = int(cached_tokens) // BLOCK
            if ch != h:
                self.stats["pb_resyncs"] += 1
                if ch < h:
                    self.stats["pb_resync_changed"] += 1
                    for i in range(ch, h):
                        self._host.pop((key, i), None)
                    for i in range(ch, h):
                        self._host_put((key, i))
        if self.host_engine:
            tk = self._touch.pop(rid, [])
            if er and cached_tokens is not None and int(cached_tokens) // BLOCK < h:
                tk = tk + [(key, i) for i in range(int(cached_tokens) // BLOCK, min(h, cap))]
            seen = set()
            tk = [b for b in sorted(set(tk), key=lambda b: b[1])]
            for b in reversed(tk):
                if b in self._host:
                    self._host.move_to_end(b)
        for i in range(nb - 1, -1, -1):
            b = (key, i)
            c = self._pin.get(b)
            if c is None:
                continue
            if c > 1:
                self._pin[b] = c - 1
            else:
                del self._pin[b]
                if er and i >= cap:
                    self._host.pop(b, None)
                    continue
                self._free[b] = None
                self._free.move_to_end(b)
        self._admit(float(now))


def shared_prefix_tokens(prev_uuids: Any, prev_tokens: int, uuids: Any) -> int:
    """Tokens of this prompt that equal the previous prompt under the same key, from what the
    coordinator itself presents: the leading frame uuids in common, at the previous prompt's own
    tokens-per-frame. Known pre-send; reads nothing the engine returns."""
    if not prev_uuids:
        return 0
    cp, m = 0, min(len(prev_uuids), len(uuids))
    while cp < m and prev_uuids[cp] == uuids[cp]:
        cp += 1
    return int(cp * int(prev_tokens) / max(len(prev_uuids), 1))
