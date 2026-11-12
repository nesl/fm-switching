#!/usr/bin/env python3
"""Toy test for the Pensieve reconstruction. CPU only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pensieve import CPU, DROPPED, GPU, Chunk, aot_swap_s, chunk_value, evict_to_fit, serve_cost_s  # noqa

res = []

# ---- S4: at equal reuse horizon, the chunk that is EXPENSIVE to recompute is more valuable, so
#      eviction drops the cheap-to-recompute one first.
cheap = Chunk("s", 0, 1000, GPU, recompute_tok_s=20000.0, reuse_horizon_s=10.0)
dear = Chunk("s", 1, 1000, GPU, recompute_tok_s=1000.0, reuse_horizon_s=10.0)
res.append(("S4: value grows with recompute cost, so the cheap chunk is evicted first",
            chunk_value(dear) > chunk_value(cheap),
            f"value dear {chunk_value(dear):.3f} > cheap {chunk_value(cheap):.3f}"))

# ---- S4: value also grows with how long the chunk stays attractive.
short = Chunk("s", 2, 1000, GPU, recompute_tok_s=4500.0, reuse_horizon_s=1.0)
long_ = Chunk("s", 3, 1000, GPU, recompute_tok_s=4500.0, reuse_horizon_s=30.0)
res.append(("S4: value grows with the reuse horizon", chunk_value(long_) > chunk_value(short),
            f"value long {chunk_value(long_):.3f} > short {chunk_value(short):.3f}"))

# ---- S4: eviction runs until the GPU tier fits, and evicts the least valuable chunks.
out = evict_to_fit([cheap, dear, short, long_], gpu_capacity_tokens=2000)
on_gpu = sorted(c.index for c in out if c.tier == GPU)
res.append(("S4: evict least-valuable chunks until the GPU tier fits",
            sum(c.tokens for c in out if c.tier == GPU) <= 2000 and 1 in on_gpu and 3 in on_gpu,
            f"GPU-resident chunk indices {on_gpu} (1 = expensive, 3 = long horizon)"))

# ---- S4: token granularity means a session may be PARTIALLY resident; the dropped part is
#      recomputed and the CPU part is transferred.
chunks = [Chunk("s", 0, 1000, GPU), Chunk("s", 1, 1000, CPU), Chunk("s", 2, 1000, DROPPED)]
cost = serve_cost_s(chunks, cpu_to_gpu_tok_s=100000.0)
only_gpu = serve_cost_s([Chunk("s", 0, 3000, GPU)], cpu_to_gpu_tok_s=100000.0)
res.append(("S4: a partially resident session costs transfer + recompute; fully GPU-resident is free",
            cost > 0 and only_gpu == 0.0, f"mixed {cost:.4f} s vs fully GPU-resident {only_gpu:.4f} s"))

# ---- S4: recompute dominates transfer, which is why the paper prefers swapping to dropping.
drop_only = serve_cost_s([Chunk("s", 0, 1000, DROPPED)], cpu_to_gpu_tok_s=100000.0)
swap_only = serve_cost_s([Chunk("s", 0, 1000, CPU)], cpu_to_gpu_tok_s=100000.0)
res.append(("S4: dropping costs more than swapping for the same tokens",
            drop_only > swap_only, f"drop {drop_only:.4f} s vs swap {swap_only:.4f} s"))

# ---- S4: ahead-of-time pipelined swapping hides transfer behind computation.
res.append(("S4: ahead-of-time pipelined swap hides transfer behind compute",
            aot_swap_s(1.0, 0.4) == 0.6 and aot_swap_s(1.0, 1.5) == 0.0,
            "1.0 s transfer with 0.4 s overlap -> 0.6 s; with 1.5 s -> 0.0 s"))

print("Pensieve reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
