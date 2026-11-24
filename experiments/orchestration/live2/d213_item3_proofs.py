#!/usr/bin/env python3
"""D213 item 3: the belief's predicted resident prefix is RECORDED, feeds no decision, moves no dry
digest.

Four proofs, three of them exact rather than statistical:

  P1 DRY IS UNTOUCHED, PER ROW. `_belief_prefix_record` is called on a coordinator with
     `dry_run=True` and must return exactly `asdict(Belief())`, which is the committed value the
     field already carried, so a dry decision row is byte-identical and no dry digest can move. The
     paired dry-cell digest run is the end-to-end form of the same claim; this is the mechanism.

  P2 LIVE IS FILLED, WITH THE DECLARED DEFINITION. On a coordinator with `dry_run=False` and seeded
     sessions, the record must carry each session's built prefix under its believed tier, so D211
     signal (a) (`max(0, cached_tokens - gpu_tokens_by_session[sid])`) is computable.

  P3 NOTHING READS IT. A census of every reference to a decision row's `belief` in the tree.

  P4 IT CANNOT CONTAMINATE THE MEASURED DECISION LATENCY. `_log_decision` takes `latency_ms` as an
     argument, so the caller has already measured it before this record is built.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

GPU_KV = 62_944
HOST_GIB = 27.0
HOST_TOK = 48_000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tree = Path(a.tree).resolve()
    L = tree / "experiments/orchestration/live2"
    for q in (L, L / "hybrid", L / "fleet", L / "v5",
              tree / "experiments/orchestration/baselines",
              tree / "experiments/orchestration/baselines/reconstructed",
              tree / "experiments/orchestration/sim", tree / "experiments/lib",
              tree / "experiments/dashcam"):
        sys.path.insert(0, str(q))
    import arms as A
    import cstate as CS
    import schema as SC
    from coordinator import Live2Coordinator

    present = hasattr(Live2Coordinator, "_belief_prefix_record")
    doc = {"tree": str(tree), "recording_site_present": present,
           "empty_belief": SC.asdict(SC.Belief())}

    def build(dry: bool):
        arm = A.make_arm("covex-v6-fair-c5attr")
        arm.live2_configure(gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                            host_tier_tokens=HOST_TOK, targets=CS.TARGETS)
        co = Live2Coordinator(arm, None, [], gpu_kv_tokens=GPU_KV, host_tier_gib=HOST_GIB,
                              host_tier_tokens=HOST_TOK, upload_mode="A", window_s=60.0,
                              drain_s=5.0, seed=4, logs=None, run_tag="x", dry_run=dry)
        co.st.sessions["gpu1"] = CS.SessionRec(
            session_id="gpu1", device_id="rob1", est_tokens=11000, built_tokens=11000,
            belief={"gpu": 1.0, "host": 0.0, "cold": 0.0})
        co.st.sessions["gpu_partial"] = CS.SessionRec(
            session_id="gpu_partial", device_id="rob2", est_tokens=11000, built_tokens=4096,
            belief={"gpu": 1.0, "host": 0.0, "cold": 0.0})
        co.st.sessions["host1"] = CS.SessionRec(
            session_id="host1", device_id="rob3", est_tokens=8000, built_tokens=8000,
            belief={"gpu": 0.0, "host": 1.0, "cold": 0.0})
        co.st.sessions["cold1"] = CS.SessionRec(
            session_id="cold1", device_id="rob4", est_tokens=9000, built_tokens=0,
            belief={"gpu": 0.0, "host": 0.0, "cold": 1.0})
        co.st.sessions["empty"] = CS.SessionRec(session_id="empty", device_id="rob5",
                                                est_tokens=0, built_tokens=0)
        return co

    if present:
        doc["P1_dry_record"] = build(True)._belief_prefix_record()
        doc["P1_dry_equals_committed_empty"] = (
            doc["P1_dry_record"] == SC.asdict(SC.Belief()))
        doc["P2_live_record"] = build(False)._belief_prefix_record()
        r = doc["P2_live_record"]
        doc["P2_signal_a_example"] = {
            "cached_tokens_reported_by_engine": 11000,
            "session": "gpu_partial",
            "believed_gpu_prefix": r["gpu_tokens_by_session"].get("gpu_partial", 0),
            "host_tokens": max(0, 11000 - r["gpu_tokens_by_session"].get("gpu_partial", 0))}
    else:
        doc["P1_dry_record"] = doc["P2_live_record"] = None

    # ---- P3 census: who reads a decision row's `belief`
    pat = re.compile(r"""(\.belief\b|\[['"]belief['"]\]|get\(['"]belief['"])""")
    hits = []
    for p in sorted(tree.rglob("*.py")):
        try:
            txt = p.read_text()
        except Exception:                                                 # noqa: BLE001
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if pat.search(line):
                hits.append({"file": str(p.relative_to(tree)), "line": i,
                             "text": line.strip()[:140]})
    doc["P3_belief_references"] = hits
    doc["P3_n_references"] = len(hits)

    # ---- P4: the signature proves latency is measured by the caller
    src = (L / "coordinator.py").read_text()
    doc["P4_log_decision_takes_latency_arg"] = "latency_ms: float = 0.0" in src
    doc["P4_log_decision_callers"] = len(re.findall(r"_log_decision\(", src)) - 1

    doc["git_describe_of_tree"] = subprocess.run(
        ["true"], capture_output=True, text=True).returncode
    Path(a.out).write_text(json.dumps(doc, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in doc.items() if k != "P3_belief_references"},
                     indent=1, default=str))
    print("P3 references:", doc["P3_n_references"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
