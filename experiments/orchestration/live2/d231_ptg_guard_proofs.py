#!/usr/bin/env python3
"""D230 (2) / D178 (3) / D166 (3) / D231 (3): THE PROOFS FOR covex-v6-fair-final-ptg.

WHAT THE VARIANT IS. Rung 3 (`covex-v6-fair-final`) plus BOTH halves of freeze-gate row 10.7:

  (a) PER-TYPE SATURATION-GUARD THRESHOLDS, D178 (3): fire when a type's observed first-token lag
      exceeds 80 percent of ITS OWN deadline (alert 0.8 s, assistance 1.6 s, recall 2.4 s), in
      place of the single `GUARD_LAG_S_DEFAULT = 2.0` the committed arms read. The thresholds are
      DERIVED from `share_admission.DEADLINE_S`, not written out, so they cannot drift from the
      committed deadlines.
  (b) A THIRD EWMA LAG CLASS at the write site, `coordinator._collect`, because (a) cannot be
      implemented without it: `d230_guard_107.json` found that the guard had only TWO channels and
      that every non-monitor completion was folded into "recall", so ASSISTANCE HAD NO GUARD
      SIGNAL AT ALL and "recall" was a mixture of recall questions, assistance questions, warm
      pieces and touches. The new class is ADDITIVE: the committed line is unchanged, so
      `latency_estimate_s["recall"]` is bit-for-bit what every committed arm has always read.
  (c) D166 (3) EXIT HYSTERESIS: exit only after ALL signals have been below 0.5x their entry
      thresholds for 2 s. In scope per D231 (3), which withdrew an earlier deferral.
  (d) D230 (2) limitation 1: `guard_state`'s `lag_s` and `backlog` LOGGED PER DECISION PERIOD, so
      the next ruling of this kind needs no replay of the EWMA recurrence.

WHAT IT IS NOT, said here because the name invites the wrong reading. This is the D160 (2)
SATURATION EARLY WARNING. When it fires, the base action is returned UNTOUCHED and only the
background warming channel is shed (and, at rung 2+, state actions deferred). It is NOT a
per-request deadline rescue and nothing here should be read as rescuing an individual late alert.

THE INSTRUMENT, AND WHY NOT THE OTHER ONE. `hybrid/test_hybrid.dry`: in-process,
`realtime=False`, `dry_run=True`, therefore DETERMINISTIC. The REALTIME dry-cell instrument is NOT
used, on the committed record's own advice: `RUNG3_KV05R_CELLS` records that it was REJECTED for a
byte-identity claim because the same tree disagreed with itself
(`d223_byte_identity_realtime_probe.json`). Every A-versus-B comparison here still runs its own
A/A control FIRST, and a comparison whose control is dirty is not reported as a result.

*** THE ONE THING A READER MUST TAKE FROM THIS FILE BEFORE ANY NUMBER IN IT. ***
A DRY CELL CANNOT EXERCISE THE ALERT CHANNEL, AND THAT IS A PROPERTY OF THE HARNESS, NOT OF THE
VARIANT. `coordinator._dry_service_s` returns `costs.episodic_cloud_latency_s("32BI", 1, 25)` for
EVERY monitor request: a CONSTANT, with no queueing term. So the dry alert EWMA takes exactly TWO
values in a whole cell (0.0 before the first completion, 0.394966 after it) and cannot reach 0.8 s
in any period. Assistance is the same story at a different number (dry max 0.296889 s against
1.6 s). Proof 3's observed alert count is therefore ZERO, and that zero is CLAUDE.md Rule 2's
`unexercised` - NOT a negative, and not evidence about the guard. What this file CAN establish
about the alert channel is (i) that the branch is REACHABLE, by a positive control that moves the
alert threshold below the dry constant and shows it firing and moving decisions, and (ii) the
CONSTRUCTED expectation for the s4 GPU cell, cited from `d230_guard_107.json` and not re-derived.
The observed count can only come from a cell with a real engine under queueing.

USAGE
    python3 -I d231_ptg_guard_proofs.py --after <live2 dir> --before <live2 dir of 281f29c7>
            [--out FILE] [--run-s 1200] [--seed 4] [--n 16]
    python3 -I d231_ptg_guard_proofs.py --one-cell --live2 DIR --arm NAME ...   (internal)
Exit status: 0 if every proof passes, 1 if any fails, 2 on error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HINTS = ("run_live2_real.py", "run_live2_cell.py", "test_hybrid.py", "cfr3_one_cell.py",
         "d216_final_kv025_one_cell.py", "f14_one_cell.py", "d231_ptg_guard_proofs.py")
# The POSTED workload knobs, all of them, so the proof sits on the path the real cells take.
WORKLOAD = dict(ratio="40:40:20", robot_question_set="lh_req", ss_question_set="ss2",
                dashcam_format="epg", robot_upload="per-frame", robot_reask_mean_s=30.0)


# ------------------------------------------------------------------ one cell, in its own process

def one_cell(a: Any) -> int:
    L = Path(a.live2).resolve()
    for p in (L / "hybrid", L, L / "v5", L / "fleet", L / "tests", L.parent,
              L.parent / "baselines", L.parent / "sim", L.parents[1] / "lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import test_hybrid as TH

    cap: Dict[str, Any] = {}

    def patch(arm: Any) -> None:
        cap["arm"] = arm
        if a.thresholds:
            # applied through the PRODUCTION setter, so a probe cannot take a path the shipped
            # variant does not take
            import arms_final_ladder as FL
            FL._set_per_type_guard(arm, json.loads(a.thresholds))
            cap["thresholds_applied"] = dict(
                getattr(vars(arm).get("_rules"), "guard_lag_s_by_class", {}) or {})

    l0 = os.getloadavg()
    rows, _ = TH.dry(a.arm, a.seed, a.n, run_s=a.run_s, patch=patch, **WORKLOAD)
    l1 = os.getloadavg()
    arm = cap.get("arm")
    glog = list(getattr(arm, "guard_log_rows", []) or [])

    # EVERY Counter in the delegation chain, the way `coordinator._arm_stats` collects them.
    # `arm.stats` ALONE IS THE WRONG OBJECT: `guard_state` increments `self.stats` on the composed
    # `_rules`, and `test_hybrid.dry` returns only the outer arm's Counter, so every guard counter
    # is invisible to a reader who trusts that return value.
    seen, chain, i, st = {id(arm)}, [arm], 0, {}
    while i < len(chain):
        o = chain[i]
        i += 1
        for at in ("_rules", "_base", "_scorer"):
            nx = getattr(o, at, None)
            if nx is not None and id(nx) not in seen:
                seen.add(id(nx))
                chain.append(nx)
    for o in chain:
        for k, v in dict(getattr(o, "stats", None) or {}).items():
            st.setdefault("%s.%s" % (type(o).__name__, k), v)

    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=float)
    rec: Dict[str, Any] = {
        "arm": a.arm, "tree": str(L), "seed": a.seed, "n": a.n, "run_s": a.run_s,
        "n_decision_rows": len(rows),
        "decision_digest": hashlib.sha256(blob.encode()).hexdigest()[:16],
        "loadavg_at_start": [round(x, 2) for x in l0],
        "loadavg_at_end": [round(x, 2) for x in l1],
        "guard_stats": {k: v for k, v in sorted(st.items())
                        if "guard" in k or k.endswith(".epochs")},
        "thresholds_applied": cap.get("thresholds_applied"),
        "guard_log_rows": len(glog),
        "describe_guard": {k: v for k, v in
                           ((arm.live2_describe().get("v5_rules2") or {}) if arm else {}).items()
                           if k.startswith("guard")},
    }
    if glog:
        def span(cls: Optional[str], key: str = "lag_s"):
            vs = [((r.get("lag_s_by_class") or {}).get(cls) if cls else r.get(key))
                  for r in glog]
            vs = [v for v in vs if v is not None]
            return [round(min(vs), 6), round(max(vs), 6)] if vs else None
        rec["guard_log_summary"] = {
            "periods": len(glog),
            "lag_s_min_max": span(None),
            "backlog_min_max": span(None, "backlog"),
            "episodic_min_max": span("episodic"),
            "assistance_min_max": span("assistance"),
            "recall_min_max": span("recall"),
            "n_active": sum(1 for r in glog if r.get("active")),
            "n_entry": sum(1 for r in glog if r.get("entry")),
            "n_latched": sum(1 for r in glog if r.get("latched")),
            # the characteristic decision, PER CHANNEL: this is proof 3's number
            "fired_by_class": {c: sum(1 for r in glog if c in (r.get("fired_classes") or ()))
                               for c in ("episodic", "assistance", "recall")},
            "first_alert_firing": next((r for r in glog
                                        if "episodic" in (r.get("fired_classes") or ())), None),
            # periods where the LATCH alone kept the guard active: the hysteresis' own decision
            "n_latched_without_entry": sum(1 for r in glog
                                           if r.get("latched") and not r.get("entry")),
        }
    if a.rows_out:
        Path(a.rows_out).write_text(blob)
    if a.guard_out and glog:
        Path(a.guard_out).write_text("\n".join(json.dumps(r, default=float) for r in glog))
    print(json.dumps(rec, default=float))
    return 0


# ------------------------------------------------------------------ the ALONE census, by process

def _ancestors(pid: int) -> set:
    out, cur = {pid}, pid
    for _ in range(64):
        try:
            with open("/proc/%d/stat" % cur, "rb") as fh:
                cur = int(fh.read().rsplit(b")", 1)[1].split()[1])
        except Exception:                                                      # noqa: BLE001
            break
        if not cur or cur in out:
            break
        out.add(cur)
    return out


def census(mine: set) -> List[Dict[str, Any]]:
    """Foreign live2 processes BY PROCESS (`/proc/<pid>/cwd` plus the interpreter), never by name
    or size. THE BASENAME LIST IS A BOUND ON THIS CENSUS AND NOT THE CENSUS: a process whose
    script is not in `HINTS` is invisible to it, so a clear guard is a summary and never the
    finding. The loadavg magnitudes beside it, and the A/A controls, outrank it."""
    out = []
    for ent in os.listdir("/proc"):
        if not ent.isdigit() or int(ent) in mine:
            continue
        pid = int(ent)
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                parts = [x.decode("utf-8", "replace") for x in fh.read().split(b"\0") if x]
            cwd = os.readlink("/proc/%d/cwd" % pid)
        except Exception:                                                      # noqa: BLE001
            continue
        if parts and [t for t in parts if os.path.basename(t) in HINTS]:
            out.append({"pid": pid, "cwd": cwd, "cmd": " ".join(parts)[:200]})
    return out


# ------------------------------------------------------------------ the driver

class Runner:
    def __init__(self, a: Any) -> None:
        self.a = a
        self.cells = Path(a.cells).resolve()
        self.cells.mkdir(parents=True, exist_ok=True)
        self.self_py = [sys.executable, "-I", str(Path(__file__).resolve())]
        self.by_tag: Dict[str, Dict[str, Any]] = {}

    def cell(self, tree: Path, arm: str, tag: str, *,
             thresholds: Optional[Dict[str, float]] = None,
             run_s: Optional[float] = None) -> Dict[str, Any]:
        run_s = float(self.a.run_s if run_s is None else run_s)
        mine = _ancestors(os.getpid())
        before = census(mine)
        rows_out = self.cells / (tag + ".rows.json")
        cmd = self.self_py + ["--one-cell", "--live2", str(tree), "--arm", arm,
                              "--seed", str(self.a.seed), "--n", str(self.a.n),
                              "--run-s", str(run_s), "--rows-out", str(rows_out),
                              "--guard-out", str(self.cells / (tag + ".guard.jsonl"))]
        if thresholds:
            cmd += ["--thresholds", json.dumps(thresholds)]
        p = subprocess.run(cmd, cwd=str(tree), capture_output=True, text=True)
        after = census(mine)
        if p.returncode != 0:
            raise SystemExit("CELL %s FAILED rc=%d\n%s\n%s"
                             % (tag, p.returncode, p.stdout[-1500:], p.stderr[-3000:]))
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rec.update(tag=tag, tree_role=("AFTER" if Path(tree) == Path(self.a.after) else "BEFORE"),
                   rows_file=str(rows_out),
                   # The cell's own exit code, recorded and printed BESIDE the digest. A digest is
                   # only a digest of a run that finished: a non-zero rc raises above, so every rc
                   # here is 0 by construction, and printing it is what makes that checkable
                   # rather than assumed.
                   returncode=p.returncode,
                   foreign_live2_at_start=before, foreign_live2_at_end=after,
                   alone=("GUARD-ASSERTED CLEAR" if not before and not after
                          else "FOREIGN LIVE2 PROCESS SEEN"))
        self.by_tag[tag] = rec
        print("    %-46s %-6s rows=%-6d digest=%s rc=%d load %4.2f->%4.2f %s"
              % (tag, rec["tree_role"], rec["n_decision_rows"], rec["decision_digest"],
                 rec["returncode"], rec["loadavg_at_start"][0], rec["loadavg_at_end"][0],
                 rec["alone"]))
        return rec


def compare(a: Dict[str, Any], b: Dict[str, Any], label: str) -> Dict[str, Any]:
    """POSITIONAL and SET-WISE, the two registers `test_hybrid` distinguishes, plus the FIRST
    differing decision. Positional is the right register for a byte-identity claim and the wrong
    one for "did this switch move a decision": one early divergence desynchronises the rest of the
    log, and a transposition inside one period counts as 2 while nothing was decided differently.
    Both are printed so a reader can see which register a statement is in."""
    ra = json.loads(Path(a["rows_file"]).read_text())
    rb = json.loads(Path(b["rows_file"]).read_text())
    pos = sum(1 for x, y in zip(ra, rb) if x != y) + abs(len(ra) - len(rb))
    first = None
    for i, (x, y) in enumerate(zip(ra, rb)):
        if x != y:
            first = {"index": i, "a_row": x, "b_row": y}
            break
    if first is None and len(ra) != len(rb):
        lo = min(len(ra), len(rb))
        first = {"index": lo, "a_row": (ra[lo] if lo < len(ra) else None),
                 "b_row": (rb[lo] if lo < len(rb) else None),
                 "note": "the logs agree up to the shorter one and differ in LENGTH"}

    def key(r):
        return (r.get("t"), r.get("kind"), tuple(r.get("opportunity_ids") or ()),
                r.get("representation"))
    setwise = len(set(key(r) for r in ra) ^ set(key(r) for r in rb))
    out = {"label": label, "a": a["tag"], "b": b["tag"],
           "a_digest": a["decision_digest"], "b_digest": b["decision_digest"],
           "a_rows": len(ra), "b_rows": len(rb),
           "digests_equal": a["decision_digest"] == b["decision_digest"],
           "n_differing_positional": pos, "n_differing_setwise": setwise,
           "first_differing_decision": first}
    print("  %-58s pos=%-6d set=%-6d identical=%s"
          % (label, pos, setwise, out["digests_equal"]))
    return out


# The COMMITTED dry 300 s n16 s4 digests, from
# results/orchestration/live2/d222_pass1/proof_ab_pristine_tree.json at b0767b46. The
# POSITIVE CONTROL for proof 1: an arm nobody changed must still hash to its committed value
# in THIS tree. If one of these fails, the CHECK is broken and not the arm, and proof 1's
# verdict must be disregarded until it is fixed.
COMMITTED_DRY300_DIGESTS = {
    "hybrid-F-lhreq-noc3": ("26fa08e255cfac87", 2840),
    "covex-v6-state-final": ("8d901f7bc82b7f37", 2877),
    "covex-v6-fair-final": ("62b0f9a977189c78", 2814),
    # *** CORRECTED, and the correction is itself recorded. *** d222_pass1 committed TWO
    # tables. proof_ab_PRISTINE_tree.json is the tree BEFORE the rung-4 pass-1 counterfactual
    # was built and lists this arm at 62b0f9a977189c78, the SAME value as covex-v6-fair-final,
    # because the counterfactual was absent. proof_ab_PASS1_tree.json is the tree WITH it and
    # lists 63eeaf6f7432dece, with covex-v6-final-off back at 62b0f9a977189c78. This build sits
    # on 281f29c7, AFTER the pass-1 build landed, so the PASS1 value is the applicable bar.
    # The first run of this script cited the pristine value, the control FAILED, and the
    # failure was the CHECK and not the arm: see
    # results/orchestration/live2/d231_ptg_guard/d231_broken_bar_not_broken_arm.json.
    "covex-v6-final": ("63eeaf6f7432dece", 2814),
    "mooncake": ("b0fdc7d489a16d78", 3052),
    "simplestream": ("1f80561c5dde58af", 2932),
    "llf": ("e404b1fe2eeb7dbb", 3381),
}
COMMITTED_DIGEST_CELL = "dry, 300 s, n 16, seed 4, the posted workload knobs"

IDENTITY_ARMS = ("hybrid-F-lhreq-noc3", "covex-v6-state-final", "covex-v6-fair-final",
                 "covex-v6-final", "mooncake", "simplestream", "llf")
PTG = "covex-v6-fair-final-ptg"
R3 = "covex-v6-fair-final"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one-cell", action="store_true")
    ap.add_argument("--live2")
    ap.add_argument("--arm")
    ap.add_argument("--thresholds")
    ap.add_argument("--rows-out")
    ap.add_argument("--guard-out")
    ap.add_argument("--after")
    ap.add_argument("--before")
    ap.add_argument("--cells", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--run-s", type=float, default=1200.0,
                    help="the cell length for the VARIANT comparisons, proofs 2 to 5")
    ap.add_argument("--only-proof1", action="store_true",
                    help=("run PROOF 1 alone. For re-checking identity against a tip that has "
                          "gained an arm since the variant was proved, without re-running the "
                          "1200 s variant comparisons, which do not involve that arm."))
    ap.add_argument("--extra-identity-arms", default="",
                    help=("comma-separated arm names to ADD to proof 1, for arms that did "
                          "not exist when this build was first proved. They have NO entry "
                          "in COMMITTED_DRY300_DIGESTS, so their evidence is BEFORE vs "
                          "AFTER plus their own A/A control and NOT a committed bar, and "
                          "the report says so per arm."))
    ap.add_argument("--identity-run-s", type=float, default=300.0,
                    help=("the cell length for proof 1. 300 s by default BECAUSE A COMMITTED "
                          "BAR EXISTS AT THAT LENGTH: d222_pass1/proof_ab_pristine_tree.json "
                          "carries dry 300 s n16 s4 digests for six of the seven identity "
                          "arms. Checking identity against a COMMITTED digest is a stronger "
                          "kind of evidence than agreement between two trees this session "
                          "made, because it cannot be satisfied by a shared mistake."))
    a = ap.parse_args(argv)
    if a.one_cell:
        return one_cell(a)
    if not a.after or not a.before:
        raise SystemExit("--after and --before are both required")
    a.cells = a.cells or str(Path(a.out or ".").resolve().parent / "ptg_cells")
    AFTER, BEFORE = Path(a.after).resolve(), Path(a.before).resolve()
    R = Runner(a)

    RES: Dict[str, Any] = {
        "study": ("D230 (2) / D178 (3) / D166 (3) / D231 (3): the proofs for "
                  "covex-v6-fair-final-ptg, the per-type saturation guard with exit hysteresis"),
        "citations": ["D230 (2)", "D178 (3)", "D166 (3)", "D166 (4) commit rules", "D231 (3)",
                      "D187", "D208", "D216", "D225 (3)"],
        "cell": {"seed": a.seed, "n": a.n, "run_s": a.run_s, "workload": dict(WORKLOAD),
                 "instrument": ("hybrid/test_hybrid.dry: in-process, realtime=False, "
                                "dry_run=True, therefore deterministic"),
                 "CACHING": ("NO prefix cache and NO ENGINE AT ALL: a dry cell sends no HTTP. "
                             "Service time is the committed cost curve via "
                             "coordinator._dry_service_s. NO LATENCY IN THIS FILE IS A "
                             "MEASUREMENT and none may be quoted as one."),
                 "is_measurement": False},
        "proofs": {},
    }

    # ---------------------------------------------------------------- PROOF 1
    print("PROOF 1: byte-identical decisions for every arm that is not %s" % PTG)
    p1: Dict[str, Any] = {
        "_register": ("OBSERVED, paired cells. BEFORE is a git archive of the origin sha, "
                      "verified file by file against its blob; AFTER is this build."),
        "_why_prove_what_holds_by_construction": (
            "The third EWMA class adds a dict key no existing arm reads and every new switch "
            "defaults OFF, so identity should hold BY CONSTRUCTION. It is proved anyway: 'no "
            "existing arm reads it' is exactly the kind of claim that has been wrong three times "
            "on this project today."),
        "arms": {}}
    arms_to_check = list(IDENTITY_ARMS) + [x.strip() for x in
                                           (a.extra_identity_arms or "").split(",")
                                           if x.strip()]
    p1["arms_checked"] = arms_to_check
    p1["arms_added_after_the_first_proof"] = [x for x in arms_to_check
                                              if x not in IDENTITY_ARMS]
    for arm in arms_to_check:
        IR = a.identity_run_s
        b1 = R.cell(BEFORE, arm, "p1_%s_before" % arm, run_s=IR)
        b2 = R.cell(BEFORE, arm, "p1_%s_before2" % arm, run_s=IR)
        a1 = R.cell(AFTER, arm, "p1_%s_after" % arm, run_s=IR)
        a2 = R.cell(AFTER, arm, "p1_%s_after2" % arm, run_s=IR)
        cb = compare(b1, b2, "A/A control BEFORE  %s" % arm)
        ca = compare(a1, a2, "A/A control AFTER   %s" % arm)
        mn = compare(b1, a1, "BEFORE vs AFTER     %s" % arm)
        want = COMMITTED_DRY300_DIGESTS.get(arm) if IR == 300.0 else None
        if want is None and IR == 300.0:
            print("    committed bar %-24s NONE: no committed dry-300 digest exists for "
                  "this arm, so its evidence is BEFORE vs AFTER plus its own A/A control, "
                  "NOT a committed bar" % arm)
        bar = None
        if want is not None:
            bar = {"committed_digest": want[0], "committed_rows": want[1],
                   "this_tree_digest": a1["decision_digest"],
                   "this_tree_rows": a1["n_decision_rows"],
                   "before_tree_digest": b1["decision_digest"],
                   "cell": COMMITTED_DIGEST_CELL,
                   "source": ("results/orchestration/live2/d222_pass1/"
                              "proof_ab_pristine_tree.json at b0767b46"),
                   "MATCHES": (a1["decision_digest"] == want[0]
                               and a1["n_decision_rows"] == want[1])}
            print("    committed bar %-24s want=%s got=%s rows %d/%d %s"
                  % (arm, want[0], a1["decision_digest"], a1["n_decision_rows"], want[1],
                     "MATCH" if bar["MATCHES"] else "*** MISMATCH ***"))
        p1["arms"][arm] = {
            "committed_digest_bar": bar,
            "aa_control_before": cb, "aa_control_after": ca, "before_vs_after": mn,
            "controls_clean": bool(cb["digests_equal"] and ca["digests_equal"]),
            "VERDICT": ("IDENTICAL" if mn["digests_equal"]
                        else "MOVED: %d positional differences" % mn["n_differing_positional"]),
            "cells": {k: {kk: v[kk] for kk in
                          ("decision_digest", "n_decision_rows", "loadavg_at_start",
                           "loadavg_at_end", "alone", "foreign_live2_at_start",
                           "foreign_live2_at_end", "guard_stats")}
                      for k, v in (("before", b1), ("before2", b2),
                                   ("after", a1), ("after2", a2))}}
    p1["cell_length_s"] = a.identity_run_s
    p1["committed_bar_all_match"] = all(
        (v.get("committed_digest_bar") or {}).get("MATCHES", True) for v in p1["arms"].values())
    p1["PASS"] = bool(all(v["before_vs_after"]["digests_equal"] and v["controls_clean"]
                          for v in p1["arms"].values()) and p1["committed_bar_all_match"])
    p1["_positive_control"] = (
        "COMMITTED_DRY300_DIGESTS is the positive control. Six of these arms are untouched by "
        "this build and the seventh, covex-v6-fair-final, is the comparator the variant is judged "
        "against, so all seven must still hash to their committed values IN THIS TREE. If any "
        "fails, the CHECK IS BROKEN AND NOT THE ARM and this proof's verdict is void.")
    RES["proofs"]["1_byte_identity_every_other_arm"] = p1

    if a.only_proof1:
        RES["proofs"]["1_byte_identity_every_other_arm"] = p1
        RES["SCOPE"] = ("PROOF 1 ONLY (--only-proof1). The other four proofs are NOT in this "
                        "file and no verdict about them may be read from it.")
        RES["ALL_PASS"] = bool(p1["PASS"])
        RES["VERDICTS"] = {"1_byte_identity_every_other_arm":
                           "PASS" if p1["PASS"] else "FAIL"}
        RES["all_cells"] = {k: {kk: vv for kk, vv in v.items() if kk != "rows_file"}
                            for k, v in R.by_tag.items()}
        out = Path(a.out) if a.out else (Path.cwd() / "d231_ptg_identity_only.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(RES, indent=1, default=str))
        print("\nwrote %s  (PROOF 1 ONLY)" % out)
        print("  PASS: %s   committed bars all match: %s"
              % (p1["PASS"], p1["committed_bar_all_match"]))
        return 0 if p1["PASS"] else 1

    # ---------------------------------------------------------------- the variant and its factors
    print("\nTHE VARIANT AND ITS ONE-FACTOR ARMS, all in THIS tree, one cell each")
    # *** THE COMPARATOR RUNS AT THE SAME CELL LENGTH AS THE TREATMENT. ***
    # The identity proof above runs at --identity-run-s (300 s, where a COMMITTED digest bar
    # exists); every variant cell below runs at --run-s (1200 s, the committed cell length).
    # Reusing the 300 s rung-3 cell as the comparator would have compared a 300 s log against
    # 1200 s logs and reported the cell length as a policy difference. That is the same
    # blindness as a comparator planning at one price while charged another: one side of the
    # comparison never audited. So rung 3 is run AGAIN here, at --run-s, with its own A/A.
    r3 = R.cell(AFTER, R3, "r3_at_variant_length")
    r3b = R.cell(AFTER, R3, "r3_at_variant_length_2")
    r3_aa = compare(r3, r3b, "A/A control  rung3 at the variant cell length")
    ptg = R.cell(AFTER, PTG, "ptg_both")
    nohyst = R.cell(AFTER, PTG + "-nohyst", "ptg_thresholds_only")
    hystonly = R.cell(AFTER, PTG + "-hystonly", "ptg_hysteresis_only")
    ctl20 = R.cell(AFTER, PTG + "-ctl20", "ctl20_neither")
    nolog = R.cell(AFTER, PTG + "-nolog", "ptg_both_without_the_log")
    r3glog = R.cell(AFTER, R3 + "-glog", "rung3_with_only_the_log")

    # ---------------------------------------------------------------- PROOF 2 (Step 2b)
    print("\nPROOF 2 (Step 2b): the switch reaches a decision")
    c_both = compare(r3, ptg, "rung3 vs ptg (BOTH mechanisms)")
    c_thr = compare(r3, nohyst, "rung3 vs ptg-nohyst (THRESHOLDS alone)")
    c_hys = compare(r3, hystonly, "rung3 vs ptg-hystonly (LATCH alone)")
    c_add = compare(nohyst, ptg, "ptg-nohyst vs ptg (the LATCH on top)")
    RES["proofs"]["2_step2b"] = {
        "_register": ("OBSERVED, both arms in THIS tree, ONE CELL LENGTH FOR BOTH SIDES "
                      "(--run-s), same instrument and same workload."),
        "comparator_aa_control": r3_aa,
        "headline": c_both,
        "attribution_one_factor_at_a_time": {
            "thresholds_alone_vs_rung3": c_thr,
            "hysteresis_alone_vs_rung3": c_hys,
            "latch_on_top_of_thresholds": c_add},
        "guard_stats": {"rung3": r3["guard_stats"], "ptg": ptg["guard_stats"],
                        "ptg_nohyst": nohyst["guard_stats"],
                        "ptg_hystonly": hystonly["guard_stats"]},
        "guard_log_summary_ptg": ptg.get("guard_log_summary"),
        "VERDICT": ("DIFFERING DECISIONS: the switch reaches a decision"
                    if not c_both["digests_equal"] else
                    "IDENTICAL LOGS: ABSENT LINK, NEVER a negative (CLAUDE.md Step 2b)"),
        "ATTRIBUTION_NOTE": (
            "A combined count that cannot be attributed is not a pass (addendum 12 item 5), so "
            "each mechanism is also run ALONE against rung 3. Read the three one-factor rows "
            "before the headline."),
    }

    # ---------------------------------------------------------------- PROOF 3
    print("\nPROOF 3: the characteristic decision, per channel")
    probe = R.cell(AFTER, PTG, "p3_alert_reachability_probe",
                   thresholds={"episodic": 0.3, "recall": 2.4, "assistance": 1.6})
    c_probe = compare(ptg, probe, "ptg vs ptg with ALERT threshold at 0.3 s")
    g = ptg.get("guard_log_summary") or {}
    gp = probe.get("guard_log_summary") or {}
    fb = g.get("fired_by_class", {})
    RES["proofs"]["3_characteristic_decision"] = {
        "_the_question": ("D230 (2): count guard activations attributable to the ALERT channel "
                          "under the new thresholds and confirm non-zero. The as-built guard "
                          "managed 16 across four seeds."),
        "OBSERVED_in_this_dry_cell": {
            "alert_channel_firings": fb.get("episodic"),
            "assistance_channel_firings": fb.get("assistance"),
            "recall_channel_firings": fb.get("recall"),
            "episodic_lag_s_min_max": g.get("episodic_min_max"),
            "assistance_lag_s_min_max": g.get("assistance_min_max"),
            "recall_lag_s_min_max": g.get("recall_min_max"),
            "latched_periods": g.get("n_latched"),
            "latched_without_entry": g.get("n_latched_without_entry"),
        },
        "WHY_THE_ALERT_COUNT_IS_ZERO_AND_WHAT_THAT_IS": (
            "*** A DRY CELL CANNOT TEST THIS AND THE ZERO IS NOT A NEGATIVE. *** "
            "`coordinator._dry_service_s` returns `costs.episodic_cloud_latency_s('32BI', 1, 25)` "
            "for EVERY monitor request: a CONSTANT 0.394966 s with no queueing term. The dry "
            "alert EWMA therefore takes exactly TWO values in a whole cell (0.0 before the first "
            "completion and 0.394966 after it) and CANNOT reach 0.8 s in any period. Assistance "
            "is the same shape at a different number. This is CLAUDE.md Rule 2's `unexercised` "
            "and it is a property of the dry harness, not of the variant. An OBSERVED "
            "alert-channel count can only come from a cell with a real engine under queueing, "
            "i.e. the s4 GPU cell, and it is PRE-REGISTERED as a check on that cell."),
        "POSITIVE_CONTROL_the_branch_is_reachable": {
            "_what": ("The same arm and the same cell with ONLY the alert threshold moved to "
                      "0.3 s, BELOW the dry constant, through the PRODUCTION setter "
                      "`arms_final_ladder._set_per_type_guard`. If the alert branch could not "
                      "reach a decision at all this would also fire zero times and move zero "
                      "decisions. IT IS A REACHABILITY CONTROL, NOT A RESULT, and 0.3 s is not a "
                      "threshold anyone proposes."),
            "thresholds_applied": probe.get("thresholds_applied"),
            "alert_channel_firings": (gp.get("fired_by_class", {}) or {}).get("episodic"),
            "active_periods": gp.get("n_active"),
            "first_alert_firing": gp.get("first_alert_firing"),
            "decisions_moved_against_ptg": c_probe["n_differing_positional"],
            "comparison": c_probe},
        "CONSTRUCTED_EXPECTATION_for_the_s4_cell": {
            "_source": ("results/orchestration/live2/d230_guard_thresholds/d230_guard_107.json "
                        "at 79eef689. CITED, NOT RE-DERIVED."),
            "alert_lag_ge_0.8s_s4": "251 of 12,000 decision periods, 2.0917 pct",
            "alert_lag_ge_0.8s_pooled_s4_to_s7": "497 of 47,997, 1.0355 pct",
            "alert_lag_ge_2.0s_pooled_the_as_built_bar": "16 of 47,997",
            "register": ("CONSTRUCTED BOUND from a validated replay: D230's own positive control "
                         "reproduced the committed `guard_by_lag` to within 0 to 3 epochs in "
                         "12,000 at every seed, and every fraction there is a LOWER bound "
                         "(missing request.jsonl rows). NOT an observed count from any cell this "
                         "build ran."),
            "why_it_is_not_an_equality": (
                "251 is neither a prediction nor a bar. The per-type guard also moves the RECALL "
                "bar from 2.0 to 2.4 s and adds the latch, both of which change which requests "
                "are warmed and therefore the EWMA trajectory itself. The replay is of the "
                "as-built arm's trace, so it says what the alert channel DID, not what it will "
                "do once the policy reacts differently.")},
    }

    # ---------------------------------------------------------------- PROOF 4 (Step 4)
    print("\nPROOF 4 (Step 4 negative controls)")
    c_ctl = compare(r3, ctl20, "rung3 vs ctl20 (thresholds 2.0/2.0/2.0, latch OFF)")
    RES["proofs"]["4_negative_controls"] = {
        "_what": ("The variant adds TWO mechanisms, so there are two controls and they are run "
                  "separately. The machinery stays FULLY LIVE in both: switch on, strict reader "
                  "passing, the per-type block executing, the log written."),
        "control_A_thresholds_disabled": {
            "_how": ("All three per-type thresholds set to the committed single 2.0 s bar AND the "
                     "latch off. That is the only setting that can collapse to rung 3 exactly, "
                     "because a control that left the latch on would fail for a reason other "
                     "than the thing being controlled."),
            "comparison": c_ctl,
            "guard_stats_ctl20": ctl20["guard_stats"],
            "VERDICT": ("COLLAPSES EXACTLY to %s" % R3 if c_ctl["digests_equal"]
                        else "DOES NOT COLLAPSE: %d positional differences"
                             % c_ctl["n_differing_positional"]),
            "RESIDUAL_RISK_STATED": (
                "The collapse is exact here and is NOT exact by construction. The committed test "
                "is `max(episodic, recall) >= 2.0`; the per-type test at 2.0/2.0/2.0 is "
                "`any(episodic, recall, ASSISTANCE >= 2.0)`, which also tests the THIRD channel. "
                "The two agree in this cell only because the dry assistance EWMA never reaches "
                "2.0 s. On a cell where assistance lag exceeds 2.0 s the control would differ, "
                "and that difference would be the third channel doing its job, not a defect.")},
        "control_A_MEASURED_AGREEMENT_not_argued": {
            "_what": ("The residual risk above says control A collapses only because the dry "
                      "assistance channel never reaches 2.0 s. That is an ARGUMENT. These are the "
                      "numbers that make it an OBSERVATION, recorded per run so a future cell "
                      "where assistance DOES cross 2.0 s shows up here instead of silently "
                      "breaking the collapse."),
            "committed_guard_activations_rung3_with_log": (r3glog.get("guard_log_summary") or {}
                                                           ).get("n_active"),
            "control_A_activations": (ctl.get("guard_log_summary") or {}).get("n_active"),
            "activations_equal": (((r3glog.get("guard_log_summary") or {}).get("n_active"))
                                  == ((ctl.get("guard_log_summary") or {}).get("n_active"))),
            "control_A_assistance_channel_min_max": (ctl.get("guard_log_summary") or {}
                                                     ).get("assistance_min_max"),
            "control_A_threshold_s": 2.0,
            "headroom_to_the_threshold_s": (
                None if not (ctl.get("guard_log_summary") or {}).get("assistance_min_max")
                else round(2.0 - (ctl["guard_log_summary"]["assistance_min_max"][1]), 6)),
            "assistance_ever_reached_the_threshold": (
                None if not (ctl.get("guard_log_summary") or {}).get("assistance_min_max")
                else bool(ctl["guard_log_summary"]["assistance_min_max"][1] >= 2.0)),
            "WHY_THE_COMMITTED_COUNT_IS_THE_RIGHT_COMPARATOR": (
                "`rung3_with_only_the_log` runs the COMMITTED two-channel "
                "`max(episodic, recall) >= 2.0` test and logs it, so its activation count is the "
                "committed guard's own behaviour ON THIS CELL. Control A runs "
                "`any(episodic, assistance, recall >= 2.0)`. Equal counts plus an assistance "
                "channel that never crosses is the evidence that the extra channel contributed "
                "nothing, which is exactly what the byte-identical digest implies and what this "
                "block shows independently of the digest."),
        },
        "control_B_hysteresis_disabled": {
            "_how": "The same variant with the latch off, which is the -nohyst arm.",
            "comparison": c_add,
            "guard_hysteresis_counters_when_on": {
                k: v for k, v in (ptg["guard_stats"] or {}).items() if "hyst" in k},
            "VERDICT": ("THE LATCH CHANGES THE RESULT: %d positional differences, so the "
                        "mechanism is driving something" % c_add["n_differing_positional"]
                        if not c_add["digests_equal"] else
                        "DISABLING THE LATCH CHANGES NOTHING in this cell: the hysteresis is NOT "
                        "driving the result here and must be classified, not reported as a "
                        "negative")},
    }

    # ---------------------------------------------------------------- PROOF 5
    print("\nPROOF 5: the per-period guard log changes no decision")
    c_log_ptg = compare(nolog, ptg, "ptg WITHOUT the log vs ptg WITH it")
    c_log_r3 = compare(r3, r3glog, "rung3 WITHOUT the log vs rung3 WITH it")
    RES["proofs"]["5_guard_log_is_decision_neutral"] = {
        "_what": ("D230 (2) limitation 1. Proved on BOTH sides: with the variant's mechanisms on, "
                  "and on rung 3 itself with the log as the ONLY difference, which is the "
                  "stronger of the two because nothing else can absorb a change."),
        "log_on_the_variant": c_log_ptg,
        "log_on_rung3_alone": c_log_r3,
        "rows_written_by_the_variant": ptg.get("guard_log_rows"),
        "rows_written_by_rung3_with_the_log": r3glog.get("guard_log_rows"),
        "periods_and_repeat_reads": {"ptg": ptg["guard_stats"],
                                     "rung3_glog": r3glog["guard_stats"]},
        "where_it_lands": ("<run dir>/guard_state.jsonl.gz, written by "
                           "coordinator.Live2Coordinator.write_guard_log and summarised in "
                           "coordinator_result.json under `guard_state_log`. NO FILE AT ALL for "
                           "an arm without the log, because the writer keys on the attribute "
                           "being absent."),
        "VERDICT": ("DECISION-NEUTRAL on both sides"
                    if (c_log_ptg["digests_equal"] and c_log_r3["digests_equal"])
                    else "THE LOG MOVED A DECISION: stop and investigate before anything else"),
    }

    RES["all_cells"] = {k: {kk: vv for kk, vv in v.items() if kk != "rows_file"}
                        for k, v in R.by_tag.items()}

    # The verdict line is read by people, so it must not print FAIL for a proof that passed.
    # Proofs 3 and 4 carry NESTED verdicts (proof 3 a reachability control plus a deferred s4
    # check, proof 4 two controls), so `v.get("VERDICT")` is None for them and a naive summariser
    # printed "FAIL" for both while ALL_PASS was True. A number in the wrong register is not a
    # wrong computation and survives every arithmetic check, so the register is fixed HERE, at the
    # point of use, and not only where it is derived.
    verdicts: Dict[str, Any] = {}
    for k, v in RES["proofs"].items():
        if "VERDICT" in v:
            verdicts[k] = v["VERDICT"]
        elif "PASS" in v:
            verdicts[k] = "PASS" if v["PASS"] else "FAIL"
        elif k.startswith("3_"):
            obs = v["OBSERVED_in_this_dry_cell"]
            pc = v["POSITIVE_CONTROL_the_branch_is_reachable"]
            verdicts[k] = (
                "ALERT CHANNEL UNEXERCISED IN A DRY CELL (%s firings), WHICH IS NOT A NEGATIVE: "
                "the dry monitor service time is a constant and cannot reach 0.8 s. The branch is "
                "REACHABLE (control: %s alert firings, %s decisions moved). The observed count is "
                "PRE-REGISTERED as a check on the s4 GPU cell."
                % (obs["alert_channel_firings"], pc["alert_channel_firings"],
                   pc["decisions_moved_against_ptg"]))
        elif k.startswith("4_"):
            verdicts[k] = "A: %s | B: %s" % (
                v["control_A_thresholds_disabled"]["VERDICT"],
                v["control_B_hysteresis_disabled"]["VERDICT"])
        else:
            verdicts[k] = "SEE THE BLOCK; no single-line verdict"
    RES["VERDICTS"] = verdicts
    RES["ALL_PASS"] = bool(RES["proofs"]["1_byte_identity_every_other_arm"]["PASS"]
                           and not RES["proofs"]["2_step2b"]["headline"]["digests_equal"]
                           and RES["proofs"]["4_negative_controls"][
                               "control_A_thresholds_disabled"]["comparison"]["digests_equal"]
                           and c_log_ptg["digests_equal"] and c_log_r3["digests_equal"])
    out = Path(a.out) if a.out else (Path.cwd() / "d231_ptg_guard_proofs.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RES, indent=1, default=str))
    print("\nwrote %s" % out)
    for k, v in verdicts.items():
        print("  %-42s %s" % (k, v))
    print("  ALL_PASS: %s" % RES["ALL_PASS"])
    return 0 if RES["ALL_PASS"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:                                                     # noqa: BLE001
        print("ERROR: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        sys.exit(2)
