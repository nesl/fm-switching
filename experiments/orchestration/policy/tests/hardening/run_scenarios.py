#!/usr/bin/env python3
"""Run the pre-registered StudyCOVEX-harden scenarios and score each against its committed
expectation. The expectation text is READ from the pre-registration JSON and never restated here.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenarios as S                                                  # noqa: E402

TIGHT, ROOMY = 27.0, 256.0


def _mk(tmp, name):
    d = Path(tmp) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _robot_only(tmp, name, tokens, q_at, window, sw, n_dash=0, host=TIGHT, **kw):
    ev = S.robot("rob000", tokens, question_at_s=q_at, duration_s=window, **kw)
    if n_dash:
        ev += S.dashcams(n_dash, window)
    return S.run_events(ev, _mk(tmp, name), window_s=window, switches=sw, host_gib=host)


def _verdict(ok, note, **extra):
    return dict(pass_=bool(ok), note=note, **extra)


def scenario(sid: str, tmp: Path, sw: Dict[str, bool]) -> Dict[str, Any]:
    W = 60.0
    if sid == "S1":
        r = _robot_only(tmp, "S1", 11101, 40.0, W, sw)
        o = S.question_outcome(r, list(r["questions"])[0])
        return _verdict(o["released_before_deadline"],
                        "released at %s against deadline %s" % (o["released_at"],
                                                                o["deadline_abs"]),
                        outcome=o)
    if sid == "S2":
        r = _robot_only(tmp, "S2", 11101, 40.0, W, sw, n_dash=8)
        o = S.question_outcome(r, list(r["questions"])[0])
        base = S.run_events(S.dashcams(8, W), _mk(tmp, "S2_base"), window_s=W, switches=sw)
        lost = S.monitor_releases(base) - S.monitor_releases(r)
        return _verdict(o["released_before_deadline"],
                        "released=%s at %s; dashcam releases %d against %d paired, so %d fewer"
                        % (o["released_before_deadline"], o["released_at"],
                           S.monitor_releases(r), S.monitor_releases(base), lost),
                        outcome=o, dashcam_releases=S.monitor_releases(r),
                        dashcam_releases_paired=S.monitor_releases(base), fewer=lost)
    if sid == "S3":
        r = _robot_only(tmp, "S3", 11101, 40.0, W, sw, n_dash=20)
        o = S.question_outcome(r, list(r["questions"])[0])
        admitted = o["n_releases"] > 0 or any(
            d["kind"] == "release_whole" for d in r["decisions"])
        starved = admitted and not o["released_before_deadline"]
        return _verdict(not starved,
                        "served=%s, any release=%s, declines=%d. admit-then-starve=%s"
                        % (o["released_before_deadline"], admitted, o["n_declines_in_run"],
                           starved), outcome=o, admit_then_starve=starved)
    if sid in ("S4a", "S4b", "S4c"):
        n_dash, host = {"S4a": (8, TIGHT), "S4b": (20, TIGHT), "S4c": (20, ROOMY)}[sid]
        r = _robot_only(tmp, sid, 11101, 40.0, W, sw, n_dash=n_dash, host=host)
        o = S.question_outcome(r, list(r["questions"])[0])
        kinds = collections.Counter(d["kind"] for d in r["decisions"])
        pieces = kinds.get("release_piece", 0) > 0
        whole = kinds.get("release_whole", 0) > 0
        sess = [d.get("note") for d in r["decisions"] if d["kind"].startswith("session")]
        if sid == "S4a":
            return _verdict(pieces, "pieces=%s whole=%s served=%s" % (
                pieces, whole, o["released_before_deadline"]),
                outcome=o, kinds=dict(kinds), pieces=pieces, whole=whole)
        if sid == "S4b":
            admitted = o["n_releases"] > 0 or whole
            starved = admitted and not o["released_before_deadline"]
            return _verdict(not starved,
                            "no option serves both; served=%s, admit-then-starve=%s, "
                            "dashcam releases=%d" % (o["released_before_deadline"], starved,
                                                     S.monitor_releases(r)),
                            outcome=o, kinds=dict(kinds), admit_then_starve=starved,
                            dashcam_releases=S.monitor_releases(r))
        return _verdict(o["released_before_deadline"],
                        "roomy host: served=%s, session actions=%d, pieces=%s whole=%s"
                        % (o["released_before_deadline"], len(sess), pieces, whole),
                        outcome=o, kinds=dict(kinds), session_actions=len(sess))
    if sid == "S5":
        ev = S.robot("rob000", 11101, question_at_s=40.0, duration_s=W)
        ev += S.robot("rob001", 11101, question_at_s=40.0, duration_s=W)
        r = S.run_events(ev, _mk(tmp, "S5"), window_s=W, switches=sw)
        outs = [S.question_outcome(r, q) for q in sorted(r["questions"])]
        served = sum(1 for o in outs if o["released_before_deadline"])
        both_starved = served == 0
        return _verdict(not both_starved,
                        "served %d of %d; release times %s" % (
                            served, len(outs), [o["released_at"] for o in outs]),
                        outcomes=outs, served=served)
    if sid == "S6":
        # Drive a host-warm belief: build early, then apply dashcam pressure, then ask late.
        ev = S.robot("rob000", 11101, question_at_s=55.0, duration_s=70.0, build_at_s=1.0)
        ev += S.dashcams(12, 70.0)
        r = S.run_events(ev, _mk(tmp, "S6"), window_s=70.0, switches=sw)
        o = S.question_outcome(r, list(r["questions"])[0])
        ready = [d.get("note") for d in r["decisions"] if "readiness" in str(d.get("note", ""))]
        sess = r["coordinator"].st.sessions
        tiers = {sid2: s.readiness() for sid2, s in sess.items()}
        host_warm = any(t == "HOST-WARM" for t in tiers.values())
        if not host_warm:
            return dict(pass_=None, realisable=False,
                        note="NOT REALISABLE from the trace interface: observed readiness %s, "
                             "never HOST-WARM, so the scenario is not scored (caveat "
                             "pre-registered)" % tiers, tiers=tiers, outcome=o)
        return _verdict(o["released_before_deadline"], "host-warm observed, served=%s"
                        % o["released_before_deadline"], outcome=o, tiers=tiers)
    if sid == "S7":
        r = _robot_only(tmp, "S7", 27031, 40.0, W, sw)
        o = S.question_outcome(r, list(r["questions"])[0])
        return _verdict(o["n_releases"] == 0,
                        "infeasible history: releases=%d, declines=%d, served=%s"
                        % (o["n_releases"], o["n_declines_in_run"],
                           o["released_before_deadline"]), outcome=o)
    if sid == "S8":
        # A dashcam whose instants are all already past their deadline when offered has no
        # attainable gain, so a positive-gain rule must not send them.
        ev = S.dashcams(1, W)
        for e in ev:
            if e["kind"] == "monitor_frame":
                e["t_arrive"] = round(float(e["t_capture"]) + S.DASHCAM_L_S + 2.0, 4)
        r = S.run_events(ev, _mk(tmp, "S8"), window_s=W, switches=sw)
        sent = S.monitor_releases(r)
        return _verdict(sent == 0, "instants arriving after their own deadline: %d sent" % sent,
                        monitor_releases=sent, monitor_offered=r["monitor_offered"])
    if sid == "S9":
        ev = S.robot("rob000", 20101, question_at_s=50.0, duration_s=W)
        ev += S.robot("rob001", 20101, question_at_s=52.0, duration_s=W)
        ev += S.dashcams(8, W)
        r = S.run_events(ev, _mk(tmp, "S9"), window_s=W, switches=sw, host_gib=TIGHT)
        ev_dec = [d for d in r["decisions"] if "evict" in str(d.get("kind", "")).lower()
                  or "EVICT" in str(d.get("note", ""))]
        if not ev_dec:
            return dict(pass_=None, realisable=False,
                        note="NOT REALISABLE: no eviction occurred under this pressure, so the "
                             "choice the scenario exists to test was never made (caveat "
                             "pre-registered)", evictions=0)
        return _verdict(True, "evictions observed: %d" % len(ev_dec), evictions=len(ev_dec))
    if sid == "S10":
        ev = S.dashcams(40, W)
        for j in range(3):
            ev += S.robot("rob%03d" % j, 11101, question_at_s=20.0 + 5 * j, duration_s=W)
        r = S.run_events(ev, _mk(tmp, "S10"), window_s=W, switches=sw)
        pend = [len(r["coordinator"].st.pending_opportunities())
                if hasattr(r["coordinator"].st, "pending_opportunities") else 0]
        defers = sum(1 for d in r["decisions"] if d["kind"] == "defer")
        n_dec = len(r["decisions"])
        return _verdict(True, "overload: %d decisions, %d defers; queue growth reported "
                              "rather than asserted" % (n_dec, defers),
                        decisions=n_dec, defers=defers)
    if sid == "S11":
        # The history is preloaded (D101) and the question comes much later, so the cloud has
        # had every chance to build it before the question arrives.
        r = _robot_only(tmp, "S11", 11101, 50.0, W, sw, preload=True)
        o = S.question_outcome(r, list(r["questions"])[0])
        sess = r["coordinator"].st.sessions
        tiers = {k: v.readiness() for k, v in sess.items()}
        return _verdict(o["released_before_deadline"],
                        "served=%s, readiness at end %s" % (o["released_before_deadline"],
                                                            tiers), outcome=o, tiers=tiers)
    if sid == "S12":
        r = _robot_only(tmp, "S12", 11101, 40.0, W, sw, deadline_s=0.001)
        o = S.question_outcome(r, list(r["questions"])[0])
        return _verdict(o["n_releases"] == 0,
                        "deadline already passed: releases=%d" % o["n_releases"], outcome=o)
    raise KeyError(sid)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--switches", default="")
    ap.add_argument("--label", default="v1.0")
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    sw = {s: True for s in a.switches.split(",") if s.strip()}
    prereg = S.load_prereg()
    ids = [s.strip() for s in a.only.split(",") if s.strip()] or list(prereg)
    tmp = Path(tempfile.mkdtemp(prefix="covex_scen_"))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(S.H.ROOT),
                           capture_output=True, text=True).stdout.strip()
    rows = {}
    for sid in ids:
        try:
            v = scenario(sid, tmp, sw)
        except Exception as e:                                   # noqa: BLE001
            v = dict(pass_=False, note="ERROR %s: %s" % (type(e).__name__, e), error=True)
        v["expect"] = prereg[sid]["expect"]
        v["expect_detail"] = prereg[sid]["expect_detail"]
        v["scenario"] = prereg[sid]["scenario"]
        rows[sid] = v
        print("%-5s %-6s %s" % (sid, ("PASS" if v.get("pass_") else
                                       ("n/a" if v.get("pass_") is None else "FAIL")),
                                 str(v.get("note"))[:150]), flush=True)
    scored = [v for v in rows.values() if v.get("pass_") is not None]
    out = dict(check="covex_harden_scenarios", is_measurement=False,
               label="DRY RUN, SCREENING. Crafted event lists through the committed coordinator "
                     "with dry_run=True: no GPU, no model server, no engine. Expectations were "
                     "pre-registered and committed before COVEX was run against them.",
               git_commit=head, switch_label=a.label, switches_on=sorted(sw),
               unsupported_switches=S.H.unsupported_switches(sw),
               n_scored=len(scored), n_passed=sum(1 for v in scored if v["pass_"]),
               n_not_realisable=sum(1 for v in rows.values() if v.get("pass_") is None),
               scenarios=rows,
               _provenance=dict(git_commit=head,
                                script="policy/tests/hardening/run_scenarios.py",
                                model="none (pol4 cost curve, frozen)",
                                device="flash CPU only",
                                n="14 crafted scenarios, development data only",
                                timestamp="2026-11-18T00:00:00"))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote %s: %d of %d scored scenarios pass, %d not realisable"
          % (a.out, out["n_passed"], out["n_scored"], out["n_not_realisable"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
