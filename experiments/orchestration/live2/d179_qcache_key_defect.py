#!/usr/bin/env python3
"""The `_queued_behind` cache-key defect at arms_v6state.py:236: can it change live decisions?

THE DEFECT (user ruling 2026-11-22, flash addendum 14, verified in code):

    key = (int(obs.epoch) if isinstance(obs.epoch, int) else id(obs))      arms_v6state.py:236
    def observation(self, now: float, epoch: str, ...)                     cstate.py:579

`obs.epoch` is always a str, so the isinstance test is always False and the key is always a memory
address. CPython reuses addresses for same-size objects, so a fresh Observation allocated where a
freed one sat can hit the cache entry of a PREVIOUS decision period.

HOW THIS FILE MEASURES IT. Two modes, ONE DRY CELL PER PROCESS (`d179_qcache_probe.py`), because a
dry cell does not reproduce across runs inside one process and that non-reproduction IS the defect
under test:

  probe    wraps V6StateArm._queued_behind, counting calls, hits, misses and - the quantity that
           matters - STALE hits, a hit whose cache entry was written in a different decision
           period. A stale HIT changes a value; a stale MISS costs only a recompute. The two are
           counted separately.
  fixed    rebuilds the cache once per decision period (`_q_cache_key = None` whenever obs.now_s
           changes), which is the proposed fix applied WITHOUT editing the live path, through
           test_hybrid.dry's own `patch` hook, and compares decision-row digests against the
           current key.

REGISTER, stated before any number. A DRY replay measures DRY allocation patterns. A live run has
a real backend, I/O threads and different allocation behaviour, so a dry stale-hit count is an
INDICATION of live exposure and NOT a measurement of it. This file does not bound the live effect
and says so where it reports.

Usage: python d179_qcache_key_defect.py --dir <qc dir of probe outputs> [--out <path>]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

RUNG2_ARMS = ("covex-v6-state-uo", "covex-v6-state-shares", "covex-v6-state-uo-c5attr")
CONTROL_ARMS = ("covex-v6-base", "v5-rules-2", "b7-edf-feasibility")
DECISION_FIELDS_IGNORED = ("arm_version",)


def load(d: Path) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".rows.json"):
            continue
        try:
            j = json.loads(p.read_text())
        except Exception:                                                # noqa: BLE001
            continue
        r = j.get("result")
        if r:
            r["_file"] = p.name
            r["_rows_file"] = str(p) + ".rows.json"
            out.append(r)
    return out


def row_diff(a: Path, b: Path) -> Dict[str, Any]:
    """Setwise and positional diff of two decision-row lists (arm_version already stripped)."""
    if not a.exists() or not b.exists():
        return {"available": False}
    ra = json.loads(a.read_text())
    rb = json.loads(b.read_text())
    ka = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in ra]
    kb = [json.dumps(x, sort_keys=True, separators=(",", ":")) for x in rb]
    sa, sb = defaultdict(int), defaultdict(int)
    for x in ka:
        sa[x] += 1
    for x in kb:
        sb[x] += 1
    only_a = sum(v for k, v in sa.items() if sb.get(k, 0) < v)
    only_b = sum(v for k, v in sb.items() if sa.get(k, 0) < v)
    pos = sum(1 for i in range(min(len(ka), len(kb))) if ka[i] != kb[i])
    first = None
    for i in range(min(len(ka), len(kb))):
        if ka[i] != kb[i]:
            first = {"index": i, "a": ra[i], "b": rb[i]}
            break
    return {"available": True, "rows_a": len(ka), "rows_b": len(kb),
            "setwise_only_in_a": only_a, "setwise_only_in_b": only_b,
            "positional_differing_rows": pos, "first_positional_difference": first}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    d = Path(a.dir)
    res = load(d)
    by = {}
    for r in res:
        by[(r["arm"], r["seed"], r["keymode"], r["_file"])] = r

    cells: Dict[str, Any] = {}
    for (arm, seed, km, fn), r in sorted(by.items()):
        cells.setdefault(f"{arm}|s{seed}", {}).setdefault(km, []).append(r)

    report = {}
    for cell, kms in sorted(cells.items()):
        ent: Dict[str, Any] = {}
        for km, runs in sorted(kms.items()):
            digests = sorted({x["digest"] for x in runs})
            ent[km] = {
                "runs": len(runs),
                "digests": digests,
                "reproducible_across_processes": len(digests) == 1,
                "rows": sorted({x["rows"] for x in runs}),
                "state_chosen": {k: sorted({x.get(k) for x in runs})
                                 for k in ("state_chosen_KEEP", "state_chosen_TOUCH",
                                           "state_chosen_WARM", "state_chosen_HOLD_BACK")},
                "state_touch_emitted": sorted({x.get("state_touch_emitted") for x in runs}),
                "state_hold_back_enacted": sorted({x.get("state_hold_back_enacted")
                                                   for x in runs}),
                "harm_warm_nonzero": sorted({x.get("harm_warm_nonzero") for x in runs}),
                "harm_warm_milli_sum": sorted({x.get("harm_warm_milli_sum") for x in runs}),
                "qcache": [x.get("qcache") for x in runs],
            }
        cur = ent.get("current", {})
        fix = ent.get("fixed", {})
        same = (bool(cur.get("digests")) and bool(fix.get("digests"))
                and cur["digests"] == fix["digests"])
        ent["verdict"] = {
            "current_and_fixed_digests_equal": same,
            "decision_rows_changed_by_the_fix": (None if not (cur.get("digests")
                                                              and fix.get("digests"))
                                                 else not same),
            "stale_hits_current": [q.get("stale_hits") for q in (cur.get("qcache") or []) if q],
            "fresh_hits_current": [q.get("fresh_hits") for q in (cur.get("qcache") or []) if q],
            "stale_hits_that_returned_a_nonempty_list": [
                q.get("stale_hits_returned_nonempty") for q in (cur.get("qcache") or []) if q],
        }
        if cur.get("runs", 0) >= 2:
            ent["verdict"]["current_reproduces_across_processes"] = cur[
                "reproducible_across_processes"]
        # the row-level diff, current rep 1 against fixed rep 1
        ca = [x for (arm, seed, km, fn), x in sorted(by.items())
              if f"{arm}|s{seed}" == cell and km == "current"]
        fa = [x for (arm, seed, km, fn), x in sorted(by.items())
              if f"{arm}|s{seed}" == cell and km == "fixed"]
        if ca and fa:
            ent["row_diff_current_vs_fixed"] = row_diff(Path(ca[0]["_rows_file"]),
                                                        Path(fa[0]["_rows_file"]))
        if len(ca) >= 2:
            ent["row_diff_current_vs_current_other_process"] = row_diff(
                Path(ca[0]["_rows_file"]), Path(ca[1]["_rows_file"]))
        report[cell] = ent

    doc = {
        "what": ("can the arms_v6state.py:236 `_queued_behind` cache key, which is always id(obs), "
                 "change decisions?"),
        "ruling": "user ruling 2026-11-22, flash addendum 14",
        "defect": {
            "site": "experiments/orchestration/live2/arms_v6state.py:236",
            "code": "key = (int(obs.epoch) if isinstance(obs.epoch, int) else id(obs))",
            "why_always_an_address": ("cstate.py:579 declares `def observation(self, now: float, "
                                      "epoch: str, ...)`, so obs.epoch is always a str and the "
                                      "isinstance test is always False"),
            "cache_shape": ("a SINGLE slot, not a dict: `self._q_cache_key` plus "
                            "`self._q_cache` (arms_v6state.py:146-147), replaced whenever the key "
                            "changes (237-239). So it is neither cleared nor bounded, and it never "
                            "grows: there is exactly one live entry at any instant."),
            "read_that_changes_a_decision": [
                "arms_v6state.py:255 - the filtered list is RETURNED",
                "arms_v6state.py:264 - `_harm_warm` consumes it",
                "arms_v6state.py:273-289 - it becomes `cf_objective.harm_warm_from_queue_delay`",
                "arms_v6state.py:362 and 378 - `hw` and `harm_touch`",
                "arms_v6state.py:370-381 - both are arguments to `cf.plan_state`",
                "arms_v6state.py:411-423 - `d.chosen` emits a KEEP_GPU_WARM SessionAction or "
                "REMOVES a MATERIALIZE ask, which is a decision",
            ],
            "so_not_merely_a_redundant_recompute": True,
            "what_is_stale_in_a_stale_hit": ("every entry's `slack_s` was computed from the "
                                             "PREVIOUS period's `obs.now_s` (arms_v6state.py:251), "
                                             "and the recall set itself may have changed"),
        },
        "register": {
            "measured": "DRY replay, one cell per process, 1200 s, 16 devices, posted knobs "
                        "40:40:20, lh_req, ss2, epg, per-frame, reask 30.0",
            "not_measured": ("live exposure. A live run has a real backend, I/O threads and "
                             "different allocation behaviour, so the dry stale-hit count is an "
                             "INDICATION of live exposure, not a measurement of it. No bound on "
                             "the live effect is claimed here."),
        },
        "cells": report,
    }
    if a.out:
        Path(a.out).write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
