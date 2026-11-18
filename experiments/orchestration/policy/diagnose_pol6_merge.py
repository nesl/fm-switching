#!/usr/bin/env python3
"""StudyPOL6-chain Part A addendum: does pol4 merge background prefills into a piece's own step?

THE CONTRADICTION THIS RESOLVES. StudyPOL5-engine section 1.5 reports that pol4 merges background
prefills into the action's own steps in "54 % of piece1024 steps and 66 % of piece2048 steps on
StudyENG1c Part D FIT (4 % for mono11k)", with "513 of 513" of those merges involving a request
handed over after the previous step started. StudyPOL6 Part A section 6 states the opposite, that
pol4 "never lets a background prefill share a piece's step". Both claims are about the SAME model
on the SAME collection, so at most one can be right.

pol4 is deterministic and its own step log names the requests prefilling in each step
(`EngineSim.run` -> `steps[i]["prefilling"]`), so this is settled by measurement rather than by
reading either report. This script counts, on both inputs, every simulated step in which an
ACTION request is prefilling and asks whether a BACKGROUND request is prefilling in the same step.

TWO INPUTS, because the two reports used different ones and the brief asks which statement holds
for which:
  * StudyENG1c Part D FIT, chained rebuilds (uuid-reference pieces, n_parts > 1);
  * StudyENG1d FIT, single-request pieces that carry their images as bytes.

FIT ONLY. Both loaders are the fenced ones; no HOLDOUT pair of either collection is constructed.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import trace_replay as tr
from .eng1_engine import EngineSim, make_sim
from .eng1d_replay import load_trials as load_eng1d
from .score_t0b import load_part_d_trials

OUT_PATH = "results/orchestration/study_pol6/pol6_partA_merge_addendum.json"


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def step_composition(trial: tr.Trial, sim: EngineSim) -> Dict[str, Any]:
    """pol4's own simulated steps, classified by who was prefilling in them."""
    res = sim.run(tr._arm_requests(trial.arms["with"], include_action=True))
    act = {str(r.get("rid")) for r in trial.arms["with"].action}
    bg = {str(r.get("rid")) for r in trial.arms["with"].background}
    rows = []
    for i, s in enumerate(res["steps"]):
        pre = [str(r) for r in s.get("prefilling", [])]
        mine = [r for r in pre if r in act]
        others = [r for r in pre if r in bg]
        unknown = [r for r in pre if r not in act and r not in bg]
        rows.append(dict(i=i, t_start=s["t_start"], t_end=s["t_end"],
                         duration_s=s["duration_s"], n_prefilling=len(pre),
                         n_action=len(mine), n_background=len(others),
                         n_unknown=len(unknown), decode_reqs=s.get("decode_reqs", 0),
                         action_rids=mine, background_rids=others))
    action_steps = [r for r in rows if r["n_action"] > 0]
    shared = [r for r in action_steps if r["n_background"] > 0]
    # how many requests were in the single largest simulated prefill batch at all
    return dict(
        n_steps=len(rows), n_action_steps=len(action_steps), n_shared_steps=len(shared),
        shared_fraction=(len(shared) / len(action_steps) if action_steps else None),
        max_prefilling_in_a_step=max((r["n_prefilling"] for r in rows), default=0),
        max_prefilling_in_an_action_step=max((r["n_prefilling"] for r in action_steps),
                                             default=0),
        n_steps_with_two_or_more_prefills=sum(1 for r in rows if r["n_prefilling"] > 1),
        n_action_steps_with_decodes=sum(1 for r in action_steps if r["decode_reqs"] > 0),
        unknown_rids_seen=sum(r["n_unknown"] for r in rows))


def run(trials: Sequence[tr.Trial], sim: EngineSim, label: str,
        action_of=None) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trials:
        if "with" not in t.arms or not t.arms["with"].action:
            continue
        c = step_composition(t, sim)
        c["key"] = t.key()
        g[(action_of or (lambda x: x.action))(t)].append(c)
    out = {}
    for act, rows in sorted(g.items()):
        n_act = sum(r["n_action_steps"] for r in rows)
        n_sh = sum(r["n_shared_steps"] for r in rows)
        out[act] = dict(
            n_trials=len(rows), n_action_steps=n_act, n_shared_action_steps=n_sh,
            shared_fraction=(n_sh / n_act if n_act else None),
            max_prefilling_in_an_action_step=max(
                (r["max_prefilling_in_an_action_step"] for r in rows), default=0),
            max_prefilling_in_any_step=max((r["max_prefilling_in_a_step"] for r in rows),
                                           default=0),
            n_steps_with_two_or_more_prefills=sum(
                r["n_steps_with_two_or_more_prefills"] for r in rows),
            n_action_steps_with_decodes=sum(r["n_action_steps_with_decodes"] for r in rows),
            unknown_rids_seen=sum(r["unknown_rids_seen"] for r in rows))
    return dict(label=label, by_action=out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args(argv)
    sim = make_sim("pol4")

    c_trials, c_audit = load_part_d_trials(split="fit")
    chained = [t for t in c_trials
               if int((sorted(t.arms["with"].action,
                              key=lambda r: (r.get("part_i") or 0))[0].get("n_parts")) or 1) > 1]
    single = [t for t in c_trials if t not in chained]
    eng1c_chained = run(chained, sim, "StudyENG1c Part D FIT, CHAINED (n_parts > 1)")
    eng1c_single = run(single, sim, "StudyENG1c Part D FIT, single-request (n_parts == 1)")

    d_trials, d_audit = load_eng1d("fit")
    eng1d = run(d_trials, sim, "StudyENG1d FIT (single-request pieces, images as bytes)")

    out = dict(
        study="StudyPOL6-chain Part A addendum: pol4's simulated step composition",
        model="pol4 (frozen), deterministic",
        question=("StudyPOL5 section 1.5 says pol4 merges background prefills into a piece's own "
                  "step in 54 % and 66 % of piece steps on StudyENG1c Part D FIT; StudyPOL6 Part "
                  "A section 6 says it never does. Measured here from pol4's own step log."),
        definition=("An ACTION STEP is a simulated step in which at least one action request is "
                    "prefilling. It is SHARED if a background request is prefilling in the same "
                    "step. Decodes are counted separately and are NOT a merge of prefills."),
        eng1c_chained=eng1c_chained, eng1c_single_request=eng1c_single, eng1d=eng1d,
        holdout_audit=dict(eng1c=c_audit, eng1d=d_audit),
        chunk_tokens=sim.chunk_tokens)
    p = _root() / args.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1, sort_keys=True))
    print("wrote %s" % args.out)
    for name in ("eng1c_chained", "eng1c_single_request", "eng1d"):
        print("--- %s ---" % out[name]["label"])
        for act, d in out[name]["by_action"].items():
            print("  %-10s trials %-4d action steps %-6d shared %-6d frac %-8s "
                  "max prefills in an action step %d (any step %d) decodes in %d"
                  % (act, d["n_trials"], d["n_action_steps"], d["n_shared_action_steps"],
                     (round(d["shared_fraction"], 4) if d["shared_fraction"] is not None
                      else None),
                     d["max_prefilling_in_an_action_step"], d["max_prefilling_in_any_step"],
                     d["n_action_steps_with_decodes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
