#!/usr/bin/env python3
"""Toy test for the CoVStream reconstruction. CPU only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from covstream import (answer_cost_s, bandwidth_ratio, cloud_ingest, edge_encode,  # noqa
                       standing_cost_s)

res = []
N = 600                      # 10 minutes at 1 frame/s
RAW_PER_FRAME = 354902       # StudyD4's measured PNG request bytes
pk = edge_encode(N, feature_bytes=4000, caption_bytes=400, edge_cost_s_per_frame=0.01)
st = cloud_ingest(pk, graph_cost_s_per_packet=0.002)
ratio = bandwidth_ratio(st, N * RAW_PER_FRAME)
res.append(("Abstract: the edge-cloud split cuts bandwidth far below raw upload",
            ratio < 0.2, f"bandwidth ratio {ratio:.4f} ({ratio*100:.2f} % of raw upload)"))
res.append(("S: the edge encodes EVERY frame, whether or not a query arrives",
            len(pk) == N and st.packets == N, f"{len(pk)} packets encoded and ingested"))
sc = standing_cost_s(pk, st)
res.append(("Addendum rule 3: the construction compute is CHARGED and is non-zero with no query",
            sc > 0, f"standing cost {sc:.2f} s for {N} frames "
                    f"({sum(p.edge_cost_s for p in pk):.2f} s edge + {st.graph_cost_s:.2f} s cloud)"))
res.append(("S: answering runs the heavy model over the maintained structure and uploads nothing",
            answer_cost_s(st, heavy_model_s=2.17) == 2.17,
            "answer cost is the heavy model alone"))
pk2 = edge_encode(N, 40000, 400, 0.01)
res.append(("S: a richer edge representation costs more bandwidth, monotonically",
            bandwidth_ratio(cloud_ingest(pk2, 0.002), N * RAW_PER_FRAME) > ratio,
            f"10x feature bytes -> ratio "
            f"{bandwidth_ratio(cloud_ingest(pk2, 0.002), N*RAW_PER_FRAME):.4f} > {ratio:.4f}"))
res.append(("S: the standing cost scales with the stream length, not the query count",
            standing_cost_s(edge_encode(2 * N, 4000, 400, 0.01),
                            cloud_ingest(edge_encode(2 * N, 4000, 400, 0.01), 0.002)) > sc,
            "twice the frames costs more than once"))

print("CoVStream reconstruction - toy test")
print("=" * 78)
n = sum(int(o) for _, o, _ in res)
for nm, o, d in res:
    print(f"[{'PASS' if o else 'FAIL'}] {nm}\n        {d}")
print("=" * 78)
print(f"{n}/{len(res)} behaviours reproduced")
sys.exit(0 if n == len(res) else 1)
