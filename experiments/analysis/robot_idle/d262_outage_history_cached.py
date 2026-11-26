#!/usr/bin/env python3
"""D262 / D266 item 2: THE HISTORY-CACHED OBSERVABLE. CPU, read-only, no GPU, no engine.

WHY THIS FILE EXISTS. The committed record orders this quantity and nothing computes it. The
D244 ruling orders "history cached at the FIRST POST-RECONNECT QUESTION, per robot"; AMENDMENT 2
records that BOTH robot attainment metrics are blind to the device-only questions in opposite
directions and that "the discriminating signal has to come from the history-cached observable on
the POST-RECONNECT questions, which is exactly why that observable is collected"; and the D262
estimate found that no script in `experiments/` consumes `cached_fraction` for an outage and that
no scorer for this observable exists. If the abandon check on the robot attainment metrics fails,
THIS IS THE ONLY THING THE DESIGN RESTS ON, so it is built before the cells run rather than after.

WHAT IT MEASURES, CONCRETELY, AND WHERE EVERY FIELD COMES FROM.
  - The victims and the window come from `trace_meta.json`'s `.outage` (`robots`, `t_start`,
    `t_end`, and on the D266 centre rule `victim_permutation`), or, with `--regenerate`, from
    re-running `fleet/trace.py` on the cell's own header arguments. They are never guessed from a
    directory name.
  - A question's ASK time is the `recall_question` record's `t` in `trace.jsonl`. It is the
    deadline anchor and the outage does NOT move it; only `t_offer` moves. Using `t_submit` from
    the request log instead would read the OFFER, which is the quantity the outage deliberately
    shifts, so the ask time is taken from the trace whenever a trace is available and the fallback
    is LABELLED in the output.
  - "History cached" is the committed definition and not a new one: `cache_path` is WARM when
    `cached_tokens > 0` else COLD, with `cached_fraction = cached_tokens / prompt_tokens`
    (`live2/CONTRACT.md:129`, D81). Both come from the engine's own per-request usage report and
    never from the coordinator's belief.

THE THREE CONTROLS, AND NONE OF THEM IS OPTIONAL.
  1. PREFIX CACHING IS PROVED, NOT ASSUMED. `cached_tokens` is identically zero with prefix
     caching off, so the whole observable would be a correct and consistent zero - the exact
     failure shape CLAUDE.md's mechanism protocol exists to catch. The cell's own
     `header.json` carries `server.resolved.engine_reported.enable_prefix_caching` (the ENGINE's
     report, not the launch line) and `server.resolved.flags_set_twice`, because the flag is
     passed TWICE in this grid - `--no-enable-prefix-caching` then `--enable-prefix-caching` -
     and only argparse's last-wins makes it ON. That duplicated flag is read here and restated,
     because the same duplicated-flag shape produced a wrong host size in D250.
  2. A WITHIN-CELL CONCURRENT CONTROL: the same quantity, at the same instant, for the robots that
     were NOT victims. If non-victims are cold too, the cell is measuring the cell and not the
     outage.
  3. A WITHIN-ROBOT BEFORE CONTROL: the same victim's LAST PRE-OUTAGE question. A victim that was
     already cold before the window cannot have "lost" its history to the outage.
  And one refusal: if NO request row in the whole cell has `cached_tokens > 0`, the observable is
  UNSCORABLE in that cell and the script says so instead of reporting zeros as a finding.

WHAT IS NOT SCORED, EVER. The device-only questions inside the window have no cloud payload and no
request rows. They are reported as a COUNT per victim, per AMENDMENT 2's surviving measurement
fact, and are never counted as cached, uncached, hit or miss.

Usage:
  python d262_outage_history_cached.py --cell DIR [--cell DIR ...] --out FILE
                                       [--trace-dir DIR] [--regenerate] [--repo DIR]
  python d262_outage_history_cached.py --pair SMALL_K_CELL LARGE_K_CELL --out FILE ...
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[2]


def _open_any(d: Path, stem: str):
    for cand, op in ((d / (stem + ".gz"), gzip.open), (d / stem, open)):
        if cand.exists():
            return op(cand, "rt")
    return None


def read_jsonl(d: Path, stem: str) -> List[Dict[str, Any]]:
    fh = _open_any(d, stem)
    if fh is None:
        return []
    with fh:
        return [json.loads(l) for l in fh if l.strip()]


def prefix_cache_proof(cell: Path) -> Dict[str, Any]:
    hp = cell / "header.json"
    if not hp.exists():
        return {"READ": False, "why": "no header.json", "PREFIX_CACHING_ON": None}
    h = json.loads(hp.read_text())
    srv = (h.get("server") or {})
    res = (srv.get("resolved") or {})
    eng = (res.get("engine_reported") or {})
    twice = (res.get("flags_set_twice") or {}).get("--enable-prefix-caching")
    reported = str(eng.get("enable_prefix_caching"))
    return {
        "READ": True,
        "engine_reported_enable_prefix_caching": eng.get("enable_prefix_caching"),
        "PREFIX_CACHING_ON": (reported == "True"),
        "duplicated_flag": twice,
        "duplicated_flag_last_wins": ((twice or {}).get("argv_last_wins") or {}).get("flag"),
        "_why_it_matters": ("the flag is passed twice and only argparse's last-wins makes it ON; "
                            "with it off every cached_tokens is zero and this whole observable is "
                            "a correct, consistent zero. Read from the ENGINE's own report, and "
                            "restated rather than assumed (the same duplicated-flag shape gave a "
                            "wrong host size under D250)."),
        "context_limit": h.get("context_limit"),
        "arm": h.get("arm"), "seed": h.get("seed"), "ratio": h.get("ratio"),
        "n_devices": h.get("n_devices"), "run_s": h.get("run_s"),
        "robot_question_set": h.get("robot_question_set"),
        "ss_question_set": h.get("ss_question_set"),
        "dashcam_format": h.get("dashcam_format"),
        "robot_upload": h.get("robot_upload"),
        "robot_deadline_s": h.get("robot_deadline_s"),
    }


def outage_from_trace(trace_dir: Path) -> Optional[Dict[str, Any]]:
    tm = trace_dir / "trace_meta.json"
    if not tm.exists():
        return None
    return (json.loads(tm.read_text()) or {}).get("outage")


def regenerate_outage(repo: Path, hdr: Dict[str, Any], k: int, d: float, placement: str,
                      offset: int = 0, reask_mean_s: float = 0.0) -> Dict[str, Any]:
    """Re-run the generator on the cell's own header arguments. EXACT, not an estimate: the trace
    is deterministic in the seed, so this is the same outage the cell ran, and the regenerated
    `robots`/`t_start` are asserted against anything the artefact does carry."""
    live2 = repo / "experiments/orchestration/live2"
    for p in (str(live2), str(live2 / "fleet"), str(live2 / "scorer"),
              str(repo / "experiments/lib")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import data_sources as _DS
    import trace as TR
    # D147: the generator reads DS.ROBOT_DEADLINE_S at call time, so the deadline must be set
    # BEFORE generate_trace, exactly as run_live2_real.py:781 does it. Leaving it at the module
    # default would rebuild a different workload - the same name with two definitions, which is
    # the failure CLAUDE.md check 4 exists to catch.
    if hdr.get("robot_deadline_s"):
        _DS.ROBOT_DEADLINE_S = float(hdr["robot_deadline_s"])
    kw = dict(robot_question_set=hdr.get("robot_question_set") or "eval",
              ss_question_set=hdr.get("ss_question_set") or "ss1")
    if (hdr.get("dashcam_format") or "oneframe") != "oneframe":
        kw["dashcam_format"] = hdr["dashcam_format"]
        if hdr.get("dashcam_min_frames"):
            kw["dashcam_min_frames"] = int(hdr["dashcam_min_frames"])
    if (hdr.get("robot_upload") or "batch-30s") != "batch-30s":
        kw["robot_upload"] = hdr["robot_upload"]
    # D159 (C) / D161: the re-ask volume IS the question volume. header.json does not carry it, so
    # it is read off the cell's own `_rq<k>` tag token, which is where the driver puts it. Without
    # it a regenerated 1,200 s cell has 2 to 3 robot questions per robot instead of about 19, the
    # victims and the window are still exactly right, and every question count is wrong. That is
    # the shape of a plausible spread that cannot mean what the column says.
    if float(reask_mean_s) > 0.0:
        kw["robot_reask_mean_s"] = float(reask_mean_s)
    b = TR.generate_trace(int(hdr["seed"]), int(hdr["n_devices"]), hdr["ratio"],
                          float(hdr["run_s"]), hdr.get("upload_mode") or "A",
                          outage_robots_k=int(k), outage_duration_s=float(d),
                          outage_seed_offset=int(offset),
                          **({} if placement == "band" else dict(outage_placement=placement)),
                          **kw)
    return {"outage": b["meta"]["outage"], "records": b["records"]}


def ask_times(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    per: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        if r.get("kind") != "recall_question":
            continue
        per.setdefault(str(r.get("device_id")), []).append(
            {"t_ask": float(r["t"]), "t_offer": r.get("t_offer"),
             "opportunity_id": r.get("opportunity_id"),
             "history_tokens": r.get("history_tokens"),
             "question_id": r.get("question_id")})
    for v in per.values():
        v.sort(key=lambda x: x["t_ask"])
    return per


def cache_fields(req: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if req is None:
        return {"request_row": False, "HISTORY_CACHED": None,
                "why": "no request row: never sent to the cloud"}
    ct = req.get("cached_tokens")
    pt = req.get("prompt_tokens")
    return {"request_row": True, "request_id": req.get("request_id"),
            "t_submit": req.get("t_submit"), "prompt_tokens": pt, "cached_tokens": ct,
            "cache_path": req.get("cache_path"),
            "cached_fraction": req.get("cached_fraction"),
            "cache_salt": req.get("cache_salt"),
            "HISTORY_CACHED": (None if ct is None else bool(int(ct) > 0)),
            "_definition": "CONTRACT.md:129 / D81: WARM iff cached_tokens > 0"}


def one_cell(cell: Path, args) -> Dict[str, Any]:
    hdr = prefix_cache_proof(cell)
    reqs = read_jsonl(cell, "request.jsonl")
    by_opp = {}
    for r in reqs:
        if r.get("opportunity_id"):
            by_opp.setdefault(str(r["opportunity_id"]), r)
    any_warm = any((r.get("cached_tokens") or 0) > 0 for r in reqs)
    salts = sorted({str(r.get("cache_salt")) for r in reqs})[:5]

    # ---- the window and the victims
    om = None
    recs: List[Dict[str, Any]] = []
    src = None
    tdir = Path(args.trace_dir) if args.trace_dir else None
    if tdir is None:
        cj = cell / "cell.json"
        if cj.exists():
            p = (json.loads(cj.read_text()) or {}).get("trace_dir")
            if p and Path(p).exists():
                tdir = Path(p)
    if tdir is not None and (tdir / "trace_meta.json").exists():
        om = outage_from_trace(tdir)
        recs = read_jsonl(tdir, "trace.jsonl")
        src = "trace_dir:%s" % tdir
    if om is None and args.regenerate:
        name = cell.name
        k = d = None
        import re
        m = re.search(r"_out-k(\d+)-d(\d+)", name)
        if m:
            k, d = int(m.group(1)), float(m.group(2))
        if k is None:
            return {"cell": str(cell), "READABLE": False,
                    "why": "no trace_meta.json and the cell name carries no _out-k<K>-d<D>"}
        placement = "centre" if "_nest" in name else "band"
        mrq = re.search(r"_rq(\d+(?:\.\d+)?)", name)
        rq = float(mrq.group(1)) if mrq else 0.0
        g = regenerate_outage(REPO_DEFAULT if not args.repo else Path(args.repo),
                              json.loads((cell / "header.json").read_text()), k, d, placement,
                              reask_mean_s=rq)
        om, recs = g["outage"], g["records"]
        src = ("regenerated from fleet/trace.py on this cell's own header arguments, with "
               "robot_reask_mean_s=%g read from the cell's _rq tag token and "
               "ROBOT_DEADLINE_S set before the call" % rq)
    if om is None:
        return {"cell": str(cell), "READABLE": False,
                "why": ("no trace_meta.json reachable and --regenerate not given; the window and "
                        "the victims are never guessed from a directory name")}

    t0, t1 = float(om["t_start"]), float(om["t_end"])
    victims = list(om["robots"])
    asks = ask_times(recs)
    robots = sorted(asks)
    rows: Dict[str, Any] = {}
    for rb in robots:
        qs = asks[rb]
        in_win = [q for q in qs if t0 <= q["t_ask"] < t1]
        after = [q for q in qs if q["t_ask"] >= t1]
        post = after[0] if after else None
        # THE DENOMINATOR PROBLEM, STATED IN THE OUTPUT RATHER THAN HIDDEN IN IT. A robot question
        # reaches the cloud only if the arm sent it, so the FIRST post-reconnect question may have
        # NO request row and therefore no cached_tokens at all. Two different objects are reported:
        #   `first_post_reconnect` - the ruling's object, which may be unreadable; and
        #   `first_post_reconnect_with_a_row` - the first one the arm actually sent, which IS
        #      readable and is CONDITIONED ON THE ARM'S OWN BEHAVIOUR, so it is not a fair
        #      cross-arm denominator and may not carry a cross-arm headline on its own.
        posted = next((q for q in after
                       if by_opp.get(str(q["opportunity_id"])) is not None), None)
        pre = next((q for q in reversed(qs) if q["t_ask"] < t0), None)
        rows[rb] = {
            "is_victim": rb in victims,
            "n_questions": len(qs),
            "questions_inside_window": len(in_win),
            # AMENDMENT 2's surviving measurement fact: a COUNT, never scored either way.
            "device_only_questions_UNMEASURABLE_COUNT": (len(in_win) if rb in victims else 0),
            "n_questions_after_reconnect": len(after),
            "first_post_reconnect": (None if post is None else dict(
                post, **cache_fields(by_opp.get(str(post["opportunity_id"]))))),
            "first_post_reconnect_with_a_row": (None if posted is None else dict(
                posted, **cache_fields(by_opp.get(str(posted["opportunity_id"]))))),
            "rank_of_first_row_among_post_reconnect": (
                None if posted is None else after.index(posted) + 1),
            "last_pre_outage_CONTROL": (None if pre is None else dict(
                pre, **cache_fields(by_opp.get(str(pre["opportunity_id"])))))}

    def pooled(sel, field="first_post_reconnect"):
        elig = [r for rb, r in rows.items() if sel(r)]
        xs = [r[field] for r in elig
              if r.get(field) is not None and r[field]["HISTORY_CACHED"] is not None]
        base = {"n_robots_in_class": len(elig),
                "n_with_no_post_reconnect_question": sum(
                    1 for r in elig if r["n_questions_after_reconnect"] == 0),
                "n_whose_first_post_reconnect_was_never_sent": sum(
                    1 for r in elig if r.get("first_post_reconnect") is not None
                    and r["first_post_reconnect"]["HISTORY_CACHED"] is None)}
        if not xs:
            return dict(base, n=0, cached=None, fraction=None)
        c = sum(1 for x in xs if x["HISTORY_CACHED"])
        fr = [x["cached_fraction"] for x in xs if x.get("cached_fraction") is not None]
        return dict(base, n=len(xs), cached=c, fraction=round(c / len(xs), 6),
                    cached_fraction_min=(min(fr) if fr else None),
                    cached_fraction_max=(max(fr) if fr else None),
                    cached_fraction_values=fr)

    vic = pooled(lambda r: r["is_victim"])
    non = pooled(lambda r: not r["is_victim"])
    vic_row = pooled(lambda r: r["is_victim"], "first_post_reconnect_with_a_row")
    non_row = pooled(lambda r: not r["is_victim"], "first_post_reconnect_with_a_row")
    pre_vic = [r["last_pre_outage_CONTROL"] for rb, r in rows.items()
               if r["is_victim"] and r["last_pre_outage_CONTROL"] is not None]
    pre_cached = sum(1 for x in pre_vic if x.get("HISTORY_CACHED"))
    unscorable = (not any_warm)
    return {
        "cell": str(cell), "READABLE": True, "window_source": src,
        "header": hdr,
        "outage": {k: om.get(k) for k in ("placement", "placement_rule", "robots", "t_start",
                                          "t_end", "duration_s", "n_robots_total",
                                          "victim_permutation", "victims_nested_in_k",
                                          "rng_stream_key", "device_only_questions",
                                          "deferred_history_records", "deferred_history_frames",
                                          "backlog_tokens_d2") if k in om},
        "per_robot": rows,
        "victims_first_post_reconnect": vic,
        "non_victims_first_post_reconnect_CONCURRENT_CONTROL": non,
        "victims_first_post_reconnect_WITH_A_ROW": vic_row,
        "non_victims_first_post_reconnect_WITH_A_ROW_CONCURRENT_CONTROL": non_row,
        "_denominator_warning": (
            "the ruling's object is the FIRST post-reconnect question. A robot question has a "
            "request row only if the arm sent it, so that object is unreadable for any robot whose "
            "first post-reconnect question was never sent, and the readable substitute is "
            "conditioned on the arm's own behaviour. Both are reported; neither may carry a "
            "cross-arm headline unless its n is stated beside it."),
        "victims_last_pre_outage_BEFORE_CONTROL": {
            "n": len(pre_vic), "cached": pre_cached,
            "fraction": (round(pre_cached / len(pre_vic), 6) if pre_vic else None)},
        "device_only_questions_total_UNMEASURABLE": sum(
            r["device_only_questions_UNMEASURABLE_COUNT"] for r in rows.values()),
        "cell_has_any_warm_request": bool(any_warm),
        "distinct_cache_salts_sample": salts,
        "UNSCORABLE": bool(unscorable or hdr.get("PREFIX_CACHING_ON") is False),
        "VERDICT": ("UNSCORABLE IN THIS CELL: no request row anywhere in the cell reports "
                    "cached_tokens > 0, or the engine reports prefix caching OFF. The observable "
                    "would be a correct and consistent zero for every arm and may not be reported "
                    "as a finding."
                    if (unscorable or hdr.get("PREFIX_CACHING_ON") is False) else
                    "SCORABLE: the cell reports warm requests, so a cold first post-reconnect "
                    "question is a measurement and not an artefact of the engine configuration."),
    }


def pair(small: Dict[str, Any], large: Dict[str, Any]) -> Dict[str, Any]:
    """THE NESTING DIFFERENCE, which is the whole point of the D266 keying change: the added
    victims at the larger k are differenced against THEIR OWN rows in the smaller-k cell, at the
    same instant in the same trace. Refuses unless the nesting and the window actually hold."""
    so, lo = small.get("outage", {}), large.get("outage", {})
    sv, lv = set(so.get("robots") or ()), set(lo.get("robots") or ())
    nested = sv <= lv
    same_window = (so.get("t_start") == lo.get("t_start")
                   and so.get("t_end") == lo.get("t_end"))
    added = sorted(lv - sv)
    tbl = []
    for rb in added:
        a = (small["per_robot"].get(rb) or {}).get("first_post_reconnect")
        b = (large["per_robot"].get(rb) or {}).get("first_post_reconnect")
        tbl.append({"device_id": rb,
                    "was_victim_at_small_k": False,
                    "small_k_cached": (a or {}).get("HISTORY_CACHED"),
                    "large_k_cached": (b or {}).get("HISTORY_CACHED"),
                    "small_k_cached_fraction": (a or {}).get("cached_fraction"),
                    "large_k_cached_fraction": (b or {}).get("cached_fraction"),
                    "questions_inside_window_small_k":
                        (small["per_robot"].get(rb) or {}).get("questions_inside_window"),
                    "questions_inside_window_large_k":
                        (large["per_robot"].get(rb) or {}).get("questions_inside_window")})
    return {
        "nested": bool(nested), "same_window": bool(same_window),
        "small_k_victims": sorted(sv), "large_k_victims": sorted(lv),
        "added_victims": added,
        "USABLE": bool(nested and same_window),
        "marginal_per_device": tbl,
        "_why_the_per_victim_question_count_is_beside_it": (
            "the deferred-history dose is k x (D/2) and is fixed by k, but the per-victim QUESTION "
            "dose is not: committed per-victim counts span 12 to 32, so each added victim's own "
            "count must be read beside its row and never inferred from k."),
        "VERDICT": ("USABLE: the smaller victim set is contained in the larger at the same window, "
                    "so the added victims can be differenced against their own rows."
                    if nested and same_window else
                    "REFUSED: the victim sets do not nest or the windows differ, so a k1-against-k2 "
                    "difference changes more than the victim count. This is the committed band "
                    "rule's defect and the reason for the D266 keying change."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cell", action="append", default=[])
    ap.add_argument("--pair", nargs=2, default=None,
                    metavar=("SMALL_K_CELL", "LARGE_K_CELL"))
    ap.add_argument("--trace-dir", default=None)
    ap.add_argument("--regenerate", action="store_true",
                    help="rebuild the window and victims from fleet/trace.py on the cell's own "
                         "header arguments when no trace_meta.json is reachable")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    cells = list(a.cell) + (list(a.pair) if a.pair else [])
    if not cells:
        ap.error("give --cell or --pair")
    per = {}
    for c in cells:
        per[str(c)] = one_cell(Path(c), a)
    out = {
        "_what": ("D262 / D266 item 2: history cached at the FIRST POST-RECONNECT QUESTION, per "
                  "robot, with a prefix-caching proof, a non-victim concurrent control and a "
                  "pre-outage within-robot control. Device-only questions are a COUNT and are "
                  "never scored."),
        "_definition_of_cached": "CONTRACT.md:129 / D81: cache_path WARM iff cached_tokens > 0; "
                                 "cached_fraction = cached_tokens / prompt_tokens, from the "
                                 "engine's own usage report and never from the belief",
        "cells": per,
    }
    if a.pair:
        out["nested_pair"] = pair(per[str(a.pair[0])], per[str(a.pair[1])])
    try:
        sys.path.insert(0, str((Path(a.repo) if a.repo else REPO_DEFAULT) / "experiments/lib"))
        from _provenance import stamp
        out["_provenance"] = stamp(script="d262_outage_history_cached.py", model="qwen3vl32b",
                                   device="read_only_cpu", n=len(cells), args=a)
    except Exception as e:
        out["_provenance_error"] = repr(e)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    for k, v in per.items():
        if not v.get("READABLE"):
            print("%-60s UNREADABLE: %s" % (os.path.basename(k), v.get("why")))
            continue
        print("%-60s victims %s/%s cached, non-victims %s/%s, pre-outage %s/%s, device-only %s | %s"
              % (os.path.basename(k),
                 v["victims_first_post_reconnect"]["cached"],
                 v["victims_first_post_reconnect"]["n"],
                 v["non_victims_first_post_reconnect_CONCURRENT_CONTROL"]["cached"],
                 v["non_victims_first_post_reconnect_CONCURRENT_CONTROL"]["n"],
                 v["victims_last_pre_outage_BEFORE_CONTROL"]["cached"],
                 v["victims_last_pre_outage_BEFORE_CONTROL"]["n"],
                 v["device_only_questions_total_UNMEASURABLE"],
                 ("UNSCORABLE" if v["UNSCORABLE"] else "scorable")))
    if a.pair:
        print("NESTED PAIR:", out["nested_pair"]["VERDICT"])
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
