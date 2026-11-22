#!/usr/bin/env python3
"""D170: the 32,768-token context limit, reported as a send decision per arm and seed.

READ-ONLY on the committed cells plus the trace, which is where the OFFERED side has to come from:
an arm that sends nothing over the limit has either declined every over-limit question or never
been offered one, and those are a finding and a non-finding respectively (CLAUDE.md Rule 2,
"unexercised"). The trace is deterministic in the seed, so the offered side is recomputed exactly.

WHAT "SENT" MEANS HERE, and the first join I tried got it wrong. An outcome row whose
cloud_payload carries a request_id looks like a send, and by that test `simplestream` sent all 18
over-limit questions at seed 7. It did not: its `tokens_charged` is 467, so what it sent was a
short representation of a long history, which is a representation decision and not an over-limit
send. The test used below is tokens_charged ABOVE THE LIMIT, which is the quantity D170 is about.
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
for _p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
           str(HERE.parent / "baselines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import trace as TR                                                             # noqa: E402

LIMIT = 32768
SEEDS = [4, 5, 6, 7]
CELL_ARGS = dict(n_devices=16, ratio="40:40:20", run_s=1200.0, mode="A",
                 robot_question_set="lh_req", ss_question_set="ss2",
                 dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)


def offered(seed: int) -> Dict[str, int]:
    b = TR.generate_trace(seed, CELL_ARGS["n_devices"], CELL_ARGS["ratio"], CELL_ARGS["run_s"],
                          CELL_ARGS["mode"], robot_question_set=CELL_ARGS["robot_question_set"],
                          ss_question_set=CELL_ARGS["ss_question_set"],
                          dashcam_format=CELL_ARGS["dashcam_format"],
                          robot_upload=CELL_ARGS["robot_upload"],
                          robot_reask_mean_s=CELL_ARGS["robot_reask_mean_s"])
    return {r["opportunity_id"]: int(r.get("history_tokens") or 0) for r in b["records"]
            if "recall" in str(r.get("kind") or "")
            and int(r.get("history_tokens") or 0) > LIMIT}


def main() -> int:
    out: Dict[str, Any] = {
        "_what": "D170: over-limit (>32,768-token) requests sent, per arm and seed",
        "_limit_tokens": LIMIT,
        "_sent_test": ("an outcome row whose cloud_payload.tokens_charged exceeds the limit. A "
                       "request_id alone is NOT the test: simplestream carries one on all 18 "
                       "over-limit questions at seed 7 with tokens_charged 467, which is a short "
                       "representation of a long history, not an over-limit send"),
        "offered_by_seed": {}, "cells": [], }
    off = {s: offered(s) for s in SEEDS}
    for s in SEEDS:
        out["offered_by_seed"][str(s)] = {
            "over_limit_recall_opportunities": len(off[s]),
            "max_history_tokens": max([0] + list(off[s].values())),
            "opportunity_ids": sorted(off[s])}
    for d in sorted(p for p in RUNS.iterdir() if p.is_dir() and "_rq30" in p.name):
        seed = next((s for s in SEEDS if "_s%d_" % s in d.name), None)
        f = d / "outcomes.jsonl.gz"
        if seed is None or not f.exists() or not off[seed]:
            continue
        seen = sent = short = 0
        rows: List[Dict[str, Any]] = []
        for l in gzip.open(f, "rt"):
            o = json.loads(l)
            if o.get("opportunity_id") not in off[seed]:
                continue
            seen += 1
            cp = o.get("cloud_payload") or {}
            if not cp.get("request_id"):
                continue
            tc = int(cp.get("tokens_charged") or 0)
            if tc > LIMIT:
                sent += 1
                rows.append({"opportunity_id": o["opportunity_id"], "tokens_charged": tc,
                             "history_tokens": off[seed][o["opportunity_id"]],
                             "cloud_letter": cp.get("cloud_letter"),
                             "scored_on_time": bool(o.get("within_L")),
                             "t_submit_to_delivered_s": (
                                 round(float(o["t_delivered"]) - float(o["t_cloud_done"]), 4)
                                 if o.get("t_delivered") and o.get("t_cloud_done") else None)})
            else:
                short += 1
        out["cells"].append({
            "cell": d.name, "seed": seed,
            "over_limit_offered": seen,
            "over_limit_sent_as_send_decision": sent,
            "over_limit_released_as_a_shorter_representation": short,
            "sends": rows})
    sent_any = [c for c in out["cells"] if c["over_limit_sent_as_send_decision"]]
    out["summary"] = {
        "over_limit_questions_exist_only_at_seed_7": all(
            not off[s] for s in SEEDS if s != 7) and bool(off[7]),
        "seeds_4_to_6_are_UNEXERCISED": ("no recall question reaches the limit at seeds 4 to 6 "
                                         "(max history 26,671 to 26,941 tokens), so a zero there "
                                         "is unexercised and carries no information about any "
                                         "arm's over-limit behaviour (CLAUDE.md Rule 2)"),
        "arms_that_sent_one": [c["cell"] for c in sent_any],
        "our_arms_sent_none": all(not c["over_limit_sent_as_send_decision"] for c in out["cells"]
                                  if c["cell"].split("_")[0] in
                                  ("v5-rules-2", "v5-rules", "hybrid-F-lhreq-noc3",
                                   "covex-v6-state")),
        "but_the_rule_is_still_absent": (
            "our arms decline these questions on TIME, not on the limit: the feasibility test is "
            "`est <= slack` with est = recall_ttft_s(history, readiness), and a 34k to 53k-token "
            "COLD history cannot be predicted to finish inside a 3 s deadline. That is b7's "
            "existing behaviour inherited through the base, and D170 asks that 'already behaves "
            "correctly' be verified SEPARATELY from 'has the rule'. It is absent: no 32768 "
            "appears anywhere under experiments/orchestration. THE CASE THE RULE EXISTS FOR IS "
            "ONE WARMING CREATES: a 40k-token history already built WARM has a small predicted "
            "est, passes `est <= slack`, is sent, and is refused by the engine. Rung 1 and above "
            "warm ahead, so the reachable path appears exactly where the rule is missing"),
        "defect_found_in_a_baseline_cell": (
            "always-cloud-fcfs at seed 7 sent two (38,821 and 48,811 tokens charged). Both came "
            "back with no prompt_tokens, no http_status and cloud_letter 'X', the no-letter "
            "sentinel, and opp0006097 was recorded as DELIVERED ON TIME 17 ms after submission, "
            "which is impossible for a 38,821-token prefill (check 2). The scorer's "
            "`cloud_stands = on_time and cloud_letter` is then true, so the engine's refusal "
            "REPLACES the device's answer, which is the opposite of D170's 'the device answer "
            "stands'. MEASURED IMPACT ON EVERY COMMITTED NUMBER: ZERO, because that question's "
            "device answer is itself wrong (gold A, device incorrect), so standing_correct is "
            "false either way. The conflict between D144 (3) ('a per-question MISS for whichever "
            "arm sends it') and D170's gloss ('with the device answer standing') is therefore "
            "REAL IN THE RULES and UNEXERCISED IN THE DATA, and it is the user's to settle"),
    }
    dest = REPO / "results/orchestration/live2/frozen_test/d170_overlimit.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    for s in SEEDS:
        print("seed %d: over-limit recall opportunities %2d, max history %6d" % (
            s, len(off[s]), max([0] + list(off[s].values()))))
    for c in out["cells"]:
        print("%-58s offered %2d sent %2d short-rep %2d" % (
            c["cell"][:58], c["over_limit_offered"],
            c["over_limit_sent_as_send_decision"],
            c["over_limit_released_as_a_shorter_representation"]))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
