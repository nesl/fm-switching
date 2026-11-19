#!/usr/bin/env python3
"""D132 item 1: the IDLE-GPU FEASIBILITY CEILING for robot questions.

For every robot question, what fraction could be delivered within L = 5 s on an IDLE engine, with
no contention at all. Anything above this ceiling is unreachable by ANY scheduler, so a robot
target measured over ALL questions is partly a target over work no arm can ever do.

THE SUM, with each term from the committed curve and nothing invented here:

    cold rebuild of the history AT QUESTION TIME   costs.recall_ttft_s(h, "COLD")
  + answer TTFT once that rebuild has landed       costs.recall_ttft_s(h, "GPU-WARM")
  + link                                           RTT_MS / 1000 (question up, answer down)

THE DOUBLE-COUNT TRAP, documented in the D118 llf S_hat derivation and avoided here:
`recall_ttft_s(t, "COLD")` IS the prefill on its own and contains no answer term. Adding a
GPU-WARM answer term is correct. Adding a second COLD term would charge the prefill twice.

Sanity checks against that derivation's worked numbers:
  17,581 tokens -> nearest size 11,000, rate 4,500 -> 3.907 + 0.573 = 4.48 s, feasible but barely
  20,101 tokens -> nearest size 28,000, rate 3,800 -> 5.290 s from the curve alone, INFEASIBLE

HISTORY AT QUESTION TIME, not the session's final size: robot histories grow across a run through
the D101 preload and D68 appends, so a final size would overstate every early question's cost.
The trace's `recall_question` records carry `history_tokens` for exactly this.
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

CELL = re.compile(r"s(\d+)_.*_n(\d+)$")


def questions(trace_path: Path) -> List[Dict[str, Any]]:
    out = []
    for line in open(trace_path):
        try:
            d = json.loads(line)
        except Exception:                                              # noqa: BLE001
            continue
        if d.get("kind") == "recall_question":
            out.append(d)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--roots", required=True, help="comma-separated dirs holding s<seed>_*_n<n> cells")
    ap.add_argument("--link-s", type=float, default=None,
                    help="override the link term; default RTT_MS/1000 from the committed model")
    a = ap.parse_args(argv)

    H.setup_paths()
    from baselines import costs as C
    sys.path.insert(0, str(H.ROOT / "experiments" / "orchestration" / "live2"))
    import traces as T

    link_s = a.link_s if a.link_s is not None else T.RTT_MS / 1000.0

    # Reproduce the committed worked numbers before trusting the function on real data.
    chk = {}
    for tok, want in ((17581, 4.48), (20101, 5.29)):
        cold = C.recall_ttft_s(tok, "COLD")
        warm = C.recall_ttft_s(tok, "GPU-WARM")
        chk[str(tok)] = dict(cold=round(cold, 4), warm_answer=round(warm, 4),
                             cold_plus_warm=round(cold + warm, 4), expected=want)

    seen: Dict[tuple, Dict[str, Any]] = {}
    for root in a.roots.split(","):
        for d in sorted(glob.glob(os.path.join(root.strip(), "*"))):
            m = CELL.search(os.path.basename(d))
            if not m:
                continue
            seed, n = int(m.group(1)), int(m.group(2))
            if (seed, n) in seen:
                continue
            tp = Path(d) / "trace" / "trace.jsonl"
            if not tp.exists():
                continue
            qs = questions(tp)
            if not qs:
                continue
            rows = []
            for q in qs:
                h = int(q.get("history_tokens") or 0)
                dl = float(q.get("deadline_s") or 5.0)
                cold = C.recall_ttft_s(h, "COLD")
                warm = C.recall_ttft_s(h, "GPU-WARM")
                tot = cold + warm + link_s
                rows.append(dict(h=h, cold=cold, warm=warm, total=tot, deadline=dl,
                                 feasible=bool(tot <= dl)))
            nf = sum(1 for r in rows if r["feasible"])
            hs = sorted(r["h"] for r in rows)
            seen[(seed, n)] = dict(
                seed=seed, n_devices=n, n_questions=len(rows), n_feasible=nf,
                feasible_fraction=round(nf / len(rows), 6),
                history_tokens=dict(min=hs[0], p50=hs[len(hs) // 2], max=hs[-1]),
                infeasible_min_history=min([r["h"] for r in rows if not r["feasible"]], default=None),
                feasible_max_history=max([r["h"] for r in rows if r["feasible"]], default=None),
            )

    cells = [seen[k] for k in sorted(seen)]
    by_size: Dict[str, Any] = {}
    for c in cells:
        b = by_size.setdefault(str(c["n_devices"]), dict(n_questions=0, n_feasible=0, seeds={}))
        b["n_questions"] += c["n_questions"]
        b["n_feasible"] += c["n_feasible"]
        b["seeds"][str(c["seed"])] = c["feasible_fraction"]
    for b in by_size.values():
        b["feasible_fraction"] = round(b["n_feasible"] / max(b["n_questions"], 1), 6)

    allf = (sum(c["n_feasible"] for c in cells) / max(sum(c["n_questions"] for c in cells), 1))
    minf = min((c["feasible_fraction"] for c in cells), default=None)

    out = dict(
        check="covex_harden_feasibility_ceiling",
        is_measurement=False,
        label="D132 item 1. The IDLE-GPU ceiling on robot delivery. Derived from the COMMITTED "
              "cost curve; no new measurement and no fitted quantity.",
        terms=dict(cold="costs.recall_ttft_s(history_tokens, 'COLD')",
                   answer="costs.recall_ttft_s(history_tokens, 'GPU-WARM')",
                   link_s=link_s, link_source="traces.RTT_MS / 1000, question up and answer down",
                   deadline_s="from each question's own record"),
        committed_worked_numbers=chk,
        overall_feasible_fraction=round(allf, 6),
        min_cell_feasible_fraction=minf,
        by_size=by_size,
        cells=cells,
    )
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(overall=out["overall_feasible_fraction"],
                          min_cell=minf, by_size={k: v["feasible_fraction"]
                                                  for k, v in sorted(by_size.items(), key=lambda x: int(x[0]))}),
                     indent=1))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
