#!/usr/bin/env python3
"""Why D179 share-based admission loses robot (recall) questions: per-skip diagnosis.

READ-ONLY. Reads only COMMITTED cells, through `git show <rev>:<path>`, so the shared worktree's
dirty files are never touched. No cell is run.

THE QUESTION (user ruling, flash addendum 13). Pre-registered check 2 (retain at least 90 percent
of the committed rung-2 robot on-time gain over base) FAILS at every seed: s4 30 percent, s5 56
percent. Checks 1 (alert) and 3 (assistance) pass. The loss is in the SKIPS, not in lateness.

WHAT IS AND IS NOT RECOVERABLE FROM A COMMITTED CELL, stated before any number is reported.
`coordinator.py:1258` appends the full per-skip record - `uncached`, `queued_uncached_ahead`,
`est_first_token_s`, `remaining_s`, `readiness`, `est_tokens` - to `self.release_infeasible_events`,
and that list is written to NO file: `_result()` does not carry it and no run artefact holds it.
`_share_events` (coordinator.py:1539), which carries the per-gate-call `uncached` and `w_by_type`,
is likewise in-memory only. Both are therefore ABSENT from every committed cell, and the per-skip
table below is a RECONSTRUCTION. Each reconstructed column names its proxy in PROXIES.

Usage:
  python d179_recall_skip_diagnosis.py [--rev origin/main] [--seeds 4,5] [--out <path>]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

# The git repository the committed cells are read from. Overridable because this box keeps the
# live2 tree and the git repository in different places, and every read here goes through
# `git show <rev>:<path>` rather than through the working tree.
REPO = Path(os.environ.get("D179_REPO") or Path(__file__).resolve().parents[3])
RUNS = "results/orchestration/live2/frozen_test/runs"
CELL_SUFFIX = "_1200s_h27_3t_L3_epg_rq30"
ARMS = {"base": "hybrid-F-lhreq-noc3", "uo": "covex-v6-state-uo",
        "shares": "covex-v6-state-shares"}

# the committed D162 first-token fit, IMPORTED, never retyped (one price source, 2026-11-21)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d162_price as DP                                                 # noqa: E402
import share_capacity as SCAP                                           # noqa: E402

# "materially over-predicted": the predicted uncached is at least this many times the engine's own
# uncached count for the same opportunity. 2.0 is the same threshold CLAUDE.md's consistency check 1
# uses for "a disagreement that must be investigated", so it is not a tuned number; the reported
# distribution is far above it (median 15.6x at s4, 13.9x at s5) and the classification is not
# sensitive to the choice, which is reported.
MISPRICE_FACTOR = 2.0

RECALL_OWN_SHARE = SCAP.FLOORS_TOKENS["recall"] + SCAP.FLEXIBLE_TOKENS / 3.0
ASST_OWN_SHARE = SCAP.FLOORS_TOKENS["assistance"] + SCAP.FLEXIBLE_TOKENS / 3.0

PROXIES = [
    {"column": "est_tokens_at_skip",
     "proxy": "cloud_payload.tokens_charged of the SAME opportunity in covex-v6-state-uo",
     "actually_measures": ("coordinator.py:1854 writes tokens_charged = int(sub.est_tokens) and "
                           "_submit_recall passes est_tokens=tokens = "
                           "tokens_for_representation(rep), which is est_tokens for every "
                           "representation except RECENT. So this is the session's est_tokens at "
                           "uo's release instant, not at the shares arm's skip instant."),
     "valid_for_the_claim": ("YES for the size question. The two arms replay the SAME trace at the "
                             "same seed, est_tokens is a trace property (history_preload / "
                             "history_append), and uo's release instant is within a few seconds of "
                             "the shares skip. Reported with |t_uo_release - t_skip| so a reader "
                             "can see the lag. Rows where uo never released are reported as "
                             "est_tokens unknown and are never dropped.")},
    {"column": "readiness_at_skip",
     "proxy": "the last residency.jsonl row for that session before t_skip",
     "actually_measures": ("the coordinator's BELIEVED tier. residency.jsonl is written at build "
                           "completion (coordinator.py:1788) and at session_end "
                           "(coordinator.py:591), and the belief is promoted to gpu at exactly one "
                           "place, coordinator.py:1786, inside that same completion handler. So "
                           "every belief promotion is logged."),
     "valid_for_the_claim": ("YES, with one hole: counts.belief_corrections_changed = 9 and "
                             "belief_to_gpu = 9 at s4, the D172 telemetry corrector, which does "
                             "not write a residency row. At most 9 session-events per cell could "
                             "be promoted without appearing here, against 70 skips. Reported as a "
                             "bound, not ignored. residency_readiness() also returns HOST-WARM "
                             "when measured_tier == 'host'; no OFFLOAD_TO_HOST action is counted "
                             "in any of these cells, so that branch is unreachable here.")},
    {"column": "built_tokens_at_skip",
     "proxy": ("cumulative piece_tokens of release_piece decisions for that session whose request "
               "row's t_done is before t_skip"),
     "actually_measures": ("built_tokens is incremented at coordinator.py:1777 inside _settle, so "
                           "completion time is the right clock. Reset to 0 at session_end "
                           "(cstate.py:295) and history_preload (cstate.py:315), both honoured."),
     "valid_for_the_claim": "YES; this is the quantity itself, re-derived from its own write site."},
    {"column": "oversize_wait_s",
     "proxy": "t_skip minus the first share_hold decision row carrying this opportunity id as key",
     "actually_measures": ("the time from the FIRST share-admission hold of this instant to the "
                           "skip. _share_ok logs one share_hold row per DISTINCT held instant "
                           "(coordinator.py:1496-1509) and does NOT log the hold REASON, so this "
                           "is time-held-by-the-share-gate, not time-held-by-the-oversize-rule "
                           "specifically."),
     "valid_for_the_claim": ("PARTIALLY. counts.share_reason_* are run totals in ITEM-PERIODS, not "
                             "per instant, so the reason cannot be attributed to an instant from a "
                             "committed cell. At s4 oversize_wait_for_own_type is 430 of the 1,504 "
                             "+ 430 + 243 + 58 + 262 denied item-periods across all three types; "
                             "the share-gate hold is reported as a whole and the oversize share of "
                             "it is NOT claimed. Marked unvalidated.")},
    {"column": "queued_uncached_ahead_at_skip",
     "proxy": "NONE. Not reconstructed; bounded instead.",
     "actually_measures": ("_uncached_in_flight is incremented with the PREDICTED uncached of every "
                           "monitor, recall, piece and touch submission and decremented at settle; "
                           "the monitor charge is B.epg_prompt_tokens(n_new) and n_new is not in "
                           "any committed log, so the series cannot be replayed exactly."),
     "valid_for_the_claim": ("The bound is exact and is what the classification uses: the re-check "
                             "refused iff b0 + b1*u + b2*q > remaining_s, so if b0 + b1*u alone "
                             "already exceeds remaining_s the SIZE PREDICTION decided it and the "
                             "queue is irrelevant. That split needs no value of q.")},
    {"column": "uo_engine_uncached",
     "proxy": "prompt_tokens - cached_tokens on uo's request row for the same opportunity id",
     "actually_measures": "the engine's own report of what it had to prefill.",
     "valid_for_the_claim": ("YES for 'would it have fitted'. It is the engine's measurement, not a "
                             "prediction. It is NOT the same quantity as the policy's predicted u: "
                             "u is est_tokens (a trace estimate) and prompt_tokens is the real "
                             "tokenised prompt including the question, the options and the image "
                             "placeholders. The two are compared as SIZES, with that difference "
                             "stated.")},
]


def git_show(rev: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"],
                          check=True, stdout=subprocess.PIPE).stdout


def load_cell(rev: str, cell: str) -> Dict[str, Any]:
    base = f"{RUNS}/{cell}"
    out: Dict[str, Any] = {"cell": cell}
    out["cell_json"] = json.loads(git_show(rev, f"{base}/cell.json"))
    out["coord"] = json.loads(git_show(rev, f"{base}/coordinator_result.json"))
    for name in ("decision", "outcomes", "request"):
        raw = gzip.decompress(git_show(rev, f"{base}/{name}.jsonl.gz")).decode()
        rows, bad = [], 0
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:                                            # noqa: BLE001
                bad += 1
        out[name] = rows
        out[name + "_unparsable_lines"] = bad
    res = git_show(rev, f"{base}/residency.jsonl").decode()
    out["residency"] = [json.loads(x) for x in res.splitlines() if x.strip()]
    return out


def session_of_note(note: Optional[str]) -> Optional[str]:
    if not note or not str(note).startswith("session="):
        return None
    return str(note)[len("session="):]


def apply_committed_delivery_rules(c: Dict[str, Any]) -> Dict[str, Any]:
    """The two rewrites the COMMITTED scorer applies to `outcomes` before anything reads
    `t_delivered` (scorer/score.py:539-579), re-applied here so this reader's on-time count is the
    scorer's and not a near-miss of it.

    D144: a refused request's cloud delivery is nulled. D146, the DEFAULT since 2026-11-20:
    a recall is delivered at generation COMPLETION, so t_delivered becomes the request's t_done
    plus the same per-row forward delay the first-token stamp carried.

    Without the D146 pass this reader counted uo's robot pool at 120 of 132 at s4 against the
    committed 118, and 118 of 127 at s5 against the committed 115. Validating the CONTROL arm's
    own number against its committed value is what caught it; an arm-versus-arm check could not
    have, because both arms were read the same wrong way."""
    reqs = c["request"]
    refused = set()
    for r in reqs:
        hs = r.get("http_status")
        if hs is not None:
            try:
                if int(hs) != 200:
                    refused.add(r.get("request_id"))
            except (TypeError, ValueError):
                refused.add(r.get("request_id"))
            continue
        if not r.get("prompt_tokens") and not r.get("output_tokens"):
            refused.add(r.get("request_id"))
    n144 = 0
    for o in c["outcomes"]:
        cp = o.get("cloud_payload") or {}
        if cp.get("request_id") in refused:
            o["t_delivered"] = None
            o["cloud_payload"] = None
            o["d144_failed_request"] = True
            n144 += 1
    done = {str(r["opportunity_id"]): float(r["t_done"]) for r in reqs
            if r.get("opportunity_id") and r.get("t_done") is not None}
    n146 = 0
    for o in c["outcomes"]:
        if o.get("kind") != "recall" or o.get("t_delivered") is None:
            continue
        oid = str(o["opportunity_id"])
        if o.get("t_cloud_done") is None or oid not in done:
            continue
        o["t_delivered_first_token"] = o["t_delivered"]
        o["t_delivered"] = done[oid] + (float(o["t_delivered"]) - float(o["t_cloud_done"]))
        o["delivery_rule"] = "completion"
        n146 += 1
    return {"d144_nulled": n144, "d146_rewritten_to_completion": n146,
            "refused_request_ids": len(refused)}


def build_indexes(c: Dict[str, Any]) -> Dict[str, Any]:
    """Per-cell lookups. Joins are on opportunity id throughout (the held instant travels in
    `opportunity_ids`; `key` is accepted by _log_decision and never written into the record, so
    rec["key"] does not exist and is never read here)."""
    req_by_opp: Dict[str, Dict[str, Any]] = {}
    req_by_decision: Dict[str, Dict[str, Any]] = {}
    for r in c["request"]:
        if r.get("opportunity_id"):
            req_by_opp[str(r["opportunity_id"])] = r
        if r.get("decision_id"):
            req_by_decision[str(r["decision_id"])] = r
    out_by_opp = {str(o["opportunity_id"]): o for o in c["outcomes"]}

    # built_tokens(session, t): piece completions, plus the resets
    piece_events: Dict[str, List[Any]] = defaultdict(list)
    for d in c["decision"]:
        if d.get("kind") != "release_piece":
            continue
        sid = session_of_note(d.get("note"))
        rq = req_by_decision.get(str(d.get("decision_id") or ""))
        if sid is None or rq is None or rq.get("t_done") is None:
            continue
        piece_events[sid].append((float(rq["t_done"]), int(d.get("piece_tokens") or 0)))
    for sid in piece_events:
        piece_events[sid].sort()

    # belief timeline per session (residency rows are written at the only promotion site)
    belief: Dict[str, List[Any]] = defaultdict(list)
    for r in c["residency"]:
        belief[str(r["session_id"])].append((float(r["t"]), str(r["believed_tier"])))
    for sid in belief:
        belief[sid].sort()

    # first share_hold instant per opportunity id
    hold_first: Dict[str, float] = {}
    hold_n: Dict[str, int] = defaultdict(int)
    for d in c["decision"]:
        if d.get("kind") != "share_hold":
            continue
        for k in (d.get("opportunity_ids") or ()):
            k = str(k)
            hold_n[k] += 1
            if k not in hold_first:
                hold_first[k] = float(d["t"])

    rel_recall_by_opp: Dict[str, Dict[str, Any]] = {}
    for d in c["decision"]:
        if d.get("kind") == "release_recall" and d.get("opportunity_ids"):
            rel_recall_by_opp[str(d["opportunity_ids"][0])] = d
    return dict(req_by_opp=req_by_opp, req_by_decision=req_by_decision, out_by_opp=out_by_opp,
                piece_events=dict(piece_events), belief=dict(belief), hold_first=hold_first,
                hold_n=dict(hold_n), rel_recall_by_opp=rel_recall_by_opp)


def built_at(ix: Dict[str, Any], sid: str, t: float) -> int:
    return sum(tok for (td, tok) in ix["piece_events"].get(sid, ()) if td < t)


def readiness_at(ix: Dict[str, Any], sid: str, t: float) -> str:
    tier = "cold"
    for (tt, tr) in ix["belief"].get(sid, ()):
        if tt <= t:
            tier = tr
        else:
            break
    return {"gpu": "GPU-WARM", "host": "HOST-WARM", "cold": "COLD"}[tier]


def skips_of(c: Dict[str, Any], ix: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The release_infeasible decision rows that are RECALL-path skips.

    The recall path passes session_id, which _log_decision renders as note="session=<id>"; the
    alert path (coordinator.py:947) passes none, so note is null there. The device prefix from the
    outcomes row is what finally separates robot (recall) from assistance, which is the same
    discriminator share_admission.PREFIX_TO_TYPE and release_recheck.PREFIX_TO_TYPE use."""
    out = []
    for d in c["decision"]:
        if d.get("kind") != "release_infeasible":
            continue
        sid = session_of_note(d.get("note"))
        if sid is None:
            continue                                     # alert path: no session_id is passed
        opps = [str(x) for x in (d.get("opportunity_ids") or ())]
        if not opps:
            continue
        opp = opps[0]
        o = ix["out_by_opp"].get(opp)
        dev = (o or {}).get("device_id") or ""
        qtype = {"robo": "recall", "asst": "assistance"}.get(dev[:4])
        out.append(dict(opportunity_id=opp, t_skip=float(d["t"]), session_id=sid,
                        device_id=dev, qtype=qtype,
                        t_event=(None if o is None else float(o["t_opportunity"])),
                        deadline_s=(None if o is None else float(o["deadline_s"]))))
    return out


def fix_input_probe(c: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Would the PROPOSED fix have had an input at each mispriced skip, and would it have helped?

    The fix is to read the engine's own last-reported prefix for the session instead of
    `built_tokens` alone. That quantity already exists on the session: `engine_actions.py:358`
    writes `session.last_telemetry_cached_tokens = ct` on every completed request with a session
    (reached from coordinator.py:1666), and `coordinator.py:1673-1674` restores only `belief` and
    `last_touch_s` when belief-apply is off, so the field survives on every arm. It is read
    nowhere in the pricing path, which makes it ABSENT in CLAUDE.md's sense.

    This probe reconstructs that field from the SHARES cell's own request log - the last completed
    request on the same session before the skip - and reports (i) how often it exists and is
    non-zero and (ii) how often the size term alone would then fit the slack. It is a BOUND on the
    fix, not a measurement of it: the real field also moves with requests this reconstruction
    cannot see, and the queue term still applies on top of the size term, so the second figure is
    an upper bound on what the fix recovers through the size channel alone.
    """
    by_sess: Dict[str, List[Any]] = defaultdict(list)
    for r in c["request"]:
        if r.get("session_id") and r.get("t_done") is not None \
                and r.get("cached_tokens") is not None:
            by_sess[str(r["session_id"])].append((float(r["t_done"]), int(r["cached_tokens"])))
    for k in by_sess:
        by_sess[k].sort()
    sel = [r for r in rows if r["klass"] == "a_MISPRICED_SIZE"]
    avail, fits, cts = 0, 0, []
    for r in sel:
        hist = [ct for (t, ct) in by_sess.get(r["session_id"], ()) if t < r["t_skip"]]
        last = hist[-1] if hist else 0
        cts.append(last)
        if last > 0:
            avail += 1
        prefix = max(int(r["built_tokens_at_skip"]), last)
        u = max(int(r["est_tokens_at_skip"] or 0) - prefix, 0)
        if DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(u) <= (r["remaining_s"] or 0.0):
            fits += 1
    return {
        "class_a_skips": len(sel),
        "fix_input_present_and_nonzero": avail,
        "reconstructed_last_reported_cached_tokens": _dist(cts),
        "built_tokens_at_skip": _dist([r["built_tokens_at_skip"] for r in sel]),
        "size_term_alone_would_fit_the_slack": fits,
        "register": ("an UPPER BOUND on what the size channel recovers, not a measurement: the "
                     "queue term still applies on top, and the reconstruction of the field lags "
                     "the engine's real cache because the history grows between requests"),
    }


def analyse_seed(rev: str, seed: int) -> Dict[str, Any]:
    a_rev = rev
    cells = {k: load_cell(rev, f"{v}_n16_s{seed}{CELL_SUFFIX}") for k, v in ARMS.items()}
    delivery = {k: apply_committed_delivery_rules(v) for k, v in cells.items()}
    ix = {k: build_indexes(v) for k, v in cells.items()}
    sh, uo = cells["shares"], cells["uo"]
    ixs, ixu = ix["shares"], ix["uo"]

    head = {}
    for k, c in cells.items():
        z = c["cell_json"]["score"]["score"]["sweep"][0]
        head[k] = {"robot_pool_on_time": z["robot_pool_on_time"],
                   "robot_pool_n": z["robot_pool_n"],
                   "robot_pool_fraction": z["robot_pool_fraction"],
                   "ss_pool_on_time": z["ss_pool_on_time"], "ss_pool_n": z["ss_pool_n"],
                   "dashcam_all_meet": z["dashcam_all_meet"],
                   "run_valid": c["cell_json"]["run_valid"],
                   "arm": c["coord"]["arm"]}
    gain_uo = head["uo"]["robot_pool_on_time"] - head["base"]["robot_pool_on_time"]
    gain_sh = head["shares"]["robot_pool_on_time"] - head["base"]["robot_pool_on_time"]
    check2 = {"base": head["base"]["robot_pool_on_time"], "uo": head["uo"]["robot_pool_on_time"],
              "shares": head["shares"]["robot_pool_on_time"],
              "uo_gain_over_base": gain_uo, "shares_gain_over_base": gain_sh,
              "retained_fraction": (round(gain_sh / gain_uo, 4) if gain_uo else None),
              "loss_questions": head["uo"]["robot_pool_on_time"]
              - head["shares"]["robot_pool_on_time"]}

    rows = []
    for s in skips_of(sh, ixs):
        opp, t = s["opportunity_id"], s["t_skip"]
        sid = s["session_id"]
        remaining = (None if s["t_event"] is None
                     else s["t_event"] + s["deadline_s"] - t)
        built = built_at(ixs, sid, t)
        ready = readiness_at(ixs, sid, t)
        # est_tokens: uo's tokens_charged for the SAME opportunity (declared proxy)
        uo_out = ixu["out_by_opp"].get(opp)
        uo_cp = (uo_out or {}).get("cloud_payload") or None
        est = None
        uo_rep = None
        if uo_cp:
            est = int(uo_cp.get("tokens_charged") or 0) or None
            uo_rep = uo_cp.get("representation")
        uo_req = ixu["req_by_opp"].get(opp)
        uo_unc = None
        uo_cached = None
        uo_prompt = None
        uo_t_sub = None
        if uo_req:
            uo_prompt = int(uo_req.get("prompt_tokens") or 0)
            uo_cached = int(uo_req.get("cached_tokens") or 0)
            uo_unc = max(uo_prompt - uo_cached, 0)
            uo_t_sub = (None if uo_req.get("t_submit") is None
                        else float(uo_req["t_submit"]))
        # ON TIME BY THE COMMITTED SCORER'S OWN RULE, scorer/score.py:687-689:
        # t_delivered - t_opportunity <= L + 1e-9, with L_rob = 3.0 and L_ss = 2.0 from the
        # cell's own sweep row. cloud_payload.on_time is kept beside it as a cross-check because
        # it is the COORDINATOR's view and the two disagree where a refused request's cloud answer
        # does not stand (scorer/score.py:484-522).
        uo_on_time = None
        if uo_out is not None and uo_out.get("t_delivered") is not None:
            uo_on_time = bool(float(uo_out["t_delivered"]) - float(uo_out["t_opportunity"])
                              <= float(uo_out["deadline_s"]) + 1e-9)
        elif uo_out is not None:
            uo_on_time = False
        uo_on_time_coordinator = None if uo_cp is None else uo_cp.get("on_time")

        pred_u = None
        if est is not None:
            pred_u = est if ready == "COLD" else max(est - built, 0)
        own_share = RECALL_OWN_SHARE if s["qtype"] == "recall" else ASST_OWN_SHARE
        # the exact decomposition: the re-check refused iff b0 + b1*u + b2*q > remaining_s,
        # so size alone decided it iff b0 + b1*u > remaining_s (no value of q needed)
        size_alone_s = (None if pred_u is None
                        else DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(pred_u))
        size_alone_infeasible = (None if (size_alone_s is None or remaining is None)
                                 else bool(size_alone_s > remaining))
        eng_size_alone_s = (None if uo_unc is None
                            else DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(uo_unc))
        eng_size_alone_infeasible = (None if (eng_size_alone_s is None or remaining is None)
                                     else bool(eng_size_alone_s > remaining))
        q_needed = None
        if size_alone_s is not None and remaining is not None and not size_alone_infeasible:
            q_needed = (remaining - size_alone_s) / DP.PER_QUEUE_S
        hold_t = ixs["hold_first"].get(opp)
        rows.append(dict(
            seed=seed, opportunity_id=opp, device_id=s["device_id"], qtype=s["qtype"],
            session_id=sid, t_event=s["t_event"], t_skip=t, deadline_s=s["deadline_s"],
            remaining_s=(None if remaining is None else round(remaining, 6)),
            readiness_at_skip=ready, built_tokens_at_skip=built,
            est_tokens_at_skip=est, predicted_u=pred_u,
            own_share_tokens=round(own_share, 1),
            predicted_u_over_own_share=(None if pred_u is None
                                        else round(pred_u / own_share, 4)),
            size_alone_first_token_s=(None if size_alone_s is None else round(size_alone_s, 6)),
            size_alone_already_infeasible=size_alone_infeasible,
            queued_uncached_ahead_needed_for_refusal=(None if q_needed is None
                                                      else round(q_needed, 1)),
            share_hold_first_t=hold_t,
            oversize_wait_s=(None if hold_t is None else round(t - hold_t, 6)),
            share_hold_periods_for_this_instant=ixs["hold_n"].get(opp),
            # TWO joins, named apart, because they answer different questions and a row can
            # have one and not the other. `uo_joined` is "uo saw this same opportunity at all"
            # (its outcomes row exists), which is what decides whether uo served it; the
            # REQUEST join is what supplies the engine-reported uncached count, and uo has no
            # request row for an opportunity it never released. No row is dropped for either.
            uo_joined=bool(uo_out is not None),
            uo_request_joined=bool(uo_req is not None),
            uo_t_submit=uo_t_sub,
            uo_release_lag_s=(None if uo_t_sub is None else round(uo_t_sub - t, 3)),
            uo_representation=uo_rep,
            uo_prompt_tokens=uo_prompt, uo_cached_tokens=uo_cached,
            uo_engine_uncached=uo_unc,
            uo_engine_size_alone_first_token_s=(None if eng_size_alone_s is None
                                                else round(eng_size_alone_s, 6)),
            uo_engine_size_alone_infeasible=eng_size_alone_infeasible,
            uo_on_time=uo_on_time, uo_on_time_coordinator_view=uo_on_time_coordinator,
            predicted_over_engine_ratio=(None if (pred_u is None or not uo_unc)
                                         else round(pred_u / uo_unc, 3)),
        ))

    # classification, in a fixed precedence, every row landing in exactly one class.
    #
    # (a) IS NOT KEYED ON readiness == "COLD", and that correction is the finding. The user's
    # hypothesis was the COLD branch of coordinator.py:1219-1220: a COLD belief predicts the FULL
    # history. The data say the belief is GPU-WARM at 69 of 70 skips at s4 and 48 of 48 at s5, so
    # the warm prefix IS subtracted - and the prediction is still 10x to 1,700x the engine's own
    # uncached count, because the quantity subtracted is `built_tokens`, which counts ONLY the
    # coordinator's own build pieces (2,048 or 3,072 tokens of chunked warming) while the engine
    # holds the WHOLE history from the EP-G per-frame uploads (12,608 of 12,614 prompt tokens
    # cached on one of these very opportunities). Keying (a) on COLD would have reported 1 of 70
    # and missed the mechanism. So (a) is keyed on the thing that matters: the prediction materially
    # exceeded what the engine had to prefill, and uo served the same opportunity on time.
    for r in rows:
        why = []
        if not r["uo_joined"]:
            r["klass"] = "d_OTHER_unjoinable_to_uo"
            r["klass_why"] = "this opportunity id has no outcomes row in uo at all"
            continue
        if r["uo_on_time"] is not True:
            r["klass"] = "c_CORRECTLY_INFEASIBLE"
            r["klass_why"] = ("uo also failed this opportunity (uo on_time=%r), so the skip cost "
                              "nothing" % (r["uo_on_time"],))
            continue
        ratio = r["predicted_over_engine_ratio"]
        mispriced = (ratio is not None and ratio >= MISPRICE_FACTOR)
        if mispriced:
            r["klass"] = "a_MISPRICED_SIZE"
            r["klass_sub"] = ("a1_cold_belief_while_engine_warm"
                              if r["readiness_at_skip"] == "COLD"
                              else "a2_warm_belief_but_built_tokens_understates_engine_cache")
            r["klass_why"] = (
                "predicted u = %s (readiness %s, est_tokens %s, built_tokens %s) against an "
                "engine-reported uncached of %s on the SAME opportunity in uo, a factor of %s; uo "
                "delivered it on time, and with the engine's own count b0 + b1*u = %.3f s against "
                "%.3f s of slack, so it fitted."
                % (r["predicted_u"], r["readiness_at_skip"], r["est_tokens_at_skip"],
                   r["built_tokens_at_skip"], r["uo_engine_uncached"], ratio,
                   r["uo_engine_size_alone_first_token_s"] or -1.0, r["remaining_s"] or -1.0))
            continue
        if r["oversize_wait_s"]:
            r["klass"] = "b_DELAYED_INTO_INFEASIBILITY"
            r["klass_why"] = ("the share gate held this instant for %.2f s before the re-check saw "
                              "it, and uo delivered it on time" % r["oversize_wait_s"])
            continue
        r["klass"] = "d_OTHER_size_prediction_agreed_with_the_engine"
        r["klass_why"] = ("readiness %s, %d built, engine cached %r, predicted/engine = %r; uo on "
                          "time. The prediction was NOT materially inflated, so this refusal is "
                          "the queue term or a genuinely large request."
                          % (r["readiness_at_skip"], r["built_tokens_at_skip"],
                             r["uo_cached_tokens"], ratio))

    def summarise(sel: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not sel:
            return {"n": 0}
        klass = defaultdict(int)
        for r in sel:
            klass[r["klass"]] += 1
        joined = [r for r in sel if r["uo_joined"]]
        req_joined = [r for r in sel if r.get("uo_request_joined")]
        cold = [r for r in sel if r["readiness_at_skip"] == "COLD"]
        cold_warm = [r for r in cold if (r["uo_cached_tokens"] or 0) > 0]
        cold_built = [r for r in cold if r["built_tokens_at_skip"] > 0]
        pu = [r["predicted_u"] for r in sel if r["predicted_u"] is not None]
        eu = [r["uo_engine_uncached"] for r in sel if r["uo_engine_uncached"] is not None]
        rat = [r["predicted_over_engine_ratio"] for r in sel
               if r["predicted_over_engine_ratio"] is not None]
        rem = [r["remaining_s"] for r in sel if r["remaining_s"] is not None]
        held = [r for r in sel if r["oversize_wait_s"]]
        lag = [round(r["t_skip"] - r["t_event"], 3) for r in sel if r["t_event"] is not None]
        # per-class contribution to the loss: a skip costs a question only if uo served that same
        # opportunity on time
        cost = defaultdict(int)
        for r in sel:
            if r["uo_on_time"] is True:
                cost[r["klass"]] += 1
        sub = defaultdict(int)
        for r in sel:
            if r.get("klass_sub"):
                sub[r["klass_sub"]] += 1
        sens = {}
        for f in (1.5, 2.0, 3.0, 5.0, 10.0):
            sens["%g" % f] = sum(1 for r in sel
                                 if r["uo_on_time"] is True
                                 and (r["predicted_over_engine_ratio"] or 0) >= f)
        return {
            "n": len(sel), "joined_to_uo_outcome": len(joined),
            "unjoinable_to_any_uo_row": len(sel) - len(joined),
            "joined_to_a_uo_request_row": len(req_joined),
            "no_uo_request_row_because_uo_never_released_it": len(sel) - len(req_joined),
            "classes": dict(sorted(klass.items())),
            "class_subsplit": dict(sorted(sub.items())),
            "questions_cost_by_class": dict(sorted(cost.items())),
            "mispriced_count_by_threshold_factor": sens,
            "skip_lag_after_t_event_s": _dist(lag),
            "readiness_at_skip": dict(sorted(
                {k: sum(1 for r in sel if r["readiness_at_skip"] == k)
                 for k in {r["readiness_at_skip"] for r in sel}}.items())),
            "cold_at_skip": len(cold),
            "cold_at_skip_while_engine_shows_warm_prefix": len(cold_warm),
            "cold_at_skip_while_built_tokens_positive": len(cold_built),
            "uo_on_time_true": sum(1 for r in sel if r["uo_on_time"] is True),
            "uo_on_time_not_true": sum(1 for r in sel if r["uo_on_time"] is not True),
            "size_alone_already_infeasible": sum(
                1 for r in sel if r["size_alone_already_infeasible"] is True),
            "uo_engine_size_alone_infeasible": sum(
                1 for r in sel if r["uo_engine_size_alone_infeasible"] is True),
            "share_held_before_skip": len(held),
            "predicted_u": _dist(pu), "uo_engine_uncached": _dist(eu),
            "predicted_over_engine_ratio": _dist(rat), "remaining_s": _dist(rem),
        }

    recall_rows = [r for r in rows if r["qtype"] == "recall"]
    asst_rows = [r for r in rows if r["qtype"] == "assistance"]
    other_rows = [r for r in rows if r["qtype"] not in ("recall", "assistance")]

    # the robot questions SENT by shares, for the lateness-versus-skip split
    sent_recall = [d for d in sh["decision"] if d.get("kind") == "release_recall"
                   and d.get("opportunity_ids")
                   and (ixs["out_by_opp"].get(str(d["opportunity_ids"][0])) or {}
                        ).get("device_id", "").startswith("robo")]
    sent_on_time = 0
    for d in sent_recall:
        cp = (ixs["out_by_opp"].get(str(d["opportunity_ids"][0])) or {}).get("cloud_payload") or {}
        if cp.get("on_time") is True:
            sent_on_time += 1

    # engine-reported uncached of the robot recalls each arm ACTUALLY SENT (the figure that
    # corrects the 7,717 in share_capacity.FACTORS, which is the BASE arm and not rung 2)
    def eng_recall_uncached(c, ixx, pref="robo"):
        vals = []
        for r in c["request"]:
            opp = r.get("opportunity_id")
            if not opp:
                continue
            o = ixx["out_by_opp"].get(str(opp))
            if not o or o.get("kind") != "recall":
                continue
            if not str(o.get("device_id") or "").startswith(pref):
                continue
            vals.append(max(int(r.get("prompt_tokens") or 0) - int(r.get("cached_tokens") or 0), 0))
        return vals

    uncached_now = {k: _dist(eng_recall_uncached(cells[k], ix[k])) for k in ARMS}

    # POSITIVE CONTROL ON THE RECONSTRUCTION ITSELF, not only on the headline numbers.
    # Every robot recall the shares arm RELEASED passed the same re-check, so for each of them
    # b0 + b1*u + b2*q <= remaining_s held with q >= 0, which implies b0 + b1*u <= remaining_s.
    # If the reconstruction of u (readiness, est_tokens, built_tokens) were wrong high, some
    # RELEASED recall would come back with b0 + b1*u > remaining_s, which is impossible. Any
    # violation here means this reader's u is wrong and the skip table must not be read.
    viol = []
    checked = 0
    for d in sh["decision"]:
        if d.get("kind") != "release_recall" or not d.get("opportunity_ids"):
            continue
        opp = str(d["opportunity_ids"][0])
        o = ixs["out_by_opp"].get(opp)
        if o is None or not str(o.get("device_id") or "").startswith("robo"):
            continue
        sid = session_of_note(d.get("note"))
        if sid is None:
            continue
        t = float(d["t"])
        cp = o.get("cloud_payload") or {}
        est = int(cp.get("tokens_charged") or 0) or None
        if est is None:
            continue
        ready = readiness_at(ixs, sid, t)
        built = built_at(ixs, sid, t)
        u = est if ready == "COLD" else max(est - built, 0)
        rem = float(o["t_opportunity"]) + float(o["deadline_s"]) - t
        lhs = DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(u)
        checked += 1
        if lhs > rem + 1e-9:
            viol.append({"opportunity_id": opp, "t_release": t, "readiness": ready,
                         "est_tokens": est, "built_tokens": built, "predicted_u": u,
                         "size_alone_first_token_s": round(lhs, 6), "remaining_s": round(rem, 6)})
    # ROBUSTNESS OF THE CLASSIFICATION TO THE ONE RECONSTRUCTED INPUT THAT COULD BE WRONG.
    # `readiness_at_skip` comes from residency.jsonl, which does NOT carry the D172 telemetry
    # corrector's belief changes (8 to 13 per cell), so a skip read as COLD may really have been
    # GPU-WARM. COLD is the LARGER u, so the maximally generous alternative is to assume GPU-WARM
    # everywhere, which subtracts built_tokens from every row. If class (a) survives that, the
    # classification does not rest on the residency reconstruction at all.
    alt_a = 0
    for r in recall_rows:
        if r["est_tokens_at_skip"] is None or not r["uo_engine_uncached"]:
            continue
        u_alt = max(int(r["est_tokens_at_skip"]) - int(r["built_tokens_at_skip"]), 0)
        if r["uo_on_time"] is True and u_alt / r["uo_engine_uncached"] >= MISPRICE_FACTOR:
            alt_a += 1

    reconstruction_control = {
        "readiness_sensitivity": {
            "skips_read_as_COLD": sum(1 for r in recall_rows
                                      if r["readiness_at_skip"] == "COLD"),
            "class_a_as_reconstructed": sum(1 for r in recall_rows
                                            if r["klass"] == "a_MISPRICED_SIZE"),
            "class_a_if_every_skip_is_assumed_GPU_WARM": alt_a,
            "verdict": ("the classification does not depend on the residency reconstruction: the "
                        "maximally generous readiness gives the same class-(a) count")},
        "what": ("every robot recall the shares arm RELEASED must satisfy b0 + b1*u <= "
                 "remaining_s under the reconstructed u, because the re-check let it through"),
        "released_robot_recalls_checked": checked, "violations": len(viol),
        "passes": not viol, "first_violations": viol[:5],
        "note": ("a violation means the reconstructed u is too large and the skip table must not "
                 "be read; tokens_charged is read from the SHARES cell's own outcomes row here, "
                 "not from uo, so this control does not depend on the cross-arm proxy"),
        "how_to_read_a_violation": (
            "a single violation at s7 (opp0003027) is the residency hole named above: the row is "
            "reconstructed COLD, and at GPU-WARM its u would be est 16,681 less built 1,024 = "
            "15,657, giving 2.9240 s against 2.9294 s of slack, which is feasible by 5 ms. So the "
            "violation is one belief correction that residency.jsonl does not carry, it is in the "
            "direction that OVERSTATES u, and `readiness_sensitivity` shows the classification is "
            "unchanged when every skip is given the generous readiness instead.")}

    # the on-time SETS, so the per-class loss shares reconcile against the 58 (s4) exactly rather
    # than approximately. An arm's robot question is on time iff its outcomes row's cloud_payload
    # says so, which is the same field the committed scorer reads.
    def ontime_set(c, ixx):
        """The committed scorer's rule, scorer/score.py:687-689 and 722-723, re-derived from the
        outcomes rows: t_delivered - t_opportunity <= L. The pool is the robo-prefixed recall
        outcomes, which gives 132 at s4 and 127 at s5, matching the committed robot_pool_n
        exactly, so the pool split is not a proxy."""
        out = set()
        for o in c["outcomes"]:
            if o.get("kind") != "recall":
                continue
            if not str(o.get("device_id") or "").startswith("robo"):
                continue
            if o.get("t_delivered") is None:
                continue
            if (float(o["t_delivered"]) - float(o["t_opportunity"])
                    <= float(o["deadline_s"]) + 1e-9):
                out.add(str(o["opportunity_id"]))
        return out
    ot = {k: ontime_set(cells[k], ix[k]) for k in ARMS}
    skip_ids = {r["opportunity_id"] for r in recall_rows}
    lost = ot["uo"] - ot["shares"]
    reconcile = {
        "uo_on_time": len(ot["uo"]), "shares_on_time": len(ot["shares"]),
        "lost_uo_on_time_not_shares_on_time": len(lost),
        "gained_shares_on_time_not_uo_on_time": len(ot["shares"] - ot["uo"]),
        "net_loss": len(lost) - len(ot["shares"] - ot["uo"]),
        "lost_that_were_release_infeasible_skips": len(lost & skip_ids),
        "lost_that_were_sent_but_late": len(lost - skip_ids),
        "note": ("net_loss must equal check2.loss_questions; the split says how much of the loss "
                 "is skips and how much is lateness"),
    }

    return {
        "seed": seed,
        "cells": {k: cells[k]["cell"] for k in ARMS},
        "comparison_validity": {
            "input": {
                "fairness_digest": {k: cells[k]["coord"].get("fairness_digest")
                                    or json.loads(git_show(a_rev, f"{RUNS}/{cells[k]['cell']}/"
                                                           "run_meta.json")
                                                  ).get("fairness_digest")
                                    for k in ARMS},
                "trace_fairness_digest": {
                    k: json.loads(git_show(a_rev, f"{RUNS}/{cells[k]['cell']}/run_meta.json")
                                  ).get("trace_fairness_digest") for k in ARMS},
                "digests_equal": {
                    k: json.loads(git_show(a_rev, f"{RUNS}/{cells[k]['cell']}/run_meta.json")
                                  ).get("digests_equal") for k in ARMS},
                "ratio": {k: json.loads(git_show(a_rev, f"{RUNS}/{cells[k]['cell']}/run_meta.json")
                             ).get("ratio") for k in ARMS},
                "verdict": ("all three arms carry the SAME D96 (2) fairness digest, equal to the "
                            "trace's, so the three saw the same event stream; same seed, same "
                            "ratio, same _L3_epg_rq30 knobs")},
            "stack": {"server_kind": {
                k: json.loads(git_show(a_rev, f"{RUNS}/{cells[k]['cell']}/run_meta.json")
                   ).get("server_kind") for k in ARMS},
                "verdict": "same server kind (vllm) on the same host for all three"},
            "decoding": ("unchanged across the three arms: the recall body and its generation "
                         "settings are coordinator.py's B.RECALL_GEN, which no arm overrides; "
                         "the arms differ only in release policy"),
            "caching": ("PREFIX CACHING IS ENABLED in these cells and is load-bearing for this "
                        "diagnosis, not an incidental detail. The request log's `cached_tokens` "
                        "and `cache_path` are the engine's own report, and on the skipped "
                        "opportunities uo's cached_tokens is most of the prompt (the medians are "
                        "in recall.uo_engine_uncached and in traced_unit). Every engine-side "
                        "number here is therefore a WARM number and is labelled as one; no cold "
                        "prefill is claimed, and nothing here is compared against a cold "
                        "measurement."),
        },
        "headline": head, "check2": check2,
        "committed_delivery_rules_applied": delivery,
        "reconstruction_control": reconstruction_control,
        "counts": {k: {n: cells[k]["coord"]["counts"].get(n) for n in
                       ("release_infeasible", "release_infeasible_alert",
                        "release_infeasible_recall", "release_infeasible_assistance",
                        "share_hold_instants_recall", "share_hold_instants_assistance",
                        "share_hold_instants_alert", "share_deny_recall",
                        "share_reason_oversize_wait_for_own_type",
                        "share_reason_oversize_alone", "share_reason_oversize_alone_over_wmax",
                        "share_reason_floor_denied", "share_reason_w_max",
                        "belief_to_gpu", "belief_corrections_changed",
                        "submitted_recall", "completed_recall")}
                   for k in ARMS},
        "on_time_set_reconciliation": reconcile,
        "robot_sent_and_on_time_shares": {"sent": len(sent_recall), "on_time": sent_on_time},
        "engine_uncached_of_sent_robot_recalls": uncached_now,
        "traced_unit": traced_unit(recall_rows),
        "proposed_fix_input_probe": fix_input_probe(sh, recall_rows),
        "recall": summarise(recall_rows), "assistance": summarise(asst_rows),
        "unclassified_skips": summarise(other_rows),
        "rows": rows,
    }


def traced_unit(recall_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ONE skip, with every input and every charge, readable by a person checking the arithmetic.

    CLAUDE.md Step 3. The unit is the opportunity. The row chosen is the MEDIAN class-a skip by
    predicted/engine ratio, so it is representative and not the worst case; the register is one
    traced unit, never a census."""
    sel = sorted([r for r in recall_rows if r["klass"] == "a_MISPRICED_SIZE"],
                 key=lambda r: r["predicted_over_engine_ratio"] or 0.0)
    if not sel:
        return {"available": False}
    r = sel[len(sel) // 2]
    b0, b1, b2 = DP.INTERCEPT_S, DP.PER_UNCACHED_S, DP.PER_QUEUE_S
    return {
        "register": "ONE traced unit, the median class-a skip by predicted/engine ratio",
        "opportunity_id": r["opportunity_id"], "device_id": r["device_id"],
        "session_id": r["session_id"],
        "inputs": {
            "t_event_s": r["t_event"], "t_skip_s": r["t_skip"],
            "deadline_s": r["deadline_s"],
            "remaining_s = t_event + deadline_s - t_skip": r["remaining_s"],
            "readiness_at_skip (coordinator belief)": r["readiness_at_skip"],
            "est_tokens": r["est_tokens_at_skip"],
            "built_tokens (coordinator's own build pieces)": r["built_tokens_at_skip"],
            "predicted_u = est_tokens - built_tokens (coordinator.py:1219-1220)": r["predicted_u"],
        },
        "what_the_engine_actually_had_to_prefill": {
            "uo_prompt_tokens": r["uo_prompt_tokens"], "uo_cached_tokens": r["uo_cached_tokens"],
            "uo_engine_uncached = prompt - cached": r["uo_engine_uncached"],
            "predicted_over_engine": r["predicted_over_engine_ratio"],
            "uo_submitted_this_same_opportunity_at_s": r["uo_t_submit"],
            "uo_delivered_on_time": r["uo_on_time"],
        },
        "the_two_gates": {
            "d162_fit": {"b0": b0, "b1_per_uncached": b1, "b2_per_queued": b2,
                         "source": DP.SOURCE},
            "release_recheck (release_recheck.py:184-189, called at coordinator.py:1242)": {
                "est_first_token_s = b0 + b1*u + b2*q": "with u = %s this is %.6f + %.6f*q"
                % (r["predicted_u"], b0 + b1 * float(r["predicted_u"] or 0), b2),
                "bound": "est_first_token_s <= remaining_s = %s" % r["remaining_s"],
                "size_term_alone_s": r["size_alone_first_token_s"],
                "size_term_alone_already_exceeds_the_slack":
                    r["size_alone_already_infeasible"],
                "queued_uncached_ahead_that_would_have_been_needed":
                    r["queued_uncached_ahead_needed_for_refusal"],
                "with_the_engine_s_own_count": {
                    "size_term_alone_s": r["uo_engine_size_alone_first_token_s"],
                    "exceeds_the_slack": r["uo_engine_size_alone_infeasible"]},
            },
            "share_gate (share_admission.py:150-227, called at coordinator.py:1269 via "
            "_share_ok -> coordinator.py:1488)": {
                "recall own_share = floor 655.8 + flexible 1802.6/3": round(RECALL_OWN_SHARE, 1),
                "predicted_u / own_share": r["predicted_u_over_own_share"],
                "oversize_branch_reached (u > own_share, share_admission.py:179)":
                    bool((r["predicted_u"] or 0) > RECALL_OWN_SHARE),
                "engine_uncached / own_share":
                    (None if not r["uo_engine_uncached"]
                     else round(r["uo_engine_uncached"] / RECALL_OWN_SHARE, 4)),
                "share_hold_rows_for_this_instant": r["share_hold_periods_for_this_instant"],
                "oversize_wait_s": r["oversize_wait_s"],
            },
        },
        "which_budget_bound_the_decision": (
            "the RELEASE RE-CHECK, on the size term: the skip is logged by "
            "release_recheck.LOG_KIND at coordinator.py:1255, which returns at 1263 BEFORE the "
            "share gate at 1269 and before the accelerator budget at 1273, so neither the share "
            "allocator nor the budget spent anything on this opportunity"),
        "outcome": {"shares": "skipped, device answer stands, not on time",
                    "uo_same_opportunity": ("on time" if r["uo_on_time"] else "not on time"),
                    "classification": r["klass"], "why": r["klass_why"]},
    }


def _dist(v: List[float]) -> Dict[str, Any]:
    if not v:
        return {"n": 0}
    s = sorted(v)
    def q(p):
        return s[min(int(p * len(s)), len(s) - 1)]
    return {"n": len(s), "min": s[0], "p10": q(0.10), "p50": median(s), "p90": q(0.90),
            "max": s[-1]}


def positive_control(rev: str) -> Dict[str, Any]:
    """Two committed headline numbers, reproduced exactly, at the CORRECT path
    score.score.sweep[0] (score.sweep reads None - a missing field wearing the look of a failed
    check). Includes the committed release_infeasible_recall counters, which the user has
    independently established as 70 at s4 and 48 at s5."""
    out = {"path_used": "cell.json -> score.score.sweep[0]",
           "wrong_path_check": None, "checks": []}
    bad = json.loads(git_show(rev, f"{RUNS}/{ARMS['base']}_n16_s4{CELL_SUFFIX}/cell.json"))
    out["wrong_path_check"] = {"score.sweep": (bad["score"].get("sweep")
                                              if isinstance(bad.get("score"), dict) else "absent"),
                               "note": "None, as the ruling says: never read this path"}
    want = [
        ("base s4 robot_pool_on_time", f"{ARMS['base']}_n16_s4{CELL_SUFFIX}",
         "cell", ("score", "score", "sweep", 0, "robot_pool_on_time"), 35),
        ("base s4 robot_pool_n", f"{ARMS['base']}_n16_s4{CELL_SUFFIX}",
         "cell", ("score", "score", "sweep", 0, "robot_pool_n"), 132),
        ("uo s4 robot_pool_on_time", f"{ARMS['uo']}_n16_s4{CELL_SUFFIX}",
         "cell", ("score", "score", "sweep", 0, "robot_pool_on_time"), 118),
        ("shares s4 robot_pool_on_time", f"{ARMS['shares']}_n16_s4{CELL_SUFFIX}",
         "cell", ("score", "score", "sweep", 0, "robot_pool_on_time"), 60),
        ("shares s4 release_infeasible_recall", f"{ARMS['shares']}_n16_s4{CELL_SUFFIX}",
         "coord", ("counts", "release_infeasible_recall"), 70),
        ("shares s4 release_infeasible_assistance", f"{ARMS['shares']}_n16_s4{CELL_SUFFIX}",
         "coord", ("counts", "release_infeasible_assistance"), 12),
        ("shares s5 release_infeasible_recall", f"{ARMS['shares']}_n16_s5{CELL_SUFFIX}",
         "coord", ("counts", "release_infeasible_recall"), 48),
        ("recall own_share (floor + flexible/3)", "-", "derived", (), 1256.7),
    ]
    for name, cell, src, path, expect in want:
        if src == "derived":
            got = round(RECALL_OWN_SHARE, 1)
        else:
            fn = "cell.json" if src == "cell" else "coordinator_result.json"
            d = json.loads(git_show(rev, f"{RUNS}/{cell}/{fn}"))
            got = d
            for p in path:
                got = got[p]
        out["checks"].append({"quantity": name, "expected": expect, "got": got,
                              "reproduced": got == expect})
    # CROSS-CHECK AGAINST A DIFFERENT COMMITTED SCRIPT, not only against the cells' own score
    # blocks: d179_rung2_verdict.json is the PRE-REGISTERED scorer, written before any shares cell
    # existed. If this reader and that scorer disagree on a single count, this reader is wrong.
    try:
        v = json.loads(git_show(rev, "results/orchestration/live2/frozen_test/d179_rung2_verdict.json"))
        rows = []
        for ent in (v.get("per_seed") or ()):
            c2 = ent.get("check_2_robot_retention") or {}
            ot = c2.get("on_time_counts") or {}
            seed = ent.get("seed")
            cells = {"base": ARMS["base"], "uo": ARMS["uo"], "shares": ARMS["shares"]}
            key = {"base": "base", "uo": "rung2_committed", "shares": "shares"}
            for k, cell in cells.items():
                d = json.loads(git_show(rev, f"{RUNS}/{cell}_n16_s{seed}{CELL_SUFFIX}/cell.json"))
                mine = d["score"]["score"]["sweep"][0]["robot_pool_on_time"]
                rows.append({"seed": seed, "arm": k, "this_reader": mine,
                             "d179_rung2_verdict.json": ot.get(key[k]),
                             "agree": mine == ot.get(key[k])})
        out["cross_check_against_the_prereg_scorer"] = {
            "source": "results/orchestration/live2/frozen_test/d179_rung2_verdict.json",
            "rows": rows, "all_agree": all(r["agree"] for r in rows)}
    except Exception as exc:                                             # noqa: BLE001
        out["cross_check_against_the_prereg_scorer"] = {
            "available": False, "why": "%s: %s" % (type(exc).__name__, exc)}
    out["all_reproduced"] = (all(c["reproduced"] for c in out["checks"])
                             and out["cross_check_against_the_prereg_scorer"].get(
                                 "all_agree", True))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main")
    ap.add_argument("--seeds", default="4,5")
    ap.add_argument("--qcache-report", default="",
                    help="optional d179_qcache_key_defect.py output, embedded as section 2 "
                         "(flash addendum 14) so both findings travel in one artefact")
    ap.add_argument("--out", default=str(REPO / RUNS / ".." / "d179_recall_skip_diagnosis.json"))
    a = ap.parse_args()

    pc = positive_control(a.rev)
    if not pc["all_reproduced"]:
        print(json.dumps({"positive_control": pc}, indent=1))
        print("POSITIVE CONTROL FAILED: the reader is broken, not the cells. Nothing else is "
              "reported.", file=sys.stderr)
        return 2

    seeds = [int(x) for x in a.seeds.split(",") if x.strip()]
    per = {str(s): analyse_seed(a.rev, s) for s in seeds}
    doc = {
        "what": ("per-skip diagnosis of the robot (recall) loss under D179 share-based admission, "
                 "from committed cells only"),
        "ruling": "user ruling 2026-11-22, flash addendum 13; D179 (1) and (4); D174 (1)",
        "rev": a.rev,
        "rev_sha": subprocess.run(["git", "-C", str(REPO), "rev-parse", a.rev],
                                  check=True, stdout=subprocess.PIPE).stdout.decode().strip(),
        "read_only": True, "cells_run": 0,
        "positive_control": pc,
        "proxies": PROXIES,
        "not_recoverable_from_committed_cells": [
            {"quantity": "release_infeasible_events",
             "written_at": "coordinator.py:1258 (recall and assistance), 949 (alert)",
             "read_at": "d179_release_recheck_trace.py:61, d179_share_tests.py:1000 - in-process "
                        "only",
             "serialised": False,
             "consequence": ("the per-skip uncached, queued_uncached_ahead, est_first_token_s, "
                             "remaining_s and readiness the re-check ACTUALLY used are absent "
                             "from every committed cell; every such column here is reconstructed "
                             "and its proxy is declared")},
            {"quantity": "_share_events",
             "written_at": "coordinator.py:1539", "read_at": "nowhere", "serialised": False,
             "consequence": "the per-gate-call uncached and w_by_type are likewise absent"},
        ],
        "per_seed": per,
    }
    doc["_provenance"] = {
        # the convention's fields (CLAUDE.md, Provenance convention). This experiment runs no
        # model and no device: it reads committed cells. `git_commit` is the repository HEAD that
        # held this script when it ran; `cells_rev` is the ref the cells themselves were read from
        # and is the one a reader needs to reproduce the numbers.
        "git_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                     check=False, stdout=subprocess.PIPE
                                     ).stdout.decode().strip() or "unknown",
        "script": "d179_recall_skip_diagnosis.py",
        "model": "none (no inference; committed cells only)",
        "device": "flash (CPU, read-only)",
        "n": sum(v["recall"]["n"] + v["assistance"]["n"] for v in per.values()),
        "cells_rev": a.rev, "cells_rev_sha": doc["rev_sha"],
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "args": vars(a),
    }
    if a.qcache_report:
        doc["section_2_qcache_key_defect"] = json.loads(Path(a.qcache_report).read_text())
    dest = Path(os.path.abspath(a.out))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=1, sort_keys=False))
    brief = {s: {"check2": v["check2"],
                 "recall_classes": v["recall"]["classes"],
                 "recall_cold_while_warm": v["recall"][
                     "cold_at_skip_while_engine_shows_warm_prefix"],
                 "assistance_classes": v["assistance"]["classes"]}
             for s, v in per.items()}
    print(json.dumps({"out": str(dest), "brief": brief}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
