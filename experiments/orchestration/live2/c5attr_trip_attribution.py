#!/usr/bin/env python3
"""WHICH slow monitors trip C5's cap, classified by what their wait overlapped. READ-ONLY.

Asked for by the user ruling of 2026-11-22 (second addendum), because it bounds how much the C5
attribution candidate can recover. A monitor whose first-token time crosses C5's 0.8 s trip is the
EVIDENCE the cap reacts to. This file classifies every such monitor by what the coordinator had
released and running during its wait:

    recall / piece (warm build) / whole / touch   a request OF OURS with uncached >= 200 tokens
    several                                        more than one kind at once
    NONE                                           nothing of ours was in flight

**NONE is the case that bounds the candidate.** A monitor that trips the cap while nothing of ours
was running is the cap reacting to its own queueing (other monitors) rather than to released work,
and the attribution rule does NOT suppress that halving by design.

The classification uses the DECISION KIND of the overlapping request, taken from the cell's own
decision log by `decision_id`, so "warm build" and "recall" are the coordinator's own names and
not a guess from token counts.

Also reported, as a cross-check against the user's own independent measurement: the RELEASE DELAY
(t_submit - t_opportunity) per cell, which is the quantity that ruling rests on.
"""
from __future__ import annotations

import gzip
import json
import statistics as ST
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"

PERIOD_S, RUN_S = 0.1, 1200.0
DASH_L_S = 1.0
TRIP_S = 0.8 * DASH_L_S
EWMA_A = 0.3
CAP_FLOOR, CAP_CEIL = 4, 8
UNCACHED_MIN = 200
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"
CELLS = ([("hybrid-F-lhreq-noc3", s) for s in (4, 5, 6, 7)]
         + [("v5-rules-2", s) for s in (4, 5, 6, 7)]
         + [("covex-v6-state-uo", s) for s in (4, 5, 6, 7)])


def _gz(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _plain(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _q(xs, q):
    xs = sorted(xs)
    return round(xs[min(int(q * len(xs)), len(xs) - 1)], 3) if xs else None


def _cell(arm: str, seed: int) -> Optional[Dict[str, Any]]:
    d = RUNS / (arm + TAG % seed)
    if not d.exists():
        return None
    req = _gz(d / "request.jsonl.gz")
    out = _gz(d / "outcomes.jsonl.gz")
    dec = _plain(d / "decision.jsonl") or _gz(d / "decision.jsonl.gz")
    if not req or not out:
        return None
    kind_of_dec = {x["decision_id"]: x.get("kind") for x in dec if x.get("decision_id")}
    opp_kind = {o["opportunity_id"]: o["kind"] for o in out if o.get("opportunity_id")}
    t_opp = {o["opportunity_id"]: float(o["t_opportunity"]) for o in out
             if o.get("opportunity_id") and o.get("t_opportunity") is not None}

    mons: List[Dict[str, Any]] = []
    ours: List[Dict[str, Any]] = []
    delays: List[float] = []
    mon_uncached: List[int] = []
    for r in req:
        opp = r.get("opportunity_id")
        dk = kind_of_dec.get(r.get("decision_id"))
        t0 = float(r["t_submit"])
        tf = float(r["t_first_token"]) if r.get("t_first_token") else None
        t1 = float(r.get("t_done") or t0)
        unc = max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0)
        if (dk == "release_monitor") or (opp and opp_kind.get(opp) == "monitor"):
            if tf is not None:
                mons.append({"t0": t0, "tf": tf, "ttft": tf - t0, "t1": t1})
            if opp in t_opp:
                delays.append(t0 - t_opp[opp])
            mon_uncached.append(unc)
        elif unc >= UNCACHED_MIN:
            ours.append({"t0": t0, "t1": t1, "uncached": unc,
                         "kind": {"release_recall": "recall", "release_piece": "warm_build",
                                  "release_whole": "whole", "release_touch": "touch"}.get(
                                      dk, dk or "unlabelled")})
    mons.sort(key=lambda m: m["t0"])
    ours.sort(key=lambda x: x["t0"])

    # the AIMD replay, to find WHICH slow monitors were the evidence at an actual halving
    n_ep = int(RUN_S / PERIOD_S)
    upd = sorted((m["t1"], m) for m in mons)
    lat, j, cap, last_adj = 0.0, 0, CAP_CEIL, None
    pending: List[Dict[str, Any]] = []
    classes: Dict[str, int] = {}
    halvings = {"evidence_all_ours": 0, "evidence_mixed": 0, "evidence_none_ours": 0,
                "no_slow_evidence": 0}
    slow_total = 0
    for e in range(n_ep):
        t = e * PERIOD_S
        while j < len(upd) and upd[j][0] <= t:
            m = upd[j][1]
            lat = m["ttft"] if lat <= 0 else EWMA_A * m["ttft"] + (1 - EWMA_A) * lat
            pending.append(m)
            j += 1
        if lat > TRIP_S:
            if last_adj is None or t - last_adj >= 1.0:
                slow = [m for m in pending if m["ttft"] > TRIP_S]
                slow_total += len(slow)
                kinds_seen = []
                for m in slow:
                    hit = sorted({x["kind"] for x in ours
                                  if x["t0"] <= m["tf"] and x["t1"] >= m["t0"]})
                    cls = "NONE" if not hit else (hit[0] if len(hit) == 1 else "several")
                    classes[cls] = classes.get(cls, 0) + 1
                    kinds_seen.append(cls)
                if not slow:
                    halvings["no_slow_evidence"] += 1
                elif all(k != "NONE" for k in kinds_seen):
                    halvings["evidence_all_ours"] += 1
                elif all(k == "NONE" for k in kinds_seen):
                    halvings["evidence_none_ours"] += 1
                else:
                    halvings["evidence_mixed"] += 1
                cap = max(CAP_FLOOR, cap // 2)
                last_adj = t
                pending = []
        elif last_adj is None or t - last_adj >= 5.0:
            if cap < CAP_CEIL:
                cap += 1
            last_adj = t
            pending = []
    tot = max(sum(classes.values()), 1)
    return {
        "cell": arm + TAG % seed,
        "monitor_requests_with_a_first_token": len(mons),
        "monitor_ttft_p50": _q([m["ttft"] for m in mons], 0.5),
        "monitor_ttft_p90": _q([m["ttft"] for m in mons], 0.9),
        "monitor_uncached_median": (int(ST.median(mon_uncached)) if mon_uncached else None),
        "release_delay_s_p50": _q(delays, 0.5), "release_delay_s_p90": _q(delays, 0.9),
        "release_delay_share_over_0_5s": (round(sum(1 for d in delays if d > 0.5)
                                                / len(delays), 4) if delays else None),
        "our_released_prefills_uncached_ge_200": len(ours),
        "slow_monitors_counted_at_a_halving": slow_total,
        "slow_monitor_overlap_classes": dict(sorted(classes.items())),
        "slow_monitor_overlap_shares": {k: round(v / tot, 4)
                                        for k, v in sorted(classes.items())},
        "halvings_by_evidence": halvings,
        "halvings_total": sum(halvings.values()),
        "share_of_halvings_the_rule_would_suppress": round(
            halvings["evidence_all_ours"] / max(sum(halvings.values()), 1), 4),
    }


def main() -> int:
    out: Dict[str, Any] = {
        "_what": ("which slow monitors trip C5's cap, classified by what their wait overlapped; "
                  "and the release delay the user's ruling of 2026-11-22 rests on"),
        "_register": ("READ-ONLY attribution on committed traces. NONE means nothing OF OURS with "
                      "uncached >= 200 tokens was in flight during that monitor's wait, so the "
                      "cap was reacting to its own queueing and the attribution rule does NOT "
                      "suppress that halving"),
        "_definitions": {
            "slow monitor": "first-token time > 0.8 s, C5's own trip",
            "ours": ("a non-monitor request the coordinator released with uncached >= 200 "
                     "tokens, labelled by its own decision kind from the cell's decision log"),
            "counted at a halving": ("slow monitors are counted as the evidence of the halving "
                                     "they were pending for, so a monitor is counted once"),
        },
        "cells": [], }
    for arm, s in CELLS:
        c = _cell(arm, s)
        out["cells"].append(c or {"cell": arm + TAG % s, "missing": True})
    live = [c for c in out["cells"] if not c.get("missing")]
    def rng(pref, key):
        v = [c[key] for c in live if c["cell"].startswith(pref) and c.get(key) is not None]
        return [min(v), max(v)] if v else None
    out["summary"] = {
        "release_delay_p50": {"base": rng("hybrid-F", "release_delay_s_p50"),
                              "rung1": rng("v5-rules-2", "release_delay_s_p50"),
                              "rung2": rng("covex-v6-state-uo", "release_delay_s_p50")},
        "release_delay_share_over_0_5s": {
            "base": rng("hybrid-F", "release_delay_share_over_0_5s"),
            "rung1": rng("v5-rules-2", "release_delay_share_over_0_5s"),
            "rung2": rng("covex-v6-state-uo", "release_delay_share_over_0_5s")},
        "share_of_halvings_the_rule_would_suppress": {
            "base": rng("hybrid-F", "share_of_halvings_the_rule_would_suppress"),
            "rung1": rng("v5-rules-2", "share_of_halvings_the_rule_would_suppress"),
            "rung2": rng("covex-v6-state-uo", "share_of_halvings_the_rule_would_suppress")},
        "reading": ("the share of slow monitors whose wait overlapped NOTHING of ours bounds what "
                    "the attribution rule can recover: those halvings are not suppressed by it, "
                    "by design, because the cap is then reacting to its own queueing"),
    }
    dest = REPO / "results/orchestration/live2/frozen_test/c5attr_trip_attribution.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print("%-56s %7s %7s %7s %8s %8s" % ("cell", "slow", "NONE", "ours", "suppress", "reldelay"))
    for c in live:
        cl = c["slow_monitor_overlap_classes"]
        print("%-56s %7d %7d %7d %8.3f %8s" % (
            c["cell"][:56], c["slow_monitors_counted_at_a_halving"], cl.get("NONE", 0),
            sum(v for k, v in cl.items() if k != "NONE"),
            c["share_of_halvings_the_rule_would_suppress"], c["release_delay_s_p50"]))
    print(json.dumps(out["summary"], indent=1))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
