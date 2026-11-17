"""D56 (user decision, 2026-11-16): three tiers per history, both warm tiers BOUNDED, and
evidence is never deleted.

    GPU-warm    KV blocks in the engine's GPU KV pool. Size is an INPUT (a parameter), not the
                H100's number: 62,944 tokens is what StudyENG1 and StudyENG1b measured on
                h100nvl, and it is supplied as a parameter so a different deployment is a
                different parameter and not a different code path.
    host-warm   KV blocks caught by the offloading connector. Size is an INPUT and is BOUNDED,
                which is the part D56 changes: POL2 treated the host as unbounded and P_host as
                the constant 0.0.
    cold        the raw frames. Always available, because EVIDENCE IS NEVER DELETED. "Drop" in
                the memory decision means DEMOTE TO COLD, and a cold history is rebuilt by
                prefill at the committed cold rate.

P_host IS NOW A FUNCTION OF HOST OCCUPANCY (D56), not a constant. StudyENG1b measured the
numerator: on the KV-HOST server 853,936 of 854,898 evicted prefix tokens came back as external
(host) hits, P_host = 0.999, because the connector writes every built block through to host as it
is computed. That measurement was taken with 256 GiB of host offload and one prefix in flight,
i.e. WITH ROOM. It says nothing about a FULL host tier, so when the host has no room for the
evicted blocks this module falls back to the host eviction rule and reports the fraction the rule
would keep.

ONE CONSEQUENCE OF THAT RULE, STATED RATHER THAN DISCOVERED LATER. Freshly evicted GPU blocks are
the most recently used, so under LRU a FULL host tier admits them and demotes its INCUMBENTS to
cold. P_host for the blocks being evicted therefore stays at the measured 0.999 even at full
occupancy, the result is flagged `measured: false` because the rule and not a measurement decided
it, and the cost of the full tier appears as other prefixes' tokens in `TieredStore.cold_tokens`.
P_host falls below the measured value only when the evicted blocks do not fit the host tier at
all. A different eviction rule moves that cost somewhere else, which is why the rule is a
pluggable argument and why StudyENG1c matters.

THE HOST EVICTION RULE IS AN ASSUMPTION. vLLM 0.31.0's native offloading backend was not measured
for its eviction order: StudyENG1 Part D found that eviction counters exist only as sampled
lifetime and idle histograms and that no counter reports cached-but-unreferenced blocks. The
default here is LRU and it is labelled ASSUMPTION in `HostPool.eviction_rule_status` and in the
report, until StudyENG1c measures it. The rule is a pluggable callable so the measured rule
replaces one argument.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# StudyENG1b section 5, KV-HOST: 853,936 of 854,898 evicted prefix tokens returned as external
# (host) hits over 103 trials with eviction. Measured WITH room on the host tier.
P_HOST_WITH_ROOM = 0.999
P_HOST_WITH_ROOM_SOURCE = ("StudyENG1b section 5: 853,936 / 854,898 evicted prefix tokens "
                           "returned as external host hits on the KV-HOST server (write-through "
                           "connector), measured with room on the host tier")

EVICTION_RULE_ASSUMPTION = (
    "ASSUMPTION, not a measurement: the host tier's eviction order is modelled as LRU. "
    "StudyENG1 Part D found vLLM 0.31.0 exposes eviction only as sampled lifetime and idle "
    "histograms and no counter for cached-but-unreferenced blocks, so the order was never "
    "observed. StudyENG1c is the measurement that replaces this.")


@dataclass
class HostEntry:
    prefix_id: str
    tokens: int
    last_used: float = 0.0
    owner_job: Optional[str] = None
    owner_device: Optional[str] = None
    rep: str = "RICH"


HostEvictionRule = Callable[[Sequence[HostEntry]], List[str]]


def lru_rule(entries: Sequence[HostEntry]) -> List[str]:
    """The DEFAULT and an ASSUMPTION: least recently used first. See EVICTION_RULE_ASSUMPTION."""
    return [e.prefix_id for e in sorted(entries, key=lambda e: (e.last_used, e.prefix_id))]


def largest_first_rule(entries: Sequence[HostEntry]) -> List[str]:
    """An alternative the pluggable slot exists for; not a default and not measured."""
    return [e.prefix_id for e in sorted(entries, key=lambda e: (-e.tokens, e.prefix_id))]


@dataclass
class HostPool:
    """The host-warm tier: BOUNDED capacity, pluggable eviction, and nothing is ever deleted.

    `demoted_to_cold` records what left the host tier. It is not a loss of evidence: the raw
    frames remain and the history is rebuildable by prefill, which is exactly what D56 means by
    "evidence is never deleted; drop means demote to cold"."""

    capacity_tokens: int
    entries: Dict[str, HostEntry] = field(default_factory=dict)
    demoted_to_cold: Dict[str, int] = field(default_factory=dict)
    eviction_rule: HostEvictionRule = lru_rule
    rule_name: str = "lru"
    t: float = 0.0

    def occupancy(self) -> int:
        return sum(e.tokens for e in self.entries.values())

    def free_tokens(self) -> int:
        return max(self.capacity_tokens - self.occupancy(), 0)

    def occupancy_fraction(self) -> float:
        return (self.occupancy() / self.capacity_tokens) if self.capacity_tokens > 0 else 1.0

    def has_room_for(self, tokens: int) -> bool:
        return self.free_tokens() >= max(int(tokens), 0)

    def eviction_rule_status(self) -> str:
        return EVICTION_RULE_ASSUMPTION

    def accept(self, prefix_id: str, tokens: int, t: float, owner_job: Optional[str] = None,
               owner_device: Optional[str] = None, rep: str = "RICH") -> Dict[str, Any]:
        """Take `tokens` of a prefix into the host tier, evicting by the rule if needed.

        Returns what was accepted, what the rule demoted to cold to make room, and the fraction
        of the offered tokens that the host tier actually holds afterwards. That fraction is what
        P_host means for THIS demotion."""
        tokens = max(int(tokens), 0)
        self.t = max(self.t, t)
        if tokens == 0:
            return dict(accepted_tokens=0, offered_tokens=0, fraction_kept=1.0, evicted={},
                        rule=self.rule_name)
        evicted: Dict[str, int] = {}
        need = tokens - self.free_tokens()
        if need > 0:
            for pid in self.eviction_rule(list(self.entries.values())):
                if need <= 0:
                    break
                if pid == prefix_id:
                    continue
                e = self.entries[pid]
                take = min(e.tokens, need)
                e.tokens -= take
                need -= take
                evicted[pid] = evicted.get(pid, 0) + take
                self.demoted_to_cold[pid] = self.demoted_to_cold.get(pid, 0) + take
                if e.tokens <= 0:
                    del self.entries[pid]
        accepted = min(tokens, self.free_tokens())
        if accepted > 0:
            e = self.entries.get(prefix_id)
            if e is None:
                e = HostEntry(prefix_id, 0, t, owner_job, owner_device, rep)
                self.entries[prefix_id] = e
            e.tokens += accepted
            e.last_used = t
        return dict(accepted_tokens=int(accepted), offered_tokens=int(tokens),
                    fraction_kept=float(accepted) / float(tokens), evicted=evicted,
                    rule=self.rule_name, rule_status=self.eviction_rule_status())

    def reference(self, prefix_id: str, t: float) -> None:
        e = self.entries.get(prefix_id)
        if e is not None:
            e.last_used = t
        self.t = max(self.t, t)

    def tokens_of(self, prefix_id: str) -> int:
        e = self.entries.get(prefix_id)
        return int(e.tokens) if e is not None else 0

    def clone(self) -> "HostPool":
        return HostPool(capacity_tokens=self.capacity_tokens,
                        entries={k: HostEntry(v.prefix_id, v.tokens, v.last_used, v.owner_job,
                                              v.owner_device, v.rep)
                                 for k, v in self.entries.items()},
                        demoted_to_cold=dict(self.demoted_to_cold),
                        eviction_rule=self.eviction_rule, rule_name=self.rule_name, t=self.t)

    def describe(self) -> Dict[str, Any]:
        return dict(capacity_tokens=self.capacity_tokens, occupancy_tokens=self.occupancy(),
                    occupancy_fraction=self.occupancy_fraction(), n_prefixes=len(self.entries),
                    rule=self.rule_name, rule_status=self.eviction_rule_status(),
                    demoted_to_cold=dict(self.demoted_to_cold))


def p_host_from_occupancy(host: Optional[HostPool], evicted_tokens: int,
                          prefix_id: Optional[str] = None, t: float = 0.0) -> Dict[str, Any]:
    """D56: P_host is a FUNCTION OF HOST OCCUPANCY, not a constant.

    With room for the evicted blocks, P_host is StudyENG1b's measured 0.999. Without room, the
    host eviction rule decides how much survives, so P_host is the fraction the rule keeps, and
    that fraction carries the rule's ASSUMPTION label with it. With no host tier at all (the E0
    server of StudyENG1b) P_host is 0 by construction, which is the measurement on E0.
    """
    ev = max(int(evicted_tokens), 0)
    if host is None or host.capacity_tokens <= 0:
        return dict(p_host=0.0, basis="no host tier is configured, so evicted blocks are "
                                     "recomputed; this is StudyENG1b's E0 server by "
                                     "construction",
                    host_occupancy_fraction=None, measured=True,
                    source="StudyENG1b section 5, E0: every evicted token was recomputed")
    if ev == 0:
        return dict(p_host=P_HOST_WITH_ROOM, basis="nothing is evicted",
                    host_occupancy_fraction=host.occupancy_fraction(), measured=True,
                    source=P_HOST_WITH_ROOM_SOURCE)
    if host.has_room_for(ev):
        return dict(p_host=P_HOST_WITH_ROOM,
                    basis="the host tier has room for the evicted blocks, so the write-through "
                          "connector's measured recovery applies",
                    host_occupancy_fraction=host.occupancy_fraction(), measured=True,
                    source=P_HOST_WITH_ROOM_SOURCE)
    shadow = host.clone()
    res = shadow.accept(prefix_id or "evicted", ev, t)
    kept = res["fraction_kept"]
    return dict(p_host=float(P_HOST_WITH_ROOM * kept),
                basis="the host tier is FULL, so the eviction rule decides what survives: the "
                      "rule keeps %.3f of the evicted blocks and the measured recovery applies "
                      "to that part only" % kept,
                host_occupancy_fraction=host.occupancy_fraction(), fraction_kept=float(kept),
                measured=False, rule=host.rule_name, rule_status=host.eviction_rule_status(),
                source=P_HOST_WITH_ROOM_SOURCE)


@dataclass
class TieredStore:
    """D56's three tiers as one object, so a demotion is one call and cold is never a deletion.

    `gpu` is the `kvpool.KVPool` the rollout already tracks (A6.2); this adds the bounded host
    tier beneath it and the cold tier beneath that. A token that leaves the GPU is offered to the
    host; what the host cannot take becomes cold, and cold is ALWAYS available."""

    gpu: Any
    host: Optional[HostPool] = None
    cold_tokens: Dict[str, int] = field(default_factory=dict)

    def demote_from_gpu(self, freed: Dict[str, int], t: float) -> Dict[str, Any]:
        """Route blocks the GPU pool freed into the host tier, and whatever the host cannot hold
        into cold. Returns a per-prefix split, which is what A6.1's P_host multiplies."""
        out: Dict[str, Any] = {}
        for pid, tok in sorted(freed.items()):
            res = p_host_from_occupancy(self.host, tok, prefix_id=pid, t=t)
            to_host = 0
            if self.host is not None and self.host.capacity_tokens > 0:
                acc = self.host.accept(pid, tok, t)
                to_host = int(acc["accepted_tokens"])
            to_cold = int(tok) - to_host
            if to_cold > 0:
                self.cold_tokens[pid] = self.cold_tokens.get(pid, 0) + to_cold
            out[pid] = dict(tokens=int(tok), to_host=to_host, to_cold=to_cold,
                            p_host=res["p_host"], p_host_basis=res["basis"])
        return out

    def tier_of(self, prefix_id: str) -> str:
        e = getattr(self.gpu, "entries", {}).get(prefix_id)
        if e is not None and e.tokens > 0:
            return "GPU"
        if self.host is not None and self.host.tokens_of(prefix_id) > 0:
            return "HOST"
        return "STORED"

    def describe(self) -> Dict[str, Any]:
        """The GPU pool's own keys stay at the TOP LEVEL, because every reader of the rollout's
        `kv` field before D56 read them there and a silent rename is how a reader starts reading
        a different quantity. The two tiers beneath it are added, not substituted."""
        gpu = self.gpu.describe() if self.gpu is not None else {}
        out: Dict[str, Any] = dict(gpu)
        out.update(gpu=gpu, host=self.host.describe() if self.host is not None else None,
                   cold_tokens=dict(self.cold_tokens),
                   note="evidence is never deleted (D56): a prefix that leaves both warm tiers "
                        "is COLD and is rebuilt by prefill, it is not lost")
        return out
