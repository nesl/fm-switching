"""StudyPOL5-engine Part 3: the controller's residency belief, from StudyRES1's measured rule.

WHAT THIS REPLACES. `tiers.p_host_from_occupancy` decides residency from host OCCUPANCY and an
explicitly labelled ASSUMPTION about the eviction order (`tiers.EVICTION_RULE_ASSUMPTION`: "the
host tier's eviction order is modelled as LRU ... StudyENG1c is the measurement that replaces
this"). StudyENG1c measured it and StudyRES1 tested a bookkeeping model of it: 4-class tier
accuracy **0.9946** on 2,573 StudyENG1c requests whose tier is measured, 0.9936 to 1.0000 in every
cap, with no confusion at all between GPU-warm and host-warm. This module is that model, wired in
as the belief.

WHAT RES1 SAID ABOUT WHICH RULE TO USE. R2 FAILED: the identified rule and plain LRU-by-any-access
disagree on 2 of 2,573 requests, a difference of 0.0004 with a CI touching zero. The user's ruling
is to use the RES1 rule as implemented, which is what `residency.ResidencyModel(policy="rule")`
is; LRU-by-any-access is available behind the same flag and is, on this evidence, as good.

THE BOUNDARY RULE, AND WHY A BELIEF SPLIT RATHER THAN A POINT PREDICTION. RES1 section 8: the one
quantity its bookkeeping should not be trusted for is HOW MUCH of a history survives when the
write volume sits within a couple of per cent of the cap. In its R3 cell a median error of 3,064
tokens in cumulative write accounting, **1.37 % of the 245,760-token cap at 60 GiB**, became a
0.29 error in the surviving fraction. So inside a margin of the cap this module reports a SPLIT
belief (part host-warm, part cold) instead of a point answer, and says so in `basis`.

THE MARGIN AND ITS SOURCES (`boundary_margin_tokens`):
  - RES1's median accounting error, 3,064 tokens, which is 1.37 % of the cap it was measured at
    (`reports/study_res1_residency.md` section 3.2);
  - plus RES1's identified block-rounding component, 816 tokens over the same window, which is
    the part this module FIXES below and therefore no longer contributes to its own error, kept
    in the margin because the fix is untested (same section).
The margin is expressed as a FRACTION of the cap, so a different cap is a different margin and
not a different code path.

THE BLOCK-ROUNDING FIX, DISCLOSED. The engine caches whole 16-token blocks and does not store a
trailing partial block; RES1's model charged the ceiling, which was 816 tokens of its 3,064-token
median gap. `blocks_written` here charges the FLOOR. **StudyRES1 is NOT re-scored on its TEST set
with this fix**, because that would be fitting on TEST; the fix is recorded as pre-registerable
for a later row, and until then it is why the block-rounding term stays inside the margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .residency import TOKENS_PER_BLOCK, ResidencyModel, host_tokens_for_cap, n_chunks

# StudyRES1 section 3.2, measured in its 60 GiB occupancy-0.5 cell.
RES1_ACCOUNTING_ERROR_TOKENS = 3064
RES1_ACCOUNTING_ERROR_CAP_TOKENS = 245760
RES1_BLOCK_ROUNDING_TOKENS = 816
BOUNDARY_MARGIN_FRACTION = ((RES1_ACCOUNTING_ERROR_TOKENS + RES1_BLOCK_ROUNDING_TOKENS)
                            / float(RES1_ACCOUNTING_ERROR_CAP_TOKENS))

MARGIN_SOURCE = (
    "StudyRES1 section 3.2: the model's cumulative write accounting is off by a median of 3,064 "
    "tokens, 1.37 per cent of the 245,760-token cap at 60 GiB, of which 816 tokens is block "
    "rounding (the engine stores whole blocks; RES1 charged the ceiling). The margin is their "
    "sum as a fraction of the cap, %.4f, so a different cap scales it rather than changing the "
    "rule." % BOUNDARY_MARGIN_FRACTION)

BLOCK_ROUNDING_FIX = (
    "DISCLOSED CHANGE: this module charges the FLOOR of tokens / 16 blocks, because the engine "
    "does not store a trailing partial block. StudyRES1 charged the ceiling. RES1 is NOT "
    "re-scored on its TEST set with the fix, which would be fitting on TEST; the fix is "
    "pre-registerable for a later row, and until it is tested its 816 tokens stay inside the "
    "boundary margin.")


def blocks_written(tokens: int) -> int:
    """The blocks a request actually leaves behind: whole blocks only (the fix above)."""
    return max(int(tokens), 0) // TOKENS_PER_BLOCK


def boundary_margin_tokens(cap_tokens: int) -> int:
    return int(round(max(int(cap_tokens), 0) * BOUNDARY_MARGIN_FRACTION))


@dataclass
class ResidencyBelief:
    """The belief, with the same entry point the controller already calls.

    `p_host_for(host_pool, evicted_tokens, prefix_id, t)` returns the dict shape
    `Params.p_host_for` returns, plus the split and the boundary fields, so a caller that reads
    only `p_host` and `basis` keeps working."""

    cap_gib: float
    gpu_pool_tokens: int = 0
    policy: str = "rule"
    model: Optional[ResidencyModel] = None
    written_since_refresh: Dict[str, int] = field(default_factory=dict)
    history_tokens: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.model is None:
            kw = dict(cap_gib=self.cap_gib, policy=self.policy)
            if self.gpu_pool_tokens > 0:
                kw["gpu_pool_tokens"] = self.gpu_pool_tokens
            self.model = ResidencyModel(**kw)

    # ------------------------------------------------------------- bookkeeping
    def note_build(self, prefix_id: str, tokens: int) -> None:
        """A history was built or refreshed: its own clock restarts and everything else ages."""
        self.history_tokens[prefix_id] = max(int(tokens), 0)
        self.written_since_refresh[prefix_id] = 0
        self.note_write(blocks_written(tokens) * TOKENS_PER_BLOCK, exclude=prefix_id)

    def note_refresh(self, prefix_id: str) -> None:
        self.written_since_refresh[prefix_id] = 0

    def note_write(self, tokens: int, exclude: Optional[str] = None) -> None:
        """Other work written through to both tiers, which is what ages every history."""
        add = blocks_written(tokens) * TOKENS_PER_BLOCK
        if add <= 0:
            return
        for pid in self.written_since_refresh:
            if pid != exclude:
                self.written_since_refresh[pid] += add

    # ------------------------------------------------------------- the belief
    def host_capacity_tokens(self) -> int:
        return host_tokens_for_cap(self.cap_gib)

    def belief(self, prefix_id: str, written_since_refresh: Optional[int] = None,
               cap_tokens: Optional[int] = None) -> Dict[str, Any]:
        """StudyENG1c implication 1, with StudyRES1's boundary caveat: a history is host-warm
        while the tokens written since its last refresh are below the cap, and the belief SPLITS
        inside the margin rather than committing to one side."""
        cap = int(cap_tokens if cap_tokens is not None else self.host_capacity_tokens())
        written = int(written_since_refresh if written_since_refresh is not None
                      else self.written_since_refresh.get(prefix_id, 0))
        margin = boundary_margin_tokens(cap)
        if cap <= 0:
            return dict(p_host=0.0, p_cold=1.0, boundary=False, written_since_refresh=written,
                        cap_tokens=cap, margin_tokens=margin, measured=True,
                        basis="no host tier is configured, so nothing survives eviction",
                        source=MARGIN_SOURCE, rule=self.policy)
        if written <= cap - margin:
            return dict(p_host=1.0, p_cold=0.0, boundary=False, written_since_refresh=written,
                        cap_tokens=cap, margin_tokens=margin, measured=True,
                        basis="tokens written since the history's last refresh are below the "
                              "host cap by more than the boundary margin, so StudyENG1c's rule "
                              "keeps it",
                        source=MARGIN_SOURCE, rule=self.policy)
        if written >= cap + margin:
            return dict(p_host=0.0, p_cold=1.0, boundary=False, written_since_refresh=written,
                        cap_tokens=cap, margin_tokens=margin, measured=True,
                        basis="more than the host cap has been written since the history's last "
                              "refresh, by more than the boundary margin, so it is gone",
                        source=MARGIN_SOURCE, rule=self.policy)
        span = max(2 * margin, 1)
        p_host = max(0.0, min(1.0, ((cap + margin) - written) / float(span)))
        return dict(p_host=p_host, p_cold=1.0 - p_host, boundary=True,
                    written_since_refresh=written, cap_tokens=cap, margin_tokens=margin,
                    measured=False,
                    basis="POSSIBLY COLD: the write volume is within the boundary margin of the "
                          "cap, where StudyRES1 measured that its own accounting error (1.37 per "
                          "cent of the cap) becomes a 0.29 error in the surviving fraction, so "
                          "the belief is SPLIT rather than a point prediction",
                    source=MARGIN_SOURCE, rule=self.policy)

    # ------------------------------------------- drop-in for Params.p_host_for
    def p_host_for(self, host_pool: Any = None, evicted_tokens: int = 0,
                   prefix_id: Optional[str] = None, t: float = 0.0) -> Dict[str, Any]:
        """Same signature and the same keys the controller already reads, so this replaces
        `Params.p_host_for` without any frozen file changing.

        `evicted_tokens` is what the caller expects to lose from GPU; the belief is about where
        those tokens go. When the caller has not fed this object its write stream, the host
        pool's own occupancy stands in for it, which is stated in `basis`."""
        pid = prefix_id or "unknown"
        cap = (int(getattr(host_pool, "capacity_tokens", 0) or 0) if host_pool is not None
               else self.host_capacity_tokens())
        if host_pool is not None and cap <= 0:
            out = self.belief(pid, written_since_refresh=0, cap_tokens=0)
            out["evicted_tokens"] = int(evicted_tokens)
            return out
        tracked = pid in self.written_since_refresh
        written = (self.written_since_refresh.get(pid, 0) if tracked
                   else int(getattr(host_pool, "used_tokens", lambda: 0)()
                            if callable(getattr(host_pool, "used_tokens", None))
                            else getattr(host_pool, "used_tokens", 0) or 0))
        out = self.belief(pid, written_since_refresh=written, cap_tokens=cap)
        out["evicted_tokens"] = int(evicted_tokens)
        out["write_stream_tracked"] = bool(tracked)
        if not tracked:
            out["basis"] = (out["basis"] + "; the write stream was not fed to the belief, so the "
                            "host pool's own occupancy stood in for it")
            out["measured"] = False
        out["host_occupancy_fraction"] = (host_pool.occupancy_fraction()
                                          if hasattr(host_pool, "occupancy_fraction") else None)
        out["replaces"] = ("tiers.p_host_from_occupancy and its EVICTION_RULE_ASSUMPTION, which "
                           "StudyENG1c measured and StudyRES1 tested at 0.9946 four-class "
                           "accuracy")
        out["block_rounding"] = BLOCK_ROUNDING_FIX
        return out
