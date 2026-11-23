#!/usr/bin/env python3
"""Proofs for the PER-DEVICE normalised deficit feed of covex-v6-fair (rung 3) and its 2 consumers.

ONE DRY CELL PER PROCESS, because dry decisions do not reproduce across runs INSIDE one process
(the OPEN DEFECT recorded in spec v6 section 12; the planner cutoff, PYTHONHASHSEED and the
registration context are all ruled out, and separate processes with identical setup DO reproduce).
Every cell is a subprocess of this script and decides nothing else.

  (a) IDENTITY, audited against values committed BEFORE this work and not only against this run's
      own other side. That includes VALIDATING THE CONTROL, which is the point of consistency check
      7: `hybrid_arm.py` gained a new leading sort key for this rung, and if prepending a neutral
      constant really cannot reorder anything then `covex-v6-state-shares`, `covex-v6-base` and
      `v5-rules-2` must still give their committed digests. A broken control passes every check
      applied to the treatment.
  (b) THE PRE-REGISTERED PASS CONDITION (addendum 12 item 5): gain 2.0 against gain 0 on the dry
      s4 cell MUST show differing decisions, and the count must be ATTRIBUTABLE TO A CONSUMER.
      "A combined count that cannot be attributed is not a pass." So the comparison is run four
      ways against the SAME gain-0 comparator: both consumers, ORDERING alone, SPLIT alone, and
      with the ordering shim removed. If none differ, this file REPORTS AND STOPS; rung 3 is then
      a NON-CONTRIBUTION and is never tuned.
  (c) THE WEIGHTS VARY, per device and over time, with min / median / max. A weight constant at 1.0
      everywhere means the feed is CONSTANT, which is a stopping condition and not a result.
  (d) STEP 4: gain 0 leaves every hook, counter and code path live, including BOTH consumers, and
      removes only the quantity under test. Every weight must be exactly 1.0, the ordering key must
      be the same constant for every device, and the arm must collapse to the rung-2 base.

THE DIGEST RECIPE IS THE ESTABLISHED ONE AND IS NOT RE-DERIVED HERE:

    sha256(json.dumps(rows_without_arm_version, sort_keys=True, separators=(',', ':'),
                      default=float)).hexdigest()[:16]

with the planner's wall-clock cutoff (`cf_instrument.over_budget`) patched OFF, exactly as
`c5attr_digest_proofs.py` and `d179_release_recheck_proofs.py` do, so a digest is a property of the
arm and not of how busy this host was. A digest is comparable ONLY within one recipe.

WHAT IS WIRED AND WHAT IS SHIMMED, said here rather than buried.

  CONSUMER 2, THE FLEXIBLE SPLIT, IS FULLY WIRED. The coordinator now reads
  `arm.live2_share_weights()` and passes it to `SA.allowed(weights_by_type=)`. No shim.

  CONSUMER 1, THE ORDERING, IS WIRED BUT CANNOT SEE THE DEVICE. `hybrid_arm.py`'s three call sites
  pass `getattr(<frozen dataclass>, "device_id", None)`, and neither `interface.EpisodicStream` nor
  `interface.RecallQuery` HAS that field, so every call receives None: measured, 10,956 calls in a
  180 s dry cell, ONE distinct argument value. A per-device weight then collapses to one value,
  which is exactly the failure that carrying `device_id` was meant to prevent. The one-line fix is
  named in this build's report and belongs to the owner of that file. `--order-shim` adds a
  `device_id` PROPERTY to those two dataclasses in the proof process only - `stream_id` for a
  dashcam stream, which IS its device id (the roster's `sh_instant` is keyed by exactly `dash000`
  to `dash005` and `hybrid_arm` looks items up in it by `stream_id`), and `session_id` for a recall
  query, which the arm's resolver maps through the roster's `session_device`. It changes nothing
  else. Both numbers are reported: with the shim, to show the consumer reaches a decision once it
  can see a device; without it, to show what the committed tree does today.

Usage:
    python d178_deficit_feed_proofs.py
    python d178_deficit_feed_proofs.py --one ARM [--order-shim] [--weights OUT.json]
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

# Digests COMMITTED BEFORE this work. These are the bar; they are audited, not assumed.
COMMITTED: Dict[str, Dict[str, Any]] = {
    "covex-v6-base": dict(digest="af8befb9420ad86a", rows=12085,
                          src="c5attr_digest_proofs.json P1 before-side (f2d617fa); "
                              "d179_share_admission_proofs.json off_switch_identity"),
    "v5-rules-2": dict(digest="18067c4c66bb44b8", rows=11955,
                       src="c5attr_digest_proofs.json P1 before-side (f2d617fa)"),
    "covex-v6-state-shares": dict(digest="3a5b40d78b9dcb3b", rows=13390,
                                  src="d179_share_admission_proofs.json step_2b shares_on; also "
                                      "reproduced by d178_deficit_feed_proofs.json before the "
                                      "hybrid_arm ordering hook existed"),
}


# --------------------------------------------------------------------------- one cell, one process
def _patch_planner_cutoff() -> None:
    import cf_instrument as CI
    for n in dir(CI):
        o = getattr(CI, n)
        if isinstance(o, type) and hasattr(o, "over_budget"):
            o.over_budget = lambda self, budget_ms=None: False


def _install_order_shim() -> Dict[str, Any]:
    """Give the two frozen observation dataclasses a `device_id` the ordering hook can read.

    PROOF ONLY, declared, and applied identically to BOTH sides of every comparison. A property is
    added to the CLASS; it is not a dataclass field, so no constructor and no existing reader
    changes. See the module docstring for why it is needed and whose one-line fix replaces it.
    """
    import interface as I
    before = (hasattr(I.EpisodicStream, "device_id"), hasattr(I.RecallQuery, "device_id"))
    if not hasattr(I.EpisodicStream, "device_id"):
        I.EpisodicStream.device_id = property(lambda self: self.stream_id)
    if not hasattr(I.RecallQuery, "device_id"):
        # the SESSION id, which the arm's resolver maps through the roster's session_device; the
        # shim does not do the mapping itself, so the production resolver is the thing under test
        I.RecallQuery.device_id = property(lambda self: self.session_id)
    return {"already_present_before_shim": list(before),
            "episodic_stream_device_id": "stream_id",
            "recall_query_device_id": "session_id (resolved by the arm through session_device)"}


def run_one(arm_name: str, *, order_shim: bool, weights_out: Optional[str]) -> Dict[str, Any]:
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
    shim = _install_order_shim() if order_shim else None
    import test_hybrid as TH

    samples: List[Dict[str, Any]] = []

    def patch(arm: Any) -> None:
        """Sample the per-device weights every decision period. Observation only, and applied to
        EVERY arm including the bases, so the two sides of a comparison carry identical
        instrumentation."""
        patch.arm = arm                                                   # type: ignore[attr-defined]
        feed = getattr(arm, "_feed", None)
        base_decide = arm.decide

        def decide(obs: Any) -> Any:
            act = base_decide(obs)
            if feed is not None:
                ws = {d: round(feed.weight_device(d), 6) for d in feed.devices()}
                if ws:
                    samples.append(dict(t=round(float(obs.now_s), 3), w=ws))
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
    res = dict(arm=arm_name, order_shim=bool(order_shim), shim=shim, seed=CELL["seed"],
               digest=digest, rows=len(rows),
               share_counts={k: v for k, v in sorted(st.items()) if str(k).startswith("share_")
                             and not isinstance(v, dict)},
               deficit_feed_completions=st.get("deficit_feed_completions"),
               n_weight_samples=len(samples), feed=feed)
    if weights_out:
        Path(weights_out).write_text(json.dumps(
            dict(arm=arm_name, order_shim=bool(order_shim), rows=rr, samples=samples, feed=feed),
            default=float) + "\n")
    return res


# --------------------------------------------------------------------------- the parent
def _cell(arm: str, *, shim: bool = False, keep: Optional[Path] = None) -> Dict[str, Any]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--one", arm]
    if shim:
        cmd.append("--order-shim")
    if keep is not None:
        cmd += ["--weights", str(keep)]
    env = dict(os.environ, PYTHONHASHSEED="0")
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=7200, env=env)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode or not line:
        return dict(arm=arm, order_shim=shim, error=(p.stderr or p.stdout)[-2000:])
    return json.loads(line[-1])


def _weight_stats(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per device, over time. PER DEVICE is the point: a per-type summary is what the superseded
    build reported and it hides exactly the spread the ordering consumer acts on."""
    per: Dict[str, List[float]] = {}
    for s in samples:
        for d, w in (s.get("w") or {}).items():
            per.setdefault(d, []).append(float(w))
    out: Dict[str, Any] = {}
    for d, v in sorted(per.items()):
        out[d] = dict(min=round(min(v), 6), median=round(statistics.median(v), 6),
                      max=round(max(v), 6), n=len(v),
                      distinct=len(set(round(x, 6) for x in v)))
    allv = [x for v in per.values() for x in v]
    out["_ALL"] = (dict(min=round(min(allv), 6), max=round(max(allv), 6),
                        constant_at_one=bool(allv and max(allv) == 1.0 == min(allv)),
                        devices=len(per),
                        devices_above_one=sum(1 for v in per.values() if max(v) > 1.0))
                   if allv else None)
    return out


def _diff(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    for p in (str(HERE), str(HERE / "hybrid")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_hybrid as TH
    first = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            first = dict(index=i, comparator=x, treatment=y)
            break
    if first is None and len(a) != len(b):
        n = min(len(a), len(b))
        first = dict(index=n, comparator=(a[n] if n < len(a) else None),
                     treatment=(b[n] if n < len(b) else None))
    return dict(positional=TH._differing(a, b), setwise=TH._differing_setwise(a, b),
                rows_comparator=len(a), rows_treatment=len(b), first_differing=first)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--one")
    ap.add_argument("--order-shim", action="store_true")
    ap.add_argument("--weights")
    a = ap.parse_args()
    if a.one:
        print(json.dumps(run_one(a.one, order_shim=a.order_shim, weights_out=a.weights),
                         default=float))
        return 0

    tmp = Path(os.environ.get("D178_SCRATCH", "/tmp")) / "d178_feed2"
    tmp.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=3)

    out: Dict[str, Any] = {
        "_what": ("the PER-DEVICE normalised deficit feed of covex-v6-fair (rung 3) and its two "
                  "consumers: identity against committed digests, the addendum 12 item 5 pass "
                  "condition with per-consumer attribution, the weight distribution, and the "
                  "gain-0 negative control"),
        "_protocol": ("ONE dry cell per process (subprocess), planner wall-clock cutoff patched "
                      "off, POSTED knobs forwarded, seed 4, 3 concurrent"),
        "_digest_recipe": ("sha256(json.dumps(rows without arm_version, sort_keys=True, "
                           "separators=(',',':'), default=float))[:16]; comparable only within "
                           "this recipe"),
        "_form": "w_d = 1 + 2.0 * (shortfall_d / target_d), floored at 1, PER DEVICE; the raw "
                 "unnormalised form is corrected in place in deficit_gain_d178.py and is NOT RUN",
        "_consumers": {
            "ordering": "PRIMARY. hybrid_arm._deficit_order_key, overridden on the inner "
                        "HybridArm instance to return the NEGATIVE w_d. WIRED but blind: the "
                        "committed call sites pass a device_id the frozen dataclasses do not "
                        "have, so --order-shim is needed until the one-line fix lands.",
            "flexible_split": "share_admission.py:162-168 through the coordinator's "
                              "SA.allowed(weights_by_type=) call site. FULLY WIRED, no shim."},
        "cell": dict(CELL), "committed_bar": COMMITTED,
    }

    # ---- (a) identity, and VALIDATE THE CONTROL after hybrid_arm gained the ordering hook
    a_futs = {arm: pool.submit(_cell, arm)
              for arm in ("covex-v6-base", "v5-rules-2", "covex-v6-state-shares",
                          "covex-v6-fair-shares-off")}
    a_rows = []
    for arm, fut in a_futs.items():
        r = fut.result()
        bar = COMMITTED.get(arm)
        r["committed"] = bar
        r["agrees"] = (None if bar is None
                       else bool(r.get("digest") == bar["digest"] and r.get("rows") == bar["rows"]))
        a_rows.append({k: v for k, v in r.items() if k != "feed"})
        print(json.dumps(a_rows[-1], default=float)[:260], flush=True)
    base = next(r for r in a_rows if r["arm"] == "covex-v6-state-shares")
    off = next(r for r in a_rows if r["arm"] == "covex-v6-fair-shares-off")
    out["a_identity"] = dict(
        _claim=("the new ordering hook moved no existing arm, and the switch off collapses to the "
                "rung-2 base; the bar is a value committed BEFORE this work"),
        rows=a_rows,
        control_validated=("covex-v6-state-shares is the COMPARATOR for every treatment below, so "
                           "its own digest is checked against a committed value FIRST: a broken "
                           "control passes every check applied to the treatment"),
        positive_control=("covex-v6-base and v5-rules-2 are known-good committed arms and must "
                          "pass; if one of them fails, the CHECK is broken, not the arm"),
        switch_off_identical=bool(off.get("digest") == base.get("digest")),
        verdict=("PASS" if all(r.get("agrees") is not False for r in a_rows)
                 and off.get("digest") == base.get("digest") else "FAIL"))

    # ---- (b) the pass condition, four ways against ONE comparator
    keep: Dict[str, Path] = {}
    futs = {}
    for tag, arm, shim in (("gain0", "covex-v6-fair-shares-gain0", True),
                           ("both", "covex-v6-fair-shares", True),
                           ("orderonly", "covex-v6-fair-shares-orderonly", True),
                           ("splitonly", "covex-v6-fair-shares-splitonly", True),
                           ("both_no_order_shim", "covex-v6-fair-shares", False)):
        f = tmp / ("rows_%s.json" % tag)
        keep[tag] = f
        futs[tag] = pool.submit(_cell, arm, shim=shim, keep=f)
    base_rows_f = tmp / "rows_base.json"
    base_fut = pool.submit(_cell, "covex-v6-state-shares", shim=False, keep=base_rows_f)
    cases = {t: f.result() for t, f in futs.items()}
    for t, c in cases.items():
        print(t, json.dumps({k: v for k, v in c.items() if k != "feed"}, default=float)[:240],
              flush=True)
    base_run = base_fut.result()

    def _rows(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["rows"]

    def _samples(p: Path) -> List[Dict[str, Any]]:
        return json.loads(p.read_text())["samples"]

    out["_base_rerun_for_rows"] = dict(
        digest=base_run.get("digest"), rows=base_run.get("rows"),
        agrees_with_first_run=bool(base_run.get("digest") == base.get("digest")),
        _why=("the rows themselves are needed for a row-level diff, and a dry cell does not "
              "reproduce inside one process, so the base is re-run in its OWN process and the two "
              "digests are compared before any diff is read"))

    g0 = _rows(keep["gain0"])
    attrib = {}
    for tag in ("both", "orderonly", "splitonly", "both_no_order_shim"):
        attrib[tag] = dict(
            arm=cases[tag].get("arm"), order_shim=cases[tag].get("order_shim"),
            digest=cases[tag].get("digest"), rows=cases[tag].get("rows"),
            identical_to_gain0=bool(cases[tag].get("digest") == cases["gain0"].get("digest")),
            diff_vs_gain0=_diff(g0, _rows(keep[tag])))
    moved_order = attrib["orderonly"]["diff_vs_gain0"]["setwise"]
    moved_split = attrib["splitonly"]["diff_vs_gain0"]["setwise"]
    moved_both = attrib["both"]["diff_vs_gain0"]["setwise"]
    out["b_pass_condition"] = dict(
        _claim=("addendum 12 item 5: gain 2.0 against gain 0 MUST show differing decisions, and "
                "the count MUST be attributable to a consumer"),
        comparator=dict(arm=cases["gain0"].get("arm"), digest=cases["gain0"].get("digest"),
                        rows=cases["gain0"].get("rows"),
                        _why=("gain 0 and not the rung-2 base: it leaves BOTH consumers live and "
                              "fully instrumented and removes only the quantity under test, so a "
                              "difference cannot be attributed to the plumbing")),
        gain0_equals_rung2_base=bool(cases["gain0"].get("digest") == base.get("digest")),
        by_consumer=attrib,
        attribution=dict(ordering_alone=moved_order, split_alone=moved_split,
                         both=moved_both,
                         additive=bool(moved_order + moved_split == moved_both),
                         _note=("ordering and split are not required to add up: they interact "
                                "through which request is admitted first. The three numbers are "
                                "reported separately rather than summed.")),
        verdict=("PASS" if moved_both > 0 else
                 "STOP: NO DIFFERING DECISIONS. Rung 3 is a NON-CONTRIBUTION and is NOT TUNED."))

    # ---- (c) the weights vary, per device
    out["c_weights_vary"] = dict(
        _claim=("the per-device weights vary across devices and over time; a weight constant at "
                "1.0 everywhere means the feed is CONSTANT, a stopping condition"),
        both=_weight_stats(_samples(keep["both"])),
        gain0=_weight_stats(_samples(keep["gain0"])),
        feed_at_end=cases["both"].get("feed"))

    # ---- (d) Step 4
    g0w = _weight_stats(_samples(keep["gain0"]))
    out["d_negative_control_gain0"] = dict(
        _claim=("gain 0 leaves every hook, counter and BOTH consumers live and removes only the "
                "quantity under test: every weight exactly 1.0 and a byte-identical collapse to "
                "the rung-2 base"),
        all_weights_one=bool((g0w.get("_ALL") or {}).get("constant_at_one")),
        devices_seen=(g0w.get("_ALL") or {}).get("devices"),
        digest=cases["gain0"].get("digest"), base_digest=base.get("digest"),
        identical_to_base=bool(cases["gain0"].get("digest") == base.get("digest")),
        verdict=("PASS" if (g0w.get("_ALL") or {}).get("constant_at_one")
                 and cases["gain0"].get("digest") == base.get("digest") else "FAIL"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote", OUT)
    bad = [k for k in ("a_identity", "d_negative_control_gain0")
           if str(out[k].get("verdict", "")).startswith("FAIL")]
    stop = str(out["b_pass_condition"]["verdict"]).startswith("STOP")
    print("FAILED:", bad if bad else "none", "| PASS CONDITION:",
          out["b_pass_condition"]["verdict"][:60])
    return 1 if (bad or stop) else 0


if __name__ == "__main__":
    raise SystemExit(main())
