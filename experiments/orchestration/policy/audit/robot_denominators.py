#!/usr/bin/env python3
"""D132 item 2: robot on-time over BOTH denominators, and the capacity conjunct at p = 0.50/0.75/0.90.

The feasible-only numerator is matched BY QUESTION, not derived by dividing a fraction by the
ceiling. A question is feasible when its own idle-engine cost fits its own deadline, exactly as
`feasibility_ceiling.py` computes it, and the match is on `opportunity_id`, which identifies the
question instance in both the trace and the outcomes.

Why this matters: the ceiling of 0.9039 means about 9.6 percent of robot questions cannot be
delivered on an idle GPU by any scheduler. An all-questions denominator therefore scores every arm
partly against work no arm could do. D132 item 1 fixed the headline at p = 0.90 over FEASIBLE
questions because the ceiling falls below 0.90 at 32 devices; both denominators are reported here
regardless, per the ruling.

This is a POST-PROCESSOR over runs already measured. It starts no new run.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

CELL = re.compile(r"^s(\d+)_(.+)_n(\d+)$")
P_GRID = (0.50, 0.75, 0.90)


def feasible_map(trace_dir: Path, costs, link_s: float) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for line in open(Path(trace_dir) / "trace.jsonl"):
        try:
            d = json.loads(line)
        except Exception:                                              # noqa: BLE001
            continue
        if d.get("kind") != "recall_question":
            continue
        h = int(d.get("history_tokens") or 0)
        dl = float(d.get("deadline_s") or 5.0)
        tot = costs.recall_ttft_s(h, "COLD") + costs.recall_ttft_s(h, "GPU-WARM") + link_s
        out[d["opportunity_id"]] = bool(tot <= dl)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--roots", required=True)
    a = ap.parse_args(argv)

    H.setup_paths()
    import importlib
    sc = importlib.import_module("scorer.score")
    from baselines import costs
    sys.path.insert(0, str(H.ROOT / "experiments" / "orchestration" / "live2"))
    import traces as T
    link_s = T.RTT_MS / 1000.0

    feas_cache: Dict[tuple, Dict[str, bool]] = {}
    rows: List[Dict[str, Any]] = []

    for root in a.roots.split(","):
        for d in sorted(glob.glob(os.path.join(root.strip(), "*"))):
            m = CELL.match(os.path.basename(d))
            if not m:
                continue
            seed, arm, n = int(m.group(1)), m.group(2), int(m.group(3))
            run, trace = Path(d) / "run", Path(d) / "trace"
            if not (run / "outcomes.jsonl").exists() or not (trace / "trace.jsonl").exists():
                continue
            key = (seed, n)
            if key not in feas_cache:
                feas_cache[key] = feasible_map(trace, costs, link_s)
            feas = feas_cache[key]

            outs = {}
            for line in open(run / "outcomes.jsonl"):
                try:
                    r = json.loads(line)
                except Exception:                                      # noqa: BLE001
                    continue
                if r.get("opportunity_id") is not None:
                    outs[r["opportunity_id"]] = r
            rec = [o for o in outs.values() if o.get("kind") == "recall"]
            if not rec:
                continue

            all_n = len(rec)
            all_k = sum(1 for o in rec if sc._within(o, sc.ROB_L_S))
            fe = [o for o in rec if feas.get(o["opportunity_id"], False)]
            fe_n = len(fe)
            fe_k = sum(1 for o in fe if sc._within(o, sc.ROB_L_S))

            att = sc.attainment(type("S", (), {"outcomes": outs})())
            dash_ok = bool(att.dashcam_all_meet)
            elig = all_n >= sc.ROB_MIN_QUESTIONS

            row = dict(seed=seed, n_devices=n, arm=arm,
                       dashcam_all_meet=dash_ok,
                       robot_all=dict(n=all_n, on_time=all_k,
                                      fraction=round(all_k / all_n, 6)),
                       robot_feasible=dict(n=fe_n, on_time=fe_k,
                                           fraction=(round(fe_k / fe_n, 6) if fe_n else None)),
                       infeasible_excluded=all_n - fe_n,
                       robot_pool_eligible=elig)
            for p in P_GRID:
                row["capacity_all_p%.2f" % p] = bool(
                    dash_ok and elig and all_k / all_n >= p - 1e-12)
                row["capacity_feasible_p%.2f" % p] = bool(
                    dash_ok and elig and fe_n and fe_k / fe_n >= p - 1e-12)
            rows.append(row)

    out = dict(check="covex_harden_robot_denominators", is_measurement=False,
               label="D132 item 2. Robot on-time over ALL and over FEASIBLE questions, matched by "
                     "opportunity_id, with the capacity conjunct at p = 0.50, 0.75 and 0.90 over "
                     "BOTH denominators. Post-processor over runs already measured.",
               headline="D132 item 1 fixed the headline at p = 0.90 over FEASIBLE questions, "
                        "because the idle-GPU ceiling is 0.8871 at 32 devices.",
               p_grid=list(P_GRID), link_s=link_s, rows=rows)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("cells:", len(rows), "-> wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
