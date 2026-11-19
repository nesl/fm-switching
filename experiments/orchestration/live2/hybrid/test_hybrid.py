#!/usr/bin/env python3
"""Hybrid (D138) proofs on DRY runs (no server):
  1. BASE == b7-edf-feasibility: decision logs byte-identical except the arm name and timing fields,
     on several seeds and sizes.
  2. MOVE PROOF (CLAUDE.md Step 2b): each switch configuration vs the base on one cell: number of differing
     decisions and the first one. A configuration with ZERO differing decisions is an ABSENT LINK.
Usage: python test_hybrid.py identity | moves   (writes results/orchestration/live2/hybrid/*.json)"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE2 = HERE.parent
REPO = LIVE2.parents[2]
for p in (LIVE2, LIVE2 / "fleet", LIVE2 / "tests", REPO / "experiments/orchestration/baselines",
          REPO / "experiments/orchestration/sim", REPO / "experiments/lib"):
    sys.path.insert(0, str(p))
OUT = REPO / "results/orchestration/live2/hybrid"
STRIP = ("arm", "decision_latency_ms", "decision_id")


def dry(arm_name, seed, n, run_s=120.0):
    import arms as A
    import cachekeys as CK
    import cstate as CS
    import emulator as EM
    import hybrid  # noqa: F401
    import trace as TR
    from bridge import EmulatorBridge
    from coordinator import Live2Coordinator, Logs
    from test_live2_coord import GPU_KV, HOST_GIB, HOST_TOK
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        TR.write_trace(d / "t", TR.generate_trace(seed, n, "50:50", run_s, "A"))
        arm = A.make_arm(arm_name)
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB, host_tier_tokens=HOST_TOK,
                            targets=CS.TARGETS)
        logs = Logs(d / "r").open()
        co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                              host_tier_tokens=HOST_TOK, upload_mode="A", window_s=run_s, drain_s=5.0,
                              seed=seed, logs=logs, run_tag=CK.run_tag(seed, "x"), dry_run=True)
        br = EmulatorBridge(co)
        br.kind = "stub"
        EM.FleetEmulator(d / "t", br, "A", realtime=False, drain_s=5.0).run(d / "r")
        logs.close()
        rows = [json.loads(l) for l in open(d / "r" / "decision.jsonl")]
    return [{k: v for k, v in r.items() if k not in STRIP} for r in rows], getattr(arm, "stats", None)


def identity():
    out = []
    for seed, n in ((0, 8), (0, 12), (4, 10), (5, 16)):
        a, _ = dry("hybrid-base", seed, n)
        b, _ = dry("b7-edf-feasibility", seed, n)
        same = a == b
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
        out.append(dict(seed=seed, n=n, decisions=len(a), b7_decisions=len(b), identical=same, first_diff=first))
        print(out[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hybrid_identity.json").write_text(json.dumps(out, indent=1) + "\n")
    if not all(x["identical"] for x in out):
        raise SystemExit("BASE IS NOT byte-identical to b7")


def moves(seed=0, n=12):
    import hybrid
    base, _ = dry("hybrid-base", seed, n)
    out = []
    for name in hybrid.CONFIGS:
        if name == "hybrid-base":
            continue
        rows, stats = dry(name, seed, n)
        diff = sum(1 for x, y in zip(base, rows) if x != y) + abs(len(base) - len(rows))
        first = next(((i, base[i], rows[i]) for i, (x, y) in enumerate(zip(base, rows)) if x != y), None)
        out.append(dict(config=name, seed=seed, n=n, base_decisions=len(base), decisions=len(rows),
                        differing=diff, absent_link=(diff == 0), stats=dict(stats or {}),
                        first_diff=(dict(index=first[0], base=first[1], cfg=first[2]) if first else None)))
        print(name, "differing", diff, "stats", dict(stats or {}), flush=True)
    (OUT / "hybrid_moves.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


def pairs(seed=0, n=12):
    """Step 2b on the comparisons the screening actually makes: each component against its neighbour."""
    P = [("C1 under the cap", "hybrid-c5", "hybrid-c1c5"),
         ("k_r 1.0 vs 2.0", "hybrid-c1c2k1", "hybrid-c1c2k2"),
         ("C3 (k_r 1.0)", "hybrid-c1c2k1", "hybrid-c1c2k1c3"),
         ("C3 (k_r 2.0)", "hybrid-c1c2k2", "hybrid-c1c2k2c3"),
         ("C2 (vs C1)", "hybrid-c1", "hybrid-c1c2k1")]
    cache, out = {}, []
    for label, a, b in P:
        for x in (a, b):
            if x not in cache:
                cache[x] = dry(x, seed, n)
        ra, rb = cache[a][0], cache[b][0]
        diff = sum(1 for x, y in zip(ra, rb) if x != y) + abs(len(ra) - len(rb))
        out.append(dict(comparison=label, a=a, b=b, differing=diff, absent_link=(diff == 0),
                        stats_b=dict(cache[b][1] or {})))
        print(label, a, "vs", b, "differing", diff, dict(cache[b][1] or {}), flush=True)
    (OUT / "hybrid_pairs.json").write_text(json.dumps(out, indent=1, default=str) + "\n")


if __name__ == "__main__":
    {"identity": identity, "moves": moves, "pairs": pairs}[sys.argv[1]]()
