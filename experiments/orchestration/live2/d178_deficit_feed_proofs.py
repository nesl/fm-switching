#!/usr/bin/env python3
"""Proofs for the D178 (1) per-type deficit feed of covex-v6-fair (rung 3), as the DEFICIT FEED ONLY.

FOUR PROOFS, each ONE DRY CELL PER PROCESS, because dry decisions do not reproduce across runs
INSIDE one process (the OPEN DEFECT recorded in spec v6 section 12; the planner cutoff,
PYTHONHASHSEED and the registration context are all ruled out, separate processes with identical
setup DO reproduce). Every cell is a subprocess of this script and decides nothing else.

  (a) SWITCHES OFF: every other arm byte-identical, audited against digests COMMITTED BEFORE this
      change (c5attr_digest_proofs.json's before side at f2d617fa, and
      d179_share_admission_proofs.json's off_switch_identity and step_2b blocks), not only against
      itself. That is consistency check 7: a side of the comparison that is never audited is the
      same blindness whether it is the control arm or the bar.
  (b) STEP 2b: the switch ON moves decisions, as a count of differing decision rows and the first
      one, SETWISE as well as positionally.
  (c) THE WEIGHTS VARY across types and over time: min / median / max per type over the run. A
      weight constant at 1.0 everywhere means the feed is CONSTANT, which is a stopping condition
      and not a result.
  (d) STEP 4 NEGATIVE CONTROL: gain 0 leaves every hook, counter and code path live and removes
      only the quantity under test. Every weight must be exactly 1.0 and the arm must collapse to
      the rung-2 base byte-identically.

THE DIGEST RECIPE IS THE ESTABLISHED ONE AND IS NOT RE-DERIVED HERE:

    sha256(json.dumps(rows_without_arm_version, sort_keys=True, separators=(',', ':'),
                      default=float)).hexdigest()[:16]

with the planner's wall-clock cutoff (`cf_instrument.over_budget`) patched OFF, exactly as
`c5attr_digest_proofs.py` and `d179_release_recheck_proofs.py` do, so a digest is a property of the
arm and not of how busy this host was. A digest is comparable ONLY within one recipe; a different
serialisation produced a phantom discrepancy on this box today.

THE PROOF-ONLY SHIM, DECLARED HERE AND NOT BURIED. The coordinator's single admission gate calls
`SA.allowed(...)` WITHOUT `weights_by_type` (coordinator.py:1437 (origin/main)), so against the committed
coordinator the feed's weights are computed and NOT READ: a write-only field, CLAUDE.md Step 2's
stopping condition. `--shim` patches `Live2Coordinator._share_ok` to forward
`arm.live2_share_weights()` into the SAME `SA.allowed` argument the one-line coordinator change
would use, and nothing else. Both numbers are reported: WITH the shim, to show the mechanism
reaches a decision when it is wired; WITHOUT it, to show it reaches none today. The un-shimmed
number is the one that describes the committed tree.

Usage:
    python d178_deficit_feed_proofs.py              # all proofs, writes the JSON
    python d178_deficit_feed_proofs.py --one ARM [--shim] [--weights OUT.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = REPO / "results/orchestration/live2/frozen_test/d178_deficit_feed_proofs.json"

CELL = dict(seed=4, n=16, run_s=1200.0, ratio="40:40:20", robot_question_set="lh_req",
            ss_question_set="ss2", dashcam_format="epg", robot_upload="per-frame",
            robot_reask_mean_s=30.0)

# Digests COMMITTED BEFORE this change. Sources named per row, and each is the SAME cell and the
# SAME recipe as the runs below. These are the bar; they are audited, not assumed.
COMMITTED: Dict[str, Dict[str, Any]] = {
    "covex-v6-state-uo": dict(digest="9a4be873eb3c5fba", rows=14218,
                              src="c5attr_digest_proofs.json P1 before (f2d617fa); "
                                  "d179_share_admission_proofs.json off_switch_identity"),
    "covex-v6-base": dict(digest="af8befb9420ad86a", rows=12085,
                          src="c5attr_digest_proofs.json P1 before (f2d617fa); "
                              "d179_share_admission_proofs.json off_switch_identity"),
    "v5-rules-2": dict(digest="18067c4c66bb44b8", rows=11955,
                       src="c5attr_digest_proofs.json P1 before (f2d617fa)"),
    "b7-edf-feasibility": dict(digest="b9aadd1c3a2b26d5", rows=12265,
                               src="c5attr_digest_proofs.json P1 before (f2d617fa)"),
    "covex-v6-state-shares": dict(digest="3a5b40d78b9dcb3b", rows=13390,
                                  src="d179_share_admission_proofs.json step_2b shares_on"),
}


# --------------------------------------------------------------------------- one cell, one process
def _patch_planner_cutoff() -> None:
    """The planner's wall-clock limit is patched OFF for a digest, as the committed proofs do."""
    import cf_instrument as CI
    for n in dir(CI):
        o = getattr(CI, n)
        if isinstance(o, type) and hasattr(o, "over_budget"):
            o.over_budget = lambda self, budget_ms=None: False


def _install_shim() -> None:
    """Forward the arm's per-type weights into `SA.allowed`, which is the ONE line the coordinator
    is missing. Declared, reversible, and applied identically to both sides of every comparison."""
    import coordinator as CO
    import share_admission as SA
    orig_ok = CO.Live2Coordinator._share_ok
    orig_allowed = SA.allowed

    def _share_ok(self: Any, **kw: Any) -> bool:
        getter = getattr(self.arm, "live2_share_weights", None)
        wt = getter() if callable(getter) else None

        def allowed(**kw2: Any) -> Any:
            kw2.setdefault("weights_by_type", wt)
            return orig_allowed(**kw2)

        SA.allowed = allowed
        try:
            return orig_ok(self, **kw)
        finally:
            SA.allowed = orig_allowed

    CO.Live2Coordinator._share_ok = _share_ok


def run_one(arm_name: str, *, shim: bool, weights_out: Optional[str]) -> Dict[str, Any]:
    for p in (str(HERE), str(HERE / "fleet"), str(HERE / "v5"), str(HERE / "hybrid"),
              str(HERE.parent / "baselines")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import arms as A
    import arms_v6fairfeed as FF
    import arms_v6state as VS
    VS.register()
    FF.register()
    _patch_planner_cutoff()
    if shim:
        _install_shim()
    import test_hybrid as TH

    samples: List[Dict[str, Any]] = []

    def patch(arm: Any) -> None:
        """Sample the weights the feed is producing, every decision period. Observation only.

        WRAPPED ON EVERY ARM, including the bases that have no weights to report, so the two sides
        of every comparison carry the identical instrumentation. Wrapping only the arm under test
        is an un-audited asymmetry between the sides, which is the shape consistency check 7 is
        about.
        """
        patch.arm = arm                                                   # type: ignore[attr-defined]
        getter = getattr(arm, "live2_share_weights", None)
        base_decide = arm.decide

        def decide(obs: Any) -> Any:
            act = base_decide(obs)
            w = getter() if callable(getter) else None
            if w is not None:
                samples.append(dict(t=round(float(obs.now_s), 3),
                                    **{k: round(float(v), 6) for k, v in w.items()}))
            return act
        arm.decide = decide

    rows, st = TH.dry(arm_name, CELL["seed"], CELL["n"], run_s=CELL["run_s"],
                      ratio=CELL["ratio"], robot_question_set=CELL["robot_question_set"],
                      ss_question_set=CELL["ss_question_set"],
                      dashcam_format=CELL["dashcam_format"], robot_upload=CELL["robot_upload"],
                      robot_reask_mean_s=CELL["robot_reask_mean_s"], patch=patch)
    rows = list(rows or [])
    rr = [{k: v for k, v in r.items() if k != "arm_version"} for r in rows]
    digest = hashlib.sha256(json.dumps(rr, sort_keys=True, separators=(",", ":"),
                                       default=float).encode()).hexdigest()[:16]
    st = dict(st or {})
    arm = getattr(patch, "arm", None)
    feed = arm.deficit_feed_report() if hasattr(arm, "deficit_feed_report") else None
    res = dict(arm=arm_name, shim=bool(shim), seed=CELL["seed"], digest=digest, rows=len(rows),
               share_counts={k: v for k, v in sorted(st.items()) if str(k).startswith("share_")
                             and not isinstance(v, dict)},
               deficit_feed_completions=st.get("deficit_feed_completions"),
               n_weight_samples=len(samples))
    if weights_out:
        Path(weights_out).write_text(json.dumps(
            dict(arm=arm_name, shim=bool(shim), rows=[{k: v for k, v in r.items()} for r in rr],
                 samples=samples, feed=feed), default=float) + "\n")
    res["feed"] = feed
    return res


# --------------------------------------------------------------------------- committed-cell replay
COMMITTED_CELL = (REPO / "results/orchestration/live2/frozen_test/runs"
                  / "covex-v6-state_n16_s5_1200s_h27_3t_L3_epg_rq30")

# An INDEPENDENT offline computation of the same three shortfalls, done directly from the
# committed cell before this feed existed, with the alert episode taken from `play_id` and
# `t_local` (episode = round((t_local - 3.0) / 0.5) // 21) rather than from the token law. It is
# the POSITIVE CONTROL for the feed's arithmetic: two different derivations of the episode must
# give the same shortfall, and if they disagree the FEED is wrong, not the cell.
INDEPENDENT = {"alert": 0.1427, "recall": 0.1048, "assistance": 0.0,
               "alert_episodes": 714, "alert_pooled_shortfall": 0.0411,
               "alert_flat19_on_true_episodes": 0.1467,
               "_how": ("episode from play_id and t_local (= round((t_local - 3.0)/0.5) // 21),"
                        " each episode's OWN instant count as denominator, numerator "
                        "cloud_payload.on_time"),
               "_why_the_two_differ": (
                   "the feed uses a DECLARED 19 instants per episode, so the truncated last "
                   "episode of each play is given 19 and its shortfall is overstated: flat 19 on "
                   "the true episodes is 0.1467 against 0.1427, and the feed's own episode "
                   "detection (707 of 714) brings it to about 0.1456. The bar below is therefore "
                   "0.01 absolute, which the 0.0029 difference clears, and the three numbers are "
                   "all reported so the denominator choice and the detection are separable")}


def replay_committed_cell() -> Dict[str, Any]:
    """Run the SAME `DeficitFeed` over a committed LIVE cell's own logs.

    WHY THIS IS HERE AND NOT OPTIONAL. A dry cell's service model delivers almost every alert
    instant on time, so the alert shortfall is zero there and the alert weight is UNEXERCISED in
    dry, exactly as the per-type host retention row of spec v6 section 12 is. A weight that is
    zero because the harness cannot reach the regime says nothing about the mechanism (Rule 1), so
    the quantity is shown to be non-zero and to vary in the regime the claim is about, on live
    committed data, through the same code.
    """
    import gzip
    for p in (str(HERE),):
        if p not in sys.path:
            sys.path.insert(0, p)
    import deficit_feed as DF
    import deficit_gain_d178 as GAIND
    out_f = COMMITTED_CELL / "outcomes.jsonl.gz"
    req_f = COMMITTED_CELL / "request.jsonl.gz"
    if not out_f.exists():
        return dict(error="committed cell not present: %s" % COMMITTED_CELL)
    outs = [json.loads(l) for l in gzip.open(out_f, "rt")]
    reqs = [json.loads(l) for l in gzip.open(req_f, "rt")]
    ont = {r["opportunity_id"]: bool((r.get("cloud_payload") or {}).get("on_time")) for r in outs}
    ev: List[Any] = []
    for r in outs:
        t = r.get("t_opportunity")
        ev.append((float(t if t is not None else 0.0), 0, r["device_id"], r["opportunity_id"],
                   r["kind"], None))
    for r in reqs:
        t = r.get("t_done")
        ev.append((float(t if t is not None else 0.0), 1, r["device_id"], r["opportunity_id"],
                   None, r.get("prompt_tokens")))
    ev.sort(key=lambda e: (e[0], e[1]))
    feed = DF.DeficitFeed(gain=GAIND.GAIN)
    for _t, what, did, oid, kind, pt in ev:
        if what == 0:
            if str(did)[:4] == "dash":
                feed.observe_offered_instant(did, oid)
            else:
                feed.observe_offered_question(did, oid)
        else:
            feed.observe_completion(device_id=did, kind=("monitor" if str(did)[:4] == "dash"
                                                         else "recall"),
                                    cloud_on_time=ont.get(oid, False), prompt_tokens=pt)
    rep = feed.as_dict()
    agree = {}
    for t in ("alert", "recall", "assistance"):
        got = float(rep["shortfall"][t])
        want = float(INDEPENDENT[t])
        agree[t] = dict(feed=round(got, 4), independent=want, delta=round(got - want, 4),
                        agrees=bool(abs(got - want) <= 0.01))
    return dict(cell=str(COMMITTED_CELL.name), feed=rep, independent=INDEPENDENT,
                agreement=agree,
                episodes_feed=rep["n_units"]["alert"],
                episodes_independent=INDEPENDENT["alert_episodes"],
                verdict=("PASS" if all(v["agrees"] for v in agree.values()) else "FAIL"))


# --------------------------------------------------------------------------- the parent
def _cell(arm: str, *, shim: bool = False, keep: Optional[Path] = None) -> Dict[str, Any]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", arm]
    if shim:
        cmd.append("--shim")
    if keep is not None:
        cmd += ["--weights", str(keep)]
    env = dict(os.environ, PYTHONHASHSEED="0")
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=7200, env=env)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode or not line:
        return dict(arm=arm, shim=shim, error=(p.stderr or p.stdout)[-2000:])
    return json.loads(line[-1])


def _weight_stats(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for t in ("alert", "recall", "assistance"):
        v = [float(s[t]) for s in samples if t in s]
        if not v:
            out[t] = None
            continue
        out[t] = dict(min=round(min(v), 6), median=round(statistics.median(v), 6),
                      max=round(max(v), 6), n=len(v),
                      distinct_values=len(set(round(x, 6) for x in v)),
                      constant_at_one=bool(max(v) == 1.0 and min(v) == 1.0))
    return out


def _diff(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Positional and setwise, both, with the first differing row. `test_hybrid._differing` and
    `_differing_setwise` are the committed definitions and are reused rather than re-invented."""
    for p in (str(HERE), str(HERE / "hybrid")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_hybrid as TH
    first = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            first = dict(index=i, base=x, feed=y)
            break
    if first is None and len(a) != len(b):
        n = min(len(a), len(b))
        first = dict(index=n, base=(a[n] if n < len(a) else None),
                     feed=(b[n] if n < len(b) else None))
    return dict(positional=TH._differing(a, b), setwise=TH._differing_setwise(a, b),
                rows_base=len(a), rows_feed=len(b), first_differing=first)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--shim", action="store_true")
    ap.add_argument("--weights")
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one, shim=a.shim, weights_out=a.weights), default=float))
        return 0

    tmp = Path(os.environ.get("D178_SCRATCH", "/tmp")) / "d178_feed"
    tmp.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Any] = {
        "_what": ("the D178 (1) per-type deficit feed of covex-v6-fair (rung 3): switch-off "
                  "identity against committed digests, Step 2b, the weight distribution, and the "
                  "gain-0 negative control"),
        "_protocol": ("ONE dry cell per process (subprocess), planner wall-clock cutoff patched "
                      "off, POSTED knobs forwarded, seeds 0/4/5/6/7 only"),
        "_digest_recipe": ("sha256(json.dumps(rows without arm_version, sort_keys=True, "
                           "separators=(',',':'), default=float))[:16]; comparable only within "
                           "this recipe"),
        "_shim": ("coordinator.py:1437 (origin/main) calls SA.allowed WITHOUT weights_by_type, so the weights "
                  "have no reader in the committed tree. --shim forwards "
                  "arm.live2_share_weights() into that one argument and changes nothing else. "
                  "Both the shimmed and the un-shimmed number are reported."),
        "cell": dict(CELL), "committed_bar": COMMITTED,
    }

    # ---- (a) every other arm byte-identical, against digests committed BEFORE this change
    # Cells run in PARALLEL PROCESSES, which is the same protocol as sequential ones: the defect
    # the one-cell-per-process rule works around is a second cell INSIDE one process, and separate
    # processes with identical setup reproduce exactly. Three at a time on a 24-core box.
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=3)
    a_futs = {arm: pool.submit(_cell, arm)
              for arm in ("covex-v6-base", "v5-rules-2", "b7-edf-feasibility",
                          "covex-v6-state-uo", "covex-v6-state-shares",
                          "covex-v6-state-uo-c5attr")}
    a_rows = []
    for arm, fut in a_futs.items():
        r = fut.result()
        bar = COMMITTED.get(arm)
        r["committed"] = bar
        r["agrees"] = (None if bar is None
                       else bool(r.get("digest") == bar["digest"] and r.get("rows") == bar["rows"]))
        a_rows.append(r)
        print(json.dumps(r, default=float)[:300], flush=True)
    out["a_other_arms_unchanged"] = dict(
        _claim=("no arm but the two new names decides differently after this change; the bar is a "
                "value committed BEFORE it, not this run's own other side"),
        rows=a_rows,
        positive_control=("b7-edf-feasibility and v5-rules-2 are known-good committed arms and "
                          "must pass; if one of them fails, the CHECK is broken, not the arm"),
        verdict=("PASS" if all(r.get("agrees") is not False for r in a_rows) else "FAIL"))

    # ---- the two rung-2 bases, as the comparators for (b) and (d)
    base_shares = next(r for r in a_rows if r["arm"] == "covex-v6-state-shares")
    base_c5 = next(r for r in a_rows if r["arm"] == "covex-v6-state-uo-c5attr")

    # ---- the feed, off / on-unshimmed / on-shimmed / gain-0-shimmed, on the shares base
    keep = {}
    futs = {}
    for tag, arm, shim in (("off", "covex-v6-fair-shares-off", False),
                           ("on_unshimmed", "covex-v6-fair-shares", False),
                           ("on_shimmed", "covex-v6-fair-shares", True),
                           ("gain0_shimmed", "covex-v6-fair-shares-gain0", True)):
        f = tmp / ("rows_%s.json" % tag)
        keep[tag] = f
        futs[tag] = pool.submit(_cell, arm, shim=shim, keep=f)
    base_rows_f = tmp / "rows_base_shares.json"
    base_fut = pool.submit(_cell, "covex-v6-state-shares", shim=False, keep=base_rows_f)
    c5_futs = {tag: pool.submit(_cell, arm, shim=shim)
               for tag, arm, shim in (("off", "covex-v6-fair-c5attr-off", False),
                                      ("on_shimmed", "covex-v6-fair-c5attr", True))}
    cases: Dict[str, Dict[str, Any]] = {}
    for tag, fut in futs.items():
        cases[tag] = fut.result()
        print(tag, json.dumps({k: v for k, v in cases[tag].items() if k != "feed"},
                              default=float)[:300], flush=True)
    base_run = base_fut.result()

    def _rows(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["rows"]

    def _samples(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["samples"]

    br = _rows(base_rows_f)
    out["_base_rerun_for_rows"] = dict(
        digest=base_run.get("digest"), rows=base_run.get("rows"),
        agrees_with_first_run=bool(base_run.get("digest") == base_shares.get("digest")),
        _why=("the rows themselves are needed for a row-level diff, and a dry cell does not "
              "reproduce inside one process, so the base is re-run in its OWN process and the two "
              "digests are compared before the diff is read"))

    out["a_switch_off_collapses"] = dict(
        _claim="with live2_deficit_feed OFF the rung-3 arm IS the rung-2 base, byte-identically",
        base=dict(digest=base_shares.get("digest"), rows=base_shares.get("rows"),
                  committed=COMMITTED["covex-v6-state-shares"]),
        off=dict(digest=cases["off"].get("digest"), rows=cases["off"].get("rows")),
        identical=bool(cases["off"].get("digest") == base_shares.get("digest")),
        verdict=("PASS" if cases["off"].get("digest") == base_shares.get("digest") else "FAIL"))

    out["b_step_2b"] = dict(
        _claim="the switch ON moves decisions; the number of differing rows and the first one",
        unshimmed=dict(
            digest=cases["on_unshimmed"].get("digest"), rows=cases["on_unshimmed"].get("rows"),
            identical_to_base=bool(cases["on_unshimmed"].get("digest")
                                   == base_shares.get("digest")),
            diff=_diff(br, _rows(keep["on_unshimmed"])),
            reading=("ZERO differing decisions against the committed coordinator is an ABSENT "
                     "LINK, never a negative: Rule 2's UNEXPRESSIBLE category. The channel the "
                     "mechanism acts through (weights_by_type) is discarded by the gate.")),
        shimmed=dict(
            digest=cases["on_shimmed"].get("digest"), rows=cases["on_shimmed"].get("rows"),
            identical_to_base=bool(cases["on_shimmed"].get("digest")
                                   == base_shares.get("digest")),
            diff=_diff(br, _rows(keep["on_shimmed"]))))

    out["c_weights_vary"] = dict(
        _claim=("the weights vary across types and over time; a weight constant at 1.0 everywhere "
                "means the feed is CONSTANT, which is a stopping condition"),
        on_shimmed=_weight_stats(_samples(keep["on_shimmed"])),
        on_unshimmed=_weight_stats(_samples(keep["on_unshimmed"])),
        feed=cases["on_shimmed"].get("feed"))

    g0 = _weight_stats(_samples(keep["gain0_shimmed"]))
    out["d_negative_control_gain0"] = dict(
        _claim=("gain 0 leaves every hook and counter live and removes only the quantity under "
                "test: every weight exactly 1.0 and a byte-identical collapse to the rung-2 base"),
        weights=g0,
        all_weights_one=all((v or {}).get("constant_at_one") for v in g0.values()),
        digest=cases["gain0_shimmed"].get("digest"), rows=cases["gain0_shimmed"].get("rows"),
        base_digest=base_shares.get("digest"),
        identical_to_base=bool(cases["gain0_shimmed"].get("digest") == base_shares.get("digest")),
        verdict=("PASS" if (all((v or {}).get("constant_at_one") for v in g0.values())
                            and cases["gain0_shimmed"].get("digest") == base_shares.get("digest"))
                 else "FAIL"))

    # ---- the c5attr contingency: the switch is harmless and the weights have NO reader there
    c5_cases = {}
    for tag, fut in c5_futs.items():
        c5_cases[tag] = fut.result()
        print("c5attr", tag, json.dumps({k: v for k, v in c5_cases[tag].items() if k != "feed"},
                                        default=float)[:240], flush=True)
    out["e_c5attr_base_has_no_reader"] = dict(
        _claim=("on the c5attr rung-2 base the weights have NO reader AT ALL, because that base "
                "carries no D179 share admission, so `_share_ok` returns before `SA.allowed` is "
                "reached and even the shim cannot deliver them. ABSENT LINK BY CONSTRUCTION, and "
                "the cells say so rather than the argument alone."),
        base=dict(digest=base_c5.get("digest"), rows=base_c5.get("rows")),
        off=dict(digest=c5_cases["off"].get("digest"), rows=c5_cases["off"].get("rows")),
        on_shimmed=dict(digest=c5_cases["on_shimmed"].get("digest"),
                        rows=c5_cases["on_shimmed"].get("rows"),
                        feed=(c5_cases["on_shimmed"].get("feed") or {}).get("weights")),
        off_identical=bool(c5_cases["off"].get("digest") == base_c5.get("digest")),
        on_identical=bool(c5_cases["on_shimmed"].get("digest") == base_c5.get("digest")))

    out["f_replay_committed_live_cell"] = replay_committed_cell()
    print("replay", json.dumps(out["f_replay_committed_live_cell"].get("agreement"),
                               default=float), flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote", OUT)
    bad = [k for k in ("a_other_arms_unchanged", "a_switch_off_collapses",
                       "d_negative_control_gain0")
           if out[k].get("verdict") == "FAIL"]
    print("FAILED:", bad if bad else "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
