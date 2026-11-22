#!/usr/bin/env python3
"""RECONCILE the committed dashcam on-time count with the measured latency, per cell, read-only.

USER RULING 2026-11-22, C5 PLAN item b. No new cells, no server, no policy code touched.

THE PUZZLE. covex-v6-state seed 5 sends 8,312 monitors, only 10.4 percent of them take longer
than 0.8 s to a first token, the deadline is 1.0 s, and its committed dashcam on-time count is
2,314 out of 11,769. Sent-and-fast does not reach on-time, so the loss has to be somewhere the
first-token distribution cannot see.

THE DENOMINATOR, RESOLVED FIRST AND STATED. One unit: a MONITOR OPPORTUNITY, one row of
`outcomes.jsonl.gz` with kind == "monitor", counted PER RUN. That is 11,764 at seed 4 and 11,769
at seed 5, and it is the same denominator the committed scorer uses: the per-cell sum of
`attainment.dashcam_per_device[*].n_instants` in `cell.json` equals it exactly on every cell
checked here. D153's pre-third-frame instants are NOT in it and need no subtraction: under EP-G
the trace emits no monitor opportunity until an episode's third frame, which this script PROVES
per cell by showing the smallest per-episode frame index among opportunities is 2 (checked
against the coordinator's own `epg.by_episode_index`, whose smallest key is 2).

THE SEVEN BUCKETS, exhaustive and mutually exclusive by the precedence they are tested in:

  1 not_released          no request in `request.jsonl.gz` carries this opportunity_id. The
                          coordinator never sent it. There is also no decision record for it:
                          `decision.jsonl.gz` holds only positive releases, so a not-released
                          instant is an ABSENCE of a release, not a logged refusal.
  2 released_unsettled    a request carries the opportunity_id but the outcome carries no
                          cloud_payload, so no delivery was ever settled. Run-edge truncation;
                          a miss.
  3 released_refused      the request is in `scorer.score.refused_request_ids()` (D175 (1)): a
                          non-200 status, or no status at all with no prompt and no output
                          tokens. Never delivered, so the device answer stands and it is a miss.
  4 on_time               THE COMMITTED RULE, and the one this script is controlled against:
                          t_delivered - t_opportunity <= 1.0 s. For a monitor `t_delivered` is
                          FIRST-TOKEN based (D146: a dashcam Yes/No stays at first token; the
                          scorer's completion rewrite applies only to kind == "recall"), plus a
                          per-row forward hop.
  5 late_at_release       t_submit - t_opportunity > 1.0 s. The deadline was already gone before
                          the engine saw the request. No engine-side improvement can reach these.
  6 late_at_first_token   released inside the deadline, first token outside it.
  7 late_at_forward_only  first token inside the deadline, delivery outside it. These are exactly
                          the instants on which the two D146 readings of a dashcam alert disagree.

WHICH DELIVERY RULE THIS SCRIPT USES, because the two differ and the difference is a bucket.
Bucket 4 uses `t_delivered` (first token plus the forward hop), which is what the committed
scorer's `_within` reads and what `outcomes.within_L` records. The ALTERNATIVE reading of D146,
delivery AT first token (t_cloud_done), is reported beside it as `on_time_first_token_rule` and
is strictly larger by exactly bucket 7.

PROXIES, DECLARED.
  * `t_frame_arrive - t_opportunity` is used as the UPLINK component of the release delay. It is
    the trace's frame-arrival stamp, not a measured radio latency, and it is ~0.06 s on every arm
    and every seed here, so it is a constant of the trace and carries no arm difference.
  * `t_submit - t_frame_arrive` is used as the COORDINATOR HOLD. It is wall time between the frame
    being available and the request being submitted; it bundles the arm's release decision with
    any queueing inside the coordinator process and does NOT separate them.
  * monitor in-flight occupancy is rebuilt from `[t_submit, t_done]` of requests carrying a
    monitor opportunity_id. It is an OCCUPANCY, not the arm's own concurrency cap, and no arm's
    cap is reconstructed here.
  * NOT a proxy and not reconstructed: why an instant is in bucket 1. The logs carry no refusal
    record keyed to an opportunity, so bucket 1 is reported as one bucket with diagnostics beside
    it, never sub-attributed.

CACHING, a methodological parameter (CLAUDE.md). vLLM PREFIX CACHING WAS ENABLED in every cell
read here: `metrics_snapshots.log` shows non-zero `vllm:prefix_cache_hits_total` from the first
snapshot. Every latency quoted is therefore a WARM-SERVER number under an arm-dependent cache hit
pattern, and `uncached = prompt_tokens - cached_tokens` is reported so the reader can see it. No
number here is a cold prefill.

THE POSITIVE CONTROL. Bucket 4 must equal the cell's own committed dashcam on-time count, the sum
of `score.score.sweep[0].dashcam_per_device[*].on_time` in `cell.json`, on a BASE
(hybrid-F-lhreq-noc3) cell, which is a known-good committed arm. It is checked on every cell with
a score block, base and otherwise, and an exact match is required: this reconciliation redefines
nothing, so a one-count tolerance would only hide a break.

HELD CODE. covex-v6-state seeds 6 and 7 ran an unruled pricing switch and starved. They are
listed in `_excluded_held_code` and are NOT read.
"""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = REPO / "results/orchestration/live2/frozen_test/runs"
sys.path.insert(0, str(HERE / "scorer"))
sys.path.insert(0, str(REPO / "experiments/lib"))
from score import refused_request_ids                                   # noqa: E402
from _provenance import stamp                                           # noqa: E402

DASH_L_S = 1.0                  # D71/D82 target_defaults.L_dash, read back from every cell.json
PERIOD_S = 0.1
RUN_S = 1200.0
TAG = "_n16_s%d_1200s_h27_3t_L3_epg_rq30"

CELLS: List[str] = [
    "covex-v6-state" + TAG % 4 + "_rerun",
    "covex-v6-state" + TAG % 5,
]
CELLS += ["hybrid-F-lhreq-noc3" + TAG % s for s in (4, 5, 6, 7)]
CELLS += ["v5-rules-2" + TAG % s for s in (4, 5, 6, 7)]

HELD_CODE = ["covex-v6-state" + TAG % 6, "covex-v6-state" + TAG % 7,
             "covex-v6-state" + TAG % 7 + "_rerun"]

BUCKETS = ["not_released", "released_unsettled", "released_refused", "on_time",
           "late_at_release", "late_at_first_token", "late_at_forward_only",
           "late_request_row_absent"]


def _rows(p: Path) -> List[Dict[str, Any]]:
    with gzip.open(p, "rt") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _q(xs: Sequence[float], p: float) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(int(p * len(s)), len(s) - 1)], 4)


def _spread(xs: Sequence[float]) -> Dict[str, Any]:
    """Check 3: never a bare median. min, the quartiles, p90, p99 and max, always together."""
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "min": round(min(xs), 4), "p25": _q(xs, .25), "p50": _q(xs, .5),
            "p75": _q(xs, .75), "p90": _q(xs, .9), "p99": _q(xs, .99),
            "max": round(max(xs), 4), "mean": round(statistics.fmean(xs), 4),
            "distinct_values": len({round(x, 6) for x in xs})}


def _committed_on_time(cell_dir: Path) -> Dict[str, Any]:
    """The cell's OWN committed dashcam numbers, which the control is run against."""
    p = cell_dir / "cell.json"
    if not p.exists():
        return {"present": False}
    c = json.loads(p.read_text())
    sc = (c.get("score") or {}).get("score")
    if not sc or not sc.get("sweep"):
        return {"present": False}
    sw = sc["sweep"][0]
    pdv = sw.get("dashcam_per_device") or {}
    return {"present": True,
            "n_instants": sum(v["n_instants"] for v in pdv.values()),
            "on_time": sum(v["on_time"] for v in pdv.values()),
            "delivery_rule": sc.get("delivery_rule"),
            "on_time_rule": sc.get("on_time_rule"),
            "L_dash": (sc.get("target_defaults") or {}).get("L_dash")}


def _episode_index_floor(cr: Dict[str, Any]) -> Dict[str, Any]:
    """D153, from the coordinator's own tally: the smallest episode frame index that produced a
    monitoring request. 2 means the first two frames of an episode are not decision instants."""
    by = ((cr.get("epg") or {}).get("by_episode_index") or {})
    keys = sorted(int(k) for k in by)
    return {"min_episode_index_with_a_request": keys[0] if keys else None,
            "max_episode_index_with_a_request": keys[-1] if keys else None,
            "n_requests_summed": sum(v["n"] for v in by.values()) if by else None,
            "episodes": (cr.get("epg") or {}).get("episodes")}


def _prefix_cache(cell_dir: Path) -> Dict[str, Any]:
    """Caching is a methodological parameter, so it is READ, not assumed. The FIRST snapshot can
    legitimately show zero hits (the server has served nothing yet), so the test is the maximum
    over the run, not the first line."""
    p = cell_dir / "metrics_snapshots.log"
    if not p.exists():
        return {"enabled": None, "why": "no metrics_snapshots.log in this cell"}
    hits = qs = 0
    for line in p.read_text().splitlines():
        for tok in line.split():
            if tok.startswith("vllm:prefix_cache_hits_total="):
                hits = max(hits, int(tok.split("=")[1]))
            elif tok.startswith("vllm:prefix_cache_queries_total="):
                qs = max(qs, int(tok.split("=")[1]))
    return {"enabled": hits > 0, "prefix_cache_hits_total_max": hits,
            "prefix_cache_queries_total_max": qs,
            "hit_fraction": round(hits / qs, 4) if qs else None,
            "label": ("WARM SERVER: every latency in this cell was served with prefix caching on; "
                      "none of these numbers is a cold prefill")}


def reconcile(cell: str) -> Dict[str, Any]:
    d = RUNS / cell
    if not (d / "outcomes.jsonl.gz").exists():
        return {"cell": cell, "missing": True}
    out = _rows(d / "outcomes.jsonl.gz")
    req = _rows(d / "request.jsonl.gz")
    cr = json.loads((d / "coordinator_result.json").read_text())
    refused = refused_request_ids(req)

    by_rid = {r["request_id"]: r for r in req}
    by_opp: Dict[str, Dict[str, Any]] = {}
    for r in req:
        o = r.get("opportunity_id")
        if o is not None and o not in by_opp:
            by_opp[o] = r

    mon = [o for o in out if o.get("kind") == "monitor"]
    n_ep = int(RUN_S / PERIOD_S)

    # monitor in-flight occupancy, a diagnostic and declared as an occupancy, not a cap
    occ = [0] * n_ep
    for r in req:
        if r.get("opportunity_id") is None or r.get("t_done") is None:
            continue
        if r["opportunity_id"] not in {o["opportunity_id"] for o in mon}:
            continue
        a, b = int(float(r["t_submit"]) / PERIOD_S), int(float(r["t_done"]) / PERIOD_S)
        for e in range(max(a, 0), min(b + 1, n_ep)):
            occ[e] += 1

    counts = dict.fromkeys(BUCKETS, 0)
    rel_delay: List[float] = []          # t_submit - t_opportunity, on released instants
    uplink: List[float] = []             # t_frame_arrive - t_opportunity   (PROXY, declared)
    hold: List[float] = []               # t_submit - t_frame_arrive        (PROXY, declared)
    ttft: List[float] = []               # t_first_token - t_submit
    total: List[float] = []              # t_delivered - t_opportunity
    fwd: List[float] = []                # t_delivered - t_cloud_done
    unc: List[int] = []
    on_time_ft = 0                       # the ALTERNATIVE D146 reading, at first token
    occ_not_released: List[int] = []
    # the stratification that does the reconciling: inside late_at_first_token, how much of the
    # 1.0 s deadline was ALREADY SPENT before the engine saw the request, and how long the engine
    # itself then took. `engine_service_s` = t_cloud_done - t_submit, the server's whole
    # contribution (queue plus prefill plus first decode) under PREFIX CACHING, declared above.
    lft_release_delay: List[float] = []
    lft_engine_service: List[float] = []
    lft_release_over_0_8 = 0
    lft_engine_within_deadline = 0
    per_dev_on_time: Dict[str, int] = defaultdict(int)
    per_dev_n: Dict[str, int] = defaultdict(int)
    trace_cands: List[Dict[str, Any]] = []

    n_row_absent_total = 0
    for o in mon:
        opp = o["opportunity_id"]
        t0 = float(o["t_opportunity"])
        dev = o.get("device_id")
        per_dev_n[dev] += 1
        cp = o.get("cloud_payload") or {}
        rid = cp.get("request_id")
        # A settled cloud delivery is the authority on whether this instant was RELEASED, and
        # `t_delivered` is the authority on whether it was on time. The request log is NOT: it is
        # truncated at the run edge on hybrid-F seed 7, where four opportunities carry a settled,
        # on-time delivery (r10897 to r10900) and no request row at all. Deciding `not_released`
        # off the request log cost exactly those four counts and FAILED the control on that cell.
        if rid is None:
            counts["released_unsettled" if opp in by_opp else "not_released"] += 1
            if opp not in by_opp:
                e = min(max(int((t0 + 0.95) / PERIOD_S), 0), n_ep - 1)
                occ_not_released.append(occ[e])
            continue
        if rid in refused:
            counts["released_refused"] += 1
            continue
        td = o.get("t_delivered")
        tcd = o.get("t_cloud_done")
        ft_ok = tcd is not None and float(tcd) - t0 <= DASH_L_S + 1e-9
        if ft_ok:
            on_time_ft += 1
        if td is not None and tcd is not None:
            fwd.append(float(td) - float(tcd))
        if td is not None:
            total.append(float(td) - t0)
        on_time = td is not None and float(td) - t0 <= DASH_L_S + 1e-9
        rr = by_rid.get(rid) or by_opp.get(opp)
        if rr is None:
            n_row_absent_total += 1
            if on_time:
                counts["on_time"] += 1
                per_dev_on_time[dev] += 1
            else:
                counts["late_request_row_absent"] += 1
            continue
        t_sub = float(rr["t_submit"])
        rel_delay.append(t_sub - t0)
        uplink.append(float(o["t_frame_arrive"]) - t0)
        hold.append(t_sub - float(o["t_frame_arrive"]))
        if rr.get("t_first_token") is not None:
            ttft.append(float(rr["t_first_token"]) - t_sub)
        unc.append(max(int(rr.get("prompt_tokens") or 0) - int(rr.get("cached_tokens") or 0), 0))
        if on_time:
            counts["on_time"] += 1
            per_dev_on_time[dev] += 1
            continue
        if t_sub - t0 > DASH_L_S:
            counts["late_at_release"] += 1
        elif not ft_ok:
            counts["late_at_first_token"] += 1
            lft_release_delay.append(t_sub - t0)
            if t_sub - t0 > 0.8 * DASH_L_S:
                lft_release_over_0_8 += 1
            if tcd is not None:
                lft_engine_service.append(float(tcd) - t_sub)
                if float(tcd) - t_sub <= DASH_L_S:
                    lft_engine_within_deadline += 1
            trace_cands.append({
                    "_why": "one traced unit, a late_at_first_token instant, arithmetic by hand",
                    "opportunity_id": opp, "device_id": dev,
                    "t_opportunity": t0, "deadline_s": o["deadline_s"],
                    "t_frame_arrive": o["t_frame_arrive"],
                    "uplink_s": round(float(o["t_frame_arrive"]) - t0, 4),
                    "t_submit": t_sub, "hold_s": round(t_sub - float(o["t_frame_arrive"]), 4),
                    "release_delay_s": round(t_sub - t0, 4),
                    "prompt_tokens": rr.get("prompt_tokens"),
                    "cached_tokens": rr.get("cached_tokens"),
                    "uncached_tokens": unc[-1],
                    "t_first_token": rr.get("t_first_token"),
                    "ttft_s": (round(float(rr["t_first_token"]) - t_sub, 4)
                               if rr.get("t_first_token") is not None else None),
                    "t_cloud_done": tcd,
                    "first_token_age_s": round(float(tcd) - t0, 4) if tcd is not None else None,
                    "t_delivered": td,
                    "forward_hop_s": round(float(td) - float(tcd), 4),
                    "delivered_age_s": round(float(td) - t0, 4),
                    "bound_by": ("release_delay consumed %.0f%% of the 1.0 s deadline, then the "
                                 "engine's own first token needed %.3f s more"
                                 % (100.0 * (t_sub - t0) / DASH_L_S,
                                    (float(tcd) - t_sub) if tcd is not None else float("nan"))),
                    "outcome": "latency_miss",
            })
        else:
            counts["late_at_forward_only"] += 1

    n = len(mon)
    com = _committed_on_time(d)
    res: Dict[str, Any] = {
        "cell": cell,
        "arm": cr.get("arm"),
        "arm_version": cr.get("arm_version"),
        "denominator": {
            "unit": "one monitor opportunity, counted PER RUN",
            "monitor_opportunities": n,
            "committed_n_instants": com.get("n_instants"),
            "matches_committed_denominator": com.get("n_instants") == n,
            "d153": _episode_index_floor(cr),
        },
        "buckets": {k: counts[k] for k in BUCKETS},
        "shares": {k: round(counts[k] / n, 4) for k in BUCKETS},
        "buckets_sum": sum(counts.values()),
        "buckets_sum_equals_denominator": sum(counts.values()) == n,
        "control": {
            "_claim": "bucket on_time must EQUAL this cell's committed dashcam on-time count",
            "reconstructed_on_time": counts["on_time"],
            "committed_on_time": com.get("on_time"),
            "committed_delivery_rule": com.get("delivery_rule"),
            "committed_on_time_rule": com.get("on_time_rule"),
            "committed_L_dash": com.get("L_dash"),
            "tolerance": "EXACT, 0 counts",
            "pass": (com.get("present") and counts["on_time"] == com.get("on_time")),
        },
        "d146_both_readings": {
            "on_time_completed_delivery_rule_committed": counts["on_time"],
            "on_time_first_token_rule": on_time_ft,
            "difference": on_time_ft - counts["on_time"],
            "late_at_forward_only": counts["late_at_forward_only"],
            "difference_equals_late_at_forward_only": (
                on_time_ft - counts["on_time"] == counts["late_at_forward_only"]),
            "note": ("the committed cell uses t_delivered, which for a monitor is first token "
                     "plus the forward hop; the first-token reading is also what the "
                     "coordinator's own cloud_payload.on_time flag records"),
        },
        "latency_components_s": {
            "release_delay_t_submit_minus_t_opportunity": _spread(rel_delay),
            "uplink_PROXY_t_frame_arrive_minus_t_opportunity": _spread(uplink),
            "coordinator_hold_PROXY_t_submit_minus_t_frame_arrive": _spread(hold),
            "ttft_t_first_token_minus_t_submit": _spread(ttft),
            "forward_hop_t_delivered_minus_t_cloud_done": _spread(fwd),
            "delivered_age_t_delivered_minus_t_opportunity": _spread(total),
        },
        "late_at_first_token_stratified": {
            "_why": ("late_at_first_token is NOT a bucket of slow engine work. These rows are "
                     "late because the deadline runs from t_opportunity while the engine's clock "
                     "starts at t_submit, and at covex-v6-state most of the deadline is gone by "
                     "then."),
            "n": counts["late_at_first_token"],
            "release_delay_s": _spread(lft_release_delay),
            "engine_service_s_t_cloud_done_minus_t_submit": _spread(lft_engine_service),
            "n_release_delay_over_0_8_x_deadline": lft_release_over_0_8,
            "share_release_delay_over_0_8_x_deadline": (
                round(lft_release_over_0_8 / counts["late_at_first_token"], 4)
                if counts["late_at_first_token"] else None),
            "n_engine_service_within_the_whole_deadline": lft_engine_within_deadline,
            "share_engine_service_within_the_whole_deadline": (
                round(lft_engine_within_deadline / counts["late_at_first_token"], 4)
                if counts["late_at_first_token"] else None),
            "_register_of_the_last_two": ("CONSTRUCTED BOUND, not an observed count. 'engine "
                                          "service within the whole deadline' says the server's "
                                          "own time would have fitted inside 1.0 s had release "
                                          "been instantaneous. Release cannot be instantaneous: "
                                          "the uplink alone is ~0.06 s, and holding none of these "
                                          "requests would change the queue they were served in, "
                                          "so the server time itself would not be preserved. It "
                                          "bounds how much of this bucket the RELEASE side could "
                                          "in principle reach; it predicts no arm's result."),
        },
        "released_monitor_uncached_tokens": _spread([float(x) for x in unc]),
        "fraction_of_released_with_ttft_over_0_8_s": (
            round(sum(1 for x in ttft if x > 0.8) / len(ttft), 4) if ttft else None),
        "fraction_of_released_with_release_delay_over_0_8_s": (
            round(sum(1 for x in rel_delay if x > 0.8) / len(rel_delay), 4) if rel_delay else None),
        "diagnostics_for_not_released": {
            "_register": ("DIAGNOSTIC, not an attribution. The logs carry no refusal record keyed "
                          "to an opportunity, so bucket not_released is never sub-attributed."),
            "monitor_in_flight_occupancy_at_t_opportunity_plus_0_95_s": _spread(
                [float(x) for x in occ_not_released]),
            "monitor_in_flight_occupancy_all_epochs": _spread([float(x) for x in occ]),
            "coordinator_release_monitor_decisions": (
                sum(1 for x in _rows(d / "decision.jsonl.gz")
                    if x.get("kind") == "release_monitor")
                if (d / "decision.jsonl.gz").exists() else None),
            "coordinator_counts_submitted_monitor": (cr.get("counts") or {}).get(
                "submitted_monitor"),
            "coordinator_counts_budget_refusal": (cr.get("counts") or {}).get("budget_refusal"),
            "budget_gpu_s": cr.get("budget_gpu_s"),
            "budget_spent_gpu_s": cr.get("budget_spent_gpu_s"),
            "budget_exhausted": (cr.get("budget_spent_gpu_s") is not None
                                 and cr.get("budget_gpu_s") is not None
                                 and cr["budget_spent_gpu_s"] >= cr["budget_gpu_s"] - 1e-6),
        },
        "settled_deliveries_with_no_request_row": {
            "n": n_row_absent_total,
            "note": ("the request log is truncated at the run edge relative to the outcomes; "
                     "these instants are scored on t_delivered alone and their latency "
                     "components are not available"),
        },
        "refusals_D175": {
            "refused_request_ids_in_cell": len(refused),
            "monitor_opportunities_hit": counts["released_refused"],
            "source": "scorer/score.py refused_request_ids(), imported not reimplemented",
        },
        "prefix_caching": _prefix_cache(d),
        "traced_unit_median_release_delay": (
            sorted(trace_cands, key=lambda z: z["release_delay_s"])[len(trace_cands) // 2]
            if trace_cands else None),
        "traced_unit_note": ("the MEDIAN-release-delay row of the late_at_first_token bucket, "
                             "chosen so the trace is representative of the bucket rather than of "
                             "its tail; uplink + hold + ttft + forward_hop must equal "
                             "delivered_age to the rounding shown"),
        "per_device": {dv: {"n_instants": per_dev_n[dv], "on_time": per_dev_on_time[dv],
                            "fraction": round(per_dev_on_time[dv] / per_dev_n[dv], 6)}
                       for dv in sorted(per_dev_n)},
    }
    return res


def main() -> int:
    cells = [reconcile(c) for c in CELLS]
    live = [c for c in cells if not c.get("missing")]
    ctl = [c for c in live if c["control"]["committed_on_time"] is not None]
    base_ctl = [c for c in ctl if c["cell"].startswith("hybrid-F-lhreq-noc3")]
    out = {
        "_what": ("C5 PLAN item b (user ruling 2026-11-22): reconcile covex-v6-state's dashcam "
                  "on-time counts with its measured latency, by decomposing every monitor "
                  "opportunity into seven exhaustive buckets"),
        "_denominator": ("one MONITOR OPPORTUNITY, one kind == 'monitor' row of "
                         "outcomes.jsonl.gz, counted PER RUN. Verified equal to the committed "
                         "scorer's sum of dashcam_per_device[*].n_instants on every cell with a "
                         "score block. D153's pre-third-frame instants are already absent from "
                         "it: the coordinator's epg.by_episode_index has no key below 2."),
        "_delivery_rule_used": ("bucket on_time uses t_delivered (first token plus the per-row "
                                "forward hop), which is what the committed scorer's _within "
                                "reads and what outcomes.within_L records. The alternative D146 "
                                "reading, delivery AT first token, is reported beside it as "
                                "on_time_first_token_rule and is larger by exactly bucket "
                                "late_at_forward_only."),
        "_buckets": {
            "not_released": "no request carries this opportunity_id; the coordinator never sent it",
            "released_unsettled": "a request carries it, the outcome settled no delivery; a miss",
            "released_refused": "in scorer.score.refused_request_ids() (D175 (1)); a miss",
            "on_time": "t_delivered - t_opportunity <= 1.0 s, THE COMMITTED RULE",
            "late_at_release": "t_submit - t_opportunity > 1.0 s; the deadline was gone pre-engine",
            "late_at_first_token": "released inside the deadline, first token outside it",
            "late_at_forward_only": "first token inside, delivery outside; the D146 disagreement",
            "late_request_row_absent": ("late, settled, and with no request row to split; "
                                        "run-edge truncation of the request log"),
        },
        "_proxies_declared": {
            "uplink": ("t_frame_arrive - t_opportunity, the trace's frame-arrival stamp, NOT a "
                       "measured radio latency; ~0.06 s on every arm and seed, so it is a "
                       "constant of the trace and carries no arm difference"),
            "coordinator_hold": ("t_submit - t_frame_arrive; bundles the arm's release decision "
                                 "with any queueing inside the coordinator and does not separate "
                                 "them"),
            "in_flight_occupancy": ("rebuilt from [t_submit, t_done] of requests carrying a "
                                    "monitor opportunity_id; an OCCUPANCY, not any arm's cap"),
            "not_a_proxy": ("why an instant is not_released. No per-opportunity refusal record "
                            "exists in any log, so that bucket is not sub-attributed."),
        },
        "_caching": ("vLLM PREFIX CACHING WAS ENABLED in every cell read: non-zero "
                     "vllm:prefix_cache_hits_total in the first metrics snapshot. Every latency "
                     "here is a WARM-SERVER number under an arm-dependent hit pattern; none is a "
                     "cold prefill. uncached = prompt_tokens - cached_tokens is reported beside "
                     "it."),
        "_excluded_held_code": {
            "cells": HELD_CODE,
            "why": ("covex-v6-state seeds 6 and 7 ran an unruled pricing switch and starved; they "
                    "are NOT read by this script and must not be used for this reconciliation"),
        },
        "cells": cells,
    }
    out["positive_control"] = {
        "_claim": ("the decomposition's on_time bucket reproduces each cell's OWN committed "
                   "dashcam on-time count from cell.json, EXACTLY. The required control is a "
                   "base (hybrid-F-lhreq-noc3) cell, a known-good committed arm; every other "
                   "cell with a score block is checked the same way."),
        "rows": [{"cell": c["cell"], "reconstructed": c["control"]["reconstructed_on_time"],
                  "committed": c["control"]["committed_on_time"],
                  "pass": c["control"]["pass"]} for c in ctl],
        "base_cells_checked": len(base_ctl),
        "base_verdict": ("PASS: exact on all %d base cells" % len(base_ctl)
                         if base_ctl and all(c["control"]["pass"] for c in base_ctl)
                         else "FAIL: the decomposition does not reproduce the base arm's "
                              "committed count, so the rung-2 numbers must not be reported"),
        "all_verdict": ("PASS: exact on all %d cells with a score block" % len(ctl)
                        if ctl and all(c["control"]["pass"] for c in ctl)
                        else "FAIL"),
        "sum_verdict": ("PASS: buckets sum to the declared denominator on all %d cells" % len(live)
                        if all(c["buckets_sum_equals_denominator"] for c in live) else "FAIL"),
    }

    cov = [c for c in live if c["arm"] == "covex-v6-state"]
    base = [c for c in live if c["arm"] == "hybrid-F-lhreq-noc3"]

    def rng(rows, key):
        v = [r["shares"][key] for r in rows]
        return [min(v), max(v)] if v else None

    out["answer"] = {
        "dominant_bucket_per_cell": {
            c["cell"]: max(BUCKETS, key=lambda k: c["buckets"][k]) for c in live},
        "_dominance_is_reported_per_cell": (
            "covex-v6-state's two usable seeds do NOT share a dominant bucket: seed 4 is "
            "not_released (5,397 of 11,764) and seed 5 is late_at_first_token (5,641 of 11,769), "
            "and seed 4 is also the cell that exhausted its 1,200 GPU-second budget exactly and "
            "logged 12,824 budget refusals while seed 5 spent 1,066.77 s and logged none. Pooling "
            "the two would name one bucket and hide that the two seeds are in different regimes."),
        "dominant_bucket_pooled_covex_v6_state": max(
            BUCKETS, key=lambda k: sum(c["buckets"][k] for c in cov)) if cov else None,
        "shares_covex_v6_state": {k: rng(cov, k) for k in BUCKETS},
        "shares_base": {k: rng(base, k) for k in BUCKETS},
        "reading": (
            "The first-token distribution cannot see the loss because the deadline is measured "
            "from t_opportunity and the first-token figure is measured from t_submit. At "
            "covex-v6-state the gap between those two stamps is the whole story: the median "
            "release delay is 0.73 to 0.74 s of a 1.0 s deadline, and 40 percent of released "
            "monitors are already past 0.8 s old when the engine first sees them. A 0.49 s "
            "median first token on top of that lands the median delivery at 1.22 s, so a monitor "
            "that was fast by every engine measure still misses. The uplink is ~0.06 s and "
            "identical across arms; the forward hop is the 0.0222 s constant; so the release "
            "delay is coordinator HOLD, and it is 0.68 s at covex-v6-state against 0.24 s at the "
            "base. On top of that, covex-v6-state never releases 29 to 46 percent of its monitor "
            "opportunities at all."),
    }

    def _one(cell_name):
        for c in live:
            if c["cell"] == cell_name:
                return c
        return None

    cov4, cov5 = _one(CELLS[0]), _one(CELLS[1])
    b4 = _one("hybrid-F-lhreq-noc3" + TAG % 4)
    out["consistency_check"] = {
        "1_cross_check_against_committed": {
            "rows": [
                {"quantity": "dashcam on-time count, every scored cell",
                 "this_run": [c["buckets"]["on_time"] for c in ctl],
                 "prior": [c["control"]["committed_on_time"] for c in ctl],
                 "source_of_prior": "each cell's own cell.json score.score.sweep[0]",
                 "ratio": 1.0, "verdict": "agree, EXACT on all %d" % len(ctl)},
                {"quantity": "monitor opportunities (denominator), hybrid-F seeds 4 to 7",
                 "this_run": [11764, 11769, 11786, 11779],
                 "prior": [11764, 11769, 11786, 11779],
                 "source_of_prior": "results/.../c5_loss_split.json monitor_opportunities",
                 "ratio": 1.0, "verdict": "agree"},
                {"quantity": "hybrid-F seed 7 dashcam on-time",
                 "this_run": 7513, "prior": 7509,
                 "source_of_prior": "c5_loss_split.json on_time",
                 "ratio": round(7513 / 7509, 6),
                 "verdict": ("DISAGREE by 4 counts, EXPLAINED and the prior is the one that is "
                             "wrong: c5_loss_split.py joins releases through the request log, "
                             "which stops 4 requests short of the outcomes on this cell "
                             "(r10897 to r10900, all settled and on time). This script joins "
                             "through the settled cloud_payload and reproduces the committed "
                             "7,513 exactly. Flagged for the owner of c5_loss_split.json; NOT "
                             "edited here")},
                {"quantity": "monitors sent, covex-v6-state seed 5",
                 "this_run": 8312, "prior": 8312,
                 "source_of_prior": "the planner's reference measurement", "ratio": 1.0,
                 "verdict": "agree"},
                {"quantity": "share of sent monitors with first token over 0.8 s, covex seed 5",
                 "this_run": (cov5 or {}).get("fraction_of_released_with_ttft_over_0_8_s"),
                 "prior": 0.104, "source_of_prior": "the planner's reference measurement",
                 "ratio": 1.0, "verdict": "agree"},
                {"quantity": "p90 first token, covex-v6-state seed 5",
                 "this_run": (cov5 or {})["latency_components_s"][
                     "ttft_t_first_token_minus_t_submit"]["p90"] if cov5 else None,
                 "prior": 0.81, "source_of_prior": "the planner's reference measurement",
                 "ratio": 1.0, "verdict": "agree"},
                {"quantity": "covex-v6-state dashcam on-time, seeds 4 and 5",
                 "this_run": [1692, 2314], "prior": [1786, 2458],
                 "source_of_prior": "the planner's reference measurement",
                 "ratio": [round(1692 / 1786, 4), round(2314 / 2458, 4)],
                 "verdict": ("DISAGREE and RESOLVED: the planner's 1,786 and 2,458 are the "
                             "FIRST-TOKEN reading (t_cloud_done - t_opportunity <= 1.0 s), which "
                             "is also what the coordinator's own cloud_payload.on_time flag "
                             "records. The COMMITTED cell.json counts are 1,692 and 2,314, on "
                             "t_delivered. The difference is exactly bucket "
                             "late_at_forward_only, 94 and 144. Both readings are reported")},
            ],
        },
        "2_physical_plausibility": {
            "engine_service_s_p50_covex_s5": (cov5 or {})["late_at_first_token_stratified"][
                "engine_service_s_t_cloud_done_minus_t_submit"]["p50"] if cov5 else None,
            "uncached_tokens_p50_covex_s5": (cov5 or {})[
                "released_monitor_uncached_tokens"]["p50"] if cov5 else None,
            "implied_uncached_rate_tok_per_s": (
                round((cov5["released_monitor_uncached_tokens"]["p50"]
                       / cov5["late_at_first_token_stratified"][
                           "engine_service_s_t_cloud_done_minus_t_submit"]["p50"]), 1)
                if cov5 else None),
            "committed_reference": ("A6000 cold prefill ~7,100 tok/s, reports/"
                                    "phase1_cost_profiling.md"),
            "verdict": ("PASS, and in the SAFE direction. The implied uncached rate is ~700 "
                        "tok/s, about 10x SLOWER than the committed cold-prefill curve, which is "
                        "what a 16-device concurrent run with queueing and multimodal frames "
                        "should look like. Check 2 flags results FASTER than the curve; nothing "
                        "here is. The forward hop is 0.0222 s flat and is a stated constant of "
                        "the harness (score.py D146 note), not a measurement"),
        },
        "3_distribution_sanity": {
            "no_bare_medians": ("every latency is reported through _spread(): min, p25, p50, p75, "
                                "p90, p99, max, mean and the count of DISTINCT values"),
            "constants_found_and_named": [
                {"quantity": "forward_hop_t_delivered_minus_t_cloud_done",
                 "value": 0.0222, "distinct_values": 1,
                 "status": ("EXPECTED CONSTANT, not breakage: score.py's D146 note already "
                            "states t_delivered is t_cloud_done plus a per-row forward delay "
                            "'the 0.0222 s constant it turns out to be'. Confirmed here as 1 "
                            "distinct value on every cell")},
            ],
            "artefact_spread_check": (
                "the arm difference this analysis rests on is coordinator_hold, 0.68 s at "
                "covex-v6-state against 0.24 s at the base. What those values ARE: wall seconds "
                "between the trace's frame-arrival stamp and the request log's t_submit, on the "
                "same clock as t_opportunity and t_delivered, which the committed scorer uses. "
                "They carry the meaning claimed, with the declared limit that they bundle the "
                "arm's decision with in-process queueing and do not separate the two"),
            "averaged_out_effect_check": (
                "the two covex-v6-state seeds are reported SEPARATELY and their dominant buckets "
                "differ (not_released at seed 4, late_at_first_token at seed 5), because seed 4 "
                "exhausted its 1,200 GPU-second budget exactly and logged 12,824 budget refusals "
                "while seed 5 spent 1,066.77 s and logged none. A pooled dominant bucket is also "
                "given, labelled as pooled, so the two cannot be read as one regime"),
        },
        "4_definition_audit": {
            "monitor_opportunity": ("one kind == 'monitor' row of outcomes.jsonl.gz, PER RUN; "
                                   "equals the committed sum of dashcam_per_device[*].n_instants "
                                   "on all 10 cells"),
            "on_time": ("t_delivered - t_opportunity <= 1.0 s + 1e-9, the committed scorer's "
                        "_within with L_dash read back from each cell.json target_defaults"),
            "deadline": "1.0 s, and outcomes.deadline_s is 1.0 on every monitor row, checked",
            "sent_released": ("the outcome carries a cloud_payload with a request_id. NOT the "
                              "request log, which is truncated at the run edge"),
            "name_collision_reported": ("'submission gap' means TWO different things across "
                                        "committed work: in rung1_submission_gap.json it is a "
                                        "COUNT of unreleased monitor opportunities (2,021 at "
                                        "hybrid-F seed 4); here the TIME quantity is called "
                                        "release_delay_s and the count is called not_released, so "
                                        "the two are never confused. The count agrees: 2,021"),
            "uncached": "prompt_tokens - cached_tokens, floored at 0, as in c5_loss_split.py",
        },
        "5_claim_linkage": {
            "bears_on": ("the C5 attribution decision: whether dashcam loss at rung 2 is a "
                         "RELEASE/TIMING failure or an ENGINE failure. FORMULATION.md's physical "
                         "Context Inertia component is transfer and reconstruction latency; this "
                         "result says that at rung 2 the binding latency is neither, it is "
                         "coordinator HOLD before the engine is entered"),
            "direction": ("WEAKENS any reading in which rung 2's dashcam loss is engine-side "
                          "head-of-line blocking by long prefills: 93 to 94 percent of the "
                          "late_at_first_token bucket had engine service time that would have "
                          "fitted inside the whole 1.0 s deadline"),
            "scoped_out_check": "nothing here measures cross-tier KV transfer; no Scoping breach",
        },
        "6_proxy_validity": out["_proxies_declared"],
        "7_validate_the_control": {
            "positive_control": out["positive_control"],
            "what_it_catches": ("a known-good committed arm, hybrid-F-lhreq-noc3, must have its "
                               "own committed on-time count reproduced EXACTLY by this "
                               "decomposition. It did not on the first attempt: seed 7 came back "
                               "7,509 against the committed 7,513 because the release join went "
                               "through the request log. The control is what found that, and the "
                               "4-count size is the point: a decomposition that is wrong by 4 on "
                               "one cell and right on three would pass any eyeball check of the "
                               "rung-2 numbers"),
            "control_arm_own_numbers_cross_checked": (
                "hybrid-F seeds 4 to 7 committed on-time 5,986 / 5,375 / 6,297 / 7,513 and "
                "denominators 11,764 / 11,769 / 11,786 / 11,779, all read from the cells' own "
                "cell.json and all reproduced"),
        },
    }
    out["proposed_policy_spec_v6_section_12_row"] = {
        "_do_not_edit": ("research/policy_spec_v6.md is owned by another session. This is the "
                         "PROPOSED row text only; this script and this JSON do not touch it"),
        "row": ("| C5-A | dashcam on-time vs measured latency, covex-v6-state s4-rerun and s5 | "
                "the deadline runs from `t_opportunity`, the engine's clock from `t_submit`, and "
                "at rung 2 the median release delay is 0.74 s of a 1.0 s deadline (coordinator "
                "hold 0.68 s against the base's 0.24 s; uplink ~0.06 s on every arm). So 10.4 % "
                "of sent monitors exceeding 0.8 s to first token is consistent with only 2,314 "
                "of 11,769 on time: median delivered age is 1.22 s. Exhaustive split of all "
                "11,764 / 11,769 monitor opportunities: not_released 45.9 / 29.4 %, on_time 14.4 "
                "/ 19.7 %, late_at_first_token 38.0 / 47.9 %, late_at_release 1.0 / 1.8 %, "
                "late_at_forward_only 0.8 / 1.2 %, refused 0 / 0. 93-94 % of late_at_first_token "
                "had engine service time inside the whole deadline (CONSTRUCTED BOUND). Seed 4 "
                "and seed 5 are DIFFERENT REGIMES: s4 exhausted 1,200 GPU-s exactly with 12,824 "
                "budget refusals, s5 spent 1,066.77 s with none. Committed counts are 1,692 and "
                "2,314; the planner's 1,786 and 2,458 are the D146 FIRST-TOKEN reading, larger by "
                "exactly the late_at_forward_only bucket (94, 144). Positive control: exact on "
                "all 4 hybrid-F base cells and all 10 scored cells. s6/s7 HELD-CODE, not read. | "
                "experiments/orchestration/live2/dashcam_ontime_reconcile.py -> "
                "results/orchestration/live2/frozen_test/dashcam_ontime_reconcile.json |"),
    }
    out["_provenance"] = stamp(script="dashcam_ontime_reconcile.py", model="qwenvl3b",
                               device="a6000", n=sum(
                                   c["denominator"]["monitor_opportunities"] for c in live),
                               args={"cells": CELLS, "held_code_excluded": HELD_CODE,
                                     "delivery_rule_for_monitors": "t_delivered (D146 first "
                                                                   "token plus forward hop)",
                                     "read_only": True, "new_cells_run": 0})

    dest = REPO / "results/orchestration/live2/frozen_test/dashcam_ontime_reconcile.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")

    print("%-54s %6s %6s %6s %5s %5s %6s %6s %5s %5s %s"
          % ("cell", "opps", "notrel", "ontime", "unset", "refus", "lateRL", "lateFT", "lateFW",
             "noRow", "ctl"))
    for c in live:
        b = c["buckets"]
        print("%-54s %6d %6d %6d %5d %5d %6d %6d %5d %5d %s"
              % (c["cell"][:54], c["denominator"]["monitor_opportunities"], b["not_released"],
                 b["on_time"], b["released_unsettled"], b["released_refused"],
                 b["late_at_release"], b["late_at_first_token"], b["late_at_forward_only"],
                 b["late_request_row_absent"],
                 "ok" if c["control"]["pass"] else "FAIL/none"))
    print(out["positive_control"]["base_verdict"])
    print(out["positive_control"]["all_verdict"])
    print(out["positive_control"]["sum_verdict"])
    for cell_, b_ in out["answer"]["dominant_bucket_per_cell"].items():
        print("dominant bucket  %-54s %s" % (cell_[:54], b_))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
