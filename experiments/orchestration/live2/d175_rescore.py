#!/usr/bin/env python3
"""D175 (1): a REFUSED cloud request never replaces the device answer. What changes, measured.

THE TWO SCORERS DISAGREED, and the headline reader was the correct one.

  frozen_headline.py:157   `http_status != 200`  -> True for None, so a refusal was ALREADY
                           excluded from `ont`, and `cloud_stands` was already False. The
                           HEADLINE numbers were never affected.
  scorer/score.py          `http_status is not None and != 200` -> False for None, so the D144
                           pass SKIPPED a request that never got a status, and the per-cell score
                           block let the refusal replace the device answer.

So this is a one-sided fix: score.py is brought to the reader's rule, not the other way round.

THE TEST IS THE REQUEST, NOT THE LETTER. 'X' is StudyR1's "no A-E found in the answer" sentinel,
which a genuinely delivered answer can also produce, so keying on the letter would discard real
cloud answers and flatter every arm whose text is poor.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(HERE / "scorer"))
import score as SC                                                             # noqa: E402

DEADLINE = {"monitor": 1.0, "recall": 3.0}
DASH_P = 0.25


def _rows(p: Path):
    if not p.exists():
        return []
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _old_failed(reqs) -> set:
    """score.py as committed before D175 (1)."""
    return {r.get("request_id") for r in reqs
            if r.get("http_status") is not None and int(r.get("http_status")) != 200}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "D175 (1): impact of never letting a refused request replace the device answer",
        "_fix": ("scorer/score.py now uses refused_request_ids(): a non-200 status, OR no status "
                 "at all with no prompt_tokens and no output_tokens. frozen_headline.py already "
                 "excluded these, so the headline is unchanged by construction"),
        "cells": [], }
    for d in sorted(p for p in RUNS.iterdir() if p.is_dir() and "_rq30" in p.name):
        reqs = _rows(d / "request.jsonl.gz")
        outs = _rows(d / "outcomes.jsonl.gz")
        if not reqs or not outs:
            continue
        old, new = _old_failed(reqs), SC.refused_request_ids(reqs)
        added = new - old
        if not added:
            continue
        # which outcomes lose their cloud delivery, and which of those were scored ON TIME
        flipped: List[Dict[str, Any]] = []
        dash_tot: Dict[str, int] = {}
        dash_on_before: Dict[str, int] = {}
        dash_on_after: Dict[str, int] = {}
        for o in outs:
            k = o.get("kind")
            dev = o.get("device_id")
            if k == "monitor":
                dash_tot[dev] = dash_tot.get(dev, 0) + 1
            rid = (o.get("cloud_payload") or {}).get("request_id")
            td, t0 = o.get("t_delivered"), o.get("t_opportunity")
            on_before = bool(td is not None and t0 is not None
                             and rid not in old
                             and float(td) - float(t0) <= DEADLINE.get(k, 3.0) + 1e-9)
            on_after = on_before and rid not in added
            if k == "monitor":
                dash_on_before[dev] = dash_on_before.get(dev, 0) + int(on_before)
                dash_on_after[dev] = dash_on_after.get(dev, 0) + int(on_after)
            if on_before and not on_after:
                cp = o.get("cloud_payload") or {}
                flipped.append({"opportunity_id": o.get("opportunity_id"), "kind": k,
                                "device_id": dev,
                                "tokens_charged": cp.get("tokens_charged"),
                                "cloud_letter": cp.get("cloud_letter"),
                                "delivered_minus_opportunity_s": (
                                    round(float(td) - float(t0), 4))})
        # does any dashcam device's target (p >= 0.25) flip?
        flips = []
        for dev, tot in sorted(dash_tot.items()):
            if not tot:
                continue
            b = dash_on_before.get(dev, 0) / tot
            a = dash_on_after.get(dev, 0) / tot
            if (b >= DASH_P) != (a >= DASH_P):
                flips.append({"device_id": dev, "before": round(b, 4), "after": round(a, 4),
                              "instants": tot})
        out["cells"].append({
            "cell": d.name,
            "requests_newly_treated_as_refused": len(added),
            "outcomes_that_lose_an_on_time_cloud_answer": len(flipped),
            "flipped": flipped,
            "dashcam_devices_whose_target_verdict_changes": flips,
            "dashcam_on_time_total_before": sum(dash_on_before.values()),
            "dashcam_on_time_total_after": sum(dash_on_after.values())})
    ours = ("v5-rules-2", "v5-rules", "hybrid-F-lhreq-noc3", "covex-v6-state", "covex-v6-base",
            "covex-v6-rules")
    our_cells = [c for c in out["cells"] if c["cell"].split("_n16")[0] in ours]
    out["summary"] = {
        "cells_touched": len(out["cells"]),
        "total_outcomes_losing_an_on_time_cloud_answer":
            sum(c["outcomes_that_lose_an_on_time_cloud_answer"] for c in out["cells"]),
        "by_kind": {k: sum(1 for c in out["cells"] for f in c["flipped"] if f["kind"] == k)
                    for k in ("monitor", "recall")},
        "dashcam_target_verdicts_changed":
            sum(len(c["dashcam_devices_whose_target_verdict_changes"]) for c in out["cells"]),
        "our_arms_affected": [c["cell"] for c in our_cells
                              if c["outcomes_that_lose_an_on_time_cloud_answer"]],
        "headline_impact": ("ZERO BY CONSTRUCTION: frozen_headline.py already excluded every "
                           "request with a missing status from `ont`, and `cloud_stands` reads "
                           "`ont`, so no headline number moves. The movement is confined to the "
                           "per-cell score blocks that scorer/score.py writes"),
        "the_over_limit_recall": ("always-cloud-fcfs seed 7, opp0006097, 38,821 tokens charged, "
                                 "letter 'X', recorded delivered 17 ms after submission. Its "
                                 "standing answer does not change even so, because that "
                                 "question's DEVICE answer is also wrong (gold A, device "
                                 "incorrect), so standing_correct is false either way. The "
                                 "D144 (3) against D175 (1) conflict stays unexercised in the "
                                 "data"),
    }
    dest = REPO / "results/orchestration/live2/frozen_test/d175_rescore.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for c in out["cells"]:
        print("%-58s +refused %3d  on-time lost %2d  dash verdict flips %d" % (
            c["cell"][:58], c["requests_newly_treated_as_refused"],
            c["outcomes_that_lose_an_on_time_cloud_answer"],
            len(c["dashcam_devices_whose_target_verdict_changes"])))
    print(json.dumps(out["summary"], indent=1)[:900])
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
