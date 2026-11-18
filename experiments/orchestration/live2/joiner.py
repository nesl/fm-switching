#!/usr/bin/env python3
"""D63: predicted versus actual, per decision and per affected request. CPU only.

D63 makes the mixed-traffic validation of the cost model a product of the LIVE RUN: every engine
study so far injected ONE action into a background of short N = 1 calls, so the evidence that the
step rules hold on a realistic mix comes from here. This module joins the coordinator's three
log streams into one row per decision and one row per affected request, each TAGGED WITH THE
TRAFFIC MIX IN FLIGHT AT SUBMIT TIME (monitoring calls, pieces, whole rebuilds, recall answers),
which is the axis D63 asks the report to break the comparison down by.

A baseline logs ACTUALS only, and its own estimate when it has one: the `predicted` block of its
decisions is empty, and the joiner says `predicted_by = "none"` for those rows rather than
treating a missing prediction as a prediction of zero.
"""
import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List

import schema as SC


def join(out_dir: Any) -> Dict[str, Any]:
    d = Path(out_dir)
    decisions = SC.read_jsonl(d / "decision.jsonl") if (d / "decision.jsonl").exists() else []
    requests = SC.read_jsonl(d / "request.jsonl") if (d / "request.jsonl").exists() else []
    by_decision: Dict[str, List[Dict[str, Any]]] = {}
    for r in requests:
        by_decision.setdefault(r.get("decision_id"), []).append(r)
    rows: List[Dict[str, Any]] = []
    req_rows: List[Dict[str, Any]] = []
    for dec in decisions:
        pr = dec.get("predicted") or {}
        has = any(pr.get(k) is not None for k in ("ttft_s", "completion_s")) or \
            bool(pr.get("imposed_delay_s_by_request"))
        reqs = by_decision.get(dec["decision_id"], [])
        for r in reqs:
            actual_ttft = (None if r.get("t_first_token") is None
                           else r["t_first_token"] - r["t_submit"])
            actual_done = None if r.get("t_done") is None else r["t_done"] - r["t_submit"]
            rows.append(dict(
                decision_id=dec["decision_id"], request_id=r["request_id"], arm=dec["arm"],
                arm_version=dec.get("arm_version"), kind=dec["kind"], t=dec["t"],
                piece_tokens=dec.get("piece_tokens"), cost_model_id=dec.get("cost_model_id"),
                mu=dec.get("mu"), H=dec.get("H"),
                predicted_by=("policy" if has else "none"),
                predicted_ttft_s=pr.get("ttft_s"), actual_ttft_s=actual_ttft,
                predicted_completion_s=pr.get("completion_s"), actual_completion_s=actual_done,
                traffic_mix=r.get("traffic_mix") or dec.get("traffic_mix") or {},
                cache_path=r.get("cache_path"), cached_fraction=r.get("cached_fraction"),
                prompt_tokens=r.get("prompt_tokens"), http_status=r.get("http_status"),
                decision_latency_ms=dec.get("decision_latency_ms")))
        for rid, pred_delay in (pr.get("imposed_delay_s_by_request") or {}).items():
            req_rows.append(dict(decision_id=dec["decision_id"], affected=rid,
                                 predicted_imposed_delay_s=pred_delay, arm=dec["arm"],
                                 traffic_mix=dec.get("traffic_mix") or {},
                                 note="the actual imposed delay is the affected request's own "
                                      "delivery shift, which the analysis computes against the "
                                      "paired no-release cell of the run matrix"))
    return dict(n_decisions=len(decisions), n_requests=len(requests), rows=rows,
                imposed_delay_rows=req_rows, by_mix=_by_mix(rows))


def _mix_key(mix: Dict[str, Any]) -> str:
    if not mix:
        return "unknown"
    return ",".join(f"{k}={int(v)}" for k, v in sorted(mix.items()) if int(v or 0) > 0) or "idle"


def _by_mix(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(_mix_key(r.get("traffic_mix") or {}), []).append(r)
    out = []
    for mix, rs in sorted(groups.items()):
        pairs = [(r["predicted_ttft_s"], r["actual_ttft_s"]) for r in rs
                 if r["predicted_ttft_s"] is not None and r["actual_ttft_s"] is not None]
        out.append(dict(mix=mix, n=len(rs), n_paired=len(pairs),
                        median_predicted_ttft_s=(round(median([p for p, _ in pairs]), 4)
                                                 if pairs else None),
                        median_actual_ttft_s=(round(median([a for _, a in pairs]), 4)
                                              if pairs else None),
                        median_ratio=(round(median([p / a for p, a in pairs if a > 0]), 4)
                                      if [1 for _, a in pairs if a > 0] else None)))
    return out


def write(out_dir: Any, joined: Dict[str, Any]) -> Path:
    d = Path(out_dir)
    p = d / "predicted_vs_actual.json"
    p.write_text(json.dumps(joined, indent=1, sort_keys=True) + "\n")
    return p
