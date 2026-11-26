#!/usr/bin/env python3
"""D273 (1): THE TWO HALVES OF THE TRUE-OUTAGE PROOF. CPU, read-only, no GPU, no cell.

The ruling asks for both halves and names the one that could go wrong silently.

  HALF A  THE CLOUD-SIDE HISTORY FOR VICTIMS HAS EXACTLY THE WINDOW'S FRAMES MISSING.
          Not "fewer frames", EXACTLY those: the set of `history_batch` records present with the
          switch off and absent with it on must equal, record for record, the set whose offer time
          lies in the window and whose device is a victim. The token arithmetic is checked on top
          of the set: the cloud's cumulative history after the window must fall by exactly the lost
          tokens, and each later question's `history_tokens` by exactly the tokens lost at or
          before its own ask time. A non-victim's records and a victim's out-of-window records must
          be untouched.

  HALF B  THE DEVICE-SIDE HISTORY IS COMPLETE, AND THIS IS THE HALF THAT COULD SILENTLY GO WRONG.
          If the switch also shortened the device's history it would have broken the DEVICE rather
          than the uplink, and that would invalidate every cell WITHOUT failing the off-by-default
          identity proof, because that proof only runs with the outage off. So it is proved on the
          artefact: `device_answers` must be BYTE-IDENTICAL between switch off and switch on, with
          every row's `history_tokens` and `device_latency_s` unchanged, and the device answer for
          every affected question must still be present.

  AND THE NEGATIVE CONTROL, because a proof that cannot fail is not a proof: the same comparison is
  run between switch-off and switch-off. Half A must then find ZERO missing records. If it does not,
  the comparator is broken and neither half is readable.

Usage:
  python d273_true_outage_proofs.py --repo DIR --out FILE [--seed 4 --seed 5] [--k 3 --k 5]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[2]

WORKLOAD = dict(robot_question_set="lh_req", ss_question_set="ss2", dashcam_format="epg",
                dashcam_min_frames=3, robot_upload="per-frame", robot_reask_mean_s=30.0)
D2_TOK_PER_IMG = 90          # fleet/data_sources.py, StudyRH4 D2 accounting


def load(repo: Path):
    live2 = repo / "experiments/orchestration/live2"
    for p in (str(live2), str(live2 / "fleet"), str(repo / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import data_sources as DS
    import trace as TR
    return DS, TR


def gen(DS, TR, seed, n, ratio, run_s, k, d, semantics, deadline_s):
    """`semantics=None` means THE OUTAGE IS OFF: no k, no D, no placement, the committed call."""
    DS.ROBOT_DEADLINE_S = float(deadline_s)
    kw = dict(WORKLOAD)
    if semantics is None:
        return TR.generate_trace(seed, n, ratio, run_s, "A", **kw)
    if semantics != "buffered":
        kw["outage_semantics"] = semantics
    return TR.generate_trace(seed, n, ratio, run_s, "A", outage_robots_k=k, outage_duration_s=d,
                             outage_placement="centre", **kw)


def canon(TR, rows) -> str:
    return "\n".join(TR._canon(r) for r in rows)


def sid_of(r) -> str:
    return str(r.get("session_id"))


def key(r) -> tuple:
    return (r.get("kind"), str(r.get("device_id")), str(r.get("session_id")),
            str(r.get("batch_id") or r.get("question_id") or ""), round(float(r.get("t", 0.0)), 6))


def half_a(TR, off, on, om, per_frame_tok: int = D2_TOK_PER_IMG) -> Dict[str, Any]:
    """`off` MUST be the NO-OUTAGE trace: it is the only one whose history offers still carry their
    original times, so it is the only valid reference for "which records were offered inside the
    window"."""
    t0, t1 = float(om["t_start"]), float(om["t_end"])
    vset = set(om["robots"])
    off_h = {key(r): r for r in off["records"] if r["kind"] == "history_batch"}
    on_h = {key(r): r for r in on["records"] if r["kind"] == "history_batch"}
    missing = sorted(k for k in off_h if k not in on_h)
    added = sorted(k for k in on_h if k not in off_h)
    # THE SET THE RULING NAMES: a victim's history record offered inside the window.
    expected = sorted(key(r) for r in off["records"]
                      if r["kind"] == "history_batch" and str(r.get("device_id")) in vset
                      and t0 <= float(r["t"]) < t1)
    exact = (missing == expected)

    # the lost tokens, PER FRAME, and which sessions lost their header-carrying batch
    lost_tok: Dict[str, List[Any]] = {}
    header_sessions = set()
    for k2 in expected:
        r = off_h[k2]
        nfr_r = len(r.get("frame_refs") or ())
        lost_tok.setdefault(sid_of(r), []).append((float(r["t"]), nfr_r * per_frame_tok))
        if int(r["est_tokens"]) > nfr_r * per_frame_tok:
            header_sessions.add(sid_of(r))
    lost_frames = sum(len(off_h[k2].get("frame_refs") or ()) for k2 in expected)
    lost_tokens = sum(tok for v in lost_tok.values() for _t, tok in v)

    # NOTHING ELSE MOVED. `cum_tokens` is expected to fall and is checked separately below;
    # `est_tokens` may rise by exactly the 31-token D2 header on the first surviving batch of a
    # session that lost its header, and by nothing else, anywhere.
    moved_elsewhere = []
    header_bumps = []
    for k2, r_off in off_h.items():
        r_on = on_h.get(k2)
        if r_on is None:
            continue
        a_ = {kk: vv for kk, vv in r_off.items() if kk not in ("cum_tokens", "est_tokens")}
        b_ = {kk: vv for kk, vv in r_on.items() if kk not in ("cum_tokens", "est_tokens")}
        if a_ != b_:
            moved_elsewhere.append({"key": list(k2), "why": "a non-token field moved"})
            continue
        d_tok = int(r_on.get("est_tokens", 0)) - int(r_off.get("est_tokens", 0))
        if d_tok == 0:
            continue
        if d_tok == 31 and sid_of(r_on) in header_sessions:
            header_bumps.append({"key": list(k2), "session": sid_of(r_on)})
        else:
            moved_elsewhere.append({"key": list(k2), "why": "est_tokens moved by %d" % d_tok})

    # THE CLOUD'S CUMULATIVE HISTORY: every surviving record must fall by exactly the frames lost
    # at or before its own offer time, and by nothing else.
    cum_bad = []
    for k2, r_on in on_h.items():
        r_off = off_h.get(k2)
        if r_off is None:
            continue
        cut = sum(tok for t, tok in lost_tok.get(sid_of(r_on), [])
                  if t <= float(r_on["t"]) + 1e-9)
        want = int(r_off["cum_tokens"]) - cut
        if int(r_on["cum_tokens"]) != want:
            cum_bad.append({"key": list(k2), "want": want, "got": int(r_on["cum_tokens"]),
                            "cut": cut})

    # AND EVERY LATER QUESTION'S CLOUD HISTORY, by the same rule on its own session clock.
    off_q = {key(r): r for r in off["records"] if r["kind"] == "recall_question"}
    on_q = {key(r): r for r in on["records"] if r["kind"] == "recall_question"}
    hist_bad = []
    n_q_reduced = 0
    for k2, r_on in on_q.items():
        r_off = off_q.get(k2)
        if r_off is None or r_on.get("t_ask_session") is None:
            continue
        sess0 = float(r_on["t"]) - float(r_on["t_ask_session"])
        cut = sum(tok for t, tok in lost_tok.get(sid_of(r_on), [])
                  if t - sess0 <= float(r_on["t_ask_session"]) + 1e-9)
        want = int(r_off["history_tokens"]) - cut
        if int(r_on["history_tokens"]) != want:
            hist_bad.append({"key": list(k2), "want": want, "got": int(r_on["history_tokens"]),
                             "cut": cut})
        elif cut:
            n_q_reduced += 1

    asks_same = ({k2: float(r["t"]) for k2, r in off_q.items() if k2 in on_q}
                 == {k2: float(r["t"]) for k2, r in on_q.items() if k2 in off_q})
    q_missing = sorted(k for k in off_q if k not in on_q)
    return {
        "n_history_records_no_outage": len(off_h), "n_history_records_true": len(on_h),
        "n_missing": len(missing), "n_added_that_should_not_exist": len(added),
        "n_expected_missing": len(expected),
        "MISSING_SET_IS_EXACTLY_THE_WINDOWS_VICTIM_FRAMES": bool(exact),
        "lost_frames": lost_frames, "lost_tokens": lost_tokens,
        "lost_tokens_equals_90_per_frame": bool(lost_tokens == lost_frames * per_frame_tok),
        "sessions_whose_header_batch_was_lost": sorted(header_sessions),
        "n_header_reattributions": len(header_bumps),
        "_header_note": ("a header is not a frame: the cut is %d tokens per lost frame and the "
                         "one-off 31-token D2 header is re-attributed to the first surviving "
                         "batch, so the equality above is exact rather than 31 short per session"
                         % per_frame_tok),
        "n_other_records_that_moved": len(moved_elsewhere),
        "first_other_moves": moved_elsewhere[:5],
        "CUM_TOKENS_ARITHMETIC_EXACT": bool(not cum_bad), "cum_token_mismatches": cum_bad[:5],
        "QUESTION_HISTORY_ARITHMETIC_EXACT": bool(not hist_bad),
        "question_history_mismatches": hist_bad[:5],
        "n_questions_whose_cloud_history_fell": n_q_reduced,
        "n_questions_missing": len(q_missing),
        "ASK_TIMES_UNCHANGED": bool(asks_same),
        "PASS": bool(exact and not added and not moved_elsewhere and not cum_bad
                     and not hist_bad and asks_same and not q_missing
                     and lost_tokens == lost_frames * per_frame_tok),
    }


def half_b(TR, off, on) -> Dict[str, Any]:
    a = canon(TR, off["device_answers"])
    b = canon(TR, on["device_answers"])
    ha = hashlib.sha256(a.encode()).hexdigest()[:16]
    hb = hashlib.sha256(b.encode()).hexdigest()[:16]
    off_rows = {str(r.get("opportunity_key")): r for r in off["device_answers"]}
    on_rows = {str(r.get("opportunity_key")): r for r in on["device_answers"]}
    fields = ("history_tokens", "device_latency_s", "device_answer", "device_correct",
              "gold_letter")
    moved = []
    for k2, r in off_rows.items():
        r2 = on_rows.get(k2)
        if r2 is None:
            moved.append({"opportunity_key": k2, "why": "row missing with the switch on"})
            continue
        for f in fields:
            if r.get(f) != r2.get(f):
                moved.append({"opportunity_key": k2, "field": f,
                              "off": r.get(f), "on": r2.get(f)})
    return {"n_device_answers_off": len(off["device_answers"]),
            "n_device_answers_on": len(on["device_answers"]),
            "digest_off": ha, "digest_on": hb,
            "BYTE_IDENTICAL": bool(ha == hb),
            "n_rows_that_moved": len(moved), "first_moves": moved[:5],
            "fields_checked": list(fields),
            "PASS": bool(ha == hb and not moved),
            "_why_this_half": ("a switch that shortened the DEVICE's history would have broken the "
                              "device rather than the uplink, and would pass the off-by-default "
                              "identity proof while invalidating every cell, because that proof "
                              "only runs with the outage off")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, action="append", default=None)
    ap.add_argument("--k", type=int, action="append", default=None)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--ratio", default="3:11:2")
    ap.add_argument("--run-s", type=float, default=1200.0)
    ap.add_argument("--d", type=float, default=120.0)
    ap.add_argument("--robot-deadline-s", type=float, default=3.0)
    a = ap.parse_args(argv)
    seeds = sorted(a.seed) if a.seed else [4, 5]
    ks = sorted(a.k) if a.k else [1, 3, 5]
    repo = Path(a.repo) if a.repo else REPO_DEFAULT
    DS, TR = load(repo)

    cells: Dict[str, Any] = {}
    for sd in seeds:
        for k in ks:
            base = gen(DS, TR, sd, a.n, a.ratio, a.run_s, 0, 0.0, None, a.robot_deadline_s)
            buf = gen(DS, TR, sd, a.n, a.ratio, a.run_s, k, a.d, "buffered", a.robot_deadline_s)
            on = gen(DS, TR, sd, a.n, a.ratio, a.run_s, k, a.d, "true", a.robot_deadline_s)
            off = base
            om = on["meta"]["outage"]
            ctl = gen(DS, TR, sd, a.n, a.ratio, a.run_s, 0, 0.0, None, a.robot_deadline_s)
            neg = half_a(TR, base, ctl, om)
            cells["s%d_k%d" % (sd, k)] = {
                "outage_semantics_recorded": om.get("semantics"),
                "placement_recorded": om.get("placement"),
                "window": [om.get("t_start"), om.get("t_end")],
                "victims": om.get("robots"),
                "meta_lost_block": om.get("lost"),
                "_reference": ("the NO-OUTAGE trace, because it is the only one whose history "
                               "offers still carry their original times. Comparing against the "
                               "BUFFERED trace is what the first version of this proof did, and it "
                               "found 0 expected-missing against 298 actually missing, because "
                               "buffered had already re-timed them."),
                "HALF_A_cloud_history_exactly_short": half_a(TR, base, on, om),
                "HALF_B_device_history_complete": half_b(TR, base, on),
                "BUFFERED_ARM_still_loses_nothing": {
                    "n_history_records_no_outage": sum(
                        1 for r in base["records"] if r["kind"] == "history_batch"),
                    "n_history_records_buffered": sum(
                        1 for r in buf["records"] if r["kind"] == "history_batch"),
                    "PASS": bool(sum(1 for r in base["records"] if r["kind"] == "history_batch")
                                 == sum(1 for r in buf["records"]
                                        if r["kind"] == "history_batch")),
                    "_why": ("the other semantics, proved on the way past: buffered must keep every "
                             "record and only move offer times, so its record count must equal the "
                             "no-outage count while true's is short by the lost frames")},
                "NEGATIVE_CONTROL_off_vs_off": {
                    "n_missing": neg["n_missing"],
                    "PASS": bool(neg["n_missing"] == 0 and neg["n_added_that_should_not_exist"] == 0),
                    "_why": ("the same comparison with the switch OFF on both sides. It must find "
                             "nothing missing; if it finds something, the comparator is broken and "
                             "neither half above is readable.")},
            }
    allpass = all(c["HALF_A_cloud_history_exactly_short"]["PASS"]
                  and c["HALF_B_device_history_complete"]["PASS"]
                  and c["BUFFERED_ARM_still_loses_nothing"]["PASS"]
                  and c["NEGATIVE_CONTROL_off_vs_off"]["PASS"] for c in cells.values())
    out = {
        "_what": ("D273 (1): true-outage semantics proofs. Half A, the cloud-side history is short "
                  "by EXACTLY the window's victim frames; half B, the device-side history is "
                  "complete; plus an off-against-off negative control."),
        "cell": {"n_devices": a.n, "ratio": a.ratio, "run_s": a.run_s, "D": a.d,
                 "seeds": seeds, "k": ks, "placement": "centre",
                 "robot_deadline_s": a.robot_deadline_s, "workload": WORKLOAD},
        "cells": cells,
        "ALL_PASS": bool(allpass),
        "VERDICT": ("PASS: with the switch on, the cloud loses exactly the window's victim frames "
                    "and nothing else, the token arithmetic is exact, ask times do not move, and "
                    "the device's own history is byte-identical. The off-against-off control finds "
                    "nothing, so the comparator can fail."
                    if allpass else
                    "STOP: a half failed. Do not run a cell; see the per-cell blocks."),
    }
    try:
        sys.path.insert(0, str(repo / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d273_true_outage_proofs.py", model="none-cpu",
                                   device="flash_cpu", n=len(cells), args=a)
    except Exception as e:
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("%-10s %-9s %-9s %-9s %7s %7s %6s" % ("cell", "halfA", "halfB", "neg-ctl", "lost_fr",
                                                "lost_tok", "q_cut"))
    for k2, c in cells.items():
        A = c["HALF_A_cloud_history_exactly_short"]
        print("%-10s %-9s %-9s %-9s %7d %7d %6d" % (
            k2, A["PASS"], c["HALF_B_device_history_complete"]["PASS"],
            c["NEGATIVE_CONTROL_off_vs_off"]["PASS"], A["lost_frames"], A["lost_tokens"],
            A["n_questions_whose_cloud_history_fell"]))
    print(out["VERDICT"])
    return 0 if allpass else 1


if __name__ == "__main__":
    raise SystemExit(main())
