#!/usr/bin/env python3
"""Toy test for the KVFlow reconstruction. CPU only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kvflow import KVNode, evict, exposed_prefetch_s, prefetch, steps_to_execution  # noqa

res = []
order = ["c", "a", "b", "a"]
res.append(("S: steps-to-execution is read off the workflow order",
            steps_to_execution(order, 0, "c") == 0 and steps_to_execution(order, 0, "b") == 2
            and steps_to_execution(order, 0, "z") == float("inf"),
            "c=0, b=2, absent=inf"))

# The paper's point: 'a' was used long ago (LRU would evict it) but runs NEXT, so KVFlow keeps it.
nodes = [KVNode("a", 1000, True, steps_to_execution=1.0),    # about to run, stale by recency
         KVNode("b", 1000, True, steps_to_execution=50.0)]   # fresh by recency, far from reuse
after = {n.node_id: n.resident for n in evict(nodes, capacity_tokens=1000)}
res.append(("S: eviction keeps the node about to execute and drops the far one - the named "
            "departure from LRU",
            after["a"] and not after["b"], f"resident after eviction: {after}"))
res.append(("S: eviction runs until the tier fits",
            sum(n.tokens for n in evict(nodes, 1000) if n.resident) <= 1000,
            "footprint within capacity"))
cold = [KVNode("x", 500, False, 1.0), KVNode("y", 500, False, 30.0), KVNode("z", 500, False, 3.0)]
res.append(("S: prefetch takes the nodes nearest to execution, within the horizon and the slots",
            prefetch(cold, horizon_steps=5.0, slots=2) == ["x", "z"],
            f"prefetched {prefetch(cold, 5.0, 2)}"))
res.append(("S: fully overlapped prefetching exposes only what the overlap cannot hide",
            exposed_prefetch_s(1.0, 0.4) == 0.6 and exposed_prefetch_s(1.0, 2.0) == 0.0,
            "1.0 s transfer with 0.4 s / 2.0 s cover -> 0.6 s / 0.0 s"))
res.append(("S: a node with infinite steps-to-execution is evicted first",
            not {n.node_id: n.resident for n in
                 evict([KVNode("p", 1000, True, 2.0), KVNode("q", 1000, True, float("inf"))],
                       1000)}["q"],
            "the never-reused node goes first"))

print("KVFlow reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
