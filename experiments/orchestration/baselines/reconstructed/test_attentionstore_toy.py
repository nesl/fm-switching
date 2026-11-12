#!/usr/bin/env python3
"""Toy test for the AttentionStore / CachedAttention reconstruction. CPU only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attentionstore import (DISK, DRAM, HBM, Session, async_save_exposed_s,  # noqa
                            decoupled_positional_valid, layer_wise_preload_s,
                            scheduler_aware_evict, scheduler_aware_fetch)

res = []

# ---- S4.1 / Fig 6c: when per-layer compute covers per-layer load, only the first layer's load
#      is exposed -- the rest is hidden behind computation.
e = layer_wise_preload_s(n_layers=64, load_total_s=1.0, compute_total_s=2.0, buffer_layers=1)
res.append(("S4.1 / Fig 6c: load hidden behind compute, only the head layer exposed",
            abs(e - 1.0 / 64) < 1e-12, f"exposed {e*1000:.2f} ms of a 1.000 s load"))

# ---- S4.1 / Fig 7a vs 7b: when load outruns compute, a LARGER buffer absorbs more of the
#      deficit, which is the paper's "perfect pre-loading with a customized larger buffer".
e1 = layer_wise_preload_s(64, load_total_s=2.0, compute_total_s=1.0, buffer_layers=1)
e8 = layer_wise_preload_s(64, load_total_s=2.0, compute_total_s=1.0, buffer_layers=8)
e64 = layer_wise_preload_s(64, load_total_s=2.0, compute_total_s=1.0, buffer_layers=64)
res.append(("S4.1 / Fig 7a->7b: a larger buffer reduces exposed load, monotonically",
            e1 > e8 > e64, f"buffer 1/8/64 -> {e1:.3f} / {e8:.3f} / {e64:.3f} s exposed"))

# ---- S4.1: asynchronous saving exposes only the part that cannot overlap.
res.append(("S4.1: async save exposes only the non-overlapped remainder",
            async_save_exposed_s(1.0, 0.4) == 0.6 and async_save_exposed_s(1.0, 2.0) == 0.0,
            "1.0 s save with 0.4 s cover -> 0.6 s; with 2.0 s cover -> 0.0 s"))

# ---- S4.2: scheduler-aware FETCH promotes the head of the scheduler's queue, bounded by slots.
sess = {s: Session(s, 1000, DISK) for s in ("a", "b", "c", "d")}
f = scheduler_aware_fetch(["c", "a", "d", "b"], sess, hbm_slots=2)
res.append(("S4.2: fetch follows the scheduler's queue order, bounded by HBM slots",
            f == ["c", "a"], f"fetched {f}"))

# ---- S4.2: scheduler-aware EVICTION differs from LRU. Here the LRU victim ('a', oldest access)
#      is the one the scheduler will run NEXT, so the paper's policy must keep it and evict the
#      session that is absent from the queue.
sess = {"a": Session("a", 1000, HBM, last_access_s=0.0),
        "b": Session("b", 1000, HBM, last_access_s=9.0)}
ev = scheduler_aware_evict(queue=["a"], sessions=sess, n_evict=1)
lru = min(sess.values(), key=lambda s: s.last_access_s).sid
res.append(("S4.2: eviction by predicted next access, NOT by recency (differs from LRU here)",
            ev == ["b"] and lru == "a", f"scheduler-aware evicts {ev}, LRU would evict ['{lru}']"))

# ---- S4.3: decoupling the positional encoding keeps a cache valid when the prefix shifted.
coupled = decoupled_positional_valid(saved_prefix_tokens=100, current_prefix_tokens=120,
                                     decoupled=False)
decoup = decoupled_positional_valid(saved_prefix_tokens=100, current_prefix_tokens=120,
                                    decoupled=True)
res.append(("S4.3: a shifted prefix invalidates a coupled cache but not a decoupled one",
            (not coupled) and decoup, f"coupled valid = {coupled}, decoupled valid = {decoup}"))

print("AttentionStore / CachedAttention reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
