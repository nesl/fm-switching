#!/usr/bin/env python3
"""Why the 34 residual recall skips in covex-v6-state-shares-r1 are still refused.

READ-ONLY. Reads only COMMITTED cells, through `git show <rev>:<path>`. No cell is run, no
live-path file is touched.

THE QUESTION (D187, flash overnight). The cold-pricing fix (79eedc6d) moved robot on-time from
60 to 95 of 132 at s4 against covex-v6-state-uo's 118, and cut release_infeasible_recall from 70
to 34 against a pre-registered bar of at most 13. The H100 measured the residual mispricing on
those 34 at about 6.4x (predicted uncached median 8,122 against the engine's 1,265 on the same
opportunity in uo). This asks WHY, and what the smallest honest fix is.

WHAT IS READ DIRECTLY AND WHAT IS STILL INFERRED, stated before any number.

DIRECT, from `coordinator_result.json` of the r1 cell (the P0 instrumentation that shipped with
the fix):
  * `release_infeasible_events` - per skip: `uncached` (the predicted u the re-check USED),
    `queued_uncached_ahead`, `est_first_token_s`, `remaining_s`, `readiness`, `est_tokens`,
    `session_id`, `t`, `deadline_abs`. These are the quantities the re-check actually consumed,
    not a reconstruction of them.
  * `share_events` - per gate call: `qtype`, `kind`, `uncached`, `admitted`, `reason`, `w_by_type`.

DERIVED BY ARITHMETIC FROM TWO DIRECT FIELDS, so not a proxy:
  * `prefix_used = est_tokens - uncached` on the WARM branch. coordinator.py:1253-1256 computes
    `_uncached = max(tokens - max(built_tokens, last_telemetry_cached_tokens), 0)` and the event
    carries `est_tokens = tokens` and `uncached = _uncached`, so the difference IS the prefix the
    code subtracted. Every one of the 34 skips is readiness GPU-WARM (direct field), so the COLD
    branch is never taken and the identity holds on all of them.

STILL INFERRED, each declared at its point of use (see PROXIES):
  * `built_tokens` and `last_telemetry_cached_tokens` SEPARATELY. Neither is in the event. They
    are reconstructed from their own write sites and then VALIDATED against the direct
    `prefix_used` by the identity `prefix_used == max(built_recon, tel_recon)`, which is checked
    on every row and is a stopping condition (positive control PC2).
  * the engine's resident prefix at the skip instant. No arm reports it. Two separate proxies are
    used and never mixed: the cross-arm uo `cached_tokens` on the same opportunity, and a
    WITHIN-ARM lower bound from r1's own later requests on the same session.

Usage:
  python d187_r1_residual_diagnosis.py [--rev origin/main] [--seeds 4] [--out <path>]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(os.environ.get("D179_REPO") or Path(__file__).resolve().parents[3])
RUNS = "results/orchestration/live2/frozen_test/runs"
CELL_SUFFIX = "_1200s_h27_3t_L3_epg_rq30"
ARMS = {"base": "hybrid-F-lhreq-noc3", "uo": "covex-v6-state-uo",
        "shares": "covex-v6-state-shares", "r1": "covex-v6-state-shares-r1"}

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import d162_price as DP                                             # noqa: E402
    _DP_FROM = "experiments/orchestration/live2/d162_price.py (working tree)"
except ImportError:
    # This box's working tree can sit behind the rev the cells were committed on, and
    # `d162_price.py` then does not exist beside this file. ONE PRICE SOURCE (2026-11-21): the
    # coefficients are never retyped here. The committed module is materialised from the rev
    # under test into a session-unique scratch directory and imported from there, and where it
    # came from is recorded in the output.
    import tempfile                                                     # noqa: E402
    _d = Path(tempfile.mkdtemp(prefix="d187_price_"))
    _rev_for_price = os.environ.get("D187_REV", "origin/main")
    # the module reads its gate file at REPO/results/..., with REPO = parents[3] of its own
    # path, so the repo layout is reproduced around it and the GATE FILE IS EXTRACTED TOO. The
    # module's own drift check then runs for real instead of being silently skipped.
    for _rel in ("experiments/orchestration/live2/d162_price.py",
                 "results/orchestration/live2/frozen_test/cost_model_gate_d162.json"):
        (_d / _rel).parent.mkdir(parents=True, exist_ok=True)
        (_d / _rel).write_bytes(subprocess.run(
            ["git", "-C", str(REPO), "show", f"{_rev_for_price}:{_rel}"],
            check=True, stdout=subprocess.PIPE).stdout)
    sys.path.insert(0, str(_d / "experiments/orchestration/live2"))
    import d162_price as DP                                             # noqa: E402
    _DP_FROM = (f"git show {_rev_for_price}:experiments/orchestration/live2/d162_price.py "
                "(the working tree is behind that rev and does not carry the file)")

# the within-arm engine probe window, in seconds after the skip. Not tuned: reported at three
# widths so a reader can see the probe is sparse rather than sensitive.
PROBE_WINDOWS = (15.0, 30.0, 60.0)

PROXIES = [
    {"column": "built_tokens_at_skip",
     "proxy": "cumulative release_piece piece_tokens whose request row's t_done precedes t_skip",
     "actually_measures": ("built_tokens is incremented at coordinator.py:1813 inside _settle, so "
                           "completion time is the right clock; reset at session_end and "
                           "history_preload."),
     "valid_for_the_claim": ("YES, and it is VALIDATED here rather than asserted: together with "
                             "the telemetry reconstruction it must reproduce the DIRECT "
                             "prefix_used exactly on every row (PC2). It does, 34 of 34 at s4.")},
    {"column": "last_telemetry_cached_tokens_at_skip",
     "proxy": ("cached_tokens of the last COMPLETED request carrying this session_id before "
               "t_skip, with cached_tokens not None"),
     "actually_measures": ("exactly the write site: engine_actions.py:358 sets "
                           "`session.last_telemetry_cached_tokens = ct` on every completed "
                           "request that carries a session_id and a usage block, reached from "
                           "coordinator.py:1702. The guard there is `if sub.session_id:`, which "
                           "is SESSION-based and not KIND-based, and the belief-apply-off restore "
                           "at coordinator.py:1708 restores only `belief` and `last_touch_s`, so "
                           "the field is never clobbered."),
     "valid_for_the_claim": ("YES, validated by PC2 as above. The request log carries no `kind`, "
                             "so the kind of each telemetry write is itself joined through "
                             "decision_id to the decision log's `kind`.")},
    {"column": "uo_engine_cached_tokens / uo_engine_uncached",
     "proxy": "prompt_tokens and cached_tokens on uo's request row for the SAME opportunity id",
     "actually_measures": "the engine's own report of the prefix it held and what it prefilled.",
     "valid_for_the_claim": ("PARTIALLY, AND THIS IS THE CENTRAL CAVEAT OF THIS DIAGNOSIS. It is "
                             "the engine's measurement, not a prediction, but it is NOT "
                             "counterfactually attainable by r1. A recall is the only request "
                             "that presents the WHOLE history to the engine (a touch sends "
                             "s.frames[:len(confirmed_bytes_for)], coordinator.py:1120, and a "
                             "build piece sends only the built prefix), so uo's engine prefix on "
                             "a session is largely PLANTED BY UO'S OWN EARLIER RECALLS on that "
                             "session - the very recalls r1 skipped. `prior_uo_recalls_on_session` "
                             "and `prior_r1_recalls_on_session` are reported on every row so a "
                             "reader can stratify, and the uncontaminated stratum "
                             "(prior_uo_recalls == 0) is reported separately.")},
    {"column": "r1_engine_prefix_lower_bound_in_window",
     "proxy": ("max cached_tokens over r1's OWN requests on the same session submitted in "
               "[t_skip, t_skip + W]"),
     "actually_measures": ("a LOWER BOUND on the engine's resident prefix for that session in the "
                           "r1 arm, because cached_tokens <= resident prefix always."),
     "valid_for_the_claim": ("YES as a lower bound, and only as one. It exists for a minority of "
                             "rows (the count is reported, never padded), because r1 skipped the "
                             "later recalls too. Never averaged with the uo proxy.")},
    {"column": "uo_on_time",
     "proxy": "the committed scorer's own rule re-derived from uo's outcomes rows",
     "actually_measures": ("t_delivered - t_opportunity <= deadline_s, after the committed D144 "
                           "and D146 delivery rewrites (scorer/score.py:539-579)."),
     "valid_for_the_claim": ("YES; the reader's robot_pool_on_time reproduces the committed 118 / "
                             "95 / 60 / 35 exactly (PC1), which is what makes the per-skip cost "
                             "attribution the scorer's and not a near-miss of it.")},
]


def git_show(rev: str, path: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"],
                          check=True, stdout=subprocess.PIPE).stdout


def have(rev: str, path: str) -> bool:
    return subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}:{path}"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def load_cell(rev: str, cell: str) -> Dict[str, Any]:
    base = f"{RUNS}/{cell}"
    out: Dict[str, Any] = {"cell": cell}
    out["cell_json"] = json.loads(git_show(rev, f"{base}/cell.json"))
    out["coord"] = json.loads(git_show(rev, f"{base}/coordinator_result.json"))
    out["run_meta"] = json.loads(git_show(rev, f"{base}/run_meta.json"))
    for name in ("decision", "outcomes", "request"):
        raw = gzip.decompress(git_show(rev, f"{base}/{name}.jsonl.gz")).decode()
        out[name] = [json.loads(x) for x in raw.splitlines() if x.strip()]
    return out


def apply_committed_delivery_rules(c: Dict[str, Any]) -> Dict[str, Any]:
    """The two rewrites the COMMITTED scorer applies before anything reads `t_delivered`
    (scorer/score.py:539-579), re-applied here so this reader's on-time count is the scorer's.
    D144 nulls a refused request's cloud delivery; D146 delivers a recall at generation
    COMPLETION."""
    refused = set()
    for r in c["request"]:
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
            n144 += 1
    done = {str(r["opportunity_id"]): float(r["t_done"]) for r in c["request"]
            if r.get("opportunity_id") and r.get("t_done") is not None}
    n146 = 0
    for o in c["outcomes"]:
        if o.get("kind") != "recall" or o.get("t_delivered") is None:
            continue
        oid = str(o["opportunity_id"])
        if o.get("t_cloud_done") is None or oid not in done:
            continue
        o["t_delivered"] = done[oid] + (float(o["t_delivered"]) - float(o["t_cloud_done"]))
        n146 += 1
    return {"d144_nulled": n144, "d146_rewritten_to_completion": n146}


def robot_pool(c: Dict[str, Any]) -> set:
    return {str(o["opportunity_id"]) for o in c["outcomes"]
            if o.get("kind") == "recall" and str(o.get("device_id") or "").startswith("robo")}


def robot_on_time(c: Dict[str, Any]) -> set:
    out = set()
    for o in c["outcomes"]:
        if o.get("kind") != "recall" or not str(o.get("device_id") or "").startswith("robo"):
            continue
        if o.get("t_delivered") is None:
            continue
        if float(o["t_delivered"]) - float(o["t_opportunity"]) <= float(o["deadline_s"]) + 1e-9:
            out.add(str(o["opportunity_id"]))
    return out


def session_of_note(note: Optional[str]) -> Optional[str]:
    if not note or not str(note).startswith("session="):
        return None
    return str(note)[len("session="):]


def indexes(c: Dict[str, Any]) -> Dict[str, Any]:
    req_by_dec = {str(r["decision_id"]): r for r in c["request"] if r.get("decision_id")}
    kind_by_dec = {str(d["decision_id"]): d.get("kind") for d in c["decision"]
                   if d.get("decision_id")}
    piece = defaultdict(list)
    recalls = defaultdict(list)
    for d in c["decision"]:
        sid = session_of_note(d.get("note"))
        if d.get("kind") == "release_piece" and sid:
            rq = req_by_dec.get(str(d.get("decision_id") or ""))
            if rq is not None and rq.get("t_done") is not None:
                piece[sid].append((float(rq["t_done"]), int(d.get("piece_tokens") or 0)))
        if d.get("kind") == "release_recall" and sid and d.get("opportunity_ids"):
            recalls[sid].append((float(d["t"]), str(d["opportunity_ids"][0])))
    for m in (piece, recalls):
        for k in m:
            m[k].sort()
    # telemetry writes: every completed request carrying a session_id with a usage block
    tel = defaultdict(list)
    for r in c["request"]:
        if (r.get("session_id") and r.get("t_done") is not None
                and r.get("cached_tokens") is not None):
            tel[str(r["session_id"])].append(dict(
                t_done=float(r["t_done"]), t_submit=float(r["t_submit"]),
                cached=int(r["cached_tokens"]), prompt=int(r.get("prompt_tokens") or 0),
                kind=kind_by_dec.get(str(r.get("decision_id") or ""))))
    for k in tel:
        tel[k].sort(key=lambda x: x["t_done"])
    return dict(req_by_opp={str(r["opportunity_id"]): r for r in c["request"]
                            if r.get("opportunity_id")},
                out_by_opp={str(o["opportunity_id"]): o for o in c["outcomes"]},
                piece=dict(piece), recalls=dict(recalls), tel=dict(tel),
                kind_by_dec=kind_by_dec)


def _dist(v: List[float]) -> Dict[str, Any]:
    v = sorted(x for x in v if x is not None)
    if not v:
        return {"n": 0}
    def q(p):
        i = min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))
        return v[i]
    return {"n": len(v), "min": v[0], "p25": q(0.25), "median": q(0.5), "p75": q(0.75),
            "max": v[-1], "all": v}


# ---------------------------------------------------------------- the per-seed analysis
def analyse_seed(rev: str, seed: int) -> Dict[str, Any]:
    cells = {k: load_cell(rev, f"{v}_n16_s{seed}{CELL_SUFFIX}") for k, v in ARMS.items()}
    delivery = {k: apply_committed_delivery_rules(v) for k, v in cells.items()}
    ix = {k: indexes(v) for k, v in cells.items()}
    r1, uo, sh = cells["r1"], cells["uo"], cells["shares"]
    ixr, ixu = ix["r1"], ix["uo"]

    # ---- POSITIVE CONTROL 1: reproduce committed headline numbers two ways -----------------
    head = {}
    for k, c in cells.items():
        z = c["cell_json"]["score"]["score"]["sweep"][0]
        head[k] = {"robot_pool_on_time_COMMITTED": z["robot_pool_on_time"],
                   "robot_pool_n_COMMITTED": z["robot_pool_n"],
                   "ss_pool_on_time_COMMITTED": z["ss_pool_on_time"],
                   "ss_pool_n_COMMITTED": z["ss_pool_n"],
                   "dashcam_all_meet_COMMITTED": z["dashcam_all_meet"],
                   "run_valid": c["cell_json"]["run_valid"],
                   "arm": c["coord"]["arm"],
                   "robot_pool_n_THIS_READER": len(robot_pool(c)),
                   "robot_pool_on_time_THIS_READER": len(robot_on_time(c))}
    pc1_rows = [{"arm": k,
                 "committed": head[k]["robot_pool_on_time_COMMITTED"],
                 "this_reader": head[k]["robot_pool_on_time_THIS_READER"],
                 "pool_committed": head[k]["robot_pool_n_COMMITTED"],
                 "pool_this_reader": head[k]["robot_pool_n_THIS_READER"],
                 "exact": (head[k]["robot_pool_on_time_COMMITTED"]
                           == head[k]["robot_pool_on_time_THIS_READER"]
                           and head[k]["robot_pool_n_COMMITTED"]
                           == head[k]["robot_pool_n_THIS_READER"])}
                for k in ARMS]
    pc1 = {"what": ("this reader's robot pool and on-time count, re-derived from the outcomes "
                    "rows under the committed D144/D146 delivery rules, must equal the committed "
                    "cell.json score.score.sweep[0] values for EVERY arm including the controls. "
                    "`score.sweep` is not the path and reads None."),
           "rows": pc1_rows, "passes": all(r["exact"] for r in pc1_rows)}

    # ---- the 34 (or n) residual recall skips, from the DIRECT event list -------------------
    ev = sorted([e for e in r1["coord"]["release_infeasible_events"]
                 if e.get("qtype") == "recall"], key=lambda e: e["t"])
    counts_r1 = r1["coord"]["counts"]
    event_count_check = {
        "release_infeasible_recall_counter": counts_r1.get("release_infeasible_recall", 0),
        "recall_events_serialised": len(ev),
        "release_infeasible_events_total": r1["coord"].get("release_infeasible_events_total"),
        "share_events_total": r1["coord"].get("share_events_total"),
        "share_events_serialised": len(r1["coord"]["share_events"]),
        "share_events_cap": r1["coord"].get("share_events_cap"),
        "agrees": (counts_r1.get("release_infeasible_recall", 0) == len(ev)
                   and r1["coord"].get("share_events_total") == len(r1["coord"]["share_events"])),
        "note": ("if the serialised list were truncated at share_events_cap the share-side "
                 "analysis would be a sample and would have to be labelled one")}

    uo_ot = robot_on_time(uo)
    r1_ot = robot_on_time(r1)

    rows: List[Dict[str, Any]] = []
    for e in ev:
        opp, t, sid = e["opportunity_id"], float(e["t"]), e["session_id"]
        est, u = int(e["est_tokens"]), int(e["uncached"])
        prefix_used = est - u                       # DERIVED from two direct fields, not a proxy
        built = sum(tok for (td, tok) in ixr["piece"].get(sid, ()) if td < t)        # PROXY
        hist = [x for x in ixr["tel"].get(sid, ()) if x["t_done"] < t]               # PROXY
        last = hist[-1] if hist else None
        tel = (last["cached"] if last else None)
        tel_runmax = (max(x["cached"] for x in hist) if hist else None)
        kinds = Counter(x["kind"] for x in hist)
        # the identity that validates both reconstructions (PC2)
        identity_ok = (prefix_used == max(built, tel if tel is not None else 0))

        uo_req = ixu["req_by_opp"].get(opp)
        uo_prompt = None if uo_req is None else int(uo_req.get("prompt_tokens") or 0)
        uo_cached = None if uo_req is None else int(uo_req.get("cached_tokens") or 0)
        uo_unc = None if uo_req is None else max(uo_prompt - uo_cached, 0)
        uo_ttft = None
        if uo_req is not None and uo_req.get("t_first_token") is not None:
            uo_ttft = round(float(uo_req["t_first_token"]) - float(uo_req["t_submit"]), 4)

        probe = {}
        for W in PROBE_WINDOWS:
            v = [x["cached"] for x in ixr["tel"].get(sid, ())
                 if t <= x["t_submit"] <= t + W]
            probe["w%g" % W] = max(v) if v else None

        prior_r1 = sum(1 for (tt, _o) in ixr["recalls"].get(sid, ()) if tt < t)
        prior_uo = sum(1 for (tt, _o) in ixu["recalls"].get(sid, ()) if tt < t)

        size_alone = DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(u)
        rem = float(e["remaining_s"])
        eft_recomputed = size_alone + DP.PER_QUEUE_S * float(e["queued_uncached_ahead"])
        eng_full = (None if uo_unc is None
                    else DP.INTERCEPT_S + DP.PER_UNCACHED_S * float(uo_unc)
                    + DP.PER_QUEUE_S * float(e["queued_uncached_ahead"]))
        rows.append(dict(
            seed=seed, opportunity_id=opp, session_id=sid, device_id=e["device_id"],
            t_skip=round(t, 3),
            # ---- DIRECT, from release_infeasible_events
            est_tokens=est, predicted_u_AS_USED=u,
            queued_uncached_ahead=int(e["queued_uncached_ahead"]),
            est_first_token_s=round(float(e["est_first_token_s"]), 6),
            remaining_s=round(rem, 6), readiness=e["readiness"],
            deadline_abs=round(float(e["deadline_abs"]), 6),
            # ---- DERIVED by arithmetic from two direct fields
            prefix_used=prefix_used,
            # ---- PROXY (validated by PC2)
            built_tokens_at_skip=built,
            last_telemetry_cached_tokens_set=bool(hist),
            last_telemetry_cached_tokens=tel,
            last_telemetry_prompt_tokens=(last["prompt"] if last else None),
            last_telemetry_write_kind=(last["kind"] if last else None),
            telemetry_running_max_before_skip=tel_runmax,
            telemetry_write_kinds_before_skip=dict(kinds),
            n_telemetry_writes_before_skip=len(hist),
            prefix_reconstruction_identity_ok=identity_ok,
            # ---- which term refused it
            size_alone_first_token_s=round(size_alone, 6),
            size_alone_exceeded_slack=bool(size_alone > rem),
            queue_term_s=round(DP.PER_QUEUE_S * float(e["queued_uncached_ahead"]), 6),
            refused_by=("size" if size_alone > rem else "queue"),
            est_first_token_s_recomputed=round(eft_recomputed, 6),
            price_model_arithmetic_ok=bool(abs(eft_recomputed
                                               - float(e["est_first_token_s"])) < 1e-9),
            # ---- PROXY: the cross-arm engine report
            uo_request_joined=bool(uo_req is not None),
            uo_prompt_tokens=uo_prompt, uo_engine_cached_tokens=uo_cached,
            uo_engine_uncached=uo_unc,
            uo_actual_first_token_s=uo_ttft,
            predicted_over_engine_ratio=(None if not uo_unc else round(u / uo_unc, 3)),
            lag_tokens_vs_uo=(None if uo_cached is None else uo_cached - prefix_used),
            would_pass_recheck_with_engine_prefix=(None if eng_full is None
                                                   else bool(eng_full <= rem)),
            # ---- PROXY: the within-arm engine lower bound
            r1_engine_prefix_lower_bound=probe,
            lag_tokens_vs_r1_own_probe_w60=(None if probe["w60"] is None
                                            else probe["w60"] - prefix_used),
            # ---- contamination stratifiers
            prior_r1_recalls_on_session=prior_r1,
            prior_uo_recalls_on_session=prior_uo,
            # ---- what the skip cost
            uo_on_time=bool(opp in uo_ot),
            r1_on_time=bool(opp in r1_ot),
            skip_cost_a_question=bool(opp in uo_ot and opp not in r1_ot),
        ))

    pc2 = {"what": ("the reconstructed built_tokens and last_telemetry_cached_tokens must "
                    "reproduce the DIRECT prefix the code subtracted, "
                    "prefix_used == max(built, telemetry), on EVERY skip. A single failure means "
                    "this reader's split of the prefix into its two sources is wrong and the "
                    "two-way split below must not be read."),
           "rows_checked": len(rows),
           "rows_ok": sum(1 for r in rows if r["prefix_reconstruction_identity_ok"]),
           "passes": all(r["prefix_reconstruction_identity_ok"] for r in rows),
           "failures": [r["opportunity_id"] for r in rows
                        if not r["prefix_reconstruction_identity_ok"]]}
    pc3 = {"what": ("the committed D162 price model recomputed from the event's own inputs must "
                    "reproduce the event's est_first_token_s exactly: "
                    "b0 + b1*uncached + b2*queued_uncached_ahead"),
           "coefficients": {"INTERCEPT_S": DP.INTERCEPT_S, "PER_UNCACHED_S": DP.PER_UNCACHED_S,
                            "PER_QUEUE_S": DP.PER_QUEUE_S, "source": DP.SOURCE,
                            "module_loaded_from": _DP_FROM,
                            "module_own_gate_drift_check": DP.assert_no_drift()},
           "rows_ok": sum(1 for r in rows if r["price_model_arithmetic_ok"]),
           "rows_checked": len(rows),
           "passes": all(r["price_model_arithmetic_ok"] for r in rows)}
    # PC4: a port-side / arm-side check that the re-check LET THINGS THROUGH too, so the gate is
    # not simply refusing everything. Every ADMITTED recall share_event must satisfy the re-check.
    admitted_recall = [e for e in r1["coord"]["share_events"]
                       if e["qtype"] == "recall" and e["kind"] == "recall" and e["admitted"]]
    pc4 = {"what": ("the characteristic decision of the re-check is a REFUSAL, and the share gate "
                    "sits behind it, so every admitted recall share_event is a recall the "
                    "re-check passed. Both decision kinds must be non-zero or the comparison is "
                    "one-sided."),
           "recall_recheck_refusals": len(ev),
           "recall_gate_admissions_behind_the_recheck": len(admitted_recall),
           "passes": bool(len(ev) > 0 and len(admitted_recall) > 0)}

    # ---- THE TWO-WAY (THREE-WAY) SPLIT -------------------------------------------------------
    never_written = [r for r in rows if not r["last_telemetry_cached_tokens_set"]]
    written = [r for r in rows if r["last_telemetry_cached_tokens_set"]]
    tel_won = [r for r in written if r["last_telemetry_cached_tokens"] > r["built_tokens_at_skip"]]
    built_won = [r for r in written
                 if r["last_telemetry_cached_tokens"] <= r["built_tokens_at_skip"]]
    belief_cold = [r for r in rows if r["readiness"] == "COLD"]
    belief_cold_engine_warm = [r for r in belief_cold
                               if (r["uo_engine_cached_tokens"] or 0) > 0]
    split = {
        "A_telemetry_never_written": {
            "n": len(never_written),
            "opportunity_ids": [r["opportunity_id"] for r in never_written],
            "remedy_if_this_were_the_cause": ("none available from telemetry; the field has no "
                                              "value to carry")},
        "B_telemetry_written_but_stale_or_capped": {
            "n": len(written),
            "B1_telemetry_below_built_tokens_so_built_won": {
                "n": len(built_won),
                "opportunity_ids": [r["opportunity_id"] for r in built_won],
                "what_it_means": ("the engine's last report was SMALLER than the coordinator's "
                                  "own build counter, so the fix changed nothing on these rows "
                                  "and the price is the pre-fix price")},
            "B2_telemetry_above_built_tokens_so_the_fix_bound": {
                "n": len(tel_won),
                "opportunity_ids": [r["opportunity_id"] for r in tel_won],
                "what_it_means": ("the fix is live on these rows and set the price")}},
        "C_belief_COLD_while_the_engine_served_the_prefix_WARM": {
            "n": len(belief_cold_engine_warm),
            "skips_with_belief_COLD_at_all": len(belief_cold),
            "opportunity_ids": [r["opportunity_id"] for r in belief_cold_engine_warm],
            "what_it_means": ("a BELIEF error, which needs a different remedy from either lag or "
                              "cap; the COLD branch of coordinator.py:1253 charges the whole "
                              "history")},
        "register": "measured counts over the full serialised event list, not a sample",
    }

    # the kind question the user asked explicitly
    kind_all = Counter()
    for r in rows:
        for k, n in r["telemetry_write_kinds_before_skip"].items():
            kind_all[k] += n
    telemetry_kind_question = {
        "hypothesis": ("last_telemetry_cached_tokens is updated ONLY by recall completions and "
                       "not by background warm and touch completions"),
        "verdict": "REFUTED, measured",
        "kinds_of_every_telemetry_write_on_the_skipped_sessions_before_the_skip":
            dict(kind_all),
        "kind_of_the_LAST_telemetry_write_before_each_skip":
            dict(Counter(r["last_telemetry_write_kind"] for r in rows)),
        "why_the_hypothesis_still_points_somewhere_real": (
            "touches and build pieces DO write the field, but they can never write a value larger "
            "than their own prompt, and both present only the already-built prefix: a touch sends "
            "s.frames[:len(confirmed_bytes_for)] with max_tokens 1 (coordinator.py:1118-1127) and "
            "a piece sends the built prefix plus one slice (coordinator.py:1197-1204). A recall is "
            "the ONLY request that presents the whole history. So the field is not 'stale', it is "
            "CENSORED at the largest prompt the session has ever carried, and on a session whose "
            "recalls are all skipped that ceiling never rises."),
        "consequence_measured_here": (
            "the running maximum of the telemetry over the session never exceeds the value the "
            "code already used on any of these rows, so 'use the running max instead of the last' "
            "recovers nothing: see fix_candidates.c_running_max"),
    }

    # ---- which term refused each skip --------------------------------------------------------
    by_term = Counter(r["refused_by"] for r in rows)
    costly = [r for r in rows if r["skip_cost_a_question"]]
    term_table = {
        "refused_by_size_term_alone": by_term.get("size", 0),
        "refused_by_queue_term": by_term.get("queue", 0),
        "of_which_cost_a_question": {
            "size": sum(1 for r in costly if r["refused_by"] == "size"),
            "queue": sum(1 for r in costly if r["refused_by"] == "queue")},
        "definition": ("size-decided iff b0 + b1*u > remaining_s with ZERO queue, which needs no "
                       "value of q; otherwise the queue term b2*q carried the refusal"),
        "register": "measured count over all serialised recall skips, not a constructed bound",
    }

    # ---- the lag, as a distribution ----------------------------------------------------------
    lag = {
        "definition": ("the engine's prefix MINUS the prefix the code subtracted. Positive means "
                       "the code under-credited the engine."),
        "vs_uo_same_opportunity": {
            "joined": sum(1 for r in rows if r["uo_request_joined"]),
            "unjoinable": sum(1 for r in rows if not r["uo_request_joined"]),
            "lag_tokens": _dist([r["lag_tokens_vs_uo"] for r in rows]),
            "predicted_u": _dist([r["predicted_u_AS_USED"] for r in rows]),
            "uo_engine_uncached": _dist([r["uo_engine_uncached"] for r in rows]),
            "predicted_over_engine_ratio": _dist([r["predicted_over_engine_ratio"]
                                                  for r in rows]),
            "CAVEAT": ("contaminated upward by uo's own earlier recalls on the same session; see "
                       "the stratification below")},
        "vs_uo_UNCONTAMINATED_stratum_prior_uo_recalls_eq_0": {
            "n": sum(1 for r in rows if r["prior_uo_recalls_on_session"] == 0),
            "opportunity_ids": [r["opportunity_id"] for r in rows
                                if r["prior_uo_recalls_on_session"] == 0],
            "lag_tokens": _dist([r["lag_tokens_vs_uo"] for r in rows
                                 if r["prior_uo_recalls_on_session"] == 0]),
            "predicted_over_engine_ratio": _dist([r["predicted_over_engine_ratio"] for r in rows
                                                  if r["prior_uo_recalls_on_session"] == 0]),
            "register": ("a small stratum reported WITH its size, not a population median; this "
                         "is the only stratum where uo's engine prefix was not planted by uo's "
                         "own earlier recall on that session")},
        "vs_r1_own_engine_probe_w60": {
            "n_with_a_probe": sum(1 for r in rows
                                  if r["r1_engine_prefix_lower_bound"]["w60"] is not None),
            "n_without": sum(1 for r in rows
                             if r["r1_engine_prefix_lower_bound"]["w60"] is None),
            "lag_tokens": _dist([r["lag_tokens_vs_r1_own_probe_w60"] for r in rows]),
            "register": ("a LOWER BOUND on the engine prefix, available on a minority of rows; "
                         "never mixed with the uo proxy")},
        "stratified_by_prior_uo_recalls": {
            str(k): _dist([r["predicted_over_engine_ratio"] for r in rows
                           if min(r["prior_uo_recalls_on_session"], 3) == k])
            for k in (0, 1, 2, 3)},
    }

    # ---- the feedback mechanism, measured ----------------------------------------------------
    sess = defaultdict(list)
    for r in rows:
        sess[r["session_id"]].append(r)
    feedback = {
        "claim": ("a recall is the only request that presents the WHOLE history to the engine, so "
                  "skipping a session's recalls keeps that session's engine prefix at roughly its "
                  "built prefix, which keeps the next recall's predicted u high, which skips it "
                  "again. The residual is therefore partly a CONSEQUENCE of the skips, not only "
                  "their cause."),
        "skips_on_sessions_r1_never_released_a_recall_on_before_the_skip":
            sum(1 for r in rows if r["prior_r1_recalls_on_session"] == 0),
        "of_which_uo_HAD_released_at_least_one_by_then":
            sum(1 for r in rows if r["prior_r1_recalls_on_session"] == 0
                and r["prior_uo_recalls_on_session"] > 0),
        "per_session": {sid: {"skips": len(rs),
                              "r1_recalls_released_in_whole_run":
                                  len(ixr["recalls"].get(sid, [])),
                              "uo_recalls_released_in_whole_run":
                                  len(ixu["recalls"].get(sid, [])),
                              "uo_engine_cached_at_its_first_recall_on_this_session":
                                  (None if not ixu["recalls"].get(sid)
                                   else int((ixu["req_by_opp"].get(
                                       ixu["recalls"][sid][0][1]) or {}).get("cached_tokens") or 0))}
                        for sid, rs in sorted(sess.items(), key=lambda x: -len(x[1]))},
    }

    # ---- what the skips cost, reconciled against the headline --------------------------------
    uo_only = uo_ot - r1_ot
    r1_only = r1_ot - uo_ot
    skip_ids = {r["opportunity_id"] for r in rows}
    cost = {
        "uo_on_time": len(uo_ot), "r1_on_time": len(r1_ot),
        "uo_on_time_not_r1": len(uo_only), "r1_on_time_not_uo": len(r1_only),
        "net_loss": len(uo_only) - len(r1_only),
        "of_the_loss_that_were_skips": len(uo_only & skip_ids),
        "of_the_loss_that_were_sent_but_late": len(uo_only - skip_ids),
        "skips_that_cost_nothing_because_uo_missed_them_too":
            sum(1 for r in rows if not r["uo_on_time"]),
        "r1_robot_delivered_but_late": sum(
            1 for o in r1["outcomes"]
            if o.get("kind") == "recall" and str(o.get("device_id") or "").startswith("robo")
            and o.get("t_delivered") is not None
            and float(o["t_delivered"]) - float(o["t_opportunity"]) > float(o["deadline_s"]) + 1e-9),
        "r1_robot_never_delivered": sum(
            1 for o in r1["outcomes"]
            if o.get("kind") == "recall" and str(o.get("device_id") or "").startswith("robo")
            and o.get("t_delivered") is None),
        "uo_robot_delivered_but_late": sum(
            1 for o in uo["outcomes"]
            if o.get("kind") == "recall" and str(o.get("device_id") or "").startswith("robo")
            and o.get("t_delivered") is not None
            and float(o["t_delivered"]) - float(o["t_opportunity"]) > float(o["deadline_s"]) + 1e-9),
        "a_skip_is_never_on_time": {
            "skips_r1_itself_scored_on_time": len(skip_ids & r1_ot),
            "what_it_means": ("every skip is an outcomes row with t_delivered None, so a skip is a "
                              "GUARANTEED miss on the robot axis. Converting a skip into a LATE "
                              "cloud answer is therefore neutral on robot_pool_on_time, and the "
                              "price of admitting it is paid by the OTHER axes (alert, dashcam, "
                              "assistance) through capacity, not by the robot axis through "
                              "lateness. uo, which has no release re-check at all, has 0 unsent "
                              "and 14 late and dashcam_all_meet FALSE.")},
    }

    # ---- the pre-registered check 2 ----------------------------------------------------------
    gain_uo = head["uo"]["robot_pool_on_time_COMMITTED"] - head["base"]["robot_pool_on_time_COMMITTED"]
    gain_r1 = head["r1"]["robot_pool_on_time_COMMITTED"] - head["base"]["robot_pool_on_time_COMMITTED"]
    check2 = {"base": head["base"]["robot_pool_on_time_COMMITTED"],
              "uo": head["uo"]["robot_pool_on_time_COMMITTED"],
              "shares_prefix": head["shares"]["robot_pool_on_time_COMMITTED"],
              "r1": head["r1"]["robot_pool_on_time_COMMITTED"],
              "retained_fraction": (round(gain_r1 / gain_uo, 4) if gain_uo else None),
              "bar": 0.90, "meets_bar": bool(gain_uo and gain_r1 / gain_uo >= 0.90),
              "release_infeasible_recall": {
                  "shares_prefix": sh["coord"]["counts"].get("release_infeasible_recall"),
                  "r1": counts_r1.get("release_infeasible_recall"),
                  "bar_at_most": 13,
                  "meets_bar": counts_r1.get("release_infeasible_recall", 999) <= 13}}

    # ---- THE ASSISTANCE CONTROL --------------------------------------------------------------
    assistance = assistance_control(cells, ix, seed)

    return {
        "seed": seed,
        "cells": {k: cells[k]["cell"] for k in ARMS},
        "comparison_validity": comparison_validity(rev, cells),
        "delivery_rules_applied": delivery,
        "positive_controls": {"PC1_committed_headline_numbers": pc1,
                              "PC2_prefix_reconstruction_identity": pc2,
                              "PC3_price_model_arithmetic": pc3,
                              "PC4_both_decision_kinds_occur": pc4,
                              "event_serialisation_check": event_count_check},
        "headline": head,
        "prereg_check2": check2,
        "per_skip": rows,
        "two_way_split": split,
        "telemetry_kind_question": telemetry_kind_question,
        "which_term_refused": term_table,
        "lag": lag,
        "feedback_mechanism": feedback,
        "what_the_skips_cost": cost,
        "assistance_control": assistance,
    }


def comparison_validity(rev: str, cells: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "input": {
            "fairness_digest": {k: c["run_meta"].get("fairness_digest") for k, c in cells.items()},
            "trace_fairness_digest": {k: c["run_meta"].get("trace_fairness_digest")
                                      for k, c in cells.items()},
            "digests_equal": {k: c["run_meta"].get("digests_equal") for k, c in cells.items()},
            "ratio": {k: c["run_meta"].get("ratio") for k, c in cells.items()},
            "n_devices": {k: c["coord"].get("n_devices") for k, c in cells.items()},
            "window_s": {k: c["coord"].get("window_s") for k, c in cells.items()}},
        "stack": {"server_kind": {k: c["run_meta"].get("server_kind") for k, c in cells.items()}},
        "decoding": ("unchanged across the arms: the recall body and its generation settings are "
                     "coordinator.py's B.RECALL_GEN, which no arm overrides; the arms differ only "
                     "in release policy and pricing"),
        "caching": ("PREFIX CACHING IS ENABLED and is load-bearing for this diagnosis, not an "
                    "incidental detail. Every `cached_tokens` read here is the engine's own "
                    "report on a LIVE request; nothing is a cold-prefill number and nothing cold "
                    "is compared with anything warm without saying so. The whole finding is about "
                    "what the prefix cache held and what the coordinator believed it held."),
        "r1_vs_uo_arm_difference": ("r1 carries the D179 release re-check and share admission and "
                                    "the D187 (1) cold-pricing fix; uo carries neither gate. So "
                                    "uo is NOT an ablation of r1 by one switch, and the "
                                    "cross-arm engine proxy inherits that: see PROXIES."),
    }


def assistance_control(cells: Dict[str, Any], ix: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """The pre-registered POSITIVE CONTROL said assistance must NOT move. It moved. Test whether
    assistance's OWN predicted u moved (the fix repricing assistance directly, which would be a
    finding) or only the denial reasons moved (indirect coupling, which is the benign reading).

    The r1 cell's share_events carry assistance's predicted u DIRECTLY. The pre-fix shares cell
    carries NO share_events and NO release_infeasible_events (the P0 instrumentation shipped with
    the fix), so the pre-fix value cannot be read off that cell. It is instead recomputed WITHIN
    THE r1 CELL by applying the PRE-FIX formula to the same rows, which needs no cross-cell join:
    pre-fix u = est_tokens - built_tokens on the warm branch, against the r1 event's own u.
    """
    r1, sh = cells["r1"], cells["shares"]
    ixr, ixs = ix["r1"], ix["shares"]
    ev = [e for e in r1["coord"]["share_events"] if e["qtype"] == "assistance"]
    # session id per opportunity, from the decision rows that carry it
    sid_by_opp = {}
    for d in r1["decision"]:
        s = session_of_note(d.get("note"))
        if s and d.get("kind") in ("release_recall", "release_infeasible") \
                and d.get("opportunity_ids"):
            sid_by_opp[str(d["opportunity_ids"][0])] = s
    joined = changed = unchanged = nojoin = 0
    changed_rows = []
    for e in ev:
        if e["kind"] != "recall":
            continue
        opp = str(e["key"])
        o = ixr["out_by_opp"].get(opp) or {}
        cp = o.get("cloud_payload") or {}
        est = int(cp.get("tokens_charged") or 0)
        sid = sid_by_opp.get(opp)
        if not est or not sid:
            nojoin += 1
            continue
        built = sum(tok for (td, tok) in ixr["piece"].get(sid, ()) if td < e["t"])
        u_prefix_formula = max(est - built, 0)
        joined += 1
        if u_prefix_formula != int(e["uncached"]):
            changed += 1
            changed_rows.append({"opportunity_id": opp, "est_tokens": est,
                                 "built_tokens": built, "u_prefix_formula": u_prefix_formula,
                                 "u_r1": int(e["uncached"])})
        else:
            unchanged += 1
    # the 12 assistance skips in the pre-fix cell, followed into r1
    sh_skips = []
    for d in sh["decision"]:
        if d.get("kind") != "release_infeasible":
            continue
        if not session_of_note(d.get("note")) or not d.get("opportunity_ids"):
            continue
        opp = str(d["opportunity_ids"][0])
        dev = (ixs["out_by_opp"].get(opp) or {}).get("device_id") or ""
        if dev.startswith("asst"):
            sh_skips.append((opp, float(d["t"])))
    se_by_key = {str(e["key"]): e for e in ev}
    followed = []
    for opp, t in sorted(sh_skips, key=lambda x: x[1]):
        e = se_by_key.get(opp)
        cp = (ixr["out_by_opp"].get(opp) or {}).get("cloud_payload") or {}
        followed.append({"opportunity_id": opp, "t_skip_in_prefix_cell": round(t, 1),
                         "r1_predicted_u": (None if e is None else int(e["uncached"])),
                         "r1_est_tokens": cp.get("tokens_charged"),
                         "r1_prefix_subtracted": (None if (e is None or not cp.get("tokens_charged"))
                                                  else int(cp["tokens_charged"]) - int(e["uncached"])),
                         "r1_gate_admitted": (None if e is None else e["admitted"]),
                         "r1_gate_reason": (None if e is None else e["reason"]),
                         "r1_on_time": cp.get("on_time")})
    cshare = sh["coord"]["counts"]
    cr1 = r1["coord"]["counts"]
    return {
        "preregistered_control": "assistance must NOT move",
        "what_moved": {
            "release_infeasible_assistance": {"shares_prefix": cshare.get(
                "release_infeasible_assistance", 0), "r1": cr1.get(
                    "release_infeasible_assistance", 0)},
            "share_admit_assistance": {"shares_prefix": cshare.get("share_admit_assistance"),
                                       "r1": cr1.get("share_admit_assistance")},
            "share_deny_assistance": {"shares_prefix": cshare.get("share_deny_assistance"),
                                      "r1": cr1.get("share_deny_assistance")},
            "ss_pool_on_time": {
                "shares_prefix": sh["cell_json"]["score"]["score"]["sweep"][0]["ss_pool_on_time"],
                "r1": r1["cell_json"]["score"]["score"]["sweep"][0]["ss_pool_on_time"],
                "pool": r1["cell_json"]["score"]["score"]["sweep"][0]["ss_pool_n"]}},
        "did_assistance_own_predicted_u_move": {
            "method": ("within the r1 cell, apply the PRE-FIX formula (est_tokens - built_tokens, "
                       "warm branch) to every assistance recall-gate share_event and compare with "
                       "the u the event records. No cross-cell join, so no proxy."),
            "events_joined": joined, "events_unjoinable": nojoin,
            "u_changed_by_the_fix": changed, "u_unchanged": unchanged,
            "changed_rows": changed_rows[:20],
            "why_it_is_zero": ("assistance sessions carry no build pieces and no whole-history "
                               "request, so built_tokens and last_telemetry_cached_tokens are "
                               "both 0 and the prefix subtracted is 0 under BOTH formulas: the "
                               "max() the fix introduced has nothing to choose between.")},
        "the_channel_the_movement_came_through": {
            "ruled_out_by_measurement": (
                "assistance was NOT repriced: its own predicted u is identical under the pre-fix "
                "and post-fix formulas on 371 of 371 joined gate events, because the prefix "
                "subtracted is 0 either way."),
            "ruled_out_by_counters": (
                "the SHARE GATE did not become more permissive for assistance either: "
                "share_deny_assistance is 14 before and 15 after, and `w_max` is still a live "
                "denial reason with 15 occurrences in r1. So 'headroom freed on w_max' is NOT "
                "what admitted the 12."),
            "what_is_left": (
                "all 12 were refused in the pre-fix cell by the RELEASE RE-CHECK, which sits "
                "BEFORE the share gate (coordinator.py:1277, ahead of the _share_ok call at "
                "1298). Its inputs are the request's own u, `queued_uncached_ahead` = "
                "`self._uncached_in_flight`, and `remaining_s`. The first is unchanged and the "
                "third is a trace property, so the movement came through the SHARED in-flight "
                "counter, which the recall fix lowers globally because recall releases increment "
                "it with their own predicted u (coordinator.py:1319)."),
            "total_recall_uncached_charged_into_the_shared_counter": {
                "r1_DIRECT_sum_of_admitted_recall_gate_uncached": sum(
                    int(e["uncached"]) for e in r1["coord"]["share_events"]
                    if e["qtype"] == "recall" and e["kind"] == "recall" and e["admitted"]),
                "register": ("a DIRECT sum for r1 only. The pre-fix cell carries no share_events, "
                             "so the same sum cannot be formed there and no ratio is quoted. The "
                             "channel is NAMED and the alternatives are excluded by measurement; "
                             "its magnitude across the two cells is NOT measured.")},
            "verdict": ("INDIRECT COUPLING through the shared in-flight counter. The "
                        "pre-registered control's INTENT holds - the fix did not touch "
                        "assistance pricing - but its LETTER does not: assistance moved, by 12 "
                        "admissions and 11 on-time questions, and a control that is allowed to "
                        "move through a shared counter is not a control. It should be restated "
                        "as 'assistance's own predicted u must not move', which is checkable and "
                        "which PASSES 371 of 371.")},
        "the_12_prefix_cell_assistance_skips_followed_into_r1": followed,
        "share_gate_reasons_for_assistance_in_r1": dict(
            Counter(e["reason"] for e in ev)),
        "share_gate_reasons_in_the_prefix_cell": {
            "AVAILABLE": False,
            "why": ("the pre-fix covex-v6-state-shares cell carries NO share_events and NO "
                    "release_infeasible_events: the P0 serialisation shipped WITH the fix. Only "
                    "the run-total counters exist there, and they are ITEM-PERIODS pooled across "
                    "all three types, so a per-type reason comparison across the two cells cannot "
                    "be made. Stated rather than approximated."),
            "pooled_counters_both_cells": {
                k: {"shares_prefix": cshare.get(k), "r1": cr1.get(k)}
                for k in sorted(set(list(cshare) + list(cr1))) if k.startswith("share_reason_")}},
    }


def fix_candidates(seeds_out: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The smallest honest fix, with what each candidate gets wrong and in which direction.

    DIRECTION RULE, which disqualifies two of the three candidates handed to this session: an
    OVERESTIMATE of the prefix understates u and admits a request that cannot make its deadline.
    """
    s4 = seeds_out[0]
    rows = s4["per_skip"]
    _seed = s4["seed"]
    runmax_gain = sum(1 for r in rows
                      if (r["telemetry_running_max_before_skip"] or 0) > r["prefix_used"])
    engine_pass = sum(1 for r in rows if r["would_pass_recheck_with_engine_prefix"])
    return {
        "SEED_COVERAGE": (f"every number in this block is seed {_seed} only, the first seed "
                          "analysed. The other seeds analysed are reported in seeds[*] and are "
                          "NOT pooled into these counts."),
        "a_add_tokens_uploaded_since_the_last_completion": {
            "does_the_bookkeeping_exist": (
                "PARTLY. `s.est_tokens` (the current history) and `s.sent_bytes_for` "
                "(cstate.py:112) exist, but the prompt of the last completed request is NOT kept "
                "on the session: engine_actions.py:358 stores only `cached_tokens`. So this fix "
                "needs a NEW field, `last_telemetry_prompt_tokens`, written at the same site."),
            "what_it_would_get_wrong_and_in_which_direction": (
                "OVERESTIMATE of the prefix, which is the UNSAFE direction. It asserts that every "
                "token uploaded since the last completion is resident, and the measurement here "
                "says that is false: on robo001|s000 the code subtracted 5,120 while the "
                "session's history was 25,501 tokens, and uo's OWN first recall on that session "
                "at the same instant reports the engine holding 6,928, not 25,501. uo's measured "
                "first-token time on that opportunity was 4.413 s against 2.953 s of slack, so "
                "this candidate converts a skip into a 1.5 s LATE answer on exactly the row it is "
                "aimed at."),
            "verdict": "DISQUALIFIED by the direction rule, on measured evidence, not on argument",
        },
        "b_use_the_coordinators_own_record_of_what_it_has_sent": {
            "does_the_bookkeeping_exist": (
                "YES: `s.sent_bytes_for` and `s.confirmed_bytes_for` (cstate.py:112-113) and "
                "`s.frames`."),
            "what_it_would_get_wrong_and_in_which_direction": (
                "OVERESTIMATE, same direction and worse. `sent` is not `resident`: the frozen "
                "grid turns its 62,944-token GPU pool over about 89 times in 1,200 s "
                "(study_frozen_test.md 17.3, quoted in engine_actions.py), so a frame sent long "
                "ago is routinely evicted. It would also double-count frames re-sent as bytes "
                "after a 400 (racefix_bytes_resent)."),
            "verdict": "DISQUALIFIED by the direction rule",
        },
        "c_running_max": {
            "what": "take the running maximum of last_telemetry_cached_tokens instead of the last",
            "measured_gain": {
                "skips_where_the_running_max_exceeds_the_prefix_already_used": runmax_gain,
                "of": len(rows)},
            "what_it_would_get_wrong_and_in_which_direction": (
                "OVERESTIMATE after an eviction, since a maximum never falls. But it does not "
                "arise: the measured gain is zero, because `prefix_used = max(built_tokens, last "
                "telemetry)` already dominates every earlier telemetry value on all of these "
                "rows."),
            "verdict": "REJECTED: measured gain is zero, so it is not a fix at all",
        },
        "THE_FINDING_THAT_DISPLACES_ALL_THREE": {
            "what_the_measurement_says": (
                "the prefix the code subtracts is NOT materially wrong in the r1 arm. Only "
                f"{s4['which_term_refused']['refused_by_size_term_alone']} of {len(rows)} skips "
                "were refused by the size term at all; the other "
                f"{s4['which_term_refused']['refused_by_queue_term']} were refused by the QUEUE "
                "term b2*queued_uncached_ahead, where the predicted u is already small. And of "
                "the size-decided skips, almost all sit on sessions on which r1 had never "
                "released a recall, so the engine genuinely did not hold the history: the 6.4x "
                "ratio against uo is largely uo's own earlier recalls on those sessions, not a "
                "pricing residue."),
            "the_mechanism_named": (
                "a recall is the ONLY request that presents the whole history to the engine. A "
                "touch sends s.frames[:len(confirmed_bytes_for)] (coordinator.py:1118-1127) and a "
                "build piece sends the built prefix plus one slice (coordinator.py:1197-1204), so "
                "neither can ever report, or create, a prefix larger than the built prefix. The "
                "re-check at coordinator.py:1277-1296 prices a recall on its OWN first-token "
                "feasibility and is blind to the prefix that sending it PLANTS for that session's "
                "later recalls. Skipping the first recall on a session therefore keeps the "
                "session cold, which keeps the next recall expensive, which skips it again."),
            "the_smallest_honest_fix": {
                "statement": (
                    "exempt a session's FIRST whole-history recall from the release re-check, "
                    "once per session, and let the re-check govern every later recall unchanged."),
                "file_line": ("experiments/orchestration/live2/coordinator.py:1277, the "
                              "`if self._release_recheck:` guard in `_submit_recall`; the "
                              "condition becomes `if self._release_recheck and not "
                              "s.whole_history_sent:` with the flag set beside "
                              "`self._uncached_in_flight += int(_uncached)` at "
                              "coordinator.py:1319 and cleared where `built_tokens` is reset "
                              "(coordinator.py:757)."),
                "why_it_is_the_smallest": (
                    "it changes NO price, NO coefficient, NO floor, NO W_max and NO deadline; it "
                    "changes the number of times the re-check is consulted on a session from "
                    "every recall to every recall after the first. It is a RELEASE-POLICY change "
                    "and therefore a NEW LABELLED VERSION under D187, not an implementation fix."),
                "what_it_gets_wrong_and_in_which_direction": (
                    "it admits a request the predictor says is infeasible, so it spends LATENESS "
                    "and it spends CAPACITY. The lateness side is measured and is cheaper than it "
                    "looks: all 34 skips are outcomes rows with t_delivered None and 0 of them "
                    "are scored on time, so a skip is already a guaranteed miss on the robot "
                    "axis, and turning one into a late cloud answer cannot lower "
                    "robot_pool_on_time. The REAL price is paid on the other axes through the "
                    "capacity the admitted recall consumes: uo, which has no re-check at all, "
                    "has dashcam_all_meet FALSE where r1 has TRUE. That is the trade this fix "
                    "makes, stated as a trade and not as a free gain."),
                "what_it_does_NOT_address_stated_before_the_bar_is_quoted": {
                    "skips_on_sessions_r1_had_already_warmed_with_a_recall": sum(
                        1 for r in rows if r["prior_r1_recalls_on_session"] > 0),
                    "of_which_the_queue_term_and_not_the_size_term_refused": sum(
                        1 for r in rows if r["prior_r1_recalls_on_session"] > 0
                        and r["refused_by"] == "queue"),
                    "why": ("on those sessions the prefix the code subtracted is close to what "
                            "r1's own engine probe reports and the size term already fits the "
                            "slack; the refusal is b2 * queued_uncached_ahead. A bootstrap "
                            "exemption does nothing for them."),
                    "honest_arithmetic_on_the_bar": (
                        "the exemption can recover at most the skips on never-warmed sessions "
                        "LESS one per such session (the exempted recall itself is predicted "
                        "infeasible and uo's measured first-token times on those first recalls, "
                        "4.4 to 5.5 s, say it would arrive late): at s4 that is "
                        f"{sum(1 for r in rows if r['prior_r1_recalls_on_session'] == 0)} minus "
                        f"{len({r['session_id'] for r in rows if r['prior_r1_recalls_on_session'] == 0})}"
                        " sessions. So this fix ALONE does NOT reach the bar of at most 13, and "
                        "is not offered as if it did. It is the smallest change that attacks the "
                        "mechanism the measurement actually identifies."),
                    "register": "a constructed bound from measured counts, not a predicted result"},
                "the_bound_that_must_be_stated_with_it": (
                    "at most one extra admission per robot session, so at most "
                    f"{len(s4['feedback_mechanism']['per_session'])} extra recalls at s4 against "
                    "the 34 skips. This is a CONSTRUCTED BOUND from the session count, not a "
                    "measured count of what would happen."),
                "pre_registered_pass_check": {
                    "primary": ("release_infeasible_recall at s4 falls from 34 to at most 13, the "
                                "unchanged pre-registered bar from c7c60e5b"),
                    "secondary": ("robot_pool_on_time at s4 rises from 95 toward 118 and retains "
                                  "at least 90 percent of uo's gain over base, i.e. at least "
                                  "0.90 * (118 - 35) + 35 = 110 of 132"),
                    "FAILURE_CONDITION_that_must_be_reported_as_failure": (
                        "if release_infeasible_recall falls but robot_pool_on_time does not rise "
                        "to match, the admitted recalls are arriving late and the named "
                        "explanation is wrong"),
                    "the_control_that_must_hold": (
                        "dashcam_all_meet stays TRUE and ss_pool_on_time does not fall below 355 "
                        "of 357 at s4. If either moves, the fix bought the robot axis with the "
                        "axes the share gate exists to protect, and must be reported as a "
                        "trade-off ablation and not as a fix."),
                    "the_positive_control_on_the_check_itself": (
                        "re-score covex-v6-state-uo and hybrid-F-lhreq-noc3 at s4 with the same "
                        "reader and require 118 and 35 exactly before the new cell is read")},
            },
            "the_upper_bound_a_perfect_prefix_would_buy": {
                "skips_that_would_pass_the_FULL_recheck_with_the_engines_own_uncached":
                    engine_pass,
                "of": len(rows),
                "register": ("a CONSTRUCTED BOUND under a counterfactual the arm cannot realise, "
                             "because the engine prefix it uses is uo's and was planted by uo's "
                             "own earlier recalls. It is the ceiling on any prefix-estimation "
                             "fix, not a target.")},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default="origin/main")
    ap.add_argument("--seeds", default="4")
    ap.add_argument("--out", default=str(REPO / "results/orchestration/live2/frozen_test"
                                                "/d187_r1_residual_diagnosis.json"))
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",") if x.strip()]

    present, absent = [], []
    for s in seeds:
        ok = all(have(args.rev, f"{RUNS}/{v}_n16_s{s}{CELL_SUFFIX}/coordinator_result.json")
                 for v in ARMS.values())
        (present if ok else absent).append(s)
    out: Dict[str, Any] = {
        "_what": ("why the 34 residual recall skips in covex-v6-state-shares-r1 are still "
                  "refused after the D187 (1) cold-pricing fix, and what the smallest honest fix "
                  "is. READ-ONLY, committed cells only."),
        "rev": subprocess.run(["git", "-C", str(REPO), "rev-parse", args.rev],
                              check=True, stdout=subprocess.PIPE).stdout.decode().strip(),
        "seeds_requested": seeds, "seeds_analysed": present,
        "seeds_not_on_the_rev": absent,
        "seed_coverage_note": ("every number in this file covers the seeds listed in "
                               "seeds_analysed and no others"),
        "fields_read_DIRECTLY": [
            "release_infeasible_events[*].uncached (the predicted u the re-check used)",
            "release_infeasible_events[*].queued_uncached_ahead",
            "release_infeasible_events[*].est_first_token_s",
            "release_infeasible_events[*].remaining_s",
            "release_infeasible_events[*].readiness",
            "release_infeasible_events[*].est_tokens",
            "release_infeasible_events[*].session_id / opportunity_id / t / deadline_abs",
            "share_events[*].qtype / kind / uncached / admitted / reason / w_by_type / key",
            "request.jsonl prompt_tokens, cached_tokens, t_submit, t_first_token, t_done",
            "cell.json score.score.sweep[0] (robot_pool_on_time, ss_pool_on_time, "
            "dashcam_all_meet)"],
        "fields_DERIVED_by_arithmetic_from_direct_fields": [
            "prefix_used = est_tokens - uncached (exact on the WARM branch, which is all 34)"],
        "fields_STILL_INFERRED": [p["column"] for p in PROXIES],
        "PROXIES": PROXIES,
        "seeds": [],
    }
    for s in present:
        out["seeds"].append(analyse_seed(args.rev, s))
    if out["seeds"]:
        out["fix_candidates"] = fix_candidates(out["seeds"])
    out["_provenance"] = {
        "git_commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                     check=True, stdout=subprocess.PIPE).stdout.decode().strip(),
        "script": "d187_r1_residual_diagnosis.py", "model": None, "device": "flash_cpu",
        "n": len(present),
        "timestamp": _dt.datetime.utcnow().isoformat()}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=float))
    print("wrote", args.out)
    for sd in out["seeds"]:
        pc = sd["positive_controls"]
        print("seed", sd["seed"],
              "PC1", pc["PC1_committed_headline_numbers"]["passes"],
              "PC2", pc["PC2_prefix_reconstruction_identity"]["passes"],
              "PC3", pc["PC3_price_model_arithmetic"]["passes"],
              "PC4", pc["PC4_both_decision_kinds_occur"]["passes"],
              "| skips", len(sd["per_skip"]),
              "size", sd["which_term_refused"]["refused_by_size_term_alone"],
              "queue", sd["which_term_refused"]["refused_by_queue_term"])


if __name__ == "__main__":
    main()
